"""Unit tests for DefectFiler and R-REPORT-1 reproducible bug reports."""

from sentinel.core.schemas import ExpectedResult, Report, TestCase, TestStep, Verdict
from sentinel.defects.filer import DefectFiler
from sentinel.memory.store import MemoryStore


def test_defect_filer_repro_steps_and_deduplication():
    store = MemoryStore(db_path=":memory:")
    filer = DefectFiler(memory_store=store)

    tc = TestCase(
        id="TC-BUG-001",
        target_type="api",
        title="Check User Creation Validation",
        steps=[
            TestStep(action="http_request", method="POST", path="/users", body='{"name": "Alice"}')
        ],
        expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 201"]),
    )

    verdict = Verdict(
        test_id="TC-BUG-001",
        status="fail",
        oracle_used="deterministic",
        reasoning="Expected status_code 201, got 500 Internal Server Error",
        duration_ms=120,
    )

    report = Report(
        run_id="run-filer-1",
        project_id="test-proj",
        target_type="api",
        environment="staging",
        verdicts=[verdict],
    )

    # 1. Format defect body and verify R-REPORT-1 components
    body = filer.format_defect_body(tc, verdict, report)
    assert "Steps to Reproduce" in body
    assert "Execute `http_request` on `/users`" in body
    assert "Expected Assertions" in body
    assert "500 Internal Server Error" in body
    assert "staging" in body

    # 2. File the defect
    defect_info = filer.file_defect(tc, verdict, report)
    assert defect_info is not None
    assert "github_issue_url" in defect_info
    assert defect_info["fingerprint"] is not None

    # 3. Test Deduplication: Calling file_defect again on same failure skips duplicate
    duplicate_info = filer.file_defect(tc, verdict, report)
    assert duplicate_info is not None
    assert duplicate_info["id"] == defect_info["id"]
