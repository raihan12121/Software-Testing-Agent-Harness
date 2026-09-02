"""Unit tests for Autonomous Explore Mode and R-SAFE-3 sandbox enforcement."""

import pytest

from sentinel.adapters.api_adapter.adapter import APIAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.explorer.explorer import AutonomousExplorer, SecurityViolationError


def test_explore_mode_blocked_on_production():
    """Verify R-SAFE-3: Explore mode is strictly prohibited on production."""
    target_config = TargetConfig(target_type="api", name="prod-target")
    run_config = RunConfig(
        run_id="run-prod-explore",
        project_id="security-test",
        environment="production",
        allow_mutations=False,
    )

    with pytest.raises(SecurityViolationError) as exc_info:
        AutonomousExplorer(target_config, run_config)

    assert "R-SAFE-3" in str(exc_info.value)
    assert "production" in str(exc_info.value)


def test_explore_mode_discovery_on_staging():
    """Verify Explore Mode discovers unmapped flows in staging environment."""
    target_config = TargetConfig(
        target_type="api",
        name="staging-target",
        spec_path="examples/petstore_spec.yaml",
        base_url="http://127.0.0.1:8765",
    )
    run_config = RunConfig(
        run_id="run-staging-explore",
        project_id="explore-test",
        environment="staging",
        allow_mutations=True,
    )

    explorer = AutonomousExplorer(target_config, run_config)
    adapter = APIAdapter(target_config)

    discovered = explorer.explore(adapter, max_steps=5)
    assert len(discovered) > 0
    assert all(tc.id.startswith("TC-EXPLORE-") for tc in discovered)
    assert any("debug=true" in tc.steps[0].path for tc in discovered)
