"""REST and HTTP API Adapter for Sentinel.

Adheres to:
- TRD.md §2.3 & §3.1 (TargetAdapter interface)
- rules.md R-SAFE-5 (Network allow-listing)
- rules.md R-EXEC-3 (Timeouts mandatory)
- rules.md R-BUILD-1 (Adapters never talk to LLM)
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.adapters.base import TargetAdapter, register_adapter
from sentinel.core.config import TargetConfig
from sentinel.core.logging import logger
from sentinel.core.schemas import Artifact, Observation, TargetModel, TestStep


class APIAdapter(TargetAdapter):
    """Adapter for testing REST/HTTP APIs with OpenAPI introspection and HTTP execution."""

    def __init__(self, target_config: TargetConfig | None = None) -> None:
        self.target_config = target_config
        self.client = httpx.Client(follow_redirects=True)

    def discover(self, config: TargetConfig) -> TargetModel:
        """Parse OpenAPI specification and return TargetModel."""
        self.target_config = config

        if not config.spec_path:
            # Fallback if only base_url is known
            return TargetModel(
                target_type="api",
                name=config.name or "REST Service",
                endpoints=[],
                metadata={"base_url": config.base_url or "http://localhost:8000"},
            )

        parser = OpenAPIParser.from_file(config.spec_path, base_url=config.base_url)
        return parser.parse()

    def execute_action(self, action: TestStep) -> Observation:
        """Perform an HTTP request and capture structured observation."""
        start_time = time.perf_counter()
        test_id = action.metadata.get("test_id", "TC-API")

        base_url = (
            (self.target_config.base_url if self.target_config else None)
            or action.metadata.get("base_url")
            or "http://localhost:8000"
        )
        base_url = base_url.rstrip("/")

        # 1. Build and resolve URL path parameters
        raw_path = action.path or "/"
        if not raw_path.startswith("/"):
            raw_path = "/" + raw_path

        url = f"{base_url}{raw_path}"

        # Resolve path parameters {id} from action.params
        query_params: dict[str, Any] = {}
        for k, v in action.params.items():
            placeholder = f"{{{k}}}"
            if placeholder in url:
                url = url.replace(placeholder, str(v))
            else:
                query_params[k] = v

        # 2. R-SAFE-5: Network allow-listing check
        parsed_url = urlparse(url)
        host = parsed_url.hostname or ""

        allowed_hosts = self.target_config.allowed_hosts if self.target_config else []
        if allowed_hosts:
            is_allowed = (
                host in allowed_hosts
                or (host in ("localhost", "127.0.0.1", "::1") and any(h in ("localhost", "127.0.0.1") for h in allowed_hosts))
            )
            if not is_allowed:
                logger.warning(f"BLOCKED: Attempted to contact unlisted host '{host}' (R-SAFE-5).")
                return Observation(
                    test_id=test_id,
                    raw_result={"url": url, "host": host},
                    duration_ms=0,
                    error=f"SECURITY_BLOCK: Host '{host}' is not in configured allowlist {allowed_hosts} (R-SAFE-5).",
                )

        # 3. Prepare request options
        method = (action.method or "GET").upper()
        headers = dict(action.headers)
        timeout = action.timeout_seconds or 10.0

        req_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
            "params": query_params if query_params else None,
            "timeout": timeout,
        }

        if action.body is not None:
            if isinstance(action.body, (dict, list)):
                req_kwargs["json"] = action.body
            else:
                req_kwargs["content"] = str(action.body).encode("utf-8")

        # 4. Execute HTTP request
        try:
            resp = self.client.request(**req_kwargs)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # Extract response body (parse JSON if possible)
            try:
                body_content = resp.json()
            except Exception:
                body_content = resp.text

            raw_result = {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": body_content,
                "url": str(resp.url),
                "method": method,
                "duration_ms": elapsed_ms,
            }

            # 5. Capture artifacts if payload is large or explicitly requested
            artifacts: list[Artifact] = []
            if action.metadata.get("capture_artifacts", False) or resp.status_code >= 400:
                artifact_path = f"artifacts/{test_id}_response.json"
                artifacts.append(
                    Artifact(
                        path=artifact_path,
                        mime_type="application/json",
                        description=f"HTTP {resp.status_code} response for {method} {raw_path}",
                        metadata={"status_code": resp.status_code, "url": str(resp.url)},
                    )
                )

            return Observation(
                test_id=test_id,
                raw_result=raw_result,
                artifacts=artifacts,
                duration_ms=elapsed_ms,
                error=None,
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=test_id,
                raw_result={"url": url, "method": method},
                duration_ms=elapsed_ms,
                error=f"TIMEOUT: HTTP request timed out after {timeout}s (R-SAFE-4 / R-EXEC-3).",
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return Observation(
                test_id=test_id,
                raw_result={"url": url, "method": method},
                duration_ms=elapsed_ms,
                error=f"HTTP_REQUEST_FAILED: {exc}",
            )

    def capture_artifacts(self, observation: Observation) -> list[Artifact]:
        """Return captured artifacts."""
        return list(observation.artifacts)

    def reset_state(self, config: TargetConfig) -> None:
        """Perform state reset if a reset endpoint is configured."""
        reset_url = config.custom_options.get("reset_url")
        if reset_url:
            try:
                self.client.post(reset_url, timeout=5.0)
            except Exception as exc:
                logger.warning(f"Reset endpoint call failed: {exc}")


# Auto-register API adapter
register_adapter("api", APIAdapter)
