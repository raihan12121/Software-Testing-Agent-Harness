# Memory Document
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Purpose:** Defines what Sentinel remembers across runs, why, how it's stored, and how it's used to make the agent smarter over time (risk-based prioritization, flaky detection, defect trends).

---

## 1. Why Memory Matters

Without memory, every run is stateless — the agent re-discovers, re-plans, and re-tests everything from scratch, with no sense of what's historically risky, what's flaky, or what's already well-covered. Memory turns Sentinel from a "test generator" into a system that **improves its own targeting over time**, which is the core differentiator from static test scripts.

Memory serves four purposes:
1. **Risk-based prioritization** — bias the Planner toward historically defect-prone or recently changed areas (design.md §4).
2. **Flaky test management** — distinguish "flaky" from "broken" so signal isn't drowned in noise (rules.md R-EXEC-2).
3. **Regression awareness** — know what passed before, so a new failure is flagged as a regression, not just "a failure."
4. **Continuous improvement of generation quality** — track which generated tests actually found real bugs vs. which were noise, to tune future generation.

---

## 2. What Is Stored

| Category | Examples | Retention |
|---|---|---|
| Run metadata | run_id, timestamp, target, environment, config snapshot | Indefinite (or per project retention policy) |
| Test case history | every generated `TestCase`, its provenance, and every `Verdict` it ever received | Indefinite, versioned per test id |
| Defect records | title, severity, root cause tags, linked test_id(s), linked issue tracker URL, status (open/fixed/wontfix) | Indefinite |
| Flaky test registry | test_id, flake rate (last N runs), first observed, quarantine status | Rolling window (default: last 50 runs) |
| Risk index | per module/endpoint/page: defect_count, churn_rate, coverage_ratio, computed risk_score, last_updated | Recomputed each run, history retained for trend charts |
| LLM generation quality signal | per generated test: did it ever catch a real (human-confirmed) defect? | Indefinite, used to tune generation prompts/weights over time |
| Human review resolutions | every `pending_review` verdict's human resolution + rationale | Indefinite (audit trail, rules.md R-ORACLE-5) |

**Explicitly NOT stored in memory (see rules.md §2):** raw secrets/credentials, unredacted PII, raw request/response bodies containing sensitive data (only redacted artifacts are persisted).

---

## 3. Storage Schema (Built-in SQLite Default; Extensible to PostgreSQL)

Sentinel uses embedded SQLite as its primary zero-dependency storage engine for test runs, verdicts, and risk history, with automated `SAVEPOINT` transaction rollbacks for database target testing (R-EXEC-1). For external database testing, SQLite is built-in, while PostgreSQL and MongoDB drivers are supported via the optional `db-extended` package group.
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    environment TEXT NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    config_snapshot JSON,
    pass_count INTEGER, fail_count INTEGER, flaky_count INTEGER, pending_count INTEGER
);

CREATE TABLE test_cases (
    test_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    target_type TEXT,
    module TEXT,                 -- e.g. "/orders", "checkout_page", derived from source_context
    priority TEXT,
    generated_by TEXT,
    source_context TEXT,
    created_at TIMESTAMP,
    schema JSON                  -- full TestCase payload
);

CREATE TABLE verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(run_id),
    test_id TEXT REFERENCES test_cases(test_id),
    status TEXT,                 -- pass|fail|error|flaky|skipped|pending_review
    oracle_used TEXT,
    confidence REAL,
    reasoning TEXT,
    duration_ms INTEGER,
    retries INTEGER
);

CREATE TABLE defects (
    defect_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT,
    severity TEXT,               -- low|medium|high|critical
    root_cause_tags JSON,
    linked_test_ids JSON,
    tracker_url TEXT,
    status TEXT,                 -- open|fixed|wontfix
    first_seen_run_id TEXT,
    module TEXT
);

CREATE TABLE flaky_registry (
    test_id TEXT PRIMARY KEY REFERENCES test_cases(test_id),
    flake_count INTEGER,
    total_runs_observed INTEGER,
    first_observed_at TIMESTAMP,
    quarantined BOOLEAN DEFAULT FALSE
);

CREATE TABLE risk_index (
    project_id TEXT,
    module TEXT,
    defect_count INTEGER,
    churn_rate REAL,
    coverage_ratio REAL,
    flaky_count INTEGER,
    risk_score REAL,
    computed_at TIMESTAMP,
    PRIMARY KEY (project_id, module, computed_at)
);

CREATE TABLE human_review_resolutions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id TEXT,
    run_id TEXT,
    original_status TEXT,
    resolved_status TEXT,
    resolved_by TEXT,
    rationale TEXT,
    resolved_at TIMESTAMP
);
```

---

## 4. How Memory Is Used (read paths)

1. **Planner risk context** (design.md §4): before building a plan, the Planner queries `risk_index` (latest `computed_at` per module) to weight scenario prioritization.
2. **Flaky suppression from "new failure" alarms**: the Executor/Reporter checks `flaky_registry` before classifying a `fail` as a *regression alert* — a known-flaky test failing is reported differently (lower urgency, grouped) than a previously-always-passing test suddenly failing.
3. **Regression detection**: Reporter compares the current run's verdicts against the immediately preceding run's verdicts for the same `test_id`s; a `pass → fail` transition is flagged as a regression, distinct from a fresh/never-run failure.
4. **Generation quality feedback loop**: periodically (e.g., weekly or per Phase-3 tuning cycle), cross-reference `test_cases.generated_by` against `defects.linked_test_ids` where `defects.status` was human-confirmed — tests that never catch real defects across many runs are candidates for pruning or lower future priority; this signal can also inform prompt-tuning for the Generator.
5. **Human review audit**: `human_review_resolutions` is queried whenever someone asks "why did we trust this verdict" — full traceability from LLM judge → human override.

---

## 5. Memory Lifecycle & Hygiene

- **Pruning stale test cases** (FR-23): a test case whose `source_context` no longer exists in the latest `discover()` output (e.g., an endpoint was removed) is marked `stale` (not deleted) after N consecutive runs where it's unreachable, and excluded from active planning — but its history is retained for audit.
- **Flaky quarantine**: a test exceeding a configurable flake-rate threshold (default: fails intermittently in >20% of last 10 runs) is auto-quarantined — still executed and tracked, but excluded from CI quality-gate failure decisions until a human investigates (prevents flaky tests from blocking releases while still surfacing them).
- **Risk index recomputation**: recomputed at the start of every run (cheap query), with history retained so the dashboard (design.md §7) can show risk trending up/down per module over time.
- **Retention policy**: configurable per project; default keeps full history, with an optional archival/compaction job for very high-volume projects (e.g., collapse verdict-level detail older than 6 months into aggregate stats, keep defect records indefinitely).

---

## 6. Privacy & Security Notes (cross-reference rules.md §2)

- All persisted artifacts pass through the redaction filter before hitting any memory table.
- `config_snapshot` in the `runs` table stores config *structure*, not resolved secret values (secret references like `{{staging_api_key}}` are stored as-is, never resolved and persisted).
- Memory store access is scoped per `project_id`; in hosted/team mode (Phase 4), row-level access control ensures Project A's history is never visible to Project B's users.

---

## 7. Open Design Question for Later Phases

Should memory eventually support **cross-project learning** (e.g., "auth-token-expiry bugs are common across many API projects, weight that scenario higher by default even on a brand-new project")? This is deliberately deferred — v1–v3 memory is strictly per-project to avoid premature generalization and to keep the risk-scoring model simple and explainable. Revisit once several real projects have enough history to validate whether cross-project patterns actually generalize.
