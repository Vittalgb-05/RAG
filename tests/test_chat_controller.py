"""Characterization tests for framework-independent chat-turn orchestration."""

from __future__ import annotations

from typing import Any

from core.citation_validator import CitationVerificationResult
from core.models import EvidenceSnippet, RetrievalResult
from ui.chat_controller import ChatTurnService


def _snippet(
    rank: int = 1,
    *,
    content: str = "Acid rain lowers soil pH.",
    doc_id: str = "doc_alpha",
    filename: str = "alpha.pdf",
    page: int = 1,
) -> EvidenceSnippet:
    return EvidenceSnippet(
        content=content,
        doc_id=doc_id,
        filename=filename,
        page=page,
        chunk_id=f"chunk_{doc_id}_{rank}",
        score=1.0 / rank,
        rank=rank,
    )


def _result(
    *snippets: EvidenceSnippet, search_mode: str = "hybrid", chunk_cap_reached: bool = False
) -> RetrievalResult:
    return RetrievalResult(
        query="query",
        snippets=list(snippets),
        total_candidates=len(snippets),
        search_mode=search_mode,
        chunk_cap_reached=chunk_cap_reached,
    )


class FakeHybridRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def search_hybrid(self, query: str, k: int = 8, doc_id: str | None = None) -> RetrievalResult:
        self.calls.append({"query": query, "k": k, "doc_id": doc_id})
        return self.result


def _validator(cited_ranks: list[int]) -> Any:
    def validate(_text: str, _retrieval: RetrievalResult | None) -> CitationVerificationResult:
        return CitationVerificationResult(
            is_valid=bool(cited_ranks),
            precision=1.0 if cited_ranks else 0.0,
            total_citations=len(cited_ranks),
            valid_citations=[f"[E{rank}]" for rank in cited_ranks],
            hallucinated_citations=[],
            cited_ranks=cited_ranks,
            abstention_detected=False,
            message="characterization stub",
        )

    return validate


def test_prepare_prefers_explicit_document_filter_over_prompt_mention() -> None:
    retriever = FakeHybridRetriever(_result(_snippet(doc_id="doc_beta", filename="beta.pdf")))
    service = ChatTurnService(_validator([1]))

    prepared = service.prepare(
        prompt="Compare this with alpha.pdf",
        history_before_turn=[],
        selected_doc="doc_beta",
        document_metadata={
            "doc_alpha": {"filename": "alpha.pdf", "pages": 3},
            "doc_beta": {"filename": "beta.pdf", "pages": 4},
        },
        retriever=retriever,
        context_window=4096,
    )

    assert prepared.doc_filter == "doc_beta"
    assert prepared.retrieval_scope == "doc_beta"
    assert retriever.calls == [{"query": "Compare this with alpha.pdf", "k": 10, "doc_id": "doc_beta"}]


def test_prepare_infers_single_document_scope_without_changing_doc_filter() -> None:
    retriever = FakeHybridRetriever(_result(_snippet(doc_id="doc_only", filename="only.pdf")))
    service = ChatTurnService(_validator([1]))

    prepared = service.prepare(
        prompt="What is the main finding?",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={"doc_only": {"filename": "only.pdf", "pages": 2}},
        retriever=retriever,
        context_window=4096,
    )

    assert prepared.doc_filter is None
    assert prepared.retrieval_scope == "doc_only"
    assert retriever.calls[0]["doc_id"] == "doc_only"


def test_prepare_detects_filename_mention_across_multiple_documents() -> None:
    retriever = FakeHybridRetriever(_result(_snippet(doc_id="doc_alpha", filename="alpha.pdf")))
    service = ChatTurnService(_validator([1]))

    prepared = service.prepare(
        prompt="Summarize alpha.pdf for me",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={
            "doc_alpha": {"filename": "alpha.pdf", "pages": 3},
            "doc_beta": {"filename": "beta.pdf", "pages": 4},
        },
        retriever=retriever,
        context_window=4096,
    )

    assert prepared.doc_filter == "doc_alpha"
    assert prepared.retrieval_scope == "doc_alpha"


def test_intent_mismatch_skips_generation_and_returns_selection_prompt() -> None:
    retriever = FakeHybridRetriever(_result())
    service = ChatTurnService(_validator([1]))

    prepared = service.prepare(
        prompt="List all the questions",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={
            "doc_alpha": {"filename": "alpha.pdf", "pages": 3},
            "doc_beta": {"filename": "beta.pdf", "pages": 4},
        },
        retriever=retriever,
        context_window=4096,
    )
    result = service.intent_mismatch_result(prepared)

    assert prepared.intent_mismatch is True
    assert prepared.sources == []
    assert retriever.calls == []
    assert result.assistant_turn["content"] == "[Please select a specific document to run exhaustive extraction.]"
    assert result.assistant_turn["sources"] == []
    assert result.verification is None


def test_finalize_distinguishes_cited_from_uncited_evidence() -> None:
    snippet = _snippet(content="Acid rain lowers soil pH.")
    preparation = ChatTurnService(_validator([1])).prepare(
        prompt="What does the document say?",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={"doc_alpha": {"filename": "alpha.pdf", "pages": 3}},
        retriever=FakeHybridRetriever(_result(snippet)),
        context_window=4096,
    )

    cited_service = ChatTurnService(_validator([1]))
    cited = cited_service.finalize(
        preparation,
        "Acid rain lowers soil pH [E1].",
        is_cloud=False,
        model_name="local-model",
    )
    uncited_service = ChatTurnService(_validator([]))
    uncited = uncited_service.finalize(
        preparation,
        "The weather is pleasant today.",
        is_cloud=False,
        model_name="local-model",
    )

    assert cited.cited_ranks == [1]
    assert cited.assistant_turn["verification"]["cited_ranks"] == [1]
    assert uncited.cited_ranks == []
    assert uncited.assistant_turn["verification"]["cited_ranks"] == []
    assert uncited.withheld is True
    assert uncited.unverified is True


def test_finalize_preserves_chunk_cap_signal() -> None:
    retriever = FakeHybridRetriever(_result(_snippet(), search_mode="document_truncated", chunk_cap_reached=True))
    service = ChatTurnService(_validator([1]))
    preparation = service.prepare(
        prompt="What is the finding?",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={"doc_alpha": {"filename": "alpha.pdf", "pages": 3}},
        retriever=retriever,
        context_window=4096,
    )

    result = service.finalize(preparation, "Acid rain lowers soil pH [E1].")

    assert preparation.chunk_cap_reached is True
    assert result.chunk_cap_reached is True
    assert result.assistant_turn["snippets"][0]["rank"] == 1


def test_finalize_persists_auto_attributed_metadata_in_transcript_turn() -> None:
    preparation = ChatTurnService(_validator([1])).prepare(
        prompt="What does the document say?",
        history_before_turn=[],
        selected_doc=None,
        document_metadata={"doc_alpha": {"filename": "alpha.pdf", "pages": 3}},
        retriever=FakeHybridRetriever(_result(_snippet(content="Acid rain lowers soil pH."))),
        context_window=4096,
    )
    result = ChatTurnService(_validator([1])).finalize(
        preparation,
        "Acid rain lowers soil pH.",
        is_cloud=False,
        model_name="local-model",
    )

    verification = result.assistant_turn["verification"]
    assert result.auto_attributed_count == 1
    assert result.auto_attributed_ranks == [1]
    assert verification["auto_attributed_count"] == 1
    assert verification["auto_attributed_ranks"] == [1]
    assert verification["cited_ranks"] == [1]
