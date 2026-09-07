"""
Two facts the system got wrong on 8 September 2026, both with the same cause:
a failed cell was being treated as a collected cell.

1. A refusal or a network failure counted as "already collected", so a re-run
   after the cause was fixed skipped the cell forever. Airfares cannot be
   collected retrospectively, so that silently loses a day.

2. Every non-OK row carries NULL carrier, flight_no and total_fare, so the
   Silver unique key could not tell a POLICY refusal from a SYSTEM failure and
   dropped the second one. Seven real FETCH_FAIL rows vanished behind that
   day's refusal rows.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from apix.collect import bronze
from apix.collect.base import RawResponse
from apix.vocab import ObsStatus, SourceClass

DAY = date(2026, 9, 8)


def _resp(window: int, status: ObsStatus) -> RawResponse:
    return RawResponse(
        source_id="testsrc",
        source_class=SourceClass.LIVE,
        observation_date=DAY,
        route_code="DEL-BOM",
        window_days=window,
        departure_date=DAY,
        fetch_status=status,
        payload="{}" if status is ObsStatus.OK else None,
    )


def test_only_market_results_count_as_collected(tmp_path, monkeypatch):
    monkeypatch.setattr(bronze, "BRONZE_DIR", tmp_path)
    bronze.append_many([
        _resp(1, ObsStatus.OK),
        _resp(7, ObsStatus.SOLD_OUT),          # MARKET: nothing to retry
        _resp(14, ObsStatus.SOURCE_DISALLOWED),  # POLICY: must be retried
        _resp(21, ObsStatus.FETCH_FAIL),         # SYSTEM: must be retried
    ])
    assert bronze.existing_cells(DAY, "testsrc") == {("DEL-BOM", 1), ("DEL-BOM", 7)}


def test_two_failure_reasons_for_one_cell_both_survive():
    conn = sqlite3.connect(":memory:")
    conn.executescript(open("db/schema.sql", encoding="utf-8").read())
    row = "2026-09-08", "DEL-BOM", 21, "2026-09-29", "cleartrip", "LIVE"
    for status, cls in (("SOURCE_DISALLOWED", "POLICY"), ("FETCH_FAIL", "SYSTEM")):
        conn.execute(
            "INSERT OR IGNORE INTO silver_fare_observation "
            "(observation_date, route_code, window_days, departure_date, "
            " source_id, source_class, status, status_class) "
            "VALUES (?,?,?,?,?,?,?,?)", (*row, status, cls))
    kept = {r[0] for r in conn.execute("SELECT status FROM silver_fare_observation")}
    assert kept == {"SOURCE_DISALLOWED", "FETCH_FAIL"}
