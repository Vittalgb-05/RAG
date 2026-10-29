"""
Streamlit front-end for the local-first PDF intelligence workspace.

Chat is the default workspace: evidence-grounded questions and document-wide
summaries with page provenance. Library owns upload and lifecycle actions,
Summarizer exposes the hierarchical summarizer, Settings owns inference/privacy,
and Diagnostics exposes redacted health and log data. Navigation exists once
(sidebar); content views never duplicate it.
"""

import logging
import os
from pathlib import Path
import time
import uuid

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from dotenv import load_dotenv
import streamlit as st

from core.doc_store import DocStore
from providers.litellm_provider import LiteLLMProvider
from core.local_llm import AiModel
from core.logging_setup import configure_logging, suppress_torch_classes_scan_warning
from core.redaction import redact_text
from providers.model_provider import HealthStatus, ProviderCapabilities
from ui.components import push_notification, render_brand_header, render_notifications
from core.resource_telemetry import get_gpu_memory_info, get_process_memory_info
from ui.hydration import hydrate_startup_state
from ui.session_state import reset_in_memory_session
from ui.theme import inject_custom_theme
from ui.views import (
    render_chat_view,
    render_diagnostics_view,
    render_library_view,
    render_settings_view,
    render_summarizer_view,
)

APP_DIR = Path(__file__).resolve().parent
DOC_STORE_PATH = APP_DIR / "data" / "documents.db"
LOG_DIR = APP_DIR / "data" / "logs"
CACHE_DIR = APP_DIR / ".cache"

# Install the single application logging configuration before any startup work so
# an initialization failure is captured instead of printed to a blank page.
configure_logging(log_dir=LOG_DIR)

logger = logging.getLogger(__name__)

# Silence Streamlit's benign file-watcher traceback for `torch.classes`
suppress_torch_classes_scan_warning()

MAX_CHAT_TURNS = 50
WORKSPACES = ["Chat", "Document Library", "Summarizer", "Settings", "Diagnostics"]
NAV_WORKSPACES = ["Chat", "Document Library", "Summarizer"]
WORKSPACE_ALIASES = {
    "Workspace": "Chat",
    "Ask Documents": "Chat",
    "Library": "Document Library",
}


def normalize_workspace(value: str | None) -> str:
    """Return a canonical workspace name, falling back to Chat for unknown values."""
    candidate = WORKSPACE_ALIASES.get(value or "", value or "")
    return candidate if candidate in WORKSPACES else "Chat"


def safe_has_secret(key: str) -> bool:
    """Safely check if key exists in st.secrets without throwing FileNotFoundError or KeyError."""
    try:
        if hasattr(st, "secrets"):
            return key in st.secrets
    except (FileNotFoundError, KeyError, AttributeError):
        # Streamlit raises FileNotFoundError when no secrets.toml exists.
        return False
    return False


def _render_startup_failure(title: str, detail: str, remediation: str) -> None:
    """Render an actionable startup error instead of a blank Streamlit page."""
    st.error(title)
    detail = redact_text(detail)
    st.markdown(f"**How to fix it:** {remediation}")
    with st.expander("Technical details", expanded=False):
        st.code(detail)


def _reset_session_security_state() -> None:
    """Reset session security state, in-memory models, and cleanse credentials (WR-02)."""
    reset_in_memory_session()


# ------------------------------------------------------------------
# Page configuration (must be the first Streamlit call)
# ------------------------------------------------------------------

st.set_page_config(
    page_title="PAPER / INTELLIGENCE",
    page_icon="assets/brand_mark.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply AMOLED CSS tokens, scoped component styling, and subtle motion
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
    ("chat_sessions", []),
    ("current_chat_id", None),
    ("notifications", []),
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


@st.cache_resource(show_spinner=False)
def get_doc_store() -> DocStore:
    """Return the process-wide SQLite document store shared across sessions.

    Construction is cached so Streamlit reruns do not reopen/re-migrate the
    database, and startup failures can be rendered with actionable guidance.
    """
    return DocStore(DOC_STORE_PATH)


try:
    doc_store = get_doc_store()
except Exception as startup_err:
    # Startup boundary: surface guidance instead of Streamlit's blank error page.
    logger.exception("Failed to initialize the document store at %s", DOC_STORE_PATH)
    _render_startup_failure(
        "The document database could not be opened.",
        f"{type(startup_err).__name__}: {startup_err}",
        f"Ensure `{DOC_STORE_PATH.parent}` exists and is writable, then reload. "
        "If the database file is corrupt, move it aside (a fresh empty store will be created) "
        "and re-ingest your PDFs.",
    )
    st.stop()


def _make_hydration_progress_reporter():
    """Build a lazy progress reporter so the bar only appears when repair is needed."""
    state = {"bar": None}

    def report(completed: int, total: int, label: str) -> None:
        try:
            bar = state["bar"]
            if bar is None:
                bar = st.progress(0.0, text=label)
                state["bar"] = bar
            bar.progress(min(completed / max(total, 1), 1.0), text=label)
        except Exception as progress_err:  # pragma: no cover - UI boundary
            logger.debug("Could not render hydration progress: %s", progress_err)

    def finish() -> None:
        bar = state["bar"]
        if bar is not None:
            try:
                bar.empty()
            except Exception as progress_err:  # pragma: no cover - UI boundary
                logger.debug("Could not clear hydration progress: %s", progress_err)

    return report, finish


_report_hydration, _finish_hydration = _make_hydration_progress_reporter()
try:
    # Hydrate documents and retriever from SQLite & LanceDB on initial connection (P0-2).
    hydrate_startup_state(doc_store, progress_callback=_report_hydration)
finally:
    _finish_hydration()


def get_session_ai_model() -> AiModel:
    """Retrieve or initialize session-scoped AiModel instance."""
    if "ai_model" not in st.session_state or st.session_state.ai_model is None:
        load_dotenv()
        st.session_state.ai_model = AiModel()
    return st.session_state.ai_model


load_ai_model = get_session_ai_model

try:
    ai_model = load_ai_model()
except Exception as model_err:
    logger.exception("Failed to initialize the inference model")
    _render_startup_failure(
        "The inference engine could not be initialized.",
        f"{type(model_err).__name__}: {model_err}",
        "Start the local llama-server (see the README) or check `LLAMA_SERVER_URL`. "
        "Cloud mode requires a consented provider and a valid API key.",
    )
    st.stop()
st.session_state.ai_model = ai_model

# Synchronize cloud provider if enabled with user consent
try:
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
except Exception as cloud_err:
    # Never leave the user on a blank page because cloud state is malformed;
    # fall back to strictly local inference and report the problem.
    logger.exception("Cloud provider synchronization failed; falling back to local mode.")
    st.session_state.cloud_mode = False
    st.session_state.cloud_mode_toggle = False
    st.session_state.user_consented = False
    st.warning(f"Cloud mode could not be enabled: {redact_text(str(cloud_err))}. Continuing in local mode.")
    ai_model.set_cloud_mode(False)

# Probe provider health at most once every 5 seconds.  Streamlit reruns this script
# on every interaction; probing an offline llama-server on each rerun adds seconds of
# latency.  The snapshot lives in session state so it survives reruns.
_HEALTH_TTL_SECONDS = 5.0
_now = time.monotonic()
_snapshot = st.session_state.get("_health_snapshot")
_last_probe = float(st.session_state.get("_health_probe_ts", 0.0))
if (
    _snapshot is None
    or _snapshot.get("provider") is not ai_model.provider
    or (_now - _last_probe) >= _HEALTH_TTL_SECONDS
):
    try:
        health = ai_model.check_health()
        caps = ai_model.get_capabilities()
    except Exception as health_err:
        # Never let a provider probe blank the app; present an offline state with
        # the underlying reason so the operator can act on it.
        logger.exception("Provider health probe failed")
        health = HealthStatus(
            status="error",
            message=f"Health probe failed: {redact_text(str(health_err))}",
        )
        caps = ProviderCapabilities(
            model_name="unavailable",
            context_window=4096,
            supports_vision=False,
            is_local=True,
            supports_streaming=False,
        )
    st.session_state._health_snapshot = {"health": health, "caps": caps, "provider": ai_model.provider}
    st.session_state._health_probe_ts = _now
else:
    health = _snapshot["health"]
    caps = _snapshot["caps"]
is_healthy = bool(health.status == "healthy")
cloud_active = bool(st.session_state.cloud_mode and st.session_state.user_consented)


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
        "**What stays on your device when only local inference is active:**\n"
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
        if st.button("Cancel (Keep Local)", use_container_width=True, key="consent_no_btn"):
            st.session_state.user_consented = False
            st.session_state.cloud_mode = False
            st.session_state.cloud_mode_toggle = False
            st.session_state.settings_cloud_toggle = False
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
# Recent chats (real, session-scoped conversations)
# ------------------------------------------------------------------


def _archive_current_chat() -> None:
    """Archive the current transcript before starting a new conversation."""
    history = list(st.session_state.chat_history)
    if not history:
        st.session_state.current_chat_id = None
        return
    first_user = next(
        (turn.get("content", "") for turn in history if turn.get("role") == "user" and turn.get("content")),
        "Conversation",
    )
    session_id = st.session_state.current_chat_id or f"chat_{uuid.uuid4().hex[:8]}"
    sessions = [session for session in st.session_state.chat_sessions if session.get("id") != session_id]
    sessions.append(
        {
            "id": session_id,
            "title": str(first_user).strip()[:80] or "Conversation",
            "history": history,
            "updated": time.time(),
        }
    )
    st.session_state.chat_sessions = sessions[-8:]
    st.session_state.current_chat_id = None


def _start_new_chat() -> None:
    """Start a fresh conversation without deleting stored documents or indexes."""
    _archive_current_chat()
    st.session_state.chat_history = []
    st.session_state.active_workspace = "Chat"


# ------------------------------------------------------------------
# Sidebar: brand, navigation, recent chats, truthful status
# ------------------------------------------------------------------

with st.sidebar:
    render_brand_header()

    if st.button("New chat", key="sidebar_new_conversation", use_container_width=True):
        _start_new_chat()
        st.rerun()

    current_ws = normalize_workspace(st.session_state.active_workspace)
    # Off-nav workspaces (Settings, Diagnostics) keep the last nav selection so a
    # rerun does not look like a radio change and bounce back to Chat.
    nav_value = current_ws if current_ws in NAV_WORKSPACES else st.session_state.get("_nav_value", "Chat")
    selected_workspace = st.radio(
        "Workspace",
        options=NAV_WORKSPACES,
        index=NAV_WORKSPACES.index(nav_value),
        label_visibility="collapsed",
    )
    # Compare against the previous radio value instead of the active workspace:
    # Settings/Diagnostics are not radio options, so comparing to the active page
    # would immediately bounce those workspaces back to Chat.
    previous_nav = st.session_state.get("_nav_value")
    st.session_state._nav_value = selected_workspace
    if previous_nav is not None and selected_workspace != previous_nav:
        st.session_state.active_workspace = selected_workspace
        st.rerun()

    st.markdown(
        "<div class='sidebar-section-label'>Recent chats</div>",
        unsafe_allow_html=True,
    )
    archived = sorted(st.session_state.chat_sessions, key=lambda item: item.get("updated", 0.0), reverse=True)
    if st.session_state.chat_history:
        st.caption("Current conversation")
    if not archived and not st.session_state.chat_history:
        st.caption("No conversations yet.")
    for session in archived[:5]:
        if st.button(
            str(session.get("title", "Conversation"))[:48], key=f"recent_{session.get('id')}", use_container_width=True
        ):
            st.session_state.chat_history = list(session.get("history", []))
            st.session_state.current_chat_id = session.get("id")
            st.session_state.active_workspace = "Chat"
            st.rerun()

    st.divider()

    # Truthful provider status: derived from the active provider, not a constant.
    if is_healthy:
        if getattr(caps, "is_local", True):
            status_text = f"Local · {caps.model_name}"
            dot_color = "#34D399"
        else:
            status_text = f"Cloud · {caps.model_name}"
            dot_color = "#A78BFA"
    elif health.status == "loading":
        status_text = "Provider loading"
        dot_color = "#FBBF24"
    else:
        status_text = "Provider offline"
        dot_color = "#F87171"
    st.html(
        f'<div class="provider-status">'
        f'<span class="provider-dot" style="background-color:{dot_color};"></span>'
        f"<span>{status_text}</span></div>"
    )
    if not is_healthy and health.message:
        st.caption(redact_text(health.message))
    st.caption(
        "Inference is local by default. Cloud excerpts leave this device only after explicit consent."
        if not cloud_active
        else "Cloud inference is active: prompts and retrieved excerpts leave this device."
    )

    st.divider()
    if st.button("Diagnostics", key="sidebar_diagnostics_btn", use_container_width=True):
        st.session_state.active_workspace = "Diagnostics"
        st.rerun()

    with st.expander("Session", expanded=False):
        proc_info = get_process_memory_info()
        gpu_info = get_gpu_memory_info()
        ram_mb = proc_info.get("rss_mb", 0.0)
        vram_str = (
            f"{gpu_info.get('used_mb', 0.0):.0f} / {gpu_info.get('total_mb', 0.0):.0f} MB" if gpu_info else "CPU-only"
        )
        st.markdown(
            f"<div class='sidebar-meta'>RAM: {ram_mb:.0f} MB · VRAM: {vram_str}</div>",
            unsafe_allow_html=True,
        )
        if st.button("Clear session", key="sidebar_clear_session_btn", use_container_width=True):
            _reset_session_security_state()
            push_notification("info", "Session cleared. Stored documents and indexes are untouched.")
            st.rerun()

    if st.button("Settings", key="sidebar_settings_btn", use_container_width=True):
        st.session_state.active_workspace = "Settings"
        st.rerun()


# ------------------------------------------------------------------
# Main Content View Routing (single navigation source)
# ------------------------------------------------------------------

active_page = normalize_workspace(st.session_state.active_workspace)

if active_page == "Chat":
    render_chat_view(
        ai_model=ai_model,
        health=health,
        caps=caps,
        doc_store=doc_store,
        cache_dir=CACHE_DIR,
    )
elif active_page == "Summarizer":
    render_summarizer_view(
        doc_store=doc_store,
        ai_model=ai_model,
        is_healthy=is_healthy,
    )
elif active_page == "Document Library":
    render_library_view(
        doc_store=doc_store,
        hybrid_retriever=st.session_state.hybrid_retriever,
        cache_dir=CACHE_DIR,
        ai_model=ai_model,
    )
elif active_page == "Settings":
    render_settings_view(
        ai_model=ai_model,
        health=health,
        caps=caps,
        doc_store=doc_store,
        cache_dir=CACHE_DIR,
    )
elif active_page == "Diagnostics":
    render_diagnostics_view(
        ai_model=ai_model,
        health=health,
        caps=caps,
        doc_store=doc_store,
        cache_dir=CACHE_DIR,
    )

render_notifications()
