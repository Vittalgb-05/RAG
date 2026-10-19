"""Modular view renderers for the AMOLED document workspace."""

import datetime
import io
import json
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

import streamlit as st

from doc_store import DocStore
from docling_reader import DoclingReader
from hybrid_retriever import HybridRetriever
from local_embedding import LocalEmbedding
from local_llm import AiModel
from models import Chunk, Document, EvidenceElement, Page, cache_dir_for
from ocr_fallback import apply_conditional_ocr
from prompt_budget import bound_chat_history
from resource_telemetry import get_gpu_memory_info, get_process_memory_info
from summarizer import Summarizer
from ui.components import (
    get_svg_icon,
    render_citation_chip,
    render_empty_state,
    render_stat_card,
    render_status_pill,
)
from ui.sanitizer import sanitize_display_markdown
from upload_validation import MAX_FILE_MB, validate_pdf_bytes
from visual_analyzer import VisualAnalyzer

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
# 1. WORKSPACE VIEW (Landing / Upload / Metrics / Recent Documents)
# =====================================================================


def render_workspace_view(
    doc_store: DocStore,
    ai_model: AiModel,
    health: Any,
    caps: Any,
    cache_dir: Path,
) -> None:
    """Render landing workspace with prominent upload surface and document statistics."""
    st.markdown("# Your documents, understood.")
    st.markdown(
        "<p style='color: #9693A6; font-size: 1.05rem; margin-top: -0.5rem; margin-bottom: 1.5rem;'>"
        "Search, summarize and explore your PDFs. Your documents stay on this device."
        "</p>",
        unsafe_allow_html=True,
    )

    # Telemetry metrics row
    c1, c2, c3 = st.columns(3)
    num_docs = len(st.session_state.indexed_files)
    num_chunks = sum(meta.get("chunks", 0) for meta in st.session_state.document_metadata.values())
    mode_label = "Cloud" if (st.session_state.cloud_mode and st.session_state.user_consented) else "Local"
    mode_subtext = "Zero network egress" if mode_label == "Local" else caps.model_name

    with c1:
        render_stat_card("Documents", num_docs, subtext="Persistent library", icon_name="document")
    with c2:
        render_stat_card("Indexed Chunks", num_chunks, subtext="Hybrid LanceDB + FTS", icon_name="search")
    with c3:
        render_stat_card("Inference Mode", mode_label, subtext=mode_subtext, icon_name="check")

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # Prominent Drag and Drop Upload Card
    st.markdown("### Add documents")
    st.caption("PDF · Local processing · Persistent library")

    uploader_key = st.session_state.get("uploader_key", 0)
    uploaded_files = st.file_uploader(
        "Drop your PDFs here or browse files from your device",
        type=["pdf"],
        help=f"Maximum file size: {MAX_FILE_MB} MB. Pages processed locally with OCR and visual parsing.",
        key=f"pdf_uploader_{uploader_key}",
        accept_multiple_files=True,
    )

    if uploaded_files:
        with st.status("Processing documents…", expanded=True) as doc_status:
            new_pdf_uploaded = False

            for uploaded_file in uploaded_files:
                filename = uploaded_file.name

                if (
                    hasattr(uploaded_file, "size")
                    and uploaded_file.size is not None
                    and uploaded_file.size > MAX_FILE_MB * 1024 * 1024
                ):
                    st.error(
                        f"File too large ({uploaded_file.size / (1024 * 1024):.1f} MB > {MAX_FILE_MB} MB) — `{filename}`."
                    )
                    continue

                raw_bytes = uploaded_file.getvalue()
                st.write(f"Validating `{filename}`…")
                try:
                    validated = validate_pdf_bytes(raw_bytes, filename)
                except ValueError as e:
                    st.error(str(e))
                    continue

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
                    continue

                if doc_id in st.session_state.failed_doc_ids:
                    st.error(f"Processing previously failed for `{filename}`. Reset session or delete to retry.")
                    continue

                # 4. Text extraction
                st.write(f"Extracting text & layout from `{filename}`…")
                paragraphs: list[dict[str, Any]] = []
                page_records: list[Page] = []
                evidence_elements: list[EvidenceElement] = []
                sha12 = validated.sha256[:12]

                try:
                    pdf_stream = io.BytesIO(raw_bytes)
                    docling_reader = DoclingReader(pdf_stream, filename=filename)
                    docling_reader.extract_text(doc_id=doc_id, sha12=sha12)
                    paragraphs = docling_reader.get_paragraphs()
                    page_records = docling_reader.get_page_records()

                    if getattr(docling_reader, "fallback_used", False):
                        st.warning(
                            f"Extraction fallback triggered for `{filename}`: Docling unavailable or failed; "
                            "fell back to basic parser. Table structure and reading order may be degraded."
                        )

                    # 4b. Conditional RapidOCR fallback
                    page_records, paragraphs = apply_conditional_ocr(
                        pdf_bytes=raw_bytes,
                        page_records=page_records,
                        existing_chunks=paragraphs,
                        doc_id=doc_id,
                        sha12=sha12,
                        filename=filename,
                    )

                    # 4c. Visual element detection & VLM analysis (GPU serialized via InferenceGate)
                    visual_analyzer = VisualAnalyzer()
                    active_provider = ai_model.provider if ai_model is not None else None
                    local_vlm_provider = (
                        active_provider
                        if (active_provider is not None and active_provider.get_capabilities().is_local)
                        else None
                    )

                    detected_regions = visual_analyzer.detect_visual_regions(raw_bytes)
                    if (
                        detected_regions
                        and local_vlm_provider is not None
                        and local_vlm_provider.get_capabilities().supports_vision
                    ):
                        with st.status(
                            f"Analyzing visual elements in `{filename}` on GPU...",
                            expanded=False,
                        ) as vision_status:

                            def _vision_progress(cur: int, tot: int, desc: str) -> None:
                                if vision_status:
                                    vision_status.update(label=f"Analyzing visual elements: {cur}/{tot} ({desc})...")

                            evidence_elements = visual_analyzer.analyze_visual_elements(
                                pdf_bytes=raw_bytes,
                                doc_id=doc_id,
                                provider=local_vlm_provider,
                                progress_callback=_vision_progress,
                            )
                            if vision_status:
                                vision_status.update(
                                    label=f"Visual analysis complete ({len(evidence_elements)} elements)",
                                    state="complete",
                                    expanded=False,
                                )
                    else:
                        evidence_elements = visual_analyzer.analyze_visual_elements(
                            pdf_bytes=raw_bytes,
                            doc_id=doc_id,
                            provider=local_vlm_provider,
                        )

                except Exception as err:
                    st.error(f"Could not extract text from `{filename}` ({err})")
                    st.session_state.failed_doc_ids.add(doc_id)
                    continue

                # 5. Persist Document and Pages atomically
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
                    pass

                if evidence_elements:
                    try:
                        doc_store.record_evidence_elements(evidence_elements)
                    except Exception as ev_err:
                        logger.warning("Failed to record evidence elements: %s", ev_err)

                # Batch write page records in single transaction
                doc_store.record_pages_batch(page_records)

                # 6. Index into LanceDB
                st.write(f"Building index for `{filename}` ({len(paragraphs)} chunks)…")
                if st.session_state.local_embedding is None:
                    st.session_state.local_embedding = LocalEmbedding()

                if st.session_state.hybrid_retriever is None:
                    st.session_state.hybrid_retriever = HybridRetriever(
                        embedding_fn=st.session_state.local_embedding._embed_one
                    )

                embeddings = st.session_state.local_embedding.get_embeddings([p["content"] for p in paragraphs])
                st.session_state.hybrid_retriever.index_chunks(paragraphs, embeddings=embeddings.tolist())

                # 7. Record chunks in SQLite
                chunk_models = [Chunk.model_validate(p) for p in paragraphs]
                doc_store.record_chunks(chunk_models)

                # 8. Best-effort disk cache write
                try:
                    c_dir = cache_dir_for(cache_dir, validated.sha256)
                    c_dir.mkdir(parents=True, exist_ok=True)
                    with open(c_dir / "pages.json", "w", encoding="utf-8") as f:
                        json.dump([p.model_dump() for p in page_records], f, indent=2)
                    with open(c_dir / "chunks.json", "w", encoding="utf-8") as f:
                        json.dump(paragraphs, f, indent=2)
                    with open(c_dir / "manifest.json", "w", encoding="utf-8") as f:
                        json.dump(doc_model.model_dump(), f, indent=2)
                except OSError as err:
                    logger.warning("Disk cache write failed for %s: %s", filename, err)

                # Update session state
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
                new_pdf_uploaded = True
                st.success(f"**`{filename}`** indexed successfully (`{doc_id}`)")

            if new_pdf_uploaded:
                st.session_state.chat_history = []
                st.rerun()

            doc_status.update(
                label=f"Indexed {len(st.session_state.indexed_files)} document(s)",
                state="complete",
                expanded=False,
            )

    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)

    # Recent Documents Section
    st.markdown("### Recent documents")
    if not st.session_state.document_metadata:
        render_empty_state("No documents indexed yet", "Upload a PDF above to begin asking questions and summarizing.")
    else:
        for doc_key, meta in list(st.session_state.document_metadata.items())[:5]:
            fname = meta.get("filename", doc_key)
            pages = meta.get("pages", 1)
            chunks = meta.get("chunks", 0)
            upload_time = meta.get("upload_time", "")[:19].replace("T", " ")

            c_doc, c_act1, c_act2 = st.columns([4, 1.2, 1.2])
            with c_doc:
                st.markdown(
                    f"""
                    <div style="background: #0C0D12; border: 1px solid #252632; border-radius: 8px; padding: 0.85rem 1rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="font-weight: 600; color: #F5F3FF; font-size: 0.95rem;">{fname}</div>
                            <span class="status-badge local">{get_svg_icon("check", size=12, color="#70D9C2")} Indexed</span>
                        </div>
                        <div style="font-size: 0.8rem; color: #9693A6; margin-top: 0.35rem;">
                            {pages} pages · {chunks} chunks · Uploaded {upload_time}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with c_act1:
                if st.button("Ask in Chat", key=f"ws_chat_{doc_key}", use_container_width=True):
                    st.session_state.selected_chat_doc = doc_key
                    st.session_state.active_workspace = "Ask Documents"
                    st.rerun()
            with c_act2:
                if st.button("Summarize", key=f"ws_sum_{doc_key}", use_container_width=True):
                    st.session_state.selected_summary_doc = doc_key
                    st.session_state.active_workspace = "Summarizer"
                    st.rerun()


# =====================================================================
# 2. ASK DOCUMENTS VIEW (Chat / Citations / Evidence Drawer)
# =====================================================================


def render_chat_view(
    ai_model: AiModel,
    health: Any,
    caps: Any,
) -> None:
    """Render evidence-grounded chat with document filtering and citation drawer."""
    st.markdown("## Ask documents")
    st.caption("Evidence-grounded conversational search. Every answer cites verifiable page references.")

    # Document filtering selector
    doc_options = ["all"] + list(st.session_state.document_metadata.keys())

    def _doc_label(key: str) -> str:
        if key == "all":
            return f"All Documents ({len(st.session_state.indexed_files)} files)"
        meta = st.session_state.document_metadata.get(key, {})
        return f"{meta.get('filename', key)} ({meta.get('chunks', 0)} chunks)"

    selected_filter = st.selectbox(
        "Focus Conversation",
        options=doc_options,
        format_func=_doc_label,
        index=0
        if "selected_chat_doc" not in st.session_state or st.session_state.selected_chat_doc not in doc_options
        else doc_options.index(st.session_state.selected_chat_doc),
        help="Restrict retrieval to a single PDF or search across your entire workspace.",
    )

    col_info, col_clear = st.columns([4, 1])
    with col_info:
        if st.session_state.hybrid_retriever is None and st.session_state.local_embedding is None:
            st.info("Upload a document in the Workspace to begin chatting.")
    with col_clear:
        if st.button("Clear Chat", use_container_width=True, help="Clear active conversation history"):
            st.session_state.chat_history = []
            st.rerun()

    st.divider()

    # Replay conversation
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
                    st.caption(f"☁️ *Generated via external cloud provider ({cloud_m}) with user consent.*")
                else:
                    st.caption("🔒 *Generated locally on-device (zero network egress).*")

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
                    st.markdown(" ".join(chips), unsafe_allow_html=True)

                    with st.expander("🔍 Cited Evidence & Source Context", expanded=False):
                        for s in snippets:
                            header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                            st.markdown(header)
                            st.markdown(f"> {s.get('content', '').strip()}")
                            if s.get("bbox"):
                                bbox = s["bbox"]
                                st.caption(
                                    f"Region: x0={bbox.get('x0', 0.0):.1f}, y0={bbox.get('y0', 0.0):.1f}, "
                                    f"x1={bbox.get('x1', 0.0):.1f}, y1={bbox.get('y1', 0.0):.1f}"
                                )
                            st.divider()

    # Chat Input
    is_healthy = bool(health.status == "healthy")
    placeholder_text = (
        "Ask a question about your documents…"
        if is_healthy
        else "Inference backend is offline. Start llama-server or configure cloud provider in Settings."
    )
    prompt = st.chat_input(
        placeholder=placeholder_text,
        disabled=(st.session_state.local_embedding is None or not is_healthy),
    )

    if prompt:
        if not is_healthy:
            st.error(f"Inference backend unavailable: {health.message}")
            return

        append_chat_turn({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

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

        sources: list[str] = []
        retrieval_res = None
        active_retriever = st.session_state.get("hybrid_retriever") or st.session_state.local_embedding

        if active_retriever is not None:
            if hasattr(active_retriever, "search_hybrid"):
                doc_filter = None if selected_filter == "all" else selected_filter
                retrieval_res = active_retriever.search_hybrid(search_query, k=5, doc_id=doc_filter)
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
                    prompt=prompt,
                    local_embedding=active_retriever,
                    chat_history=history_to_pass,
                    retrieval_result=retrieval_res,
                )
                full_response = st.write_stream(response_stream)

                if not caps.is_local:
                    st.caption(f"☁️ *Generated via external cloud provider ({caps.model_name}) with user consent.*")
                else:
                    st.caption("🔒 *Generated locally on-device (zero network egress).*")

                verification = ai_model.validate_response(full_response, retrieval_res)
                if verification.abstention_detected:
                    st.caption("ℹ️ *Explicit abstention — no document evidence found.*")
                elif verification.is_valid:
                    precision = verification.precision
                    st.caption(f"✅ Verified Grounding ({precision:.0%} citation precision)")
                else:
                    precision = verification.precision
                    st.caption(f"⚠️ Unverified Citations ({precision:.0%} citation precision)")

                if snippets_data:
                    chips = [
                        render_citation_chip(
                            doc_id=s.get("doc_id", ""),
                            page=s.get("page", 1),
                            filename=s.get("filename", "doc"),
                            rank=s.get("rank"),
                        )
                        for s in snippets_data
                    ]
                    st.markdown(" ".join(chips), unsafe_allow_html=True)

                    with st.expander("🔍 Cited Evidence & Source Context", expanded=False):
                        for s in snippets_data:
                            header = f"**[E{s['rank']}]** `{s.get('filename', 'doc')}` *(p. {s.get('page', 1)}, score: {s.get('score', 0.0):.3f})*"
                            st.markdown(header)
                            st.markdown(f"> {s.get('content', '').strip()}")
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
    st.markdown("## Summarizer")
    st.caption("Synthesize documents across 5 analytical profiles with page references and export options.")

    if not st.session_state.document_metadata and not st.session_state.indexed_files:
        render_empty_state("No documents available", "Upload a PDF in the Workspace to generate structured summaries.")
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

    # Check for summary to display with model version verification (P1 audit)
    active_summary = st.session_state.get(summary_cache_key)
    if not active_summary and selected_sha:
        cached_summ = doc_store.get_summary(selected_sha, selected_profile, model_version=ai_model.model_name)
        if cached_summ:
            active_summary = cached_summ.model_dump()

    if active_summary:
        st.divider()
        col_tag, col_dl = st.columns([3, 1])
        with col_tag:
            if active_summary.get("cached"):
                st.caption("⚡ *Loaded from persistent SQLite cache (DocStore v3)*")
            else:
                st.caption(f"✨ *Generated fresh with {active_summary.get('model_version', 'model')}*")
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
            with st.expander("📄 Referenced Source Pages", expanded=False):
                st.markdown(f"**Source pages cited:** {', '.join(f'Page {p}' for p in p_refs)}")
                st.caption(f"Generated at: {active_summary.get('created_at', '')}")


# =====================================================================
# 4. DOCUMENT LIBRARY VIEW
# =====================================================================


def render_library_view(
    doc_store: DocStore,
    hybrid_retriever: HybridRetriever | None,
) -> None:
    """Render document lifecycle manager: search, inspect, retry, re-index, and delete."""
    st.markdown("## Document library")
    st.caption("Manage stored documents, inspect chunk indexing, or remove files from local storage.")

    all_docs = doc_store.list_documents()

    if not all_docs:
        render_empty_state("No documents in database", "Upload your first PDF in the Workspace to build your library.")
        return

    # Search bar
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
            st.markdown(
                f"""
                <div class="amoled-card" style="margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600; color: #F5F3FF; font-size: 1rem;">{doc.filename}</span>
                        {render_status_pill(doc.status.title(), variant=status_variant)}
                    </div>
                    <div style="font-size: 0.8rem; color: #9693A6; margin-top: 0.4rem;">
                        <code>{doc.doc_id}</code> · {doc.num_pages} pages · {doc.num_chunks} chunks · {doc.size_bytes / 1024:.1f} KB
                    </div>
                    <div style="font-size: 0.75rem; color: #9693A6; margin-top: 0.2rem;">
                        Uploaded: {upload_dt} · SHA-256: <code>{doc.sha256[:16]}...</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with c_action:
            st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
            col_open, col_del = st.columns(2)
            with col_open:
                if st.button("Open", key=f"lib_open_{doc.doc_id}", use_container_width=True):
                    st.session_state.selected_chat_doc = doc.doc_id
                    st.session_state.active_workspace = "Ask Documents"
                    st.rerun()
            with col_del:
                if st.button("Delete", key=f"lib_del_{doc.doc_id}", type="secondary", use_container_width=True):
                    # Delete from SQLite
                    doc_store.delete_document(doc.doc_id)
                    # Delete from LanceDB
                    if hybrid_retriever is not None:
                        try:
                            hybrid_retriever.delete_document(doc.doc_id)
                        except Exception as err:
                            logger.warning("Failed to delete from retriever: %s", err)
                    # Remove from session state
                    st.session_state.doc_ids.discard(doc.doc_id)
                    st.session_state.indexed_files.discard(doc.filename)
                    st.session_state.document_metadata.pop(doc.doc_id, None)
                    st.toast(f"Deleted `{doc.filename}`.")
                    st.rerun()

    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)
    st.markdown("### Danger zone")
    with st.expander("Delete All Stored Data", expanded=False):
        st.warning(
            "This will permanently delete all indexed documents, SQLite rows, LanceDB vector tables, and disk caches. "
            "This operation cannot be undone."
        )
        confirm_purge = st.checkbox("I understand that this will erase all stored documents and vectors.")
        if st.button("Purge All Data Now", type="primary", disabled=not confirm_purge):
            doc_store.purge_all()
            if hybrid_retriever is not None:
                hybrid_retriever.purge_all()
            st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
            st.session_state.doc_ids = set()
            st.session_state.failed_doc_ids = set()
            st.session_state.indexed_files = set()
            st.session_state.document_metadata = {}
            st.session_state._startup_hydrated = False
            st.toast("Purged all local database records and index tables.")
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
    st.markdown("## Settings & diagnostics")
    st.caption("Telemetry, model configurations, and local privacy guarantees.")

    st.markdown("### Privacy & inference mode")

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
            st.markdown(render_status_pill("Cloud Active", variant="cloud"), unsafe_allow_html=True)
        else:
            st.markdown(render_status_pill("100% Local", variant="local"), unsafe_allow_html=True)

    if st.session_state.cloud_mode and st.session_state.user_consented:
        st.markdown(
            """
            <div class="amoled-card-elevated" style="border-left: 3px solid #B9A3FF;">
                <div style="font-weight: 600; color: #B9A3FF;">Cloud Egress Permitted</div>
                <div style="font-size: 0.85rem; color: #9693A6; margin-top: 0.25rem;">
                    Prompts and retrieved text excerpts are transmitted to your selected cloud API. Original PDF files and dense embeddings remain local on disk.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        provider_map = {
            "groq": "Groq (Llama 3.3 70B)",
            "openai": "OpenAI (GPT-4o mini)",
            "anthropic": "Anthropic (Claude 3.5 Haiku)",
        }
        selected_prov = st.selectbox(
            "Cloud Provider",
            options=list(provider_map.keys()),
            format_func=lambda k: provider_map[k],
            index=list(provider_map.keys()).index(st.session_state.cloud_provider)
            if st.session_state.cloud_provider in provider_map
            else 0,
        )
        if selected_prov != st.session_state.cloud_provider:
            st.session_state.cloud_provider = selected_prov
            st.rerun()

        if st.button("Revoke Consent (Switch back to 100% Local)", use_container_width=True):
            st.session_state.cloud_mode = False
            st.session_state.cloud_mode_toggle = False
            st.session_state.user_consented = False
            st.rerun()

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # Hardware & VRAM Telemetry
    st.markdown("### Hardware & telemetry")
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
    st.markdown("### Storage & session")
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
