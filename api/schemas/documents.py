"""Document catalog schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class DocumentSummary(BaseModel):
    """Document catalog item."""

    doc_id: str
    filename: str
    sha256: str
    status: Literal["indexing", "indexed", "failed"]
    pages: int
    chunks: int
    evidence_elements: int = 0
    size_bytes: int
    created_at: str
    has_vectors: bool = True


class DocumentDetail(BaseModel):
    """Full document detail with chunk sample and evidence count."""

    doc_id: str
    filename: str
    sha256: str
    status: str
    num_pages: int
    num_chunks: int
    size_bytes: int
    upload_time: str
    chunks: list[dict[str, object]] = Field(default_factory=list)
    evidence: list[dict[str, object]] = Field(default_factory=list)


class DocumentJobItem(BaseModel):
    """Ingestion job metadata per uploaded file."""

    job_id: str
    filename: str
    doc_id: str
    duplicate: bool = False


class DocumentUploadResponse(BaseModel):
    """Response payload for multi-file upload."""

    jobs: list[DocumentJobItem]
