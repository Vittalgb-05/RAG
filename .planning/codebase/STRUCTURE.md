# Codebase Structure

**Analysis Date:** 2026-10-21

## Directory Layout

```text
RAG/
├── main.py                     # Streamlit composition root: config, session, routing
├── start.py                    # One-command launcher (llama-server + Streamlit)
├── setup.py                    # Packaging + model/binary setup CLI
├── pyproject.toml              # Ruff (py311, line-length 120) + pytest config
├── requirements.txt            # Direct runtime dependencies
├── requirements-lock.txt       # uv-compiled universal lockfile (Python 3.11)
├── requirements-test.txt       # pytest/reportlab test dependencies
├── Dockerfile                  # python:3.11-slim-bookworm image, port 8501
├── docker-compose.yml          # app service + optional CUDA llama-server profile
├── .streamlit/config.toml      # AMOLED theme, upload cap, CORS/XSRF
├── .github/workflows/ci.yml    # Ruff + corpus generation + pytest on Python 3.11
├── .devcontainer/              # Dev container definition
│
├── core/                       # Domain models, persistence, LLM facade, summarizer
│   ├── __init__.py
│   ├── models.py               # Pydantic schemas + cache_dir_for()
│   ├── doc_store.py            # SQLite WAL store, migrations v1–v4
│   ├── local_llm.py            # AiModel facade + InferenceGate
│   ├── summarizer.py           # 5-profile single-pass / map-reduce summarizer
│   ├── citation_validator.py   # [E#] precision, abstention, injection checks
│   ├── prompt_budget.py        # Token budgeting, XML isolation, history bounding
│   ├── resource_telemetry.py   # GPU/RSS telemetry + latency tracking
│   └── logging_setup.py        # Streamlit torch.classes watcher filter
│
├── ingestion/                  # PDF → chunks/pages/evidence pipeline
│   ├── upload_validation.py    # Magic bytes, size/page caps, SHA-256, doc_id
│   ├── docling_reader.py       # Structured layout + markdown tables (primary)
│   ├── pdf_reader.py           # pypdf per-page extraction (fallback)
│   ├── ocr_fallback.py         # Conditional RapidOCR + PyMuPDF raster
│   └── visual_analyzer.py      # Figure/diagram detection, crops, VLM analysis
│
├── retrieval/                  # Embeddings and hybrid search
│   ├── local_embedding.py      # CPU-pinned all-MiniLM-L6-v2 (384-dim)
│   ├── hybrid_retriever.py     # LanceDB dense + FTS + RRF, BM25 fallback
│   ├── vector_index.py         # Pure-Python cosine/euclidean index
│   └── data/lancedb/           # DEFAULT_DB_URI resolved by HybridRetriever
│
├── providers/                  # Inference backends behind BaseModelProvider
│   ├── model_provider.py       # ABC + ProviderCapabilities + HealthStatus
│   ├── llama_cpp_provider.py   # llama-server HTTP/SSE, loopback enforcement
│   ├── litellm_provider.py     # Consent-gated cloud adapter
│   └── groq_provider.py        # Direct Groq client
│
├── ui/                         # Streamlit presentation + workflow orchestration
│   ├── views.py                # 4 workspaces + sidebar document manager
│   ├── components.py           # SVG icons, cards, status pills, citation chips
│   ├── theme.py                # AMOLED CSS tokens and injected styles
│   ├── sanitizer.py            # Markdown/HTML egress neutralization
│   ├── ingestion_service.py    # IngestionService (end-to-end ingest)
│   ├── lifecycle_service.py    # LifecycleService (delete/purge/reindex)
│   └── hydration.py            # Startup catalog + vector repair
│
├── tests/                      # pytest suite (29 files) + synthetic PDF corpus
│   ├── conftest.py             # Offline mocks for Groq, SentenceTransformer, etc.
│   └── data/corpus/            # Generated PDFs: digital, scanned, tables, diagrams
│
├── scripts/                    # Manual benchmarks, profiling, icon generation
│   ├── benchmark_baseline.py
│   ├── benchmark_multimodal.py
│   ├── profile_resources.py
│   └── generate_icons.py
│
├── data/                       # Runtime persistence (gitignored except layout)
│   ├── documents.db            # SQLite source of truth
│   ├── lancedb/                # Existing on-disk index (not DEFAULT_DB_URI)
│   └── lancedb_bench/          # Benchmark index (explicit db_uri)
│
├── .cache/                     # Per-document extraction cache: <sha256>/<CONFIG_VERSION>/
├── models/                     # GGUF weights (Qwen3-VL 2B Q4_K_M + mmproj)
├── tools/llama-server/         # Native llama-server binary (installed by setup.py)
├── assets/                     # brand_mark.svg + 22 monochrome icons
├── docs/                       # RUNBOOK, LOCAL_INFERENCE, EVALUATION, LICENSES
├── application_screenshots/    # Reference UI captures
└── .planning/                  # GSD planning artifacts (not application code)
```

## Directory Purposes

**`core/`:**
- Purpose: Framework-independent domain logic and persistence.
- Contains: Pydantic models, SQLite store, inference facade/gate, summarizer, citation validator, prompt budgeter, telemetry, logging filter.
- Key files: `core/models.py`, `core/doc_store.py`, `core/local_llm.py`, `core/summarizer.py`.
- Rule: Must not import from `ui/`. May import `providers/` and `retrieval/`.

**`ingestion/`:**
- Purpose: Convert untrusted PDF bytes into canonical text/visual evidence.
- Contains: Validation, Docling and pypdf extractors, OCR engine, visual region detection/cropping.
- Key files: `ingestion/upload_validation.py:64` (`validate_pdf_bytes`), `ingestion/docling_reader.py:95` (`extract_text`), `ingestion/ocr_fallback.py:318` (`apply_conditional_ocr`), `ingestion/visual_analyzer.py:202` (`analyze_visual_elements`).
- Rule: Must not import from `ui/`. `visual_analyzer` lazily imports `InferenceGate` (`ingestion/visual_analyzer.py:275`) to avoid an import cycle.

**`retrieval/`:**
- Purpose: Embedding and search.
- Contains: `LocalEmbedding`, `HybridRetriever`, `compute_rrf`, `VectorIndex`.
- Key files: `retrieval/hybrid_retriever.py:110`, `:623` (`search_hybrid`), `retrieval/local_embedding.py:50`.
- Rule: Must not import from `ui/` or `core/local_llm.py`.

**`providers/`:**
- Purpose: Normalize local and cloud model access behind one contract.
- Contains: ABC + schemas, llama-server client, LiteLLM adapter, Groq client.
- Key files: `providers/model_provider.py:64`, `providers/llama_cpp_provider.py:24`, `providers/litellm_provider.py:104`.
- Rule: Every provider implements all five abstract methods; `analyze_image` may raise `NotImplementedError` (see `providers/groq_provider.py:163`).

**`ui/`:**
- Purpose: Streamlit rendering plus workflow services that coordinate domain/storage.
- Contains: View renderers, reusable components, CSS theme, sanitizer, ingestion/lifecycle/hydration services.
- Key files: `ui/views.py`, `ui/ingestion_service.py:39`, `ui/lifecycle_service.py:16`, `ui/hydration.py:13`.
- Rule: Renderers return `None` and are named `render_<area>`; views must not execute SQL or direct LanceDB deletes.

**`tests/`:**
- Purpose: Fully offline unit/integration tests with mocked models.
- Contains: One `test_<module>.py` per module/feature plus `conftest.py` fixtures and `data/corpus/`.
- Key files: `tests/conftest.py` (mock providers/embeddings), `tests/data/corpus/generate_corpus.py` (reportlab PDF fixtures).
- Rule: No network, no GPU, no real API keys.

**`scripts/`:**
- Purpose: Operator tools run manually.
- Contains: Baseline/multimodal benchmarks, resource profiling, SVG icon generation.
- Key files: `scripts/profile_resources.py`, `scripts/benchmark_baseline.py`.
- Rule: May import app packages; the app must never import `scripts/`.

**`data/`:**
- Purpose: Durable runtime state.
- Contains: `documents.db` (SQLite), `lancedb/` (an existing chunks table + FTS indices), `lancedb_bench/`.
- Key files: `data/documents.db`, `data/lancedb/chunks.lance/`.
- Note: `HybridRetriever()` with no argument resolves `DEFAULT_DB_URI` to `retrieval/data/lancedb/` (`retrieval/hybrid_retriever.py:58`), not `data/lancedb/`.
- Rule: Created automatically by `start.py:57` and `DocStore.__init__` (`core/doc_store.py:126`).

**`.cache/`:**
- Purpose: Content-addressed intermediate extraction artifacts.
- Contains: `<sha256>/docling-1000-200-v1/{pages.json,chunks.json,manifest.json}`.
- Key files: `core/models.py:17` (`cache_dir_for`), written at `ui/ingestion_service.py:311`–`:320`.
- Rule: `CONFIG_VERSION` (`core/models.py:14`) is part of the path, so extraction-policy changes naturally invalidate old caches.

**`models/`:**
- Purpose: Local GGUF weights (not committed).
- Contains: `qwen3-vl-2b-instruct-q4_k_m.gguf`, `mmproj-f16.gguf`.
- Key files: registry in `setup.py:59`; consumed by `start.py:127`–`:128`.

**`tools/llama-server/`:**
- Purpose: Per-repo native inference binary installed by setup.
- Contains: `llama-server.exe` on Windows, `llama-server` on Linux.
- Key files: resolution in `start.py:69`, `setup.py:302`.

**`assets/`:**
- Purpose: Local-only visual assets (no CDN/network requests).
- Contains: `assets/brand_mark.svg`, `assets/icons/*.svg` (22 icons).
- Key files: loaded and cached by `ui/components.py:14`.

**`docs/`:**
- Purpose: Operator documentation.
- Contains: `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`, `LICENSES.md`.

**`.planning/`:**
- Purpose: GSD planning/state artifacts (PROJECT, ROADMAP, phases, debug, codebase maps).
- Rule: Excluded from Ruff (`pyproject.toml`) and Docker context via `.dockerignore`.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit UI entry; `st.set_page_config` at `main.py:98`, routing at `main.py:335`.
- `start.py`: Launcher entry; `main()` at `start.py:214`.
- `setup.py`: Setup CLI; console entry points at `setup.py:638`+.
- `scripts/profile_resources.py`: Resource/concurrency verification harness.

**Configuration:**
- `pyproject.toml`: Ruff and pytest settings (`testpaths = ["tests"]`, warnings ignored).
- `requirements.txt` / `requirements-lock.txt` / `requirements-test.txt`: dependency sources.
- `.streamlit/config.toml`: theme colors, `maxUploadSize = 50`, `gatherUsageStats = false`.
- `Dockerfile`, `docker-compose.yml`: container and CUDA llama-server profile.
- Environment variables (names only): `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `USE_TF`, `USE_TORCH`.
- `.env` may exist locally; contents are not documented.

**Core Logic:**
- `core/local_llm.py`: `InferenceGate` (`:26`), `AiModel` (`:93`), grounded streaming (`:217`).
- `core/summarizer.py`: profile prompts (`:31`), map-reduce (`:233`), public API (`:301`).
- `core/doc_store.py`: DDL/migrations (`:17`–`:110`), CRUD surface (`:166`–`:651`).
- `core/models.py`: all canonical schemas and `cache_dir_for`.
- `retrieval/hybrid_retriever.py`: RRF (`:62`), indexing (`:278`), hybrid search (`:623`).
- `ui/ingestion_service.py`: `ingest_pdf` nine-stage pipeline (`:54`–`:334`).

**Presentation:**
- `ui/views.py`: sidebar (`:50`), chat (`:185`), summarizer (`:503`), library (`:620`), settings (`:731`).
- `ui/theme.py`: design tokens (`:6`–`:15`), `inject_custom_theme` (`:186`).
- `ui/components.py`: `get_svg_icon` (`:14`), `render_status_pill` (`:86`), `render_citation_chip` (`:113`).
- `ui/sanitizer.py`: `sanitize_markdown_for_local` (`:33`).

**Testing:**
- `tests/conftest.py`: shared offline fixtures.
- `tests/data/corpus/`: `clean_digital.pdf`, `scanned_sample.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`.
- `tests/test_ui_smoke.py`, `tests/test_main_ui.py`: UI contract/smoke coverage without importing all of `main.py`.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (`hybrid_retriever.py`, `upload_validation.py`, `prompt_budget.py`).
- Tests: `tests/test_<module_or_feature>.py` (`test_doc_store.py`, `test_cloud_privacy.py`).
- Docs: uppercase Markdown at repo root or `docs/` (`README.md`, `docs/RUNBOOK.md`).
- Assets: lowercase snake/kebab SVG names matching the icon key (`assets/icons/chevron-right.svg`).

**Directories:**
- Package names are short, lowercase, responsibility-based: `core`, `ingestion`, `retrieval`, `providers`, `ui`, `tests`, `scripts`.
- Persistence directories are lowercase (`data`, `.cache`, `models`, `tools`).

**Classes:**
- `PascalCase` nouns: `DocStore`, `HybridRetriever`, `LocalEmbedding`, `AiModel`, `Summarizer`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`, `OcrEngine`, `LlamaCppProvider`, `LiteLLMProvider`.
- Pydantic schemas are singular nouns: `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`.

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `validate_pdf_bytes`, `search_hybrid`, `assemble_grounded_messages`, `hydrate_startup_state`.
- Renderers: `render_<area>` returning `None` (`render_chat_view`, `render_sidebar_documents`).
- Predicates/tests: `should_ocr_page`, `is_abstention`, `has_document`, `is_persistent`, `is_locked`.
- Private helpers: leading underscore (`_connect`, `_bundle_pages`, `_scrub_credentials`, `_bm25_search_fallback`).

**Variables/Constants:**
- Locals `snake_case`; module constants `UPPER_SNAKE_CASE` (`MAX_FILE_MB`, `MAX_PAGES`, `CONFIG_VERSION`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`, `PROFILE_SYSTEM_INSTRUCTIONS`).
- Identifier prefixes are contracts: `doc_<sha16>` (documents), `summ_<hex16>` (summaries), `elem_<doc_id>_p<page>_<kind>_<idx>` (evidence), `<sha12>_p<page>_<idx:04d>` (chunks).

**Tests:**
- Functions `test_<behavior>_<condition>` (e.g., `test_ingestion_rejects_non_pdf_bytes`), grouped by module under test.

## Where to Add New Code

**New ingestion extractor (e.g., another PDF engine):**
- Implementation: new module in `ingestion/` exposing `extract_text(doc_id, sha12)`, `get_paragraphs()`, `get_page_records()` and returning `Chunk`/`Page` objects.
- Wiring: add as a branch inside `IngestionService.ingest_pdf` step 3 (`ui/ingestion_service.py:145`–`:171`), keeping Docling → pypdf fallback order explicit.
- Tests: `tests/test_<engine>_reader.py` using bytes fixtures from `tests/data/corpus/`.

**New inference provider:**
- Implementation: `providers/<name>_provider.py` subclassing `BaseModelProvider` (`providers/model_provider.py:64`) and returning `ProviderCapabilities`/`HealthStatus`.
- Wiring: register selection in `AiModel._detect_provider` (`core/local_llm.py:168`) and the cloud provider map in `ui/views.py:790`.
- Tests: `tests/test_<name>_provider.py` with `httpx.MockTransport` or client mocks; add a consent test if it egresses.

**New retrieval modality or ranking stage:**
- Implementation: add a search method to `HybridRetriever` (`retrieval/hybrid_retriever.py`) and a fusion helper beside `compute_rrf` (`:62`).
- Wiring: extend `search_hybrid` (`:623`) and add a `search_mode` literal in `core/models.py:181`.
- Tests: `tests/test_hybrid_retriever.py`; assert deterministic ranks and fallback behavior.

**New UI workspace:**
- Renderer: `render_<name>_view(...)` in `ui/views.py`, returning `None`.
- Wiring: add to `WORKSPACES` (`main.py:291`) and the routing chain (`main.py:335`–`:362`).
- Components: reuse `ui/components.py` helpers; load icons via `get_svg_icon` and add the SVG to `assets/icons/`.

**New reusable UI card/badge:**
- Implementation: `ui/components.py`; style tokens/markup in `ui/theme.py`.
- Rule: HTML-escape any document-derived text (`html.escape`) and route markdown through `ui/sanitizer.py`.

**New SQLite table or column:**
- Schema: append a new `SCHEMA_V<n>_DDL` list and register it in `MIGRATIONS` (`core/doc_store.py:105`); never edit an existing version in place.
- Accessors: add typed CRUD methods that validate with Pydantic on read.
- Tests: `tests/test_doc_store.py` including migration-from-old-version coverage.

**New domain data model:**
- Implementation: `core/models.py` with `ConfigDict(extra="forbid")` (add `frozen=True` for value objects) and `model_validator` ID/format checks.
- Export: import from `core.models` everywhere; do not create parallel dict schemas.

**New summary profile:**
- Add the system instruction to `PROFILE_SYSTEM_INSTRUCTIONS` (`core/summarizer.py:31`), the label in `ui/views.py:532`, and the name to `VALID_SUMMARY_PROFILES` / `SummaryProfile` (`core/models.py:208`–`:209`).

**New orchestration workflow spanning stores:**
- Implementation: new service class in `ui/` (e.g., `ui/<workflow>_service.py`) taking `doc_store`, `hybrid_retriever`, `local_embedding`, `cache_dir` in `__init__`, mirroring `IngestionService`/`LifecycleService`.
- Rule: keep Streamlit calls out of the service (pass `session_state` as an argument, as `LifecycleService` does).

**Utilities:**
- Shared helpers that are domain-agnostic belong in the consuming package; token/context helpers belong in `core/prompt_budget.py`; cache-path helpers belong in `core/models.py`.

## Special Directories

**`retrieval/data/lancedb/` (implicit default):**
- Purpose: Persistent vector + FTS projection used when `HybridRetriever()` is constructed without `db_uri` (`retrieval/hybrid_retriever.py:58`, `:127`).
- Generated: Yes (created on first `HybridRetriever` init, `retrieval/hybrid_retriever.py:145`).
- Committed: No.

**`data/lancedb/`:**
- Purpose: Existing on-disk index present in this checkout; only used when a caller explicitly passes this `db_uri`.
- Generated: Yes (runtime artifact).
- Committed: No.

**`data/lancedb_bench/`:**
- Purpose: Benchmark index written by `scripts/benchmark_multimodal.py:162`.
- Generated: Yes.
- Committed: No.

**`.cache/`:**
- Purpose: Extraction artifact cache keyed by content hash and extraction-policy version.
- Generated: Yes (`ui/ingestion_service.py:311`).
- Committed: No.

**`models/`:**
- Purpose: Local GGUF weights.
- Generated: Yes (`setup.py download_models`).
- Committed: No (large binaries).

**`tools/llama-server/`:**
- Purpose: Native llama.cpp server binary.
- Generated: Yes (`python setup.py setup_llama_server`).
- Committed: No.

**`tests/data/corpus/`:**
- Purpose: Deterministic synthetic PDFs for ingestion/OCR/visual tests.
- Generated: Yes (`tests/data/corpus/generate_corpus.py`, also run in CI before pytest).
- Committed: Yes (PDFs are checked in).

**`application_screenshots/`:**
- Purpose: Reference UI imagery for documentation.
- Generated: No.
- Committed: Yes.

**`.planning/`:**
- Purpose: GSD workflow state, phase plans, debug notes, and this codebase map.
- Generated: Partially (by GSD commands).
- Committed: Yes.

---

*Structure analysis: 2026-10-21*
