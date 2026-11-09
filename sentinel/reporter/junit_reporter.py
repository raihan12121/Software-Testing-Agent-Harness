"""JUnit XML Reporter for Sentinel run results.

Adheres strictly to:
- PRD.md §6.6 (FR-17: JUnit XML export for CI/CD integration)
- TRD.md §2.5 (CI Integration)
- rules.md R-SEC-3 (Redaction before storage)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from sentinel.core.redaction import default_redactor
from sentinel.core.schemas import Report
from sentinel.reporter.base import Reporter, register_reporter


class JUnitReporter(Reporter):
    """Outputs standard JUnit XML reports for CI/CD runners (Jenkins, GitHub Actions, GitLab CI)."""

    def __init__(self, redactor=None) -> None:
        self.redactor = redactor or default_redactor

    def generate_report(self, report: Report, output_dir: Path) -> Path:
        """Format and write standard JUnit XML report file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        report_file = output_dir / f"junit_{report.run_id}.xml"

        duration_sec = f"{report.duration_ms / 1000.0:.3f}"
        total_tests = len(report.verdicts)

        testsuites = ET.Element("testsuites", {
            "name": "Sentinel Test Suite",
            "tests": str(total_tests),
            "failures": str(report.fail_count),
            "errors": str(report.error_count),
            "skipped": str(report.skipped_count),
            "time": duration_sec,
        })

        testsuite = ET.SubElement(testsuites, "testsuite", {
            "name": f"{report.project_id}.{report.target_type}",
            "tests": str(total_tests),
            "failures": str(report.fail_count),
            "errors": str(report.error_count),
            "skipped": str(report.skipped_count),
            "time": duration_sec,
            "timestamp": report.finished_at.isoformat() if report.finished_at else "",
        })

        for verdict in report.verdicts:
            testcase = ET.SubElement(testsuite, "testcase", {
                "name": verdict.test_id,
                "classname": f"sentinel.{report.target_type}.{report.environment}",
                "time": "0.000",
            })

            clean_reasoning = self.redactor.redact_text(verdict.reasoning or "")

            if verdict.status == "fail":
                failure = ET.SubElement(testcase, "failure", {
                    "message": clean_reasoning[:120] or "Test assertion failure",
                    "type": "AssertionError",
                })
                failure.text = clean_reasoning
            elif verdict.status == "error":
                error_elem = ET.SubElement(testcase, "error", {
                    "message": clean_reasoning[:120] or "Execution error",
                    "type": "ExecutionError",
                })
                error_elem.text = clean_reasoning
            elif verdict.status in ("skipped", "pending_review"):
                skipped = ET.SubElement(testcase, "skipped", {
                    "message": f"Verdict: {verdict.status} ({clean_reasoning[:80]})",
                })
                skipped.text = clean_reasoning

        rough_string = ET.tostring(testsuites, encoding="utf-8")
        parsed = minidom.parseString(rough_string)
        pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

        report_file.write_bytes(pretty_xml)
        return report_file


# Auto-register JUnit reporters
register_reporter("junit", JUnitReporter)
register_reporter("xml", JUnitReporter)
