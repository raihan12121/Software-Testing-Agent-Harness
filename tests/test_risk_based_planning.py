"""Unit tests for Risk-Based Testing and Planner Prioritization."""

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.memory.store import MemoryStore
from sentinel.planner.rule_based import RuleBasedPlanner


def test_risk_based_planning_prioritization():
    store = MemoryStore(db_path=":memory:")

    # Seed risk index: 'orders' is high-risk (recent failures + churn), 'health' is zero-risk
    store.update_risk_index(
        project_id="test-proj",
        component="orders",
        failure_count_30d=5,
        git_churn_score=0.8,
    )
    store.update_risk_index(
        project_id="test-proj",
        component="health",
        failure_count_30d=0,
        git_churn_score=0.0,
    )

    risk_scores = store.get_risk_index("test-proj")
    assert risk_scores["orders"] >= 0.8
    assert risk_scores["health"] == 0.0

    # Build plan using OpenAPI spec
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    target_model = parser.parse()

    planner = RuleBasedPlanner()
    plan = planner.build_plan(target_model, memory_context={"risk_scores": risk_scores})

    # Verify orders happy path is critical
    orders_scenarios = [s for s in plan.scenarios if s.target_component == "orders" and "happy_path" in s.tags]
    health_scenarios = [s for s in plan.scenarios if s.target_component == "health" and "happy_path" in s.tags]

    assert len(orders_scenarios) > 0
    assert len(health_scenarios) > 0
    assert orders_scenarios[0].priority == "critical"
    assert health_scenarios[0].priority == "low"

    # Verify critical scenarios appear before low priority scenarios (sorting check)
    critical_indices = [i for i, s in enumerate(plan.scenarios) if s.priority == "critical"]
    low_indices = [i for i, s in enumerate(plan.scenarios) if s.priority == "low"]
    assert min(critical_indices) < min(low_indices)
