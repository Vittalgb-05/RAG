"""Unit tests for query intent detection and retrieval routing."""

from unittest.mock import MagicMock

from core.models import EvidenceSnippet, RetrievalResult
from core.query_intent import (
    is_whole_document_query,
    resolve_retrieval,
)


def test_is_whole_document_query_patterns() -> None:
    """Verify exhaustive inventory phrasing matches while specific questions do not."""
    # Matches with verbs like mention, state, list, tell
    assert is_whole_document_query("mention all the questions that are there in the question paper")
    assert is_whole_document_query("mention all the questions")
    assert is_whole_document_query("tell me all the exercises")
    assert is_whole_document_query("state the questions in the document")
    assert is_whole_document_query("what questions are in the paper")
    assert is_whole_document_query("list every problem in this PDF")
    assert is_whole_document_query("give all topics covered")
    assert is_whole_document_query("summarize the entire document")

    # Non-exhaustive targeted queries must stay False
    assert not is_whole_document_query("What is the greenhouse effect?")
    assert not is_whole_document_query("Explain question 2 in detail.")
    assert not is_whole_document_query("Who wrote this paper?")
    assert not is_whole_document_query("How does photosynthesis work?")


def test_resolve_retrieval_intent_mismatch_when_doc_id_missing() -> None:
    """When whole-document intent is detected but doc_id is None, return intent_mismatch."""
    retriever = MagicMock()
    query = "mention all the questions that are there in the question paper"

    res = resolve_retrieval(retriever, query, doc_id=None)
    assert isinstance(res, RetrievalResult)
    assert res.search_mode == "intent_mismatch"
    assert res.snippets == []
    assert res.total_candidates == 0
    # Retriever should not have been called for hybrid search or fetch_document_chunks
    assert not retriever.search_hybrid.called
    assert not retriever.fetch_document_chunks.called


def test_resolve_retrieval_intent_mismatch_when_doc_id_is_list() -> None:
    """When whole-document intent is detected but multiple docs are scoped, return intent_mismatch."""
    retriever = MagicMock()
    query = "list all questions in the document"

    res = resolve_retrieval(retriever, query, doc_id=["doc_1", "doc_2"])
    assert res.search_mode == "intent_mismatch"
    assert res.snippets == []


def test_resolve_retrieval_success_with_single_doc_id() -> None:
    """When single doc_id is provided, resolve_retrieval calls fetch_document_chunks."""
    retriever = MagicMock()
    snippets = [
        EvidenceSnippet(
            content=f"Question {i}",
            doc_id="doc_evs",
            filename="evs.pdf",
            page=i,
            chunk_id=f"chk_{i}",
            score=1.0,
            rank=i,
        )
        for i in range(1, 5)
    ]
    retriever.fetch_document_chunks.return_value = RetrievalResult(
        query="",
        snippets=snippets,
        total_candidates=4,
        search_mode="document",
    )

    query = "mention all the questions that are there in the question paper"
    res = resolve_retrieval(retriever, query, doc_id="doc_evs")

    assert res.search_mode == "document"
    assert len(res.snippets) == 4
    retriever.fetch_document_chunks.assert_called_once_with("doc_evs")


def test_resolve_retrieval_falls_back_to_search_hybrid_for_targeted_query() -> None:
    """Non-inventory queries route to search_hybrid."""
    retriever = MagicMock()
    snippets = [
        EvidenceSnippet(
            content="Acid rain is caused by...",
            doc_id="doc_evs",
            filename="evs.pdf",
            page=1,
            chunk_id="chk_1",
            score=0.9,
            rank=1,
        )
    ]
    retriever.search_hybrid.return_value = RetrievalResult(
        query="what is acid rain?",
        snippets=snippets,
        total_candidates=1,
        search_mode="hybrid",
    )

    res = resolve_retrieval(retriever, "what is acid rain?", doc_id="doc_evs", k=5)
    assert res.search_mode == "hybrid"
    retriever.search_hybrid.assert_called_once_with("what is acid rain?", k=5, doc_id="doc_evs")
