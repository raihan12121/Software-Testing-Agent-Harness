"""Standard Adapter Conformance Test Suite.

Adheres strictly to:
- rules.md R-BUILD-4 (New adapters require a conformance test suite)
- TRD.md §3.1 (TargetAdapter Protocol contract)
"""

from sentinel.adapters.api_adapter import APIAdapter
from sentinel.adapters.base import TargetAdapter
from sentinel.adapters.stub import StubAdapter
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import Observation, TargetModel, TestStep


class ConformanceSuiteBase:
    """Base conformance checks that any TargetAdapter MUST satisfy."""

    def get_adapter(self) -> TargetAdapter:
        raise NotImplementedError

    def get_valid_config(self) -> TargetConfig:
        raise NotImplementedError

    def get_valid_step(self) -> TestStep:
        raise NotImplementedError

    def test_discover_contract(self):
        """discover() must return a valid TargetModel with target_type and endpoints."""
        adapter = self.get_adapter()
        config = self.get_valid_config()
        model = adapter.discover(config)

        assert isinstance(model, TargetModel)
        assert model.target_type == config.target_type
        assert isinstance(model.endpoints, list)
        assert isinstance(model.metadata, dict)

    def test_execute_action_contract(self):
        """execute_action() must return a structured Observation without throwing unhandled exceptions."""
        adapter = self.get_adapter()
        step = self.get_valid_step()
        obs = adapter.execute_action(step)

        assert isinstance(obs, Observation)
        assert isinstance(obs.raw_result, dict)
        assert isinstance(obs.artifacts, list)
        assert isinstance(obs.duration_ms, int)
        assert obs.duration_ms >= 0

    def test_capture_artifacts_contract(self):
        """capture_artifacts() must return a list of Artifact instances."""
        adapter = self.get_adapter()
        obs = Observation(test_id="TC-CONF", raw_result={}, duration_ms=10)
        artifacts = adapter.capture_artifacts(obs)
        assert isinstance(artifacts, list)

    def test_reset_state_contract(self):
        """reset_state() must execute cleanly without crashing."""
        adapter = self.get_adapter()
        config = self.get_valid_config()
        adapter.reset_state(config)


class TestStubAdapterConformance(ConformanceSuiteBase):
    """Validate StubAdapter against conformance suite."""

    def get_adapter(self) -> TargetAdapter:
        return StubAdapter()

    def get_valid_config(self) -> TargetConfig:
        return TargetConfig(target_type="stub", name="stub-conf")

    def get_valid_step(self) -> TestStep:
        return TestStep(action="echo", path="/test")


class TestAPIAdapterConformance(ConformanceSuiteBase):
    """Validate APIAdapter against conformance suite (R-BUILD-4)."""

    def get_adapter(self) -> TargetAdapter:
        return APIAdapter()

    def get_valid_config(self) -> TargetConfig:
        return TargetConfig(
            target_type="api",
            name="api-conf",
            spec_path="examples/petstore_spec.yaml",
            base_url="http://127.0.0.1:8765",
            allowed_hosts=["127.0.0.1", "localhost"],
        )

    def get_valid_step(self) -> TestStep:
        return TestStep(
            action="http_request",
            method="GET",
            path="/health",
            timeout_seconds=5.0,
            metadata={"base_url": "http://127.0.0.1:8765"},
        )


class TestCLIAdapterConformance(ConformanceSuiteBase):
    """Validate CLIAdapter against conformance suite (R-BUILD-4)."""

    def get_adapter(self) -> TargetAdapter:
        from sentinel.adapters.cli_adapter import CLIAdapter
        return CLIAdapter()

    def get_valid_config(self) -> TargetConfig:
        return TargetConfig(target_type="cli", name="python")

    def get_valid_step(self) -> TestStep:
        return TestStep(action="cli_exec", path="python -c \"print('conformance_ok')\"")


class TestDatabaseAdapterConformance(ConformanceSuiteBase):
    """Validate DatabaseAdapter against conformance suite (R-BUILD-4)."""

    def get_adapter(self) -> TargetAdapter:
        from sentinel.adapters.db_adapter import DatabaseAdapter
        return DatabaseAdapter()

    def get_valid_config(self) -> TargetConfig:
        return TargetConfig(target_type="database", name="test-db", base_url=":memory:")

    def get_valid_step(self) -> TestStep:
        return TestStep(action="sql_query", path="SELECT 1 as val;")
