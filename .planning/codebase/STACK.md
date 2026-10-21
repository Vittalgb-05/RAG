# Technology Stack

**Analysis Date:** 2026-10-21

## Languages

**Primary:**
- Python 3.11+ — all application code: `main.py`, `start.py`, `setup.py`, `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`, `scripts/`, `tests/`. Requirement declared in `setup.py` (`python_requires=">=3.11"`), enforced at launch in `start.py:49-54`, targeted by Ruff (`target-version = "py311"` in `pyproject.toml`), and used by CI (`.github/workflows/ci.yml`) and Docker (`Dockerfile`).

**Secondary:**
- SQL — SQLite DDL/migrations and queries in `core/doc_store.py` (`SCHEMA_V1_DDL` … `SCHEMA_V4_DDL`); LanceDB SQL filter strings in `retrieval/hybrid_retriever.py` (`_escape_sql_literal`).
- Inline HTML/CSS — AMOLED theme and card styling injected from `ui/theme.py`, `ui/components.py`, `main.py`; local SVG iconography in `assets/icons/*.svg`.
- PowerShell / Bash — operational commands only (documented in `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`).

- **No JavaScript, TypeScript, CSS, or frontend build toolchain.** The UI is server-rendered Streamlit with injected CSS strings.

## Runtime

**Environment:**
- CPython 3.11 (Docker base `python:3.11-slim-bookworm`; CI `python-version: "3.11"`; devcontainer `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`).
- Streamlit web server on port `8501` (`main.py`, `start.py:181-198`, `.streamlit/config.toml`).
- Native `llama-server` (llama.cpp C++ binary, release `b11718`) bound to loopback `127.0.0.1:8080` (`start.py:114-178`, `providers/llama_cpp_provider.py`).
- Optional NVIDIA CUDA 12.x runtime for GPU offload (`-ngl 28`); CPU-only operation is supported with graceful degradation.

**Package Manager:**
- pip (`requirements.txt`, `requirements-test.txt`, `requirements-lock.txt`; `pip install -e .`).
- uv used to compile the lockfile and to install in CI: `# uv pip compile --universal --python-version 3.11 requirements.txt -o requirements-lock.txt` (header of `requirements-lock.txt`), `astral-sh/setup-uv@v5` in `.github/workflows/ci.yml`.
- Lockfile: **present** — `requirements-lock.txt` (645 lines, universal, Python 3.11).
- Packaging: setuptools via legacy `setup.py` (`name="rag-assistant"`, version `1.0.0`); `pyproject.toml` contains only Ruff and pytest config (no `[build-system]`, no PEP 621 metadata).

**Pinned runtime versions (from `requirements-lock.txt`):**

| Package | Locked Version | Role |
|---------|----------------|------|
| `streamlit` | 1.42.0 | Presentation server and UI runtime |
| `pydantic` | 2.11.9 | Canonical schemas in `core/models.py`, `providers/model_provider.py` |
| `lancedb` | 0.40.0 | Persistent vector + FTS index |
| `pyarrow` | 23.0.1 | Arrow schema and table I/O for LanceDB |
| `docling` | 2.138.0 | Layout/table extraction |
| `pymupdf` | 1.28.2 | PDF rasterization, visual crops |
| `sentence-transformers` | 3.4.1 | CPU embeddings (`all-MiniLM-L6-v2`) |
| `torch` | 2.14.1 | Backend for sentence-transformers |
| `transformers` | 4.57.6 | Transitive model runtime |
| `onnxruntime` | 1.31.0 | RapidOCR execution backend |
| `rapidocr` | 3.10.0 | OCR on Python >= 3.13 |
| `rapidocr-onnxruntime` | 1.4.4 | OCR on Python < 3.13 |
| `httpx` | 0.28.1 | llama-server HTTP/SSE client |
| `litellm` | 1.105.0 (<3.14) / 1.102.4 (>=3.14) | Cloud provider adapter |
| `groq` | 0.15.0 | Direct Groq SDK adapter |
| `numpy` | 2.4.6 | Vector math (declared `>=1.26.0,<3.0.0`) |
| `pillow` | 11.3.0 | Image encoding for VLM crops |
| `psutil` | 6.1.1 | Process RAM telemetry |
| `langchain-text-splitters` | 0.3.6 | `RecursiveCharacterTextSplitter` chunking |
| `python-dotenv` | 1.0.1 | `.env` loading in `main.py` |
| `pypdf` | 5.3.0 | Text extraction fallback + magic-byte validation |
| `tiktoken` | 0.14.0 | Transitive tokenizer dependency |

Source declarations in `requirements.txt` use ranges/lower bounds (e.g. `docling>=2.0.0`, `lancedb>=0.17.0`, `pymupdf>=1.24.0`, `litellm>=1.50.0`); the lockfile is the deterministic install source for CI and is recommended in `docs/RUNBOOK.md`.

## Frameworks

**Core:**
- Streamlit 1.42.0 — chatbot-first AMOLED UI, four workspaces (Chat, Summarizer, Document Library, Settings), `st.dialog` consent modal in `main.py:232-244`.
- Pydantic 2.11.9 — frozen/validated models: `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult` (`core/models.py`); `ProviderCapabilities`, `HealthStatus`, `BaseModelProvider` ABC (`providers/model_provider.py`).
- LanceDB 0.40.0 + PyArrow 23.0.1 — persistent vector table, native FTS index on `content`, dense search, RRF fusion (`retrieval/hybrid_retriever.py`).
- SQLite (stdlib `sqlite3`) — metadata source of truth, WAL mode, schema migrations v1–v4, summary cache (`core/doc_store.py`).
- Docling 2.138.0 — structured layout/reading-order and markdown table extraction with `pypdf` fallback (`ingestion/docling_reader.py`).
- RapidOCR (ONNX) — conditional OCR for pages with < 50 characters (`ingestion/ocr_fallback.py`).
- PyMuPDF 1.28.2 (`import pymupdf as fitz`) — page rasterization, 2× visual crops (`ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`).
- sentence-transformers 3.4.1 — CPU-pinned 384-dim L2-normalized embeddings, process-level model cache (`retrieval/local_embedding.py`).
- httpx 0.28.1 — llama-server REST/SSE client with loopback allowlist and explicit timeouts (`providers/llama_cpp_provider.py`).
- LiteLLM 1.105.0 — consent-gated cloud completions for Groq/OpenAI/Anthropic (`providers/litellm_provider.py`).
- groq 0.15.0 — direct Groq SDK fallback provider (`providers/groq_provider.py`).
- langchain-text-splitters 0.3.6 — chunk sizing in `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`.

**Testing:**
- pytest >= 8.3.0 — config in `pyproject.toml` (`testpaths = ["tests"]`, `python_files = ["test_*.py"]`, warning filters).
- `unittest.mock` (`MagicMock`, `monkeypatch`) and `httpx.MockTransport` — offline provider/embedding/GPU tests (`tests/conftest.py`).
- reportlab >= 4.2.0 — synthetic PDF corpus generator `tests/data/corpus/generate_corpus.py`.
- 296 test functions across `tests/` (README/EVALUATION quote 248 at an earlier revision).

**Build/Dev:**
- Ruff >= 0.9.0 — `ruff check .` and `ruff format --check .`; config `pyproject.toml` (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`, `ignore = ["E501","W291","W293"]`, `scripts/*` ignores `E402`).
- setuptools — `setup.py` custom commands (`download_models`, `setup_llama_server`) and console scripts.
- uv — lockfile compilation and CI installation.
- Docker / Docker Compose — app image plus optional CUDA llama-server service.
- GitHub Actions — single `test` job (`.github/workflows/ci.yml`).

## Key Dependencies

**Critical:**
- `llama.cpp` `llama-server` `b11718` — **not a pip dependency.** Downloaded per-platform by `setup.py:288-493` from `https://github.com/ggml-org/llama.cpp/releases/download/b11718` (fallback mirror `ggml-org` → `ggerganov`) into `tools/llama-server/`; launched by `start.py` or Docker Compose.
- Qwen2-VL 2B Instruct GGUF — `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (~986 MB on disk) and `models/mmproj-f16.gguf` (~1.33 GB on disk). Registered download sources in `setup.py:59-78` (bartowski and lmstudio-community Hugging Face mirrors). Local filename says "qwen3-vl" but the registry sources are Qwen2-VL 2B.
- `all-MiniLM-L6-v2` — 384-dim embedding model, CPU device, shared process cache (`retrieval/local_embedding.py:18-45`), pre-cached by `setup.py:196-213`.
- PyMuPDF (`pymupdf`) — **AGPL-3.0 / commercial dual license**, called out in `docs/LICENSES.md`; distribution constraint for downstream packaging.
- Docling — heavy transitive dependency tree (docling-core, docling-ibm-models, docling-parse, accelerate, scikit-learn, scipy, etc. in `requirements-lock.txt`).

**Infrastructure:**
- `psutil` 6.1.1 — RSS/VMS telemetry (`core/resource_telemetry.py:169-194`).
- `nvidia-smi` (system binary) — GPU VRAM/utilization with 5 s TTL cache (`core/resource_telemetry.py:33-97`).
- `httpx` — all local inference traffic; custom transports used for tests.
- `python-dotenv` — loads `.env` when the AI model is first created (`main.py:151`).

**Optional / degradable:**
- `docling` — falls back to `ingestion/pdf_reader.py` (pypdf) on import failure or conversion error.
- `lancedb`/`pyarrow` — falls back to pure-Python `retrieval/vector_index.py` plus persisted `fallback_store.json` in `retrieval/hybrid_retriever.py`.
- `rapidocr`/`rapidocr_onnxruntime` — OCR skipped if unavailable.
- `litellm`/`groq` — cloud providers report `unreachable` health if missing.

## Configuration

**Environment:**
- `.env` loaded via `python-dotenv` in `main.py:151`; `.env` is git-ignored (`.gitignore`) and **not present** in the working tree.
- Streamlit secrets read opportunistically via `st.secrets` (`providers/groq_provider.py:39-44`, `providers/litellm_provider.py:74-85`); no `.streamlit/secrets.toml` present.
- API keys are held in session memory (`st.session_state.cloud_api_keys`) and never written to disk.
- Environment variables consumed at runtime:
  - `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` (`providers/llama_cpp_provider.py:44-54`)
  - `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (`providers/litellm_provider.py:44-88`, `providers/groq_provider.py:37-47`)
  - `LITELLM_TELEMETRY=False` default (`providers/litellm_provider.py:19-24`)
  - `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` (`main.py:16-18`, `start.py:34-36`, `retrieval/local_embedding.py:12-14`, `setup.py:200-201`, `tests/conftest.py:9-11`)
- `.streamlit/config.toml`: dark base theme (`#050608`, primary `#B9A3FF`), `enableCORS = true`, `enableXsrfProtection = true`, `maxUploadSize = 50` (MB), `gatherUsageStats = false`.
- `docker-compose.yml` passes `LLAMA_SERVER_HOST=host.docker.internal`, `LLAMA_SERVER_PORT=8080`, and optional `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` from host environment.

**Build:**
- `Dockerfile` — Python 3.11 slim; installs `build-essential`, `curl`, `libgl1`, `libglib2.0-0`, `libgomp1`; installs `requirements.txt` (not the lockfile), then `pip install -e .`; creates `data/`, `models/`, `.cache/`; exposes `8501`; healthcheck `curl -f http://localhost:8501/_stcore/health`.
- `docker-compose.yml` — `app` service (bind `127.0.0.1:8501:8501`, mounts `./data`, `./models`, `./.cache`) and optional `llama-server` service under profile `gpu` using `ghcr.io/ggml-org/llama.cpp:server-cuda` with `-c 4096 -ngl 28`.
- `pyproject.toml` — lint/test configuration only.
- `setup.py` — packaging metadata, `MODEL_REGISTRY`, llama.cpp release acquisition, custom setuptools commands, CLI entry points.
- `.dockerignore` — excludes `.env`, `tests/`, `data/`, `models/`, `.planning/`, caches.
- `.github/workflows/ci.yml` — Python 3.11 on `ubuntu-latest`; installs lockfile + test requirements + editable package with `--no-deps`; runs Ruff check, Ruff format check, corpus generation, `pytest tests/ -v`.
- `.devcontainer/devcontainer.json` — Python 3.11 bookworm image, forwards `8501`, runs Streamlit.

## Platform Requirements

**Development:**
- Windows 11 (primary, PowerShell) or Linux x86_64; Python 3.11+.
- NVIDIA GPU optional; CUDA 12.x driver 550+ recommended for GPU offload (`docs/LOCAL_INFERENCE.md`, `docs/RUNBOOK.md`).
- 16 GB system RAM, ~10 GB free SSD for models + caches.
- `llama-server` binary on `PATH` or in `tools/llama-server/` (`start.py:69-79`).
- System `nvidia-smi` for GPU telemetry (gracefully absent).

**Production:**
- Single-user local workstation; Streamlit on `localhost:8501` and llama-server on `127.0.0.1:8080` (`docs/RUNBOOK.md` §8).
- Docker Compose as the supported container target, with optional CUDA GPU profile; no hosted/cloud deployment pipeline.
- Cloud mode works from any host with outbound HTTPS, but local inference is unreachable from hosted environments (`README.md` deployment notes).

---

*Stack analysis: 2026-10-21*
