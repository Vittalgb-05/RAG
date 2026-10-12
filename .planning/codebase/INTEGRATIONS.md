# External Integrations

**Analysis Date:** 2026-10-13

## APIs & External Services

**Local inference (default, zero egress):**
- llama.cpp `llama-server` over loopback HTTP — text generation, SSE token streaming, `analyze_image` VLM calls
  - Client: `LlamaCppProvider` (`llama_cpp_provider.py:27+`), transport `httpx` (injectable `httpx.MockTransport` for tests)
  - Endpoint: `base_url="http://127.0.0.1:8080"` (`llama_cpp_provider.py:30`); non-loopback hosts rejected unless `allow_remote=True` (SSRF guard via `ipaddress` + `urlparse`, `llama_cpp_provider.py:40-60`)
  - Model: `qwen3-vl-2b` / `qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16` (~2.4 GB VRAM vs 4 GB ceiling); context 4096; setup in `docs/LOCAL_INFERENCE.md`
  - Image path: base64-encoded PNG crops from `VisualAnalyzer.crop_visual_element` → `analyze_image(image_bytes, prompt)` (`visual_analyzer.py:138-186`, `llama_cpp_provider.py`)
  - Auth: none (local socket); health via `check_health()` → `HealthStatus(status="healthy"|"unreachable", ...)` with `llama-server -m models/...` remediation text (`tests/conftest.py:110-117`)

**Cloud inference (explicit opt-in only, consent-gated):**
- Groq API (direct path)
  - SDK/Client: `groq==0.15.0`, `groq.Groq` wrapped by `GroqProvider` (`groq_provider.py:12`)
  - Default model: `openai/gpt-oss-20b`, context 8192 (`groq_provider.py:22`)
  - Auth: `GROQ_API_KEY` — precedence explicit arg → Streamlit session state (isolated per-session post-audit, P1-3) → `st.secrets["GROQ_API_KEY"]` → `os.environ`; missing key raises `ValueError` naming both locations
- LiteLLM multi-cloud router (`litellm_provider.py`)
  - SDK/Client: `litellm>=1.50.0` (locked `1.105.0`), guarded `try/except ImportError → litellm = None` (`litellm_provider.py:22-25`)
  - Routes: `groq/llama-3.3-70b-versatile` (DEFAULT_CLOUD_MODEL), `openai/gpt-4o-mini`, `anthropic/claude-3.5-haiku` and prefix-matched siblings; `KNOWN_CONTEXT_WINDOWS` groq 131072 / openai 128000 / anthropic 200000; vision enabled only for `openai/gpt-4o*`, `anthropic/claude-3*` (`VISION_SUPPORTED_PREFIXES`)
  - Auth: per-prefix env map `groq→GROQ_API_KEY`, `openai→OPENAI_API_KEY`, `anthropic→ANTHROPIC_API_KEY` (`_resolve_api_key_for_model`, `litellm_provider.py:42+`); bounded timeouts/retries; strict programmatic privacy gate — cloud call blocked without recorded user consent (INF-04/UI-04, `tests/test_cloud_privacy.py` 251 lines)
  - Contract: implements `BaseModelProvider` (`model_provider.py:10+`) — `generate_text` / `stream_text` (generator of `str`) / `analyze_image` / `check_health` / `get_capabilities`

**Embeddings (local, no network at query time after first download):**
- HuggingFace `sentence-transformers` `all-MiniLM-L6-v2`, 384-dim, CPU device (`local_embedding.py:11`); weights from HF Hub → `~/.cache/huggingface/`; shared-across-sessions in-RAM singleton post-audit (P1-2); deterministic `MagicMock` seam in `tests/conftest.py:55-85` keeps suite 100% offline

**Document parsing (local libraries, no SaaS):**
- Docling (`docling>=2.0.0`, locked `2.138.0`): `DocumentConverter` + `PdfPipelineOptions` + `DocumentStream/InputFormat` (`docling_reader.py:23-25`); tables via `doc.iterate_items()` / `doc.tables` / `export_to_markdown()` fallbacks (`docling_reader.py:122-167`); missing/failed → `PdfReader` (pypdf) fallback
- RapidOCR (`rapidocr-onnxruntime>=1.3.0`, locked `1.4.4` + `onnxruntime==1.31.0` + `opencv-python==5.0.0.93`): `RapidOCR()` CPU `CPUExecutionProvider` (`ocr_fallback.py:63-68`); selectively run per page via `apply_conditional_ocr` (`main.py` import); zoom/DPI budgets clamped post-audit (P1-2)
- PyMuPDF (`pymupdf>=1.24.0`, locked `1.28.2`, `import fitz`): raster render `fitz.open(stream=...)` + `fitz.Matrix(zoom, zoom)` (`ocr_fallback.py:96-104`); drawing-inspection detection + `fitz.Rect` union + 2x PNG crops capped at 2048² px with truncation warnings (`visual_analyzer.py:65-186`, P1-2)

## Data Storage

**Databases:**
- SQLite via stdlib `sqlite3` — `DocStore` ACID document/metadata store (`doc_store.py:13,105-141`): `sqlite3.connect(db_path, timeout=5.0)`, `row_factory = sqlite3.Row`, `_apply_migrations`; dedup by SHA-256 (`sha256_bytes`, `doc_id_for` in `upload_validation.py`); persistent `delete` + `purge_all` added in `619814a` (P1-1, `doc_store.py`, `tests/test_doc_store.py` +79 lines); `HybridRetriever.purge` mirrors it (`hybrid_retriever.py`, `tests/test_hybrid_retriever.py` +22)
  - Connection: local file under `data/` (gitignored); anchored paths post-audit (P1-1)
  - Client: no ORM — raw `sqlite3` + contextmanager `_connect` generator
- LanceDB (`lancedb>=0.17.0`, locked `0.40.0` + `pyarrow>=14`, locked `23.0.1`) — persistent on-disk vector + BM25/FTS5 hybrid table `chunks` with RRF fusion (`hybrid_retriever.py:1-4,80-120`): `lancedb.connect(str(db_uri))` at `data/lancedb` (`DEFAULT_DB_URI`, `hybrid_retriever.py:27`); optional import (`lancedb = None` fallback, `hybrid_retriever.py:18-23`) → disk-backed in-memory mode; existing-table reopen path (`hybrid_retriever.py:194-200`)
- In-memory `VectorIndex` (`vector_index.py`, 228 lines, stdlib-only) — legacy/embedded linear-scan cosine k-NN; no disk I/O

**File Storage:**
- Local filesystem only: uploads via `st.file_uploader` → `validate_pdf_bytes` (size/pages/MIME/magic-byte checks, `MAX_FILE_MB`, `MAX_PAGES` in `upload_validation.py:113`) → `DocStore` persistence; visual crops transient `bytes` (PNG); `data/` excluded from git (`.gitignore`)
- Cache: content-hash-keyed summary cache (`Summarizer`, `models.SummaryResult`) with cache-version field post-audit (P1-1, `tests/test_cache_invalidation.py` 218 lines); embedding-index cache versioning (`local_embedding.py`, `tests/test_local_embedding.py` +15)

**Caching:**
- No Redis/Memcached. App-level: `@st.cache_resource` singletons (model/provider), `st.session_state` per-browser-session index, summary content-hash cache, GPU telemetry 5.0 s TTL (`_GPU_CACHE_TTL_SECONDS`, `resource_telemetry.py`)

## Authentication & Identity

**Auth Provider:**
- None for the app itself — single-user local workstation design (documented post-audit, P1-3). No login, no user store
  - Implementation: Streamlit session-state isolation — `AiModel` instance and cloud-consent flag scoped to `st.session_state`, not globals (`local_llm.py`, `main.py`, `tests/test_main_ui.py` +69 in `619814a`)
- Upstream credentials (all user-supplied, never committed):
  - `GROQ_API_KEY` → Groq direct + `groq/*` via LiteLLM
  - `OPENAI_API_KEY` → `openai/*` via LiteLLM
  - `ANTHROPIC_API_KEY` → `anthropic/*` via LiteLLM
  - `HF_TOKEN` mentioned only in a comment, never read in code

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/DataDog). Per-file upload `try/except → st.error(...) → continue` isolation (`main.py`); constructor validation raises (`ValueError`/`TypeError` in `vector_index.py`, `upload_validation.py`, `LlamaCppProvider` loopback guard); no retry/timeout wrapper on the Groq stream (surfaces as Streamlit exception page — see `CONCERNS.md`)

**Logs:**
- stdlib `logging` per module (`logger = logging.getLogger(__name__)`) + developer `print("[LocalEmbedding] ...")` lifecycle lines; user-facing feedback exclusively via `st.*` (`st.error/info/success/status/write`)
- Latency instrumentation: `LatencyTracker` contextmanager + `_LATENCY_HISTORY` registry (cap 200/stage, thread-locked) in `resource_telemetry.py:22-33`
- Benchmark artifacts: `scripts/profile_resources.py` (342 lines, QUAL-01) → `.planning/research/RESOURCE_PROFILE.json` (live RTX 3050: 4096 MB total, 690 MB used, projected peak 3450 MB, 646 MB headroom); `scripts/benchmark_baseline.py` (174 lines); `scripts/benchmark_multimodal.py` (292 lines, NEW in `619814a`, QUAL-02/P0-3) → `.planning/research/MULTIMODAL_BENCHMARK.json` (factual/visual/abstention/citation 100%, avg latency 0.087 s, deterministic offline provider)
- Docs: `docs/EVALUATION.md`, `docs/RUNBOOK.md` (purge/ops updated in `619814a`), `docs/LOCAL_INFERENCE.md`

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (live app) + local `streamlit run main.py` + devcontainer port 8501. No containers/Dockerfile in repo

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` (44 lines), trigger `push`/`pull_request` on `main`, single job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`:
  1. `actions/checkout@v4` → 2. `actions/setup-python@v5` (3.11) → 3. `astral-sh/setup-uv@v5` (cache on) → 4. `uv pip install --system -r requirements-lock.txt` + `-r requirements-test.txt` (P0-1 fix — installs FROM the lockfile, `ci.yml:28-31`) → 5. `ruff check .` + `ruff format --check .` → 6. `python tests/data/corpus/generate_corpus.py` (synthetic fixtures incl. `clean_digital.pdf` 20 pp, `dense_table.pdf`, `multi_column.pdf`) → 7. `pytest tests/ -v` (24 modules, 217 passing per README badge; offline via `tests/conftest.py` mocks — mock Groq streaming deltas, mock 384-dim ST vectors, mock LlamaCpp provider)

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — required ONLY for cloud-fallback paths (direct Groq + `groq/*` LiteLLM routes); local-only operation needs none
- `OPENAI_API_KEY` — required only for `openai/*` LiteLLM routes
- `ANTHROPIC_API_KEY` — required only for `anthropic/*` LiteLLM routes
- `LLAMA_SERVER_URL` (optional, defaults `http://127.0.0.1:8080`) — local llama-server endpoint; must be loopback unless explicitly overridden

**Secrets location:**
- Local: `.env` file in repo root (gitignored, absent from tree — existence only, never read); loaded via `load_dotenv()`
- Cloud: Streamlit secrets panel (`st.secrets`); no `.streamlit/secrets.toml` committed
- Tests: fake key `test-key-not-a-secret-mock-value` via `fake_env_groq_key` fixture (`tests/conftest.py:12-15`); `httpx.MockTransport`-based provider doubles — no real credentials anywhere in repo

## Webhooks & Callbacks

**Incoming:**
- None — no webhook receivers, no API routes; only Streamlit UI interactions and loopback llama-server client calls

**Outgoing:**
- Cloud LLM completions (consent-gated): `groq.chat.completions.create` (streaming deltas, `groq_provider.py`), `litellm.completion` fan-out to Groq/OpenAI/Anthropic (`litellm_provider.py`)
- Local LLM/VLM (loopback): `POST {base_url}/completion` + SSE stream + `/v1/chat`-style image endpoint via `httpx` (`llama_cpp_provider.py`)
- One-time model fetch: HuggingFace Hub download of `all-MiniLM-L6-v2` on first embedding run (cached thereafter)
- Zero egress by default: local-only mode makes no outbound calls; `tests/test_cloud_privacy.py` asserts no document text/embeddings/queries leave the machine without consent

---

*Integration audit: 2026-10-13*
