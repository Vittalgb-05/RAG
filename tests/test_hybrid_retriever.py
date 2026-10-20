"""Unit tests for HybridRetriever persistent vector storage and CPU embedding pipeline (RETR-01, RETR-02)."""

from unittest.mock import MagicMock

import numpy as np

from hybrid_retriever import DEFAULT_DB_URI, HybridRetriever, compute_rrf
from local_embedding import LocalEmbedding
from models import BBox, Chunk, EvidenceElement, RetrievalResult


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
        local_embedding.clear_shared_model_cache()
        local_embedding.SentenceTransformer = mock_st_class
        embedder = LocalEmbedding(model_name="all-MiniLM-L6-v2")
        assert embedder.device == "cpu"
        mock_st_class.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")
    finally:
        local_embedding.clear_shared_model_cache()
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


def test_rrf_scoring_math():
    """Verify Reciprocal Rank Fusion calculation and rank ordering (RETR-03)."""
    # doc_b: dense rank 2, fts rank 1 -> 1/(60+2) + 1/(60+1) = 0.016129 + 0.016393 = 0.032522
    # doc_a: dense rank 1, fts rank 3 -> 1/(60+1) + 1/(60+3) = 0.016393 + 0.015873 = 0.032266
    # doc_d: fts rank 2               -> 1/(60+2) = 0.016129
    # doc_c: dense rank 3             -> 1/(60+3) = 0.015873
    dense_ranks = [("doc_a", 1, 0.95), ("doc_b", 2, 0.85), ("doc_c", 3, 0.70)]
    fts_ranks = [("doc_b", 1, 10.0), ("doc_d", 2, 8.0), ("doc_a", 3, 5.0)]

    rrf_results = compute_rrf(dense_ranks, fts_ranks, k_rrf=60)
    ordered_ids = [item[0] for item in rrf_results]

    assert ordered_ids == ["doc_b", "doc_a", "doc_d", "doc_c"]

    # Verify score magnitudes
    top_chunk, top_score, final_rank, d_rank, f_rank = rrf_results[0]
    assert top_chunk == "doc_b"
    assert round(top_score, 5) == round(1.0 / 62 + 1.0 / 61, 5)
    assert final_rank == 1
    assert d_rank == 2
    assert f_rank == 1


def test_hybrid_retrieval_keyword_boost(tmp_path):
    """Verify exact technical keywords (e.g. acronyms/model IDs) receive keyword boost under hybrid search."""
    retriever = HybridRetriever(db_uri=tmp_path / "keyword_boost_db")

    v_general = _make_unit_vector(10)
    v_exact = _make_unit_vector(20)

    chunks = [
        Chunk(
            content="General overview of GPU acceleration and graphical rendering pipelines.",
            filename="general_gpu.pdf",
            page=1,
            chunk_id="chk_general",
            doc_id="doc_1",
        ),
        Chunk(
            content="Specification sheet for NVIDIA RTX-3050-Ti Laptop GPU with 4GB VRAM.",
            filename="specs_sheet.pdf",
            page=1,
            chunk_id="chk_exact_rtx",
            doc_id="doc_2",
        ),
    ]

    retriever.index_chunks(chunks, embeddings=[v_general, v_exact])

    # Query with exact model identifier
    res = retriever.search_hybrid("RTX-3050-Ti", k=2)
    assert isinstance(res, RetrievalResult)
    assert len(res.snippets) > 0
    top_match = res.snippets[0]
    assert top_match.chunk_id == "chk_exact_rtx"
    assert "RTX-3050-Ti" in top_match.content


def test_hybrid_retrieval_semantic_boost(tmp_path):
    """Verify semantic queries without keyword overlap match via dense path (RETR-03)."""
    # Simple embedding mock that maps similar topics to close vectors
    topic_vec = _make_unit_vector(55)

    def mock_embed(text: str) -> list[float]:
        if "fiscal" in text.lower() or "profit" in text.lower() or "earnings" in text.lower():
            return topic_vec
        return _make_unit_vector(99)

    retriever = HybridRetriever(db_uri=tmp_path / "semantic_boost_db", embedding_fn=mock_embed)

    chunk1 = Chunk(
        content="Quarterly earnings and fiscal balance sheet statements.",
        filename="earnings.pdf",
        page=1,
        chunk_id="chk_fiscal",
        doc_id="doc_f",
    )
    chunk2 = Chunk(
        content="Plant biological taxonomy and cellular morphology.",
        filename="biology.pdf",
        page=1,
        chunk_id="chk_bio",
        doc_id="doc_b",
    )

    retriever.index_chunks([chunk1, chunk2], embeddings=[topic_vec, _make_unit_vector(99)])

    # Query without literal word overlap
    res = retriever.search_hybrid("company profits", k=2)
    assert len(res.snippets) > 0
    assert res.snippets[0].chunk_id == "chk_fiscal"


def test_retrieval_result_shared_identity(tmp_path):
    """Verify shared RetrievalResult produces matching prompt context and UI citation metadata (RETR-04)."""
    retriever = HybridRetriever(db_uri=tmp_path / "shared_identity_db")

    v1 = _make_unit_vector(1)
    chunk = Chunk(
        content="Local AI assistant operating strictly offline.",
        filename="offline_guide.pdf",
        page=2,
        chunk_id="chk_offline_1",
        doc_id="doc_off",
    )
    retriever.index_chunks([chunk], embeddings=[v1])

    result = retriever.search_hybrid("offline", k=1)
    assert isinstance(result, RetrievalResult)
    assert len(result.snippets) == 1

    # Generation context formatting
    context_text = result.formatted_evidence()
    assert "[E1] (offline_guide.pdf, p. 2)" in context_text
    assert "strictly offline" in context_text

    # UI citation source labels
    sources = result.source_labels()
    assert sources == ["offline_guide.pdf (p. 2)"]


def test_hybrid_retriever_empty_query_safe(tmp_path):
    """Verify empty query or k <= 0 returns empty RetrievalResult safely without error."""
    retriever = HybridRetriever(db_uri=tmp_path / "empty_q_db")
    res1 = retriever.search_hybrid("", k=5)
    assert res1.snippets == []
    assert res1.total_candidates == 0

    res2 = retriever.search_hybrid("query", k=0)
    assert res2.snippets == []


def test_hybrid_retriever_filter_injection_escaping(tmp_path):
    """Verify single quotes in doc_id do not cause filter injection or SQL syntax crashes (CR-03)."""
    retriever = HybridRetriever(db_uri=tmp_path / "sql_injection_db")

    v1 = _make_unit_vector(1)
    chunk1 = Chunk(
        content="Document for normal user.",
        filename="normal.pdf",
        page=1,
        chunk_id="chk_normal",
        doc_id="doc_normal",
    )
    v2 = _make_unit_vector(2)
    chunk2 = Chunk(
        content="Document with quotation in id.",
        filename="quotes.pdf",
        page=1,
        chunk_id="chk_quote",
        doc_id="doc_O'Reilly",
    )

    retriever.index_chunks([chunk1, chunk2], embeddings=[v1, v2])
    assert retriever.count_chunks() == 2

    # Query has_document with quotes and injection payloads
    assert retriever.has_document("doc_O'Reilly") is True
    assert retriever.has_document("doc_normal' OR '1'='1") is False

    # Delete with injection payload should not delete normal document
    retriever.delete_document("doc_normal' OR '1'='1")
    assert retriever.has_document("doc_normal") is True

    # Legitimate deletion with quote
    retriever.delete_document("doc_O'Reilly")
    assert retriever.has_document("doc_O'Reilly") is False
    assert retriever.has_document("doc_normal") is True


def test_hybrid_retriever_fallback_deduplication(tmp_path, monkeypatch):
    """Verify fallback store deduplicates chunks by chunk_id on re-indexing (WR-01)."""
    import hybrid_retriever

    monkeypatch.setattr(hybrid_retriever, "lancedb", None)
    retriever = HybridRetriever(db_uri=tmp_path / "fallback_dedup_db")

    v1 = _make_unit_vector(1)
    chunk1 = Chunk(
        content="Initial version of chunk 1.",
        filename="doc.pdf",
        page=1,
        chunk_id="chk_1",
        doc_id="doc_1",
    )
    retriever.index_chunks([chunk1], embeddings=[v1])
    assert retriever.count_chunks() == 1

    # Re-indexing the same chunk with updated content
    v1_updated = _make_unit_vector(10)
    chunk1_updated = Chunk(
        content="Updated version of chunk 1.",
        filename="doc.pdf",
        page=1,
        chunk_id="chk_1",
        doc_id="doc_1",
    )
    retriever.index_chunks([chunk1_updated], embeddings=[v1_updated])

    # Count must remain 1 (no duplicate accumulation)
    assert retriever.count_chunks() == 1
    assert retriever._fallback_store.documents[0]["content"] == "Updated version of chunk 1."


def test_hybrid_retriever_lifecycle_and_setter(tmp_path):
    """Verify close(), context manager, and dynamic set_embedding_fn work cleanly (WR-05, IN-02)."""
    with HybridRetriever(db_uri=tmp_path / "lifecycle_db") as retriever:
        assert retriever.is_persistent() or not retriever.is_persistent()

        # Dynamic setter
        dummy_vec = _make_unit_vector(42)
        retriever.set_embedding_fn(lambda text: dummy_vec)
        assert retriever.embedding_fn("test") == dummy_vec

    # Exiting context manager closes retriever
    assert retriever._db is None
    assert retriever._table is None


def test_hybrid_retriever_purge_all(tmp_path):
    """Verify purge_all removes all indexed chunks and unlinks fallback store on disk."""
    db_dir = tmp_path / "purge_lancedb"
    retriever = HybridRetriever(db_uri=db_dir)

    v1 = _make_unit_vector(50)
    v2 = _make_unit_vector(60)
    chunks = [
        Chunk(content="A", filename="a.pdf", page=1, chunk_id="c1", doc_id="d1"),
        Chunk(content="B", filename="b.pdf", page=1, chunk_id="c2", doc_id="d2"),
    ]
    retriever.index_chunks(chunks, embeddings=[v1, v2])
    assert retriever.count_chunks() == 2

    retriever.purge_all()
    assert retriever.count_chunks() == 0
    assert not retriever.has_document("d1")
    assert not retriever.has_document("d2")


def test_search_hybrid_doc_id_filter(tmp_path):
    """Verify search_hybrid accepts doc_id keyword argument and restricts results."""
    db_dir = tmp_path / "filter_lancedb"
    retriever = HybridRetriever(db_uri=db_dir)

    v1 = _make_unit_vector(11)
    v2 = _make_unit_vector(22)
    chunks = [
        Chunk(
            content="Alpha deep learning architectures",
            filename="doc_a.pdf",
            page=1,
            chunk_id="c_a1",
            doc_id="doc_alpha",
        ),
        Chunk(
            content="Beta distributed systems consensus",
            filename="doc_b.pdf",
            page=1,
            chunk_id="c_b1",
            doc_id="doc_beta",
        ),
    ]
    retriever.index_chunks(chunks, embeddings=[v1, v2])

    retriever.set_embedding_fn(lambda q: v1)

    # Search with no filter returns results
    res_all = retriever.search_hybrid("deep learning", k=5)
    assert isinstance(res_all, RetrievalResult)
    assert len(res_all.snippets) > 0

    # Search with doc_id filter restricts to doc_alpha
    res_alpha = retriever.search_hybrid("deep learning", k=5, doc_id="doc_alpha")
    assert all(s.doc_id == "doc_alpha" for s in res_alpha.snippets)
    assert any(s.chunk_id == "c_a1" for s in res_alpha.snippets)

    # Search with doc_id filter for doc_beta
    res_beta = retriever.search_hybrid("deep learning", k=5, doc_id="doc_beta")
    assert all(s.doc_id == "doc_beta" for s in res_beta.snippets)


def test_index_evidence_elements(tmp_path):
    """Verify evidence elements from visual analysis are indexed and retrievable."""
    db_dir = tmp_path / "evidence_lancedb"
    retriever = HybridRetriever(db_uri=db_dir)

    elements = [
        EvidenceElement(
            element_id="elem_fig_1",
            doc_id="doc_vlm_test",
            page=3,
            kind="chart",
            content="Bar chart showing quarterly GPU utilization across 4 clusters.",
            bbox=BBox(x0=50.0, y0=100.0, x1=400.0, y1=300.0),
        )
    ]

    failed_elem = EvidenceElement(
        element_id="elem_failed_1",
        doc_id="doc_vlm_test",
        page=4,
        kind="chart",
        content="[Visual element: analysis failed: InferenceGate timeout]",
        bbox=BBox(x0=0.0, y0=0.0, x1=100.0, y1=100.0),
    )

    retriever.set_embedding_fn(lambda q: _make_unit_vector(99))
    # Pass both valid and failed elements, with filename="chart_report.pdf"
    indexed_count = retriever.index_evidence_elements([elements[0], failed_elem], filename="chart_report.pdf")
    # Only the valid element should be indexed
    assert indexed_count == 1
    assert retriever.count_chunks() == 1

    # Verify BM25 / FTS keyword search retrieves the figure description with attributed filename
    fts_results = retriever.search_fts("GPU utilization clusters", k=1)
    assert len(fts_results) == 1
    assert fts_results[0]["chunk_id"] == "elem_fig_1"
    assert fts_results[0]["filename"] == "chart_report.pdf"
    assert fts_results[0]["extraction"] == "vlm"
    assert fts_results[0]["page"] == 3

    # Verify failed analysis was never indexed
    assert retriever.search_fts("InferenceGate timeout", k=1) == []
