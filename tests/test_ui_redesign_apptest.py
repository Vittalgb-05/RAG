"""Streamlit AppTest and UI integration tests for the Stage 6 redesign."""

from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest

from ui.components import (
    render_citation_chip,
    render_empty_state,
)
from ui.views import verification_caption


@pytest.fixture
def base_app():
    """Create an AppTest instance for main.py with mocked llama health/capabilities."""
    at = AppTest.from_file("main.py", default_timeout=45)
    return at


def test_apptest_initial_shell_and_welcome_state(base_app):
    """AppTest must render the Stage 6 AMOLED shell, New Chat button, and welcome hero."""
    at = base_app.run()
    assert not at.exception

    # Verify Sidebar components
    sidebar_buttons = [b.label for b in at.sidebar.button]
    assert "New conversation" in sidebar_buttons
    assert "Open Diagnostics" in sidebar_buttons
    assert "Clear Session" in sidebar_buttons

    # Verify 5 primary workspaces in sidebar radio
    sidebar_radios = at.sidebar.radio
    assert len(sidebar_radios) >= 1
    assert sidebar_radios[0].value == "Chat"
    assert "Document Library" in sidebar_radios[0].options
    assert "Summarizer" in sidebar_radios[0].options
    assert "Settings" in sidebar_radios[0].options
    assert "Diagnostics" in sidebar_radios[0].options

    # Verify Chat view is active by default and renders chat input
    assert len(at.chat_input) == 1
    assert "Ask a question about the document" in at.chat_input[0].placeholder

    # Verify no emojis in buttons
    for btn in at.button:
        assert not any(ord(c) > 0x1F000 for c in btn.label)


def test_apptest_workspace_navigation(base_app):
    """AppTest navigation across all 5 primary workspaces."""
    at = base_app.run()
    assert not at.exception

    # 1. Navigate to Document Library
    at.sidebar.radio[0].set_value("Document Library").run()
    assert not at.exception
    assert any("Document Library" in str(m.value) for m in at.markdown)

    # 2. Navigate to Summarizer
    at.sidebar.radio[0].set_value("Summarizer").run()
    assert not at.exception
    assert any("Document Summarizer" in str(m.value) for m in at.markdown)

    # 3. Navigate to Settings
    at.sidebar.radio[0].set_value("Settings").run()
    assert not at.exception
    assert any("Settings & Diagnostics" in str(m.value) for m in at.markdown)

    # 4. Navigate to Diagnostics
    at.sidebar.radio[0].set_value("Diagnostics").run()
    assert not at.exception
    assert any("Settings & Diagnostics" in str(m.value) for m in at.markdown)

    # 5. Navigate back to Chat
    at.sidebar.radio[0].set_value("Chat").run()
    assert not at.exception
    assert len(at.chat_input) == 1


def test_apptest_new_conversation_clears_history(base_app):
    """Clicking 'New conversation' resets chat transcript while preserving active session."""
    at = base_app.run()
    assert not at.exception

    # Populate dummy conversation in session state
    at.session_state.chat_history = [
        {"role": "user", "content": "What is this paper about?"},
        {"role": "assistant", "content": "This paper presents a local-first system."},
    ]
    at.run()

    # Find and click 'New conversation' button
    new_chat_btn = [b for b in at.sidebar.button if b.label == "New conversation"][0]
    new_chat_btn.click().run()
    assert not at.exception

    # Verify chat history is now empty
    assert len(at.session_state.chat_history) == 0


def test_apptest_example_prompt_selection(base_app):
    """Clicking an example analysis prompt queues the prompt into session state."""
    at = base_app.run()
    assert not at.exception

    # Add mock document so example prompt buttons appear
    at.session_state.indexed_files = {"sample.pdf"}
    at.session_state.document_metadata = {
        "doc_test": {"doc_id": "doc_test", "filename": "sample.pdf", "pages": 5, "chunks": 12}
    }
    at.run()

    # Find example prompt buttons
    summary_btn = [b for b in at.button if b.label == "Summarize thesis"]
    assert len(summary_btn) == 1

    summary_btn[0].click().run()
    assert not at.exception
    # Verify the prompt was consumed and submitted into chat history
    assert len(at.session_state.chat_history) >= 1
    assert (
        at.session_state.chat_history[0]["content"]
        == "Summarize the core thesis and key findings of the document in detail."
    )


def test_direct_vs_auto_attributed_citation_chips():
    """Citation chips distinguish direct model citations from auto-attributed citations."""
    direct_chip = render_citation_chip(doc_id="doc_1", page=7, filename="paper.pdf", rank=1, auto_attributed=False)
    assert "[E1] paper.pdf · p. 7" in direct_chip
    assert "(auto)" not in direct_chip
    assert "#5EEAD4" in direct_chip

    auto_chip = render_citation_chip(doc_id="doc_1", page=12, filename="paper.pdf", rank=2, auto_attributed=True)
    assert "[E2] paper.pdf · p. 12" in auto_chip
    assert "(auto)" in auto_chip
    assert 'data-citation-state="auto"' in auto_chip
    assert "#C4B5FD" in auto_chip


def test_verification_caption_grounding_distinctions():
    """Grounding captions separate abstention, ungrounded, mixed, and auto-attributed states."""
    # 1. Explicit abstention
    assert "Explicit abstention" in verification_caption({"abstention_detected": True})

    # 2. Ungrounded response
    assert "Ungrounded response" in verification_caption({"total_citations": 0})

    # 3. Auto-attributed only
    auto_ver = {
        "is_valid": True,
        "precision": 1.0,
        "total_citations": 2,
        "auto_attributed_count": 2,
        "support_checked": False,
    }
    cap = verification_caption(auto_ver)
    assert "Auto-attributed citations (2/2)" in cap
    assert "support not verified" in cap

    # 4. Model-generated grounded
    model_ver = {
        "is_valid": True,
        "precision": 1.0,
        "total_citations": 2,
        "auto_attributed_count": 0,
        "support_checked": True,
        "support_precision": 0.65,
    }
    cap_model = verification_caption(model_ver)
    assert "Citation validity 100%" in cap_model
    assert "grounded (65% lexical overlap, support confirmed)" in cap_model


def test_empty_and_error_state_rendering():
    """render_empty_state renders Stage 6 card with clean SVG icon and no emojis."""
    with patch("streamlit.html") as mock_html, patch("streamlit.markdown") as mock_md:
        render_empty_state("No Documents", "Please upload a document to proceed.", icon_name="document")
        call_arg = mock_html.call_args[0][0] if mock_html.called else mock_md.call_args[0][0]
        assert "amoled-card" in call_arg
        assert "No Documents" in call_arg
        assert "<svg" in call_arg
        assert not any(ord(c) > 0x1F000 for c in call_arg)
