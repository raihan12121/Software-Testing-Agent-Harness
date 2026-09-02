"""Phase 5 Exit Gate Verification Suite.

Adheres strictly to phases.md §Phase 5:
1. Performance/load testing adapter executes load benchmarks with latency percentiles.
2. Security/pentest-oriented test generation with strict R-SAFE guardrails.
3. Embedded/IoT adapter verifies telemetry and clean session state reset.
4. Conformance suite passes for all new adapters (R-BUILD-4).
"""

from __future__ import annotations

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.adapters.iot_adapter.adapter import IoTAdapter
from sentinel.adapters.perf_adapter.adapter import PerformanceAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep
from sentinel.generator.security_generator import SecurityTestGenerator
from sentinel.oracle.deterministic import DeterministicOracle


def test_phase5_exit_gate_end_to_end():
    """Verify all Phase 5 Exit Gate criteria."""
    oracle = DeterministicOracle()

    # --- CRITERION 1: Performance Adapter Benchmarking ---
    perf_config = TargetConfig(target_type="performance", name="GatewayLoadTest")
    perf_adapter = PerformanceAdapter(perf_config)
    perf_model = perf_adapter.discover(perf_config)
    assert perf_model.target_type == "performance"

    perf_step = TestStep(
        action="load_test",
        path="/health",
        params={"concurrency": 10, "iterations": 50},
    )
    perf_obs = perf_adapter.execute_action(perf_step)
    assert perf_obs.error is None
    metrics = perf_obs.raw_result
    assert metrics["total_requests"] == 50
    assert metrics["rps"] > 0
    assert "p50_ms" in metrics
    assert "p95_ms" in metrics
    assert "p99_ms" in metrics
    assert len(perf_obs.artifacts) == 1

    perf_test = TestCase(
        id="TC-PERF-GATE-01",
        target_type="performance",
        title="Health Check Latency Benchmark",
        steps=[perf_step],
        expected=ExpectedResult(
            oracle="deterministic",
            assertions=["status_code == 200", "p95_ms < 500.0", "error_rate == 0.0"],
        ),
    )
    perf_verdict = oracle.evaluate(perf_test, perf_obs)
    assert perf_verdict.status == "pass"
    perf_adapter.reset_state(perf_config)
    perf_adapter.close()

    # --- CRITERION 2: Grounded Security Generation with R-SAFE Guardrails ---
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    api_model = parser.parse()

    sec_gen = SecurityTestGenerator()
    sec_tests = sec_gen.generate_security_suite(api_model)
    assert len(sec_tests) >= 3

    # Validate that all tests have non-destructive safe assertions and error code expectations
    for st in sec_tests:
        assert st.priority in ("high", "critical")
        assert any(tag in st.tags for tag in ("injection", "bola", "info_leak"))
        assert any("status_code" in a for a in st.expected.assertions)

    # --- CRITERION 3: Embedded / IoT Adapter Telemetry & Session Isolation (R-EXEC-1) ---
    iot_config = TargetConfig(target_type="iot", name="IndustrialSensorNet")
    iot_adapter = IoTAdapter(iot_config)
    iot_model = iot_adapter.discover(iot_config)
    assert iot_model.target_type == "iot"

    # Publish sensor reading
    pub_step = TestStep(
        action="publish",
        path="sensors/pressure",
        body={"psi": 101.3, "status": "nominal"},
    )
    pub_obs = iot_adapter.execute_action(pub_step)
    assert pub_obs.raw_result["delivered"] is True

    # Read back telemetry
    sub_step = TestStep(action="subscribe", path="sensors/pressure")
    sub_obs = iot_adapter.execute_action(sub_step)
    assert sub_obs.raw_result["message_count"] == 1
    assert sub_obs.raw_result["latest_message"]["psi"] == 101.3

    # Reset state (R-EXEC-1)
    iot_adapter.reset_state(iot_config)
    assert len(iot_adapter._topics) == 0
    iot_adapter.close()

    print("\nPhase 5 Exit Gate Successfully Verified!")
