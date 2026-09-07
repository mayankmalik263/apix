-- ===========================================================================
-- APIx database schema  ·  PostgreSQL 15+  ·  the production target
-- ===========================================================================
--
-- WHY THIS FILE EXISTS
--
-- We demo on SQLite. SQLite installs nowhere, has no service to start, no
-- port, no password, and cannot fail on stage. Twenty-four hours before a
-- presentation that has to run ten times, that is the whole argument.
--
-- It is not the argument for production. Postgres is, and this file is what
-- that costs: about forty lines of difference, none of it in application
-- code, because everything above the database goes through SQLAlchemy.
--
--     psql -U apix -d apix -f db/schema.postgres.sql
--     APIX_DB_URL=postgresql+psycopg2://apix:apix@localhost:5433/apix
--
-- WHAT ACTUALLY CHANGES, AND WHY EACH ONE MATTERS HERE
--
--   TEXT payload      -> JSONB + GIN      the raw archive becomes queryable.
--                                         "which payloads carried a fare over
--                                         20,000" stops being a Python loop
--                                         over 2.7 GB of files.
--   REAL money        -> NUMERIC(10,2)    a float loses paise. An index that
--                                         drifts in the fourth decimal is an
--                                         index somebody eventually cannot
--                                         reproduce.
--   TEXT timestamps   -> TIMESTAMPTZ      collection happens at a fixed IST
--                                         slot and is stored UTC. Naive
--                                         strings make that a convention;
--                                         TIMESTAMPTZ makes it a fact.
--   name prefixes     -> real schemas     bronze. silver. gold. Grant SELECT
--                                         on gold to the NSO read-only role
--                                         and the raw archive is not exposed
--                                         by the same grant.
--   inline CHECK      -> domain + ENUM    the vocabulary is declared once, in
--                                         one place, and every table that
--                                         references it is correct by
--                                         construction rather than by copy.
--   -                 -> partitioning     Bronze grows 30 rows a day per
--                                         source forever. Monthly range
--                                         partitions let a year be detached
--                                         and archived in one statement.
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS meta;


-- ---------------------------------------------------------------------------
-- The controlled vocabulary, declared once.
-- ---------------------------------------------------------------------------
-- In SQLite this is a CHECK list repeated in four tables, and four copies of a
-- rule is three chances to get it wrong. Here it is a type. Adding an eighth
-- status becomes an ALTER TYPE that someone has to write down and review,
-- which is the correct amount of friction for changing a contract.

CREATE TYPE meta.obs_status AS ENUM (
    'OK',                 -- MARKET  fare captured and parsed
    'SOLD_OUT',           -- MARKET  served, no inventory
    'NO_SERVICE',         -- MARKET  no flight operates this pair
    'SOURCE_DISALLOWED',  -- POLICY  the registry refused it
    'FETCH_FAIL',         -- SYSTEM  timeout, 5xx, network
    'BLOCKED',            -- SYSTEM  bot wall, never bypassed
    'PARSE_FAIL'          -- SYSTEM  fetched, shape changed
);

CREATE TYPE meta.status_class AS ENUM ('MARKET', 'POLICY', 'SYSTEM');
CREATE TYPE meta.source_class AS ENUM ('LIVE', 'SIMULATED', 'MANUAL');
CREATE TYPE meta.verdict     AS ENUM ('PERMITTED', 'DISALLOWED', 'BLOCKED', 'UNKNOWN');
CREATE TYPE meta.confidence  AS ENUM ('A', 'B', 'C');

-- Money, once, everywhere. NUMERIC because fares are decimal currency and
-- binary floating point is not.
CREATE DOMAIN meta.inr AS NUMERIC(10,2) CHECK (VALUE >= 0);

-- The mapping from status to whose fault the gap is. A function rather than a
-- column, so it cannot disagree with itself between two rows.
CREATE FUNCTION meta.class_of(s meta.obs_status)
RETURNS meta.status_class
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE s
        WHEN 'OK'                THEN 'MARKET'
        WHEN 'SOLD_OUT'          THEN 'MARKET'
        WHEN 'NO_SERVICE'        THEN 'MARKET'
        WHEN 'SOURCE_DISALLOWED' THEN 'POLICY'
        ELSE 'SYSTEM'
    END::meta.status_class;
$$;


-- ---------------------------------------------------------------------------
-- BRONZE — the raw archive
-- ---------------------------------------------------------------------------
-- Append-only and immutable. Airfares cannot be collected retrospectively, so
-- a discarded payload is a permanently lost day. Range-partitioned by month
-- because this table only ever grows.

CREATE TABLE bronze.observation_raw (
    id                BIGINT GENERATED ALWAYS AS IDENTITY,
    observation_date  DATE          NOT NULL,
    route_code        TEXT          NOT NULL,
    window_days       SMALLINT      NOT NULL,
    departure_date    DATE          NOT NULL,
    source_id         TEXT          NOT NULL,
    source_class      meta.source_class NOT NULL,

    fetch_status      meta.obs_status   NOT NULL,
    http_status       SMALLINT,
    request_url       TEXT,
    user_agent        TEXT,

    -- The whole reason to be on Postgres. The payload stays verbatim AND
    -- becomes searchable: fares can be counted straight out of the archive
    -- without going through Silver, which is how you audit Silver.
    payload           JSONB,
    payload_sha256    CHAR(64),

    error_detail      TEXT,
    fetched_at_utc    TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- A partitioned table's primary key must contain the partition key.
    -- Postgres will not let you forget this; it is the one thing that makes
    -- partitioning visible in the schema rather than just in the DDL.
    PRIMARY KEY (id, observation_date)
) PARTITION BY RANGE (observation_date);

CREATE TABLE bronze.observation_raw_2026_09 PARTITION OF bronze.observation_raw
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE bronze.observation_raw_2026_10 PARTITION OF bronze.observation_raw
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE INDEX ix_bronze_cell
    ON bronze.observation_raw (observation_date, route_code, window_days);

-- Reach into the raw JSON without parsing it first.
CREATE INDEX ix_bronze_payload
    ON bronze.observation_raw USING GIN (payload jsonb_path_ops);

-- No UPDATE, no DELETE. Enforced, not agreed.
CREATE RULE bronze_no_update AS ON UPDATE TO bronze.observation_raw DO INSTEAD NOTHING;
CREATE RULE bronze_no_delete AS ON DELETE TO bronze.observation_raw DO INSTEAD NOTHING;


-- ---------------------------------------------------------------------------
-- SILVER — one row per flight quote
-- ---------------------------------------------------------------------------

CREATE TABLE silver.fare_observation (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bronze_id         BIGINT,

    observation_date  DATE          NOT NULL,
    route_code        TEXT          NOT NULL,
    window_days       SMALLINT      NOT NULL,
    departure_date    DATE          NOT NULL,
    source_id         TEXT          NOT NULL,
    source_class      meta.source_class NOT NULL,

    status            meta.obs_status   NOT NULL,
    -- Derived, not stored twice. In SQLite this is a column the loader has to
    -- remember to fill; here it cannot be wrong.
    status_class      meta.status_class
                      GENERATED ALWAYS AS (meta.class_of(status)) STORED,

    carrier           TEXT,
    flight_no         TEXT,
    departure_time    TIME,
    stops             SMALLINT,

    base_fare         meta.inr,
    taxes             meta.inr,
    fees              NUMERIC(10,2),        -- can be negative if a site rounds
    total_fare        meta.inr,
    currency          CHAR(3)       NOT NULL DEFAULT 'INR',

    is_outlier        BOOLEAN       NOT NULL DEFAULT FALSE,
    outlier_score     NUMERIC(8,4),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- A fare row must carry a fare; a non-OK row must not pretend to.
    CONSTRAINT ok_rows_have_a_fare
        CHECK ((status = 'OK') = (total_fare IS NOT NULL)),

    -- The logical flight key. This is what makes re-running the loader a
    -- no-op instead of a duplication.
    UNIQUE NULLS NOT DISTINCT (observation_date, route_code, window_days,
                               source_id, carrier, flight_no, total_fare)
);

-- NULLS NOT DISTINCT is the one place Postgres is plainly better here. Live
-- Cleartrip fares carry no flight number, so flight_no is NULL on every real
-- row. Under the SQL default two NULLs are never equal, so every re-run would
-- insert them all again. SQLite happens to treat them as equal in a UNIQUE
-- index; Postgres needs this said out loud. (PostgreSQL 15+.)

CREATE INDEX ix_silver_cell   ON silver.fare_observation (observation_date, route_code, window_days);
CREATE INDEX ix_silver_status ON silver.fare_observation (status);
CREATE INDEX ix_silver_ok     ON silver.fare_observation (observation_date, route_code, window_days)
                               WHERE status = 'OK' AND NOT is_outlier;
-- ^ the index the cell median actually uses: a partial index over exactly the
--   rows that aggregation reads.


-- ---------------------------------------------------------------------------
-- GOLD — the published index
-- ---------------------------------------------------------------------------
-- source_class is in every key. Real and simulated series never mix; see the
-- note in db/schema.sql and METHODOLOGY.md section 4.

CREATE TABLE gold.cell_median (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_date   DATE          NOT NULL,
    route_code         TEXT          NOT NULL,
    window_days        SMALLINT      NOT NULL,
    source_class       meta.source_class NOT NULL,

    median_fare        meta.inr,
    n_used             INTEGER       NOT NULL DEFAULT 0,
    n_outliers_flagged INTEGER       NOT NULL DEFAULT 0,
    status             meta.obs_status NOT NULL,
    price_relative     NUMERIC(12,6),

    UNIQUE (observation_date, route_code, window_days, source_class)
);

CREATE TABLE gold.route_index_daily (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_date  DATE          NOT NULL,
    route_code        TEXT          NOT NULL,
    source_class      meta.source_class NOT NULL,

    route_index       NUMERIC(10,4),
    n_windows_used    SMALLINT      NOT NULL DEFAULT 0,
    n_observations    INTEGER       NOT NULL DEFAULT 0,
    coverage          NUMERIC(5,4)  NOT NULL DEFAULT 0 CHECK (coverage BETWEEN 0 AND 1),
    method_version    TEXT          NOT NULL,

    UNIQUE (observation_date, route_code, source_class)
);

CREATE TABLE gold.apix_daily (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_date    DATE          NOT NULL,
    source_class        meta.source_class NOT NULL,

    apix                NUMERIC(10,4),
    change_pct          NUMERIC(8,4),

    coverage            NUMERIC(5,4)  NOT NULL DEFAULT 0 CHECK (coverage BETWEEN 0 AND 1),
    n_expected          SMALLINT      NOT NULL DEFAULT 0,
    n_observed          SMALLINT      NOT NULL DEFAULT 0,
    confidence          meta.confidence NOT NULL DEFAULT 'C',

    weights_provisional BOOLEAN       NOT NULL DEFAULT TRUE,
    method_version      TEXT          NOT NULL,
    computed_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- An A grade requires coverage. Asserting it in the table means a bug in
    -- the engine surfaces as a failed INSERT rather than as a published
    -- number that overstates what we measured.
    CONSTRAINT grade_matches_coverage CHECK (
        (confidence = 'A' AND coverage >= 0.90) OR
        (confidence = 'B' AND coverage >= 0.70) OR
        (confidence = 'C')
    ),

    UNIQUE (observation_date, source_class)
);


-- ---------------------------------------------------------------------------
-- EVIDENCE
-- ---------------------------------------------------------------------------

CREATE TABLE meta.source_registry (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id      TEXT          NOT NULL,
    source_name    TEXT          NOT NULL,
    kind           TEXT,
    checked_on     DATE          NOT NULL,
    verdict        meta.verdict  NOT NULL,
    reason         TEXT,
    robots_sha256  CHAR(64),
    http_status    SMALLINT,
    evidence_file  TEXT,

    UNIQUE (source_id, checked_on)
);

CREATE TABLE meta.ground_truth (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    observation_date  DATE          NOT NULL,
    route_code        TEXT          NOT NULL,
    window_days       SMALLINT      NOT NULL,
    departure_date    DATE          NOT NULL,

    checker           TEXT          NOT NULL,
    time_checked      TIME,
    website           TEXT,
    airline           TEXT,
    flight_no         TEXT,
    fare_shown        meta.inr,
    status            meta.obs_status NOT NULL DEFAULT 'OK',
    notes             TEXT,

    UNIQUE (observation_date, route_code, window_days, checker)
);


-- ---------------------------------------------------------------------------
-- WHO CAN READ WHAT
-- ---------------------------------------------------------------------------
-- The reason for real schemas rather than name prefixes. An NSO or RBI
-- consumer reads the published index and nothing else; they cannot reach the
-- raw archive, and that is granted rather than promised.

CREATE ROLE apix_reader NOLOGIN;
GRANT USAGE ON SCHEMA gold, meta TO apix_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO apix_reader;
GRANT SELECT ON meta.source_registry TO apix_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA gold GRANT SELECT ON TABLES TO apix_reader;

CREATE ROLE apix_writer NOLOGIN;
GRANT USAGE ON SCHEMA bronze, silver, gold, meta TO apix_writer;
GRANT INSERT ON ALL TABLES IN SCHEMA bronze TO apix_writer;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA silver, gold, meta TO apix_writer;
