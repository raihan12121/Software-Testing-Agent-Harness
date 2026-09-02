"""TargetAdapter Protocol and Adapter Registry.

Adheres to:
- TRD.md §3.1 (Adapter Interface)
- rules.md R-BUILD-1 (Adapters never talk to the LLM)
- rules.md R-BUILD-2 (Core has zero target-specific imports)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sentinel.core.config import TargetConfig
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


@runtime_checkable
class TargetAdapter(Protocol):
    """Protocol that all target-type adapters must implement."""

    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect the target and return a structured model of it
        (endpoints, pages, commands, schema, etc.)."""
        ...

    def execute_action(self, action: TestStep) -> Observation:
        """Perform a single test action (HTTP call, click, keypress, DB query, CLI invocation)
        and return a structured observation (response, DOM state, stdout, etc.)."""
        ...

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Extract screenshots/logs/traces relevant to this observation."""
        ...

    def reset_state(self, config: TargetConfig) -> None:
        """Return the target to a known baseline state where supported
        (test DB rollback, browser context reset, etc.)."""
        ...


_ADAPTER_REGISTRY: dict[str, type[TargetAdapter]] = {}


def register_adapter(target_type: str, adapter_cls: type[TargetAdapter]) -> None:
    """Register an adapter class for a given target type."""
    _ADAPTER_REGISTRY[target_type.lower()] = adapter_cls


def get_adapter(target_type: str) -> TargetAdapter:
    """Retrieve an instantiated adapter for the specified target type."""
    target_key = target_type.lower()
    if target_key not in _ADAPTER_REGISTRY:
        available = list(_ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"No adapter registered for target type '{target_type}'. Available adapters: {available}"
        )
    return _ADAPTER_REGISTRY[target_key]()
