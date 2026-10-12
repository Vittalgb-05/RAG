# External Integrations

**Analysis Date:** 2026-10-13

## APIs & External Services

**Local Inference (Default / Zero-Egress):**
- llama.cpp `llama-server` — Primary inference engine for local LLM text generation, SSE token streaming, and VLM multimodal image understanding.
  - SDK/Client: `LlamaCppProvider` (`llama_cpp_provider.py`) communicating over HTTP REST/SSE via `httpx`.
  - Endpoint: Defaults to `http://127.0.0.1:8080`.
  - Security Guard: Enforces strict loopback verification (`ipaddress.is_loopback` and `localhost`) to prevent SSRF vulnerabilities unless `allow_remote=True` is explicitly specified.
  - Target Model: Qwen3-VL 2B GGUF (`qwen3-vl-2b-instruct-q4_k_m.gguf`) with multimodal projector (`mmproj-f16`), requiring ~2.4 GB VRAM.
  - Image Payload: 2x cropped PNG visual element crops passed as base64-encoded data URIs to `analyze_image`.
  - Health & Probes: `check_health()` pinging `/health` with latency metrics and actionable startup instructions (`llama-server -m models/...`). Probed on startup by `start.py`.

**Cloud Inference (Explicit Opt-In / Privacy-Gated):**
- Groq API (Direct Path):
  - SDK/Client: `groq.Groq` wrapped by `GroqProvider` (`groq_provider.py`).
  - Models: Defaults to `openai/gpt-oss-20b` or `llama-3.3-70b-versatile`.
  - Authentication: `GROQ_API_KEY` resolved with strict precedence (explicit arg → Streamlit session state → `st.secrets` → `os.environ`).
- LiteLLM Multi-Cloud Router:
  - SDK/Client: `litellm` library wrapped by `LiteLLMProvider` (`litellm_provider.py`).
  - Supported Providers: Groq (`groq/*`), OpenAI (`openai/*`), Anthropic (`anthropic/*`).
  - Default Model: `groq/llama-3.3-70b-versatile` (128k context window).
  - Vision Support: Filtered to models with verified vision capabilities (`openai/gpt-4o*`, `anthropic/claude-3*`).
  - Privacy Enforcer: Strict programmatic `_assert_consent()` check requiring `user_consented=True` before transmitting any document payload across external networks.
  - Resilience: Configurable timeouts (default 30.0s) and retry backoff (default 2 retries).

**Local Embeddings (Offline Inference):**
- Hugging Face / Sentence-Transformers:
  - Model: `all-MiniLM-L6-v2` (384-dimensional normalized float32 vectors).
  - Client: `LocalEmbedding` (`local_embedding.py`).
  - Network Requirement: One-time model download cached to local filesystem (`~/.cache/huggingface/hub/`); zero network calls during subsequent execution.
  - Device Pinning: Explicitly pinned to CPU to protect the 4 GB GPU VRAM envelope for VLM inference.

**Document Parsing & Ingestion (Local Compute):**
- Docling (`docling`): CPU-only layout and table extraction using `DocumentConverter` with `PdfPipelineOptions(do_ocr=False, do_table_structure=True)` (`docling_reader.py`).
- RapidOCR (`rapidocr-onnxruntime`): CPU-based ONNX OCR runtime selectively triggered by `should_ocr_page` for pages with text counts below threshold or extraction errors (`ocr_fallback.py`).
- PyMuPDF (`pymupdf` / `fitz`): High-speed PDF rendering for OCR rasterization and vector drawing segmentation for visual bounding-box extraction (`visual_analyzer.py`).

## Data Storage

**Relational & Metadata Storage:**
- SQLite 3 (Python stdlib `sqlite3`):
  - Store: `DocStore` (`doc_store.py`) located at `data/documents.db`.
  - Mode: Write-Ahead Logging (`PRAGMA journal_mode = WAL`) with busy timeout of 5000ms.
  - Lifecycles: Explicit per-operation connection lifecycle context manager (`_connect()`) to prevent Windows file locking issues and Streamlit multi-thread race conditions.
  - Tables:
    - `documents`: Document ID (`doc_<sha16>`), original filename, SHA-256 digest, file size, page count, status, upload time, chunk count.
    - `pages`: Page number, extraction status, character count, chunk count, error details.
    - `chunks`: Chunk ID (`chk_<sha16>_<idx>`), page number, text content, character offsets, extraction source (`docling`, `ocr`, `pypdf`), bounding box JSON.
    - `evidence_elements`: Visual/table evidence IDs, type (`table`, `chart`, `image`), markdown/transcription content, source extractor, model provenance.
    - `summary_cache`: Cached summary results keyed by `doc_id`, profile (`overview`, `detailed`, `study_notes`, `tables_figures`, `findings`), and configuration version.

**Vector & Hybrid Indexing:**
- LanceDB (`lancedb`):
  - Path: `data/lancedb` (`DEFAULT_DB_URI`).
  - Table: `chunks` storing dense vector embeddings (384 dims, cosine metric) alongside full-text inverted indices (FTS BM25).
  - Implementation: `HybridRetriever` (`hybrid_retriever.py`) executing dense vector k-NN and full-text keyword queries, fused via Reciprocal Rank Fusion (`compute_rrf` with default $k=60$).
  - Degradation Seam: Disk-backed in-memory linear cosine search fallback when LanceDB is missing.

**File System & Caching:**
- Uploaded Files: Processed in-memory via `io.BytesIO` after validation (`upload_validation.py`) without writing raw user PDFs to disk.
- Persistence Root: `data/` directory (gitignored) housing `documents.db` and `lancedb/`.
- Local Disk Cache: `.cache/<sha256>/<config_version>/` for document-specific artifact storage (`models.py:cache_dir_for`).

## Authentication & Identity

**User Authentication:**
- None — Designed for local single-user operation.
- Session Isolation: Per-browser session isolation using Streamlit `st.session_state` (`doc_ids`, `indexed_files`, `chat_history`, `cloud_mode`, `user_consented`, `cloud_api_keys`).

**Upstream Provider Credentials:**
- `GROQ_API_KEY`: Groq API authorization token.
- `OPENAI_API_KEY`: OpenAI API authorization token.
- `ANTHROPIC_API_KEY`: Anthropic API authorization token.
- Injection Methods: Local `.env` file (loaded via `python-dotenv`), Streamlit secrets configuration (`st.secrets`), or explicit UI input into session memory.

## Monitoring & Observability

**Telemetry & Profiling:**
- Resource Telemetry (`resource_telemetry.py`):
  - GPU Profiling: Live NVIDIA GPU VRAM metrics queried via `nvidia-smi` with a 5.0-second TTL cache lock to prevent subprocess throttling.
  - Process Memory: Host system RSS and VMS memory tracked via `psutil`.
  - Latency Tracking: Context manager `LatencyTracker` maintaining an in-memory thread-safe rolling history of up to 200 samples per execution stage.
- Performance Benchmarking:
  - `scripts/profile_resources.py`: Measures end-to-end memory and latency benchmarks against the 4 GB VRAM ceiling.
  - `scripts/benchmark_baseline.py` & `scripts/benchmark_multimodal.py`: Benchmarks multimodal QA retrieval, citation accuracy, and abstention behavior.

**Logging:**
- Standard Python logging (`logging.getLogger(__name__)`) across all modules.
- Streamlit notification widgets (`st.status`, `st.error`, `st.info`, `st.warning`) for interactive user diagnostics.

## CI/CD & Deployment

**CI Automation:**
- GitHub Actions workflow `.github/workflows/ci.yml`:
  - Target: Python 3.11 on `ubuntu-latest`.
  - Tooling: Astral `uv` for ultra-fast dependency caching and installation.
  - Lockfile Verification: Strict installation from `requirements-lock.txt` and `requirements-test.txt`.
  - Code Quality: `ruff check .` and `ruff format --check .`.
  - Synthetic Data: `python tests/data/corpus/generate_corpus.py` to synthesize test PDF fixtures without binary repository bloat.
  - Test Suite: Full pytest execution across all 24 test modules (`pytest tests/ -v`).

**Deployment & Launch:**
- Launch Script: `start.py` providing one-command startup with Python version verification, directory scaffolding (`data`, `.cache`, `models`), `llama-server` connectivity checks, and argument forwarding to Streamlit.
- Setuptools Package: `setup.py` defining package metadata for `rag-assistant` with console entry point `rag-assistant=start:main`.

---

*Integrations analysis: 2026-10-13*
*Update after major dependency changes*
