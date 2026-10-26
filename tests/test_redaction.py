"""Regression tests for secret redaction at provider and UI error boundaries."""

from unittest.mock import MagicMock

import pytest

from core.redaction import redact_text
from providers.groq_provider import GroqProvider
from ui.chat_controller import ChatTurnPreparation, ChatTurnService


def test_redact_text_scrubs_known_api_keys_and_bearer_tokens() -> None:
    secret = "gsk_live_abcdefghijklmnopqrstuvwxyz"
    raw = f"upstream failed with key={secret}; Authorization: Bearer sk-proj-abcdefghijklmnop"

    scrubbed = redact_text(raw, extra_secrets=(secret,))

    assert secret not in scrubbed
    assert "sk-proj-abcdefghijklmnop" not in scrubbed
    assert "[REDACTED]" in scrubbed


def test_groq_provider_redacts_api_key_from_wrapped_error() -> None:
    secret = "gsk_live_abcdefghijklmnopqrstuvwxyz"
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError(f"401 invalid API key {secret}")

    provider = GroqProvider(api_key=secret, user_consented=True)
    provider._client = mock_client

    with pytest.raises(RuntimeError) as exc_info:
        provider.generate_text("test")

    assert secret not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_chat_error_result_redacts_secret_before_storage() -> None:
    secret = "gsk_live_abcdefghijklmnopqrstuvwxyz"
    preparation = ChatTurnPreparation(
        prompt="question",
        history=[],
        search_query="question",
        doc_filter=None,
        retrieval_scope=None,
        retrieval_result=None,
        sources=["alpha.pdf"],
        snippets=[],
        intent_mismatch=False,
        chunk_cap_reached=False,
    )
    service = ChatTurnService(lambda text, retrieval: None)

    result = service.error_result(
        preparation,
        RuntimeError(f"stream failed for key {secret}"),
        is_cloud=True,
        model_name="cloud-model",
    )

    assert secret not in result.error_message
    assert secret not in result.assistant_turn["content"]
    assert "[REDACTED]" in result.error_message
    assert result.assistant_turn["sources"] == ["alpha.pdf"]
