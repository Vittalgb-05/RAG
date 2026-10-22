<!-- refreshed: 2026-10-22 -->
# External Integrations

**Analysis Date:** 2026-10-22

## Integration Model

The application is a **local-first modular monolith** with three integration classes:

1. **Inbound:** a single Streamlit listener; no document-processing HTTP API, no webhook receivers.
2. **Outbound at runtime:** local `llama-server` over loopback by default; cloud LLM providers only after explicit per-session consent.
3. **Outbound at setup time:** explicit operator-run downloads of GGUF weights, llama.cpp binaries, and model caches (`setup.py`).

There is no analytics SDK, payment, email, third-party auth, or background telemetry service. `docs/ENDPOINT_INTEGRATION_MATRIX.md` records the same rule: all inference is outbound, all persistence is embedded, and the only inbound listener is the UI.

## APIs & External Services

**Local Inference (default; zero document egress):**
- **llama-server (llama.cpp)** — primary LLM/VLM backend for chat, streaming, summarization, and visual descriptions.
  - SDK/Client: `httpx==0.28.1` in `providers/llama_cpp_provider.py`.
  - Default base URL: `http://127.0.0.1:8080`. Resolution order: explicit argument, `LLAMA_SERVER_URL`, then `LLAMA_SERVER_HOST`/`LLAMA_SERVER_PORT`, then loopback default.
  - Endpoints:
    - `GET /health` — `check_health` maps HTTP 200 to `healthy`, 503 to `loading`, other codes to `error`; connection failures to `unreachable` with a copy-paste launch command.
    - `POST /v1/chat/completions` with `stream: false` — blocking text generation.
    - `POST /v1/chat/completions` with `stream: true` — SSE token stream, terminated by `data: [DONE]`.
    - `POST /v1/chat/completions` with an `image_url` data URI — vision analysis of PNG/JPEG/GIF/WebP/BMP.
  - Auth: none. The client rejects non-loopback hosts unless `allow_remote=True`; allowed hostnames are `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, and `llama-server`, plus IP-loopback detection.
  - Timeouts: connect 2.0 s, read 60.0 s, write 10.0 s, pool 5.0 s.
  - Model identity: provider reports `model_name="qwen2-vl-2b"` and `context_window=4096`; the selected GGUF pair is validated by `core/model_identity.py`.
  - Process management: `start.py` finds `llama-server` on `PATH` or `tools/llama-server/` and spawns it with `-m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c <ctx> -ngl <ngl> --port <port>`, defaulting to `-c 4096 -ngl 28`. It waits on `/health` before launching Streamlit.
  - Serialization: every generation, streaming, vision, and summarization call acquires `InferenceGate` (`core/local_llm.py`) to keep one active GPU inference operation within the 4 GB VRAM envelope.

**Optional Cloud LLM Providers (explicit opt-in only):**
- **LiteLLM gateway** — unified adapter for Groq, OpenAI, and Anthropic (`providers/litellm_provider.py`).
  - SDK/Client: `litellm==1.105.0` (Python <3.14) / `1.102.4` (Python >=3.14) from `requirements-lock.txt`; `litellm` is imported defensively and a missing package yields an `unreachable` health status.
  - Selectable models in `ui/views.py`: `groq/llama-3.3-70b-versatile`, `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022`.
  - Context windows: Groq 131,072; OpenAI 128,000; Anthropic 200,000 (`KNOWN_CONTEXT_WINDOWS`).
  - Vision: only model prefixes `openai/gpt-4o*` and `anthropic/claude-3*` are treated as vision-capable; `analyze_image` raises `NotImplementedError` otherwise.
  - Auth/key resolution order: explicit constructor argument → Streamlit `st.session_state.cloud_api_keys[provider]` → Streamlit secrets → environment (`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).
  - Consent: `user_consented=True` is mandatory. Every generation, stream, and image call calls `_assert_consent()` first and raises `PermissionError` otherwise. `AiModel(cloud_mode=True)` also refuses to construct without a consented provider.
  - Privacy: `LITELLM_TELEMETRY=False` and `litellm.telemetry = False` are set at import; API keys are scrubbed from error strings before logging or surfacing.
  - Timeouts/retries: default timeout 30 s, `num_retries=2` for blocking generation and vision, `num_retries=0` while streaming.
- **Groq direct SDK** — secondary cloud adapter (`providers/groq_provider.py`).
  - SDK/Client: `groq==0.15.0`; default model `openai/gpt-oss-20b`, context window 8192.
  - Auth: `GROQ_API_KEY` from Streamlit secrets, then environment. Same explicit-consent gate.
  - Vision: not supported; `analyze_image` raises `NotImplementedError`.
  - Wiring: `AiModel._detect_provider()` only auto-creates `LlamaCppProvider`; `GroqProvider` is never auto-selected and must be injected by a caller.
- **Cloud routing:** `main.py` builds a per-session `LiteLLMProvider` when `cloud_mode` and `user_consented` are true and calls `ai_model.set_cloud_mode(True, ...)`; otherwise it closes the cached provider and forces local mode. Settings UI clears keys from session state and closes provider clients on disable.

## Data Storage

**Databases:**
- **SQLite** (embedded, stdlib `sqlite3`) — source of truth for documents, pages, chunks, evidence elements, and summary cache.
  - Path: `data/documents.db`, derived from `APP_DIR` in `main.py`; no connection-string environment variable.
  - Client: `core/doc_store.py` (`DocStore`).
  - Consistency: per-operation connections, `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`; write transactions retry up to 3 times with exponential backoff and jitter on `SQLITE_BUSY`/`SQLITE_LOCKED`; physical `VACUUM` after purge.
  - Schema: migrations v1–v4 tracked by `PRAGMA user_version`; tables include `documents`, `pages`, `chunks`, `evidence_elements`, and summaries.
  - Summary cache key: document SHA-256 + profile + `model_version` (`"{model_name}:{CONFIG_VERSION}"`), invalidated when `core/models.py::CONFIG_VERSION` or the model changes (`core/summarizer.py`).
- **LanceDB** (embedded, on-disk) — dense vector index and native full-text search.
  - Path: `data/lancedb/` (`DEFAULT_DB_URI` in `retrieval/hybrid_retriever.py`). Legacy `retrieval/data/lancedb/` is migrated non-destructively when the target has no data.
  - Client: `lancedb==0.40.0` + `pyarrow==23.0.1`.
  - Table: `chunks`, explicit PyArrow schema, 384-dimensional `vector` column; FTS index on `content` via `create_fts_index("content", replace=True)`.
  - Fusion: dense cosine search + BM25/FTS candidates combined with Reciprocal Rank Fusion (`k=60`); falls back to pure-Python BM25 if the LanceDB FTS index is unavailable.
  - Fallback: a durable JSON mirror at `data/lancedb/fallback_store.json` backs the in-memory `VectorIndex` when LanceDB is unavailable; writes are atomic (`.tmp` then replace) and document scope is pushed into the backend before limiting.
  - Failure policy: vector write failures raise `VectorIndexError` rather than reporting a successful ingestion with missing vectors.

**File Storage:**
- **Local filesystem only.** No S3, GCS, Azure Blob, or object storage.
- Input PDFs are processed from in-memory Streamlit upload buffers; the PDF file itself is not archived. Only extracted metadata and chunks persist in SQLite/LanceDB.
- GGUF weights live in `models/` and the native server binary in `tools/llama-server/`; both are gitignored and mounted into Docker Compose.
- **Extraction cache removed:** no `pages.json`, `chunks.json`, or `manifest.json` are written. `ui/ingestion_service.py` holds a `cache_dir` path, while `ui/lifecycle_service.py` and `core/models.py::cache_dir_for` use it only for best-effort deletion during document delete/purge and legacy cleanup. `docker-compose.yml` still mounts `./.cache:/app/.cache` for compatibility.
- Logs: `data/logs/app.log` with `RotatingFileHandler` (5 MB max, 3 backups).

**Caching:**
- SQLite-summary cache (persistent).
- Process-level `SentenceTransformer` cache keyed by `(model_name, device)` (`retrieval/local_embedding.py`).
- 5-second TTL cache for `nvidia-smi` GPU memory samples (`core/resource_telemetry.py`).
- Streamlit resource cache for the process-wide `DocStore` (`@st.cache_resource` in `main.py`).
- No Redis, Memcached, or external cache service.

## Authentication & Identity

**Auth Provider:**
- **None.** The application is single-user and has no login, session auth, accounts, or RBAC. `start.py` refuses a non-loopback Streamlit bind unless `--allow-non-loopback` or `RAG_ALLOW_NON_LOOPBACK=1` is set, and `.streamlit/config.toml` defaults `server.address` to `127.0.0.1`.
- Cloud credentials are per-session API keys in `st.session_state.cloud_api_keys`, Streamlit secrets, or environment variables. The app does not write them to disk; `ui/views.py::clear_cloud_credentials` wipes them from session state and cached providers.
- Document identity is content-derived: SHA-256 of the uploaded bytes and `doc_<sha16>` (`ingestion/upload_validation.py`).
- Model identity is metadata-derived: `core/model_identity.py` parses GGUF metadata to reject mismatched language-model/projector pairs, because filenames are not trustworthy.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, OpenTelemetry, Datadog, or hosted error reporting.
- Exceptions are logged locally and surfaced in the Streamlit UI (startup failure panels, status pills, settings diagnostics).

**Logs:**
- Standard-library logging with per-module `logger = logging.getLogger(__name__)`.
- `core/logging_setup.py` configures a stream handler and `data/logs/app.log` rotating file handler, default level `INFO`, overridable via `RAG_LOG_LEVEL` and `RAG_LOG_DIR`.
- Benign Streamlit `torch.classes` watcher noise is filtered; Torch is forced (`USE_TF=0`, `USE_TORCH=1`).
- Hardware telemetry: GPU total/used/free VRAM and compute apps via `nvidia-smi`; process RSS/VMS via `psutil`; stage latency history in `core/resource_telemetry.py`, surfaced in Settings.
- Privacy posture: `browser.gatherUsageStats = false`; LiteLLM telemetry disabled; no document content leaves the machine unless cloud mode is explicitly enabled and consented.

## CI/CD & Deployment

**Hosting:**
- Local workstation (Windows 11 primary; Linux x86_64 supported) or Docker Compose on the same machine. No cloud hosting target or Kubernetes manifests in the repository.

**CI Pipeline:**
- `.github/workflows/ci.yml`, on push/PR to `main`, `ubuntu-latest`:
  1. `actions/checkout@v4` and `actions/setup-python@v5` with Python 3.11.
  2. `astral-sh/setup-uv@v5` with caching.
  3. `uv pip install --system -r requirements-lock.txt`, `-r requirements-test.txt`, and `-e . --no-deps`.
  4. `ruff check .` and `ruff format --check .`.
  5. `python tests/data/corpus/generate_corpus.py` (reportlab synthetic PDFs).
  6. `pytest tests/ -v`.
- The suite is offline: inference, embeddings, and telemetry are mocked. CI does not build the Docker image, download GGUF weights, or call live providers.
- No release, publish, image-signing, or deployment workflow.

**Containerization:**
- `Dockerfile`: Python 3.11 slim Bookworm, installs system libraries for OpenCV/RapidOCR/PyMuPDF, copies `requirements.txt` + `requirements-lock.txt` but installs from **`requirements.txt`**, then `pip install -e .`; exposes `8501`; healthcheck `curl -f http://localhost:8501/_stcore/health`; runs Streamlit on `0.0.0.0:8501` inside the container.
- `docker-compose.yml`: `app` publishes only `127.0.0.1:8501`, mounts `./data`, `./models`, `./.cache`, passes `LLAMA_SERVER_HOST=host.docker.internal` and optional cloud keys. `llama-server` is opt-in under profile `gpu`, uses `ghcr.io/ggml-org/llama.cpp:server-cuda`, one NVIDIA GPU, `-c 4096 -ngl 28`, and publishes `127.0.0.1:8080`.
- `.dockerignore` excludes `tests/`, `data/`, `.cache/`, `models/`, `.env*`, `.planning/`, `tools/`, and VCS/CI files from the image context.

## Environment Configuration

**Required or meaningful env vars:**
- Local endpoint (optional): `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT`.
- Cloud (optional, cloud mode only): `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Docling offline artifacts (optional): `DOCLING_ARTIFACTS_PATH`.
- Logging (optional): `RAG_LOG_LEVEL`, `RAG_LOG_DIR`.
- Setup integrity (optional): `RAG_REQUIRE_CHECKSUMS=1` makes a missing SHA-256 a hard download failure.
- Bind safety (optional): `RAG_ALLOW_NON_LOOPBACK=1`.
- Runtime backend defaults: `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`; `LITELLM_TELEMETRY=False`.
- Docker-only: `PYTHONUNBUFFERED=1`, plus the Compose-passed values above.

**Secrets location:**
- Environment variables, operator-created `.env` (loaded by `python-dotenv`; **not present** in the workspace), Streamlit secrets `.streamlit/secrets.toml` (**not present**), or in-memory `st.session_state`.
- No `.env`, `.env.*`, `secrets.toml`, or credential file exists on disk to read; only their absence is recorded here.
- `.gitignore` excludes `.env`, `.env.*`, databases, models, binaries, and caches. The repository does track `.streamlit/config.toml`, which contains no secrets.

## Setup-Time Downloads (Explicit, Operator-Initiated)

- **Hugging Face — GGUF weights:** `setup.py` downloads:
  - `Qwen2-VL-2B-Instruct-Q4_K_M.gguf` from `https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/...`, saved as `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (legacy filename; GGUF metadata is Qwen2-VL).
  - `mmproj-Qwen2-VL-2B-Instruct-f16.gguf` from the same repository, saved as `models/mmproj-f16.gguf`.
  - Implementation: stdlib `urllib.request` with streaming progress, minimum-size checks, pinned SHA-256 verification, and atomic replacement. No HF SDK is required.
- **GitHub Releases — llama.cpp binaries:** release `b11718` from `https://github.com/ggml-org/llama.cpp/releases/download/b11718/...` with a fallback mirror on the legacy `ggerganov/llama.cpp` path.
  - Artifacts: Windows CUDA 12.4 (`llama-...-bin-win-cuda-12.4-x64.zip` + `cudart-...`), Windows CPU, Linux CPU, Linux CUDA 12.8.
  - Every archive has a pinned SHA-256 in `LLAMA_ARCHIVE_SHA256`; `RAG_REQUIRE_CHECKSUMS` turns missing pins into hard failures. Extraction rejects traversal and symlinks.
  - CLI: `python setup.py download_models`, `--llama-only` / `setup_llama_server`, `--models-only`, `--lockfile`, or console scripts `rag-download-models` / `rag-setup-llama`.
- **Hugging Face — sentence-transformers:** `all-MiniLM-L6-v2` is downloaded on first `SentenceTransformer(...)` load (`retrieval/local_embedding.py`), or pre-cached by `setup.py::precache_embedding_model`. No `HF_HOME` override is configured, so the default Hugging Face cache is used.
- **Docling model artifacts:** first use may download layout/table models through Docling. `DOCLING_ARTIFACTS_PATH` pins a fully offline artifact directory. This is model acquisition, not document-content egress.
- **RapidOCR ONNX weights:** initialized once by `setup.py::precache_ocr_model` or lazily on first OCR page (`ingestion/ocr_fallback.py`); inference runs on CPU.

## Webhooks & Callbacks

**Incoming:**
- **None.** No FastAPI/Flask routes, no upload webhook, no callback endpoint.
- The only inbound HTTP surfaces are the Streamlit UI on port `8501` and Streamlit's built-in health route `/_stcore/health`, which the Docker healthcheck polls.
- PDF uploads are in-process Streamlit widget events validated by `ingestion/upload_validation.py`: `%PDF-` magic bytes, 50 MB maximum, 500 pages maximum, at least one page.

**Outgoing:**
- **No webhook delivery or event publishing.**
- Outbound traffic is limited to: the configured local llama-server endpoint, cloud provider APIs when explicitly enabled and consented, and setup-time model/binary downloads.
- Browser-side egress is suppressed in local mode by `ui/sanitizer.py`, which strips scripts/SVG/iframes/objects/embeds, neutralizes external Markdown and HTML links/images, and blocks `javascript:`, `data:`, `vbscript:`, and `file:` schemes.

---

*Integration audit: 2026-10-22*
