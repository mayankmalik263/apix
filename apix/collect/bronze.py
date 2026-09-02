"""
Bronze: the raw archive.

Append-only newline-delimited JSON, one file per observation day per source:

    data/bronze/<observation_date>/<source_id>.jsonl

Deliberately files rather than database rows. Three reasons, all of which are
answers to questions a jury actually asks:

1. Airfare data cannot be collected retrospectively. If the database is
   dropped -- and during a two-day build it will be, several times -- the raw
   archive must survive. A file does. A table does not.

2. The collection layer must run before the database layer exists, so two
   people can work in parallel without one blocking the other.

3. "Where is your raw data?" is answered by opening a file, not by explaining
   a schema.

Nothing in this module parses a fare. Parsing happens downstream, in Silver,
and it happens against a copy of the bytes that is never modified. When the
parser breaks in week three, the history is re-parseable because the bytes
are still here.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from apix.collect.base import RawResponse
from apix.config import DATA_DIR

BRONZE_DIR = DATA_DIR / "bronze"

# The frozen wire format between collection (Mayank) and the database (Bharat).
# Adding a key is safe. Renaming or removing one is a breaking change and must
# be announced before it is committed.
FIELDS = (
    "observation_date",
    "route_code",
    "window_days",
    "departure_date",
    "source_id",
    "source_class",
    "fetch_status",
    "http_status",
    "request_url",
    "user_agent",
    "payload",
    "payload_sha256",
    "error_detail",
    "fetched_at_utc",
)


def day_dir(observation_date: date) -> Path:
    return BRONZE_DIR / observation_date.isoformat()


def path_for(observation_date: date, source_id: str) -> Path:
    return day_dir(observation_date) / f"{source_id}.jsonl"


def to_record(resp: RawResponse, fetched_at: datetime | None = None) -> dict:
    """RawResponse -> the frozen Bronze record."""
    ts = fetched_at or datetime.now(timezone.utc)
    return {
        "observation_date": resp.observation_date.isoformat(),
        "route_code": resp.route_code,
        "window_days": resp.window_days,
        "departure_date": resp.departure_date.isoformat(),
        "source_id": resp.source_id,
        "source_class": resp.source_class.value,
        "fetch_status": resp.fetch_status.value,
        "http_status": resp.http_status,
        "request_url": resp.request_url,
        "user_agent": resp.user_agent,
        "payload": resp.payload,
        "payload_sha256": resp.payload_sha256,
        "error_detail": resp.error_detail,
        "fetched_at_utc": ts.isoformat(),
    }


def append(resp: RawResponse, fetched_at: datetime | None = None) -> Path:
    """Append one observation. Creates the day folder on first write."""
    p = path_for(resp.observation_date, resp.source_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(to_record(resp, fetched_at), ensure_ascii=False) + "\n")
    return p


def append_many(responses: list[RawResponse]) -> int:
    for r in responses:
        append(r)
    return len(responses)


def read_day(observation_date: date, source_id: str | None = None) -> Iterator[dict]:
    """Stream Bronze records back. This is the function Bharat's loader calls.

    A malformed line is skipped rather than raising: one corrupt write must not
    make an entire day unreadable.
    """
    d = day_dir(observation_date)
    if not d.exists():
        return
    files = [path_for(observation_date, source_id)] if source_id else sorted(d.glob("*.jsonl"))
    for f in files:
        if not f.exists():
            continue
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def read_all() -> Iterator[dict]:
    if not BRONZE_DIR.exists():
        return
    for d in sorted(BRONZE_DIR.iterdir()):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            with f.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue


def existing_cells(observation_date: date, source_id: str) -> set[tuple[str, int]]:
    """(route, window) pairs already collected, so a re-run resumes rather
    than duplicating. Collection is expensive and rate-limited; repeating a
    cell we already have wastes the politeness budget."""
    return {
        (r["route_code"], int(r["window_days"]))
        for r in read_day(observation_date, source_id)
    }


def stats() -> dict:
    """Archive summary, for the CLI and the demo."""
    days: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    total = 0
    for rec in read_all():
        total += 1
        days[rec["observation_date"]] = days.get(rec["observation_date"], 0) + 1
        by_status[rec["fetch_status"]] = by_status.get(rec["fetch_status"], 0) + 1
        by_source[rec["source_id"]] = by_source.get(rec["source_id"], 0) + 1
    return {
        "total_records": total,
        "n_days": len(days),
        "first_day": min(days) if days else None,
        "last_day": max(days) if days else None,
        "by_status": by_status,
        "by_source": by_source,
    }
