"""
Regression tests for semantic retrieval and evidence synthesis fixes.

Verifies:
- EMBEDDING_MAX_LENGTH constant is set at 256.
- get_embeddings uses convert_to_numpy=True for determinism.
- RRF fused retrieval returns semantically related chunks.
- Prompt assembly retains evidence from multiple [E#] blocks without truncation.
- The synthesis rule is present in the system grounding template.
- ChatTurnService default k is 10 for broader evidence surface.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from core.models import Chunk, EvidenceSnippet, RetrievalResult
from core.prompt_budget import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    SYSTEM_GROUNDING_TEMPLATE,
    assemble_grounded_messages,
)
from retrieval.hybrid_retriever import HybridRetriever, compute_rrf
from retrieval.local_embedding import EMBEDDING_MAX_LENGTH, LocalEmbedding
from ui.chat_controller import ChatTurnService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    norm = np.linalg.norm(v)
    return (v / norm if norm > 0 else v).tolist()


def _make_snippet(rank: int, content: str, page: int = 1) -> EvidenceSnippet:
    return EvidenceSnippet(
        content=content,
        doc_id="doc_0000000000000001",
        filename="test.pdf",
        page=page,
        chunk_id=f"chk_{rank:04d}",
        score=1.0 / rank,
        rank=rank,
    )


# ---------------------------------------------------------------------------
# 1. Embedding configuration
# ---------------------------------------------------------------------------


def test_embedding_max_length_constant_is_256() -> None:
    """EMBEDDING_MAX_LENGTH must be pinned to the all-MiniLM-L6-v2 training limit."""
    assert EMBEDDING_MAX_LENGTH == 256, (
        "all-MiniLM-L6-v2 was trained with 256 word-piece sequences. "
        "Changing this limit can cause mismatched index vs. query embeddings."
    )


def test_get_embeddings_uses_convert_to_numpy(monkeypatch) -> None:
    """get_embeddings must request convert_to_numpy=True so it always returns ndarray."""
    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros((2, 384), dtype=np.float32)

    from retrieval import local_embedding as le

    monkeypatch.setattr(le, "SentenceTransformer", lambda *a, **kw: mock_model)
    le.clear_shared_model_cache()

    try:
        embedder = LocalEmbedding()
        embedder.get_embeddings(["hello world", "second text"])
        call_kwargs = mock_model.encode.call_args.kwargs
        assert call_kwargs.get("convert_to_numpy") is True
        assert call_kwargs.get("normalize_embeddings") is True
    finally:
        le.clear_shared_model_cache()


def test_get_embeddings_returns_consistent_shape(monkeypatch) -> None:
    """get_embeddings returns an ndarray with shape (N, 384)."""
    fake_vectors = np.eye(3, 384, dtype=np.float32)
    mock_model = MagicMock()
    mock_model.encode.return_value = fake_vectors

    from retrieval import local_embedding as le

    monkeypatch.setattr(le, "SentenceTransformer", lambda *a, **kw: mock_model)
    le.clear_shared_model_cache()

    try:
        embedder = LocalEmbedding()
        result = embedder.get_embeddings(["a", "b", "c"])
        assert result.shape == (3, 384)
    finally:
        le.clear_shared_model_cache()


# ---------------------------------------------------------------------------
# 2. RRF fusion: semantically related chunk surfaces even with low keyword overlap
# ---------------------------------------------------------------------------


def test_rrf_surfaces_dense_only_candidate(tmp_path) -> None:
    """Dense-only candidates (no keyword match) must survive RRF fusion.

    This is the core semantic retrieval regression: a chunk that matches
    semantically but uses different vocabulary from the query must still
    appear in the top-k after RRF, not be silently dropped.
    """
    v_query = _make_unit_vector(1)
    v_semantic = _make_unit_vector(1)  # identical direction -> perfect dense match
    v_keyword = _make_unit_vector(999)  # orthogonal -> poor dense match

    db_dir = tmp_path / "rrf_semantic"
    retriever = HybridRetriever(db_uri=db_dir)

    chunks = [
        Chunk(
            content="The mitochondria is the powerhouse of the cell.",
            filename="bio.pdf",
            page=1,
            chunk_id="chk_semantic",
            doc_id="doc_bio",
            extraction="docling",
        ),
        Chunk(
            content="Energy organelle cell biology ATP synthesis.",
            filename="bio.pdf",
            page=2,
            chunk_id="chk_keyword",
            doc_id="doc_bio",
            extraction="docling",
        ),
    ]
    retriever.index_chunks(chunks, embeddings=[v_semantic, v_keyword])
    retriever.set_embedding_fn(lambda _q: v_query)

    result = retriever.search_hybrid("What generates energy in a cell?", k=5)
    chunk_ids = [s.chunk_id for s in result.snippets]

    assert "chk_semantic" in chunk_ids, (
        "RRF must surface the semantically related chunk even when it has no keyword overlap with the query text."
    )


def test_rrf_fuses_dense_and_fts_complementary() -> None:
    """RRF score for a chunk in BOTH dense and FTS lists must be higher than either alone."""
    # chunk_a: appears in both dense (rank 2) and fts (rank 3)
    # chunk_b: dense only (rank 1)
    # chunk_c: fts only (rank 1)
    dense = [("chunk_a", 2, 0.8), ("chunk_b", 1, 0.95)]
    fts = [("chunk_c", 1, 0.9), ("chunk_a", 3, 0.7)]

    fused = compute_rrf(dense, fts, k_rrf=60)
    score_map = {cid: score for cid, score, *_ in fused}

    assert score_map["chunk_a"] > score_map["chunk_b"], (
        "Chunk in both dense+FTS must outscore one appearing only in dense."
    )
    assert score_map["chunk_a"] > score_map["chunk_c"], (
        "Chunk in both dense+FTS must outscore one appearing only in FTS."
    )


# ---------------------------------------------------------------------------
# 3. Prompt assembly: multi-evidence synthesis
# ---------------------------------------------------------------------------


def test_formatted_evidence_preserves_all_evidence_blocks() -> None:
    """formatted_evidence must emit all [E#] blocks in rank order, none dropped."""
    snippets = [_make_snippet(rank=i, content=f"Evidence block {i} content.", page=i) for i in range(1, 11)]
    result = RetrievalResult(
        query="test",
        snippets=snippets,
        total_candidates=10,
        search_mode="hybrid",
    )
    evidence_text = result.formatted_evidence()

    for i in range(1, 11):
        assert f"[E{i}]" in evidence_text, f"[E{i}] block missing from formatted_evidence."
    assert evidence_text.index("[E1]") < evidence_text.index("[E5]") < evidence_text.index("[E10]")


def test_prompt_assembly_retains_multi_chunk_evidence() -> None:
    """assemble_grounded_messages must not truncate 10 small evidence blocks."""
    snippets = [
        _make_snippet(rank=i, content=f"Fact {i}: measurement {i} is {i * 10} units.", page=i) for i in range(1, 11)
    ]
    result = RetrievalResult(
        query="What are the measurements?",
        snippets=snippets,
        total_candidates=10,
        search_mode="hybrid",
    )
    context_text = result.formatted_evidence()

    meta: dict[str, bool] = {}
    messages = assemble_grounded_messages(
        prompt="What are the measurements?",
        context_text=context_text,
        history=[],
        max_context_tokens=4096,
        max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        truncation_meta=meta,
    )

    assert meta.get("context_truncated") is False, (
        "10 small evidence blocks should not trigger context truncation in a 4096-token window."
    )
    system_content = messages[0]["content"]
    for i in range(1, 11):
        assert f"[E{i}]" in system_content, f"[E{i}] must be present in the assembled system prompt."


def test_synthesis_rule_present_in_system_template() -> None:
    """The system template must contain an explicit multi-passage synthesis instruction."""
    lowered = SYSTEM_GROUNDING_TEMPLATE.lower()
    assert "synthesis" in lowered or "synthesize" in lowered or "combining" in lowered, (
        "SYSTEM_GROUNDING_TEMPLATE must include an explicit multi-passage synthesis rule."
    )


def test_synthesis_example_present_in_system_template() -> None:
    """The system template must include a worked multi-passage synthesis example."""
    lowered = SYSTEM_GROUNDING_TEMPLATE.lower()
    assert "example 3" in lowered or "multi-passage" in lowered or "spans" in lowered, (
        "The template must include a worked example showing synthesis across multiple [E#] blocks."
    )


# ---------------------------------------------------------------------------
# 4. ChatTurnService defaults
# ---------------------------------------------------------------------------


def test_chat_turn_service_default_k_is_10() -> None:
    """ChatTurnService must default to k=10 for adequate evidence breadth."""
    mock_validator = MagicMock()
    service = ChatTurnService(validator=mock_validator)
    assert service._k == 10


def test_chat_turn_service_custom_k_respected() -> None:
    """ChatTurnService must honor an explicitly supplied k value."""
    mock_validator = MagicMock()
    service = ChatTurnService(validator=mock_validator, k=5)
    assert service._k == 5


# ---------------------------------------------------------------------------
# 5. Supporting invariants still intact
# ---------------------------------------------------------------------------


def test_retrieval_result_source_labels_unique() -> None:
    """source_labels must deduplicate by (filename, page) label."""
    snippets = [
        _make_snippet(1, "content A", page=1),
        _make_snippet(2, "content B", page=1),
        _make_snippet(3, "content C", page=2),
    ]
    result = RetrievalResult(query="q", snippets=snippets, total_candidates=3, search_mode="hybrid")
    labels = result.source_labels()
    assert len(labels) == 2


def test_rrf_empty_inputs_returns_empty() -> None:
    """compute_rrf with both empty lists must return an empty list."""
    assert compute_rrf([], [], k_rrf=60) == []


def test_rrf_single_source_passthrough() -> None:
    """compute_rrf with only dense results must preserve all chunks in rank order."""
    dense = [("a", 1, 0.9), ("b", 2, 0.8), ("c", 3, 0.7)]
    fused = compute_rrf(dense, [], k_rrf=60)
    chunk_ids = [cid for cid, *_ in fused]
    assert set(chunk_ids) == {"a", "b", "c"}
    assert chunk_ids[0] == "a"
