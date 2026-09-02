"""Unit tests for the CLIAdapter."""

import sys

from sentinel.adapters.cli_adapter.adapter import CLIAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_cli_adapter_discovery():
    config = TargetConfig(target_type="cli", name="python", custom_options={"binary": sys.executable})
    adapter = CLIAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "cli"
    assert len(model.endpoints) >= 1
    assert model.endpoints[0]["path"] == "--help"


def test_cli_adapter_successful_execution():
    config = TargetConfig(target_type="cli", name="python")
    adapter = CLIAdapter(config)

    step = TestStep(
        action="exec",
        path=f'{sys.executable} -c "import sys; sys.stdout.write(\'SENTINEL_CLI_SUCCESS\')"',
    )
    obs = adapter.execute_action(step)

    assert obs.error is None
    assert obs.raw_result["exit_code"] == 0
    assert "SENTINEL_CLI_SUCCESS" in obs.raw_result["stdout"]
    assert obs.duration_ms >= 0


def test_cli_adapter_failure_and_artifact_capture():
    config = TargetConfig(target_type="cli", name="python")
    adapter = CLIAdapter(config)

    step = TestStep(
        action="exec",
        path=f'{sys.executable} -c "import sys; sys.stderr.write(\'ERROR_LOG\'); sys.exit(42)"',
    )
    obs = adapter.execute_action(step)

    assert obs.raw_result["exit_code"] == 42
    assert "ERROR_LOG" in obs.raw_result["stderr"]
    assert len(obs.artifacts) >= 1
    assert obs.artifacts[0].metadata["exit_code"] == 42


def test_cli_adapter_timeout_enforcement():
    config = TargetConfig(target_type="cli", name="python")
    adapter = CLIAdapter(config)

    step = TestStep(
        action="exec",
        path=f'{sys.executable} -c "import time; time.sleep(1.0)"',
        timeout_seconds=0.1,
    )
    obs = adapter.execute_action(step)

    assert obs.error is not None
    assert "TIMEOUT" in obs.error
