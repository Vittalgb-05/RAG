# Codebase Structure

**Analysis Date:** 2026-10-29

## Directory Layout

```text
RAG/
├── main.py                     # Streamlit composition root + workspace router (542 lines)
├── start.py                    # Unified launcher: llama-server + Streamlit (355 lines)
├── setup.py                    # Packaging + setup CLI (models, llama.cpp, deps) (937 lines)
├── pyproject.toml              # Ruff + pytest configuration
├── requirements.txt            # Direct runtime dependencies
├── requirements-lock.txt       # uv-compiled universal lockfile (py3.11)
├── requirements-test.txt       # Test-only dependencies
├── Dockerfile                  # python:3.11-slim-bookworm image
├── docker-compose.yml          # app + optional CUDA llama-server profile
├── core/                       # Domain: models, storage, LLM facade, summary, validation
├── ui/                         # Presentation + UI orchestration services
├── ingestion/                  # PDF validation, extraction, OCR, visual analysis
├── retrieval/                  # Embeddings, hybrid index, in-memory fallback
├── providers/                  # Inference adapters behind one ABC
├── tests/                      # pytest suite (42 files, 474 test functions)
├── scripts/                    # Benchmarks, resource profiling, icon generation
├── docs/                       # Runbook, audits, evaluation, traceability
├── assets/                     # Brand mark + 20 monochrome SVG icons
├── models/                     # Local GGUF weights (gitignored runtime artifacts)
├── tools/                      # Vendored llama.cpp Windows binaries (+ rollback copy)
├── data/                       # SQLite DB, LanceDB tables, logs (gitignored)
├── .cache/                     # Per-document extraction cache (gitignored)
├── .streamlit/config.toml      # Dark AMOLED theme + loopback bind + 50 MB upload cap
├── .github/workflows/ci.yml    # Ruff check/format, corpus generation, pytest
├── .devcontainer/              # Dev container definition
├── .planning/                  # GSD planning artifacts (phases, research, codebase docs)
└── rag_assistant.egg-info/     # Editable-install metadata (generated)
```

## Directory Purposes

**`core/`:**
- Purpose: Framework-independent domain logic and persistence.
- Contains: Pydantic models, SQLite store, inference facade + VRAM gate, summarizer, citation validator, prompt budgeting, query intent, telemetry, runtime/model identity, redaction, logging setup.
- Key files: `core/models.py` (286), `core/doc_store.py` (931), `core/local_llm.py` (420), `core/summarizer.py` (602), `core/citation_validator.py` (677), `core/prompt_budget.py` (200), `core/query_intent.py` (377).

**`ui/`:**
- Purpose: Streamlit presentation plus session-coupled orchestration.
- Contains: Five workspace renderers, reusable components, AMOLED theme CSS, markdown sanitizer, chat turn service, ingestion/lifecycle services, startup hydration, session reset.
- Key files: `ui/views.py` (1548), `ui/chat_controller.py` (737), `ui/theme.py` (493), `ui/ingestion_service.py` (339), `ui/sanitizer.py` (249), `ui/components.py` (240), `ui/hydration.py` (221), `ui/lifecycle_service.py` (206), `ui/session_state.py` (64).

**`ingestion/`:**
- Purpose: Convert untrusted PDF bytes into canonical records.
- Contains: Upload validation, Docling layout/table extraction, pypdf fallback, conditional RapidOCR, PyMuPDF visual detection + VLM analysis.
- Key files: `ingestion/upload_validation.py` (176), `ingestion/docling_reader.py` (439), `ingestion/pdf_reader.py` (170), `ingestion/ocr_fallback.py` (533), `ingestion/visual_analyzer.py` (322).

**`retrieval/`:**
- Purpose: Embedding, indexing, and search.
- Contains: CPU sentence-transformer wrapper + process cache, LanceDB hybrid retriever with RRF and JSON mirror fallback, pure-Python `VectorIndex`.
- Key files: `retrieval/hybrid_retriever.py` (1092), `retrieval/local_embedding.py` (176), `retrieval/vector_index.py` (228).

**`providers/`:**
- Purpose: Inference backend adapters.
- Contains: `BaseModelProvider` ABC + capability/health schemas, local llama-server HTTP/SSE client, LiteLLM cloud adapter, direct Groq client.
- Key files: `providers/model_provider.py` (156), `providers/llama_cpp_provider.py` (366), `providers/litellm_provider.py` (358), `providers/groq_provider.py` (194).

**`tests/`:**
- Purpose: Fully offline unit/integration/UI tests.
- Contains: 42 `test_*.py` modules, shared fixtures in `tests/conftest.py`, synthetic PDF corpus generator and fixtures in `tests/data/corpus/`.
- Key files: `tests/conftest.py`, `tests/data/corpus/generate_corpus.py`, `tests/test_hybrid_retriever.py` (27 tests), `tests/test_doc_store.py` (21), `tests/test_models.py` (20), `tests/test_llama_cpp_provider.py` (20).

**`scripts/`:**
- Purpose: Operator/developer tooling, not imported by the app.
- Contains: `benchmark_baseline.py`, `benchmark_multimodal.py`, `profile_resources.py` (writes JSON to `.planning/research/`), `generate_icons.py` (regenerates `assets/icons/*.svg`).

**`docs/`:**
- Purpose: Human-facing engineering documentation.
- Contains: `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`, `DEPENDENCY_AUDIT.md`, `CODE_QUALITY_REPORT.md`, `REQUIREMENTS_TRACEABILITY.md`, `FILE_CALLER_TEST_MAP.md`, `ENDPOINT_INTEGRATION_MATRIX.md`, `TEST_RESULTS.md`, `REPAIR_LOG.md`, `AUDIT_SUMMARY.md`, `LICENSES.md`.

**`assets/`:**
- Purpose: Local-only visual assets (no CDN/font fetches).
- Contains: `assets/brand_mark.svg`, `assets/icons/{chat,document,library,summarizer,settings,gpu,ram,database,lock,cloud,cpu,search,upload,download,trash,refresh,check,alert,info,sparkle,chevron-right,workspace}.svg`.

**`tools/`:**
- Purpose: Vendored native llama.cpp runtime for Windows.
- Contains: `tools/llama-server/` (current build binaries + CUDA/CPU DLLs) and `tools/llama-server-b11718-rollback/` (previous build for rollback). Binary artifacts, not source.

## Key File Locations

**Entry Points:**
- `start.py:292`: `main()` launcher (loopback guard, optional llama-server spawn, Streamlit launch).
- `main.py`: Streamlit script body; routing at `main.py:502`.
- `setup.py:774`: `main_cli()` setup entry; console scripts declared at `setup.py:827-833`.
- `Dockerfile`: `CMD ["streamlit", "run", "main.py", ...]`.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length=120`, `target-version=py311`, rules `E,F,W,B,UP,SIM`) and pytest (`testpaths=["tests"]`).
- `.streamlit/config.toml`: dark theme tokens, `address="127.0.0.1"`, `maxUploadSize=50`, telemetry off.
- `.env.example`: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLAMA_SERVER_URL/HOST/PORT`, `DOCLING_ARTIFACTS_PATH`, `RAG_LOG_LEVEL`, `RAG_LOG_DIR`, `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`.
- `docker-compose.yml`: host-loopback port mapping, data/models/cache volumes, `gpu` profile for llama-server.
- `.github/workflows/ci.yml`: uv install from lockfile, `ruff check .`, `ruff format --check .`, corpus generation, `pytest tests/ -v`.

**Core Logic:**
- `core/models.py`: canonical schemas + `CONFIG_VERSION = "docling-1000-200-v1"` + `cache_dir_for()`.
- `core/doc_store.py:141`: `MIGRATIONS` map (v1 documents/pages/chunks, v2 evidence_elements, v3 document_summaries, v4 indexes, v5 deletion_tombstones).
- `core/local_llm.py:35`: `InferenceGate`; `:112` `AiModel`.
- `core/summarizer.py:476`: `summarize_document` (single-pass vs map-reduce).
- `core/citation_validator.py:411`: `validate_citations`; `:579` `auto_attribute_citations`.
- `core/prompt_budget.py:19`/`:40`: QA and summary system templates; `:85` `assemble_grounded_messages`.
- `core/query_intent.py:325`: `resolve_retrieval` (hybrid vs whole-document vs intent mismatch).
- `retrieval/hybrid_retriever.py:959`: `search_hybrid`; `:641` `fetch_document_chunks`.
- `ui/chat_controller.py:131`: `ChatTurnService` (Streamlit-free).
- `ui/ingestion_service.py:54`: `ingest_pdf` (the single ingestion pipeline).

**Testing:**
- `tests/conftest.py`: env hardening (`USE_TF=0`, `USE_TORCH=1`), Groq mock client, shared fixtures.
- `tests/data/corpus/generate_corpus.py`: reportlab synthetic PDFs (`clean_digital.pdf`, `scanned_sample.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`).
- `tests/test_grounding_contract.py`, `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`: grounding/abstention invariants.
- `tests/test_ui_smoke.py`, `tests/test_ui_redesign_apptest.py`, `tests/test_main_ui.py`: Streamlit `AppTest` coverage.

## Naming Conventions

**Files:**
- Modules: `snake_case`, one responsibility per module (`hybrid_retriever.py`, `upload_validation.py`, `citation_validator.py`).
- UI renderers: `ui/views.py` holds `render_<workspace>_view`; supporting renderers are `render_<area>` (`render_file_upload_button`, `render_notifications`).
- Orchestration services: `ui/<workflow>_service.py` with a `<Workflow>Service` class (`ingestion_service.py` → `IngestionService`, `lifecycle_service.py` → `LifecycleService`).
- Tests: `tests/test_<module_or_feature>.py`; test functions `test_<behavior>_<condition>`.
- Data models: singular nouns in `core/models.py` (`Chunk`, `Page`, `Document`, `EvidenceElement`).

**Directories:**
- Domain packages are single-word and plural-agnostic: `core/`, `ui/`, `ingestion/`, `retrieval/`, `providers/`.
- Generated/runtime directories are dot-prefixed or conventional: `.cache/`, `.planning/`, `data/`, `models/`, `tools/`.

**Symbols:**
- Classes `PascalCase` (`DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `ChatTurnService`, `VisualAnalyzer`).
- Functions `snake_case`, verb-first (`ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `resolve_retrieval`).
- Private helpers prefixed `_` (`_retrieve_document_wide`, `_consume_deletion_tombstones`, `_build_report`, `_execute_write`).
- Constants `UPPER_SNAKE` (`MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_MAX_OUTPUT_TOKENS`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`, `CONFIG_VERSION`).
- Pydantic fields `snake_case`; literals used for enums (`status`, `search_mode`, `grounding_status`, `profile`).

## Where to Add New Code

**New Workspace (e.g. an "Evaluation" page):**
- Register the name in `WORKSPACES` (and `NAV_WORKSPACES` if it belongs in the sidebar radio) at `main.py:59-60`.
- Add a `render_<name>_view(...)` function. Current convention appends to `ui/views.py`; prefer a new `ui/views_<name>.py` module imported by `main.py` to avoid growing the 1548-line file.
- Add the dispatch branch at `main.py:502-540` and pass only the dependencies it needs (`doc_store`, `ai_model`, `cache_dir`, `health`, `caps`).
- Reuse `ui/components.py` (`render_stat_card`, `render_status_pill`, `render_empty_state`, `push_notification`) rather than new HTML strings.

**New UI Orchestration Workflow:**
- Create `ui/<workflow>_service.py` with a dataclass result (pattern: `IngestionResult`, `ChatTurnPreparation`, `ChatTurnResult`).
- Do not import Streamlit in the service; follow `ui/chat_controller.py` (module docstring explicitly states the boundary). Session mutation belongs in the view or in a documented helper in `ui/session_state.py`.
- Tests: `tests/test_<workflow>_service.py` with fake `DocStore`/retriever objects.

**New Domain Capability (intent, budgeting, validation):**
- Add to the matching `core/` module rather than a new one where possible: prompt assembly → `core/prompt_budget.py`; intent/scope → `core/query_intent.py`; citation/support rules → `core/citation_validator.py`.
- New cross-layer schema → `core/models.py` (frozen, `extra="forbid"`), then update `DocStore` serialization and any `model_dump()` consumers.

**New Inference Provider:**
- Subclass `BaseModelProvider` in `providers/<name>_provider.py` and implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities` (`providers/model_provider.py:64-156`).
- Cloud adapters must accept `user_consented` and assert it on every call (pattern: `providers/litellm_provider.py:141`, `providers/groq_provider.py:65`).
- Wire selection in `AiModel._detect_provider` (`core/local_llm.py:217`) and add an entry to `PROVIDER_CONFIG` in `ui/views.py:1270` (and the duplicate map at `:1499` until it is deduplicated).
- Tests: `tests/test_<name>_provider.py` using `httpx.MockTransport` (see `providers/llama_cpp_provider.py:71` `transport` parameter).

**New Ingestion Stage:**
- Add the module under `ingestion/` with a pure function/class that accepts bytes and returns canonical models.
- Insert the call in `IngestionService.ingest_pdf` between extraction (`ui/ingestion_service.py:147`), OCR (`:178`), and visual analysis (`:192`), wrapped in its own try/except so one stage cannot abort ingestion.
- Persist new artifacts through `DocStore.record_ingestion` / `record_evidence_elements`; never write SQLite directly from a view.

**New Retrieval Capability:**
- Implement on `HybridRetriever` (`retrieval/hybrid_retriever.py`) and expose through `resolve_retrieval` (`core/query_intent.py:325`) so every caller inherits scope/budget rules.
- Keep `EvidenceSnippet.rank` contiguous from 1 — citation validation assumes `max_valid_rank == len(snippets)`.

**New SQLite Schema Change:**
- Add `SCHEMA_V6_DDL` and register `6: SCHEMA_V6_DDL` in `MIGRATIONS` (`core/doc_store.py:141-147`); never edit v1–v5.
- Add the corresponding read/write method on `DocStore` using `_execute_write` for mutations and `_connect` for reads.

**New Prompt Template / Pipeline Contract:**
- Add the template to `core/prompt_budget.py` next to `SYSTEM_GROUNDING_TEMPLATE` and `SUMMARY_SYSTEM_TEMPLATE`, and pass it via the `system_template` argument of `assemble_grounded_messages`.
- Keep `<document_context>` as the only evidence wrapper; run untrusted text through `sanitize_xml_boundary`.

**New UI Component:**
- Add to `ui/components.py` (returning HTML strings for `st.html` or rendering directly), and read colors/spacing from the token constants in `ui/theme.py` (`COLOR_BG`, `COLOR_SURFACE`, `COLOR_PRIMARY`, …).
- Add icons to `assets/icons/` and register them in `scripts/generate_icons.py` so they are reproducible.

**Utilities:**
- Shared helpers that touch several layers belong in `core/` (e.g. redaction `core/redaction.py`, telemetry `core/resource_telemetry.py`). Avoid creating a generic `utils.py`; every existing helper has a domain-named home.

## Special Directories

**`data/`:**
- Purpose: Runtime persistence — `documents.db` (SQLite WAL), `lancedb/` (vector + FTS tables and `fallback_store.json` mirror), `lancedb_bench/` (benchmark output), `logs/app.log`.
- Generated: Yes.
- Committed: No (gitignored).

**`.cache/`:**
- Purpose: Per-document extraction artifacts at `.cache/<sha256>/<CONFIG_VERSION>/` (pages/chunks/manifest), keyed by `core/models.py:17` `cache_dir_for`.
- Generated: Yes.
- Committed: No.

**`models/`:**
- Purpose: Local GGUF weights — `qwen3.5-2b-q4_k_m.gguf`, `qwen3.5-2b-mmproj-f16.gguf` (expected names from `providers/llama_cpp_provider.py:50-51`); older `qwen3-vl-2b-instruct-q4_k_m.gguf` / `mmproj-f16.gguf` may remain from a prior install.
- Generated: Downloaded by `setup.py download_models`.
- Committed: No.

**`tools/`:**
- Purpose: Vendored llama.cpp binaries and DLLs; `llama-server-b11718-rollback/` keeps the previous build for rollback.
- Generated: Downloaded by `setup.py install_llama`.
- Committed: Binary artifacts are present in the working tree; treat as environment-specific.

**`.planning/`:**
- Purpose: GSD workflow state — `PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `phases/`, `research/`, `debug/`, and this `codebase/` directory.
- Generated: By GSD commands.
- Committed: Yes (planning history is tracked).

**`.freebuff/`:**
- Purpose: Contains only `project-id`; tool-specific marker directory with no application role.
- Generated: Yes.
- Committed: Currently present in the working tree; not referenced by any code.

**`application_screenshots/`:**
- Purpose: Reference screenshots of the UI, not consumed by the app.
- Generated: Manually captured.
- Committed: Yes.

---

*Structure analysis: 2026-10-29*
