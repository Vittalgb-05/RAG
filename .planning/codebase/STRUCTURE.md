<!-- refreshed: 2026-10-28 -->
# Codebase Structure

**Analysis Date:** 2026-10-28

## Directory Layout

```
RAG/
├── main.py                     # Streamlit composition root: config, hydration, routing
├── start.py                    # One-command launcher: pre-flight, llama-server, Streamlit
├── setup.py                    # setuptools packaging + model/server setup CLI
│
├── core/                       # Domain layer: schemas, storage, LLM facade, budgeting
│   ├── __init__.py             # __version__ only
│   ├── models.py               # Pydantic schemas + cache_dir_for + CONFIG_VERSION
│   ├── doc_store.py            # SQLite persistence, migrations, transactions
│   ├── local_llm.py            # AiModel facade + InferenceGate
│   ├── summarizer.py           # 5-profile single-pass / map-reduce summarizer
│   ├── citation_validator.py   # [E#] precision, abstention, injection detection
│   ├── prompt_budget.py        # Token budgeting, XML isolation, history bounding
│   ├── query_intent.py         # Follow-up contextualization + retrieval resolution
│   ├── resource_telemetry.py   # GPU/RAM telemetry, latency tracking
│   ├── logging_setup.py        # Idempotent logging configuration
│   ├── model_identity.py       # GGUF metadata parsing/verification
│   └── redaction.py            # Secret scrubbing for errors/logs
│
├── ingestion/                  # PDF -> validated chunks + visual evidence
│   ├── upload_validation.py    # %PDF, size/page caps, SHA identity, scanned pre-flight
│   ├── docling_reader.py       # Primary layout/table extractor
│   ├── pdf_reader.py           # pypdf fallback extractor
│   ├── ocr_fallback.py         # Conditional RapidOCR, CPU-only, page/time caps
│   └── visual_analyzer.py      # PyMuPDF region detection + VLM descriptions
│
├── retrieval/                  # Embeddings + vector/FTS retrieval
│   ├── local_embedding.py      # MiniLM CPU embeddings, shared model cache
│   ├── hybrid_retriever.py     # LanceDB dense + FTS + RRF + JSON mirror
│   ├── vector_index.py         # Pure-stdlib cosine/euclidean/dot index
│   └── data/lancedb/           # Pre-0.2 legacy index (migration source; gitignored)
│
├── providers/                  # Inference adapters
│   ├── model_provider.py       # BaseModelProvider ABC + capability/health models
│   ├── llama_cpp_provider.py   # Local llama-server HTTP/SSE client
│   ├── litellm_provider.py     # Cloud adapter (Groq/OpenAI/Anthropic) + consent
│   └── groq_provider.py        # Direct Groq SDK adapter
│
├── ui/                         # Streamlit presentation + UI orchestration
│   ├── views.py                # 5 workspaces (Chat/Summarizer/Library/Settings/Diagnostics)
│   ├── chat_controller.py      # Streamlit-free chat turn service
│   ├── ingestion_service.py    # End-to-end ingest orchestration
│   ├── lifecycle_service.py    # Delete / purge / re-index orchestration
│   ├── hydration.py            # Startup catalog + vector repair
│   ├── session_state.py        # Central in-memory session reset
│   ├── components.py           # SVG icons, status pills, citation pills, stat cards
│   ├── theme.py                # AMOLED CSS injection
│   └── sanitizer.py            # Markdown/HTML egress sanitizer
│
├── tests/                      # pytest suite (37 modules)
│   ├── conftest.py             # Offline fixtures: mock providers, embeddings, corpus
│   └── data/corpus/            # Generated PDF fixtures + generator
│
├── scripts/                    # Operational tooling
│   ├── benchmark_multimodal.py # Multimodal evaluation harness (--live)
│   ├── benchmark_baseline.py   # Retrieval baseline harness
│   ├── profile_resources.py    # VRAM/RAM + InferenceGate profiling
│   └── generate_icons.py       # Regenerates assets/icons/*.svg
│
├── docs/                       # Operational and audit documentation
│   ├── RUNBOOK.md
│   ├── LOCAL_INFERENCE.md
│   ├── EVALUATION.md
│   ├── ENDPOINT_INTEGRATION_MATRIX.md
│   ├── FILE_CALLER_TEST_MAP.md
│   ├── REQUIREMENTS_TRACEABILITY.md
│   ├── AUDIT_SUMMARY.md
│   ├── CODE_QUALITY_REPORT.md
│   ├── REPAIR_LOG.md
│   ├── TEST_RESULTS.md
│   └── LICENSES.md
│
├── assets/
│   ├── brand_mark.svg
│   └── icons/*.svg             # 22 monochrome icons, cached at runtime
│
├── .streamlit/config.toml      # Dark theme, 127.0.0.1 bind, 50 MB upload cap
├── .github/workflows/ci.yml    # Ruff + corpus generation + pytest on Python 3.11
├── .devcontainer/devcontainer.json
├── Dockerfile                  # python:3.11-slim-bookworm image
├── docker-compose.yml          # app + optional CUDA llama-server profile
├── pyproject.toml              # Ruff + pytest configuration
├── requirements.txt            # Runtime dependencies
├── requirements-lock.txt       # uv-compiled universal lockfile (3.11)
├── requirements-test.txt       # Test/benchmark dependencies
├── CLAUDE.md                   # GSD project context (generated sections)
├── README.md
├── LICENSE                     # MIT
│
├── .planning/                  # GSD planning artifacts (not shipped)
├── application_screenshots/    # Reference screenshots
│
├── models/                     # GITIGNORED: GGUF weights + mmproj projector
├── tools/llama-server/         # GITIGNORED: llama-server binaries + CUDA DLLs
├── data/                       # GITIGNORED: documents.db, lancedb/, logs/, lancedb_bench/
├── .cache/                     # GITIGNORED: <sha256>/<CONFIG_VERSION>/ extraction cache
├── rag_assistant.egg-info/     # Generated by pip install -e .
└── __pycache__/                # Generated
```

## Directory Purposes

**`core/`:**
- Purpose: Model-independent domain logic and the system of record.
- Contains: Frozen Pydantic schemas, SQLite persistence, provider routing, prompt budgeting, citation verification, summarization, telemetry, logging, redaction, GGUF identity.
- Key files: `core/models.py`, `core/doc_store.py`, `core/local_llm.py`, `core/summarizer.py`, `core/citation_validator.py`, `core/prompt_budget.py`, `core/query_intent.py`.
- Rule: No Streamlit imports. No PDF parsing. No embedding model loading.

**`ingestion/`:**
- Purpose: Convert untrusted PDF bytes into validated text chunks, page records, and visual evidence.
- Contains: Upload validation, Docling primary extractor, pypdf fallback, conditional OCR, VLM region analysis.
- Key files: `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`.
- Rule: Depends only on `core/models.py` (plus a lazy `InferenceGate` import in the visual analyzer). No Streamlit, no DocStore, no retriever writes.

**`retrieval/`:**
- Purpose: Embedding generation, vector persistence, lexical search, and rank fusion.
- Contains: `HybridRetriever` (LanceDB primary + JSON mirror + in-memory fallback), `LocalEmbedding`, `VectorIndex`, `compute_rrf`.
- Key files: `retrieval/hybrid_retriever.py` (1,092 lines), `retrieval/local_embedding.py`, `retrieval/vector_index.py`.
- Rule: Returns canonical `RetrievalResult`; do not invent alternate result shapes.

**`providers/`:**
- Purpose: Uniform inference contract for local and cloud backends.
- Contains: `BaseModelProvider` ABC, `ProviderCapabilities`, `HealthStatus`, three adapters.
- Key files: `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`.
- Rule: Cloud adapters must gate every generation/vision call on `user_consented`.

**`ui/`:**
- Purpose: Streamlit rendering plus orchestration that would otherwise entangle views with persistence.
- Contains: Five workspace renderers, chat turn service, ingestion/lifecycle services, hydration, session reset, components, theme, sanitizer.
- Key files: `ui/views.py` (1,225 lines, the largest module), `ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`.
- Rule: Prefer `render_*` functions returning `None`; put decisions in a service and keep Streamlit calls at the edge.

**`tests/`:**
- Purpose: Fully offline verification (no GPU, no network, no API calls).
- Contains: 37 `test_*.py` modules, shared fixtures in `tests/conftest.py`, synthetic PDF corpus in `tests/data/corpus/`.
- Key files: `tests/conftest.py`, `tests/test_concurrency_lock.py`, `tests/test_hybrid_retriever.py`, `tests/test_main_ui.py`, `tests/data/corpus/generate_corpus.py`.

**`scripts/`:**
- Purpose: Benchmarks and hardware profiling outside the application runtime.
- Contains: Multimodal eval (`--live`), retrieval baseline, resource profiler, icon generator.
- Key files: `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`.

**`docs/`:**
- Purpose: Operator runbook, inference tuning, evaluation results, and audit trail.
- Contains: `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`, integration/caller maps, repair log, test results.
- Key files: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/ENDPOINT_INTEGRATION_MATRIX.md`.

**`assets/`:**
- Purpose: Local-only visual identity (no CDN, no external fonts).
- Contains: `brand_mark.svg` and 22 monochrome icons loaded and cached by `ui/components.py`.
- Key files: `assets/brand_mark.svg`, `assets/icons/*.svg`.

**`.streamlit/`:**
- Purpose: Streamlit runtime configuration.
- Contains: Dark AMOLED theme colors, loopback bind, CORS/XSRF, 50 MB upload cap, usage-stats disabled.
- Key files: `.streamlit/config.toml`.

**`.github/workflows/`:**
- Purpose: CI gate.
- Contains: Ruff check + format check, corpus generation, pytest on Python 3.11 with uv.
- Key files: `.github/workflows/ci.yml`.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit composition root and workspace router (`main.py:509-538`).
- `start.py`: Launcher CLI, loopback policy, llama-server lifecycle (`start.py:283`).
- `setup.py`: Packaging metadata, console scripts, model/server install commands (`setup.py:804-844`).
- `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`: operational entry points.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`) and pytest settings.
- `requirements.txt` / `requirements-lock.txt` / `requirements-test.txt`: dependency inputs and lockfile.
- `.streamlit/config.toml`: theme + server security defaults.
- `Dockerfile`, `docker-compose.yml`: container topology.
- `.env.example`: documents expected environment variable **names** (no values are read by this analysis).
- `main.py:43-46`: runtime paths — `data/documents.db`, `data/logs/`, `.cache/`.
- `retrieval/hybrid_retriever.py:70`: `DEFAULT_DB_URI = <repo>/data/lancedb`.

**Core Logic:**
- `core/models.py`: canonical schemas; `CONFIG_VERSION` at line 14; `cache_dir_for` at line 17.
- `core/doc_store.py`: schema DDL v1–v5 (`:44-147`), migration runner (`:230-242`), `record_ingestion` (`:363`), `get_summary` (`:715`), `purge_all` (`:893`).
- `core/local_llm.py`: `InferenceGate` (`:26`), `AiModel` (`:103`), streaming (`:247`).
- `core/summarizer.py`: profile prompts (`:44-123`), map-reduce (`:411`), `summarize_document` (`:465`).
- `core/prompt_budget.py`: `DEFAULT_MAX_OUTPUT_TOKENS` (`:17`), `assemble_grounded_messages` (`:75`).
- `core/query_intent.py`: `resolve_retrieval` (`:227`), `select_page_diverse_snippets` (`:147`).
- `core/citation_validator.py`: `CitationVerificationResult` (`:134`), `validate_citations` (`:306`), `auto_attribute_citations` (`:431`).
- `retrieval/hybrid_retriever.py`: `compute_rrf` (`:121`), `index_chunks` (`:452`), `fetch_document_chunks` (`:641`), `search_hybrid` (`:959`).
- `ingestion/upload_validation.py`: `validate_pdf_bytes` (`:120`); limits at `:18-19`.
- `ingestion/docling_reader.py`: `DoclingReader` (`:37`), chunking at `:261-263`.

**UI / Presentation:**
- `ui/views.py`: `render_chat_view` (`:489`), `render_summarizer_view` (`:806`), `render_library_view` (`:936`), `render_settings_view` (`:1058`), `render_sidebar_documents` (`:414`).
- `ui/chat_controller.py`: `ChatTurnService` (`:73`), `prepare` (`:80`), `finalize` (`:130`).
- `ui/ingestion_service.py`: `IngestionService.ingest_pdf` (`:54`).
- `ui/lifecycle_service.py`: `delete_document` (`:32`), `purge_all` (`:104`), `reindex_document` (`:162`).
- `ui/hydration.py`: `hydrate_startup_state` (`:83`).
- `ui/components.py`: `get_svg_icon` (`:14`), `render_status_pill` (`:86`), `render_chatgpt_citation_pill` (`:144`).
- `ui/theme.py`: `inject_custom_theme` (`:323`).
- `ui/sanitizer.py`: `sanitize_markdown_for_local` (`:130`), alias `sanitize_display_markdown` (`:249`).

**Testing:**
- `tests/conftest.py`: `mock_llama_provider`, `mock_sentence_transformer`, `sample_pdf_path`.
- `tests/data/corpus/`: `clean_digital.pdf`, `scanned_sample.pdf`, `dense_table.pdf`, `chart_diagram.pdf`, `multi_column.pdf`, `corrupt_invalid.pdf`.
- `tests/data/corpus/generate_corpus.py`: regenerates fixtures (run in CI before pytest).

## Naming Conventions

**Files:**
- `snake_case.py` everywhere; module name describes capability, not class: `upload_validation.py`, `citation_validator.py`, `resource_telemetry.py`, `prompt_budget.py`.
- Providers are `<vendor>_provider.py` (`llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`).
- Root-level executable scripts are short verbs/nouns: `main.py`, `start.py`, `setup.py`.
- Tests are `test_<feature_or_module>.py`; benchmark/profile scripts are verb-first (`benchmark_multimodal.py`, `profile_resources.py`).

**Directories:**
- Single lowercase noun, no plurals: `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`.
- Dot-prefixed tooling config: `.streamlit/`, `.github/`, `.devcontainer/`, `.planning/`.

**Classes:**
- `PascalCase` with role suffix: `DocStore`, `IngestionService`, `LifecycleService`, `ChatTurnService`, `BaseModelProvider`, `LlamaCppProvider`, `DoclingReader`, `VisualAnalyzer`, `HybridRetriever`, `LocalEmbedding`, `VectorIndex`, `InferenceGate`.
- Result/transport objects end in `Result`/`Preparation`/`Status`/`Capabilities`: `IngestionResult`, `ChatTurnResult`, `ChatTurnPreparation`, `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`, `HealthStatus`, `ProviderCapabilities`.
- Frozen dataclasses only for internal UI transport (`@dataclass(frozen=True)` in `ui/chat_controller.py`); everything crossing a persistence/API boundary is Pydantic.

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `resolve_retrieval`, `assemble_grounded_messages`.
- UI renderers are `render_<area>` and return `None`: `render_chat_view`, `render_library_view`, `render_sidebar_documents`, `render_status_pill` (this one returns an HTML string).
- Predicates/queries: `is_*`, `has_*`, `should_*`, `get_*`, `check_*`, `detect_*`.
- Private helpers are `_`-prefixed (`_execute_write`, `_doc_filter_clause`, `_merge_evidence_into_pages`).
- Public helpers that return HTML are named `get_*_svg` or `render_*` and return `str`.

**Variables / Constants:**
- `snake_case` locals and Pydantic fields; `UPPER_SNAKE_CASE` module constants (`MAX_FILE_MB`, `MAX_PAGES`, `MAX_CHAT_TURNS`, `DEFAULT_MAX_OUTPUT_TOKENS`, `CONFIG_VERSION`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`).
- Pydantic discriminated fields use `Literal[...]` unions: `Page.status`, `Document.status`, `EvidenceElement.kind`, `SummaryProfile`, `RetrievalResult.search_mode`.

**Session-state keys:**
- `snake_case` domain keys: `doc_ids`, `document_metadata`, `chat_history`, `cloud_mode`, `user_consented`, `uploader_key`, `active_workspace`.
- Transient/internal UI flags are `_`-prefixed: `_startup_hydrated`, `_health_snapshot`, `_health_probe_ts`, `_show_consent_dialog`, `_show_settings_dialog`, `_queued_prompt`, `_cached_cloud_model`, `_cached_cloud_key`.
- Widget keys are namespaced by area: `sidebar_new_conversation`, `lib_del_<doc_id>`, `del_sidebar_<doc_id>`, `pdf_uploader_<suffix>_<n>`, `summary_<doc_id>_<profile>_<model_version>`.

**Identifiers:**
- Document: `doc_<sha256[:16]>` (`ingestion/upload_validation.py:90`).
- Chunk: `<sha256[:12]>_p<page>_<0000>` (`ingestion/pdf_reader.py:97`, `ingestion/docling_reader.py:339`).
- Evidence element: `elem_<doc_id>_p<page>_<kind>_<idx:02d>` (`ingestion/visual_analyzer.py:273`).
- Summary: `summ_<uuid4hex[:16]>` (`core/summarizer.py:576`).

## Where to Add New Code

**New workspace / top-level page:**
- Add the label to `WORKSPACES` in `main.py:57` (and an alias in `WORKSPACE_ALIASES` if needed).
- Implement `render_<name>_view(...)` in `ui/views.py` following the existing signature style (keyword-style args, no return value).
- Route it in `main.py:509-538`; keep the sidebar radio order in sync.
- If it has decision logic, put it in a new Streamlit-free service under `ui/` (model: `ui/chat_controller.py`).

**New ingestion extractor / parser:**
- Create `ingestion/<name>_reader.py` exposing `extract_text(doc_id, sha12)`, `get_paragraphs()`, `get_page_records()`, and a `fallback_used` flag (match `ingestion/docling_reader.py`).
- Wire it into the extraction chain in `ui/ingestion_service.py:141-173`; keep Docling first and the pypdf fallback last.
- Reuse `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` and the `<sha12>_p<page>_<idx>` chunk-id format.
- Add `tests/test_<name>_reader.py` using `tests/data/corpus/`.

**New inference provider:**
- Create `providers/<vendor>_provider.py` subclassing `BaseModelProvider` (`providers/model_provider.py:64`); implement all five abstract methods.
- For cloud providers, accept `user_consented: bool` and call `_assert_consent()` before every generation/vision call; resolve keys via an explicit `api_key` parameter (do **not** import Streamlit).
- Register it in `core/local_llm.py:_detect_provider` (`:208-224`) and/or the cloud sync block in `main.py:224-252`; add a `PROVIDER_CONFIG` entry in `ui/views.py:1124-1128` for the settings dropdown.
- Add `tests/test_<vendor>_provider.py` with `httpx.MockTransport` or SDK mocks, mirroring `tests/test_litellm_provider.py`.

**New retrieval capability (e.g. reranker):**
- Add the implementation under `retrieval/` and return a canonical `RetrievalResult`.
- If it introduces a new mode, extend the `search_mode` `Literal` in `core/models.py:181-190` and handle it in `core/query_intent.resolve_retrieval` and `ui/views.py` rendering.
- Preserve the invariant that snippet `rank` values are contiguous from 1 — citation validation depends on it.

**New persisted field / table:**
- Append a `SCHEMA_V6_DDL` list in `core/doc_store.py` and register it in `MIGRATIONS` (currently v1–v5 at `:141-147`); never edit an existing migration.
- Add the field to the relevant Pydantic model in `core/models.py`.
- Update the mapper in the corresponding `record_*` / `get_*` method (`record_ingestion` at `core/doc_store.py:363`, `get_chunks_for_doc` at `:584`, etc.).
- If it affects summary validity, bump `CONFIG_VERSION` (`core/models.py:14`) so cache keys invalidate.

**New domain rule / validator:**
- Add a module under `core/` with pure functions and a frozen result model; no Streamlit, no network.
- Call it from `ui/chat_controller.py` (chat) or `ui/ingestion_service.py` (ingestion) rather than from `ui/views.py`.
- Add a focused test in `tests/test_<rule>.py`; follow `tests/test_citation_validator.py` for table-driven cases.

**New UI component:**
- Add a `render_<component>` (returns `None`) or `get_<asset>` (returns `str`) to `ui/components.py`.
- Reuse `get_svg_icon("<name>")`; add the SVG to `assets/icons/` (or regenerate with `scripts/generate_icons.py`).
- Sanitize any model- or document-derived markdown with `sanitize_display_markdown` before rendering.

**New lifecycle operation:**
- Add the method to `ui/lifecycle_service.py` with explicit tier ordering (vectors → SQLite → cache → session) and failure semantics.
- Add a thin view helper with `_lifecycle_preflight` (`ui/views.py:147`) so the UI refuses to mutate SQLite without a retriever.
- Cover failure ordering in `tests/test_doc_store.py` / a new `tests/test_lifecycle_service.py`.

**New configuration / environment variable:**
- Runtime knobs: add an `argparse` flag in `start.py:285-310` and/or read `RAG_*`-prefixed env vars (`RAG_LOG_LEVEL`, `RAG_LOG_DIR`, `RAG_ALLOW_NON_LOOPBACK` are existing precedents).
- Provider endpoints: `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT` are read in `providers/llama_cpp_provider.py:76-83`.
- Document new variable **names** in `.env.example` and `README.md`; never commit values.

**New tests:**
- Place at `tests/test_<area>.py`; pytest is configured in `pyproject.toml:21-30` with `testpaths = ["tests"]`.
- Add reusable fakes to `tests/conftest.py` (existing: `mock_llama_provider`, `mock_sentence_transformer`, `mock_groq_client`).
- Keep tests offline: no real llama-server, no network, no GPU. Use `httpx.MockTransport` or injected fakes.
- Regenerate PDF fixtures with `python tests/data/corpus/generate_corpus.py` when corpus shape changes.

## Special Directories

**`data/`:**
- Purpose: Runtime persistence — `documents.db` (SQLite WAL), `lancedb/chunks.lance`, `lancedb/fallback_store.json`, `logs/`, `lancedb_bench/`.
- Generated: Yes.
- Committed: No (`.gitignore:26-36`).

**`.cache/`:**
- Purpose: Content-addressed extraction cache at `.cache/<sha256>/<CONFIG_VERSION>/` (`cache_dir_for`, `core/models.py:17`).
- Generated: Yes.
- Committed: No.

**`models/`:**
- Purpose: `qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16.gguf` (legacy filenames; GGUF metadata is authoritative and verified by `core/model_identity.py`).
- Generated: Downloaded via `python setup.py download_models`.
- Committed: No.

**`tools/llama-server/`:**
- Purpose: Windows llama.cpp binaries and CUDA runtime DLLs used when `llama-server` is not on `PATH`.
- Generated: Downloaded via `python setup.py setup_llama_server`.
- Committed: No.

**`retrieval/data/lancedb/`:**
- Purpose: Pre-0.2 legacy index location (`LEGACY_DB_URI`, `retrieval/hybrid_retriever.py:71`). `_migrate_legacy_index` copies it non-destructively into `<repo>/data/lancedb` when the canonical target has no `*.lance` data (`retrieval/hybrid_retriever.py:84-118`). The source is intentionally left in place.
- Generated: Yes (legacy).
- Committed: No.

**`.planning/`:**
- Purpose: GSD workflow state, phase plans, research, and this codebase map.
- Generated: By GSD commands.
- Committed: Yes (except `.planning/debug/*.py`, `.gitignore:63`).

**`rag_assistant.egg-info/` and `__pycache__/`:**
- Purpose: Packaging metadata and bytecode.
- Generated: Yes.
- Committed: No.

**`application_screenshots/`:**
- Purpose: Reference UI captures used in documentation.
- Generated: Manually captured.
- Committed: Yes.

**`.devcontainer/`:**
- Purpose: GitHub Codespaces / VS Code dev container (Python 3.11 base image, forwards port 8501).
- Generated: No.
- Committed: Yes.

---

*Structure analysis: 2026-10-28*
