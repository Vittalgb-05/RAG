"""Document Constellation and visualization schemas."""

from __future__ import annotations
from pydantic import BaseModel, Field


class EmbeddingPoint(BaseModel):
    """3D point representing an embedded chunk."""

    chunk_id: str
    doc_id: str
    filename: str
    point: list[float]  # [x, y, z]
    page: int | None = None
    preview: str = ""


class EmbeddingsResponse(BaseModel):
    """3D point cloud for the document constellation."""

    points: list[EmbeddingPoint]
    dims: int = 3
    total_points: int


class QueryTraceRequest(BaseModel):
    """Payload to project a query and trace retrieved candidates."""

    query: str
    doc_ids: list[str] | None = None
    k: int = 5


class QueryTraceResponse(BaseModel):
    """Projected query coordinate and target chunk IDs."""

    point: list[float]  # [x, y, z]
    retrieved_chunk_ids: list[str]
