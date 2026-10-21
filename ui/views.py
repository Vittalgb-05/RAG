"""Modular view renderers for the AMOLED chatbot-first document workspace."""

import html
import logging
from pathlib import Path
import shutil
from typing import Any

import streamlit as st

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from core.citation_validator import should_withhold_answer
from core.local_llm import AiModel
from core.models import CONFIG_VERSION
from core.prompt_budget import bound_chat_history
from core.query_intent import contextualize_query, resolve_retrieval, whole_document_char_budget
from core.resource_telemetry import get_gpu_memory_info, get_process_memory_info
from core.summarizer import Summarizer
from ui.components import (
    get_brand_mark_svg,
    get_svg_icon,
    render_citation_chip,
    render_empty_state,
    render_stat_card,
    render_status_pill,
)
from ui.ingestion_service import IngestionService
from ui.lifecycle_service import LifecycleService
from ui.sanitizer import sanitize_display_markdown
from ui.session_state import reset_in_memory_session
from ingestion.upload_validation import MAX_FILE_MB

logger = logging.getLogger(__name__)

MAX_CHAT_TURNS = 50


def summary_session_key(doc_id: str, profile: str, model_version: str) -> str:
    """Return the version-aware session cache key for a generated summary."""
    return f"summary_{doc_id}_{profile}_{model_version}"


def clear_summary_session_cache() -> None:
    """Drop every in-memory summary, e.g. after a provider or model change."""
    for key in list(st.session_state.keys()):
        if key.startswith("summary_"):
            del st.session_state[key]


def get_session_summary(doc_id: str, profile: str, model_version: str) -> dict[str, Any] | None:
    """Return a session-cached summary only when it matches the active model version.

    The persistent SQLite cache is already version-aware. The session layer used to
    short-circuit it with a version-agnostic key, so a summary from the previous
    provider could be displayed as current after switching models.

    Args:
        doc_id: Selected document ID.
        profile: Summary profile.
        model_version: Active ``model_name:CONFIG_VERSION`` string.

    Returns:
        The cached summary payload, or None if absent/stale (stale keys are removed).
    """
    key = summary_session_key(doc_id, profile, model_version)
    cached = st.session_state.get(key)
    if not isinstance(cached, dict):
        return None
    if cached.get("model_version") != model_version:
        logger.info("Discarding stale session summary for %s (%s)", doc_id, profile)
        st.session_state.pop(key, None)
        return None
    return cached


def store_session_summary(doc_id: str, profile: str, model_version: str, summary: dict[str, Any]) -> None:
    """Store a summary payload under its version-aware session key."""
    st.session_state[summary_session_key(doc_id, profile, model_version)] = summary


def verification_caption(verification: dict[str, Any]) -> str:
    """Build a caption that separates citation validity from verified support.

    ``is_valid`` / ``precision`` only assert that cited ranks exist. The lexical
    support check is a weaker, separate signal; the UI must not call a rank-valid
    answer "verified" when the cited text does not overlap the claim.
    """
    if verification.get("abstention_detected"):
        return "Explicit abstention — no document evidence found."
    if verification.get("total_citations", 0) == 0:
        return "Ungrounded response — no evidence citations ([E#]) were included in the answer."

    precision = float(verification.get("precision", 0.0))
    if not verification.get("is_valid"):
        return f"Citation validity failed ({precision:.0%} of cited ranks exist in retrieved evidence)."

    caption = f"Citation validity {precision:.0%} (cited ranks exist)"
    if verification.get("support_checked"):
        support = float(verification.get("support_precision", 0.0))
        if support >= 0.5:
            caption += f" — lexical support confirmed ({support:.0%})"
        else:
            caption += f" — lexical support not confirmed ({support:.0%})"
    else:
        caption += " — support not verified"
    return caption + "."


def truncation_notice(warning: dict[str, bool] | None) -> str | None:
    """Return a small non-blocking notice for the truncation flags, if any fired."""
    if not warning:
        return None
    if warning.get("context_truncated"):
        return "Context truncated; some evidence was omitted from the prompt."
    if warning.get("history_truncated"):
        return "Conversation history truncated; earlier turns were omitted from the prompt."
    if warning.get("prompt_truncated"):
        return "Question truncated; the prompt exceeded the context budget."
    return None


def _active_retriever() -> Any | None:
    """Return the active vector retriever for lifecycle operations, if any."""
    return st.session_state.get("hybrid_retriever") or st.session_state.get("local_embedding")


def _lifecycle_preflight(action: str, retriever: Any | None = None) -> Any | None:
    """Require a working vector retriever before mutating persistent storage.

    Deleting SQLite rows while vectors remain indexed lets hydration resurrect a
    "deleted" document. Missing retriever support is therefore a hard failure.
    """
    retriever = retriever or _active_retriever()
    if retriever is None or not hasattr(retriever, "delete_document"):
        st.error(
            f"Cannot {action}: the vector index is unavailable in this session. "
            "Refusing to modify SQLite only, because orphaned vectors can resurrect deleted documents. "
            "Restart the app so the index rehydrates, then retry."
        )
        return None
    return retriever


def _delete_document(
    doc_store: DocStore,
    cache_dir: Path,
    doc_id: str,
    filename: str,
    retriever: Any | None = None,
) -> bool:
    """Delete a document across storage tiers with an error boundary."""
    retriever = _lifecycle_preflight("delete this document", retriever)
    if retriever is None:
        return False

    try:
        lifecycle = LifecycleService(
            doc_store=doc_store,
            hybrid_retriever=retriever,
            local_embedding=st.session_state.get("local_embedding"),
            cache_dir=cache_dir,
        )
        lifecycle.delete_document(doc_id, session_state=st.session_state)
    except Exception as err:
        logger.exception("Delete failed for %s", doc_id)
        st.error(
            f"Delete failed for {filename}: {err}. SQLite was left untouched, so the document remains visible. "
            "Retry, or restart the app if the vector index is locked."
        )
        return False

    st.session_state.pop("pending_delete_doc_id", None)
    st.session_state.pop("pending_delete_filename", None)
    st.toast(f"Deleted {filename}")
    return True


def _reindex_document(
    doc_store: DocStore,
    cache_dir: Path,
    doc_id: str,
    filename: str,
    retriever: Any | None = None,
) -> bool:
    """Re-index one document with an error boundary and retriever preflight."""
    retriever = _lifecycle_preflight("re-index this document", retriever)
    if retriever is None:
        return False

    try:
        lifecycle = LifecycleService(
            doc_store=doc_store,
            hybrid_retriever=retriever,
            local_embedding=st.session_state.get("local_embedding"),
            cache_dir=cache_dir,
        )
        reindexed = lifecycle.reindex_document(doc_id)
    except Exception as err:
        logger.exception("Reindex failed for %s", doc_id)
        st.error(
            f"Re-index failed for {filename}: {err}. Stored text is intact; retry after restarting "
            "the app if the vector index is locked."
        )
        return False

    if not reindexed:
        st.error(
            f"Could not re-index {filename}: the document has no stored chunks or the vector index "
            "is unavailable. Re-upload the PDF if extraction produced no text."
        )
        return False

    st.toast(f"Re-indexed {filename}")
    return True


def _purge_all(doc_store: DocStore, cache_dir: Path, retriever: Any | None = None) -> bool:
    """Purge all storage with an error boundary and retriever preflight."""
    retriever = _lifecycle_preflight("purge all data", retriever)
    if retriever is None:
        return False

    try:
        lifecycle = LifecycleService(
            doc_store=doc_store,
            hybrid_retriever=retriever,
            local_embedding=st.session_state.get("local_embedding"),
            cache_dir=cache_dir,
        )
        lifecycle.purge_all(session_state=st.session_state)
    except Exception as err:
        logger.exception("Purge failed")
        st.error(
            f"Purge incomplete: {err}. Some storage tiers may still hold data; retry, or restart "
            "the app if the vector index is locked."
        )
        return False

    st.toast("Purged all local database records, vector tables, and cache files.")
    return True


def clear_cloud_credentials(ai_model: AiModel) -> None:
    """Remove cloud API keys from session state and active provider objects."""
    st.session_state.cloud_api_keys = {"groq": "", "openai": "", "anthropic": ""}
    st.session_state._cached_cloud_key = None
    st.session_state._cached_cloud_model = None

    active = st.session_state.get("active_cloud_provider")
    for provider in (active, getattr(ai_model, "cloud_provider", None), getattr(ai_model, "provider", None)):
        if provider is None:
            continue
        if hasattr(provider, "api_key"):
            try:
                provider.api_key = None
            except Exception as err:  # noqa: BLE001 - credentials must still be scrubbed best-effort
                logger.warning("Could not clear provider key: %s", err)
        if hasattr(provider, "_client"):
            try:
                provider._client = None
            except Exception as err:  # noqa: BLE001
                logger.warning("Could not clear provider client: %s", err)

    if active is not None and hasattr(active, "close"):
        try:
            active.close()
        except Exception as err:  # noqa: BLE001
            logger.warning("Could not close cloud provider: %s", err)
    st.session_state.active_cloud_provider = None


def append_chat_turn(turn: dict[str, Any]) -> None:
    """Append a message turn to chat history and enforce MAX_CHAT_TURNS memory bounding."""
    st.session_state.chat_history.append(turn)
    st.session_state.chat_history = bound_chat_history(
        st.session_state.chat_history,
        max_turns=MAX_CHAT_TURNS,
    )


# =====================================================================
# 1. SIDEBAR DOCUMENT MANAGER & INGESTION
# =====================================================================


def render_sidebar_documents(
    doc_store: DocStore,
    ai_model: AiModel,
    cache_dir: Path,
) -> None:
    """Render document uploader and active document list in the left sidebar."""
    st.sidebar.markdown(
        "<div style='font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; "
        "color: #9693A6; font-weight: 700; margin-top: 0.5rem; margin-bottom: 0.25rem;'>"
        "Documents</div>",
        unsafe_allow_html=True,
    )

    uploader_key = st.session_state.get("uploader_key", 0)
    uploaded_files = st.sidebar.file_uploader(
        "Upload PDFs",
        type=["pdf"],
        help=f"Max file size: {MAX_FILE_MB} MB. Processed on-device with OCR and layout parsing.",
        key=f"pdf_uploader_{uploader_key}",
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        with st.sidebar.status("Processing uploads…", expanded=True) as status_widget:
            ingestion_service = IngestionService(
                doc_store=doc_store,
                hybrid_retriever=st.session_state.get("hybrid_retriever"),
                local_embedding=st.session_state.get("local_embedding"),
                cache_dir=cache_dir,
            )

            new_docs_indexed = 0
            failures = []

            for f in uploaded_files:
                if hasattr(f, "size") and f.size and f.size > MAX_FILE_MB * 1024 * 1024:
                    failures.append(f"{f.name} exceeds {MAX_FILE_MB} MB cap")
                    continue

                raw_bytes = f.getvalue()
                active_prov = ai_model.provider if ai_model is not None else None
                vlm = active_prov if (active_prov and active_prov.get_capabilities().is_local) else None

                res = ingestion_service.ingest_pdf(
                    raw_bytes=raw_bytes,
                    filename=f.name,
                    vlm_provider=vlm,
                    progress_callback=lambda msg: status_widget.write(msg),
                )

                # Keep retriever and embedding bound to session
                st.session_state.local_embedding = ingestion_service.embedding
                st.session_state.hybrid_retriever = ingestion_service.retriever

                if res.success:
                    st.session_state.doc_ids.add(res.doc_id)
                    st.session_state.indexed_files.add(res.filename)
                    st.session_state.document_metadata[res.doc_id] = {
                        "doc_id": res.doc_id,
                        "filename": res.filename,
                        "sha256": res.sha256,
                        "upload_time": res.upload_time,
                        "pages": res.num_pages,
                        "chunks": res.num_chunks,
                    }
                    if not getattr(res, "already_indexed", False):
                        new_docs_indexed += 1
                else:
                    failures.append(f"{f.name}: {res.error}")
                    if res.doc_id:
                        st.session_state.failed_doc_ids.add(res.doc_id)

            # Rotate uploader_key to clear uploaded files from widget and prevent infinite rerun loop
            st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1

            if failures:
                status_widget.update(
                    label=f"Ingestion notice ({len(failures)} issue{'s' if len(failures) > 1 else ''})",
                    state="error",
                    expanded=True,
                )
                for fail_msg in failures:
                    st.sidebar.error(fail_msg)
            else:
                status_widget.update(
                    label=f"Ready! Indexed {new_docs_indexed} file(s)",
                    state="complete",
                    expanded=False,
                )

            if new_docs_indexed > 0:
                st.rerun()

    # Active Documents List in Sidebar
    if st.session_state.document_metadata:
        st.sidebar.markdown(
            f"<div style='font-size: 0.75rem; color: #70D9C2; font-weight: 600; margin-top: 0.5rem;'>"
            f"{len(st.session_state.indexed_files)} Active Document(s)</div>",
            unsafe_allow_html=True,
        )

        for doc_id, meta in list(st.session_state.document_metadata.items()):
            fname = meta.get("filename", doc_id)
            pages = meta.get("pages", 1)
            chunks = meta.get("chunks", 0)
            safe_name = html.escape(fname)

            col_doc, col_del = st.sidebar.columns([4, 1])
            with col_doc:
                doc_icon = get_svg_icon("document", size=13, color="#B9A3FF")
                st.markdown(
                    f"<div style='font-size: 0.8rem; font-weight: 500; color: #F5F3FF; overflow: hidden; "
                    f"text-overflow: ellipsis; white-space: nowrap;'>{doc_icon} {safe_name}</div>"
                    f"<div style='font-size: 0.7rem; color: #9693A6;'>{pages}p · {chunks} chunks</div>",
                    unsafe_allow_html=True,
                )
            with col_del:
                if st.button("×", key=f"del_sidebar_{doc_id}", help=f"Remove {fname}"):
                    st.session_state.pending_delete_doc_id = doc_id
                    st.session_state.pending_delete_filename = fname
                    st.rerun()

        pending_delete_id = st.session_state.get("pending_delete_doc_id")
        if pending_delete_id:
            pending_name = st.session_state.get("pending_delete_filename", pending_delete_id)
            st.sidebar.warning(
                f"Delete '{pending_name}'? Its text, visual evidence, vectors, summaries, and cache "
                "will be permanently removed."
            )
            confirm_col, cancel_col = st.sidebar.columns(2)
            with confirm_col:
                if st.button("Confirm delete", key="sidebar_confirm_delete", type="primary", use_container_width=True):
                    if _delete_document(doc_store, cache_dir, pending_delete_id, pending_name):
                        st.rerun()
            with cancel_col:
                if st.button("Cancel", key="sidebar_cancel_delete", use_container_width=True):
                    st.session_state.pop("pending_delete_doc_id", None)
                    st.session_state.pop("pending_delete_filename", None)
                    st.rerun()


# =====================================================================
# 2. CHAT VIEW (Conversational AI Chatbot Interface)
# =====================================================================


def render_chat_view(
    ai_model: AiModel,
    health: Any,
    caps: Any,
    doc_store: DocStore,
) -> None:
    """Render modern evidence-grounded chatbot workspace."""
    is_healthy = bool(health.status == "healthy")
    has_docs = bool(st.session_state.document_metadata or st.session_state.indexed_files)

    # Focus Filter Dropdown (All Documents vs specific file)
    doc_options = ["all"] + list(st.session_state.document_metadata.keys())

    def _doc_label(key: str) -> str:
        if key == "all":
            cnt = len(st.session_state.indexed_files)
            return f"All Documents ({cnt} file{'s' if cnt != 1 else ''})"
        meta = st.session_state.document_metadata.get(key, {})
        return f"{meta.get('filename', key)} (p. {meta.get('pages', 1)})"

    current_filter_idx = 0
    if "selected_chat_doc" in st.session_state and st.session_state.selected_chat_doc in doc_options:
        current_filter_idx = doc_options.index(st.session_state.selected_chat_doc)

    col_filter, col_actions = st.columns([4, 1.5])
    with col_filter:
        selected_filter = st.selectbox(
            "Focus Context",
            options=doc_options,
            format_func=_doc_label,
            index=current_filter_idx,
            label_visibility="collapsed",
            help="Filter responses across all uploaded PDFs or restrict to a single document.",
        )
        st.session_state.selected_chat_doc = selected_filter

    with col_actions:
        if st.button("New Chat", use_container_width=True, help="Clear active conversation"):
            st.session_state.chat_history = []
            st.rerun()

    # Empty State Hero when chat history is clean
    if not st.session_state.chat_history:
        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        brand_svg = get_brand_mark_svg(size=44)
        hero_html = (
            f'<div class="amoled-card" style="text-align: center; padding: 3rem 1.5rem; margin-bottom: 2rem;">'
            f'<div style="margin-bottom: 1rem;">{brand_svg}</div>'
            f'<div style="font-size: 1.35rem; font-weight: 700; color: #F5F3FF; margin-bottom: 0.5rem; letter-spacing: -0.02em;">'
            f"How can I help with your documents?</div>"
            f'<div style="font-size: 0.9rem; color: #9693A6; max-width: 520px; margin: 0 auto;">'
            f"Local-first multimodal intelligence. Ask questions, analyze figures, and verify findings "
            f"with page-grounded citations. Zero network egress.</div>"
            f"</div>"
        )
        if hasattr(st, "html"):
            st.html(hero_html)
        else:
            st.markdown(hero_html, unsafe_allow_html=True)

        if not has_docs:
            st.info("Upload one or more PDFs in the left sidebar to begin asking questions.")
        else:
            # Quick suggestion prompts
            st.markdown(
                "<div style='font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; "
                "color: #9693A6; font-weight: 700; margin-bottom: 0.5rem;'>Suggested Prompts</div>",
                unsafe_allow_html=True,
            )
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                if st.button("Summarize thesis", use_container_width=True):
                    st.session_state._queued_prompt = "Summarize the core thesis and key findings of the document."
                    st.rerun()
            with s2:
                if st.button("Extract key tables", use_container_width=True):
                    st.session_state._queued_prompt = (
                        "What are the key tables, numbers, and quantitative data reported?"
                    )
                    st.rerun()
            with s3:
                if st.button("Analyze methodology", use_container_width=True):
                    st.session_state._queued_prompt = "Explain the methodology and approach used in this document."
                    st.rerun()
            with s4:
                if st.button("Risks & limitations", use_container_width=True):
                    st.session_state._queued_prompt = "What risks, limitations, or open questions are noted?"
                    st.rerun()

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Conversation Stream
    for message in st.session_state.chat_history:
        role = message.get("role", "user")
        with st.chat_message(role):
            raw_content = message.get("content", "")
            allow_ext = bool(
                st.session_state.get("cloud_mode", False) and st.session_state.get("user_consented", False)
            )
            if role == "assistant" and message.get("rejected"):
                st.warning(
                    "Response withheld — grounding check failed. The draft did not cite retrieved evidence "
                    "with [E#], cited invalid evidence, or echoed a prompt-injection directive."
                )
                with st.expander("Rejected draft (not accepted as an answer)", expanded=False):
                    st.markdown(
                        sanitize_display_markdown(message.get("rejected_draft") or "", allow_external=allow_ext)
                    )
            else:
                st.markdown(sanitize_display_markdown(raw_content, allow_external=allow_ext))

            if role == "assistant":
                if message.get("is_cloud"):
                    cloud_m = message.get("model_name", "Cloud API")
                    st.caption(f"Generated via external cloud provider ({cloud_m}) with user consent.")
                else:
                    st.caption("Generated locally on-device (zero network egress).")

                v_data = message.get("verification")
                if v_data and not message.get("rejected"):
                    st.caption(verification_caption(v_data))

                notice = truncation_notice(message.get("truncation_warning"))
                if notice:
                    st.caption(notice)

                snippets = message.get("snippets", [])
                if snippets:
                    cited_ranks = set((v_data or {}).get("cited_ranks") or [])
                    if cited_ranks:
                        chips = [
                            render_citation_chip(
                                doc_id=s.get("doc_id", ""),
                                page=s.get("page", 1),
                                filename=s.get("filename", "doc"),
                                rank=s.get("rank"),
                            )
                            for s in snippets
                            if s.get("rank") in cited_ranks
                        ]
                        chip_html = " ".join(chips)
                        if hasattr(st, "html"):
                            st.html(chip_html)
                        else:
                            st.markdown(chip_html, unsafe_allow_html=True)
                        expander_label = "Cited Evidence & Source Context"
                    else:
                        expander_label = "Retrieved Candidate Context (Uncited)"

                    with st.expander(expander_label, expanded=False):
                        for s in snippets:
                            is_cited = s.get("rank") in cited_ranks
                            header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                            if is_cited:
                                header += " — *Cited in response*"
                            st.markdown(header)
                            snippet_text = sanitize_display_markdown(
                                s.get("content", "").strip(), allow_external=allow_ext
                            )
                            st.markdown(f"> {snippet_text}")
                            if s.get("bbox"):
                                bbox = s["bbox"]
                                st.caption(
                                    f"Region: x0={bbox.get('x0', 0.0):.1f}, y0={bbox.get('y0', 0.0):.1f}, "
                                    f"x1={bbox.get('x1', 0.0):.1f}, y1={bbox.get('y1', 0.0):.1f}"
                                )
                            st.divider()

    # Chat Input Box
    input_placeholder = (
        "Ask a question about your documents… (Press Enter)"
        if is_healthy
        else "Inference backend is offline. Start llama-server or configure Cloud in Settings."
    )
    user_prompt = st.chat_input(
        placeholder=input_placeholder,
        disabled=(not has_docs or not is_healthy),
    )

    # Handle queued suggestion prompt or user input
    effective_prompt = user_prompt or st.session_state.pop("_queued_prompt", None)

    if effective_prompt:
        if not is_healthy:
            st.error(f"Inference engine unavailable: {health.message}")
            return

        append_chat_turn({"role": "user", "content": effective_prompt})
        with st.chat_message("user"):
            st.markdown(effective_prompt)

        history_to_pass = st.session_state.chat_history[:-1][-10:]
        # Single shared follow-up heuristic (no drift with AiModel's internal path).
        search_query = contextualize_query(effective_prompt, history_to_pass)

        # Target document: explicit filter or auto-detected from query
        doc_filter = None if selected_filter == "all" else selected_filter
        if doc_filter is None and st.session_state.get("document_metadata"):
            prompt_lower = effective_prompt.lower()
            for did, meta in st.session_state.document_metadata.items():
                fn = meta.get("filename", "").lower()
                stem = Path(fn).stem.lower()
                if fn in prompt_lower or (len(stem) >= 3 and stem in prompt_lower):
                    doc_filter = did
                    break

        sources: list[str] = []
        retrieval_res = None
        active_retriever = st.session_state.get("hybrid_retriever") or st.session_state.local_embedding

        # Whole-document inventory questions need an explicit document scope. When the
        # filter is "all" but only one document is indexed, that scope is unambiguous.
        retrieval_scope = doc_filter
        if retrieval_scope is None and len(st.session_state.document_metadata) == 1:
            retrieval_scope = next(iter(st.session_state.document_metadata))

        if active_retriever is not None:
            if hasattr(active_retriever, "search_hybrid"):
                retrieval_res = resolve_retrieval(
                    active_retriever,
                    search_query,
                    doc_id=retrieval_scope,
                    k=8,
                    max_context_chars=whole_document_char_budget(caps.context_window),
                )
                sources = retrieval_res.source_labels()
            else:
                results = active_retriever.search(search_query, k=10)
                seen_sources = set()
                for doc, _ in results:
                    fn = doc.get("filename")
                    if fn and fn not in seen_sources:
                        seen_sources.add(fn)
                        sources.append(fn)

        snippets_data = (
            [s.model_dump() for s in retrieval_res.snippets] if retrieval_res and retrieval_res.snippets else []
        )

        with st.chat_message("assistant"):
            try:
                response_stream = ai_model.ask_a_question_from_pdf_stream(
                    pdf_path="",
                    prompt=effective_prompt,
                    local_embedding=active_retriever,
                    chat_history=history_to_pass,
                    retrieval_result=retrieval_res,
                    doc_id=doc_filter,
                )
                # Buffer the stream so an ungrounded draft is never left on screen
                # as if it were an accepted answer.
                stream_placeholder = st.empty()
                response_chunks: list[str] = []
                for token in response_stream:
                    response_chunks.append(token)
                    stream_placeholder.markdown("".join(response_chunks) + "▌")
                full_response = "".join(response_chunks)
                stream_placeholder.markdown(full_response)

                verification = ai_model.validate_response(full_response, retrieval_res)
                withheld = should_withhold_answer(verification)

                if withheld:
                    stream_placeholder.empty()
                    st.warning(
                        "Response withheld — grounding check failed. The draft did not cite retrieved "
                        "evidence with [E#], cited invalid evidence, or echoed a prompt-injection directive."
                    )
                    with st.expander("Rejected draft (not accepted as an answer)", expanded=False):
                        st.markdown(sanitize_display_markdown(full_response))
                else:
                    st.caption(verification_caption(verification.model_dump()))

                truncation_warning = dict(getattr(ai_model, "last_truncation_warning", {}) or {})
                notice = truncation_notice(truncation_warning)
                if notice:
                    st.caption(notice)

                if not caps.is_local:
                    st.caption(f"Generated via external cloud provider ({caps.model_name}) with user consent.")
                else:
                    st.caption("Generated locally on-device (zero network egress).")

                if snippets_data:
                    cited_ranks = set(verification.cited_ranks or [])
                    if cited_ranks:
                        chips = [
                            render_citation_chip(
                                doc_id=s.get("doc_id", ""),
                                page=s.get("page", 1),
                                filename=s.get("filename", "doc"),
                                rank=s.get("rank"),
                            )
                            for s in snippets_data
                            if s.get("rank") in cited_ranks
                        ]
                        chip_html = " ".join(chips)
                        if hasattr(st, "html"):
                            st.html(chip_html)
                        else:
                            st.markdown(chip_html, unsafe_allow_html=True)
                        expander_label = "Cited Evidence & Source Context"
                    else:
                        st.caption("No retrieved candidate was cited by the answer.")
                        expander_label = "Retrieved Candidate Context (Uncited)"

                    with st.expander(expander_label, expanded=False):
                        for s in snippets_data:
                            is_cited = s.get("rank") in cited_ranks
                            header = (
                                f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                                + (" — *Cited in response*" if is_cited else "")
                            )
                            st.markdown(header)
                            snippet_text = sanitize_display_markdown(s.get("content", "").strip())
                            st.markdown(f"> {snippet_text}")
                            st.divider()

                append_chat_turn(
                    {
                        "role": "assistant",
                        # Withheld drafts must not re-enter model history as if accepted.
                        "content": "[Response withheld: grounding check failed.]" if withheld else full_response,
                        "rejected": withheld,
                        "rejected_draft": full_response if withheld else None,
                        "sources": list(sources),
                        "verification": verification.model_dump(),
                        "snippets": snippets_data,
                        "truncation_warning": truncation_warning,
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
                        "rejected": False,
                        "sources": list(sources),
                        "verification": None,
                        "snippets": snippets_data,
                        "truncation_warning": dict(getattr(ai_model, "last_truncation_warning", {}) or {}),
                        "is_cloud": not caps.is_local,
                        "model_name": caps.model_name,
                    }
                )


# =====================================================================
# 3. SUMMARIZER VIEW
# =====================================================================


def render_summarizer_view(
    doc_store: DocStore,
    ai_model: AiModel,
    is_healthy: bool,
) -> None:
    """Render multi-profile document summarization workspace with export actions."""
    st.markdown("## Document Summarizer")
    st.caption("Synthesize documents across 5 analytical profiles with page references and markdown export.")

    if not st.session_state.document_metadata and not st.session_state.indexed_files:
        render_empty_state("No documents available", "Upload a PDF in the sidebar to generate structured summaries.")
        return

    doc_options = list(st.session_state.document_metadata.keys())
    selected_doc_id = st.selectbox(
        "Select Document",
        options=doc_options,
        format_func=lambda k: f"{st.session_state.document_metadata[k].get('filename', k)} ({k})",
        index=0
        if "selected_summary_doc" not in st.session_state or st.session_state.selected_summary_doc not in doc_options
        else doc_options.index(st.session_state.selected_summary_doc),
    )
    file_meta = st.session_state.document_metadata.get(selected_doc_id, {})
    selected_sha = file_meta.get("sha256", "")
    if not selected_sha and selected_doc_id:
        doc_rec = doc_store.get_document(selected_doc_id)
        if doc_rec:
            selected_sha = doc_rec.sha256

    profile_map = {
        "overview": "Overview — Executive synthesis & core thesis",
        "detailed": "Detailed — Comprehensive section-by-section breakdown",
        "study_notes": "Study Notes — Pedagogical takeaways & key concepts",
        "tables_figures": "Tables & Figures — Structured data & visual synthesis",
        "findings": "Findings — Strategic discoveries, risks & recommendations",
    }

    selected_profile = st.radio(
        "Analytical Profile",
        options=list(profile_map.keys()),
        format_func=lambda p: profile_map[p],
        index=0,
    )

    col_btn, col_force = st.columns([1, 2])
    with col_btn:
        generate_summary_btn = st.button(
            "Generate Summary",
            type="primary",
            disabled=not is_healthy,
            use_container_width=True,
        )
    with col_force:
        force_refresh_summary = st.checkbox("Force re-generate (bypass cache)", value=False)

    # The session layer must use the same version-aware key as the SQLite cache,
    # otherwise a summary generated by the previous provider is shown as current.
    active_model_version = f"{ai_model.model_name}:{CONFIG_VERSION}"

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
                store_session_summary(
                    selected_doc_id,
                    selected_profile,
                    active_model_version,
                    summary_obj.model_dump(),
                )
                sum_status.update(label="Summary generated successfully!", state="complete", expanded=False)
            except Exception as sum_err:
                sum_status.update(label="Summary generation failed", state="error", expanded=True)
                st.error(f"Summarization error: {sum_err}")

    # Check for summary to display with exact model version + config verification (P1 audit)
    active_summary = get_session_summary(selected_doc_id, selected_profile, active_model_version)
    if not active_summary and selected_sha:
        # Never fall back to a version-agnostic lookup here: that would resurrect a
        # summary generated by a different model/config after invalidation.
        cached_summ = doc_store.get_summary(selected_sha, selected_profile, model_version=active_model_version)
        if cached_summ:
            active_summary = cached_summ.model_dump()

    if active_summary:
        st.divider()
        col_tag, col_dl = st.columns([3, 1])
        with col_tag:
            if active_summary.get("cached"):
                st.caption("Loaded from persistent SQLite cache")
            else:
                st.caption(f"Generated fresh with {active_summary.get('model_version', 'model')}")
        with col_dl:
            st.download_button(
                "Export Markdown",
                data=active_summary.get("summary_text", ""),
                file_name=f"{file_meta.get('filename', 'summary')}_{selected_profile}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        allow_ext = bool(st.session_state.get("cloud_mode", False) and st.session_state.get("user_consented", False))
        st.markdown(sanitize_display_markdown(active_summary.get("summary_text", ""), allow_external=allow_ext))

        p_refs = active_summary.get("page_references", [])
        if p_refs:
            with st.expander("Referenced Source Pages", expanded=False):
                st.markdown(f"**Source pages cited:** {', '.join(f'Page {p}' for p in p_refs)}")
                st.caption(f"Generated at: {active_summary.get('created_at', '')}")


# =====================================================================
# 4. DOCUMENT LIBRARY VIEW
# =====================================================================


def render_library_view(
    doc_store: DocStore,
    hybrid_retriever: HybridRetriever | None,
    cache_dir: Path | None = None,
) -> None:
    """Render document lifecycle manager: search, inspect, retry, re-index, and delete."""
    cache_dir = cache_dir or (Path(__file__).resolve().parent.parent / ".cache")
    st.markdown("## Document Library")
    st.caption("Inspect stored documents, verify chunk counts, or delete files from local storage.")

    all_docs = doc_store.list_documents()

    if not all_docs:
        render_empty_state("No documents in database", "Upload a PDF in the sidebar to populate your library.")
        return

    search_q = st.text_input("Filter documents by filename or ID", placeholder="Search filename...")

    filtered_docs = all_docs
    if search_q.strip():
        q_lower = search_q.strip().lower()
        filtered_docs = [d for d in all_docs if q_lower in d.filename.lower() or q_lower in d.doc_id.lower()]

    st.markdown(f"**{len(filtered_docs)}** document(s) found")

    for doc in filtered_docs:
        c_info, c_action = st.columns([3, 1.5])
        with c_info:
            upload_dt = doc.upload_time[:19].replace("T", " ") if doc.upload_time else "Unknown"
            status_variant = "local" if doc.status == "indexed" else ("error" if doc.status == "failed" else "warning")
            safe_fname = html.escape(doc.filename)
            card_html = (
                f'<div class="amoled-card" style="margin-bottom: 0.5rem;">'
                f'<div style="display: flex; justify-content: space-between; align-items: center;">'
                f'<span style="font-weight: 600; color: #F5F3FF; font-size: 1rem;">{safe_fname}</span>'
                f"{render_status_pill(doc.status.title(), variant=status_variant)}</div>"
                f'<div style="font-size: 0.8rem; color: #9693A6; margin-top: 0.4rem;">'
                f"<code>{doc.doc_id}</code> · {doc.num_pages} pages · {doc.num_chunks} chunks · {doc.size_bytes / 1024:.1f} KB</div>"
                f'<div style="font-size: 0.75rem; color: #9693A6; margin-top: 0.2rem;">'
                f"Uploaded: {upload_dt} · SHA-256: <code>{doc.sha256[:16]}...</code></div>"
                f"</div>"
            )
            if hasattr(st, "html"):
                st.html(card_html)
            else:
                st.markdown(card_html, unsafe_allow_html=True)

        with c_action:
            col_open, col_reidx, col_del = st.columns([1, 1, 1])
            with col_open:
                if st.button("Chat", key=f"lib_open_{doc.doc_id}", use_container_width=True):
                    st.session_state.selected_chat_doc = doc.doc_id
                    st.session_state.active_workspace = "Chat"
                    st.rerun()
            with col_reidx:
                if st.button(
                    "Re-index",
                    key=f"lib_reidx_{doc.doc_id}",
                    help="Rebuild vector embeddings in LanceDB",
                    use_container_width=True,
                ):
                    if _reindex_document(
                        doc_store,
                        cache_dir,
                        doc.doc_id,
                        doc.filename,
                        retriever=hybrid_retriever,
                    ):
                        if doc.doc_id in st.session_state.document_metadata:
                            st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = False
                        st.rerun()
            with col_del:
                if st.button("Delete", key=f"lib_del_{doc.doc_id}", type="secondary", use_container_width=True):
                    st.session_state.pending_delete_doc_id = doc.doc_id
                    st.session_state.pending_delete_filename = doc.filename
                    st.rerun()

        if st.session_state.get("pending_delete_doc_id") == doc.doc_id:
            st.warning(
                f"Delete '{doc.filename}'? Its text, visual evidence, vectors, summaries, and cache "
                "will be permanently removed. This cannot be undone."
            )
            confirm_col, cancel_col = st.columns([1, 1])
            with confirm_col:
                if st.button(
                    "Confirm delete",
                    key=f"lib_confirm_del_{doc.doc_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    if _delete_document(
                        doc_store,
                        cache_dir,
                        doc.doc_id,
                        doc.filename,
                        retriever=hybrid_retriever,
                    ):
                        st.rerun()
            with cancel_col:
                if st.button("Cancel", key=f"lib_cancel_del_{doc.doc_id}", use_container_width=True):
                    st.session_state.pop("pending_delete_doc_id", None)
                    st.session_state.pop("pending_delete_filename", None)
                    st.rerun()

    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)
    st.markdown("### Danger Zone")
    with st.expander("Delete All Stored Data", expanded=False):
        st.warning(
            "This will permanently delete all indexed documents, SQLite rows, LanceDB vector tables, disk caches, and chat transcript. "
            "This operation cannot be undone."
        )
        confirm_purge = st.checkbox("I understand that this will erase all stored documents and vectors.")
        if st.button("Purge All Data Now", type="primary", disabled=not confirm_purge):
            if _purge_all(doc_store, cache_dir, retriever=hybrid_retriever):
                st.rerun()


# =====================================================================
# 5. SETTINGS AND DIAGNOSTICS VIEW
# =====================================================================


def render_settings_view(
    ai_model: AiModel,
    health: Any,
    caps: Any,
    doc_store: DocStore,
    cache_dir: Path,
) -> None:
    """Render system settings, cloud consent controls, and hardware telemetry."""
    st.markdown("## Settings & Diagnostics")
    st.caption("Telemetry, model configurations, and local privacy guarantees.")

    st.markdown("### Privacy & Inference Mode")

    # Synchronize widget toggle state with actual consented cloud_mode
    if not st.session_state.cloud_mode and not st.session_state.get("_show_consent_dialog", False):
        if st.session_state.get("settings_cloud_toggle", False):
            st.session_state.settings_cloud_toggle = False

    col_toggle, col_status = st.columns([2, 1])
    with col_toggle:
        cloud_active = st.toggle(
            "Enable Cloud Inference",
            value=st.session_state.cloud_mode,
            key="settings_cloud_toggle",
            help="Route queries through cloud model providers (Groq, OpenAI, Anthropic).",
        )
        if cloud_active != st.session_state.cloud_mode:
            if cloud_active and not st.session_state.user_consented:
                st.session_state._show_consent_dialog = True
            else:
                st.session_state.cloud_mode = cloud_active
                st.session_state.cloud_mode_toggle = cloud_active
                if not cloud_active:
                    st.session_state.user_consented = False
                # Summaries are model-specific: never show a previous model's output.
                clear_summary_session_cache()
            st.rerun()

    with col_status:
        if st.session_state.cloud_mode and st.session_state.user_consented:
            status_badge = render_status_pill("Cloud Active", variant="cloud")
        else:
            status_badge = render_status_pill("100% Local", variant="local")
        if hasattr(st, "html"):
            st.html(status_badge)
        else:
            st.markdown(status_badge, unsafe_allow_html=True)

    if st.session_state.cloud_mode and st.session_state.user_consented:
        cloud_info_html = (
            '<div class="amoled-card-elevated" style="border-left: 3px solid #B9A3FF;">'
            '<div style="font-weight: 600; color: #B9A3FF;">Cloud Egress Permitted</div>'
            '<div style="font-size: 0.85rem; color: #9693A6; margin-top: 0.25rem;">'
            "Prompts and retrieved text excerpts are transmitted to your selected cloud API. "
            "Original PDF files and dense embeddings remain local on disk.</div></div>"
        )
        if hasattr(st, "html"):
            st.html(cloud_info_html)
        else:
            st.markdown(cloud_info_html, unsafe_allow_html=True)

        PROVIDER_CONFIG = {
            "groq": ("Groq (Llama 3.3 70B)", "groq/llama-3.3-70b-versatile", "GROQ_API_KEY"),
            "openai": ("OpenAI (GPT-4o mini)", "openai/gpt-4o-mini", "OPENAI_API_KEY"),
            "anthropic": ("Anthropic (Claude 3.5 Haiku)", "anthropic/claude-3-5-haiku-20241022", "ANTHROPIC_API_KEY"),
        }

        selected_prov = st.selectbox(
            "Cloud Provider",
            options=list(PROVIDER_CONFIG.keys()),
            format_func=lambda k: PROVIDER_CONFIG[k][0],
            index=list(PROVIDER_CONFIG.keys()).index(st.session_state.cloud_provider)
            if st.session_state.cloud_provider in PROVIDER_CONFIG
            else 0,
        )

        if selected_prov != st.session_state.cloud_provider:
            st.session_state.cloud_provider = selected_prov
            st.session_state.cloud_model = PROVIDER_CONFIG[selected_prov][1]
            clear_summary_session_cache()
            st.rerun()

        # API Key entry for cloud providers
        current_api_key = st.session_state.cloud_api_keys.get(selected_prov, "")
        env_var_name = PROVIDER_CONFIG[selected_prov][2]
        api_key_input = st.text_input(
            f"API Key for {PROVIDER_CONFIG[selected_prov][0]} (Optional if set in {env_var_name})",
            value=current_api_key,
            type="password",
            placeholder=f"Paste {env_var_name} here (kept in session memory only)",
        )
        if api_key_input != current_api_key:
            st.session_state.cloud_api_keys[selected_prov] = api_key_input
            st.rerun()

        if st.button("Revoke Consent (Switch back to 100% Local)", use_container_width=True):
            st.session_state.cloud_mode = False
            st.session_state.cloud_mode_toggle = False
            st.session_state.user_consented = False
            clear_summary_session_cache()
            st.rerun()

    with st.expander("Cloud Credentials", expanded=False):
        st.caption(
            "Cloud API keys are kept in this browser session only. Clearing them removes the keys "
            "from session state and the active provider objects."
        )
        if st.button("Clear cloud keys", use_container_width=True):
            clear_cloud_credentials(ai_model)
            st.toast("Cloud API keys cleared from session state.")
            st.rerun()

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # Hardware & VRAM Telemetry
    st.markdown("### Hardware & Telemetry")
    gpu_info = get_gpu_memory_info()
    proc_info = get_process_memory_info()

    g1, g2, g3 = st.columns(3)
    with g1:
        if gpu_info is not None:
            v_used = gpu_info["used_mb"]
            v_tot = gpu_info["total_mb"]
            render_stat_card("GPU VRAM", f"{v_used:.0f} MB", subtext=f"Total: {v_tot:.0f} MB", icon_name="gpu")
        else:
            render_stat_card("GPU VRAM", "CPU Mode", subtext="No NVIDIA GPU", icon_name="gpu")
    with g2:
        render_stat_card("Process RAM", f"{proc_info['rss_mb']:.0f} MB", subtext="Resident Set Size", icon_name="ram")
    with g3:
        total_d = doc_store.count_documents()
        total_s = doc_store.count_summaries()
        render_stat_card(
            "Store Records", f"{total_d} docs", subtext=f"{total_s} cached summaries", icon_name="database"
        )

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # Storage paths and session management
    st.markdown("### Storage & Session")
    st.markdown(
        """
        - **SQLite Store:** `data/documents.db`
        - **LanceDB Vector URI:** `data/lancedb/`
        - **Disk Cache Directory:** `.cache/`
        """
    )

    col_cs, col_cl = st.columns(2)
    with col_cs:
        if st.button("Reset In-Memory Session", use_container_width=True):
            reset_in_memory_session()
            st.toast("In-memory session state cleared.")
            st.rerun()
    with col_cl:
        if st.button("Clear Disk Cache (.cache/)", use_container_width=True):
            if cache_dir.exists():
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    st.toast("Disk cache cleared.")
                except Exception as e:
                    st.error(f"Error clearing cache: {e}")
            st.rerun()
