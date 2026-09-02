"""Unit tests for the test executor."""

from sentinel.adapters.stub import StubAdapter
from sentinel.core.config import RunConfig, TargetConfig
from sentinel.core.schemas import ExpectedResult, TestCase, TestStep
from sentinel.executor.executor import Executor


def test_executor_blocks_mutation_when_disallowed():
    target_conf = TargetConfig(target_type="stub", name="stub")
    run_conf = RunConfig(run_id="run-1", environment="local", allow_mutations=False)

    executor = Executor(target_conf, run_conf)
    adapter = StubAdapter()

    tc = TestCase(
        id="TC-MUT-1",
        target_type="stub",
        title="Mutating action without permission",
        steps=[TestStep(action="delete_item", path="/item/123")],
        expected=ExpectedResult(oracle="deterministic"),
        mutating=True,
    )

    obs, retries = executor.execute_test(adapter, tc)
    assert obs.error is not None
    assert "BLOCKED_BY_POLICY" in obs.error
    assert retries == 0


def test_executor_executes_allowed_mutation():
    target_conf = TargetConfig(target_type="stub", name="stub")
    run_conf = RunConfig(run_id="run-1", environment="local", allow_mutations=True)

    executor = Executor(target_conf, run_conf)
    adapter = StubAdapter()

    tc = TestCase(
        id="TC-MUT-2",
        target_type="stub",
        title="Mutating action with permission",
        steps=[TestStep(action="delete_item", path="/item/123")],
        expected=ExpectedResult(oracle="deterministic"),
        mutating=True,
    )

    obs, retries = executor.execute_test(adapter, tc)
    assert obs.error is None
    assert retries == 0


def test_executor_retry_and_timeout():
    target_conf = TargetConfig(target_type="stub", name="stub")
    run_conf = RunConfig(run_id="run-1", environment="local", retry_budget=1, timeout_seconds=0.2)

    executor = Executor(target_conf, run_conf)
    adapter = StubAdapter()

    # Test step that simulates delay exceeding timeout
    tc = TestCase(
        id="TC-TIME-1",
        target_type="stub",
        title="Timeout test",
        steps=[
            TestStep(
                action="slow_call",
                timeout_seconds=0.1,
                metadata={"simulated_delay_seconds": 0.5},
            )
        ],
        expected=ExpectedResult(oracle="deterministic"),
    )

    obs, retries = executor.execute_test(adapter, tc)
    assert obs.error is not None
    assert "TIMEOUT" in obs.error
    assert retries == 1  # Exhausted 1 retry
