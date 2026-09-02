"""JSON Reporter for Sentinel run results.

Adheres to:
- TRD.md §2.4 & §3.3
- PRD.md §6.6 (FR-17)
- rules.md R-SEC-3 (Redaction before storage)
"""

from __future__ import annotations

import json
from pathlib import Path

from sentinel.core.redaction import default_redactor
from sentinel.core.schemas import Report
from sentinel.reporter.base import Reporter, register_reporter


class JSONReporter(Reporter):
    """Outputs machine-readable JSON reports."""

    def __init__(self, redactor=None) -> None:
        self.redactor = redactor or default_redactor

    def generate_report(self, report: Report, output_dir: Path) -> Path:
        """Write sanitized JSON report file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        report_file = output_dir / f"report_{report.run_id}.json"

        raw_dict = report.model_dump(mode="json")
        clean_dict = self.redactor.redact(raw_dict)

        report_file.write_text(json.dumps(clean_dict, indent=2), encoding="utf-8")
        return report_file


# Register default json reporter
register_reporter("json", JSONReporter)
