"""Oracle layer for evaluating test results."""

from sentinel.oracle.base import Oracle, get_oracle, register_oracle
from sentinel.oracle.deterministic import DeterministicOracle
from sentinel.oracle.llm_judge import LLMJudgeOracle
from sentinel.oracle.visual_diff import VisualDiffChecker

__all__ = ["Oracle", "register_oracle", "get_oracle", "DeterministicOracle", "LLMJudgeOracle", "VisualDiffChecker"]

