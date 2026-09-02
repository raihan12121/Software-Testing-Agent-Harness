"""Unit tests for configuration loading and safety rules."""

import pytest
from pydantic import ValidationError

from sentinel.core.config import RunConfig, SentinelConfig


def test_run_config_requires_environment():
    with pytest.raises(ValidationError):
        # Missing environment
        RunConfig(run_id="run-1")


def test_production_mutation_rejected_without_confirmation():
    # rules.md R-SAFE-2: production mutations require prod_confirmed
    with pytest.raises(ValueError, match="production"):
        RunConfig(
            run_id="run-prod-1",
            environment="production",
            allow_mutations=True,
            prod_confirmed=False,
        )

    # Valid when confirmed
    conf = RunConfig(
        run_id="run-prod-1",
        environment="production",
        allow_mutations=True,
        prod_confirmed=True,
    )
    assert conf.allow_mutations is True
    assert conf.prod_confirmed is True


def test_sentinel_config_loading(tmp_path):
    config_file = tmp_path / "sentinel.config.yaml"
    config_file.write_text(
        """
project_id: test-proj
target:
  target_type: stub
  name: stub-svc
environments:
  local:
    env_name: local
    allow_mutations: true
  production:
    env_name: production
    allow_mutations: false
defaults:
  parallelism: 4
  timeout_seconds: 20.0
""",
        encoding="utf-8",
    )

    loaded = SentinelConfig.load(config_file)
    assert loaded.project_id == "test-proj"
    assert loaded.target.target_type == "stub"
    assert loaded.defaults["parallelism"] == 4

    run_conf = loaded.create_run_config(env="local", run_id="run-100")
    assert run_conf.environment == "local"
    assert run_conf.allow_mutations is True
    assert run_conf.parallelism == 4
