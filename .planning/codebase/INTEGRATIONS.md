# External Integrations

**Analysis Date:** 2026-10-11

## APIs & External Services

**Local inference (primary, zero network egress):**
- llama-server (llama.cpp) — OpenAI-compatible chat completions + health probe serving Qwen3-VL 2B Q4_K_M GGUF + `mmproj-f16` projector
  - SDK/Client: `httpx.Client(base_url, timeout=connect 2.0 / read 60.0 / write 10.0 / pool 5.0)` over REST (`llama_cpp_provider.py:39-43`)
  - Endpoints: `GET /health` → `healthy` (200) / `loading` (503) / `error` / `unreachable` (ConnectError → setup command in message) (`llama_cpp_provider.py:49-94`); `POST /v1/chat/completions` non-stream (`generate_text`, `llama_cpp_provider.py:110-153`) and SSE stream (`stream_text`, parses `data: ` lines until `[DONE]`, skips `:` keep-alives, `llama_cpp_provider.py:155-214`); vision via `image_url` base64 data-URI payload (`analyze_image`, `llama_cpp_provider.py:216-268`)
  - Defaults: `base_url="http://127.0.0.1:8080"`, `model_name="qwen3-vl-2b"`, `context_window=4096` (`llama_cpp_provider.py:21-26`)
  - Server launch (external binary, not pip): `llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port 8080 --host 127.0.0.1` (`docs/LOCAL_INFERENCE.md:52-60`; health message reproduces the command at `llama_cpp_provider.py:79-82`)
  - Auth: none — bound to `127.0.0.1` only (`docs/LOCAL_INFERENCE.md:66-68`)
  - Capabilities: `supports_vision=True, is_local=True, supports_streaming=True` (`llama_cpp_provider.py:96-108`)

**Cloud inference (optional fallback, only egress path):**
- Groq Cloud — chat completions via the `groq` Python SDK (`groq==0.15.0`, guarded `try/except ImportError → Groq=None` in `groq_provider.py:12-15`)
  - SDK/Client: `groq.Groq(api_key)` (`groq_provider.py:50-52`); `chat.completions.create` non-stream (`groq_provider.py:116-126`) and stream yielding `chunk.choices[0].delta.content` (`groq_provider.py:148-161`)
  - Model: `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-25`)
  - Auth: `GROQ_API_KEY` with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); missing key/package yields `unreachable` `HealthStatus`, never raises (`groq_provider.py:59-83`)
  - Selection: used only when the local server is unhealthy; chosen in `AiModel._detect_provider` (local → Groq → local-with-diagnostics) and re-probed on every unhealthy `check_health()` (`local_llm.py:46-89`)
  - Capabilities: `supports_vision=False, is_local=False, supports_streaming=True` (`groq_provider.py:85-97`)
  - Vision: not supported — `analyze_image` raises `NotImplementedError` (`groq_provider.py:163-170`); visual evidence degrades to `[Visual element: vision analysis unsupported by active model]` (`visual_analyzer.py:246-249`)

**Model hosting:**
- HuggingFace Hub (embedding weights) — `sentence-transformers` downloads `all-MiniLM-L6-v2` on first run, cached in `~/.cache/huggingface/` (`local_embedding.py:22`); no token required for the public model
- HuggingFace Hub (GGUF weights) — `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB) + `mmproj-f16.gguf` (~450 MB) downloaded manually into local `models/` (`docs/LOCAL_INFERENCE.md:31-44`); consumed by the external `llama-server` process, never imported in Python
- Docling model zoo — first `DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(...)})` construction (`docling_reader.py:103-109`) downloads layout/table-structure weights on CPU; converter is lazily built inside `extract_text()` and injectable via `DoclingReader(converter=...)` for tests (`docling_reader.py:37-71`)

## Data Storage

**Databases:**
- SQLite via stdlib `sqlite3` (`doc_store.py:12,78-413`)
  - Connection: file path `data/documents.db`, passed to `DocStore(...)` in the `main.py:150` upload loop; parent dirs auto-created (`doc_store.py:90-91`); `data/` is gitignored (`.gitignore:10`)
  - Tables v1 (`SCHEMA_V1_DDL`, `doc_store.py:16-54`): `documents` (PK `doc_id`, UNIQUE `sha256`), `pages` (PK `doc_id,page_num`), `chunks` (PK `chunk_id`)
  - Tables v2 (`SCHEMA_V2_DDL`, `doc_store.py:56-70`): `evidence_elements` (PK `element_id`, FK `doc_id → documents` with `ON DELETE CASCADE`)
  - Mode: WAL + `busy_timeout=5000` + `foreign_keys=ON` (`doc_store.py:106-110`); schema versioned via `PRAGMA user_version` with `MIGRATIONS = {1: V1, 2: V2}` dict (`doc_store.py:72-75,116-129`)
  - Lifecycle: per-operation connection opened/closed inside `_connect()` context manager — Windows-lock and Streamlit-rerun safe (`doc_store.py:97-114`)
  - Writes: `upsert_document` / `record_page` / `record_chunks` (single-transaction `executemany`) / `record_evidence_elements` (`doc_store.py:131-371`); reads: `get_by_sha` (dedup), `get_chunks_for_doc` (CR-01 index restore after restart), `get_evidence_for_doc` (`doc_store.py:188-398`); `bbox` round-trips as `bbox_json` (`doc_store.py:283,319-324`)

**File Storage:**
- Local filesystem only
  - Deterministic JSON cache under `.cache/<sha256>/<CONFIG_VERSION>/{pages.json,chunks.json,manifest.json}` written best-effort in `main.py:278-289`; path computed by `cache_dir_for` with strict 64-hex validation (`models.py:17-30`); `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`); `.cache/` is gitignored (`.gitignore:17`)
  - SQLite file `data/documents.db` (see above)
  - Local GGUF weights in `models/` (external to pip; see local-inference section)
  - Synthetic test PDFs `tests/data/corpus/*.pdf` (6 files: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`) generated by `tests/data/corpus/generate_corpus.py` (reportlab)

**Ingestion backends (local libraries, no network):**
- Docling `>=2.0.0` (`docling_reader.py`): `DocumentConverter` + `DocumentStream(name, BytesIO)` (`docling_reader.py:111-115`); CPU-only pipeline `do_ocr=False, do_table_structure=True` (`docling_reader.py:104-106`); reading-order grouping by `item.prov[0].page_no`, markdown tables via `export_to_markdown()` preserved intact as single chunks when `startswith("|")` and ≤2000 chars, prose split 1000/200 (`docling_reader.py:118-267`); chunk `extraction="docling"` (`docling_reader.py:228-266`); any missing package / empty result / exception degrades to `PdfReader` fallback (`docling_reader.py:95-100,183-191,288-293`)
- RapidOCR / ONNX Runtime `>=1.3.0` (`ocr_fallback.py`): `RapidOCR()` CPU default (`ocr_fallback.py:63-69`); trigger `should_ocr_page(text, status, threshold=50)` — `empty`/`failed` status or <50 chars (`ocr_fallback.py:29-43`); page render via PyMuPDF at 150 DPI (`ocr_fallback.py:77-110`); `ocr_page_image` parses `[[box], text, score]` tuples → `(full_text, avg_conf)` (`ocr_fallback.py:112-159`); `apply_conditional_ocr` preserves clean pages untouched, isolates per-page faults to `status="failed"` without aborting the document, tags new chunks `extraction="ocr"` (`ocr_fallback.py:162-320`)
- PyMuPDF `>=1.24.0` (`import fitz`): OCR renderer `fitz.open(stream, filetype="pdf") → page.get_pixmap(Matrix(zoom,zoom)).tobytes("png")` (`ocr_fallback.py:96-108`); visual detection of raster images (`get_images` + `get_image_rects`, ≥30×30 pt, `kind="image"`) and vector diagrams (`get_drawings` cluster ≥2 drawings, ≥40×40 pt, 95%-area background exclusion, 10 pt padding, `kind="chart"`) (`visual_analyzer.py:64-136`); 2x-zoom PNG crops clipped to page rect (`crop_visual_element`, `visual_analyzer.py:138-183`); both modules guard `fitz is None` (OCR unavailable / regions `[]` / crop raises `RuntimeError`) (`ocr_fallback.py:23-26,72-75`, `visual_analyzer.py:17-20,59-61,164-165`)
- pypdf `==5.3.0`: baseline `PdfReader` extraction with per-page `try/except` → `ok`/`empty`/`failed` `Page` records and `extraction="pypdf"` chunks (`pdf_reader.py:29-114`); validation probe in `upload_validation.py:89-94`

**Caching:**
- In-process Streamlit cache: `@st.cache_resource(show_spinner=False)` memoizes one `AiModel` (and its active provider) per server process (`main.py:68-76`)
- Per-session in-memory vector store: `VectorIndex` (no persistence) held inside `LocalEmbedding`, itself stored in `st.session_state` (`main.py:57,254-256`); dedup-hit-after-restart restores it from `DocStore.get_chunks_for_doc` (`main.py:193-200`)
- No Redis / external cache

## Authentication & Identity

**Auth Provider:**
- None. No user accounts or sessions. The only credential is the optional `GROQ_API_KEY`, resolved with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); absence yields an `unreachable` `HealthStatus`, not an error.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/OpenTelemetry).

**Logs:**
- `logging` module (`getLogger(__name__)`) in the Phase 3 ingestion modules: `logger.info` for Docling fallback paths (`docling_reader.py:96,184,281`), `logger.warning` for conversion/crop failures (`docling_reader.py:289`, `ocr_fallback.py:68,128`, `visual_analyzer.py:60,228`), `logger.error` for page-level OCR faults and VLM failures (`ocr_fallback.py:307`, `visual_analyzer.py:133,238`)
- Module-prefixed `print()` for developer diagnostics in legacy modules: `[LocalEmbedding]` (`local_embedding.py:21,23,58`), `[DocStore]` migrations (`doc_store.py:129`), `[UploadValidation]` (`upload_validation.py:106`), pypdf success line (`pdf_reader.py:113`)
- User-facing feedback via Streamlit (`st.status`, `st.error`, `st.warning`, `st.info`, `st.success`, `st.progress`) — never `print` (`main.py:90-121,148-310,351-410`)
- Provider health surfaced through the `HealthStatus` schema rendered in the sidebar (`main.py:93-121`); VLM provenance kept separate as `EvidenceElement(source="vlm:<model_name>")` so visual approximations never contaminate ground-truth tables (`visual_analyzer.py:240-262`)

## CI/CD & Deployment

**Hosting:**
- Primary: local Windows workstation (RTX 3050, 4 GB VRAM ceiling) — zero-egress local inference (`docs/LOCAL_INFERENCE.md`, `llama_cpp_provider.py:1-6`)
- Fallback: Streamlit Community Cloud with `GROQ_API_KEY` in the Cloud secrets panel; ephemeral disk (SQLite + `.cache/` best-effort only)
- Devcontainer/Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` with Streamlit on port 8501 (`.devcontainer/devcontainer.json`)

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml` (sole workflow)
  - Triggers: push / pull_request on `main` (`.github/workflows/ci.yml:3-7`)
  - Job `test` on `ubuntu-latest`: checkout (`actions/checkout@v4`) → setup Python `"3.11"` with pip cache (`actions/setup-python@v5`) → `pip install -r requirements.txt` + `pip install -r requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v` (`.github/workflows/ci.yml:9-41`)
  - No deploy job, no artifact upload, no coverage gate
- Benchmark (manual): `python scripts/benchmark_baseline.py` measures pypdf extraction latency, 1000/200 chunking, CPU `SentenceTransformer("all-MiniLM-L6-v2")` load + batch encode latency, `VectorIndex` linear-scan latency over 100/500/1000 vectors, and RSS via `psutil`; writes `.planning/research/BASELINE_BENCHMARK.json` (`scripts/benchmark_baseline.py:1-174`)

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — optional; only needed for the cloud fallback path (`groq_provider.py:37-49`); no other env var is read in app code

**Secrets location:**
- Local: `.env` in project root (gitignored, `.gitignore:1`) loaded via `python-dotenv` inside `load_ai_model()` (`main.py:75`)
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]`, `groq_provider.py:40-44`)
- No `.streamlit/secrets.toml` is committed; never quote secret values in docs or code

**Local runtime state (gitignored, existence-only):**
- `.env` — API key (`main.py:75`)
- `data/documents.db` — SQLite store (`.gitignore:10`, `main.py:150`)
- `.cache/<sha256>/<CONFIG_VERSION>/` — extraction cache (`.gitignore:17`, `main.py:278-289`)
- `models/` — local GGUF weights (downloaded per `docs/LOCAL_INFERENCE.md:31-44`, served by external `llama-server`)
- `~/.cache/huggingface/` — sentence-transformers + Docling model downloads (outside repo)

## Test Mock Seams (offline — no GPU, no network, no API keys)

- `httpx.MockTransport(handler)` injected as `LlamaCppProvider(transport=...)` — covers `GET /health` (200/503/error/connect-fail) and `POST /v1/chat/completions` (JSON + SSE `data: [DONE]`) (`tests/test_llama_cpp_provider.py`, `llama_cpp_provider.py:26,34,39-43`)
- `MagicMock` Groq client (`mock_groq_client`, `tests/conftest.py:18-48`) yielding canned `delta.content` tokens `["This ", "is ", "a ", "grounded ", "answer."]`; `fake_env_groq_key` sets a dummy `GROQ_API_KEY` (`tests/conftest.py:11-16`)
- `MagicMock` SentenceTransformer (`mock_sentence_transformer`, `tests/conftest.py:51-81`) returning deterministic 384-dim L2-normalised `numpy.float32` vectors
- `MockLlamaCppProvider(BaseModelProvider)` healthy/unhealthy double recording `stream_calls` (`tests/conftest.py:91-161`)
- Constructor injection seams (no network/install required): `DoclingReader(converter=...)` (`docling_reader.py:37-71`), `OcrEngine(recognizer=..., renderer=...)` (`ocr_fallback.py:49-61`), `VisualAnalyzer(region_detector=..., cropper=...)` (`visual_analyzer.py:33-45`); `FakeFitz` module double via `monkeypatch.setattr("visual_analyzer.fitz", FakeFitz)` (`tests/test_visual_analyzer.py:286-332`)
- Corpus fixtures: `sample_pdf_path` → `tests/data/corpus/clean_digital.pdf` (`tests/conftest.py:84-88`); full 13-file suite `tests/test_*.py` (doc_store, docling_reader, llama_cpp_provider, local_embedding, local_llm, model_provider, models, ocr_fallback, pdf_reader, prompt_budget, upload_validation, vector_index, visual_analyzer)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (Groq fallback is a direct SDK call, not a webhook; llama-server is localhost REST, not external)

---

*Integration audit: 2026-10-11*
