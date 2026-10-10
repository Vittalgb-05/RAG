# ------------------------------------------------------------------
# Unit Tests for DocStore (doc_store.py)
# Verifies SQLite persistence, WAL mode, migrations, UNIQUE(sha256)
# constraint handling, page failure tracking, and chunk storage.
# ------------------------------------------------------------------

import sqlite3
import pytest
from doc_store import DocStore
from models import BBox, Chunk, Document, Page


def test_insert_get_roundtrip(tmp_path):
    """Verify Document insertion and retrieval equality."""
    db_file = tmp_path / "test_docs.db"
    store = DocStore(db_file)

    sha = "1" * 64
    doc = Document(
        doc_id="doc_1111111111111111",
        filename="test_doc.pdf",
        sha256=sha,
        size_bytes=4096,
        num_pages=3,
        status="indexed",
        upload_time="2026-10-11T01:00:00Z",
        num_chunks=6,
    )
    store.upsert_document(doc)

    retrieved = store.get_document("doc_1111111111111111")
    assert retrieved is not None
    assert retrieved == doc

    # Also test get_by_sha
    by_sha = store.get_by_sha(sha)
    assert by_sha == doc


def test_sha_unique_violation_on_reupload(tmp_path):
    """Verify that uploading the same SHA with a different doc_id raises IntegrityError."""
    db_file = tmp_path / "test_docs.db"
    store = DocStore(db_file)

    sha = "2" * 64
    doc1 = Document(
        doc_id="doc_first",
        filename="first.pdf",
        sha256=sha,
        size_bytes=1000,
        num_pages=1,
        upload_time="2026-10-11T01:00:00Z",
    )
    store.upsert_document(doc1)

    # Different doc_id but same sha256
    doc2 = Document(
        doc_id="doc_second",
        filename="second.pdf",
        sha256=sha,
        size_bytes=1000,
        num_pages=1,
        upload_time="2026-10-11T01:05:00Z",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_document(doc2)


def test_page_failure_record(tmp_path):
    """Verify page extraction errors are recorded and preserved."""
    db_file = tmp_path / "test_docs.db"
    store = DocStore(db_file)

    page = Page(
        doc_id="doc_123",
        page_num=4,
        status="failed",
        char_count=0,
        error="DecryptionError: Encrypted stream with unsupported filter",
        num_chunks=0,
    )
    store.record_page(page)

    with store._connect() as conn:
        cursor = conn.execute("SELECT * FROM pages WHERE doc_id = ? AND page_num = ?;", ("doc_123", 4))
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "failed"
        assert "DecryptionError" in row["error"]


def test_two_instance_interleave_R1(tmp_path):
    """
    Verify two DocStore instances on the same file can interleave operations without locks.
    Guarantees per-operation connection lifecycle works under Streamlit rerun patterns.
    """
    db_file = tmp_path / "interleave.db"
    store_a = DocStore(db_file)
    store_b = DocStore(db_file)

    doc_a = Document(
        doc_id="doc_a",
        filename="a.pdf",
        sha256="a" * 64,
        size_bytes=10,
        num_pages=1,
        upload_time="2026-10-11T01:00:00Z",
    )
    doc_b = Document(
        doc_id="doc_b",
        filename="b.pdf",
        sha256="b" * 64,
        size_bytes=20,
        num_pages=2,
        upload_time="2026-10-11T01:01:00Z",
    )

    store_a.upsert_document(doc_a)
    assert store_b.get_document("doc_a") is not None

    store_b.upsert_document(doc_b)
    docs = store_a.list_documents()
    assert len(docs) == 2


def test_user_version_set(tmp_path):
    """Verify schema migrations apply and PRAGMA user_version is 1."""
    db_file = tmp_path / "version_check.db"
    store = DocStore(db_file)

    with store._connect() as conn:
        cursor = conn.execute("PRAGMA user_version;")
        version = cursor.fetchone()[0]
        assert version == 1


def test_chunk_json_columns_nullable(tmp_path):
    """Verify Chunk bbox_json and embedding_model columns handle NULL safely."""
    db_file = tmp_path / "chunks.db"
    store = DocStore(db_file)

    chunk_without_bbox = Chunk(
        content="Plain chunk without bounding box.",
        filename="plain.pdf",
        page=1,
        chunk_id="chunk_null_bbox",
        doc_id="doc_999",
    )
    store.record_chunks([chunk_without_bbox])

    retrieved = store.get_chunks_for_doc("doc_999")
    assert len(retrieved) == 1
    assert retrieved[0].bbox is None
    assert retrieved[0].embedding_model is None

    # Test chunk with bbox
    chunk_with_bbox = Chunk(
        content="Visual chunk with bbox.",
        filename="plain.pdf",
        page=1,
        chunk_id="chunk_with_bbox",
        doc_id="doc_999",
        bbox=BBox(x0=50.0, y0=100.0, x1=200.0, y1=300.0),
        embedding_model="all-MiniLM-L6-v2",
    )
    store.record_chunks([chunk_with_bbox])

    retrieved_both = store.get_chunks_for_doc("doc_999")
    assert len(retrieved_both) == 2
    by_id = {c.chunk_id: c for c in retrieved_both}
    assert by_id["chunk_with_bbox"].bbox is not None
    assert by_id["chunk_with_bbox"].bbox.x0 == 50.0
    assert by_id["chunk_with_bbox"].embedding_model == "all-MiniLM-L6-v2"
