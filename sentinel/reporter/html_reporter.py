"""HTML Reporter for Sentinel run dashboards.

Adheres to:
- PRD.md §6.6 (FR-17: Human-readable HTML report)
- rules.md R-SEC-3 (Redaction before storage)
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from sentinel.core.redaction import default_redactor
from sentinel.core.schemas import Report
from sentinel.reporter.base import Reporter, register_reporter

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sentinel Report — {{ report.run_id }}</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --border: #334155;
      --pass: #10b981;
      --fail: #ef4444;
      --flaky: #f59e0b;
      --error: #dc2626;
      --primary: #3b82f6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      padding: 2rem;
      line-height: 1.5;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 2rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border);
    }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.875rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .badge-pass { background: rgba(16, 185, 129, 0.2); color: var(--pass); border: 1px solid var(--pass); }
    .badge-fail { background: rgba(239, 68, 68, 0.2); color: var(--fail); border: 1px solid var(--fail); }
    .badge-flaky { background: rgba(245, 158, 11, 0.2); color: var(--flaky); border: 1px solid var(--flaky); }
    .badge-error { background: rgba(220, 38, 38, 0.2); color: var(--error); border: 1px solid var(--error); }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      padding: 1.25rem;
    }
    .card h3 { font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; }
    .card .value { font-size: 2rem; font-weight: 700; margin-top: 0.5rem; }

    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--card-bg);
      border-radius: 0.5rem;
      overflow: hidden;
      border: 1px solid var(--border);
    }
    th, td {
      padding: 0.875rem 1rem;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th { background: #182234; color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
    tr:hover { background: rgba(255, 255, 255, 0.02); }
    .assertions-list {
      margin-top: 0.5rem;
      font-size: 0.8rem;
      font-family: monospace;
      color: var(--text-muted);
    }
    .assert-item { margin-bottom: 0.25rem; }
    .assert-passed { color: var(--pass); }
    .assert-failed { color: var(--fail); }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Sentinel SQA Run Report</h1>
      <p style="color: var(--text-muted);">Run ID: {{ report.run_id }} &bull; Env: {{ report.environment }} &bull; Target: {{ report.target_type }}</p>
    </div>
    <div>
      {% if report.fail_count == 0 and report.error_count == 0 %}
      <span class="badge badge-pass">Quality Gate Passed</span>
      {% else %}
      <span class="badge badge-fail">Quality Gate Failed</span>
      {% endif %}
    </div>
  </div>

  <div class="stats-grid">
    <div class="card">
      <h3>Total Tests</h3>
      <div class="value">{{ report.verdicts|length }}</div>
    </div>
    <div class="card">
      <h3>Passed</h3>
      <div class="value" style="color: var(--pass);">{{ report.pass_count }}</div>
    </div>
    <div class="card">
      <h3>Failed</h3>
      <div class="value" style="color: var(--fail);">{{ report.fail_count }}</div>
    </div>
    <div class="card">
      <h3>Flaky</h3>
      <div class="value" style="color: var(--flaky);">{{ report.flaky_count }}</div>
    </div>
    <div class="card">
      <h3>Errors</h3>
      <div class="value" style="color: var(--error);">{{ report.error_count }}</div>
    </div>
    <div class="card">
      <h3>Duration</h3>
      <div class="value">{{ report.duration_ms }} ms</div>
    </div>
  </div>

  <h2>Test Verdicts</h2>
  <table style="margin-top: 1rem;">
    <thead>
      <tr>
        <th>Test ID</th>
        <th>Status</th>
        <th>Reasoning / Assertions</th>
        <th>Oracle</th>
        <th>Retries</th>
        <th>Duration</th>
      </tr>
    </thead>
    <tbody>
      {% for v in report.verdicts %}
      <tr>
        <td><strong>{{ v.test_id }}</strong></td>
        <td>
          <span class="badge badge-{{ v.status }}">{{ v.status }}</span>
        </td>
        <td>
          <div>{{ v.reasoning or 'Evaluation completed' }}</div>
          {% if v.assertions_result %}
          <div class="assertions-list">
            {% for a in v.assertions_result %}
            <div class="assert-item {% if a.passed %}assert-passed{% else %}assert-failed{% endif %}">
              {% if a.passed %}✓{% else %}✗{% endif %} {{ a.assertion }} {% if a.message %}({{ a.message }}){% endif %}
            </div>
            {% endfor %}
          </div>
          {% endif %}
        </td>
        <td>{{ v.oracle_used }}</td>
        <td>{{ v.retries }}</td>
        <td>{{ v.duration_ms }} ms</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</body>
</html>
"""


class HTMLReporter(Reporter):
    """Generates human-readable HTML reports."""

    def __init__(self, redactor=None) -> None:
        self.redactor = redactor or default_redactor
        self.template = Template(HTML_TEMPLATE)

    def generate_report(self, report: Report, output_dir: Path) -> Path:
        """Render and save HTML report dashboard."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        report_file = output_dir / f"report_{report.run_id}.html"

        # Apply redaction before rendering
        clean_report_dict = self.redactor.redact(report.model_dump(mode="json"))
        rendered = self.template.render(report=clean_report_dict)

        report_file.write_text(rendered, encoding="utf-8")
        return report_file


# Register HTML reporter
register_reporter("html", HTMLReporter)
