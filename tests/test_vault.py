"""Unit tests for CredentialVault."""

import os
from pathlib import Path

from sentinel.vault.manager import CredentialVault


def test_vault_set_get_and_delete(tmp_path):
    vault = CredentialVault(storage_dir=tmp_path)

    # Set Anthropic key
    vault.set_key("anthropic", "sk-ant-test-key-123456789")
    val = vault.get_key("anthropic")
    assert val == "sk-ant-test-key-123456789"

    # Status check (should have preview and not expose raw key)
    status = vault.get_all_status()
    assert status["anthropic"]["configured"] is True
    assert status["anthropic"]["preview"] == "...6789"

    # Delete key
    vault.delete_key("anthropic")
    # Clean env var just in case
    old_env = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert vault.get_key("anthropic") is None
    finally:
        if old_env:
            os.environ["ANTHROPIC_API_KEY"] = old_env
