---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# Technology Stack

**Analysis Date:** 2026-11-14

## Languages

**Primary:**
- Python 3.11+ - Backend API, ingestion/retrieval pipeline, model providers, launcher and setup tooling. Minimum declared in `pyproject.toml` (`target-version = "py311"`), `setup.py` (`python_requires=">=3.11"`), and CI (`.github/workflows/ci.yml`, Python 3.11). `requirements.txt` has Python-version markers covering 3.13 (`rapidocr>=3.0.0; python_version >= "3.13"`).
- TypeScript 5.8 / TSX - All frontend code under `frontend/src/`.

**Secondary:**
- SQL (SQLite dialect) - Schema DDL and queries in `core/doc_store.py`.
- Dockerfile / YAML - Deployment and CI configuration in `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`.

## Runtime

**Environment:**
- Python 3.11-slim-bookworm container runtime (`Dockerfile` line 12); host development on Windows 11 or Linux x86_64 (`docs/RUNBOOK.md`).
- Node.js 20 (build stage only) for the Next.js static export (`Dockerfile` lines 2-9).
- ASGI server: Uvicorn (`uvicorn==0.54.0` in `requirements-lock.txt`; declared `uvicorn[standard]>=0.30.0` in `requirements.txt`).
- Concurrency model: single-process FastAPI app with `threading` workers for inference/jobs (`api/streaming.py`, `api/jobs.py`, `core/local_llm.py::InferenceGate`), plus a daemon hydration thread (`api/container.py`).

**Package Manager:**
- Backend: `pip` for installs, `uv` for lockfile compilation and CI installs. `requirements-lock.txt` header records `uv pip compile --universal --python-version 3.11 requirements.txt`.
- Frontend: `pnpm` (version 9 in CI via `pnpm/action-setup@v4`; `Dockerfile` activates `pnpm@latest` through corepack).
- Lockfiles: backend `requirements-lock.txt` (present), frontend `frontend/pnpm-lock.yaml` (present).

## Frameworks

**Core:**
- FastAPI >=0.115.0 - HTTP API, routing, dependency injection, static frontend mount (`api/main.py`, `api/routers/*.py`). Starlette is the underlying ASGI toolkit (`starlette==1.10.0` in lockfile).
- Pydantic 2.11.9 / pydantic-settings 2.15.0 - API schemas and env-driven settings (`api/schemas/*.py`, `api/config.py`).
- Next.js 15.2.1 (App Router, `output: "export"` static export) - Frontend application (`frontend/src/app/`, `frontend/next.config.mjs`).
- React 19 - UI runtime (`frontend/package.json`).
- Tailwind CSS 4.0.9 via `@tailwindcss/postcss` - Styling (`frontend/postcss.config.mjs`, `frontend/src/styles/globals.css`).

**Testing:**
- pytest >=8.3.0 - Test runner; configuration in `pyproject.toml` (`testpaths = ["tests"]`).
- reportlab >=4.2.0 - Synthetic PDF corpus generation for tests.
- ruff >=0.9.0 - Lint and format checks in CI (also the formatter, not Black).

**Build/Dev:**
- Ruff - Linter/formatter config in `pyproject.toml` (`line-length = 120`, rules `E,F,W,B,UP,SIM`).
- Docker multi-stage build - Node frontend build then Python runtime (`Dockerfile`).
- Docker Compose - `app` service plus optional GPU `llama-server` profile (`docker-compose.yml`).
- GitHub Actions - `.github/workflows/ci.yml` (backend lint/contract/tests, frontend typecheck/static build).
- pnpm scripts - `dev`, `build`, `start`, `lint`, `typecheck` (`frontend/package.json`).

## Key Dependencies

**Critical:**
- `lancedb==0.40.0` + `pyarrow==23.0.1` - Persistent vector table `chunks` with 384-dim vectors and full-text index (`retrieval/hybrid_retriever.py`).
- `sentence-transformers==3.4.1` / `torch==2.14.1` - Local embeddings with `all-MiniLM-L6-v2`, CPU-pinned, 384 dimensions, 256-token truncation (`retrieval/local_embedding.py`).
- `docling==2.138.0` - Primary PDF layout/table extraction, gracefully falls back to pypdf (`ingestion/docling_reader.py`).
- `rapidocr==3.10.0` (Python >= 3.13) or `rapidocr-onnxruntime==1.4.4` (Python < 3.13) - Conditional OCR on low-text pages via ONNX Runtime CPU (`ingestion/ocr_fallback.py`).
- `pymupdf==1.28.2` (`>=1.24.0,<2.0`) - Page rasterization and crops for OCR/vision (`ingestion/visual_analyzer.py`, `ingestion/ocr_fallback.py`).
- `pypdf==6.21.4` - Validation and text-extraction fallback (`ingestion/upload_validation.py`, `ingestion/pdf_reader.py`).
- `langchain-text-splitters==0.3.6` - `RecursiveCharacterTextSplitter` chunking (`ingestion/docling_reader.py`, `ingestion/pdf_reader.py`).
- `litellm==1.105.0` - Cloud provider adapter for Groq/OpenAI/Anthropic with consent gating (`providers/litellm_provider.py`).
- `groq==0.15.0` - Direct Groq SDK provider (`providers/groq_provider.py`).
- `httpx==0.28.1` - HTTP client to local `llama-server` (`providers/llama_cpp_provider.py`).
- `numpy==2.4.6` - Embedding arrays and vector math (`retrieval/local_embedding.py`, `retrieval/vector_index.py`).

**Infrastructure:**
- `psutil==6.1.1` - Process RAM/CPU telemetry (`core/resource_telemetry.py`, `api/routers/system.py`).
- `python-multipart==0.0.32` - Multipart PDF uploads (`api/routers/documents.py`).
- `python-dotenv==1.0.1` - `.env` loading for pydantic-settings and setup/launcher.
- `pillow==11.3.0` - Image handling for cropped page/figure analysis; ceiling `<13` imposed by Docling.
- `tiktoken==0.14.0` (transitive in lockfile) - present in the environment but prompt budgeting uses a character heuristic, not tiktoken (`core/prompt_budget.py`).
- Frontend: `@tanstack/react-query` 5.67 (server-state cache), `zustand` 5.0 (client store), `zod` 3.24 (validation), `eventsource-parser` 3.0 (SSE), `react-markdown`/`remark-gfm`/`rehype-sanitize` (rendering), `cmdk`, `sonner`, `lucide-react`, `motion`, `clsx`, `tailwind-merge` (`frontend/package.json`).

## Configuration

**Environment:**
- Backend settings are loaded by `pydantic-settings` with prefix `RAG_` and `.env` (`api/config.py`): `RAG_API_HOST`, `RAG_API_PORT`, `RAG_ALLOW_NON_LOOPBACK`, `RAG_CORS_ORIGINS`, `RAG_ALLOWED_HOSTS`, `RAG_SERVE_FRONTEND`, `RAG_PERSIST_CHAT`, `RAG_STORE_ORIGINALS`, `RAG_DATA_DIR`, `RAG_LOG_DIR`, `RAG_LOG_LEVEL`.
- `.env.example` documents provider/model/inference variables: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT`, `DOCLING_ARTIFACTS_PATH`, `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`.
- Additional runtime variables read directly in code: `RAG_ALLOW_ENV_KEYS` (`providers/litellm_provider.py`, `providers/groq_provider.py`), `RAG_VENV_PATH` (`setup.py`, `start.py`), `LITELLM_TELEMETRY` (forced off in `providers/litellm_provider.py`), `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` (`start.py`, `Dockerfile`, `retrieval/local_embedding.py`).
- Frontend variables (`frontend/.env.example`): `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`), `NEXT_PUBLIC_USE_MOCKS` (`1` enables `frontend/src/lib/api/mocks.ts`).
- Secrets are not stored in the repo; `.env` is the local mechanism and cloud API keys are held in process memory only (`api/cloud_state.py`).

**Build:**
- `pyproject.toml` - Ruff + pytest configuration.
- `requirements.txt` / `requirements-lock.txt` - direct ranges and pinned universal lock.
- `frontend/next.config.mjs` - static export, unoptimized images, trailing slashes.
- `frontend/tsconfig.json` - strict TypeScript, `@/*` -> `./src/*` alias.
- `Dockerfile` / `docker-compose.yml` - image build and service topology.

## Platform Requirements

**Development:**
- Python 3.11+ with a virtual environment at `.venv` by default (`setup.py` `DEFAULT_VENV_DIRNAME`).
- Node.js 20 + pnpm 9 to build/serve the frontend.
- Optional NVIDIA GPU with 4 GB VRAM and CUDA 12.x for local vision-language inference (`docs/LOCAL_INFERENCE.md`).
- `llama-server` binary at `tools/llama-server/` or on `PATH`; expected llama.cpp v0.8.0 build `b11960` (`core/runtime_info.py`).

**Production:**
- Container image exposing port 8000 (`Dockerfile` `EXPOSE 8000`); `docker-compose.yml` publishes `127.0.0.1:8000` only.
- Persistent mounts: `./data` (SQLite + LanceDB + logs), `./models` (GGUF weights), `./.cache`.
- Single-user deployment with no authentication; loopback binding is enforced unless `RAG_ALLOW_NON_LOOPBACK=1` (`start.py`, `api/config.py`).

## Version and Packaging Notes

- `requirements-lock.txt` is generated from `requirements.txt`, but **does not contain a `fastapi` pin** (verified: no `fastapi` entry in the file), even though `Dockerfile` installs only the lockfile. Starlette, Uvicorn, and Pydantic are pinned. Treat `fastapi` as installed transitively only if the chosen base already provides it; this is a packaging gap to verify before relying on the Docker image.
- `requirements-lock.txt` still contains `streamlit==1.66.1` and `pandas==2.3.3`, but no application module imports Streamlit (only `tests/test_logging_setup.py` references `streamlit.watcher`). These are historical residue from the pre-FastAPI UI.
- `README.md` badges/architecture and `docs/ENDPOINT_INTEGRATION_MATRIX.md` still describe a Streamlit single-process UI; the implemented runtime is FastAPI + Next.js static export (`api/main.py`, `frontend/next.config.mjs`).
- `.devcontainer/devcontainer.json` still provisions Streamlit on port 8501; it does not match the current FastAPI/Next.js workflow.

---

*Stack analysis: 2026-11-14*
