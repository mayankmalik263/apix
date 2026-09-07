-- ===========================================================================
-- APIx web layer  ·  admin accounts, API keys, scheduler history
-- ===========================================================================
-- Kept in its own file, and its own tables, so the measurement layer and the
-- serving layer can be reasoned about separately. Nothing here can change a
-- published index value.
-- ===========================================================================

-- Admin accounts. There is no self-service signup: an operator is created by
-- someone who already has shell access to the box.
CREATE TABLE IF NOT EXISTS web_user (
    id             INTEGER PRIMARY KEY,
    email          TEXT    NOT NULL UNIQUE,
    display_name   TEXT    NOT NULL,

    -- scrypt. The salt is per-user and stored beside the hash; the password
    -- itself is never written anywhere, including the logs.
    pw_salt        BLOB    NOT NULL,
    pw_hash        BLOB    NOT NULL,

    role           TEXT    NOT NULL DEFAULT 'admin'
                           CHECK (role IN ('admin','viewer')),
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),

    failed_logins  INTEGER NOT NULL DEFAULT 0,
    locked_until   TEXT,                     -- set after repeated failures
    last_login_at  TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);


-- API keys, for consumers like the RBI and the NSO.
--
-- The key itself is shown exactly once, at creation, and never stored. What is
-- stored is a SHA-256 of it plus a short non-secret prefix used to find the
-- row. SHA-256 rather than scrypt on purpose: this is checked on every single
-- API request, and a deliberately slow hash there is a denial-of-service
-- vector rather than a security gain. The keys are 256 bits of OS randomness,
-- so there is nothing to brute-force.
CREATE TABLE IF NOT EXISTS api_key (
    id             INTEGER PRIMARY KEY,
    prefix         TEXT    NOT NULL UNIQUE,  -- e.g. apix_live_9f3c2ab1 — safe to display
    key_sha256     TEXT    NOT NULL UNIQUE,
    label          TEXT    NOT NULL,         -- "Reserve Bank of India — research"
    organisation   TEXT,

    -- What this key may read. Gold only by default: a consumer gets the
    -- published index, never the raw archive.
    scopes         TEXT    NOT NULL DEFAULT 'read:index',

    rate_per_min   INTEGER NOT NULL DEFAULT 60,

    created_by     INTEGER REFERENCES web_user(id),
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at     TEXT,
    revoked_at     TEXT,                     -- revocation is a fact, not a delete
    revoked_reason TEXT,

    last_used_at   TEXT,
    request_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_api_key_sha ON api_key (key_sha256);


-- Every authenticated call, so an operator can answer "who read what, when".
-- Keys are recorded by id; the key itself never enters this table.
CREATE TABLE IF NOT EXISTS api_access_log (
    id           INTEGER PRIMARY KEY,
    api_key_id   INTEGER REFERENCES api_key(id),
    path         TEXT    NOT NULL,
    status_code  INTEGER NOT NULL,
    ip           TEXT,
    at_utc       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS ix_access_at  ON api_access_log (at_utc);
CREATE INDEX IF NOT EXISTS ix_access_key ON api_access_log (api_key_id, at_utc);


-- What the scheduler did, and what happened. A collection that silently did
-- not run is indistinguishable from one that ran and found nothing, unless
-- the attempt itself is recorded.
CREATE TABLE IF NOT EXISTS collection_run (
    id                INTEGER PRIMARY KEY,
    observation_date  TEXT    NOT NULL,
    trigger           TEXT    NOT NULL CHECK (trigger IN ('SCHEDULED','MANUAL','CATCHUP')),
    started_at        TEXT    NOT NULL,
    finished_at       TEXT,

    status            TEXT    NOT NULL DEFAULT 'RUNNING'
                              CHECK (status IN ('RUNNING','OK','PARTIAL','FAILED')),
    cells_attempted   INTEGER NOT NULL DEFAULT 0,
    cells_ok          INTEGER NOT NULL DEFAULT 0,
    sources_used      TEXT,
    error_detail      TEXT
);

CREATE INDEX IF NOT EXISTS ix_run_date ON collection_run (observation_date);
