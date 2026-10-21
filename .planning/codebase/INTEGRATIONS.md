# External Integrations

**Analysis Date:** 2026-10-21

## APIs & External Services

**Local Inference (llama.cpp):**
- `llama-server` — native C++ OpenAI-compatible REST server providing text generation, SSE token streaming, and multimodal image analysis with Qwen2-VL 2B GGUF.
  - SDK/Client: `httpx` 0.28.1, `providers/llama_cpp_provider.py`
  - Base URL: `LLAMA_SERVER_URL`, else `http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}`, else `http://127.0.0.1:8080` (`providers/llama_cpp_provider.py:44-54`)
  - Auth: none (loopback only)
  - Endpoints used:
    - `GET /health` — returns 200 healthy / 503 loading; 2 s timeout (`providers/llama_cpp_provider.py:89-141`)
    - `POST /v1/chat/completions` — non-streaming text, streaming SSE (`stream: true`), and image payloads as base64 `data:image/jpeg;base64,...` (`providers/llama_cpp_provider.py:157-315`)
  - Client timeouts: connect 2 s, read 60 s, write 10 s, pool 5 s (`providers/llama_cpp_provider.py:79-83`)
  - SSRF/egress guard: only `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server`, or any `ipaddress` loopback host accepted unless `allow_remote=True` (`providers/llama_cpp_provider.py:56-73`)
  - Model identifier label: `qwen3-vl-2b`; context window 4096; vision + streaming enabled (`providers/llama_cpp_provider.py:27-34`, `143-155`)
- Server binary launched by `start.py:114-178` (`python start.py --start-llama`) with `-m models/qwen3-vl-2b-instruct-q4_k_m.gguf -c 4096 -ngl 28 --port 8080 --host 127.0.0.1 [--mmproj models/mmproj-f16.gguf]`.
- Container alternative: `docker-compose.yml` service `llama-server` using image `ghcr.io/ggml-org/llama.cpp:server-cuda`, profile `gpu`, NVIDIA device reservation, ports `127.0.0.1:8080:8080`, read-only `./models` mount.

**Cloud LLM Providers (opt-in, consent-gated):**
- LiteLLM 1.105.0 adapter — `providers/litellm_provider.py`
  - Default model: `groq/llama-3.3-70b-versatile` (`providers/litellm_provider.py:28`)
  - UI-selectable models (`ui/views.py:791-793`):
    - Groq — `groq/llama-3.3-70b-versatile`, key `GROQ_API_KEY`
    - OpenAI — `openai/gpt-4o-mini`, key `OPENAI_API_KEY`
    - Anthropic — `anthropic/claude-3-5-haiku-20241022`, key `ANTHROPIC_API_KEY`
  - Auth resolution order: explicit constructor arg → Streamlit `session_state.cloud_api_keys` → Streamlit `st.secrets` → environment variable (`providers/litellm_provider.py:44-88`)
  - Consent gate: every `generate_text`, `stream_text`, and `analyze_image` call raises `PermissionError` unless `user_consented=True` (`providers/litellm_provider.py:142-148`, `211`, `261`, `314`)
  - Privacy: `LITELLM_TELEMETRY=False` set before import and `litellm.telemetry = False` (`providers/litellm_provider.py:19-26`); API keys scrubbed from error text/logs (`providers/litellm_provider.py:135-140`)
  - Timeouts/retries: 30 s default timeout, 2 retries non-streaming, 0 retries streaming (`providers/litellm_provider.py:107-129`)
  - Vision support allowlist: `openai/gpt-4o*`, `anthropic/claude-3*` prefixes (`providers/litellm_provider.py:36-41`)
  - Known context windows: Groq 131072, OpenAI 128000, Anthropic 200000 (`providers/litellm_provider.py:30-34`)
- Groq SDK 0.15.0 direct adapter — `providers/groq_provider.py`
  - Default model: `openai/gpt-oss-20b`; context window 8192; text-only (`supports_vision=False`)
  - Auth: `st.secrets["GROQ_API_KEY"]` then `GROQ_API_KEY` env var (`providers/groq_provider.py:37-47`)
  - Not wired as the default cloud path (`main.py` constructs `LiteLLMProvider`); retained as an alternate implementation.

**Model & Binary Artifact Sources (install-time only):**
- Hugging Face GGUF downloads (primary + fallback mirrors) in `setup.py:59-78`:
  - `https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf`
  - `https://huggingface.co/lmstudio-community/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf`
  - `https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf`
  - `https://huggingface.co/lmstudio-community/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf`
  - Saved locally as `models/qwen3-vl-2b-instruct-q4_k_m.gguf` and `models/mmproj-f16.gguf`.
- sentence-transformers `all-MiniLM-L6-v2` — downloaded from the Hugging Face Hub on first use and pre-cached by `setup.py:196-213` (`SentenceTransformer(model_name, device="cpu")`).
- RapidOCR ONNX weights — pre-cached by constructing `RapidOCR()` in `setup.py:216-233`.
- llama.cpp binaries — release `b11718` from `https://github.com/ggml-org/llama.cpp/releases/download/b11718` with `ggerganov/llama.cpp` fallback (`setup.py:288-290`):
  - Windows CUDA 12.4: `llama-b11718-bin-win-cuda-12.4-x64.zip` + `cudart-llama-bin-win-cuda-12.4-x64.zip`
  - Windows CPU: `llama-b11718-bin-win-cpu-x64.zip`
  - Linux CUDA 12.8: `llama-b11718-bin-ubuntu-cuda-12.8-x64.tar.gz`
  - Linux CPU: `llama-b11718-bin-ubuntu-x64.tar.gz`
- No artifact downloads occur at application runtime; only `setup.py` and first-run Hugging Face cache population.

**No other external API clients exist.** Runtime scans of `core/`, `ui/`, `retrieval/`, `ingestion/`, `providers/`, and `main.py` show no `requests`, `aiohttp`, or non-loopback HTTP calls. `ui/sanitizer.py` strips `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`, `<link>`, and neutralizes external Markdown/HTML links and images to prevent browser-driven egress.

## Data Storage

**Databases:**
- SQLite — metadata source of truth
  - Connection: `data/documents.db`, constructed in `main.py:140` and passed to `DocStore` (`core/doc_store.py`)
  - Client: Python stdlib `sqlite3`, per-operation connections, `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `PRAGMA foreign_keys=ON` (`core/doc_store.py:133-149`)
  - Schema migrations v1–v4 (`PRAGMA user_version`): `documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries`; indexes `idx_summaries_sha256`, `idx_summaries_doc_id`, `idx_chunks_doc_id`, `idx_pages_doc_id` (`core/doc_store.py:17-109`)
  - Retention: cascade delete per document; `purge_all()` deletes all tables and runs `VACUUM` (`core/doc_store.py:597-631`)
- LanceDB — persistent vector + full-text index
  - Client: `lancedb` 0.40.0 with `pyarrow` explicit schema (`chunk_id`, `doc_id`, `filename`, `page`, `content`, `vector[384]`, `extraction`, `char_start`, `char_end`, `bbox_json`) in `retrieval/hybrid_retriever.py:26-49`
  - Table name: `chunks` (`retrieval/hybrid_retriever.py:224`, `383`)
  - FTS: `table.create_fts_index("content", replace=True)`; queries via `search(query, query_type="fts")`; pure-Python BM25 fallback (`retrieval/hybrid_retriever.py:522-621`)
  - Dense search fused with FTS via Reciprocal Rank Fusion, `k=60` (`retrieval/hybrid_retriever.py:59-100`, `627+`)
  - Effective default URI: `retrieval/data/lancedb` because `DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"` in `retrieval/hybrid_retriever.py:58`. `ui/hydration.py:54` and `ui/ingestion_service.py:275` instantiate `HybridRetriever()` without an override, so vectors are written under `retrieval/data/lancedb`. Documentation and UI labels still reference `data/lancedb/` (`ui/views.py:860`), and a separate `data/lancedb/` directory exists in the working tree. Treat `retrieval/data/lancedb` as the code-level reality and reconcile before relying on backup/purge paths.
  - Fallback: if LanceDB import/init fails, `retrieval/vector_index.py` in-memory cosine index is persisted to `<db_uri>/fallback_store.json` (`retrieval/hybrid_retriever.py:136-209`).

**File Storage:**
- Local filesystem only. No S3/GCS/Azure Blob integration.
- Extraction cache: `.cache/<sha256>/docling-1000-200-v1/` via `cache_dir_for()` (`core/models.py:13-30`; `CONFIG_VERSION = "docling-1000-200-v1"`), storing `pages.json`, `chunks.json`, `manifest.json` (`ui/ingestion_service.py:313+`).
- Model weights: `models/*.gguf` (two files, ~2.3 GB total on disk).
- Native runtime: `tools/llama-server/` (Windows CUDA DLLs and `llama-server.exe` present).
- Synthetic test PDFs: `tests/data/corpus/*.pdf` generated by `tests/data/corpus/generate_corpus.py`.
- Brand assets: `assets/brand_mark.svg`, `assets/icons/*.svg`.

**Caching:**
- Summary cache in SQLite `document_summaries`, unique on `(sha256, profile)`, with `model_version` invalidation (`core/doc_store.py:73-93`, `core/summarizer.py:332-336`, `417+`).
- Process-level `SentenceTransformer` cache keyed by `(model_name, device)` (`retrieval/local_embedding.py:21-45`).
- GPU telemetry cache with 5.0 s TTL (`core/resource_telemetry.py:25-31`, `33-97`).
- Ingestion artifact cache under `.cache/` (see above).
- No Redis/Memcached or external cache service.

## Authentication & Identity

**Auth Provider:**
- None. Single-user local workstation application; no login, session auth, OAuth, SSO, or user accounts.
- Streamlit security settings: `enableCORS = true` and `enableXsrfProtection = true` in `.streamlit/config.toml`; upload cap 50 MB.
- Cloud provider authentication is API-key based only, scoped to a browser session:
  1. `st.session_state.cloud_api_keys` (UI input, in-memory)
  2. `st.secrets[<PROVIDER>_API_KEY]`
  3. `<PROVIDER>_API_KEY` environment variable / `.env`
- Explicit consent is required before any cloud transmission (`main.py:200-244`, `providers/litellm_provider.py:142-148`). Session reset clears consent, provider clients, keys, and chat state (`main.py:56-92`).
- Docker Compose forwards `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` from the host environment into the app container (`docker-compose.yml`).

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Rollbar, OpenTelemetry, or equivalent).

**Logs:**
- Python stdlib `logging` with module-level `logger = logging.getLogger(__name__)` across `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`.
- `core/logging_setup.py` suppresses Streamlit's benign `torch.classes` watcher warning (`main.py:26-41`).
- LiteLLM errors are logged with API keys scrubbed (`providers/litellm_provider.py:236-239`, `293-296`, `352-355`).
- No log shipping or centralized aggregation.

**Runtime telemetry:**
- `core/resource_telemetry.py`: `nvidia-smi --query-gpu=memory.total,memory.used,memory.free` (5 s TTL), `nvidia-smi --query-compute-apps=pid,process_name,used_memory`, `psutil` process RSS/VMS, stage latency history (`MAX_STAGE_HISTORY = 200`), and `get_system_telemetry_snapshot()`.
- Health surfaces: provider `HealthStatus` (`healthy` / `loading` / `unreachable` / `error`) rendered in the sidebar (`main.py:190-277`); llama-server `GET /health`; Docker `HEALTHCHECK` against `http://localhost:8501/_stcore/health`.
- Benchmark harnesses: `scripts/profile_resources.py`, `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`; results documented in `docs/EVALUATION.md`.

## CI/CD & Deployment

**Hosting:**
- Local workstation (Windows 11 primary, Linux x86_64 supported). No cloud hosting configuration in the repository.
- Docker Compose: `app` (Streamlit, `127.0.0.1:8501`) plus optional `llama-server` GPU profile (`ghcr.io/ggml-org/llama.cpp:server-cuda`, `127.0.0.1:8080`).
- Dev container: `.devcontainer/devcontainer.json` (Python 3.11 bookworm, port 8501, CORS/XSRF disabled only in the dev command).

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` — single job on `push`/`pull_request` to `main`:
  1. `actions/checkout@v4`, `actions/setup-python@v5` (3.11)
  2. `astral-sh/setup-uv@v5` with cache
  3. `uv pip install --system -r requirements-lock.txt`, `-r requirements-test.txt`, `-e . --no-deps`
  4. `ruff check .` and `ruff format --check .`
  5. `python tests/data/corpus/generate_corpus.py`
  6. `pytest tests/ -v`
- No deployment/release workflow, no container registry publishing, no scheduled jobs.

## Environment Configuration

**Required env vars:**
- None strictly required for local operation (defaults bind to `127.0.0.1:8080`).
- Optional local inference: `LLAMA_SERVER_URL`, or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT` (default `8080`).
- Optional cloud mode: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Privacy/runtime flags set by code defaults: `LITELLM_TELEMETRY=False`, `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`.
- Documented optional: `HF_HUB_DISABLE_SYMLINKS_WARNING=1` (Windows Hugging Face cache warnings, `docs/RUNBOOK.md`).
- Docker Compose supplies `PYTHONUNBUFFERED=1`, `USE_TF=0`, `USE_TORCH=1`, `LLAMA_SERVER_HOST=host.docker.internal`, `LLAMA_SERVER_PORT=8080`.

**Secrets location:**
- `.env` at repo root — git-ignored, loaded via `python-dotenv`; **no `.env` file is present in the working tree.**
- `.streamlit/secrets.toml` — supported through `st.secrets`, **not present.**
- Session memory (`st.session_state.cloud_api_keys`) — keys are never persisted by the app.
- Docker Compose reads keys from the invoking shell environment.
- No credentials, tokens, or secret material are committed; `tools/` (binaries) and `models/` (weights) are git-ignored.

## Webhooks & Callbacks

**Incoming:**
- None. No webhook receivers or public callback routes.
- Only HTTP surface is Streamlit itself: UI on `8501` and Streamlit's built-in `/_stcore/health` used by the Docker healthcheck.

**Outgoing:**
- None. No webhook/event delivery.
- Outbound HTTP is limited to: loopback `llama-server` calls (`/health`, `/v1/chat/completions`) and, only after explicit consent, LiteLLM calls to Groq/OpenAI/Anthropic API endpoints.

---

*Integration audit: 2026-10-21*
