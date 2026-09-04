"""
BHARAT — Round 3. Silver rows -> the published index. This is your headline piece.

WHAT THIS DOES, IN ONE SENTENCE
    Turns thousands of individual fares into one number per day that says
    whether flying India got dearer or cheaper.

FOUR STEPS, IN ORDER. Each one feeds the next.

    1. CELL MEDIAN      one number per (route, window, day)
    2. PRICE RELATIVE   that number compared against the base day
    3. ROUTE INDEX      the five windows of a route combined
    4. APIX             the six routes combined into one national number

Plus two things computed in the SAME pass, not bolted on afterwards:
    COVERAGE    what fraction of what we expected did we actually observe
    CONFIDENCE  A / B / C, published on every value

Every formula here is specified in METHODOLOGY.md sections 3 to 9. Implement
what is written there. If a formula looks wrong to you, tell Ayush -- do not
quietly change it, because he has to defend it on Monday.

RUN IT:
    python -m apix.index.engine
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "apix.db"

METHOD_VERSION = "0.1"

# The base day for the REAL index: our first real collection day.
# The real series starts at 100 here. Simulated history is based separately
# and never anchors the real numbers. (METHODOLOGY.md section 4.)
BASE_DATE = date(2026, 9, 3)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# STEP 1 — cell median
# ---------------------------------------------------------------------------
def cell_medians(conn, observation_date: str) -> dict[tuple[str, int], dict]:
    """One median per (route, window) for a given day.

    METHODOLOGY.md section 3:
        P(r,w,t) = median of total_fare, over rows where
                   status = 'OK' AND is_outlier = 0

    Note what is excluded: outliers are flagged in Silver and left out HERE,
    at aggregation. The row still exists in the database -- we exclude it from
    the average, we do not delete it.

    Return shape:
        { ("DEL-BOM", 21): {"median": 7675.0, "n_used": 221,
                            "n_outliers": 3, "status": "OK"}, ... }

    A cell with no OK rows still needs an entry, with median None and the
    status that explains why (BLOCKED, SOLD_OUT, PARSE_FAIL...). Coverage
    depends on knowing the difference.
    """
    # TODO: SELECT the OK rows for this date, group them in Python by
    # (route_code, window_days), take statistics.median of total_fare.
    # Then SELECT the non-OK cells so you can record their status too.
    raise NotImplementedError("BHARAT: cell medians")


# ---------------------------------------------------------------------------
# STEP 2 — price relative
# ---------------------------------------------------------------------------
def price_relatives(conn, medians: dict, base_medians: dict) -> dict:
    """Compare each cell against the same cell on the base day.

    METHODOLOGY.md section 4:
        R(r,w,t) = P(r,w,t) / P(r,w,0)

    On the base day itself every relative is exactly 1.0, which is why the
    index reads 100 there.

    If a cell has no median today, or had none on the base day, it has no
    relative. Skip it -- and remember you skipped it, because that is what
    lowers coverage.
    """
    # TODO: divide today's median by the base day's median, per cell.
    raise NotImplementedError("BHARAT: price relatives")


# ---------------------------------------------------------------------------
# STEP 3 — route index (GEOMETRIC mean)
# ---------------------------------------------------------------------------
def route_index(relatives_for_one_route: list[float]) -> float:
    """Combine one route's window relatives into that route's index.

    METHODOLOGY.md section 6:
        I(r,t) = 100 * ( product of all R ) ^ (1 / number_of_R)

    This is a GEOMETRIC mean, not a normal average. It is called a Jevons
    index and it is the same form CPI uses for elementary aggregation.

    WHY geometric here: the windows are ratios, and ratios multiply. A plain
    average would let T+1 -- the dearest and most jumpy window -- dominate.

    Safe way to compute it (avoids overflow on many values):
        exp( mean( log(r) for r in relatives ) ) * 100

    Every relative is > 0, so log is always safe. If the list is empty,
    return None rather than crashing -- an empty route is a coverage problem,
    not an exception.
    """
    # TODO: implement the geometric mean.
    raise NotImplementedError("BHARAT: route index, geometric mean")


# ---------------------------------------------------------------------------
# STEP 4 — national index (WEIGHTED ARITHMETIC mean)
# ---------------------------------------------------------------------------
def national_index(route_indices: dict[str, float], weights: dict[str, float]) -> float:
    """Combine the six route indices into one national number.

    METHODOLOGY.md section 7:
        APIx(t) = sum over routes of ( weight_r * I(r,t) )    weights sum to 1

    This one IS a normal weighted average, NOT geometric. That difference
    matters and you will be asked about it:

        windows  -> geometric, because they are repeated measures of the
                    same route's price, and they carry no spending weight
        routes   -> arithmetic, because each route carries a real share of
                    what travellers actually spend, like a budget share

    If some routes are missing today, re-normalise the weights over the
    routes you do have, so they still sum to 1. Otherwise a missing route
    silently drags the index down, which would be the index lying.
    """
    # TODO: implement the weighted sum with re-normalisation.
    raise NotImplementedError("BHARAT: national index")


# ---------------------------------------------------------------------------
# COVERAGE AND CONFIDENCE — same pass, not an afterthought
# ---------------------------------------------------------------------------
def coverage(medians: dict, n_routes: int = 6, n_windows: int = 5) -> tuple[int, int, float]:
    """METHODOLOGY.md section 8. Returns (observed, expected, ratio).

        expected = 30 minus any cell whose status is NO_SERVICE
                   (no flight exists, so there was never anything to observe)
        observed = cells whose status is OK or SOLD_OUT
                   (SOLD_OUT COUNTS -- we checked, and the market said
                    "nothing for sale". That is a successful observation.)

    Everything else -- BLOCKED, FETCH_FAIL, PARSE_FAIL, SOURCE_DISALLOWED --
    is a gap and pulls coverage down.
    """
    # TODO: implement.
    raise NotImplementedError("BHARAT: coverage")


def confidence(cov: float, n_source_classes: int) -> str:
    """METHODOLOGY.md section 9.

        A  cov >= 0.90 AND at least 2 source classes
        B  cov >= 0.70
        C  anything else -- still published, marked provisional

    We publish a C. We just say it is a C. An index built from 11 of 30
    observations and one built from 30 of 30 are not the same fact, and most
    official series never tell you which one you are looking at.
    """
    # TODO: implement.
    raise NotImplementedError("BHARAT: confidence grade")


# ---------------------------------------------------------------------------
# Put it together
# ---------------------------------------------------------------------------
def compute_day(conn, observation_date: str, weights: dict[str, float]) -> dict:
    """Run all four steps for one day and write gold_cell_median,
    gold_route_index_daily and gold_apix_daily.

    Stamp EVERY gold row with method_version = METHOD_VERSION.
    Stamp gold_apix_daily with weights_provisional = 1 while the weights are
    still equal-weighted (they are, until Ayush finds DGCA passenger data).
    """
    # TODO: orchestrate steps 1-4, compute coverage and confidence, INSERT.
    raise NotImplementedError("BHARAT: tie the four steps together")


def main() -> None:
    from apix.config import load_basket

    basket = load_basket()
    weights = basket.effective_weights()
    provisional = basket.weights_provisional

    conn = connect()
    days = [r[0] for r in conn.execute(
        "SELECT DISTINCT observation_date FROM silver_fare_observation ORDER BY 1"
    ).fetchall()]

    print(f"weights: {'PROVISIONAL (equal)' if provisional else 'from DGCA'}")
    print(f"days to compute: {len(days)}")
    for d in days:
        compute_day(conn, d, weights)
    conn.close()
    print("done -- check gold_apix_daily")


if __name__ == "__main__":
    main()
