# Phases Document (Build Roadmap)
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Last updated:** 2026-09-02

Philosophy: **prove the core loop on the easiest, most deterministic target type first (APIs), then generalize.** Each phase has a hard exit gate — do not start the next phase until the current one's gate is met. This mirrors the PRD's non-goal of avoiding scope creep.

---

## Phase 0 — Foundations (Completed)

**Goal:** Skeleton project, no intelligence yet — just the plumbing.

- [x] Set up repo structure, `pyproject.toml`, CI skeleton (lint, type-check, unit test runner).
- [x] Define and implement the canonical `TestCase`, `Observation`, `Verdict` schemas (TRD.md §3.2–3.3) with validation.
- [x] Implement the `TargetAdapter`, `Oracle`, `Generator`, `Reporter` interfaces as abstract base classes/Protocols.
- [x] Implement config loading (`sentinel.config.yaml`) and secrets/redaction filter.
- [x] Implement basic structured logging/tracing.

**Exit gate:** [PASSED & VERIFIED] A hand-written `TestCase` (no LLM involved) can be executed end-to-end through a stub adapter and produce a JSON report. No generation or judging yet — just prove the pipe works.

---

## Phase 1 — API Adapter + Core Loop (Completed)

**Goal:** The full agent loop works on the easiest, most deterministic target: REST APIs.

- [x] Build `APIAdapter`: OpenAPI spec parsing → `TargetModel`; HTTP execution; JSON schema validation as deterministic oracle.
- [x] Build the rule-based half of the Planner: equivalence partitioning, boundary value analysis, CRUD coverage checklist, auth/permission checklist — all without an LLM.
- [x] Integrate the LLM for: (a) augmenting the rule-based plan with additional scenarios grounded in the spec, (b) generating concrete request payloads for each scenario.
- [x] Implement the Generator's schema-validation + repair-retry loop.
- [x] Implement basic Reporter: JSON + HTML.
- [x] Implement a minimal Memory store (SQLite): run history + per-test pass/fail log.
- [x] Write the adapter-conformance test suite (R-BUILD-4) and validate `APIAdapter` against it.

**Exit gate (= TRD.md §9 acceptance criteria):** [PASSED & VERIFIED]
1. [x] ≥20 meaningful test cases generated from a real OpenAPI spec without human editing (57 scenarios generated from sample spec).
2. [x] Correct pass/fail on a live test API, ≥95% agreement with manual spot-check.
3. [x] Zero false negatives across 3 repeated runs against a deliberately broken endpoint.
4. [x] Full loop < 10 minutes for a ~30-endpoint API (executed in seconds).
5. [x] CI exit codes correct; JSON + HTML reports generated.

**Milestone significance:** this is the "prove the brain works" phase. Everything after this is about adding more hands (adapters) and refining the brain — not rearchitecting it.

---

## Phase 2 — Web Adapter + LLM-as-Judge + CLI Adapter (Completed)

**Goal:** Generalize beyond pure deterministic targets; introduce the fuzzy oracle; add a second and third target type to validate the adapter abstraction actually generalizes.

- [x] Build `WebAdapter` using Playwright: DOM/accessibility-tree discovery, click/type/navigate actions, screenshot capture, worker thread isolation.
- [x] Build `CLIAdapter`: `--help`-based discovery, subprocess execution, stdout/stderr/exit-code assertions.
- [x] Implement the LLM-as-Judge Oracle (TRD.md §3.4) with confidence scoring and human-review routing (R-ORACLE-2).
- [x] Implement visual regression checking (screenshot diffing) as a deterministic pre-check before falling back to LLM judgment for ambiguous visual diffs.
- [x] Extend Memory and CLI with Review Queue (`sentinel review`) and human resolution audit logging (R-ORACLE-5).
- [x] Extend conformance test suite (R-BUILD-4) to validate CLIAdapter and WebAdapter.

**Exit gate:** [PASSED & VERIFIED]
1. [x] `WebAdapter` runs a full test plan against a real multi-page web app, correctly catching at least 2 seeded bugs and producing zero false positives on the clean baseline.
2. [x] `CLIAdapter` passes its conformance suite and correctly tests a real CLI tool.
3. [x] LLM-as-judge correctly defers to human review on a deliberately ambiguous test case (proves R-ORACLE-2 works, not just exists).
4. [x] Adding `CLIAdapter` took materially less engineering time than `WebAdapter` (validates the abstraction is paying off — target: ≤ 2 engineer-days per TRD.md §7).

---

## Phase 3 — Risk-Based Testing, Memory Maturity, DB Adapter (4–6 weeks)

**Goal:** Make the agent smarter over time, not just wider.

- Build `DatabaseAdapter`: schema/migration validation, data integrity checks, transactional test isolation with rollback (R-EXEC-1).
- Mature the Memory store schema (see `memory.md`) — defect clustering, flaky-test quarantine list, git-diff-aware risk scoring (recently changed code → higher priority).
- Add "explore mode" (bounded autonomous exploration in sandboxed/staging environments only, per R-SAFE-3) to discover untested flows.
- Add auto defect filing to GitHub Issues (FR-19) with repro steps and artifacts attached.
- Begin cost/latency optimization: prompt caching, cheap-model-for-volume / strong-model-for-judging tiering.

**Exit gate:**
1. A second consecutive run on an unchanged target shows the Planner correctly deprioritizing already-well-covered, defect-free areas and prioritizing recently changed/historically risky ones.
2. Explore mode discovers at least one previously untested flow in a pilot web app and generates valid test cases for it.
3. Auto-filed GitHub Issues contain correct repro steps validated by manual reproduction.

---

## Phase 4 — Mobile & Desktop Adapters, Hosted/Team Mode (6–10 weeks)

**Goal:** Broaden target coverage to the harder platforms; make Sentinel usable by a team, not just a solo user.

- Build `MobileAdapter` (Appium — iOS/Android).
- Build `DesktopAdapter` (platform-specific accessibility APIs).
- Migrate Memory store from SQLite to Postgres; add multi-project/multi-user support.
- Build a web dashboard for trend viewing, quality gates, and human-review queue (for R-ORACLE-2 escalations).
- Revisit multi-agent architecture for coverage optimization (architecture.md §5) now that correctness is proven — evaluate competitive/collaborative multi-agent generation for coverage gains on mature targets.

**Exit gate:**
1. Mobile and desktop adapters pass conformance suites and catch seeded bugs in pilot apps.
2. Team of 2+ users can run Sentinel against the same project with shared memory/history via the dashboard.
3. A/B comparison shows measurable coverage improvement from multi-agent generation on a mature target, or a documented decision not to adopt it if gains don't justify cost.

---

## Phase 5 — Stretch: Performance, Security, Embedded/IoT (open-ended)

**Goal:** Round out non-functional and specialized testing types explicitly deferred in the PRD's non-goals.

- Performance/load testing adapter (integrate or build on existing load-testing tools, orchestrated by Sentinel's planner for risk-based load scenario selection).
- Security/pentest-oriented test generation (grounded, scoped, with strict R-SAFE guardrails — never freeform "hack the target").
- Embedded/IoT hardware-in-the-loop adapter (serial/MQTT protocols) — only after core platform is stable and there's concrete demand.

**Exit gate:** defined per sub-project when Phase 5 is actually scoped; not blocking for the core product.

---

## Cross-Phase Rules
- No phase begins until the previous phase's exit gate is met and documented (avoids the "scope creep" risk called out in PRD §9).
- Every phase ends with an update pass on `architecture.md`, `design.md`, and `memory.md` to prevent doc drift (per rules.md R-BUILD-5).
- Every new adapter must pass the standard conformance suite (rules.md R-BUILD-4) before its phase is considered closed.
