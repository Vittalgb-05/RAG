# ------------------------------------------------------------------
# Unit Tests for DocStore (doc_store.py)
# Verifies SQLite persistence, WAL mode, migrations, UNIQUE(sha256)
# constraint handling, page failure tracking, and chunk storage.
# ------------------------------------------------------------------

import sqlite3
import pytest
from doc_store import DocStore
from models import BBox, Chunk, Document, EvidenceElement, Page


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
        assert version == 2


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


def test_restore_chunks_to_embedding_from_doc_store(tmp_path, mock_sentence_transformer):
    """
    Verify restart rebuild flow (CR-01 & CR-03):
    Stored chunks can be restored from DocStore and passed into LocalEmbedding.build_index.
    """
    from local_embedding import LocalEmbedding

    db_file = tmp_path / "restore.db"
    store = DocStore(db_file)

    doc_id = "doc_restore_12345"
    doc = Document(
        doc_id=doc_id,
        filename="manual.pdf",
        sha256="d" * 64,
        size_bytes=2048,
        num_pages=2,
        status="indexed",
        upload_time="2026-10-11T02:00:00Z",
        num_chunks=2,
    )
    store.upsert_document(doc)

    chunks = [
        Chunk(
            content="Local multimodal RAG system running on RTX 3050 GPU.",
            filename="manual.pdf",
            page=1,
            chunk_id=f"{doc_id[:12]}_p1_0000",
            doc_id=doc_id,
            extraction="pypdf",
        ),
        Chunk(
            content="Fast vector similarity search via normalized inner product.",
            filename="manual.pdf",
            page=2,
            chunk_id=f"{doc_id[:12]}_p2_0000",
            doc_id=doc_id,
            extraction="pypdf",
        ),
    ]
    store.record_chunks(chunks)

    # Simulate restart: empty session embedding index
    retrieved = store.get_chunks_for_doc(doc_id)
    assert len(retrieved) == 2

    local_embedding = LocalEmbedding()
    local_embedding.build_index([c.model_dump() for c in retrieved])

    results = local_embedding.search("RTX 3050 GPU", k=1)
    assert len(results) == 1
    doc, score = results[0]
    assert "RTX 3050" in doc["content"]
    assert doc["page"] == 1


def test_upsert_document_updates_size_and_time(tmp_path):
    """Verify upsert_document updates size_bytes and upload_time on conflict (WR-02)."""
    db_file = tmp_path / "upsert_check.db"
    store = DocStore(db_file)

    sha = "e" * 64
    doc_id = "doc_test_upsert"
    doc_v1 = Document(
        doc_id=doc_id,
        filename="v1.pdf",
        sha256=sha,
        size_bytes=100,
        num_pages=1,
        status="pending",
        upload_time="2026-10-11T01:00:00Z",
        num_chunks=1,
    )
    store.upsert_document(doc_v1)

    doc_v2 = Document(
        doc_id=doc_id,
        filename="v2.pdf",
        sha256=sha,
        size_bytes=250,
        num_pages=2,
        status="indexed",
        upload_time="2026-10-11T02:00:00Z",
        num_chunks=5,
    )
    store.upsert_document(doc_v2)

    updated = store.get_document(doc_id)
    assert updated is not None
    assert updated.filename == "v2.pdf"
    assert updated.size_bytes == 250
    assert updated.num_pages == 2
    assert updated.status == "indexed"
    assert updated.upload_time == "2026-10-11T02:00:00Z"
    assert updated.num_chunks == 5


def test_record_chunks_full_column_update_on_conflict(tmp_path):
    """Verify record_chunks updates all metadata columns on chunk_id conflict (IN-06)."""
    db_file = tmp_path / "chunks_conflict.db"
    store = DocStore(db_file)

    chunk_v1 = Chunk(
        content="Original content.",
        filename="old.pdf",
        page=1,
        chunk_id="chunk_conflict_1",
        doc_id="doc_v1",
        extraction="pypdf",
    )
    store.record_chunks([chunk_v1])

    chunk_v2 = Chunk(
        content="Updated content.",
        filename="new.pdf",
        page=3,
        chunk_id="chunk_conflict_1",
        doc_id="doc_v2",
        extraction="docling",
    )
    store.record_chunks([chunk_v2])

    retrieved = store.get_chunks_for_doc("doc_v2")
    assert len(retrieved) == 1
    assert retrieved[0].content == "Updated content."
    assert retrieved[0].filename == "new.pdf"
    assert retrieved[0].page == 3
    assert retrieved[0].extraction == "docling"


def test_evidence_elements_roundtrip(tmp_path):
    """Verify EvidenceElement insertion, update, and retrieval equality."""
    db_file = tmp_path / "evidence.db"
    store = DocStore(db_file)

    doc_id = "doc_1234567812345678"
    store.upsert_document(
        Document(
            doc_id=doc_id,
            filename="evidence_doc.pdf",
            sha256="1" * 64,
            size_bytes=512,
            num_pages=2,
            status="indexed",
            upload_time="2026-10-11T10:00:00Z",
            num_chunks=2,
        )
    )

    elem1 = EvidenceElement(
        element_id="elem_doc1_p1_fig1",
        doc_id=doc_id,
        page=1,
        kind="chart",
        content="Bar chart showing quarterly performance metrics.",
        bbox=BBox(x0=50.0, y0=100.0, x1=400.0, y1=300.0),
        source="vlm:qwen3-vl-2b",
        model_version="qwen3-vl-2b",
    )
    elem2 = EvidenceElement(
        element_id="elem_doc1_p2_tab1",
        doc_id=doc_id,
        page=2,
        kind="table",
        content="| Col A | Col B |\n|---|---|\n| 1 | 2 |",
        bbox=None,
        source="docling",
        model_version="",
    )

    store.record_evidence_elements([elem1, elem2])

    retrieved = store.get_evidence_for_doc("doc_1234567812345678")
    assert len(retrieved) == 2

    fig = next(e for e in retrieved if e.element_id == "elem_doc1_p1_fig1")
    assert fig.kind == "chart"
    assert fig.source == "vlm:qwen3-vl-2b"
    assert fig.model_version == "qwen3-vl-2b"
    assert fig.bbox is not None
    assert fig.bbox.x0 == 50.0

    tab = next(e for e in retrieved if e.element_id == "elem_doc1_p2_tab1")
    assert tab.kind == "table"
    assert tab.source == "docling"
    assert tab.bbox is None


def test_foreign_key_cascade_deletion(tmp_path):
    """Verify deleting a Document cascades to associated EvidenceElements (CR-02)."""
    db_file = tmp_path / "cascade.db"
    store = DocStore(db_file)

    doc_id = "doc_cascade_test_1"
    sha = "c" * 64
    doc = Document(
        doc_id=doc_id,
        filename="cascade_doc.pdf",
        sha256=sha,
        size_bytes=1024,
        num_pages=1,
        status="indexed",
        upload_time="2026-10-11T12:00:00Z",
        num_chunks=1,
    )
    store.upsert_document(doc)

    elem = EvidenceElement(
        element_id="elem_cascade_1",
        doc_id=doc_id,
        page=1,
        kind="chart",
        content="Test diagram for cascade",
        source="vlm:qwen3-vl-2b",
    )
    store.record_evidence_elements([elem])

    # Verify present
    assert len(store.get_evidence_for_doc(doc_id)) == 1

    # Delete parent document
    deleted = store.delete_document(doc_id)
    assert deleted is True

    # Verify parent is gone and child evidence_elements was cascade-deleted
    assert store.get_document(doc_id) is None
    assert len(store.get_evidence_for_doc(doc_id)) == 0
