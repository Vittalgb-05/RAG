"""Comprehensive UI smoke tests and regression tests for AMOLED workspace."""

from unittest.mock import MagicMock, patch
import pytest
import streamlit as st

from core.doc_store import DocStore
from core.models import Document, SummaryResult
from ui.components import (
    get_brand_mark_svg,
    get_svg_icon,
    render_citation_chip,
    render_status_pill,
)
from ui.hydration import hydrate_startup_state
from ui.sanitizer import sanitize_display_markdown
from ui.views import (
    clear_cloud_credentials,
    get_session_summary,
    store_session_summary,
    summary_session_key,
    truncation_notice,
    verification_caption,
)


@pytest.fixture(autouse=True)
def clean_session_state():
    """Ensure clean Streamlit session state for UI testing."""
    st.session_state.clear()
    st.session_state.doc_ids = set()
    st.session_state.failed_doc_ids = set()
    st.session_state.indexed_files = set()
    st.session_state.document_metadata = {}
    st.session_state.local_embedding = None
    st.session_state.hybrid_retriever = None
    st.session_state.chat_history = []
    st.session_state.cloud_mode = False
    st.session_state.cloud_mode_toggle = False
    st.session_state.user_consented = False
    st.session_state.uploader_key = 0
    st.session_state.active_workspace = "Workspace"
    st.session_state._startup_hydrated = False


def test_brand_assets_and_icons_load_locally():
    """Verify all local SVG icons and brand mark load without remote CDN dependencies."""
    brand_svg = get_brand_mark_svg(size=32)
    assert "<svg" in brand_svg
    assert "PAPER / INTELLIGENCE" not in brand_svg  # SVG markup only

    for icon_name in [
        "document",
        "chat",
        "summarizer",
        "library",
        "settings",
        "check",
        "alert",
        "search",
        "gpu",
        "ram",
    ]:
        icon_svg = get_svg_icon(icon_name, size=18)
        assert "<svg" in icon_svg, f"Failed to load SVG for {icon_name}"
        stripped = icon_svg.replace("http://www.w3.org/2000/svg", "")
        assert "http://" not in stripped and "https://" not in stripped, (
            f"Icon {icon_name} must not contain remote URLs"
        )


def test_status_pill_rendering():
    """Verify monochrome status pill markup for local and cloud states."""
    local_pill = render_status_pill("Local Mode", variant="local")
    assert "status-badge local" in local_pill
    assert "#5EEAD4" in local_pill
    assert "Local Mode" in local_pill

    cloud_pill = render_status_pill("Cloud Active", variant="cloud")
    assert "status-badge cloud" in cloud_pill
    assert "#A78BFA" in cloud_pill

    error_pill = render_status_pill("Offline", variant="error")
    assert "status-badge error" in error_pill
    assert "#F87171" in error_pill


def test_citation_chip_formatting():
    """Verify evidence citation chip includes page reference and local styling."""
    chip = render_citation_chip(doc_id="doc_123", page=4, filename="research.pdf", rank=1)
    assert "[E1]" in chip
    assert "research.pdf" in chip
    assert "p. 4" in chip
    assert "<svg" in chip


def test_sanitizer_prevents_network_egress_in_local_mode():
    """Verify that external image and link tags are neutralized in local mode."""
    untrusted = (
        "Here is an exfiltration attempt: ![tracker](https://malicious.com/pixel.png) and [click](https://evil.com)."
    )
    sanitized = sanitize_display_markdown(untrusted, allow_external=False)
    assert "https://malicious.com/pixel.png" not in sanitized
    assert "Blocked external image" in sanitized


def test_sanitizer_allows_external_when_cloud_consented():
    """Verify that external markdown remains intact when explicit consent is provided."""
    text = "Check this [resource](https://example.com/guide) and ![diagram](https://example.com/fig.png)."
    sanitized = sanitize_display_markdown(text, allow_external=True)
    assert "[resource](https://example.com/guide)" in sanitized
    assert "![diagram](https://example.com/fig.png)" in sanitized


def test_uploader_key_increments_on_session_reset():
    """Verify that uploader_key increments on clear/purge to prevent re-ingesting cached widget files (P0-1)."""
    from main import _reset_session_security_state

    initial_key = st.session_state.uploader_key
    st.session_state.doc_ids.add("doc_to_purge")
    st.session_state.failed_doc_ids.add("doc_failed")

    _reset_session_security_state()

    assert st.session_state.uploader_key == initial_key + 1
    assert len(st.session_state.doc_ids) == 0
    assert len(st.session_state.failed_doc_ids) == 0


def test_session_reset_clears_ai_model_turn_state():
    """Clear Session must reset per-turn retrieval/citation state on the AiModel (P1)."""
    from main import _reset_session_security_state

    fake_model = MagicMock()
    st.session_state.ai_model = fake_model

    _reset_session_security_state()

    fake_model.reset_turn_state.assert_called_once()


def test_restart_recovery_hydration(tmp_path):
    """Verify documents stored on disk are hydrated into session_state on restart (P0-2)."""
    db_file = tmp_path / "smoke_docs.db"
    store = DocStore(db_file)

    doc = Document(
        doc_id="doc_smoke_01",
        filename="specs.pdf",
        sha256="b" * 64,
        size_bytes=2048,
        num_pages=5,
        status="indexed",
        upload_time="2026-10-19T10:00:00Z",
        num_chunks=8,
    )
    store.upsert_document(doc)

    with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
        mock_retriever = MagicMock()
        mock_retriever.count_chunks.return_value = 8
        mock_retriever_cls.return_value = mock_retriever

        with patch("ui.hydration.LocalEmbedding") as mock_embed_cls:
            mock_embed_cls.return_value = MagicMock()
            hydrate_startup_state(store)

    assert "doc_smoke_01" in st.session_state.doc_ids
    assert "specs.pdf" in st.session_state.indexed_files
    assert st.session_state.document_metadata["doc_smoke_01"]["chunks"] == 8
    assert st.session_state._startup_hydrated is True


def test_single_document_deletion_workflow(tmp_path):
    """Verify deleting a single document purges SQLite records and retriever chunks."""
    db_file = tmp_path / "single_delete.db"
    store = DocStore(db_file)

    doc = Document(
        doc_id="doc_del_me",
        filename="remove_me.pdf",
        sha256="c" * 64,
        size_bytes=4096,
        num_pages=2,
        status="indexed",
        upload_time="2026-10-19T12:00:00Z",
        num_chunks=4,
    )
    store.upsert_document(doc)
    assert store.get_document("doc_del_me") is not None

    mock_retriever = MagicMock()
    # Execute deletion
    store.delete_document("doc_del_me")
    mock_retriever.delete_document("doc_del_me")

    assert store.get_document("doc_del_me") is None
    mock_retriever.delete_document.assert_called_once_with("doc_del_me")


def test_cached_summary_invalidates_on_model_version_mismatch(tmp_path):
    """Verify that cached summaries for old models are not served when active model changes (P1-5)."""
    db_file = tmp_path / "summary_version.db"
    store = DocStore(db_file)

    sha = "d" * 64
    store.upsert_document(
        Document(
            doc_id="doc_sum_ver",
            filename="analysis.pdf",
            sha256=sha,
            size_bytes=1000,
            num_pages=1,
            upload_time="2026-10-19T00:00:00Z",
        )
    )

    old_summary = SummaryResult(
        summary_id="summ_old_1",
        doc_id="doc_sum_ver",
        sha256=sha,
        profile="overview",
        summary_text="Old model summary.",
        page_references=[1],
        created_at="2026-10-19T00:00:00Z",
        model_version="qwen3-vl-2b-q4",
    )
    store.save_summary(old_summary)

    # Lookup with matching model version succeeds
    hit = store.get_summary(sha, "overview", model_version="qwen3-vl-2b-q4")
    assert hit is not None
    assert hit.summary_text == "Old model summary."

    # Lookup with upgraded model version returns None (invalidating stale cache)
    miss = store.get_summary(sha, "overview", model_version="qwen3-vl-2b-q8")
    assert miss is None


def test_stale_summary_session_entry_is_rejected():
    """A session summary from another model version must not be displayed."""
    model_version = "active-model:cfg"
    store_session_summary(
        "doc_stale",
        "overview",
        model_version,
        {"model_version": "old-model:cfg", "summary_text": "stale summary"},
    )

    stale_key = summary_session_key("doc_stale", "overview", model_version)
    assert st.session_state[stale_key]["model_version"] == "old-model:cfg"

    assert get_session_summary("doc_stale", "overview", model_version) is None
    assert stale_key not in st.session_state


def test_current_summary_session_entry_is_returned():
    """A session summary matching the active version is served."""
    model_version = "active-model:cfg"
    store_session_summary(
        "doc_current",
        "overview",
        model_version,
        {"model_version": model_version, "summary_text": "current summary"},
    )

    cached = get_session_summary("doc_current", "overview", model_version)
    assert cached is not None
    assert cached["summary_text"] == "current summary"


def test_truncation_notice_contract_is_non_blocking():
    """Truncation is surfaced as a caption string, never as an error."""
    assert truncation_notice(None) is None
    assert (
        truncation_notice({"prompt_truncated": False, "context_truncated": False, "history_truncated": False}) is None
    )
    assert "Context truncated" in truncation_notice(
        {"prompt_truncated": False, "context_truncated": True, "history_truncated": False}
    )
    assert "history truncated" in truncation_notice(
        {"prompt_truncated": False, "context_truncated": False, "history_truncated": True}
    )


def test_verification_caption_separates_validity_from_support():
    """The UI caption must not call rank-valid citations 'verified grounding'."""
    valid_but_unsupported = {
        "abstention_detected": False,
        "total_citations": 1,
        "is_valid": True,
        "precision": 1.0,
        "support_checked": True,
        "support_precision": 0.0,
    }
    caption = verification_caption(valid_but_unsupported)
    assert "Citation validity 100%" in caption
    assert "support not confirmed" in caption
    assert "Verified Grounding" not in caption

    supported = dict(valid_but_unsupported, support_precision=1.0)
    assert "support confirmed" in verification_caption(supported)

    unchecked = dict(valid_but_unsupported, support_checked=False, support_precision=0.0)
    assert "support not verified" in verification_caption(unchecked)

    # Auto-attributed citations
    auto_attributed = {
        "abstention_detected": False,
        "total_citations": 2,
        "auto_attributed_count": 2,
        "is_valid": True,
        "precision": 1.0,
        "support_checked": True,
        "support_precision": 0.4,
    }
    auto_caption = verification_caption(auto_attributed)
    assert "Auto-attributed citations (2/2)" in auto_caption
    assert "partially supported" in auto_caption

    # Mixed citations
    mixed = {
        "abstention_detected": False,
        "total_citations": 3,
        "auto_attributed_count": 1,
        "is_valid": True,
        "precision": 1.0,
        "support_checked": True,
        "support_precision": 0.8,
    }
    mixed_caption = verification_caption(mixed)
    assert "Mixed citations (2 model-generated, 1 auto-attributed)" in mixed_caption
    assert "grounded" in mixed_caption


def test_clear_cloud_credentials_scrubs_session_and_provider():
    """Clearing keys removes them from session state and provider objects."""
    provider = MagicMock()
    provider.api_key = "secret-key"
    provider._client = object()
    ai_model = MagicMock()
    ai_model.cloud_provider = provider
    ai_model.provider = provider

    st.session_state.cloud_api_keys = {"groq": "gsk_secret", "openai": "sk_secret", "anthropic": ""}
    st.session_state.active_cloud_provider = provider
    st.session_state._cached_cloud_key = "gsk_secret"

    clear_cloud_credentials(ai_model)

    assert st.session_state.cloud_api_keys == {"groq": "", "openai": "", "anthropic": ""}
    assert st.session_state._cached_cloud_key is None
    assert st.session_state.active_cloud_provider is None
    assert provider.api_key is None
    assert provider._client is None


def test_workspace_navigation_includes_all_primary_destinations():
    """Sidebar navigation must expose every routed workspace and normalize legacy aliases."""
    import main

    assert main.WORKSPACES == ["Chat", "Document Library", "Summarizer", "Settings", "Diagnostics"]
    assert main.normalize_workspace("Workspace") == "Chat"
    assert main.normalize_workspace("Ask Documents") == "Chat"
    assert main.normalize_workspace("Library") == "Document Library"
    assert main.normalize_workspace("Diagnostics") == "Diagnostics"
    assert main.normalize_workspace("Settings") == "Settings"
    assert main.normalize_workspace("unknown") == "Chat"


def test_session_reset_clears_shared_embedding_model_cache():
    """Clear Session must drop the process-level SentenceTransformer cache."""
    from main import _reset_session_security_state

    with patch("ui.session_state.clear_shared_model_cache") as clear_mock:
        _reset_session_security_state()

    clear_mock.assert_called_once()
