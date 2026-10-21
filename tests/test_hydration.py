"""Unit tests for startup state hydration from SQLite and LanceDB."""

from unittest.mock import MagicMock, patch
import pytest
import streamlit as st

from core.doc_store import DocStore
from core.models import Chunk, Document
from ui.hydration import hydrate_startup_state


@pytest.fixture(autouse=True)
def clean_session_state():
    """Ensure clean Streamlit session state for hydration testing."""
    st.session_state.clear()
    st.session_state.doc_ids = set()
    st.session_state.failed_doc_ids = set()
    st.session_state.indexed_files = set()
    st.session_state.document_metadata = {}
    st.session_state.hybrid_retriever = None
    st.session_state.local_embedding = None


def test_hydrate_startup_state_populates_session(tmp_path):
    """Verify indexed documents from DocStore populate session_state upon startup."""
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

    with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
        mock_instance = MagicMock()
        mock_instance.count_chunks.return_value = 5
        mock_retriever_cls.return_value = mock_instance

        with patch("ui.hydration.LocalEmbedding") as mock_embed_cls:
            mock_embed = MagicMock()
            mock_embed_cls.return_value = mock_embed

            hydrate_startup_state(store)

    assert "doc_hydrate_01" in st.session_state.doc_ids
    assert "report.pdf" in st.session_state.indexed_files
    meta = st.session_state.document_metadata.get("doc_hydrate_01")
    assert meta is not None
    assert meta["pages"] == 3
    assert meta["chunks"] == 5


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


def test_hydration_skips_reembedding_when_vectors_valid(tmp_path):
    """A healthy vector index must not trigger any embedding work."""
    store = DocStore(tmp_path / "valid.db")
    doc = _indexed_document()
    store.upsert_document(doc)

    with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
        retriever = MagicMock()
        retriever.has_document.return_value = True
        mock_retriever_cls.return_value = retriever

        with patch("ui.hydration.LocalEmbedding") as mock_embed_cls:
            embedding = MagicMock()
            mock_embed_cls.return_value = embedding

            hydrate_startup_state(store)

    retriever.index_chunks.assert_not_called()
    embedding.get_embeddings.assert_not_called()
    assert st.session_state.document_metadata[doc.doc_id]["needs_reindex"] is False
    assert st.session_state._startup_hydrated is True


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

    with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
        retriever = MagicMock()
        # First call is the coverage scan (missing), second is post-write verification.
        retriever.has_document.side_effect = [False, True]
        mock_retriever_cls.return_value = retriever

        with patch("ui.hydration.LocalEmbedding") as mock_embed_cls:
            embedding = MagicMock()
            embedding.get_embeddings.return_value.tolist.return_value = [[0.1] * 384]
            mock_embed_cls.return_value = embedding

            hydrate_startup_state(
                store,
                progress_callback=lambda done, total, label: progress.append((done, total, label)),
            )

    assert retriever.index_chunks.call_count == 1
    assert progress, "Repair should report progress"
    assert progress[0][:2] == (0, 1)
    assert progress[-1][:2] == (1, 1)
    assert st.session_state.document_metadata[doc.doc_id]["needs_reindex"] is False
    assert st.session_state._startup_hydrated is True
