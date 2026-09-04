"""
VERIFICATION TOOL — Mayank, Round 3.

WHAT THIS DOES
    Pulls the raw fares for ONE route on ONE day out of the database and
    writes them to a CSV you can open in Google Sheets or Excel.

WHY YOU NEED IT
    Bharat writes the index engine. Somebody who did NOT write it has to work
    the same number out independently, or the check is worthless. Mayank does
    it in a spreadsheet: different tool, different person, no shared
    assumptions. "We recomputed it by hand and it matched" is a sentence a
    jury believes; "we ran our code twice" is not.

RUN IT
    python scripts/dump_for_check.py DEL-BOM 2026-09-04

    Then open  data/verify_DEL-BOM_2026-09-04.csv  in Google Sheets.
    Step-by-step spreadsheet instructions are in the build plan.

If the database does not exist yet, Bharat has not finished the loader.
Wait for him -- do not try to work around it.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "apix.db"
OUT_DIR = ROOT / "data"

QUERY = """
SELECT window_days,
       departure_date,
       carrier,
       total_fare,
       base_fare,
       taxes,
       fees,
       status,
       is_outlier,
       outlier_score,
       source_id,
       source_class
FROM   silver_fare_observation
WHERE  route_code = ?
  AND  observation_date = ?
ORDER  BY window_days, total_fare
"""


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        print("\nUsage:  python scripts/dump_for_check.py <ROUTE> <DATE>")
        print("Example: python scripts/dump_for_check.py DEL-BOM 2026-09-04")
        sys.exit(1)

    route, day = sys.argv[1].upper(), sys.argv[2]

    if not DB.exists():
        print(f"No database at {DB}")
        print("Bharat has not run the loader yet. Ask him, then try again.")
        sys.exit(1)

    conn = sqlite3.connect(DB)
    rows = conn.execute(QUERY, (route, day)).fetchall()
    cols = [d[0] for d in conn.execute(QUERY, (route, day)).description]
    conn.close()

    if not rows:
        print(f"No rows for {route} on {day}.")
        print("Check the date is one we actually collected, and that the")
        print("loader has run. Try: 2026-09-03 or 2026-09-04")
        sys.exit(1)

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"verify_{route}_{day}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)

    # A quick summary so you know what to expect before opening the file.
    by_window: dict[int, list[float]] = {}
    for r in rows:
        if r[7] == "OK" and not r[8] and r[3] is not None:
            by_window.setdefault(r[0], []).append(r[3])

    print(f"Wrote {len(rows)} rows to {out}")
    print()
    print(f"{route} on {day} -- what you should find:")
    print(f"  {'WINDOW':<10}{'FARES USED':>12}{'CHEAPEST':>12}{'DEAREST':>12}")
    print("  " + "-" * 46)
    for w_days in sorted(by_window):
        f = sorted(by_window[w_days])
        print(f"  T+{w_days:<8}{len(f):>12}{f[0]:>12,.0f}{f[-1]:>12,.0f}")
    print()
    print("Excluded from those counts: rows where status is not OK, and rows")
    print("flagged as outliers. Both are still in the CSV -- flagged, not deleted.")
    print()
    print("Next: open the CSV in Google Sheets and follow the steps in the")
    print("handbook under 'Mayank, Round 3'.")


if __name__ == "__main__":
    main()
