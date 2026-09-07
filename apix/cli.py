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

    # Live adapters register here; the gate decides at run time whether each
    # one may proceed. Replay is the fallback so a demo never shows an empty
    # screen because a portal was slow.
    if args.live:
        from apix.collect.live_cleartrip import CleartripAdapter
        adapters = [CleartripAdapter()]
    elif args.simulated:
        adapters = [ReplayAdapter(anchor_date=obs)]
    else:
        from apix.collect.live_cleartrip import CleartripAdapter
        adapters = [CleartripAdapter(), ReplayAdapter(anchor_date=obs)]

    from apix.collect.runner import collect_day

    print(f"Collecting for {obs}")
    print(BAR)
    for a in adapters:
        print(collect_day(a, obs, resume=not args.force,
                          only_routes=args.routes, only_windows=args.windows).line())
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



def cmd_load(args) -> int:
    from apix.load.loader import main as load_main
    load_main()
    if args.evidence:
        from apix.load.evidence import main as ev_main
        ev_main([])
    return 0


def cmd_index(args) -> int:
    from apix.index.engine import main as index_main
    index_main()
    return 0


# ---------------------------------------------------------------------------
# demo -- one command, cold clone to running dashboard
# ---------------------------------------------------------------------------
def _step(n: int, total: int, title: str) -> None:
    print()
    print(f"[{n}/{total}] {title}")
    print(BAR)


def cmd_demo(args) -> int:
    """Everything, in order, with every failure narrated rather than hidden.

    Designed to be watched. If a step fails on stage the demo does not stop --
    it says what failed, shows the status that produced, and carries on. A
    BLOCKED row appearing live is the system working as designed.
    """
    import subprocess
    import sys as _sys
    from datetime import date as _date

    total = 6
    obs = _date.today()

    _step(1, total, "COMPLIANCE -- may we collect at all?")
    try:
        if args.check:
            run_checks()
        rows = compliance_report(obs)
        if not rows or all(r["verdict"] == "UNKNOWN" for r in rows):
            run_checks()
            rows = compliance_report(obs)
        _print_compliance(rows)
    except Exception as exc:
        print(f"  compliance check unavailable ({type(exc).__name__}). "
              f"The gate refuses everything when it cannot verify -- that is the "
              f"designed behaviour, not a crash.")

    _step(2, total, "COLLECT -- one live cell from a permitted source")
    if args.offline:
        print("  --offline: skipping the network entirely, using the archive on disk.")
    else:
        try:
            from apix.collect.live_cleartrip import CleartripAdapter
            from apix.collect.runner import collect_day
            s = collect_day(CleartripAdapter(), obs, resume=not args.force,
                            only_routes=[args.route], only_windows=[args.window])
            print("  " + s.line())
            if s.gate_refused:
                print("  The gate refused before any request was made. That is the feature.")
        except Exception as exc:
            print(f"  live collection failed: {type(exc).__name__}: {str(exc)[:120]}")
            print("  Falling back to the archive already on disk. The fare could not be")
            print("  collected, and the system says so rather than inventing one.")

    _step(3, total, "BRONZE -- what is in the immutable archive")
    st = bronze.stats()
    print(f"  {st['total_records']} records across {st['n_days']} days "
          f"({st['first_day']} .. {st['last_day']})")
    print(f"  sources: {', '.join(f'{k}={v}' for k, v in sorted(st['by_source'].items()))}")

    _step(4, total, "SILVER -- parse the raw archive into clean rows")
    from apix.load.loader import main as load_main
    load_main()

    _step(5, total, "GOLD -- compute the index")
    from apix.index.engine import main as index_main
    index_main()
    try:
        from apix.load.evidence import main as ev_main
        ev_main([])
    except Exception:
        pass

    _step(6, total, "SERVE -- API and dashboard")
    print(f"  dashboard  http://localhost:{args.port}/")
    print(f"  API docs   http://localhost:{args.port}/docs")
    print(f"  lineage    http://localhost:{args.port}/v1/lineage/"
          f"{obs}/{args.route}/{args.window}")
    print(BAR)
    if args.no_serve:
        print("  --no-serve: stopping here.")
        return 0
    print("  Ctrl-C to stop.")
    print()
    return subprocess.call([_sys.executable, "-m", "uvicorn", "webapp.backend.app:app",
                            "--port", str(args.port)])


def cmd_serve(args) -> int:
    """Run the web app: API, dashboard, admin and the daily scheduler."""
    import subprocess
    import sys as _sys
    cmd = [_sys.executable, "-m", "uvicorn", "webapp.backend.app:app",
           "--host", args.host, "--port", str(args.port)]
    if args.reload:
        cmd.append("--reload")
    print(f"  dashboard   http://localhost:{args.port}/")
    print(f"  admin       http://localhost:{args.port}/console")
    print(f"  API docs    http://localhost:{args.port}/docs")
    print(BAR)
    return subprocess.call(cmd)


def cmd_useradd(args) -> int:
    """Create an operator account. There is no signup page on purpose --
    an account is made by someone who already has shell access to the box."""
    import getpass
    import secrets
    import sqlite3
    from pathlib import Path as _P

    from apix.web import auth

    root = _P(__file__).resolve().parents[1]
    db = root / "apix.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    for f in ("db/schema.sql", "webapp/backend/schema_web.sql"):
        pth = root / f
        if pth.exists():
            conn.executescript(pth.read_text(encoding="utf-8"))

    email = args.email or input("email: ").strip()
    name = args.name or input("display name: ").strip() or email.split("@")[0]

    if args.password:
        pw, shown = args.password, False
    elif args.generate_password:
        pw = secrets.token_urlsafe(12)
        shown = True
    else:
        pw = getpass.getpass("password (min 10 chars, not echoed): ")
        if pw != getpass.getpass("confirm: "):
            print("Passwords did not match.")
            return 1
        shown = False

    if args.replace and conn.execute(
            "SELECT 1 FROM web_user WHERE email=?", (email.strip().lower(),)).fetchone():
        auth.set_password(conn, email, pw)
        print(BAR)
        print(f"  password updated for {email.strip().lower()}")
        print(BAR)
        return 0

    try:
        u = auth.create_user(conn, email, name, pw, role=args.role)
    except sqlite3.IntegrityError:
        print(f"An account for {email} already exists.")
        return 1
    except ValueError as exc:
        print(exc)
        return 1

    print(BAR)
    print(f"  created {u.role} account for {u.email}")
    if shown:
        print(f"  password: {pw}")
        print("  Copy it now -- it is stored only as a scrypt hash.")
    print(BAR)
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
    src = c.add_mutually_exclusive_group()
    src.add_argument("--live", action="store_true", help="live sources only")
    src.add_argument("--simulated", action="store_true", help="replay only")
    c.add_argument("--routes", nargs="*", help="limit to these route codes")
    c.add_argument("--windows", nargs="*", type=int, help="limit to these windows")
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

    c = sub.add_parser("load", help="Bronze files -> Silver table")
    c.add_argument("--evidence", action="store_true",
                   help="also load the compliance ledger and the manual panel")
    c.set_defaults(func=cmd_load)

    c = sub.add_parser("index", help="Silver -> the published index")
    c.set_defaults(func=cmd_index)

    c = sub.add_parser("serve", help="run the web app and the daily scheduler")
    c.add_argument("--port", type=int, default=8000)
    c.add_argument("--host", default="127.0.0.1")
    c.add_argument("--reload", action="store_true")
    c.set_defaults(func=cmd_serve)

    c = sub.add_parser("useradd", help="create an operator account")
    c.add_argument("--email")
    c.add_argument("--name")
    c.add_argument("--role", default="admin", choices=["admin", "viewer"])
    c.add_argument("--password", help="set it directly (skips the prompt)")
    c.add_argument("--generate-password", action="store_true",
                   help="generate one and print it once")
    c.add_argument("--replace", action="store_true",
                   help="overwrite the account if the email already exists")
    c.set_defaults(func=cmd_useradd)

    c = sub.add_parser("demo", help="one command: compliance -> collect -> load -> index -> serve")
    c.add_argument("--port", type=int, default=8000)
    c.add_argument("--route", default="DEL-BOM", help="which cell to collect live")
    c.add_argument("--window", type=int, default=21)
    c.add_argument("--check", action="store_true", help="re-fetch every robots.txt first")
    c.add_argument("--offline", action="store_true", help="skip the network entirely")
    c.add_argument("--force", action="store_true", help="re-collect a cell already held")
    c.add_argument("--no-serve", action="store_true", help="stop before starting the server")
    c.set_defaults(func=cmd_demo)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
