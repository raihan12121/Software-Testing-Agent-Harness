"""Unit tests for Human Review Queue and Resolution Trail (R-ORACLE-2, R-ORACLE-5)."""

from sentinel.core.schemas import ExpectedResult, Report, TestCase, TestStep, Verdict
from sentinel.memory.store import MemoryStore


def test_review_queue_persistence_and_resolution():
    store = MemoryStore(db_path=":memory:")

    tc = TestCase(
        id="TC-REV-01",
        target_type="web",
        title="Check dashboard layout",
        steps=[TestStep(action="navigate", path="/dashboard")],
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Check layout clarity"),
    )

    verdict = Verdict(
        test_id="TC-REV-01",
        status="pending_review",
        oracle_used="llm_judge",
        confidence=0.65,
        reasoning="Layout is readable but font contrast is borderline.",
        duration_ms=50,
    )

    report = Report(
        run_id="run-rev-01",
        project_id="review-proj",
        target_type="web",
        environment="staging",
        verdicts=[verdict],
    )

    store.persist_run(report, [tc])

    # 1. Verify it shows up in get_pending_reviews
    pending = store.get_pending_reviews("run-rev-01")
    assert len(pending) == 1
    assert pending[0]["test_id"] == "TC-REV-01"
    assert pending[0]["confidence"] == 0.65

    # 2. Resolve the verdict
    store.record_human_resolution(
        test_id="TC-REV-01",
        run_id="run-rev-01",
        original_status="pending_review",
        resolved_status="pass",
        resolved_by="lead_qa",
        rationale="Contrast verified with accessibility tool; approved.",
    )

    # 3. Verify verdict table updated and audit trail recorded (R-ORACLE-5)
    with store.connection() as conn:
        v_row = conn.execute(
            "SELECT status FROM verdicts WHERE test_id = 'TC-REV-01'"
        ).fetchone()
        assert v_row["status"] == "pass"

        res_row = conn.execute(
            "SELECT * FROM human_review_resolutions WHERE test_id = 'TC-REV-01'"
        ).fetchone()
        assert res_row is not None
        assert res_row["resolved_status"] == "pass"
        assert res_row["resolved_by"] == "lead_qa"
        assert "Contrast verified" in res_row["rationale"]

    # 4. Pending queue should now be empty
    pending_after = store.get_pending_reviews("run-rev-01")
    assert len(pending_after) == 0
