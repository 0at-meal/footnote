-- Footnote observation store, schema v1 (P1-01, local SQLite edition).
--
-- Public filing data only (global, keyed by CIK + accession + period). Reported
-- values are append-only observations: nothing here is ever updated in place.
-- A recast is two observations of the same (cik, line_key, period_id) from
-- different accessions with different values. Portable to Postgres (ADR 0006).

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS issuers (
    cik             TEXT PRIMARY KEY,           -- 10 digits
    ticker          TEXT NOT NULL,
    name            TEXT NOT NULL,
    fiscal_year_end TEXT NOT NULL,              -- MMDD from EDGAR submissions
    sector          TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    command     TEXT NOT NULL,
    stats_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS filings (
    accession   TEXT PRIMARY KEY,
    cik         TEXT NOT NULL REFERENCES issuers(cik),
    form        TEXT NOT NULL,
    items       TEXT NOT NULL,                  -- e.g. "2.02,9.01"
    filed       TEXT NOT NULL,                  -- YYYY-MM-DD
    exhibit     TEXT,                           -- EX-99.1 filename, NULL if none
    url         TEXT,                           -- CIK-qualified sec.gov URL
    sha256      TEXT,                           -- of the exhibit bytes
    bytes       INTEGER,
    first_run   INTEGER NOT NULL REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS bridges (
    bridge_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    accession      TEXT NOT NULL REFERENCES filings(accession),
    engine_version TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('ok', 'exceptions', 'not_found')),
    reason         TEXT,
    table_index    INTEGER,
    table_title    TEXT,
    table_xpath    TEXT,
    metric_label   TEXT,
    scale          TEXT,                        -- units | thousands | millions | billions
    scale_quote    TEXT,
    direction      INTEGER,
    exceptions     TEXT NOT NULL DEFAULT '[]',  -- JSON list
    notes          TEXT NOT NULL DEFAULT '[]',
    candidates     TEXT NOT NULL DEFAULT '[]',
    run_id         INTEGER NOT NULL REFERENCES runs(run_id),
    UNIQUE (accession, engine_version)
);

CREATE TABLE IF NOT EXISTS bridge_periods (
    bridge_id  INTEGER NOT NULL REFERENCES bridges(bridge_id),
    col        INTEGER NOT NULL,
    period_id  TEXT,                            -- e.g. 3M-2026-06-30; NULL if unresolved
    months     INTEGER,
    end_date   TEXT,
    header     TEXT NOT NULL,
    PRIMARY KEY (bridge_id, col)
);

CREATE TABLE IF NOT EXISTS observations (
    bridge_id  INTEGER NOT NULL REFERENCES bridges(bridge_id),
    cik        TEXT NOT NULL,
    accession  TEXT NOT NULL,
    filed      TEXT NOT NULL,
    row_order  INTEGER NOT NULL,
    label      TEXT NOT NULL,                   -- as reported
    line_key   TEXT NOT NULL,                   -- normalized label, stable across quarters
    role       TEXT NOT NULL,
    sign       INTEGER NOT NULL,
    period_id  TEXT NOT NULL,
    value_raw  TEXT NOT NULL,                   -- as reported, e.g. "(1,431)"
    value      TEXT,                            -- Decimal in reported scale; NULL for a dash
    scale      TEXT,
    value_usd  TEXT,                            -- value x scale; NULL if scale unknown
    xpath      TEXT,
    url        TEXT,                            -- sec.gov URL with text fragment
    PRIMARY KEY (bridge_id, row_order, period_id)
);
CREATE INDEX IF NOT EXISTS obs_series ON observations (cik, line_key, period_id);

CREATE TABLE IF NOT EXISTS checks (
    bridge_id  INTEGER NOT NULL REFERENCES bridges(bridge_id),
    kind       TEXT NOT NULL CHECK (kind IN ('sum', 'anchor')),
    period_id  TEXT NOT NULL,
    status     TEXT NOT NULL,                   -- pass | fail | mismatch | unavailable
    detail     TEXT NOT NULL,                   -- JSON
    PRIMARY KEY (bridge_id, kind, period_id)
);

CREATE TABLE IF NOT EXISTS failures (
    run_id    INTEGER NOT NULL REFERENCES runs(run_id),
    cik       TEXT,
    accession TEXT,
    stage     TEXT NOT NULL,                    -- submissions | index | exhibit | facts | extract
    reason    TEXT NOT NULL,
    at        TEXT NOT NULL
);

-- P2-07: issuer-scoped label memory. A category decided once for (issuer, label)
-- applies to every later quarter. source: rule (deterministic suggestion,
-- pending review) | human (confirmed). Never an LLM.
CREATE TABLE IF NOT EXISTS label_memory (
    cik        TEXT NOT NULL,
    line_key   TEXT NOT NULL,
    code       TEXT NOT NULL,
    components TEXT NOT NULL DEFAULT '[]',      -- constituents for MIXED
    flags      TEXT NOT NULL DEFAULT '[]',
    source     TEXT NOT NULL CHECK (source IN ('rule', 'human')),
    decided_by TEXT NOT NULL,
    decided_on TEXT NOT NULL,
    PRIMARY KEY (cik, line_key)
);

-- The most recent extraction of each filing (the newest engine version run
-- on it). Older extractions stay in the store (append-only) but are not served.
CREATE VIEW IF NOT EXISTS current_bridges AS
SELECT b.* FROM bridges b
WHERE b.bridge_id = (
    SELECT MAX(b2.bridge_id) FROM bridges b2 WHERE b2.accession = b.accession
);
