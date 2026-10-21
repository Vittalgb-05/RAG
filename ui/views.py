"""Modular view renderers for the AMOLED chatbot-first document workspace."""

import html
import logging
from pathlib import Path
import shutil
from typing import Any

import streamlit as st

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from core.local_llm import AiModel
from core.models import CONFIG_VERSION
from core.prompt_budget import bound_chat_history
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
from ingestion.upload_validation import MAX_FILE_MB

logger = logging.getLogger(__name__)

MAX_CHAT_TURNS = 50


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
                    lifecycle = LifecycleService(
                        doc_store=doc_store,
                        hybrid_retriever=st.session_state.get("hybrid_retriever"),
                        local_embedding=st.session_state.get("local_embedding"),
                        cache_dir=cache_dir,
                    )
                    lifecycle.delete_document(doc_id, session_state=st.session_state)
                    st.toast(f"Removed {fname}")
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
            st.markdown(sanitize_display_markdown(raw_content, allow_external=allow_ext))

            if role == "assistant":
                if message.get("is_cloud"):
                    cloud_m = message.get("model_name", "Cloud API")
                    st.caption(f"Generated via external cloud provider ({cloud_m}) with user consent.")
                else:
                    st.caption("Generated locally on-device (zero network egress).")

                v_data = message.get("verification")
                if v_data:
                    if v_data.get("abstention_detected"):
                        st.caption("Explicit abstention — no document evidence found.")
                    elif v_data.get("total_citations", 0) == 0:
                        st.caption("Ungrounded response — no evidence citations ([E#]) were included in the answer.")
                    elif v_data.get("is_valid"):
                        precision = v_data.get("precision", 1.0)
                        st.caption(f"Verified Grounding ({precision:.0%} citation precision)")
                    else:
                        precision = v_data.get("precision", 0.0)
                        st.caption(f"Unverified Citations ({precision:.0%} citation precision)")

                snippets = message.get("snippets", [])
                if snippets:
                    chips = [
                        render_citation_chip(
                            doc_id=s.get("doc_id", ""),
                            page=s.get("page", 1),
                            filename=s.get("filename", "doc"),
                            rank=s.get("rank"),
                        )
                        for s in snippets
                    ]
                    chip_html = " ".join(chips)
                    if hasattr(st, "html"):
                        st.html(chip_html)
                    else:
                        st.markdown(chip_html, unsafe_allow_html=True)

                    with st.expander("Cited Evidence & Source Context", expanded=False):
                        for s in snippets:
                            header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
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
        search_query = effective_prompt
        # Contextualize search query ONLY if current prompt is an ambiguous short follow-up
        tokens = effective_prompt.strip().lower().split()
        is_short_followup = len(tokens) <= 4 and any(
            t in {"it", "that", "this", "these", "those", "they", "them", "why", "how", "more", "elaborate", "details"}
            for t in tokens
        )
        if is_short_followup and history_to_pass:
            last_user_msgs = [
                m["content"]
                for m in history_to_pass
                if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)
            ]
            if last_user_msgs:
                search_query = f"{last_user_msgs[-1]} {effective_prompt}"

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

        if active_retriever is not None:
            if hasattr(active_retriever, "search_hybrid"):
                retrieval_res = active_retriever.search_hybrid(search_query, k=8, doc_id=doc_filter)
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
                )
                full_response = st.write_stream(response_stream)

                if not caps.is_local:
                    st.caption(f"Generated via external cloud provider ({caps.model_name}) with user consent.")
                else:
                    st.caption("Generated locally on-device (zero network egress).")

                verification = ai_model.validate_response(full_response, retrieval_res)
                if verification.abstention_detected:
                    st.caption("Explicit abstention — no document evidence found.")
                elif verification.total_citations == 0:
                    st.caption("Ungrounded response — no evidence citations ([E#]) were included in the answer.")
                elif verification.is_valid:
                    precision = verification.precision
                    st.caption(f"Verified Grounding ({precision:.0%} citation precision)")
                else:
                    precision = verification.precision
                    st.caption(f"Unverified Citations ({precision:.0%} citation precision)")

                if snippets_data:
                    cited_ranks = set(verification.cited_ranks) if verification.cited_ranks else set()
                    chips = [
                        render_citation_chip(
                            doc_id=s.get("doc_id", ""),
                            page=s.get("page", 1),
                            filename=s.get("filename", "doc"),
                            rank=s.get("rank"),
                        )
                        for s in snippets_data
                        if (not cited_ranks or s.get("rank") in cited_ranks)
                    ]
                    chip_html = " ".join(chips)
                    if hasattr(st, "html"):
                        st.html(chip_html)
                    else:
                        st.markdown(chip_html, unsafe_allow_html=True)

                    expander_label = (
                        "Cited Evidence & Source Context" if cited_ranks else "Retrieved Candidate Context (Uncited)"
                    )
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

    # Check for summary to display with exact model version + config verification (P1 audit)
    active_summary = st.session_state.get(summary_cache_key)
    if not active_summary and selected_sha:
        expected_version = f"{ai_model.model_name}:{CONFIG_VERSION}"
        cached_summ = doc_store.get_summary(selected_sha, selected_profile, model_version=expected_version)
        if not cached_summ:
            cached_summ = doc_store.get_summary(selected_sha, selected_profile)
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
                    lifecycle = LifecycleService(
                        doc_store=doc_store,
                        hybrid_retriever=hybrid_retriever,
                        local_embedding=st.session_state.get("local_embedding"),
                        cache_dir=cache_dir,
                    )
                    if lifecycle.reindex_document(doc.doc_id):
                        if doc.doc_id in st.session_state.document_metadata:
                            st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = False
                        st.toast(f"Reindexed {doc.filename}")
                    else:
                        st.error(f"Could not reindex {doc.filename}")
                    st.rerun()
            with col_del:
                if st.button("Delete", key=f"lib_del_{doc.doc_id}", type="secondary", use_container_width=True):
                    lifecycle = LifecycleService(
                        doc_store=doc_store,
                        hybrid_retriever=hybrid_retriever,
                        local_embedding=st.session_state.get("local_embedding"),
                        cache_dir=cache_dir,
                    )
                    lifecycle.delete_document(doc.doc_id, session_state=st.session_state)
                    st.toast(f"Deleted {doc.filename}")
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
            lifecycle = LifecycleService(
                doc_store=doc_store,
                hybrid_retriever=hybrid_retriever,
                local_embedding=st.session_state.get("local_embedding"),
                cache_dir=cache_dir,
            )
            lifecycle.purge_all(session_state=st.session_state)
            st.toast("Purged all local database records, vector tables, and cache files.")
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
            st.session_state.chat_history = []
            st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
            st.session_state.failed_doc_ids = set()
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
