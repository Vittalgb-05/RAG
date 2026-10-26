"""LiteLLM cloud provider adapter with explicit privacy consent controls.

Implements BaseModelProvider interface routing completions through LiteLLM to
Groq, OpenAI, and Anthropic with bounded timeouts, retries, and a strict
programmatic privacy gate (INF-04, UI-04).
"""

import base64
from collections.abc import Generator
import logging
import os
from typing import Any

from core.redaction import redact_text
from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities

logger = logging.getLogger(__name__)

# Disable LiteLLM external telemetry by default for privacy (Security concern 1)
os.environ.setdefault("LITELLM_TELEMETRY", "False")

try:
    import litellm

    litellm.telemetry = False
except ImportError:
    litellm = None  # type: ignore[assignment]

DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"

KNOWN_CONTEXT_WINDOWS: dict[str, int] = {
    "groq": 131072,
    "openai": 128000,
    "anthropic": 200000,
}

VISION_SUPPORTED_PREFIXES = (
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "anthropic/claude-3",
    "anthropic/claude-3-5",
)


def _resolve_api_key_for_model(model_name: str, explicit_key: str | None = None) -> str | None:
    """Resolve API key from explicit arg, session state, Streamlit secrets, or env vars."""
    if explicit_key:
        return explicit_key

    provider_prefix = model_name.split("/")[0].lower() if "/" in model_name else "groq"
    env_var_map = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    target_var = env_var_map.get(provider_prefix, f"{provider_prefix.upper()}_API_KEY")

    # 1. Try Streamlit session_state if running inside Streamlit
    try:
        import streamlit as st

        if hasattr(st, "session_state"):
            session_state = st.session_state
            keys_dict = getattr(session_state, "cloud_api_keys", None)
            if keys_dict is None and hasattr(session_state, "get"):
                keys_dict = session_state.get("cloud_api_keys")

            if isinstance(keys_dict, dict):
                val = keys_dict.get(provider_prefix)
                if val:
                    return str(val)
    except Exception:
        pass

    # 2. Try Streamlit secrets
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            try:
                if target_var in st.secrets:
                    return str(st.secrets[target_var])
            except (KeyError, FileNotFoundError, AttributeError):
                pass
    except Exception:
        pass

    # 3. Try os.environ
    return os.environ.get(target_var)


def _detect_image_mime_type(image_bytes: bytes) -> str:
    """Sniff image format magic bytes to determine MIME type."""
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


class LiteLLMProvider(BaseModelProvider):
    """Unified cloud LLM provider adapter using LiteLLM with strict consent checks."""

    def __init__(
        self,
        model_name: str = DEFAULT_CLOUD_MODEL,
        api_key: str | None = None,
        user_consented: bool = False,
        timeout: float = 30.0,
        num_retries: int = 2,
    ) -> None:
        """Initialize LiteLLM provider.

        Args:
            model_name: LiteLLM model identifier (e.g. 'groq/llama-3.3-70b-versatile',
                        'openai/gpt-4o-mini', 'anthropic/claude-3-5-haiku-20241022').
            api_key: Optional explicit API key. If omitted, resolved from environment/secrets.
            user_consented: Explicit user consent allowing data transmission to cloud.
            timeout: Maximum seconds to wait for network completion before failing.
            num_retries: Maximum automatic retry attempts on transient network failures.
        """
        self.model_name = model_name or DEFAULT_CLOUD_MODEL
        self.api_key = _resolve_api_key_for_model(self.model_name, explicit_key=api_key)
        self.user_consented = bool(user_consented)
        self.timeout = float(timeout)
        self.num_retries = int(num_retries)

    def set_consent(self, consented: bool) -> None:
        """Update explicit user consent state."""
        self.user_consented = bool(consented)

    def _scrub_credentials(self, text: str) -> str:
        """Scrub API keys and token patterns from error strings or logs."""
        resolved_key = self.api_key or _resolve_api_key_for_model(self.model_name) or ""
        return redact_text(text, extra_secrets=(resolved_key,))

    def _assert_consent(self) -> None:
        """Verify user consent prior to transmitting document data."""
        if not self.user_consented:
            raise PermissionError(
                "Cloud transmission blocked: explicit user consent is required before transmitting "
                "document data to cloud providers (INF-04, UI-04)."
            )

    def check_health(self) -> HealthStatus:
        """Inspect provider configuration and API key readiness without billable requests.

        Returns:
            HealthStatus schema with operational state.
        """
        if litellm is None:
            return HealthStatus(
                status="unreachable",
                message="LiteLLM library is not installed. Install via `pip install litellm`.",
            )

        key = _resolve_api_key_for_model(self.model_name, explicit_key=self.api_key)
        if not key:
            provider_prefix = self.model_name.split("/")[0].upper()
            return HealthStatus(
                status="unreachable",
                message=f"Missing API key for {self.model_name}. Please set {provider_prefix}_API_KEY.",
            )

        return HealthStatus(
            status="healthy",
            message=f"LiteLLM provider ready ({self.model_name})",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect capabilities of the configured cloud model.

        Returns:
            ProviderCapabilities schema.
        """
        provider_prefix = self.model_name.split("/")[0].lower() if "/" in self.model_name else "groq"
        context_window = KNOWN_CONTEXT_WINDOWS.get(provider_prefix, 128000)
        supports_vision = any(self.model_name.startswith(p) for p in VISION_SUPPORTED_PREFIXES)

        return ProviderCapabilities(
            model_name=self.model_name,
            context_window=context_window,
            supports_vision=supports_vision,
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
        """Execute non-streaming text generation guarded by user consent.

        Args:
            prompt: User prompt text.
            system_prompt: Optional system instruction.
            max_tokens: Upper bound on generated tokens.
            temperature: Sampling temperature (clamped 0.0 - 2.0).

        Returns:
            Completed assistant response text.
        """
        self._assert_consent()
        if litellm is None:
            raise RuntimeError("LiteLLM is not installed.")

        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": clamped_temp,
                "timeout": self.timeout,
                "num_retries": self.num_retries,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key

            response = litellm.completion(**kwargs)
            choice = response.choices[0]
            return choice.message.content or ""
        except Exception as err:
            scrubbed = self._scrub_credentials(str(err))
            logger.error("LiteLLM generation failure (%s): %s", self.model_name, scrubbed)
            raise RuntimeError(f"Cloud provider generation error ({self.model_name}): {scrubbed}") from err

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        """Stream generated tokens incrementally guarded by user consent.

        Args:
            prompt: User prompt text.
            system_prompt: Optional system instruction.
            history: Optional conversation history.
            max_tokens: Upper bound on generated tokens.
            temperature: Sampling temperature (clamped 0.0 - 2.0).

        Yields:
            Token text chunks as generated.
        """
        self._assert_consent()
        if litellm is None:
            raise RuntimeError("LiteLLM is not installed.")

        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": clamped_temp,
                "stream": True,
                "timeout": self.timeout,
                "num_retries": 0,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key

            response = litellm.completion(**kwargs)
            for chunk in response:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, "content", None)
                    if content:
                        yield str(content)
        except Exception as err:
            scrubbed = self._scrub_credentials(str(err))
            logger.error("LiteLLM streaming failure (%s): %s", self.model_name, scrubbed)
            raise RuntimeError(f"Cloud provider streaming error ({self.model_name}): {scrubbed}") from err

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Analyze document image using multimodal cloud model.

        Args:
            image_bytes: Raw PNG/JPEG image bytes.
            prompt: Analysis prompt.
            max_tokens: Maximum tokens for description.

        Returns:
            Structured text description of image contents.
        """
        self._assert_consent()
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty.")
        if litellm is None:
            raise RuntimeError("LiteLLM is not installed.")

        capabilities = self.get_capabilities()
        if not capabilities.supports_vision:
            raise NotImplementedError(
                f"Vision analysis is not supported by {self.model_name}. Select a multimodal model (e.g. gpt-4o-mini)."
            )

        mime_type = _detect_image_mime_type(image_bytes)
        base64_img = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}},
                ],
            }
        ]

        try:
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "timeout": self.timeout,
                "num_retries": self.num_retries,
            }
            if self.api_key:
                kwargs["api_key"] = self.api_key

            response = litellm.completion(**kwargs)
            choice = response.choices[0]
            return choice.message.content or ""
        except Exception as err:
            scrubbed = self._scrub_credentials(str(err))
            logger.error("LiteLLM vision failure (%s): %s", self.model_name, scrubbed)
            raise RuntimeError(f"Cloud provider vision error ({self.model_name}): {scrubbed}") from err

    def close(self) -> None:
        """Close provider resources (no-op for LiteLLM stateless client)."""
        pass
