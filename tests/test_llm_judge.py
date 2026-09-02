"""Unit tests for the LLM-as-Judge Oracle."""

from sentinel.core.schemas import ExpectedResult, Observation, TestCase, TestStep
from sentinel.llm.provider import LLMProvider, LLMUsageMetrics
from sentinel.oracle.llm_judge import JudgeResponse, LLMJudgeOracle


class ConfigurableJudgeProvider(LLMProvider):
    """Mock provider allowing controlled verdict, confidence, and reasoning for testing."""

    def __init__(self, verdict: str, confidence: float, reasoning: str) -> None:
        self.verdict = verdict
        self.confidence = confidence
        self.reasoning = reasoning
        self.last_prompt = ""

    def generate_structured(self, prompt: str, response_model: type, system_prompt: str | None = None):
        self.last_prompt = prompt
        resp = JudgeResponse(
            verdict=self.verdict,  # type: ignore
            confidence=self.confidence,
            reasoning=self.reasoning,
        )
        metrics = LLMUsageMetrics(
            prompt_hash="test_hash",
            model="test-judge",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
        )
        return resp, metrics


def test_llm_judge_high_confidence_pass():
    provider = ConfigurableJudgeProvider(verdict="pass", confidence=0.95, reasoning="Response clearly satisfies criteria.")
    oracle = LLMJudgeOracle(llm_provider=provider)

    tc = TestCase(
        id="TC-JUDGE-01",
        target_type="api",
        title="Check helpful error message",
        steps=[TestStep(action="http_request", path="/login")],
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Error message should be user-friendly"),
    )
    obs = Observation(test_id="TC-JUDGE-01", raw_result={"body": {"error": "Please provide a valid email address."}})

    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pass"
    assert verdict.confidence == 0.95
    assert verdict.reasoning == "Response clearly satisfies criteria."


def test_llm_judge_low_confidence_routes_to_pending_review():
    """Verify R-ORACLE-2: Verdicts with confidence < 0.75 route to pending_review."""
    provider = ConfigurableJudgeProvider(verdict="pass", confidence=0.60, reasoning="Likely acceptable, but borderline.")
    oracle = LLMJudgeOracle(llm_provider=provider)

    tc = TestCase(
        id="TC-JUDGE-02",
        target_type="api",
        title="Check ambiguous wording",
        steps=[TestStep(action="http_request", path="/status")],
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Check wording tone"),
    )
    obs = Observation(test_id="TC-JUDGE-02", raw_result={"body": {"message": "Might be operational."}})

    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pending_review"


def test_llm_judge_uncertain_verdict_routes_to_pending_review():
    """Verify R-ORACLE-2: Uncertain verdict routes to pending_review regardless of confidence."""
    provider = ConfigurableJudgeProvider(verdict="uncertain", confidence=0.85, reasoning="Observation is ambiguous.")
    oracle = LLMJudgeOracle(llm_provider=provider)

    tc = TestCase(
        id="TC-JUDGE-03",
        target_type="api",
        title="Check uncertain outcome",
        steps=[TestStep(action="http_request", path="/item")],
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Check item validity"),
    )
    obs = Observation(test_id="TC-JUDGE-03", raw_result={"body": {}})

    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pending_review"


def test_llm_judge_isolation():
    """Verify R-ORACLE-3: Judge does not receive planner or generator reasoning."""
    provider = ConfigurableJudgeProvider(verdict="pass", confidence=0.90, reasoning="Looks good.")
    oracle = LLMJudgeOracle(llm_provider=provider)

    tc = TestCase(
        id="TC-JUDGE-04",
        target_type="api",
        title="Check isolation",
        steps=[TestStep(action="http_request", path="/")] ,
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Verify home page welcome text"),
    )
    obs = Observation(test_id="TC-JUDGE-04", raw_result={"body": {"welcome": "Hello World"}})

    oracle.evaluate(tc, obs)
    # The prompt should contain criteria and observation, but no planner notes or internal reasoning
    assert "Verify home page welcome text" in provider.last_prompt
    assert "Hello World" in provider.last_prompt
    assert "planner_rationale" not in provider.last_prompt
