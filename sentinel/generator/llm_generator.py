"""Test Generator for converting Scenarios to concrete executable TestCases.

Adheres to:
- TRD.md §3.2 (TestCase schema)
- rules.md R-GEN-1 (Grounded generation)
- rules.md R-GEN-2 (Schema validation & repair-retry loop)
- rules.md R-GEN-3 (Provenance tracking)
- rules.md R-GEN-4 (Deduplication)
"""

from __future__ import annotations

from typing import Any

from sentinel.core.schemas import TargetModel, TestCase, TestStep
from sentinel.generator.base import Generator
from sentinel.generator.dedup import TestDeduplicator
from sentinel.generator.validator import GenerationValidator
from sentinel.llm.provider import LLMProvider, get_llm_provider
from sentinel.planner.base import Scenario, TestPlan


class APITestGenerator(Generator):
    """Generates concrete API TestCases from planned scenarios and TargetModel."""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or get_llm_provider()
        self.validator = GenerationValidator()
        self.dedup = TestDeduplicator()

    def generate(self, plan: TestPlan, target_model: TargetModel) -> list[TestCase]:
        """Convert planned scenarios into concrete, validated TestCase objects."""
        test_cases: list[TestCase] = []
        endpoints_by_path: dict[str, dict[str, Any]] = {}
        for ep in target_model.endpoints:
            key = f"{ep.get('method', 'GET').upper()}:{ep.get('path', '/')}"
            endpoints_by_path[key] = ep

        for scenario in plan.scenarios:
            tc = self._generate_case_for_scenario(scenario, target_model, endpoints_by_path)
            if tc:
                test_cases.append(tc)

        base_url = target_model.metadata.get("base_url")
        if base_url:
            for tc in test_cases:
                for step in tc.steps:
                    if "base_url" not in step.metadata:
                        step.metadata["base_url"] = base_url

        # R-GEN-4: Deduplicate and merge near-identical cases
        return self.dedup.cluster_and_merge(test_cases)

    def _generate_case_for_scenario(
        self,
        scenario: Scenario,
        target_model: TargetModel,
        endpoints_map: dict[str, dict[str, Any]],
    ) -> TestCase | None:
        """Create and validate a single TestCase for a scenario."""
        # Find matching endpoint
        matched_ep = None
        for key, ep in endpoints_map.items():
            method, path = key.split(":", 1)
            if path in scenario.title or path in scenario.description:
                if method in scenario.title or method in scenario.description or method.lower() in scenario.tags:
                    matched_ep = ep
                    break

        if not matched_ep and target_model.endpoints:
            # Fallback to first endpoint if none explicitly matched
            matched_ep = target_model.endpoints[0]

        if not matched_ep:
            return None

        # Handle CLI target type
        if target_model.target_type == "cli":
            cmd = f"{target_model.name} --help" if "help" in scenario.tags or "Happy" in scenario.title else f"{target_model.name} --version"
            step = TestStep(action="cli_exec", path=cmd, timeout_seconds=10.0)
            raw_case = {
                "id": f"TC-{scenario.id}",
                "target_type": "cli",
                "title": scenario.title,
                "priority": scenario.priority,
                "tags": scenario.tags,
                "steps": [step.model_dump()],
                "expected": {"oracle": "deterministic", "assertions": ["status_code == 0", "exit_code == 0"]},
                "mutating": False,
                "generated_by": "CLITestGenerator_v1",
                "source_context": f"cli://{target_model.name}",
            }
            return TestCase.model_validate(raw_case)

        # Handle Database target type
        if target_model.target_type in ("db", "database"):
            ep_path = matched_ep.get("path", "table://items")
            tbl = ep_path.split("//")[-1] if "//" in ep_path else "items"
            step = TestStep(action="query", path=f"SELECT count(*) FROM {tbl};", timeout_seconds=10.0)
            raw_case = {
                "id": f"TC-{scenario.id}",
                "target_type": "database",
                "title": scenario.title,
                "priority": scenario.priority,
                "tags": scenario.tags,
                "steps": [step.model_dump()],
                "expected": {"oracle": "deterministic", "assertions": ["status_code == 200"]},
                "mutating": False,
                "generated_by": "DBTestGenerator_v1",
                "source_context": f"db://{tbl}",
            }
            return TestCase.model_validate(raw_case)

        method = matched_ep.get("method", "GET").upper()
        path = matched_ep.get("path", "/")
        req_schema = matched_ep.get("request_body_schema")
        params = matched_ep.get("parameters", [])

        # Build request parameters and body based on scenario tags
        resolved_params: dict[str, Any] = {}
        headers: dict[str, str] = {"Content-Type": "application/json"}
        body: Any = None
        assertions: list[str] = []

        is_mutating = method in ("POST", "PUT", "PATCH", "DELETE")

        # 1. Path & Query parameters
        for p in params:
            p_name = p.get("name")
            p_type = p.get("schema", {}).get("type", "string")

            if "not_found" in scenario.tags:
                resolved_params[p_name] = 999999 if p_type in ("integer", "number") else "nonexistent-id-999"
            elif "invalid_type" in scenario.tags and p_name in scenario.title:
                resolved_params[p_name] = "invalid_string_class"
            elif "bva" in scenario.tags and p_name in scenario.title:
                resolved_params[p_name] = 0 if p_type in ("integer", "number") else ""
            else:
                resolved_params[p_name] = 1 if p_type in ("integer", "number") else "default-id"

        # 2. Body generation
        if req_schema and isinstance(req_schema, dict):
            body_dict: dict[str, Any] = {}
            props = req_schema.get("properties", {})
            for k, prop_spec in props.items():
                p_type = prop_spec.get("type", "string")
                if "negative" in scenario.tags and f"'{k}'" in scenario.title:
                    # Omit required field
                    continue
                if "bva" in scenario.tags and f"'{k}'" in scenario.title:
                    body_dict[k] = "" if p_type == "string" else 0
                elif p_type in ("integer", "number"):
                    body_dict[k] = 10
                elif p_type == "boolean":
                    body_dict[k] = True
                elif p_type == "array":
                    body_dict[k] = []
                else:
                    body_dict[k] = f"sample_{k}"
            body = body_dict

        # 3. Auth headers
        if "auth" in scenario.tags:
            if "reject request without credentials" in scenario.title.lower():
                # Omit Authorization header
                pass
            else:
                # Malformed/invalid token
                headers["Authorization"] = "Bearer invalid_expired_signature_token"

        # 4. Assertions formulation
        if "auth" in scenario.tags:
            assertions = ["status_code in [401, 403]"]
        elif "negative" in scenario.tags:
            assertions = ["status_code in [400, 422]"]
        elif "not_found" in scenario.tags:
            assertions = ["status_code == 404"]
        elif "invalid_type" in scenario.tags:
            assertions = ["status_code in [400, 404, 422]"]
        elif "crud_checklist" in scenario.tags:
            assertions = ["status_code in [200, 201, 204]"]
        else:
            # Happy path
            expected_code = "200" if "200" in matched_ep.get("responses", {}) else "201"
            assertions = [f"status_code in [{expected_code}, 200, 204]"]
            if matched_ep.get("responses", {}).get(expected_code, {}).get("schema"):
                assertions.append("schema_valid == True")
        step_metadata: dict[str, Any] = {
            "scenario_id": scenario.id,
            "expected_response_schema": matched_ep.get("responses", {}).get("200", {}).get("schema"),
        }
        if target_model.metadata.get("base_url"):
            step_metadata["base_url"] = target_model.metadata["base_url"]

        step = TestStep(
            action="http_request",
            method=method,
            path=path,
            headers=headers,
            params=resolved_params,
            body=body,
            timeout_seconds=10.0,
            metadata=step_metadata,
        )

        raw_case = {
            "id": f"TC-{scenario.id}",
            "target_type": "api",
            "title": scenario.title,
            "priority": scenario.priority,
            "tags": scenario.tags,
            "steps": [step.model_dump()],
            "expected": {
                "oracle": "deterministic",
                "assertions": assertions,
            },
            "mutating": is_mutating,
            "generated_by": "APITestGenerator_v1",
            "source_context": f"openapi.yaml#{path}#{method}",
        }

        # R-GEN-2: Validate via GenerationValidator with repair retry loop
        return self.validator.validate_and_repair(raw_case)
