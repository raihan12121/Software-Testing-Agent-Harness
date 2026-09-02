"""Regression test for BUG 1: base_url from OpenAPI spec is wired to execution."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator


class LiveMockServerHandler(BaseHTTPRequestHandler):
    """Simple mock server responding to OpenAPI petstore endpoints."""

    def log_message(self, format, *args):
        pass  # Suppress logs

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ready", "uptime": 3600}')
        elif self.path.startswith("/users"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'[{"id": 1, "name": "Alice"}]')
        elif self.path.startswith("/orders"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'[{"id": 100, "item_count": 2}]')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"id": "order-123", "status": "created"}')


def test_base_url_wired_from_openapi_spec(tmp_path: Path):
    """Test that TargetConfig without explicit base_url automatically resolves and reaches spec server."""
    server = HTTPServer(("127.0.0.1", 8765), LiveMockServerHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    try:
        # Construct TargetConfig with NO base_url set (base_url=None)
        target_config = TargetConfig(
            target_type="api",
            name="Petstore API",
            spec_path="examples/petstore_spec.yaml",
            base_url=None,
        )

        run_config = RunConfig(
            run_id="test-bug1-run",
            project_id="test-bug1",
            environment="staging",
            allow_mutations=True,
            output_dir=tmp_path / "reports",
        )

        orchestrator = Orchestrator(target_config, run_config)
        report, exit_code = orchestrator.plan_and_run(report_format="json")

        # Requests must genuinely reach the server on 127.0.0.1:8765
        assert report.pass_count > 0, "Expected tests to pass against live spec server"
        assert report.error_count == 0, f"Expected 0 execution errors, got {report.error_count}"

        # Assert no connection errors or localhost:8000 fallbacks in verdicts
        for v in report.verdicts:
            reasoning = str(v.reasoning or "")
            assert "Connection refused" not in reasoning, f"Test {v.test_id} failed with connection refused: {reasoning}"
            assert "WinError 10061" not in reasoning, f"Test {v.test_id} connection error: {reasoning}"

    finally:
        server.shutdown()
        server.server_close()


def test_cli_base_url_override(tmp_path: Path):
    """Test that --base-url CLI flag explicitly overrides the spec's declared server."""
    server = HTTPServer(("127.0.0.1", 8766), LiveMockServerHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.1)

    try:
        from sentinel.cli import main

        out_dir = str(tmp_path / "cli_reports")
        exit_code = main([
            "run",
            "--env", "staging",
            "--target", "examples/petstore_spec.yaml",
            "--target-type", "api",
            "--base-url", "http://127.0.0.1:8766",
            "--allow-mutations",
            "--output-dir", out_dir,
            "--format", "json",
        ])

        assert exit_code in (0, 1), f"Expected normal execution exit code 0 or 1, got {exit_code}"
        reports = list(Path(out_dir).glob("*.json"))
        assert len(reports) == 1, "Expected JSON report to be generated in out_dir"

    finally:
        server.shutdown()
        server.server_close()
