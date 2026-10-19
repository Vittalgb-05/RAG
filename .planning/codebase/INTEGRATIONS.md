# External Integrations

**Analysis Date:** 2026-10-19

## APIs & External Services

**Local Inference (default, no network egress):**
- llama.cpp `llama-server` — local HTTP REST server hosting `Qwen3-VL 2B` GGUF for text + vision generation.
  - Client: `LiteLLMProvider`-independent `httpx.Client` in `llama_cpp_provider.py:79-83`
  - Endpoint resolution: `LLAMA_SERVER_URL` → `LLAMA_SERVER_HOST:LLAMA_SERVER_PORT` (default 8080) → `http://127.0.0.1:8080` (`llama_cpp_provider.py:44-54`)
  - Routes used: `GET /health` (`llama_cpp_provider.py:97`), `POST /v1/chat/completions` (streaming SSE at `llama_cpp_provider.py:242`, non-streaming at `:193`, vision at `:308`)
  - Safety: loopback/host allowlist `{localhost, 127.0.0.1, ::1, host.docker.internal, llama-server}` with SSRF guard raising unless `allow_remote=True` (`llama_cpp_provider.py:61-73`)
  - Auth: none (localhost). Timeouts: connect 2s / read 60s / write 10s (`llama_cpp_provider.py:82`).
  - Out-of-band probing: `start.py` checks `http://{host}:8080/health` and optionally spawns the binary (`start.py:82-178`).

**Cloud LLM — Groq (consent-gated, optional):**
- Groq Cloud API via `groq` SDK — `GroqProvider` (`groq_provider.py:18-170`).
  - SDK/Client: `groq.Groq(api_key=...)` (`groq_provider.py:52`)
  - Default model: `openai/gpt-oss-20b` (`groq_provider.py:24`); app default cloud model `groq/llama-3.3-70b-versatile` (`main.py:122`)
  - Auth: `GROQ_API_KEY` resolved from `st.secrets` then `os.environ` (`groq_provider.py:37-47`)
  - Vision: not supported (`groq_provider.py:169`)

**Cloud LLM — LiteLLM multi-provider (consent-gated, optional):**
- LiteLLM unified router to **Groq, OpenAI, Anthropic** — `LiteLLMProvider` (`litellm_provider.py:104-359`).
  - Default model: `groq/llama-3.3-70b-versatile` (`litellm_provider.py:28`)
  - Auth resolution order: explicit arg → `st.session_state.cloud_api_keys[provider]` → `st.secrets` → `os.environ` (`litellm_provider.py:44-88`)
  - Env vars: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (`litellm_provider.py:50-54`)
  - Known context windows: groq 131072, openai 128000, anthropic 200000 (`litellm_provider.py:30-34`)
  - Vision-capable model prefixes: `openai/gpt-4o`, `openai/gpt-4o-mini`, `anthropic/claude-3`, `anthropic/claude-3-5` (`litellm_provider.py:36-41`)
  - Privacy controls: `LITELLM_TELEMETRY=False` + `litellm.telemetry = False` (`litellm_provider.py:19,24`); `_assert_consent()` raises `PermissionError` unless `user_consented` (`litellm_provider.py:142-148`); API-key scrubbing on errors (`litellm_provider.py:135-140`)
  - Timeouts/retries: 30s timeout, 2 retries for non-stream, 0 retries for stream (`litellm_provider.py:112-113,281,344`)
  - UI provider choices: `groq` → Groq (Llama 3.3 70B), `openai` → OpenAI (GPT-4o mini), `anthropic` → Anthropic (Claude 3.5 Haiku) (`ui/views.py:837-841`)

**Provider abstraction:**
- `BaseModelProvider` contract (`model_provider.py:64-156`) with `ProviderCapabilities` (`model_provider.py:15-41`) and `HealthStatus` (`model_provider.py:44-61`); routing/fallback orchestrated by `AiModel._detect_provider` and `InferenceGate` (`local_llm.py:168-207,26-90`).

## Data Storage

**Databases:**
- SQLite (stdlib `sqlite3`) — canonical document/metadata store.
  - Connection: local file `data/documents.db`, path fixed in `main.py:138`
  - Client/ORM: raw SQL in `DocStore` (`doc_store.py:105-160`); WAL mode, `busy_timeout=5000`, foreign keys on (`doc_store.py:131-136`)
  - Schema (PRAGMA `user_version` migrations): `documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` (`doc_store.py:19-96`)
- LanceDB (embedded, serverless, on-disk) — persistent hybrid vector + FTS store.
  - Connection: `lancedb.connect("data/lancedb")` (`hybrid_retriever.py:36,124`)
  - Client: `HybridRetriever` (`hybrid_retriever.py:88-659`); single `chunks` table with dense vectors + BM25 FTS index (`hybrid_retriever.py:342,439`)
  - Fallback when unavailable: pure-Python `VectorIndex` persisted to `data/lancedb/fallback_store.json` (`hybrid_retriever.py:114-148`)

**File Storage:**
- Local filesystem only.
  - GGUF model weights: `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (~986 MB), `models/mmproj-f16.gguf` (~1.33 GB) — present
  - llama-server native runtime: `tools/llama-server/` (Windows CUDA DLLs + exes, ~1.17 GB) — present
  - Document blob cache: `.cache/<sha256>/<CONFIG_VERSION>/` via `cache_dir_for` (`models.py:17-30`); `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`)
  - HuggingFace model cache: `~/.cache/huggingface/` (transitive; documented `README.md:199`)
  - Benchmark store: `data/lancedb_bench/fallback_store.json`

**Caching:**
- In-process caches only: `st.cache_resource` for the `AiModel` singleton (`main.py:146-157`); module-level `_MODEL_CACHE` for `SentenceTransformer` (`local_embedding.py:24-42`); 5s TTL GPU telemetry cache (`resource_telemetry.py:25,33`). No Redis/Memcached.

## Authentication & Identity

**Auth Provider:**
- None — no end-user auth, accounts, or identity provider. Single-user local app.
- Machine-level credential flow is API-key based only (see env vars below). Cloud keys are held in `st.session_state.cloud_api_keys` (session memory) and cleared on reset (`main.py:89,58-89`).

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry/Datadog/etc.

**Logs:**
- stdlib `logging` with module-level loggers (e.g. `local_llm.py:23`, `hybrid_retriever.py:20`, `logging_setup.py:11-46`).
- `logging_setup.suppress_torch_classes_scan_warning()` filters Streamlit's benign `torch.classes` watcher traceback (`logging_setup.py:16-47`, wired at `main.py:42`).
- User-facing diagnostics via Streamlit (`st.error/st.warning/st.status`); developer diagnostics via `print()`/`logger`.
- Hardware telemetry: NVIDIA GPU VRAM via `nvidia-smi` subprocess (`resource_telemetry.py:33-140`), process RAM via `psutil` (`resource_telemetry.py:172-190`). Graceful degradation when unavailable.

## CI/CD & Deployment

**Hosting:**
- Local workstation (primary) and Docker/Docker Compose (`docker-compose.yml`).
- Optional containerized CUDA llama-server image `ghcr.io/ggml-org/llama.cpp:server-cuda` under `profiles: ["gpu"]` (`docker-compose.yml:29-51`).

**CI Pipeline:**
- GitHub Actions `CI Pipeline` on push/PR to `main` (`.github/workflows/ci.yml`).
  - Steps: checkout → Python 3.11 → `astral-sh/setup-uv@v5` → install `requirements-lock.txt` + `requirements-test.txt` → `ruff check .` + `ruff format --check .` → generate corpus (`tests/data/corpus/generate_corpus.py`) → `pytest tests/ -v`.

## Environment Configuration

**Required env vars:**
- Local mode: none required if `llama-server` runs on the loopback default; optional `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT`.
- Cloud mode (only when user consents): one of `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- Process-level toggles set by code: `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0`, `LITELLM_TELEMETRY=False`.
- Docker Compose forwards `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` (`docker-compose.yml:18-23`).

**Secrets location:**
- `.env` at repo root (gitignored `.gitignore:1`; **not present**, contents never read).
- Streamlit secrets (`st.secrets`) — no `.streamlit/secrets.toml` present; checked at runtime (`groq_provider.py:42`, `litellm_provider.py:80`).
- Enterprise CI has no secret step; CI installs from lockfile only.

## Webhooks & Callbacks

**Incoming:**
- None. No HTTP server endpoints beyond Streamlit's own `/_stcore/health` (used by Docker healthcheck, `Dockerfile:43`).

**Outgoing:**
- Cloud LLM API calls only, and only when Cloud Mode is enabled with explicit user consent (`main.py:198-241`, `litellm_provider.py:142-148`).
- One-time setup/download traffic (not runtime): HuggingFace mirror downloads for GGUF weights (`setup.py:59-78`), GitHub release downloads for `llama-server` binaries (`setup.py:288-493`), and model pre-caching for SentenceTransformer/RapidOCR (`setup.py:196-233`).

## External Content Fetches (one-time, not runtime)

- **HuggingFace Hub** — GGUF text+vision weights and mmproj from `bartowski/Qwen2-VL-2B-Instruct-GGUF` and `lmstudio-community/Qwen2-VL-2B-Instruct-GGUF` (`setup.py:64-76`); embedding `all-MiniLM-L6-v2` (`setup.py:196-206`); Docling model assets (`docling-ibm-models`); RapidOCR ONNX weights (`setup.py:216-233`). No HF token is read in code.
- **GitHub Releases** — llama.cpp `b11718` binaries from `ggml-org/llama.cpp` with `ggerganov/llama.cpp` mirror, per-platform/arch variants (`setup.py:288-493`).

## Privacy Boundary (effective)

- Default runtime is zero-egress: ingestion, OCR, embeddings, vector search, and LLM/VLM inference all execute locally (`main.py:198-211`, `README.md:16`).
- Cloud egress requires a consent dialog (`main.py:198-241`) and is blocked programmatically by `_assert_consent` (`litellm_provider.py:142-148`); external image URLs/scripts in document text and model output are neutralized by `ui/sanitizer.py:19-38` unless cloud mode allows them (`ui/views.py:673`).

---

*Integration audit: 2026-10-19*
