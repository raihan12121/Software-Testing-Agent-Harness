"""Automated end-to-end regression tests verifying production safety rules (P3 item 16).

Verifies strict enforcement of:
- rules.md R-SAFE-1 (No mutations without explicit allow_mutations)
- rules.md R-SAFE-2 (Production mutation triple opt-in: environment_ack + prod_confirmed)
- rules.md R-SAFE-3 (Explore mode strictly blocked on production)
"""

import argparse
from unittest.mock import MagicMock

import pytest

from sentinel.cli import cmd_run
from sentinel.core.config import EnvironmentConfig, RunConfig, SentinelConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep
from sentinel.executor.executor import Executor
from sentinel.explorer.explorer import AutonomousExplorer, SecurityViolationError


def test_explore_mode_blocked_against_production_directly():
    """Verify R-SAFE-3: AutonomousExplorer refuses to instantiate against environment='production'."""
    target_config = TargetConfig(target_type="web", name="prod-site", base_url="https://prod.example.com")
    run_config = RunConfig(
        run_id="run-prod-explore",
        project_id="safety-test",
        environment="production",
        allow_mutations=False,
    )

    with pytest.raises(SecurityViolationError) as exc_info:
        AutonomousExplorer(target_config, run_config)

    assert "R-SAFE-3" in str(exc_info.value)
    assert "production" in str(exc_info.value)


def test_explore_mode_blocked_via_cli_against_production(capsys):
    """Verify R-SAFE-3: CLI command sentinel run --explore --env production is blocked with exit code 2."""
    args = argparse.Namespace(
        config="non_existent_config.yaml",
        env="production",
        run_id="cli-prod-test",
        project=None,
        target_type="web",
        target="prod-app",
        base_url="https://prod.example.com",
        allow_mutations=False,
        yes_i_know_prod=False,
        parallelism=1,
        timeout=10.0,
        output_dir="reports",
        explore=True,
        test_file=None,
        format="json",
        llm_provider="auto",
    )

    exit_code = cmd_run(args)
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "R-SAFE-3" in captured.out or "R-SAFE-3" in captured.err or "production" in captured.out


def test_mutating_action_blocked_on_production_without_allow_mutations():
    """Verify R-SAFE-1: Mutating test case against production without allow_mutations is blocked."""
    target_config = TargetConfig(target_type="stub", name="prod-target")
    run_config = RunConfig(
        run_id="run-prod-mutation",
        project_id="safety-test",
        environment="production",
        allow_mutations=False,
    )

    mutating_test = TestCase(
        id="TC-PROD-MUTATE-01",
        target_type="stub",
        title="Attempt Unauthorized Production Mutation",
        mutating=True,
        steps=[TestStep(action="write", path="/data", body={"key": "val"})],
        expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
    )

    mock_adapter = MagicMock()
    executor = Executor(target_config, run_config)
    obs, retries = executor.execute_test(mock_adapter, mutating_test)

    # Assert adapter execute_action was never called
    mock_adapter.execute_action.assert_not_called()
    assert obs.error is not None
    assert "BLOCKED_BY_POLICY" in obs.error
    assert "R-SAFE-1" in obs.error


def test_mutating_action_blocked_on_production_without_prod_confirmation():
    """Verify R-SAFE-2: allow_mutations=True on production requires explicit prod_confirmed=True."""
    with pytest.raises(ValueError) as exc_info:
        RunConfig(
            run_id="run-prod-unconfirmed-mutation",
            project_id="safety-test",
            environment="production",
            allow_mutations=True,
            prod_confirmed=False,  # Missing --yes-i-know-prod flag
        )

    assert "R-SAFE-2" in str(exc_info.value)
    assert "production" in str(exc_info.value)


def test_sentinel_config_requires_environment_ack_for_production_mutations():
    """Verify R-SAFE-2: SentinelConfig requires environment_ack='I understand this targets production'."""
    sentinel_conf = SentinelConfig(
        project_id="prod-guard",
        target=TargetConfig(target_type="api", name="prod-api"),
        environments={
            "production": EnvironmentConfig(
                env_name="production",
                allow_mutations=True,
                environment_ack=None,  # Missing explicit ack token
            )
        },
    )

    with pytest.raises(PermissionError) as exc_info:
        sentinel_conf.create_run_config(
            env="production",
            run_id="run-test",
            allow_mutations=True,
            prod_confirmed=True,
        )

    assert "R-SAFE-2" in str(exc_info.value)
    assert "I understand this targets production" in str(exc_info.value)


def test_end_to_end_orchestrator_production_safety(tmp_path):
    """Verify end-to-end Orchestrator execution refuses unauthorized mutations on production."""
    target_config = TargetConfig(target_type="stub", name="prod-site")
    run_config = RunConfig(
        run_id="orch-prod-safety",
        project_id="safety-test",
        environment="production",
        allow_mutations=False,
        output_dir=tmp_path / "reports",
    )

    tests = [
        TestCase(
            id="TC-PROD-READ",
            target_type="stub",
            title="Safe Read Operation",
            mutating=False,
            steps=[TestStep(action="read", path="/status")],
            expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
        ),
        TestCase(
            id="TC-PROD-WRITE",
            target_type="stub",
            title="Blocked Write Operation",
            mutating=True,
            steps=[TestStep(action="write", path="/delete_all")],
            expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
        ),
    ]

    orchestrator = Orchestrator(target_config, run_config)
    report, exit_code = orchestrator.run_tests(tests)

    # Verify read operation passed, while write operation was blocked
    verdicts = {v.test_id: v for v in report.verdicts}
    assert verdicts["TC-PROD-READ"].status == "pass"
    assert verdicts["TC-PROD-WRITE"].status in ("fail", "error")
    assert "BLOCKED_BY_POLICY" in verdicts["TC-PROD-WRITE"].reasoning
    assert "R-SAFE-1" in verdicts["TC-PROD-WRITE"].reasoning
