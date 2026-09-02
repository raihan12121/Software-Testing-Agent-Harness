"""LLM-as-Judge Oracle for semantic and fuzzy assertions.

Adheres strictly to:
- TRD.md §3.4 (LLM-as-Judge Contract)
- design.md §2 (LLMJudge sketch)
- rules.md R-ORACLE-2 (No silent uncertainty resolution, <0.75 routes to pending_review)
- rules.md R-ORACLE-3 (Judge isolation: blinded from planner/generator rationale)
- rules.md R-ORACLE-4 (Reasoning is mandatory)
- rules.md R-SEC-2 (Redaction before LLM)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from sentinel.core.logging import logger
from sentinel.core.redaction import default_redactor
from sentinel.core.schemas import Observation, TestCase, Verdict
from sentinel.llm.provider import LLMProvider, MockLLMProvider
from sentinel.oracle.base import Oracle, register_oracle


class JudgeResponse(BaseModel):
    """Structured response schema returned by LLM Judge."""
    verdict: Literal["pass", "fail", "uncertain"] = Field(..., description="Verdict outcome")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Mandatory natural language explanation (R-ORACLE-4)")


class LLMJudgeOracle(Oracle):
    """Evaluates semantic, fuzzy, or visual criteria using an LLM-as-judge."""

    CONFIDENCE_THRESHOLD = 0.75

    def __init__(self, llm_provider: LLMProvider | None = None, confidence_threshold: float = 0.75) -> None:
        self.llm = llm_provider or MockLLMProvider()
        self.confidence_threshold = confidence_threshold
        self.redactor = default_redactor

    def evaluate(self, test_case: TestCase, observation: Observation) -> Verdict:
        """Evaluate observation against judge_criteria with strict judge isolation."""
        # Handle execution errors first
        if observation.error:
            return Verdict(
                test_id=test_case.id,
                status="error",
                oracle_used="llm_judge",
                confidence=1.0,
                reasoning=f"Execution error prevented evaluation: {observation.error}",
                duration_ms=observation.duration_ms,
            )

        criteria = test_case.expected.judge_criteria or "Verify that the response is correct and appropriate."

        # R-ORACLE-3: Blind the judge - only provide criteria and sanitized observation (no planner reasoning)
        clean_observation = self.redactor.redact(observation.raw_result)

        prompt = (
            f"Test Intent / Judging Criteria:\n{criteria}\n\n"
            f"Actual Observation:\n{clean_observation}\n\n"
            f"Evaluate whether the observation satisfies the criteria. "
            f"Return a verdict ('pass', 'fail', or 'uncertain'), a confidence score from 0.0 to 1.0, "
            f"and a detailed reasoning string explaining your decision."
        )

        try:
            judge_res, metrics = self.llm.generate_structured(
                prompt=prompt,
                response_model=JudgeResponse,
                system_prompt=(
                    "You are an impartial, objective Software Quality Assurance Judge. "
                    "Evaluate observations strictly against stated criteria. "
                    "You MUST provide clear natural-language reasoning. "
                    "If the observation is ambiguous or insufficient, mark verdict as 'uncertain' "
                    "or give a confidence score below 0.75."
                ),
            )

            # R-ORACLE-4: Reasoning is mandatory
            if not judge_res.reasoning or len(judge_res.reasoning.strip()) < 3:
                logger.error(f"Judge returned empty reasoning for {test_case.id} (R-ORACLE-4). Invaliding verdict.")
                return Verdict(
                    test_id=test_case.id,
                    status="error",
                    oracle_used="llm_judge",
                    confidence=0.0,
                    reasoning="INVALID_VERDICT: Judge omitted mandatory reasoning (R-ORACLE-4).",
                    duration_ms=observation.duration_ms,
                )

            # R-ORACLE-2: Route uncertain or low confidence to pending_review
            if judge_res.verdict == "uncertain" or judge_res.confidence < self.confidence_threshold:
                status = "pending_review"
            elif judge_res.verdict == "pass":
                status = "pass"
            else:
                status = "fail"

            return Verdict(
                test_id=test_case.id,
                status=status,
                oracle_used="llm_judge",
                confidence=judge_res.confidence,
                reasoning=judge_res.reasoning,
                duration_ms=observation.duration_ms,
            )

        except Exception as exc:
            logger.error(f"LLM Judge call failed: {exc}")
            return Verdict(
                test_id=test_case.id,
                status="error",
                oracle_used="llm_judge",
                confidence=0.0,
                reasoning=f"LLM Judge execution failure: {exc}",
                duration_ms=observation.duration_ms,
            )


# Register LLM Judge oracle
register_oracle("llm_judge", LLMJudgeOracle)
