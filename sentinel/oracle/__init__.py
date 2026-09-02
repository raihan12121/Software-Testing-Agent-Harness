"""Oracle layer for evaluating test results."""

from sentinel.oracle.base import Oracle, get_oracle, register_oracle
from sentinel.oracle.deterministic import DeterministicOracle

__all__ = ["Oracle", "register_oracle", "get_oracle", "DeterministicOracle"]

