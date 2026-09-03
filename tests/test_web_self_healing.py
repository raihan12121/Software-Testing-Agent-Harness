"""Unit tests for WebAdapter Locator Self-Healing (P3 item 13)."""

from unittest.mock import MagicMock

from sentinel.adapters.web_adapter.adapter import (
    HealedLocatorProposal,
    WebAdapter,
)
from sentinel.core.config import TargetConfig
from sentinel.core.schemas import TestStep
from sentinel.llm.provider import LLMUsageMetrics, MockLLMProvider


class StubSelfHealingLLMProvider(MockLLMProvider):
    """Stub provider returning a deterministic healed locator proposal."""

    def __init__(self, proposed_locator: str = "button[name='Sign In']", confidence: float = 0.92) -> None:
        super().__init__()
        self.proposal = HealedLocatorProposal(
            original_locator="#old-login-btn",
            proposed_locator=proposed_locator,
            confidence=confidence,
            reasoning="Found button element matching 'Sign In' intent in accessibility tree.",
            matched_role="button",
        )

    def generate_structured(self, prompt, response_model, system_prompt=None):
        metrics = LLMUsageMetrics(prompt_hash="heal_123", model="mock-claude", latency_ms=10)
        return self.proposal, metrics


def test_web_adapter_self_healing_generates_diff_proposal():
    """Verify that when a selector fails, WebAdapter uses accessibility snapshot and LLM to propose a diff."""
    config = TargetConfig(target_type="web", name="WebApp", base_url="http://localhost:3000")
    healing_provider = StubSelfHealingLLMProvider(proposed_locator="button[name='Sign In']", confidence=0.88)
    adapter = WebAdapter(config, llm_provider=healing_provider)

    mock_page = MagicMock()
    mock_page.accessibility.snapshot.return_value = {
        "role": "WebArea",
        "name": "Login",
        "children": [
            {"role": "button", "name": "Sign In", "value": ""},
            {"role": "textbox", "name": "Username", "value": ""},
        ],
    }
    # Cause click to fail with locator error
    mock_page.click.side_effect = TimeoutError("Timeout 5000ms exceeded waiting for #old-login-btn")
    adapter._page = mock_page

    step = TestStep(
        action="click",
        path="#old-login-btn",
        metadata={"test_id": "TC-WEB-HEAL-01", "intent": "Click sign-in button"},
    )

    # Execute action implementation
    obs = adapter._execute_action_impl(step)

    # 1. Action was intercepted and not silently passed or hard-errored
    assert obs.raw_result.get("needs_human_review") is True
    assert "LOCATOR_FAILED_HEALED_FOR_REVIEW" in obs.error

    # 2. Healed proposal recorded with confidence and proposed locator
    proposal_data = obs.raw_result["healed_proposal"]
    assert proposal_data["proposed_locator"] == "button[name='Sign In']"
    assert proposal_data["confidence"] == 0.88
    assert "Found button element" in proposal_data["reasoning"]

    # 3. Diff artifact generated for human review per rules.md
    assert len(obs.artifacts) >= 1
    diff_artifact = obs.artifacts[0]
    assert diff_artifact.mime_type == "text/x-diff"
    assert "button[name='Sign In']" in diff_artifact.metadata["proposed"]


def test_web_adapter_self_healing_low_confidence_raises_exception():
    """Verify that if self-healing confidence is below 0.70, it does not propose a diff and raises error."""
    config = TargetConfig(target_type="web", name="WebApp")
    low_confidence_provider = StubSelfHealingLLMProvider(proposed_locator="#random-div", confidence=0.45)
    adapter = WebAdapter(config, llm_provider=low_confidence_provider)

    mock_page = MagicMock()
    mock_page.accessibility.snapshot.return_value = None
    mock_page.click.side_effect = TimeoutError("Element not found")
    adapter._page = mock_page

    step = TestStep(action="click", path="#missing-elem", metadata={"test_id": "TC-WEB-FAIL-01"})

    obs = adapter._execute_action_impl(step)
    # Surfaced as standard exception observation
    assert "WEB_EXECUTION_EXCEPTION" in obs.error
    assert "healed_proposal" not in obs.raw_result
