"""LLM Provider abstraction and implementations.

Adheres to:
- TRD.md §2.2 (LLM Integration)
- rules.md R-SEC-2 (Redaction before LLM)
- rules.md R-BUILD-3 (Every LLM call is logged with cost/latency)
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Protocol, TypeVar, runtime_checkable

import anthropic
from pydantic import BaseModel

from sentinel.core.logging import logger
from sentinel.core.redaction import default_redactor

T = TypeVar("T", bound=BaseModel)


class LLMUsageMetrics(BaseModel):
    """Instrumentation record for an LLM call per rules.md R-BUILD-3."""
    prompt_hash: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    estimated_cost_usd: float = 0.0


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for structured output LLM providers."""

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        """Generate a response constrained to a Pydantic schema."""
        ...


class MockLLMProvider(LLMProvider):
    """Deterministic Mock LLM Provider for unit testing and CI without external API keys."""

    def __init__(self, model_name: str = "mock-claude-3-5-sonnet") -> None:
        self.model_name = model_name
        self.call_history: list[dict[str, Any]] = []
        self.redactor = default_redactor

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        """Synthesize a valid instance of response_model deterministically."""
        start_time = time.perf_counter()

        # R-SEC-2: Redact sensitive information before processing
        clean_prompt = self.redactor.redact_text(prompt)
        prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()[:12]

        # Generate realistic default mock payload adhering to response_model fields
        fields_data: dict[str, Any] = {}
        for name, field in response_model.model_fields.items():
            annotation = field.annotation
            # Assign appropriate dummy data based on name and type
            if "title" in name.lower() or "summary" in name.lower():
                fields_data[name] = f"Synthesized test for {prompt_hash}"
            elif "id" in name.lower():
                fields_data[name] = f"SYN-{prompt_hash[:6]}"
            elif "priority" in name.lower():
                fields_data[name] = "high"
            elif "tags" in name.lower() or "preconditions" in name.lower() or "assertions" in name.lower():
                fields_data[name] = ["llm_augmented", "synthesized"]
            elif "steps" in name.lower() or "list" in str(annotation).lower():
                fields_data[name] = []
            elif "mutating" in name.lower():
                fields_data[name] = False
            elif "generated_by" in name.lower():
                fields_data[name] = self.model_name
            elif "oracle" in name.lower():
                fields_data[name] = "deterministic"
            elif "target_type" in name.lower():
                fields_data[name] = "api"
            elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
                # Recurse for nested model
                nested_data = {}
                for sub_k, sub_f in annotation.model_fields.items():
                    if "oracle" in sub_k:
                        nested_data[sub_k] = "deterministic"
                    elif "assertions" in sub_k:
                        nested_data[sub_k] = ["status_code == 200"]
                    else:
                        nested_data[sub_k] = None
                fields_data[name] = annotation.model_validate(nested_data)
            else:
                fields_data[name] = "synthesized_value"

        instance = response_model.model_validate(fields_data)
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        metrics = LLMUsageMetrics(
            prompt_hash=prompt_hash,
            model=self.model_name,
            prompt_tokens=len(clean_prompt) // 4,
            completion_tokens=len(str(fields_data)) // 4,
            latency_ms=elapsed_ms,
            estimated_cost_usd=0.0,
        )

        self.call_history.append({
            "prompt": clean_prompt,
            "system_prompt": system_prompt,
            "metrics": metrics,
        })
        logger.info(f"MockLLM call completed: hash={prompt_hash} latency={elapsed_ms}ms")
        return instance, metrics


DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"


class AnthropicLLMProvider(LLMProvider):
    """Production LLM Provider powered by Anthropic Claude tool calling.

    Adheres strictly to:
    - TRD.md §2.2 (Structured tool-calling outputs)
    - rules.md R-SEC-1/R-SEC-2 (API key from env, prompts redacted before transit)
    - rules.md R-BUILD-3 (Latency, tokens, and cost instrumentation)
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model_name = (
            model_name
            or os.environ.get("SENTINEL_LLM_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or DEFAULT_ANTHROPIC_MODEL
        )
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured. Set ANTHROPIC_API_KEY environment variable (R-SEC-1)."
            )
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.redactor = default_redactor

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        """Generate structured Pydantic object via Claude tool use with redaction & metrics."""
        start_time = time.perf_counter()

        # R-SEC-2: Redact sensitive information from prompt before transmission
        clean_prompt = self.redactor.redact_text(prompt)
        prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()[:12]

        tool_name = response_model.__name__
        tool_definition = {
            "name": tool_name,
            "description": f"Return structured {tool_name} matching schema",
            "input_schema": response_model.model_json_schema(),
        }

        sys_prompt = system_prompt or "You are an expert QA testing agent. Produce structured output adhering to the schema."
        sys_prompt = self.redactor.redact_text(sys_prompt)

        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=sys_prompt,
            messages=[{"role": "user", "content": clean_prompt}],
            tools=[tool_definition],
            tool_choice={"type": "tool", "name": tool_name},
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        parsed_data = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                parsed_data = block.input
                break

        if parsed_data is None:
            raise ValueError(f"Anthropic model {self.model_name} failed to generate valid {tool_name} tool call")

        instance = response_model.model_validate(parsed_data)

        in_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens
        # Estimated cost for Claude 3.5 Sonnet: $3.00/MTok in, $15.00/MTok out
        cost_usd = (in_tokens * 3.0 + out_tokens * 15.0) / 1_000_000.0

        metrics = LLMUsageMetrics(
            prompt_hash=prompt_hash,
            model=self.model_name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            latency_ms=elapsed_ms,
            estimated_cost_usd=round(cost_usd, 6),
        )

        logger.info(
            f"Anthropic call completed: model={self.model_name} hash={prompt_hash} "
            f"tokens={in_tokens}+{out_tokens} latency={elapsed_ms}ms cost=${cost_usd:.5f}"
        )
        return instance, metrics


def get_llm_provider(
    provider_type: str = "auto",
    model_name: str | None = None,
) -> LLMProvider:
    """Resolve and return an LLM provider based on configuration or environment (R-BUILD-3)."""
    resolved_model = (
        model_name
        or os.environ.get("SENTINEL_LLM_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
    )
    if provider_type == "mock":
        return MockLLMProvider(model_name=resolved_model or "mock-claude-3-5-sonnet")

    if provider_type == "anthropic":
        return AnthropicLLMProvider(model_name=resolved_model or DEFAULT_ANTHROPIC_MODEL)

    # Auto: use Anthropic if ANTHROPIC_API_KEY is available, otherwise Mock
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLMProvider(model_name=resolved_model or DEFAULT_ANTHROPIC_MODEL)

    return MockLLMProvider(model_name=resolved_model or "mock-claude-3-5-sonnet")
