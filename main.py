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

from dotenv import load_dotenv
import streamlit as st

from doc_store import DocStore
from local_embedding import LocalEmbedding
from local_llm import AiModel
from models import Document, cache_dir_for
from pdf_reader import PdfReader
from upload_validation import validate_pdf_bytes

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


# ------------------------------------------------------------------
# Sidebar — model status + document upload
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📄 RAG Assistant")
    st.markdown("Ask questions about any PDF with local indexing and intelligent deduplication.")
    st.divider()

    # Model loading
    st.markdown("#### Model")
    with st.status("Initializing AI Assistant...", expanded=True) as model_status:
        ai_model = load_ai_model()
        model_status.update(label="LLM ready — Groq Cloud", state="complete", expanded=False)

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
            doc_store = DocStore(Path("data/documents.db"))

            for uploaded_file in uploaded_files:
                # 1. Single raw bytes read per file
                raw_bytes = uploaded_file.getvalue()
                filename = uploaded_file.name

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
                        "upload_time": existing_doc.upload_time
                        if existing_doc
                        else datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S"),
                        "pages": existing_doc.num_pages if existing_doc else validated.num_pages,
                        "chunks": existing_doc.num_chunks if existing_doc else 0,
                    }
                    continue

                new_pdf_uploaded = True

                # 4. Text extraction with page-level fault isolation and progress indicator
                st.write(f"Extracting text from `{filename}`…")
                progress_bar = st.progress(0.0)

                pdf_stream = io.BytesIO(raw_bytes)
                pdf_reader = PdfReader(pdf_stream, filename=filename)

                sha12 = validated.sha256[:12]
                pdf_reader.extract_text(doc_id=doc_id, sha12=sha12)
                paragraphs = pdf_reader.get_paragraphs()
                page_records = pdf_reader.get_page_records()

                for idx, page in enumerate(page_records):
                    doc_store.record_page(page)
                    progress_bar.progress((idx + 1) / max(1, len(page_records)))
                    if page.status == "failed":
                        st.warning(f"Page {page.page_num} in `{filename}` skipped ({page.error})")

                # 5. Build vector embeddings
                st.write(f"Building index for `{filename}` ({len(paragraphs)} chunks)…")
                if st.session_state.local_embedding is None:
                    st.session_state.local_embedding = LocalEmbedding()
                st.session_state.local_embedding.build_index(paragraphs)

                # 6. Persist metadata in DocStore
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
                doc_store.upsert_document(doc_model)

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
                    "upload_time": datetime.datetime.now().strftime("%H:%M:%S"),
                    "pages": validated.num_pages,
                    "chunks": len(paragraphs),
                }
                st.success(f"**{filename}** indexed successfully (`{doc_id}`)")

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
            st.success(
                f"**{filename}**{doc_id_label}\n\n{meta['pages']} pages · {meta['chunks']} chunks · Indexed at {meta['upload_time']}"
            )
    else:
        st.info("Upload a PDF to get started.")

    st.divider()
    st.caption(f"Powered by **Groq ({ai_model.model_name})** + **MiniLM-L6-v2**")


# ------------------------------------------------------------------
# Main content area — chat interface
# ------------------------------------------------------------------

st.markdown("# Ask Your Document")

if st.session_state.local_embedding is None:
    st.markdown("> **Upload a PDF in the sidebar** to begin asking questions.")
else:
    total_chunks = sum(meta["chunks"] for meta in st.session_state.document_metadata.values())
    st.markdown(
        f"Chatting across **{len(st.session_state.indexed_files)} documents** · {total_chunks} total chunks indexed"
    )

st.divider()

# Replay the full conversation on every rerun so chat history stays visible
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        if message.get("sources"):
            st.info(f"**Sources used:** {', '.join(message['sources'])}", icon="ℹ️")
        st.markdown(message["content"])

# Chat input — pinned to the bottom of the page by Streamlit natively.
# Passing disabled=True prevents questions before a PDF is indexed.
prompt = st.chat_input(
    placeholder="Ask a question about your documents…",
    disabled=(st.session_state.local_embedding is None),
)

if prompt:
    # Show the user's message immediately
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Fetch context to display sources BEFORE generation starts
    results = st.session_state.local_embedding.search(prompt, k=10)
    sources = set()
    for doc, dist in results:
        if "filename" in doc:
            sources.add(doc["filename"])

    # Stream the assistant response token-by-token.
    with st.chat_message("assistant"):
        if sources:
            st.info(f"**Sources used:** {', '.join(sources)}", icon="ℹ️")

        # Pass conversation history (excluding the current prompt just appended)
        # Limit to the last 10 messages (5 exchanges)
        history_to_pass = st.session_state.chat_history[:-1][-10:]

        response_stream = ai_model.ask_a_question_from_pdf_stream(
            pdf_path="",  # ignored because local_embedding is provided
            prompt=prompt,
            local_embedding=st.session_state.local_embedding,
            chat_history=history_to_pass,
        )
        full_response = st.write_stream(response_stream)

    st.session_state.chat_history.append({"role": "assistant", "content": full_response, "sources": list(sources)})
