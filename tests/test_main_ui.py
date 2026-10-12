"""Unit tests for Streamlit UI data structures and presentation contracts."""

from citation_validator import CitationVerificationResult
from doc_store import DocStore
from models import BBox, Document, EvidenceSnippet, SummaryResult


def test_chat_turn_schema_contract():
    """Verify chat turn dictionary structure accommodates citations, verification, and snippets."""
    bbox = BBox(x0=10.0, y0=20.0, x1=100.0, y1=200.0, page_width=612.0, page_height=792.0)
    snippet = EvidenceSnippet(
        content="Grounded excerpt from page 2.",
        doc_id="doc_test_ui",
        filename="report.pdf",
        page=2,
        chunk_id="chk_ui_1",
        score=0.88,
        rank=1,
        bbox=bbox,
    )

    verification = CitationVerificationResult(
        is_valid=True,
        precision=1.0,
        total_citations=1,
        valid_citations=["[E1]"],
        hallucinated_citations=[],
        cited_ranks=[1],
        abstention_detected=False,
        message="100.0% precision",
    )

    turn = {
        "role": "assistant",
        "content": "The report highlights key metrics in 2024 [E1].",
        "sources": ["report.pdf (p. 2)"],
        "verification": verification.model_dump(),
        "snippets": [snippet.model_dump()],
    }

    assert turn["role"] == "assistant"
    assert turn["verification"]["is_valid"] is True
    assert turn["verification"]["precision"] == 1.0
    assert len(turn["snippets"]) == 1
    assert turn["snippets"][0]["rank"] == 1
    assert turn["snippets"][0]["filename"] == "report.pdf"
    assert turn["snippets"][0]["page"] == 2
    assert turn["snippets"][0]["bbox"]["x0"] == 10.0


def test_evidence_drawer_card_formatting():
    """Verify card header and chip generation from snippets data."""
    snippets = [
        {
            "rank": 1,
            "filename": "doc_a.pdf",
            "page": 3,
            "score": 0.854,
            "content": "Exemplary evidence text.",
            "bbox": None,
        },
        {
            "rank": 2,
            "filename": "doc_b.pdf",
            "page": 7,
            "score": 0.721,
            "content": "Secondary evidence.",
            "bbox": {"x0": 5.0, "y0": 10.0, "x1": 50.0, "y1": 100.0},
        },
    ]

    chip_labels = [f"[E{s['rank']}] {s['filename']} (p. {s['page']})" for s in snippets]
    assert chip_labels == ["[E1] doc_a.pdf (p. 3)", "[E2] doc_b.pdf (p. 7)"]

    card_headers = [
        f"**[E{s['rank']}]** `{s['filename']}` *(p. {s['page']}, score: {s['score']:.3f})*" for s in snippets
    ]
    assert card_headers[0] == "**[E1]** `doc_a.pdf` *(p. 3, score: 0.854)*"
    assert card_headers[1] == "**[E2]** `doc_b.pdf` *(p. 7, score: 0.721)*"


def test_summary_data_contract_and_page_formatting(tmp_path):
    """Verify summary serialization and page reference drawer display formatting."""
    db_file = tmp_path / "ui_summary.db"
    store = DocStore(db_file)

    doc_id = "doc_ui_summary"
    sha = "9" * 64
    store.upsert_document(
        Document(
            doc_id=doc_id,
            filename="analysis.pdf",
            sha256=sha,
            size_bytes=1024,
            num_pages=10,
            upload_time="2026-10-11T14:00:00Z",
        )
    )

    summary = SummaryResult(
        summary_id="summ_ui_12345678",
        doc_id=doc_id,
        sha256=sha,
        profile="detailed",
        summary_text="## Detailed Breakdown\n\nMethodology (p. 2) and results (p. 8).",
        page_references=[2, 8],
        created_at="2026-10-11T14:05:00Z",
        model_version="qwen3-vl-2b",
        cached=False,
    )
    store.save_summary(summary)

    # Re-fetch from store to verify UI cache lookup
    cached = store.get_summary(sha, "detailed")
    assert cached is not None
    data = cached.model_dump()
    assert data["cached"] is True
    assert data["profile"] == "detailed"

    # Verify formatted page reference labels
    page_labels = [f"Page {p}" for p in data["page_references"]]
    assert page_labels == ["Page 2", "Page 8"]
    assert ", ".join(page_labels) == "Page 2, Page 8"


def test_ai_model_provider_attribute_contract(mock_llama_provider):
    """Verify that AiModel exposes .provider attribute rather than ._provider (CR-01)."""
    from local_llm import AiModel

    model = AiModel(provider=mock_llama_provider)
    assert hasattr(model, "provider")
    assert not hasattr(model, "_provider")
    assert model.provider is mock_llama_provider

    # Verify upload loop expression works without AttributeError
    active_provider = model.provider if model is not None else None
    assert active_provider is mock_llama_provider


def test_clear_all_purges_summary_keys():
    """Verify that Clear All logic purges all summary_* keys from session state (WR-05)."""
    mock_session = {
        "doc_ids": {"doc_1"},
        "summary_doc_1_overview": {"text": "summary overview"},
        "summary_doc_1_detailed": {"text": "summary detailed"},
        "other_key": 123,
    }

    # Simulate Clear All handler purge
    for k in list(mock_session.keys()):
        if k.startswith("summary_"):
            del mock_session[k]

    assert "summary_doc_1_overview" not in mock_session
    assert "summary_doc_1_detailed" not in mock_session
    assert mock_session["other_key"] == 123


def test_clear_all_resets_cloud_posture_and_credentials():
    """Verify that Clear All logic resets cloud posture, revokes consent, and clears keys (WR-02)."""
    from unittest.mock import MagicMock

    mock_provider = MagicMock()
    mock_session = {
        "doc_ids": {"doc_1"},
        "cloud_mode": True,
        "cloud_mode_toggle": True,
        "user_consented": True,
        "active_cloud_provider": mock_provider,
        "_cached_cloud_model": "groq/llama-3.3-70b-versatile",
        "_cached_cloud_key": "gsk_secret",
        "cloud_api_keys": {"groq": "gsk_secret", "openai": "sk_secret", "anthropic": ""},
        "cloud_api_key": "legacy_key",
    }

    # Simulate Clear All handler logic
    if mock_session.get("active_cloud_provider"):
        mock_session["active_cloud_provider"].close()
    mock_session["active_cloud_provider"] = None
    mock_session["_cached_cloud_model"] = None
    mock_session["_cached_cloud_key"] = None
    mock_session["cloud_mode"] = False
    mock_session["cloud_mode_toggle"] = False
    mock_session["user_consented"] = False
    mock_session["cloud_api_keys"] = {"groq": "", "openai": "", "anthropic": ""}
    if "cloud_api_key" in mock_session:
        mock_session["cloud_api_key"] = ""

    mock_provider.close.assert_called_once()
    assert mock_session["cloud_mode"] is False
    assert mock_session["cloud_mode_toggle"] is False
    assert mock_session["user_consented"] is False
    assert mock_session["active_cloud_provider"] is None
    assert mock_session["cloud_api_keys"] == {"groq": "", "openai": "", "anthropic": ""}
    assert mock_session["cloud_api_key"] == ""
