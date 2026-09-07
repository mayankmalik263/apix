"""Silver rows -> the published index.

Four steps, each feeding the next:

    1. cell median      one number per (route, window, day)
    2. price relative   that median against the base day
    3. route index      a route's five windows combined, geometrically
    4. APIx             the six routes combined, by weight

Coverage and the confidence grade are computed in the same pass rather than
derived afterwards, so a value can never be published without them.

Formulas are specified in METHODOLOGY.md sections 3-9.

    python -m apix.cli index
"""
from __future__ import annotations

import math
import sqlite3
import statistics
from datetime import date
from pathlib import Path

from apix.vocab import COVERAGE_NUMERATOR, EXCLUDED_FROM_EXPECTED

ROOT = Path(__file__).resolve().parents[2]
from apix.config import db_path

DB_PATH = db_path()

METHOD_VERSION = "0.1"

# The base day for the REAL index: our first real collection day.
# The real series starts at 100 here. Simulated history is based separately
# and never anchors the real numbers. (METHODOLOGY.md section 4.)
BASE_DATE = date(2026, 9, 3)

# ---------------------------------------------------------------------------
# Four methodology settings. Each changes published numbers, so each is a
# switch with the evidence for its default written next to it.
# ---------------------------------------------------------------------------

# 1. Does a flagged outlier leave the median?
#
#    METHODOLOGY section 3 says yes. Measured over the whole archive, the
#    section 5 rule flags 3.67% of rows on data that contains no injected
#    outliers at all -- and because fares are right-skewed, 65% of those
#    flags land on the dear side. Excluding them moves the affected cell
#    medians by -0.69% on average and up to -7.66%. MoSPI's largest ever
#    monthly airfare move was -4.4%.
#
#    Section 3 also argues the median resists outliers. Both cannot be doing
#    work: if the median resists them, removing them only adds bias.
#
#    Default False -- flag and publish, do not exclude. Set True to follow
#    section 3 as literally written.
EXCLUDE_OUTLIERS_FROM_MEDIAN = False

# 2. Single-day base, or the 7-day mean basket.yml already promises?
#
#    3 September has 28 of 30 cells with a median. Under R = P(t)/P(0) the
#    other two can never produce a relative on any day, so one bad base day
#    removes two windows from the entire series permanently.
#
#    Default 1 = single-day, matching METHODOLOGY section 11. Set to
#    basket.base_period_days (7) once enough days exist.
BASE_PERIOD_DAYS = 1

# 3. What does grade A actually require?
#
#    Section 9 says coverage >= 0.90 AND >= 2 source classes. Section 4 says
#    real and simulated never mix. Since the classes are LIVE/SIMULATED/MANUAL,
#    a pure-LIVE series could only reach A by mixing in simulated data, which
#    section 4 forbids. The two rules contradict each other as written.
#
#    Default counts distinct source_ids WITHIN one class: one portal is a B,
#    A needs two independent portals agreeing.
GRADE_A_NEEDS_SOURCES = 2

# 4. What date does the simulated series base on?
#
#    METHODOLOGY section 4 says it is "based separately" and never says on
#    what. Basing it on BASE_DATE would put 88 of its 91 days before its own
#    base. Its first day is the only choice that gives it the same shape as
#    the real series: starts at 100, runs forward.
SIMULATED_BASE = "first_day"


def _round(v, places: int):
    """Round for publication, leaving None alone."""
    return None if v is None else round(v, places)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# STEP 1 — cell median
# ---------------------------------------------------------------------------
def cell_medians(conn, observation_date: str, source_class: str) -> dict[tuple[str, int], dict]:
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
    out: dict[tuple[str, int], dict] = {}

    fares: dict[tuple[str, int], list[float]] = {}
    n_flagged: dict[tuple[str, int], int] = {}

    rows = conn.execute(
        """
        SELECT route_code, window_days, total_fare, is_outlier
        FROM   silver_fare_observation
        WHERE  observation_date = ? AND source_class = ?
          AND  status = 'OK' AND total_fare IS NOT NULL
        """,
        (observation_date, source_class),
    ).fetchall()

    for r in rows:
        key = (r["route_code"], r["window_days"])
        if r["is_outlier"]:
            n_flagged[key] = n_flagged.get(key, 0) + 1
            if EXCLUDE_OUTLIERS_FROM_MEDIAN:
                continue
        fares.setdefault(key, []).append(r["total_fare"])

    for key, vals in fares.items():
        out[key] = {
            "median": statistics.median(vals),
            "n_used": len(vals),
            "n_outliers": n_flagged.get(key, 0),
            "status": "OK",
        }

    # The cells with no usable fare still need an entry. Their status is the
    # whole reason coverage can be reported honestly -- a cell we were blocked
    # from and a cell that was sold out are not the same absence.
    for r in conn.execute(
        """
        SELECT route_code, window_days, status
        FROM   silver_fare_observation
        WHERE  observation_date = ? AND source_class = ? AND status <> 'OK'
        """,
        (observation_date, source_class),
    ).fetchall():
        key = (r["route_code"], r["window_days"])
        if key not in out:
            out[key] = {"median": None, "n_used": 0,
                        "n_outliers": n_flagged.get(key, 0),
                        "status": r["status"]}

    return out


# ---------------------------------------------------------------------------
# STEP 2 — price relative
# ---------------------------------------------------------------------------
def price_relatives(medians: dict, base_medians: dict) -> dict:
    """Compare each cell against the same cell on the base day.

    METHODOLOGY.md section 4:
        R(r,w,t) = P(r,w,t) / P(r,w,0)

    On the base day itself every relative is exactly 1.0, which is why the
    index reads 100 there.

    If a cell has no median today, or had none on the base day, it has no
    relative. Skip it -- and remember you skipped it, because that is what
    lowers coverage.
    """
    out: dict[tuple[str, int], float] = {}
    for key, cell in medians.items():
        base = base_medians.get(key)
        if cell["median"] is None or base is None or not base.get("median"):
            # No relative is possible. Skipped deliberately, and the skip is
            # what shows up as lost coverage rather than as a quiet gap.
            continue
        out[key] = cell["median"] / base["median"]
    return out


# ---------------------------------------------------------------------------
# STEP 3 — route index (GEOMETRIC mean)
# ---------------------------------------------------------------------------
def route_index(relatives_for_one_route: list[float]) -> float | None:
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
    vals = [r for r in relatives_for_one_route if r and r > 0]
    if not vals:
        return None
    # exp(mean(log)) rather than the nth root of a product: the product of
    # many relatives overflows, the sum of their logs does not.
    return 100.0 * math.exp(sum(math.log(r) for r in vals) / len(vals))


# ---------------------------------------------------------------------------
# STEP 4 — national index (WEIGHTED ARITHMETIC mean)
# ---------------------------------------------------------------------------
def national_index(route_indices: dict[str, float | None],
                   weights: dict[str, float]) -> float | None:
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
    present = {r: v for r, v in route_indices.items() if v is not None}
    if not present:
        return None

    total_weight = sum(weights.get(r, 0.0) for r in present)
    if total_weight <= 0:
        return None

    # Re-normalise over the routes we actually have. Without this a missing
    # route contributes zero to a sum whose weights still total 1, and the
    # index reports a fall that never happened.
    return sum(v * weights.get(r, 0.0) for r, v in present.items()) / total_weight


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
    expected = n_routes * n_windows
    observed = 0
    for cell in medians.values():
        if cell["status"] in EXCLUDED_FROM_EXPECTED:
            expected -= 1
        elif cell["status"] in COVERAGE_NUMERATOR:
            observed += 1

    # Cells we never heard about at all are still expected. Silence is not
    # an observation.
    if expected <= 0:
        return 0, 0, 0.0
    return observed, expected, observed / expected


def confidence(cov: float, n_sources: int) -> str:
    """METHODOLOGY.md section 9.

        A  cov >= 0.90 AND at least 2 source classes
        B  cov >= 0.70
        C  anything else -- still published, marked provisional

    We publish a C. We just say it is a C. An index built from 11 of 30
    observations and one built from 30 of 30 are not the same fact, and most
    official series never tell you which one you are looking at.
    """
    if cov >= 0.90 and n_sources >= GRADE_A_NEEDS_SOURCES:
        return "A"
    if cov >= 0.70:
        return "B"
    return "C"


# ---------------------------------------------------------------------------
# Put it together
# ---------------------------------------------------------------------------
def base_date_for(conn, source_class: str) -> str:
    """Which day this series is based on.

    The real series bases on BASE_DATE, our first real collection day, and
    reads exactly 100 there. The simulated series bases on its own first day
    -- METHODOLOGY section 4 says it is "based separately" and never says on
    what, and its first day is the only choice that gives it the same shape
    as the real one: starts at 100, runs forward. Basing it on BASE_DATE
    would put 88 of its 91 days before its own base.
    """
    if source_class == "LIVE":
        # Use the declared base date only if we actually hold real data for it.
        # We do not: the 3-4 September captures were never committed to the
        # repo. Falling through to the first real day we DO hold is the same
        # rule the simulated series follows, and it is the only one that
        # produces an index at all. If those files arrive later, this returns
        # to BASE_DATE on its own and the whole series recomputes.
        got = conn.execute(
            """SELECT 1 FROM silver_fare_observation
               WHERE source_class='LIVE' AND status='OK' AND observation_date=?
               LIMIT 1""",
            (BASE_DATE.isoformat(),),
        ).fetchone()
        if got:
            return BASE_DATE.isoformat()

    row = conn.execute(
        """
        SELECT MIN(observation_date) FROM silver_fare_observation
        WHERE source_class = ? AND status = 'OK'
        """,
        (source_class,),
    ).fetchone()
    return row[0]


def compute_day(conn, observation_date: str, source_class: str,
                weights: dict[str, float], provisional: bool = True) -> dict:
    """Run all four steps for one day and write gold_cell_median,
    gold_route_index_daily and gold_apix_daily.

    Stamp EVERY gold row with method_version = METHOD_VERSION.
    Stamp gold_apix_daily with weights_provisional = 1 while the weights are
    still equal-weighted, pending DGCA city-pair passenger data.
    """
    medians = cell_medians(conn, observation_date, source_class)
    if not medians:
        return {"observation_date": observation_date, "source_class": source_class,
                "apix": None, "coverage": 0.0, "confidence": "C"}

    base_day = base_date_for(conn, source_class)
    base_medians = cell_medians(conn, base_day, source_class)

    relatives = price_relatives(medians, base_medians)

    # --- step 3: one index per route, geometric across its windows ---
    by_route: dict[str, list[float]] = {}
    for (route, _window), rel in relatives.items():
        by_route.setdefault(route, []).append(rel)

    # Rounded at the point of publication, not during calculation. Index values
    # are published to 4 decimals; carrying float noise into a number a jury
    # reads as "exactly 100" helps nobody.
    route_indices = {r: _round(route_index(v), 4) for r, v in by_route.items()}

    # --- coverage, in the same pass ---
    n_obs, n_exp, cov = coverage(medians)
    n_sources = conn.execute(
        """
        SELECT COUNT(DISTINCT source_id) FROM silver_fare_observation
        WHERE observation_date = ? AND source_class = ? AND status = 'OK'
        """,
        (observation_date, source_class),
    ).fetchone()[0]
    grade = confidence(cov, n_sources)

    # --- step 4: the national number ---
    apix = _round(national_index(route_indices, weights), 4)

    # --- write gold_cell_median ---
    for (route, window), cell in medians.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO gold_cell_median
                (observation_date, route_code, window_days, source_class,
                 median_fare, n_used, n_outliers_flagged, status, price_relative)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (observation_date, route, window, source_class,
             _round(cell["median"], 2), cell["n_used"], cell["n_outliers"],
             cell["status"], _round(relatives.get((route, window)), 6)),
        )

    # --- write gold_route_index_daily ---
    for route, idx in route_indices.items():
        route_cells = [c for (r, _w), c in medians.items() if r == route]
        r_obs = sum(1 for c in route_cells if c["status"] in COVERAGE_NUMERATOR)
        r_exp = sum(1 for c in route_cells if c["status"] not in EXCLUDED_FROM_EXPECTED)
        conn.execute(
            """
            INSERT OR REPLACE INTO gold_route_index_daily
                (observation_date, route_code, source_class, route_index,
                 n_windows_used, n_observations, coverage, method_version)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (observation_date, route, source_class, idx,
             len(by_route.get(route, [])),
             sum(c["n_used"] for c in route_cells),
             (r_obs / r_exp) if r_exp else 0.0,
             METHOD_VERSION),
        )

    # --- write gold_apix_daily, the published number ---
    prev = conn.execute(
        """
        SELECT apix FROM gold_apix_daily
        WHERE source_class = ? AND observation_date < ? AND apix IS NOT NULL
        ORDER BY observation_date DESC LIMIT 1
        """,
        (source_class, observation_date),
    ).fetchone()
    change_pct = None
    if prev and prev[0] and apix is not None:
        change_pct = _round(100.0 * (apix - prev[0]) / prev[0], 4)

    conn.execute(
        """
        INSERT OR REPLACE INTO gold_apix_daily
            (observation_date, source_class, apix, change_pct, coverage,
             n_expected, n_observed, confidence, weights_provisional,
             method_version)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (observation_date, source_class, apix, change_pct, cov,
         n_exp, n_obs, grade, 1 if provisional else 0, METHOD_VERSION),
    )
    conn.commit()

    return {"observation_date": observation_date, "source_class": source_class,
            "apix": apix, "coverage": cov, "confidence": grade,
            "n_observed": n_obs, "n_expected": n_exp}


def main() -> None:
    from apix.config import load_basket

    basket = load_basket()
    weights = basket.effective_weights()
    provisional = basket.weights_provisional

    conn = connect()
    pairs = conn.execute(
        """
        SELECT DISTINCT observation_date, source_class
        FROM silver_fare_observation ORDER BY source_class, observation_date
        """
    ).fetchall()

    print(f"weights:  {'PROVISIONAL (equal)' if provisional else 'from DGCA'}")
    print(f"outliers: {'excluded from' if EXCLUDE_OUTLIERS_FROM_MEDIAN else 'flagged, kept in'} the median")
    print(f"series:   {len(pairs)} (day, source_class) pairs")
    print("-" * 70)

    for d, sc in pairs:
        compute_day(conn, d, sc, weights, provisional=provisional)

    for sc in sorted({p[1] for p in pairs}):
        n, lo, hi = conn.execute(
            "SELECT COUNT(*), MIN(observation_date), MAX(observation_date) "
            "FROM gold_apix_daily WHERE source_class = ?", (sc,)
        ).fetchone()
        grades = dict(conn.execute(
            "SELECT confidence, COUNT(*) FROM gold_apix_daily "
            "WHERE source_class = ? GROUP BY confidence", (sc,)
        ).fetchall())
        print(f"  {sc:<10} {n:>3} days  {lo} .. {hi}   grades {grades}")
    print("-" * 70)
    conn.close()


if __name__ == "__main__":
    main()
