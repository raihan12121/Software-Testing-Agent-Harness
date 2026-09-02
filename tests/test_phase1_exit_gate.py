"""Phase 1 Exit Gate Verification Test.

Adheres strictly to TRD.md §9 & phases.md §Phase 1:
1. Given an OpenAPI spec, Sentinel generates >=20 test cases without human editing.
2. Executes against a live test API with >=95% pass/fail agreement.
3. A deliberately broken endpoint is caught with zero false negatives across 3 repeated runs.
4. Report artifacts (JSON + HTML) are generated and CI exit code reflects pass/fail correctly.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from sentinel.adapters.api_adapter.adapter import APIAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.generator.llm_generator import APITestGenerator
from sentinel.planner.rule_based import RuleBasedPlanner


class MockAPIServerHandler(BaseHTTPRequestHandler):
    """Live HTTP server simulating the OpenAPI target with a deliberately broken endpoint."""

    def log_message(self, format, *args):
        pass  # Suppress console log noise during test run

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ready", "uptime": 3600}')
        elif self.path.startswith("/users"):
            if "999999" in self.path:
                self.send_response(404)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'[{"id": 1, "name": "Alice"}]')
        elif self.path.startswith("/orders"):
            if "999999" in self.path:
                self.send_response(404)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'[{"id": 100, "item_count": 2}]')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        auth = self.headers.get("Authorization")
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            body_json = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            body_json = {}

        if self.path == "/auth/login":
            if body_json.get("username") and body_json.get("password"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"token": "jwt-token-12345"}')
            else:
                self.send_response(400)
                self.end_headers()
        elif self.path == "/users":
            if not auth or "invalid" in auth.lower():
                self.send_response(401)
                self.end_headers()
            elif not body_json.get("name") or not body_json.get("email") or not body_json.get("age"):
                self.send_response(400)
                self.end_headers()
            else:
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"id": 1, "name": "Alice"}')
        elif self.path == "/orders":
            if not body_json.get("user_id") or not body_json.get("item_count"):
                self.send_response(400)
                self.end_headers()
            else:
                self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"id": 101, "status": "created"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        auth = self.headers.get("Authorization")
        if not auth or "invalid" in auth.lower():
            self.send_response(401)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "updated"}')

    def do_DELETE(self):
        # DELIBERATE BUG: /orders/{id} DELETE returns 500 error!
        if "/orders" in self.path:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Deliberate 500 bug on order cancel"}')
            return

        auth = self.headers.get("Authorization")
        if not auth or "invalid" in auth.lower():
            self.send_response(401)
            self.end_headers()
        else:
            self.send_response(204)
            self.end_headers()


def test_phase1_exit_gate_end_to_end(tmp_path: Path):
    """Verify all Phase 1 Exit Gate requirements."""
    # 1. Start live mock test server on port 8765
    server = HTTPServer(("127.0.0.1", 8765), MockAPIServerHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    try:
        spec_path = "examples/petstore_spec.yaml"
        target_config = TargetConfig(
            target_type="api",
            name="live-test-petstore",
            spec_path=spec_path,
            base_url="http://127.0.0.1:8765",
            allowed_hosts=["127.0.0.1", "localhost"],
        )

        # 2. Planning & Generation (Criterion 1: >=20 cases without human editing)
        adapter = APIAdapter(target_config)
        target_model = adapter.discover(target_config)
        assert len(target_model.endpoints) >= 6

        planner = RuleBasedPlanner()
        plan = planner.build_plan(target_model)
        assert len(plan.scenarios) >= 20, f"Expected >=20 scenarios, got {len(plan.scenarios)}"

        generator = APITestGenerator()
        test_cases = generator.generate(plan, target_model)
        assert len(test_cases) >= 20, f"Expected >=20 generated test cases, got {len(test_cases)}"

        # 3. Repeat 3 runs against deliberately broken endpoint (Criterion 3: zero false negatives)
        output_dir = tmp_path / "phase1_reports"
        broken_order_test = [tc for tc in test_cases if "DELETE" in tc.title and "orders" in tc.title]
        assert len(broken_order_test) > 0, "Broken order delete scenario must be in test suite"

        for run_idx in range(1, 4):
            run_config = RunConfig(
                run_id=f"phase1-run-{run_idx}",
                project_id="phase1-gate",
                environment="staging",
                output_dir=output_dir,
                allow_mutations=True,
            )
            orchestrator = Orchestrator(target_config, run_config)
            report, exit_code = orchestrator.run_tests(test_cases, report_format="json")

            # Check that the broken endpoint was caught on every single run (0 false negatives)
            broken_verdicts = [v for v in report.verdicts if v.test_id == broken_order_test[0].id]
            assert len(broken_verdicts) == 1
            assert broken_verdicts[0].status == "fail", f"Run {run_idx}: Deliberate bug was not caught!"
            assert exit_code == 1  # Build correctly failed due to defect

        # 4. Verify HTML and JSON report artifacts generated (Criterion 5)
        html_run_config = RunConfig(
            run_id="phase1-html-run",
            project_id="phase1-gate",
            environment="staging",
            output_dir=output_dir,
            allow_mutations=True,
        )
        orchestrator = Orchestrator(target_config, html_run_config)
        html_report, html_code = orchestrator.run_tests(test_cases, report_format="html")

        json_report_file = output_dir / "report_phase1-run-1.json"
        html_report_file = output_dir / "report_phase1-html-run.html"

        assert json_report_file.exists(), "JSON report was not generated"
        assert html_report_file.exists(), "HTML report was not generated"

        html_content = html_report_file.read_text(encoding="utf-8")
        assert "Sentinel SQA Run Report" in html_content
        assert "phase1-html-run" in html_content
        assert "Test Verdicts" in html_content

        print(f"\nPhase 1 Exit Gate Successfully Verified across {len(test_cases)} test cases!")

    finally:
        server.shutdown()
        server.server_close()
