"""Cloud inference provider for Groq API implementing BaseModelProvider.

Used as optional cloud inference fallback when configured with a GROQ_API_KEY.
"""

from collections.abc import Generator
import os
from typing import Any

from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore[assignment, misc]


class GroqProvider(BaseModelProvider):
    """Cloud Groq API provider conforming to BaseModelProvider."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "openai/gpt-oss-20b",
        context_window: int = 8192,
        user_consented: bool = False,
    ) -> None:
        """Initialize the Groq provider.

        Args:
            api_key: Optional explicit Groq API key.
            model_name: Cloud model identifier.
            context_window: Maximum token window.
            user_consented: Explicit consent to transmit content to Groq.  Generation
                and image analysis refuse to run until this is True (INF-04, UI-04).
        """
        self.model_name = model_name
        self.context_window = context_window
        self.user_consented = bool(user_consented)

        if api_key is None:
            # Check Streamlit secrets if present, then environment
            try:
                import streamlit as st

                api_key = st.secrets.get("GROQ_API_KEY")
            except (KeyError, FileNotFoundError, AttributeError):
                api_key = None

            if not api_key:
                api_key = os.environ.get("GROQ_API_KEY")

        self.api_key = api_key
        self._client: Any = None
        if Groq is not None and self.api_key:
            self._client = Groq(api_key=self.api_key)

    def set_consent(self, consented: bool) -> None:
        """Update explicit user consent state."""
        self.user_consented = bool(consented)

    def _assert_consent(self) -> None:
        """Block transmission until the user has explicitly consented."""
        if not self.user_consented:
            raise PermissionError(
                "Cloud transmission blocked: explicit user consent is required before transmitting "
                "document data to cloud providers (INF-04, UI-04)."
            )

    def close(self) -> None:
        """Close underlying Groq client resources."""
        if hasattr(self._client, "close"):
            self._client.close()

    def check_health(self) -> HealthStatus:
        """Check whether Groq provider is configured and available.

        Returns:
            HealthStatus indicating healthy, unreachable, or error.
        """
        if Groq is None:
            return HealthStatus(
                status="unreachable",
                message="groq package is missing. Install with pip install groq.",
            )
        if not self.api_key:
            return HealthStatus(
                status="unreachable",
                message="GROQ_API_KEY is not configured in environment or Streamlit secrets.",
            )
        if self._client is None:
            return HealthStatus(
                status="error",
                message="Groq client could not be initialized.",
            )
        return HealthStatus(
            status="healthy",
            message=f"Groq Cloud ready ({self.model_name}).",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect provider capabilities.

        Returns:
            ProviderCapabilities for Groq cloud.
        """
        return ProviderCapabilities(
            model_name=self.model_name,
            context_window=self.context_window,
            supports_vision=False,
            is_local=False,
            supports_streaming=True,
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Generate text synchronously via Groq."""
        self._assert_consent()
        if not self._client:
            raise RuntimeError("Groq client is not configured or missing API key.")

        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=clamped_temp,
                stream=False,
            )
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise RuntimeError(f"Groq API error: {exc}") from exc

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        """Stream text tokens incrementally via Groq."""
        self._assert_consent()
        if not self._client:
            raise RuntimeError("Groq client is not configured or missing API key.")

        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            stream = self._client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                temperature=clamped_temp,
                stream=True,
            )
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as exc:
            raise RuntimeError(f"Groq API error: {exc}") from exc

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Multimodal image analysis is not supported on standard Groq text models."""
        self._assert_consent()
        raise NotImplementedError("Groq text model does not support image analysis.")
