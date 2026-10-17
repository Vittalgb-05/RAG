"""Unit tests for GroqProvider cloud adapter."""

from unittest.mock import MagicMock, patch
import pytest

from groq_provider import GroqProvider
from model_provider import HealthStatus, ProviderCapabilities


def test_groq_capabilities():
    """Verify provider capabilities schema for Groq cloud."""
    provider = GroqProvider(api_key="gsk_test123", model_name="llama-3.3-70b-versatile", context_window=128000)
    caps = provider.get_capabilities()

    assert isinstance(caps, ProviderCapabilities)
    assert caps.model_name == "llama-3.3-70b-versatile"
    assert caps.context_window == 128000
    assert caps.supports_vision is False
    assert caps.is_local is False
    assert caps.supports_streaming is True


def test_groq_health_without_key():
    """Verify unreachable health status when no API key is provided."""
    with patch.dict("os.environ", {}, clear=True):
        provider = GroqProvider(api_key=None)
        health = provider.check_health()
        assert isinstance(health, HealthStatus)
        assert health.status == "unreachable"
        assert "GROQ_API_KEY" in health.message


def test_groq_health_with_key():
    """Verify healthy status when API key and mock client are initialized."""
    mock_client = MagicMock()
    with patch("groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider(api_key="gsk_test_mock")
        health = provider.check_health()
        assert health.status == "healthy"
        assert "ready" in health.message


def test_groq_generate_text_success():
    """Verify synchronous generation via Groq client."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Groq generated answer."
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    with patch("groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider(api_key="gsk_test_mock")
        res = provider.generate_text("Explain quantum computing.", system_prompt="You are a physicist.")

        assert res == "Groq generated answer."
        mock_client.chat.completions.create.assert_called_once()
        args = mock_client.chat.completions.create.call_args[1]
        assert len(args["messages"]) == 2
        assert args["messages"][0]["role"] == "system"
        assert args["messages"][1]["content"] == "Explain quantum computing."


def test_groq_stream_text_success():
    """Verify token streaming via Groq client."""
    mock_client = MagicMock()
    chunk1 = MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello "))])
    chunk2 = MagicMock(choices=[MagicMock(delta=MagicMock(content="world!"))])
    mock_client.chat.completions.create.return_value = iter([chunk1, chunk2])

    with patch("groq_provider.Groq", return_value=mock_client):
        provider = GroqProvider(api_key="gsk_test_mock")
        tokens = list(provider.stream_text("Say hello"))

        assert tokens == ["Hello ", "world!"]


def test_groq_uninitialized_client_raises():
    """Verify that generate and stream raise RuntimeError if client is not configured."""
    with patch.dict("os.environ", {}, clear=True):
        provider = GroqProvider(api_key=None)
        with pytest.raises(RuntimeError, match="Groq client is not configured"):
            provider.generate_text("Hello")

        with pytest.raises(RuntimeError, match="Groq client is not configured"):
            list(provider.stream_text("Hello"))


def test_groq_analyze_image_unsupported():
    """Verify that multimodal image analysis raises NotImplementedError on text models."""
    provider = GroqProvider(api_key="gsk_mock")
    with pytest.raises(NotImplementedError, match="does not support image analysis"):
        provider.analyze_image(b"fake_image_bytes", prompt="Describe this image")
