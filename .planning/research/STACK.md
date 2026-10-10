# Stack Research

**Domain:** Local-First Multimodal PDF Intelligence & RAG (RTX 3050 Laptop 4GB VRAM)  
**Researched:** 2026-10-10  
**Confidence:** HIGH  

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Python** | `3.11.x` | Runtime & execution | Optimal compatibility across PyTorch, Docling, Sentence-Transformers, and Windows CUDA wheels. |
| **Streamlit** | `>=1.42.0` | UI Presentation Layer | Preserves existing application UX, supports `st.write_stream`, session state, status containers, and reactive document inspection. |
| **Docling** | `>=2.15.0` | Structured PDF extraction | State-of-the-art document layout parsing, section hierarchy, table structure extraction, and bounding-box preservation without mandatory heavy OCR. |
| **RapidOCR** | `>=1.4.0` | Conditional OCR engine | Fast, lightweight ONNX-based local OCR for scanned pages and image text layers; minimal memory footprint on CPU/GPU. |
| **llama-server (llama.cpp)** | `b3500+` (CUDA build) | Local LLM/VLM inference | Minimal VRAM footprint, precise GPU offload layers (`-ngl`), native GGUF 4-bit quantization, OpenAI-compatible REST server, and vision projector support. |
| **LanceDB** | `>=0.17.0` | Local persistent hybrid store | Serverless, disk-persisted vector and full-text search (BM25/FTS) with reciprocal rank fusion (RRF); avoids external DB server processes. |
| **Sentence-Transformers** | `>=3.4.1` | Local dense embeddings | Fast, proven embedding pipeline (`all-MiniLM-L6-v2` or `BAAI/bge-small-en-v1.5`); low memory consumption (~80MB). |
| **SQLite (Python stdlib)** | `3.x` | Metadata & provenance store | ACID transactional local metadata storage for document hashes, page status, element bounding boxes, and citation evidence records. |
| **LiteLLM** | `>=1.50.0` | Optional cloud provider adapter | Uniform API abstraction across Groq, OpenAI, Anthropic, and custom endpoints with standardized fallback, timeout, and schema handling. |
| **Pydantic** | `>=2.10.0` | Data modeling & validation | Fast, strict typing for canonical document models, evidence items, and summary profiles. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **Pillow (PIL)** | `>=10.4.0` | Image processing & rendering | Page image rendering, cropping visual elements, bounding box verification. |
| **pypdf** | `>=5.3.0` | Fallback extraction & fast metadata inspection | Quick page count, file signature validation, and light digital extraction fallback. |
| **PyMuPDF (fitz)** | `>=1.24.0` | High-fidelity page image rendering | Rapid page rendering to PNG for visual element crops and VLM input. |
| **tiktoken** | `>=0.8.0` | Token counting & budget allocation | Enforcing bounded context window (4K–8K tokens) before inference. |
| **python-dotenv** | `>=1.0.1` | Local environment configuration | Loading local API keys and server configuration. |
| **httpx** | `>=0.28.0` | Async/sync HTTP client | Fast, reliable communication with local `llama-server` endpoints. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **Pytest** (`>=8.3.0`) | Automated test suite | Regression testing across ingestion, extraction, retrieval, citation, and inference. |
| **Ruff** (`>=0.9.0`) | Fast linter & formatter | Enforce code quality, dead-code removal, and consistency. |
| **Pytest-mock / responses** | Mocking external services | Deterministic testing of LLM and OCR provider interfaces without active GPU. |

## Installation

```bash
# Core pipeline dependencies
pip install "streamlit>=1.42.0" "docling>=2.15.0" "rapidocr-onnxruntime>=1.4.0" "lancedb>=0.17.0" "sentence-transformers>=3.4.1" "pydantic>=2.10.0" "litellm>=1.50.0"

# Supporting utilities
pip install "pymupdf>=1.24.0" "pillow>=10.4.0" "tiktoken>=0.8.0" "python-dotenv>=1.0.1" "httpx>=0.28.0"

# Testing & Dev
pip install -D "pytest>=8.3.0" "pytest-mock>=3.14.0" "ruff>=0.9.0"
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **Docling** | PyPDF / pdfplumber | Simple, pure-text documents without tables or complex multi-column layouts. |
| **llama-server (llama.cpp)** | Ollama | Quick exploratory testing when native background process orchestration is handled externally, but llama.cpp gives tighter VRAM tuning (`-ngl`, `-c`, `-b`). |
| **LanceDB** | ChromaDB / FAISS | ChromaDB has higher memory overhead; FAISS lacks integrated full-text hybrid search and metadata filtering. |
| **SQLite** | DuckDB | DuckDB is superior for analytical OLAP queries, but SQLite is optimal for transactional document/chunk CRUD. |
| **LiteLLM** | Raw Groq/OpenAI SDKs | When only a single cloud provider is ever needed, but LiteLLM eliminates provider-specific branching logic. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **LangChain Agents / AutoGen** | Massive abstraction overhead, unpredictable multi-turn memory spikes, difficult debugging. | Deterministic service pipeline with explicit prompt templates. |
| **Unquantized 7B+ VLMs** | Exceeds 4 GB VRAM ceiling, triggers CUDA OOM and system paging thrash. | 2B-class quantized models (Qwen3-VL 2B GGUF Q4_K_M) with conservative 4K-8K context. |
| **Concurrent Multi-Model Loading** | Running embedding model, OCR, and VLM simultaneously on 4 GB GPU causes crash. | Run embeddings/OCR on CPU or sequence VRAM usage: one active model on GPU at a time. |
| **In-memory pure Python VectorIndex** | O(N) scan latency, zero disk persistence, process data loss on restart. | LanceDB hybrid store with disk persistence. |
| **Unconditional Page OCR** | Wasteful compute on clean digital PDFs; causes 10x-50x processing slowdown. | Docling layout detection + conditional RapidOCR only on unextractable/scanned pages. |

## Stack Patterns by Variant

**If GPU VRAM is severely constrained (< 4 GB available):**
- Run Sentence-Transformers embedding model on CPU (`device="cpu"`).
- Offload partial layers of llama.cpp to GPU (`-ngl 20-25` instead of full offload).
- Limit context length to 4096 tokens (`-c 4096`).

**If running on clean digital PDFs:**
- Bypass OCR completely in Docling pipeline (`pipeline_options.do_ocr = False`).
- Extract text and table structure in under 5 seconds for a 20-page document.

**If cloud mode is enabled by user:**
- Route inference through LiteLLM while keeping ingestion, embeddings, and LanceDB indexing 100% local.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `docling>=2.15.0` | `torch>=2.2.0` | Compatible with Python 3.11; ensure PyTorch matches local CUDA version (cu121/cu124). |
| `lancedb>=0.17.0` | `pyarrow>=14.0.0` | Windows binary wheels available; no C++ compiler required. |
| `rapidocr-onnxruntime` | `onnxruntime>=1.17.0` | CPU execution is robust and avoids CUDA VRAM contention. |

## Sources

- [Docling Documentation](https://docling.org/formats/) — Structured extraction & layout pipeline.
- [LanceDB Documentation](https://lancedb.github.io/lancedb/python/python/) — Hybrid search and serverless persistence.
- [llama.cpp Server Documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) — Multi-modal support, OpenAI-compatible API.
- [LiteLLM Documentation](https://docs.litellm.ai/docs/) — Uniform multi-provider abstraction.

---
*Stack research for: Local-First Multimodal PDF Intelligence System*  
*Researched: 2026-10-10*
