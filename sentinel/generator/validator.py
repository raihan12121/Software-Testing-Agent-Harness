"""Schema validation and repair-retry loop for generated test cases.

Adheres to:
- rules.md R-GEN-2 (Schema validation before acceptance + repair loop)
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import ValidationError

from sentinel.core.logging import logger
from sentinel.core.schemas import TestCase


class GenerationValidator:
    """Validates generated test cases against the canonical schema with repair retries."""

    MAX_RETRIES = 2

    def validate_and_repair(
        self,
        raw_data: dict[str, Any],
        repair_fn: Callable[[dict[str, Any], str], dict[str, Any]] | None = None,
    ) -> TestCase | None:
        """Validate raw dictionary against TestCase schema, attempting repairs up to MAX_RETRIES.

        Returns:
            Validated TestCase instance or None if all repair attempts failed.
        """
        curr_data = raw_data
        last_error = ""

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Direct validation
                return TestCase.model_validate(curr_data)
            except ValidationError as err:
                last_error = str(err)
                logger.warning(f"TestCase schema validation failed on attempt {attempt}: {err}")

                if attempt < self.MAX_RETRIES:
                    if repair_fn:
                        curr_data = repair_fn(curr_data, last_error)
                    else:
                        # Auto-repair heuristic: fix common missing fields
                        curr_data = self._apply_auto_repair(curr_data)
                else:
                    logger.error(
                        f"TestCase generation discarded after {self.MAX_RETRIES} repair attempts: {last_error}"
                    )
                    return None

        return None

    def _apply_auto_repair(self, data: dict[str, Any]) -> dict[str, Any]:
        """Apply deterministic repairs for common generation omissions."""
        repaired = dict(data)
        if "id" not in repaired:
            repaired["id"] = "TC-AUTO-REPAIRED"
        if "target_type" not in repaired:
            repaired["target_type"] = "api"
        if "title" not in repaired:
            repaired["title"] = "Repaired Test Case"
        if "steps" not in repaired:
            repaired["steps"] = []
        if "expected" not in repaired:
            repaired["expected"] = {"oracle": "deterministic", "assertions": ["status_code == 200"]}
        if "generated_by" not in repaired:
            repaired["generated_by"] = "validator_repair_loop"
        return repaired
