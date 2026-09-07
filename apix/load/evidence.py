"""The two tables the pipeline did not produce itself.

    source_registry   what we were permitted to collect, per day
    ground_truth      fares checked by hand, from data/ground_truth*.csv

Both exist as files first. Loading them lets a published value be joined
against the permission that allowed it and against an independent human
reading, in one query.

    python -m apix.load.evidence --compare
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from apix.config import COMPLIANCE_DIR, DATA_DIR
from apix.load.loader import connect

VERDICT_DIR = COMPLIANCE_DIR / "verdicts"


# ---------------------------------------------------------------------------
# source_registry
# ---------------------------------------------------------------------------
def load_source_registry(conn: sqlite3.Connection) -> int:
    """Every verdict ledger we hold, one row per source per day checked.

    Keyed on (source_id, checked_on) rather than source_id alone: a source
    that timed out on Wednesday and answered on Thursday is two facts, not a
    correction. The history of verdicts is itself a finding about which parts
    of the market can be observed at all.
    """
    rows = []
    for f in sorted(VERDICT_DIR.glob("*.json")):
        ledger = json.loads(f.read_text(encoding="utf-8"))
        for r in ledger.get("results", []):
            rows.append((
                r["source_id"], r["source_name"], r.get("kind"),
                r["checked_on"], r["verdict"], r.get("reason"),
                r.get("robots_sha256"), r.get("http_status"),
                r.get("evidence_file"),
            ))

    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO source_registry
                (source_id, source_name, kind, checked_on, verdict, reason,
                 robots_sha256, http_status, evidence_file)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    return len(rows)


# ---------------------------------------------------------------------------
# ground_truth
# ---------------------------------------------------------------------------
def _clean_fare(v: str | None) -> float | None:
    """People type '₹5,432' and '5432/-'. Take the digits and move on."""
    if not v:
        return None
    digits = "".join(ch for ch in v if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def load_ground_truth(conn: sqlite3.Connection) -> dict:
    """Load every filled row from every manual sheet.

    Reads data/ground_truth*.csv, which picks up both the combined file and
    the per-person sheets, because the sheets are what actually come back
    filled in. Rows with nothing entered are skipped -- an untouched template
    row is not an observation of anything.
    """
    rows, skipped = [], 0

    for f in sorted(DATA_DIR.glob("ground_truth*.csv")):
        with f.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                status = (r.get("status") or "").strip().upper()
                fare = _clean_fare(r.get("fare_shown"))
                notes = (r.get("notes") or "").strip()
                time_checked = (r.get("time_checked") or "").strip()

                # A genuinely untouched template row is skipped. A row where
                # somebody looked and could not get a fare is NOT: per
                # TEAM/01 they leave status blank and write why in notes.
                # Dropping those would quietly improve our coverage every
                # time collection got worse, which is the one thing this
                # project exists not to do.
                if not status and fare is None and not notes and not time_checked:
                    skipped += 1
                    continue

                # TEAM/01: if the site would not load, the checker leaves
                # status empty and notes why. That is a failure on our side,
                # not a fact about the market, so it must not become SOLD_OUT.
                if not status:
                    status = "OK" if fare is not None else "FETCH_FAIL"

                rows.append((
                    r["observation_date"], r["route_code"], int(r["window_days"]),
                    r["departure_date"], r["checker"], time_checked or None,
                    (r.get("website") or "").strip() or None,
                    (r.get("airline") or "").strip() or None,
                    (r.get("flight_no") or "").strip() or None,
                    fare, status, notes or None,
                ))

    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO ground_truth
                (observation_date, route_code, window_days, departure_date,
                 checker, time_checked, website, airline, flight_no,
                 fare_shown, status, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
    return {"loaded": len(rows), "blank_template_rows": skipped}


# ---------------------------------------------------------------------------
# The comparison — the point of all of it
# ---------------------------------------------------------------------------
COMPARE_SQL = """
SELECT g.observation_date, g.route_code, g.window_days, g.checker,
       g.website, g.status AS human_status, g.fare_shown,
       c.median_fare, c.n_used, c.status AS machine_status
FROM   ground_truth g
LEFT JOIN gold_cell_median c
       ON  c.observation_date = g.observation_date
       AND c.route_code       = g.route_code
       AND c.window_days      = g.window_days
       AND c.source_class     = 'LIVE'
ORDER BY g.observation_date, g.route_code, g.window_days
"""


def compare(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(COMPARE_SQL).fetchall()


def print_comparison(conn: sqlite3.Connection) -> None:
    rows = compare(conn)
    if not rows:
        print("\nNo hand-checked fares loaded yet.")
        print("The sheets are in data/ground_truth_<date>_<name>.csv and are")
        print("still empty templates. Nothing to compare until they come back.\n")
        return

    print()
    print(f"{'DATE':<12}{'ROUTE':<10}{'WIN':>4}  {'CHECKER':<10}"
          f"{'BY HAND':>10}{'APIx':>10}{'DIFF':>9}{'DIFF %':>9}")
    print("-" * 84)

    diffs = []
    for r in rows:
        win = f"T+{r['window_days']}"
        if r["fare_shown"] is not None and r["median_fare"]:
            d = r["fare_shown"] - r["median_fare"]
            pct = 100 * d / r["median_fare"]
            diffs.append(abs(pct))
            print(f"{r['observation_date']:<12}{r['route_code']:<10}{win:>4}  "
                  f"{r['checker']:<10}{r['fare_shown']:>10,.0f}"
                  f"{r['median_fare']:>10,.0f}{d:>9,.0f}{pct:>8.1f}%")
        else:
            note = r["human_status"] if r["fare_shown"] is None else f"no {r['machine_status'] or 'cell'}"
            print(f"{r['observation_date']:<12}{r['route_code']:<10}{win:>4}  "
                  f"{r['checker']:<10}{note:>10}{'-':>10}{'-':>9}{'-':>9}")

    print("-" * 84)
    if diffs:
        diffs.sort()
        mid = diffs[len(diffs) // 2]
        print(f"{len(diffs)} cells compared   median absolute difference {mid:.1f}%")
        print(f"within 5%: {sum(1 for d in diffs if d <= 5)}   "
              f"within 10%: {sum(1 for d in diffs if d <= 10)}")
    print()
    print("A gap is not automatically our error. The panel is checked in the")
    print("morning and the automated slot is later in the day, on a market that")
    print("reprices through the day -- so this compares two honest readings")
    print("taken at different times. Say that before someone asks.")
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apix.load.evidence")
    ap.add_argument("--compare", action="store_true",
                    help="print the hand-checked vs computed table")
    args = ap.parse_args(argv)

    conn = connect()
    n_reg = load_source_registry(conn)
    gt = load_ground_truth(conn)

    print("-" * 70)
    print(f"  source_registry rows   {n_reg:>6}   "
          f"({len(list(VERDICT_DIR.glob('*.json')))} verdict ledgers)")
    print(f"  ground_truth rows      {gt['loaded']:>6}   "
          f"({gt['blank_template_rows']} blank template rows skipped)")

    permitted = conn.execute(
        "SELECT checked_on, COUNT(*) FROM source_registry "
        "WHERE verdict='PERMITTED' GROUP BY checked_on ORDER BY 1"
    ).fetchall()
    for day, n in permitted:
        total = conn.execute(
            "SELECT COUNT(*) FROM source_registry WHERE checked_on=?", (day,)
        ).fetchone()[0]
        print(f"  {day}           {n} of {total} sources permitted")
    print("-" * 70)

    if args.compare:
        print_comparison(conn)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
