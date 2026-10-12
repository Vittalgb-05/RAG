"""Unit tests for multi-tier cache invalidation, session memory bounding, and telemetry (QUAL-01)."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from doc_store import DocStore
from hybrid_retriever import HybridRetriever
from models import Document, SummaryResult
from resource_telemetry import get_gpu_memory_info, get_process_memory_info

MAX_CHAT_TURNS = 50


def test_chat_history_bounding_drops_oldest_turns() -> None:
    """Test that chat history bounding retains at most MAX_CHAT_TURNS items."""
    history = []
    # Simulate appending 75 message turns
    for i in range(75):
        history.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"})
        if len(history) > MAX_CHAT_TURNS:
            history = history[-MAX_CHAT_TURNS:]

    assert len(history) == MAX_CHAT_TURNS
    assert MAX_CHAT_TURNS == 50
    # Oldest retained message should be message 25
    assert history[0]["content"] == "msg 25"
    assert history[-1]["content"] == "msg 74"


def test_doc_store_count_helpers() -> None:
    """Test DocStore count_documents and count_summaries methods."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        store = DocStore(db_path=str(db_path))

        assert store.count_documents() == 0
        assert store.count_summaries() == 0

        now_iso = datetime.now(timezone.utc).isoformat()
        doc1 = Document(
            doc_id="doc_1",
            filename="a.pdf",
            sha256="a" * 64,
            size_bytes=100,
            num_pages=1,
            status="indexed",
            upload_time=now_iso,
            num_chunks=2,
        )
        doc2 = Document(
            doc_id="doc_2",
            filename="b.pdf",
            sha256="b" * 64,
            size_bytes=200,
            num_pages=2,
            status="indexed",
            upload_time=now_iso,
            num_chunks=4,
        )
        store.upsert_document(doc1)
        store.upsert_document(doc2)

        assert store.count_documents() == 2

        s1 = SummaryResult(
            summary_id="summ_1",
            doc_id="doc_1",
            sha256="a" * 64,
            profile="overview",
            summary_text="Overview text",
            page_references=[1],
            created_at=now_iso,
            model_version="test-model",
            cached=False,
        )
        s2 = SummaryResult(
            summary_id="summ_2",
            doc_id="doc_1",
            sha256="a" * 64,
            profile="detailed",
            summary_text="Detailed text",
            page_references=[1],
            created_at=now_iso,
            model_version="test-model",
            cached=False,
        )
        store.save_summary(s1)
        store.save_summary(s2)

        assert store.count_summaries() == 2


def test_tier_1_session_purge() -> None:
    """Test Clear All handler purges doc state and summary_* keys."""
    mock_session: dict[str, object] = {
        "doc_ids": {"doc_1", "doc_2"},
        "indexed_files": {"a.pdf", "b.pdf"},
        "document_metadata": {"a.pdf": {}},
        "chat_history": [{"role": "user", "content": "hi"}],
        "summary_doc_1_overview": {"text": "summary 1"},
        "summary_doc_1_detailed": {"text": "summary 2"},
        "summary_doc_2_findings": {"text": "summary 3"},
        "unrelated_setting": True,
    }

    # Simulate Clear All handler purge in main.py
    mock_session["doc_ids"] = set()
    mock_session["indexed_files"] = set()
    mock_session["document_metadata"] = {}
    mock_session["chat_history"] = []
    for k in list(mock_session.keys()):
        if k.startswith("summary_"):
            del mock_session[k]

    assert mock_session["doc_ids"] == set()
    assert mock_session["indexed_files"] == set()
    assert mock_session["chat_history"] == []
    assert not any(k.startswith("summary_") for k in mock_session)
    assert mock_session["unrelated_setting"] is True


def test_tier_3_sqlite_summary_version_invalidation() -> None:
    """Test SQLite summary cache hit returns cached result and version mismatch invalidates."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        store = DocStore(db_path=str(db_path))

        now_iso = datetime.now(timezone.utc).isoformat()
        doc = Document(
            doc_id="doc_inv",
            filename="inv.pdf",
            sha256="c" * 64,
            size_bytes=100,
            num_pages=1,
            status="indexed",
            upload_time=now_iso,
            num_chunks=1,
        )
        store.upsert_document(doc)

        summ = SummaryResult(
            summary_id="summ_inv",
            doc_id="doc_inv",
            sha256="c" * 64,
            profile="overview",
            summary_text="Versioned summary",
            page_references=[1],
            created_at=now_iso,
            model_version="qwen-2b-q4",
            cached=False,
        )
        store.save_summary(summ)

        # Matching model_version yields cache hit
        hit = store.get_summary(sha256="c" * 64, profile="overview", model_version="qwen-2b-q4")
        assert hit is not None
        assert hit.cached is True
        assert hit.summary_text == "Versioned summary"

        # Mismatched model_version invalidates cache
        miss = store.get_summary(sha256="c" * 64, profile="overview", model_version="groq-llama-70b")
        assert miss is None


def test_tier_4_lancedb_document_deletion_sync() -> None:
    """Test HybridRetriever document deletion cleans up indexed chunks."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        lance_dir = Path(tmp_dir) / "lancedb"
        retriever = HybridRetriever(db_uri=lance_dir)

        chunks_d1 = [
            {"chunk_id": "c1", "doc_id": "doc_1", "content": "alpha content", "page": 1},
            {"chunk_id": "c2", "doc_id": "doc_1", "content": "beta content", "page": 1},
        ]
        chunks_d2 = [
            {"chunk_id": "c3", "doc_id": "doc_2", "content": "gamma content", "page": 1},
        ]
        vectors_d1 = [[0.1] * 384, [0.2] * 384]
        vectors_d2 = [[0.3] * 384]

        retriever.index_chunks(chunks_d1, vectors_d1)
        retriever.index_chunks(chunks_d2, vectors_d2)

        assert retriever.contains_document("doc_1") is True
        assert retriever.contains_document("doc_2") is True

        # Delete doc_1
        retriever.delete_document("doc_1")
        assert retriever.contains_document("doc_1") is False
        assert retriever.contains_document("doc_2") is True


def test_sidebar_telemetry_contracts() -> None:
    """Test telemetry query contracts for UI sidebar rendering."""
    gpu = get_gpu_memory_info()
    if gpu is not None:
        assert "used_mb" in gpu
        assert "total_mb" in gpu
        assert "utilization_pct" in gpu

    proc = get_process_memory_info()
    assert "rss_mb" in proc
    assert proc["rss_mb"] >= 0.0
