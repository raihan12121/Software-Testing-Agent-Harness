"""Phase 2 Exit Gate Verification Suite.

Adheres strictly to phases.md §Phase 2:
1. WebAdapter runs a full test plan against a real multi-page web app, correctly catching
   at least 2 seeded bugs and producing zero false positives on the clean baseline.
2. CLIAdapter passes its conformance suite and correctly tests a real CLI tool.
3. LLM-as-judge correctly defers to human review on a deliberately ambiguous test case (proving R-ORACLE-2).
4. Proves R-ORACLE-5 human review audit logging.
"""

from __future__ import annotations

import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from sentinel.adapters.cli_adapter.adapter import CLIAdapter
from sentinel.adapters.web_adapter.adapter import WebAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep
from sentinel.llm.provider import LLMProvider, LLMUsageMetrics
from sentinel.memory.store import MemoryStore
from sentinel.oracle.llm_judge import JudgeResponse, LLMJudgeOracle


class ConfigurableJudgeProvider(LLMProvider):
    """Mock provider allowing controlled verdict, confidence, and reasoning for testing."""

    def __init__(self, verdict: str, confidence: float, reasoning: str) -> None:
        self.verdict = verdict
        self.confidence = confidence
        self.reasoning = reasoning

    def generate_structured(self, prompt: str, response_model: type, system_prompt: str | None = None):
        resp = JudgeResponse(
            verdict=self.verdict,  # type: ignore
            confidence=self.confidence,
            reasoning=self.reasoning,
        )
        metrics = LLMUsageMetrics(
            prompt_hash="gate_hash",
            model="test-gate-judge",
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=5,
        )
        return resp, metrics


class MultiPageWebAppHandler(BaseHTTPRequestHandler):
    """Multi-page web server with clean pages and 2 deliberately seeded bugs."""

    def log_message(self, format, *args):
        pass  # Suppress console log spam

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """<!DOCTYPE html>
            <html>
            <head><title>Portal Home</title></head>
            <body>
              <h1>Welcome to the Multi-Page Portal</h1>
              <nav>
                <a id="link-login" href="/login">Login</a>
                <a id="link-dash" href="/dashboard">Dashboard</a>
              </nav>
            </body>
            </html>"""
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/login":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """<!DOCTYPE html>
            <html>
            <head><title>Login Page</title></head>
            <body>
              <h2>Please Sign In</h2>
              <form id="login-form">
                <input id="username" name="username" type="text" placeholder="Username" />
                <button id="btn-submit" type="button">Sign In</button>
              </form>
            </body>
            </html>"""
            self.wfile.write(html.encode("utf-8"))

        elif self.path == "/dashboard":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            html = """<!DOCTYPE html>
            <html>
            <head><title>User Dashboard</title></head>
            <body>
              <h2>User Dashboard Overview</h2>
              <p>All services are normal.</p>
            </body>
            </html>"""
            self.wfile.write(html.encode("utf-8"))

        # SEEDED BUG 1: Broken navigation link returns 404
        elif self.path == "/broken-link":
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Not Found</title></head><body>404 Not Found</body></html>")

        # SEEDED BUG 2: Crash page returns 500 Server Error
        elif self.path == "/crash-page":
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Server Error</title></head><body>500 Critical Failure</body></html>")

        else:
            self.send_response(404)
            self.end_headers()


def test_phase2_exit_gate_end_to_end(tmp_path: Path):
    """Verify all 4 Phase 2 Exit Gate requirements."""
    # 1. Start local multi-page web server on port 8766
    server = HTTPServer(("127.0.0.1", 8766), MultiPageWebAppHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.2)

    web_adapter = None
    try:
        # --- REQUIREMENT 1: WebAdapter Multi-Page App Testing ---
        target_config = TargetConfig(
            target_type="web",
            name="multi-page-app",
            base_url="http://127.0.0.1:8766",
            allowed_hosts=["127.0.0.1", "localhost"],
        )
        web_adapter = WebAdapter(target_config)

        # Discovery test
        model = web_adapter.discover(target_config)
        assert model.target_type == "web"
        assert len(model.endpoints) >= 1

        # Clean baseline tests (Expect 0 false positives)
        clean_tests = [
            TestCase(
                id="TC-WEB-BASE-01",
                target_type="web",
                title="Verify Home Page Loads Cleanly",
                steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/")],
                expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200", "title == 'Portal Home'"]),
            ),
            TestCase(
                id="TC-WEB-BASE-02",
                target_type="web",
                title="Verify Login Page Loads Cleanly",
                steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/login")],
                expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200", "title == 'Login Page'"]),
            ),
            TestCase(
                id="TC-WEB-BASE-03",
                target_type="web",
                title="Verify Dashboard Page Loads Cleanly",
                steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/dashboard")],
                expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200", "title == 'User Dashboard'"]),
            ),
        ]

        run_config_clean = RunConfig(
            run_id="phase2-clean-run",
            project_id="phase2-gate",
            environment="staging",
            output_dir=tmp_path / "reports",
            allow_mutations=True,
        )
        orch_clean = Orchestrator(target_config, run_config_clean)
        report_clean, exit_clean = orch_clean.run_tests(clean_tests)

        # Zero false positives on clean baseline
        assert report_clean.fail_count == 0, f"Clean baseline had failures: {report_clean.fail_count}"
        assert report_clean.pass_count == 3
        assert exit_clean == 0

        # Seeded bugs test cases
        bug_tests = [
            TestCase(
                id="TC-WEB-BUG-01",
                target_type="web",
                title="Seeded Bug 1: Broken Link Check",
                steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/broken-link")],
                expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
            ),
            TestCase(
                id="TC-WEB-BUG-02",
                target_type="web",
                title="Seeded Bug 2: Server Crash Page Check",
                steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/crash-page")],
                expected=ExpectedResult(oracle="deterministic", assertions=["status_code == 200"]),
            ),
        ]

        run_config_bugs = RunConfig(
            run_id="phase2-bug-run",
            project_id="phase2-gate",
            environment="staging",
            output_dir=tmp_path / "reports",
            allow_mutations=True,
        )
        orch_bugs = Orchestrator(target_config, run_config_bugs)
        report_bugs, exit_bugs = orch_bugs.run_tests(bug_tests)

        # Both seeded bugs caught
        assert report_bugs.fail_count == 2
        assert exit_bugs == 1
        failed_ids = {v.test_id for v in report_bugs.verdicts if v.status == "fail"}
        assert "TC-WEB-BUG-01" in failed_ids
        assert "TC-WEB-BUG-02" in failed_ids

        # --- REQUIREMENT 2: CLIAdapter Real Tool Testing ---
        cli_config = TargetConfig(target_type="cli", name="python-cli")
        cli_adapter = CLIAdapter(cli_config)
        cli_step = TestStep(
            action="exec",
            path=f'{sys.executable} -c "import sys; print(f\'PY_OK_{sys.version_info[0]}\')"',
        )
        cli_obs = cli_adapter.execute_action(cli_step)
        assert cli_obs.error is None
        assert cli_obs.raw_result["exit_code"] == 0
        assert "PY_OK_3" in cli_obs.raw_result["stdout"]

        # --- REQUIREMENT 3: LLM-as-Judge Defers to Human Review (R-ORACLE-2) ---
        ambiguous_provider = ConfigurableJudgeProvider(
            verdict="pass",
            confidence=0.62,  # Below 0.75 threshold
            reasoning="Wording is somewhat ambiguous; human review advised.",
        )
        judge_oracle = LLMJudgeOracle(llm_provider=ambiguous_provider)

        judge_test_case = TestCase(
            id="TC-JUDGE-AMBIGUOUS",
            target_type="web",
            title="Evaluate Subjective Welcome Banner Tone",
            steps=[TestStep(action="navigate", path="http://127.0.0.1:8766/")],
            expected=ExpectedResult(oracle="llm_judge", judge_criteria="Verify welcoming tone"),
        )
        judge_obs = web_adapter.execute_action(judge_test_case.steps[0])
        judge_verdict = judge_oracle.evaluate(judge_test_case, judge_obs)

        # Must route to pending_review per R-ORACLE-2!
        assert judge_verdict.status == "pending_review"
        assert judge_verdict.confidence == 0.62

        # --- REQUIREMENT 4: Record Human Review Resolution (R-ORACLE-5) ---
        memory_store = MemoryStore(db_path=tmp_path / "phase2_mem.sqlite")
        judge_report = report_bugs.model_copy(update={"run_id": "run-phase2-judge", "verdicts": [judge_verdict]})
        memory_store.persist_run(judge_report, [judge_test_case])

        pending_items = memory_store.get_pending_reviews("run-phase2-judge")
        assert len(pending_items) == 1
        assert pending_items[0]["test_id"] == "TC-JUDGE-AMBIGUOUS"

        # Resolve the review
        memory_store.record_human_resolution(
            test_id="TC-JUDGE-AMBIGUOUS",
            run_id="run-phase2-judge",
            original_status="pending_review",
            resolved_status="pass",
            resolved_by="qa_architect",
            rationale="Tone reviewed and deemed appropriate for internal portal.",
        )

        with memory_store.connection() as conn:
            resolution_row = conn.execute(
                "SELECT * FROM human_review_resolutions WHERE test_id = 'TC-JUDGE-AMBIGUOUS'"
            ).fetchone()
            assert resolution_row is not None
            assert resolution_row["resolved_status"] == "pass"
            assert resolution_row["resolved_by"] == "qa_architect"

        print("\nPhase 2 Exit Gate Successfully Verified!")

    finally:
        if web_adapter:
            web_adapter.close()
        server.shutdown()
        server.server_close()
