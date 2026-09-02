"""
APIx command line.

Every stage runs independently, so a broken collector never blocks work on the
index and a missing database never blocks collection.

    python -m apix.cli compliance --check     fetch robots.txt, write verdicts
    python -m apix.cli compliance --report    print the 11-source table
    python -m apix.cli collect --today        collect today from permitted sources
    python -m apix.cli seed --days 90         generate labelled synthetic history
    python -m apix.cli bronze --stats         what is in the raw archive
    python -m apix.cli sheets                 regenerate manual collection sheets
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from apix.collect import bronze
from apix.collect.compliance import PERMITTED, report as compliance_report, run_checks
from apix.collect.replay import ReplayAdapter
from apix.config import load_basket

BAR = "-" * 92


def _print_compliance(rows: list[dict]) -> None:
    print()
    print(f"{'SOURCE':<22}{'KIND':<9}{'HTTP':<6}{'VERDICT':<13}REASON")
    print(BAR)
    for r in rows:
        http = str(r["http"]) if r["http"] else "-"
        print(f"{r['name']:<22}{r['kind']:<9}{http:<6}{r['verdict']:<13}{r['reason']}")
    print(BAR)
    n_ok = sum(1 for r in rows if r["verdict"] == PERMITTED)
    print(f"{n_ok} of {len(rows)} sources permitted. "
          f"Uncleared sources are refused before any network call is made.")
    print()


def cmd_compliance(args) -> int:
    if args.check:
        print("Fetching robots.txt for every registered source...")
        run_checks(only=args.only)
    _print_compliance(compliance_report())
    return 0


def cmd_collect(args) -> int:
    basket = load_basket()
    obs = date.today() if args.today else date.fromisoformat(args.date)

    # Only the replay adapter exists so far. Live adapters register here and
    # the gate decides at run time whether each one is allowed to proceed.
    adapters = [ReplayAdapter(anchor_date=obs)]

    from apix.collect.runner import collect_day

    print(f"Collecting {basket.cells_per_day} cells "
          f"({len(basket.routes)} routes x {len(basket.windows)} windows) for {obs}")
    print(BAR)
    for a in adapters:
        print(collect_day(a, obs, resume=not args.force).line())
    print(BAR)
    return 0


def cmd_seed(args) -> int:
    from apix.collect.runner import collect_range

    end = date.today() if args.until is None else date.fromisoformat(args.until)
    start = end - timedelta(days=args.days - 1)
    adapter = ReplayAdapter(anchor_date=end)

    print(f"Seeding {args.days} days of SIMULATED history: {start} to {end}")
    print("Every row is stamped source_class=SIMULATED. There is no flag to disable that.")
    print(BAR)
    summaries = collect_range(adapter, start, end, resume=not args.force)
    written = sum(s.written for s in summaries)
    skipped = sum(s.skipped_existing for s in summaries)
    totals: dict[str, int] = {}
    for s in summaries:
        for k, v in s.by_status.items():
            totals[k] = totals.get(k, 0) + v
    print(f"{len(summaries)} days | wrote {written} | skipped {skipped} already present")
    for k, v in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<20}{v:>6}")
    print(BAR)
    return 0


def cmd_bronze(args) -> int:
    s = bronze.stats()
    print()
    print(f"Raw archive: {bronze.BRONZE_DIR}")
    print(BAR)
    print(f"  records      {s['total_records']}")
    print(f"  days         {s['n_days']}   ({s['first_day']} .. {s['last_day']})")
    print(f"  sources      {', '.join(f'{k}={v}' for k, v in sorted(s['by_source'].items())) or '-'}")
    print("  by status:")
    for k, v in sorted(s["by_status"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:<22}{v:>7}")
    print(BAR)
    print()
    return 0


def cmd_sheets(args) -> int:
    from scripts.make_ground_truth_sheets import main as make_sheets

    make_sheets()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="apix", description="APIx - Airfare Price Index")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("compliance", help="robots.txt checks and the source table")
    c.add_argument("--check", action="store_true", help="fetch robots.txt and write verdicts")
    c.add_argument("--report", action="store_true", help="print the stored table")
    c.add_argument("--only", nargs="*", help="limit --check to these source ids")
    c.set_defaults(func=cmd_compliance)

    c = sub.add_parser("collect", help="collect one observation day")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--today", action="store_true")
    g.add_argument("--date", help="YYYY-MM-DD")
    c.add_argument("--force", action="store_true", help="re-collect cells already present")
    c.set_defaults(func=cmd_collect)

    c = sub.add_parser("seed", help="generate labelled synthetic history")
    c.add_argument("--days", type=int, default=90)
    c.add_argument("--until", help="last day, YYYY-MM-DD (default today)")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_seed)

    c = sub.add_parser("bronze", help="inspect the raw archive")
    c.add_argument("--stats", action="store_true")
    c.set_defaults(func=cmd_bronze)

    c = sub.add_parser("sheets", help="regenerate the manual collection sheets")
    c.set_defaults(func=cmd_sheets)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
