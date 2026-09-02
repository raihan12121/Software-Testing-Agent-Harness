"""Unit tests for canonical schemas."""

import pytest
from pydantic import ValidationError

from sentinel.core.schemas import (
    ExpectedResult,
    Observation,
    TestCase,
    TestStep,
    Verdict,
)


def test_test_case_valid_construction():
    tc = TestCase(
        id="TC-001",
        target_type="api",
        title="Test API Endpoint",
        priority="high",
        tags=["auth", "smoke"],
        steps=[
            TestStep(action="http_request", method="GET", path="/api/v1/resource")
        ],
        expected=ExpectedResult(
            oracle="deterministic",
            assertions=["status_code == 200"],
        ),
        mutating=False,
        generated_by="human",
    )
    assert tc.id == "TC-001"
    assert tc.priority == "high"
    assert tc.mutating is False
    assert len(tc.steps) == 1
    assert tc.expected.oracle == "deterministic"


def test_test_case_validation_missing_required():
    with pytest.raises(ValidationError):
        # Missing id and steps
        TestCase(
            target_type="api",
            title="Incomplete",
            expected=ExpectedResult(oracle="deterministic"),
        )


def test_expected_result_llm_judge_requires_criteria():
    with pytest.raises(ValidationError):
        ExpectedResult(oracle="llm_judge", judge_criteria=None)

    valid_judge = ExpectedResult(oracle="llm_judge", judge_criteria="Check UI consistency")
    assert valid_judge.judge_criteria == "Check UI consistency"


def test_verdict_creation():
    verdict = Verdict(
        test_id="TC-001",
        status="pass",
        oracle_used="deterministic",
        reasoning="All checks passed",
        duration_ms=150,
    )
    assert verdict.status == "pass"
    assert verdict.oracle_used == "deterministic"
    assert verdict.retries == 0


def test_observation_creation():
    obs = Observation(
        test_id="TC-001",
        raw_result={"status_code": 200, "body": {"ok": True}},
        duration_ms=45,
    )
    assert obs.test_id == "TC-001"
    assert obs.raw_result["status_code"] == 200
    assert obs.error is None
