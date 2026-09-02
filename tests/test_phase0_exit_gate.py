"""Phase 0 Exit Gate Verification Test.

Directly tests the exit gate criterion defined in phases.md §Phase 0:
'A hand-written TestCase (no LLM involved) can be executed end-to-end through
a stub adapter and produce a JSON report. No generation or judging yet — just prove the pipe works.'
"""

import json
from pathlib import Path

from sentinel.cli import main as cli_main
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep


def test_phase0_exit_gate_end_to_end(tmp_path: Path):
    """Verify that a hand-written TestCase executes end-to-end through stub adapter to JSON report."""
    output_dir = tmp_path / "reports"

    target_config = TargetConfig(
        target_type="stub",
        name="test-stub-target",
    )

    run_config = RunConfig(
        run_id="gate-run-001",
        project_id="phase0-project",
        environment="local",
        output_dir=output_dir,
    )

    hand_written_test = TestCase(
        id="TC-GATE-01",
        target_type="stub",
        title="Verify stub endpoint health and echo response",
        priority="critical",
        tags=["smoke", "gate"],
        steps=[
            TestStep(
                action="http_request",
                method="GET",
                path="/health",
                metadata={
                    "status_code": 200,
                    "response_body": {
                        "status": "ready",
                        "secret_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token123",
                    },
                },
            )
        ],
        expected=ExpectedResult(
            oracle="deterministic",
            assertions=[
                "status_code == 200",
                "body.status == 'ready'",
            ],
        ),
        generated_by="human",
        source_context="manual_specification_phase0",
    )

    # Execute end-to-end through orchestrator
    orchestrator = Orchestrator(target_config, run_config)
    report, exit_code = orchestrator.run_tests([hand_written_test], report_format="json")

    # Assertions on execution outcomes
    assert exit_code == 0, f"Expected clean pass exit code 0, got {exit_code}"
    assert report.run_id == "gate-run-001"
    assert report.pass_count == 1
    assert report.fail_count == 0
    assert report.error_count == 0
    assert len(report.verdicts) == 1

    verdict = report.verdicts[0]
    assert verdict.test_id == "TC-GATE-01"
    assert verdict.status == "pass"
    assert verdict.oracle_used == "deterministic"
    assert len(verdict.assertions_result) == 2
    assert all(a.passed for a in verdict.assertions_result)

    # Verify JSON report on disk
    expected_report_file = output_dir / "report_gate-run-001.json"
    assert expected_report_file.exists(), f"Report file {expected_report_file} does not exist"

    saved_content = expected_report_file.read_text(encoding="utf-8")
    data = json.loads(saved_content)

    assert data["run_id"] == "gate-run-001"
    assert data["environment"] == "local"
    assert data["pass_count"] == 1
    assert len(data["verdicts"]) == 1

    # Verify secrets redaction in the generated report (R-SEC-1, R-SEC-3)
    assert "token123" not in saved_content
    print("\nPhase 0 Exit Gate Successfully Verified!")


def test_phase0_cli_execution(tmp_path: Path):
    """Verify Phase 0 execution through CLI interface."""
    output_dir = tmp_path / "cli_reports"
    sample_test_file = tmp_path / "test.yaml"
    sample_test_file.write_text(
        """
- id: TC-CLI-01
  target_type: stub
  title: "CLI test execution"
  priority: medium
  steps:
    - action: http_request
      method: GET
      path: /health
      metadata:
        status_code: 200
        response_body: {"alive": true}
  expected:
    oracle: deterministic
    assertions:
      - "status_code == 200"
      - "body.alive == True"
  generated_by: human
""",
        encoding="utf-8",
    )

    exit_code = cli_main(
        [
            "run",
            "--env",
            "local",
            "--target-type",
            "stub",
            "--test-file",
            str(sample_test_file),
            "--output-dir",
            str(output_dir),
            "--run-id",
            "cli-run-999",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "report_cli-run-999.json").exists()
