"""Admin, session and live-system routes."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from webapp.backend import analytics, auth, scheduler
from webapp.backend.deps import client_ip, current_user, db, require_admin

IST = ZoneInfo("Asia/Kolkata")

router = APIRouter()


# ---------------------------------------------------------------------------
# session
# ---------------------------------------------------------------------------
@router.post("/auth/login", include_in_schema=False)
def login(request: Request, response: Response,
          email: str = Form(...), password: str = Form(...),
          conn: sqlite3.Connection = Depends(db)):
    user, reason = auth.authenticate(conn, email, password)
    if user is None:
        return RedirectResponse(f"/login?error={reason.replace(' ', '+')}",
                                status_code=303)
    r = RedirectResponse("/admin", status_code=303)
    r.set_cookie(
        auth.SESSION_COOKIE, auth.issue_session(user),
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,            # JavaScript can never read it
        samesite="lax",           # not sent on cross-site POSTs
        secure=request.url.scheme == "https",
    )
    return r


@router.post("/auth/logout", include_in_schema=False)
def logout():
    r = RedirectResponse("/", status_code=303)
    r.delete_cookie(auth.SESSION_COOKIE)
    return r


@router.get("/auth/me", tags=["admin"])
def me(user=Depends(current_user)):
    if user is None:
        return {"signed_in": False}
    return {"signed_in": True, "email": user.email,
            "display_name": user.display_name, "role": user.role}


# ---------------------------------------------------------------------------
# live system status — what makes the page feel alive
# ---------------------------------------------------------------------------
@router.get("/v1/system/status", tags=["system"])
def system_status(conn: sqlite3.Connection = Depends(db)):
    """Everything the front page needs to tick: server clock, the next
    collection, and whether one is happening right now."""
    st = scheduler.status()
    now = datetime.now(IST)

    next_iso = st["next_run"]
    if not next_iso:
        # The scheduler is not running (or is between jobs). Work out the next
        # slot from the declared time so the countdown never goes blank.
        h, m = scheduler.slot_time()
        nxt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        next_iso = nxt.isoformat()

    seconds_to_next = max(0, int((datetime.fromisoformat(next_iso) - now).total_seconds()))

    def one(sql, *a):
        try:
            return conn.execute(sql, a).fetchone()[0]
        except sqlite3.OperationalError:
            return 0

    running = any(r["status"] == "RUNNING" for r in st["recent_runs"])

    # Bronze is files rather than a table, so the mirror table is empty and
    # counting it reported 0 records on a full archive.
    try:
        from apix.collect import bronze as _bronze
        bstats = _bronze.stats()
    except Exception:
        bstats = {"total_records": 0, "n_days": 0, "last_day": None}

    return {
        "server_time_ist": now.isoformat(),
        "scheduler_running": st["running"],
        "collection_in_progress": running,
        "slot_ist": st["slot_ist"],
        "next_run": next_iso,
        "seconds_to_next_run": seconds_to_next,
        "collected_today": st["collected_today"],
        "counts": {
            "bronze_records": bstats["total_records"],
            "bronze_days": bstats["n_days"],
            "last_collection_day": bstats["last_day"],
            "silver_rows": one("SELECT COUNT(*) FROM silver_fare_observation"),
            "published_days": one("SELECT COUNT(*) FROM gold_apix_daily"),
            "live_days": one("SELECT COUNT(*) FROM gold_apix_daily WHERE source_class='LIVE'"),
            "outliers_flagged": one("SELECT COUNT(*) FROM silver_fare_observation WHERE is_outlier=1"),
            "active_api_keys": one("SELECT COUNT(*) FROM api_key WHERE revoked_at IS NULL"),
            "api_calls_24h": one(
                "SELECT COUNT(*) FROM api_access_log WHERE at_utc > datetime('now','-1 day')"),
        },
        "recent_runs": st["recent_runs"][:5],
    }


# ---------------------------------------------------------------------------
# admin — API keys
# ---------------------------------------------------------------------------
@router.get("/console/api/keys", tags=["admin"])
def list_keys(user=Depends(require_admin), conn: sqlite3.Connection = Depends(db)):
    rows = [dict(r) for r in conn.execute(
        """SELECT id, prefix, label, organisation, scopes, rate_per_min,
                  created_at, expires_at, revoked_at, revoked_reason,
                  last_used_at, request_count
           FROM api_key ORDER BY revoked_at IS NOT NULL, created_at DESC""")]
    for r in rows:
        r["status"] = ("revoked" if r["revoked_at"] else
                       "expired" if r["expires_at"] and r["expires_at"] < datetime.now(IST).isoformat()
                       else "active")
    return {"keys": rows}


@router.post("/console/api/keys", tags=["admin"])
def create_key(payload: dict, user=Depends(require_admin),
               conn: sqlite3.Connection = Depends(db)):
    """Mint a key. The key itself appears in this response and nowhere else,
    ever again -- not in the list, not in the logs, not in the database."""
    label = (payload.get("label") or "").strip()
    if not label:
        raise HTTPException(400, "Give the key a label, so it can be recognised later.")

    scopes = payload.get("scopes") or "read:index"
    allowed = {"read:index", "read:lineage", "read:compliance"}
    bad = [s for s in (x.strip() for x in scopes.split(",")) if s and s not in allowed]
    if bad:
        raise HTTPException(400, f"Unknown scope(s): {', '.join(bad)}. "
                                 f"Allowed: {', '.join(sorted(allowed))}.")
    try:
        rate = int(payload.get("rate_per_min") or 60)
        expires = payload.get("expires_days")
        expires = int(expires) if expires not in (None, "", "never") else None
    except (TypeError, ValueError):
        raise HTTPException(400, "Rate limit and expiry must be whole numbers.")
    if not 1 <= rate <= 6000:
        raise HTTPException(400, "Rate limit must be between 1 and 6000 per minute.")

    raw, row = auth.mint_api_key(
        conn, label, (payload.get("organisation") or "").strip() or None,
        user.id, scopes, rate, expires)
    return {"key": raw, "record": row,
            "warning": "Copy this now. It is not stored and cannot be shown again."}


@router.post("/console/api/keys/{key_id}/revoke", tags=["admin"])
def revoke(key_id: int, payload: dict | None = None, user=Depends(require_admin),
           conn: sqlite3.Connection = Depends(db)):
    reason = ((payload or {}).get("reason") or "revoked by operator").strip()
    if not auth.revoke_key(conn, key_id, reason):
        raise HTTPException(404, "No active key with that id — it may already be revoked.")
    return {"revoked": key_id, "reason": reason}


@router.get("/console/api/access-log", tags=["admin"])
def access_log(limit: int = 100, user=Depends(require_admin),
               conn: sqlite3.Connection = Depends(db)):
    limit = max(1, min(limit, 1000))
    return {"entries": [dict(r) for r in conn.execute(
        """SELECT l.id, l.path, l.status_code, l.ip, l.at_utc,
                  k.label, k.prefix
           FROM api_access_log l LEFT JOIN api_key k ON k.id = l.api_key_id
           ORDER BY l.at_utc DESC LIMIT ?""", (limit,))]}


# ---------------------------------------------------------------------------
# admin — operations
# ---------------------------------------------------------------------------
@router.post("/console/api/collect-now", tags=["admin"])
def collect_now(user=Depends(require_admin)):
    """Trigger a collection by hand. Returns immediately; the run happens in a
    thread and its progress shows up in /v1/system/status."""
    import threading
    if scheduler._RUN_LOCK.locked():
        return JSONResponse({"started": False,
                             "reason": "A collection is already running."}, 409)
    threading.Thread(target=scheduler.run_collection,
                     kwargs={"trigger": "MANUAL"}, daemon=True).start()
    return {"started": True, "message": "Collection started. Watch the status strip."}


@router.get("/console/api/runs", tags=["admin"])
def runs(limit: int = 50, user=Depends(require_admin),
         conn: sqlite3.Connection = Depends(db)):
    limit = max(1, min(limit, 500))
    return {"runs": [dict(r) for r in conn.execute(
        "SELECT * FROM collection_run ORDER BY started_at DESC LIMIT ?", (limit,))]}
