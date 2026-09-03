"""Unit tests for Priority 0: Release and Publishing Readiness."""

from __future__ import annotations

import tomllib
from pathlib import Path

from sentinel.llm.provider import (
    DEFAULT_ANTHROPIC_MODEL,
    AnthropicLLMProvider,
    get_llm_provider,
)


def test_license_file_exists_and_matches_mit():
    """Verify LICENSE file is present at repo root with MIT license text (P0 item 1)."""
    license_path = Path("LICENSE")
    assert license_path.is_file(), "LICENSE file must exist at repo root."
    content = license_path.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "Muhammad Raihan Molla" in content
    assert "Permission is hereby granted, free of charge" in content


def test_pyproject_toml_configuration():
    """Verify pyproject.toml has correct metadata, readme, classifiers, and URLs (P0 item 2)."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.is_file()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    project = data.get("project", {})
    assert project.get("name") == "sentinel-sqa"
    assert project.get("readme") == "README.md"
    assert project.get("license") == {"text": "MIT"}

    # Classifiers
    classifiers = project.get("classifiers", [])
    assert "License :: OSI Approved :: MIT License" in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Programming Language :: Python :: 3.12" in classifiers
    assert "Programming Language :: Python :: 3.13" in classifiers
    assert "Topic :: Software Development :: Testing" in classifiers

    # Project URLs
    urls = project.get("urls", {})
    assert "Homepage" in urls
    assert "Repository" in urls
    assert "Bug Tracker" in urls

    # Optional dependency groups
    extras = project.get("optional-dependencies", {})
    assert "mobile" in extras
    assert "desktop" in extras
    assert "iot" in extras
    assert "db-extended" in extras


def test_dockerignore_exclusions():
    """Verify .dockerignore excludes build caches, artifacts, and test data (P0 item 3)."""
    dockerignore_path = Path(".dockerignore")
    assert dockerignore_path.is_file()
    content = dockerignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")]

    required_exclusions = [
        ".git/",
        ".venv/",
        "tests/",
        "reports/",
        "artifacts/",
        "*.sqlite",
        "*.db",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
    ]
    for req in required_exclusions:
        assert req in lines or req.rstrip("/") in lines or any(req in line for line in lines), f"Missing {req} in .dockerignore"


def test_github_release_workflow_exists():
    """Verify .github/workflows/release.yml exists and triggers on version tags (P0 item 5)."""
    workflow_path = Path(".github/workflows/release.yml")
    assert workflow_path.is_file()
    content = workflow_path.read_text(encoding="utf-8")
    assert "v*.*.*" in content
    assert "python -m build" in content
    assert "twine check" in content
    assert "ghcr.io" in content
    assert "pypa/gh-action-pypi-publish" in content


def test_llm_model_pinning_and_configuration(monkeypatch):
    """Verify Claude model string is pinned to supported alias and configurable via constructor or env (P0 item 6)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-token-xyz")
    monkeypatch.delenv("SENTINEL_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    # 1. Default pinned model
    provider = AnthropicLLMProvider()
    assert provider.model_name == DEFAULT_ANTHROPIC_MODEL
    assert "claude" in provider.model_name

    # 2. Constructor override
    custom_provider = AnthropicLLMProvider(model_name="claude-3-7-sonnet-latest")
    assert custom_provider.model_name == "claude-3-7-sonnet-latest"

    # 3. SENTINEL_LLM_MODEL env var override
    monkeypatch.setenv("SENTINEL_LLM_MODEL", "claude-3-opus-custom")
    env_provider = AnthropicLLMProvider()
    assert env_provider.model_name == "claude-3-opus-custom"

    # 4. ANTHROPIC_MODEL env var override
    monkeypatch.delenv("SENTINEL_LLM_MODEL", raising=False)
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-3-haiku-custom")
    env_provider_2 = AnthropicLLMProvider()
    assert env_provider_2.model_name == "claude-3-haiku-custom"

    # 5. get_llm_provider resolution
    resolved = get_llm_provider(provider_type="anthropic")
    assert resolved.model_name == "claude-3-haiku-custom"
