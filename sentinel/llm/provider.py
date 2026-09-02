"""LLM Provider abstraction and implementations.

Adheres to:
- TRD.md §2.2 (LLM Integration)
- rules.md R-SEC-2 (Redaction before LLM)
- rules.md R-BUILD-3 (Every LLM call is logged with cost/latency)
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Protocol, TypeVar, runtime_checkable

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
