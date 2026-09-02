"""
Generate the manual ground-truth collection sheets.

Why this exists: airfares cannot be collected retrospectively. Every morning
that passes without someone writing down a fare is a day permanently missing
from the series. These sheets exist so three people with no coding background
can start producing usable data within five minutes of opening the file.

The sheets are pre-filled with every route, window and departure date already
computed, so the only thing a person types is the fare, the airline and the
status. Nothing to calculate, nothing to get wrong.

Run:  python scripts/make_ground_truth_sheets.py
Out:  data/ground_truth_<date>_<person>.csv   (one per person per day)
      data/ground_truth.csv                   (combined, empty, for the loader)
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

# Run this file directly from anywhere: put the repo root on the path first.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apix.config import DATA_DIR, departure_date, load_basket  # noqa: E402

# Who checks what. Two routes each, ten cells each, thirty a day between them.
ASSIGNMENT = {
    "Kritika": ["DEL-BOM", "DEL-BLR"],
    "Riya": ["BOM-BLR", "DEL-CCU"],
    "Vidushi": ["BLR-HYD", "MAA-DEL"],
}

# Two collection days: 3 and 4 September. Presentation is 4 Sep at 15:00, so
# the 4th must be collected in the MORNING -- it is the freshest number we can
# show, and there is no second chance at it.
#
# 2 September was available and was not collected. That day is permanently
# missing from the series and cannot be recovered, which is precisely the
# property of this data that makes the project worth building. Do not lose
# the 3rd the same way.
COLLECTION_DAYS = [date(2026, 9, 3), date(2026, 9, 4)]

COLUMNS = [
    "observation_date",   # pre-filled
    "route_code",         # pre-filled
    "window_days",        # pre-filled
    "departure_date",     # pre-filled
    "checker",            # pre-filled
    "time_checked",       # <- you fill: HH:MM, 24h
    "website",            # <- you fill
    "airline",            # <- you fill
    "flight_no",          # <- you fill
    "fare_shown",         # <- you fill: number only, no rupee sign, no commas
    "status",             # <- you fill: OK / SOLD_OUT / NO_SERVICE
    "notes",              # <- optional
]


def rows_for(person: str, routes: list[str], obs_date: date, windows: list[int]):
    for route in routes:
        for w in windows:
            yield {
                "observation_date": obs_date.isoformat(),
                "route_code": route,
                "window_days": w,
                "departure_date": departure_date(obs_date, w).isoformat(),
                "checker": person,
                "time_checked": "",
                "website": "",
                "airline": "",
                "flight_no": "",
                "fare_shown": "",
                "status": "",
                "notes": "",
            }


def main() -> None:
    basket = load_basket()
    windows = basket.windows
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    known = {r.code for r in basket.routes}
    assigned = {r for rs in ASSIGNMENT.values() for r in rs}
    missing = known - assigned
    if missing:
        raise SystemExit(f"routes in basket with nobody assigned: {sorted(missing)}")

    written = []
    for obs_date in COLLECTION_DAYS:
        for person, routes in ASSIGNMENT.items():
            out = DATA_DIR / f"ground_truth_{obs_date.isoformat()}_{person.lower()}.csv"
            with out.open("w", newline="", encoding="utf-8") as fh:
                wr = csv.DictWriter(fh, fieldnames=COLUMNS)
                wr.writeheader()
                wr.writerows(rows_for(person, routes, obs_date, windows))
            written.append(out)

    # Combined empty file the loader reads. Filled sheets get pasted in here.
    combined = DATA_DIR / "ground_truth.csv"
    if not combined.exists():
        with combined.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=COLUMNS).writeheader()

    n_cells = len(COLLECTION_DAYS) * len(basket.routes) * len(windows)
    print(f"Wrote {len(written)} sheets covering {n_cells} cells "
          f"({len(COLLECTION_DAYS)} days x {basket.cells_per_day} per day)")
    for p in written:
        print(f"  {p.name}")
    print(f"\nCombined target: {combined}")

    print("\nDeparture dates by window:")
    for obs_date in COLLECTION_DAYS:
        parts = " · ".join(
            f"T+{w} -> {departure_date(obs_date, w).strftime('%d %b')}"
            for w in windows
        )
        print(f"  checking on {obs_date.strftime('%d %b')}:  {parts}")


if __name__ == "__main__":
    main()
