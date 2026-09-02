"""Unit tests for the RuleBasedPlanner."""

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.planner.rule_based import RuleBasedPlanner


def test_rule_based_planner_generates_comprehensive_suite():
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    target_model = parser.parse()

    planner = RuleBasedPlanner()
    plan = planner.build_plan(target_model)

    # Acceptance criteria: >= 20 scenarios
    assert len(plan.scenarios) >= 20

    tags_found = set()
    for s in plan.scenarios:
        assert s.id.startswith("SC-")
        assert len(s.title) > 5
        assert s.priority in ("low", "medium", "high", "critical")
        for t in s.tags:
            tags_found.add(t)

    # Verify key heuristic categories exist
    assert "happy_path" in tags_found
    assert "bva" in tags_found
    assert "ep" in tags_found
    assert "auth" in tags_found
    assert "negative" in tags_found
    assert "crud_checklist" in tags_found
