# External Integrations

**Analysis Date:** 2026-10-28

<!-- refreshed: 2026-10-28 -->

## APIs & External Services

**Local Inference (default, loopback-only):**
- **llama-server (llama.cpp release `b11718`)** — the primary LLM/VLM backend.
  - SDK/Client: `httpx==0.28.1`
  - Implementation: `providers/llama_cpp_provider.py`
  - Base URL resolution: `LLAMA_SERVER_URL` → else `http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}` → else `http://127.0.0.1:8080` (`providers/llama_cpp_provider.py:76-83`)
  - Endpoints used:
    - `GET /health` — `check_health()`; `200` → healthy, `503` → `loading` ("loading the model into VRAM") (`providers/llama_cpp_provider.py:126-145`)
    - `POST /v1/chat/completions` — `generate_text()` (`providers/llama_cpp_provider.py:222`)
    - `POST /v1/chat/completions` with `stream=true` — SSE `stream_text()`, parsing `choices[0].delta.content` (`providers/llama_cpp_provider.py:271-284`)
    - `POST /v1/chat/completions` with `image_url` data URI — `analyze_image()` (`providers/llama_cpp_provider.py:347`)
    - `GET /v1/models` — manual diagnostics only (documented in `docs/ENDPOINT_INTEGRATION_MATRIX.md`)
  - Auth: none. Egress is constrained by a loopback allowlist: `{"localhost","127.0.0.1","::1","host.docker.internal","llama-server"}` plus `ipaddress.is_loopback`; anything else raises `ValueError` unless `allow_remote=True` (`providers/llama_cpp_provider.py:90-102`).
  - Timeouts: `connect=2.0, read=60.0, write=10.0, pool=5.0`; `/health` uses a 2.0s override.
  - Model: `qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16.gguf`, context `4096`, `-ngl 28`.

**Cloud Inference (optional, explicit consent required):**
- **Groq / OpenAI / Anthropic via LiteLLM** — `providers/litellm_provider.py`
  - SDK/Client: `litellm==1.105.0` (1.102.4 on Python ≥3.14)
  - Default model: `groq/llama-3.3-70b-versatile` (`DEFAULT_CLOUD_MODEL`, `providers/litellm_provider.py:29`)
  - Configured cloud models (`ui/views.py:1124-1128`):
    - `groq` → `groq/llama-3.3-70b-versatile`, auth `GROQ_API_KEY`
    - `openai` → `openai/gpt-4o-mini`, auth `OPENAI_API_KEY`
    - `anthropic` → `anthropic/claude-3-5-haiku-20241022`, auth `ANTHROPIC_API_KEY`
  - Context windows: `groq 131072`, `openai 128000`, `anthropic 200000` (`KNOWN_CONTEXT_WINDOWS`)
  - Vision-capable prefixes: `openai/gpt-4o`, `openai/gpt-4o-mini`, `anthropic/claude-3`, `anthropic/claude-3-5` (`VISION_SUPPORTED_PREFIXES`)
  - Key resolution order (`_resolve_api_key_for_model`, `providers/litellm_provider.py:45-89`): explicit arg → `st.session_state.cloud_api_keys[provider]` → `st.secrets[<PROVIDER>_API_KEY]` → `os.environ[<PROVIDER>_API_KEY]`
  - Consent gate: constructors accept `user_consented`; generation raises `PermissionError` when False (`providers/groq_provider.py:63-69`)
  - Telemetry disabled: `os.environ.setdefault("LITELLM_TELEMETRY","False")` and `litellm.telemetry = False` (`providers/litellm_provider.py:20-25`)
  - Error scrubbing: `_scrub_credentials()` routes error text through `core/redaction.py::redact_text(..., extra_secrets=(resolved_key,))`
- **Groq direct SDK** — `providers/groq_provider.py`
  - SDK/Client: `groq==0.15.0`
  - Default model: `openai/gpt-oss-20b`, `context_window=8192` (`providers/groq_provider.py:25-26`)
  - Key source: `st.secrets.get("GROQ_API_KEY")` → `os.environ["GROQ_API_KEY"]`
  - Cannot be auto-constructed by `AiModel`; must be injected explicitly.

**Model / Binary Distribution (setup-time, explicit CLI only):**
- **Hugging Face** — GGUF weights (`setup.py:54-77`):
  - `https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf` → saved as `models/qwen3-vl-2b-instruct-q4_k_m.gguf`, SHA-256 `4ef095263343fc1237e8ca879790bb262bcf209f082e0a9bfce219b7ece55e8b`
  - `.../mmproj-Qwen2-VL-2B-Instruct-f16.gguf` → `models/mmproj-f16.gguf`, SHA-256 `05cc3ae461a7b6aa4023312ccab549ecab77cf8677efee04f049fcbab55b8bc3`
- **GitHub Releases (ggml-org/llama.cpp)** — native server archives for `b11718` (`setup.py:413-415`):
  - Base: `https://github.com/ggml-org/llama.cpp/releases/download/b11718`
  - Mirror: `https://github.com/ggerganov/llama.cpp/releases/download/b11718`
  - Artifacts: `llama-b11718-bin-win-cuda-12.4-x64.zip`, `cudart-llama-b11718-win.zip`, `llama-b11718-bin-win-cpu-x64.zip`, `llama-b11718-bin-ubuntu-x64.tar.gz`, `llama-b11718-bin-ubuntu-cuda-12.8-x64.tar.gz`
  - Integrity: `LLAMA_ARCHIVE_SHA256` map (`setup.py:79-85`); `RAG_REQUIRE_CHECKSUMS=1` makes a missing pin fatal (`setup.py:220`)
- **Docling model artifacts** — resolved from package default or `DOCLING_ARTIFACTS_PATH` (`ingestion/docling_reader.py:192`).

**Embedding Model (local, in-process):**
- `sentence-transformers` `all-MiniLM-L6-v2`, `device="cpu"`, 384-dim, cosine; cached per process in `_MODEL_CACHE` (`retrieval/local_embedding.py:25-47`).

## Data Storage

**Databases:**
- **SQLite** — metadata, chunks, pages, evidence elements, summaries.
  - Location: `data/documents.db` (`main.py:44`)
  - Client: stdlib `sqlite3`, per-operation connections, `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON` (`core/doc_store.py:167-186`)
  - Migrations: v1–v4 applied on `DocStore.__init__` via `_apply_migrations`; physical `VACUUM` on purge (`ui/lifecycle_service.py`)
  - Indexes include `chunks(doc_id)` and `pages(doc_id)`.
- **LanceDB (embedded, no server)** — dense vectors + native FTS/BM25 index.
  - Location: `data/lancedb/` (`DEFAULT_DB_URI`, `retrieval/hybrid_retriever.py:70`); legacy path `retrieval/data/lancedb/` migrated on first init (`_migrate_legacy_index`)
  - Client: `lancedb.connect(str(self.db_uri))` → `retrieval/hybrid_retriever.py:216`
  - Fusion: Reciprocal Rank Fusion over dense + FTS ranks, `RRF_score(d) = Σ 1/(k_rrf + rank)` (`retrieval/hybrid_retriever.py:126-148`)
  - Degradation: in-process `VectorIndex` + durable `fallback_store.json` mirror when LanceDB or FTS is unavailable; FTS health exposed via `fts_status()` (`retrieval/hybrid_retriever.py:196-225,783-797`)

**File Storage:**
- **Local filesystem only.**
  - `data/` — SQLite DB, LanceDB dir, logs (`data/logs/`)
  - `models/` — GGUF weights (gitignored, present in this checkout)
  - `.cache/<sha256>/<CONFIG_VERSION>/` — extraction cache (`pages.json`, `chunks.json`, `manifest.json`); `CACHE_DIR = <app>/.cache` (`main.py:46`), path builder `core/models.py:17-31`
  - `tools/llama-server/` — native llama-server binary + DLLs (gitignored, present)
- No S3/GCS/Azure Blob client is used directly; `boto3` is a transitive LiteLLM dependency only.

**Caching:**
- **Persistent disk cache** at `.cache/<sha256>/docling-1000-200-v1/`, keyed by document SHA-256 plus `CONFIG_VERSION`; purged through `ui/lifecycle_service.py`.
- **Summary cache in SQLite**, invalidated by model version (`core/summarizer.py`).
- **In-process caches:** `@st.cache_resource` for `DocStore`/retriever (`main.py:143`), `_MODEL_CACHE` for the embedder (`retrieval/local_embedding.py:25`), 5s TTL GPU telemetry cache (`core/resource_telemetry.py:25`).
- No Redis/Memcached or external cache service.

## Authentication & Identity

**Auth Provider:**
- **None.** The Streamlit UI has zero authentication and is single-user by design. `start.py::refuse_unsafe_bind` blocks non-loopback binds unless `--allow-non-loopback` or `RAG_ALLOW_NON_LOOPBACK=1` (`start.py:40-91`).
- Cloud provider credentials are the only identity material: API keys held in `st.session_state.cloud_api_keys`, `st.secrets`, or environment variables; entered via a `type="password"` field in Settings (`ui/views.py:1148-1156`) and kept in session memory only.
- Consent is modeled as per-provider state: `st.session_state.cloud_mode`, `user_consented`, `cloud_api_keys` (`main.py:120-133`), with a revoke flow in `ui/views.py:1158-1163`.
- Secret scrubbing before surfacing errors/logs: `core/redaction.py::redact_text` with `_SECRET_ENV_VARS` (`core/redaction.py:46`).

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/OTel exporter). Privacy constraint forbids egress.

**Logs:**
- Structured `logging` with `logger = logging.getLogger(__name__)` throughout.
- Central setup: `core/logging_setup.py::configure_logging(log_dir=..., level=...)`; format `"%(asctime)s %(levelname)s [%(name)s] %(message)s"`, rotating file handler capped at 5 MB × 3 backups, idempotent handler installation via `_HANDLER_MARKER`.
- Config: `RAG_LOG_LEVEL` (default `INFO`), `RAG_LOG_DIR` (default `data/logs`); initialized at `main.py:50`.
- Streamlit usage stats disabled (`.streamlit/config.toml:21` → `gatherUsageStats = false`; Dockerfile `--browser.gatherUsageStats=false`).

**Hardware telemetry (local, no network):**
- `core/resource_telemetry.py` — GPU VRAM via `nvidia-smi --query-gpu=memory.used,memory.total` and per-process `--query-compute-apps=pid,process_name,used_memory`; RSS/VMS via `psutil`. Degrades silently in headless/CI (`except (FileNotFoundError, subprocess.SubprocessError, ...)`).

## CI/CD & Deployment

**Hosting:**
- Local desktop (Windows 11 primary) or self-hosted Docker Compose.
- Compose port mapping is loopback-scoped: `"127.0.0.1:8501:8501"` and `"127.0.0.1:8080:8080"` (`docker-compose.yml:8,34`).
- Optional GPU service `llama-server` uses `ghcr.io/ggml-org/llama.cpp:server-cuda` with `deploy.resources.reservations.devices: nvidia` (`docker-compose.yml:29-51`).

**CI Pipeline:**
- **GitHub Actions** — `.github/workflows/ci.yml`, triggered on push/PR to `main`, `ubuntu-latest`, Python 3.11:
  1. `astral-sh/setup-uv@v5` with caching
  2. `uv pip install --system -r requirements-lock.txt` + `requirements-test.txt` + `-e . --no-deps`
  3. `ruff check .` && `ruff format --check .`
  4. `python tests/data/corpus/generate_corpus.py`
  5. `pytest tests/ -v`
- No deployment workflow, no container registry publish, no release automation present.

## Environment Configuration

**Required env vars (local mode works with all blank):**
- `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — optional cloud only
- `LLAMA_SERVER_URL` **or** `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT`
- `DOCLING_ARTIFACTS_PATH` — optional
- `RAG_LOG_LEVEL`, `RAG_LOG_DIR`
- `RAG_REQUIRE_CHECKSUMS=1` — recommended
- `RAG_ALLOW_NON_LOOPBACK=0` — must stay `0` for a safe default
- `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`, `LITELLM_TELEMETRY=False`

**Secrets location:**
- `.env` in repo root (gitignored via `.gitignore:2-4`, with `!.env.example` exception) — template at `.env.example`
- Streamlit secrets (`st.secrets`) — supported by both cloud providers
- Streamlit session state (`st.session_state.cloud_api_keys`) — in-memory only
- No secrets manager, vault, or keyring integration.

**Session state keys (cloud/privacy defaults, `main.py:120-133`):**
`cloud_mode=False`, `cloud_mode_toggle=False`, `user_consented=False`, `cloud_provider="groq"`, `cloud_model="groq/llama-3.3-70b-versatile"`, `cloud_api_keys={"groq": "", "openai": "", "anthropic": ""}`.

## Webhooks & Callbacks

**Incoming:**
- None. No webhook endpoints, no FastAPI/Flask routes, no upload HTTP API. The only inbound listener is Streamlit on `8501` (plus Streamlit's built-in `/_stcore/health`). Confirmed in `docs/ENDPOINT_INTEGRATION_MATRIX.md`.
- Document uploads are handled in-process by Streamlit's `st.file_uploader` and `ui/ingestion_service.py`.

**Outgoing:**
- None. No outbound webhooks, no analytics, no crash reporting.
- HTTP egress is limited to: loopback llama-server calls, opt-in consented cloud LLM calls, and operator-initiated setup downloads (Hugging Face / GitHub Releases).
- In local mode, rendered markdown is neutralized by `ui/sanitizer.py` (strips `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`; external links rewritten) to prevent browser-side egress.

**Internal callbacks (in-process only, not network):**
- `progress_callback: Callable[[str], None]` — ingestion progress (`ui/ingestion_service.py:59-75`)
- `progress_callback: ProgressCallback | None` — startup hydration/vector repair (`ui/hydration.py:20-96`)
- `InferenceGate.acquire/release/hold` — global VRAM serialization, `timeout=60.0` for LLM/VLM and `120.0` for summarization (`core/local_llm.py:83`, `core/summarizer.py:559`)

---

*Integration audit: 2026-10-28*
