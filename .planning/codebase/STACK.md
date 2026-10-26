# Technology Stack

**Analysis Date:** 2026-10-26

## Languages

**Primary:**
- Python 3.11 (`python_requires=">=3.11"` in `setup.py:812`) - all application code: entry points (`main.py`, `start.py`, `setup.py`), domain packages `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`, and `tests/`. Ruff targets `py311` (`pyproject.toml:3`).
- SQL (SQLite DDL) - schema and migration statements embedded in `core/doc_store.py:131` (`MIGRATIONS` dict, versions 1-4).

**Secondary:**
- TOML - `.streamlit/config.toml`, `pyproject.toml`.
- YAML - `.github/workflows/ci.yml`, `docker-compose.yml`.
- Dockerfile - `Dockerfile` (no custom JavaScript/TypeScript/CSS source; UI styling is injected from `ui/theme.py` and icons are static SVGs in `assets/icons/`).

## Runtime

**Environment:**
- CPython 3.11 (Docker base `python:3.11-slim-bookworm`, `Dockerfile:3`; devcontainer image `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`, `.devcontainer/devcontainer.json`).
- Streamlit web server bound to loopback on port `8501` (`.streamlit/config.toml:15`, `Dockerfile:39`).
- Native `llama-server` (llama.cpp release `b11718`) bound to `127.0.0.1:8080`, managed by `start.py` / `setup.py`.
- Windows 11 (primary, PowerShell) and Linux x86_64 (Docker) supported.

**Package Manager:**
- pip (editable install via `pip install -e .`; dependencies sourced from `requirements.txt` in `setup.py:47-54`).
- uv (CI only: `astral-sh/setup-uv@v5` in `.github/workflows/ci.yml:23-32`; lockfile is uv-compiled).
- Lockfile: present - `requirements-lock.txt` (universal, Python 3.11). Test-only deps in `requirements-test.txt`.

## Frameworks

**Core:**
- Streamlit 1.42.0 - single-user chatbot-first web UI; composition root `main.py`, views `ui/views.py`, components `ui/components.py`, theme `ui/theme.py`.
- Pydantic 2.11.9 - canonical schemas (`core/models.py`, `providers/model_provider.py`: `ProviderCapabilities`, `HealthStatus`).
- LanceDB 0.40.0 + PyArrow 23.0.1 - persistent dense vector table and native BM25 full-text search; RRF fusion in `retrieval/hybrid_retriever.py`.
- sentence-transformers 3.4.1 (with torch 2.14.1, transformers 4.57.6) - CPU-pinned `all-MiniLM-L6-v2` 384-dim L2-normalized embeddings (`retrieval/local_embedding.py:28`).
- Docling 2.138.0 (`docling-core` 2.101.1, `docling-parse` 7.22.2) - layout/reading-order/markdown-table extraction (`ingestion/docling_reader.py`); falls back to `pypdf` 5.3.0.
- RapidOCR (`rapidocr-onnxruntime` on Python <3.13, `rapidocr` on >=3.13; onnxruntime 1.31.0) - CPU OCR fallback (`ingestion/ocr_fallback.py`).
- PyMuPDF 1.28.2 (`import pymupdf as fitz`) - page rasterization, visual-region detection, 2x crops (`ingestion/visual_analyzer.py`).
- httpx 0.28.1 - local llama-server REST/SSE client with loopback enforcement (`providers/llama_cpp_provider.py`).
- LiteLLM 1.105.0 + groq 0.15.0 - optional cloud adapters (`providers/litellm_provider.py`, `providers/groq_provider.py`).
- python-dotenv 1.0.1 - `.env` loading at session start (`main.py:190`).
- langchain-text-splitters 0.3.6 - chunk splitting during ingestion.

**Testing:**
- pytest >=8.3.0 - configured in `pyproject.toml:21-28` (`testpaths = ["tests"]`); 35 test modules.
- reportlab >=4.2.0 - synthetic PDF corpus generator (`tests/data/corpus/generate_corpus.py`).
- Ruff >=0.9.0 - lint + format checks in CI (`.github/workflows/ci.yml:34-37`).

**Build/Dev:**
- setuptools - packaging (`setup.py:805-839`), `find_packages()`.
- Docker / Docker Compose - app image plus optional CUDA llama-server profile (`docker-compose.yml`).
- GitHub Actions - Python 3.11, uv install from lockfile, Ruff, corpus generation, pytest.

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` - the only user-facing surface; no separate HTTP API exists.
- `docling>=2.0.0` (locked 2.138.0) - primary structured extraction; missing package degrades to `pypdf`.
- `lancedb>=0.17.0` (locked 0.40.0) - vector + FTS index at `data/lancedb/`; `retrieval/vector_index.py` is the in-memory fallback.
- `sentence-transformers==3.4.1` - embedding contract is 384 dims; changing models requires re-indexing.
- `pymupdf>=1.24.0` (locked 1.28.2) - required for visual crops and OCR page rendering.
- `pydantic==2.11.9` - frozen schemas shared across UI, storage, and providers.
- `httpx==0.28.1` - local inference transport; strict loopback host allowlist in `providers/llama_cpp_provider.py:90`.
- `psutil==6.1.1` - RSS/VMS telemetry in `core/resource_telemetry.py`.

**Infrastructure:**
- `sqlite3` (stdlib) - metadata store `data/documents.db`, WAL mode, 5s busy timeout (`core/doc_store.py:160-170`).
- `pyarrow>=14.0.0` (locked 23.0.1) - LanceDB columnar transport.
- `numpy>=1.26,<3` (locked 2.4.6) - vector math.
- `pillow>=10.2.0` - image handling for OCR/VLM payloads.
- `litellm` / `groq` - optional cloud egress paths, import-guarded so the app runs without them.
- `python-dotenv` - local secrets/config loading; `.env` is gitignored and absent in the repo.

## Configuration

**Environment:**
- Streamlit config: `.streamlit/config.toml` - AMOLED dark theme, `address = "127.0.0.1"`, CORS and XSRF enabled, `maxUploadSize = 50`, `gatherUsageStats = false`.
- Local runtime env vars (names only):
  - `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` - local provider endpoint (`providers/llama_cpp_provider.py:77-83`).
  - `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - optional cloud credentials (`providers/litellm_provider.py:50-55`, `providers/groq_provider.py:51`, `docker-compose.yml:21-23`).
  - `RAG_LOG_LEVEL` (default `INFO`), `RAG_LOG_DIR` (default `data/logs`) - `core/logging_setup.py:26-28`.
  - `RAG_REQUIRE_CHECKSUMS` - fail closed on unpinned setup downloads (`setup.py:90`).
  - `RAG_ALLOW_NON_LOOPBACK` - required opt-in for non-loopback Streamlit bind (`start.py:40`).
  - `DOCLING_ARTIFACTS_PATH` - Docling model artifacts location (`ingestion/docling_reader.py:192`).
  - `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` - force PyTorch, disable TensorFlow (`main.py:16-18`, `Dockerfile:9-11`).
  - `LITELLM_TELEMETRY=False` - set by default in `providers/litellm_provider.py:19`.
  - `HF_HUB_DISABLE_SYMLINKS_WARNING=1` - optional Windows Hugging Face hint (`docs/RUNBOOK.md:69`).
- No `.env` file present in the working tree; `.gitignore` excludes `.env`, `.env.*` (allowlisting `.env.example`, which is not present).

**Build:**
- `requirements.txt` (runtime pins), `requirements-lock.txt` (resolved lock), `requirements-test.txt`.
- `setup.py` - packaging + `python setup.py download_models` / `setup_llama_server` custom commands; console scripts `rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama`.
- `pyproject.toml` - Ruff (`line-length = 120`, rules `E,F,W,B,UP,SIM`) and pytest config.
- `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.devcontainer/devcontainer.json`.

## Platform Requirements

**Development:**
- Python 3.11+; on Windows use PowerShell; GDAL-free stack (Docling + PyMuPDF + RapidOCR are wheels).
- ~4 GB VRAM NVIDIA GPU for local VLM inference (`-ngl 28`), but the app degrades gracefully when `nvidia-smi` is absent (`core/resource_telemetry.py:86`).
- `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (legacy filename; GGUF metadata is Qwen2-VL-2B-Instruct) and `models/mmproj-f16.gguf`; verified by `core/model_identity.py`.
- `tools/llama-server/llama-server[.exe]` or on `PATH`; provisioned by `python setup.py setup_llama_server`.

**Production:**
- Single-user laptop deployment; Docker Compose maps only `127.0.0.1:8501` (`docker-compose.yml:8`).
- Optional `gpu` compose profile runs `ghcr.io/ggml-org/llama.cpp:server-cuda` on `127.0.0.1:8080` with `-c 4096 -ngl 28`.
- Zero outbound network egress during local operation; model/server downloads are explicit operator CLI actions.

---

*Stack analysis: 2026-10-26*
