<!-- refreshed: 2026-10-21 -->
# External Integrations

**Analysis Date:** 2026-10-21

## APIs & External Services

**Local Inference (default, offline):**
- **llama-server (llama.cpp)** — OpenAI-compatible chat completions plus health probe on `127.0.0.1:8080`.
  - SDK/Client: `httpx==0.28.1` (`llama_cpp_provider.py`)
  - Endpoints used: `POST /v1/chat/completions` (streaming SSE and non-streaming), `GET /health`
  - Auth: none (loopback only)
  - Endpoint allowlist: `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server`, or any loopback IP; anything else raises `ValueError` unless `allow_remote=True` (`llama_cpp_provider.py:61`). This is the SSRF/egress guard.
  - Configuration: `LLAMA_SERVER_URL`, or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT`; default `http://127.0.0.1:8080`.
  - Model: Qwen3-VL 2B Instruct GGUF Q4_K_M + `mmproj-f16.gguf`, context `4096`, `-ngl 28` (`start.py`, `docker-compose.yml`).
  - Health states mapped to `HealthStatus`: `200 → healthy`, `503 → loading`, connection failure → `unreachable` with a copy-paste launch command.

**Cloud Inference (optional, consent-gated):**
- **Groq** — default cloud route `groq/llama-3.3-70b-versatile` via LiteLLM (`litellm_provider.py:28`).
  - SDK/Client: `litellm==1.105.0`; direct `groq==0.15.0` adapter exists in `groq_provider.py` (default `openai/gpt-oss-20b`, 8192 context, no vision).
  - Auth: `GROQ_API_KEY`
- **OpenAI** — `openai/gpt-4o-mini` via LiteLLM (`ui/views.py:763`).
  - Auth: `OPENAI_API_KEY`
- **Anthropic** — `anthropic/claude-3-5-haiku-20241022` via LiteLLM (`ui/views.py:764`).
  - Auth: `ANTHROPIC_API_KEY`
  - Privacy gate: every cloud call calls `_assert_consent()` and raises `PermissionError` without explicit user consent (`litellm_provider.py:142`). Errors are scrubbed of API keys via `_scrub_credentials()`.
  - Telemetry: LiteLLM external telemetry is disabled (`LITELLM_TELEMETRY=False`, `litellm.telemetry = False`).
  - Known context windows: groq 131072, openai 128000, anthropic 200000 (`litellm_provider.py:30`).

**Model & Tooling Downloads (setup-time only, not runtime):**
- **Hugging Face** — GGUF weights and multimodal projector (`setup.py:64-76`):
  - `https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/...`
  - Mirror: `https://huggingface.co/lmstudio-community/Qwen2-VL-2B-Instruct-GGUF/...`
  - `sentence-transformers`/`huggingface-hub` also fetch `all-MiniLM-L6-v2` and RapidOCR ONNX weights on first use.
- **GitHub Releases (llama.cpp)** — prebuilt `llama-server` and CUDA runtime archives, release `b11718` (`setup.py:288-290`); mirrors `ggml-org/llama.cpp` and `ggerganov/llama.cpp`.
- Downloads use `urllib.request` with mirrors, 30s timeout, minimum-size verification, and atomic `.tmp` replacement.

## Data Storage

**Databases:**
- **SQLite** — source of truth for documents, pages, chunks, evidence elements, and cached summaries.
  - File: `data/documents.db` (`main.py:140`, `doc_store.py`)
  - Client: stdlib `sqlite3` with `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` (`doc_store.py:141-145`)
  - Schema: tables `documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` (`doc_store.py:19-75`); migrations tracked via `PRAGMA user_version`.
  - Physical `VACUUM` on purge (`ui/lifecycle_service.py`).
- **LanceDB** — persistent vector + full-text index.
  - Directory: `data/lancedb/` (`hybrid_retriever.py:36`)
  - Client: `lancedb.connect(str(db_uri))`; FTS index on the `content` column via `create_fts_index`; dense search then FTS search fused with RRF (`k=60`) in `search_hybrid()`.
  - Degradation: `vector_index.VectorIndex` in-memory/JSON store at `data/lancedb/fallback_store.json` when LanceDB is unavailable; pure-Python BM25 fallback if FTS querying fails.

**File Storage:**
- Local filesystem only. Runtime directories created by `start.py`/`setup.py`: `data/`, `models/`, `.cache/`, `tools/`.
- Intermediate extraction cache: `.cache/<sha256>/<CONFIG_VERSION>/` (`models.cache_dir_for`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Uploaded PDFs are processed in memory from Streamlit uploads (`st.file_uploader`); no external object storage.

**Caching:**
- SQLite summary cache keyed by `(sha256, profile, model_version)` (`doc_store.get_summary`, `summarizer.py:330`).
- Process-level `SentenceTransformer` singleton cache (`local_embedding._MODEL_CACHE`).
- 5s TTL cache for `nvidia-smi` GPU telemetry (`resource_telemetry.py`).
- Streamlit `st.session_state` holds retriever, embedding model, chat history, and cloud credentials per session.

## Authentication & Identity

**Auth Provider:**
- None. Single-user local application; there is no login, user table, OAuth, or session authentication.
- Streamlit server hardening: `enableCORS = true`, `enableXsrfProtection = true`, `maxUploadSize = 50` (`.streamlit/config.toml`); Docker exposes `127.0.0.1:8501` only.
- Cloud credentials are user-supplied at runtime via the Settings workspace (`ui/views.py:782`) into `st.session_state.cloud_api_keys`, or resolved from `st.secrets` / environment variables (`litellm_provider.py:57-88`, `groq_provider.py:38-47`).

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/etc.).

**Logs:**
- Standard library `logging` via `logging_setup.py`; per-module `logger = logging.getLogger(__name__)`.
- Benign watcher warnings suppressed in `logging_setup.py`.
- Cloud provider errors are logged after credential scrubbing (`litellm_provider.py:237`).

**Telemetry:**
- Streamlit usage stats disabled (`gatherUsageStats = false` in `.streamlit/config.toml` and launch flags).
- Hardware telemetry: GPU VRAM/free/utilization via `nvidia-smi --query-gpu=memory.total,memory.used,memory.free`; process RSS/VMS via `psutil` (`resource_telemetry.py`).

## CI/CD & Deployment

**Hosting:**
- Local machine (Windows/Linux) or Docker host. `docker-compose.yml` maps `127.0.0.1:8501:8501` and `127.0.0.1:8080:8080`.
- Optional GPU profile: `ghcr.io/ggml-org/llama.cpp:server-cuda` with NVIDIA device reservations.

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` on push/PR to `main`, `ubuntu-latest`, Python 3.11:
  1. `uv pip install --system -r requirements-lock.txt` + `requirements-test.txt`
  2. `ruff check .` and `ruff format --check .`
  3. `python tests/data/corpus/generate_corpus.py` (reportlab synthetic corpus)
  4. `pytest tests/ -v`
- No deployment/release workflow detected.

## Environment Configuration

**Required env vars:**
- Local inference (optional, defaults work): `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT`.
- Cloud (only when cloud mode enabled): `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Framework tuning (defaulted in code): `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`, `LITELLM_TELEMETRY=False`.

**Secrets location:**
- `.env` at repo root (gitignored; not present in the working tree) loaded by `python-dotenv` (`main.py:151`).
- Streamlit secrets (`.streamlit/secrets.toml`) supported read-only via `st.secrets`; file not present.
- Session state `st.session_state.cloud_api_keys` for per-session keys.
- `docker-compose.yml` passes `${GROQ_API_KEY}`, `${OPENAI_API_KEY}`, `${ANTHROPIC_API_KEY}` from the host shell.
- No secrets committed; `.dockerignore` and `.gitignore` exclude `.env` / `.env.*`.

## Webhooks & Callbacks

**Incoming:**
- None. No webhook, callback, or public API endpoints are registered by the application.

**Outgoing:**
- None at runtime in local mode. Outbound HTTP is limited to:
  - loopback llama-server calls (`llama_cpp_provider.py`)
  - consented LiteLLM/Groq calls (`litellm_provider.py`, `groq_provider.py`)
  - setup-time downloads from huggingface.co and github.com (`setup.py`)
- UI-level egress prevention: `ui/sanitizer.py` strips `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`, `<link>`, removes external `<img>` sources, and neutralizes external Markdown/HTML links before rendering.

---

*Integration audit: 2026-10-21*
