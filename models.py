"""
Canonical Pydantic v2 data models for the local multimodal intelligence system.

Defines schemas for documents, pages, chunks, and visual evidence elements,
providing strict validation, serialization, and backward compatibility with legacy dicts.
"""

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field

# Configuration version for chunking and extraction policy
CONFIG_VERSION: str = "chunker-1000-200-pypdf"


def cache_dir_for(base: Path, sha256: str) -> Path:
    """
    Compute disk cache path for a given document SHA-256 and config version.

    Args:
        base: Base directory for cache (e.g. Path(".cache")).
        sha256: 64-character lowercase hex digest of the document.

    Returns:
        Path: Dedicated directory base / sha256 / CONFIG_VERSION.
    """
    return base / sha256 / CONFIG_VERSION


class BBox(BaseModel):
    """
    Normalized or absolute bounding-box coordinates for an element on a page.
    """

    model_config = ConfigDict(frozen=True)

    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float | None = None
    page_height: float | None = None


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
    status: str = Field(..., description="Extraction status: 'ok', 'empty', or 'failed'.")
    char_count: int = Field(default=0, ge=0, description="Total characters extracted from page.")
    error: str | None = Field(default=None, description="Error message if extraction failed.")
    num_chunks: int = Field(default=0, ge=0, description="Number of text chunks produced from this page.")


class EvidenceElement(BaseModel):
    """
    Multimodal visual or structural evidence item (text, table, chart, diagram).
    """

    model_config = ConfigDict(extra="forbid")

    element_id: str = Field(..., description="Unique element identifier.")
    doc_id: str = Field(..., description="Parent document identifier.")
    page: int = Field(..., ge=1, description="1-indexed page number.")
    kind: str = Field(default="text", description="Element type: 'text', 'table', 'chart', or 'image'.")
    content: str = Field(..., description="Textual representation, markdown table, or caption.")
    bbox: BBox | None = Field(default=None, description="Bounding box coordinates on the page.")
    source: str = Field(default="pypdf", description="Extractor that produced this evidence item.")


class Document(BaseModel):
    """
    Canonical document record representing an uploaded and processed PDF file.
    Identified primarily by sha256 content digest, independent of filename.
    """

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(..., description="Stable document ID: 'doc_' + sha256[:16].")
    filename: str = Field(..., description="Original uploaded filename.")
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$", description="64-character lowercase SHA-256 hex digest.")
    size_bytes: int = Field(..., ge=0, description="Total file size in bytes.")
    num_pages: int = Field(..., ge=0, description="Total number of pages in the PDF.")
    status: str = Field(default="pending", description="Processing status: 'pending', 'indexed', or 'failed'.")
    upload_time: str = Field(..., description="ISO 8601 UTC timestamp of upload.")
    num_chunks: int = Field(default=0, ge=0, description="Total number of indexable chunks generated.")
