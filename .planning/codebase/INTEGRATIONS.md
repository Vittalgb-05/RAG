# External Integrations

**Analysis Date:** 2026-10-29

## APIs & External Services

**Local inference (default, loopback only):**
- llama-server (`llama.cpp` v0.8.0 / build `b11960`) — the sole inference backend in local mode.
  - SDK/Client: `httpx==0.28.1` in `providers/llama_cpp_provider.py:120-124`.
  - Base URL resolution: `LLAMA_SERVER_URL`, else `http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}`, else `http://127.0.0.1:8080` (`providers/llama_cpp_provider.py:88-95`).
  - Endpoints used: `GET /health` (`:138`), `POST /v1/chat/completions` for both blocking and SSE streaming (`:232`, `:282`).
  - Health semantics: HTTP 200 → `healthy`, HTTP 503 → `loading`, connect error → `unreachable` with a copy-paste launch command (`:141-179`).
  - Loopback enforcement: hosts `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server` plus `ipaddress.is_loopback`; anything else raises `ValueError` unless `allow_remote=True` (`:101-114`). This is the SSRF guard for the provider.
  - Vision: base64 `data:` URLs with MIME sniffed from magic bytes (`:25-44`, `:326-348`).
  - Reasoning disabled per request via `reasoning_effort: "none"` and `chat_template_kwargs.enable_thinking=False` (`:62-65`).
  - Auth: **none** — trusted loopback service, no API key or token.
- Native binary management:
  - Binary discovery: PATH first, then `tools/llama-server/llama-server[.exe]` (`core/runtime_info.py:63-76`).
  - Version probing: runs `<binary> --version` with a 5s timeout and parses `version: X (build N, commit H)` (`core/runtime_info.py:94-127`), cached per process.
  - Process launch: `start.py:176-256` spawns the binary with `-m models/qwen3.5-2b-q4_k_m.gguf --mmproj models/qwen3.5-2b-mmproj-f16.gguf -c 4096 -ngl 28 --port 8080`, then polls `/health` for up to 10s.
  - Server log file: `data/logs/llama-server.log`.

**Local model weights (first-run download only):**
- Hugging Face Hub — `SoAIHQ/Qwen3.5-2B-GGUF` at revision `377fa65bb36aa83414de1ab3b40f6f15b0324cdc` (`setup.py:63-84`).
  - `Qwen3.5-2B-Q4_K_M.gguf` → `models/qwen3.5-2b-q4_k_m.gguf` (~1.31 GB), SHA-256 `a8b50de0…1523b`.
  - `mmproj-Qwen3.5-2B-f16.gguf` → `models/qwen3.5-2b-mmproj-f16.gguf` (~668 MB), SHA-256 `044a0ea1…d36`.
  - Downloader: `urllib.request` with streaming progress, size floor, SHA-256 verification, and atomic `.tmp` → final rename (`setup.py:196-308`).
  - GGUF magic-byte validation (`b"GGUF"`) at `setup.py:171-184`; architecture/projector pairing verified by `core/model_identity.py` (`qwen35` + `qwen3vl_merger`; rollback pair `qwen2vl` + `qwen2vl_merger`).
- Hugging Face model cache (via `sentence-transformers`) — `all-MiniLM-L6-v2` pre-cached on CPU (`setup.py:311-328`).
- RapidOCR ONNX weights — pre-cached locally by instantiating `RapidOCR()` (`setup.py:331-348`).

**llama.cpp release binaries (first-run download only):**
- GitHub Releases from two mirrors: `ggml-org/llama.cpp` primary, `ggerganov/llama.cpp` fallback (`setup.py:96-97`).
- Pinned archives with SHA-256 (`setup.py:89-95`): Windows CUDA 12.4 (`llama-b11960-bin-win-cuda-12.4-x64.zip`, `cudart-llama-bin-win-cuda-12.4-x64.zip`), Windows CPU (`llama-b11960-bin-win-cpu-x64.zip`), Linux CPU (`llama-b11960-bin-ubuntu-x64.tar.gz`), Linux CUDA 12.8 (`llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz`).
- Extraction is traversal-safe: zip members are resolved and rejected outside the destination, tar symlinks/hardlinks are skipped (`setup.py:134-168`).
- `RAG_REQUIRE_CHECKSUMS=1` makes a missing pin a hard failure (`setup.py:100-102`, `:232-234`).

**Optional cloud text generation (explicit opt-in):**
- LiteLLM `1.105.0` — `providers/litellm_provider.py`.
  - Default model: `groq/llama-3.3-70b-versatile` (`:29`).
  - UI-selectable models (`ui/views.py:1270-1274`, duplicated at `:1499-1503`): `groq/llama-3.3-70b-versatile`, `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022`.
  - Context windows assumed: groq 131072, openai 128000, anthropic 200000 (`:31-35`).
  - Vision allow-list: `openai/gpt-4o`, `openai/gpt-4o-mini`, `anthropic/claude-3`, `anthropic/claude-3-5` (`:37-42`).
  - Timeouts/retries: 30s timeout, 2 retries for non-streaming, 0 for streaming (`:112-115`).
- Groq SDK `0.15.0` — `providers/groq_provider.py`.
  - Default model `openai/gpt-oss-20b`, context 8192, `supports_vision=False` (`:19`, `:104-116`).
  - `analyze_image` raises `NotImplementedError` by design (`:186-194`).
- Consent gate (both cloud providers): every `generate_text`, `stream_text`, and `analyze_image` call begins with `_assert_consent()`, raising `PermissionError` until `user_consented=True` (`providers/litellm_provider.py:141-147`, `:210`, `:260`, `:313`; `providers/groq_provider.py:65-71`).
- Key scrubbing: LiteLLM disables telemetry globally (`LITELLM_TELEMETRY=False`, `litellm.telemetry = False` at `providers/litellm_provider.py:19-27`) and every cloud error string passes through `core/redaction.py:34-60` (`redact_text`) before logging or display.
- Mode wiring: `AiModel` defaults to local `LlamaCppProvider()`; cloud mode is only entered through `set_cloud_mode(True, cloud_provider=...)` and re-validates `user_consented` (`core/local_llm.py:123-186`, `:232`). `main.py:227-266` synchronizes the session's `LiteLLMProvider` and falls back to local mode on any error.

**Hardware telemetry:**
- `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits`, 2s timeout, 5s TTL cache (`core/resource_telemetry.py:62-90`). Returns `None` on headless/CI hosts; no error surfaces to the UI.
- Process RSS/VMS via `psutil` (`core/resource_telemetry.py`).

**Priming/metadata lookups:**
- No package-index, analytics, crash-reporting, or advertising endpoint is contacted at runtime. All outbound hosts observed in source: `huggingface.co`, `github.com` (setup only), and the three cloud provider APIs (consented cloud mode only).

## Data Storage

**Databases:**
- SQLite — `data/documents.db` (`DOC_STORE_PATH` in `main.py:46`).
  - Connection: per-operation connections, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON` (`core/doc_store.py:171-182`).
  - Client: stdlib `sqlite3` only — no ORM.
  - Schema migrations tracked by `PRAGMA user_version` (`core/doc_store.py:232-247`), v1–v5:
    - v1: `documents`, `pages`, `chunks`
    - v2: `evidence_elements`
    - v3: `document_summaries` (+ `idx_summaries_sha256`, `idx_summaries_doc_id`)
    - v4: `idx_chunks_doc_id`, `idx_pages_doc_id`
    - v5: `deletion_tombstones`
  - Concurrency: bounded retry (3 attempts, 50 ms base + jitter) for `SQLITE_BUSY`/`SQLITE_LOCKED` codes 5/6 (`core/doc_store.py:25-41`).
- LanceDB 0.40.0 — `data/lancedb/`.
  - Connection: `lancedb.connect(str(self.db_uri))` (`retrieval/hybrid_retriever.py:216`); canonical path resolved as `<repo_root>/data/lancedb` (`:70`).
  - Table: `chunks`, explicit PyArrow schema with `vector: float32[384]` (`:31-45`, `:542-544`).
  - FTS: `table.create_fts_index("content", replace=True)` for BM25 keyword search (`:821-826`).
  - Observed on disk: `data/lancedb/chunks.lance`, `data/lancedb/fallback_store.json`.
  - Legacy migration: copies from `retrieval/data/lancedb` non-destructively when the target is empty (`:84-118`).

**File Storage:**
- Local filesystem only.
- `models/` — GGUF weights. Observed: `qwen3.5-2b-q4_k_m.gguf` (1.31 GB), `qwen3.5-2b-mmproj-f16.gguf` (668 MB), plus stale `qwen3-vl-2b-instruct-q4_k_m.gguf` and `mmproj-f16.gguf` from the previous model pair.
- `tools/llama-server/` — unpacked native runtime (≈1.2 GB of DLLs/EXEs observed); `tools/llama-server-b11718-rollback/` retained for rollback (`core/runtime_info.py` expectation is `b11960`).
- `.cache/<sha256>/<CONFIG_VERSION>/` — per-document intermediate artifacts (pages/chunks/manifest); path contract in `core/models.py:17-30` (`cache_dir_for`), base directory set in `ui/ingestion_service.py:52`. Observed: two SHA-256-named directories (currently empty of files).
- `data/logs/` — `app.log` (rotating: 5 MB × 3 backups, `core/logging_setup.py:33-35`) and `llama-server.log`.
- Uploaded PDFs are **not** stored as files; the bytes are hashed (`doc_<sha16>` id, `ingestion/upload_validation.py:90-102`) and content persists only in SQLite/LanceDB.

**Caching:**
- LanceDB FTS + vector index (persistent).
- In-memory `VectorIndex` fallback serialized to `data/lancedb/fallback_store.json` when LanceDB is unavailable (`retrieval/hybrid_retriever.py:201-285`).
- Process-level `SentenceTransformer` cache (`retrieval/local_embedding.py:36-58`).
- SQLite `document_summaries` acts as a summary cache keyed on `(sha256, profile)` with `model_version` invalidation (`core/doc_store.py:100-120`).
- GPU telemetry TTL cache, 5s (`core/resource_telemetry.py:26-29`).

## Authentication & Identity

**Auth Provider:**
- None. The application has **no user authentication** and no session identity provider.
  - Single-user assumption documented in `.streamlit/config.toml` and enforced by `start.py:58-90` (`refuse_unsafe_bind`), which aborts a non-loopback bind unless `--allow-non-loopback` or `RAG_ALLOW_NON_LOOPBACK=1`.
  - Docker overrides the bind to `0.0.0.0` inside the container but publishes only `127.0.0.1:8501` on the host (`docker-compose.yml:8`, `Dockerfile:46`).
- Cloud credentials are the only identity material:
  - Resolution order: explicit argument → `st.session_state.cloud_api_keys[provider]` → `st.secrets[VAR]` → `os.environ[VAR]` (`providers/litellm_provider.py:45-89`).
  - UI accepts a per-provider key into session memory only (`ui/views.py:1290-1305`), never persisted to disk.
  - Mapping: `groq` → `GROQ_API_KEY`, `openai` → `OPENAI_API_KEY`, `anthropic` → `ANTHROPIC_API_KEY`.
- Trust boundary for document content: cloud transmission requires the user toggling cloud mode **and** consenting; the status pill flips from `100% Local` to `Cloud Active` and an explicit "Cloud Egress Permitted" card is rendered (`ui/views.py:1240-1268`).

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, OpenTelemetry, Datadog, or equivalent SDK.

**Logs:**
- Structured stdlib logging with one idempotent configuration: stderr + rotating file `data/logs/app.log` (`core/logging_setup.py:56-120`).
- Level from `RAG_LOG_LEVEL` (default `INFO`); directory from `RAG_LOG_DIR` (default `data/logs`).
- Format: `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
- A targeted filter suppresses Streamlit's benign `torch.classes` watcher traceback (`core/logging_setup.py:11-20`).
- Diagnostics workspace renders redacted health, resource, and log data (`ui/views.py`, `main.py:38-44`).
- Cloud/provider exceptions are redacted before logging (`core/redaction.py`), covering `gsk_`, `sk-`, `sk-proj-`, `xox[baprs]-`, `ghp_`, `github_pat_`, `hf_`, `AIza`, bearer tokens, and key/value pairs.

**Telemetry:**
- Explicitly disabled: Streamlit `gatherUsageStats = false` (`.streamlit/config.toml`, `Dockerfile:46`, `start.py:275`); LiteLLM telemetry off (`providers/litellm_provider.py:19-27`).

## CI/CD & Deployment

**Hosting:**
- Self-hosted, single machine. Two supported shapes: native (`python start.py --start-llama`) and Docker Compose (`docker compose up`, optional `--profile gpu` llama-server container).

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml`, job "Lint & Test Suite (Python 3.11)" on `ubuntu-latest`.
  - Triggers: `push` and `pull_request` on `main`.
  - Steps: `actions/checkout@v4` → `actions/setup-python@v5` (3.11) → `astral-sh/setup-uv@v5` (cached) → `uv pip install -r requirements-lock.txt` + `requirements-test.txt` + `-e . --no-deps` → `ruff check .` → `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`.
  - **No remote CI run result was observed during this analysis** (no API/artifact access; `docs/TEST_RESULTS.md` and `docs/DEPENDENCY_AUDIT.md` record local runs instead).
- Container build: `Dockerfile` installs from `requirements-lock.txt` then `pip install -e .`; `.dockerignore` excludes `tests/`, `data/`, `models/`, `tools/`, `.env`, `.planning/`.

## Environment Configuration

**Required env vars:**
- None are strictly required for local mode. All of the following are optional:
  - Cloud keys: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
  - Local server: `LLAMA_SERVER_URL` (wins when set), or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT` (default `127.0.0.1:8080`).
  - Docling: `DOCLING_ARTIFACTS_PATH`.
  - Logging: `RAG_LOG_LEVEL`, `RAG_LOG_DIR`.
  - Security/integrity: `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`.
  - Backend pinning: `USE_TF`, `USE_TORCH`, `TF_ENABLE_ONEDNN_OPTS` (set programmatically at import time).
  - Privacy: `LITELLM_TELEMETRY` (forced to `False` by default).
- `.env.example` documents all of the above. The file's `.env` counterpart is **not present** in the working tree.

**Secrets location:**
- `.env` at repo root (gitignored, absent here) — loaded by `python-dotenv` at `main.py:209`.
- `.streamlit/secrets.toml` (absent here; `st.secrets` access is guarded).
- Streamlit session state (`st.session_state.cloud_api_keys`) — memory only.
- Environment variables in Docker (`docker-compose.yml:14-23`, values interpolated from the host env with empty defaults).
- No secrets are baked into `Dockerfile`, `docker-compose.yml`, or any source file.

## Webhooks & Callbacks

**Incoming:**
- None. No webhook receiver, queue, broker, or callback endpoint exists.
- HTTP surface is three loopback-only listeners: Streamlit `127.0.0.1:8501` (plus `/_stcore/health` for the container healthcheck), llama-server `127.0.0.1:8080` (`/health`, `/v1/chat/completions`), and the pre-cached Streamlit static assets served by the same process.

**Outgoing:**
- None at runtime in local mode. Outbound calls happen only on explicit operator action (setup downloads from `huggingface.co` / `github.com`) or under consented cloud mode (Groq / OpenAI / Anthropic via LiteLLM or the Groq SDK).
- Persistence and retrieval are entirely in-process/on-disk — no queue publish, no remote index sync, no public-cloud object storage.

---

*Integration audit: 2026-10-29*
