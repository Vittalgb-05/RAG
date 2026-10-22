<!-- refreshed: 2026-10-21 -->
# Codebase Structure

**Analysis Date:** 2026-10-21

## Directory Layout

```text
RAG/
├── main.py                     # Streamlit composition root: session, hydration, routing
├── start.py                    # One-command launcher (llama-server probe/launch + Streamlit)
├── setup.py                    # Packaging + setup CLI/model downloader (setuptools)
├── core/                       # Domain: models, SQLite store, LLM facade/gate, summarizer, prompts, telemetry
├── ingestion/                  # PDF validation, Docling/pypdf extraction, OCR fallback, visual analysis
├── retrieval/                  # LanceDB hybrid retriever, MiniLM embeddings, in-memory vector fallback
├── providers/                  # BaseModelProvider ABC + llama.cpp / LiteLLM / Groq adapters
├── ui/                         # Streamlit views, components, theme, sanitizer, orchestration services
├── tests/                      # pytest suite + synthetic PDF corpus + shared fixtures
├── scripts/                    # Benchmark, multimodal evaluation, resource profiling, icon generation
├── docs/                       # Runbook, evaluation, local inference, audit/quality reports
├── assets/                     # Brand mark + monochrome SVG icon set
├── .streamlit/config.toml      # Dark AMOLED theme, 50 MB upload cap, telemetry off
├── .github/workflows/ci.yml    # Ruff + corpus generation + pytest on Python 3.11
├── data/                       # RUNTIME: documents.db + lancedb/ (generated, not committed)
├── .cache/                     # RUNTIME: <sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json
├── models/                     # RUNTIME: GGUF weights + mmproj (downloaded)
├── tools/llama-server/         # RUNTIME: local llama-server binary (downloaded)
├── requirements.txt            # Runtime dependencies
├── requirements-lock.txt       # uv-compiled universal lockfile (Python 3.11)
├── requirements-test.txt       # Test-only dependencies
├── pyproject.toml              # Ruff + pytest configuration
├── Dockerfile / docker-compose.yml
├── README.md / CLAUDE.md / LICENSE
└── .planning/                  # GSD planning + codebase docs (not application code)
```

## Directory Purposes

**`core/`:**
- Purpose: Framework-independent domain logic and persistence.
- Contains: Pydantic schemas, SQLite repository, inference facade + `InferenceGate`, summarizer, citation validator + lexical auto-attribution (`auto_attribute_citations`), prompt budgeting, hardware telemetry, GGUF identity verification, logging filter.
- Key files: `core/models.py`, `core/doc_store.py`, `core/local_llm.py`, `core/summarizer.py`, `core/citation_validator.py`, `core/prompt_budget.py`, `core/resource_telemetry.py`.

**`ingestion/`:**
- Purpose: Convert untrusted PDF bytes into canonical chunks, pages, and visual evidence.
- Contains: upload validation, Docling reader with pypdf fallback, conditional RapidOCR engine, PyMuPDF visual region detector/cropper.
- Key files: `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`.

**`retrieval/`:**
- Purpose: Embeddings and hybrid search over persisted chunks.
- Contains: `HybridRetriever` (LanceDB dense + FTS + RRF, JSON fallback mirror), `LocalEmbedding` (MiniLM CPU), `VectorIndex` (stdlib cosine/euclidean).
- Key files: `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `retrieval/vector_index.py`.
- Note: `retrieval/data/lancedb/` is a legacy index location; the canonical path is `data/lancedb/` (`retrieval/hybrid_retriever.py:66-70`, migration at lines 83–117).

**`providers/`:**
- Purpose: Normalize all inference backends behind one interface.
- Contains: `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus`; llama-server HTTP/SSE client; LiteLLM cloud adapter; direct Groq adapter.
- Key files: `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`.

**`ui/`:**
- Purpose: Streamlit presentation plus workflow orchestration.
- Contains: consolidated primary view renderers (`Chat` and `Document Library`), single-button file inserter (`render_file_upload_button`), reusable AMOLED components/theme, markdown sanitizer, `IngestionService`, `LifecycleService`, hydration, session reset.
- Key files: `ui/views.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `ui/session_state.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`.

**`tests/`:**
- Purpose: Fully offline unit/integration coverage with mocked models and a generated PDF corpus.
- Contains: 32 `test_*.py` suites (392 tests), `conftest.py` fixtures, `tests/data/corpus/` synthetic PDFs and generator.
- Key files: `tests/conftest.py` (mock provider, mock MiniLM, fake Groq, corpus path), `tests/data/corpus/generate_corpus.py`.

**`scripts/`:**
- Purpose: Manual evaluation and profiling harnesses, not imported by the app.
- Contains: `benchmark_baseline.py`, `benchmark_multimodal.py`, `profile_resources.py`, `generate_icons.py`.

**`docs/`:**
- Purpose: Operational and evaluation documentation.
- Contains: `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`, `ENDPOINT_INTEGRATION_MATRIX.md`, `FILE_CALLER_TEST_MAP.md`, `REQUIREMENTS_TRACEABILITY.md`, audit/repair/quality reports.

**`assets/`:**
- Purpose: Offline visual identity (no CDN/network).
- Contains: `assets/brand_mark.svg`, `assets/icons/*.svg` (chat, document, gpu, ram, database, lock, cloud, etc.).

**`data/` / `.cache/` / `models/` / `tools/`:**
- Purpose: Runtime state, derived artifacts, model weights, and llama-server binary.
- Contains: `data/documents.db`, `data/lancedb/`, `.cache/<sha256>/<CONFIG_VERSION>/`, `models/*.gguf`, `tools/llama-server/llama-server[.exe]`.
- Generated: Yes. Do not commit these.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit composition root — page config, session defaults, `DocStore`, hydration, `AiModel`, cloud consent, health cache, sidebar, workspace dispatch.
- `start.py`: Launcher — Python check, directory creation, llama-server health/launch, Streamlit subprocess.
- `setup.py`: Packaging + CLI (`rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama`; `setup.py:773-779`).
- `scripts/profile_resources.py`: VRAM/RAM/latency and gate-safety verification.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length=120`, `py311`) and pytest (`testpaths=["tests"]`).
- `.streamlit/config.toml`: AMOLED theme, `maxUploadSize=50`, XSRF/CORS, usage stats off.
- `requirements*.txt`: runtime, lockfile, test dependencies.
- `.github/workflows/ci.yml`: install from lockfile, `ruff check`, `ruff format --check`, generate corpus, `pytest tests/ -v`.
- `.env` (if present): local environment only; never commit or read secrets.

**Core Logic:**
- `core/models.py:14`: `CONFIG_VERSION = "docling-1000-200-v1"` drives cache paths and summary invalidation.
- `core/local_llm.py:25`: `InferenceGate`; `core/local_llm.py:236`: streaming grounded QA.
- `core/summarizer.py:376`: `summarize_document`; profiles at lines 35–109.
- `core/doc_store.py:105`: migration registry; `core/doc_store.py:291`: atomic `record_ingestion`.
- `retrieval/hybrid_retriever.py:738`: `search_hybrid`; `core/models.py:171`: `RetrievalResult`.
- `ingestion/upload_validation.py:15`: `MAX_FILE_MB=50`, `MAX_PAGES=500`.
- `ui/views.py`: `render_chat_view`, `render_library_view`, `render_file_upload_button`.
- `main.py`: consolidated 2-view navigation (`Chat` and `Document Library`); dispatch in lines 270–320.

**Testing:**
- `tests/conftest.py`: shared fixtures (`mock_llama_provider`, `mock_sentence_transformer`, `mock_groq_client`, `sample_pdf_path`).
- `tests/data/corpus/generate_corpus.py`: regenerates deterministic PDFs used by ingestion tests.
- One suite per module: `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_summarizer.py`, `tests/test_citation_validator.py`, `tests/test_concurrency_lock.py`, `tests/test_main_ui.py`, `tests/test_ui_smoke.py`, etc.

## Naming Conventions

**Files:**
- `snake_case.py`, one primary class or concern per module: `hybrid_retriever.py` → `HybridRetriever`, `doc_store.py` → `DocStore`.
- Tests: `tests/test_<module_or_feature>.py`.
- Scripts: verb/noun task names (`benchmark_baseline.py`, `profile_resources.py`).

**Directories:**
- Lowercase package names by responsibility (`core`, `ingestion`, `retrieval`, `providers`, `ui`). Do not create a new top-level package for a single module; place it in the matching layer.

**Classes:**
- `PascalCase` nouns: `DocStore`, `HybridRetriever`, `IngestionService`, `LifecycleService`, `InferenceGate`, `VisualAnalyzer`, `Summarizer`, `LlamaCppProvider`.
- Pydantic models are singular nouns in `core/models.py`; provider contract models in `providers/model_provider.py`.

**Functions / methods:**
- `snake_case`, verb-first for actions (`ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `search_hybrid`, `index_chunks`).
- UI renderers: `render_<area>` returning `None` (`render_chat_view`, `render_library_view`, `render_file_upload_button`, `render_sidebar_documents`).
- Boolean predicates: `is_*`, `has_*`, `should_*` (`is_persistent`, `has_document`, `should_ocr_page`, `is_abstention`).

**Variables / constants:**
- `snake_case` locals; module constants `UPPER_SNAKE_CASE` (`MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`, `CONFIG_VERSION`).

**Identifiers:**
- Document: `doc_<sha256[:16]>` (`ingestion/upload_validation.py:36-48`).
- Chunk: `{sha12}_p{page}_{index:04d}` (`ingestion/pdf_reader.py:94`, `ingestion/docling_reader.py:339`).
- Evidence element: `elem_{doc_id}_p{page}_{kind}_{idx:02d}` (`ingestion/visual_analyzer.py:258`).
- Summary: `summ_<uuid4[:16]>` (`core/summarizer.py:481`).
- Session summary cache key: `summary_{doc_id}_{profile}` (`ui/views.py:559`).

## Where to Add New Code

**New Feature (user-visible workspace or capability):**
- Primary code: add the workflow to a service first — `ui/ingestion_service.py` / `ui/lifecycle_service.py` for storage-touching flows, or a new `ui/<feature>_service.py` following the constructor pattern `(doc_store, hybrid_retriever, local_embedding, cache_dir)`.
- Presentation: add `render_<feature>_view(...)` in `ui/views.py`; import it in `main.py`; add the label to `WORKSPACES` in `main.py` and a branch to the dispatch chain.
- Tests: `tests/test_<feature>.py` + fixture additions in `tests/conftest.py` if a new external dependency is mocked.

**New Inference Provider:**
- Implementation: `providers/<name>_provider.py`, subclass `BaseModelProvider` (`providers/model_provider.py:64`), implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`, and `close`.
- Routing: extend `AiModel._detect_provider` (`core/local_llm.py:197-213`) and `set_cloud_mode` (`core/local_llm.py:167-195`). Cloud providers MUST accept a `user_consented` flag and assert it before any network call (mirror `providers/groq_provider.py:62-68`).
- UI configuration: extend `PROVIDER_CONFIG` in `ui/views.py:791-795` and the session default `cloud_provider` / `cloud_model` in `main.py:92-93`.
- Tests: `tests/test_<name>_provider.py` with `httpx.MockTransport` or a mocked SDK client.

**New Ingestion Extractor / Preprocessor:**
- Implementation: `ingestion/<extractor>.py` returning `list[dict]` chunks (`Chunk` dumps) and `list[Page]` records, with per-page fault isolation.
- Orchestration: call it inside `IngestionService.ingest_pdf` between extraction and OCR (`ui/ingestion_service.py:141-188`), and ensure failures degrade rather than abort.
- Chunk identity: reuse the `{sha12}_p{page}_{idx:04d}` convention and set `extraction="<backend>"` on every `Chunk`.
- If chunking policy changes: bump `CONFIG_VERSION` in `core/models.py:14` so caches and summaries invalidate.

**New Retrieval Backend or Ranking Stage:**
- Implementation: extend `retrieval/hybrid_retriever.py`; expose a free function for ranking math (follow `compute_rrf`, lines 120–165) so it is unit-testable.
- Integration: keep `search_hybrid` returning a canonical `RetrievalResult` with rank provenance; never return raw dicts to callers.
- Persistence: route writes through `index_chunks` / `delete_document` / `purge_all`; raise `VectorIndexError` on failed writes (lines 74–80) rather than returning a count.
- Tests: `tests/test_hybrid_retriever.py`; use a temp `db_uri` and the `mock_sentence_transformer` fixture.

**New Persistent Field or Table:**
- Schema: add a new DDL block and migration entry in `core/doc_store.py` (`SCHEMA_V5_DDL`, `MIGRATIONS[5]`, lines 17–110). Never edit an applied migration; append a new version.
- Model: add the field to the canonical Pydantic model in `core/models.py` and update both read (`model_validate`) and write paths.
- Ingestion/reindex: persist it in `record_ingestion` (`core/doc_store.py:291-436`) so partial writes stay atomic.
- Tests: `tests/test_doc_store.py` includes migration and transactional-ingestion coverage; extend it.

**New Domain Helper (prompting, citation, budgeting, telemetry):**
- Implementation: `core/<concern>.py`, pure functions where possible, with a module docstring stating invariants.
- Do not import Streamlit or `ui.*` from `core/`; keep the dependency direction `ui → core/ingestion/retrieval → core.models`.

**New UI Component / Icon:**
- Component: add a helper to `ui/components.py` (`get_svg_icon`, `render_status_pill`, `render_citation_chip` pattern).
- Icon: add an SVG to `assets/icons/` and reference it by name; there is no CDN or external asset load.
- Styling: extend `ui/theme.py` tokens; do not inline new color systems in views.

**Utilities:**
- Shared helpers belong in the layer that owns the concern: model/storage in `core/`, parsing in `ingestion/`, ranking in `retrieval/`, presentation in `ui/`.
- Do not add a generic `utils.py`; if truly cross-layer, add a narrowly named module (e.g. `core/token_utils.py`) and import only from allowed layers.

## Special Directories

**`data/`:**
- Purpose: `documents.db` (SQLite source of truth) and `lancedb/` (vector + FTS index).
- Generated: Yes (created by `DocStore` / `HybridRetriever`).
- Committed: No.

**`.cache/`:**
- Purpose: Extraction artifacts keyed by content hash and config version: `pages.json`, `chunks.json`, `manifest.json`.
- Generated: Yes (`ui/ingestion_service.py:329-340`; `core/models.py:17-30`).
- Committed: No. Safe to delete; re-ingestion regenerates it.

**`models/`:**
- Purpose: `qwen3-vl-2b-instruct-q4_k_m.gguf` (legacy filename, Qwen2-VL-2B weights) and `mmproj-f16.gguf`.
- Generated: Downloaded by `python setup.py download_models`.
- Committed: No (size + licensing). Identity is verified by `core/model_identity.py` before launch.

**`tools/llama-server/`:**
- Purpose: Local llama-server binary installed by `python setup.py setup_llama_server`.
- Generated: Yes.
- Committed: No.

**`tests/data/corpus/`:**
- Purpose: Deterministic synthetic PDFs (`clean_digital`, `scanned_sample`, `dense_table`, `multi_column`, `chart_diagram`, `corrupt_invalid`) plus `generate_corpus.py`.
- Generated: PDFs are generated, but the generator is committed and CI regenerates before pytest.
- Committed: Generator yes; treat generated PDFs as build artifacts.

**`.planning/`:**
- Purpose: GSD project state, phase plans, research, and these codebase maps.
- Generated: By GSD workflows.
- Committed: Per project policy; not part of the runtime application.

**`.streamlit/`:**
- Purpose: Server/theme configuration (`maxUploadSize=50`, dark palette, telemetry off).
- Generated: No.
- Committed: Yes.

**`.github/`, `.devcontainer/`:**
- Purpose: CI and development container definitions.
- Generated: No.
- Committed: Yes.

---

*Structure analysis: 2026-10-21*
