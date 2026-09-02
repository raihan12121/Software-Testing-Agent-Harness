"""Planner component interfaces and schemas."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from sentinel.core.schemas import TargetModel


class Scenario(BaseModel):
    """A high-level test scenario identified by the planner."""
    id: str
    title: str
    description: str = ""
    target_component: str = ""
    priority: str = "medium"
    tags: list[str] = Field(default_factory=list)
    risk_score: float = 0.0


class TestPlan(BaseModel):
    """Structured test plan produced by the planner."""
    project_id: str
    target_type: str
    scenarios: list[Scenario] = Field(default_factory=list)


@runtime_checkable
class Planner(Protocol):
    """Protocol for test planning engines."""

    def build_plan(self, target_model: TargetModel, memory_context: dict | None = None) -> TestPlan:
        """Analyze target model and memory to generate prioritized scenarios."""
        ...
