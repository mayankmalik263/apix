"""
The check METHODOLOGY.md claims: recompute the published index from the Silver
rows without using the engine, and see whether the two agree.

This deliberately re-implements the arithmetic from the formulas in the
document rather than importing anything from apix.index.engine. Importing the
engine would only prove the engine equals itself. If these numbers ever
disagree, that is the most important bug in the project -- either the code has
drifted from the documented method, or the document describes something the
code does not do.

It was that disagreement, caught here, which showed section 3 excluded flagged
rows from the median while the engine kept them.
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parents[1] / "apix.db"
BASE_DAY = "2026-09-03"


def _cell_medians(conn: sqlite3.Connection, day: str) -> dict[tuple[str, int], float]:
    """METHODOLOGY section 3: median of the OK fares in each cell.

    Flagged rows are included -- is_outlier is not in the WHERE clause, which
    is the whole point of the check.
    """
    fares: dict[tuple[str, int], list[float]] = {}
    for r in conn.execute(
        "SELECT route_code, window_days, total_fare "
        "FROM silver_fare_observation "
        "WHERE observation_date = ? AND source_class = 'LIVE' AND status = 'OK'",
        (day,),
    ):
        fares.setdefault((r[0], r[1]), []).append(r[2])
    return {k: statistics.median(v) for k, v in fares.items()}


def _apix_by_hand(conn: sqlite3.Connection, day: str) -> float:
    base = _cell_medians(conn, BASE_DAY)
    today = _cell_medians(conn, day)

    # Section 4: R = P(t) / P(0), skipping any cell without both.
    by_route: dict[str, list[float]] = {}
    for cell, median in today.items():
        if base.get(cell):
            by_route.setdefault(cell[0], []).append(median / base[cell])

    # Section 6: route index is the GEOMETRIC mean of its window relatives.
    route_indices = []
    for relatives in by_route.values():
        product = 1.0
        for r in relatives:
            product *= r
        route_indices.append(100 * product ** (1 / len(relatives)))

    # Section 7: national index is the weighted ARITHMETIC mean across routes.
    # Weights are provisional and equal, so this is a plain mean.
    return sum(route_indices) / len(route_indices)


@pytest.mark.skipif(not DB.exists(), reason="run the loader and engine first")
def test_published_index_matches_a_hand_recomputation():
    conn = sqlite3.connect(DB)
    published = conn.execute(
        "SELECT observation_date, apix FROM gold_apix_daily "
        "WHERE source_class = 'LIVE' ORDER BY observation_date"
    ).fetchall()
    assert published, "no LIVE index published yet"

    for day, engine_value in published:
        assert _apix_by_hand(conn, day) == pytest.approx(engine_value, abs=1e-3), day


@pytest.mark.skipif(not DB.exists(), reason="run the loader and engine first")
def test_the_base_day_reads_exactly_100():
    conn = sqlite3.connect(DB)
    assert _apix_by_hand(conn, BASE_DAY) == pytest.approx(100.0, abs=1e-9)
