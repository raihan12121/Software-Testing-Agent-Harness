"""Unit tests for APIAdapter and OpenAPIParser."""

from sentinel.adapters.api_adapter.adapter import APIAdapter
from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep


def test_openapi_parser_endpoints():
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    model = parser.parse()

    assert model.target_type == "api"
    assert len(model.endpoints) >= 6
    paths = [ep["path"] for ep in model.endpoints]
    assert "/health" in paths
    assert "/users" in paths
    assert "/users/{id}" in paths
    assert "/orders" in paths


def test_api_adapter_host_allowlist_blocking():
    """Verify R-SAFE-5: Attempts to reach unlisted hosts are blocked."""
    config = TargetConfig(
        target_type="api",
        name="test-api",
        allowed_hosts=["localhost", "127.0.0.1"],
    )
    adapter = APIAdapter(config)

    step = TestStep(
        action="http_request",
        method="GET",
        path="/malicious",
        metadata={"base_url": "http://evil-unlisted-host.com"},
    )
    obs = adapter.execute_action(step)

    assert obs.error is not None
    assert "SECURITY_BLOCK" in obs.error
    assert "evil-unlisted-host.com" in obs.error


def test_api_adapter_discover_fallback():
    config = TargetConfig(target_type="api", name="no-spec", base_url="http://example.com")
    adapter = APIAdapter()
    model = adapter.discover(config)
    assert model.name == "no-spec"
    assert len(model.endpoints) == 0
