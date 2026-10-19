# External Integrations

**Analysis Date:** 2026-10-19

## APIs & External Services

**Cloud LLM inference (optional, explicit user consent required):**
- Groq — cloud text generation via two paths:
  - Direct SDK `GroqProvider` (`groq_provider.py:18-170`), model `openai/gpt-oss-20b` (`groq_provider.py:24`), SDK `groq==0.15.0`
  - Via LiteLLM `LiteLLMProvider` (`litellm_provider.py:104-359`), default model `groq/llama-3.3-70b-versatile` (`litellm_provider.py:28`)
  - Auth: `GROQ_API_KEY` (`groq_provider.py:42-47`)
- OpenAI — cloud generation + optional vision via LiteLLM; UI option `openai/gpt-4o-mini` (`main.py:228`), vision prefixes `openai/gpt-4o*` (`litellm_provider.py:36-41`)
  - SDK/Client: `litellm>=1.50.0`
  - Auth: `OPENAI_API_KEY` (`litellm_provider.py:52`)
- Anthropic — cloud generation via LiteLLM; UI option `anthropic/claude-3-5-haiku-20241022` (`main.py:229`), vision prefixes `anthropic/claude-3*` (`litellm_provider.py:36-41`)
  - Auth: `ANTHROPIC_API_KEY` (`litellm_provider.py:53`)
- Provider routing/quota reference: `KNOWN_CONTEXT_WINDOWS` (`litellm_provider.py:30-34`)
- Privacy gate: all cloud calls raise `PermissionError` unless `user_consented=True` (`litellm_provider.py:142-148,211,261,314`); API keys are scrubbed from error strings (`litellm_provider.py:135-140`). LiteLLM telemetry explicitly disabled (`litellm_provider.py:19-24`).

**Local LLM inference (default, zero-egress):**
- llama.cpp `llama-server` — OpenAI-compatible REST at `http://127.0.0.1:8080` via `httpx` (`llama_cpp_provider.py:26-33,66-70`)
  - Endpoints used: `GET /health` (with 503 = "loading", `llama_cpp_provider.py:84-103`), `POST /v1/chat/completions` for text, streaming SSE, and multimodal image payloads (`llama_cpp_provider.py:180,229,295`)
  - Model: Qwen3-VL 2B GGUF (`qwen3-vl-2b-instruct-q4_k_m.gguf`) + `mmproj-f16.gguf` vision projector (`start.py:127-128`, `setup.py:59-78`)
  - Security: non-loopback hosts rejected unless `allow_remote=True` (SSRF guard, `llama_cpp_provider.py:43-60`)
  - Auth: none (local, no API key)

**Model / artifact downloads (setup-time only, not runtime):**
- HuggingFace — GGUF weights for Qwen2-VL 2B (mirrors `bartowski/...`, `lmstudio-community/...`) (`setup.py:64-76`); `all-MiniLM-L6-v2` SentenceTransformer cached via `SentenceTransformer(...)` (`setup.py:196-213`, `local_embedding.py:27-42`)
  - Runtime cache location: `~/.cache/huggingface/` and project `.cache/` (`.gitignore:17`, `models.py:17-30`)
- GitHub Releases (`ggml-org/llama.cpp`, mirror `ggerganov/llama.cpp`) — pinned `llama-server` release `b11718`, CUDA 12.4/12.8 and CPU builds for Windows/Linux (`setup.py:288-493`)
- NVIDIA `nvidia-smi` — no network; local subprocess for GPU presence and VRAM telemetry (`setup.py:293-299`, `resource_telemetry.py:58-144`)

## Data Storage

**Databases:**
- SQLite (stdlib `sqlite3`) — document metadata, pages, chunks, evidence elements, cached summaries
  - Connection: file path `data/documents.db` (`main.py:139-141`)
  - Client: `doc_store.py` `DocStore` class; WAL mode + busy timeout, per-operation connections, schema versioning via `PRAGMA user_version` (`doc_store.py:122-154`)
  - Tables: `documents`, `pages`, `chunks` (v1); `evidence_elements` (v2); `document_summaries` (v3) (`doc_store.py:17-100`)
- LanceDB — persistent on-disk dense vector table + full-text index, default URI `data/lancedb` (`hybrid_retriever.py:36,124`)
  - Client: `lancedb` + `pyarrow`, table `chunks`, upsert via `merge_insert`, FTS via `create_fts_index` (`hybrid_retriever.py:194-205,256-532`)
  - Fallback when LanceDB unavailable: JSON store at `data/lancedb/fallback_store.json` backed by pure-Python `VectorIndex` (`hybrid_retriever.py:113-146,169-192`)
  - Working copies present in repo: `data/documents.db`, `data/lancedb`, `data/lancedb_bench`

**File Storage:**
- Local filesystem only. Per-document cache dirs `<repo>/.cache/<sha256>/<CONFIG_VERSION>` (`main.py:140,581`, `models.py:14-30`); model weights in `models/`; downloaded binaries in `tools/` (gitignored, `.gitignore:16-23`). No S3/GCS/Azure/file API integrations in runtime code (boto3 appears only transitively via `litellm`, `requirements-lock.txt:32-37`).

**Caching:**
- In-process: `st.cache_resource` AI model singleton (`main.py`), process-level `SentenceTransformer` cache (`local_embedding.py:23-47`), 5 s TTL GPU telemetry cache (`resource_telemetry.py:25-97`)
- Persisted: SQLite `document_summaries` cache keyed by `(sha256, profile)` with `model_version` invalidation (`doc_store.py:73-94,425-514`)

## Authentication & Identity

**Auth Provider:**
- None / custom. No OAuth, SSO, or identity provider. Single-user local app.
- Cloud inference keys resolved in precedence order: explicit arg → `st.session_state.cloud_api_keys` → `st.secrets` → `os.environ` (`litellm_provider.py:44-88`)
- Session keys are held in memory only, entered via password `st.text_input` and cleared on reset (`main.py:255-265,94`; `README.md:210`)
- Consent is an explicit per-session flag gating all cloud egress (`litellm_provider.py:142-148`; UI dialog `main.py:203-224`)

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/etc.). Errors surface via stdlib `logging` (`logging.getLogger(__name__)` across modules) and Streamlit UI error/warning calls.

**Logs:**
- stdlib `logging`; a custom filter `TorchClassesScanLogFilter`/`suppress_torch_classes_scan_warning` silences Streamlit's benign `torch.classes` file-watcher traceback (`logging_setup.py:11-47`, wired at `main.py:39,51`)
- Resource telemetry: `resource_telemetry.py` — GPU VRAM via `nvidia-smi`, process RSS/VMS via `psutil`, per-stage latency via `LatencyTracker`, snapshot aggregation (`resource_telemetry.py:33-319`)

## CI/CD & Deployment

**Hosting:**
- Local / self-hosted. Docker image (`Dockerfile:3`) + Compose stack with optional GPU `llama-server` sidecar (`docker-compose.yml:28-51`). No cloud PaaS manifest committed.

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` — on push/PR to `main`; Python 3.11, `uv` install from `requirements-lock.txt` + `requirements-test.txt`, `ruff check`/`ruff format --check`, generate synthetic corpus, `pytest tests/ -v`

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — required only for Groq cloud mode (`groq_provider.py:47`, `litellm_provider.py:51`); mocked in tests (`tests/conftest.py:14-15`)
- `OPENAI_API_KEY` — required only for OpenAI cloud mode (`litellm_provider.py:52`)
- `ANTHROPIC_API_KEY` — required only for Anthropic cloud mode (`litellm_provider.py:53`)
- `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT` — Compose container reaching host llama-server (`docker-compose.yml:19-20`)
- `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` — force PyTorch backend, suppress TF (`main.py:26-28`, `start.py:34-36`)
- `LITELLM_TELEMETRY=False` — privacy default (`litellm_provider.py:19`)
- Local dev secrets in `.env` (gitignored; **not present in working tree** — existence noted only). No `.streamlit/secrets.toml` present.

**Secrets location:**
- `.env` file (local), Streamlit secrets panel (`st.secrets`) for hosted deployments, or OS environment. All gitignored / never committed. Session-entered keys live only in `st.session_state` memory.

## Webhooks & Callbacks

**Incoming:**
- None.

**Outgoing:**
- None. All external calls are request/response (cloud completions, model/binary downloads at setup). No webhook registration or callback endpoints.

---

*Integration audit: 2026-10-19*
