"""Unit tests for LiteLLMProvider and cloud privacy consent gating (INF-04, UI-04)."""

from unittest.mock import MagicMock
import pytest

from providers.litellm_provider import LiteLLMProvider
from core.local_llm import AiModel
from providers.model_provider import BaseModelProvider


class MockChoice:
    def __init__(self, content: str) -> None:
        self.message = MagicMock(content=content)


class MockDelta:
    def __init__(self, content: str | None) -> None:
        self.delta = MagicMock(content=content)


class MockCompletionResponse:
    def __init__(self, content: str) -> None:
        self.choices = [MockChoice(content)]


def test_consent_gate_blocks_generation_by_default() -> None:
    """Verify that unconsented provider calls immediately raise PermissionError (INF-04, D1)."""
    provider = LiteLLMProvider(api_key="mock-key", user_consented=False)

    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        provider.generate_text("Explain quantum computing")

    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        list(provider.stream_text("Explain quantum computing"))

    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        provider.analyze_image(b"fake_image_bytes", "Describe image")


def test_consent_grant_allows_calls(monkeypatch) -> None:
    """Verify that granting consent via set_consent(True) allows generation to proceed."""
    provider = LiteLLMProvider(api_key="mock-key", user_consented=False)
    assert provider.user_consented is False

    provider.set_consent(True)
    assert provider.user_consented is True

    import litellm

    mock_completion = MagicMock(return_value=MockCompletionResponse("Consented response"))
    monkeypatch.setattr(litellm, "completion", mock_completion)

    res = provider.generate_text("Hello cloud")
    assert res == "Consented response"
    assert mock_completion.call_count == 1


def test_check_health_reports_unreachable_when_api_key_missing(monkeypatch) -> None:
    """Verify check_health reports unreachable when API key is not supplied or in environment."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("streamlit.secrets", {}, raising=False)

    provider = LiteLLMProvider(model_name="groq/llama-3.3-70b-versatile", api_key=None)
    health = provider.check_health()
    assert health.status == "unreachable"
    assert "Missing API key" in health.message


def test_check_health_reports_healthy_with_explicit_key() -> None:
    """Verify check_health reports healthy without making network calls when key is present."""
    provider = LiteLLMProvider(model_name="openai/gpt-4o-mini", api_key="sk-mockkey123")
    health = provider.check_health()
    assert health.status == "healthy"
    assert "LiteLLM provider ready" in health.message
    assert provider.get_capabilities().is_local is False


def test_check_health_when_litellm_missing(monkeypatch) -> None:
    """Verify check_health handles missing litellm library gracefully."""
    from providers import litellm_provider

    monkeypatch.setattr(litellm_provider, "litellm", None)

    provider = LiteLLMProvider(api_key="mock-key")
    health = provider.check_health()
    assert health.status == "unreachable"
    assert "LiteLLM library is not installed" in health.message


def test_provider_capabilities_across_models() -> None:
    """Verify capabilities correctly reflect context windows and vision support for supported models."""
    groq_provider = LiteLLMProvider(model_name="groq/llama-3.3-70b-versatile")
    groq_caps = groq_provider.get_capabilities()
    assert groq_caps.context_window == 131072
    assert groq_caps.supports_vision is False
    assert groq_caps.is_local is False
    assert groq_caps.supports_streaming is True

    openai_provider = LiteLLMProvider(model_name="openai/gpt-4o-mini")
    openai_caps = openai_provider.get_capabilities()
    assert openai_caps.context_window == 128000
    assert openai_caps.supports_vision is True

    anthropic_provider = LiteLLMProvider(model_name="anthropic/claude-3-5-haiku-20241022")
    anthropic_caps = anthropic_provider.get_capabilities()
    assert anthropic_caps.context_window == 200000
    assert anthropic_caps.supports_vision is True


def test_generate_text_clamps_temperature_and_passes_bounded_params(monkeypatch) -> None:
    """Verify generate_text bounds requests with timeouts, retries, and clamped temperature."""
    import litellm

    captured_kwargs: dict = {}

    def mock_completion(**kwargs):
        captured_kwargs.update(kwargs)
        return MockCompletionResponse("Bounded output")

    monkeypatch.setattr(litellm, "completion", mock_completion)

    provider = LiteLLMProvider(
        model_name="openai/gpt-4o-mini",
        api_key="sk-test",
        user_consented=True,
        timeout=25.0,
        num_retries=3,
    )

    out = provider.generate_text(
        prompt="User prompt",
        system_prompt="System prompt",
        max_tokens=500,
        temperature=3.5,  # Exceeds max 2.0
    )

    assert out == "Bounded output"
    assert captured_kwargs["temperature"] == 2.0
    assert captured_kwargs["max_tokens"] == 500
    assert captured_kwargs["timeout"] == 25.0
    assert captured_kwargs["num_retries"] == 3
    assert captured_kwargs["messages"][0] == {"role": "system", "content": "System prompt"}
    assert captured_kwargs["messages"][1] == {"role": "user", "content": "User prompt"}


def test_stream_text_yields_deltas(monkeypatch) -> None:
    """Verify stream_text streams delta contents incrementally."""
    import litellm

    stream_chunks = [
        MagicMock(choices=[MockDelta("Hello")]),
        MagicMock(choices=[MockDelta(" ")]),
        MagicMock(choices=[MockDelta("world")]),
        MagicMock(choices=[MockDelta(None)]),
    ]

    monkeypatch.setattr(litellm, "completion", MagicMock(return_value=iter(stream_chunks)))

    provider = LiteLLMProvider(
        model_name="groq/llama-3.3-70b-versatile",
        api_key="gsk-test",
        user_consented=True,
    )

    chunks = list(provider.stream_text("Say hello"))
    assert "".join(chunks) == "Hello world"


def test_analyze_image_vision_support_and_rejection(monkeypatch) -> None:
    """Verify analyze_image works for vision models and raises NotImplementedError for non-vision models."""
    import litellm

    # 1. Non-vision model should raise NotImplementedError
    non_vision_prov = LiteLLMProvider(
        model_name="groq/llama-3.3-70b-versatile",
        api_key="mock",
        user_consented=True,
    )
    with pytest.raises(NotImplementedError, match="Vision analysis is not supported"):
        non_vision_prov.analyze_image(b"fake_bytes", "prompt")

    # 2. Empty bytes should raise ValueError
    vision_prov = LiteLLMProvider(
        model_name="openai/gpt-4o-mini",
        api_key="sk-mock",
        user_consented=True,
    )
    with pytest.raises(ValueError, match="image_bytes cannot be empty"):
        vision_prov.analyze_image(b"", "prompt")

    # 3. Vision model with valid image calls litellm with base64 data URI
    captured_kwargs: dict = {}

    def mock_completion(**kwargs):
        captured_kwargs.update(kwargs)
        return MockCompletionResponse("Visual analysis description")

    monkeypatch.setattr(litellm, "completion", mock_completion)

    result = vision_prov.analyze_image(b"png_sample_data", "Describe chart")
    assert result == "Visual analysis description"
    content_list = captured_kwargs["messages"][0]["content"]
    assert content_list[0]["text"] == "Describe chart"
    assert "data:image/png;base64," in content_list[1]["image_url"]["url"]

    # 4. MIME sniffing: JPEG and WebP bytes are recognized correctly (IN-01)
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    vision_prov.analyze_image(jpeg_bytes, "Describe photo")
    jpeg_url = captured_kwargs["messages"][0]["content"][1]["image_url"]["url"]
    assert "data:image/jpeg;base64," in jpeg_url

    webp_bytes = b"RIFF\x20\x00\x00\x00WEBPVP8 "
    vision_prov.analyze_image(webp_bytes, "Describe webp")
    webp_url = captured_kwargs["messages"][0]["content"][1]["image_url"]["url"]
    assert "data:image/webp;base64," in webp_url


def test_exception_wrapping_into_runtime_error(monkeypatch) -> None:
    """Verify provider errors are wrapped cleanly into RuntimeError."""
    import litellm

    def fail_completion(**kwargs):
        raise ValueError("Network timeout")

    monkeypatch.setattr(litellm, "completion", fail_completion)

    provider = LiteLLMProvider(api_key="mock", user_consented=True)

    with pytest.raises(RuntimeError, match="Cloud provider generation error"):
        provider.generate_text("test")

    with pytest.raises(RuntimeError, match="Cloud provider streaming error"):
        list(provider.stream_text("test"))


def test_ai_model_cloud_mode_dynamic_toggle() -> None:
    """Verify AiModel switches cleanly between local mode and consented cloud provider."""
    cloud_prov = LiteLLMProvider(model_name="openai/gpt-4o-mini", api_key="sk-test", user_consented=True)
    assert isinstance(cloud_prov, BaseModelProvider)

    model = AiModel(cloud_mode=True, cloud_provider=cloud_prov)
    assert model.cloud_mode is True
    assert model.provider is cloud_prov
    assert model.model_name == "openai/gpt-4o-mini"

    # Toggle back to local mode
    model.set_cloud_mode(False)
    assert model.cloud_mode is False
    assert model.provider.get_capabilities().is_local is True
    model.close()
