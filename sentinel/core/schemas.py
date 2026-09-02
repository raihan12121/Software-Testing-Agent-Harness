"""Canonical schemas for Sentinel.

Adheres to:
- TRD.md §3.2 (Test Case Schema)
- TRD.md §3.3 (Observation / Result Schema)
- design.md §2 (Key Class Sketches)
- rules.md (R-SAFE-1 mutating flag, R-ORACLE-4 mandatory reasoning for judge, etc.)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TestStep(BaseModel):
    """A single test step to execute against a target."""
    __test__ = False
    action: str = Field(..., description="Action type, e.g. 'http_request', 'cli_exec', 'browser_click'")
    method: str | None = Field(default=None, description="HTTP method if applicable (GET, POST, etc.)")
    path: str | None = Field(default=None, description="Path or locator or command")
    headers: dict[str, str] = Field(default_factory=dict, description="Headers or env vars")
    params: dict[str, Any] = Field(default_factory=dict, description="Query params or command arguments")
    body: Any = Field(default=None, description="Request payload or stdin data")
    timeout_seconds: float = Field(default=10.0, description="Step execution timeout in seconds (R-EXEC-3)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary step metadata")


class ExpectedResult(BaseModel):
    """Expected outcome and oracle specification for a test case."""
    oracle: Literal["deterministic", "llm_judge"] = Field(
        default="deterministic",
        description="Oracle mechanism to evaluate result"
    )
    assertions: list[str] = Field(
        default_factory=list,
        description="Deterministic assertion expressions, e.g. ['status_code == 200', 'body.error == None']"
    )
    judge_criteria: str | None = Field(
        default=None,
        description="Natural language judging criteria when oracle is 'llm_judge'"
    )

    @field_validator("judge_criteria")
    @classmethod
    def validate_judge_criteria(cls, v: str | None, info) -> str | None:
        oracle = info.data.get("oracle")
        if oracle == "llm_judge" and not v:
            raise ValueError("judge_criteria must be provided when oracle is 'llm_judge'")
        return v


class TestCase(BaseModel):
    """Canonical test case representation."""
    __test__ = False
    id: str = Field(..., description="Unique test case identifier (e.g. TC-0001)")
    target_type: Literal["api", "web", "cli", "db", "database", "mobile", "desktop", "stub"] = Field(
        ...,
        description="Target type this test executes against"
    )
    title: str = Field(..., description="Human-readable title describing the test scenario")
    priority: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description="Test priority"
    )
    tags: list[str] = Field(default_factory=list, description="Categorization tags, e.g. ['auth', 'smoke']")
    preconditions: list[str] = Field(default_factory=list, description="Preconditions required for execution")
    steps: list[TestStep] = Field(..., description="Ordered list of steps to execute")
    expected: ExpectedResult = Field(..., description="Expected results and oracle criteria")
    mutating: bool = Field(
        default=False,
        description="Whether this test case performs mutating operations (R-SAFE-1)"
    )
    generated_by: str = Field(
        default="human",
        description="Provenance of test case: model/version, 'human', or 'rule_engine' (R-GEN-3)"
    )
    source_context: str | None = Field(
        default=None,
        description="Source spec reference (e.g. 'openapi.yaml#/paths/~1login/post') (R-GEN-1, R-GEN-3)"
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Explicit test case dependencies if any (R-EXEC-1)"
    )


class Artifact(BaseModel):
    """Recorded artifact such as screenshot, payload, or log."""
    path: str = Field(..., description="Relative or absolute path to the artifact file")
    mime_type: str = Field(default="text/plain", description="MIME type of the artifact")
    description: str = Field(default="", description="Description of the artifact")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class Observation(BaseModel):
    """Execution observation captured by an adapter."""
    test_id: str = Field(..., description="Test ID this observation belongs to")
    raw_result: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific raw response/stdout/state dictionary"
    )
    artifacts: list[Artifact] = Field(default_factory=list, description="Captured artifacts")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    error: str | None = Field(default=None, description="Execution error message if failed/timed out")


class AssertionResult(BaseModel):
    """Result of an individual assertion check."""
    assertion: str = Field(..., description="Expression evaluated (e.g. 'status_code == 200')")
    actual: Any = Field(default=None, description="Actual value extracted during evaluation")
    passed: bool = Field(..., description="Whether the assertion succeeded")
    message: str | None = Field(default=None, description="Failure or diagnostic message")


class Verdict(BaseModel):
    """Final test verdict produced by an oracle."""
    test_id: str = Field(..., description="Test ID evaluated")
    status: Literal["pass", "fail", "error", "flaky", "skipped", "pending_review"] = Field(
        ...,
        description="Verdict status"
    )
    oracle_used: Literal["deterministic", "llm_judge"] = Field(..., description="Oracle mechanism used")
    confidence: float | None = Field(
        default=None,
        description="Confidence score (0.0 to 1.0) when oracle is 'llm_judge'"
    )
    reasoning: str | None = Field(
        default=None,
        description="Natural language explanation of verdict (Mandatory for llm_judge per R-ORACLE-4)"
    )
    assertions_result: list[AssertionResult] = Field(
        default_factory=list,
        description="Individual assertion evaluations for deterministic oracle"
    )
    retries: int = Field(default=0, description="Number of retries executed (R-EXEC-2)")
    duration_ms: int = Field(default=0, description="Total duration in milliseconds")


class TargetModel(BaseModel):
    """Structured representation of the introspected target."""
    target_type: str = Field(..., description="Type of target, e.g. 'api', 'web', 'cli'")
    name: str = Field(default="", description="Name or identifier of target")
    endpoints: list[dict[str, Any]] = Field(default_factory=list, description="Endpoints/commands/pages")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata from discovery")


class Report(BaseModel):
    """Complete run report for Sentinel execution."""
    run_id: str = Field(..., description="Unique run identifier")
    project_id: str = Field(default="default", description="Project identifier")
    target_type: str = Field(..., description="Target type tested")
    environment: str = Field(..., description="Target environment tested (R-EXEC-4)")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verdicts: list[Verdict] = Field(default_factory=list, description="Verdicts for all executed tests")
    pass_count: int = 0
    fail_count: int = 0
    flaky_count: int = 0
    error_count: int = 0
    pending_count: int = 0
    skipped_count: int = 0
    duration_ms: int = 0
    summary: dict[str, Any] = Field(default_factory=dict, description="Summary statistics and metadata")
