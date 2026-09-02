"""Rule-based Test Planner.

Adheres to:
- phases.md §Phase 1 (Equivalence partitioning, boundary value analysis, CRUD, auth)
- TRD.md §9 (Generates >=20 test scenarios from spec without human editing)
- rules.md R-GEN-1 (Grounded generation from actual spec)
"""

from __future__ import annotations

from typing import Any

from sentinel.core.schemas import TargetModel
from sentinel.planner.base import Planner, Scenario, TestPlan


class RuleBasedPlanner(Planner):
    """Generates test scenarios using deterministic testing heuristics."""

    def build_plan(self, target_model: TargetModel, memory_context: dict[str, Any] | None = None) -> TestPlan:
        """Analyze TargetModel endpoints and construct comprehensive test scenarios."""
        scenarios: list[Scenario] = []
        scenario_idx = 1

        for ep in target_model.endpoints:
            path = ep.get("path", "/")
            method = ep.get("method", "GET").upper()
            summary = ep.get("summary", f"{method} {path}")
            params = ep.get("parameters", [])
            req_schema = ep.get("request_body_schema")
            responses = ep.get("responses", {})
            security = ep.get("security", [])

            component = path.strip("/").split("/")[0] if path.strip("/") else "root"

            # 1. Happy Path Scenario
            expected_status = "200" if "200" in responses else ("201" if "201" in responses else "204")
            scenarios.append(
                Scenario(
                    id=f"SC-{scenario_idx:04d}",
                    title=f"Happy Path: {method} {path}",
                    description=f"Send valid conforming request to {summary} and expect success ({expected_status}).",
                    target_component=component,
                    priority="high",
                    tags=["happy_path", "smoke", method.lower()],
                )
            )
            scenario_idx += 1

            # 2. Boundary Value Analysis (BVA) Scenarios
            if req_schema and isinstance(req_schema, dict):
                props = req_schema.get("properties", {})
                for prop_name, prop_spec in props.items():
                    prop_type = prop_spec.get("type", "string")
                    if prop_type in ("integer", "number"):
                        scenarios.append(
                            Scenario(
                                id=f"SC-{scenario_idx:04d}",
                                title=f"BVA: Extreme values for '{prop_name}' on {method} {path}",
                                description=f"Test boundary values (0, negative, max int) for property '{prop_name}'.",
                                target_component=component,
                                priority="medium",
                                tags=["bva", "boundary", method.lower()],
                            )
                        )
                        scenario_idx += 1
                    elif prop_type == "string":
                        scenarios.append(
                            Scenario(
                                id=f"SC-{scenario_idx:04d}",
                                title=f"BVA: Empty and boundary string for '{prop_name}' on {method} {path}",
                                description=f"Test empty string and max length for property '{prop_name}'.",
                                target_component=component,
                                priority="medium",
                                tags=["bva", "boundary", method.lower()],
                            )
                        )
                        scenario_idx += 1

            # Path param BVA
            for p in params:
                if p.get("in") == "path":
                    p_name = p.get("name")
                    scenarios.append(
                        Scenario(
                            id=f"SC-{scenario_idx:04d}",
                            title=f"BVA: Boundary value for path param '{p_name}' on {method} {path}",
                            description=f"Test boundary/zero values for path parameter '{p_name}'.",
                            target_component=component,
                            priority="medium",
                            tags=["bva", "path_param"],
                        )
                    )
                    scenario_idx += 1

            # 3. Equivalence Partitioning (EP) - Invalid input classes
            if params:
                for p in params:
                    p_name = p.get("name")
                    p_in = p.get("in")
                    scenarios.append(
                        Scenario(
                            id=f"SC-{scenario_idx:04d}",
                            title=f"EP: Invalid type partition for {p_in} param '{p_name}' on {method} {path}",
                            description="Provide invalid type partition (e.g. non-numeric string for ID) and expect client error (400/404).",
                            target_component=component,
                            priority="medium",
                            tags=["ep", "invalid_type", method.lower()],
                        )
                    )
                    scenario_idx += 1

            if "{" in path and "}" in path:
                # Non-existent resource ID
                scenarios.append(
                    Scenario(
                        id=f"SC-{scenario_idx:04d}",
                        title=f"EP: Non-existent resource target on {method} {path}",
                        description="Query with valid syntax but non-existent resource ID (expect 404).",
                        target_component=component,
                        priority="medium",
                        tags=["ep", "negative", "not_found"],
                    )
                )
                scenario_idx += 1

            # 4. Missing Required Fields (Negative Path)
            if req_schema and isinstance(req_schema, dict):
                required_props = req_schema.get("required", [])
                for req_field in required_props:
                    scenarios.append(
                        Scenario(
                            id=f"SC-{scenario_idx:04d}",
                            title=f"Negative: Omit required field '{req_field}' on {method} {path}",
                            description=f"Omit required field '{req_field}' from request body and expect 400 or 422.",
                            target_component=component,
                            priority="high",
                            tags=["negative", "validation", method.lower()],
                        )
                    )
                    scenario_idx += 1

            # 5. Auth / Permission Checklist
            if security or ("auth" in path.lower()) or ("token" in str(params).lower()):
                scenarios.append(
                    Scenario(
                        id=f"SC-{scenario_idx:04d}",
                        title=f"Auth: Reject request without credentials on {method} {path}",
                        description=f"Send request to protected {method} {path} omitting auth credentials, expect 401.",
                        target_component=component,
                        priority="critical",
                        tags=["auth", "security"],
                    )
                )
                scenario_idx += 1
                scenarios.append(
                    Scenario(
                        id=f"SC-{scenario_idx:04d}",
                        title=f"Auth: Reject invalid or expired token on {method} {path}",
                        description=f"Send request with malformed or invalid Bearer token to {method} {path}, expect 401 or 403.",
                        target_component=component,
                        priority="critical",
                        tags=["auth", "security"],
                    )
                )
                scenario_idx += 1

        # 6. CRUD Coverage Checklist
        # Group paths and check for missing standard CRUD verbs
        resources: dict[str, set[str]] = {}
        for ep in target_model.endpoints:
            p = ep.get("path", "/")
            res_key = p.split("/")[1] if len(p.split("/")) > 1 else p
            res_key = res_key.split("{")[0].strip("/")
            if res_key:
                resources.setdefault(res_key, set()).add(ep.get("method", "GET").upper())

        for res, methods in resources.items():
            scenarios.append(
                Scenario(
                    id=f"SC-{scenario_idx:04d}",
                    title=f"CRUD Coverage Check: Resource '{res}'",
                    description=f"Verify coverage of CRUD operations for '{res}'. Implemented methods: {sorted(list(methods))}.",
                    target_component=res,
                    priority="low",
                    tags=["crud_checklist", "coverage"],
                )
            )
            scenario_idx += 1

        return TestPlan(
            project_id=target_model.name or "api-project",
            target_type="api",
            scenarios=scenarios,
        )
