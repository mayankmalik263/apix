"""Bring APIx up from nothing, in one command.

    python -m scripts.bootstrap

Used for two things that turn out to be the same thing: a cold start on a
laptop that has just cloned the repo, and the build step of a deployment.

    seed archive  ->  bronze  ->  silver  ->  gold

It is safe to run repeatedly. Every stage is idempotent, so re-running after a
failure resumes rather than duplicating, and running it on a machine that is
already up changes nothing.

What it does NOT do is collect. Collection needs a browser, a compliance
verdict dated today, and a deliberate decision to reach an airline's servers.
A deployment publishes numbers that were collected elsewhere.
"""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apix.config import db_path  # noqa: E402

SEED = ROOT / "data" / "seed"
BRONZE = ROOT / "data" / "bronze"
SCHEMAS = [ROOT / "db" / "schema.sql", ROOT / "webapp" / "backend" / "schema_web.sql"]


def rule(step: str) -> None:
    print(f"\n{'-' * 70}\n  {step}\n{'-' * 70}")


def unpack_seed() -> int:
    """Expand the compressed live archive into Bronze.

    The repo carries the three real collection days gzipped, because 140 MB of
    raw JSONL is not something to put in git but 13 MB is. Days already present
    are left alone: Bronze is append-only and the file on disk is the record.
    """
    rule("1/4  raw archive")
    if not SEED.exists():
        print("  no seed directory; skipping")
        return 0
    written = 0
    for gz in sorted(SEED.glob("*.jsonl.gz")):
        day, _, source = gz.name.removesuffix(".jsonl.gz").partition("-cleartrip")
        target = BRONZE / day / "cleartrip.jsonl"
        if target.exists():
            print(f"  {day}  already present, left as it is")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(gz, "rb") as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"  {day}  unpacked  {target.stat().st_size // 1024 // 1024} MB")
        written += 1
    return written


def apply_schemas() -> Path:
    """Both schema files, always. Applying only the first is how the scheduler
    and every data endpoint end up raising 'no such table'."""
    rule("2/4  database")
    db = db_path()
    conn = sqlite3.connect(db)
    try:
        for s in SCHEMAS:
            if s.exists():
                conn.executescript(s.read_text(encoding="utf-8"))
                print(f"  applied  {s.relative_to(ROOT)}")
        conn.commit()
    finally:
        conn.close()
    return db


def run(step: str, *args: str) -> None:
    print(f"  $ {' '.join(args)}")
    r = subprocess.run([sys.executable, *args], cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f"{step} failed with exit code {r.returncode}")


def main() -> int:
    unpack_seed()
    db = apply_schemas()

    rule("3/4  generated history")
    # The replay model is deterministic: the same seed reproduces the identical
    # 91 days, so the labelled history does not have to travel in the repo.
    run("seed", "-m", "apix.cli", "seed")

    rule("4/4  silver and gold")
    run("loader", "-m", "apix.load.loader")
    run("index", "-m", "apix.index.engine")

    conn = sqlite3.connect(db)
    days = conn.execute(
        "SELECT source_class, COUNT(*) FROM gold_apix_daily GROUP BY source_class"
    ).fetchall()
    conn.close()

    rule("ready")
    for sc, n in days:
        print(f"  {sc:<10} {n} published days")
    print(f"\n  database   {db}")
    print("  serve it   python -m webapp.run\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
