"""Unit tests for BaseModelProvider interface and capability schemas."""

from collections.abc import Generator
import pytest
from pydantic import ValidationError

from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities


def test_provider_capabilities_valid() -> None:
    """Test valid ProviderCapabilities creation and defaults."""
    caps = ProviderCapabilities(model_name="qwen3-vl-2b")
    assert caps.model_name == "qwen3-vl-2b"
    assert caps.context_window == 4096
    assert caps.supports_vision is False
    assert caps.is_local is True
    assert caps.supports_streaming is True


def test_provider_capabilities_custom_fields() -> None:
    """Test ProviderCapabilities with explicit non-default values."""
    caps = ProviderCapabilities(
        model_name="qwen3-vl-2b-custom",
        context_window=8192,
        supports_vision=True,
        is_local=False,
        supports_streaming=False,
    )
    assert caps.model_name == "qwen3-vl-2b-custom"
    assert caps.context_window == 8192
    assert caps.supports_vision is True
    assert caps.is_local is False
    assert caps.supports_streaming is False


def test_provider_capabilities_empty_name_rejected() -> None:
    """Test that empty string model_name is rejected."""
    with pytest.raises(ValidationError):
        ProviderCapabilities(model_name="")


def test_provider_capabilities_non_positive_window_rejected() -> None:
    """Test that zero or negative context_window is rejected."""
    with pytest.raises(ValidationError):
        ProviderCapabilities(model_name="qwen3-vl-2b", context_window=0)
    with pytest.raises(ValidationError):
        ProviderCapabilities(model_name="qwen3-vl-2b", context_window=-100)


def test_provider_capabilities_immutability() -> None:
    """Test that ProviderCapabilities is frozen against mutation."""
    caps = ProviderCapabilities(model_name="qwen3-vl-2b")
    with pytest.raises(ValidationError):
        caps.model_name = "other-model"  # type: ignore[misc]


def test_provider_capabilities_extra_forbidden() -> None:
    """Test that extra fields are rejected on ProviderCapabilities."""
    with pytest.raises(ValidationError):
        ProviderCapabilities(model_name="qwen3-vl-2b", unknown_field=123)  # type: ignore[call-arg]


def test_health_status_valid() -> None:
    """Test valid HealthStatus values."""
    for valid_status in ["healthy", "unreachable", "loading", "error"]:
        hs = HealthStatus(status=valid_status, message="All good", latency_ms=12.5)  # type: ignore[arg-type]
        assert hs.status == valid_status
        assert hs.message == "All good"
        assert hs.latency_ms == 12.5


def test_health_status_invalid_status() -> None:
    """Test that invalid status strings are rejected."""
    with pytest.raises(ValidationError):
        HealthStatus(status="unknown_status", message="test")  # type: ignore[arg-type]


def test_health_status_negative_latency_rejected() -> None:
    """Test that negative latency_ms is rejected."""
    with pytest.raises(ValidationError):
        HealthStatus(status="healthy", message="test", latency_ms=-1.0)


def test_health_status_immutability() -> None:
    """Test that HealthStatus is frozen against mutation."""
    hs = HealthStatus(status="healthy", message="Ready")
    with pytest.raises(ValidationError):
        hs.status = "error"  # type: ignore[misc]


def test_abstract_provider_instantiation_fails() -> None:
    """Test that BaseModelProvider cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseModelProvider()  # type: ignore[abstract]


def test_concrete_provider_implementation() -> None:
    """Test that a fully implemented concrete provider can be instantiated and invoked."""

    closed = False

    class DummyProvider(BaseModelProvider):
        def close(self) -> None:
            nonlocal closed
            closed = True

        def generate_text(
            self,
            prompt: str,
            system_prompt: str | None = None,
            max_tokens: int = 1024,
            temperature: float = 0.2,
        ) -> str:
            return f"Echo: {prompt}"

        def stream_text(
            self,
            prompt: str,
            system_prompt: str | None = None,
            history: list[dict[str, str]] | None = None,
            max_tokens: int = 1024,
            temperature: float = 0.2,
        ) -> Generator[str, None, None]:
            yield "Echo: "
            yield prompt

        def analyze_image(
            self,
            image_bytes: bytes,
            prompt: str,
            max_tokens: int = 512,
        ) -> str:
            return f"Image of size {len(image_bytes)}: {prompt}"

        def check_health(self) -> HealthStatus:
            return HealthStatus(status="healthy", message="Dummy ready", latency_ms=1.0)

        def get_capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(model_name="dummy-provider")

    with DummyProvider() as provider:
        assert provider.generate_text("hello") == "Echo: hello"
        assert list(provider.stream_text("world")) == ["Echo: ", "world"]
        assert provider.analyze_image(b"123", "describe") == "Image of size 3: describe"
        assert provider.check_health().status == "healthy"
        assert provider.get_capabilities().model_name == "dummy-provider"

    assert closed is True
