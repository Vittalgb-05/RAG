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


def test_tracer_chunk_to_store_roundtrip(tmp_path, sample_pdf_path):
    """
    Tracer slice test:
    Construct a Chunk from real PdfReader.get_paragraphs() output on clean_digital.pdf ->
    verify model_dump() retains legacy keys ->
    insert parent Document and Chunk into SQLite via DocStore ->
    read back Document and Chunk and verify round-trip.
    """
    from pdf_reader import PdfReader
    from doc_store import DocStore

    reader = PdfReader(sample_pdf_path)
    paragraphs = reader.get_paragraphs()
    assert len(paragraphs) > 0

    first_para = paragraphs[0]
    doc_id = "doc_tracer12345678"
    chunk = Chunk(
        content=first_para["content"],
        filename=first_para["filename"],
        page=first_para["page"],
        chunk_id=first_para["chunk_id"],
        doc_id=doc_id,
        extraction="pypdf",
    )
    dumped = chunk.model_dump()
    assert dumped["content"] == first_para["content"]
    assert dumped["filename"] == first_para["filename"]
    assert dumped["page"] == first_para["page"]
    assert dumped["chunk_id"] == first_para["chunk_id"]

    db_path = tmp_path / "tracer.db"
    store = DocStore(db_path)
    doc = Document(
        doc_id=doc_id,
        filename=first_para["filename"],
        sha256="c" * 64,
        size_bytes=12345,
        num_pages=20,
        status="indexed",
        upload_time="2026-10-11T01:10:00Z",
        num_chunks=len(paragraphs),
    )
    store.upsert_document(doc)
    store.record_chunks([chunk])

    retrieved_doc = store.get_document(doc_id)
    assert retrieved_doc == doc

    retrieved_chunks = store.get_chunks_for_doc(doc_id)
    assert len(retrieved_chunks) == 1
    assert retrieved_chunks[0] == chunk


def test_chunk_backward_compat_read():
    """
    Verify that legacy dictionaries can be adapted to Chunk without crashing,
    and that Chunk.model_dump() retains content equivalence.
    """
    legacy_data = {
        "content": "Legacy content string.",
        "filename": "old_file.pdf",
        "page": 1,
        "chunk_id": "old_file.pdf_p1_0",
    }
    # Using producer pattern: supply fallback doc_id and extraction
    chunk = Chunk(
        doc_id="doc_legacy",
        extraction="pypdf",
        **legacy_data,
    )
    dumped = chunk.model_dump()
    assert dumped["content"] == legacy_data["content"]
    assert dumped["filename"] == legacy_data["filename"]
    assert dumped["page"] == legacy_data["page"]
    assert dumped["chunk_id"] == legacy_data["chunk_id"]
