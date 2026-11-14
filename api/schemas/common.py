"""Common schemas used across multiple API endpoints."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class BBox(BaseModel):
    """Bounding box coordinates [x1, y1, x2, y2]."""

    x1: float
    y1: float
    x2: float
    y2: float


class Scope(BaseModel):
    """Document search scope."""

    type: Literal["all", "documents"] = "all"
    doc_ids: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Evidence snippet source attribution."""

    rank: int
    doc_id: str
    filename: str
    page: int | None = None
    preview: str
    score: float | None = None
    cited: bool = False
    supported: bool | None = None
    bbox: list[float] | None = None


GroundingStatus = Literal[
    "grounded", "partial", "unsupported", "rank_only", "abstained", "unverified"
]


class Grounding(BaseModel):
    """Verification and grounding report for generated answers."""

    status: GroundingStatus
    caption: str
    citations: list[int] = Field(default_factory=list)
    uncited_claim_count: int = 0
    incomplete_context: bool = False
    truncation_warning: bool = False
    request_id: str
    scope: Scope
    sentence_support: list[dict[str, object]] | None = None
    injection_flags: list[str] | None = None


class Problem(BaseModel):
    """RFC 9457 Problem Details schema."""

    type: str
    title: str
    status: int
    code: str
    detail: str
    request_id: str | None = None
