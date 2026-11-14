"""Chat session and message schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from api.schemas.common import Grounding, Scope, Source


class ChatMessageUsage(BaseModel):
    """Timing and token metrics for a chat completion."""

    ttft_ms: float = 0.0
    tokens: int = 0
    duration_ms: float = 0.0


class ChatMessageResponse(BaseModel):
    """A chat message record."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    grounding: Grounding | None = None
    sources: list[Source] | None = None
    usage: ChatMessageUsage | None = None
    created_at: str


class ChatSessionCreate(BaseModel):
    """Payload to start a new chat session."""

    title: str = "New Chat"
    scope: Scope = Field(default_factory=Scope)


class ChatSessionUpdate(BaseModel):
    """Payload to update an existing chat session."""

    title: str | None = None
    scope: Scope | None = None


class ChatSessionResponse(BaseModel):
    """Chat session header and message history."""

    id: str
    title: str
    scope: Scope
    updated_at: str
    messages: list[ChatMessageResponse] = Field(default_factory=list)


class SendMessage(BaseModel):
    """Payload to post a message into a chat session."""

    content: str
    scope: Scope = Field(default_factory=Scope)
