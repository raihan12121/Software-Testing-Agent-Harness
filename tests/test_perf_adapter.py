"""Unit tests for Performance & Load Testing Adapter."""

from sentinel.adapters.perf_adapter.adapter import PerformanceAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_perf_adapter_discovery():
    config = TargetConfig(target_type="performance", name="BenchTarget")
    adapter = PerformanceAdapter(config)
    model = adapter.discover(config)

    assert model.target_type == "performance"
    assert len(model.endpoints) >= 2
    adapter.close()


def test_perf_adapter_load_test_execution_and_metrics():
    config = TargetConfig(target_type="performance", name="LoadTarget")
    adapter = PerformanceAdapter(config)

    step = TestStep(
        action="load_test",
        path="/health",
        params={"concurrency": 4, "iterations": 25},
    )
    obs = adapter.execute_action(step)

    assert obs.error is None
    res = obs.raw_result
    assert res["status_code"] == 200
    assert res["total_requests"] == 25
    assert res["concurrency"] == 4
    assert res["rps"] > 0
    assert "p50_ms" in res
    assert "p95_ms" in res
    assert "p99_ms" in res
    assert len(obs.artifacts) == 1
    assert obs.artifacts[0].mime_type == "application/json"

    adapter.close()


def test_perf_adapter_reset_state():
    config = TargetConfig(target_type="performance", name="ResetTarget")
    adapter = PerformanceAdapter(config)

    adapter.execute_action(TestStep(action="measure_latency", path="/health"))
    assert len(adapter._last_metrics) > 0

    adapter.reset_state(config)
    assert len(adapter._last_metrics) == 0
    adapter.close()
