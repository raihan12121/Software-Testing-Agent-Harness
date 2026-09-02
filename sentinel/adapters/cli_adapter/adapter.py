"""CLI Adapter for testing command-line tools.

Adheres to:
- TRD.md §2.3 & §3.1 (TargetAdapter Protocol)
- rules.md R-EXEC-1 (Isolation via subprocesses)
- rules.md R-EXEC-3 (Timeouts mandatory)
- rules.md R-BUILD-1 (Adapters never talk to LLM)
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from typing import Any

from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


class CLIAdapter(TargetAdapter):
    """Adapter for executing and introspecting CLI utilities and binaries."""

    def __init__(self, target_config: TargetConfig | None = None) -> None:
        self.target_config = target_config

    def discover(self, config: TargetConfig) -> TargetModel:
        """Introspect CLI target by executing --help and extracting usage."""
        self.target_config = config
        binary = config.custom_options.get("binary") or config.name or "python"

        endpoints: list[dict[str, Any]] = []
        try:
            res = subprocess.run(
                [binary, "--help"],
                capture_output=True,
                text=True,
                timeout=5.0,
                check=False,
            )
            help_text = res.stdout or res.stderr
            endpoints.append({
                "path": "--help",
                "method": "EXEC",
                "summary": f"Introspected help for {binary}",
                "description": help_text[:500],
            })
        except Exception as exc:
            logger.warning(f"Failed to introspect CLI command '{binary} --help': {exc}")
            endpoints.append({
                "path": "exec",
                "method": "EXEC",
                "summary": f"Generic execution for {binary}",
            })

        return TargetModel(
            target_type="cli",
            name=config.name or binary,
            endpoints=endpoints,
            metadata={"binary": binary, "version_introspected": True},
        )

    def execute_action(self, action: TestStep) -> Observation:
        """Execute a CLI command in an isolated subprocess."""
        start_time = time.perf_counter()
        test_id = action.metadata.get("test_id", "TC-CLI")
        timeout = action.timeout_seconds or 10.0

        # Resolve command arguments
        cmd_input = action.path or action.params.get("cmd") or ""
        if isinstance(cmd_input, list):
            cmd_args = [str(x) for x in cmd_input]
        else:
            raw_args = (
                shlex.split(str(cmd_input), posix=(sys.platform != "win32"))
                if cmd_input
                else ["python", "-c", "print('ok')"]
            )
            cmd_args = []
            for a in raw_args:
                if len(a) >= 2 and ((a.startswith('"') and a.endswith('"')) or (a.startswith("'") and a.endswith("'"))):
                    cmd_args.append(a[1:-1])
                else:
                    cmd_args.append(a)

        # If a binary is configured and not prefixed, prepend it
        configured_binary = (
            self.target_config.custom_options.get("binary")
            if self.target_config
            else None
        )
        if configured_binary and cmd_args and cmd_args[0] != configured_binary:
            cmd_args = [configured_binary] + cmd_args

        # Stdin payload
        stdin_data = None
        if action.body is not None:
            stdin_data = str(action.body)

        cwd = action.metadata.get("cwd") or (
            self.target_config.custom_options.get("cwd") if self.target_config else None
        )

        try:
            res = subprocess.run(
                cmd_args,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                check=False,
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            raw_result = {
                "exit_code": res.returncode,
                "status_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "command": " ".join(cmd_args),
                "duration_ms": elapsed_ms,
            }

            artifacts: list[Artifact] = []
            if res.returncode != 0 or action.metadata.get("capture_artifacts", False):
                artifact_path = f"artifacts/{test_id}_cli_output.log"
                artifacts.append(
                    Artifact(
                        path=artifact_path,
                        mime_type="text/plain",
                        description=f"CLI output for: {' '.join(cmd_args)}",
                        metadata={"exit_code": res.returncode},
                    )
                )

            return Observation(
                test_id=test_id,
                raw_result=raw_result,
                artifacts=artifacts,
                duration_ms=elapsed_ms,
                error=None,
            )

        except subprocess.TimeoutExpired:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=test_id,
                raw_result={"command": " ".join(cmd_args), "exit_code": -1},
                duration_ms=elapsed_ms,
                error=f"TIMEOUT: Command exceeded limit of {timeout}s (R-SAFE-4 / R-EXEC-3).",
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=test_id,
                raw_result={"command": " ".join(cmd_args), "exit_code": -1},
                duration_ms=elapsed_ms,
                error=f"CLI_EXECUTION_EXCEPTION: {exc}",
            )

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return captured artifacts."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Reset state between CLI runs (process boundary provides natural isolation)."""
        pass


# Register CLI adapter
register_adapter("cli", CLIAdapter)
