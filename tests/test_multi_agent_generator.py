"""Unit tests for Collaborative Multi-Agent Generation (architecture.md §5)."""

from sentinel.adapters.api_adapter.parser import OpenAPIParser
from sentinel.generator.multi_agent import AdversarialAgent, FunctionalAgent, MultiAgentGenerator


def test_multi_agent_collaborative_generation():
    parser = OpenAPIParser.from_file("examples/petstore_spec.yaml")
    target_model = parser.parse()

    func_agent = FunctionalAgent()
    adv_agent = AdversarialAgent()
    generator = MultiAgentGenerator()

    func_suite = func_agent.generate(target_model)
    adv_suite = adv_agent.generate(target_model)
    collab_suite = generator.generate_collaborative_suite(target_model)

    # 1. Functional suite generates core happy-path tests
    assert len(func_suite) > 0
    assert all("functional" in tc.tags for tc in func_suite)

    # 2. Adversarial suite generates security & boundary tests
    assert len(adv_suite) > 0
    assert any("security" in tc.tags for tc in adv_suite)
    assert any("boundary" in tc.tags for tc in adv_suite)

    # 3. Measurable coverage gain: Collaborative suite has higher scenario diversity
    assert len(collab_suite) > len(func_suite)
    tags_in_collab = {tag for tc in collab_suite for tag in tc.tags}
    assert "functional" in tags_in_collab
    assert "security" in tags_in_collab
    assert "boundary" in tags_in_collab
