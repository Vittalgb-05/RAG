# Codebase Structure

**Analysis Date:** 2026-10-22

## Directory Layout

```text
RAG/
├── main.py                  # Streamlit composition root and workspace router
├── start.py                 # Launcher: loopback guard, llama-server probe/spawn, Streamlit subprocess
├── setup.py                 # Packaging + checksum-pinned model/llama-server installer CLI
├── core/                    # Domain models, persistence, inference facade, summarization, prompting
│   ├── models.py            # Pydantic v2 canonical schemas
│   ├── doc_store.py         # SQLite store, migrations v1–v4, atomic ingestion writes
│   ├── local_llm.py         # InferenceGate + AiModel facade
│   ├── summarizer.py        # Five-profile single-pass / map-reduce summarizer
│   ├── query_intent.py      # Follow-up rewrite, whole-document detection, evidence selection
│   ├── prompt_budget.py     # Context budgeting and XML isolation
│   ├── citation_validator.py# Rank/support validation, abstention, injection, auto-attribution
│   ├── model_identity.py    # GGUF metadata parsing and model-pair verification
│   ├── resource_telemetry.py# nvidia-smi/psutil telemetry and latency tracking
│   └── logging_setup.py     # Idempotent logging + watcher-noise filter
├── ui/                      # Presentation and Streamlit orchestration services
│   ├── views.py             # Chat, Summarizer, Library, Settings renderers
│   ├── components.py        # SVG icons, cards, status pills, citation chips
│   ├── theme.py             # AMOLED CSS injection
│   ├── sanitizer.py         # Markdown/HTML sanitization for local rendering
│   ├── session_state.py     # Shared in-memory reset
│   ├── ingestion_service.py # End-to-end ingestion orchestration
│   ├── lifecycle_service.py # Delete / purge / re-index orchestration
│   └── hydration.py         # Startup catalog and vector repair
├── ingestion/               # Untrusted PDF → pages/chunks/visual evidence
│   ├── upload_validation.py # Magic bytes, caps, SHA-256, doc_id
│   ├── docling_reader.py    # Docling layout/tables with pypdf fallback
│   ├── pdf_reader.py        # pypdf extraction and chunking
│   ├── ocr_fallback.py      # Conditional RapidOCR with raster/time budgets
│   └── visual_analyzer.py   # Visual region detection, crops, VLM analysis
├── retrieval/               # Embeddings and hybrid retrieval
│   ├── local_embedding.py   # CPU-pinned all-MiniLM-L6-v2, shared process cache
│   ├── hybrid_retriever.py  # LanceDB dense+FTS, RRF, durable mirror, whole-doc fetch
│   ├── vector_index.py      # Pure-Python fallback vector store
│   └── data/                # Legacy package-relative LanceDB location (migration source only)
├── providers/               # Inference provider adapters
│   ├── model_provider.py    # BaseModelProvider ABC + capability/health schemas
│   ├── llama_cpp_provider.py# Local llama-server HTTP/SSE + VLM
│   ├── litellm_provider.py  # Consent-gated cloud adapter
│   └── groq_provider.py     # Direct Groq adapter
├── tests/                   # Pytest suite, shared fixtures, synthetic corpus
│   ├── conftest.py          # Offline fixtures (mock providers, embeddings, env keys)
│   ├── test_*.py            # 30+ suites covering each module
│   └── data/corpus/         # Generated PDFs and generator script
├── scripts/                 # Benchmarking, profiling, icon generation
├── docs/                    # Runbook, audit, evaluation, traceability docs
├── assets/icons/            # Local monochrome SVGs (no external assets)
├── application_screenshots/ # Reference screenshots
├── data/                    # Runtime state (gitignored): documents.db, lancedb/, logs/
├── models/                  # GGUF weights (gitignored)
├── tools/llama-server/      # Native llama-server binaries (gitignored)
├── .cache/                  # Legacy cache directory (gitignored)
├── .streamlit/config.toml   # Dark theme, loopback bind, upload cap, CORS/XSRF
├── .github/workflows/ci.yml # Ruff + corpus generation + pytest on Python 3.11
├── pyproject.toml           # Ruff and pytest configuration
├── requirements.txt         # Runtime dependencies
├── requirements-lock.txt    # uv-compiled universal lockfile
├── requirements-test.txt    # Test-only dependencies
├── Dockerfile               # python:3.11-slim-bookworm runtime image
├── docker-compose.yml       # App + optional CUDA llama-server profile
├── CLAUDE.md                # Project context and stack/convention summaries
├── README.md                # Product overview and setup instructions
└── LICENSE                  # MIT
```

## Directory Purposes

**`core/`:**
- Purpose: Provider-independent domain logic and durable metadata.
- Contains: Pydantic schemas, SQLite store, `AiModel`, `InferenceGate`, `Summarizer`, query intent, prompt budgeting, citation validation, GGUF identity, telemetry, logging.
- Key files: `core/local_llm.py`, `core/doc_store.py`, `core/models.py`, `core/query_intent.py`, `core/citation_validator.py`.

**`ui/`:**
- Purpose: All Streamlit rendering plus the orchestration services that perform multi-tier side effects.
- Contains: four view renderers, reusable components/theme/sanitizer, session reset, ingestion/lifecycle/hydration services.
- Key files: `ui/views.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`.

**`ingestion/`:**
- Purpose: Transform untrusted PDF bytes into validated, page-attributed text/chunk/evidence records.
- Contains: upload validation, Docling reader, pypdf fallback, OCR engine, visual analyzer.
- Key files: `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`.

**`retrieval/`:**
- Purpose: Embeddings, persistent hybrid index, fallback mirror, whole-document reads.
- Contains: `LocalEmbedding`, `HybridRetriever`, pure-Python `VectorIndex`.
- Key files: `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `retrieval/vector_index.py`.

**`providers/`:**
- Purpose: Normalize local and cloud inference behind one contract.
- Contains: provider ABC/schemas and three adapters.
- Key files: `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`.

**`tests/`:**
- Purpose: Offline unit/integration coverage with mocked GPU and network boundaries.
- Contains: `conftest.py`, per-module suites, synthetic corpus PDFs and generator.
- Key files: `tests/conftest.py`, `tests/test_hybrid_retriever.py`, `tests/test_whole_document_extraction.py`, `tests/test_concurrency_lock.py`, `tests/data/corpus/generate_corpus.py`.

**`scripts/`:**
- Purpose: Developer/benchmark utilities outside the app runtime.
- Contains: `profile_resources.py`, `benchmark_baseline.py`, `benchmark_multimodal.py`, `generate_icons.py`.

**`docs/`:**
- Purpose: Operational and audit documentation.
- Contains: `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`, `AUDIT_SUMMARY.md`, `FILE_CALLER_TEST_MAP.md`, traceability and test-result reports.

**`assets/icons/`:**
- Purpose: Local SVG iconography for the AMOLED UI.
- Contains: monochrome icons consumed by `ui/components.py:14`.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit composition root, session defaults, hydration, provider sync, workspace routing.
- `start.py`: `main()` launcher; `--start-llama`, `--host`, `--port`, `--ctx`, `--ngl`.
- `setup.py`: `main_cli()`, `download_models_cli()`, `setup_llama_server_cli()`; setuptools commands `download_models`, `setup_llama_server`.
- `ui/views.py`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`) and pytest (`testpaths = ["tests"]`).
- `.streamlit/config.toml`: dark theme, `address = "127.0.0.1"`, `maxUploadSize = 50`, CORS/XSRF, telemetry off.
- `requirements.txt`, `requirements-lock.txt`, `requirements-test.txt`: dependency pins.
- `Dockerfile`, `docker-compose.yml`: container runtime and optional CUDA llama-server profile.
- `.github/workflows/ci.yml`: Ruff check/format, corpus generation, pytest.
- `.gitignore`: excludes `.env*`, `data/`, `.cache/`, `models/`, `tools/`, binaries, logs.

**Core Logic:**
- `core/local_llm.py`: `InferenceGate` and `AiModel`.
- `core/doc_store.py`: SQLite source of truth and migrations.
- `core/query_intent.py`: shared retrieval intent/whole-document extraction.
- `core/summarizer.py`: summary profiles and map-reduce.
- `retrieval/hybrid_retriever.py`: dense/FTS/RRF, mirror, scoped search, `fts_status()`.
- `ui/ingestion_service.py`: ingestion transaction.
- `ui/lifecycle_service.py`: delete/purge/re-index ordering.
- `setup.py`: checksum-pinned downloads and safe extraction.

**Testing:**
- `tests/conftest.py`: mocked provider, SentenceTransformer, Groq client, corpus path.
- `tests/data/corpus/generate_corpus.py`: reportlab-generated PDF corpus.
- Per-module suites: `tests/test_local_llm.py`, `tests/test_hybrid_retriever.py`, `tests/test_summarizer.py`, `tests/test_doc_store.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_setup_checksums.py`.

**Persistence / Runtime State:**
- `data/documents.db`: SQLite catalog (runtime, gitignored).
- `data/lancedb/chunks.lance`: LanceDB table directory.
- `data/lancedb/fallback_store.json`: durable fallback mirror.
- `data/lancedb_bench/`: benchmark index output.
- `data/logs/app.log`: rotating application log.
- `models/qwen3-vl-2b-instruct-q4_k_m.gguf` and `models/mmproj-f16.gguf`: local VLM pair (legacy filenames verified by GGUF metadata).
- `tools/llama-server/llama-server.exe`: native server binary.

## Naming Conventions

**Files:**
- `snake_case.py` by responsibility: `hybrid_retriever.py`, `citation_validator.py`, `lifecycle_service.py`.
- Tests: `tests/test_<module_or_feature>.py`.
- No `__main__` entry in library modules; root scripts `main.py`, `start.py`, `setup.py` are the exceptions.
- Package `__init__.py` files carry a one-line docstring and `__version__` (except `ui`, which exports `sanitize_markdown_for_local`).

**Directories:**
- Lowercase, single-word responsibility groups: `core`, `ui`, `ingestion`, `retrieval`, `providers`, `tests`, `scripts`, `docs`, `assets`.

**Classes:**
- `PascalCase`, noun-oriented: `AiModel`, `InferenceGate`, `HybridRetriever`, `DocStore`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`, `Summarizer`.
- Pydantic models are nouns: `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`.
- Dataclasses for internal results: `IngestionResult`, `ValidatedUpload`, `ModelIdentity`, `LatencyTracker`.

**Functions / methods:**
- `snake_case`, verb-first: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `resolve_retrieval`, `fetch_document_chunks`, `assemble_grounded_messages`.
- UI renderers are `render_<area>` and return `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`.
- Private helpers are `_leading_underscore`: `_mirror_upsert`, `_load_fallback_store`, `_doc_filter_clause`, `_bounded_zoom`, `_lifecycle_preflight`.
- Booleans read as predicates: `is_whole_document_query`, `should_ocr_page`, `has_document`, `is_persistent`, `fts_status`.

**Constants:**
- `UPPER_SNAKE_CASE`: `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `MAX_FILE_MB`, `MAX_PAGES`, `MAX_OCR_PAGES_PER_DOC`, `FAST_PATH_TOKEN_LIMIT`, `CONFIG_VERSION`, `SCHEMA_V1_DDL`.
- Env-var names are string constants or inline lookups: `RAG_LOG_LEVEL`, `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`, `LLAMA_SERVER_URL`.

**Session state keys:**
- Public state keys are plain: `doc_ids`, `chat_history`, `hybrid_retriever`, `active_workspace`.
- Internal/transient keys are underscore-prefixed: `_startup_hydrated`, `_health_snapshot`, `_health_probe_ts`, `_cached_cloud_model`, `_cached_cloud_key`, `_queued_prompt`, `_show_consent_dialog`.
- Summary cache keys: `summary_<doc_id>_<profile>_<model_version>` (`ui/views.py:39`).
- Per-widget uploader keys: `pdf_uploader_<suffix>_<counter>`, `uploader_key_<suffix>`.

**Identifiers:**
- Documents: `doc_<sha16>` (`ingestion/upload_validation.py:90`).
- Visual elements: `elem_<doc_id>_p<page>_<kind>_<index>` (`ingestion/visual_analyzer.py:273`).
- Summaries: `summ_<uuid16>` (`core/summarizer.py:576`).

## Where to Add New Code

**New feature (UI-facing):**
- Primary code: add a `render_<name>_view` in `ui/views.py` and register it in the workspace router in `main.py:383` / `main.py:443`.
- Session defaults: add keys to the initialization list in `main.py:101`.
- Reusable widgets: `ui/components.py`; styling tokens: `ui/theme.py`.
- Tests: `tests/test_main_ui.py` or a new `tests/test_<feature>.py`.

**New inference provider:**
- Implementation: `providers/<name>_provider.py`, subclass `BaseModelProvider` from `providers/model_provider.py`.
- Contract: implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`; set `ProviderCapabilities.is_local` accurately.
- Wiring: `AiModel._detect_provider` / `set_cloud_mode` in `core/local_llm.py:178`; cloud adapters must accept `user_consented` and assert it before transmission.
- Tests: add to `tests/test_model_provider.py` and a provider-specific suite; keep network mocked.

**New ingestion source or extractor:**
- Implementation: `ingestion/<name>_reader.py`, returning `list[dict]` chunks and `list[Page]` records compatible with `core/models.py`.
- Wiring: `IngestionService.ingest_pdf` extraction stage (`ui/ingestion_service.py:141`); preserve the Docling → pypdf fallback chain.
- Validation/caps: reuse `ingestion/upload_validation.py`; do not add unbounded rasterization (`ingestion/ocr_fallback.py:38` shows the bounded-zoom pattern).

**New retrieval backend or ranking stage:**
- Implementation: extend `retrieval/hybrid_retriever.py` (`search_dense`, `search_fts`, `search_hybrid`, `compute_rrf`) rather than bypassing it.
- Fallback parity: any new write path must also update the durable mirror (`_mirror_upsert`, `_mirror_delete_document`) or explicitly document why not.
- Scoped search: push `doc_id` filters into the backend before limits and keep the defense-in-depth filter (`retrieval/hybrid_retriever.py:1000`).
- Tests: `tests/test_hybrid_retriever.py`; include a LanceDB-unavailable path.

**New domain rule (intent, budgeting, citations):**
- Intent / whole-document logic: `core/query_intent.py` (shared by UI and `AiModel`).
- Token budgeting / XML isolation: `core/prompt_budget.py`.
- Citation/support/abstention: `core/citation_validator.py`.
- Keep provider-agnostic code free of `streamlit` imports.

**New lifecycle operation:**
- Implementation: add a method to `ui/lifecycle_service.py` and a preflight-gated wrapper in `ui/views.py` (`_delete_document`, `_reindex_document`, `_purge_all` are the patterns).
- Ordering rule: vectors first, then SQLite, then legacy cache, then session state.

**New background/CPU work:**
- Prefer CPU-bound preprocessing in `ingestion/` or `retrieval/`; do not acquire `InferenceGate` for CPU work.
- Any GPU model call must use `InferenceGate.hold(...)` or go through `AiModel`.

**Utilities:**
- Shared helpers: `core/` if domain-related; `ui/components.py` if presentation-only; avoid a catch-all `utils.py`.
- Cross-cutting logging: `core/logging_setup.py`.

**Tests:**
- Add `tests/test_<module>.py`; use fixtures from `tests/conftest.py` (`mock_llama_provider`, `mock_sentence_transformer`, `mock_groq_client`, `sample_pdf_path`).
- Keep tests offline: no live llama-server, GPU, or network calls.
- For PDF fixtures, extend `tests/data/corpus/generate_corpus.py` rather than committing new binaries.

## Special Directories

**`data/`:**
- Purpose: Runtime persistence: `documents.db`, `lancedb/`, `lancedb_bench/`, `logs/`.
- Generated: Yes.
- Committed: No (`.gitignore` excludes `data/`).

**`.cache/`:**
- Purpose: Legacy extraction-cache root. Ingestion does not write here; lifecycle and Settings remove legacy directories.
- Generated: Historically; retained for cleanup compatibility.
- Committed: No.

**`models/`:**
- Purpose: GGUF language model and multimodal projector weights.
- Generated: No (downloaded by `setup.py download_models`).
- Committed: No (`.gitignore` excludes `models/`, `*.gguf`).

**`tools/llama-server/`:**
- Purpose: Native llama-server binaries and CUDA runtime DLLs.
- Generated: No (downloaded/extracted by `setup.py setup_llama_server`).
- Committed: No (`.gitignore` excludes `tools/`).

**`retrieval/data/lancedb/`:**
- Purpose: Legacy package-relative LanceDB location. `_migrate_legacy_index` copies it to `data/lancedb` on first default-URI use and leaves the source intact.
- Generated: Legacy runtime artifact.
- Committed: No.

**`tests/data/corpus/`:**
- Purpose: Synthetic PDFs for extraction/OCR/retrieval tests.
- Generated: Yes, by `tests/data/corpus/generate_corpus.py` (CI generates before pytest).
- Committed: Corpus PDFs are present in the working tree; the generator is the source of truth.

**`.planning/`:**
- Purpose: GSD planning artifacts, codebase maps, debug sessions, phases, research.
- Generated: Yes, by planning commands.
- Committed: Selectively; debug scripts are gitignored (`*.py` under `.planning/debug/`).

**`assets/icons/`:**
- Purpose: Local SVG icon set used by `ui/components.py`.
- Generated: `scripts/generate_icons.py` can regenerate them.
- Committed: Yes.

**`application_screenshots/`:**
- Purpose: UI reference captures.
- Generated: Yes.
- Committed: Yes.

---

*Structure analysis: 2026-10-22*
