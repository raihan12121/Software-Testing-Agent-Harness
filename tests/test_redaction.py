"""Unit tests for the secrets and PII redaction filter."""

from sentinel.core.redaction import RedactionFilter


def test_redact_bearer_token():
    filter_ = RedactionFilter()
    text = "Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.abc"
    redacted = filter_.redact_text(text)
    assert "Bearer [REDACTED:BEARER_TOKEN]" in redacted
    assert "eyJ" not in redacted


def test_redact_api_keys():
    filter_ = RedactionFilter()
    anthropic = "key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456"
    assert "[REDACTED:ANTHROPIC_API_KEY]" in filter_.redact_text(anthropic)

    openai = "key is sk-abcdefghijklmnopqrstuvwxyz123456"
    assert "[REDACTED:OPENAI_API_KEY]" in filter_.redact_text(openai)


def test_redact_custom_secret():
    filter_ = RedactionFilter(custom_secrets=["super_secret_db_pass_99"])
    text = "Connecting with pass super_secret_db_pass_99 to host"
    redacted = filter_.redact_text(text)
    assert "super_secret_db_pass_99" not in redacted
    assert "[REDACTED:CONFIG_SECRET]" in redacted


def test_redact_nested_dict():
    filter_ = RedactionFilter()
    payload = {
        "user": {
            "name": "Alice",
            "email": "alice@example.com",
            "password": "ClearPassword123!",
        },
        "auth_header": "Bearer my_super_token_12345",
        "api_key": "my_raw_key_here",
    }
    redacted = filter_.redact(payload)
    assert redacted["user"]["password"] == "[REDACTED:SENSITIVE_KEY]"
    assert redacted["api_key"] == "[REDACTED:SENSITIVE_KEY]"
    assert "[REDACTED:EMAIL]" in redacted["user"]["email"]
    assert "Bearer [REDACTED:BEARER_TOKEN]" in redacted["auth_header"]
