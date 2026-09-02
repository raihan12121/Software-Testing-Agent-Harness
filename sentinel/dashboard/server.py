"""Interactive Web Dashboard Server for Sentinel Team Mode.

Adheres strictly to:
- phases.md §Phase 4 (Web dashboard for trend viewing, quality gates, and human-review queue)
- rules.md R-ORACLE-5 (Full audit trail recorded for human resolutions)
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from sentinel.core.logging import logger
from sentinel.memory.store import MemoryStore


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Sentinel web dashboard and REST API."""

    store: MemoryStore = None  # type: ignore

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._handle_dashboard_html(params)
        elif path == "/api/runs":
            self._handle_api_runs(params)
        elif path == "/api/trends":
            self._handle_api_trends(params)
        elif path == "/api/reviews":
            self._handle_api_reviews()
        elif path == "/health":
            self._send_json({"status": "ok", "service": "sentinel-dashboard"})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/reviews/resolve":
            content_length = int(self.headers.get("Content-Length", 0))
            body_data = self.rfile.read(content_length).decode("utf-8")
            try:
                payload = json.loads(body_data)
                self.store.record_human_resolution(
                    test_id=payload["test_id"],
                    run_id=payload["run_id"],
                    resolved_status=payload["resolved_status"],
                    resolved_by=payload.get("resolved_by", "dashboard_reviewer"),
                    rationale=payload.get("rationale", "Resolved via Dashboard UI"),
                    original_status=payload.get("original_status", "pending_review"),
                )
                self._send_json({"status": "success", "message": f"Test {payload['test_id']} resolved."})
            except Exception as e:
                self.send_error(400, f"Resolution error: {str(e)}")
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api_runs(self, params: dict[str, list[str]]) -> None:
        project_id = params.get("project_id", ["default"])[0]
        runs = self.store.get_team_run_history(project_id=project_id)
        self._send_json({"runs": runs})

    def _handle_api_trends(self, params: dict[str, list[str]]) -> None:
        project_id = params.get("project_id", ["default"])[0]
        metrics = self.store.get_trend_metrics(project_id=project_id)
        self._send_json(metrics)

    def _handle_api_reviews(self) -> None:
        reviews = self.store.get_pending_reviews()
        self._send_json({"pending_reviews": reviews})

    def _handle_dashboard_html(self, params: dict[str, list[str]] | None = None) -> None:
        project_id = params.get("project_id", [None])[0] if params else None
        metrics = self.store.get_trend_metrics(project_id)
        pending = self.store.get_pending_reviews()
        quarantined = self.store.get_quarantined_test_ids()

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Sentinel Team Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    h1 {{ color: #38bdf8; font-size: 2rem; margin-bottom: 0.5rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.5rem; margin: 2rem 0; }}
    .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; border: 1px solid #334155; }}
    .card h3 {{ font-size: 0.875rem; text-transform: uppercase; color: #94a3b8; margin: 0; }}
    .card .value {{ font-size: 2rem; font-weight: bold; margin-top: 0.5rem; color: #f8fafc; }}
    .card .green {{ color: #4ade80; }}
    .card .red {{ color: #f87171; }}
    .card .yellow {{ color: #facc15; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
    th, td {{ padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ background: #1e293b; color: #94a3b8; font-size: 0.875rem; }}
    .badge {{ display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: bold; }}
    .badge-pending {{ background: #0284c7; color: white; }}
    .badge-quarantined {{ background: #b45309; color: white; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>🛡️ Sentinel Team Dashboard</h1>
    <p>Live Quality Gates, Trend Metrics, and Human Review Queue (FR-16, R-ORACLE-2)</p>

    <div class="grid">
      <div class="card">
        <h3>Total Runs</h3>
        <div class="value">{metrics['total_runs']}</div>
      </div>
      <div class="card">
        <h3>Pass Rate</h3>
        <div class="value green">{metrics['pass_rate'] * 100:.1f}%</div>
      </div>
      <div class="card">
        <h3>Pending Reviews</h3>
        <div class="value yellow">{len(pending)}</div>
      </div>
      <div class="card">
        <h3>Quarantined Tests</h3>
        <div class="value red">{len(quarantined)}</div>
      </div>
    </div>

    <h2>Pending Human Review Queue</h2>
    <table>
      <thead>
        <tr><th>Run ID</th><th>Test ID</th><th>Status</th><th>Oracle</th><th>Confidence</th><th>Reasoning</th></tr>
      </thead>
      <tbody>
        {"".join(f"<tr><td>{r['run_id']}</td><td>{r['test_id']}</td><td><span class='badge badge-pending'>{r['status']}</span></td><td>{r['oracle_used']}</td><td>{r['confidence']}</td><td>{r['reasoning']}</td></tr>" for r in pending) if pending else "<tr><td colspan='6' style='text-align:center; color:#94a3b8;'>No pending reviews in queue. All automated verdicts resolved!</td></tr>"}
      </tbody>
    </table>
  </div>
</body>
</html>"""
        content = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server logging in production test output."""
        pass


def start_dashboard_server(
    port: int = 8080,
    db_path: str = "sentinel_memory.sqlite",
    blocking: bool = True,
) -> HTTPServer:
    """Initialize and run the Sentinel Dashboard server."""
    store = MemoryStore(db_path=db_path)
    DashboardRequestHandler.store = store
    server = HTTPServer(("127.0.0.1", port), DashboardRequestHandler)
    logger.info(f"Sentinel Dashboard running at http://127.0.0.1:{port}/")

    if blocking:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
    else:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

    return server
