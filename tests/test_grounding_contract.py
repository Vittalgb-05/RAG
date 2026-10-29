"""Regression tests for the evidence-grounding contract.

These tests pin the failure that produced fabricated content across every
document (a contaminated few-shot system prompt plus citation IDs granted on a
single shared token) and the summary/QA pipeline split that followed.
"""

from core.citation_validator import (
    auto_attribute_citations,
    extract_citations,
    should_withhold_answer,
    validate_citations,
)
from core.models import EvidenceSnippet, RetrievalResult
from core.prompt_budget import (
    SUMMARY_SYSTEM_TEMPLATE,
    SYSTEM_GROUNDING_TEMPLATE,
    assemble_grounded_messages,
)
from core.query_intent import (
    answer_states_current_location,
    asks_for_current_location,
    evidence_states_current_location,
    is_summary_request,
)
from ui.chat_controller import INSUFFICIENT_EVIDENCE_MESSAGE, ChatTurnPreparation, ChatTurnService

RESUME_EXCERPT = (
    "Om Prakash is a software engineer with experience building retrieval systems, "
    "Python services, and Streamlit interfaces. He worked at Acme Corp from 2021 to 2024."
)

# The exact fabricated claims observed in the reported session.
CONTAMINATED_PHRASES = (
    "Environmental studies is multidisciplinary",
    "Sustainable development balances ecological protection and economic growth",
    "O(n log n)",
    "2x speedup",
    "Core thesis & key findings",
)


def _resume_retrieval() -> RetrievalResult:
    """Build a one-snippet retrieval result grounded in the resume excerpt."""
    return RetrievalResult(
        query="Summarize the document",
        snippets=[
            EvidenceSnippet(
                content=RESUME_EXCERPT,
                doc_id="doc_resume",
                filename="resume.pdf",
                page=1,
                chunk_id="chunk_1",
                score=0.9,
                rank=1,
            )
        ],
        total_candidates=1,
        search_mode="document",
    )


def test_grounding_templates_contain_no_contaminated_few_shot_examples() -> None:
    """The system contracts must not carry document-specific worked examples."""
    for phrase in CONTAMINATED_PHRASES:
        assert phrase.lower() not in SYSTEM_GROUNDING_TEMPLATE.lower()
        assert phrase.lower() not in SUMMARY_SYSTEM_TEMPLATE.lower()


def test_summary_messages_use_the_summary_contract() -> None:
    """Summary assembly must not inherit the QA system prompt."""
    messages = assemble_grounded_messages(
        "Summarize the core thesis and key findings of the document in detail.",
        context_text="<document_context>[E1] resume.pdf p.1\n" + RESUME_EXCERPT + "</document_context>",
        system_template=SUMMARY_SYSTEM_TEMPLATE,
    )
    assert messages[0]["role"] == "system"
    summary_prefix = SUMMARY_SYSTEM_TEMPLATE.split("{context_text}")[0].strip()
    qa_prefix = SYSTEM_GROUNDING_TEMPLATE.split("{context_text}")[0].strip()
    assert messages[0]["content"].startswith(summary_prefix)
    assert qa_prefix not in messages[0]["content"]
    assert RESUME_EXCERPT in messages[0]["content"]


def test_summary_intent_detection_respects_localized_scope() -> None:
    """Document-wide summary requests route to summaries; page questions do not."""
    assert is_summary_request("Summarize the core thesis and key findings of the document in detail.")
    assert is_summary_request("Give me an overview of this PDF.")
    assert not is_summary_request("What does page 3 say about the thesis?")
    assert not is_summary_request("Summarize the table on page 2.")


def test_fabricated_sentence_is_not_auto_attributed() -> None:
    """A sentence sharing no real content with the evidence must stay uncited."""
    draft = "Sustainable development balances ecological protection and economic growth."
    attributed = auto_attribute_citations(draft, _resume_retrieval())
    assert extract_citations(attributed) == []
    assert attributed == draft


def test_supported_sentence_is_auto_attributed() -> None:
    """A sentence restating retrieved evidence earns a citation (control case)."""
    draft = "Om Prakash is a software engineer with experience building retrieval systems."
    attributed = auto_attribute_citations(draft, _resume_retrieval())
    assert extract_citations(attributed) == [1]


def test_unsupported_citations_are_flagged_and_withheld() -> None:
    """Rank-valid citations over fabricated claims are unsupported, not grounded."""
    response = (
        "Environmental studies is multidisciplinary and balances ecological protection with economic growth [E1]."
    )
    result = validate_citations(response, _resume_retrieval())
    assert result.is_valid is True
    assert result.grounding_status == "unsupported"
    assert result.support_verified is False
    assert should_withhold_answer(result) is True


def test_supported_citations_are_grounded() -> None:
    """A faithful, cited restatement is reported as grounded."""
    response = "Om Prakash is a software engineer who built retrieval systems and Python services [E1]."
    result = validate_citations(response, _resume_retrieval())
    assert result.is_valid is True
    assert result.grounding_status in {"grounded", "partial"}
    assert result.grounding_status != "rank_only"
    assert should_withhold_answer(result) is False


def test_rank_only_citations_are_not_presented_as_grounded() -> None:
    """In-range citations without evaluable text are rank-only, never grounded."""
    blank = RetrievalResult(
        query="who is Omprakash?",
        snippets=[
            EvidenceSnippet(
                content="   ",
                doc_id="doc_resume",
                filename="resume.pdf",
                page=1,
                chunk_id="chunk_blank",
                score=0.5,
                rank=1,
            )
        ],
        total_candidates=1,
        search_mode="hybrid",
    )
    response = "The candidate worked at Acme Corp [E1]."
    result = validate_citations(response, blank)
    assert result.is_valid is True
    assert result.support_checked is False
    assert result.grounding_status == "rank_only"
    assert should_withhold_answer(result) is False


def _multi_chunk_resume() -> RetrievalResult:
    """Résumé-like evidence: identity header, experience, and education in separate chunks."""
    return RetrievalResult(
        query="who is Omprakash?",
        snippets=[
            EvidenceSnippet(
                content=("OMPRAKASH PANDA\nomprakash@example.com | linkedin.com/in/omprakash\nPROFESSIONAL EXPERIENCE"),
                doc_id="doc_resume",
                filename="resume.pdf",
                page=1,
                chunk_id="chunk_header",
                score=0.9,
                rank=1,
            ),
            EvidenceSnippet(
                content="HashVault Systems\nSoftware Engineering Intern (Remote)\nBuilt Go and Python services.",
                doc_id="doc_resume",
                filename="resume.pdf",
                page=1,
                chunk_id="chunk_experience",
                score=0.8,
                rank=2,
            ),
            EvidenceSnippet(
                content="EDUCATION\nBachelor of Engineering, Information Science and Engineering.",
                doc_id="doc_resume",
                filename="resume.pdf",
                page=1,
                chunk_id="chunk_education",
                score=0.7,
                rank=3,
            ),
        ],
        total_candidates=3,
        search_mode="hybrid",
    )


def test_identity_answer_with_conversational_preamble_gets_cited_and_shown() -> None:
    """A correct identity paraphrase must not be withheld because of a polite preamble."""
    draft = "Based on the information provided in the resume, Omprakash Panda is a working professional."
    attributed = auto_attribute_citations(draft, _multi_chunk_resume())

    assert extract_citations(attributed) == [1]
    result = validate_citations(attributed, _multi_chunk_resume())
    assert result.grounding_status in {"grounded", "partial"}
    assert result.uncited_claim_count == 0
    assert should_withhold_answer(result) is False


def test_uncited_claims_prevent_a_full_grounding_verdict() -> None:
    """Support must cover uncited sentences too, not only citation-bearing ones."""
    response = (
        "Omprakash Panda is a software engineering intern [E1]. "
        "He previously led a quantum computing laboratory in Zurich."
    )
    result = validate_citations(response, _multi_chunk_resume())

    assert result.grounding_status != "grounded"
    assert result.uncited_claim_count == 1
    assert result.uncited_unsupported_count == 1


def test_identity_chunk_reaches_the_generation_prompt() -> None:
    """The evidence handed to the model must contain the actual name from the resume."""
    retrieval = _multi_chunk_resume()
    messages = assemble_grounded_messages(
        "who is Omprakash?",
        context_text=retrieval.formatted_evidence(),
        system_template=SYSTEM_GROUNDING_TEMPLATE,
    )
    assert "OMPRAKASH PANDA" in messages[0]["content"]


def test_current_location_intent_is_distinct_from_employment_questions() -> None:
    """Only present-location questions receive the strict answerability guard."""
    assert asks_for_current_location("where is omprakash right now") is True
    assert asks_for_current_location("where is Omprakash based") is True
    assert asks_for_current_location("where does Omprakash work") is False
    assert asks_for_current_location("what experience does Omprakash have?") is False


def test_institution_city_does_not_count_as_a_current_location() -> None:
    """A school's city must not be treated as the candidate's present location."""
    assert evidence_states_current_location("MS Ramaiah Institute of Technology, Bangalore") is False
    assert evidence_states_current_location("Current location: Bangalore") is True
    assert answer_states_current_location("He is currently working at HashVault Systems.") is False
    assert answer_states_current_location("He is based in Bangalore.") is True


def test_prepare_abstains_when_a_location_question_has_no_location_evidence() -> None:
    """A location question must abstain instead of accepting an employer as the answer."""
    retrieval = _multi_chunk_resume()

    class _Retriever:
        def search_hybrid(self, query: str, k: int = 5, doc_id: str | None = None) -> RetrievalResult:
            return retrieval

    service = ChatTurnService(lambda text, result: validate_citations(text, result))
    preparation = service.prepare(
        prompt="where is omprakash right now",
        history_before_turn=[],
        selected_doc="doc_resume",
        document_metadata={"doc_resume": {"filename": "resume.pdf"}},
        retriever=_Retriever(),
        context_window=4096,
    )

    assert preparation.abstention_reason is not None
    abstention = service.abstention_result(preparation)
    assert abstention.content == INSUFFICIENT_EVIDENCE_MESSAGE
    assert abstention.report is not None
    assert abstention.report.verification_status == "abstained"


def test_finalize_overrides_a_supported_but_off_topic_location_answer() -> None:
    """A grounded employer fact is not a valid answer to a current-location question."""
    retrieval = _multi_chunk_resume()
    preparation = ChatTurnPreparation(
        prompt="where is omprakash right now",
        history=[],
        search_query="where is omprakash right now",
        doc_filter="doc_resume",
        retrieval_scope="doc_resume",
        retrieval_result=retrieval,
        sources=retrieval.source_labels(),
        snippets=[snippet.model_dump() for snippet in retrieval.snippets],
        intent_mismatch=False,
        chunk_cap_reached=False,
        request_id="req_location",
        mode="qa",
        scope="document",
        document_ids=["doc_resume"],
    )
    service = ChatTurnService(lambda text, result: validate_citations(text, result))

    result = service.finalize(
        preparation,
        "Omprakash is currently working as a Software Engineering Intern at HashVault Systems [E2].",
    )

    assert result.content == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.report is not None
    assert result.report.verification_status == "abstained"
    assert result.withheld is True


def test_summary_prefers_page_text_and_keeps_figure_only_pages() -> None:
    """Summary evidence must not be dominated by a figure description on a text page."""
    page_one_text = EvidenceSnippet(
        content="OMPRAKASH PANDA\nPROFESSIONAL EXPERIENCE\nSoftware Engineering Intern",
        doc_id="doc_resume",
        filename="resume.pdf",
        page=1,
        chunk_id="chunk_text_p1",
        score=0.0,
        rank=1,
        extraction="docling",
    )
    page_one_figure = EvidenceSnippet(
        content="[Chart on page 1]: A flowchart describing an algorithm and its process.",
        doc_id="doc_resume",
        filename="resume.pdf",
        page=1,
        chunk_id="chunk_figure_p1",
        score=0.0,
        rank=2,
        extraction="vlm",
    )
    page_two_figure = EvidenceSnippet(
        content="[Figure on page 2]: A diagram of the system architecture.",
        doc_id="doc_resume",
        filename="resume.pdf",
        page=2,
        chunk_id="chunk_figure_p2",
        score=0.0,
        rank=3,
        extraction="vlm",
    )

    class _DocumentRetriever:
        def fetch_document_chunks(self, doc_id: str) -> RetrievalResult:
            return RetrievalResult(
                query="",
                snippets=[page_one_text, page_one_figure, page_two_figure],
                total_candidates=3,
                search_mode="document",
            )

    service = ChatTurnService(lambda text, result: validate_citations(text, result))
    preparation = service.prepare(
        prompt="Summarize the document.",
        history_before_turn=[],
        selected_doc="doc_resume",
        document_metadata={"doc_resume": {"filename": "resume.pdf"}},
        retriever=_DocumentRetriever(),
        context_window=4096,
    )

    selected_ids = {snippet["chunk_id"] for snippet in preparation.snippets}
    assert "chunk_text_p1" in selected_ids
    assert "chunk_figure_p1" not in selected_ids
    assert "chunk_figure_p2" in selected_ids
    assert preparation.incomplete_context is False


def test_summary_context_truncation_is_reported() -> None:
    """A capped document read must surface incomplete context instead of a silent partial summary."""
    snippet = EvidenceSnippet(
        content="OMPRAKASH PANDA\nPROFESSIONAL EXPERIENCE",
        doc_id="doc_resume",
        filename="resume.pdf",
        page=1,
        chunk_id="chunk_text_p1",
        score=0.0,
        rank=1,
        extraction="docling",
    )

    class _CappedRetriever:
        def fetch_document_chunks(self, doc_id: str) -> RetrievalResult:
            return RetrievalResult(
                query="",
                snippets=[snippet],
                total_candidates=1,
                search_mode="document_truncated",
                chunk_cap_reached=True,
            )

    service = ChatTurnService(lambda text, result: validate_citations(text, result))
    preparation = service.prepare(
        prompt="Summarize the document.",
        history_before_turn=[],
        selected_doc="doc_resume",
        document_metadata={"doc_resume": {"filename": "resume.pdf"}},
        retriever=_CappedRetriever(),
        context_window=4096,
    )

    assert preparation.incomplete_context is True
