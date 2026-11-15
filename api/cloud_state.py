"""Cloud inference state management with build-first swap and strict consent controls."""

from __future__ import annotations
import threading
from datetime import datetime, UTC
from pydantic import SecretStr

from providers.litellm_provider import LiteLLMProvider
from core.local_llm import AiModel
from core.redaction import redact_text


class CloudState:
    """Manages cloud credentials, consent status, and provider transitions."""

    def __init__(self, ai_model: AiModel) -> None:
        self._ai = ai_model
        self._lock = threading.Lock()
        self.enabled = False
        self.consented = False
        self.provider = "groq"
        self.model = "groq/llama-3.3-70b-versatile"
        self._keys: dict[str, SecretStr] = {}  # memory only, never persisted to disk
        self._ledger: list[dict[str, object]] = []

    def record_egress(
        self,
        provider: str,
        model: str,
        doc_filenames: list[str],
        char_count: int,
        request_id: str,
    ) -> None:
        """Record a cloud transmission event to the privacy audit ledger."""
        with self._lock:
            self._ledger.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "provider": provider,
                    "model": model,
                    "doc_filenames": doc_filenames,
                    "char_count": char_count,
                    "request_id": request_id,
                }
            )

    def get_ledger(self) -> list[dict[str, object]]:
        """Retrieve recent egress events from the privacy audit ledger."""
        with self._lock:
            return list(self._ledger)

    def has_key(self, provider: str) -> bool:
        """Check if an in-memory API key exists for the given provider."""
        with self._lock:
            return provider in self._keys

    def apply(
        self,
        *,
        enabled: bool,
        provider: str,
        model: str,
        consent: bool,
        api_key: str | None,
    ) -> str | None:
        """Apply cloud configuration settings with build-first provider swap (B3).

        Returns a warning string if we had to fall back to local mode;
        raises PermissionError if enabled without explicit consent.
        """
        with self._lock:
            if enabled and not consent:
                raise PermissionError("Cloud transmission blocked: consent not granted")

            if api_key:
                self._keys[provider] = SecretStr(api_key)

            if not enabled:
                self._to_local()
                return None

            try:
                # BUILD FIRST, then swap (B3): never leave ai_model.provider pointing at a closed client
                resolved_key = self._keys[provider].get_secret_value() if provider in self._keys else None
                new_provider = LiteLLMProvider(
                    model_name=model,
                    api_key=resolved_key,
                    user_consented=True,
                )
                self._ai.swap_provider(new_provider, cloud=True)
                self.enabled = True
                self.consented = True
                self.provider = provider
                self.model = model
                return None
            except Exception as exc:  # noqa: BLE001 - must never leave app in a half-switched state
                secrets = tuple(s.get_secret_value() for s in self._keys.values())
                return redact_text(str(exc), extra_secrets=secrets)

    def revoke(self) -> None:
        """Revoke all cloud credentials, clear consent, and return to local mode."""
        with self._lock:
            self._keys.clear()
            self.consented = False
            self._to_local()

    def _to_local(self) -> None:
        """Revert provider to local engine."""
        try:
            self._ai.swap_provider(None, cloud=False)
        finally:
            self.enabled = False
