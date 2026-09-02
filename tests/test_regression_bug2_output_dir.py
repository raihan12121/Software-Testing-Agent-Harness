"""Regression test for BUG 2: --output-dir overrides config file defaults."""

from pathlib import Path

import yaml

from sentinel.cli import main


def test_cli_output_dir_overrides_config_file(tmp_path: Path):
    """Test that an explicit --output-dir CLI flag overrides the output directory in config file."""
    config_data = {
        "version": "1.0",
        "project": "test-project-bug2",
        "target": {
            "target_type": "stub",
            "name": "Test Stub Target",
        },
        "defaults": {
            "output_dir": str(tmp_path / "config_default_reports"),
        },
        "environments": {
            "local": {
                "env_name": "local",
                "allow_mutations": True,
            }
        },
    }

    config_path = tmp_path / "sentinel.config.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")

    cli_custom_out_dir = tmp_path / "cli_override_reports"
    assert not cli_custom_out_dir.exists()

    exit_code = main([
        "run",
        "--config", str(config_path),
        "--env", "local",
        "--output-dir", str(cli_custom_out_dir),
        "--format", "json",
    ])

    assert exit_code in (0, 1), f"Unexpected exit code {exit_code}"

    # Assert report was written to the CLI-specified directory
    assert cli_custom_out_dir.exists(), "CLI override output_dir was not created"
    reports_in_cli_dir = list(cli_custom_out_dir.glob("*.json"))
    assert len(reports_in_cli_dir) >= 1, "Report was not written to CLI-specified output_dir"

    # Assert report was NOT written to the config-default directory
    config_default_dir = tmp_path / "config_default_reports"
    if config_default_dir.exists():
        reports_in_default = list(config_default_dir.glob("*.json"))
        assert len(reports_in_default) == 0, "Report was incorrectly written to config default dir"
