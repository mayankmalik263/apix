-- ===========================================================================
-- APIx database schema  ·  SQLite
-- ===========================================================================
--
-- This is the file the demo actually runs on. SQLite because it installs
-- nowhere and cannot fail on stage. See db/schema.postgres.sql for the
-- production version and the difference between them.
--
-- Seven tables, three layers:
--     BRONZE   raw, exactly as collected, never edited
--     SILVER   one clean row per flight quote
--     GOLD     the published index
-- plus source_registry (compliance evidence) and ground_truth (human checks).
--
-- APPLY IT:
--     sqlite3 apix.db < db/schema.sql
--
-- NOT NULL where a value can never legitimately be missing; CHECK where the
-- values are a fixed list, so the database rejects a bad write rather than
-- storing it.
-- ===========================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;


-- ---------------------------------------------------------------------------
-- BRONZE — the raw archive, mirrored from the JSONL files
-- ---------------------------------------------------------------------------
-- No UNIQUE constraint here:
-- Bronze is append-only and we never want a write to be silently rejected.
CREATE TABLE IF NOT EXISTS bronze_observation_raw (
    id                INTEGER PRIMARY KEY,
    observation_date  TEXT    NOT NULL,
    route_code        TEXT    NOT NULL,
    window_days       INTEGER NOT NULL,
    departure_date    TEXT    NOT NULL,
    source_id         TEXT    NOT NULL,
    source_class      TEXT    NOT NULL
                              CHECK (source_class IN ('LIVE','SIMULATED','MANUAL')),
    fetch_status      TEXT    NOT NULL,
    http_status       INTEGER,
    request_url       TEXT,
    user_agent        TEXT,
    payload           TEXT,           -- the raw response body, verbatim
    payload_sha256    TEXT,           -- proof it has not been altered
    error_detail      TEXT,
    fetched_at_utc    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_bronze_cell
    ON bronze_observation_raw (observation_date, route_code, window_days);


-- ---------------------------------------------------------------------------
-- SILVER — one row per flight quote
-- ---------------------------------------------------------------------------
-- The UNIQUE constraint at the bottom is what makes the loader safe to run
-- twice. See the note under it: on its own it does not hold.
CREATE TABLE IF NOT EXISTS silver_fare_observation (
    id                INTEGER PRIMARY KEY,
    bronze_id         INTEGER REFERENCES bronze_observation_raw(id),

    observation_date  TEXT    NOT NULL,
    route_code        TEXT    NOT NULL,
    window_days       INTEGER NOT NULL,
    departure_date    TEXT    NOT NULL,
    source_id         TEXT    NOT NULL,
    source_class      TEXT    NOT NULL,

    -- The controlled vocabulary. Seven values, and the database itself
    -- refuses an eighth. If an INSERT fails here, the bug is upstream.
    status            TEXT    NOT NULL
                              CHECK (status IN ('OK','SOLD_OUT','NO_SERVICE',
                                                'SOURCE_DISALLOWED','FETCH_FAIL',
                                                'BLOCKED','PARSE_FAIL')),
    status_class      TEXT    NOT NULL
                              CHECK (status_class IN ('MARKET','POLICY','SYSTEM')),

    carrier           TEXT,
    flight_no         TEXT,
    departure_time    TEXT,
    stops             INTEGER,

    base_fare         REAL,
    taxes             REAL,
    fees              REAL,
    total_fare        REAL,
    currency          TEXT    NOT NULL DEFAULT 'INR',

    -- The source's own identifier for this quote. Without it two genuinely
    -- different fares that happen to share a carrier and a price collapse into
    -- one row, which silently moves the median.
    fare_ref          TEXT,

    is_outlier        INTEGER NOT NULL DEFAULT 0,
    outlier_score     REAL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),

    -- The logical flight key. This is what makes re-running the loader a
    -- no-op instead of a duplication.
    UNIQUE (observation_date, route_code, window_days, source_id,
            carrier, flight_no, total_fare)
);

-- The UNIQUE above states the logical key, and it is correct as a statement of
-- intent. On its own it does not enforce it.
--
-- SQLite follows the SQL standard: inside a UNIQUE index every NULL is
-- distinct from every other NULL. Live Cleartrip fares carry no flight number,
-- so flight_no is NULL on every real row -- and a non-OK cell has carrier,
-- flight_no AND total_fare all NULL. For those rows the constraint compares
-- NULL to NULL, decides they differ, and INSERT OR IGNORE inserts a duplicate.
-- Row counts double on every re-run for exactly the rows we care most about.
--
-- Verified, not assumed: three identical runs of a two-row insert leave four
-- rows -- one for the populated row, three for the NULL-bearing one.
--
-- This index is the constraint that actually holds. COALESCE gives the NULLs a
-- concrete value so the comparison can happen at all.
CREATE UNIQUE INDEX IF NOT EXISTS ux_silver_flight_key
    ON silver_fare_observation (
        observation_date, route_code, window_days, source_id,
        COALESCE(carrier, ''), COALESCE(flight_no, ''), COALESCE(total_fare, -1),
        COALESCE(fare_ref, '')
    );

CREATE INDEX IF NOT EXISTS ix_silver_cell
    ON silver_fare_observation (observation_date, route_code, window_days);
CREATE INDEX IF NOT EXISTS ix_silver_status
    ON silver_fare_observation (status);


-- ---------------------------------------------------------------------------
-- GOLD — the published index. Built from Silver, never from Bronze directly.
-- ---------------------------------------------------------------------------
-- Three tables because the index is computed in three steps and a jury has to
-- be able to stop at any one of them. gold_apix_daily alone would be a number
-- nobody could check.
--
-- ONE DEVIATION FROM THE SPEC, AND THE REASON FOR IT
-- --------------------------------------------------
-- The starting brief keyed gold_apix_daily on observation_date alone. All
-- three Gold tables here carry source_class in the key instead.
--
-- METHODOLOGY.md section 4: "The simulated history is based separately and
-- drawn as a separate line. It never anchors the real series. Nothing real is
-- ever computed from a simulated number."
--
-- On 3, 4 and 5 September we hold BOTH a live Cleartrip collection and
-- simulated history for the same day. With one row per day, those two get
-- averaged into a single value and the rule above is broken silently, inside
-- a median, where nobody would ever find it. With source_class in the key
-- they are two series that never touch, the dashboard draws two lines
-- because there are two rows, and the separation is enforced by the database
-- rather than remembered by whoever writes the next query.
--
-- Consumers of /v1/apix/* filter on source_class; it defaults to LIVE.

-- One row per (route, window, day). The bottom of the drill-down: a published
-- APIx traces to a route index, a route index to five of these, and each of
-- these to the Silver rows it took the median of.
--
-- median_fare is NULL when the cell had no OK rows. That is not a zero and it
-- is not an average of nothing -- it is an absence, and `status` says whose
-- fault the absence was.
CREATE TABLE IF NOT EXISTS gold_cell_median (
    id                 INTEGER PRIMARY KEY,
    observation_date   TEXT    NOT NULL,
    route_code         TEXT    NOT NULL,
    window_days        INTEGER NOT NULL,

    -- REAL and SIMULATED fares are never averaged together. See the note at
    -- the top of the GOLD section.
    source_class       TEXT    NOT NULL
                               CHECK (source_class IN ('LIVE','SIMULATED','MANUAL')),

    median_fare        REAL,               -- NULL when the cell had no OK rows
    n_used             INTEGER NOT NULL DEFAULT 0,   -- OK, non-outlier rows
    n_outliers_flagged INTEGER NOT NULL DEFAULT 0,   -- excluded here, kept in Silver

    -- Same seven values as Silver. A cell's status is the status of the thing
    -- that stopped it having a median, or OK when nothing did.
    status             TEXT    NOT NULL
                               CHECK (status IN ('OK','SOLD_OUT','NO_SERVICE',
                                                 'SOURCE_DISALLOWED','FETCH_FAIL',
                                                 'BLOCKED','PARSE_FAIL')),

    price_relative     REAL,               -- this cell's median / base day's median

    UNIQUE (observation_date, route_code, window_days, source_class)
);

CREATE INDEX IF NOT EXISTS ix_cell_median_day
    ON gold_cell_median (observation_date);
CREATE INDEX IF NOT EXISTS ix_cell_median_route
    ON gold_cell_median (route_code, window_days, observation_date);


-- One row per (route, day). The geometric mean of that route's window
-- relatives -- a Jevons index, the same elementary form CPI uses.
--
-- coverage lives here as well as on the national row because a route can be
-- fully observed on a day the national number is not, and "which route did we
-- lose" is the first question after "why is coverage down".
CREATE TABLE IF NOT EXISTS gold_route_index_daily (
    id                INTEGER PRIMARY KEY,
    observation_date  TEXT    NOT NULL,
    route_code        TEXT    NOT NULL,

    route_index       REAL,                        -- NULL when no window survived
    n_windows_used    INTEGER NOT NULL DEFAULT 0,  -- out of 5
    n_observations    INTEGER NOT NULL DEFAULT 0,  -- Silver rows behind it

    coverage          REAL    NOT NULL DEFAULT 0,

    -- Which version of METHODOLOGY.md produced this number. Recomputing the
    -- series under 0.2 must not silently overwrite what 0.1 said.
    method_version    TEXT    NOT NULL,
    source_class      TEXT    NOT NULL
                              CHECK (source_class IN ('LIVE','SIMULATED','MANUAL')),

    UNIQUE (observation_date, route_code, source_class)
);

CREATE INDEX IF NOT EXISTS ix_route_index_day
    ON gold_route_index_daily (observation_date);


-- THE PUBLISHED NUMBER. One row per day.
--
-- Everything that qualifies the number sits on the same row as the number:
-- coverage, how many cells that was out of how many, the confidence grade, and
-- whether the weights behind it are real. A consumer cannot read the value
-- without also reading what it is worth.
CREATE TABLE IF NOT EXISTS gold_apix_daily (
    id                  INTEGER PRIMARY KEY,
    observation_date    TEXT    NOT NULL,

    apix                REAL,                        -- NULL if no route survived
    change_pct          REAL,                        -- vs the previous published day

    coverage            REAL    NOT NULL DEFAULT 0,
    n_expected          INTEGER NOT NULL DEFAULT 0,  -- 30 minus NO_SERVICE cells
    n_observed          INTEGER NOT NULL DEFAULT 0,  -- OK or SOLD_OUT cells

    -- We publish a C. We just say it is a C.
    confidence          TEXT    NOT NULL DEFAULT 'C'
                                CHECK (confidence IN ('A','B','C')),

    -- 1 while the route weights are equal-weighted pending DGCA city-pair
    -- passenger data. Set by the engine from the basket, never by hand.
    weights_provisional INTEGER NOT NULL DEFAULT 1
                                CHECK (weights_provisional IN (0,1)),

    source_class        TEXT    NOT NULL
                                CHECK (source_class IN ('LIVE','SIMULATED','MANUAL')),
    method_version      TEXT    NOT NULL,
    computed_at         TEXT    NOT NULL DEFAULT (datetime('now')),

    -- NOT unique on observation_date alone. On a day where we collected live
    -- fares AND hold simulated history, both exist, separately, and the
    -- dashboard draws them as two lines.
    UNIQUE (observation_date, source_class)
);


-- ---------------------------------------------------------------------------
-- EVIDENCE — what we were allowed to do, and what a human saw
-- ---------------------------------------------------------------------------

-- Mirrored from compliance/verdicts/<date>.json. In the database because
-- "which sources were permitted on the day this number was collected" is a
-- property of the observation, not a note in a folder.
--
-- Keyed on (source_id, checked_on): the verdict is re-established every
-- collection day and a source that timed out on Wednesday may answer on
-- Thursday. The history of verdicts is itself the finding.
CREATE TABLE IF NOT EXISTS source_registry (
    id             INTEGER PRIMARY KEY,
    source_id      TEXT    NOT NULL,
    source_name    TEXT    NOT NULL,
    kind           TEXT,                   -- airline | ota
    checked_on     TEXT    NOT NULL,

    verdict        TEXT    NOT NULL
                           CHECK (verdict IN ('PERMITTED','DISALLOWED','BLOCKED','UNKNOWN')),
    reason         TEXT,                   -- in words, quotable on a slide

    robots_sha256  TEXT,                   -- the robots.txt we actually read
    http_status    INTEGER,
    evidence_file  TEXT,                   -- the saved copy, under compliance/evidence/

    UNIQUE (source_id, checked_on)
);

CREATE INDEX IF NOT EXISTS ix_registry_day
    ON source_registry (checked_on);


-- The human panel, loaded from data/ground_truth.csv. Collected by hand, on a
-- phone, from the same websites, in the same hour as the automated run.
--
-- This is the only table in the database our own code did not produce, which
-- is exactly why it is here: it is the independent check on whether the
-- pipeline tells the truth.
CREATE TABLE IF NOT EXISTS ground_truth (
    id                INTEGER PRIMARY KEY,
    observation_date  TEXT    NOT NULL,
    route_code        TEXT    NOT NULL,
    window_days       INTEGER NOT NULL,
    departure_date    TEXT    NOT NULL,

    checker           TEXT    NOT NULL,    -- who looked. Attribution is evidence.
    time_checked      TEXT,
    website           TEXT,
    airline           TEXT,
    flight_no         TEXT,
    fare_shown        REAL,                -- NULL when status is not OK

    -- Same vocabulary as the machine. A human writes NO_SERVICE for the same
    -- reason the collector does, and never leaves the cell blank.
    status            TEXT    NOT NULL DEFAULT 'OK'
                              CHECK (status IN ('OK','SOLD_OUT','NO_SERVICE',
                                                'SOURCE_DISALLOWED','FETCH_FAIL',
                                                'BLOCKED','PARSE_FAIL')),
    notes             TEXT,

    -- One checker, one cell, one day. A second reading by the same person is a
    -- correction, not a new observation.
    UNIQUE (observation_date, route_code, window_days, checker)
);

CREATE INDEX IF NOT EXISTS ix_ground_truth_cell
    ON ground_truth (observation_date, route_code, window_days);
