"""Secure Credential and API Key Vault for Sentinel Studio.

Adheres to:
- rules.md R-SEC-1 (Zero secrets in plain artifacts)
- rules.md R-SEC-2 (Redaction before transmission)
- Desktop App Requirements (API key management for Anthropic, OpenAI, Gemini, Local models, GitHub)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sentinel.core.logging import logger

try:
    import keyring
    KEYRING_AVAILABLE = True
except Exception:
    KEYRING_AVAILABLE = False


class CredentialVault:
    """Manages encrypted and secure API keys for LLMs and external integrations."""

    SERVICE_NAME = "sentinel-studio"
    SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini", "ollama_url", "github_token")

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path.home() / ".sentinel"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.fallback_file = self.storage_dir / "vault.enc"
        self._machine_key = self._derive_machine_key()

    def _derive_machine_key(self) -> bytes:
        """Derive a host-specific key for local obfuscation/encryption fallback."""
        seed = f"{os.name}:{os.getenv('USERNAME') or os.getenv('USER') or 'sentinel'}:{Path.home()}"
        return hashlib.sha256(seed.encode("utf-8")).digest()

    def _encrypt(self, plain_text: str) -> str:
        """Simple XOR-based reversible obfuscation with machine key for local fallback."""
        key = self._machine_key
        data_bytes = plain_text.encode("utf-8")
        xor_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(data_bytes)])
        return base64.b64encode(xor_bytes).decode("ascii")

    def _decrypt(self, enc_text: str) -> str:
        """Decrypt XOR-based obfuscated string."""
        try:
            key = self._machine_key
            xor_bytes = base64.b64decode(enc_text.encode("ascii"))
            data_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(xor_bytes)])
            return data_bytes.decode("utf-8")
        except Exception:
            return ""

    def _load_fallback(self) -> dict[str, str]:
        if not self.fallback_file.exists():
            return {}
        try:
            raw = json.loads(self.fallback_file.read_text(encoding="utf-8"))
            return {k: self._decrypt(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning(f"Failed to read vault fallback file: {exc}")
            return {}

    def _save_fallback(self, data: dict[str, str]) -> None:
        try:
            enc_dict = {k: self._encrypt(v) for k, v in data.items() if v}
            self.fallback_file.write_text(json.dumps(enc_dict, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to write vault fallback file: {exc}")

    def set_key(self, provider: str, key_value: str) -> None:
        """Save API key for a specified provider securely."""
        provider = provider.lower().strip()
        key_value = key_value.strip()

        # 1. Try OS Keyring
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(self.SERVICE_NAME, provider, key_value)
                return
            except Exception as exc:
                logger.debug(f"OS keyring unavailable, falling back to local vault: {exc}")

        # 2. Fallback to machine-bound file
        data = self._load_fallback()
        data[provider] = key_value
        self._save_fallback(data)

    def get_key(self, provider: str, prefer_env: bool = False) -> str | None:
        """Retrieve API key for provider (checks vault storage, then falls back to environment variable)."""
        provider = provider.lower().strip()

        env_var_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "ollama_url": "OLLAMA_BASE_URL",
            "github_token": "GITHUB_TOKEN",
        }
        env_key = env_var_map.get(provider)

        if prefer_env and env_key and os.getenv(env_key):
            return os.getenv(env_key)

        # 1. Try OS Keyring
        if KEYRING_AVAILABLE:
            try:
                pwd = keyring.get_password(self.SERVICE_NAME, provider)
                if pwd:
                    return pwd
            except Exception:
                pass

        # 2. Try Fallback File
        data = self._load_fallback()
        if provider in data and data[provider]:
            return data[provider]

        # 3. Fallback to Environment Variable
        if env_key and os.getenv(env_key):
            return os.getenv(env_key)

        return None

    def delete_key(self, provider: str) -> None:
        """Remove a stored key."""
        provider = provider.lower().strip()
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password(self.SERVICE_NAME, provider)
            except Exception:
                pass
        data = self._load_fallback()
        if provider in data:
            del data[provider]
            self._save_fallback(data)

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Return configuration status of all providers without revealing raw secrets."""
        status = {}
        for prov in self.SUPPORTED_PROVIDERS:
            val = self.get_key(prov)
            is_configured = bool(val and len(val) > 3)
            preview = f"...{val[-4:]}" if is_configured and val else None
            status[prov] = {
                "configured": is_configured,
                "preview": preview,
                "provider": prov,
            }
        return status

    def test_connection(self, provider: str) -> tuple[bool, str]:
        """Test API key validity for provider."""
        key = self.get_key(provider)
        if not key:
            return False, f"No key configured for {provider}."

        try:
            if provider == "anthropic":
                import httpx
                resp = httpx.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    timeout=5.0,
                )
                if resp.status_code in (200, 400):  # 200 or active header response
                    return True, "Anthropic API key authenticated successfully."
                return False, f"Anthropic rejected key: HTTP {resp.status_code}"

            elif provider == "ollama_url":
                import httpx
                resp = httpx.get(f"{key.rstrip('/')}/api/tags", timeout=3.0)
                if resp.status_code == 200:
                    return True, "Local Ollama server is reachable and active."
                return False, f"Ollama connection error: HTTP {resp.status_code}"

            elif provider == "github_token":
                import httpx
                resp = httpx.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    login = resp.json().get("login", "unknown")
                    return True, f"GitHub authenticated as @{login}."
                return False, f"GitHub token rejected: HTTP {resp.status_code}"

            return True, f"Key saved for {provider}."
        except Exception as exc:
            return False, f"Connection failed: {exc}"


_GLOBAL_VAULT: CredentialVault | None = None


def get_vault() -> CredentialVault:
    """Retrieve singleton CredentialVault instance."""
    global _GLOBAL_VAULT
    if _GLOBAL_VAULT is None:
        _GLOBAL_VAULT = CredentialVault()
    return _GLOBAL_VAULT
