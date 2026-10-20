"""
Streamlit front-end for the AMOLED local-first document workspace.

Provides a unified chatbot-first document workspace:
1. Chat: Evidence-grounded conversational search with citations, table understanding, and visual OCR.
2. Summarizer: Multi-profile analytical summaries with page references and markdown export.
3. Document Library: Complete document lifecycle management (search, inspect, delete, purge).
4. Settings: Hardware telemetry (VRAM/RAM), model health, local/cloud privacy controls.
"""

import logging
import os
from pathlib import Path

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from dotenv import load_dotenv
import streamlit as st

from doc_store import DocStore
from litellm_provider import LiteLLMProvider
from local_llm import AiModel
from logging_setup import suppress_torch_classes_scan_warning
from ui.components import render_brand_header, render_status_pill
from ui.hydration import hydrate_startup_state
from ui.theme import inject_custom_theme
from ui.views import (
    render_chat_view,
    render_library_view,
    render_settings_view,
    render_sidebar_documents,
    render_summarizer_view,
)

logger = logging.getLogger(__name__)

# Silence Streamlit's benign file-watcher traceback for `torch.classes`
suppress_torch_classes_scan_warning()

MAX_CHAT_TURNS = 50


def safe_has_secret(key: str) -> bool:
    """Safely check if key exists in st.secrets without throwing FileNotFoundError or KeyError."""
    try:
        if hasattr(st, "secrets"):
            return key in st.secrets
    except Exception:
        return False
    return False


def _reset_session_security_state() -> None:
    """Reset session security state, in-memory models, and cleanse credentials (WR-02)."""
    st.session_state.doc_ids = set()
    st.session_state.failed_doc_ids = set()
    st.session_state.indexed_files = set()
    st.session_state.document_metadata = {}
    st.session_state.local_embedding = None
    if st.session_state.get("hybrid_retriever"):
        try:
            st.session_state.hybrid_retriever.close()
        except Exception:
            pass
    st.session_state.hybrid_retriever = None
    st.session_state.chat_history = []
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
    st.session_state._startup_hydrated = False

    for k in list(st.session_state.keys()):
        if k.startswith("summary_"):
            del st.session_state[k]

    if st.session_state.get("active_cloud_provider"):
        try:
            st.session_state.active_cloud_provider.close()
        except Exception:
            pass
    st.session_state.active_cloud_provider = None
    st.session_state._cached_cloud_model = None
    st.session_state._cached_cloud_key = None
    st.session_state.cloud_mode = False
    st.session_state.cloud_mode_toggle = False
    st.session_state.user_consented = False
    st.session_state.cloud_api_keys = {"groq": "", "openai": "", "anthropic": ""}


# ------------------------------------------------------------------
# Page configuration (must be the first Streamlit call)
# ------------------------------------------------------------------

st.set_page_config(
    page_title="PAPER / INTELLIGENCE",
    page_icon="assets/brand_mark.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply AMOLED CSS tokens, card styling, and subtle motion
inject_custom_theme()

# ------------------------------------------------------------------
# Session state initialization
# ------------------------------------------------------------------

for key, default in [
    ("doc_ids", set()),
    ("failed_doc_ids", set()),
    ("indexed_files", set()),
    ("document_metadata", {}),
    ("local_embedding", None),
    ("hybrid_retriever", None),
    ("chat_history", []),
    ("cloud_mode", False),
    ("cloud_mode_toggle", False),
    ("user_consented", False),
    ("cloud_provider", "groq"),
    ("cloud_model", "groq/llama-3.3-70b-versatile"),
    ("cloud_api_keys", {"groq": "", "openai": "", "anthropic": ""}),
    ("uploader_key", 0),
    ("active_workspace", "Chat"),
    ("_startup_hydrated", False),
    ("_show_consent_dialog", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------------------------------
# Persistent Storage & Hydration
# ------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
DOC_STORE_PATH = APP_DIR / "data" / "documents.db"
CACHE_DIR = APP_DIR / ".cache"
doc_store = DocStore(DOC_STORE_PATH)

# Hydrate documents and retriever from SQLite & LanceDB on initial connection (P0-2)
hydrate_startup_state(doc_store)


def get_session_ai_model() -> AiModel:
    """Retrieve or initialize session-scoped AiModel instance."""
    if "ai_model" not in st.session_state or st.session_state.ai_model is None:
        load_dotenv()
        st.session_state.ai_model = AiModel()
    return st.session_state.ai_model


load_ai_model = get_session_ai_model

ai_model = load_ai_model()
st.session_state.ai_model = ai_model

# Synchronize cloud provider if enabled with user consent
if st.session_state.cloud_mode and st.session_state.user_consented:
    active_key = st.session_state.cloud_api_keys.get(st.session_state.cloud_provider, "")
    cached_prov = getattr(st.session_state, "active_cloud_provider", None)
    cached_model = getattr(st.session_state, "_cached_cloud_model", None)
    cached_key = getattr(st.session_state, "_cached_cloud_key", None)

    if cached_prov is None or cached_model != st.session_state.cloud_model or cached_key != active_key:
        if cached_prov is not None and hasattr(cached_prov, "close"):
            cached_prov.close()
        cached_prov = LiteLLMProvider(
            model_name=st.session_state.cloud_model,
            api_key=active_key or None,
            user_consented=True,
        )
        st.session_state.active_cloud_provider = cached_prov
        st.session_state._cached_cloud_model = st.session_state.cloud_model
        st.session_state._cached_cloud_key = active_key

    ai_model.set_cloud_mode(True, cloud_provider=cached_prov)
else:
    if hasattr(st.session_state, "active_cloud_provider") and st.session_state.active_cloud_provider is not None:
        if hasattr(st.session_state.active_cloud_provider, "close"):
            st.session_state.active_cloud_provider.close()
        st.session_state.active_cloud_provider = None
        st.session_state._cached_cloud_model = None
        st.session_state._cached_cloud_key = None
    ai_model.set_cloud_mode(False)

health = ai_model.check_health()
caps = ai_model.get_capabilities()
is_healthy = bool(health.status == "healthy")


# ------------------------------------------------------------------
# Cloud Consent Dialog
# ------------------------------------------------------------------


def _render_consent_dialog_content() -> None:
    st.warning(
        "**External Cloud Transmission Notice**\n\n"
        "By enabling Cloud Mode, your user query prompts and retrieved document excerpts "
        "will be transmitted across the network to external model APIs for inference.\n\n"
        "**Transmitted Excerpts Include:**\n"
        "- Extracted document text, tables, and OCR-processed text\n"
        "- Visual figure descriptions and image analysis summaries\n\n"
        "**What stays 100% on your device (zero network egress):**\n"
        "- Original PDF document files and raw image bitmaps\n"
        "- Dense vector embeddings (all-MiniLM-L6-v2 on CPU)\n"
        "- Persistent LanceDB vector database & SQLite store\n\n"
        "Do you consent to transmitting document excerpts and OCR/visual summaries to external cloud APIs for this session?"
    )
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("I Consent & Enable Cloud", type="primary", use_container_width=True, key="consent_yes_btn"):
            st.session_state.user_consented = True
            st.session_state.cloud_mode = True
            st.session_state.cloud_mode_toggle = True
            st.session_state._show_consent_dialog = False
            st.rerun()
    with col_no:
        if st.button("Cancel (Keep 100% Local)", use_container_width=True, key="consent_no_btn"):
            st.session_state.user_consented = False
            st.session_state.cloud_mode = False
            st.session_state.cloud_mode_toggle = False
            st.session_state._show_consent_dialog = False
            st.rerun()


if hasattr(st, "dialog"):

    @st.dialog("Cloud Inference & Data Privacy Consent")
    def show_consent_dialog() -> None:
        _render_consent_dialog_content()
else:

    def show_consent_dialog() -> None:
        _render_consent_dialog_content()


if st.session_state.get("_show_consent_dialog", False):
    show_consent_dialog()


# ------------------------------------------------------------------
# Sidebar: Brand, Engine Status, Documents & Navigation
# ------------------------------------------------------------------

with st.sidebar:
    render_brand_header()

    # Engine Status Pill (rendered via st.sidebar.html)
    if is_healthy:
        if caps.is_local:
            status_html = render_status_pill(f"Local: {caps.model_name}", variant="local")
        else:
            status_html = render_status_pill(f"Cloud: {caps.model_name}", variant="cloud")
    elif health.status == "loading":
        status_html = render_status_pill(f"Loading: {caps.model_name}", variant="warning")
    else:
        status_html = render_status_pill("Inference Offline", variant="error")

    status_block = (
        f'<div style="margin-top: 0.25rem; margin-bottom: 0.75rem;">'
        f'<div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; '
        f'color: #9693A6; margin-bottom: 0.35rem; font-weight: 700;">Engine Status</div>'
        f"{status_html}</div>"
    )
    if hasattr(st.sidebar, "html"):
        st.sidebar.html(status_block)
    else:
        st.sidebar.markdown(status_block, unsafe_allow_html=True)

    if not is_healthy and health.message:
        st.caption(health.message)

    st.divider()

    # Document Uploader and Active Documents
    render_sidebar_documents(
        doc_store=doc_store,
        ai_model=ai_model,
        cache_dir=CACHE_DIR,
    )

    st.divider()

    # Workspace Navigation
    WORKSPACES = [
        "Chat",
        "Summarizer",
        "Document Library",
        "Settings",
    ]

    current_ws = st.session_state.active_workspace
    if current_ws in ("Workspace", "Ask Documents"):
        current_ws = "Chat"

    current_ws_idx = WORKSPACES.index(current_ws) if current_ws in WORKSPACES else 0

    selected_workspace = st.radio(
        "Navigation",
        options=WORKSPACES,
        index=current_ws_idx,
        label_visibility="collapsed",
    )
    if selected_workspace != st.session_state.active_workspace:
        st.session_state.active_workspace = selected_workspace
        st.rerun()

    st.divider()

    # Quick session reset
    if st.button("Clear Session", use_container_width=True, help="Clear in-memory chat and reset upload buffer"):
        _reset_session_security_state()
        st.rerun()

    footer_html = (
        "<div style='font-size: 0.72rem; color: #9693A6; margin-top: 0.75rem; text-align: center; line-height: 1.4;'>"
        "100% Offline Local Pipeline<br>Qwen3-VL · LanceDB · MiniLM</div>"
    )
    if hasattr(st.sidebar, "html"):
        st.sidebar.html(footer_html)
    else:
        st.sidebar.markdown(footer_html, unsafe_allow_html=True)


# ------------------------------------------------------------------
# Main Content View Routing
# ------------------------------------------------------------------

active_page = st.session_state.active_workspace

if active_page in ("Chat", "Ask Documents", "Workspace"):
    render_chat_view(
        ai_model=ai_model,
        health=health,
        caps=caps,
        doc_store=doc_store,
    )
elif active_page == "Summarizer":
    render_summarizer_view(
        doc_store=doc_store,
        ai_model=ai_model,
        is_healthy=is_healthy,
    )
elif active_page in ("Document Library", "Library"):
    render_library_view(
        doc_store=doc_store,
        hybrid_retriever=st.session_state.hybrid_retriever,
    )
elif active_page == "Settings":
    render_settings_view(
        ai_model=ai_model,
        health=health,
        caps=caps,
        doc_store=doc_store,
        cache_dir=CACHE_DIR,
    )
