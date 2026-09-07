"""
The daily collection schedule.

The slot is fixed, not chosen for speed. Fares move through the day, so a
series collected at 09:00 one day and 21:00 the next measures the clock as much
as the price. METHODOLOGY section 1 requires a fixed observation slot;
config/basket.yml declares it.

What is optimised is everything around the slot: a catch-up run if the machine
was asleep, resumption of only the cells that failed, and rate limiting that
respects each source's crawl delay.

A run is: compliance check -> collect 30 cells -> Bronze -> Silver -> Gold.
It is recorded before it starts, so a run that crashes halfway still leaves a
row. A day with no row means the scheduler never fired — a different failure
from one that fired and found nothing.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from apix.config import load_basket

log = logging.getLogger("apix.scheduler")

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[2]
DB_PATH = __import__("apix.config", fromlist=["db_path"]).db_path()

# One collection at a time, ever. Two overlapping runs would double-write
# Bronze and fight over the database.
_RUN_LOCK = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def slot_time() -> tuple[int, int]:
    """The declared observation slot, IST, from basket.yml."""
    raw = load_basket().observation_slot_ist
    try:
        h, m = raw.split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        log.warning("observation_slot_ist %r is unreadable; defaulting to 20:00", raw)
        return 20, 0


def already_collected(observation_date: date) -> bool:
    """Has a run for this day already finished successfully?"""
    with _conn() as c:
        row = c.execute(
            """SELECT 1 FROM collection_run
               WHERE observation_date = ? AND status IN ('OK','PARTIAL') LIMIT 1""",
            (observation_date.isoformat(),)).fetchone()
    return row is not None


def _start_run(observation_date: date, trigger: str) -> int:
    with _conn() as c:
        cur = c.execute(
            """INSERT INTO collection_run
                 (observation_date, trigger, started_at, status)
               VALUES (?,?,?, 'RUNNING')""",
            (observation_date.isoformat(), trigger, datetime.now(IST).isoformat()))
        return cur.lastrowid


def _finish_run(run_id: int, status: str, attempted: int, ok: int,
                sources: str, error: str | None = None) -> None:
    with _conn() as c:
        c.execute(
            """UPDATE collection_run
               SET finished_at=?, status=?, cells_attempted=?, cells_ok=?,
                   sources_used=?, error_detail=?
               WHERE id=?""",
            (datetime.now(IST).isoformat(), status, attempted, ok, sources,
             error, run_id))


def run_collection(observation_date: date | None = None, trigger: str = "SCHEDULED",
                   live: bool = True) -> dict:
    """One full cycle. Never raises -- a scheduler job that throws stops the
    scheduler, and a dead scheduler is a silently missing series."""
    obs = observation_date or datetime.now(IST).date()

    if not _RUN_LOCK.acquire(blocking=False):
        log.warning("collection already in progress; this trigger was dropped")
        return {"skipped": True, "reason": "a collection is already running"}

    run_id = _start_run(obs, trigger)
    attempted = ok = 0
    sources: list[str] = []
    try:
        from apix.collect.compliance import run_checks
        try:
            run_checks(on=obs)
        except Exception as exc:
            log.warning("compliance check failed (%s); the gate will refuse "
                        "anything it cannot verify", type(exc).__name__)

        adapters = []
        if live:
            try:
                from apix.collect.live_cleartrip import CleartripAdapter
                adapters.append(CleartripAdapter())
            except Exception as exc:
                log.error("live adapter unavailable: %s", exc)
        if not adapters:
            from apix.collect.replay import ReplayAdapter
            adapters.append(ReplayAdapter(anchor_date=obs))

        from apix.collect.runner import collect_day
        for a in adapters:
            s = collect_day(a, obs, resume=True)
            attempted += s.written + s.skipped_existing
            sources.append(a.source_id)
            log.info("collected: %s", s.line())

        # Count what the day actually HOLDS, not what this run happened to
        # write. A run that found every cell already collected did its job --
        # counting only new writes reported a complete day as FAILED.
        from apix.collect import bronze as _bronze
        ok = len({(r["route_code"], r["window_days"])
                  for r in _bronze.read_day(obs)
                  if r["fetch_status"] in ("OK", "SOLD_OUT")})

        from apix.load.loader import load_all
        load_all()
        from apix.index.engine import main as index_main
        index_main()
        try:
            from apix.load.evidence import main as ev_main
            ev_main([])
        except Exception:
            pass

        status = "OK" if ok >= 25 else ("PARTIAL" if ok else "FAILED")
        _finish_run(run_id, status, attempted, ok, ",".join(sources))
        return {"run_id": run_id, "status": status, "cells_ok": ok,
                "cells_attempted": attempted, "observation_date": obs.isoformat()}

    except Exception as exc:
        log.exception("collection run failed")
        _finish_run(run_id, "FAILED", attempted, ok, ",".join(sources),
                    f"{type(exc).__name__}: {str(exc)[:400]}")
        return {"run_id": run_id, "status": "FAILED", "error": str(exc)[:400]}
    finally:
        _RUN_LOCK.release()


_scheduler: BackgroundScheduler | None = None


def start(catch_up: bool = True) -> BackgroundScheduler:
    """Start the daily job. Idempotent -- calling it twice does not double-book."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    h, m = slot_time()
    _scheduler = BackgroundScheduler(timezone=IST, job_defaults={
        "coalesce": True,        # a missed window fires once, not N times
        "max_instances": 1,
        "misfire_grace_time": 3600,
    })
    _scheduler.add_job(run_collection, CronTrigger(hour=h, minute=m, timezone=IST),
                       id="daily_collection", replace_existing=True,
                       name=f"APIx daily collection, {h:02d}:{m:02d} IST")
    _scheduler.start()
    log.info("scheduler started; daily collection at %02d:%02d IST", h, m)

    if catch_up:
        # The machine may have been asleep at the slot. Collect today if today
        # has not been collected and the slot has passed.
        now = datetime.now(IST)
        today = now.date()
        if now.hour * 60 + now.minute >= h * 60 + m and not already_collected(today):
            log.info("slot already passed today and nothing collected; catching up")
            threading.Thread(target=run_collection, args=(today, "CATCHUP"),
                             daemon=True).start()
    return _scheduler


def stop() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("scheduler stopped")
    _scheduler = None


def status() -> dict:
    """What the scheduler is doing, for the admin dashboard."""
    h, m = slot_time()
    running = bool(_scheduler and _scheduler.running)
    nxt = None
    if running:
        job = _scheduler.get_job("daily_collection")
        if job and job.next_run_time:
            nxt = job.next_run_time.isoformat()

    with _conn() as c:
        runs = [dict(r) for r in c.execute(
            "SELECT * FROM collection_run ORDER BY started_at DESC LIMIT 10")]
    return {
        "running": running,
        "slot_ist": f"{h:02d}:{m:02d}",
        "next_run": nxt,
        "collected_today": already_collected(datetime.now(IST).date()),
        "recent_runs": runs,
    }
