"""
Extract the REAL MoSPI airfare item index from the downloaded CPI annexures.

Source: MoSPI CPI press-release Annex-V,
        "Year-on-year inflation rate (%) of key items", Base 2012=100,
        item "Air fare [normal]: economy class [adult]", weight 0.08,
        All India (Combined).

This is the only airfare-specific series MoSPI publishes. It is national-level
only, monthly, and carries a weight of 0.08 in the CPI basket. APIx exists
because one national number cannot represent 1,100+ city pairs.

Run:  python scripts/extract_mospi_airfare.py
Out:  data/mospi_airfare_index.json
"""
import csv
import json
import re
import sys
from pathlib import Path

MOSPI_DIR = Path(r"D:\SIH 2k26\mospi_cpi")
OUT = Path(__file__).resolve().parents[1] / "data" / "mospi_airfare_index.json"

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def parse_month_label(label: str):
    """'September 24 Index' -> (2024, 9). Returns None if unparseable."""
    t = label.strip().lower()
    # Annex-V repeats each month as both an INDEX column and an INFLATION RATE
    # column. Only the index columns are the series we want.
    if "inflation" in t or "%" in t:
        return None
    if "index" not in t:
        return None
    t = t.replace("index", "").strip()
    m = re.match(r"([a-z]+)\s+(\d{2,4})", t)
    if not m:
        return None
    name, yr = m.group(1), m.group(2)
    if name not in MONTHS:
        return None
    year = int(yr)
    if year < 100:
        year += 2000
    return year, MONTHS[name]


def extract_file(path: Path):
    """Yield (year, month, index_value, source_file) from one key-items CSV."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))

    header_idx = None
    for i, row in enumerate(rows[:12]):
        joined = " ".join(row).lower()
        if "index" in joined and "weight" in joined:
            header_idx = i
            break
    if header_idx is None:
        return

    header = rows[header_idx]
    # The row beneath the header marks each column (Final) or (Prov.).
    status_row = rows[header_idx + 1] if header_idx + 1 < len(rows) else []
    # column position -> (year, month)
    cols = {}
    for j, cell in enumerate(header):
        parsed = parse_month_label(cell)
        if parsed:
            cols[j] = parsed
    if not cols:
        return

    for row in rows[header_idx:]:
        if len(row) < 3:
            continue
        desc = row[1].strip().lower() if len(row) > 1 else ""
        if not desc.startswith("air fare"):
            continue
        for j, (year, month) in cols.items():
            if j >= len(row):
                continue
            raw = row[j].strip()
            if not raw:
                continue
            try:
                val = float(raw)
            except ValueError:
                continue
            if val <= 0:
                continue
            raw_status = status_row[j].strip() if j < len(status_row) else ""
            status = "final" if "final" in raw_status.lower() else (
                "provisional" if "prov" in raw_status.lower() else "unknown")
            yield year, month, val, path.name, row[1].strip(), status


def main():
    if not MOSPI_DIR.exists():
        print(f"MoSPI directory not found: {MOSPI_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(MOSPI_DIR.glob("*/*key_items*.csv")) + \
            sorted(MOSPI_DIR.glob("*/*Key_items*.csv"))
    files = sorted(set(files))

    # (year, month) -> record. Later releases revise earlier provisional values,
    # so keep the value from the most recently released file.
    series = {}
    labels = set()
    release_order = {p: i for i, p in enumerate(files)}

    for path in files:
        for year, month, val, fname, label, status in extract_file(path):
            labels.add(label)
            key = (year, month)
            prev = series.get(key)
            rank = {"final": 2, "provisional": 1, "unknown": 0}[status]
            # A Final value always supersedes a Provisional one. Between two of
            # equal standing, the later release wins.
            if prev is None or (rank, release_order[path]) >= (prev["_rank"], prev["_order"]):
                series[key] = {
                    "period": f"{year}-{month:02d}",
                    "year": year,
                    "month": month,
                    "index": val,
                    "revision_status": status,
                    "source_file": fname,
                    "_order": release_order[path],
                    "_rank": rank,
                }

    records = [
        {k: v for k, v in rec.items() if not k.startswith("_")}
        for _, rec in sorted(series.items())
    ]

    # month-on-month change where consecutive months exist
    by_period = {r["period"]: r for r in records}
    for r in records:
        y, m = r["year"], r["month"]
        pm, py = (m - 1, y) if m > 1 else (12, y - 1)
        prev = by_period.get(f"{py}-{pm:02d}")
        r["mom_pct"] = round((r["index"] / prev["index"] - 1) * 100, 2) if prev else None
        prev_year = by_period.get(f"{y-1}-{m:02d}")
        r["yoy_pct"] = round((r["index"] / prev_year["index"] - 1) * 100, 2) if prev_year else None

    payload = {
        "series_name": "CPI item: Air fare [normal]: economy class [adult]",
        "item_labels_seen": sorted(labels),
        "base": "2012=100",
        "weight_in_cpi": 0.08,
        "geography": "All India (Combined)",
        "frequency": "Monthly",
        "publisher": "Price Statistics Division, MoSPI",
        "annexure": "Annex-V, Year-on-year inflation rate of key items",
        "extracted_from_files": [p.name for p in files],
        "n_observations": len(records),
        "observations": records,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Extracted {len(records)} monthly observations -> {OUT}")
    for r in records:
        mom = f"{r['mom_pct']:+.2f}%" if r["mom_pct"] is not None else "   n/a"
        yoy = f"{r['yoy_pct']:+.2f}%" if r["yoy_pct"] is not None else "   n/a"
        print(f"  {r['period']}  index {r['index']:7.1f}   MoM {mom}   YoY {yoy}")


if __name__ == "__main__":
    main()
