# Codebase Structure

**Analysis Date:** 2026-10-20

## Directory Layout

```text
RAG/
├── main.py                     # Streamlit app shell: page config, session state, hydration, routing
├── start.py                    # Recommended launcher: pre-flight, optional llama-server, Streamlit
├── setup.py                    # Setuptools metadata + installer CLI + model/llama-server downloaders
│
├── ui/                         # Streamlit presentation package (imported by main.py)
│   ├── __init__.py             # Re-exports sanitize_markdown_for_local only
│   ├── views.py                # Sidebar uploader + Chat/Summarizer/Library/Settings renderers
│   ├── ingestion_service.py    # End-to-end PDF ingestion orchestrator (~300 lines)
│   ├── components.py           # Brand header, pills, stat cards, empty states, citation chips
│   ├── theme.py                # AMOLED tokens + injected CSS
│   ├── sanitizer.py            # Script/external-image stripping for rendered text
│   └── hydration.py            # Restore docs + retriever from SQLite/LanceDB per session
│
├── model_provider.py           # BaseModelProvider ABC + ProviderCapabilities/HealthStatus
├── llama_cpp_provider.py       # Local llama-server HTTP/SSE provider (loopback guard)
├── litellm_provider.py         # Cloud provider via LiteLLM (Groq/OpenAI/Anthropic, consent gate)
├── groq_provider.py            # Legacy direct Groq SDK provider
├── local_llm.py                # AiModel facade + InferenceGate + citation verification
├── summarizer.py               # 5-profile single-pass / map-reduce summarizer
├── citation_validator.py       # [E#] precision gate, abstention + injection detection
├── prompt_budget.py            # Token estimation, <document_context> framing, truncation
│
├── doc_store.py                # SQLite WAL store, schema v1–v3 migrations, CRUD
├── hybrid_retriever.py         # LanceDB dense + FTS/BM25 + RRF, JSON fallback store
├── local_embedding.py          # Shared MiniLM (CPU) embedding provider
├── vector_index.py             # Pure-stdlib in-memory cosine/euclidean index
│
├── docling_reader.py           # Docling structured extraction + pypdf fallback
├── pdf_reader.py               # pypdf page extraction + LangChain chunking
├── ocr_fallback.py             # Conditional RapidOCR with per-page isolation
├── visual_analyzer.py          # Region detection, cropping, local VLM analysis
├── upload_validation.py        # %PDF magic, size/page caps, SHA-256 → doc_id
├── models.py                   # Pydantic v2 canonical schemas + CONFIG_VERSION
├── resource_telemetry.py       # nvidia-smi VRAM, process memory, latency history
├── logging_setup.py            # Streamlit torch.classes watcher filter
│
├── tests/                      # pytest suite (29 test modules + shared fixtures)
│   ├── conftest.py             # Offline fixtures: mock Groq, MiniLM, provider, PDF paths
│   ├── test_*.py               # One module per production module/concern
│   └── data/corpus/            # Synthetic PDFs + generate_corpus.py
│
├── scripts/                    # Operator tooling, not imported by the app
│   ├── benchmark_baseline.py   # Retrieval baseline benchmark
│   ├── benchmark_multimodal.py # Tables/diagrams/abstention benchmark
│   ├── profile_resources.py    # VRAM/RAM/latency profile + InferenceGate check
│   └── generate_icons.py       # Regenerates assets/icons/*.svg
│
├── assets/
│   ├── brand_mark.svg          # Sidebar/hero brand mark (committed)
│   └── icons/*.svg             # 21 monochrome icons loaded by ui/components.py
│
├── docs/                       # RUNBOOK, EVALUATION, LOCAL_INFERENCE, LICENSES
├── application_screenshots/    # Screenshots used by docs
├── .streamlit/config.toml      # Dark theme, 50 MB upload cap, usage stats off
├── .devcontainer/              # Codespaces/devcontainer launch config
├── .github/workflows/ci.yml    # Ruff + synthetic corpus + pytest on Python 3.11
├── Dockerfile                  # python:3.11-slim-bookworm, Streamlit on 8501
├── docker-compose.yml          # App + optional CUDA llama-server profile
├── requirements.txt            # Runtime pins
├── requirements-lock.txt       # Deterministic Python 3.11 lockfile
├── requirements-test.txt       # pytest, reportlab, ruff, psutil
├── pyproject.toml              # Ruff + pytest configuration
│
├── data/                       # GENERATED, gitignored: documents.db + lancedb/
├── models/                     # GENERATED, gitignored: Qwen3-VL GGUF + mmproj
├── tools/llama-server/         # GENERATED, gitignored: native llama.cpp binaries/DLLs
├── .cache/                     # GENERATED, gitignored: per-SHA extraction cache
├── .planning/                  # GSD planning artifacts (this directory)
└── rag_assistant.egg-info/     # GENERATED packaging metadata
```

## Directory Purposes

**Repository root (flat module layer):**
- Purpose: All runtime domain modules live at the top level; the project is not organized into domain packages.
- Contains: 23 `snake_case.py` modules covering UI shell, inference, ingestion, storage, retrieval, and support.
- Key files: `main.py`, `local_llm.py`, `hybrid_retriever.py`, `doc_store.py`, `ui/ingestion_service.py`.

**`ui/`:**
- Purpose: Everything Streamlit-specific — rendering, theme, sanitization, session hydration, and the ingestion orchestrator.
- Contains: 7 files; `views.py` (829 lines) holds all five renderers, `ingestion_service.py` (300 lines) holds the ingestion workflow.
- Key files: `ui/views.py`, `ui/ingestion_service.py`, `ui/hydration.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`.
- Import rule: modules import each other absolutely (`from ui.components import ...`); `ui/__init__.py` deliberately exports only `sanitize_markdown_for_local`.

**`tests/`:**
- Purpose: Offline-first pytest suite; no GPU, network, or real model downloads required.
- Contains: 29 `test_*.py` modules, `conftest.py` fixtures (`mock_groq_client`, `mock_sentence_transformer`, `mock_llama_provider`, `sample_pdf_path`), and synthetic corpus PDFs.
- Key files: `tests/conftest.py`, `tests/test_hybrid_retriever.py`, `tests/test_doc_store.py`, `tests/test_main_ui.py`, `tests/test_ui_smoke.py`.

**`scripts/`:**
- Purpose: Benchmarks and profiling harnesses run manually or in CI-like environments.
- Contains: `benchmark_baseline.py`, `benchmark_multimodal.py`, `profile_resources.py`, `generate_icons.py`.
- Key files: `scripts/profile_resources.py` exercises retrieval, summarization, and `InferenceGate` end to end.

**`assets/`:**
- Purpose: Committed static presentation assets.
- Contains: `brand_mark.svg`; `icons/*.svg` (alert, chat, check, chevron-right, cloud, cpu, database, document, download, gpu, info, library, lock, ram, refresh, search, settings, sparkle, summarizer, trash, upload, workspace).
- Key files: `ui/components.py:7-49` loads these by name and caches them in process memory.

**`docs/`:**
- Purpose: Human documentation — operations, evaluation, local inference tuning, licenses.
- Contains: `RUNBOOK.md`, `EVALUATION.md`, `LOCAL_INFERENCE.md`, `LICENSES.md`.

**`data/` (generated, gitignored):**
- Purpose: Runtime persistence.
- Contains: `documents.db` (SQLite WAL), `lancedb/` (LanceDB tables and/or `fallback_store.json`), `lancedb_bench/` (benchmark store).
- Key files: created by `DocStore` (`main.py:137-139`) and `HybridRetriever` (`hybrid_retriever.py:36,105`).

**`models/` (generated, gitignored):**
- Purpose: Local GGUF weights consumed by `llama-server`.
- Contains: `qwen3-vl-2b-instruct-q4_k_m.gguf` (~986 MB) and `mmproj-f16.gguf` (~1.33 GB).
- Key files: downloaded by `setup.py` `MODEL_REGISTRY` (`setup.py:59-78`); launched by `start.py:127-149`.

**`tools/llama-server/` (generated, gitignored):**
- Purpose: Native llama.cpp server binary + CUDA/CPU runtime DLLs.
- Contains: `llama-server.exe`, `llama.dll`, `ggml-*.dll`, `cublas*.dll`, `LICENSE-LLVM-OpenMP`.
- Key files: located by `start.py:69-79` and `llama_cpp_provider.py:119-125`; provisioned by `setup.py:359-495`.

**`.cache/` (generated, gitignored):**
- Purpose: Per-document extraction cache.
- Contains: `<sha256>/<CONFIG_VERSION>/{pages.json, chunks.json, manifest.json}`.
- Key files: written by `ui/ingestion_service.py:277-288`; path helper in `models.py:17-30`.

**`.streamlit/`:**
- Purpose: Streamlit runtime configuration.
- Contains: `config.toml` — dark theme matching `ui/theme.py`, `maxUploadSize = 50`, CORS/XSRF on, usage stats off.

**`.devcontainer/`:**
- Purpose: Python 3.11 devcontainer/Codespaces bootstrap.
- Contains: `devcontainer.json` with post-attach `streamlit run main.py` (CORS/XSRF disabled for the dev container only).

**`.github/workflows/`:**
- Purpose: CI.
- Contains: `ci.yml` — uv install from lockfile, `ruff check` + `ruff format --check`, regenerate synthetic corpus, `pytest tests/ -v`.

**`application_screenshots/`:**
- Purpose: Documentation images (`image.png`, `image_2.png`, `mermaid_diagram.png`).

**`rag_assistant.egg-info/` (generated):**
- Purpose: Editable-install metadata produced by `pip install -e .` (`setup.py:676-730`). Not source.

## Key File Locations

**Entry Points:**
- `start.py`: Recommended launcher — Python check, directories, optional llama-server, Streamlit subprocess (`start.py:214-266`).
- `main.py`: Streamlit app — page config, session state, hydration, cloud sync, sidebar, workspace dispatch (`main.py:95-358`).
- `setup.py`: Packaging + installer CLIs (`setup.py:586-820`).
- `Dockerfile`: Container entry — `streamlit run main.py` on port 8501 (`Dockerfile:46`).
- `docker-compose.yml`: App service + optional `llama-server` GPU profile.

**Configuration:**
- `.streamlit/config.toml`: Theme, upload cap, server CORS/XSRF.
- `pyproject.toml`: Ruff (line length 120, E/F/W) and pytest config.
- `requirements.txt` / `requirements-lock.txt` / `requirements-test.txt`: Dependencies.
- `.env` (absent from working tree, gitignored): cloud API keys for local runs.
- `docker-compose.yml:14-23`: container environment variables (`LLAMA_SERVER_HOST/PORT`, cloud keys).

**Core Logic:**
- `main.py`: App composition and workspace routing.
- `ui/views.py`: All user-facing workflows.
- `ui/ingestion_service.py`: Ingestion pipeline.
- `local_llm.py`: Provider orchestration, prompt assembly, gate, verification.
- `hybrid_retriever.py`: Hybrid retrieval + RRF.
- `doc_store.py`: SQLite persistence and migrations.
- `summarizer.py`: Summarization strategies.
- `models.py`: Canonical data contracts.

**Testing:**
- `tests/conftest.py`: Shared offline fixtures.
- `tests/test_ui_smoke.py`: Imports and exercises UI helpers/hydration.
- `tests/test_main_ui.py`: `main.py` routing/state tests.
- `tests/data/corpus/generate_corpus.py`: Builds synthetic digital/scanned/table/chart PDFs.

## Naming Conventions

**Files:**
- Root runtime modules: `snake_case.py`, named for the subsystem or primary class (`hybrid_retriever.py`, `doc_store.py`, `upload_validation.py`).
- Provider modules: `<backend>_provider.py` (`llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`).
- UI modules: short role nouns under `ui/` (`views.py`, `components.py`, `theme.py`, `sanitizer.py`, `hydration.py`, `ingestion_service.py`). No `ui_` prefix.
- Tests: `test_<module-or-concern>.py`; one file per production module where practical (`test_hybrid_retriever.py`).
- Scripts: `verb_noun.py` or `noun_verb.py` (`benchmark_baseline.py`, `profile_resources.py`, `generate_icons.py`).
- Icons: lowercase single-word `.svg` (`document.svg`, `chevron-right.svg`).

**Classes:**
- `PascalCase`, noun-oriented: `DocStore`, `HybridRetriever`, `IngestionService`, `VisualAnalyzer`, `OcrEngine`, `Summarizer`, `AiModel`, `InferenceGate`.
- Providers end in `Provider`: `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`.
- Pydantic models are singular nouns: `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`, `CitationVerificationResult`.
- Result containers end in `Result` / `Upload` / `Capabilities` / `Status`.

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `search_hybrid`, `index_chunks`, `assemble_grounded_messages`, `validate_citations`, `hydrate_startup_state`.
- UI renderers use the `render_` prefix and return `None`: `render_chat_view`, `render_sidebar_documents`, `render_stat_card` (`ui/views.py:49,184,473,590,684`, `ui/components.py:52-122`).
- Private helpers use a single leading underscore: `_detect_provider`, `_embed_one`, `_bm25_search_fallback`, `_reset_session_security_state`, `_report`.
- Accessors use `get_` / `check_` / `is_` / `has_`: `get_embeddings`, `get_capabilities`, `check_health`, `is_persistent`, `has_document`.
- Commands/handlers use imperative verbs: `apply_conditional_ocr`, `validate_pdf_bytes`, `sanitize_markdown_for_local`, `bound_chat_history`.

**Variables / constants:**
- Locals and attributes: `snake_case` (`raw_chunks`, `computed_embeddings`, `doc_store`, `retrieval_result`).
- Module constants: `UPPER_SNAKE_CASE` (`MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_RRF_K`, `CONFIG_VERSION`, `FAST_PATH_TOKEN_LIMIT`, `MAX_BATCH_TOKENS`, `SYSTEM_GROUNDING_TEMPLATE`).
- `st.session_state` keys: `snake_case`; transient/internal keys use a leading underscore (`_startup_hydrated`, `_show_consent_dialog`, `_queued_prompt`, `_cached_cloud_model`).
- Chat turns are plain dicts with `role`, `content`, and optional `sources`, `verification`, `snippets`, `is_cloud`, `model_name` (`ui/views.py:442-452`).

**Identifiers and labels:**
- Document IDs: `doc_<sha16>` (`upload_validation.py:36-48`).
- Chunk IDs: `<sha12>_p<page>_<index:04d>` (`pdf_reader.py:94`, `docling_reader.py:251`), OCR chunks use the same shape with `extraction="ocr"`.
- Summary IDs: `summ_<uuid16>` (`summarizer.py:406`).
- Evidence element IDs: `elem_<doc_id>_p<page>_<kind>_<idx:02d>` (`visual_analyzer.py:258`).
- Evidence ranks displayed as `[E1]`, `[E2]` (`models.py:185-194`, `citation_validator.py:16`).
- Theme CSS classes: `amoled-card`, `amoled-card-elevated`, `stat-value`, `stat-label`, `stat-subtext`, `status-badge local|cloud|warning|error` (`ui/theme.py:46-126`).

**Imports:**
- Absolute imports only; the root is treated as the import root (`from doc_store import DocStore`, `from ui.views import render_chat_view`). No relative imports, no `src/` layout.
- New root modules are imported by name and must be added to the `py_modules` list in `setup.py:685-708` to be packaged.

## Where to Add New Code

**New workspace / top-level page:**
- Add a `render_<name>_view(...)` function in `ui/views.py` following the existing signature style (`doc_store`, `ai_model`, etc.).
- Register the label in `WORKSPACES` (`main.py:287-292`).
- Add the dispatch branch in `main.py:331-358`.
- Import the new renderer in the `ui.views` import block (`main.py:30-36`).
- Add a smoke/route test under `tests/test_main_ui.py` or `tests/test_ui_smoke.py`.

**New reusable UI element:**
- HTML/Streamlit primitive: `ui/components.py` (return a string when reusable, render when it owns `st.*`; use the `st.html` → `st.markdown(unsafe_allow_html=True)` fallback pattern).
- New color/token or global CSS: `ui/theme.py` (add a token constant, then reference it inside `THEME_CSS`).
- New icon: drop an SVG in `assets/icons/` (18×18 or 20×20 with `stroke="currentColor"`); optionally add it to `scripts/generate_icons.py` so it can be regenerated.
- Text sanitization: `ui/sanitizer.py`; do not inline regexes in views.

**New ingestion stage or extractor:**
- Extend `IngestionService.ingest_pdf` in `ui/ingestion_service.py` inside the numbered stage sequence; keep per-stage `try/except` + `_report()` progress.
- New extractor module at repo root (e.g. `foo_reader.py`) returning `list[Chunk | dict]` and `list[Page]`; wire it as a primary or fallback path in `ui/ingestion_service.py`.
- Persist new artifacts through `DocStore` (`doc_store.py`) and index text through `HybridRetriever.index_chunks` (`hybrid_retriever.py`).
- Add its file to `py_modules` in `setup.py:685-708`.

**New inference provider:**
- Create `<backend>_provider.py`, subclass `BaseModelProvider` (`model_provider.py:64-156`), implement all five abstract methods.
- Declare honest `ProviderCapabilities` (`is_local`, `supports_vision`, `context_window`).
- Wire selection in `AiModel._detect_provider` (`local_llm.py:168-185`) or in the cloud-provider sync in `main.py:159-185`.
- Respect `InferenceGate` when called from ingestion/summarization; use `set_consent` + `_assert_consent` for any cloud provider.
- Add `tests/test_<backend>_provider.py` using `httpx.MockTransport` or mocks (see `tests/test_llama_cpp_provider.py`).

**New persisted field or table:**
- Add/extend a Pydantic model in `models.py`.
- Add a new `SCHEMA_V<n>_DDL` list and a `MIGRATIONS` entry in `doc_store.py:17-100`; never edit an applied migration in place.
- Add CRUD methods in `DocStore` using `_connect()` and `?` placeholders; keep `TypeError` guards for wrong model types.
- Add coverage in `tests/test_doc_store.py` (migration idempotence + round-trip).

**New retrieval capability:**
- Implement in `hybrid_retriever.py`; preserve the `search_hybrid -> RetrievalResult` contract and the `EvidenceSnippet` ranking semantics.
- Extend `RetrievalResult.search_mode` literal in `models.py:181-183` if a new mode is introduced.
- Keep the LanceDB primary + `VectorIndex`/JSON fallback parity; update `tests/test_hybrid_retriever.py`.

**New summarization behavior:**
- Profiles belong in `PROFILE_SYSTEM_INSTRUCTIONS` and `VALID_SUMMARY_PROFILES` (`summarizer.py:31-105`, `models.py:208-209`); update the profile map in `ui/views.py:502-508`.
- Keep all provider calls inside `InferenceGate` and persist via `DocStore.save_summary`.

**New telemetry or diagnostics:**
- Add sampling helpers to `resource_telemetry.py` (respect TTL caches and graceful `None` on headless hosts).
- Render in `render_settings_view` (`ui/views.py:684-829`) using `render_stat_card`.

**New configuration or secret:**
- Server/theme/upload limits: `.streamlit/config.toml`.
- Cloud keys: resolve in the order session `cloud_api_keys` → `st.secrets` → environment, matching `litellm_provider.py:44-88`; never commit `.env`.
- New runtime path constants: define near `APP_DIR`/`DOC_STORE_PATH` in `main.py:136-138` if app-wide, otherwise beside the owning module.

**New tests:**
- Place in `tests/test_<module>.py`; reuse fixtures from `tests/conftest.py` to keep tests offline.
- Mock at the seam, not the internals: `httpx.MockTransport` for llama-server, `MagicMock` for Groq/LiteLLM, `mock_sentence_transformer` for embeddings.
- UI tests import from `ui.*` directly; `main.py` tests patch Streamlit state rather than executing the full script.

**New scripts / benchmarks:**
- Add to `scripts/` with a `main()`-style entry, deterministic fixtures, and a JSON report where applicable (see `scripts/benchmark_multimodal.py`).

## Special Directories

**`data/`:**
- Purpose: SQLite metadata + LanceDB vector tables.
- Generated: Yes (on first upload / retriever construction).
- Committed: No (`.gitignore:9`).

**`models/`:**
- Purpose: GGUF model weights for llama-server.
- Generated: Yes (`setup.py download_models` / `setup.py --models-only`).
- Committed: No (`.gitignore:16-17`).

**`tools/llama-server/`:**
- Purpose: Native llama.cpp server + CUDA runtime.
- Generated: Yes (`setup.py setup_llama_server` / `setup.py --llama-server`).
- Committed: No (`.gitignore:18`).

**`.cache/`:**
- Purpose: Per-document pages/chunks/manifest JSON keyed by SHA-256 + config version.
- Generated: Yes (`ui/ingestion_service.py:277-288`).
- Committed: No (`.gitignore:14`).

**`assets/icons/`:**
- Purpose: Committed monochrome icon set consumed by `ui/components.get_svg_icon`.
- Generated: Yes by `scripts/generate_icons.py`, but the SVGs are committed so the app runs without regeneration.
- Committed: Yes.

**`tests/data/corpus/`:**
- Purpose: Synthetic PDFs for extraction/OCR/table/chart tests.
- Generated: Yes by `tests/data/corpus/generate_corpus.py` (CI regenerates before pytest).
- Committed: Yes (the generated PDFs are present in-tree).

**`.planning/`:**
- Purpose: GSD planning and codebase-map artifacts (including this document).
- Generated: Yes (by GSD commands).
- Committed: Typically yes, unless the repo chooses otherwise.

**`rag_assistant.egg-info/`:**
- Purpose: Editable-install metadata.
- Generated: Yes (`pip install -e .`).
- Committed: No (`.gitignore:10`).

---

*Structure analysis: 2026-10-20*
