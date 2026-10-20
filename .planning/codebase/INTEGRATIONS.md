# External Integrations

**Analysis Date:** 2026-10-20

## Network Posture

The default runtime is **local-only**: PDF parsing, OCR, embeddings, vector search, summarization, and generation all run on the host. Outbound network calls occur only in these cases:

1. **Explicitly consented Cloud Mode** — text excerpts and chat history are sent to Groq, OpenAI, or Anthropic through LiteLLM (`litellm_provider.py`).
2. **First-run artifact acquisition** — HuggingFace model downloads, llama.cpp binary download, and PyPI installs (`setup.py`, `Dockerfile`, `local_embedding.py`, `ocr_fallback.py`).
3. **Loopback HTTP** — requests to the local `llama-server` on `127.0.0.1:8080` or `host.docker.internal:8080`.
4. **Local subprocesses** — `nvidia-smi` telemetry polling (`resource_telemetry.py`).

Browser-side egress is also blocked: `ui/sanitizer.py` neutralizes remote Markdown/HTML images and scripts so rendered document text cannot trigger external requests. Streamlit usage stats and LiteLLM telemetry are disabled (`.streamlit/config.toml:14-15`, `litellm_provider.py:19-26`).

## APIs & External Services

### Local Inference — llama-server (llama.cpp)

- **Service:** Native `llama-server` process exposing an OpenAI-compatible REST API.
- **Binary:** llama.cpp release `b11718`; local install path `tools/llama-server/llama-server.exe` on Windows, `tools/llama-server/llama-server` on Linux (`setup.py:288-305`, `llama_cpp_provider.py:119-125`).
- **Client:** `LlamaCppProvider` in `llama_cpp_provider.py` using `httpx.Client`.
- **Base URL resolution** (`llama_cpp_provider.py:44-54`):
  1. `LLAMA_SERVER_URL` if set.
  2. `http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}` (default port `8080`).
  3. `http://127.0.0.1:8080`.
- **Endpoints used:**
  - `GET /health` — `200` = healthy, `503` = model loading, other = error (`llama_cpp_provider.py:89-141`).
  - `POST /v1/chat/completions` — text generation (`stream: false`) and SSE streaming (`stream: true`, lines prefixed `data:`, terminated by `[DONE]`) (`llama_cpp_provider.py:157-261`).
  - `POST /v1/chat/completions` with `image_url` data-URL content for multimodal analysis (`llama_cpp_provider.py:263-315`).
- **Model:** `qwen3-vl-2b` identifier by default; weights `models/qwen3-vl-2b-instruct-q4_k_m.gguf` plus `models/mmproj-f16.gguf`.
- **Server launch parameters:** `-c 4096 -ngl 28 --port 8080` (`start.py:114-155`, `docker-compose.yml:37-43`).
- **Timeouts:** connect 2 s, read 60 s, write 10 s, pool 5 s (`llama_cpp_provider.py:82`). No automatic retry; failures surface as `RuntimeError`.
- **Security guard:** rejects non-loopback base URLs unless `allow_remote=True`; allowlist includes `localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server`, plus any loopback IP (`llama_cpp_provider.py:56-73`).
- **Docker access:** Compose sets `LLAMA_SERVER_HOST=host.docker.internal` and adds `host-gateway` (`docker-compose.yml:19,24-25`); the optional `gpu` profile runs a containerized CUDA llama-server instead (`docker-compose.yml:29-51`).

### Cloud Inference — LiteLLM (primary cloud path)

- **Client:** `LiteLLMProvider` in `litellm_provider.py` wrapping `litellm.completion`.
- **Providers/models configured in the UI** (`ui/views.py:739-741`):
  - Groq — `groq/llama-3.3-70b-versatile` (`GROQ_API_KEY`)
  - OpenAI — `openai/gpt-4o-mini` (`OPENAI_API_KEY`)
  - Anthropic — `anthropic/claude-3-5-haiku-20241022` (`ANTHROPIC_API_KEY`)
- **Default model:** `groq/llama-3.3-70b-versatile` (`litellm_provider.py:28`, `main.py:121`).
- **Capabilities:** context windows declared as Groq 131,072, OpenAI 128,000, Anthropic 200,000 (`litellm_provider.py:30-34`); vision only for `openai/gpt-4o*` and `anthropic/claude-3*` prefixes (`litellm_provider.py:36-41`).
- **Consent gate:** every generation/stream/vision call calls `_assert_consent()` and raises `PermissionError` unless `user_consented=True` (`litellm_provider.py:142-148, 211, 261, 314`). The UI shows an explicit transmission dialog before enabling (`main.py:197-219`).
- **Key resolution order:** explicit arg → `st.session_state.cloud_api_keys` → `st.secrets` → environment (`litellm_provider.py:44-88`).
- **Resilience:** 30 s default timeout, 2 retries for non-streaming calls, 0 retries for streaming (`litellm_provider.py:112-113, 222-229, 274-282`).
- **Privacy controls:** `LITELLM_TELEMETRY=False` and `litellm.telemetry = False` (`litellm_provider.py:19-26`); API keys are scrubbed from error strings (`litellm_provider.py:135-140`).
- **Wiring:** `main.py:158-185` constructs/caches a `LiteLLMProvider` per session when Cloud Mode is consented, then calls `AiModel.set_cloud_mode(True, cloud_provider=...)`.

### Cloud Inference — Groq direct adapter

- **Client:** `GroqProvider` in `groq_provider.py` using the official `groq` SDK.
- **Default model:** `openai/gpt-oss-20b`, declared context 8,192 (`groq_provider.py:21-35, 91-97`).
- **Key resolution:** Streamlit secrets → `GROQ_API_KEY` environment (`groq_provider.py:37-52`).
- **Vision:** unsupported; `analyze_image` raises `NotImplementedError` (`groq_provider.py:163-170`).
- **When used:** `AiModel._detect_provider` falls back to `GroqProvider()` when `cloud_mode=True` but no explicit cloud provider was supplied (`local_llm.py:168-185`). The main UI normally passes a `LiteLLMProvider` instead, so this adapter is a secondary/direct path used by scripts and tests.

### Model Artifact Downloads (install-time / first-run)

| Artifact | Source | Trigger | Code |
|---|---|---|---|
| `qwen3-vl-2b-instruct-q4_k_m.gguf` | HuggingFace: `bartowski/Qwen2-VL-2B-Instruct-GGUF`, mirror `lmstudio-community/Qwen2-VL-2B-Instruct-GGUF` | `python setup.py` / `download_models` | `setup.py:58-68, 236-285` |
| `mmproj-f16.gguf` | Same HuggingFace repos (`mmproj-...-f16.gguf`) | `python setup.py` / `download_models` | `setup.py:69-77` |
| `llama-server` + CUDA/CPU DLLs | GitHub Releases `ggml-org/llama.cpp` release `b11718`, fallback mirror `ggerganov/llama.cpp` | `python setup.py` / `setup_llama_server` | `setup.py:288-290, 380-480` |
| `all-MiniLM-L6-v2` | HuggingFace Hub via `sentence-transformers` | First `LocalEmbedding` use, or `python setup.py` pre-cache | `local_embedding.py:27-42`, `setup.py:196-213` |
| RapidOCR ONNX weights | RapidOCR package model cache | First OCR engine init, or `python setup.py` pre-cache | `ocr_fallback.py:70-75, 144-148`, `setup.py:216-233` |
| Python packages | PyPI | `pip install -r requirements*.txt`, `pip install -e .`, Docker build | `requirements*.txt`, `Dockerfile:25-33` |

- Downloads are skipped when a file already exists and exceeds a minimum size; `--force` re-downloads (`setup.py:308-378`).
- After artifacts are cached, the application can run fully offline.
- **Naming mismatch to be aware of:** the downloaded repositories are Qwen2-VL 2B, while the local filename and documentation describe Qwen3-VL 2B (`setup.py:61-66` vs `docs/LOCAL_INFERENCE.md`). Verify the checkpoint matches the expected model before benchmarking.

## Data Storage

**Databases:**
- **SQLite** — document metadata, page records, chunks, visual evidence, and cached summaries.
  - Path: `data/documents.db` (`main.py:137`).
  - Client: standard library `sqlite3`, per-operation connections, `PRAGMA journal_mode=WAL`, busy timeout 5 s (`doc_store.py:13, 103-141`).
  - Schema versioning via `PRAGMA user_version` and ordered migrations (`doc_store.py:141-154`).
  - Tables: `documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` (`doc_store.py:18-100`).
  - No SQLite FTS5 index exists in code; BM25 is provided by LanceDB FTS or the Python fallback in `hybrid_retriever.py`.
- **LanceDB** — persistent dense vectors and lexical index.
  - Path: `data/lancedb/` (default `hybrid_retriever.py:36`).
  - Client: `lancedb.connect()` with `pyarrow` records (`hybrid_retriever.py:121-130, 335-350`).
  - Table: `chunks`; columns include `chunk_id`, `doc_id`, `filename`, `page`, `content`, `vector` (384-dim), `extraction`, `char_start`, `char_end`, `bbox_json`.
  - FTS index created on `content` via `create_fts_index("content", replace=True)` (`hybrid_retriever.py:465-473`).
  - Query modes: cosine `search_dense`, `search_fts` (`query_type="fts"`), and RRF fusion in `search_hybrid` (`hybrid_retriever.py:425-564`).
  - **Fallback:** if LanceDB is missing or fails, `VectorIndex` + `data/lancedb/fallback_store.json` provides JSON-backed persistence and pure-Python BM25 (`hybrid_retriever.py:31-36, 113-133, 475-535`).
- **No external database, warehouse, or hosted vector service is used.**

**File Storage:**
- Local filesystem only.
- Uploaded PDFs are processed in memory and not persisted as originals; extracted artifacts are cached under `.cache/<sha256>/<CONFIG_VERSION>/` as `pages.json`, `chunks.json`, `manifest.json` (`ui/ingestion_service.py:277-288`, `models.py:14-30`).
- Model weights in `models/`; llama.cpp binaries in `tools/llama-server/`.
- Docker volumes persist `./data`, `./models`, `./.cache` (`docker-compose.yml:9-13`).

**Caching:**
- In-process `SentenceTransformer` model cache keyed by `(model_name, device)` (`local_embedding.py:23-47`).
- SQLite summary cache keyed by document/profile/content hash (`doc_store.py` summary methods; `summarizer.py`).
- Disk cache for parsed page/chunk artifacts.
- No Redis/Memcached.

## Authentication & Identity

**Auth Provider:**
- **None.** There are no user accounts, login screens, sessions backed by an identity provider, OAuth, SSO, or JWT handling.
- Streamlit serves an unauthenticated UI; any multi-user deployment must add authentication at a reverse proxy or platform layer.
- The only identity-adjacent concept is **per-session state** in `st.session_state`, including in-memory cloud API keys and consent flags (`main.py:56-92`, `ui/views.py:757-770`).

**Cloud credential handling:**
- Keys can come from explicit UI input (session memory only), Streamlit secrets, or environment variables (`litellm_provider.py:44-88`).
- Consent is explicit and revocable; disabling Cloud Mode closes the active provider and clears the cached provider/model/key (`main.py:158-185`, `ui/views.py:772-777`).
- **Secrets present in the tree:** `.env` is absent; `.streamlit/config.toml` only; no `.streamlit/secrets.toml`. No secret values were read. Docker Compose passes keys via host environment interpolation.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry, Rollbar, Bugsnag, OpenTelemetry, or APM integration.

**Logs:**
- Standard library `logging` throughout (`logging.getLogger(__name__)` in most modules).
- `logging_setup.py` adds a targeted filter that suppresses Streamlit's benign `torch.classes` file-watcher traceback; invoked at import time in `main.py:40`.
- Streamlit user-facing feedback uses `st.error` / `st.info` / `st.warning` / `st.status`.
- Logging is local stdout/stderr only; no log shipping.

**Telemetry (local only):**
- GPU VRAM via `nvidia-smi` with a 5 s TTL cache and graceful degradation (`resource_telemetry.py:25-97`).
- Per-process RSS/VMS via `psutil` (`resource_telemetry.py:169-190`).
- Stage latency tracking via `LatencyTracker` (`resource_telemetry.py:193-267`).
- No telemetry is transmitted off-device; Streamlit usage stats are disabled.

## CI/CD & Deployment

**Hosting:**
- Self-hosted: native process (`python start.py` / `streamlit run main.py`) or Docker (`Dockerfile`, `docker-compose.yml`).
- The Docker image listens on `8501` with a `/_stcore/health` health check (`Dockerfile:39-46`).
- No Streamlit Community Cloud manifest, Kubernetes manifests, Helm charts, Terraform, or cloud provider configuration in the repository.
- Hosted deployment cannot reach a laptop loopback llama-server; a reachable model endpoint or private tunnel is required (`README.md:216`).

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml`: checkout, Python 3.11, `uv` with cache, install from `requirements-lock.txt` + `requirements-test.txt`, Ruff lint and format checks, synthetic corpus generation, full pytest suite.
- No Docker build/publish job and no release automation in CI.

## Environment Configuration

**Required env vars (local-only default):**
- None strictly required. `LLAMA_SERVER_URL` / `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT` are optional overrides; default is `http://127.0.0.1:8080`.

**Optional env vars:**
- `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` — only for Cloud Mode.
- `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` — recommended for stability; set programmatically in `main.py`, `local_embedding.py`, `start.py`, and `Dockerfile`.
- `LITELLM_TELEMETRY=False` — set programmatically by `litellm_provider.py`.

**Secrets location:**
- Local: `.env` in project root (gitignored; not present in this working tree) or shell environment.
- Streamlit: `st.secrets` (no `secrets.toml` present).
- Docker: host environment interpolated by `docker-compose.yml`.
- UI-entered keys: Streamlit session memory only.
- **No secret file contents were read during this analysis.**

## Webhooks & Callbacks

**Incoming:**
- None. No webhook endpoints, callback routes, or public API surface beyond Streamlit's own UI and health endpoint.

**Outgoing:**
- None. There are no webhook registrations or callback POSTs.
- All outbound HTTP is request/response (or SSE streaming) to `llama-server` or cloud LLM APIs.

## Data Egress Matrix

| Data | Default (local mode) | Cloud Mode (consented) |
|---|---|---|
| Original PDF bytes | Local memory only | Never transmitted; ingestion VLM is local-only (`ui/views.py:91-96`, `ui/ingestion_service.py:163-171`) |
| Raw image crops / bitmaps | Sent only to local llama-server | Not sent during ingestion; `LiteLLMProvider.analyze_image` exists but is not used by the ingestion path |
| Extracted text, tables, OCR text | Local | Included in prompts to the selected cloud provider |
| Chat question + history | Local | Included in prompts to the selected cloud provider |
| Embeddings | Computed locally on CPU | Never transmitted; no cloud embedding API |
| Vector index / SQLite | Local disk | Never transmitted |
| Visual descriptions | Generated locally | May be included as text in later cloud prompts |

## Integration Risks & Notes

- **Model naming drift:** download URLs point to Qwen2-VL 2B while local filenames/docs say Qwen3-VL 2B; confirm weights and `mmproj` compatibility (`setup.py:58-77`).
- **Two cloud adapters exist:** `LiteLLMProvider` is the UI path; `GroqProvider` remains as a direct fallback in `AiModel._detect_provider`. Keep model defaults (`groq/llama-3.3-70b-versatile` vs `openai/gpt-oss-20b`) aligned if behavior must be consistent (`local_llm.py:174-185`).
- **Cloud streaming disables retries** (`num_retries=0`) while non-streaming uses 2; transient stream failures propagate to the UI (`litellm_provider.py:274-296`).
- **Local llama-server has no retry/backoff**; a cold model or unavailable GPU yields `RuntimeError` or an `unreachable` health status with a suggested launch command (`llama_cpp_provider.py:117-141, 197-200, 260-261`).
- **First-run network dependency:** without pre-cached HuggingFace/RapidOCR artifacts and GGUF weights, offline operation fails. `python setup.py` is the intended warm-up step.
- **LanceDB optional:** absence silently degrades to the JSON + pure-Python fallback, which preserves functionality but changes performance characteristics (`hybrid_retriever.py:113-133`).

---

*Integration audit: 2026-10-20*
