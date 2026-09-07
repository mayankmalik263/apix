"""Start APIx.

    python -m webapp.run [--port 8000] [--host 127.0.0.1] [--reload]

Applies both schemas if the database is missing, then serves the dashboard,
the API, the operator console and the daily scheduler from one process.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apix.config import db_path  # noqa: E402

SCHEMAS = [ROOT / "db" / "schema.sql", ROOT / "webapp" / "backend" / "schema_web.sql"]


def ensure_database() -> Path:
    db = db_path()
    conn = sqlite3.connect(db)
    try:
        for s in SCHEMAS:
            if s.exists():
                conn.executescript(s.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    return db


def main() -> int:
    ap = argparse.ArgumentParser(prog="webapp.run", description="Run the APIx web application")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()

    db = ensure_database()
    bar = "-" * 66
    print(bar)
    print("  APIx — Real-time Airfare Price Index for India")
    print(bar)
    print(f"  database    {db}")
    print(f"  dashboard   http://localhost:{a.port}/")
    print(f"  operator    http://localhost:{a.port}/console")
    print(f"  API schema  http://localhost:{a.port}/docs")
    print(bar)

    import uvicorn
    uvicorn.run("webapp.backend.app:app", host=a.host, port=a.port, reload=a.reload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
