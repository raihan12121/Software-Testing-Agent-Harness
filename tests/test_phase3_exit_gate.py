"""Phase 3 Exit Gate Verification Suite.

Adheres strictly to phases.md §Phase 3:
1. Risk-Based Testing: Consecutive runs show Planner deprioritizing defect-free areas
   and prioritizing historically risky / recently changed components.
2. Explore Mode: Autonomously discovers previously untested flows and synthesizes valid test cases.
3. Hard Safety: Explore mode strictly blocked from running on production (R-SAFE-3).
4. DatabaseAdapter: Transactional test isolation with rollback leaves zero persistent data (R-EXEC-1).
5. Auto-Filed Issues: Formats reproducible defect reports with exact steps (R-REPORT-1).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sentinel.adapters.api_adapter.adapter import APIAdapter
from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.adapters.db_adapter.adapter import DatabaseAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.schemas import ExpectedResult, Report, TestCase, TestStep, Verdict
from sentinel.defects.filer import DefectFiler
from sentinel.explorer.explorer import AutonomousExplorer, SecurityViolationError
from sentinel.memory.store import MemoryStore
from sentinel.planner.rule_based import RuleBasedPlanner


def test_phase3_exit_gate_end_to_end(tmp_path: Path):
    """End-to-end verification of all Phase 3 Exit Gate criteria."""
    mem_file = tmp_path / "phase3_exit_gate_memory.sqlite"
    store = MemoryStore(db_path=mem_file)

    # --- CRITERION 1: Risk-Based Prioritization on Consecutive Runs ---
    # First run identified failures in 'users' component; 'health' remained completely defect-free
    store.update_risk_index(
        project_id="pilot-proj",
        component="users",
        failure_count_30d=4,
        git_churn_score=0.9,
    )
    store.update_risk_index(
        project_id="pilot-proj",
        component="health",
        failure_count_30d=0,
        git_churn_score=0.0,
    )

    risk_map = store.get_risk_index("pilot-proj")
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    target_model = parser.parse()

    planner = RuleBasedPlanner()
    plan = planner.build_plan(target_model, memory_context={"risk_scores": risk_map})

    users_cases = [s for s in plan.scenarios if s.target_component == "users"]
    health_cases = [s for s in plan.scenarios if s.target_component == "health"]

    assert any(s.priority == "critical" for s in users_cases), "High-risk component 'users' was not elevated!"
    assert all(s.priority == "low" for s in health_cases), "Defect-free component 'health' was not deprioritized!"
    # Verify plan order places critical components first
    assert plan.scenarios[0].priority == "critical"

    # --- CRITERION 2: Explore Mode Discovery of Untested Flows ---
    api_target_config = TargetConfig(
        target_type="api",
        name="pilot-api",
        spec_path="examples/petstore_spec.yaml",
        base_url="http://127.0.0.1:8765",
    )
    run_config_staging = RunConfig(
        run_id="run-explore-p3",
        project_id="pilot-proj",
        environment="staging",
        allow_mutations=True,
    )
    explorer = AutonomousExplorer(api_target_config, run_config_staging)
    api_adapter = APIAdapter(api_target_config)
    discovered_tests = explorer.explore(api_adapter, max_steps=5)

    assert len(discovered_tests) >= 1, "Explore mode did not discover any flows!"
    assert all(isinstance(tc, TestCase) for tc in discovered_tests)
    assert all(tc.id.startswith("TC-EXPLORE-") for tc in discovered_tests)

    # --- CRITERION 3: Explore Mode Hard Production Protection (R-SAFE-3) ---
    run_config_prod = RunConfig(
        run_id="run-explore-prod",
        project_id="pilot-proj",
        environment="production",
        allow_mutations=False,
    )
    with pytest.raises(SecurityViolationError) as exc_info:
        AutonomousExplorer(api_target_config, run_config_prod)
    assert "R-SAFE-3" in str(exc_info.value)

    # --- CRITERION 4: DatabaseAdapter Transactional Rollback Isolation (R-EXEC-1) ---
    db_file = tmp_path / "target_database.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, sku TEXT, stock INTEGER);")
    conn.execute("INSERT INTO products (id, sku, stock) VALUES (1, 'PROD-A', 50);")
    conn.commit()
    conn.close()

    db_config = TargetConfig(target_type="database", name="prod-db", base_url=str(db_file))
    db_adapter = DatabaseAdapter(db_config)

    # Execute mutating test step
    mutate_step = TestStep(
        action="insert",
        body="INSERT INTO products (id, sku, stock) VALUES (999, 'MUTATED-SKU', 100);",
    )
    mutate_obs = db_adapter.execute_action(mutate_step)
    assert mutate_obs.error is None
    assert mutate_obs.raw_result["is_mutation"] is True

    # Assert that row was rolled back and does not persist
    check_step = TestStep(action="select", body="SELECT * FROM products WHERE id = 999;")
    check_obs = db_adapter.execute_action(check_step)
    assert len(check_obs.raw_result["rows"]) == 0, "Mutated row persisted in database (R-EXEC-1 violated)!"
    db_adapter.close()

    # --- CRITERION 5: Automated Defect Filing with Reproduction Steps (R-REPORT-1) ---
    filer = DefectFiler(memory_store=store)
    failing_test = TestCase(
        id="TC-GATE-FAIL-01",
        target_type="database",
        title="Check Stock Balance Integrity",
        steps=[TestStep(action="select", path="SELECT * FROM products WHERE stock < 0;")],
        expected=ExpectedResult(oracle="deterministic", assertions=["rows_affected == 0"]),
    )
    failing_verdict = Verdict(
        test_id="TC-GATE-FAIL-01",
        status="fail",
        oracle_used="deterministic",
        reasoning="Integrity violation: Negative stock balance detected in products table.",
        duration_ms=25,
    )
    gate_report = Report(
        run_id="run-gate-p3",
        project_id="pilot-proj",
        target_type="database",
        environment="staging",
        verdicts=[failing_verdict],
    )

    defect_result = filer.file_defect(failing_test, failing_verdict, gate_report)
    assert defect_result is not None
    assert "github_issue_url" in defect_result
    assert "Steps to Reproduce" in defect_result["body"]
    assert "SELECT * FROM products WHERE stock < 0;" in defect_result["body"]

    # Verify defect is recorded in memory store
    with store.connection() as c:
        row = c.execute("SELECT * FROM defects WHERE linked_test_ids LIKE '%TC-GATE-FAIL-01%'").fetchone()
        assert row is not None
        assert row["status"] == "filed"

    print("\nPhase 3 Exit Gate Successfully Verified!")
