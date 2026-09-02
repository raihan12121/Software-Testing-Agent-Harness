"""Orchestrator for the Sentinel core control loop.

Adheres to:
- architecture.md §3.1 (Top-level control loop)
- design.md §3 (Core Algorithm)
- rules.md R-EXEC-2 (Flaky != failed)
- rules.md R-REPORT-1 (Severity-based gating)
- TRD.md §2.5 (CLI exit codes: 0 = pass, 1 = failures, 2 = error)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import sentinel.adapters  # noqa: F401 - Register built-in adapters
import sentinel.oracle  # noqa: F401 - Register built-in oracles
import sentinel.reporter  # noqa: F401 - Register built-in reporters
from sentinel.adapters.base import get_adapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Report, TestCase, Verdict
from sentinel.executor.executor import Executor
from sentinel.oracle.base import get_oracle
from sentinel.reporter.base import get_reporter


class Orchestrator:
    """Coordinates discovery, execution, oracle evaluation, and reporting."""

    def __init__(self, target_config: TargetConfig, run_config: RunConfig) -> None:
        self.target_config = target_config
        self.run_config = run_config
        self.adapter = get_adapter(target_config.target_type)
        self.executor = Executor(target_config, run_config)

    def run_tests(self, test_cases: list[TestCase], report_format: str = "json") -> tuple[Report, int]:
        """Execute a suite of test cases end-to-end.

        Returns:
            (Report, exit_code)
            Exit codes:
                0 = All tests passed (or met quality gate)
                1 = One or more test failures / critical defects
                2 = Execution or configuration error
        """
        start_time = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        logger.info(
            f"Starting Sentinel run {self.run_config.run_id} against {self.target_config.target_type} "
            f"in environment '{self.run_config.environment}' ({len(test_cases)} tests)"
        )

        try:
            # 1. Discovery
            target_model = self.adapter.discover(self.target_config)
            logger.info(f"Discovered target '{target_model.name}' with {len(target_model.endpoints)} endpoints.")

            # 2. Execution
            executed_results = self.executor.run_suite(self.adapter, test_cases)

            # 3. Oracle Evaluation
            verdicts: list[Verdict] = []
            pass_count = 0
            fail_count = 0
            flaky_count = 0
            error_count = 0
            pending_count = 0
            skipped_count = 0
            has_critical_failure = False

            for tc, obs, retries in executed_results:
                oracle = get_oracle(tc.expected.oracle)
                verdict = oracle.evaluate(tc, obs)
                verdict.retries = retries

                # R-EXEC-2: A test that passed after retry is marked flaky
                if verdict.status == "pass" and retries > 0:
                    verdict.status = "flaky"
                    verdict.reasoning = (
                        f"Passed on retry {retries}/{self.run_config.retry_budget}. "
                        f"Marked flaky per R-EXEC-2."
                    )

                # Check for critical failure
                if verdict.status in ("fail", "error") and tc.priority == "critical":
                    has_critical_failure = True

                # Tally counts
                if verdict.status == "pass":
                    pass_count += 1
                elif verdict.status == "fail":
                    fail_count += 1
                elif verdict.status == "flaky":
                    flaky_count += 1
                elif verdict.status == "error":
                    error_count += 1
                elif verdict.status == "pending_review":
                    pending_count += 1
                elif verdict.status == "skipped":
                    skipped_count += 1

                verdicts.append(verdict)

            finished_at = datetime.now(timezone.utc)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # 4. Build Report
            report = Report(
                run_id=self.run_config.run_id,
                project_id=self.run_config.project_id,
                target_type=self.target_config.target_type,
                environment=self.run_config.environment,
                started_at=started_at,
                finished_at=finished_at,
                verdicts=verdicts,
                pass_count=pass_count,
                fail_count=fail_count,
                flaky_count=flaky_count,
                error_count=error_count,
                pending_count=pending_count,
                skipped_count=skipped_count,
                duration_ms=duration_ms,
                summary={
                    "total_tests": len(test_cases),
                    "target_name": target_model.name,
                    "has_critical_failure": has_critical_failure,
                },
            )

            # 5. Output Report
            reporter = get_reporter(report_format)
            report_path = reporter.generate_report(report, self.run_config.output_dir)
            logger.info(f"Report generated at: {report_path}")

            # 6. Determine CI exit code (TRD.md §2.5, rules.md R-REPORT-1)
            total = len(test_cases)
            pass_rate = (pass_count + flaky_count) / total if total > 0 else 1.0

            if error_count > 0:
                exit_code = 2
            elif (
                self.run_config.fail_on_critical_defect and has_critical_failure
            ) or (fail_count > 0) or (pass_rate < self.run_config.quality_gate_min_pass_rate):
                exit_code = 1
            else:
                exit_code = 0

            return report, exit_code

        except Exception as exc:
            logger.error(f"Orchestrator failed with unhandled error: {exc}", exc_info=True)
            empty_report = Report(
                run_id=self.run_config.run_id,
                project_id=self.run_config.project_id,
                target_type=self.target_config.target_type,
                environment=self.run_config.environment,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                error_count=len(test_cases),
                summary={"fatal_error": str(exc)},
            )
            return empty_report, 2
