# ------------------------------------------------------------------
# Unit Tests for LocalEmbedding
# Tests embedding generation, batch index building, and context retrieval
# ------------------------------------------------------------------

from unittest.mock import patch
from local_embedding import LocalEmbedding


def test_local_embedding_initialization(mock_sentence_transformer):
    """Verify initialization and model instantiation."""
    embedding = LocalEmbedding(model_name="all-MiniLM-L6-v2", distance_metric="cosine")
    assert embedding.model_name == "all-MiniLM-L6-v2"
    assert embedding.store._distance_metric == "cosine"


def test_local_embedding_build_index(mock_sentence_transformer):
    """Verify build_index embeds chunks and populates VectorIndex."""
    embedding = LocalEmbedding()
    chunks = [
        {"content": "Document chunk number 1", "page": 1, "filename": "doc.pdf"},
        {"content": "Document chunk number 2", "page": 2, "filename": "doc.pdf"},
        {"content": "Document chunk number 3", "page": 3, "filename": "doc.pdf"},
    ]

    embedding.build_index(chunks)
    assert len(embedding.store) == 3
    assert embedding.store._vector_dim == 384


def test_local_embedding_get_context(mock_sentence_transformer):
    """Verify get_context retrieves top-k chunks with delimiters and respects k parameter."""
    embedding = LocalEmbedding()
    chunks = [
        {"content": "Primary architectural specification for local RAG.", "page": 1},
        {"content": "Secondary discussion of memory management on 4GB VRAM.", "page": 2},
    ]
    embedding.build_index(chunks)

    # Verify get_context with explicit k=10 forwards k=10 to search (00-02-PLAN Task 2 requirement)
    with patch.object(embedding, "search", wraps=embedding.search) as spy_search:
        context = embedding.get_context("memory management", k=10)
        spy_search.assert_called_once_with("memory management", k=10)
        assert "\n\n---\n\n" in context
        assert "management" in context
