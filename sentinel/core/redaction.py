"""Secrets and PII Redaction Filter.

Complies with:
- rules.md R-SEC-1 (No secrets in generated artifacts)
- rules.md R-SEC-2 (Redaction before LLM)
- rules.md R-SEC-3 (Redaction before storage)
- rules.md R-SEC-4 (No PII in test data)
"""

from __future__ import annotations

import re
from typing import Any


class RedactionFilter:
    """Filter that detects and sanitizes sensitive data and secrets."""

    # Default regex patterns for common secrets and PII
    PATTERNS: dict[str, re.Pattern[str]] = {
        "BEARER_TOKEN": re.compile(r"(?i)\bBearer\s+([A-Za-z0-9\-._~+/]+=*)"),
        "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "ANTHROPIC_API_KEY": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        "OPENAI_API_KEY": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
        "GITHUB_TOKEN": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        "GENERIC_SECRET_KEY": re.compile(
            r'(?i)(["\']?(?:api[_-]?key|secret|password|passwd|auth[_-]?token|access[_-]?token)["\']?\s*[:=]\s*["\'])([^"\']+)(["\'])'
        ),
        "CREDIT_CARD": re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
        "EMAIL": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    }

    def __init__(self, custom_secrets: list[str] | None = None) -> None:
        """Initialize filter with optional list of known literal secrets."""
        self.custom_secrets: list[str] = [s for s in (custom_secrets or []) if s and len(s) > 3]

    def add_secret(self, secret: str) -> None:
        """Register a specific literal secret string to redact."""
        if secret and len(secret) > 3 and secret not in self.custom_secrets:
            self.custom_secrets.append(secret)

    def redact_text(self, text: str) -> str:
        """Redact secrets and sensitive information from a string."""
        if not text or not isinstance(text, str):
            return text

        redacted = text

        # 1. Redact known exact secret strings first
        for secret in self.custom_secrets:
            redacted = redacted.replace(secret, "[REDACTED:CONFIG_SECRET]")

        # 2. Redact key-value secrets preserving structure
        def _replace_kv(m: re.Match[str]) -> str:
            prefix, _, suffix = m.groups()
            return f"{prefix}[REDACTED:SECRET]{suffix}"

        redacted = self.PATTERNS["GENERIC_SECRET_KEY"].sub(_replace_kv, redacted)

        # 3. Redact Bearer tokens
        redacted = self.PATTERNS["BEARER_TOKEN"].sub("Bearer [REDACTED:BEARER_TOKEN]", redacted)

        # 4. Redact remaining regex patterns
        for name, pattern in self.PATTERNS.items():
            if name in ("GENERIC_SECRET_KEY", "BEARER_TOKEN"):
                continue
            redacted = pattern.sub(f"[REDACTED:{name}]", redacted)

        return redacted

    def redact(self, obj: Any) -> Any:
        """Recursively redact strings, dictionaries, lists, or pydantic models."""
        if obj is None:
            return None
        if isinstance(obj, str):
            return self.redact_text(obj)
        if isinstance(obj, dict):
            clean_dict: dict[str, Any] = {}
            for k, v in obj.items():
                # If the key itself looks like a secret/password, redact value completely
                if isinstance(k, str) and re.search(r"(?i)password|passwd|secret|api[_-]?key|token", k):
                    clean_dict[k] = "[REDACTED:SENSITIVE_KEY]"
                else:
                    clean_dict[k] = self.redact(v)
            return clean_dict
        if isinstance(obj, list):
            return [self.redact(item) for item in obj]
        if isinstance(obj, tuple):
            return tuple(self.redact(item) for item in obj)
        if hasattr(obj, "model_dump"):
            dumped = obj.model_dump()
            return self.redact(dumped)
        return obj


# Global default redactor instance
default_redactor = RedactionFilter()
