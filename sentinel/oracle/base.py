"""Oracle Protocol and Oracle Registry.

Adheres to:
- TRD.md §3.4 (Oracle Contract)
- rules.md R-ORACLE-1 (Deterministic first)
- rules.md R-ORACLE-4 (Reasoning is mandatory for LLM judge)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sentinel.core.schemas import Observation, TestCase, Verdict


@runtime_checkable
class Oracle(Protocol):
    """Protocol for evaluating an observation against a test case's expected outcome."""

    def evaluate(self, test_case: TestCase, observation: Observation) -> Verdict:
        """Evaluate observation and return structured Verdict."""
        ...


_ORACLE_REGISTRY: dict[str, type[Oracle]] = {}


def register_oracle(oracle_type: str, oracle_cls: type[Oracle]) -> None:
    """Register an oracle class for an oracle type."""
    _ORACLE_REGISTRY[oracle_type.lower()] = oracle_cls


def get_oracle(oracle_type: str) -> Oracle:
    """Retrieve an instantiated oracle for the specified oracle type."""
    oracle_key = oracle_type.lower()
    if oracle_key not in _ORACLE_REGISTRY:
        available = list(_ORACLE_REGISTRY.keys())
        raise ValueError(
            f"No oracle registered for type '{oracle_type}'. Available oracles: {available}"
        )
    return _ORACLE_REGISTRY[oracle_key]()
