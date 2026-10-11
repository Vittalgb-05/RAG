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
from pathlib import Path
import sqlite3
from typing import Any

from dotenv import load_dotenv
import streamlit as st

from citation_validator import validate_citations
from doc_store import DocStore
from docling_reader import DoclingReader
from hybrid_retriever import HybridRetriever
from local_embedding import LocalEmbedding
from local_llm import AiModel
from models import Chunk, Document, Page, cache_dir_for
from ocr_fallback import apply_conditional_ocr
from summarizer import Summarizer
from upload_validation import MAX_FILE_MB, validate_pdf_bytes
from visual_analyzer import VisualAnalyzer

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
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------------------------------
# Cached helpers
# ------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def load_ai_model() -> AiModel:
    """
    Loads AiModel exactly once for the lifetime of the Streamlit server process.
    @st.cache_resource returns the same instance on every subsequent call,
    so the LLM is never loaded more than once regardless of reruns.
    """
    load_dotenv()
    return AiModel()


DOC_STORE_PATH = Path(__file__).resolve().parent / "data" / "documents.db"
doc_store = DocStore(DOC_STORE_PATH)


# ------------------------------------------------------------------
# Sidebar — model status + document upload
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📄 RAG Assistant")
    st.markdown("Ask questions about any PDF with local indexing and intelligent deduplication.")
    st.divider()

    # Model loading & health
    st.markdown("#### Model")
    with st.status("Initializing AI Assistant...", expanded=True) as model_status:
        ai_model = load_ai_model()
        st.session_state.ai_model = ai_model
        health = ai_model.check_health()
        caps = ai_model.get_capabilities()
        if health.status == "healthy":
            if caps.is_local:
                model_status.update(
                    label=f"🟢 Inference: Local ({caps.model_name})",
                    state="complete",
                    expanded=False,
                )
            else:
                model_status.update(
                    label=f"🔵 Inference: Groq Cloud ({caps.model_name})",
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

    col1, col2 = st.columns([2, 1])
    with col2:
        if st.button("Clear All", use_container_width=True):
            st.session_state.doc_ids = set()
            st.session_state.indexed_files = set()
            st.session_state.document_metadata = {}
            st.session_state.local_embedding = None
            if st.session_state.get("hybrid_retriever"):
                st.session_state.hybrid_retriever.close()
            st.session_state.hybrid_retriever = None
            st.session_state.chat_history = []
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
                    st.session_state.document_metadata[filename] = {
                        "doc_id": doc_id,
                        "sha256": validated.sha256,
                        "upload_time": existing_doc.upload_time
                        if existing_doc
                        else datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "pages": existing_doc.num_pages if existing_doc else validated.num_pages,
                        "chunks": existing_doc.num_chunks if existing_doc else 0,
                    }
                    # CR-01: On dedup hit after restart (empty session index), restore chunks from DocStore
                    if st.session_state.local_embedding is None:
                        persisted_chunks = doc_store.get_chunks_for_doc(doc_id)
                        if persisted_chunks:
                            st.session_state.local_embedding = LocalEmbedding()
                            chunk_dicts = [c.model_dump() for c in persisted_chunks]
                            st.session_state.local_embedding.build_index(chunk_dicts)
                            if st.session_state.hybrid_retriever is None:
                                st.session_state.hybrid_retriever = HybridRetriever(
                                    embedding_fn=st.session_state.local_embedding._embed_one
                                )
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
                    active_provider = current_model._provider if current_model is not None else None
                    evidence_elements = visual_analyzer.analyze_visual_elements(
                        pdf_bytes=raw_bytes,
                        doc_id=doc_id,
                        provider=active_provider,
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

                # 5. Build vector embeddings and persistent LanceDB hybrid index
                st.write(f"Building index for `{filename}` ({len(paragraphs)} chunks)…")
                if st.session_state.local_embedding is None:
                    st.session_state.local_embedding = LocalEmbedding()
                st.session_state.local_embedding.build_index(paragraphs)

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
                    cache_dir = cache_dir_for(Path(".cache"), validated.sha256)
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
                st.session_state.document_metadata[filename] = {
                    "doc_id": doc_id,
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
        for filename, meta in st.session_state.document_metadata.items():
            doc_id_label = f" (`{meta['doc_id']}`)" if "doc_id" in meta else ""
            display_time = meta["upload_time"][:19].replace("T", " ")
            st.success(
                f"**`{filename}`**{doc_id_label}\n\n{meta['pages']} pages · {meta['chunks']} chunks · Indexed at {display_time}"
            )
    else:
        st.info("Upload a PDF to get started.")

    st.divider()
    st.caption(f"Powered by **Groq ({ai_model.model_name})** + **MiniLM-L6-v2**")


# ------------------------------------------------------------------
# Main content area — tabs for Chat and Summarizer
# ------------------------------------------------------------------

tab_chat, tab_summary = st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])

with tab_chat:
    st.markdown("## Chat & Grounded Question Answering")

    if st.session_state.local_embedding is None:
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
            st.session_state.chat_history.append({"role": "user", "content": prompt})
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

                    # Validate citations and abstention (QA-03, QA-04)
                    verification = validate_citations(full_response, retrieval_res)
                    if verification.abstention_detected:
                        st.caption("ℹ️ *Explicit abstention — no document evidence found.*")
                    elif verification.is_valid:
                        st.caption(f"✅ Verified Grounding ({verification.precision:.0%} citation precision)")
                    else:
                        st.caption(f"⚠️ Unverified Citations ({verification.precision:.0%} citation precision)")

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

                    st.session_state.chat_history.append(
                        {
                            "role": "assistant",
                            "content": full_response,
                            "sources": list(sources),
                            "verification": verification.model_dump(),
                            "snippets": snippets_data,
                        }
                    )
                except Exception as err:
                    st.error(f"Inference streaming failed: {err}")
                    st.session_state.chat_history.append(
                        {
                            "role": "assistant",
                            "content": f"*[Response generation interrupted: {err}]*",
                            "sources": list(sources),
                            "verification": None,
                            "snippets": snippets_data,
                        }
                    )


with tab_summary:
    st.markdown("## 📑 Document Summarizer")
    st.caption("Generate grounded, page-referenced summaries across 5 analytical profiles.")

    if not st.session_state.indexed_files:
        st.info("Upload and index a PDF in the sidebar to enable summarization.")
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
