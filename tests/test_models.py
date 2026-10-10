# ------------------------------------------------------------------
# Unit Tests for Canonical Models (models.py)
# Verifies schema validation, legacy dictionary key compatibility,
# immutability, extra-field forbidding, and JSON serialization.
# ------------------------------------------------------------------

import pytest
from pydantic import ValidationError
from models import BBox, Chunk, Document, EvidenceElement, Page, CONFIG_VERSION, cache_dir_for
from pathlib import Path


def test_chunk_dump_matches_legacy_keys():
    """Verify Chunk.model_dump() retains all 4 legacy dictionary keys with identical values."""
    chunk = Chunk(
        content="Sample extracted text chunk.",
        filename="report.pdf",
        page=1,
        chunk_id="report.pdf_p1_0",
        doc_id="doc_1234567890abcdef",
    )
    dumped = chunk.model_dump()

    # Legacy callers expect content, filename, page, chunk_id
    assert dumped["content"] == "Sample extracted text chunk."
    assert dumped["filename"] == "report.pdf"
    assert dumped["page"] == 1
    assert dumped["chunk_id"] == "report.pdf_p1_0"

    # New canonical fields are present
    assert dumped["doc_id"] == "doc_1234567890abcdef"
    assert dumped["extraction"] == "pypdf"
    assert dumped["bbox"] is None
    assert dumped["embedding_model"] is None


def test_chunk_frozen_and_hashable():
    """Verify Chunk is immutable and hashable (frozen=True)."""
    chunk = Chunk(
        content="Immutable chunk text.",
        filename="data.pdf",
        page=2,
        chunk_id="data.pdf_p2_0",
        doc_id="doc_abcdef1234567890",
    )
    # Must be hashable
    assert isinstance(hash(chunk), int)

    # Reassignment must raise ValidationError
    with pytest.raises(ValidationError):
        chunk.content = "Mutated text"  # type: ignore


def test_document_extra_forbidden():
    """Verify Document model forbids unmodeled extra fields."""
    valid_sha = "a" * 64
    with pytest.raises(ValidationError, match="extra"):
        Document(
            doc_id="doc_123",
            filename="test.pdf",
            sha256=valid_sha,
            size_bytes=1024,
            num_pages=5,
            upload_time="2026-10-10T12:00:00Z",
            unexpected_field="disallowed",
        )


def test_sha256_pattern_rejects_invalid():
    """Verify Document rejects non-64-character or non-hex sha256 digests."""
    with pytest.raises(ValidationError):
        Document(
            doc_id="doc_123",
            filename="test.pdf",
            sha256="short_hash",
            size_bytes=100,
            num_pages=1,
            upload_time="2026-10-10T12:00:00Z",
        )

    with pytest.raises(ValidationError):
        Document(
            doc_id="doc_123",
            filename="test.pdf",
            sha256="Z" * 64,  # Uppercase non-hex
            size_bytes=100,
            num_pages=1,
            upload_time="2026-10-10T12:00:00Z",
        )


def test_json_roundtrip():
    """Verify serialization to JSON string and reconstruction via model_validate_json."""
    sha = "f" * 64
    doc = Document(
        doc_id="doc_ffffffffffffffff",
        filename="spec.pdf",
        sha256=sha,
        size_bytes=2048,
        num_pages=10,
        status="indexed",
        upload_time="2026-10-11T00:00:00Z",
        num_chunks=25,
    )
    json_str = doc.model_dump_json()
    reconstructed = Document.model_validate_json(json_str)
    assert reconstructed == doc


def test_bbox_none_default_and_forward_compat():
    """Verify BBox coordinates, optional fields, and Chunk embedding_model defaults."""
    bbox = BBox(x0=10.0, y0=20.0, x1=100.0, y1=200.0, page_width=612.0, page_height=792.0)
    chunk = Chunk(
        content="Bounding box chunk.",
        filename="scan.pdf",
        page=1,
        chunk_id="chunk_1",
        doc_id="doc_1",
        bbox=bbox,
        embedding_model="all-MiniLM-L6-v2",
    )
    assert chunk.bbox is not None
    assert chunk.bbox.x0 == 10.0
    assert chunk.bbox.page_width == 612.0
    assert chunk.embedding_model == "all-MiniLM-L6-v2"


def test_page_and_evidence_elements():
    """Verify Page and EvidenceElement construction and status contracts."""
    page = Page(doc_id="doc_1", page_num=3, status="failed", error="Malformed font dictionary")
    assert page.status == "failed"
    assert page.error == "Malformed font dictionary"
    assert page.char_count == 0

    evidence = EvidenceElement(
        element_id="elem_p3_table_0",
        doc_id="doc_1",
        page=3,
        kind="table",
        content="| Col1 | Col2 |\n|---|---|",
    )
    assert evidence.kind == "table"
    assert evidence.source == "pypdf"


def test_config_version_and_cache_dir_helper():
    """Verify CONFIG_VERSION constant and cache_dir_for path computation."""
    assert CONFIG_VERSION == "chunker-1000-200-pypdf"
    sha = "e" * 64
    base = Path(".cache")
    cache_path = cache_dir_for(base, sha)
    assert cache_path == base / sha / "chunker-1000-200-pypdf"
