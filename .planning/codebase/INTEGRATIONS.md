# External Integrations

**Analysis Date:** 2026-10-11

## APIs & External Services

**Local inference (primary, no network egress):**
- llama-server (llama.cpp) — OpenAI-compatible chat completions + health probe for Qwen3-VL 2B GGUF
  - SDK/Client: `httpx.Client` over REST (`llama_cpp_provider.py:39-43`)
  - Endpoints: `GET /health` (status), `POST /v1/chat/completions` (stream + non-stream), image input via `image_url` data URI (`llama_cpp_provider.py:116-160,240-262`)
  - Base URL: `http://127.0.0.1:8080` (override via `LlamaCppProvider(base_url=...)`)
  - Auth: none — bound to localhost only (`docs/LOCAL_INFERENCE.md`)

**Cloud inference (optional fallback):**
- Groq Cloud — chat completions via the `groq` Python SDK
  - SDK/Client: `groq.Groq` (`groq_provider.py:12-14,48-53`)
  - Model: `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-26`)
  - Auth: `GROQ_API_KEY` (Streamlit secrets → environment) (`groq_provider.py:36-50`)
  - Used only when the local server is unhealthy; selected in `AiModel._detect_provider` (`local_llm.py:36-56`)
  - Vision: not supported — `analyze_image` raises `NotImplementedError` (`groq_provider.py:151-156`)

**Model hosting:**
- HuggingFace Hub — `sentence-transformers` downloads `all-MiniLM-L6-v2` on first run, cached in `~/.cache/huggingface/` (`local_embedding.py:23`)
  - Integration point: `LocalEmbedding.__init__` (`local_embedding.py:21-23`)
  - No token required for the public model; `HF_TOKEN` mentioned only in a comment, never read

## Data Storage

**Databases:**
- SQLite via stdlib `sqlite3` (`doc_store.py:81-95`)
  - Connection: file path `data/documents.db`, passed to `DocStore(...)` in the `main.py` upload loop
  - Tables: `documents` (PK `doc_id`, UNIQUE `sha256`), `pages` (PK `doc_id,page_num`), `chunks` (PK `chunk_id`)
  - Mode: WAL + `busy_timeout=5000`; schema versioned via `PRAGMA user_version` with `MIGRATIONS` dict (`doc_store.py:56-58,98-110`)
  - Lifecycle: per-operation connection, opened and closed inside `_connect()` context manager (`doc_store.py:81-95`)
  - `data/` is gitignored (`.gitignore:9`)

**File Storage:**
- Local filesystem only
  - Deterministic JSON cache under `.cache/<sha256>/<CONFIG_VERSION>/{pages.json,chunks.json,manifest.json}` written best-effort in `main.py:249-262`; path computed by `cache_dir_for` (`models.py:17-30`)
  - `.cache/` is gitignored (`.gitignore:18`)
  - Synthetic test PDFs written to `tests/data/corpus/*.pdf` by `tests/data/corpus/generate_corpus.py`

**Caching:**
- In-process Streamlit cache: `@st.cache_resource(show_spinner=False)` memoizes one `AiModel` per server process (`main.py:65-72`)
- In-memory vector store: `VectorIndex` (no persistence) held inside `LocalEmbedding`, itself stored in `st.session_state` (`main.py:224-227`)
- No Redis / external cache

## Authentication & Identity

**Auth Provider:**
- None. No user accounts or sessions. The only credential is the optional `GROQ_API_KEY`, resolved with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:36-50`); absence yields an `unreachable` `HealthStatus`, not an error.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/OpenTelemetry).

**Logs:**
- Module-prefixed `print()` for developer diagnostics, e.g. `[LocalEmbedding]`, `[DocStore]`, `[UploadValidation]` (`local_embedding.py:21,23,58`, `doc_store.py:98-110`, `upload_validation.py:106`)
- User-facing feedback via Streamlit (`st.status`, `st.error`, `st.warning`, `st.info`) — never `print`
- Provider health surfaced through the `HealthStatus` schema rendered in the sidebar (`main.py:87-117`)

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (documented in `README.md`); primary operation is local on Windows

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml`
  - Triggers: push / pull_request on `main`
  - Steps: setup Python 3.11 (pip cache) → install `requirements.txt` + `requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`
  - No deploy job, no artifact upload

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — optional; only needed for the cloud fallback path

**Secrets location:**
- Local: `.env` in project root (gitignored) loaded via `python-dotenv`
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]`)
- No `.streamlit/secrets.toml` is committed

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

---

*Integration audit: 2026-10-11*
