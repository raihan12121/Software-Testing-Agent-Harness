"""Unit and live eval tests for AnthropicLLMProvider and provider factory."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field

from sentinel.core.redaction import default_redactor
from sentinel.llm.provider import (
    AnthropicLLMProvider,
    MockLLMProvider,
    get_llm_provider,
)


class SampleEvaluationOutput(BaseModel):
    summary: str = Field(..., description="Summary text")
    score: int = Field(..., description="Evaluation score 1-100")


def test_provider_factory_resolution():
    """Test get_llm_provider returns MockLLMProvider when unconfigured or requested."""
    # When explicitly requesting mock
    mock_prov = get_llm_provider(provider_type="mock")
    assert isinstance(mock_prov, MockLLMProvider)


def test_anthropic_provider_requires_api_key(monkeypatch):
    """Test AnthropicLLMProvider raises ValueError if ANTHROPIC_API_KEY is missing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not configured"):
        AnthropicLLMProvider()


def test_prompt_redaction_before_transmission():
    """Test that default_redactor scrubs secrets from prompt before LLM invocation (R-SEC-2)."""
    prompt_with_secret = "Here is my secret token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID separators."
    redacted = default_redactor.redact_text(prompt_with_secret)
    assert "[REDACTED:BEARER_TOKEN]" in redacted
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted


def test_anthropic_provider_structured_generation_mocked(monkeypatch):
    """Test AnthropicLLMProvider generates structured output and usage metrics using mocked client."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-testkey-12345")
    provider = AnthropicLLMProvider()

    # Mock client messages.create response
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "SampleEvaluationOutput"
    mock_block.input = {"summary": "Great coverage", "score": 98}

    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_response.usage.input_tokens = 120
    mock_response.usage.output_tokens = 45

    provider.client.messages.create = MagicMock(return_value=mock_response)

    result, metrics = provider.generate_structured(
        prompt="Evaluate test: Bearer secret_token_abc",
        response_model=SampleEvaluationOutput,
        system_prompt="System prompt with Bearer secret_token_def",
    )

    # 1. Output conforms to Pydantic model
    assert isinstance(result, SampleEvaluationOutput)
    assert result.summary == "Great coverage"
    assert result.score == 98

    # 2. LLMUsageMetrics is populated with token and cost data per R-BUILD-3
    assert metrics.prompt_tokens == 120
    assert metrics.completion_tokens == 45
    assert metrics.estimated_cost_usd > 0.0

    # 3. Redaction filter ran before messages.create was called (R-SEC-2)
    called_kwargs = provider.client.messages.create.call_args.kwargs
    called_prompt = called_kwargs["messages"][0]["content"]
    assert "[REDACTED:BEARER_TOKEN]" in called_prompt
    assert "secret_token_abc" not in called_prompt


@pytest.mark.live_eval
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY") == "ollama",
    reason="Live test requires a genuine ANTHROPIC_API_KEY",
)
def test_anthropic_live_eval_structured_output():
    """Live eval: exercise AnthropicLLMProvider against real Claude API call (design.md §9)."""
    provider = AnthropicLLMProvider(model_name="claude-3-5-sonnet-20241022")
    prompt = "Please evaluate this test case with a summary and score 95: Bearer super_secret_12345"

    result, metrics = provider.generate_structured(
        prompt=prompt,
        response_model=SampleEvaluationOutput,
        system_prompt="Return structured evaluation.",
    )

    # Output conforms to Pydantic model
    assert isinstance(result, SampleEvaluationOutput)
    assert result.score > 0
    assert len(result.summary) > 0

    # LLMUsageMetrics is properly populated per R-BUILD-3
    assert metrics.model == "claude-3-5-sonnet-20241022"
    assert metrics.prompt_tokens > 0
    assert metrics.completion_tokens > 0
    assert metrics.latency_ms > 0
    assert metrics.estimated_cost_usd > 0.0
