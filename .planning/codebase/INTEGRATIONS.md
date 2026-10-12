# External Integrations

**Analysis Date:** 2026-10-12

## APIs & External Services

**Cloud LLM (direct):**
- Groq Cloud — optional cloud inference fallback
  - SDK/Client: `groq==0.15.0` via `groq.Groq` (`groq_provider.py:13,52`)
  - Auth: `GROQ_API_KEY`
  - Default model: `openai/gpt-oss-20b` (`groq_provider.py:24`); UI preset `groq/llama-3.3-70b-versatile` (`main.py:165`)
  - Endpoints used: `chat.completions.create` sync (`groq_provider.py:117-124`) + streaming (`groq_provider.py:149-159`)
  - Vision: NOT supported — `analyze_image` raises `NotImplementedError` (`groq_provider.py:163-170`)

**Cloud LLM (routed):**
- LiteLLM router → Groq / OpenAI / Anthropic — unified cloud adapter with explicit consent gate
  - SDK/Client: `litellm>=1.50.0` via `litellm.completion` (`litellm_provider.py:223,275,337`)
  - Auth: `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (prefix-mapped in `litellm_provider.py:44-50`)
  - Default model: `groq/llama-3.3-70b-versatile` (`litellm_provider.py:23`); UI presets in `main.py:165-167`
  - Behaviour: bounded `timeout=30.0s`, `num_retries=2` (`litellm_provider.py:104-111`); consent enforced by `_assert_consent()` raising `PermissionError` without opt-in (`litellm_provider.py:132-138`); vision gated by `VISION_SUPPORTED_PREFIXES` (`litellm_provider.py:31-36`)
  - Known context windows: groq 131072 / openai 128000 / anthropic 200000 (`litellm_provider.py:25-29`)

**Local inference server (no egress):**
- llama-server (llama.cpp) hosting Qwen3-VL 2B GGUF — primary local backend
  - SDK/Client: `httpx==0.28.1` `httpx.Client` with `Timeout(connect=2.0, read=60.0, write=10.0, pool=5.0)` (`llama_cpp_provider.py:63-67`)
  - Auth: none (loopback only)
  - Default endpoint: `http://127.0.0.1:8080` (`llama_cpp_provider.py:25`); model `qwen3-vl-2b`, context 4096 (`llama_cpp_provider.py:26-27`)
  - Endpoints used: `GET /health` (200 healthy / 503 loading — `llama_cpp_provider.py:81-100`), `POST /v1/chat/completions` sync + SSE stream (`llama_cpp_provider.py:170-171,219-236`), multimodal `analyze_image` via base64 `image_url` payload (`llama_cpp_provider.py:263-285`)
  - Safety: non-loopback hosts rejected unless `allow_remote=True` (`llama_cpp_provider.py:40-57`); test seam via `httpx.MockTransport` (`llama_cpp_provider.py:28,37`)
  - Setup hint emitted on `ConnectError`: `llama-server -m models/<name>-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c <ctx> -ngl 28 --port 8080` (`llama_cpp_provider.py:103-110`)
  - Docs: `docs/LOCAL_INFERENCE.md`, `docs/RUNBOOK.md`

**Embeddings (local, no egress):**
- sentence-transformers `all-MiniLM-L6-v2` on CPU (`local_embedding.py:22,40`) — 384-dim L2-normalised vectors; weights cached in `~/.cache/huggingface/`

**Document intelligence (local, no egress):**
- Docling `>=2.0.0` — CPU-only pipeline (`do_ocr=False`, `do_table_structure=True`) for reading order/headings/markdown tables (`docling_reader.py:1-7,23-25`)
- RapidOCR (`rapidocr-onnxruntime>=1.3.0`) + PyMuPDF raster (`pymupdf>=1.24.0`, `pillow>=10.2.0`) — conditional page-level OCR when extracted text < 50 chars or status empty/failed (`ocr_fallback.py:29-43`)

## Data Storage

**Databases:**
- SQLite (stdlib `sqlite3`, WAL mode, schema versioning) — document/page/chunk/evidence/summary persistence
  - Connection: per-operation connect/close lifecycle (Windows-lock + Streamlit-loop safe); default file under gitignored `data/` (live local file: `data/documents.db`)
  - Client: `DocStore` in `doc_store.py:1-610` (tables `documents`, `pages`, `chunks`, `evidence_elements` + V2 DDL)
  - Used by: `main.py:20,26` (dedup + persistence across restarts)
- LanceDB (serverless on-disk vector store) — persistent hybrid retrieval
  - Connection: `lancedb.connect(str(db_uri))`, default `<repo_root>/data/lancedb` (`hybrid_retriever.py:27,92-115`); live local dir `data/lancedb/` present
  - Client: `lancedb` + `pyarrow` (`hybrid_retriever.py:20-21`), guarded import with pure in-memory fallback (`hybrid_retriever.py:19-24,100-120,151`)
  - Fusion: dense + BM25-style FTS with Reciprocal Rank Fusion `k_rrf=60` (`hybrid_retriever.py:28,31-50`)
- In-memory only: `VectorIndex` (stdlib `math`, no driver) — per-session k-NN inside `LocalEmbedding.store` (`local_embedding.py:43`, `vector_index.py:1-228`); lost on restart
- Disk cache: content-addressed `.cache/<sha256>/<CONFIG_VERSION>/` via `cache_dir_for` (`models.py:17-30`, `CONFIG_VERSION = "docling-1000-200-v1"`); `.cache/` gitignored (`.gitignore:17`)

**File Storage:**
- Local filesystem only — uploads validated then persisted via `DocStore`; no S3/GCS/Azure integration
- Upload validation: `validate_pdf_bytes` + `MAX_FILE_MB` (`upload_validation.py`, wired in `main.py:37`)

**Caching:**
- GPU telemetry 5s TTL cache to avoid `nvidia-smi` spawn storms (`resource_telemetry.py:25-30,33-97`)
- Latency history ring buffer `MAX_STAGE_HISTORY = 200` (`resource_telemetry.py:23`)
- Summary results cached in SQLite `DocStore` (`summarizer.py`, `models.SummaryResult`)
- No Redis/Memcached

## Authentication & Identity

**Auth Provider:**
- Custom (API-key passthrough, no OAuth/SSO)
  - Implementation: key resolution order explicit-arg → `st.session_state.cloud_api_keys` → `st.secrets` → `os.environ` (`litellm_provider.py:39-85`); Groq-direct variant `st.secrets` → `os.environ` (`groq_provider.py:37-47`)
  - Privacy gate: `LiteLLMProvider(user_consented=False)` by default; `set_consent()` flips (`litellm_provider.py:128-138`); every network call asserts consent first (`litellm_provider.py:201,250,302`)
  - Tests use mock key `test-key-not-a-secret-mock-value` via `fake_env_groq_key` (`tests/conftest.py:14-15`); never a real credential

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/Datadog/OTel integration)

**Logs:**
- Stdlib `logging` per module (`logger = logging.getLogger(__name__)`) — e.g. `local_embedding.py:16`, `litellm_provider.py:16`, `docling_reader.py:20`, `resource_telemetry.py:18`
- Telemetry module (`resource_telemetry.py:1-245`): `get_gpu_memory_info()` (nvidia-smi CSV parse, `None` on headless/CI), `get_process_memory_info()` (psutil RSS/VMS, zeros when psutil absent), `LatencyTracker` / `track_stage` context managers, `get_system_telemetry_snapshot()` (timestamp + gpu + process + stage summaries)
- Benchmarks: `scripts/benchmark_baseline.py` (extraction/chunk/CPU-embed/search/memory → `.planning/research/BASELINE_BENCHMARK.json`), `scripts/profile_resources.py` (cold-vs-warm/LanceDB/summarizer/VRAM headroom → `.planning/research/RESOURCE_PROFILE.json`)
- Docs: `docs/EVALUATION.md` (quality gates), `docs/RUNBOOK.md` (ops)

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (or any `streamlit run main.py` host); devcontainer auto-launch on port 8501 (`.devcontainer/devcontainer.json:21-32`)

**CI Pipeline:**
- GitHub Actions (`.github/workflows/ci.yml`, 41 lines): push/PR to `main` → `ubuntu-latest` + Python 3.11 + pip cache → `pip install -r requirements.txt` + `pip install -r requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`
- NOTE: CI does NOT install or verify `requirements-lock.txt` — lockfile is currently unenforced (see STACK.md pin-consistency audit)

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — Groq-direct + LiteLLM-groq paths (only key strictly required for cloud fallback)
- `OPENAI_API_KEY` — only when LiteLLM model prefix is `openai/`
- `ANTHROPIC_API_KEY` — only when LiteLLM model prefix is `anthropic/`
- No `HF_TOKEN` read in code (public embedding model needs none); no other service keys

**Secrets location:**
- Local: `.env` in project root (gitignored, loaded by `load_dotenv()` at `main.py:91`)
- Cloud: Streamlit secrets panel (`st.secrets["GROQ_API_KEY"]` etc.)
- Session-scoped: `st.session_state.cloud_api_keys` / `cloud_api_key` (per-user keys entered in UI, `main.py:190`, `litellm_provider.py:56-71`)
- Forbidden: never commit `.env`, `.streamlit/secrets.toml`, or any key material; test fixtures use mock values only

## Webhooks & Callbacks

**Incoming:**
- None (no webhook receivers, no API routes — Streamlit UI only)

**Outgoing:**
- `POST {llama-server}/v1/chat/completions` (local loopback, OpenAI-compatible + SSE) — `llama_cpp_provider.py:170,219,285`
- `GET {llama-server}/health` (local loopback health probe) — `llama_cpp_provider.py:81`
- Groq `chat.completions.create` (sync + stream) via `groq` SDK — `groq_provider.py:117,149`
- `litellm.completion` (sync + stream + vision) to Groq/OpenAI/Anthropic endpoints — `litellm_provider.py:223,275,337`

---

*Integration audit: 2026-10-12*
