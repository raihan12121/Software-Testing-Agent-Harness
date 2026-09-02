"""OpenAPI Spec Parser for APIAdapter.

Supports OpenAPI 3.0 and 3.1 (YAML and JSON).
Extracts paths, methods, parameters, request schemas, response schemas, and security.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from sentinel.core.schemas import TargetModel


class OpenAPIParser:
    """Parses OpenAPI specifications into a structured TargetModel."""

    def __init__(self, spec_data: dict[str, Any], base_url: str | None = None) -> None:
        self.spec = spec_data
        self.base_url = base_url or self._extract_base_url(spec_data)

    @classmethod
    def from_file(cls, file_path: str | Path, base_url: str | None = None) -> "OpenAPIParser":
        """Load parser from a YAML or JSON file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OpenAPI spec file not found: {path}")

        content = path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(content)
        except Exception:
            data = json.loads(content)

        return cls(data, base_url=base_url)

    def _extract_base_url(self, spec: dict[str, Any]) -> str:
        """Extract primary server URL if defined in spec."""
        servers = spec.get("servers", [])
        if servers and isinstance(servers, list) and len(servers) > 0:
            return servers[0].get("url", "http://localhost:8000")
        return "http://localhost:8000"

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        """Resolve internal $ref like #/components/schemas/Pet."""
        if not ref.startswith("#/"):
            return {}
        parts = ref.lstrip("#/").split("/")
        curr = self.spec
        for p in parts:
            if isinstance(curr, dict) and p in curr:
                curr = curr[p]
            else:
                return {}
        return curr if isinstance(curr, dict) else {}

    def _dereference_schema(self, schema: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        """Recursively resolve $ref references up to max depth."""
        if depth > 10 or not isinstance(schema, dict):
            return schema

        if "$ref" in schema:
            resolved = self._resolve_ref(schema["$ref"])
            return self._dereference_schema(resolved, depth + 1)

        result: dict[str, Any] = {}
        for k, v in schema.items():
            if isinstance(v, dict):
                result[k] = self._dereference_schema(v, depth + 1)
            elif isinstance(v, list):
                result[k] = [self._dereference_schema(item, depth + 1) if isinstance(item, dict) else item for item in v]
            else:
                result[k] = v
        return result

    def parse(self) -> TargetModel:
        """Parse OpenAPI specification into TargetModel."""
        info = self.spec.get("info", {})
        title = info.get("title", "OpenAPI Service")
        endpoints: list[dict[str, Any]] = []

        paths = self.spec.get("paths", {})
        for path_str, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method in ("get", "post", "put", "delete", "patch", "options", "head"):
                operation = path_item.get(method)
                if not operation or not isinstance(operation, dict):
                    continue

                operation_id = operation.get("operationId", f"{method}_{path_str}")
                summary = operation.get("summary", "")
                description = operation.get("description", "")
                tags = operation.get("tags", [])

                # Extract parameters
                params_list = operation.get("parameters", [])
                parsed_params: list[dict[str, Any]] = []
                for param in params_list:
                    if "$ref" in param:
                        param = self._resolve_ref(param["$ref"])
                    param_schema = self._dereference_schema(param.get("schema", {}))
                    parsed_params.append({
                        "name": param.get("name"),
                        "in": param.get("in"),  # query, path, header
                        "required": param.get("required", False),
                        "description": param.get("description", ""),
                        "schema": param_schema,
                    })

                # Extract request body
                request_body = operation.get("requestBody")
                req_schema = None
                req_required = False
                if request_body:
                    if "$ref" in request_body:
                        request_body = self._resolve_ref(request_body["$ref"])
                    req_required = request_body.get("required", False)
                    content = request_body.get("content", {})
                    json_media = content.get("application/json") or content.get("*/*")
                    if json_media and "schema" in json_media:
                        req_schema = self._dereference_schema(json_media["schema"])

                # Extract responses
                responses = operation.get("responses", {})
                parsed_responses: dict[str, Any] = {}
                for status_code, resp_obj in responses.items():
                    if "$ref" in resp_obj:
                        resp_obj = self._resolve_ref(resp_obj["$ref"])
                    resp_schema = None
                    content = resp_obj.get("content", {})
                    json_media = content.get("application/json")
                    if json_media and "schema" in json_media:
                        resp_schema = self._dereference_schema(json_media["schema"])
                    parsed_responses[str(status_code)] = {
                        "description": resp_obj.get("description", ""),
                        "schema": resp_schema,
                    }

                # Extract security
                security = operation.get("security", self.spec.get("security", []))

                endpoints.append({
                    "path": path_str,
                    "method": method.upper(),
                    "operation_id": operation_id,
                    "summary": summary,
                    "description": description,
                    "tags": tags,
                    "parameters": parsed_params,
                    "request_body_schema": req_schema,
                    "request_body_required": req_required,
                    "responses": parsed_responses,
                    "security": security,
                })

        return TargetModel(
            target_type="api",
            name=title,
            endpoints=endpoints,
            metadata={
                "version": info.get("version", "1.0.0"),
                "base_url": self.base_url,
                "endpoint_count": len(endpoints),
            },
        )
