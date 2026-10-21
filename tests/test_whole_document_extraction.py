"""Regression tests for whole-document question extraction and the grounding render gate.

Reproduces the EVS.pdf failure structurally: "What are the questions?" was routed
through top-k chat retrieval (k=8), so later question pages never reached the model,
the system prompt seeded the phrase "What are the primary findings?", and an
uncited answer was still rendered with retrieved-evidence chips.

No GPU, network, or real PDF is required.
"""

import hashlib
from pathlib import Path

import pytest

from core.citation_validator import should_withhold_answer, validate_citations
from core.local_llm import AiModel
from core.models import Chunk, EvidenceSnippet, RetrievalResult
from core.prompt_budget import SYSTEM_GROUNDING_TEMPLATE
from core.query_intent import (
    contextualize_query,
    is_whole_document_query,
    resolve_retrieval,
    select_page_diverse_snippets,
    whole_document_char_budget,
)
from retrieval.hybrid_retriever import HybridRetriever

QUESTION_PAGES: dict[int, str] = {
    1: "Q1. What are the primary findings of the environmental survey? (5 marks)",
    2: "Q2. Explain the water cycle with a labelled diagram. (10 marks)",
    3: "Q3. List three causes of air pollution and one control measure. (5 marks)",
    4: "Q4. What is biodiversity and why is it important? (5 marks)",
    5: "Q5. Differentiate renewable and non-renewable resources. (10 marks)",
    6: "Q6. Describe the role of forests in ecological balance. (5 marks)",
    7: "Q7. What are the effects of deforestation on soil and climate? (10 marks)",
    8: "Q8. Explain the process of photosynthesis in plants. (5 marks)",
    9: "Q9. What steps can students take to reduce plastic waste? (5 marks)",
    10: "Q10. Define sustainable development and give two examples. (5 marks)",
    11: "Q11. Prepare a poster on 'Save Water' with a slogan. (10 marks)",
}


def _embed(text: str) -> list[float]:
    """Deterministic 384-dim hashing embedding (avoids downloading MiniLM)."""
    vector = [0.0] * 384
    for token in text.lower().replace("?", " ").split():
        digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vector[digest % 384] += 1.0
    norm = sum(value * value for value in vector) ** 0.5 or 1.0
    return [value / norm for value in vector]


@pytest.fixture
def question_retriever(tmp_path: Path) -> HybridRetriever:
    """Index an 11-page synthetic exam booklet with one question per page."""
    retriever = HybridRetriever(db_uri=tmp_path / "evs_lancedb")
    retriever.set_embedding_fn(_embed)
    chunks = [
        Chunk(
            content=text,
            filename="EVS.pdf",
            page=page,
            chunk_id=f"chk_evs_{page:02d}",
            doc_id="doc_evs",
            extraction="pypdf",
        )
        for page, text in QUESTION_PAGES.items()
    ]
    retriever.index_chunks(chunks, embeddings=[_embed(chunk.content) for chunk in chunks])
    retriever.create_fts_index()
    return retriever


def test_whole_document_intent_detection() -> None:
    """Inventory/extraction phrasing is detected; targeted questions are not."""
    assert is_whole_document_query("What are the questions?")
    assert is_whole_document_query("list all the questions")
    assert is_whole_document_query("extract every exercise from the booklet")
    assert is_whole_document_query("what questions does the document ask?")
    assert is_whole_document_query("summarize the entire document")

    # Targeted questions must stay on normal top-k hybrid retrieval.
    assert not is_whole_document_query("What are the primary findings of section 2?")
    assert not is_whole_document_query("What is the water cycle?")
    assert not is_whole_document_query("Explain the methodology used in this document.")
    assert not is_whole_document_query("What are the key tables, numbers, and quantitative data reported?")


def test_contextualize_query_is_the_single_followup_heuristic() -> None:
    """Short follow-ups borrow the previous user question; full questions do not."""
    history = [
        {"role": "user", "content": "What are the questions?"},
        {"role": "assistant", "content": "Here are the questions [E1]."},
    ]
    assert contextualize_query("why?", history) == "What are the questions? why?"
    assert contextualize_query("What is the water cycle?", history) == "What is the water cycle?"
    assert contextualize_query("why?", None) == "why?"
    assert contextualize_query("why?", [{"role": "user", "content": None}]) == "why?"


def test_fetch_document_chunks_returns_every_page_in_order(question_retriever: HybridRetriever) -> None:
    """The retriever can return a complete page-ordered inventory, not a k sample."""
    result = question_retriever.fetch_document_chunks("doc_evs")

    assert result.search_mode == "document"
    assert [snippet.page for snippet in result.snippets] == list(range(1, 12))
    assert [snippet.rank for snippet in result.snippets] == list(range(1, 12))
    for page, text in QUESTION_PAGES.items():
        assert result.snippets[page - 1].content == text


def test_whole_document_query_covers_all_pages_not_just_top_k(question_retriever: HybridRetriever) -> None:
    """Regression: k=8 previously omitted question pages 5, 10, and 11."""
    result = resolve_retrieval(
        question_retriever,
        "What are the questions?",
        doc_id="doc_evs",
        k=8,
        max_context_chars=whole_document_char_budget(4096),
    )

    assert result.search_mode == "document"
    assert len(result.snippets) == len(QUESTION_PAGES) > 8
    assert sorted(snippet.page for snippet in result.snippets) == list(range(1, 12))
    assert [snippet.rank for snippet in result.snippets] == list(range(1, 12))


def test_page_diverse_selection_keeps_every_page_under_budget() -> None:
    """Large first chunks must not starve later pages; ranks stay contiguous."""
    snippets = [
        EvidenceSnippet(
            content="X" * 2000,
            doc_id="doc_evs",
            filename="EVS.pdf",
            page=page,
            chunk_id=f"chk_{page}",
            score=0.0,
            rank=page,
        )
        for page in range(1, 12)
    ]
    budget = whole_document_char_budget(4096)

    selected = select_page_diverse_snippets(snippets, budget)

    assert sorted(snippet.page for snippet in selected) == list(range(1, 12))
    assert [snippet.rank for snippet in selected] == list(range(1, len(selected) + 1))
    assert sum(len(snippet.content) for snippet in selected) <= budget + 11


def test_system_prompt_no_longer_seeds_the_echoed_phrase() -> None:
    """The few-shot example must not contain a likely user question verbatim."""
    assert "What are the primary findings?" not in SYSTEM_GROUNDING_TEMPLATE
    assert "Never restate the user's question as the answer" in SYSTEM_GROUNDING_TEMPLATE
    assert "[E1]" in SYSTEM_GROUNDING_TEMPLATE


def test_ai_model_sends_every_question_page_and_withholds_uncited_answer(
    question_retriever: HybridRetriever,
    mock_llama_provider,
) -> None:
    """End-to-end structural regression for the failing chat turn (no GPU)."""
    model = AiModel(provider=mock_llama_provider)

    tokens = list(
        model.ask_a_question_from_pdf_stream(
            pdf_path="",
            prompt="What are the questions?",
            local_embedding=question_retriever,
            doc_id="doc_evs",
        )
    )
    assert tokens

    sent_system_prompt = mock_llama_provider.stream_calls[0]["system_prompt"]
    for text in QUESTION_PAGES.values():
        assert text in sent_system_prompt

    assert model.last_retrieval_result is not None
    assert len(model.last_retrieval_result.snippets) == len(QUESTION_PAGES)

    verification = model.validate_response("".join(tokens), model.last_retrieval_result)
    assert verification.total_citations == 0
    assert should_withhold_answer(verification) is True


def test_grounding_gate_allows_abstention_and_cited_answers() -> None:
    """Only genuinely grounded/abstaining answers are rendered normally."""
    retrieval = RetrievalResult(
        query="What are the questions?",
        snippets=[
            EvidenceSnippet(
                content="Q1. What are the primary findings?",
                doc_id="doc_evs",
                filename="EVS.pdf",
                page=1,
                chunk_id="chk_1",
                score=0.0,
                rank=1,
            )
        ],
        search_mode="document",
    )

    abstention = validate_citations(
        "The document does not contain sufficient evidence to answer this question.", retrieval
    )
    assert abstention.abstention_detected is True
    assert should_withhold_answer(abstention) is False

    grounded = validate_citations("The first question asks about primary findings [E1].", retrieval)
    assert grounded.is_valid is True
    assert should_withhold_answer(grounded) is False

    hallucinated = validate_citations("The first question asks about primary findings [E99].", retrieval)
    assert hallucinated.is_valid is False
    assert should_withhold_answer(hallucinated) is True

    uncited = validate_citations("The first question asks about primary findings.", retrieval)
    assert should_withhold_answer(uncited) is True
