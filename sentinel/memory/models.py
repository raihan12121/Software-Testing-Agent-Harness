"""Database schema models for Sentinel SQLite Memory Store.

Adheres strictly to:
- memory.md §3 (Storage Schema)
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    config_snapshot TEXT,
    pass_count INTEGER,
    fail_count INTEGER,
    flaky_count INTEGER,
    pending_count INTEGER
);

CREATE TABLE IF NOT EXISTS test_cases (
    test_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    target_type TEXT,
    module TEXT,
    priority TEXT,
    generated_by TEXT,
    source_context TEXT,
    created_at TEXT,
    schema TEXT
);

CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(run_id),
    test_id TEXT REFERENCES test_cases(test_id),
    status TEXT,
    oracle_used TEXT,
    confidence REAL,
    reasoning TEXT,
    duration_ms INTEGER,
    retries INTEGER
);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    severity TEXT,
    root_cause_tags TEXT,
    linked_test_ids TEXT,
    tracker_url TEXT,
    status TEXT,
    first_seen_run_id TEXT,
    module TEXT
);

CREATE TABLE IF NOT EXISTS flaky_registry (
    test_id TEXT PRIMARY KEY REFERENCES test_cases(test_id),
    flake_count INTEGER,
    total_runs_observed INTEGER,
    first_observed_at TEXT,
    quarantined BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS risk_index (
    project_id TEXT,
    module TEXT,
    defect_count INTEGER,
    churn_rate REAL,
    coverage_ratio REAL,
    flaky_count INTEGER,
    risk_score REAL,
    computed_at TEXT,
    PRIMARY KEY (project_id, module, computed_at)
);

CREATE TABLE IF NOT EXISTS human_review_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id TEXT,
    run_id TEXT,
    original_status TEXT,
    resolved_status TEXT,
    resolved_by TEXT,
    rationale TEXT,
    resolved_at TEXT
);
"""
