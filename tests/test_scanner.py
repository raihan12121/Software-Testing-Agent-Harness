"""Unit tests for ProjectScanner and project directory auto-detection."""

from pathlib import Path

from sentinel.scanner import ProjectScanner


def test_project_scanner_finds_api_spec_and_env():
    cwd = Path.cwd()
    scanner = ProjectScanner(cwd)
    targets = scanner.scan()

    assert len(targets) > 0
    target_types = {t.target_type for t in targets}
    # Should detect OpenAPI spec from examples/ and python CLI
    assert "api" in target_types
    assert "cli" in target_types

    api_target = next(t for t in targets if t.target_type == "api")
    assert "petstore_spec.yaml" in api_target.target_path


def test_project_scanner_empty_dir(tmp_path: Path):
    scanner = ProjectScanner(tmp_path)
    targets = scanner.scan()
    assert targets == []
