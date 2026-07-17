# RAG AI System — Ask Your Documents, Privately

> A Retrieval-Augmented Generation (RAG) pipeline with a Streamlit chat UI — upload any PDF, ask questions in plain English, and get grounded, streamed answers. 
>
> **Deployment Mode**: Uses Groq API for fast inference.
> **Local Mode (Optional)**: Supports running a local Hugging Face model with suitable hardware.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![PyTorch](https://img.shields.io/badge/PyTorch-CUDA_12.1-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Transformers-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/)
[![Model](https://img.shields.io/badge/Model-Qwen2.5--3B--Instruct-a78bfa)](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct)

---

## What Is This?

RAG AI System is a fully local Retrieval-Augmented Generation pipeline that lets you upload a PDF and ask natural-language questions against it — with the answer streamed token-by-token directly to your browser.

This project runs a MiniLM embedding model to convert your document into semantic vectors and retrieves the most relevant paragraphs using a pure-Python cosine-search index. The answers are then generated using either Groq's lightning-fast Llama 3 API or a fully local Hugging Face model.

| File | Responsibility |
|---|---|
| `main.py` | Streamlit UI — chat interface, file upload, streaming output |
| `local_llm.py` | `AiModel` — connects to Groq API or loads local HF model, streams token output |
| `local_embedding.py` | `LocalEmbedding` — MiniLM wrapper and vector index interface |
| `vector_index.py` | `VectorIndex` — pure-stdlib in-memory cosine/Euclidean vector store |
| `pdf_reader.py` | `PdfReader` — PDF text extraction and paragraph splitting |

---

## Screenshots

### Upload screen — ready state

![Upload screen](application_screenshots/image_2.png)

The sidebar shows **LLM ready** once the Qwen model has loaded. The PDF uploader accepts drag-and-drop or file browser. The chat area waits for a document before accepting questions.

---

### Active conversation

![Chat screen](application_screenshots/image.png)

After indexing, answers stream token-by-token into the chat. The sidebar displays the paragraph count for the indexed document. Follow-up questions reuse the cached index without re-embedding.

---

## Feature List

### Retrieval-Augmented Generation
- PDF ingestion directly from memory (no disk IO) using `pypdf`
- Advanced text chunking using Langchain's `RecursiveCharacterTextSplitter`
- Batch embedding of all chunks in a single GPU pass using `all-MiniLM-L6-v2`
- Cosine similarity search over 384-dimensional MiniLM vectors
- Dynamic search query contextualization using recent chat history
- Strict grounding prompt — the model is instructed to answer only from the provided document text

### Streaming Output
- `TextIteratorStreamer` runs local `model.generate()` in a background thread, while `groq` streams via its native client
- Tokens are yielded through the streamer without blocking the Streamlit main thread
- `st.write_stream()` renders tokens progressively as they arrive in the browser

### Caching and Session Management
- `@st.cache_resource` loads the LLM once per server process
- `st.session_state` persists the embedding index across follow-up questions
- **Conversational Memory**: Remembers your last 5 questions for fluid follow-ups
- Uploading a new PDF automatically resets the conversation and builds a fresh index

### Pure-Python Vector Store
- `VectorIndex` uses no NumPy, FAISS, or external vector database
- Vectors are L2-normalised at index time; similarity search reduces to a dot-product scan over stored vectors
- Both Euclidean and cosine metrics are available in the same class

---

## How It Works

1. **PDF → Chunks** — `PdfReader` reads directly from a memory stream and uses Langchain's `RecursiveCharacterTextSplitter` to generate clean, overlapping chunks of text.

2. **Chunks → Vectors** — `LocalEmbedding.build_index()` batch-embeds all chunks in one GPU pass using `all-MiniLM-L6-v2` and stores the 384-dimensional vectors in `VectorIndex`.

3. **Question → Context** — At query time, your latest question is dynamically appended to your previous question to maintain context. It is embedded and compared against every stored vector by cosine distance to fetch the top-k chunks.

4. **Context + History → Answer** — `AiModel` wraps the retrieved context, your chat history, and your question into a structured Chat ML array. It sends this to Groq (or local PyTorch) and yields tokens into `st.write_stream()` for a live UI.

---

## Architecture

The retrieval pipeline is fully implemented by me. I generate embeddings locally, retrieve the most relevant chunks from the uploaded PDF, and then pass those chunks as context to the LLM. For deployment, I switched from a locally hosted Qwen model to Groq's hosted Llama model to improve latency and make the application easier to deploy. The RAG architecture itself remains unchanged.

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit UI (main.py)                 │
│                                                           │
│  Sidebar: [Load Model]  [Upload PDF]  [Status]           │
│  Main:    [Chat input]  →  [Streamed answer]             │
└─────────────────────────┬────────────────────────────────┘
                          │
            ┌─────────────▼──────────────┐
            │        PDF Ingestion        │
            │  PdfReader: page text →     │
            │  clean paragraph list       │
            └─────────────┬──────────────┘
                          │
            ┌─────────────▼──────────────┐
            │       LocalEmbedding        │
            │  all-MiniLM-L6-v2          │
            │  batch embed → 384-dim     │
            │  L2-normalised vectors      │
            └─────────────┬──────────────┘
                          │
            ┌─────────────▼──────────────┐
            │        VectorIndex          │
            │  in-memory cosine store     │
            │  (pure Python stdlib)       │
            └─────────────┬──────────────┘
                          │ top-k chunks
            ┌─────────────▼──────────────┐
            │          AiModel            │
            │  Groq Llama 3 (or Qwen)     │
            │  RAG prompt assembly        │
            │  Streaming API response     │
            └─────────────┬──────────────┘
                          │ token stream
            ┌─────────────▼──────────────┐
            │    TextIteratorStreamer      │
            │  + st.write_stream()        │
            │  → live tokens in browser   │
            └─────────────────────────────┘
```

**Model weight acquisition** (first run only):

```text
HuggingFace Hub
  ├── sentence-transformers/all-MiniLM-L6-v2   → embedding model (always downloaded)
  └── Qwen/Qwen2.5-3B-Instruct                 → generation model (only downloaded in Local Mode)
```

---

## Project Structure

```
RAG/
├── main.py                  # Streamlit UI — entry point
├── local_llm.py             # AiModel: loads Qwen, orchestrates RAG, streams output
├── local_embedding.py       # LocalEmbedding: MiniLM wrapper + index interface
├── vector_index.py          # VectorIndex: pure-stdlib cosine/Euclidean vector store
├── pdf_reader.py            # PdfReader: PDF → clean paragraph list
├── application_screenshots/ # UI screenshots used in this README
└── .env                     # HF_TOKEN (gitignored — create this yourself)
```

---

## Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Earlier versions not tested |
| CUDA-capable GPU | Recommended; CPU inference works but is slow |
| Hugging Face account | Free — needed for `HF_TOKEN` |

### Setup

```bash
# Clone the repository
git clone https://github.com/Vittalgb-05/RAG.git
cd RAG

# Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows (Git Bash)
# source .venv/bin/activate     # macOS / Linux

# Install PyTorch with CUDA 12.1 support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Install remaining dependencies
pip install transformers streamlit pypdf python-dotenv huggingface_hub accelerate langchain-text-splitters groq
```

> **GPU note:** the `cu121` wheel targets CUDA 12.1. Find the right wheel for your GPU at [pytorch.org/get-started](https://pytorch.org/get-started/locally/). For CPU-only: `pip install torch torchvision torchaudio`.

### Configuration

Create a `.env` file in the project root. Depending on your mode, add:

```
# For Deployment Mode (Default)
GROQ_API_KEY=gsk_your_groq_key_here

# For Local Mode (Optional)
LLM_MODE=local
HF_TOKEN=hf_your_token_here
```

Get a free Groq key at [console.groq.com](https://console.groq.com/). Get a Hugging Face token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).

---

## Usage

```bash
streamlit run main.py
```

Streamlit will print a local URL (default `http://localhost:8501`). Open it in your browser.

> **First run:** both models are downloaded from HuggingFace Hub and cached in `~/.cache/huggingface/`. This takes a few minutes depending on your connection. Subsequent runs start in seconds.

### Basic workflow

1. Wait for **"LLM ready"** in the sidebar — the Qwen model has finished loading.
2. Drag and drop one or more PDFs onto the uploader, or click **Browse**.
3. Wait for **"Document ready — N paragraphs indexed"** in the sidebar.
4. Type your question in the chat input at the bottom and press Enter.
5. The answer streams token-by-token. Ask follow-up questions freely — the index is cached.
6. Upload additional PDFs to add them to the index, or click **Clear All** to start a fresh conversation.

---

## Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **UI** | Streamlit | Chat interface, file upload, live streaming |
| **LLM** | Groq Llama 3 API (or Local Qwen) | Answer generation |
| **Embeddings** | all-MiniLM-L6-v2 | 384-dim semantic search vectors |
| **Inference** | HuggingFace Transformers | Model loading and generation |
| **Compute** | PyTorch (CUDA 12.1) | GPU-accelerated inference |
| **PDF parsing** | pypdf | Text extraction |
| **Vector store** | Custom `VectorIndex` | In-memory cosine search — no external DB |
| **Streaming** | `TextIteratorStreamer` | Non-blocking token delivery to UI |
| **Config** | python-dotenv | `.env`-based HF token loading |
| **Hub access** | huggingface_hub | Model download and authentication |

---

## Limitations

- **In-memory index only** — `VectorIndex` is not persisted to disk; re-uploading the same PDF re-embeds it from scratch on every run.
- **Linear scan** — similarity search scans every stored vector; performance degrades on very large documents with thousands of paragraphs.
- **Context window cap** — the top-k chunks must fit within the LLM's context window; very long documents or a high `k` value can exceed it.
- **CPU inference is slow** — without a CUDA device, running in Local Mode takes significantly longer than real-time.

---

## Future Improvements

- **Persistent index** — serialize `VectorIndex.vectors` and `.documents` to disk so documents do not need to be re-embedded on every startup.
- **ANN indexing** — replace linear scan with an approximate nearest-neighbour structure (e.g. HNSW) for sub-linear search at scale.
- **Quantized inference** — add `load_in_4bit=True` via `bitsandbytes` to run larger models on smaller GPUs in Local Mode.
- **Embedding progress bar** — show per-paragraph indexing progress during PDF ingestion rather than a single blocking wait.
