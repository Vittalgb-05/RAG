"""Application settings schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class CloudSettings(BaseModel):
    """Cloud provider configuration status."""

    enabled: bool
    provider: Literal["groq", "openai", "anthropic"]
    model: str
    consented: bool
    has_key: bool


class LimitsSettings(BaseModel):
    """System ingestion and conversation limits."""

    max_file_mb: int
    max_pages: int
    max_chat_turns: int


class AppSettings(BaseModel):
    """Application configuration payload."""

    mode: Literal["local", "cloud"]
    egress_policy: Literal["local", "cloud"]
    limits: LimitsSettings
    cloud: CloudSettings


class UpdateCloudSettings(BaseModel):
    """Payload for updating cloud settings and consent."""

    enabled: bool
    provider: Literal["groq", "openai", "anthropic"]
    model: str
    consent: bool
    api_key: str | None = None
