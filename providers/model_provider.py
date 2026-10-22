"""Unified BaseModelProvider interface and capability schemas for inference backends.

Defines the contract for local (llama.cpp) and cloud (Groq) LLM/VLM providers,
supporting text generation, token streaming, multimodal image analysis,
capability inspection, and health checking.
"""

from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderCapabilities(BaseModel):
    """Immutable metadata describing the features and limits of an inference provider."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_name: str = Field(
        ...,
        min_length=1,
        description="Identifier of the underlying model.",
    )
    context_window: int = Field(
        default=4096,
        gt=0,
        description="Maximum combined input + output token budget.",
    )
    supports_vision: bool = Field(
        default=False,
        description="Whether the provider accepts image input payloads.",
    )
    is_local: bool = Field(
        default=True,
        description="Whether inference executes locally on-device without network egress.",
    )
    supports_streaming: bool = Field(
        default=True,
        description="Whether the provider yields incremental token streams.",
    )


class HealthStatus(BaseModel):
    """Health and connectivity status of an inference backend."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["healthy", "unreachable", "loading", "error"] = Field(
        ...,
        description="Operational health category.",
    )
    message: str = Field(
        ...,
        description="Human-readable diagnostics or actionable setup instructions.",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Round-trip health check latency in milliseconds.",
    )


class BaseModelProvider(ABC):
    """Abstract base class defining the inference interface for LLM/VLM models."""

    def close(self) -> None:
        """Release underlying HTTP client or network resources. Default is no-op."""
        return None

    def __enter__(self) -> "BaseModelProvider":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Generate a complete text response synchronously.

        Args:
            prompt: User or grounded instruction prompt.
            system_prompt: Optional system role instructions.
            max_tokens: Upper bound on output tokens.
            temperature: Sampling temperature (0.0 - 1.0).

        Returns:
            The generated response string.
        """
        ...

    @abstractmethod
    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        """Stream response tokens incrementally.

        Args:
            prompt: Current turn prompt.
            system_prompt: Optional system role instructions.
            history: Optional list of previous chat turns [{"role": "...", "content": "..."}].
            max_tokens: Upper bound on generated tokens.
            temperature: Sampling temperature.

        Yields:
            Incremental text tokens as generated.
        """
        ...

    @abstractmethod
    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Analyze an image or document diagram with multimodal prompt.

        Args:
            image_bytes: Raw bytes of the image (PNG/JPEG).
            prompt: Text prompt asking for visual description or data extraction.
            max_tokens: Maximum tokens in description.

        Returns:
            Model analysis or transcription of the image.
        """
        ...

    @abstractmethod
    def check_health(self) -> HealthStatus:
        """Probe provider connectivity and readiness.

        Returns:
            HealthStatus indicating healthy, unreachable, loading, or error.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect provider capabilities and context bounds.

        Returns:
            ProviderCapabilities schema instance.
        """
        ...
