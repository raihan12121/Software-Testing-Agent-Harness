"""Executor for dispatching test cases to adapters.

Adheres to:
- rules.md R-SAFE-1 (Read-only by default, check allow_mutations)
- rules.md R-SAFE-4 (Resource limits, timeouts)
- rules.md R-EXEC-1 (Isolation between test cases, reset_state)
- rules.md R-EXEC-2 (Flaky != failed, retry tracking)
- rules.md R-EXEC-3 (Timeouts are mandatory)
"""

from __future__ import annotations

import concurrent.futures
import time
from typing import Callable

from sentinel.adapters.base import TargetAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.schemas import Observation, TestCase, TestStep


class Executor:
    """Dispatches test cases to target adapters with timeout, retry, and safety enforcement."""

    def __init__(self, target_config: TargetConfig, run_config: RunConfig) -> None:
        self.target_config = target_config
        self.run_config = run_config

    def execute_test(self, adapter: TargetAdapter, test_case: TestCase) -> tuple[Observation, int]:
        """Execute a single test case with safety checks, retries, and isolation.

        Returns:
            (final_observation, retry_count)
        """
        # R-SAFE-1: Guard against unauthorized mutations
        if test_case.mutating and not self.run_config.allow_mutations:
            return (
                Observation(
                    test_id=test_case.id,
                    raw_result={},
                    duration_ms=0,
                    error="BLOCKED_BY_POLICY: Test case is marked mutating=True but allow_mutations=False (R-SAFE-1).",
                ),
                0,
            )

        # R-EXEC-1: Isolation - reset state if needed
        try:
            adapter.reset_state(self.target_config)
        except Exception:
            pass  # Some adapters may not implement state reset

        max_retries = self.run_config.retry_budget
        attempt = 0
        last_obs: Observation | None = None

        while attempt <= max_retries:
            obs = self._execute_steps(adapter, test_case)
            last_obs = obs

            # If execution had no low-level error, return observation and attempt count
            if not obs.error:
                return obs, attempt

            attempt += 1
            if attempt <= max_retries:
                time.sleep(0.1 * attempt)  # Backoff before retry

        return (
            last_obs or Observation(test_id=test_case.id, raw_result={}, duration_ms=0, error="Unknown failure"),
            max_retries,
        )

    def _execute_steps(self, adapter: TargetAdapter, test_case: TestCase) -> Observation:
        """Execute all steps for a test case sequentially, aggregating observations."""
        total_duration_ms = 0
        merged_raw: dict = {}
        all_artifacts = []

        for step in test_case.steps:
            # Inject test_id into step metadata for adapter context
            step.metadata["test_id"] = test_case.id

            # R-EXEC-3: Enforce step timeout
            timeout_sec = step.timeout_seconds or self.run_config.timeout_seconds

            step_obs = self._run_step_with_timeout(adapter, step, timeout_sec)
            total_duration_ms += step_obs.duration_ms
            merged_raw.update(step_obs.raw_result)
            all_artifacts.extend(step_obs.artifacts)

            if step_obs.error:
                return Observation(
                    test_id=test_case.id,
                    raw_result=merged_raw,
                    artifacts=all_artifacts,
                    duration_ms=total_duration_ms,
                    error=step_obs.error,
                )

        return Observation(
            test_id=test_case.id,
            raw_result=merged_raw,
            artifacts=all_artifacts,
            duration_ms=total_duration_ms,
            error=None,
        )

    def _run_step_with_timeout(self, adapter: TargetAdapter, step: TestStep, timeout_sec: float) -> Observation:
        """Run single step with hard timeout."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(adapter.execute_action, step)
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError:
                return Observation(
                    test_id=step.metadata.get("test_id", "UNKNOWN"),
                    raw_result={},
                    duration_ms=int(timeout_sec * 1000),
                    error=f"TIMEOUT: Step exceeded timeout limit of {timeout_sec}s (R-SAFE-4 / R-EXEC-3).",
                )
            except Exception as exc:
                return Observation(
                    test_id=step.metadata.get("test_id", "UNKNOWN"),
                    raw_result={},
                    duration_ms=0,
                    error=f"EXECUTION_EXCEPTION: {exc}",
                )

    def run_suite(
        self,
        adapter: TargetAdapter,
        test_cases: list[TestCase],
        on_result: Callable[[TestCase, Observation, int], None] | None = None,
    ) -> list[tuple[TestCase, Observation, int]]:
        """Run a list of test cases, supporting worker pool parallelism."""
        results: list[tuple[TestCase, Observation, int]] = []
        parallelism = min(self.run_config.parallelism, len(test_cases) or 1)

        if parallelism <= 1:
            for tc in test_cases:
                obs, retries = self.execute_test(adapter, tc)
                results.append((tc, obs, retries))
                if on_result:
                    on_result(tc, obs, retries)
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism) as pool:
            future_to_tc = {pool.submit(self.execute_test, adapter, tc): tc for tc in test_cases}
            for future in concurrent.futures.as_completed(future_to_tc):
                tc = future_to_tc[future]
                obs, retries = future.result()
                results.append((tc, obs, retries))
                if on_result:
                    on_result(tc, obs, retries)

        return results
