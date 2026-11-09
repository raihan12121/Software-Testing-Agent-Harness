"""LLM Provider abstraction and implementations.

Adheres to:
- TRD.md §2.2 (LLM Integration)
- rules.md R-SEC-2 (Redaction before LLM)
- rules.md R-BUILD-3 (Every LLM call is logged with cost/latency)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Literal, Protocol, TypeVar, get_args, get_origin, runtime_checkable

import anthropic
import httpx
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
            origin = get_origin(annotation)
            args = get_args(annotation)

            # Assign appropriate dummy data based on name and type
            if origin is Literal and args:
                fields_data[name] = args[0]
            elif name.lower() == "verdict":
                fields_data[name] = "pass"
            elif name.lower() == "confidence":
                fields_data[name] = 0.95
            elif "reasoning" in name.lower() or "rationale" in name.lower():
                fields_data[name] = f"Synthesized reasoning: criteria satisfied for prompt {prompt_hash}."
            elif "title" in name.lower() or "summary" in name.lower():
                fields_data[name] = f"Synthesized test for {prompt_hash}"
            elif name.lower() == "id" or name.lower().endswith("_id"):
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
            elif annotation in (float, float | None) or origin in (float,):
                fields_data[name] = 0.95
            elif annotation in (int, int | None) or origin in (int,):
                fields_data[name] = 1
            elif annotation in (bool, bool | None):
                fields_data[name] = True
            elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
                # Recurse for nested model
                nested_data = {}
                for sub_k, sub_f in annotation.model_fields.items():
                    sub_origin = get_origin(sub_f.annotation)
                    sub_args = get_args(sub_f.annotation)
                    if sub_origin is Literal and sub_args:
                        nested_data[sub_k] = sub_args[0]
                    elif "oracle" in sub_k:
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

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Deterministic text generation for general prompts."""
        clean_prompt = self.redactor.redact_text(prompt)
        return json.dumps({
            "thought": "Probing interactive application flow via Set-of-Marks indexed badges.",
            "action": "click",
            "target": 1,
            "assertion": "status_code == 200",
        })


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

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        """Text generation via Claude."""
        clean_prompt = self.redactor.redact_text(prompt)
        sys_prompt = self.redactor.redact_text(system_prompt or "You are a QA automation agent.")
        resp = self.client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=sys_prompt,
            messages=[{"role": "user", "content": clean_prompt}],
        )
        for block in resp.content:
            if getattr(block, "text", None):
                return block.text
        return ""


class OpenAILLMProvider(LLMProvider):
    """Production LLM Provider powered by OpenAI (GPT-4o, GPT-4o-mini)."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("OPENAI_MODEL") or "gpt-4o"
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured (R-SEC-1).")
        self.client = httpx.Client(timeout=45.0)
        self.redactor = default_redactor

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        clean_prompt = self.redactor.redact_text(prompt)
        sys_prompt = self.redactor.redact_text(system_prompt or "You are a senior QA automation engineer.")
        resp = self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": clean_prompt},
                ],
                "temperature": 0.2,
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenAI API error {resp.status_code}: {resp.text}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        start_time = time.perf_counter()
        clean_prompt = self.redactor.redact_text(prompt)
        prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()[:12]
        schema = response_model.model_json_schema()
        sys_prompt = self.redactor.redact_text(
            system_prompt or f"You are a senior QA engineer. Output valid JSON adhering to schema: {json.dumps(schema)}"
        )

        resp = self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": clean_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if resp.status_code != 200:
            raise ValueError(f"OpenAI API error {resp.status_code}: {resp.text}")
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        instance = response_model.model_validate_json(content)
        usage = data.get("usage", {})
        in_tokens = usage.get("prompt_tokens", 0)
        out_tokens = usage.get("completion_tokens", 0)
        cost_usd = (in_tokens * 2.50 + out_tokens * 10.00) / 1_000_000.0

        metrics = LLMUsageMetrics(
            prompt_hash=prompt_hash,
            model=self.model_name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            latency_ms=elapsed_ms,
            estimated_cost_usd=round(cost_usd, 6),
        )
        return instance, metrics


class GeminiLLMProvider(LLMProvider):
    """Production LLM Provider powered by Google Gemini (Gemini 1.5 Pro / Flash)."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("GEMINI_MODEL") or "gemini-1.5-flash"
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured (R-SEC-1).")
        self.client = httpx.Client(timeout=45.0)
        self.redactor = default_redactor

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        clean_prompt = self.redactor.redact_text(prompt)
        sys_prompt = self.redactor.redact_text(system_prompt or "You are a QA automation agent.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        resp = self.client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": sys_prompt}]},
                "contents": [{"parts": [{"text": clean_prompt}]}],
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"Gemini API error {resp.status_code}: {resp.text}")
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates and "content" in candidates[0]:
            return candidates[0]["content"]["parts"][0]["text"]
        return ""

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        start_time = time.perf_counter()
        clean_prompt = self.redactor.redact_text(prompt)
        prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()[:12]
        schema = response_model.model_json_schema()
        sys_prompt = self.redactor.redact_text(
            system_prompt or f"You are a QA automation agent. Output JSON adhering to schema: {json.dumps(schema)}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        resp = self.client.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": sys_prompt}]},
                "contents": [{"parts": [{"text": clean_prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"},
            },
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if resp.status_code != 200:
            raise ValueError(f"Gemini API error {resp.status_code}: {resp.text}")
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        instance = response_model.model_validate_json(text)
        usage = data.get("usageMetadata", {})
        in_tokens = usage.get("promptTokenCount", 0)
        out_tokens = usage.get("candidatesTokenCount", 0)
        cost_usd = (in_tokens * 0.35 + out_tokens * 1.05) / 1_000_000.0

        metrics = LLMUsageMetrics(
            prompt_hash=prompt_hash,
            model=self.model_name,
            prompt_tokens=in_tokens,
            completion_tokens=out_tokens,
            latency_ms=elapsed_ms,
            estimated_cost_usd=round(cost_usd, 6),
        )
        return instance, metrics


class OllamaLLMProvider(LLMProvider):
    """Local / Private LLM Provider powered by Ollama or vLLM."""

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL") or "llama3.2"
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
        self.client = httpx.Client(timeout=90.0)
        self.redactor = default_redactor

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        clean_prompt = self.redactor.redact_text(prompt)
        sys_prompt = self.redactor.redact_text(system_prompt or "You are a QA automation agent.")
        resp = self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": clean_prompt},
                ],
                "stream": False,
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"Ollama API error {resp.status_code}: {resp.text}")
        return resp.json()["message"]["content"]

    def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str | None = None,
    ) -> tuple[T, LLMUsageMetrics]:
        start_time = time.perf_counter()
        clean_prompt = self.redactor.redact_text(prompt)
        prompt_hash = hashlib.sha256(clean_prompt.encode("utf-8")).hexdigest()[:12]
        schema = response_model.model_json_schema()
        sys_prompt = self.redactor.redact_text(
            system_prompt or f"You are a QA engineer. Return strictly JSON matching: {json.dumps(schema)}"
        )

        resp = self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": clean_prompt},
                ],
                "format": "json",
                "stream": False,
            },
        )
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        if resp.status_code != 200:
            raise ValueError(f"Ollama API error {resp.status_code}: {resp.text}")
        data = resp.json()
        content = data["message"]["content"]
        instance = response_model.model_validate_json(content)

        metrics = LLMUsageMetrics(
            prompt_hash=prompt_hash,
            model=self.model_name,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            latency_ms=elapsed_ms,
            estimated_cost_usd=0.0,
        )
        return instance, metrics


def get_llm_provider(
    provider_type: str = "auto",
    model_name: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    """Resolve and return an LLM provider based on configuration, vault, or environment (R-BUILD-3)."""
    p_type = provider_type.lower()
    resolved_model = (
        model_name
        or os.environ.get("SENTINEL_LLM_MODEL")
        or os.environ.get("ANTHROPIC_MODEL")
    )

    if p_type == "mock":
        return MockLLMProvider(model_name=resolved_model or "mock-claude-3-5-sonnet")

    if p_type == "anthropic":
        return AnthropicLLMProvider(model_name=resolved_model or DEFAULT_ANTHROPIC_MODEL, api_key=api_key)

    if p_type == "openai":
        return OpenAILLMProvider(model_name=resolved_model or "gpt-4o", api_key=api_key)

    if p_type == "gemini":
        return GeminiLLMProvider(model_name=resolved_model or "gemini-1.5-flash", api_key=api_key)

    if p_type in ("ollama", "local"):
        return OllamaLLMProvider(model_name=resolved_model or "llama3.2", base_url=api_key)

    # Auto: Check Vault first, then Environment variables
    try:
        from sentinel.vault.manager import get_vault
        vault = get_vault()

        # 1. Anthropic Claude
        ant_key = api_key or vault.get_key("anthropic")
        if ant_key and ant_key != "ollama":
            return AnthropicLLMProvider(model_name=resolved_model or DEFAULT_ANTHROPIC_MODEL, api_key=ant_key)

        # 2. OpenAI
        oai_key = vault.get_key("openai")
        if oai_key:
            return OpenAILLMProvider(model_name=resolved_model or "gpt-4o", api_key=oai_key)

        # 3. Google Gemini
        gem_key = vault.get_key("gemini")
        if gem_key:
            return GeminiLLMProvider(model_name=resolved_model or "gemini-1.5-flash", api_key=gem_key)

        # 4. Local Ollama
        ollama_url = vault.get_key("ollama_url")
        if ollama_url:
            return OllamaLLMProvider(model_name=resolved_model or "llama3.2", base_url=ollama_url)
    except Exception:
        pass

    # 5. Environment check fallback
    if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("ANTHROPIC_API_KEY") != "ollama":
        return AnthropicLLMProvider(model_name=resolved_model or DEFAULT_ANTHROPIC_MODEL)
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAILLMProvider(model_name=resolved_model or "gpt-4o")
    if os.environ.get("GEMINI_API_KEY"):
        return GeminiLLMProvider(model_name=resolved_model or "gemini-1.5-flash")

    return MockLLMProvider(model_name=resolved_model or "mock-claude-3-5-sonnet")
