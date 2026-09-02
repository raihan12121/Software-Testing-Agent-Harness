"""Unit tests for Scoped Security Test Generator."""

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.generator.security_generator import SecurityTestGenerator


def test_security_generator_r_safe_probes():
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    target_model = parser.parse()

    sec_gen = SecurityTestGenerator()
    sec_tests = sec_gen.generate_security_suite(target_model)

    assert len(sec_tests) > 0

    tags_set = {t for tc in sec_tests for t in tc.tags}
    assert "security" in tags_set
    assert "injection" in tags_set
    assert "bola" in tags_set
    assert "info_leak" in tags_set

    # Verify R-SAFE guardrails: all generated tests assert rejection and no unhandled 500
    for tc in sec_tests:
        assert tc.priority in ("high", "critical")
        assert tc.generated_by == "security_generator"
        assertions_joined = " ".join(tc.expected.assertions)
        assert "status_code" in assertions_joined
        if "injection" in tc.tags or "info_leak" in tc.tags:
            assert "status_code != 500" in tc.expected.assertions
