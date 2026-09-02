# Architecture Document
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Last updated:** 2026-09-02

---

## 1. Architectural Principles

1. **Separate the brain from the hands.** Planning/reasoning (what to test, is it correct) is target-agnostic. Execution (how to click a button, how to send an HTTP request) is target-specific and lives in adapters.
2. **Deterministic-first.** Every layer prefers deterministic logic; the LLM is invoked only where deterministic logic can't do the job (novel test-idea generation, semantic judgment, natural-language spec understanding).
3. **Everything is data.** Test cases, observations, and verdicts are structured, versioned, diffable artifacts — not opaque agent chatter.
4. **Single-agent core, multi-role prompting.** Research (ICST 2026 ASTA workshop) shows multi-agent architectures improve coverage (~99.75% vs single-agent's strong baseline) but not correctness (Execution Success Rate ~97.3% either way), at higher cost/complexity. Sentinel starts with a **single orchestrating agent that plays different roles (planner, generator, judge) via distinct prompts/contexts**, and only splits into true multi-agent (separate processes/contexts) where a role benefits from isolation — e.g., the judge must not see the planner's reasoning, to avoid confirmation bias.
5. **Plugin-based extensibility.** Adapters, oracles, generators, and reporters are all pluggable — the core never imports a specific adapter directly.
6. **Fail loud, not silent.** Uncertain LLM verdicts, adapter errors, and flaky tests are surfaced explicitly, never silently resolved.

---

## 2. High-Level System Diagram

```
                        ┌─────────────────────────────────────────┐
                        │              CLI / API / CI              │
                        │        (sentinel run / plan / report)    │
                        └───────────────────┬───────────────────────┘
                                             │
                        ┌────────────────────▼────────────────────┐
                        │            ORCHESTRATOR (core)            │
                        │  - Owns the agent loop                    │
                        │  - Coordinates planner/generator/judge     │
                        │  - Manages run state & concurrency         │
                        └───┬────────┬─────────┬────────┬──────────┘
                            │        │         │        │
                ┌───────────▼─┐ ┌────▼────┐ ┌──▼─────┐ ┌▼─────────────┐
                │   PLANNER    │ │GENERATOR│ │EXECUTOR│ │    ORACLE     │
                │ (risk-based  │ │(spec →  │ │(runs   │ │ (deterministic│
                │  test plan)  │ │ test    │ │ cases  │ │  + LLM judge) │
                │              │ │ cases)  │ │ via    │ │               │
                │              │ │         │ │adapter)│ │               │
                └──────────────┘ └─────────┘ └───┬────┘ └───────────────┘
                                                  │
                        ┌─────────────────────────▼─────────────────────────┐
                        │                 ADAPTER LAYER                      │
                        │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │
                        │  │  API   │ │  Web   │ │  CLI   │ │  DB / Mobile│  │
                        │  │Adapter │ │Adapter │ │Adapter │ │  / Desktop  │  │
                        │  └────────┘ └────────┘ └────────┘ └────────────┘  │
                        └─────────────────────────┬─────────────────────────┘
                                                  │
                                    ┌──────────────▼──────────────┐
                                    │         TARGET UNDER TEST     │
                                    │ (API / web app / CLI / DB...) │
                                    └────────────────────────────────┘

        ┌───────────────────────────────────────────────────────────────┐
        │  CROSS-CUTTING: Memory Store · Artifact Store · Reporter ·      │
        │  Secrets/Redaction · Observability (tracing/logging)            │
        └───────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 Orchestrator (core loop)
The orchestrator runs the top-level control loop:

```
1. Load target config → discover() via adapter → TargetModel
2. Planner: TargetModel + Memory → TestPlan (prioritized list of scenarios)
3. Generator: TestPlan scenarios → concrete TestCase objects (schema in TRD.md)
4. Executor: for each TestCase (parallelized) → adapter.execute_action() → Observation
5. Oracle: Observation + TestCase.expected → Verdict
6. Reporter: aggregate Verdicts → Report (JSON/HTML/JUnit)
7. Memory: persist run, verdicts, flaky/defect data
8. Exit with appropriate code
```

This loop is intentionally **linear and inspectable** in v1 (not a free-roaming agent loop), because SQA needs predictability and auditability more than open-ended autonomy. Autonomy is added incrementally (Phase 3+): e.g., the executor may re-invoke the generator mid-run if it discovers new, previously-unknown endpoints during exploration ("explore-then-test" mode).

### 3.2 Planner
- Input: `TargetModel` (from adapter discovery) + `Memory` (past defects, flaky areas, code diff if available).
- Output: `TestPlan` — a prioritized list of *scenarios* (natural-language + tags), not yet concrete test cases.
- Logic: hybrid — rule-based heuristics (equivalence partitioning, boundary value analysis, CRUD coverage checklist) generate a baseline scenario set; LLM call augments with scenarios a human tester would think of (edge cases, security probes, negative paths) grounded in the actual spec/DOM/CLI help text (not hallucinated).

### 3.3 Generator
- Converts each planned scenario into one or more concrete, executable `TestCase` objects in the canonical schema.
- Uses LLM structured output (JSON schema-constrained) — never free-text parsed via regex.
- Validates generated cases against the schema before accepting them; malformed output triggers a repair retry (generation-validation-repair pattern), consistent with current best practice in LLM-based test generation research.
- Deduplicates near-identical cases via similarity clustering.

### 3.4 Executor
- Pulls `TestCase`s from a queue, dispatches to the correct adapter based on `target_type`.
- Manages concurrency (worker pool), retries (to separate real failures from flakiness), timeouts, and state isolation/reset between cases.
- Captures `Observation` + `Artifact`s for every execution.

### 3.5 Adapters
Each adapter implements the `TargetAdapter` interface (TRD.md §3.1). Adapters are the **only** components that know how to talk to a specific technology (Playwright, httpx, subprocess, Appium, etc.). This is the primary extension point for supporting new software types.

### 3.6 Oracle
Two-tier:
- **Deterministic Oracle** (default): schema validators, status-code/value assertions, DOM state assertions, exact-match checks. Fast, cheap, reliable.
- **LLM-as-Judge Oracle** (fallback): invoked only when the test case's `expected.oracle` is `llm_judge` (e.g., "the error message should be user-friendly," visual correctness). Returns verdict + confidence + reasoning (TRD.md §3.4). Low-confidence verdicts route to human review queue, never silently pass.

### 3.7 Memory Store
See `memory.md` for full schema. Summary of what's stored: run history, per-test pass/fail time series (for flaky detection), defect records with severity/root cause tags, and a "risk index" per module/endpoint/page used to bias the Planner.

### 3.8 Reporter
Pluggable output formats: JSON (machine), HTML (human dashboard), JUnit XML (CI integration), GitHub Issues (defect filing), Slack/webhook notification (optional).

### 3.9 Cross-cutting concerns
- **Secrets/redaction filter**: sits between every component and (a) storage, (b) LLM calls.
- **Observability**: structured tracing of every orchestrator step and every LLM call (prompt, response, tokens, latency, cost) for debugging and cost control.
- **Config system**: `sentinel.config.yaml` per project, layered with environment-specific overrides.

---

## 4. Data Flow Example (API target)

1. User runs `sentinel run --target openapi.yaml --env staging`.
2. Adapter (`APIAdapter.discover`) parses the OpenAPI spec → `TargetModel` (endpoints, schemas, auth scheme).
3. Planner produces scenarios: "valid login," "expired token," "SQL-injection-shaped input on `search` param," "missing required field on `POST /orders`," etc., informed by Memory (e.g., `/orders` has 3 historical defects → high priority).
4. Generator turns each scenario into concrete `TestCase`s with real payloads.
5. Executor fires HTTP requests via `APIAdapter.execute_action`, capturing responses.
6. Oracle: schema + status-code checks (deterministic) for nearly all cases; LLM judge only for a case like "error message is helpful and doesn't leak stack traces."
7. Reporter emits `report.json`, `report.html`, `junit.xml`; CI fails the build because one Critical-severity defect was found (SQLi input returned a 500 with a stack trace).
8. Memory records the defect against `/search`, raising its risk index for the next run.

---

## 5. Why Not Pure Multi-Agent from Day One?

Current (2026) research directly comparing single-agent vs. multi-agent LLM architectures for black-box test generation found multi-agent setups gain meaningfully in **coverage** (up to ~99.75%) but are roughly on par in **execution success rate** (~97.3% vs ~97.25% for single-agent), while adding orchestration complexity, latency, and cost. Given Sentinel's SQA use case values **correctness and auditability** highly, the architecture:
- Starts single-agent-with-roles (cheaper, simpler, easier to debug/trust).
- Reserves true multi-agent (separate contexts/processes) for the **planner vs. judge separation** specifically, since judge independence from planner reasoning is a correctness-relevant isolation, not just a coverage optimization.
- Revisits full multi-agent (e.g., competing test-generation agents to maximize coverage) as a Phase 4+ enhancement once the core loop is proven and coverage becomes the binding constraint rather than correctness.

---

## 6. Deployment Topology

- **Local/dev mode:** single process, SQLite memory store, local filesystem artifacts — for individual developers and small projects.
- **CI mode:** ephemeral container per run, memory store mounted from a persistent volume or remote DB, artifacts uploaded to CI's artifact storage.
- **Hosted/team mode (Phase 4+):** orchestrator as a service, Postgres memory store, S3-compatible artifact store, multi-project/multi-user support, web dashboard.

---

## 7. Key Architectural Decisions Log (ADR summary)

| Decision | Rationale | Alternative considered |
|---|---|---|
| Single-agent-with-roles over multi-agent for v1 | Correctness parity, lower cost/complexity, easier debugging | Full multi-agent (planner/generator/executor/judge as separate LLM contexts from day one) |
| Deterministic oracle as default, LLM judge as fallback | Avoid non-determinism on correctness-critical checks | LLM-judge-everything (rejected: cost, non-determinism) |
| Adapter plugin architecture | Extensibility without core rewrites | Hardcoded per-target-type branching in core (rejected: doesn't scale) |
| Structured test case schema (not prose) | Diffable, versionable, executable, auditable | Natural-language test cases interpreted at run time (rejected: fragile, unauditable — see soundness/consistency concerns in current LLM-agent test execution research) |
| Linear inspectable orchestrator loop for v1 | Predictability required for SQA trust | Fully autonomous open-ended agent loop (deferred to Phase 3+ as an opt-in "explore mode") |
