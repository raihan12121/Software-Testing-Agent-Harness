"""Stub Adapter for testing and Phase 0 pipeline verification.

Simulates execution of test steps and produces observations and artifacts
without requiring external services.
"""

from __future__ import annotations

import time
from typing import Any

from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


class StubAdapter(TargetAdapter):
    """Stub adapter for testing the harness pipe in isolation."""

    def __init__(self, default_response: dict[str, Any] | None = None) -> None:
        self.default_response = default_response or {"status_code": 200, "body": {"status": "ok"}}
        self.reset_count = 0
        self.executed_actions: list[TestStep] = []

    def discover(self, config: TargetConfig) -> TargetModel:
        """Return a simulated target model."""
        return TargetModel(
            target_type="stub",
            name=config.name or "stub-target",
            endpoints=[
                {"path": "/health", "method": "GET", "description": "Health check"},
                {"path": "/api/v1/echo", "method": "POST", "description": "Echo endpoint"},
                {"path": "/api/v1/users", "method": "GET", "description": "List users"},
            ],
            metadata={"version": "1.0", "mock": True},
        )

    def execute_action(self, action: TestStep) -> Observation:
        """Execute a simulated action and return a structured observation."""
        start_time = time.perf_counter()
        self.executed_actions.append(action)

        # Allow step metadata or params to override simulated behavior
        sim_delay = action.metadata.get("simulated_delay_seconds", 0.0)
        if sim_delay > 0:
            time.sleep(sim_delay)

        sim_error = action.metadata.get("simulated_error")
        if sim_error:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=action.metadata.get("test_id", "TC-STUB"),
                raw_result={},
                duration_ms=elapsed_ms,
                error=str(sim_error),
            )

        # Build raw result
        sim_status = action.metadata.get("status_code", 200)
        sim_body = action.metadata.get("response_body", action.body or {"status": "ok", "echo": action.path})

        raw_result = {
            "status_code": sim_status,
            "body": sim_body,
            "action": action.action,
            "path": action.path,
            "method": action.method,
        }

        # Simulated artifacts
        artifacts: list[Artifact] = []
        if action.metadata.get("create_artifact", False):
            artifacts.append(
                Artifact(
                    path="artifacts/stub_response.json",
                    mime_type="application/json",
                    description="Simulated HTTP response payload",
                    metadata={"bytes": len(str(sim_body))},
                )
            )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return Observation(
            test_id=action.metadata.get("test_id", "TC-STUB"),
            raw_result=raw_result,
            artifacts=artifacts,
            duration_ms=elapsed_ms,
            error=None,
        )

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return artifacts for the observation."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Reset internal execution state."""
        self.reset_count += 1
        self.executed_actions.clear()


# Register stub adapter by default
register_adapter("stub", StubAdapter)
