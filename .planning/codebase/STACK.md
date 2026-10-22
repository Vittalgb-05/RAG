<!-- refreshed: 2026-10-22 -->
# Technology Stack

**Analysis Date:** 2026-10-22

## Languages

**Primary:**
- **Python 3.11+** — all application code: `main.py`, `start.py`, `setup.py`, `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`, `tests/`, and `scripts/`. Declared by `python_requires=">=3.11"` in `setup.py`, `target-version = "py311"` in `pyproject.toml`, and a runtime guard in `start.py` (`sys.version_info < (3, 11)`).
- **CPython 3.11** is the reference runtime: `Dockerfile` uses `python:3.11-slim-bookworm`, `.github/workflows/ci.yml` uses `python-version: "3.11"`, and `.devcontainer/devcontainer.json` uses `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`.
- **Python 3.12** is listed as a supported classifier in `setup.py`; Python 3.13+ switches OCR packages via environment markers (`rapidocr>=3.0.0` instead of `rapidocr-onnxruntime`).

**Secondary:**
- No JavaScript, TypeScript, or standalone CSS. The UI is server-rendered Streamlit Python; AMOLED CSS is injected from a Python string in `ui/theme.py`, and icons are local SVGs under `assets/icons/`.
- Declarative/config formats only: `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `.streamlit/config.toml`, `.github/workflows/ci.yml`, `.devcontainer/devcontainer.json`, Markdown docs in `docs/`.

## Runtime

**Environment:**
- **CPython 3.11** on Windows 11 / PowerShell (primary), Linux x86_64, or Docker.
- **Streamlit** web server on port `8501` (`main.py`, `start.py`, `Dockerfile`, `.streamlit/config.toml`).
- **llama.cpp / llama-server** native inference server (`b11718`) on `127.0.0.1:8080`, launched manually or by `python start.py --start-llama` (`start.py`, `setup.py`).
- **NVIDIA GPU** optional but required for the target VRAM profile; CPU-only operation degrades telemetry and local inference capability gracefully.

**Package Manager:**
- **pip** for direct/editable installs; **uv** in CI (`astral-sh/setup-uv@v5`) and for lockfile generation.
- **Lockfile: canonical and required for reproducible installs — `requirements-lock.txt`** (645 lines), generated with:
  `uv pip compile --universal --python-version 3.11 requirements.txt -o requirements-lock.txt` (header of `requirements-lock.txt:1-2`). CI and `README.md` install from it.
- **`requirements.txt`** is the human-maintained runtime declaration. It mixes exact pins (`streamlit==1.42.0`, `pydantic==2.11.9`, `httpx==0.28.1`, `psutil==6.1.1`) with ranges (`docling>=2.0.0`, `pymupdf>=1.24.0`, `pillow>=10.2.0`, `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `litellm>=1.50.0`, `numpy>=1.26.0,<3.0.0`, RapidOCR markers). Do not treat it as resolved.
- **`requirements-test.txt`** carries test-only ranges (`pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0`).
- **Packaging:** setuptools via `setup.py` (name `rag-assistant`, version `1.0.0`, `packages=find_packages()`, `py_modules=["main", "setup", "start"]`). There is no `[build-system]` table in `pyproject.toml`; `setup.py` is the build entry point.

## Frameworks

**Core:**
- **Streamlit 1.42.0** — the entire presentation layer and workspace router (`main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/session_state.py`).
- **Pydantic 2.11.9** — domain schemas and frozen provider contracts (`core/models.py`, `providers/model_provider.py`).
- **Docling 2.138.0** (lock; declared `>=2.0.0`) — structured PDF layout, reading order, and markdown tables, pinned to CPU (`ingestion/docling_reader.py`).
- **LanceDB 0.40.0 + PyArrow 23.0.1** — persistent dense vector index and native full-text search fused with RRF (`retrieval/hybrid_retriever.py`).
- **sentence-transformers 3.4.1** — CPU-pinned `all-MiniLM-L6-v2` embeddings, 384 dimensions, L2-normalized (`retrieval/local_embedding.py`).
- **httpx 0.28.1** — blocking/SSE HTTP client for local llama-server (`providers/llama_cpp_provider.py`).
- **LiteLLM 1.105.0** (Python <3.14) / **1.102.4** (Python >=3.14), per conditional pins in `requirements-lock.txt` — optional cloud adapter (`providers/litellm_provider.py`).
- **Groq SDK 0.15.0** — optional direct cloud adapter (`providers/groq_provider.py`).

**Testing:**
- **pytest >=8.3.0** — 388 `test_*` functions across 32 `tests/test_*.py` modules (count from source; no `pytest` markers beyond default collection). Config: `pyproject.toml` (`testpaths=["tests"]`, `python_files=["test_*.py"]`, filters `UserWarning`/`DeprecationWarning`).
- **reportlab >=4.2.0** — generates six synthetic PDFs in `tests/data/corpus/generate_corpus.py`, including a CI generation step.

**Build/Dev:**
- **Ruff >=0.9.0** — lint and format. `pyproject.toml`: `line-length = 120`, `target-version = "py311"`, `select = ["E", "F", "W", "B", "UP", "SIM"]`, `ignore = ["E501", "W291", "W293"]`; per-file ignores `scripts/* = ["E402"]` and `start.py = ["UP036"]`.
- **setuptools CLI commands** — `download_models`, `setup_llama_server` (`setup.py`), plus console scripts `rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama`.
- **Docker** — `python:3.11-slim-bookworm` image installing `build-essential`, `curl`, `libgl1`, `libglib2.0-0`, `libgomp1`.
- **Docker Compose** — `app` service plus an optional CUDA `llama-server` service under the `gpu` profile.
- **GitHub Actions** — `.github/workflows/ci.yml` (lint, format check, corpus generation, pytest).
- **Dev container** — `.devcontainer/devcontainer.json`, Python 3.11 Bookworm, forwards port 8501.

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` — the only inbound listener and the whole UI.
- `pydantic==2.11.9` — `BBox`, `Chunk`, `Page`, `Document`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult` in `core/models.py`; `ProviderCapabilities` and `HealthStatus` in `providers/model_provider.py`.
- `lancedb==0.40.0` + `pyarrow==23.0.1` — durable `chunks` table at `data/lancedb/`, FTS on `content`, and `compute_rrf` in `retrieval/hybrid_retriever.py`; in-memory `VectorIndex` fallback in `retrieval/vector_index.py`.
- `sentence-transformers==3.4.1` — pulls `torch==2.14.1`, `transformers==4.57.6`, `scikit-learn==1.9.1`, `huggingface-hub==0.36.2` (lock).
- `docling==2.138.0` — pulls `docling-slim==2.138.0`, `docling-core==2.101.1`, `docling-parse==7.22.2`, `docling-ibm-models==4.0.3` (lock).
- `pymupdf==1.28.2` (`import pymupdf as fitz`) — page rasterization and 2x visual crops (`ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`).
- `pypdf==5.3.0` — fallback text extraction, page counting, and magic-byte validation (`ingestion/pdf_reader.py`, `ingestion/upload_validation.py`).
- `rapidocr-onnxruntime==1.4.4` (Python <3.13) / `rapidocr==3.10.0` (>=3.13), with `onnxruntime==1.31.0` and `opencv-python==5.0.0.93` — CPU OCR fallback (`ingestion/ocr_fallback.py`).
- `httpx==0.28.1` — llama-server transport, including SSE streaming and base64 vision payloads.
- `litellm==1.105.0`, `openai==2.54.0`, `groq==0.15.0` — optional cloud inference.
- `langchain-text-splitters==0.3.6` (pulls `langchain-core==0.3.86`) — chunking only; no LangChain agents/chains.
- `numpy==2.4.6`, `pillow==11.3.0`, `pandas==2.3.3` — embedding, raster, and Docling/Streamlit support.
- `python-dotenv==1.0.1` — optional `.env` loading in `main.py`.

**Infrastructure:**
- SQLite via stdlib `sqlite3` — WAL mode, `busy_timeout=5000`, `foreign_keys=ON`, `PRAGMA user_version` migrations v1–v4 (`core/doc_store.py`).
- `psutil==6.1.1` + `nvidia-smi` subprocess — RAM/VMS and GPU VRAM telemetry with a 5-second TTL cache (`core/resource_telemetry.py`).
- `altair==5.5.0`, `jinja2==3.1.6`, `faker==40.43.0` — Streamlit/Docling transitive dependencies (lock only).

## Configuration

**Environment:**
- `.streamlit/config.toml`: dark theme (`#050608`), `server.address = "127.0.0.1"`, `enableCORS = true`, `enableXsrfProtection = true`, `maxUploadSize = 50` MB, `browser.gatherUsageStats = false`.
- No `.env` file is present in the workspace, and no `.env.example` exists. `.env`/`.env.*` are gitignored; `main.py` calls `load_dotenv()` so an operator-created `.env` is honored.
- No `.streamlit/secrets.toml` is present. `providers/litellm_provider.py` and `providers/groq_provider.py` read secrets only if Streamlit provides them.
- Environment surface actually read by code:
  - `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` — local provider endpoint (`providers/llama_cpp_provider.py`).
  - `DOCLING_ARTIFACTS_PATH` — local Docling model artifacts directory (`ingestion/docling_reader.py`).
  - `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — cloud mode only.
  - `RAG_LOG_LEVEL` (default `INFO`), `RAG_LOG_DIR` (default `data/logs`) — `core/logging_setup.py`.
  - `RAG_REQUIRE_CHECKSUMS` — when truthy, `setup.py` refuses any download without a pinned SHA-256.
  - `RAG_ALLOW_NON_LOOPBACK` — allows the Streamlit bind guard in `start.py` to be bypassed.
  - `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` — set by default in `main.py`, `start.py`, `setup.py`, and `retrieval/local_embedding.py`.
  - `LITELLM_TELEMETRY=False` — set by `providers/litellm_provider.py`.
- Docker/Compose environment: `PYTHONUNBUFFERED=1`, `USE_TF=0`, `USE_TORCH=1`, `LLAMA_SERVER_HOST=host.docker.internal`, `LLAMA_SERVER_PORT=8080`, optional cloud keys; `app` publishes only `127.0.0.1:8501` and the GPU-profile `llama-server` only `127.0.0.1:8080`.
- Docker note: `Dockerfile` installs `pip install -r requirements.txt`, not the canonical lockfile. CI and README use `requirements-lock.txt`; treat the Dockerfile as a reproducibility gap when changing dependencies.

**Build:**
- `requirements.txt`, `requirements-lock.txt`, `requirements-test.txt`.
- `pyproject.toml` — Ruff and pytest configuration only.
- `setup.py` — setuptools packaging, model/server download CLI, and **SHA-256 integrity pinning**:
  - `MODEL_REGISTRY` pins `qwen3-vl-2b-instruct-q4_k_m.gguf` and `mmproj-f16.gguf` with `sha256` values and minimum sizes (`800_000_000` and `500_000_000` bytes). The `qwen3-vl` filename is a legacy artifact name; GGUF metadata reports Qwen2-VL (`core/model_identity.py`).
  - `LLAMA_ARCHIVE_SHA256` pins Windows CUDA 12.4, Windows CPU, Linux CPU, and Linux CUDA 12.8 archives from llama.cpp release `b11718`.
  - Downloads verify size and digest, write to a `.tmp` file, and only then replace the destination. Archive extraction rejects path traversal and skips symlinks/hardlinks (`safe_extract_archive`).
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.devcontainer/devcontainer.json`, `.github/workflows/ci.yml`.

## Data & Cache Layout

- `data/documents.db` — SQLite source of truth; `data/lancedb/` — LanceDB index; `data/logs/app.log` — rotating file log (5 MB x 3 backups).
- `models/` — GGUF weights and projector (gitignored); `tools/llama-server/` — native server binary (gitignored).
- `.cache/` is still mounted in `docker-compose.yml` and removed on document delete/purge, but **the write-only extraction cache has been removed**: `IngestionService` no longer writes `pages.json`, `chunks.json`, or `manifest.json`. `ui/ingestion_service.py` stores a `cache_dir` path only; `ui/lifecycle_service.py` and `core/models.py::cache_dir_for` use it solely for best-effort cleanup. `CONFIG_VERSION = "docling-1000-200-v1"` remains for summary-cache keying and legacy path cleanup.
- `.gitignore` excludes `data/`, `.cache/`, `models/`, `tools/`, `*.gguf`, `*.onnx`, `*.lance`, and database journals.

## Platform Requirements

**Development:**
- Python 3.11+, pip or uv; Windows 11/PowerShell primary, Linux x86_64 supported.
- NVIDIA driver with `nvidia-smi` for VRAM telemetry and GPU inference; CPU-only hosts still run OCR, Docling, and embeddings.
- Local GGUF artifacts expected in `models/`: `qwen3-vl-2b-instruct-q4_k_m.gguf` and `mmproj-f16.gguf`; identity verified by `core/model_identity.py` and `start.py` before launch.
- `llama-server` on `PATH` or in `tools/llama-server/`. Installer supports Windows CUDA 12.4, Windows CPU, Linux CUDA 12.8, and Linux CPU.
- Target envelope: 4 GB VRAM (RTX 3050 Laptop class), 16 GB RAM, one active LLM/VLM serialized by `InferenceGate` (`core/local_llm.py`), context 4096 tokens, `-ngl 28`.

**Production:**
- Single-user local deployment: Streamlit bound to loopback `:8501`, llama-server bound to loopback `:8080`. No external application server, database service, or auth provider.
- Docker Compose: `app` container with host-mounted `./data`, `./models`, `./.cache`; optional `llama-server` from `ghcr.io/ggml-org/llama.cpp:server-cuda` with `-c 4096 -ngl 28` and one NVIDIA GPU.
- Windows executable staging: `tools/llama-server` is populated by `python setup.py setup-llama` / `--llama-only`.

---

*Stack analysis: 2026-10-22*
