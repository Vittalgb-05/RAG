"""
Streamlit front-end for the local RAG pipeline.

Lets the user upload any PDF, asks questions about it, and streams
the answer token-by-token from a fully local LLM — no cloud required.

Pipeline recap
--------------
PDF upload → PdfReader (text extraction) → LocalEmbedding (indexing)
→ AiModel.ask_a_question_from_pdf_stream (retrieval + generation)
→ st.write_stream (live token rendering in the browser)
"""

import os
import tempfile
import datetime

import streamlit as st
from dotenv import load_dotenv

from local_llm import AiModel
from local_embedding import LocalEmbedding
from pdf_reader import PdfReader


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
# Session state is the only thing that persists across those reruns
# within a single browser session.

for key, default in [
    ("indexed_files", set()),       # set of filenames we have already indexed
    ("document_metadata", {}),      # dict mapping filename -> metadata dict
    ("local_embedding", None),      # unified index spanning all uploaded documents
    ("chat_history", []),           # list of {"role": ..., "content": ..., "sources": ...} dicts
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ------------------------------------------------------------------
# Cached helpers
# ------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_ai_model() -> AiModel:
    '''
        Loads AiModel exactly once for the lifetime of the Streamlit server process.
        @st.cache_resource returns the same instance on every subsequent call,
        so the LLM is never loaded more than once regardless of reruns.
    '''
    load_dotenv()    # make HF_TOKEN available before AiModel.__init__ reads it
    return AiModel()


def save_uploaded_pdf(uploaded_file) -> str:
    '''
        Writes the uploaded PDF bytes to a NamedTemporaryFile on disk
        and returns the absolute path to that file.

        delete=False is required because PdfReader must open the file
        by path after this function returns — it cannot accept raw bytes.
    '''
    suffix = f"_{uploaded_file.name}"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return tmp.name


# ------------------------------------------------------------------
# Sidebar — model status + document upload
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 📄 RAG Assistant")
    st.markdown("Ask questions about any PDF — Fast Groq Deployment Mode or Fully Local Mode.")
    st.divider()

    # Model loading
    # show_spinner=False on the decorator lets us display our own richer status widget
    st.markdown("#### Model")
    with st.status("Initializing AI Assistant...", expanded=True) as model_status:
        ai_model = load_ai_model()
        mode_label = "Deployment (Groq)" if ai_model.mode == "groq" else "Local (HuggingFace)"
        model_status.update(label=f"LLM ready — {mode_label}", state="complete", expanded=False)

    st.divider()

    # Document upload
    st.markdown("#### Document")
    
    col1, col2 = st.columns([2, 1])
    with col2:
        if st.button("Clear All", use_container_width=True):
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
        accept_multiple_files=True
    )

    if uploaded_files:
        # Build the embedding index for any new PDFs
        with st.status("Processing documents…", expanded=True) as doc_status:
            new_pdf_uploaded = False
            for uploaded_file in uploaded_files:
                if uploaded_file.name not in st.session_state.indexed_files:
                    new_pdf_uploaded = True
                    st.write(f"Extracting text from {uploaded_file.name}…")
                    
                    import io
                    pdf_stream = io.BytesIO(uploaded_file.getvalue())
                    
                    try:
                        pdf_reader = PdfReader(pdf_stream, filename=uploaded_file.name)
                        paragraphs = pdf_reader.get_paragraphs()
                    except Exception as e:
                        st.error(f"Failed to parse `{uploaded_file.name}`. The file may be corrupted, empty, or not a valid PDF. (Error: {e})")
                        continue
                    
                    if st.session_state.local_embedding is None:
                        st.session_state.local_embedding = LocalEmbedding()
                    
                    st.write(f"Building index for {uploaded_file.name} ({len(paragraphs)} chunks)…")
                    st.session_state.local_embedding.build_index(paragraphs)
                    
                    st.session_state.indexed_files.add(uploaded_file.name)
                    st.session_state.document_metadata[uploaded_file.name] = {
                        "upload_time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "pages": paragraphs[-1]["page"] if paragraphs else 0,
                        "chunks": len(paragraphs)
                    }

            if new_pdf_uploaded:
                st.session_state.chat_history = []
                st.rerun()

            doc_status.update(
                label=f"Indexed {len(st.session_state.indexed_files)} document(s)",
                state="complete",
                expanded=False,
            )

        st.markdown("##### Indexed Documents:")
        for filename in st.session_state.indexed_files:
            meta = st.session_state.document_metadata[filename]
            st.success(
                f"**{filename}**\n\n"
                f"{meta['pages']} pages · {meta['chunks']} chunks · Indexed at {meta['upload_time']}"
            )
    else:
        st.info("Upload a PDF to get started.")

    st.divider()
    if ai_model.mode == "groq":
        st.caption(f"Powered by **Groq ({ai_model.model_name})** + **MiniLM-L6-v2**")
    else:
        st.caption(f"Powered by **{ai_model.model_name}** + **MiniLM-L6-v2** · runs entirely on your machine")


# ------------------------------------------------------------------
# Main content area — chat interface
# ------------------------------------------------------------------

st.markdown("# Ask Your Document")

if st.session_state.local_embedding is None:
    st.markdown("> **Upload a PDF in the sidebar** to begin asking questions.")
else:
    total_chunks = sum(meta["chunks"] for meta in st.session_state.document_metadata.values())
    st.markdown(
        f"Chatting across **{len(st.session_state.indexed_files)} documents** · "
        f"{total_chunks} total chunks indexed"
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
    # st.write_stream consumes the generator and renders each chunk as it arrives,
    # then returns the fully concatenated string when generation is complete.
    with st.chat_message("assistant"):
        if sources:
            st.info(f"**Sources used:** {', '.join(sources)}", icon="ℹ️")
            
        # Pass conversation history (excluding the current prompt just appended)
        # Limit to the last 10 messages (5 exchanges)
        history_to_pass = st.session_state.chat_history[:-1][-10:]
            
        response_stream = ai_model.ask_a_question_from_pdf_stream(
            pdf_path="", # ignored because local_embedding is provided
            prompt=prompt,
            local_embedding=st.session_state.local_embedding,
            chat_history=history_to_pass
        )
        full_response = st.write_stream(response_stream)

    st.session_state.chat_history.append({
        "role": "assistant", 
        "content": full_response,
        "sources": list(sources)
    })


###############
# Run
###############

# source .venv/Scripts/activate
# streamlit run main.py
