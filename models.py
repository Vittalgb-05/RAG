"""
Canonical Pydantic v2 data models for the local multimodal intelligence system.

Defines schemas for documents, pages, chunks, and visual evidence elements,
providing strict validation, serialization, and backward compatibility with legacy dicts.
"""

from pathlib import Path
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Configuration version for chunking and extraction policy
CONFIG_VERSION: str = "docling-1000-200-v1"


def cache_dir_for(base: Path, sha256: str) -> Path:
    """
    Compute disk cache path for a given document SHA-256 and config version.

    Args:
        base: Base directory for cache (e.g. Path(".cache")).
        sha256: 64-character lowercase hex digest of the document.

    Returns:
        Path: Dedicated directory base / sha256 / CONFIG_VERSION.
    """
    if not isinstance(sha256, str) or not re.match(r"^[0-9a-f]{64}$", sha256):
        raise ValueError(f"Invalid sha256 digest: {sha256!r}")
    return base / sha256 / CONFIG_VERSION


class BBox(BaseModel):
    """
    Normalized or absolute bounding-box coordinates for an element on a page.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float | None = None
    page_height: float | None = None

    @model_validator(mode="after")
    def validate_coordinates(self) -> "BBox":
        if self.x0 < 0 or self.y0 < 0 or self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"Invalid BBox coordinates: ({self.x0}, {self.y0}, {self.x1}, {self.y1})")
        return self


class Chunk(BaseModel):
    """
    Canonical document text chunk used for embeddings, indexing, and retrieval.
    Matches legacy dictionary keys (content, filename, page, chunk_id) while adding
    typed metadata and forward-compatibility fields for bounding boxes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(..., min_length=1, description="Extracted chunk text content.")
    filename: str = Field(..., description="Original filename of the source document.")
    page: int = Field(..., ge=1, description="1-indexed source page number.")
    chunk_id: str = Field(..., description="Unique chunk identifier.")
    doc_id: str = Field(..., description="Parent document identifier (e.g. doc_<sha16>).")
    char_start: int | None = Field(default=None, description="Starting character offset in page text.")
    char_end: int | None = Field(default=None, description="Ending character offset in page text.")
    bbox: BBox | None = Field(default=None, description="Optional bounding box on source page.")
    extraction: str = Field(default="pypdf", description="Extraction backend used (pypdf, docling, ocr).")
    embedding_model: str | None = Field(default=None, description="Model identifier used for vector embedding.")


class Page(BaseModel):
    """
    Page-level extraction status, metrics, and error tracking.
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(..., description="Parent document identifier.")
    page_num: int = Field(..., ge=1, description="1-indexed page number.")
    status: Literal["ok", "empty", "failed"] = Field(..., description="Extraction status: 'ok', 'empty', or 'failed'.")
    char_count: int = Field(default=0, ge=0, description="Total characters extracted from page.")
    error: str | None = Field(default=None, description="Error message if extraction failed.")
    num_chunks: int = Field(default=0, ge=0, description="Number of text chunks produced from this page.")


class EvidenceElement(BaseModel):
    """
    Multimodal visual or structural evidence item (text, table, chart, diagram).
    """

    model_config = ConfigDict(extra="forbid")

    element_id: str = Field(..., min_length=1, description="Unique element identifier.")
    doc_id: str = Field(..., description="Parent document identifier.")
    page: int = Field(..., ge=1, description="1-indexed page number.")
    kind: Literal["text", "table", "chart", "image"] = Field(
        default="text", description="Element type: 'text', 'table', 'chart', or 'image'."
    )
    content: str = Field(..., description="Textual representation, markdown table, or caption.")
    bbox: BBox | None = Field(default=None, description="Bounding box coordinates on the page.")
    source: str = Field(default="pypdf", description="Extractor that produced this evidence item.")
    model_version: str = Field(default="", description="Model version or extractor identifier.")

    @model_validator(mode="after")
    def validate_doc_id(self) -> "EvidenceElement":
        if not self.doc_id.startswith("doc_"):
            raise ValueError(f"doc_id must start with 'doc_': {self.doc_id!r}")
        return self


class Document(BaseModel):
    """
    Canonical document record representing an uploaded and processed PDF file.
    Identified primarily by sha256 content digest, independent of filename.
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(..., description="Stable document ID starting with 'doc_'.")
    filename: str = Field(..., description="Original uploaded filename.")
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$", description="64-character lowercase SHA-256 hex digest.")
    size_bytes: int = Field(..., ge=0, description="Total file size in bytes.")
    num_pages: int = Field(..., ge=0, description="Total number of pages in the PDF.")
    status: Literal["pending", "indexed", "failed"] = Field(
        default="pending", description="Processing status: 'pending', 'indexed', or 'failed'."
    )
    upload_time: str = Field(..., description="ISO 8601 UTC timestamp of upload.")
    num_chunks: int = Field(default=0, ge=0, description="Total number of indexable chunks generated.")

    @model_validator(mode="after")
    def validate_doc_id(self) -> "Document":
        if not self.doc_id.startswith("doc_"):
            raise ValueError(f"doc_id must start with 'doc_': {self.doc_id!r}")
        return self


class EvidenceSnippet(BaseModel):
    """
    An individual retrieved evidence snippet with ranking and provenance.
    Shared identically across LLM generation prompt assembly and UI citation rendering (RETR-04).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(..., description="Text content of the retrieved snippet.")
    doc_id: str = Field(..., description="Parent document identifier.")
    filename: str = Field(..., description="Source PDF filename.")
    page: int = Field(..., ge=1, description="1-indexed source page number.")
    chunk_id: str = Field(..., description="Unique chunk identifier.")
    score: float = Field(..., description="Composite retrieval or RRF score (higher is better).")
    rank: int = Field(..., ge=1, description="1-based composite rank ([E1], [E2], ...).")
    dense_rank: int | None = Field(default=None, description="1-based rank from vector search.")
    fts_rank: int | None = Field(default=None, description="1-based rank from full-text keyword search.")
    extraction: str = Field(default="docling", description="Extraction backend used (docling, ocr, pypdf).")
    char_start: int | None = Field(default=None, description="Starting character offset on page.")
    char_end: int | None = Field(default=None, description="Ending character offset on page.")
    bbox: BBox | None = Field(default=None, description="Optional bounding box on source page.")


class RetrievalResult(BaseModel):
    """
    Immutable retrieval container shared identically across generation and UI citations (RETR-04).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str = Field(..., description="User search query or question.")
    snippets: list[EvidenceSnippet] = Field(default_factory=list, description="Ranked list of evidence snippets.")
    total_candidates: int = Field(default=0, ge=0, description="Total candidates examined across modalities.")
    search_mode: Literal["hybrid", "dense", "fts", "fallback"] = Field(
        default="hybrid", description="Retrieval execution mode."
    )

    def formatted_evidence(self) -> str:
        """Render numbered evidence blocks ([E1], [E2], ...) for the LLM prompt context."""
        if not self.snippets:
            return ""
        blocks = []
        for s in self.snippets:
            header = f"[E{s.rank}] ({s.filename}, p. {s.page})"
            blocks.append(f"{header}\n{s.content}")
        return "\n\n---\n\n".join(blocks)

    def source_labels(self) -> list[str]:
        """Return unique source citation labels for UI display chips."""
        seen = set()
        labels = []
        for s in self.snippets:
            lbl = f"{s.filename} (p. {s.page})"
            if lbl not in seen:
                seen.add(lbl)
                labels.append(lbl)
        return labels

