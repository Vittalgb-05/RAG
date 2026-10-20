# Codebase Structure

**Analysis Date:** 2026-10-21

## Directory Layout

```text
RAG/
├── main.py                      # Streamlit composition root; page config, hydration, routing
├── start.py                     # One-command launcher (llama-server + Streamlit subprocess)
├── setup.py                     # Packaging + model/server/dependency installer CLI
├── models.py                    # Canonical Pydantic domain schemas + cache path helper
├── doc_store.py                 # SQLite metadata/pages/chunks/evidence/summaries store
├── hybrid_retriever.py          # LanceDB dense + FTS retrieval with RRF and fallbacks
├── vector_index.py              # Pure-Python vector index (LanceDB fallback)
├── local_embedding.py           # CPU MiniLM embeddings (384-d, L2-normalized)
├── local_llm.py                 # AiModel facade + process-wide InferenceGate
├── model_provider.py            # BaseModelProvider ABC + capabilities/health schemas
├── llama_cpp_provider.py        # Local llama-server HTTP/SSE provider
├── litellm_provider.py          # Cloud LiteLLM provider with consent gate
├── groq_provider.py             # Direct Groq cloud provider fallback
├── summarizer.py                # Multi-profile fast-path / map-reduce summarization
├── citation_validator.py        # [E#] precision, abstention, injection detection
├── prompt_budget.py             # Token budgeting, XML isolation, history truncation
├── upload_validation.py         # PDF magic-byte/size/page validation + SHA hashing
├── docling_reader.py            # Docling layout/table extraction with pypdf fallback
├── pdf_reader.py                # pypdf text extraction and page records
├── ocr_fallback.py              # Conditional RapidOCR for low-text pages
├── visual_analyzer.py           # PyMuPDF visual region detection + VLM descriptions
├── resource_telemetry.py        # VRAM/RAM telemetry and latency tracking
├── logging_setup.py             # Streamlit torch.classes watcher log filter
├── requirements.txt             # Direct runtime dependencies
├── requirements-lock.txt        # Universal lockfile (Python 3.11, uv-compiled)
├── requirements-test.txt        # Test-only dependencies
├── pyproject.toml               # Ruff + pytest configuration
├── Dockerfile                   # Python 3.11 slim application image
├── docker-compose.yml           # App + optional CUDA llama-server services
├── README.md                    # Project overview and quick start
├── CLAUDE.md                    # GSD project context and stack/architecture summaries
├── LICENSE                      # Project license
├── ui/                          # Streamlit presentation package
│   ├── __init__.py              # Re-exports sanitizer entry point
│   ├── views.py                 # Workspace renderers + sidebar upload/document manager
│   ├── components.py            # Brand header, SVG icons, stat cards, status pills, chips
│   ├── theme.py                 # AMOLED color tokens and injected CSS
│   ├── sanitizer.py             # Local-only markdown/HTML sanitization
│   ├── hydration.py             # Startup state restoration and vector repair
│   ├── ingestion_service.py     # End-to-end ingestion orchestration
│   └── lifecycle_service.py     # Delete / purge / re-index orchestration
├── tests/                       # pytest suite (29 test modules)
│   ├── conftest.py              # Offline fixtures and provider mocks
│   ├── __init__.py
│   ├── test_*.py                # One module per production module/feature
│   └── data/corpus/             # Synthetic PDF corpus + generator
├── data/                        # Runtime persistence (gitignored; created at launch)
│   ├── documents.db             # SQLite metadata store (WAL)
│   ├── lancedb/                 # LanceDB tables + fallback_store.json
│   └── lancedb_bench/           # Benchmark-only LanceDB directory
├── .cache/                      # Runtime extraction cache (gitignored)
├── models/                      # Local GGUF weights (gitignored; downloaded by setup)
├── tools/                       # llama-server binaries/DLLs (gitignored; installed by setup)
├── assets/                      # Committed brand mark and monochrome SVG icon set
│   ├── brand_mark.svg
│   └── icons/*.svg              # 22 inline UI icons
├── docs/                        # Operational and evaluation documentation
│   ├── RUNBOOK.md
│   ├── LOCAL_INFERENCE.md
│   ├── EVALUATION.md
│   └── LICENSES.md
├── scripts/                     # Benchmark, profiling, and asset-generation scripts
│   ├── benchmark_baseline.py
│   ├── benchmark_multimodal.py
│   ├── profile_resources.py
│   └── generate_icons.py
├── application_screenshots/     # Reference UI screenshots
├── .github/workflows/ci.yml     # Lint, corpus generation, pytest
├── .streamlit/config.toml       # Dark theme, upload cap, telemetry disabled
├── .devcontainer/devcontainer.json
├── .planning/                   # GSD project artifacts (committed)
└── rag_assistant.egg-info/      # Generated packaging metadata (gitignored)
```

## Directory Purposes

**Repository root (flat domain modules):**
- Purpose: all runtime Python modules live at the top level, grouped by domain noun.
- Contains: extraction, retrieval, inference providers, persistence, budgeting,
  validation, telemetry, and launcher/setup scripts.
- Key files: `main.py`, `local_llm.py`, `hybrid_retriever.py`, `doc_store.py`,
  `models.py`, `summarizer.py`.

**`ui/`:**
- Purpose: presentation and UI-specific orchestration.
- Contains: four workspace renderers, reusable HTML/SVG components, theme CSS,
  sanitizer, hydration, ingestion service, lifecycle service.
- Key files: `ui/views.py` (852 lines, largest module), `ui/ingestion_service.py`,
  `ui/lifecycle_service.py`, `ui/hydration.py`.

**`tests/`:**
- Purpose: fully offline unit/integration suite (no GPU, no network).
- Contains: 29 `test_*.py` modules, shared fixtures in `tests/conftest.py`, synthetic
  corpus under `tests/data/corpus/` generated by `generate_corpus.py`.
- Key files: `tests/conftest.py`, `tests/test_main_ui.py`, `tests/test_hybrid_retriever.py`,
  `tests/test_doc_store.py`.

**`data/`:**
- Purpose: runtime persistence; ignored by git and created on launch.
- Contains: `documents.db` (SQLite source of truth), `lancedb/` (persistent vector/FTS
  tables and `fallback_store.json`), `lancedb_bench/` (benchmark isolation).
- Key files: `data/documents.db`, `data/lancedb/`.

**`.cache/`:**
- Purpose: per-document intermediate extraction cache.
- Contains: `<sha256>/<CONFIG_VERSION>/pages.json`, `chunks.json`, `manifest.json`
  (`models.py:17-30`).
- Key files: populated by `ui/ingestion_service.py:311-322`; removed by
  `ui/lifecycle_service.py:56-62`.

**`models/` and `tools/`:**
- Purpose: native runtime assets; ignored by git.
- Contains: `models/qwen3-vl-2b-instruct-q4_k_m.gguf`,
  `models/mmproj-f16.gguf`, and `tools/llama-server/` binaries + CUDA DLLs.
- Key files: downloaded/installed by `setup.py:236-495`, used by `start.py:114-149`.

**`assets/`:**
- Purpose: committed static UI assets.
- Contains: brand mark and local monochrome SVG icons loaded by
  `ui/components.py:7-49`.
- Key files: `assets/brand_mark.svg`, `assets/icons/*.svg`.

**`docs/`:**
- Purpose: operator/developer documentation.
- Contains: installation/operations runbook, local llama.cpp inference guide,
  evaluation report, third-party license notices.

**`scripts/`:**
- Purpose: non-runtime tooling.
- Contains: baseline benchmark, multimodal quality benchmark, resource profiler,
  SVG icon generator. Outputs go to `.planning/research/*.json`.

**`.planning/`:**
- Purpose: GSD project management artifacts.
- Contains: `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, phase plans,
  debug notes, research, and this `codebase/` map.

**`.github/workflows/`:**
- Purpose: CI.
- Contains: `ci.yml` — Ruff check/format, corpus generation, `pytest tests/ -v`.

**`.streamlit/`:**
- Purpose: Streamlit configuration.
- Contains: `config.toml` — dark theme, primary color `#B9A3FF`, upload cap 50 MB,
  usage stats disabled, CORS/XSRF enabled.

**`.devcontainer/`:**
- Purpose: reproducible development container definition.

**`application_screenshots/`:**
- Purpose: committed reference screenshots of the UI and diagram.

**`rag_assistant.egg-info/`:**
- Purpose: generated setuptools metadata. Not source; safe to ignore.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit composition root; page config (`main.py:98-106`), session defaults
  (`main.py:112-132`), hydration (`main.py:139-145`), provider wiring
  (`main.py:148-192`), sidebar (`main.py:251-328`), routing (`main.py:335-363`).
- `start.py`: launcher; `main()` at `start.py:214-262`.
- `setup.py`: CLI/setup commands at `setup.py:586-660`.
- `scripts/*.py`: benchmark/profiling entry points.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `py311`) and pytest settings.
- `requirements.txt` / `requirements-lock.txt` / `requirements-test.txt`: dependencies.
- `.streamlit/config.toml`: UI theme and server limits.
- `Dockerfile`, `docker-compose.yml`: container build/runtime and llama-server service.
- `.github/workflows/ci.yml`: CI pipeline.
- `.gitignore`: excludes `.env`, `data/`, `.cache/`, `models/`, `tools/`, caches,
  and packaging artifacts.

**Presentation / UI:**
- `ui/views.py:36-42`: chat history bounding helper.
- `ui/views.py:50-177`: sidebar upload + active document list.
- `ui/views.py:185-466`: Chat workspace (retrieval, streaming, citations, verification).
- `ui/views.py:474-583`: Summarizer workspace.
- `ui/views.py:591-694`: Document Library (inspect, re-index, delete, purge).
- `ui/views.py:702-852`: Settings (cloud consent, telemetry, storage/session controls).
- `ui/components.py`: `get_svg_icon`, `render_brand_header`, `render_stat_card`,
  `render_status_pill`, `render_empty_state`, `render_citation_chip`.
- `ui/theme.py:5-15`: AMOLED color tokens; `inject_custom_theme` at `ui/theme.py:186`.
- `ui/sanitizer.py:33-78`: `sanitize_markdown_for_local`.

**Core Logic — ingestion:**
- `upload_validation.py:64-113`: validation and stable `doc_<sha16>` IDs.
- `docling_reader.py:95-320`: Docling extraction, chunking, page records.
- `pdf_reader.py:46-151`: pypdf extraction fallback.
- `ocr_fallback.py:35-49`: OCR trigger policy; `apply_conditional_ocr` at
  `ocr_fallback.py:318`.
- `visual_analyzer.py:49-309`: region detection, cropping, VLM evidence generation.
- `ui/ingestion_service.py:54-334`: orchestration pipeline and result object.

**Core Logic — retrieval:**
- `local_embedding.py:50-156`: MiniLM wrapper and legacy dense search.
- `hybrid_retriever.py:40-85`: RRF computation.
- `hybrid_retriever.py:256-408`: chunk/evidence indexing.
- `hybrid_retriever.py:580-693`: `search_hybrid` returning `RetrievalResult`.
- `vector_index.py:15-208`: pure-Python vector store fallback.

**Core Logic — inference/grounding:**
- `local_llm.py:26-90`: `InferenceGate`.
- `local_llm.py:93-359`: `AiModel` (provider detection, streaming, validation).
- `model_provider.py:15-156`: provider schemas and ABC.
- `llama_cpp_provider.py:24-315`: local HTTP/SSE provider.
- `litellm_provider.py:104-359`: cloud provider with consent scrubbing.
- `groq_provider.py:18-...`: direct Groq adapter.
- `prompt_budget.py:26-166`: XML sanitization, token budgeting, history bounding.
- `citation_validator.py:50-230`: citation precision/abstention/injection checks.
- `summarizer.py:153-422`: profiles, batching, map-reduce, caching.

**Core Logic — persistence/lifecycle:**
- `doc_store.py:17-110`: schema DDL v1–v4.
- `doc_store.py:132-164`: per-operation connections and migrations.
- `doc_store.py:166-652`: CRUD for documents/pages/chunks/evidence/summaries/purge.
- `ui/hydration.py:13-74`: startup restoration and vector repair.
- `ui/lifecycle_service.py:31-166`: delete/purge/re-index.

**Testing:**
- `tests/conftest.py`: offline fixtures, mock Groq client, fake embeddings, temp paths.
- `tests/data/corpus/generate_corpus.py`: reportlab corpus generator (run before tests
  in CI).
- `tests/test_*.py`: one module per production module; UI tests in
  `tests/test_main_ui.py` and `tests/test_ui_smoke.py`.

**Assets/Docs:**
- `assets/brand_mark.svg`, `assets/icons/`.
- `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`,
  `docs/LICENSES.md`.

## Naming Conventions

**Files:**
- Root modules: `snake_case.py`, named by domain noun (`doc_store.py`,
  `hybrid_retriever.py`, `local_llm.py`, `visual_analyzer.py`).
- Providers: `<backend>_provider.py` (`llama_cpp_provider.py`, `litellm_provider.py`,
  `groq_provider.py`).
- Readers/extractors: `<format>_reader.py` (`docling_reader.py`, `pdf_reader.py`).
- UI services: `<domain>_service.py` under `ui/`.
- Tests: `tests/test_<module_or_feature>.py`.
- Scripts: `<verb>_<object>.py` (`benchmark_baseline.py`, `profile_resources.py`).

**Functions:**
- `snake_case`, verb-first (`ingest_pdf`, `delete_document`, `purge_all`,
  `reindex_document`, `hydrate_startup_state`, `assemble_grounded_messages`).
- UI renderers: `render_<area>` returning `None` (`render_chat_view`,
  `render_summarizer_view`, `render_library_view`, `render_settings_view`,
  `render_sidebar_documents`, `render_stat_card`).
- Data access: `get_*`, `list_*`, `record_*`, `upsert_*`, `delete_*`, `count_*`.
- Private helpers: leading underscore (`_connect`, `_apply_migrations`, `_embed_one`,
  `_detect_provider`, `_export_table_markdown`).

**Classes:**
- `PascalCase` nouns: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`,
  `Summarizer`, `VisualAnalyzer`, `OcrEngine`, `IngestionService`, `LifecycleService`.
- Provider classes end in `Provider`: `LlamaCppProvider`, `LiteLLMProvider`,
  `GroqProvider`.
- Pydantic schemas are singular nouns (`Document`, `Page`, `Chunk`, `EvidenceElement`,
  `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`).

**Variables/constants:**
- `snake_case`; module constants in `UPPER_SNAKE_CASE`
  (`CONFIG_VERSION`, `MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_DB_URI`, `DEFAULT_RRF_K`,
  `FAST_PATH_TOKEN_LIMIT`, `MAX_BATCH_TOKENS`).

**Identifiers:**
- Documents: `doc_<sha256[:16]>` (`upload_validation.py:36-48`).
- Summaries: `summ_<uuid4 hex[:16]>` (`summarizer.py:406`).
- Session cache keys: `summary_<doc_id>_<profile>` (`ui/views.py:529`).
- SQLite tables: snake_case plural (`documents`, `pages`, `chunks`,
  `evidence_elements`, `document_summaries`).

**Directories:**
- Lowercase single words (`ui`, `tests`, `data`, `models`, `tools`, `assets`, `docs`,
  `scripts`); generated/runtime dirs are dot-prefixed (`.cache`, `.streamlit`,
  `.planning`, `.github`).

## Where to Add New Code

**New workspace/feature view:**
- Renderer: add `render_<feature>_view` to `ui/views.py` following the existing
  `(doc_store, ai_model, ...)` dependency-injection signature.
- Routing: add the label to `WORKSPACES` and the dispatch chain in
  `main.py:291-363`.
- Reusable atoms: add to `ui/components.py`; colors/tokens to `ui/theme.py`.
- Session state defaults: add to the initialization list in `main.py:112-132`.

**New inference provider:**
- Implementation: create `<backend>_provider.py` at the repo root subclassing
  `BaseModelProvider` (`model_provider.py:64-156`); implement `generate_text`,
  `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Selection: update `AiModel._detect_provider` (`local_llm.py:168-185`) and/or the cloud
  wiring in `main.py:161-188`. Keep all generation behind `InferenceGate`.
- Tests: add `tests/test_<backend>_provider.py` using the mock patterns in
  `tests/conftest.py`.

**New extraction backend or file format:**
- Implementation: add `<format>_reader.py` exposing `extract_text`,
  `get_paragraphs`, and `get_page_records` returning `Chunk`/`Page`-compatible data
  (mirror `docling_reader.py` / `pdf_reader.py`).
- Wiring: call it in the extraction stage of `ui/ingestion_service.py:139-171`.
- Persistence: use `doc_store.record_pages_batch` / `record_chunks`
  (`doc_store.py:255-373`).

**New retrieval signal or ranking change:**
- Add candidate pool logic in `hybrid_retriever.py` next to `search_dense` /
  `search_fts`, and extend `compute_rrf` (`hybrid_retriever.py:40-85`) or add a new
  fusion function.
- Keep the public return type `RetrievalResult` (`models.py:171-205`); do not add new
  ad-hoc dict shapes at the UI boundary.

**New persisted field or table:**
- Add DDL as a new `SCHEMA_V<n>_DDL` and `MIGRATIONS` entry in `doc_store.py:17-110`;
  update the canonical model in `models.py`; update `upsert_*`/`get_*` methods.
- Never mutate an existing migration; migrations are applied by `PRAGMA user_version`.

**New UI orchestration workflow:**
- Create `ui/<workflow>_service.py` with explicit constructor injection
  (`doc_store`, `hybrid_retriever`, `local_embedding`, `cache_dir`) and a result object
  or `bool` return, following `ui/ingestion_service.py` and `ui/lifecycle_service.py`.
- Call it from `ui/views.py`; do not write SQL or LanceDB calls in renderers.

**New utility/helper:**
- If it is domain logic used by multiple layers, place it at the repo root and import
  only `models`/stdlib (e.g., `prompt_budget.py`, `citation_validator.py`).
- If it is UI-only, place it in `ui/components.py` or a new `ui/<name>.py`.

**New tests:**
- Add `tests/test_<module>.py`; use `tmp_path` for SQLite/LanceDB/cache isolation and
  the fixtures/mocks in `tests/conftest.py`. Keep tests offline (no GPU, no network).
- Add corpus fixtures under `tests/data/corpus/` and regenerate via
  `python tests/data/corpus/generate_corpus.py`.

**New benchmark/tooling:**
- Add `scripts/<purpose>.py`; write JSON output under `.planning/research/` as the
  existing benchmark scripts do.

**New static UI asset:**
- Add `assets/icons/<name>.svg` (18×18, `stroke="currentColor"`) or regenerate with
  `python scripts/generate_icons.py`; load via `get_svg_icon("<name>")`.

## Import & Dependency Rules

- `models.py` is the leaf: it imports only stdlib + Pydantic. Do not import domain
  modules from it.
- `prompt_budget.py` and `citation_validator.py` depend only on stdlib and `models`.
- Domain modules (`doc_store`, `hybrid_retriever`, providers, extraction) must not
  import `ui/` or `main.py`.
- `ui/views.py` is the UI composition layer: it may import domain/services, but domain
  modules must not import it.
- `ui/__init__.py` re-exports only `sanitize_markdown_for_local`; avoid turning it into
  a broad barrel that creates import cycles.
- `summarizer.py` imports `InferenceGate` from `local_llm.py`
  (`summarizer.py:16`); therefore `local_llm.py` must not import `summarizer.py`.
- Provider adapters import `model_provider` and their SDK only; they must not import
  retrieval or UI modules.
- `start.py` and `setup.py` are standalone scripts and must not be imported by the app.

## Special Directories

**`data/`:**
- Purpose: runtime persistence (SQLite + LanceDB).
- Generated: Yes (created by `start.py` / `setup.py`; DB schema by `DocStore`).
- Committed: No (`.gitignore` excludes `data/`).

**`.cache/`:**
- Purpose: per-document extraction artifacts.
- Generated: Yes.
- Committed: No.

**`models/`:**
- Purpose: GGUF model weights and mmproj adapter.
- Generated: Downloaded by `setup.py` (`MODEL_REGISTRY`, `setup.py:59-78`).
- Committed: No (`models/`, `*.gguf` ignored).

**`tools/`:**
- Purpose: llama-server executable and runtime DLLs.
- Generated: Installed by `setup.py`.
- Committed: No.

**`tests/data/corpus/`:**
- Purpose: deterministic synthetic PDF fixtures for extraction/OCR/retrieval tests.
- Generated: Partially — `generate_corpus.py` regenerates the PDFs, but the PDFs are
  also committed.
- Committed: Yes.

**`.planning/`:**
- Purpose: GSD planning, phase, research, debug, and codebase-map artifacts.
- Generated: By GSD commands.
- Committed: Yes.

**`rag_assistant.egg-info/`:**
- Purpose: setuptools build metadata.
- Generated: Yes.
- Committed: No.

**`application_screenshots/`:**
- Purpose: reference UI screenshots.
- Generated: No (manually captured).
- Committed: Yes.

---

*Structure analysis: 2026-10-21*
