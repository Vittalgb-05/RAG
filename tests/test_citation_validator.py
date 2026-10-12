"""Unit tests for citation validation and abstention detection."""

from citation_validator import (
    CitationVerificationResult,
    extract_citations,
    is_abstention,
    validate_citations,
)
from local_llm import AiModel
from models import EvidenceSnippet, RetrievalResult


def _make_retrieval_result(num_snippets: int = 3) -> RetrievalResult:
    """Helper to construct a canonical RetrievalResult with dummy snippets."""
    snippets = [
        EvidenceSnippet(
            content=f"Content for snippet {i}",
            doc_id="doc_test",
            filename="test.pdf",
            page=i,
            chunk_id=f"chk_{i}",
            score=0.9 - (i * 0.1),
            rank=i,
        )
        for i in range(1, num_snippets + 1)
    ]
    return RetrievalResult(
        query="test query",
        snippets=snippets,
        total_candidates=num_snippets,
        search_mode="hybrid",
    )


def test_extract_citations() -> None:
    """Verify regex extraction of bracketed citations [En] in various formats."""
    assert extract_citations("Simple citation [E1].") == [1]
    assert extract_citations("Multiple citations [E1] and [E3].") == [1, 3]
    assert extract_citations("Adjacent citations [E1][E2] in sentence.") == [1, 2]
    assert extract_citations("Duplicate citations [E1] mentioned twice [E1].") == [1]
    assert extract_citations("Invalid tokens [E0], [X1], [E] are ignored.") == []
    assert extract_citations("No citations in text.") == []


def test_is_abstention() -> None:
    """Verify detection of canonical model abstention markers."""
    assert is_abstention("The document does not contain sufficient evidence to answer.") is True
    assert is_abstention("I have INSUFFICIENT INFORMATION in the provided context.") is True
    assert is_abstention("The document does not mention the revenue.") is True
    assert is_abstention("Cannot find the answer in the document context.") is True
    assert is_abstention("The revenue in 2024 was $5 million [E1].") is False


def test_validate_citations_perfect_precision() -> None:
    """Verify 100% precision when all cited ranks exist in retrieval results."""
    rr = _make_retrieval_result(num_snippets=4)
    response = "The system achieved 95% precision [E1] and operates under 4 GB VRAM [E2][E3]."

    result = validate_citations(response, rr)
    assert isinstance(result, CitationVerificationResult)
    assert result.is_valid is True
    assert result.precision == 1.0
    assert result.total_citations == 3
    assert result.valid_citations == ["[E1]", "[E2]", "[E3]"]
    assert result.hallucinated_citations == []
    assert result.cited_ranks == [1, 2, 3]
    assert result.abstention_detected is False
    assert "100.0%" in result.message


def test_validate_citations_hallucinated_rank() -> None:
    """Verify out-of-bounds citations reduce precision and fail the >=95% requirement."""
    rr = _make_retrieval_result(num_snippets=2)
    # [E1] is valid, [E5] is out of bounds (only 2 snippets exist)
    response = "Known finding [E1] and fabricated assertion [E5]."

    result = validate_citations(response, rr)
    assert result.is_valid is False
    assert result.precision == 0.5
    assert result.total_citations == 2
    assert result.valid_citations == ["[E1]"]
    assert result.hallucinated_citations == ["[E5]"]
    assert result.cited_ranks == [1]
    assert "hallucinated [E5]" in result.message


def test_validate_citations_valid_abstention() -> None:
    """Verify explicit abstention with zero citations achieves 100% precision."""
    rr = _make_retrieval_result(num_snippets=3)
    response = "The document does not contain sufficient evidence to answer this question."

    result = validate_citations(response, rr)
    assert result.is_valid is True
    assert result.precision == 1.0
    assert result.total_citations == 0
    assert result.abstention_detected is True
    assert "Valid explicit abstention" in result.message


def test_validate_citations_abstention_with_hallucinated_citations() -> None:
    """Verify abstention text that fabricates citations fails validation."""
    rr = _make_retrieval_result(num_snippets=3)
    response = "The document does not contain sufficient evidence to answer [E1]."

    result = validate_citations(response, rr)
    assert result.is_valid is False
    assert result.precision == 0.0
    assert result.abstention_detected is True
    assert "[E1]" in result.hallucinated_citations
    assert "unexpected citations" in result.message


def test_validate_citations_empty_response() -> None:
    """Verify empty response fails validation and returns precision 0.0."""
    rr = _make_retrieval_result(num_snippets=3)

    result = validate_citations("", rr)
    assert result.is_valid is False
    assert result.precision == 0.0
    assert result.total_citations == 0
    assert "Empty response" in result.message


def test_extract_citations_case_insensitive() -> None:
    """Verify citation regex extracts lowercase [e1] tags as rank 1."""
    assert extract_citations("Valid citation [e1] and uppercase [E2].") == [1, 2]


def test_is_abstention_benign_prose_does_not_fire() -> None:
    """Verify that benign analytical statements do not trigger false positive abstention."""
    # Statements mentioning evidence in clinical / analytical context without claiming lack of context
    assert is_abstention("The clinical trial showed insufficient evidence of toxicity in cohort A [E1].") is False


def test_validate_citations_ungrounded_response() -> None:
    """Verify factual response with 0 citations is flagged as ungrounded."""
    rr = _make_retrieval_result(num_snippets=3)
    response = "The revenue in 2024 was five million dollars."

    result = validate_citations(response, rr)
    assert result.is_valid is False
    assert result.precision == 0.0
    assert result.total_citations == 0
    assert "without any bracketed [E1] evidence citations" in result.message


def test_ai_model_validate_response_integration(mock_llama_provider) -> None:
    """Verify AiModel stores last_retrieval_result and delegates validate_response."""
    model = AiModel(provider=mock_llama_provider)
    rr = _make_retrieval_result(num_snippets=3)

    # Validate directly using retrieval result
    res = model.validate_response("Grounded statement [E1].", retrieval_result=rr)
    assert res.is_valid is True
    assert model.last_verification_result == res

    # Validate using cached last_retrieval_result
    model.last_retrieval_result = rr
    res2 = model.validate_response("Another grounded claim [E2].")
    assert res2.is_valid is True
    assert res2.cited_ranks == [2]
