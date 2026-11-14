"""Unit tests for CloudState managing in-memory API keys, consent, and build-first swaps."""

from unittest.mock import MagicMock
import pytest
from pydantic import SecretStr

from api.cloud_state import CloudState


def test_cloud_state_initial_state():
    ai = MagicMock()
    cs = CloudState(ai)
    assert cs.enabled is False
    assert cs.consented is False
    assert cs.has_key("groq") is False


def test_cloud_state_enforce_consent():
    ai = MagicMock()
    cs = CloudState(ai)
    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        cs.apply(
            enabled=True,
            provider="groq",
            model="groq/llama-3.3-70b-versatile",
            consent=False,
            api_key="secret-key",
        )


def test_cloud_state_apply_stores_secret_and_swaps():
    ai = MagicMock()
    cs = CloudState(ai)

    warning = cs.apply(
        enabled=True,
        provider="groq",
        model="groq/llama-3.3-70b-versatile",
        consent=True,
        api_key="gsk_1234567890abcdef",
    )

    assert warning is None
    assert cs.enabled is True
    assert cs.consented is True
    assert cs.has_key("groq") is True
    assert isinstance(cs._keys["groq"], SecretStr)
    assert cs._keys["groq"].get_secret_value() == "gsk_1234567890abcdef"
    assert "1234567890" not in str(cs._keys["groq"])
    ai.swap_provider.assert_called_once()


def test_cloud_state_fallback_on_build_failure():
    ai = MagicMock()
    cs = CloudState(ai)

    # First swap fails, second swap (_to_local fallback) succeeds
    ai.swap_provider.side_effect = [RuntimeError("Failed to initialize backend client: raw_key_12345"), None]

    warning = cs.apply(
        enabled=True,
        provider="groq",
        model="groq/llama-3.3-70b-versatile",
        consent=True,
        api_key="raw_key_12345",
    )

    assert cs.enabled is False
    assert warning is not None
    # Verify sensitive error detail is redacted
    assert "raw_key_12345" not in warning


def test_cloud_state_revoke():
    ai = MagicMock()
    cs = CloudState(ai)

    cs.apply(
        enabled=True,
        provider="groq",
        model="groq/llama-3.3-70b-versatile",
        consent=True,
        api_key="gsk_secret",
    )
    assert cs.has_key("groq") is True
    assert cs.enabled is True

    cs.revoke()

    assert cs.enabled is False
    assert cs.consented is False
    assert cs.has_key("groq") is False
    assert len(cs._keys) == 0
