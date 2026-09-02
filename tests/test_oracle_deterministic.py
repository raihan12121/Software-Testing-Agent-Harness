"""Unit tests for the deterministic oracle."""

from sentinel.core.schemas import ExpectedResult, Observation, TestCase, TestStep
from sentinel.oracle.deterministic import DeterministicOracle


def test_deterministic_oracle_pass():
    oracle = DeterministicOracle()
    tc = TestCase(
        id="TC-101",
        target_type="stub",
        title="Valid 200 response check",
        steps=[TestStep(action="http_request", method="GET", path="/health")],
        expected=ExpectedResult(
            oracle="deterministic",
            assertions=[
                "status_code == 200",
                "body.status == 'ok'",
                "body.count >= 1",
            ],
        ),
    )
    obs = Observation(
        test_id="TC-101",
        raw_result={"status_code": 200, "body": {"status": "ok", "count": 5}},
        duration_ms=50,
    )
    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pass"
    assert len(verdict.assertions_result) == 3
    assert all(r.passed for r in verdict.assertions_result)


def test_deterministic_oracle_fail():
    oracle = DeterministicOracle()
    tc = TestCase(
        id="TC-102",
        target_type="stub",
        title="Check status code mismatch",
        steps=[TestStep(action="http_request", method="GET", path="/api/item")],
        expected=ExpectedResult(
            oracle="deterministic",
            assertions=["status_code == 200", "body.found == True"],
        ),
    )
    obs = Observation(
        test_id="TC-102",
        raw_result={"status_code": 404, "body": {"found": False}},
        duration_ms=30,
    )
    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "fail"
    assert len(verdict.assertions_result) == 2
    assert not verdict.assertions_result[0].passed
    assert not verdict.assertions_result[1].passed


def test_deterministic_oracle_handles_execution_error():
    oracle = DeterministicOracle()
    tc = TestCase(
        id="TC-103",
        target_type="stub",
        title="Check error handling",
        steps=[TestStep(action="http_request", method="GET", path="/fail")],
        expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
    )
    obs = Observation(
        test_id="TC-103",
        raw_result={},
        error="Network timeout connection refused",
    )
    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "error"
    assert "Network timeout" in (verdict.reasoning or "")
