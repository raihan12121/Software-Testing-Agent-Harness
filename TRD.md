# Technical Requirements Document (TRD)
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Companion to:** PRD.md, architecture.md, design.md
**Last updated:** 2026-09-02

---

## 1. Purpose

This document translates the PRD's functional goals into concrete technical requirements: languages, frameworks, interfaces, data formats, performance budgets, and quality attributes. It is the contract engineers build against.

---

## 2. Technology Stack

### 2.1 Core language & runtime
- **Primary language:** Python 3.12+ (best ecosystem overlap for testing libs, LLM SDKs, data handling).
- **Secondary language (optional, adapter-specific):** TypeScript/Node.js for web adapters where Playwright's native TS ergonomics are preferable — exposed to the Python core via a thin RPC/subprocess boundary.
- **Agent orchestration:** Hand-rolled control loop initially (see architecture.md), with optional migration to a graph-based orchestration library (e.g., LangGraph-style state machine) once the loop's shape stabilizes. Avoid framework lock-in during Phase 1.

### 2.2 LLM Integration
- **Provider:** Anthropic Claude via the Messages API (primary). Design the LLM client behind an interface (`LLMProvider`) so providers are swappable.
- **Capabilities required from the LLM layer:**
  - Structured output (JSON mode / tool-use) for test-case generation — never freeform prose parsed with regex.
  - Tool-calling for adapter actions (the LLM decides *which* action to take; the harness executes it — separation of decision and execution).
  - Vision input support for visual/DOM screenshot review (web/desktop targets).
- **Cost/latency controls:** token budgets per phase (planning vs. execution vs. judging), caching of repeated prompts (e.g., system prompts, spec context), and a configurable "cheap model for volume tasks / strong model for judging" tiering strategy.

### 2.3 Adapter Technologies (by target type)

| Target type | Library/Tooling | Protocol | Status / Requirements |
|---|---|---|---|
| API (REST/GraphQL) | `httpx`, `jsonschema` | HTTP/HTTPS | Core / Built-in |
| Web app | Playwright | CDP / browser automation | Core / Built-in |
| CLI | `subprocess` | stdin/stdout/stderr/exit code | Core / Built-in |
| Database | `sqlite3` (built-in default); `psycopg` (Postgres), `pymongo` (Mongo) | SQL wire / BSON | Built-in SQLite; `[db-extended]` for Postgres/Mongo |
| Mobile | Appium Python Client (WebDriver protocol) | WebDriver / W3C Actions | `[mobile]` extra; requires running Appium server; offline simulation fallback |
| Desktop | Windows UI Automation / `pywinauto` (Windows); AT-SPI (Linux); pyobjc (macOS) | OS accessibility trees | `[desktop]` extra; Windows implementation active; Linux/macOS experimental |
| IoT | `paho-mqtt` (MQTT), `pyserial` (Serial UART) | MQTT / Serial UART | `[iot]` extra; requires broker or serial device; R-SAFE-5 allow-list |

### 2.4 Data & Storage
- **Test case store:** structured files (YAML/JSON) in a `tests/generated/` directory, version-controlled, human-diffable.
- **Run artifacts:** object storage (local filesystem in v1; S3-compatible in hosted mode) — screenshots, HAR files, logs.
- **Memory store:** embedded database for v1 (SQLite), with schema designed to migrate to Postgres for multi-user/hosted mode (see `memory.md` for schema).
- **Vector store (optional, Phase 3+):** for semantic search over past defects/test history, to support "have we seen a failure like this before" queries.

### 2.5 CI/CD Integration
- Ship as a CLI (`sentinel run`, `sentinel plan`, `sentinel report`) with clean exit codes (0 = pass, 1 = failures, 2 = execution error).
- Provide a GitHub Actions workflow template as first-class support; design the CI interface generically enough for GitLab CI/Jenkins to be added later.
- Output JUnit XML (for CI test-result integrations) in addition to Sentinel's native JSON report.

---

## 3. Interface Contracts

### 3.1 Adapter Interface (all target-type adapters must implement)

```python
class TargetAdapter(Protocol):
    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect the target and return a structured model of it
        (endpoints, pages, commands, schema, etc.)."""

    def execute_action(self, action: TestAction) -> Observation:
        """Perform a single test action (HTTP call, click, keypress, DB query, CLI invocation)
        and return a structured observation (response, DOM state, stdout, etc.)."""

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Extract screenshots/logs/traces relevant to this observation."""

    def reset_state(self, config: TargetConfig) -> None:
        """Return the target to a known baseline state where supported
        (test DB rollback, browser context reset, etc.)."""
```

### 3.2 Test Case Schema (canonical, adapter-agnostic)

```yaml
id: TC-0001
target_type: api
title: "Reject login with expired token"
priority: high
tags: [auth, security, regression]
preconditions:
  - "user session token is expired"
steps:
  - action: http_request
    method: POST
    path: /api/v1/login
    headers: { Authorization: "Bearer {{expired_token}}" }
expected:
  oracle: deterministic
  assertions:
    - status_code == 401
    - body.error == "token_expired"
generated_by: llm_planner_v1   # or "human", "rule_engine"
source_context: "openapi.yaml#/paths/~1login/post"
```

### 3.3 Observation / Result Schema

```yaml
test_id: TC-0001
run_id: run-2026-09-02-014
status: fail            # pass | fail | error | flaky | skipped
oracle_used: deterministic
duration_ms: 214
assertions_result:
  - assertion: "status_code == 401"
    actual: 500
    passed: false
artifacts: [artifacts/TC-0001/response.json]
error: null
retries: 1
```

### 3.4 LLM-as-Judge Contract
When deterministic assertions are insufficient, the judge call must:
- Receive: the test intent, the expected behavior description, and the actual observation (never raw secrets).
- Return: `{verdict: pass|fail|uncertain, confidence: 0-1, reasoning: string}`.
- `uncertain` or confidence below a configured threshold (default 0.75) **must** route to human review, never auto-resolve to pass.

---

## 4. Performance Requirements

| Requirement | Budget |
|---|---|
| API test execution (single case) | < 2s typical, configurable timeout |
| Web test execution (single case, incl. browser action) | < 10s typical |
| Full suite parallelism | configurable worker pool, default = CPU core count |
| LLM planning call latency (test-plan generation) | should not block execution start — plan for the next batch while current batch executes |
| Report generation | < 5s for suites up to 5,000 cases |

---

## 5. Reliability & Quality Attributes

- **Determinism where it matters:** any assertion that can be deterministic (schema match, status code, exact value) must be — LLM judgment is a fallback, not a default.
- **Idempotency:** re-running the same test plan against an unchanged target must produce the same pass/fail result (barring genuine flakiness, which must be tracked, not hidden).
- **Isolation:** each test run executes in an isolated context (browser context, DB transaction/rollback, subprocess) to prevent cross-test contamination.
- **Fail-safe defaults:** the agent defaults to **read-only / non-destructive** actions unless a target is explicitly marked as a sandbox/test environment where mutation is allowed.
- **Auditability:** every generated test case and every judge verdict must record its provenance (what prompt, what model, what context) for debugging and trust-building.

---

## 6. Security Requirements

- Secrets (API keys, credentials, tokens) are supplied via environment variables or a secrets manager — never embedded in generated test files or sent verbatim into LLM prompts/logs. A redaction filter runs on all artifacts before storage and before any LLM call.
- Network egress from adapters is limited to explicitly configured target domains/hosts (allow-list), preventing an agent from wandering off-target.
- Generated test actions that are potentially destructive (`DELETE`, `DROP`, `rm`, form submissions with side effects) require an explicit `mutating: true` flag in the test case and a corresponding opt-in in the run config.
- All LLM prompts and responses are logged (with secrets redacted) for audit, but access to these logs is restricted like any other sensitive operational data.

---

## 7. Extensibility Requirements

- New adapters register via a plugin entry-point mechanism (e.g., Python `entry_points` in `pyproject.toml`), not hardcoded imports in the core.
- Oracle strategies (deterministic checkers, LLM judges, visual diff engines) are pluggable via a common `Oracle` interface.
- Reporters (HTML, JSON, JUnit XML, Slack notification, GitHub Issue filer) are pluggable via a common `Reporter` interface.
- Test generators (spec-based, exploration-based, diff-based/risk-based) are pluggable via a common `Generator` interface.

---

## 8. Constraints & Assumptions

- Assumes network access to the target under test and to the LLM provider's API.
- Assumes targets expose enough structure to introspect (OpenAPI spec, reachable DOM, `--help` text) — pure black-box binaries with no introspection are out of scope until a dedicated fuzzing-based adapter is built (Phase 5+).
- Assumes a single organization/user context in v1 (no multi-tenant auth model yet).

---

## 9. Acceptance Criteria for "Core Loop Done" (Phase 1 exit gate)
1. Given an OpenAPI spec, Sentinel generates ≥20 meaningful test cases covering happy path, boundary, and auth-failure scenarios without human editing.
2. Sentinel executes those cases against a live test API and produces a correct pass/fail report validated by manual spot-check (≥95% agreement).
3. A deliberately broken endpoint is caught with zero false negatives across 3 repeated runs.
4. Full loop (ingest → plan → generate → execute → report) completes for a ~30-endpoint API in under 10 minutes.
5. Report artifacts (JSON + HTML) are generated and CI exit code reflects pass/fail correctly.
