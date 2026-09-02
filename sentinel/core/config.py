"""Configuration models and loader for Sentinel.

Adheres to:
- rules.md R-SAFE-1 (Read-only by default)
- rules.md R-SAFE-2 (Production mutation guard)
- rules.md R-SAFE-4 (Resource limits)
- rules.md R-SAFE-5 (Network allow-listing)
- rules.md R-EXEC-4 (Environment tagging mandatory)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

EnvironmentType = Literal["local", "staging", "sandbox", "production"]


class TargetConfig(BaseModel):
    """Configuration defining the software target under test."""
    target_type: str = Field(..., description="Target adapter type, e.g. 'api', 'web', 'cli', 'stub'")
    name: str = Field(default="unnamed-target", description="Target identifier name")
    spec_path: str | None = Field(default=None, description="Path to OpenAPI spec, schema, or doc")
    base_url: str | None = Field(default=None, description="Base URL for network targets")
    allowed_hosts: list[str] = Field(
        default_factory=list,
        description="Explicit network host allowlist (R-SAFE-5)"
    )
    custom_options: dict[str, Any] = Field(default_factory=dict, description="Target-specific adapter options")


class EnvironmentConfig(BaseModel):
    """Environment-specific settings."""
    env_name: EnvironmentType = Field(..., description="Environment type (R-EXEC-4)")
    allow_mutations: bool = Field(default=False, description="Whether mutating operations are permitted (R-SAFE-1)")
    environment_ack: str | None = Field(
        default=None,
        description="Required literal 'I understand this targets production' for prod mutations (R-SAFE-2)"
    )
    secrets: dict[str, str] = Field(default_factory=dict, description="Environment variables or secrets mapping")
    base_url_override: str | None = Field(default=None, description="Optional override for target base URL")


class RunConfig(BaseModel):
    """Run-time execution configuration."""
    run_id: str = Field(..., description="Unique run identifier")
    project_id: str = Field(default="default", description="Project identifier")
    environment: EnvironmentType = Field(..., description="Target environment name (R-EXEC-4)")
    allow_mutations: bool = Field(default=False, description="Runtime mutation flag (R-SAFE-1)")
    prod_confirmed: bool = Field(default=False, description="Flag indicating production mutation confirmed (R-SAFE-2)")
    parallelism: int = Field(default=1, ge=1, le=64, description="Worker pool size")
    retry_budget: int = Field(default=2, ge=0, le=5, description="Max retries for flaky handling")
    timeout_seconds: float = Field(default=30.0, ge=0.1, le=600.0, description="Default wall-clock timeout")
    output_dir: Path = Field(default=Path("reports"), description="Directory to store reports and artifacts")
    quality_gate_min_pass_rate: float = Field(default=0.95, ge=0.0, le=1.0, description="Minimum pass rate threshold")
    fail_on_critical_defect: bool = Field(default=True, description="Fail CI if any Critical defect occurs (R-REPORT-1)")

    @model_validator(mode="after")
    def validate_production_safeguards(self) -> "RunConfig":
        """Enforce R-SAFE-2: production mutation triple opt-in."""
        if self.environment == "production" and self.allow_mutations:
            if not self.prod_confirmed:
                raise ValueError(
                    "Mutating actions on 'production' environment require explicit confirmation flag (R-SAFE-2)."
                )
        return self


class SentinelConfig(BaseModel):
    """Top-level sentinel.config.yaml specification."""
    project_id: str = Field(default="default")
    target: TargetConfig
    environments: dict[EnvironmentType, EnvironmentConfig] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, config_path: str | Path) -> "SentinelConfig":
        """Load and validate SentinelConfig from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        content = path.read_text(encoding="utf-8")
        raw_data = yaml.safe_load(content) or {}
        return cls.model_validate(raw_data)

    def create_run_config(
        self,
        env: EnvironmentType,
        run_id: str,
        allow_mutations: bool | None = None,
        prod_confirmed: bool = False,
        parallelism: int | None = None,
        timeout: float | None = None,
    ) -> RunConfig:
        """Create a validated RunConfig for a specific environment."""
        env_conf = self.environments.get(env)
        if allow_mutations is None:
            mutations_allowed = env_conf.allow_mutations if env_conf else False
        else:
            mutations_allowed = allow_mutations
            if env_conf and not env_conf.allow_mutations and allow_mutations:
                # If environment config strictly forbids mutations, disallow override
                mutations_allowed = False

        if env == "production" and mutations_allowed:
            if not (env_conf and env_conf.environment_ack == "I understand this targets production"):
                raise PermissionError(
                    "Production mutations require environment_ack: 'I understand this targets production' (R-SAFE-2)"
                )

        return RunConfig(
            run_id=run_id,
            project_id=self.project_id,
            environment=env,
            allow_mutations=mutations_allowed,
            prod_confirmed=prod_confirmed,
            parallelism=parallelism or self.defaults.get("parallelism", 1),
            timeout_seconds=timeout or self.defaults.get("timeout_seconds", 30.0),
        )
