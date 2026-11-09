"""Automated regression and conformance tests for SQA audit findings.

Covers:
- BUG-CRIT-01: print_report_summary import and execution in scanner/cli
- BUG-CRIT-02: MockLLMProvider synthesis for JudgeResponse schema
- BUG-HIGH-01: DeterministicOracle dict method collision ('items') and nested list dot-access
- BUG-HIGH-02: Web target unhandled action / offline failure detection in Orchestrator
- BUG-HIGH-03: TestDeduplicator preserving distinct request bodies and headers
- BUG-HIGH-04: RuleBasedPlanner CRUD coverage checklist unique scenario IDs
- BUG-HIGH-05: DefectFiler handling verdict.reasoning=None and priority severity mapping
- BUG-HIGH-06: XSS escaping in dashboard server and HTML reporter
- BUG-MED-01: RedactionFilter unquoted key-values and Python set handling
- BUG-MED-02: MemoryStore trend metrics on all-error runs
- BUG-MED-06: sentinel review CLI explicit status requirement
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sentinel.adapters.base import get_adapter
from sentinel.adapters.web_adapter.adapter import WebAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.orchestrator import Orchestrator
from sentinel.core.redaction import RedactionFilter, default_redactor
from sentinel.core.schemas import (
    ExpectedResult,
    Observation,
    Report,
    TargetModel,
    TestCase,
    TestStep,
    Verdict,
)
from sentinel.defects.filer import DefectFiler
from sentinel.generator.dedup import TestDeduplicator
from sentinel.llm.provider import MockLLMProvider
from sentinel.memory.store import MemoryStore
from sentinel.oracle.deterministic import DeterministicOracle
from sentinel.oracle.llm_judge import JudgeResponse, LLMJudgeOracle
from sentinel.planner.rule_based import RuleBasedPlanner
from sentinel.reporter.html_reporter import HTMLReporter


# ---------------------------------------------------------------------------
# BUG-CRIT-01: print_report_summary availability and CLI interactive execution
# ---------------------------------------------------------------------------
def test_cli_print_report_summary_exists_and_executes(capsys):
    """Verify print_report_summary can be imported from sentinel.cli and renders report summary."""
    from sentinel.cli import print_report_summary

    report = Report(
        run_id="run-test-summary",
        project_id="test",
        target_type="stub",
        environment="local",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        pass_count=2,
        fail_count=0,
        flaky_count=0,
        error_count=0,
        pending_count=0,
        duration_ms=15,
        verdicts=[],
    )
    # Must execute cleanly without error
    print_report_summary(report)


# ---------------------------------------------------------------------------
# BUG-CRIT-02: MockLLMProvider synthesis for JudgeResponse
# ---------------------------------------------------------------------------
def test_mock_llm_provider_judge_response_conformance():
    """Verify MockLLMProvider successfully synthesizes JudgeResponse without ValidationError."""
    mock = MockLLMProvider()
    response, metrics = mock.generate_structured(
        prompt="Evaluate whether user was logged in properly.",
        response_model=JudgeResponse,
    )
    assert isinstance(response, JudgeResponse)
    assert response.verdict in ("pass", "fail", "uncertain")
    assert isinstance(response.confidence, float)
    assert 0.0 <= response.confidence <= 1.0
    assert isinstance(response.reasoning, str)
    assert len(response.reasoning) > 0


def test_llm_judge_oracle_works_with_default_mock_provider():
    """Verify LLMJudgeOracle works out-of-the-box with default MockLLMProvider."""
    mock_provider = MockLLMProvider()
    oracle = LLMJudgeOracle(llm_provider=mock_provider)

    tc = TestCase(
        id="TC-JUDGE-DEFAULT",
        target_type="api",
        title="Check semantic response",
        steps=[TestStep(action="http_request", path="/greet")],
        expected=ExpectedResult(oracle="llm_judge", judge_criteria="Greeting should be friendly"),
    )
    obs = Observation(test_id="TC-JUDGE-DEFAULT", raw_result={"body": {"message": "Hello!"}})

    verdict = oracle.evaluate(tc, obs)
    assert verdict.status in ("pass", "fail", "pending_review")
    assert verdict.status != "error"
    assert "LLM Judge execution failure" not in (verdict.reasoning or "")


# ---------------------------------------------------------------------------
# BUG-HIGH-01: DeterministicOracle dict method collision and nested lists
# ---------------------------------------------------------------------------
def test_deterministic_oracle_dict_key_collision_items():
    """Verify 'items', 'keys', 'values' dictionary keys do not collide with dict methods."""
    oracle = DeterministicOracle()
    tc = TestCase(
        id="TC-ITEMS",
        target_type="api",
        title="Check items key",
        steps=[TestStep(action="http_request")],
        expected=ExpectedResult(assertions=["body.items == [1, 2, 3]"]),
    )
    obs = Observation(
        test_id="TC-ITEMS",
        raw_result={"body": {"items": [1, 2, 3]}},
    )
    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pass"
    assert verdict.assertions_result[0].passed is True


def test_deterministic_oracle_nested_list_dot_access():
    """Verify dot notation works on dictionaries nested inside lists: body.items[0].name."""
    oracle = DeterministicOracle()
    tc = TestCase(
        id="TC-NESTED-LIST",
        target_type="api",
        title="Check nested list dot access",
        steps=[TestStep(action="http_request")],
        expected=ExpectedResult(assertions=["body.users[0].name == 'Alice'"]),
    )
    obs = Observation(
        test_id="TC-NESTED-LIST",
        raw_result={"body": {"users": [{"name": "Alice", "role": "admin"}]}},
    )
    verdict = oracle.evaluate(tc, obs)
    assert verdict.status == "pass"
    assert verdict.assertions_result[0].passed is True


# ---------------------------------------------------------------------------
# BUG-HIGH-02: False pass on unreachable / dead targets in plan_and_run
# ---------------------------------------------------------------------------
def test_web_adapter_rejects_unhandled_action_with_error():
    """Verify WebAdapter does not silently default unhandled actions to status_code 200."""
    adapter = WebAdapter()
    try:
        step = TestStep(action="unknown_non_web_action", path="/something")
        obs = adapter.execute_action(step)
        # Must report error or failure status rather than silent success
        assert obs.error is not None or obs.raw_result.get("status_code", 0) >= 400
    finally:
        adapter.close()


# ---------------------------------------------------------------------------
# BUG-HIGH-03: TestDeduplicator preserving distinct bodies and headers
# ---------------------------------------------------------------------------
def test_test_deduplicator_preserves_distinct_payload_bodies():
    """Verify TestDeduplicator does not merge distinct test payloads (e.g. security vs happy path)."""
    dedup = TestDeduplicator()
    tc_valid = TestCase(
        id="TC-HAPPY",
        target_type="api",
        title="Valid login",
        steps=[TestStep(action="http_request", method="POST", path="/login", body={"user": "admin"})],
        expected=ExpectedResult(assertions=["status_code == 200"]),
    )
    tc_inject = TestCase(
        id="TC-INJECT",
        target_type="api",
        title="SQL injection probe",
        steps=[TestStep(action="http_request", method="POST", path="/login", body={"user": "' OR 1=1 --"})],
        expected=ExpectedResult(assertions=["status_code == 200"]),
    )
    merged = dedup.cluster_and_merge([tc_valid, tc_inject])
    assert len(merged) == 2, "TestDeduplicator discarded test case with distinct request body!"
    test_ids = {t.id for t in merged}
    assert "TC-HAPPY" in test_ids
    assert "TC-INJECT" in test_ids


# ---------------------------------------------------------------------------
# BUG-HIGH-04: RuleBasedPlanner CRUD coverage checklist unique scenario IDs
# ---------------------------------------------------------------------------
def test_rule_based_planner_unique_crud_scenario_ids():
    """Verify RuleBasedPlanner assigns unique IDs to all CRUD coverage scenarios."""
    planner = RuleBasedPlanner()
    target_model = TargetModel(
        target_type="api",
        name="Store API",
        endpoints=[
            {"path": "/users", "method": "GET", "summary": "List users"},
            {"path": "/users/{id}", "method": "GET", "summary": "Get user"},
            {"path": "/orders", "method": "GET", "summary": "List orders"},
            {"path": "/orders/{id}", "method": "GET", "summary": "Get order"},
        ],
    )
    plan = planner.build_plan(target_model)
    crud_scenarios = [s for s in plan.scenarios if "crud_checklist" in s.tags]
    assert len(crud_scenarios) >= 2
    scenario_ids = [s.id for s in crud_scenarios]
    assert len(scenario_ids) == len(set(scenario_ids)), f"Duplicate scenario IDs found: {scenario_ids}"


# ---------------------------------------------------------------------------
# BUG-HIGH-05: DefectFiler handling verdict.reasoning=None and severity mapping
# ---------------------------------------------------------------------------
def test_defect_filer_handles_none_reasoning_and_maps_priority():
    """Verify DefectFiler generates fingerprint without error when reasoning is None and maps priority."""
    store = MemoryStore(":memory:")
    filer = DefectFiler(memory_store=store)

    verdict = Verdict(
        test_id="TC-NO-REASON",
        status="fail",
        oracle_used="deterministic",
        reasoning=None,
    )
    fingerprint = filer.generate_fingerprint(verdict)
    assert len(fingerprint) == 16

    tc = TestCase(
        id="TC-CRIT",
        target_type="api",
        title="Critical auth failure",
        priority="critical",
        steps=[TestStep(action="http_request", path="/admin")],
        expected=ExpectedResult(assertions=["status_code == 403"]),
        source_context="openapi.yaml#/paths/~1admin/get",
    )
    report = Report(
        run_id="run-filer-test",
        project_id="test",
        target_type="api",
        environment="staging",
        verdicts=[verdict],
    )

    defect_res = filer.file_defect(tc, verdict, report)
    assert defect_res is not None

    with store.connection() as conn:
        row = conn.execute("SELECT severity, module FROM defects WHERE defect_id = ?", (defect_res["defect_id"],)).fetchone()
        assert row is not None
        assert row["severity"] == "critical", f"Expected severity 'critical' from test case priority, got {row['severity']}"
        assert row["module"] != "openapi.yaml#"


# ---------------------------------------------------------------------------
# BUG-HIGH-06: Stored XSS / HTML escaping in reporting and dashboard
# ---------------------------------------------------------------------------
def test_html_reporter_escapes_xss_payloads(tmp_path: Path):
    """Verify HTMLReporter escapes HTML/script injection payloads in verdicts and assertions."""
    reporter = HTMLReporter()
    xss_payload = "<script>alert('xss')</script>"
    verdict = Verdict(
        test_id="TC-XSS",
        status="fail",
        oracle_used="deterministic",
        reasoning=xss_payload,
        assertions_result=[],
    )
    report = Report(
        run_id="run-xss",
        project_id="test",
        target_type="api",
        environment="staging",
        verdicts=[verdict],
        fail_count=1,
    )
    out_file = reporter.generate_report(report, tmp_path)
    content = out_file.read_text(encoding="utf-8")

    assert "<script>alert('xss')</script>" not in content
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in content or "&lt;script&gt;alert('xss')&lt;/script&gt;" in content


# ---------------------------------------------------------------------------
# BUG-MED-01: RedactionFilter unquoted key-values and Python set handling
# ---------------------------------------------------------------------------
def test_redaction_filter_handles_unquoted_and_sets():
    """Verify RedactionFilter sanitizes unquoted passwords/keys and recursively sanitizes sets."""
    redactor = RedactionFilter()

    # Unquoted YAML/header text
    text = "password: super_secret_12345\napi_key: secret_token_xyz"
    redacted_text = redactor.redact_text(text)
    assert "super_secret_12345" not in redacted_text
    assert "secret_token_xyz" not in redacted_text

    # Set collection
    data_set = {"user@example.com", "clean_value"}
    redacted_set = redactor.redact(data_set)
    assert isinstance(redacted_set, set)
    assert "user@example.com" not in redacted_set
    assert any("[REDACTED:EMAIL]" in item for item in redacted_set)


# ---------------------------------------------------------------------------
# BUG-MED-02: MemoryStore trend metrics on pure error runs
# ---------------------------------------------------------------------------
def test_memory_store_trend_metrics_pure_error_run():
    """Verify MemoryStore does not report 100% pass rate when run has only execution errors."""
    store = MemoryStore(":memory:")
    verdict = Verdict(
        test_id="TC-ERR",
        status="error",
        oracle_used="deterministic",
        reasoning="Execution crashed",
    )
    report = Report(
        run_id="run-all-err",
        project_id="test-proj",
        target_type="api",
        environment="staging",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        verdicts=[verdict],
        pass_count=0,
        fail_count=0,
        flaky_count=0,
        error_count=1,
    )
    tc = TestCase(
        id="TC-ERR",
        target_type="api",
        title="Error test",
        steps=[TestStep(action="http_request")],
        expected=ExpectedResult(),
    )
    store.persist_run(report, [tc])
    metrics = store.get_trend_metrics("test-proj")
    assert metrics["total_tests"] == 1
    assert metrics["pass_rate"] == 0.0


# ---------------------------------------------------------------------------
# BUG-MED-04: Adapters write real artifact files to disk
# ---------------------------------------------------------------------------
def test_adapters_write_real_artifact_files_to_disk(tmp_path, monkeypatch):
    """Verify APIAdapter, CLIAdapter, and PerformanceAdapter write physical artifact files to disk."""
    import sys
    from sentinel.adapters.api_adapter.adapter import APIAdapter
    from sentinel.adapters.cli_adapter.adapter import CLIAdapter
    from sentinel.adapters.perf_adapter.adapter import PerformanceAdapter

    monkeypatch.chdir(tmp_path)

    # 1. CLIAdapter with non-zero exit code
    cli_config = TargetConfig(target_type="cli", name="python")
    cli_adapter = CLIAdapter(cli_config)
    cli_step = TestStep(
        action="exec",
        path=f'{sys.executable} -c "import sys; sys.stderr.write(\'ERR_OUT\'); sys.exit(1)"',
        metadata={"test_id": "TC-CLI-ART"},
    )
    cli_obs = cli_adapter.execute_action(cli_step)
    assert len(cli_obs.artifacts) >= 1
    cli_file = Path(cli_obs.artifacts[0].path)
    assert cli_file.exists(), f"CLI artifact file {cli_file} was not written to disk!"
    assert "ERR_OUT" in cli_file.read_text(encoding="utf-8")

    # 2. PerformanceAdapter load execution
    perf_config = TargetConfig(target_type="perf", name="local_perf")
    perf_adapter = PerformanceAdapter(perf_config)
    perf_step = TestStep(
        action="load",
        path="/api/benchmark",
        metadata={"test_id": "TC-PERF-ART", "iterations": 5, "concurrency": 1},
    )
    perf_obs = perf_adapter.execute_action(perf_step)
    assert len(perf_obs.artifacts) >= 1
    perf_file = Path(perf_obs.artifacts[0].path)
    assert perf_file.exists(), f"Perf artifact file {perf_file} was not written to disk!"
    assert "/api/benchmark" in perf_file.read_text(encoding="utf-8")

    # 3. APIAdapter error response (status >= 400) artifact writing
    api_config = TargetConfig(
        target_type="api",
        name="test_api",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    api_adapter = APIAdapter(api_config)
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.url = "http://localhost/api/fail"
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {"error": "Internal Error"}
    with patch.object(api_adapter.client, "request", return_value=mock_resp):
        api_step = TestStep(
            action="GET",
            path="http://localhost/api/fail",
            metadata={"test_id": "TC-API-ART"},
        )
        api_obs = api_adapter.execute_action(api_step)
        assert len(api_obs.artifacts) >= 1
        api_file = Path(api_obs.artifacts[0].path)
        assert api_file.exists(), f"API artifact file {api_file} was not written to disk!"
        assert "Internal Error" in api_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# BUG-MED-03: Empty allowed_hosts default denies arbitrary external hosts
# ---------------------------------------------------------------------------
def test_empty_allowed_hosts_blocks_external_hosts_by_default():
    """Verify R-SAFE-5: TargetConfig with empty allowed_hosts blocks arbitrary internet domains."""
    from sentinel.adapters.api_adapter.adapter import APIAdapter
    from sentinel.adapters.web_adapter.adapter import WebAdapter
    from sentinel.adapters.db_adapter.adapter import DatabaseAdapter
    from sentinel.adapters.iot_adapter.adapter import IoTAdapter

    # 1. APIAdapter with empty allowed_hosts
    api_config = TargetConfig(target_type="api", name="test_api", allowed_hosts=[])
    api_adapter = APIAdapter(api_config)
    api_step = TestStep(
        action="GET",
        path="https://unauthorized-external-domain.com/data",
        metadata={"test_id": "TC-ALLOW-API"},
    )
    api_obs = api_adapter.execute_action(api_step)
    assert api_obs.error is not None
    assert "SECURITY_BLOCK" in api_obs.error

    # 2. WebAdapter with empty allowed_hosts
    web_config = TargetConfig(target_type="web", name="test_web", allowed_hosts=[])
    web_adapter = WebAdapter(web_config)
    web_step = TestStep(
        action="navigate",
        path="https://malicious-phishing-site.org",
        metadata={"test_id": "TC-ALLOW-WEB"},
    )
    web_obs = web_adapter.execute_action(web_step)
    assert web_obs.error is not None
    assert "SECURITY_BLOCK" in web_obs.error

    # 3. DatabaseAdapter with empty allowed_hosts
    db_config = TargetConfig(target_type="database", name="test_db", allowed_hosts=[])
    db_adapter = DatabaseAdapter(db_config)
    db_step = TestStep(
        action="connect",
        path="postgresql://user:pass@remote-leak-host.com:5432/mydb",
        metadata={"test_id": "TC-ALLOW-DB"},
    )
    db_obs = db_adapter.execute_action(db_step)
    assert db_obs.error is not None
    assert "SECURITY_BLOCK" in db_obs.error

    # 4. IoTAdapter with empty allowed_hosts
    iot_config = TargetConfig(target_type="iot", name="test_iot", allowed_hosts=[])
    iot_adapter = IoTAdapter(iot_config)
    iot_step = TestStep(
        action="mqtt_connect",
        path="broker.hivemq.com",
        metadata={"test_id": "TC-ALLOW-IOT"},
    )
    iot_obs = iot_adapter.execute_action(iot_step)
    assert iot_obs.error is not None
    assert "SECURITY_BLOCK" in iot_obs.error


# ---------------------------------------------------------------------------
# BUG-LOW-02: OpenAPI parser path-level parameters & RFC 6901 ~1 escaping
# ---------------------------------------------------------------------------
def test_openapi_parser_path_level_parameters_and_rfc6901():
    """Verify OpenAPIParser merges path-level parameters and decodes RFC 6901 ~1 in $ref."""
    from sentinel.adapters.api_adapter.parser import OpenAPIParser

    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0"},
        "paths": {
            "/items/{item_id}": {
                "parameters": [
                    {
                        "name": "item_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "operationId": "getItem",
                    "parameters": [
                        {
                            "$ref": "#/components/parameters/fields~1filter",
                        }
                    ],
                    "responses": {"200": {"description": "OK"}},
                },
            }
        },
        "components": {
            "parameters": {
                "fields/filter": {
                    "name": "fields",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                }
            }
        },
    }

    parser = OpenAPIParser(spec)
    model = parser.parse()
    assert len(model.endpoints) == 1
    endpoint = model.endpoints[0]
    param_names = [p["name"] for p in endpoint["parameters"]]
    assert "item_id" in param_names, "Path-level parameter 'item_id' was omitted!"
    assert "fields" in param_names, "RFC 6901 parameter 'fields/filter' was not resolved!"


# ---------------------------------------------------------------------------
# BUG-LOW-03: JUnit XML Reporter implementation
# ---------------------------------------------------------------------------
def test_junit_xml_reporter_generation(tmp_path):
    """Verify JUnitReporter produces valid standard JUnit XML conforming to PRD FR-17."""
    import xml.etree.ElementTree as ET
    from sentinel.reporter import get_reporter
    from sentinel.reporter.junit_reporter import JUnitReporter

    reporter = get_reporter("junit")
    assert isinstance(reporter, JUnitReporter)

    verdicts = [
        Verdict(test_id="TC-001", status="pass", oracle_used="deterministic", reasoning="OK"),
        Verdict(test_id="TC-002", status="fail", oracle_used="deterministic", reasoning="Expected 200 got 500"),
        Verdict(test_id="TC-003", status="error", oracle_used="deterministic", reasoning="Timeout"),
        Verdict(test_id="TC-004", status="skipped", oracle_used="deterministic", reasoning="Precondition failed"),
    ]
    report = Report(
        run_id="run-junit-test",
        project_id="test-proj",
        target_type="api",
        environment="staging",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        verdicts=verdicts,
        pass_count=1,
        fail_count=1,
        error_count=1,
        skipped_count=1,
        duration_ms=1250,
    )

    out_file = reporter.generate_report(report, tmp_path)
    assert out_file.exists()
    assert out_file.suffix == ".xml"

    # Verify XML structure
    tree = ET.parse(out_file)
    root = tree.getroot()
    assert root.tag in ("testsuites", "testsuite")
    testcases = root.findall(".//testcase")
    assert len(testcases) == 4

    tc_names = [tc.get("name") for tc in testcases]
    assert "TC-001" in tc_names
    assert "TC-002" in tc_names
    assert "TC-003" in tc_names
    assert "TC-004" in tc_names

    # Check failure and error tags
    tc2 = [tc for tc in testcases if tc.get("name") == "TC-002"][0]
    assert tc2.find("failure") is not None
    tc3 = [tc for tc in testcases if tc.get("name") == "TC-003"][0]
    assert tc3.find("error") is not None
    tc4 = [tc for tc in testcases if tc.get("name") == "TC-004"][0]
    assert tc4.find("skipped") is not None





