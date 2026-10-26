# External Integrations

**Analysis Date:** 2026-10-26

## APIs & External Services

**Local Inference (default, no egress):**
- `llama-server` (llama.cpp `b11718`) - text generation, SSE streaming, and VLM image analysis.
  - SDK/Client: `httpx` 0.28.1 (`providers/llama_cpp_provider.py`)
  - Endpoints: `GET /health` (`:126`), `POST /v1/chat/completions` blocking (`:222`), SSE streaming with `"stream": true` (`:271`), vision payloads via base64 `data:` URI `image_url` (`:332-333`); `GET /v1/models` is diagnostics-only.
  - Auth: none; enforced by loopback allowlist `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server` (`providers/llama_cpp_provider.py:90-102`). `allow_remote=True` is required to bypass.
  - Config: `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT` (default `http://127.0.0.1:8080`).

**Cloud LLM (opt-in, explicit consent required):**
- Groq / OpenAI / Anthropic via LiteLLM - chat and image analysis fallback.
  - SDK/Client: `litellm` 1.105.0 (`providers/litellm_provider.py`); default `groq/llama-3.3-70b-versatile` (`:28`).
  - Auth: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`; resolution order session state `cloud_api_keys` -> `st.secrets` -> `os.environ` (`:44-88`).
  - Gate: `user_consented=True` is mandatory; generation raises `PermissionError` otherwise (`:104-160`), and `AiModel` refuses cloud mode without a consented provider (`core/local_llm.py:131-136`).
  - UI choices: Groq Llama 3.3 70B, OpenAI GPT-4o mini, Anthropic Claude 3.5 Haiku (`ui/views.py:1232-1234`).
- Groq direct SDK - secondary cloud adapter.
  - SDK/Client: `groq` 0.15.0 (`providers/groq_provider.py`); default model `openai/gpt-oss-20b` (`:24`).
  - Auth: `GROQ_API_KEY` via `st.secrets` or environment (`:41-51`); same consent gate.

**Model & Binary Distribution (explicit setup CLI only):**
- Hugging Face HTTPS downloads - quantized GGUF weights.
  - Client: `urllib.request` in `setup.py:57-76` (`MODEL_REGISTRY`), pinned SHA-256 per artifact.
  - Artifacts: `qwen3-vl-2b-instruct-q4_k_m.gguf` (legacy filename for Qwen2-VL-2B-Instruct Q4_K_M) and `mmproj-f16.gguf`.
- llama.cpp GitHub releases - `llama-b11718` Windows CUDA 12.4 / CPU and Ubuntu / Ubuntu CUDA 12.8 archives.
  - Client: `urllib.request` + `zipfile`/`tarfile` in `setup.py`; pinned digests in `LLAMA_ARCHIVE_SHA256` (`setup.py:79-85`).
  - Set `RAG_REQUIRE_CHECKSUMS=1` to fail closed on unpinned downloads (`setup.py:88-90`).

**Local Hardware Telemetry:**
- NVIDIA `nvidia-smi` - GPU VRAM totals and per-process allocations; 5s TTL cache (`core/resource_telemetry.py:34-140`).
- `psutil` 6.1.1 - process RSS/VMS (`core/resource_telemetry.py:172-190`).
- Not a network integration; degrades to zeros on headless/CI hosts.

## Data Storage

**Databases:**
- SQLite - source of truth for documents, pages, chunks, evidence elements, and cached summaries.
  - Connection: `data/documents.db` (resolved at `main.py:40`), stdlib `sqlite3`, WAL mode, 5s busy timeout (`core/doc_store.py:160-170`).
  - Client: `DocStore` (`core/doc_store.py`), schema migrations v1-v4 (`:131-136`), indexes on `chunks(doc_id)` and `pages(doc_id)`.
- LanceDB - persistent dense vector table plus BM25/FTS index.
  - Connection: `data/lancedb/` (`retrieval/hybrid_retriever.py:70`); legacy `retrieval/data/lancedb/` migration path (`:71`, non-destructive copy).
  - Client: `lancedb` 0.40.0 via `HybridRetriever`; in-memory `VectorIndex` fallback at `retrieval/vector_index.py`.
  - Fusion: Reciprocal Rank Fusion with `DEFAULT_RRF_K = 60` (`retrieval/hybrid_retriever.py:72,123-148`).

**File Storage:**
- Local filesystem only. Extraction cache `.cache/<sha256>/<config-version>/` (`pages.json`, `chunks.json`, `manifest.json`); helper `cache_dir_for` in `core/models.py:17`.
- Uploads are held in memory per request; limit 50 MB and 500 pages (`ingestion/upload_validation.py:18-19`), `%PDF-` magic-byte check (`:136`), stable `doc_<sha16>` IDs (`:90-102`).
- Logs: `data/logs/app.log`, rotating at 5 MB with 3 backups (`core/logging_setup.py:29-38,115-125`).

**Caching:**
- Summary cache in SQLite keyed by `sha256 + profile + model_version` (`core/summarizer.py:494-498`, `:573`).
- In-process caches: shared `SentenceTransformer` (`retrieval/local_embedding.py:25`), 5s GPU telemetry cache (`core/resource_telemetry.py:25`), Streamlit `@st.cache_resource` DocStore (`main.py:130`).
- No external cache service (no Redis).

## Authentication & Identity

**Auth Provider:**
- None / custom - the app is explicitly single-user with no login. Streamlit binds to `127.0.0.1` and refuses non-loopback binds without `--allow-non-loopback` or `RAG_ALLOW_NON_LOOPBACK=1` (`start.py:40,63-75`; `.streamlit/config.toml:10-18`).
- Cloud provider identity is credential-only: API keys stored in `st.session_state.cloud_api_keys` or environment, cleared via the Settings scrub path (`ui/views.py:265-290`), and scrubbed from surfaced errors (`providers/litellm_provider.py`).
- Consent state: `st.session_state.user_consented` plus provider-level `user_consented` (`ui/views.py:1194`, `core/local_llm.py:131`).

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry/Datadog/APM SDK. Startup failures render actionable pages via `_render_startup_failure` (`main.py`).

**Logs:**
- Stdlib `logging` with `logger = logging.getLogger(__name__)`; centralized `configure_logging` (`core/logging_setup.py`), console + rotating file (`data/logs/app.log`), level via `RAG_LOG_LEVEL`.
- Never logs API key values; LiteLLM telemetry disabled at import (`providers/litellm_provider.py:18-24`).
- Streamlit usage stats disabled (`.streamlit/config.toml:21`).

## CI/CD & Deployment

**Hosting:**
- Local/self-hosted only. Docker image `python:3.11-slim-bookworm`, Streamlit on `8501` (`Dockerfile`), compose maps `127.0.0.1:8501:8501` (`docker-compose.yml:8`).
- Optional GPU sidecar `ghcr.io/ggml-org/llama.cpp:server-cuda` under the `gpu` compose profile on `127.0.0.1:8080` (`docker-compose.yml:29-51`).

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml`: `ubuntu-latest`, Python 3.11, uv install from `requirements-lock.txt` + `requirements-test.txt` + `pip install -e . --no-deps`, Ruff check/format, synthetic corpus generation, `pytest tests/ -v`.
- No deployment/release automation detected.

## Environment Configuration

**Required env vars:**
- Local inference: `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT` (optional; loopback default).
- Optional cloud: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Operations: `RAG_LOG_LEVEL`, `RAG_LOG_DIR`, `RAG_ALLOW_NON_LOOPBACK`, `RAG_REQUIRE_CHECKSUMS`.
- Library behavior: `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`, `LITELLM_TELEMETRY=False`, `DOCLING_ARTIFACTS_PATH`, `HF_HUB_DISABLE_SYMLINKS_WARNING`.

**Secrets location:**
- `.env` at repo root (gitignored, loaded by `python-dotenv` at `main.py:190`; not present in the working tree), process environment, Streamlit `st.secrets`, or in-session `st.session_state.cloud_api_keys`. Docker Compose forwards host env (`docker-compose.yml:21-23`). No secret files are committed.

## Webhooks & Callbacks

**Incoming:**
- None. No FastAPI/Flask routes, upload endpoints, or webhook receivers. The only inbound listener is Streamlit on `127.0.0.1:8501` plus its built-in `/_stcore/health` (`docs/ENDPOINT_INTEGRATION_MATRIX.md:6-13`).

**Outgoing:**
- None (no user-configured webhooks or callbacks). Outbound traffic is limited to: loopback llama-server HTTP/SSE, opt-in cloud HTTPS via LiteLLM/Groq, and explicit setup-time HTTPS downloads from Hugging Face/GitHub.

## Privacy & Egress Boundaries

- Local mode performs zero external network calls; cloud mode is unreachable without explicit consent and a key (`core/local_llm.py:131-220`).
- `ui/sanitizer.py` strips `<script>/<iframe>/<object>/<embed>/<style>` and neutralizes external Markdown/HTML links so rendered answers cannot trigger browser egress.
- All LLM/VLM/summarizer calls serialize through `InferenceGate.hold(...)` to stay inside the 4 GB VRAM envelope (`core/local_llm.py:26-78`, `core/summarizer.py:559`, `ingestion/visual_analyzer.py:290`).

---

*Integration audit: 2026-10-26*
