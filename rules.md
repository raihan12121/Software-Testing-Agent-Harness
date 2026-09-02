# Rules Document
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Purpose:** Hard constraints and operating rules for both the agent's runtime behavior and the engineering team building it. Rules are non-negotiable defaults; exceptions require explicit, logged opt-in.

---

## 1. Safety & Destructiveness Rules

1. **R-SAFE-1 — Read-only by default.** Sentinel never performs a mutating action (`POST`/`PUT`/`PATCH`/`DELETE` with side effects, form submission that writes data, DB write/DROP, destructive CLI commands) unless the test case is explicitly flagged `mutating: true` **and** the run config explicitly enables `allow_mutations: true` for that environment.
2. **R-SAFE-2 — No production mutation, ever, without triple opt-in.** Mutating actions against any environment tagged `production` require: (a) `allow_mutations: true`, (b) `environment_ack: "I understand this targets production"` literal string in config, and (c) a human confirmation prompt at run start (bypassable only via an explicit `--yes-i-know-prod` CI flag).
3. **R-SAFE-3 — Sandboxed exploration.** Any exploratory/autonomous action (e.g., "explore mode" clicking through a web app to discover flows) runs against a designated test/staging environment only; exploration mode is disabled by default against anything not explicitly tagged `sandbox` or `staging`.
4. **R-SAFE-4 — Resource limits.** All executor runs have hard wall-clock timeouts, max-retry limits, and max-request-rate limits to prevent runaway loops or accidental DoS of the target.
5. **R-SAFE-5 — Network allow-listing.** Adapters may only reach hosts explicitly listed in the target config. Any attempt to reach an unlisted host is blocked and logged as a security event, not silently allowed.

---

## 2. Secrets & Data Handling Rules

6. **R-SEC-1 — No secrets in generated artifacts.** Test cases, reports, and logs never contain raw credentials, API keys, or tokens. Secrets are referenced by name (e.g., `{{staging_api_key}}`) and resolved at execution time from environment variables or a secrets manager.
7. **R-SEC-2 — Redaction before LLM.** All content sent to an LLM (for planning, generation, or judging) passes through a redaction filter that strips known secret patterns (API keys, JWTs, passwords, PII patterns) before leaving the process.
8. **R-SEC-3 — Redaction before storage.** The same redaction filter applies before any artifact (log, screenshot metadata, HTTP payload) is written to the memory store or artifact store.
9. **R-SEC-4 — No PII in test data by default.** Synthetic/fake data generation is preferred for names, emails, addresses, etc.; real user data is never used in generated test cases unless explicitly provided by the user for a specific, consented purpose.
10. **R-SEC-5 — Least privilege credentials.** Test accounts/API keys used by Sentinel must be scoped to the minimum permissions needed for the test plan; the agent must never request or infer elevated credentials on its own.

---

## 3. Oracle & Verdict Rules

11. **R-ORACLE-1 — Deterministic first.** If a deterministic assertion can express the expected behavior, it must be used instead of an LLM judge.
12. **R-ORACLE-2 — No silent uncertainty resolution.** An LLM judge verdict of `uncertain`, or any verdict below the configured confidence threshold (default 0.75), is never auto-resolved to `pass` or `fail` — it is routed to a human review queue and the run report explicitly shows "N results pending human review."
13. **R-ORACLE-3 — Judge isolation.** The LLM judge must not see the planner's or generator's reasoning/rationale for a test case — only the test's stated intent/expected behavior and the actual observation — to avoid confirmation bias.
14. **R-ORACLE-4 — Reasoning is mandatory.** Every LLM judge verdict must include a logged natural-language reasoning string; verdicts without reasoning are treated as invalid and discarded.
15. **R-ORACLE-5 — No retroactive verdict changes without a trail.** If a human overrides an oracle verdict, the override and the reason are recorded alongside the original verdict — the original is never deleted.

---

## 4. Test Generation Rules

16. **R-GEN-1 — Grounded generation only.** Test cases must be generated with reference to an actual artifact (spec, DOM snapshot, `--help` output, requirements doc) — never purely from the LLM's general knowledge of "what a login page probably looks like." Ungrounded generation is flagged and requires human review before execution.
17. **R-GEN-2 — Schema validation before acceptance.** Every generated test case is validated against the canonical schema (TRD.md §3.2); invalid cases trigger a repair-retry loop (max 2 retries) before being discarded and logged as a generation failure.
18. **R-GEN-3 — Provenance tracking.** Every test case records `generated_by` (model/version or "human" or "rule_engine") and `source_context` (what spec/section it came from).
19. **R-GEN-4 — No duplicate/near-duplicate bloat.** Generated cases are deduplicated via similarity clustering before being added to a run; near-duplicates are merged with a note, not silently dropped (traceability).

---

## 5. Execution Rules

20. **R-EXEC-1 — Isolation between test cases.** No test case's execution may depend on state left behind by another, unless explicitly declared as a sequential scenario (`depends_on: [TC-xxxx]`). Default is independent, resettable state.
21. **R-EXEC-2 — Flaky ≠ failed.** A test that passes after retry is marked `flaky`, not `pass` or `fail` outright, and is surfaced separately in reporting — never silently treated as a clean pass.
22. **R-EXEC-3 — Timeouts are mandatory.** No test action executes without an explicit timeout; default timeouts are defined per adapter type and are overridable per test case, never globally disabled.
23. **R-EXEC-4 — Environment tagging is mandatory.** Every run declares its target environment (`local`/`staging`/`production`/`sandbox`); the executor refuses to run if this tag is missing.

---

## 6. Reporting & Escalation Rules

24. **R-REPORT-1 — Severity-based gating.** CI quality gates are defined by severity, not raw pass rate alone: any single `Critical` severity defect fails the build regardless of overall pass percentage.
25. **R-REPORT-2 — No suppressing failures.** A failing test cannot be excluded from a report without an explicit, logged suppression record (who, when, why) — silent exclusion is prohibited.
26. **R-REPORT-3 — Full traceability.** Every reported defect links back to: the test case, the run ID, the artifacts, and (if applicable) the judge's reasoning.

---

## 7. Engineering / Build Rules (for the team building Sentinel itself)

27. **R-BUILD-1 — Adapters never talk to the LLM.** Only the Planner/Generator/Oracle components call the LLM; adapters are pure execution/introspection code. This keeps the "hands" deterministic and testable in isolation (mock-the-model unit testing pattern).
28. **R-BUILD-2 — Core has zero target-specific imports.** The orchestrator, planner, generator, and oracle must never import a specific adapter (e.g., `playwright`) directly — only via the `TargetAdapter` interface, enforced by lint rule / import boundary check.
29. **R-BUILD-3 — Every LLM call is logged with cost/latency.** No LLM call ships without instrumentation (prompt hash, token count, latency, cost) for observability and budget control.
30. **R-BUILD-4 — New adapters require a conformance test suite.** Before a new adapter is merged, it must pass a standard adapter-conformance test suite (discover/execute/capture/reset all behave per interface contract) to guarantee it plugs into the core loop correctly.
31. **R-BUILD-5 — Documentation-as-code.** Any change to the test case schema, adapter interface, or oracle contract must update `design.md`/`TRD.md` in the same change set — docs are never allowed to drift from code.

---

## 8. Exception Process

Any rule above may be overridden **only** via an explicit, named config flag (never a default), and every override must be logged in the run's audit trail with who/what/why. Rules R-SAFE-1 through R-SAFE-3 additionally require the triple-opt-in described in R-SAFE-2 when targeting production-tagged environments.
