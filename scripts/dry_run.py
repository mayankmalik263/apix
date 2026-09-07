"""
The ten counted runs.

The rule from the team meeting was not "it should work" -- it was ten actual
runs, tallied, with a note of what broke. This script is that tally, so the
count is a file rather than somebody's memory.

Each run is a genuine cold start: the database is deleted, the schema is
reapplied, the archive is reparsed, the index is recomputed, the API is booted
on a scratch port and every endpoint the demo touches is called and checked.

    python scripts/dry_run.py            # 10 runs, no network
    python scripts/dry_run.py -n 3       # fewer
    python scripts/dry_run.py --port 8931

Writes: data/dry_run_log.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A scratch database, never the live one. An earlier version of this harness
# deleted apix.db on every run and took the operator accounts and every issued
# API key with it.
DB = ROOT / "apix.dryrun.db"
os.environ["APIX_DB_PATH"] = str(DB)

LOG = ROOT / "data" / "dry_run_log.md"

# Every endpoint the five-minute demo actually touches, with the check that
# proves it returned something real rather than an empty shell.
# The open tier: what the dashboard reads, and what must never need a key.
CHECKS = [
    ("/v1/health",                                   lambda d: d["status"] == "ok"),
    ("/v1/system/status",                            lambda d: "seconds_to_next_run" in d),
    ("/public/overview",                             lambda d: d["latest"] is not None),
    ("/public/overview?freq=weekly",                 lambda d: d["frequency"] == "weekly"),
    ("/public/overview?freq=monthly",                lambda d: d["frequency"] == "monthly"),
    ("/public/apix/latest",                          lambda d: d["available"]),
    ("/public/apix/series?source_class=SIMULATED",   lambda d: d["n"] > 0),
    ("/public/lead-time?source_class=SIMULATED",     lambda d: d["available"] and d["curve"]),
    ("/public/composition?source_class=SIMULATED",   lambda d: d["available"]),
    ("/public/compliance/report",                    lambda d: d["total"] == 11),
    ("/public/bronze/stats",                         lambda d: d["total_records"] > 0),
    ("/public/basket",                               lambda d: d["cells_per_day"] == 30),
    ("/public/mospi",                                lambda d: d["n_observations"] == 12),
]

# Pages must be served, not just endpoints. A demo is a browser, not curl.
PAGES = ["/", "/login", "/docs", "/app.css", "/app.js", "/console.js",
         "/vendor/echarts.min.js"]

# The keyed tier and the admin console must refuse an anonymous caller. If one
# of these ever returns 200 the system is open and the console is lying.
MUST_REFUSE = [
    ("/v1/apix/latest",   401),
    ("/console/api/keys",   401),
    ("/console/api/runs",   401),
    ("/nope.css",         404),
]


def _env() -> dict:
    e = dict(os.environ)
    e["APIX_DB_PATH"] = str(DB)
    return e


def sh(*cmd) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=_env())
    return p.returncode, (p.stdout + p.stderr)[-400:]


def get(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def wait_for_api(base: str, seconds: float = 25.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            get(base + "/v1/health", timeout=2)
            return True
        except Exception:
            time.sleep(0.4)
    return False


def one_run(n: int, port: int) -> dict:
    base = f"http://127.0.0.1:{port}"
    started = time.time()
    broke: list[str] = []

    for f in (DB, Path(str(DB) + "-wal"), Path(str(DB) + "-shm")):
        f.unlink(missing_ok=True)

    import sqlite3
    con = sqlite3.connect(DB)
    for f in (ROOT / "db" / "schema.sql", ROOT / "webapp" / "backend" / "schema_web.sql"):
        con.executescript(f.read_text(encoding="utf-8"))
    con.close()

    for label, cmd in (("load",  (sys.executable, "-m", "apix.cli", "load")),
                       ("index", (sys.executable, "-m", "apix.cli", "index"))):
        rc, out = sh(*cmd)
        if rc != 0:
            broke.append(f"{label}: {out.strip().splitlines()[-1][:110]}")

    srv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.backend.app:app", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_env())
    try:
        if not wait_for_api(base):
            broke.append("api: did not come up within 25s")
        else:
            for path, ok in CHECKS:
                try:
                    if not ok(get(base + path)):
                        broke.append(f"{path}: returned an empty or wrong shape")
                except Exception as exc:
                    broke.append(f"{path}: {type(exc).__name__}")

            for path in PAGES:
                try:
                    with urllib.request.urlopen(base + path, timeout=8) as r:
                        if r.status != 200:
                            broke.append(f"page {path}: HTTP {r.status}")
                except Exception as exc:
                    broke.append(f"page {path}: {type(exc).__name__}")

            for path, want in MUST_REFUSE:
                try:
                    urllib.request.urlopen(base + path, timeout=8)
                    broke.append(f"SECURITY {path}: served without credentials")
                except urllib.error.HTTPError as e:
                    if e.code != want:
                        broke.append(f"{path}: expected {want}, got {e.code}")
                except Exception as exc:
                    broke.append(f"{path}: {type(exc).__name__}")
            try:
                lin = get(base + "/public/lineage/2026-09-05/DEL-BOM/21"
                          "?source_class=SIMULATED")
                if not lin["bronze"] or not lin["bronze"][0]["payload_sha256"]:
                    broke.append("lineage: no payload hash returned")
                if lin["gold"] is None:
                    broke.append("lineage: no published median for that cell")
            except Exception as exc:
                broke.append(f"lineage: {type(exc).__name__}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()

    took = time.time() - started
    print(f"  run {n:>2}   {'PASS' if not broke else 'FAIL'}   {took:5.1f}s"
          + ("" if not broke else "   " + broke[0]))
    for b in broke[1:]:
        print(" " * 24 + b)
    return {"run": n, "ok": not broke, "seconds": round(took, 1), "broke": broke}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--runs", type=int, default=10)
    ap.add_argument("--port", type=int, default=8931)
    a = ap.parse_args()

    print(f"\nAPIx dry run — {a.runs} cold starts, each rebuilding from the raw archive")
    print("-" * 68)
    results = [one_run(i, a.port) for i in range(1, a.runs + 1)]
    print("-" * 68)

    passed = sum(r["ok"] for r in results)
    avg = sum(r["seconds"] for r in results) / len(results)
    print(f"  {passed} of {len(results)} passed   ·   average {avg:.1f}s per cold start\n")

    lines = [
        "# APIx dry-run log", "",
        f"_{datetime.now():%A %d %B %Y, %H:%M}_", "",
        f"**{passed} of {len(results)} runs passed.** Average cold start {avg:.1f}s.",
        "",
        "Each run deletes the database, reapplies both schemas, reparses the whole",
        "raw archive, recomputes the index, boots the API, serves every page, calls",
        "every open endpoint, walks the lineage back to a real SHA-256, and checks",
        "that the keyed API and the admin console refuse an anonymous caller.", "",
        "| Run | Result | Seconds | What broke |", "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['run']} | {'PASS' if r['ok'] else 'FAIL'} | "
                     f"{r['seconds']} | {'—' if r['ok'] else '; '.join(r['broke'])} |")
    for f in (DB, Path(str(DB) + "-wal"), Path(str(DB) + "-shm")):
        f.unlink(missing_ok=True)

    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  written to {LOG.relative_to(ROOT)}\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
