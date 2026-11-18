---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# External Integrations

**Analysis Date:** 2026-11-14

## APIs & External Services

**Local LLM inference (default, no egress):**
- `llama-server` (llama.cpp v0.8.0, build `b11960`) - Serves the Qwen3.5-2B GGUF model and F16 vision projector over a local OpenAI-compatible REST API.
  - SDK/Client: `httpx==0.28.1` in `providers/llama_cpp_provider.py`
  - Endpoints used: `GET /health`, `POST /v1/chat/completions` (blocking, SSE streaming, and vision data-URI payloads)
  - Base URL resolution: `LLAMA_SERVER_URL`, else `http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}` with defaults `127.0.0.1:8080` (`providers/llama_cpp_provider.py` lines 88-95)
  - Auth: none; loopback/host allow-list guard rejects non-local URLs (`localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server`) unless `allow_remote=True`
  - Serialization: process-wide `InferenceGate` reentrant lock ensures one GPU inference at a time (`core/local_llm.py`)
  - Model artifacts: `models/qwen3.5-2b-q4_k_m.gguf` + `models/qwen3.5-2b-mmproj-f16.gguf`, downloaded from Hugging Face `SoAIHQ/Qwen3.5-2B-GGUF` at pinned revision `377fa65bb36aa83414de1ab3b40f6f15b0324cdc` with SHA-256 checks (`setup.py`, `docs/LOCAL_INFERENCE.md`)

**Cloud LLM inference (optional, consent-gated):**
- LiteLLM - Unified client to Groq, OpenAI, and Anthropic (`providers/litellm_provider.py`).
  - SDK/Client: `litellm==1.105.0` (lockfile)
  - Default model: `groq/llama-3.3-70b-versatile` (`DEFAULT_CLOUD_MODEL`)
  - Supported providers/models: any LiteLLM model ID; UI settings accept `groq`, `openai`, `anthropic` (`api/schemas/settings.py`); vision support detected for `openai/gpt-4o*`, `anthropic/claude-3*` prefixes
  - Auth: API key supplied at runtime via `PUT /api/v1/settings/cloud` and held only in memory as `pydantic.SecretStr` (`api/cloud_state.py`); environment keys are read only when `RAG_ALLOW_ENV_KEYS=1`
  - Consent: every generation/stream/vision call asserts `user_consented=True`, otherwise raises `PermissionError` (`providers/litellm_provider.py::_assert_consent`)
  - Privacy: `LITELLM_TELEMETRY=False` and `litellm.telemetry = False` forced at import; errors scrubbed with `core/redaction.py`; egress events recorded in an in-memory ledger exposed at `GET /api/v1/privacy/ledger`
  - Timeouts/retries: 30 s timeout, 2 retries for blocking calls, 0 retries for streaming
- Groq direct SDK - `providers/groq_provider.py`, `groq==0.15.0`, default `openai/gpt-oss-20b`. Implements the same provider interface and consent gate but is **not wired into** `AiModel`/`CloudState`; cloud routing in the application uses LiteLLM.

**Document processing models:**
- Docling 2.138.0 - Local layout/table extraction; optional model artifacts via `DOCLING_ARTIFACTS_PATH` (`ingestion/docling_reader.py`). CPU pipeline (`do_ocr=False`), graceful fallback to pypdf when unavailable.
- RapidOCR / ONNX Runtime - Local OCR fallback for low-text pages (`ingestion/ocr_fallback.py`); package split by Python version (`rapidocr-onnxruntime` < 3.13, `rapidocr` >= 3.13).
- Sentence-Transformers (`all-MiniLM-L6-v2`) - Local embedding model, downloaded/cached through Hugging Face Hub by `setup.py::precache_embedding_model`; CPU device by default.

**Setup-time downloads (explicit operator action, not background telemetry):**
- Hugging Face Hub - GGUF weights and vision projector from `SoAIHQ/Qwen3.5-2B-GGUF` (`setup.py` `MODEL_REGISTRY`).
- GitHub Releases (`ggml-org/llama.cpp`, fallback mirror `ggerganov/llama.cpp`) - Platform llama-server archives for build `b11960`, pinned SHA-256 per archive (`setup.py` `LLAMA_ARCHIVE_SHA256`); download/verification happens only via `python setup.py --llama-server`.
- RapidOCR ONNX weights - Pre-cached by `setup.py::precache_ocr_model`.

**Developer tooling (not runtime):**
- Graphicle MCP server - Project code-graph tooling configured in `.mcp.json` and `.vscode/mcp.json`; also wired as Claude Code hooks in `.claude/settings.local.json`. No application code depends on it.

## Data Storage

**Databases:**
- SQLite (standard library `sqlite3`) - Document catalog, pages, chunks, evidence elements, summaries, chat sessions/messages, deletion tombstones.
  - Connection: `data/documents.db`, opened per operation with `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` (`core/doc_store.py::_connect`)
  - Schema: versioned migrations (`SCHEMA_V1_DDL` … `SCHEMA_V7_DDL`) applied through `_apply_migrations`
  - Client: no ORM; parameterized SQL in `core/doc_store.py`
- LanceDB 0.40.0 - Persistent vector + full-text index in `data/lancedb/`, table `chunks` with explicit PyArrow schema (`vector` = fixed-size list of 384 float32 values).
  - Connection: `lancedb.connect(str(db_uri))` in `retrieval/hybrid_retriever.py`
  - Hybrid search: LanceDB dense search + LanceDB FTS (`create_fts_index("content")`), fused with Reciprocal Rank Fusion; falls back to a pure-Python BM25 implementation and a durable `data/lancedb/fallback_store.json` mirror if LanceDB/FTS is unavailable
  - Legacy migration: copies `retrieval/data/lancedb` to `data/lancedb` when the target has no `*.lance` files

**File Storage:**
- Local filesystem only:
  - `data/originals/` - original PDFs stored as `<sha256>.pdf` when `RAG_STORE_ORIGINALS=1`, used to render page images for Evidence Lens (`api/routers/documents.py` lines 176-192)
  - `data/.cache/` - ingestion extraction cache keyed by document SHA-256 and config version (`api/container.py`)
  - `models/` - GGUF weights and vision projector
  - `tools/llama-server/` - downloaded llama.cpp binaries
  - `.cache/` - Hugging Face / OCR model caches (container mount in `docker-compose.yml`)
  - `frontend/out/` - static frontend export mounted at `/` when `RAG_SERVE_FRONTEND=1` (`api/main.py`)

**Caching:**
- In-process caches: shared `SentenceTransformer` instance (`retrieval/local_embedding.py` `_MODEL_CACHE`), 5 s TTL GPU telemetry (`core/resource_telemetry.py`), summary rows keyed by `(sha256, profile)` in SQLite (`document_summaries` table).
- No Redis/Memcached or external cache service.

## Authentication & Identity

**Auth Provider:**
- None. The application is explicitly single-user with no authentication layer (`start.py` refuses non-loopback binds unless `--allow-non-loopback` / `RAG_ALLOW_NON_LOOPBACK=1`).
- Request guard: every mutating request must send `X-RAG-Client: web`, enforced by `api/deps.py::require_client_header` (403 `missing_client_header`). Frontend sets it in `frontend/src/lib/api/client.ts` and `frontend/src/lib/api/sse.ts`.
- Host/CORS controls: `TrustedHostMiddleware` with `RAG_ALLOWED_HOSTS`; CORS origins default to `http://localhost:3000` and `http://127.0.0.1:3000` (`api/config.py`).
- Cloud credentials are user-supplied, in-memory only, revocable via `DELETE /api/v1/settings/cloud/credentials`.

**Inbound HTTP API (`/api/v1`, `api/routers/`):**
- System: `GET /health`, `GET /telemetry`, `GET /telemetry/stream`, `GET /diagnostics`, `GET /diagnostics/logs`
- Settings/privacy: `GET /settings`, `PUT /settings/cloud`, `DELETE /settings/cloud/credentials`, `GET /privacy/ledger`
- Documents: `GET /documents`, `POST /documents` (multipart), `DELETE /documents` (delete all), `GET|DELETE /documents/{doc_id}`, `GET /documents/{doc_id}/pages/{page_num}`, `GET /documents/{doc_id}/pages/{page_num}/image`, `GET /documents/{doc_id}/evidence`, `POST /documents/{doc_id}/reindex`
- Jobs: `GET /jobs`, `GET /jobs/{job_id}`, `GET /jobs/{job_id}/events` (SSE), `POST /jobs/{job_id}/cancel`
- Chat: `GET|POST /chat/sessions`, `GET|PATCH|DELETE /chat/sessions/{session_id}`, `GET /chat/sessions/{session_id}/export`, `POST /chat/sessions/{session_id}/messages/stream` (SSE), `POST /chat/sessions/{session_id}/stop`
- Summaries: `GET|POST /summaries`, `DELETE /summaries/{doc_id}`, `GET /summaries/{doc_id}/{profile}`, `GET /summaries/{doc_id}/{profile}/export`
- Search/visualization: `POST /search`, `GET /visualize/embeddings`, `POST /visualize/query-trace`
- Contract: OpenAPI 3.1 document committed at `openapi.json`; CI verifies sync via `python -m api.export_openapi --check`.

**Server-Sent Events (internal streaming transport):**
- Chat token stream, job progress, and telemetry use `text/event-stream` built in `api/streaming.py` (`event:` + JSON `data:` frames, 10 s keepalive comments) and consumed by `frontend/src/lib/api/sse.ts` with `eventsource-parser`.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/etc.). Errors are converted to RFC 9457 `application/problem+json` payloads with request IDs and redaction in `api/errors.py`.

**Logs:**
- Python `logging` to stdout and `data/logs/rag.log` (`api/main.py::configure_logging`), level from `RAG_LOG_LEVEL`, directory from `RAG_LOG_DIR`.
- Diagnostics log tail endpoint: `GET /api/v1/diagnostics/logs`.
- Telemetry: process RAM/CPU via `psutil`; GPU VRAM and compute processes via `nvidia-smi` with 5 s TTL caching and graceful degradation (`core/resource_telemetry.py`), surfaced at `GET /api/v1/telemetry` and `/telemetry/stream`.

## CI/CD & Deployment

**Hosting:**
- Self-hosted / local Docker. `docker-compose.yml` runs `rag-assistant-app` on `127.0.0.1:8000` with `data`, `models`, `.cache` bind mounts.
- Optional GPU profile `llama-server` uses image `ghcr.io/ggml-org/llama.cpp:server-cuda-b11960` on port 8080 with NVIDIA device reservation.

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` on pushes/PRs to `main` and `feat/fastapi-react`:
  - Backend: Python 3.11, `uv pip install` from `requirements.txt` + `requirements-test.txt`, Ruff lint/format, OpenAPI sync check, synthetic corpus generation (`tests/data/corpus/generate_corpus.py`), pytest.
  - Frontend: pnpm 9 + Node 20, `pnpm typecheck`, `pnpm build` (static export).

## Environment Configuration

**Required env vars:**
- Local mode: none. Defaults run fully offline (`api/config.py`, `providers/llama_cpp_provider.py`).
- Local model endpoint (optional overrides): `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT`.
- Cloud mode (optional): `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (only auto-read when `RAG_ALLOW_ENV_KEYS=1`; otherwise entered in the UI).
- Security/limits: `RAG_ALLOW_NON_LOOPBACK`, `RAG_ALLOWED_HOSTS`, `RAG_CORS_ORIGINS`, `RAG_REQUIRE_CHECKSUMS`.
- Storage/logging: `RAG_DATA_DIR`, `RAG_LOG_DIR`, `RAG_LOG_LEVEL`, `RAG_STORE_ORIGINALS`, `RAG_PERSIST_CHAT`, `RAG_SERVE_FRONTEND`.
- Frontend: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_USE_MOCKS`.
- Docling artifacts: `DOCLING_ARTIFACTS_PATH`.

**Secrets location:**
- `.env` in the repository root (gitignored; template at `.env.example`) - never committed.
- Cloud API keys in process memory only (`api/cloud_state.py` `_keys: dict[str, SecretStr]`); never written to disk or logs. Errors are scrubbed by `core/redaction.py`.

## Webhooks & Callbacks

**Incoming:**
- None. There are no webhook endpoints and no third-party callbacks. The only inbound listener is the FastAPI app (port 8000), optionally mounted with the static frontend.

**Outgoing:**
- None (no webhooks, no analytics, no telemetry callbacks). Outbound traffic is limited to:
  - `llama-server` on loopback (default)
  - cloud LLM APIs through LiteLLM only when the user enables Cloud Mode with consent
  - explicit setup-time downloads from Hugging Face and GitHub Releases
- LiteLLM telemetry is explicitly disabled (`providers/litellm_provider.py`).

## Ports and Local Endpoints

| Port | Service | Binding | Source |
|------|---------|---------|--------|
| 8000 | FastAPI + static frontend | `127.0.0.1` default (loopback guard) | `api/config.py`, `Dockerfile`, `docker-compose.yml` |
| 8080 | `llama-server` OpenAI-compatible API | `127.0.0.1` (Docker profile binds `0.0.0.0` inside container) | `providers/llama_cpp_provider.py`, `docker-compose.yml` |
| 3000 | Next.js dev server (`pnpm dev`) | localhost | `frontend/package.json`, CORS defaults |
| 8501 | Stale devcontainer Streamlit port | n/a in current runtime | `.devcontainer/devcontainer.json` (outdated) |

---

*Integration audit: 2026-11-14*
