"""Credential redaction for errors crossing provider, UI, and log boundaries.

Redaction is intentionally best-effort and pattern-based: it removes known cloud
token formats, explicit environment secrets, bearer tokens, and key/value pairs
before an exception message is displayed, persisted in a transcript, or logged.
"""

from __future__ import annotations

from collections.abc import Iterable
import os
import re

REDACTED = "[REDACTED]"

_SECRET_ENV_VARS = (
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)

_TOKEN_PATTERN = re.compile(r"\b(?:gsk_|sk-proj-|sk-|xox[baprs]-|ghp_|github_pat_|hf_|AIza)[A-Za-z0-9_\-]{8,}")
_BEARER_PATTERN = re.compile(r"(?i)\b(Bearer)\s+[A-Za-z0-9._\-+/=]{8,}")
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|authorization)\b"
    r"(\s*[:=]\s*)(['\"]?)([^\s,'\"]{4,})\3"
)


def redact_text(text: object, extra_secrets: Iterable[str] = ()) -> str:
    """Return *text* with known credentials replaced by ``[REDACTED]``.

    Args:
        text: Error message or other text that may contain a credential.
        extra_secrets: Additional exact secret values known to the caller.

    Returns:
        Scrubbed text safe to display, persist, or log.
    """
    if text is None:
        return ""

    redacted = str(text)
    secrets = [os.environ.get(name) for name in _SECRET_ENV_VARS]
    secrets.extend(extra_secrets)
    for secret in sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True):
        redacted = redacted.replace(secret, REDACTED)

    redacted = _TOKEN_PATTERN.sub(REDACTED, redacted)
    redacted = _BEARER_PATTERN.sub(r"\1 " + REDACTED, redacted)
    redacted = _KEY_VALUE_PATTERN.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}{REDACTED}{match.group(3)}",
        redacted,
    )
    return redacted
