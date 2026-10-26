# Codebase Structure

**Analysis Date:** 2026-10-26

## Directory Layout

```text
RAG/
├── main.py                      # Streamlit composition root: session state, hydration, sidebar, workspace router
├── start.py                     # One-command launcher: pre-flight checks, llama-server launch, Streamlit subprocess
├── setup.py                     # Packaging + setup CLI (deps, GGUF models, llama-server binary)
├── core/                        # Domain: models, SQLite store, LLM facade, summarizer, citation/prompt logic
├── ingestion/                   # PDF validation, Docling/pypdf extraction, conditional OCR, visual analysis
├── retrieval/                   # LanceDB hybrid retrieval, MiniLM embeddings, in-memory fallback index
├── providers/                   # BaseModelProvider ABC, llama.cpp, LiteLLM, Groq adapters
├── ui/                          # Streamlit views, components, theme, sanitizer, orchestration services
├── tests/                       # pytest suite + synthetic PDF corpus generator
├── scripts/                     # Benchmarks, resource profiling, icon generation
├── docs/                        # Operator and audit documentation
├── assets/                      # Brand mark + monochrome SVG icon set
├── .streamlit/config.toml       # AMOLED theme and loopback server settings
├── .github/workflows/ci.yml     # Ruff + corpus generation + pytest on Python 3.11
├── .planning/                   # GSD project state, phase plans, research, codebase maps
├── data/                        # Generated: SQLite DB, LanceDB, logs, benchmark index (gitignored)
├── .cache/                      # Generated: reserved content-addressed extraction cache (gitignored)
├── models/                      # Generated/downloaded: GGUF language model + mmproj (gitignored)
├── tools/llama-server/          # Generated/downloaded: llama-server binary (gitignored)
├── application_screenshots/     # README screenshots
├── Dockerfile                   # python:3.11-slim-bookworm image, Streamlit on 8501
├── docker-compose.yml           # app service + optional CUDA llama-server service
├── pyproject.toml               # Ruff + pytest configuration
├── requirements.txt             # Runtime dependencies
├── requirements-lock.txt        # uv-compiled universal lockfile (Python 3.11)
├── requirements-test.txt        # Test-only dependencies
├── README.md                    # User-facing overview, quickstart, privacy model
├── CLAUDE.md                    # Generated project/stack/convention context for agents
└── LICENSE
```

## Directory Purposes

**`core/`:**
- Purpose: Framework-light domain logic and persistence; the only package that defines canonical schemas.
- Contains: Pydantic models, SQLite store, provider-facing LLM facade, concurrency gate, summarizer, query-intent resolution, citation validation, prompt budgeting, telemetry, logging setup, GGUF identity verification.
- Key files: `core/models.py`, `core/doc_store.py`, `core/local_llm.py`, `core/summarizer.py`, `core/query_intent.py`, `core/citation_validator.py`, `core/prompt_budget.py`.
- Dependency rule: may import `providers.model_provider`, concrete providers, and `retrieval`; must not import `ui`.

**`ingestion/`:**
- Purpose: Convert untrusted PDF bytes into canonical chunks/pages/evidence with bounded resource use.
- Contains: upload validation, Docling structured reader, pypdf fallback, conditional RapidOCR, PyMuPDF visual region detection and VLM analysis.
- Key files: `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`.
- Dependency rule: may import `core.models` and the `BaseModelProvider` type; must not import `ui`.

**`retrieval/`:**
- Purpose: Persist embeddings and return ranked evidence as `RetrievalResult`.
- Contains: LanceDB hybrid retriever with FTS + RRF, CPU MiniLM wrapper, pure-stdlib `VectorIndex` fallback, legacy-index migration, durable JSON mirror.
- Key files: `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `retrieval/vector_index.py`.
- Dependency rule: may import `core.models`; must not import `ui` or concrete providers.

**`providers/`:**
- Purpose: Inference backend adapters behind one ABC.
- Contains: `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus`, llama-server HTTP/SSE client, LiteLLM cloud adapter, direct Groq adapter.
- Key files: `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`.
- Dependency rule: may import only `providers.model_provider`; no `core`/`ui` imports.

**`ui/`:**
- Purpose: Streamlit presentation plus document-workflow orchestration.
- Contains: four view renderers, reusable HTML/SVG components, AMOLED CSS, Markdown/HTML sanitizer, session reset, ingestion service, lifecycle service, startup hydration.
- Key files: `ui/views.py` (largest module, 1,332 lines), `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`, `ui/session_state.py`.
- Dependency rule: may import every other package; no other package may import `ui`.

**`tests/`:**
- Purpose: Offline pytest coverage for every module, including mocked providers and synthetic PDFs.
- Contains: 29 test modules (~9,500 lines), shared fixtures in `tests/conftest.py`, corpus generator and generated PDFs in `tests/data/corpus/`.
- Key files: `tests/conftest.py`, `tests/data/corpus/generate_corpus.py`, `tests/test_main_ui.py`, `tests/test_hybrid_retriever.py`, `tests/test_doc_store.py`.

**`scripts/`:**
- Purpose: Manual benchmarking and profiling harnesses, not part of the runtime import graph.
- Contains: baseline retrieval benchmark, multimodal quality/grounding benchmark, VRAM/RAM profiler, SVG icon generator.
- Key files: `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`.

**`docs/`:**
- Purpose: Operator runbook, evaluation results, endpoint integration matrix, file→caller→test map, audit/repair history, licenses.
- Key files: `docs/RUNBOOK.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`, `docs/FILE_CALLER_TEST_MAP.md`, `docs/ENDPOINT_INTEGRATION_MATRIX.md`.

**`assets/`:**
- Purpose: Local-only visual assets (no CDN/font/icon network requests).
- Contains: `assets/brand_mark.svg` and monochrome SVGs in `assets/icons/` loaded by `ui/components.py`.

**`.streamlit/`:**
- Purpose: Runtime UI configuration.
- Key files: `.streamlit/config.toml` (AMOLED palette, `address = "127.0.0.1"`, 50 MB upload cap, CORS/XSRF enabled).

**`.github/`:**
- Purpose: CI automation.
- Key files: `.github/workflows/ci.yml` (uv install from lockfile, `ruff check`, `ruff format --check`, corpus generation, `pytest tests/ -v`).

**`.planning/`:**
- Purpose: GSD planning state and historical artifacts.
- Contains: `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, phase directories `00`–`08`, `research/`, `debug/`, and this `codebase/` map.
- Note: `pyproject.toml` excludes `.planning` from Ruff.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit composition root; page config, session defaults, DocStore cache, hydration, health probe, consent dialog, sidebar, four-workspace router.
- `start.py`: CLI launcher; loopback enforcement, directory creation, llama-server probe/launch, GGUF identity verification, Streamlit subprocess.
- `setup.py`: setuptools packaging and setup commands (`download_models`, `install-llama`).
- `tests/conftest.py`: pytest fixtures and offline mocking seams.
- `scripts/profile_resources.py`: resource profiling harness.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, target `py311`) and pytest (`testpaths = ["tests"]`).
- `.streamlit/config.toml`: theme and server bind/upload limits.
- `requirements.txt`, `requirements-lock.txt`, `requirements-test.txt`: dependency manifests.
- `.github/workflows/ci.yml`: CI pipeline definition.
- `Dockerfile`, `docker-compose.yml`, `.dockerignore`: container deployment.
- `.env` / `.env.example`: local environment configuration (existence noted only; contents not read).
- `core/prompt_budget.py`: token-budget constants (`DEFAULT_MAX_OUTPUT_TOKENS`).
- `core/summarizer.py`: summarizer batching constants (`FAST_PATH_TOKEN_LIMIT`, `MAX_BATCH_TOKENS`).
- `ingestion/ocr_fallback.py`: OCR resource budgets (`MAX_RENDER_PIXELS`, `MAX_OCR_PAGES_PER_DOC`, `MAX_OCR_SECONDS_PER_DOC`).
- `ingestion/visual_analyzer.py`: crop budgets (`MAX_CROP_PIXELS`, `MAX_CROP_BYTES`).

**Core Logic:**
- `core/models.py`: canonical schemas, `CONFIG_VERSION`, `cache_dir_for`.
- `core/doc_store.py`: SQLite schema v1–v4, atomic `record_ingestion`, summaries, delete/purge.
- `core/local_llm.py`: `AiModel` facade and `InferenceGate`.
- `core/summarizer.py`: five profile prompts, single-pass/map-reduce, summary cache.
- `core/query_intent.py`: follow-up contextualization, whole-document detection, page-diverse selection.
- `core/citation_validator.py`: citation precision, abstention, injection detection, auto-attribution.
- `core/prompt_budget.py`: grounded message assembly and XML isolation.
- `retrieval/hybrid_retriever.py`: LanceDB dense + FTS + RRF, whole-document fetch, fallback mirror.
- `ui/ingestion_service.py`: end-to-end ingestion transaction script.
- `ui/lifecycle_service.py`: delete/purge/re-index transaction script.
- `ui/views.py`: chat, summarizer, library, settings renderers.

**Testing:**
- `tests/conftest.py`: provider/embedding mocks and shared fixtures.
- `tests/data/corpus/generate_corpus.py`: synthetic PDF corpus (clean digital, scanned, tables, charts, multi-column, corrupt).
- `tests/test_main_ui.py`, `tests/test_ui_smoke.py`: UI routing and rendering behavior.
- `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`: persistence and retrieval contracts.
- `tests/test_concurrency_lock.py`, `tests/test_cloud_privacy.py`: `InferenceGate` and consent invariants.

## Module Dependency Direction

| From | May depend on | Must not depend on |
|------|---------------|--------------------|
| `providers/` | `providers.model_provider` | `core`, `ingestion`, `retrieval`, `ui` |
| `retrieval/` | `core.models`, `retrieval.vector_index` | `providers` concrete classes, `ingestion`, `ui` |
| `ingestion/` | `core.models`, `providers.model_provider` (type) | `ui`; avoid `core.local_llm` (current exception: lazy `InferenceGate` import at `ingestion/visual_analyzer.py:288`) |
| `core/` | `core.*`, `providers.*`, `retrieval.*` | `ingestion`, `ui` |
| `ui/` | all packages | nothing imports `ui` |
| `main.py` / `start.py` / `setup.py` | all packages | — |

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` describing one responsibility (`hybrid_retriever.py`, `citation_validator.py`, `prompt_budget.py`).
- Tests: `tests/test_<module_or_feature>.py` (`test_doc_store.py`, `test_whole_document_extraction.py`).
- Documentation: `UPPERCASE.md` for operational/reference docs (`RUNBOOK.md`, `EVALUATION.md`); `README.md` and `CLAUDE.md` are conventional exceptions.
- Generated artifacts: lowercase directories (`data/`, `.cache/`, `models/`, `tools/`).

**Directories:**
- Top-level packages are single-word, lowercase, responsibility-based: `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`.
- No `src/` layout; packages sit at repository root and are discovered by `find_packages()` in `setup.py`.
- Test data lives under `tests/data/corpus/`, not beside source modules.

**Classes:**
- `PascalCase` domain nouns and services: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `Summarizer`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`.
- Provider classes end in `Provider`: `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`.
- Result/value types end in `Result`/`Status`/`Capabilities`: `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`, `IngestionResult`, `HealthStatus`, `ProviderCapabilities`.

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `resolve_retrieval`, `validate_citations`, `assemble_grounded_messages`.
- Streamlit renderers are `render_<area>` and return `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`.
- Test functions are `test_<behavior>_<condition>`.

**Private helpers:**
- Leading underscore for module-internal helpers: `_execute_write`, `_apply_migrations`, `_migrate_legacy_index`, `_escape_sql_literal`, `_bounded_zoom`, `_report_progress`.

## Where to Add New Code

**New Feature (user-facing workflow):**
- Primary code: add a `render_<workspace>_view` in `ui/views.py`, or a new `ui/<feature>_service.py` if the workflow spans storage + retrieval.
- Routing: add the workspace to the `WORKSPACES` list and router in `main.py` (keep both lists in sync; see ARCHITECTURE.md anti-pattern “Navigation source-of-truth drift”).
- Tests: `tests/test_ui_smoke.py` or `tests/test_main_ui.py`.

**New Ingestion Extractor or Preprocessor:**
- Implementation: `ingestion/<extractor>.py`, returning `Chunk`/`Page`/`EvidenceElement` from `core.models`.
- Wiring: call it from the extraction stage of `ui/ingestion_service.py:ingest_pdf` and isolate failures with a stage-level `try/except`.
- Tests: `tests/test_<extractor>.py` with synthetic PDFs from `tests/data/corpus/`.

**New Retrieval Mode or Ranking Strategy:**
- Implementation: `retrieval/hybrid_retriever.py` (or a new module under `retrieval/`), returning `RetrievalResult`/`EvidenceSnippet`.
- Contract: keep `search_hybrid(query, k, doc_id)` and `fetch_document_chunks(doc_id)` signatures; callers and citation validation depend on `rank` matching snippet order.
- Tests: `tests/test_hybrid_retriever.py` and `tests/test_whole_document_extraction.py`.

**New Inference Provider:**
- Implementation: `providers/<name>_provider.py` subclassing `BaseModelProvider`; implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Wiring: provider selection currently lives in `core/local_llm.py:_detect_provider` and cloud construction in `main.py`; add both, or introduce a provider factory first.
- Consent: any network provider must accept and enforce `user_consented` before generation.
- Tests: `tests/test_<name>_provider.py` using `httpx.MockTransport` or `unittest.mock`.

**New Persistence Table or Column:**
- Schema: add `SCHEMA_V5_DDL` and `MIGRATIONS[5]` in `core/doc_store.py`, bump the `PRAGMA user_version` path via the existing migration loop.
- Model: add/adjust the Pydantic schema in `core/models.py`.
- Access: add typed methods on `DocStore`; use `_execute_write` for mutations.
- Tests: `tests/test_doc_store.py` (migration + CRUD) and `tests/test_cache_invalidation.py` if summaries are affected.

**New Prompt/Context Rule:**
- Implementation: `core/prompt_budget.py` (budgeting/XML isolation) or `core/query_intent.py` (intent/selection).
- Consumers: `core/local_llm.py` and `ui/views.py` must use the same helper — do not duplicate heuristics.
- Tests: `tests/test_prompt_budget.py`, `tests/test_query_intent.py`.

**New Domain Algorithm or Validation:**
- Implementation: `core/<name>.py`; keep it framework-free and importable without Streamlit.
- Tests: `tests/test_<name>.py`.

**Utilities / Shared Helpers:**
- Cross-layer helpers belong in `core/` (domain) or the owning package; avoid a generic `utils/` package.
- UI-only helpers belong in `ui/components.py` (presentation) or `ui/views.py` (workflow-specific).
- Constants used by multiple modules belong with their owner (`core/prompt_budget.py`, `ingestion/ocr_fallback.py`) and should be imported, not re-declared.

**New Script or Benchmark:**
- Implementation: `scripts/<purpose>.py`; insert repository root into `sys.path` as existing scripts do.
- Output: write machine-readable JSON under `.planning/research/` (existing convention).

**New Documentation:**
- Operator docs: `docs/UPPERCASE.md`.
- Agent-facing project context: `.planning/codebase/*.md` (this map) and `CLAUDE.md`.

## Special Directories

**`data/`:**
- Purpose: Runtime persistence root.
- Contains: `documents.db` (SQLite WAL + `-wal`/`-shm`), `lancedb/` (table `chunks` + `fallback_store.json`), `logs/app.log`, `lancedb_bench/` (profiling output).
- Generated: Yes.
- Committed: No (`.gitignore` ignores `data/`).

**`.cache/`:**
- Purpose: Reserved content-addressed extraction cache (`<sha256>/<CONFIG_VERSION>` via `core/models.py:cache_dir_for`).
- Contains: currently no production writer; lifecycle services delete the per-document directory on delete and the whole directory on purge.
- Generated: Yes.
- Committed: No.

**`models/`:**
- Purpose: Local GGUF artifacts.
- Contains: `qwen3-vl-2b-instruct-q4_k_m.gguf` (metadata identifies Qwen2-VL-2B-Instruct) and `mmproj-f16.gguf`.
- Generated: Yes (downloaded by `setup.py download_models` with SHA-256 checks).
- Committed: No.

**`tools/llama-server/`:**
- Purpose: Local llama.cpp server binary.
- Contains: `llama-server.exe` on Windows or `llama-server` on Linux.
- Generated: Yes (installed by `setup.py install-llama`).
- Committed: No.

**`retrieval/data/lancedb/`:**
- Purpose: Legacy pre-0.2 vector index location.
- Contains: legacy LanceDB files that `_migrate_legacy_index` copies non-destructively into `data/lancedb/` when the canonical target has no table.
- Generated: Yes (legacy).
- Committed: No (`*.lance`/`*.lance/` ignored).

**`rag_assistant.egg-info/`:**
- Purpose: Editable-install metadata produced by `pip install -e .`.
- Generated: Yes.
- Committed: No (`*.egg-info/` ignored).

**`application_screenshots/`:**
- Purpose: README screenshots and Mermaid architecture image.
- Generated: No (curated).
- Committed: Yes.

**`.planning/`:**
- Purpose: GSD state, phase plans/summaries, research benchmarks, debug logs, codebase maps.
- Generated: Partially (by GSD workflows).
- Committed: Yes (except `.planning/debug/*.py`, which is ignored).

**`.devcontainer/`:**
- Purpose: Dev container definition (Python 3.11 bookworm, port 8501).
- Generated: No.
- Committed: Yes.

## Documentation Note

`README.md:72-109` describes a flat module layout (`local_llm.py`, `doc_store.py`, etc. at repository root). The current code is package-based under `core/`, `ingestion/`, `retrieval/`, `providers/`, and `ui/`. Use this STRUCTURE.md for file placement; treat the README tree as a high-level conceptual overview.

---

*Structure analysis: 2026-10-26*
