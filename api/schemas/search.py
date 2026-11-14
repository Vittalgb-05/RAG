"""Search and Retrieval X-Ray schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
from api.schemas.common import Source


class ExplanationItem(BaseModel):
    """Retrieval rank breakdown across dense and BM25 pools."""

    chunk_id: str
    doc_id: str
    dense_rank: int | None = None
    dense_score: float | None = None
    fts_rank: int | None = None
    fts_score: float | None = None
    rrf_score: float


class SearchRequest(BaseModel):
    """Payload to perform hybrid search with optional explanation."""

    query: str
    doc_ids: list[str] | None = None
    k: int = 5
    mode: Literal["hybrid", "dense", "fts"] = "hybrid"
    explain: bool = False


class SearchResponse(BaseModel):
    """Hybrid search results with sources and optional X-ray breakdown."""

    query: str
    sources: list[Source]
    explanations: list[ExplanationItem] | None = None
