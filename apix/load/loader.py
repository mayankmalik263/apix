"""Bronze files -> Silver table.

Reads the raw responses the collector archived, pulls the fares out, and writes
one row per flight quote.

Three constraints the rest of the pipeline depends on:
  - Bronze files are read-only. They are the evidence.
  - Every record produces at least one row, failures included. A cell with no
    row is indistinguishable from a cell nobody tried.
  - Re-running is a no-op. Same row count every time.

    python -m apix.cli load
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from pathlib import Path

from apix.collect import bronze
from apix.vocab import ObsStatus, status_class

ROOT = Path(__file__).resolve().parents[2]
from apix.config import db_path

DB_PATH = db_path()
SCHEMA_PATH = ROOT / "db" / "schema.sql"

# METHODOLOGY.md section 5.
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
        try:
            return parse_quotes(payload)
        except (json.JSONDecodeError, AttributeError, TypeError):
            # A shape we did not expect. Say so by returning nothing and let
            # the caller record PARSE_FAIL -- the payload is still in Bronze,
            # so the day is re-parseable once the parser is fixed.
            return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    return data.get("quotes") or []


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
            currency="INR", fare_ref=None, is_outlier=0, outlier_score=None,
        )

    # 1. The fetch never succeeded. One row carrying the reason, no fares.
    #    The cell is still represented, which is what keeps coverage honest:
    #    a BLOCKED cell and a cell nobody tried are different facts.
    if rec["fetch_status"] != "OK":
        return [one(rec["fetch_status"])]

    quotes = quotes_from_record(rec)

    # 2. Fetched fine, nothing came back. Two different reasons, and the
    #    the difference is what the vocabulary exists to record:
    #
    #      payload present but yielded nothing  -> PARSE_FAIL, our fault
    #      payload was an empty result set      -> SOLD_OUT, the market's answer
    #
    #    Both look like "no price". Only one is a failure.
    if not quotes:
        if not rec.get("payload"):
            return [one(ObsStatus.PARSE_FAIL.value)]
        try:
            data = json.loads(rec["payload"])
            empty_result = isinstance(data, dict) and "quotes" in data
        except (json.JSONDecodeError, TypeError):
            empty_result = False
        return [one(ObsStatus.SOLD_OUT.value if empty_result
                    else ObsStatus.PARSE_FAIL.value)]

    # 3. Quotes found. One Silver row per quote, all of them OK.
    rows = []
    for q in quotes:
        if q.get("total_fare") is None:
            continue
        rows.append(dict(
            base, status=ObsStatus.OK.value,
            status_class=status_class(ObsStatus.OK.value),
            carrier=q.get("carrier"),
            flight_no=q.get("flight_no"),
            departure_time=q.get("departure_time"),
            stops=q.get("stops"),
            base_fare=q.get("base_fare"),
            taxes=q.get("taxes"),
            fees=q.get("fees"),
            total_fare=float(q["total_fare"]),
            currency=q.get("currency") or "INR",
            fare_ref=q.get("fare_ref"),
            is_outlier=0, outlier_score=None,
        ))

    # Every quote carried a null fare. Parsed, but useless.
    return rows or [one(ObsStatus.PARSE_FAIL.value)]


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
    if len(values) < 3:
        return [0.0] * len(values)

    med = statistics.median(values)
    mad = statistics.median([abs(v - med) for v in values])
    if mad == 0:
        # Every fare identical. There is no dispersion to be an outlier from,
        # and dividing by zero here would flag the entire cell.
        return [0.0] * len(values)

    return [MAD_SCALE * (v - med) / mad for v in values]


def flag_outliers(rows: list[dict]) -> int:
    """Group the OK rows by (observation_date, route_code, window_days),
    score each group, and set is_outlier = 1 where |z| > MAD_THRESHOLD.

    FLAG. NEVER DELETE. A 4x fare is usually real -- we measured one at
    Rs 24,056 against a Rs 6,090 cheapest on the same route and date.
    Deleting it would be editing the market.

    Returns how many rows got flagged.
    """
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        if r["status"] != ObsStatus.OK.value or r["total_fare"] is None:
            continue
        # Grouped by source_class as well as by cell. Scoring a real Cleartrip
        # fare against simulated ones would flag it for being real, and
        # METHODOLOGY section 4 says the two never touch.
        key = (r["observation_date"], r["route_code"],
               r["window_days"], r["source_class"])
        groups.setdefault(key, []).append(r)

    n_flagged = 0
    for group in groups.values():
        scores = modified_z_scores([r["total_fare"] for r in group])
        for r, z in zip(group, scores):
            r["outlier_score"] = round(z, 4)
            if abs(z) > MAD_THRESHOLD:
                r["is_outlier"] = 1
                n_flagged += 1

    return n_flagged


# ---------------------------------------------------------------------------
# STEP 4 — write to the database, without creating duplicates
# ---------------------------------------------------------------------------
INSERT_SQL = """
INSERT OR IGNORE INTO silver_fare_observation
    (observation_date, route_code, window_days, departure_date,
     source_id, source_class, status, status_class,
     carrier, flight_no, departure_time, stops,
     base_fare, taxes, fees, total_fare, currency, fare_ref,
     is_outlier, outlier_score)
VALUES
    (:observation_date, :route_code, :window_days, :departure_date,
     :source_id, :source_class, :status, :status_class,
     :carrier, :flight_no, :departure_time, :stops,
     :base_fare, :taxes, :fees, :total_fare, :currency, :fare_ref,
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
