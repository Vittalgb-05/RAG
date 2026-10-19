"""Unit tests for startup state hydration from SQLite and LanceDB."""

from unittest.mock import MagicMock, patch
import pytest
import streamlit as st

from doc_store import DocStore
from models import Document
from ui.hydration import hydrate_startup_state


@pytest.fixture(autouse=True)
def clean_session_state():
    """Ensure clean Streamlit session state for hydration testing."""
    st.session_state.clear()
    st.session_state.doc_ids = set()
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
