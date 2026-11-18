"""Unit tests for startup state hydration from SQLite and LanceDB."""

from unittest.mock import MagicMock

from core.doc_store import DocStore
from core.models import Chunk, Document
from services.hydration import HydrationReport, hydrate_startup_state


def _indexed_document(doc_id: str = "doc_valid") -> Document:
    return Document(
        doc_id=doc_id,
        filename="valid.pdf",
        sha256="b" * 64,
        size_bytes=512,
        num_pages=1,
        status="indexed",
        upload_time="2026-10-22T00:00:00Z",
        num_chunks=1,
    )


def test_hydrate_startup_state_returns_report(tmp_path):
    """Verify indexed documents from DocStore return proper HydrationReport."""
    db_file = tmp_path / "test_hydrate.db"
    store = DocStore(db_file)

    doc = Document(
        doc_id="doc_hydrate_01",
        filename="report.pdf",
        sha256="a" * 64,
        size_bytes=1024,
        num_pages=3,
        status="indexed",
        upload_time="2026-10-19T00:00:00Z",
        num_chunks=5,
    )
    store.upsert_document(doc)

    mock_retriever = MagicMock()
    mock_retriever.count_chunks.return_value = 5
    mock_retriever.has_document.return_value = True
    mock_retriever.get_visual_evidence.return_value = []

    mock_embed = MagicMock()

    report = hydrate_startup_state(store, retriever=mock_retriever, embedding=mock_embed)

    assert isinstance(report, HydrationReport)
    assert report.restored == 1
    assert report.repaired == 0
    assert report.failed == 0


def test_hydration_skips_reembedding_when_vectors_valid(tmp_path):
    """A healthy vector index must not trigger any embedding work."""
    store = DocStore(tmp_path / "valid.db")
    doc = _indexed_document()
    store.upsert_document(doc)

    retriever = MagicMock()
    retriever.has_document.return_value = True
    retriever.get_visual_evidence.return_value = []

    embedding = MagicMock()

    report = hydrate_startup_state(store, retriever=retriever, embedding=embedding)

    retriever.index_chunks.assert_not_called()
    embedding.get_embeddings.assert_not_called()
    assert report.restored == 1
    assert report.repaired == 0


def test_hydration_reports_progress_when_repairing_missing_vectors(tmp_path):
    """Missing vectors are repaired with progress callbacks, not silently."""
    store = DocStore(tmp_path / "repair.db")
    doc = _indexed_document("doc_needs_repair")
    store.upsert_document(doc)
    store.record_chunks(
        [
            Chunk(
                chunk_id="chunk_repair_1",
                doc_id=doc.doc_id,
                filename=doc.filename,
                page=1,
                content="Evidence that must be re-embedded.",
            )
        ]
    )

    progress: list[tuple[int, int, str]] = []

    retriever = MagicMock()
    # First call is the coverage scan (missing), second is post-write verification.
    retriever.has_document.side_effect = [False, True]
    retriever.get_visual_evidence.return_value = []

    embedding = MagicMock()
    embedding.get_embeddings.return_value.tolist.return_value = [[0.1] * 384]

    report = hydrate_startup_state(
        store,
        retriever=retriever,
        embedding=embedding,
        progress_callback=lambda done, total, label: progress.append((done, total, label)),
    )

    assert retriever.index_chunks.call_count == 1
    assert progress, "Repair should report progress"
    assert report.restored == 0
    assert report.repaired == 1
    assert report.failed == 0


def test_hydration_consumes_deletion_tombstones_without_indexed_documents(tmp_path):
    """A pending tombstone must purge vectors even when SQLite has no indexed docs."""
    store = DocStore(tmp_path / "tombstone_hydrate.db")
    store.record_deletion_tombstone("doc_deleted_offline")

    retriever = MagicMock()

    report = hydrate_startup_state(store, retriever=retriever)

    retriever.delete_document.assert_called_once_with("doc_deleted_offline")
    assert store.list_deletion_tombstones() == []
    assert report.tombstones_consumed == 1


def test_hydration_keeps_tombstone_when_vector_purge_fails(tmp_path):
    """A failed vector purge must leave the tombstone for the next retry."""
    store = DocStore(tmp_path / "tombstone_retry.db")
    store.record_deletion_tombstone("doc_retry")

    retriever = MagicMock()
    retriever.delete_document.side_effect = RuntimeError("index unavailable")

    report = hydrate_startup_state(store, retriever=retriever)

    assert store.list_deletion_tombstones() == ["doc_retry"]
    assert report.tombstones_consumed == 0
