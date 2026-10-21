<!-- refreshed: 2026-10-21 -->
# Technology Stack

**Analysis Date:** 2026-10-21

## Languages

**Primary:**
- Python 3.11+ - 100% of application code: `main.py`, `start.py`, `setup.py`, `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`, `tests/`, `scripts/`. Declared in `setup.py` (`python_requires=">=3.11"`) and `pyproject.toml` (`target-version = "py311"`).
- CPython 3.11 is the reference runtime: `Dockerfile` uses `python:3.11-slim-bookworm`; `.github/workflows/ci.yml` uses `python-version: "3.11"`; `start.py:49` enforces `sys.version_info >= (3, 11)` at launch.

**Secondary:**
- Python 3.12 is listed as a supported classifier in `setup.py`; Python 3.13+ takes a different OCR dependency branch (`rapidocr>=3.0.0` instead of `rapidocr-onnxruntime`), declared via environment markers in `requirements.txt:11-12`.
- No JavaScript, TypeScript, or standalone CSS sources. The UI is server-side Streamlit Python; theme CSS is injected as a Python string from `ui/theme.py`, and icons are pre-rendered local SVGs in `assets/icons/`.

## Runtime

**Environment:**
- CPython 3.11 (3.11 recommended; 3.11–3.12 supported, 3.13 handled by conditional OCR wheel markers).
- Streamlit server on port `8501` (`main.py`, `Dockerfile:46`, `.streamlit/config.toml`).
- Native local inference server `llama-server` (llama.cpp release `b11718`) bound to `127.0.0.1:8080` (`start.py:114-175`, `setup.py:374-376`).
- OS: Windows 11 / PowerShell is the primary target; Linux x86_64 and Docker Compose are supported (`docker-compose.yml`, `.devcontainer/devcontainer.json`).

**Package Manager:**
- `pip` for direct installs; `uv` in CI (`astral-sh/setup-uv@v5`) and for lockfile generation (`uv pip compile --universal --python-version 3.11 requirements.txt -o requirements-lock.txt`, header of `requirements-lock.txt:1-2`).
- Lockfile: present and fully pinned — `requirements-lock.txt` (645 lines, universal resolution for Python 3.11). Runtime declarations live in `requirements.txt`; test/benchmark declarations in `requirements-test.txt`.
- Packaging: setuptools via `setup.py` (`rag-assistant` version `1.0.0`), installed editable with `pip install -e .` (`Dockerfile:33`, `README.md:143`).

## Frameworks

**Core:**
- Streamlit `1.42.0` - entire presentation layer and workspace router (`main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`).
- Pydantic `2.11.9` - canonical domain schemas and provider capability/health contracts (`core/models.py`, `providers/model_provider.py`).
- Docling `2.138.0` (lockfile; declared `>=2.0.0`) - structured PDF layout/reading-order/table extraction with CPU-only pipeline (`ingestion/docling_reader.py:175-194`).
- LanceDB `0.40.0` (lockfile; declared `>=0.17.0`) + PyArrow `23.0.1` - persistent dense vector index and native full-text search with RRF fusion (`retrieval/hybrid_retriever.py`).
- sentence-transformers `3.4.1` - CPU-pinned `all-MiniLM-L6-v2` 384-dim embeddings (`retrieval/local_embedding.py`).
- LiteLLM `1.105.0` (Python <3.14) / `1.102.4` (Python >=3.14) - optional cloud adapter (`providers/litellm_provider.py`).
- Groq SDK `0.15.0` - optional direct cloud fallback (`providers/groq_provider.py`).
- httpx `0.28.1` - HTTP/SSE client to local llama-server with loopback/SSRF enforcement (`providers/llama_cpp_provider.py`).

**Testing:**
- pytest `>=8.3.0` (`requirements-test.txt`) - 32 test modules, ~318 `test_` functions under `tests/`; config in `pyproject.toml:20-27` (`testpaths = ["tests"]`, warnings filtered).
- reportlab `>=4.2.0` - synthetic PDF corpus generation (`tests/data/corpus/generate_corpus.py`), run as a CI step.

**Build/Dev:**
- Ruff `>=0.9.0` (declared; local `.ruff_cache/0.15.12` indicates 0.15.12 in use) - lint + format, `line-length = 120`, `target-version = "py311"`, rules `E,F,W` with `E501/W291/W293` ignored (`pyproject.toml:1-17`).
- setuptools `setup.py` with console scripts: `rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:773-779`).
- Docker `python:3.11-slim-bookworm` (`Dockerfile`); Docker Compose with optional CUDA `llama-server` profile (`docker-compose.yml:29-51`).
- GitHub Actions CI: `.github/workflows/ci.yml` (lint, format check, corpus generation, pytest).

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` - renders the four workspaces and owns the single inbound listener.
- `pydantic==2.11.9` - all document/chunk/evidence/result schemas in `core/models.py`.
- `lancedb==0.40.0` + `pyarrow==23.0.1` - durable vector + FTS index at `data/lancedb/`; in-memory `VectorIndex` fallback lives in `retrieval/vector_index.py`.
- `sentence-transformers==3.4.1` (pulls `torch==2.14.1`, `transformers==4.57.6`, `scikit-learn==1.9.1`, `huggingface-hub==0.36.2`) - embeddings pinned to CPU to reserve VRAM.
- `docling==2.138.0` (pulls `docling-core==2.101.1`, `docling-parse==7.22.2`, `docling-ibm-models==4.0.3`) - primary structured PDF reader.
- `pymupdf==1.28.2` - page rasterization and 2x visual crops (`ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`).
- `pypdf==5.3.0` - fallback text extraction and page counting (`ingestion/pdf_reader.py`, `ingestion/upload_validation.py`).
- `rapidocr-onnxruntime==1.4.4` (Python <3.13) / `rapidocr==3.10.0` (Python >=3.13), backed by `onnxruntime==1.31.0` and OpenCV `5.0.0.93` - CPU OCR for scanned pages (`ingestion/ocr_fallback.py`).
- `httpx==0.28.1` - local llama-server transport (blocking, SSE streaming, vision data URIs).
- `litellm==1.105.0` + `openai==2.54.0` + `groq==0.15.0` - optional cloud providers, gated by explicit consent.
- `langchain-text-splitters==0.3.6` (pulls `langchain-core==0.3.86`) - text chunking only; no LangChain agent/chain runtime.

**Infrastructure:**
- `psutil==6.1.1` - RAM/VMS telemetry (`core/resource_telemetry.py`); `nvidia-smi` subprocess for GPU VRAM with 5s cache.
- SQLite via stdlib `sqlite3` (WAL, `PRAGMA user_version` migrations v1–v4) - `core/doc_store.py`.
- `python-dotenv==1.0.1` - loads `.env` when present (`main.py:120`); no `.env` file exists in the workspace.
- `numpy==2.4.6`, `pandas==2.3.3`, `pillow==11.3.0`, `jinja2==3.1.6`, `altair==5.5.0` - transitive/runtime support for embeddings, OCR, Docling, and Streamlit.

## Configuration

**Environment:**
- `.streamlit/config.toml` - dark theme (`#050608`), `server.enableCORS = true`, `server.enableXsrfProtection = true`, `server.maxUploadSize = 50` (MB), `browser.gatherUsageStats = false`.
- `.env` file NOT detected in the repository root; it is gitignored (`.gitignore` line 1) and loaded optionally by `main.py:120` via `python-dotenv`.
- Environment-variable surface (read in code, not secrets):
  - `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` (`providers/llama_cpp_provider.py:51-59`).
  - `DOCLING_ARTIFACTS_PATH` (`ingestion/docling_reader.py:192`).
  - `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (optional cloud only; `providers/litellm_provider.py:51-90`, `providers/groq_provider.py:51`).
  - `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` set at import/launch (`main.py:17-19`, `start.py:34-36`, `retrieval/local_embedding.py:12-14`, `Dockerfile:9-11`).
  - `LITELLM_TELEMETRY=False` set by default (`providers/litellm_provider.py:19-23`).
- Docker Compose passes `LLAMA_SERVER_HOST=host.docker.internal`, `LLAMA_SERVER_PORT=8080`, and optional cloud keys (`docker-compose.yml:14-23`).

**Build:**
- `requirements.txt` (runtime, range-pinned then lock-resolved), `requirements-lock.txt` (exact universal pins), `requirements-test.txt` (pytest/reportlab/ruff/psutil).
- `pyproject.toml` (Ruff + pytest configuration), `setup.py` (setuptools packaging, model/server download CLI), `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.devcontainer/devcontainer.json`, `.github/workflows/ci.yml`.

## Platform Requirements

**Development:**
- Python 3.11+, pip or uv; Windows 11/PowerShell primary, Linux x86_64 supported.
- Optional NVIDIA GPU + driver exposing `nvidia-smi` for VRAM telemetry; CPU-only operation degrades gracefully (`core/resource_telemetry.py:86-90`).
- Local GGUF artifacts required for inference: `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (~986 MB, legacy filename for Qwen2-VL-2B-Instruct weights) and `models/mmproj-f16.gguf` (~1.33 GB), validated by `core/model_identity.py`. Both are gitignored (`models/`, `*.gguf`).
- `llama-server` binary found on `PATH` or `tools/llama-server/` (`start.py:69-80`); installer supports Windows CUDA 12.4, Windows CPU, Linux CUDA 12.8, and Linux CPU builds (`setup.py:483-547`).

**Production:**
- Single-user local deployment: Streamlit bound to `localhost:8501`, llama-server bound to `127.0.0.1:8080`. No external application server or database service.
- Docker Compose: `app` container publishes `127.0.0.1:8501`, mounts `./data`, `./models`, `./.cache`; optional `llama-server` service under the `gpu` profile using `ghcr.io/ggml-org/llama.cpp:server-cuda` with `-c 4096 -ngl 28` and one NVIDIA GPU (`docker-compose.yml:29-51`).
- Target hardware envelope: 4 GB VRAM (RTX 3050 Laptop class), 16 GB system RAM; only one LLM/VLM active at a time, serialized by `InferenceGate` (`core/local_llm.py:25-62`).

---

*Stack analysis: 2026-10-21*
