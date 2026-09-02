"""Unit tests for HTMLReporter."""

from pathlib import Path

from sentinel.core.schemas import AssertionResult, Report, Verdict
from sentinel.reporter.html_reporter import HTMLReporter


def test_html_reporter_generates_dashboard(tmp_path: Path):
    reporter = HTMLReporter()

    verdict = Verdict(
        test_id="TC-HTML-1",
        status="pass",
        oracle_used="deterministic",
        reasoning="Status code 200 with Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.leakedtoken",
        assertions_result=[
            AssertionResult(assertion="status_code == 200", actual=200, passed=True)
        ],
        duration_ms=12,
    )

    report = Report(
        run_id="run-html-99",
        project_id="html-proj",
        target_type="api",
        environment="staging",
        verdicts=[verdict],
        pass_count=1,
        duration_ms=12,
    )

    out_file = reporter.generate_report(report, tmp_path)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")

    assert "Sentinel SQA Run Report" in content
    assert "run-html-99" in content
    assert "TC-HTML-1" in content
    assert "Quality Gate Passed" in content
    # Verify secrets redaction in HTML output (R-SEC-3)
    assert "leakedtoken" not in content
    assert "[REDACTED:BEARER_TOKEN]" in content
