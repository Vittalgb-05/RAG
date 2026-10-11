"""Unit tests for HybridRetriever persistent vector storage and CPU embedding pipeline (RETR-01, RETR-02)."""

from unittest.mock import MagicMock

import numpy as np

from hybrid_retriever import DEFAULT_DB_URI, HybridRetriever
from local_embedding import LocalEmbedding
from models import Chunk


def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized float vector."""
    np.random.seed(seed)
    v = np.random.randn(dim).astype(np.float32)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return [float(x) for x in v]


def test_local_embedding_cpu_pinning():
    """Verify LocalEmbedding explicitly initializes SentenceTransformer on CPU (RETR-01)."""
    mock_st_class = MagicMock()
    import local_embedding

    original_st = local_embedding.SentenceTransformer
    try:
        local_embedding.SentenceTransformer = mock_st_class
        embedder = LocalEmbedding(model_name="all-MiniLM-L6-v2")
        assert embedder.device == "cpu"
        mock_st_class.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")
    finally:
        local_embedding.SentenceTransformer = original_st


def test_hybrid_retriever_anchored_default_path():
    """Verify default storage URI is anchored to repository root rather than CWD."""
    retriever = HybridRetriever()
    assert retriever.db_uri == DEFAULT_DB_URI
    assert retriever.db_uri.is_absolute()
    assert retriever.db_uri.name == "lancedb"
    assert retriever.db_uri.parent.name == "data"


def test_hybrid_retriever_dense_indexing_and_search(tmp_path):
    """Verify chunks are indexed and nearest neighbors returned by cosine similarity."""
    db_dir = tmp_path / "lancedb_test"
    retriever = HybridRetriever(db_uri=db_dir)

    v1 = _make_unit_vector(101)
    v2 = _make_unit_vector(202)
    v3 = _make_unit_vector(303)

    chunks = [
        Chunk(
            content="NVIDIA RTX 3050 Laptop GPU with 4GB VRAM.",
            filename="gpu_specs.pdf",
            page=1,
            chunk_id="chk_gpu_01",
            doc_id="doc_gpu",
            extraction="docling",
        ),
        Chunk(
            content="Qwen3-VL 2B quantized multimodal model inference.",
            filename="vlm_notes.pdf",
            page=2,
            chunk_id="chk_vlm_02",
            doc_id="doc_vlm",
            extraction="docling",
        ),
        Chunk(
            content="Financial accounting quarterly revenue report.",
            filename="finance.pdf",
            page=1,
            chunk_id="chk_fin_03",
            doc_id="doc_fin",
            extraction="pypdf",
        ),
    ]

    indexed_count = retriever.index_chunks(chunks, embeddings=[v1, v2, v3])
    assert indexed_count == 3
    assert retriever.count_chunks() == 3
    assert retriever.has_document("doc_gpu")
    assert retriever.has_document("doc_vlm")
    assert not retriever.has_document("doc_nonexistent")

    # Search with v1: chk_gpu_01 should be top-1 with near 1.0 similarity score
    results = retriever.search_dense(v1, k=2)
    assert len(results) == 2
    top = results[0]
    assert top["chunk_id"] == "chk_gpu_01"
    assert top["doc_id"] == "doc_gpu"
    assert top["score"] >= 0.95


def test_hybrid_retriever_disk_persistence(tmp_path):
    """Verify data persists on disk across retriever re-instantiations (RETR-02)."""
    db_dir = tmp_path / "persistent_lancedb"

    # Instance 1: write data
    retriever1 = HybridRetriever(db_uri=db_dir)
    vec = _make_unit_vector(42)
    chunk = Chunk(
        content="Persistent storage verification across instance restart.",
        filename="restart.pdf",
        page=1,
        chunk_id="chk_restart_01",
        doc_id="doc_restart",
    )
    retriever1.index_chunks([chunk], embeddings=[vec])
    assert retriever1.count_chunks() == 1

    # Instance 2: reopen same directory
    retriever2 = HybridRetriever(db_uri=db_dir)
    assert retriever2.has_document("doc_restart")
    assert retriever2.count_chunks() == 1

    results = retriever2.search_dense(vec, k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "chk_restart_01"
    assert results[0]["filename"] == "restart.pdf"
    assert "Persistent storage" in results[0]["content"]


def test_hybrid_retriever_document_deletion(tmp_path):
    """Verify document chunks can be deleted cleanly without affecting other documents."""
    db_dir = tmp_path / "deletion_test"
    retriever = HybridRetriever(db_uri=db_dir)

    v1 = _make_unit_vector(11)
    v2 = _make_unit_vector(22)

    chunks = [
        Chunk(content="Doc A content", filename="doc_a.pdf", page=1, chunk_id="chk_a1", doc_id="doc_a"),
        Chunk(content="Doc B content", filename="doc_b.pdf", page=1, chunk_id="chk_b1", doc_id="doc_b"),
    ]
    retriever.index_chunks(chunks, embeddings=[v1, v2])
    assert retriever.count_chunks() == 2

    # Delete Doc A
    retriever.delete_document("doc_a")
    assert not retriever.has_document("doc_a")
    assert retriever.has_document("doc_b")
    assert retriever.count_chunks() == 1

    # Search should only find Doc B
    results = retriever.search_dense(v1, k=5)
    assert len(results) == 1
    assert results[0]["doc_id"] == "doc_b"


def test_hybrid_retriever_fallback_when_lancedb_missing(tmp_path, monkeypatch):
    """Verify graceful fallback to VectorIndex when LanceDB is not available."""
    monkeypatch.setattr("hybrid_retriever.lancedb", None)

    retriever = HybridRetriever(db_uri=tmp_path / "fallback_db")
    assert not retriever.is_persistent()

    v1 = _make_unit_vector(77)
    chunk = Chunk(content="Fallback chunk content.", filename="fb.pdf", page=1, chunk_id="chk_fb_1", doc_id="doc_fb")
    retriever.index_chunks([chunk], embeddings=[v1])

    assert retriever.count_chunks() == 1
    assert retriever.has_document("doc_fb")

    results = retriever.search_dense(v1, k=1)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "chk_fb_1"
    assert results[0]["score"] >= 0.95
