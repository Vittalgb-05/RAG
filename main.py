"""
Streamlit front-end for the local RAG pipeline.

Lets the user upload any PDF, asks questions about it, and streams
the answer token-by-token from an LLM — with server-side validation,
deduplication via SQLite metadata store, and page-level progress tracking.

Pipeline recap
--------------
PDF upload → validate_pdf_bytes → DocStore dedup check → PdfReader (text extraction)
→ DocStore persistence → LocalEmbedding (indexing) → AiModel (retrieval + streaming generation)
→ st.write_stream (live token rendering in the browser)
"""

import datetime
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from dotenv import load_dotenv
import streamlit as st

from doc_store import DocStore
from docling_reader import DoclingReader
from hybrid_retriever import HybridRetriever
from litellm_provider import LiteLLMProvider
from local_embedding import LocalEmbedding
from local_llm import AiModel
from logging_setup import suppress_torch_classes_scan_warning
from models import Chunk, Document, Page, cache_dir_for
from ocr_fallback import apply_conditional_ocr
from prompt_budget import bound_chat_history
from resource_telemetry import get_gpu_memory_info, get_process_memory_info
from summarizer import Summarizer
from upload_validation import MAX_FILE_MB, validate_pdf_bytes
from visual_analyzer import VisualAnalyzer

logger = logging.getLogger(__name__)

# Silence Streamlit's benign file-watcher traceback for `torch.classes` (see logging_setup).
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
# Page configuration  (must be the very first Streamlit call)
# ------------------------------------------------------------------

st.set_page_config(
    page_title="RAG Assistant",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
# Streamlit reruns the whole script on every user interaction.
# Session state persists across reruns within a single browser session.

for key, default in [
    ("doc_ids", set()),  # set of doc_id hashes we have already indexed in this session
    ("indexed_files", set()),  # set of filenames displayed in the UI
    ("document_metadata", {}),  # dict mapping filename -> metadata dict
    ("local_embedding", None),  # unified index spanning all uploaded documents
    ("hybrid_retriever", None),  # persistent LanceDB hybrid retriever
    ("chat_history", []),  # list of {"role": ..., "content": ..., "sources": ...} dicts
    ("cloud_mode", False),  # boolean toggle for optional cloud inference (INF-04, UI-04)
    ("cloud_mode_toggle", False),  # widget key state for toggle synchronization (UI-04)
    ("user_consented", False),  # explicit user consent required for cloud transmission
    ("cloud_provider", "groq"),  # active cloud provider: "groq", "openai", "anthropic"
    ("cloud_model", "groq/llama-3.3-70b-versatile"),  # model identifier for LiteLLM
    ("cloud_api_keys", {"groq": "", "openai": "", "anthropic": ""}),  # per-provider session API keys
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------------------------------
# Cached helpers & Anchored Storage Paths
# ------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent
DOC_STORE_PATH = APP_DIR / "data" / "documents.db"
CACHE_DIR = APP_DIR / ".cache"
doc_store = DocStore(DOC_STORE_PATH)


def get_session_ai_model() -> AiModel:
    """Retrieve or initialize session-scoped AiModel instance.

    Guarantees that user consent, model selection, and cloud mode toggling
    remain strictly isolated to the active browser session, preventing
    cross-session routing contamination in multi-user deployments (P1 audit).
    """
    if "ai_model" not in st.session_state or st.session_state.ai_model is None:
        load_dotenv()
        st.session_state.ai_model = AiModel()
    return st.session_state.ai_model


# Backwards compatibility alias
load_ai_model = get_session_ai_model


# ------------------------------------------------------------------
# Sidebar — model status + document upload
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📄 RAG Assistant")
    st.markdown("Ask questions about any PDF with local indexing and intelligent deduplication.")
    st.divider()

    # Privacy & Cloud Inference Controls (UI-04, INF-04)
    st.markdown("#### Privacy & Provider Mode")

    def _render_consent_dialog_content() -> None:
        st.warning(
            "⚠️ **External Cloud Transmission Notice**\n\n"
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
                st.rerun()
        with col_no:
            if st.button("Cancel (Keep 100% Local)", use_container_width=True, key="consent_no_btn"):
                st.session_state.user_consented = False
                st.session_state.cloud_mode = False
                st.session_state.cloud_mode_toggle = False
                st.rerun()

    if hasattr(st, "dialog"):

        @st.dialog("Cloud Inference & Data Privacy Consent")
        def show_consent_dialog() -> None:
            _render_consent_dialog_content()
    else:

        def show_consent_dialog() -> None:
            _render_consent_dialog_content()

    cloud_toggle_val = st.toggle(
        "Enable Cloud Inference",
        value=st.session_state.cloud_mode,
        key="cloud_mode_toggle",
        help="Route response generation through optional cloud LLM providers (Groq, OpenAI, Anthropic).",
    )

    if cloud_toggle_val and not st.session_state.user_consented:
        show_consent_dialog()
    elif not cloud_toggle_val and st.session_state.cloud_mode:
        st.session_state.cloud_mode = False
        st.session_state.cloud_mode_toggle = False
        st.session_state.user_consented = False
        st.rerun()

    CLOUD_PROVIDER_OPTIONS = {
        "groq": ("Groq (Llama 3.3 70B)", "groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
        "openai": ("OpenAI (GPT-4o mini)", "openai/gpt-4o-mini", "OPENAI_API_KEY"),
        "anthropic": ("Anthropic (Claude 3.5 Haiku)", "anthropic/claude-3-5-haiku-20241022", "ANTHROPIC_API_KEY"),
    }

    if st.session_state.cloud_mode and st.session_state.user_consented:
        st.caption("☁️ **Cloud Mode Active** (Egress permitted with user consent)")
        current_idx = (
            list(CLOUD_PROVIDER_OPTIONS.keys()).index(st.session_state.cloud_provider)
            if st.session_state.cloud_provider in CLOUD_PROVIDER_OPTIONS
            else 0
        )
        selected_provider_key = st.selectbox(
            "Cloud Provider",
            options=list(CLOUD_PROVIDER_OPTIONS.keys()),
            format_func=lambda k: CLOUD_PROVIDER_OPTIONS[k][0],
            index=current_idx,
        )
        if selected_provider_key != st.session_state.cloud_provider:
            st.session_state.cloud_provider = selected_provider_key
            st.session_state.cloud_model = CLOUD_PROVIDER_OPTIONS[selected_provider_key][1]
            st.rerun()

        st.session_state.cloud_model = CLOUD_PROVIDER_OPTIONS[selected_provider_key][1]
        env_var_name = CLOUD_PROVIDER_OPTIONS[selected_provider_key][2]
        env_has_key = bool(os.environ.get(env_var_name) or safe_has_secret(env_var_name))
        key_placeholder = f"Configured via {env_var_name}" if env_has_key else f"Enter {env_var_name}"

        current_key = st.session_state.cloud_api_keys.get(selected_provider_key, "")
        entered_key = st.text_input(
            "Session API Key (Optional if set in env)",
            value=current_key,
            type="password",
            placeholder=key_placeholder,
            help=f"Session API key for {CLOUD_PROVIDER_OPTIONS[selected_provider_key][0]}. Kept in memory only.",
        )
        if entered_key != current_key:
            st.session_state.cloud_api_keys[selected_provider_key] = entered_key
            st.rerun()

        if st.button("Revoke Consent (Switch to Local)", use_container_width=True):
            st.session_state.cloud_mode = False
            st.session_state.cloud_mode_toggle = False
            st.session_state.user_consented = False
            st.rerun()
    else:
        st.caption("🔒 **Local Mode Active** (100% on-device, zero network egress)")

    st.divider()

    # Model loading & health
    st.markdown("#### Model Status")
    ai_model = load_ai_model()
    st.session_state.ai_model = ai_model

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

    with st.status("Initializing AI Assistant...", expanded=False) as model_status:
        if model_status is not None:
            if is_healthy:
                if caps.is_local:
                    model_status.update(
                        label=f"🟢 Inference: Local ({caps.model_name})",
                        state="complete",
                        expanded=False,
                    )
                else:
                    model_status.update(
                        label=f"☁️ Inference: Cloud ({caps.model_name})",
                        state="complete",
                        expanded=False,
                    )
            elif health.status == "loading":
                model_status.update(
                    label=f"⏳ Inference: Loading ({caps.model_name})...",
                    state="running",
                    expanded=True,
                )
                st.info(health.message)
            else:
                model_status.update(
                    label="⚠️ Inference: Offline (setup required)",
                    state="error",
                    expanded=True,
                )
                st.warning(health.message)

    st.divider()

    # Document upload
    st.markdown("#### Document")

    col_clear, col_purge = st.columns(2)
    with col_clear:
        if st.button("Clear Session", use_container_width=True, help="Reset in-memory chat and session state"):
            _reset_session_security_state()
            st.rerun()

    with col_purge:
        if st.button(
            "Purge All Data",
            type="secondary",
            use_container_width=True,
            help="Permanently delete all indexed documents, SQLite records, LanceDB tables, and disk caches",
        ):
            doc_store.purge_all()
            if st.session_state.get("hybrid_retriever"):
                st.session_state.hybrid_retriever.purge_all()
                st.session_state.hybrid_retriever.close()
            else:
                temp_retriever = HybridRetriever()
                temp_retriever.purge_all()
                temp_retriever.close()

            if CACHE_DIR.exists():
                try:
                    shutil.rmtree(CACHE_DIR, ignore_errors=True)
                except Exception as err:
                    logger.warning("Failed to remove cache dir %s: %s", CACHE_DIR, err)

            _reset_session_security_state()
            st.toast("Purged all persistent databases, vectors, and disk caches.")
            st.rerun()

    uploaded_files = st.file_uploader(
        "Upload PDFs",
        type=["pdf"],
        help="Drag and drop PDFs here, or click Browse files.",
        label_visibility="collapsed",
        accept_multiple_files=True,
    )

    if uploaded_files:
        # Build the embedding index for any new PDFs
        with st.status("Processing documents…", expanded=True) as doc_status:
            new_pdf_uploaded = False

            for uploaded_file in uploaded_files:
                filename = uploaded_file.name

                # WR-04: Size pre-check before buffering into memory
                if (
                    hasattr(uploaded_file, "size")
                    and uploaded_file.size is not None
                    and uploaded_file.size > MAX_FILE_MB * 1024 * 1024
                ):
                    st.error(
                        f"File too large ({uploaded_file.size / (1024 * 1024):.1f} MB > {MAX_FILE_MB} MB) — `{filename}`."
                    )
                    continue

                # 1. Single raw bytes read per file
                raw_bytes = uploaded_file.getvalue()

                # 2. Server-side validation (%PDF header, size limit, page limit)
                st.write(f"Validating `{filename}`…")
                try:
                    validated = validate_pdf_bytes(raw_bytes, filename)
                except ValueError as e:
                    st.error(str(e))
                    continue

                # 3. Deduplication check via SHA-256 in DocStore and session state
                doc_id = validated.doc_id
                existing_doc = doc_store.get_by_sha(validated.sha256)

                if doc_id in st.session_state.doc_ids or (existing_doc and existing_doc.status == "indexed"):
                    st.info(f"Already indexed (`{doc_id}`) — skipped duplicate.")
                    st.session_state.doc_ids.add(doc_id)
                    st.session_state.indexed_files.add(filename)
                    st.session_state.document_metadata[doc_id] = {
                        "doc_id": doc_id,
                        "filename": filename,
                        "sha256": validated.sha256,
                        "upload_time": existing_doc.upload_time
                        if existing_doc
                        else datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "pages": existing_doc.num_pages if existing_doc else validated.num_pages,
                        "chunks": existing_doc.num_chunks if existing_doc else 0,
                    }
                    # CR-01: On dedup hit after restart (empty session index), restore chunks from DocStore
                    if st.session_state.hybrid_retriever is None:
                        persisted_chunks = doc_store.get_chunks_for_doc(doc_id)
                        if persisted_chunks:
                            if st.session_state.local_embedding is None:
                                st.session_state.local_embedding = LocalEmbedding()
                            st.session_state.hybrid_retriever = HybridRetriever(
                                embedding_fn=st.session_state.local_embedding._embed_one
                            )
                            chunk_dicts = [c.model_dump() for c in persisted_chunks]
                            embeddings = st.session_state.local_embedding.get_embeddings(
                                [c["content"] for c in chunk_dicts]
                            )
                            st.session_state.hybrid_retriever.index_chunks(chunk_dicts, embeddings.tolist())
                            new_pdf_uploaded = True
                    continue

                new_pdf_uploaded = True

                # 4. Text extraction with page-level fault isolation and progress indicator
                st.write(f"Extracting text from `{filename}`…")
                progress_bar = st.progress(0.0)

                # CR-02: Guard reader construction and text extraction against malformed PDFs
                paragraphs: list[dict[str, Any]] = []
                page_records: list[Page] = []
                try:
                    pdf_stream = io.BytesIO(raw_bytes)
                    docling_reader = DoclingReader(pdf_stream, filename=filename)

                    sha12 = validated.sha256[:12]
                    docling_reader.extract_text(doc_id=doc_id, sha12=sha12)
                    paragraphs = docling_reader.get_paragraphs()
                    page_records = docling_reader.get_page_records()

                    # 4b. Conditional RapidOCR fallback for low-text or scanned pages (INGEST-04)
                    page_records, paragraphs = apply_conditional_ocr(
                        pdf_bytes=raw_bytes,
                        page_records=page_records,
                        existing_chunks=paragraphs,
                        doc_id=doc_id,
                        sha12=sha12,
                        filename=filename,
                    )

                    # 4c. Visual element detection, cropping, and VLM analysis (VIS-01, VIS-02, VIS-03)
                    visual_analyzer = VisualAnalyzer()
                    current_model = getattr(st.session_state, "ai_model", None) or ai_model
                    active_provider = current_model.provider if current_model is not None else None
                    local_vlm_provider = (
                        active_provider
                        if (active_provider is not None and active_provider.get_capabilities().is_local)
                        else None
                    )
                    evidence_elements = visual_analyzer.analyze_visual_elements(
                        pdf_bytes=raw_bytes,
                        doc_id=doc_id,
                        provider=local_vlm_provider,
                    )
                    if evidence_elements:
                        doc_store.record_evidence_elements(evidence_elements)

                except Exception as err:
                    st.error(f"Could not extract text from `{filename}` ({err})")
                    continue

                for idx, page in enumerate(page_records):
                    doc_store.record_page(page)
                    progress_bar.progress((idx + 1) / max(1, len(page_records)))
                    if page.status == "failed":
                        st.warning(f"Page {page.page_num} in `{filename}` skipped ({page.error})")

                # 5. Build vector embeddings and persistent LanceDB hybrid index (QUAL-01: sole index in session)
                st.write(f"Building index for `{filename}` ({len(paragraphs)} chunks)…")
                if st.session_state.local_embedding is None:
                    st.session_state.local_embedding = LocalEmbedding()

                if st.session_state.hybrid_retriever is None:
                    st.session_state.hybrid_retriever = HybridRetriever(
                        embedding_fn=st.session_state.local_embedding._embed_one
                    )
                embeddings = st.session_state.local_embedding.get_embeddings([p["content"] for p in paragraphs])
                st.session_state.hybrid_retriever.index_chunks(paragraphs, embeddings=embeddings.tolist())

                # 6. Persist metadata and chunks in DocStore (CR-03 & WR-03)
                chunk_models = [Chunk.model_validate(p) for p in paragraphs]
                doc_store.record_chunks(chunk_models)

                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                doc_model = Document(
                    doc_id=doc_id,
                    filename=filename,
                    sha256=validated.sha256,
                    size_bytes=validated.size_bytes,
                    num_pages=validated.num_pages,
                    status="indexed",
                    upload_time=now_iso,
                    num_chunks=len(paragraphs),
                )
                try:
                    doc_store.upsert_document(doc_model)
                except sqlite3.IntegrityError:
                    st.info(f"Document `{filename}` already recorded.")

                # 7. Best-effort disk cache write (STORE-03)
                try:
                    cache_dir = cache_dir_for(CACHE_DIR, validated.sha256)
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    with open(cache_dir / "pages.json", "w", encoding="utf-8") as f:
                        json.dump([p.model_dump() for p in page_records], f, indent=2)
                    with open(cache_dir / "chunks.json", "w", encoding="utf-8") as f:
                        json.dump(paragraphs, f, indent=2)
                    with open(cache_dir / "manifest.json", "w", encoding="utf-8") as f:
                        json.dump(doc_model.model_dump(), f, indent=2)
                except OSError as err:
                    st.warning(f"Disk cache write failed for `{filename}` ({err})")

                # 8. Update session state
                st.session_state.doc_ids.add(doc_id)
                st.session_state.indexed_files.add(filename)
                st.session_state.document_metadata[doc_id] = {
                    "doc_id": doc_id,
                    "filename": filename,
                    "sha256": validated.sha256,
                    "upload_time": now_iso,
                    "pages": validated.num_pages,
                    "chunks": len(paragraphs),
                }
                st.success(f"**`{filename}`** indexed successfully (`{doc_id}`)")

            if new_pdf_uploaded:
                st.session_state.chat_history = []
                st.rerun()

            doc_status.update(
                label=f"Indexed {len(st.session_state.indexed_files)} document(s)",
                state="complete",
                expanded=False,
            )

        st.markdown("##### Indexed Documents:")
        for doc_key, meta in st.session_state.document_metadata.items():
            fname = meta.get("filename", doc_key)
            doc_id_label = f" (`{meta.get('doc_id', doc_key)}`)"
            display_time = meta["upload_time"][:19].replace("T", " ")
            st.success(
                f"**`{fname}`**{doc_id_label}\n\n{meta['pages']} pages · {meta['chunks']} chunks · Indexed at {display_time}"
            )
    else:
        st.info("Upload a PDF to get started.")

    st.divider()

    # System Telemetry & Resource Monitoring (QUAL-01)
    with st.expander("📊 System Telemetry & VRAM", expanded=False):
        gpu_info = get_gpu_memory_info()
        proc_info = get_process_memory_info()
        total_docs = doc_store.count_documents()
        total_sums = doc_store.count_summaries()

        if gpu_info is not None:
            vram_used = gpu_info["used_mb"]
            vram_total = gpu_info["total_mb"]
            util_pct = gpu_info["utilization_pct"]
            st.metric(
                label="GPU VRAM",
                value=f"{vram_used:.0f} / {vram_total:.0f} MB",
                delta=f"{util_pct:.1f}% used",
            )
            st.progress(min(1.0, max(0.0, vram_used / max(1.0, vram_total))))
            if vram_used < 3500.0:
                st.caption("🟢 VRAM Healthy (< 3.5 GB)")
            elif vram_used <= 3800.0:
                st.caption("🟡 VRAM Headroom Limited (3.5–3.8 GB)")
            else:
                st.caption("🔴 High VRAM (> 3.8 GB)")
        else:
            st.caption("ℹ️ CPU-only Mode (No NVIDIA GPU detected)")

        st.caption(f"**Process RAM (RSS):** {proc_info['rss_mb']:.1f} MB")
        st.caption(f"**Persistent Cache:** {total_docs} docs · {total_sums} summaries")

    if caps.is_local:
        st.caption(f"🔒 **100% Offline Local Pipeline** · Qwen3-VL ({ai_model.model_name}) + MiniLM-L6-v2 + LanceDB")
    else:
        st.caption(f"☁️ **Cloud Inference** · {caps.model_name} (Embeddings & LanceDB 100% Local)")


def append_chat_turn(turn: dict[str, Any]) -> None:
    """Append a message turn to chat history and enforce MAX_CHAT_TURNS memory bounding."""
    st.session_state.chat_history.append(turn)
    st.session_state.chat_history = bound_chat_history(
        st.session_state.chat_history,
        max_turns=MAX_CHAT_TURNS,
    )


# ------------------------------------------------------------------
# Main content area — tabs for Chat and Summarizer
# ------------------------------------------------------------------

tab_chat, tab_summary = st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])

with tab_chat:
    st.markdown("## Chat & Grounded Question Answering")

    if st.session_state.hybrid_retriever is None and st.session_state.local_embedding is None:
        st.markdown("> **Upload a PDF in the sidebar** to begin asking questions.")
    else:
        total_chunks = sum(meta["chunks"] for meta in st.session_state.document_metadata.values())
        st.caption(
            f"Chatting across **{len(st.session_state.indexed_files)} documents** · {total_chunks} total chunks indexed"
        )

    st.divider()

    # Replay full conversation on every rerun
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message.get("role") == "assistant":
                # Egress disclosure badge (UI-04)
                if message.get("is_cloud"):
                    cloud_m = message.get("model_name", "Cloud API")
                    st.caption(f"☁️ *Generated via external cloud provider ({cloud_m}) with user consent.*")
                elif message.get("is_cloud") is False:
                    st.caption("🔒 *Generated locally on-device (zero network egress).*")

                # Citation verification badge
                v_data = message.get("verification")
                if v_data:
                    if v_data.get("abstention_detected"):
                        st.caption("ℹ️ *Explicit abstention — no document evidence found.*")
                    elif v_data.get("is_valid"):
                        precision = v_data.get("precision", 1.0)
                        st.caption(f"✅ Verified Grounding ({precision:.0%} citation precision)")
                    else:
                        precision = v_data.get("precision", 0.0)
                        st.caption(f"⚠️ Unverified Citations ({precision:.0%} citation precision)")

                # Evidence chips & drawer
                snippets = message.get("snippets", [])
                if snippets:
                    chip_labels = [
                        f"[E{s['rank']}] {s.get('filename', 'doc')} (p. {s.get('page', 1)})" for s in snippets
                    ]
                    if chip_labels:
                        st.caption(f"**Sources:** {', '.join(chip_labels)}")

                    with st.expander("🔍 Cited Evidence & Source Context", expanded=False):
                        for s in snippets:
                            header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                            st.markdown(header)
                            st.markdown(f"> {s.get('content', '').strip()}")
                            if s.get("bbox"):
                                bbox = s["bbox"]
                                st.caption(
                                    f"📐 Region: x0={bbox.get('x0', 0.0):.1f}, y0={bbox.get('y0', 0.0):.1f}, "
                                    f"x1={bbox.get('x1', 0.0):.1f}, y1={bbox.get('y1', 0.0):.1f}"
                                )
                            st.divider()
                elif message.get("sources"):
                    st.info(f"**Sources used:** {', '.join(message['sources'])}", icon="ℹ️")

    # Chat input pinned to bottom
    is_healthy = health.status == "healthy"
    prompt_placeholder = (
        "Ask a question about your documents…"
        if is_healthy
        else "Inference backend is offline. Start llama-server or configure Groq."
    )
    prompt = st.chat_input(
        placeholder=prompt_placeholder,
        disabled=(st.session_state.local_embedding is None or not is_healthy),
    )

    if prompt:
        if not is_healthy:
            st.error(f"Inference backend unavailable: {health.message}")
        else:
            # Show the user's message immediately
            append_chat_turn({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # Contextualize search query with previous user question if history exists
            history_to_pass = st.session_state.chat_history[:-1][-10:]
            search_query = prompt
            if history_to_pass:
                last_user_msgs = [
                    m["content"]
                    for m in history_to_pass
                    if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)
                ]
                if last_user_msgs:
                    search_query = f"{last_user_msgs[-1]} {prompt}"

            # Fetch context once to ensure single shared RetrievalResult identity (RETR-04)
            sources: list[str] = []
            retrieval_res = None
            active_retriever = st.session_state.get("hybrid_retriever") or st.session_state.local_embedding
            if active_retriever is not None:
                if hasattr(active_retriever, "search_hybrid"):
                    retrieval_res = active_retriever.search_hybrid(search_query, k=5)
                    sources = retrieval_res.source_labels()
                else:
                    results = active_retriever.search(search_query, k=10)
                    seen_sources = set()
                    for doc, dist in results:
                        fn = doc.get("filename")
                        if fn and fn not in seen_sources:
                            seen_sources.add(fn)
                            sources.append(fn)

            snippets_data = (
                [s.model_dump() for s in retrieval_res.snippets] if retrieval_res and retrieval_res.snippets else []
            )

            # Stream the assistant response token-by-token
            with st.chat_message("assistant"):
                try:
                    response_stream = ai_model.ask_a_question_from_pdf_stream(
                        pdf_path="",
                        prompt=prompt,
                        local_embedding=active_retriever,
                        chat_history=history_to_pass,
                        retrieval_result=retrieval_res,
                    )
                    full_response = st.write_stream(response_stream)

                    # Egress disclosure badge (UI-04)
                    if not caps.is_local:
                        st.caption(f"☁️ *Generated via external cloud provider ({caps.model_name}) with user consent.*")
                    else:
                        st.caption("🔒 *Generated locally on-device (zero network egress).*")

                    # Validate citations and abstention (QA-03, QA-04)
                    verification = ai_model.validate_response(full_response, retrieval_res)
                    if verification.abstention_detected:
                        st.caption("ℹ️ *Explicit abstention — no document evidence found.*")
                    elif verification.is_valid:
                        precision = verification.precision
                        st.caption(f"✅ Verified Grounding ({precision:.0%} citation precision)")
                    else:
                        precision = verification.precision
                        st.caption(f"⚠️ Unverified Citations ({precision:.0%} citation precision)")

                    # Render live evidence drawer
                    if snippets_data:
                        chip_labels = [
                            f"[E{s['rank']}] {s.get('filename', 'doc')} (p. {s.get('page', 1)})" for s in snippets_data
                        ]
                        if chip_labels:
                            st.caption(f"**Sources:** {', '.join(chip_labels)}")

                        with st.expander("🔍 Cited Evidence & Source Context", expanded=False):
                            for s in snippets_data:
                                header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                                st.markdown(header)
                                st.markdown(f"> {s.get('content', '').strip()}")
                                if s.get("bbox"):
                                    bbox = s["bbox"]
                                    st.caption(
                                        f"📐 Region: x0={bbox.get('x0', 0.0):.1f}, y0={bbox.get('y0', 0.0):.1f}, "
                                        f"x1={bbox.get('x1', 0.0):.1f}, y1={bbox.get('y1', 0.0):.1f}"
                                    )
                                st.divider()
                    elif sources:
                        st.info(f"**Sources used:** {', '.join(sources)}", icon="ℹ️")

                    if getattr(ai_model, "last_truncation_warning", {}).get("context_truncated"):
                        st.caption(
                            "ℹ️ Retrieved evidence context was truncated to fit the active model's token context budget."
                        )

                    append_chat_turn(
                        {
                            "role": "assistant",
                            "content": full_response,
                            "sources": list(sources),
                            "verification": verification.model_dump(),
                            "snippets": snippets_data,
                            "is_cloud": not caps.is_local,
                            "model_name": caps.model_name,
                        }
                    )
                except Exception as err:
                    st.error(f"Inference streaming failed: {err}")
                    append_chat_turn(
                        {
                            "role": "assistant",
                            "content": f"*[Response generation interrupted: {err}]*",
                            "sources": list(sources),
                            "verification": None,
                            "snippets": snippets_data,
                            "is_cloud": not caps.is_local,
                            "model_name": caps.model_name,
                        }
                    )


with tab_summary:
    st.markdown("## 📑 Document Summarizer")
    st.caption("Generate grounded, page-referenced summaries across 5 analytical profiles.")

    if not st.session_state.document_metadata and not st.session_state.indexed_files:
        st.info("Upload and index a PDF in the sidebar to enable summarization.")
    else:
        doc_options = list(st.session_state.document_metadata.keys())
        if doc_options:
            selected_doc_id = st.selectbox(
                "Select Document to Summarize",
                options=doc_options,
                format_func=lambda k: f"{st.session_state.document_metadata[k].get('filename', k)} ({k})",
            )
            file_meta = st.session_state.document_metadata.get(selected_doc_id, {})
        else:
            file_options = sorted(list(st.session_state.indexed_files))
            selected_file = st.selectbox("Select Document to Summarize", options=file_options)
            file_meta = st.session_state.document_metadata.get(selected_file, {})
            selected_doc_id = file_meta.get("doc_id", "")

        selected_sha = file_meta.get("sha256", "")
        if not selected_sha and selected_doc_id:
            doc_rec = doc_store.get_document(selected_doc_id)
            if doc_rec:
                selected_sha = doc_rec.sha256

        profile_map = {
            "overview": "Overview — Executive synthesis & core thesis",
            "detailed": "Detailed — Comprehensive section-by-section breakdown",
            "study_notes": "Study Notes — Pedagogical takeaways & quiz questions",
            "tables_figures": "Tables & Figures — Structured data & visual synthesis",
            "findings": "Findings — Strategic discoveries, risks & recommendations",
        }

        selected_profile = st.radio(
            "Select Summary Profile",
            options=list(profile_map.keys()),
            format_func=lambda p: profile_map[p],
            index=0,
        )

        col_btn, col_force = st.columns([1, 3])
        with col_btn:
            generate_summary_btn = st.button(
                "Generate Summary",
                type="primary",
                disabled=not is_healthy,
                use_container_width=True,
            )
        with col_force:
            force_refresh_summary = st.checkbox("Force re-generate (bypass persistent cache)", value=False)

        summary_cache_key = f"summary_{selected_doc_id}_{selected_profile}"

        if generate_summary_btn:
            with st.status(
                f"Generating {selected_profile.replace('_', ' ').title()} summary...", expanded=True
            ) as sum_status:
                summarizer = Summarizer(provider=ai_model.provider, doc_store=doc_store)
                try:
                    summary_obj = summarizer.summarize_document(
                        doc_id=selected_doc_id,
                        sha256=selected_sha,
                        profile=selected_profile,
                        force_refresh=force_refresh_summary,
                    )
                    st.session_state[summary_cache_key] = summary_obj.model_dump()
                    sum_status.update(label="Summary generated successfully!", state="complete", expanded=False)
                except Exception as sum_err:
                    sum_status.update(label="Summary generation failed", state="error", expanded=True)
                    st.error(f"Summarization error: {sum_err}")

        # Check for summary to display
        active_summary = st.session_state.get(summary_cache_key)
        if not active_summary and selected_sha:
            cached_summ = doc_store.get_summary(selected_sha, selected_profile)
            if cached_summ:
                active_summary = cached_summ.model_dump()

        if active_summary:
            st.divider()
            if active_summary.get("cached"):
                st.caption("⚡ *Loaded from persistent SQLite cache (DocStore v3)*")
            else:
                st.caption(f"✨ *Generated fresh with {active_summary.get('model_version', 'model')}*")

            st.markdown(active_summary.get("summary_text", ""))

            p_refs = active_summary.get("page_references", [])
            if p_refs:
                with st.expander("📄 Referenced Source Pages", expanded=False):
                    st.markdown(f"**Source pages cited:** {', '.join(f'Page {p}' for p in p_refs)}")
                    st.caption(f"Generated at: {active_summary.get('created_at', '')}")
            else:
                st.caption("ℹ️ *No explicit page references cited in summary.*")
