# Product Requirements Document (PRD)
## Universal SQA Testing Harness / Agent ("Sentinel")

**Version:** 1.0
**Status:** Draft for build
**Owner:** You (Product/Tech Lead)
**Last updated:** 2026-09-02

---

## 1. Purpose & Vision

Build an autonomous, extensible **Software Quality Assurance (SQA) agent** — internally named **Sentinel** — capable of testing arbitrary software targets (web apps, APIs, mobile apps, desktop apps, CLIs, databases) with minimal human setup. Sentinel should be able to:

1. Ingest a target (URL, repo, API spec, binary, app package).
2. Understand what the target does (via specs, code, or exploration).
3. Plan a test strategy appropriate to the target type and risk profile.
4. Generate and execute tests (functional, regression, performance, security, accessibility).
5. Judge pass/fail using deterministic assertions and, where needed, an LLM-as-judge oracle.
6. Report results, log defects, and learn from history to improve future runs.

The long-term vision is a **type-agnostic testing brain** with **pluggable hands** (adapters) — the same reasoning/planning core drives a browser, an API client, a mobile driver, or a CLI wrapper, depending on the target.

---

## 2. Problem Statement

Traditional SQA suffers from:

- **High setup cost per project** — every app type needs its own framework, scripts, and maintenance.
- **Shallow coverage** — human testers and static scripts can't explore edge cases exhaustively.
- **Brittle automation** — UI-based scripts break on minor changes (selector drift).
- **Slow feedback loops** — full regression suites are expensive to run and triage.
- **Fragmented tooling** — different tools for web, API, mobile, performance, security; no unified view of quality.
- **Manual test-case authorship** — writing test cases is slow and inconsistent in quality.

Sentinel addresses this by centralizing planning/reasoning in one agent core, while keeping execution modular so new software types can be supported by adding an adapter, not rebuilding the system.

---

## 3. Goals & Non-Goals

### 3.1 Goals
- G1: Support testing of at least these target types in v1–v2: Web apps, REST/GraphQL APIs, CLI tools.
- G2: Auto-generate test cases from specs (OpenAPI, DOM/page structure, requirements text) with human-reviewable output.
- G3: Execute tests with retries, parallelism, and artifact capture (screenshots, logs, traces, HTTP payloads).
- G4: Provide two oracle tiers: deterministic assertions (fast, reliable) and LLM-as-judge (fuzzy/semantic checks), never LLM-only for critical paths.
- G5: Produce structured, actionable reports (pass/fail, coverage, flaky tests, severity-ranked defects).
- G6: Persist a "memory" of past runs, known-flaky tests, and defect history to prioritize future testing (risk-based testing).
- G7: Run in CI/CD (headless, exit codes, machine-readable output) and standalone/interactively.
- G8: Be extensible — adding a new target type (e.g., mobile) should require a new adapter, not core rewrites.

### 3.2 Non-Goals (explicitly out of scope for v1)
- NG1: Full autonomous production deployment/rollback decisions.
- NG2: Replacing human exploratory testers entirely — Sentinel augments, not replaces, humans in v1.
- NG3: Formal certification-grade testing (e.g., DO-178C, medical device software) — not a target use case initially.
- NG4: Testing of embedded/firmware/IoT hardware-in-the-loop systems in v1 (planned as a later adapter, v3+).
- NG5: Building our own foundation model — Sentinel consumes an LLM via API, it doesn't train one.

---

## 4. Target Users / Personas

| Persona | Description | Needs |
|---|---|---|
| **Solo developer / indie hacker** | Building a web app or API, wants confidence before shipping | Fast setup, low config, sane defaults |
| **QA Engineer** | Owns test strategy for a team | Fine-grained control, reviewable generated tests, integration with existing test repos |
| **Engineering Manager / Tech Lead** | Cares about release risk and quality trends | Dashboards, quality gates in CI, defect trend reports |
| **You (the builder)** | Building this as a learning + portfolio project, and to actually use on your own projects | Modular, well-documented, extensible codebase |

---

## 5. Scope by Software Type (phased)

| Target type | Phase introduced | Adapter tech (planned) | Notes |
|---|---|---|---|
| REST/GraphQL APIs | Phase 1 | HTTP client + schema validation | Easiest to start: deterministic, no UI flakiness |
| Web applications | Phase 2 | Playwright | DOM inspection, visual diffing, accessibility |
| CLI tools | Phase 2 | subprocess wrapper | stdin/stdout/exit-code based |
| Databases | Phase 3 | DB drivers (SQL/NoSQL) | Data integrity, migration testing |
| Desktop apps | Phase 4 | Platform-specific (WinAppDriver / AT-SPI / macOS Accessibility API) | Higher complexity, OS-dependent |
| Mobile apps | Phase 4 | Appium | iOS/Android, device farms |
| Embedded/IoT | Phase 5 (stretch) | Hardware-in-the-loop, serial/MQTT | Out of scope until core is proven |

---

## 6. Functional Requirements

### 6.1 Ingestion
- FR-1: Accept a target definition: URL, repo path, OpenAPI/Swagger spec, Postman collection, or natural-language requirements doc.
- FR-2: Auto-detect target type where possible (e.g., presence of `openapi.yaml` → API target).
- FR-3: Support manual override of target type and configuration via a config file (`sentinel.config.yaml`).

### 6.2 Test Planning
- FR-4: Generate a test plan covering, at minimum: happy path, boundary values, invalid input, auth/permission checks, and (for APIs) schema conformance.
- FR-5: Support risk-based prioritization using historical defect data and recent code diffs (if a git repo is provided).
- FR-6: Allow human review/edit of the generated plan before execution (human-in-the-loop gate, configurable to skip in CI).

### 6.3 Test Generation
- FR-7: Generate structured test cases in a standard internal schema (see `design.md`) — not just prose — so they're executable and diffable.
- FR-8: Support test generation from: OpenAPI specs, page object/DOM structure, CLI `--help` output, and free-text requirements.
- FR-9: Deduplicate and cluster near-identical generated cases.

### 6.4 Execution
- FR-10: Execute test cases via the appropriate adapter with configurable parallelism.
- FR-11: Capture artifacts: request/response payloads, screenshots, console logs, network traces, stdout/stderr, exit codes.
- FR-12: Support retry-on-failure with a configurable retry budget to distinguish real failures from flakiness.
- FR-13: Support execution against multiple environments (local, staging, prod-readonly) with environment-specific config/secrets handling.

### 6.5 Evaluation (Oracle)
- FR-14: Deterministic assertion evaluation (status codes, schema match, DOM state, exact value match) as the default oracle.
- FR-15: LLM-as-judge oracle for semantic/fuzzy checks (e.g., "does this response make sense," visual regression judgment), used only when deterministic checks are insufficient, with the judge's reasoning logged for auditability.
- FR-16: Confidence scoring on LLM-judged results; low-confidence results flagged for human review, not silently marked pass/fail.

### 6.6 Reporting & Feedback
- FR-17: Machine-readable report (JSON) + human-readable report (HTML/Markdown) per run.
- FR-18: Trend view across runs: pass rate, flaky-test list, coverage delta, defect severity distribution.
- FR-19: Auto-file defects to an external tracker (GitHub Issues at minimum) with repro steps and artifacts attached.
- FR-20: CI-friendly exit codes and a quality gate threshold (e.g., fail build if pass rate < 95% or any Critical severity defect found).

### 6.7 Memory & Learning
- FR-21: Persist run history, known-flaky tests, and defect patterns (see `memory.md`).
- FR-22: Use memory to bias future test generation toward historically risky areas.
- FR-23: Allow pruning/expiry of stale memory (e.g., tests for removed features).

---

## 7. Non-Functional Requirements (summary — full detail in TRD.md)
- Reliability: deterministic checks must never produce false negatives due to agent non-determinism.
- Performance: full regression run on a medium web app should complete in a target run-time budget defined per-project.
- Security: no secrets in logs/artifacts; sandboxed execution of any generated/exploratory actions.
- Extensibility: new adapter addable in under ~1 day of engineering effort once core interfaces stabilize.
- Observability: every agent decision must be traceable (why was this test generated, why did the oracle decide pass/fail).

---

## 8. Success Metrics

| Metric | Target (v1) |
|---|---|
| Time to first test run on a new API target | < 15 minutes from spec to first report |
| False positive rate (flagged fail, actually passing) | < 5% |
| False negative rate (flagged pass, actually broken) | ~0% for deterministic checks |
| Defect detection vs. baseline manual testing (pilot project) | ≥ parity |
| New adapter build time (post v2 core stabilization) | ≤ 2 engineer-days |

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LLM-generated tests are shallow or repetitive | Medium coverage, false confidence | Combine LLM generation with rule-based heuristics (boundary value analysis, equivalence partitioning); track coverage metrics, not just test count |
| LLM-as-judge is non-deterministic / hallucinates verdicts | False pass/fail | Use deterministic oracle wherever possible; log judge reasoning; require confidence threshold; sample human review |
| Agent takes destructive actions on a live/prod system | Data loss, outages | Strict environment allow-listing; read-only mode by default; sandboxing; explicit opt-in for mutating actions |
| Selector/DOM drift breaks web tests | Flaky suite | Prefer role/accessibility-tree based locators over brittle CSS/XPath; self-healing locator strategy with human review of changes |
| Secrets/credentials leak via logs or LLM context | Security incident | Secrets redaction pipeline before any artifact is logged or sent to an LLM |
| Scope creep across too many target types at once | Never ship v1 | Strict phase gating (see `phases.md`) — API + Web only until core loop is proven |

---

## 10. Open Questions
1. Will Sentinel run purely locally/self-hosted, or also as a hosted service? (Affects secrets handling and multi-tenancy.)
2. Which LLM provider(s) are primary vs. fallback for cost/latency tradeoffs?
3. Do we need multi-agent (planner/executor/critic as separate LLM roles) from day one, or single-agent-with-tools first? (Research suggests single-agent baselines are already strong; multi-agent gains are mostly in coverage, not correctness — see `architecture.md` §2.)
4. What's the human-in-the-loop policy for production-adjacent test targets?

---

## 11. References Consulted
- ICST 2026 ASTA workshop research comparing single- vs multi-agent LLM test generation architectures (coverage vs. execution success rate tradeoffs).
- 2026 industry guidance on LLM agent evaluation harnesses (mock-the-model unit testing, fixture-based eval, threshold-based CI gates).
- Current (2026) LLM-as-judge best practices for scalable subjective assessment combined with deterministic checks.
