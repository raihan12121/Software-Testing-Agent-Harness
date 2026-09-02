# Design Document
## Sentinel — Universal SQA Testing Harness / Agent

**Version:** 1.0
**Companion to:** architecture.md (system-level), TRD.md (interfaces)
**Last updated:** 2026-09-02

This document goes one level deeper than `architecture.md`: concrete module layout, class sketches, key algorithms, and UX (CLI/dashboard) design.

---

## 1. Repository / Module Layout

```
sentinel/
├── core/
│   ├── orchestrator.py       # main control loop
│   ├── schemas.py            # TestCase, Observation, Verdict, TargetModel (pydantic models)
│   ├── config.py             # sentinel.config.yaml loading + validation
│   └── redaction.py          # secrets redaction filter
├── planner/
│   ├── rule_based.py         # equivalence partitioning, boundary value analysis, checklists
│   ├── llm_planner.py        # LLM-augmented scenario generation
│   └── risk_scoring.py       # memory-informed prioritization
├── generator/
│   ├── llm_generator.py      # scenario -> concrete TestCase (structured output)
│   ├── validator.py          # schema validation + repair-retry loop
│   └── dedup.py              # similarity clustering
├── executor/
│   ├── executor.py           # queue, worker pool, retries, timeouts
│   └── state.py              # isolation / reset coordination
├── oracle/
│   ├── deterministic.py      # assertion evaluators (status code, schema, DOM state, exact match)
│   ├── llm_judge.py          # LLM-as-judge, confidence scoring
│   └── visual_diff.py        # screenshot diffing (pre-check before LLM visual judgment)
├── adapters/
│   ├── base.py                # TargetAdapter Protocol
│   ├── api_adapter/
│   ├── web_adapter/
│   ├── cli_adapter/
│   ├── db_adapter/
│   ├── mobile_adapter/        # Phase 4
│   └── desktop_adapter/       # Phase 4
├── memory/
│   ├── store.py               # SQLite (v1) / Postgres (v4) abstraction
│   ├── models.py              # run, test_history, defect, flaky_test, risk_index tables
│   └── queries.py             # risk scoring queries, flaky detection queries
├── reporter/
│   ├── json_reporter.py
│   ├── html_reporter.py
│   ├── junit_reporter.py
│   └── issue_filer.py         # GitHub Issues integration
├── llm/
│   ├── provider.py            # LLMProvider interface (Anthropic primary)
│   └── prompts/               # versioned prompt templates
├── cli.py                     # `sentinel run|plan|report` entrypoints
└── tests/                     # Sentinel's own test suite (dogfooding!)
```

**Design note:** `adapters/*` are the only modules allowed to import target-specific libraries (Playwright, Appium, etc.) — enforced by an import-linter rule per `rules.md` R-BUILD-2.

---

## 2. Key Class Sketches

```python
# core/schemas.py
class TestCase(BaseModel):
    id: str
    target_type: Literal["api", "web", "cli", "db", "mobile", "desktop"]
    title: str
    priority: Literal["low", "medium", "high", "critical"]
    tags: list[str]
    preconditions: list[str] = []
    steps: list[TestStep]
    expected: ExpectedResult
    mutating: bool = False
    generated_by: str
    source_context: str | None = None

class ExpectedResult(BaseModel):
    oracle: Literal["deterministic", "llm_judge"]
    assertions: list[str] = []          # for deterministic
    judge_criteria: str | None = None   # for llm_judge

class Observation(BaseModel):
    test_id: str
    raw_result: dict                    # adapter-specific payload
    artifacts: list[Artifact]
    duration_ms: int
    error: str | None = None

class Verdict(BaseModel):
    test_id: str
    status: Literal["pass", "fail", "error", "flaky", "skipped", "pending_review"]
    oracle_used: Literal["deterministic", "llm_judge"]
    confidence: float | None = None      # only for llm_judge
    reasoning: str | None = None         # only for llm_judge, mandatory when used (rules.md R-ORACLE-4)
    assertions_result: list[AssertionResult] = []
```

```python
# adapters/base.py
class TargetAdapter(Protocol):
    def discover(self, config: TargetConfig) -> TargetModel: ...
    def execute_action(self, action: TestStep) -> Observation: ...
    def capture_artifacts(self, observation: Observation) -> list[Artifact]: ...
    def reset_state(self, config: TargetConfig) -> None: ...
```

```python
# oracle/llm_judge.py
class LLMJudge:
    CONFIDENCE_THRESHOLD = 0.75

    def evaluate(self, test_case: TestCase, observation: Observation) -> Verdict:
        # Note: does NOT receive planner/generator reasoning (rules.md R-ORACLE-3)
        response = self.llm.judge(
            intent=test_case.expected.judge_criteria,
            observation=self.redactor.clean(observation),
        )
        status = "pass" if response.verdict == "pass" and response.confidence >= self.CONFIDENCE_THRESHOLD \
                 else "fail" if response.verdict == "fail" and response.confidence >= self.CONFIDENCE_THRESHOLD \
                 else "pending_review"
        return Verdict(
            test_id=test_case.id, status=status, oracle_used="llm_judge",
            confidence=response.confidence, reasoning=response.reasoning,
        )
```

---

## 3. Core Algorithm: The Orchestration Loop

```python
def run(target_config: TargetConfig, run_config: RunConfig) -> Report:
    adapter = adapter_registry.get(target_config.target_type)
    target_model = adapter.discover(target_config)

    memory_context = memory.get_risk_context(target_config.project_id)
    plan = planner.build_plan(target_model, memory_context)          # scenarios
    test_cases = generator.generate(plan, target_model)               # concrete TestCase[]
    test_cases = dedup.cluster_and_merge(test_cases)

    verdicts = []
    with executor.worker_pool(run_config.parallelism) as pool:
        for tc in test_cases:
            obs = pool.submit(execute_with_retry, adapter, tc, run_config.retry_budget)
            verdict = oracle_registry.get(tc.expected.oracle).evaluate(tc, obs)
            verdicts.append(verdict)

    report = reporter.build(verdicts, run_id=run_config.run_id)
    memory.persist_run(run_config.run_id, test_cases, verdicts)
    return report
```

`execute_with_retry` wraps `adapter.execute_action`, applying timeouts (R-EXEC-3) and marking results `flaky` rather than `pass` when a retry was needed (R-EXEC-2).

---

## 4. Risk Scoring Algorithm (Planner bias)

Simple, explainable v1 scoring (not a black box):

```
risk_score(module) =
      w1 * historical_defect_count(module, lookback_days)
    + w2 * recent_change_frequency(module, git_log)      # if repo available
    + w3 * (1 - test_coverage_ratio(module))
    + w4 * flaky_test_count(module)
```

Weights (`w1..w4`) are configurable per project; defaults favor historical defects and recent churn (the two strongest, most literature-supported predictors of future defects). The Planner sorts scenarios by the risk score of the module/endpoint/page they touch, ensuring limited test budget goes to the riskiest areas first.

---

## 5. Prompt Design Principles (LLM layer)

- **Structured output only.** Every LLM call that produces data Sentinel will act on uses JSON-schema-constrained output (tool-use / structured output mode), never freeform text parsed by regex.
- **Grounding is enforced in the prompt, not assumed.** Planner/Generator prompts always include the actual spec/DOM/help-text excerpt the scenario is grounded in, and the prompt explicitly instructs the model to cite `source_context`.
- **Judge prompts are minimal and isolated.** The judge prompt contains only: test intent/criteria + redacted observation. No planner rationale, no other test results, no "hint" of expected outcome beyond the stated criteria — to reduce bias (rules.md R-ORACLE-3).
- **Prompts are versioned files**, not inline strings, so prompt changes are diffable and A/B-testable (`llm/prompts/`).
- **Few-shot + rule-augmented prompting is the default strategy**, consistent with 2026 research showing rule-augmented few-shot prompting outperforming zero-shot and conventional few-shot approaches by 20–30% in coverage/execution success rate for black-box test generation.

---

## 6. CLI UX Design

```
sentinel init                          # scaffold sentinel.config.yaml for a project
sentinel discover --target <spec>      # run discovery only, show TargetModel
sentinel plan --target <spec>          # generate + display test plan for review (human gate)
sentinel run --target <spec> --env staging [--parallelism N] [--allow-mutations]
sentinel report --run-id <id> [--format html|json|junit]
sentinel review                        # interactive queue for pending_review verdicts
```

- `sentinel plan` is the human-in-the-loop checkpoint (FR-6): shows the generated plan in a readable table, lets the user edit/remove scenarios before `run` executes them.
- `sentinel review` surfaces every `pending_review` verdict (from low-confidence LLM judge calls) with the observation, artifacts, and judge reasoning, and lets a human resolve pass/fail/flag-as-bug.

---

## 7. Dashboard UX Design (Phase 4, high-level)

- **Run view:** pass/fail/flaky/pending breakdown, filterable by tag/module/priority.
- **Trend view:** pass-rate over time, coverage delta, defect count by severity, flaky-test leaderboard.
- **Defect view:** severity-ranked list, linked to GitHub Issues, with repro artifacts inline.
- **Review queue:** shared across team members for resolving `pending_review` verdicts.
- **Risk map:** visual (heatmap) of modules/endpoints/pages by risk score, showing where the Planner is currently focusing test budget.

---

## 8. Error Handling & Degradation Design

| Failure mode | Design response |
|---|---|
| LLM provider unavailable/timeout | Orchestrator falls back to rule-based-only Planner/Generator (reduced scenario richness, but run still completes); logged as a degraded run |
| Adapter crashes mid-execution | Executor marks remaining queued cases for that adapter as `error` (not silently dropped), continues other adapters if multi-target run |
| Malformed LLM structured output after repair retries exhausted | Scenario discarded, logged as `generation_failure`, surfaced in the report's "generation issues" section — never silently skipped without a trace |
| Target unreachable at discovery | Run aborts immediately with a clear error, before wasting planning/generation effort |
| Memory store unavailable | Run proceeds without risk-based prioritization (falls back to plain rule-based ordering), logged as degraded; run still persists locally and syncs when memory store returns |

---

## 9. Testing Sentinel Itself (dogfooding)

Per current best practice for testing agentic systems: Sentinel's own LLM-calling components are unit-tested with the LLM mocked via dependency injection (deterministic tests, no live API calls in the standard test suite), while a smaller, separate "live eval" suite runs against real LLM calls on a schedule (not every commit) to catch prompt/model drift — mirroring the fixture-based evaluation harness and threshold-based CI gate patterns established in current LLM agent testing practice.
