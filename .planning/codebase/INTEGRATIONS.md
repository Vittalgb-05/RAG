<!-- refreshed: 2026-10-21 -->
# External Integrations

**Analysis Date:** 2026-10-21

## APIs & External Services

**Local Inference (default, no network egress):**
- `llama-server` (llama.cpp) - primary LLM and VLM backend for chat, streaming, summarization, and visual descriptions.
  - SDK/Client: `httpx==0.28.1` via `providers/llama_cpp_provider.py`
  - Base URL: `http://127.0.0.1:8080` by default; overridable with `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST`/`LLAMA_SERVER_PORT`.
  - Endpoints used: `GET /health` (`check_health`), `POST /v1/chat/completions` with `stream: false` (blocking generation and vision), the same endpoint with `stream: true` for SSE token streaming, and `GET /v1/models` for manual diagnostics per `docs/ENDPOINT_INTEGRATION_MATRIX.md`.
  - Auth: none. Endpoint allowlist restricts hosts to `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, and `llama-server` unless `allow_remote=True` (`providers/llama_cpp_provider.py:60-85`).
  - Process management: `start.py:114-195` spawns `llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port 8080`; GGUF identity is verified first via `core/model_identity.py`.

**Optional Cloud LLM Providers (explicit opt-in only):**
- LiteLLM gateway - unified adapter for Groq, OpenAI, and Anthropic (`providers/litellm_provider.py`).
  - SDK/Client: `litellm==1.105.0` (Python <3.14) / `1.102.4` (Python >=3.14)
  - Selectable models in `ui/views.py`: `groq/llama-3.3-70b-versatile`, `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022` (configured via sidebar System & Privacy expander).
  - Auth: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, resolved in order from explicit argument, Streamlit `session_state.cloud_api_keys`, Streamlit secrets, then `os.environ` (`providers/litellm_provider.py:44-90`).
  - Consent: `user_consented=True` is mandatory before any transmission; otherwise `PermissionError` is raised. LiteLLM telemetry is force-disabled (`providers/litellm_provider.py:19-23`).
- Groq direct SDK - secondary cloud path (`providers/groq_provider.py`).
  - SDK/Client: `groq==0.15.0`, default model `openai/gpt-oss-20b`, context window `8192`.
  - Auth: `GROQ_API_KEY` from Streamlit secrets or environment; same explicit consent gate. Not auto-constructed by `AiModel` (`core/local_llm.py`).
- Cloud model defaults/context windows are tracked in `providers/litellm_provider.py:28-40`: Groq 131072, OpenAI 128000, Anthropic 200000; vision allowed only for `openai/gpt-4o*` and `anthropic/claude-3*` prefixes.

**Model & Binary Distribution (setup-time only):**
- Hugging Face - GGUF weights and multimodal projector downloads during `python setup.py download-models`.
  - Client: stdlib `urllib.request` (`setup.py:167-250`), no HF SDK dependency.
  - Mirrors in `setup.py:62-78`: `bartowski/Qwen2-VL-2B-Instruct-GGUF` then `lmstudio-community/Qwen2-VL-2B-Instruct-GGUF`; files `Qwen2-VL-2B-Instruct-Q4_K_M.gguf` and `mmproj-Qwen2-VL-2B-Instruct-f16.gguf`.
  - Auth: none (public repos).
- Hugging Face Hub (implicit at first embedding use) - `sentence-transformers==3.4.1` fetches `all-MiniLM-L6-v2` on first load via `huggingface-hub==0.36.2` (`retrieval/local_embedding.py:31-42`). No `HF_HOME`/`SENTENCE_TRANSFORMERS_HOME` override is configured, so default HF cache is used.
- GitHub Releases (llama.cpp) - `llama-server` binary archives from release `b11718`.
  - URLs: `https://github.com/ggml-org/llama.cpp/releases/download/b11718/...` with fallback mirror `https://github.com/ggerganov/llama.cpp/releases/download/b11718/...` (`setup.py:374-376`).
  - Artifacts: Windows CUDA 12.4 (`llama-b11718-bin-win-cuda-12.4-x64.zip` + `cudart-...`), Windows CPU, Linux CUDA 12.8, Linux CPU (`setup.py:483-547`). Downloads are extracted with traversal-safe logic (`setup.py:91-130`).

**No other outbound HTTP integrations:** no analytics SDKs, no payment, no email, no third-party auth. `ui/sanitizer.py` neutralizes external Markdown/HTML links and embeds to prevent browser-side egress in local mode.

## Data Storage

**Databases:**
- SQLite (embedded, stdlib `sqlite3`) - source of truth for documents, pages, chunks, evidence elements, and cached summaries.
  - Connection: file path `data/documents.db` (`main.py:109-111`); WAL mode with `busy_timeout=5000` and `foreign_keys=ON` (`core/doc_store.py:141-145`).
  - Client: `core/doc_store.py` (`DocStore`), schema migrations v1–v4 tracked in `PRAGMA user_version`; physical `VACUUM` on purge via `ui/lifecycle_service.py`.
  - No connection string env var; path is derived from `APP_DIR` (`main.py:108`).
- LanceDB (embedded, on-disk) - dense vector index plus native FTS index.
  - Connection: `data/lancedb/` (`retrieval/hybrid_retriever.py:69`); legacy `retrieval/data/lancedb/` is migrated non-destructively (`DEFAULT_DB_URI` / `LEGACY_DB_URI`).
  - Client: `lancedb==0.40.0` + `pyarrow==23.0.1`; single table `chunks`, FTS index on `content` via `create_fts_index("content", replace=True)` (`retrieval/hybrid_retriever.py:617-626`).
  - Fallback: in-memory/JSON `VectorIndex` if LanceDB import or table creation fails (`retrieval/vector_index.py`, `retrieval/hybrid_retriever.py:204-212`).

**File Storage:**
- Local filesystem only.
  - GGUF weights: `models/` (gitignored).
  - Extraction cache: `.cache/<sha256>/<config_version>/` holding `pages.json`, `chunks.json`, `manifest.json` (`core/models.py:17`, `ui/ingestion_service.py`).
  - Uploaded PDFs are processed in memory/from Streamlit buffers; no object storage and no document file archive is persisted.
  - Docker Compose mounts `./data`, `./models`, `./.cache` for persistence (`docker-compose.yml:9-13`).

**Caching:**
- SQLite-backed summary cache keyed by document SHA-256, summary profile, and `model_version` (`"{model_name}:{CONFIG_VERSION}"`) in `core/summarizer.py:405-412`.
- Process-level `SentenceTransformer` singleton cache in `retrieval/local_embedding.py:19-45`.
- 5-second TTL cache for `nvidia-smi` GPU telemetry (`core/resource_telemetry.py:25-60`).
- No Redis/Memcached or external cache service.

## Authentication & Identity

**Auth Provider:**
- None (custom, single-user local application). The Streamlit UI has no login, session auth, or user accounts; access control relies on binding to `localhost`/`127.0.0.1` (`start.py`, `docker-compose.yml:8`).
- Cloud provider credentials are per-session API keys held in `st.session_state.cloud_api_keys`, Streamlit secrets, or environment variables; keys are scrubbed from error messages in `providers/litellm_provider.py`.
- Document identity uses content hashing (`doc_<sha16>` from SHA-256) in `ingestion/upload_validation.py`; GGUF identity is verified by parsing metadata in `core/model_identity.py`.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, OpenTelemetry, or hosted error reporting.
- Application errors surface through Python `logging` (`logger = logging.getLogger(__name__)`) and Streamlit UI status pills/messages.

**Logs:**
- Standard-library structured logging to stderr/stdout with per-module loggers; benign third-party warnings suppressed in `core/logging_setup.py`.
- Local hardware telemetry: RAM RSS/VMS via `psutil==6.1.1` and GPU VRAM/compute apps via `nvidia-smi` subprocess (`core/resource_telemetry.py`), surfaced in the Settings workspace.
- Privacy posture: `browser.gatherUsageStats = false` (`.streamlit/config.toml:15`), `LITELLM_TELEMETRY=False` (`providers/litellm_provider.py:19`), `USE_TF=0` to avoid TensorFlow telemetry/scan overhead.

## CI/CD & Deployment

**Hosting:**
- Local workstation (Windows 11 primary; Linux x86_64 supported) or Docker Compose on the same machine. No cloud hosting target in the repo.
- `app` service: `127.0.0.1:8501`; optional `llama-server` service: `127.0.0.1:8080` under Compose profile `gpu` (`docker-compose.yml`).

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` on pushes/PRs to `main`, `ubuntu-latest`:
  1. `actions/setup-python@v5` with Python 3.11
  2. `astral-sh/setup-uv@v5`
  3. `uv pip install --system -r requirements-lock.txt`, `-r requirements-test.txt`, `-e . --no-deps`
  4. `ruff check .` and `ruff format --check .`
  5. `python tests/data/corpus/generate_corpus.py` (reportlab synthetic PDFs)
  6. `pytest tests/ -v`
- No deployment/release workflow, no container registry publish step, no code-signing step.
- Dev container: `.devcontainer/devcontainer.json` on `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`, forwards port 8501, auto-installs `requirements.txt`.

## Environment Configuration

**Required env vars:**
- `LLAMA_SERVER_URL` or (`LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT`) - optional; defaults to `http://127.0.0.1:8080`.
- `DOCLING_ARTIFACTS_PATH` - optional override for Docling model artifacts cache (`ingestion/docling_reader.py:192`).
- `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` - optional, cloud mode only.
- `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` - set by the app/launcher but also honored from the environment.
- `LITELLM_TELEMETRY=False` - defaulted by the adapter.
- Docker-only: `PYTHONUNBUFFERED=1` (`docker-compose.yml:15`).

**Secrets location:**
- Environment variables, Streamlit secrets (`.streamlit/secrets.toml`, not present), or in-memory `st.session_state` (`main.py:132`, `providers/litellm_provider.py:60-90`).
- No `.env` file is present in the workspace; `.env` is gitignored (`.gitignore` line 1) and loaded if created (`main.py:120`).
- GGUF/ONNX/zip artifacts and `models/`, `tools/`, `data/`, `.cache/` are gitignored.

## Webhooks & Callbacks

**Incoming:**
- None. There are no FastAPI/Flask routes, upload webhooks, or callback endpoints. The only inbound listener is the Streamlit server on `8501` plus Streamlit's built-in health route `/_stcore/health` (used by `Dockerfile:42-43`).
- File uploads are handled in-process by Streamlit widgets and validated in `ingestion/upload_validation.py` (50 MB max, 500 pages max, `%PDF` magic bytes).

**Outgoing:**
- None (no webhook delivery, no event publishing). Outbound calls are limited to the configured LLM provider endpoint and explicit setup-time downloads.

---

*Integration audit: 2026-10-21*
