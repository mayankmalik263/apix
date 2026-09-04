"""
BHARAT — Round 2. Bronze files -> Silver table.

WHAT THIS DOES, IN ONE SENTENCE
    Reads the raw files the collector saved, pulls the fares out of them, and
    writes one clean row per flight quote into the database.

THE THREE RULES YOU MUST NOT BREAK
    1. Never change a Bronze file. Read only. Those are the raw evidence.
    2. Every record produces at least one Silver row, even the failures.
       A failed fetch still tells us something, so it gets a row with a status.
    3. Running this twice must not duplicate anything. Same row count both times.

Everything marked "TODO" is yours to write. The structure, the signatures and
the tricky bits are already here so you are not starting from a blank file.

RUN IT:
    python -m apix.load.loader
    python -m apix.load.loader      <- run again, count must be identical
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from pathlib import Path

from apix.collect import bronze
from apix.vocab import ObsStatus, status_class

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "apix.db"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# From METHODOLOGY.md section 5. Ayush confirmed these numbers.
MAD_THRESHOLD = 3.5
MAD_SCALE = 0.6745


# ---------------------------------------------------------------------------
# STEP 1 — open the database
# ---------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    """Open apix.db, creating the tables from your schema.sql if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


# ---------------------------------------------------------------------------
# STEP 2 — turn ONE Bronze record into the Silver rows it implies
# ---------------------------------------------------------------------------
def quotes_from_record(rec: dict) -> list[dict]:
    """Pull the list of flight quotes out of one Bronze record's payload.

    THERE ARE TWO PAYLOAD SHAPES. This is the bit people get wrong.

      - source_id == "cleartrip"  -> real data. Call parse_quotes(), which
                                     already exists and is already validated.
                                     DO NOT write your own Cleartrip parser.
      - anything else ("replay")  -> simulated data, shaped as
                                     {"quotes": [ ... ]}

    Both return the same dict per quote:
        carrier, flight_no, departure_time, stops,
        base_fare, taxes, fees, total_fare, currency

    Returns an empty list if there are no usable quotes.
    """
    payload = rec.get("payload")
    if not payload:
        return []

    if rec["source_id"] == "cleartrip":
        from apix.collect.live_cleartrip import parse_quotes
        # TODO: call parse_quotes(payload) and return the result.
        # Wrap it in try/except json.JSONDecodeError and return [] on failure --
        # the caller turns an empty list into a PARSE_FAIL row.
        raise NotImplementedError("BHARAT: call parse_quotes here")

    # TODO: simulated payload. json.loads it, return data.get("quotes") or [].
    raise NotImplementedError("BHARAT: parse the replay payload here")


def silver_rows_for(rec: dict) -> list[dict]:
    """One Bronze record -> the list of Silver rows to insert.

    THE LOGIC, IN ORDER:

      1. If rec["fetch_status"] is NOT "OK":
             return ONE row carrying that status, with every fare field None.
             This is how a blocked or failed cell still appears in the data,
             which is how coverage stays honest.

      2. Otherwise try to get the quotes.
             - quotes list is empty        -> ONE row, status SOLD_OUT
               (the search worked, nothing was for sale -- a market fact)
             - payload will not parse      -> ONE row, status PARSE_FAIL
               (our problem, not the market's)
             - quotes found                -> ONE row PER QUOTE, status OK

    Every row must carry both `status` and `status_class`. Use
    status_class(status) from apix.vocab -- do not type the class by hand.
    """
    base = {
        "observation_date": rec["observation_date"],
        "route_code": rec["route_code"],
        "window_days": rec["window_days"],
        "departure_date": rec["departure_date"],
        "source_id": rec["source_id"],
        "source_class": rec["source_class"],
    }

    def one(status: str) -> dict:
        return dict(
            base, status=status, status_class=status_class(status),
            carrier=None, flight_no=None, departure_time=None, stops=None,
            base_fare=None, taxes=None, fees=None, total_fare=None,
            currency="INR", is_outlier=0, outlier_score=None,
        )

    # TODO: implement the three cases described above, using one() for the
    # single-row cases. Return a list of dicts.
    raise NotImplementedError("BHARAT: this is the heart of the loader")


# ---------------------------------------------------------------------------
# STEP 3 — flag outliers WITHIN each cell
# ---------------------------------------------------------------------------
def modified_z_scores(values: list[float]) -> list[float]:
    """METHODOLOGY.md section 5.

        median = median(values)
        MAD    = median( |v - median| for each v )
        z(i)   = 0.6745 * (v_i - median) / MAD

    Two edge cases that must not crash:
        - fewer than 3 values -> return all zeros (nothing is an outlier)
        - MAD is exactly 0    -> return all zeros (every fare is identical)
    """
    # TODO: implement. Use statistics.median.
    raise NotImplementedError("BHARAT: MAD outlier scores")


def flag_outliers(rows: list[dict]) -> int:
    """Group the OK rows by (observation_date, route_code, window_days),
    score each group, and set is_outlier = 1 where |z| > MAD_THRESHOLD.

    FLAG. NEVER DELETE. A 4x fare is usually real -- we measured one at
    Rs 24,056 against a Rs 6,090 cheapest on the same route and date.
    Deleting it would be editing the market.

    Returns how many rows got flagged.
    """
    # TODO: implement.
    raise NotImplementedError("BHARAT: outlier flagging")


# ---------------------------------------------------------------------------
# STEP 4 — write to the database, without creating duplicates
# ---------------------------------------------------------------------------
INSERT_SQL = """
INSERT OR IGNORE INTO silver_fare_observation
    (observation_date, route_code, window_days, departure_date,
     source_id, source_class, status, status_class,
     carrier, flight_no, departure_time, stops,
     base_fare, taxes, fees, total_fare, currency,
     is_outlier, outlier_score)
VALUES
    (:observation_date, :route_code, :window_days, :departure_date,
     :source_id, :source_class, :status, :status_class,
     :carrier, :flight_no, :departure_time, :stops,
     :base_fare, :taxes, :fees, :total_fare, :currency,
     :is_outlier, :outlier_score)
"""
# "INSERT OR IGNORE" is what makes re-running safe. It only works if your
# schema.sql has the UNIQUE constraint on the logical flight key. If running
# the loader twice doubles your row count, that constraint is missing.


def load_all() -> dict:
    """Read every Bronze record, build Silver rows, flag outliers, insert.

    Returns a small summary dict so the CLI can print what happened.
    """
    conn = connect()
    all_rows: list[dict] = []
    n_bronze = 0

    for rec in bronze.read_all():
        n_bronze += 1
        all_rows.extend(silver_rows_for(rec))

    n_flagged = flag_outliers(all_rows)

    with conn:
        conn.executemany(INSERT_SQL, all_rows)

    total = conn.execute("SELECT COUNT(*) FROM silver_fare_observation").fetchone()[0]
    by_status = dict(
        conn.execute(
            "SELECT status, COUNT(*) FROM silver_fare_observation GROUP BY status"
        ).fetchall()
    )
    conn.close()
    return {
        "bronze_records": n_bronze,
        "silver_rows_built": len(all_rows),
        "silver_rows_in_db": total,
        "outliers_flagged": n_flagged,
        "by_status": by_status,
    }


def main() -> None:
    s = load_all()
    print("-" * 70)
    print(f"  bronze records read   {s['bronze_records']:>8}")
    print(f"  silver rows built     {s['silver_rows_built']:>8}")
    print(f"  silver rows in db     {s['silver_rows_in_db']:>8}   <- must not")
    print(f"  outliers flagged      {s['outliers_flagged']:>8}      change on a re-run")
    print("  by status:")
    for k, v in sorted(s["by_status"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:<22}{v:>8}")
    print("-" * 70)


if __name__ == "__main__":
    main()
