"""
The test that matters: does the engine reproduce a number worked out by hand?

Everything else here is a guard on a rule we make a claim about in front of a
jury. If one of these fails, a sentence in the pitch has become untrue.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import math
import sqlite3
import statistics
from pathlib import Path

import pytest

from apix.index.engine import (
    cell_medians, coverage, confidence, national_index,
    price_relatives, route_index,
)
from apix.load.loader import flag_outliers, modified_z_scores, silver_rows_for

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "db" / "schema.sql"


# ---------------------------------------------------------------------------
# THE HAND CALCULATION
# ---------------------------------------------------------------------------
# Two routes, two windows, three identical fares per cell so every median is
# obvious and nothing gets flagged as an outlier.
#
#                   base day        day 1        relative
#   R1  W1            1000           1100          1.10
#   R1  W2            2000           1800          0.90
#   R2  W1             500            600          1.20
#   R2  W2            4000           4000          1.00
#
#   route index R1 = 100 * sqrt(1.10 * 0.90) = 100 * sqrt(0.99) =  99.498744
#   route index R2 = 100 * sqrt(1.20 * 1.00) = 100 * sqrt(1.20) = 109.544512
#
#   APIx = 0.5 * 99.498744 + 0.5 * 109.544512 = 104.521628
#
# Worked on paper first. The engine has to agree with the paper, not the
# other way round.
HAND_APIX = 104.521628

BASE_FARES = {("R1", 1): 1000.0, ("R1", 2): 2000.0,
              ("R2", 1): 500.0,  ("R2", 2): 4000.0}
DAY1_FARES = {("R1", 1): 1100.0, ("R1", 2): 1800.0,
              ("R2", 1): 600.0,  ("R2", 2): 4000.0}


@pytest.fixture
def conn(tmp_path):
    db = sqlite3.connect(tmp_path / "t.db")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA.read_text(encoding="utf-8"))

    def insert(day, fares):
        for (route, window), fare in fares.items():
            for i in range(3):
                db.execute(
                    """
                    INSERT INTO silver_fare_observation
                        (observation_date, route_code, window_days,
                         departure_date, source_id, source_class,
                         status, status_class, carrier, flight_no, total_fare)
                    VALUES (?,?,?,?,'test','LIVE','OK','MARKET',?,?,?)
                    """,
                    (day, route, window, day, "XX", f"{i}", fare),
                )

    insert("2026-09-03", BASE_FARES)
    insert("2026-09-04", DAY1_FARES)
    db.commit()
    yield db
    db.close()


def test_engine_matches_the_hand_calculation(conn):
    base = cell_medians(conn, "2026-09-03", "LIVE")
    today = cell_medians(conn, "2026-09-04", "LIVE")

    assert today[("R1", 1)]["median"] == 1100.0
    assert today[("R1", 2)]["median"] == 1800.0

    rel = price_relatives(today, base)
    assert rel[("R1", 1)] == pytest.approx(1.10)
    assert rel[("R2", 1)] == pytest.approx(1.20)

    by_route = {}
    for (route, _w), r in rel.items():
        by_route.setdefault(route, []).append(r)

    assert route_index(by_route["R1"]) == pytest.approx(99.498744, abs=1e-5)
    assert route_index(by_route["R2"]) == pytest.approx(109.544512, abs=1e-5)

    apix = national_index(
        {r: route_index(v) for r, v in by_route.items()},
        {"R1": 0.5, "R2": 0.5},
    )
    assert apix == pytest.approx(HAND_APIX, abs=1e-5)


def test_base_day_reads_exactly_100(conn):
    base = cell_medians(conn, "2026-09-03", "LIVE")
    rel = price_relatives(base, base)
    by_route = {}
    for (route, _w), r in rel.items():
        by_route.setdefault(route, []).append(r)
    apix = national_index(
        {r: route_index(v) for r, v in by_route.items()},
        {"R1": 0.5, "R2": 0.5},
    )
    assert apix == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Claims we make out loud
# ---------------------------------------------------------------------------
def test_windows_combine_geometrically_not_arithmetically():
    """A doubling and a halving cancel. Under an arithmetic mean they do not,
    and the index would report a 25% rise where nothing changed."""
    assert route_index([2.0, 0.5]) == pytest.approx(100.0)
    assert 100 * statistics.mean([2.0, 0.5]) == pytest.approx(125.0)


def test_a_missing_route_does_not_drag_the_index_down():
    """Re-normalisation. Without it a missing route contributes zero against
    weights that still sum to 1, and the index reports a fall that never
    happened."""
    weights = {"R1": 0.5, "R2": 0.5}
    assert national_index({"R1": 110.0, "R2": None}, weights) == pytest.approx(110.0)
    assert national_index({"R1": 110.0, "R2": 90.0}, weights) == pytest.approx(100.0)


def test_sold_out_counts_as_observed_but_blocked_does_not():
    """METHODOLOGY section 8. The market answering 'nothing for sale' is a
    successful observation. Our scraper failing is not."""
    cells = {
        ("R1", 1): {"status": "OK", "median": 1.0, "n_used": 1, "n_outliers": 0},
        ("R1", 2): {"status": "SOLD_OUT", "median": None, "n_used": 0, "n_outliers": 0},
        ("R2", 1): {"status": "BLOCKED", "median": None, "n_used": 0, "n_outliers": 0},
        ("R2", 2): {"status": "NO_SERVICE", "median": None, "n_used": 0, "n_outliers": 0},
    }
    # Dimensions passed explicitly: a cell nobody ever reported is still
    # expected, so `expected` comes from the basket, not from what turned up.
    observed, expected, cov = coverage(cells, n_routes=2, n_windows=2)
    assert observed == 2          # OK + SOLD_OUT
    assert expected == 3          # NO_SERVICE leaves the denominator entirely
    assert cov == pytest.approx(2 / 3)


def test_a_cell_that_never_reported_still_counts_against_coverage():
    """Silence is not an observation. Four cells reported out of a 30-cell
    basket is coverage 0.13, not 1.00."""
    cells = {("R1", 1): {"status": "OK", "median": 1.0, "n_used": 1, "n_outliers": 0}}
    observed, expected, cov = coverage(cells)      # basket defaults: 6 x 5
    assert (observed, expected) == (1, 30)
    assert cov == pytest.approx(1 / 30)


def test_grade_a_needs_corroboration_not_just_coverage():
    """Perfect coverage from a single portal is a B. A needs two independent
    sources agreeing."""
    assert confidence(1.00, n_sources=1) == "B"
    assert confidence(1.00, n_sources=2) == "A"
    assert confidence(0.80, n_sources=5) == "B"
    assert confidence(0.50, n_sources=5) == "C"


# ---------------------------------------------------------------------------
# The loader's two rules
# ---------------------------------------------------------------------------
def _bronze(status="OK", payload=None, source="replay"):
    return {
        "observation_date": "2026-09-04", "route_code": "DEL-BOM",
        "window_days": 21, "departure_date": "2026-09-25",
        "source_id": source, "source_class": "SIMULATED",
        "fetch_status": status, "payload": payload,
    }


def test_empty_result_is_sold_out_but_broken_payload_is_parse_fail():
    """The single most quotable idea in the project, as a test."""
    sold_out = silver_rows_for(_bronze(payload='{"quotes": []}'))
    assert [r["status"] for r in sold_out] == ["SOLD_OUT"]
    assert sold_out[0]["status_class"] == "MARKET"

    broken = silver_rows_for(_bronze(payload='{"unexpected": "layout changed"}'))
    assert [r["status"] for r in broken] == ["PARSE_FAIL"]
    assert broken[0]["status_class"] == "SYSTEM"


def test_a_failed_fetch_still_produces_a_row():
    """If a blocked cell vanished instead, coverage would silently improve
    every time collection got worse."""
    rows = silver_rows_for(_bronze(status="BLOCKED"))
    assert len(rows) == 1
    assert rows[0]["status"] == "BLOCKED"
    assert rows[0]["total_fare"] is None


def test_outliers_are_flagged_never_removed():
    rows = [
        dict(observation_date="2026-09-04", route_code="DEL-BOM", window_days=21,
             source_class="LIVE", status="OK", total_fare=f, is_outlier=0,
             outlier_score=None)
        for f in [6000, 6100, 6050, 6080, 6020, 6090, 60000]
    ]
    n = flag_outliers(rows)
    assert n == 1
    assert len(rows) == 7                      # nothing was deleted
    assert rows[-1]["is_outlier"] == 1         # the 60,000 is marked
    assert rows[-1]["outlier_score"] > 3.5


def test_mad_edge_cases_do_not_crash_or_flag_everything():
    assert modified_z_scores([100.0, 100.0]) == [0.0, 0.0]          # n < 3
    assert modified_z_scores([5.0] * 6) == [0.0] * 6                # MAD == 0


def test_real_and_simulated_are_never_scored_against_each_other():
    """Scoring a real fare against simulated ones would flag it for being
    real. METHODOLOGY section 4: the two series never touch."""
    rows = [
        dict(observation_date="2026-09-04", route_code="DEL-BOM", window_days=21,
             source_class=sc, status="OK", total_fare=f, is_outlier=0,
             outlier_score=None)
        for sc, f in ([("SIMULATED", 5000.0)] * 6 + [("LIVE", 20000.0)] * 3)
    ]
    flag_outliers(rows)
    assert not any(r["is_outlier"] for r in rows if r["source_class"] == "LIVE")
