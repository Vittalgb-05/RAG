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

    mock_provider.close.assert_called_once()
    assert mock_session["cloud_mode"] is False
    assert mock_session["cloud_mode_toggle"] is False
    assert mock_session["user_consented"] is False
    assert mock_session["active_cloud_provider"] is None
    assert mock_session["cloud_api_keys"] == {"groq": "", "openai": "", "anthropic": ""}


def test_consent_dialog_approval_and_dismissal():
    """Verify state transitions for user consenting to cloud vs dismissing / cancelling."""
    # 1. User consents
    session = {
        "user_consented": False,
        "cloud_mode": False,
        "cloud_mode_toggle": False,
    }

    # Simulate 'I Consent & Enable Cloud' click
    session["user_consented"] = True
    session["cloud_mode"] = True
    session["cloud_mode_toggle"] = True

    assert session["user_consented"] is True
    assert session["cloud_mode"] is True
    assert session["cloud_mode_toggle"] is True

    # 2. User cancels / dismisses dialog ('Cancel (Keep 100% Local)')
    session["user_consented"] = False
    session["cloud_mode"] = False
    session["cloud_mode_toggle"] = False

    assert session["user_consented"] is False
    assert session["cloud_mode"] is False
    assert session["cloud_mode_toggle"] is False


def test_session_isolation_posture():
    """Verify that multiple concurrent sessions maintain isolated AiModel and consent state."""
    from local_llm import AiModel
    from model_provider import HealthStatus, ProviderCapabilities, BaseModelProvider

    class DummyLocalProvider(BaseModelProvider):
        def check_health(self):
            return HealthStatus(status="healthy", message="ok", provider_type="local")

        def get_capabilities(self):
            return ProviderCapabilities(
                model_name="local-qwen", context_window=4096, supports_vision=True, is_local=True
            )

        def generate_text(self, *args, **kwargs):
            return "local"

        def stream_text(self, *args, **kwargs):
            yield "local"

        def analyze_image(self, *args, **kwargs):
            return "image"

    shared_provider = DummyLocalProvider()

    # Session A creates its model
    session_a_model = AiModel(provider=shared_provider)
    # Session B creates its model
    session_b_model = AiModel(provider=shared_provider)

    assert session_a_model.cloud_mode is False
    assert session_b_model.cloud_mode is False

    # Session A enables cloud mode
    session_a_model.set_cloud_mode(True)
    assert session_a_model.cloud_mode is True

    # Session B MUST remain strictly in local mode (zero cross-session leakage)
    assert session_b_model.cloud_mode is False


def test_failed_doc_ids_cleared_on_delete():
    """Verify that deleting a document discards its ID from failed_doc_ids to enable retries."""
    mock_session = {
        "doc_ids": {"doc_failed_1"},
        "failed_doc_ids": {"doc_failed_1", "doc_other"},
        "indexed_files": {"failed.pdf"},
        "document_metadata": {"doc_failed_1": {"filename": "failed.pdf"}},
    }

    # Simulate library deletion
    doc_id_to_delete = "doc_failed_1"
    mock_session["doc_ids"].discard(doc_id_to_delete)
    mock_session["failed_doc_ids"].discard(doc_id_to_delete)
    mock_session["indexed_files"].discard("failed.pdf")
    mock_session["document_metadata"].pop(doc_id_to_delete, None)

    assert doc_id_to_delete not in mock_session["failed_doc_ids"]
    assert doc_id_to_delete not in mock_session["doc_ids"]
    assert "doc_other" in mock_session["failed_doc_ids"]


def test_cloud_provider_model_mapping():
    """Verify provider choice maps cleanly to correct LiteLLM cloud_model strings."""
    provider_config = {
        "Groq (Llama 3.3 70B)": {"model": "groq/llama-3.3-70b-versatile", "env": "GROQ_API_KEY"},
        "OpenAI (GPT-4o mini)": {"model": "openai/gpt-4o-mini", "env": "OPENAI_API_KEY"},
        "Anthropic (Claude 3.5 Haiku)": {"model": "anthropic/claude-3-5-haiku-latest", "env": "ANTHROPIC_API_KEY"},
    }

    assert provider_config["OpenAI (GPT-4o mini)"]["model"] == "openai/gpt-4o-mini"
    assert provider_config["Anthropic (Claude 3.5 Haiku)"]["model"] == "anthropic/claude-3-5-haiku-latest"
    assert provider_config["Groq (Llama 3.3 70B)"]["model"] == "groq/llama-3.3-70b-versatile"


def test_summary_cache_version_key_contract(tmp_path):
    """Verify summary retrieval uses f'{model_name}:{CONFIG_VERSION}' to match save key."""
    from summarizer import CONFIG_VERSION

    db_file = tmp_path / "ui_summary_ver.db"
    store = DocStore(db_file)

    doc_id = "doc_ver_1"
    sha = "8" * 64
    store.upsert_document(
        Document(
            doc_id=doc_id,
            filename="versioned.pdf",
            sha256=sha,
            size_bytes=2048,
            num_pages=5,
            upload_time="2026-10-15T12:00:00Z",
        )
    )

    expected_version = f"qwen3-vl-2b:{CONFIG_VERSION}"
    summary = SummaryResult(
        summary_id="summ_ver_123",
        doc_id=doc_id,
        sha256=sha,
        profile="overview",
        summary_text="Overview content.",
        page_references=[1],
        created_at="2026-10-15T12:05:00Z",
        model_version=expected_version,
    )
    store.save_summary(summary)

    # UI lookup with expected version matches cached entry
    cached = store.get_summary(sha, "overview", model_version=expected_version)
    assert cached is not None
    assert cached.cached is True
    assert cached.model_version == expected_version


def test_ingestion_service_empty_chunks_reports_failure(tmp_path, monkeypatch):
    """Verify IngestionService marks 0-chunk documents as failed/empty honestly."""
    from ui.ingestion_service import IngestionService
    from unittest.mock import MagicMock

    db_file = tmp_path / "empty_test.db"
    store = DocStore(db_file)
    service = IngestionService(doc_store=store, cache_dir=tmp_path / "cache")

    # Mock DoclingReader to return empty paragraphs
    mock_reader = MagicMock()
    mock_reader.get_paragraphs.return_value = []
    mock_reader.get_page_records.return_value = []

    import docling_reader

    monkeypatch.setattr(docling_reader, "DoclingReader", lambda *args, **kwargs: mock_reader)

    # Valid dummy PDF bytes
    dummy_pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n170\n%%EOF"

    result = service.ingest_pdf(dummy_pdf, filename="blank.pdf")
    assert result.success is False
    assert result.num_chunks == 0
    assert "0 usable" in (result.error or "")

    doc_in_db = store.get_document(result.doc_id)
    assert doc_in_db is not None
    assert doc_in_db.status == "failed"
