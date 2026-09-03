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


def test_explore_mode_web_app_validation(tmp_path):
    """Verify Explore Mode against sandboxed multi-page web app discovers untested flows (P3 item 14)."""
    import sys
    from pathlib import Path
    root_dir = str(Path(__file__).parent.parent)
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    from examples.demo_shop_app import run_server
    from sentinel.adapters.web_adapter.adapter import WebAdapter
    from sentinel.core.orchestrator import Orchestrator

    server = run_server(8898)
    base_url = "http://127.0.0.1:8898"

    try:
        target_config = TargetConfig(
            target_type="web",
            name="demo-shop-app",
            base_url=base_url,
            allowed_hosts=["127.0.0.1", "localhost"],
        )
        run_config = RunConfig(
            run_id="run-explore-shop",
            project_id="explore-validation",
            environment="staging",
            allow_mutations=True,
            output_dir=tmp_path / "reports",
        )

        explorer = AutonomousExplorer(target_config, run_config)
        adapter = WebAdapter(target_config)

        # 1. Discover untested flows
        discovered_tests = explorer.explore(adapter, max_steps=4)
        assert len(discovered_tests) >= 3
        paths = [t.steps[0].path for t in discovered_tests]
        assert any("cart" in p for p in paths)
        assert any("checkout" in p for p in paths)
        assert any("product/1" in p for p in paths)

        # 2. Execute discovered test cases via Orchestrator
        orch = Orchestrator(target_config, run_config)
        report, exit_code = orch.run_tests(discovered_tests)
        assert len(report.verdicts) >= 3
        assert report.pass_count >= 3
        assert exit_code == 0
    finally:
        server.shutdown()
        server.server_close()

