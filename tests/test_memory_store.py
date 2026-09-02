"""Unit tests for SQLite MemoryStore."""

from sentinel.core.schemas import ExpectedResult, Report, TestCase, TestStep, Verdict
from sentinel.memory.store import MemoryStore


def test_memory_store_persist_and_retrieve():
    store = MemoryStore(db_path=":memory:")

    tc = TestCase(
        id="TC-MEM-01",
        target_type="api",
        title="Check User Auth with Secret",
        steps=[TestStep(action="http_request", path="/auth")],
        expected=ExpectedResult(oracle="deterministic"),
        source_context="spec.yaml#/auth",
    )

    verdict = Verdict(
        test_id="TC-MEM-01",
        status="flaky",
        oracle_used="deterministic",
        reasoning="Failed first attempt with token Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret123, passed retry.",
        retries=1,
        duration_ms=45,
    )

    report = Report(
        run_id="run-mem-001",
        project_id="test-proj",
        target_type="api",
        environment="staging",
        verdicts=[verdict],
        flaky_count=1,
    )

    store.persist_run(report, [tc])

    # Check flaky registry
    flaky_ids = store.get_flaky_test_ids()
    assert "TC-MEM-01" in flaky_ids

    # Check that secrets are redacted from SQLite storage (R-SEC-3)
    with store.connection() as conn:
        row = conn.execute("SELECT reasoning FROM verdicts WHERE test_id = 'TC-MEM-01'").fetchone()
        stored_reasoning = row["reasoning"]
        assert "secret123" not in stored_reasoning
        assert "[REDACTED:BEARER_TOKEN]" in stored_reasoning
