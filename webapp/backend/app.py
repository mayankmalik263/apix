"""APIx web application.

One process serves four things: the public dashboard, the open data feed it
reads, the keyed API for institutional consumers, and the scheduler that
collects at the declared daily slot.

    python -m webapp.run

Endpoints are declared once on a router and mounted twice — open at /public,
key-protected at /v1 — so the two tiers cannot drift apart.

Nothing here raises because data is missing. The app may start with no
database, no collection yet, or no network; endpoints return an empty result
and a reason instead.
"""
from __future__ import annotations

import json
import os
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from apix.collect import bronze
from apix.collect.compliance import report as compliance_report
from apix.config import db_path, load_basket
from webapp.backend import analytics, auth, scheduler
from webapp.backend.deps import db, require_scoped_access
from webapp.backend.routes_admin import router as admin_router

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s")
log = logging.getLogger("apix.web")

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "webapp" / "frontend"
DB_PATH = db_path()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Scheduler lifetime is tied to the app, so running it is one command.
    A failure to start is logged and the API serves anyway.

    APIX_SCHEDULER=off disables it outright. A public read-only deployment
    publishes numbers collected elsewhere: it has no browser installed, no
    business reaching an airline portal, and nothing to gain from trying.
    """
    if os.environ.get("APIX_SCHEDULER", "on").lower() in {"off", "0", "false", "no"}:
        log.info("scheduler disabled by APIX_SCHEDULER; serving read-only")
        yield
        return
    try:
        scheduler.start(catch_up=True)
    except Exception:
        log.exception("scheduler did not start; serving without it")
    yield
    try:
        scheduler.stop()
    except Exception:
        pass


limiter = Limiter(key_func=get_remote_address, default_limits=["600/minute"])

app = FastAPI(
    title="APIx — Real-time Airfare Price Index for India",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "A daily, route-level airfare price index built for augmentation of the "
        "Consumer Price Index. Every published value carries its coverage, a "
        "confidence grade, and a lineage path back to the stored payload.\n\n"
        "**SIH26056 · Ministry of Statistics and Programme Implementation**\n\n"
        "Every endpoint below is documented under `/v1`, which needs an API key. "
        "The same routes are open and unkeyed under `/public` — a published "
        "index is a public statistic, so reading it never requires a credential. "
        "Try [`/public/apix/latest`](/public/apix/latest), "
        "[`/public/apix/series`](/public/apix/series) or "
        "[`/public/methodology`](/public/methodology). The key protects write "
        "and operator routes, not the numbers."
    ),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


data = APIRouter()


# ---------------------------------------------------------------------------
# the index
# ---------------------------------------------------------------------------
@data.get("/overview", tags=["index"])
def overview(source_class: str = Query("LIVE"),
             freq: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
             conn: sqlite3.Connection = Depends(db)):
    """Everything the dashboard opens with, in one response."""
    return analytics.overview(conn, source_class, freq)


@data.get("/apix/series", tags=["index"])
def apix_series(source_class: str = Query("LIVE"),
                freq: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
                conn: sqlite3.Connection = Depends(db)):
    """The published series at daily, weekly or monthly frequency.

    Weekly and monthly are means of the daily index over the period, not the
    period's closing value — otherwise the figure would depend on which weekday
    the month happened to end on.
    """
    sc = analytics.effective_class(conn, source_class)
    rows = analytics.series(conn, sc, freq)
    return {"source_class": sc, "frequency": freq, "n": len(rows), "series": rows}


@data.get("/apix/latest", tags=["index"])
def apix_latest(source_class: str = Query("LIVE"),
                conn: sqlite3.Connection = Depends(db)):
    sc = analytics.effective_class(conn, source_class)
    rows = analytics.series(conn, sc, "daily")
    if not rows:
        return {"available": False, "reason": "no index computed yet"}
    return {"available": True, "source_class": sc, **rows[-1]}


@data.get("/routes/{code}/series", tags=["index"])
def route_series(code: str, source_class: str = Query("LIVE"),
                 conn: sqlite3.Connection = Depends(db)):
    sc = analytics.effective_class(conn, source_class)
    return {"route_code": code.upper(), "source_class": sc, "series": analytics._rows(conn, """
        SELECT observation_date, route_index, n_windows_used, n_observations, coverage
        FROM gold_route_index_daily WHERE route_code=? AND source_class=?
        ORDER BY observation_date""", code.upper(), sc)}


@data.get("/windows/{days}/series", tags=["index"])
def window_series(days: int, source_class: str = Query("LIVE"),
                  conn: sqlite3.Connection = Depends(db)):
    """One booking window across all routes.

    T+21 is the documented official domestic collection window, which makes
    that series directly comparable to the published item index.
    """
    sc = analytics.effective_class(conn, source_class)
    return {"window_days": days, "source_class": sc, "series": analytics._rows(conn, """
        SELECT observation_date, route_code, median_fare, price_relative, n_used, status
        FROM gold_cell_median WHERE window_days=? AND source_class=?
        ORDER BY observation_date, route_code""", days, sc)}


@data.get("/lead-time", tags=["index"])
def lead_time(source_class: str = Query("LIVE"), observation_date: str | None = None,
              conn: sqlite3.Connection = Depends(db)):
    """Lead-time elasticity: median fare against how far ahead the seat is booked."""
    sc = analytics.effective_class(conn, source_class)
    return analytics.lead_time(conn, sc, observation_date)


@data.get("/composition", tags=["index"])
def composition(source_class: str = Query("LIVE"), observation_date: str | None = None,
                conn: sqlite3.Connection = Depends(db)):
    """Base fare separated from taxes and fees, overall and per route."""
    sc = analytics.effective_class(conn, source_class)
    return analytics.composition(conn, sc, observation_date)


@data.get("/mospi", tags=["index"])
def mospi():
    """The official published airfare item index that APIx sits beside."""
    p = ROOT / "data" / "mospi_airfare_index.json"
    if not p.exists():
        return {"available": False, "reason": "extract not present"}
    return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}


@data.get("/basket", tags=["index"])
def basket():
    """Routes, windows and weights. Configuration, not code."""
    b = load_basket()
    return {
        "method_version": b.method_version,
        "routes": [{"code": r.code, "origin": r.origin, "destination": r.destination,
                    "origin_city": r.origin_city, "destination_city": r.destination_city,
                    "weight": r.weight} for r in b.routes],
        "windows": b.windows,
        "cells_per_day": b.cells_per_day,
        "spec": b.spec,
        "observation_slot_ist": b.observation_slot_ist,
        "weights_provisional": b.weights_provisional,
        "effective_weights": b.effective_weights(),
    }


# ---------------------------------------------------------------------------
# provenance and compliance
# ---------------------------------------------------------------------------
@data.get("/lineage/{observation_date}/{route}/{window}", tags=["provenance"])
def lineage(observation_date: str, route: str, window: int,
            source_class: str = Query("LIVE"), conn: sqlite3.Connection = Depends(db)):
    """A published cell median back to the fares behind it and the stored
    payload those fares were parsed from, with its SHA-256."""
    try:
        date.fromisoformat(observation_date)
    except ValueError:
        raise HTTPException(400, "observation_date must be YYYY-MM-DD")
    sc = analytics.effective_class(conn, source_class)
    out = analytics.lineage(conn, observation_date, route, window, sc)
    if not out["silver"] and not out["bronze"]:
        raise HTTPException(404, f"nothing collected for {route.upper()} "
                                 f"T+{window} on {observation_date}")
    return out


@data.get("/compliance/report", tags=["provenance"])
def compliance(on: str | None = None):
    """Which sources were permitted on a given day, with the hash of the
    robots.txt actually read."""
    d = date.fromisoformat(on) if on else date.today()
    rows = compliance_report(d)
    return {"checked_on": d.isoformat(),
            "permitted": sum(1 for r in rows if r["verdict"] == "PERMITTED"),
            "total": len(rows), "sources": rows}


@data.get("/bronze/stats", tags=["provenance"])
def bronze_stats():
    """What the immutable raw archive holds."""
    return bronze.stats()


@data.get("/methodology", response_class=PlainTextResponse, tags=["provenance"])
def methodology():
    p = ROOT / "METHODOLOGY.md"
    return p.read_text(encoding="utf-8") if p.exists() else "not found"


# ---------------------------------------------------------------------------
# open tier, keyed tier, admin
# ---------------------------------------------------------------------------
app.include_router(data, prefix="/public", include_in_schema=False)
app.include_router(data, prefix="/v1", dependencies=[Depends(require_scoped_access)])
app.include_router(admin_router)


@app.get("/v1/health", tags=["meta"])
def health(conn: sqlite3.Connection = Depends(db)):
    return {"status": "ok", "database": DB_PATH.exists(),
            "published_days": analytics._one(conn, "SELECT COUNT(*) FROM gold_apix_daily")}


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------
def _page(name: str):
    f = FRONTEND / name
    if not f.exists():
        return PlainTextResponse(f"{name} is missing from webapp/frontend/", 404)
    return FileResponse(f, headers={"Cache-Control": "no-store"})


@app.get("/", include_in_schema=False)
def page_index():
    return _page("index.html")


@app.get("/login", include_in_schema=False)
def page_login():
    return _page("login.html")


@app.get("/console", include_in_schema=False)
def page_console(request: Request):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        user = auth.read_session(conn, request.cookies.get(auth.SESSION_COOKIE))
    finally:
        conn.close()
    if user is None:
        return RedirectResponse("/login?next=/console", status_code=303)
    return _page("console.html")


ASSETS = {".css": "text/css", ".js": "application/javascript", ".html": "text/html",
          ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2",
          ".json": "application/json", ".ico": "image/x-icon"}


@app.get("/{asset:path}", include_in_schema=False)
def static_asset(asset: str):
    """Serve the frontend's own files. Registered last so it cannot shadow an
    API route, and resolved inside the frontend directory so a path with .. in
    it cannot escape it."""
    if Path(asset).suffix.lower() not in ASSETS:
        raise HTTPException(404, "Not found")
    target = (FRONTEND / asset).resolve()
    if not str(target).startswith(str(FRONTEND.resolve())) or not target.is_file():
        raise HTTPException(404, "Not found")
    # no-store on the frontend assets: a judge opening this on a laptop that
    # cached an older build would silently see the wrong dashboard.
    return FileResponse(target, media_type=ASSETS[Path(asset).suffix.lower()],
                        headers={"Cache-Control": "no-store"})
