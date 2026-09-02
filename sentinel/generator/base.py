"""Generator component interfaces."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sentinel.core.schemas import TargetModel, TestCase
from sentinel.planner.base import TestPlan


@runtime_checkable
class Generator(Protocol):
    """Protocol for test case generators."""

    def generate(self, plan: TestPlan, target_model: TargetModel) -> list[TestCase]:
        """Convert planned scenarios into concrete, executable TestCases."""
        ...
