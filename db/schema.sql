-- ===========================================================================
-- APIx database schema  ·  SQLite  ·  BHARAT, Round 1
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
-- Two tables are written out in full as worked examples. The rest are yours.
-- Copy the style: same column order as the comment block, NOT NULL where the
-- value can never legitimately be missing, CHECK where the values are a fixed
-- list.
-- ===========================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;


-- ---------------------------------------------------------------------------
-- BRONZE — the raw archive, mirrored from the JSONL files
-- ---------------------------------------------------------------------------
-- WRITTEN FOR YOU AS THE EXAMPLE. Note there is no UNIQUE constraint here:
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
-- WRITTEN FOR YOU AS THE EXAMPLE. The UNIQUE constraint at the bottom is the
-- most important line in this whole file: it is what makes the loader safe to
-- run twice. Remove it and your row count doubles every run.
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

    is_outlier        INTEGER NOT NULL DEFAULT 0,
    outlier_score     REAL,
    created_at        TEXT    NOT NULL DEFAULT (datetime('now')),

    -- The logical flight key. This is what makes re-running the loader a
    -- no-op instead of a duplication.
    UNIQUE (observation_date, route_code, window_days, source_id,
            carrier, flight_no, total_fare)
);

CREATE INDEX IF NOT EXISTS ix_silver_cell
    ON silver_fare_observation (observation_date, route_code, window_days);
CREATE INDEX IF NOT EXISTS ix_silver_status
    ON silver_fare_observation (status);


-- ---------------------------------------------------------------------------
-- GOLD — the published index. THREE TABLES, ALL YOURS.
-- ---------------------------------------------------------------------------

-- TODO 1 —  gold_cell_median
-- One row per (route, window, day). This is the number that feeds the index,
-- kept so a jury can drill from a published value down to the exact cell.
--
--   id                INTEGER PRIMARY KEY
--   observation_date  TEXT NOT NULL
--   route_code        TEXT NOT NULL
--   window_days       INTEGER NOT NULL
--   median_fare       REAL              -- NULL when the cell had no OK rows
--   n_used            INTEGER NOT NULL DEFAULT 0
--   n_outliers_flagged INTEGER NOT NULL DEFAULT 0
--   status            TEXT NOT NULL     -- same CHECK list as Silver
--   price_relative    REAL
--   UNIQUE (observation_date, route_code, window_days)


-- TODO 2 —  gold_route_index_daily
-- One row per (route, day).
--
--   id                INTEGER PRIMARY KEY
--   observation_date  TEXT NOT NULL
--   route_code        TEXT NOT NULL
--   route_index       REAL
--   n_windows_used    INTEGER NOT NULL DEFAULT 0
--   n_observations    INTEGER NOT NULL DEFAULT 0
--   coverage          REAL NOT NULL DEFAULT 0
--   method_version    TEXT NOT NULL
--   source_class      TEXT NOT NULL
--   UNIQUE (observation_date, route_code)


-- TODO 3 —  gold_apix_daily
-- One row per day. THIS IS THE PUBLISHED NUMBER.
--
--   id                  INTEGER PRIMARY KEY
--   observation_date    TEXT NOT NULL UNIQUE
--   apix                REAL
--   change_pct          REAL
--   coverage            REAL NOT NULL DEFAULT 0
--   n_expected          INTEGER NOT NULL DEFAULT 0
--   n_observed          INTEGER NOT NULL DEFAULT 0
--   confidence          TEXT NOT NULL DEFAULT 'C'  CHECK (confidence IN ('A','B','C'))
--   weights_provisional INTEGER NOT NULL DEFAULT 1
--   source_class        TEXT NOT NULL
--   method_version      TEXT NOT NULL
--   computed_at         TEXT NOT NULL DEFAULT (datetime('now'))


-- ---------------------------------------------------------------------------
-- SUPPORTING TABLES — both yours
-- ---------------------------------------------------------------------------

-- TODO 4 —  source_registry
-- Loaded from compliance/verdicts/<date>.json. This is the compliance
-- evidence, in the database, queryable. It goes on a slide as-is.
--
--   id              INTEGER PRIMARY KEY
--   source_id       TEXT NOT NULL
--   source_name     TEXT NOT NULL
--   kind            TEXT
--   checked_on      TEXT NOT NULL
--   verdict         TEXT NOT NULL
--                   CHECK (verdict IN ('PERMITTED','DISALLOWED','BLOCKED','UNKNOWN'))
--   reason          TEXT
--   robots_sha256   TEXT
--   http_status     INTEGER
--   evidence_file   TEXT
--   UNIQUE (source_id, checked_on)


-- TODO 5 —  ground_truth
-- Loaded from data/ground_truth.csv -- the fares checked by hand.
-- This is what lets us say "a human checked and got the same number".
--
--   id                INTEGER PRIMARY KEY
--   observation_date  TEXT NOT NULL
--   route_code        TEXT NOT NULL
--   window_days       INTEGER NOT NULL
--   departure_date    TEXT NOT NULL
--   checker           TEXT NOT NULL
--   website           TEXT
--   airline           TEXT
--   flight_no         TEXT
--   fare_shown        REAL
--   status            TEXT NOT NULL DEFAULT 'OK'
--   notes             TEXT
--   UNIQUE (observation_date, route_code, window_days, checker)
