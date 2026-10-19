# Codebase Structure

**Analysis Date:** 2026-10-19

## Directory Layout

```
RAG/
├── main.py                     # Streamlit entry script (page config, session, routing)
├── start.py                    # One-command launcher (pre-flight + llama-server + Streamlit)
├── setup.py                    # setuptools packaging + CLI/model/llama-server acquisition
├── models.py                   # Canonical Pydantic v2 schemas + cache_dir_for
├── model_provider.py           # BaseModelProvider ABC + capabilities/health schemas
├── llama_cpp_provider.py       # Local llama-server provider (HTTP/SSE/vision)
├── groq_provider.py            # Direct Groq cloud provider
├── litellm_provider.py         # LiteLLM multi-cloud provider (consent-gated)
├── local_llm.py                # AiModel + InferenceGate orchestration
├── prompt_budget.py            # Token budgeting + XML injection defense
├── summarizer.py               # 5-profile single-pass / map-reduce summarizer
├── citation_validator.py       # Citation precision + abstention + injection checks
├── doc_store.py                # SQLite (WAL) metadata/chunk/evidence/summary store
├── hybrid_retriever.py         # LanceDB + BM25 + RRF hybrid retriever
├── vector_index.py             # Pure-stdlib in-memory vector index (fallback)
├── local_embedding.py          # sentence-transformers MiniLM wrapper (CPU)
├── docling_reader.py           # Docling layout/table extraction (+ pypdf fallback)
├── pdf_reader.py               # pypdf fallback extractor with per-page isolation
├── ocr_fallback.py             # Conditional RapidOCR with thread-pool batching
├── visual_analyzer.py          # Region detection, cropping, VLM analysis
├── upload_validation.py        # PDF validation + streaming SHA-256 + doc_id
├── resource_telemetry.py       # GPU/RAM telemetry + latency profiling
├── logging_setup.py            # Streamlit torch.classes watcher filter
├── ui/                         # Streamlit UI package (recently modularized)
│   ├── __init__.py             # Re-exports sanitize_markdown_for_local
│   ├── views.py                # 5 workspace renderers + append_chat_turn
│   ├── components.py           # SVG icons, brand header, stat cards, pills, chips
│   ├── theme.py                # AMOLED design tokens + injected CSS
│   ├── hydration.py            # Startup hydration from SQLite + LanceDB
│   └── sanitizer.py            # Markdown/HTML sanitization (zero-egress)
├── assets/                     # In-repo visual assets (committed)
│   ├── brand_mark.svg          # App brand mark (also favicon via set_page_config)
│   └── icons/                  # 22 monochrome SVG icons (committed)
│       ├── alert.svg chat.svg check.svg chevron-right.svg cloud.svg
│       ├── cpu.svg database.svg document.svg download.svg gpu.svg info.svg
│       ├── library.svg lock.svg ram.svg refresh.svg search.svg settings.svg
│       ├── sparkle.svg summarizer.svg trash.svg upload.svg workspace.svg
├── tools/                      # Native runtime binaries (gitignored)
│   └── llama-server/           # llama.cpp Windows CUDA build + DLLs (llama.exe, ggml*.dll, cublas*.dll, ...)
├── models/                     # GGUF model weights (gitignored)
│   ├── qwen3-vl-2b-instruct-q4_k_m.gguf
│   └── mmproj-f16.gguf
├── data/                       # Runtime persistence (gitignored)
│   ├── documents.db            # SQLite database (WAL mode)
│   ├── lancedb/                # LanceDB tables or fallback_store.json
│   └── lancedb_bench/          # Benchmark-only LanceDB instance
├── .cache/                     # Per-document extraction cache (gitignored)
├── docs/                       # Committed operator/developer documentation
│   ├── RUNBOOK.md              # Install, model acquisition, operations
│   ├── EVALUATION.md           # Benchmarks, VRAM profile, test metrics
│   ├── LOCAL_INFERENCE.md      # llama-server tuning reference (4 GB GPU)
│   └── LICENSES.md             # Third-party license inventory
├── scripts/                    # Standalone benchmark/utility scripts
│   ├── benchmark_baseline.py   # Baseline retrieval/perf suite
│   ├── benchmark_multimodal.py # Quality + grounding benchmark suite
│   ├── profile_resources.py    # VRAM/RAM profiling harness
│   └── generate_icons.py       # Regenerates assets/icons/*.svg
├── tests/                      # pytest suite (31 modules, offline)
│   ├── conftest.py             # Shared offline fixtures/mocks
│   ├── __init__.py
│   ├── data/corpus/            # Synthetic PDF corpus + generate_corpus.py
│   └── test_*.py               # One test module per subsystem
├── .github/workflows/ci.yml    # Lint + corpus gen + pytest on Python 3.11
├── .devcontainer/              # Dev container definition (Python 3.11 image)
├── .streamlit/config.toml      # Dark theme tokens, CORS/XSRF, 50 MB upload cap
├── application_screenshots/    # Committed UI screenshots + mermaid diagram PNG
├── Dockerfile                  # python:3.11-slim-bookworm app image
├── docker-compose.yml          # app service + optional GPU llama-server profile
├── requirements.txt            # Runtime deps (pinned where stable)
├── requirements-lock.txt       # Deterministic lockfile
├── requirements-test.txt       # pytest/reportlab/ruff
├── pyproject.toml              # Ruff + pytest configuration
├── .planning/                  # GSD planning artifacts (phases, research, codebase map)
├── rag_assistant.egg-info/     # Generated packaging metadata (gitignored)
├── LICENSE README.md CLAUDE.md
```

## Directory Purposes

**Repository root (flat Python modules):**
- Purpose: All application logic lives as single-purpose top-level modules — no `src/` or package layout.
- Contains: 22 importable `.py` modules + entry scripts.
- Key files: `main.py`, `ui/views.py`, `models.py`, `local_llm.py`.

**`ui/` (presentation package):**
- Purpose: Isolate Streamlit presentation, theming, components, hydration, and sanitization from domain logic.
- Contains: `views.py` (5 `render_*_view` functions + `append_chat_turn`), `components.py`, `theme.py`, `hydration.py`, `sanitizer.py`, `__init__.py`.
- Key files: `ui/views.py` (912 lines, largest module), `ui/hydration.py`, `ui/components.py`.

**`assets/` (committed static assets):**
- Purpose: Serve local-only brand/icon imagery with zero network egress.
- Contains: `brand_mark.svg`; `icons/*.svg` (22 monochrome stroke icons, `width/height=18`).
- Key files: `assets/icons/document.svg`, `assets/icons/search.svg`, `assets/brand_mark.svg`.

**`tools/llama-server/` (native runtime):**
- Purpose: Hold the downloaded llama.cpp binary + Windows CUDA DLLs used by `LlamaCppProvider` / `start.py`.
- Contains: `llama-server.exe` and companion `.exe`/`.dll` files; `LICENSE-LLVM-OpenMP`.
- Key files: `tools/llama-server/llama-server.exe` (resolved at `start.py:74-79`, `llama_cpp_provider.py:119-125`).
- Generated: Yes (via `setup.py setup_llama_server`). Committed: No (`tools/` in `.gitignore`).

**`models/` (GGUF weights):**
- Purpose: Local inference weights for llama-server plus the multimodal projector.
- Key files: `models/qwen3-vl-2b-instruct-q4_k_m.gguf`, `models/mmproj-f16.gguf`.
- Generated: Yes (via `setup.py download_models`). Committed: No.

**`data/` (runtime persistence):**
- Purpose: Durable SQLite store and LanceDB vector tables.
- Key files: `data/documents.db`, `data/lancedb/fallback_store.json` (present; LanceDB tables absent when `lancedb` is unavailable), `data/lancedb_bench/`.
- Generated: Yes. Committed: No.

**`.cache/` (extraction cache):**
- Purpose: Per-document cached artefacts at `.cache/<sha256>/<CONFIG_VERSION>/{pages.json,chunks.json,manifest.json}`.
- Key files: path computed by `models.cache_dir_for` (`models.py:17-30`).
- Generated: Yes. Committed: No.

**`docs/` (operator docs):**
- Purpose: Installation, ops, evaluation, and inference-tuning references.
- Key files: `docs/RUNBOOK.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`, `docs/LICENSES.md`.

**`scripts/` (benchmarks/utilities):**
- Purpose: Standalone, manually-run evaluation and asset-generation tooling; each inserts repo root on `sys.path`.
- Key files: `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`.

**`tests/` (pytest suite):**
- Purpose: Offline unit/integration tests with mocked providers and corpus PDFs.
- Key files: `tests/conftest.py` (fixtures: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `mock_llama_provider`), `tests/data/corpus/generate_corpus.py`.
- Generated: `tests/data/corpus/*.pdf` regenerated by CI. Committed: Yes (PDFs + generator).

**`application_screenshots/`:**
- Purpose: Committed UI reference images, including `mermaid_diagram.png`.

**`.planning/`:**
- Purpose: GSD workflow artefacts: `PROJECT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `STATE.md`, `phases/`, `research/`, `codebase/`.
- Generated: Yes (by GSD commands). N/A for runtime.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit script executed by `streamlit run main.py`.
- `start.py`: `python start.py` launcher; console-script `rag-assistant` (`setup.py:712`).
- `setup.py`: `python setup.py <subcommand>`; console-scripts `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:713-715`).
- `scripts/*.py`: Direct execution only.
- `Dockerfile`: `CMD ["streamlit", "run", "main.py", ...]` (`Dockerfile:46`).

**Configuration:**
- `pyproject.toml`: Ruff (`line-length=120`, `select=["E","F","W"]`) + pytest (`testpaths=["tests"]`).
- `.streamlit/config.toml`: Dark theme, `maxUploadSize = 50`, XSRF on / CORS off.
- `.env` (gitignored, not present): local `GROQ_API_KEY` / cloud keys; read via `load_dotenv()` (`main.py:149`).
- `docker-compose.yml`: `app` service (ports, volumes, env) + `gpu`-profile `llama-server`.
- `.github/workflows/ci.yml`: uv install from lockfile → ruff check/format → corpus gen → pytest.
- `.devcontainer/devcontainer.json`: Python 3.11 image + port 8501.

**Core Logic:**
- `models.py`: every schema; `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`).
- `local_llm.py`: `AiModel` + `InferenceGate` (`local_llm.py:26`, `local_llm.py:93`).
- `hybrid_retriever.py`: `compute_rrf` + `HybridRetriever` (`hybrid_retriever.py:40`, `hybrid_retriever.py:88`).
- `doc_store.py`: `DocStore` + migration registry (`doc_store.py:96-100`, `doc_store.py:103`).
- `ui/views.py`: `render_workspace_view` / `render_chat_view` / `render_summarizer_view` / `render_library_view` / `render_settings_view`.
- `prompt_budget.py`: `SYSTEM_GROUNDING_TEMPLATE` (`prompt_budget.py:13`), `assemble_grounded_messages` (`prompt_budget.py:57`).

**Testing:**
- `tests/conftest.py`: shared fixtures and provider/network mocks.
- `tests/test_ui_smoke.py`, `tests/test_main_ui.py`: UI contracts.
- `tests/test_hydration.py`: startup hydration.
- `tests/test_visual_analyzer.py`, `tests/test_ocr_fallback.py`, `tests/test_docling_reader.py`: ingestion.
- `tests/data/corpus/`: `clean_digital.pdf`, `scanned_sample.pdf`, `dense_table.pdf`, `chart_diagram.pdf`, `multi_column.pdf`, `corrupt_invalid.pdf`.

## Naming Conventions

**Files:**
- Root modules: flat `snake_case.py`, one primary class or one concern per file (e.g. `hybrid_retriever.py` → `HybridRetriever`; `upload_validation.py` → functions only).
- UI package members: single lowercase word (`views.py`, `theme.py`, `components.py`, `hydration.py`, `sanitizer.py`).
- Test modules: `tests/test_<module>.py` mirroring the module under test (e.g. `tests/test_hybrid_retriever.py`, `tests/test_ui_smoke.py`).
- Scripts: `scripts/<verb>_<noun>.py` (`benchmark_baseline.py`, `profile_resources.py`).
- Docs & plan files: `UPPERCASE.md` (`README.md`, `RUNBOOK.md`, `ARCHITECTURE.md`).

**Directories:**
- Lowercase single-word at root: `ui/`, `tests/`, `scripts/`, `docs/`, `tools/`, `models/`, `data/`, `assets/`, `application_screenshots/`.
- Nested asset dir: `assets/icons/`.

**Classes:**
- `PascalCase`, one public class per module: `AiModel`, `InferenceGate`, `HybridRetriever`, `VectorIndex`, `DocStore`, `DoclingReader`, `PdfReader`, `OcrEngine`, `VisualAnalyzer`, `Summarizer`, `LocalEmbedding`, `LlamaCppProvider`, `GroqProvider`, `LiteLLMProvider`, `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus`, `LatencyTracker`.
- UI components are module-level functions, not classes.

**Functions / methods:**
- `snake_case` verbs: `render_workspace_view`, `render_chat_view`, `hydrate_startup_state`, `inject_custom_theme`, `get_svg_icon`, `render_status_pill`, `sanitize_markdown_for_local`, `assemble_grounded_messages`, `validate_citations`, `summarize_document`, `search_hybrid`, `index_chunks`, `apply_conditional_ocr`, `detect_visual_regions`, `analyze_visual_elements`, `validate_pdf_bytes`.
- Private helpers/vars use a single leading underscore: `_detect_provider`, `_embed_one`, `_cosine_distance`, `_resolve_api_key_for_model`, `_assert_consent`, `_bm25_search_fallback`, `_save_fallback_store`, `_connect`, `_startup_hydrated`, `_reset_session_security_state`.

**Identifiers / value formats:**
- Document: `doc_<sha16>` via `upload_validation.doc_id_for` (`upload_validation.py:36`); identity is the SHA-256 digest.
- Chunk: `f"{sha12}_p{page}_{index:04d}"` (`docling_reader.py:251`, `ocr_fallback.py:276`, `pdf_reader.py:94`).
- Summary: `summ_<uuid4hex[:16]>` (`summarizer.py:406`).
- Evidence element: `elem_{doc_id}_p{page}_{kind}_{idx:02d}` (`visual_analyzer.py:258`).
- Session keys: `snake_case` (`doc_ids`, `indexed_files`, `document_metadata`, `hybrid_retriever`, `chat_history`, `cloud_api_keys`, `uploader_key`, `active_workspace`, `_startup_hydrated`, `_show_consent_dialog`).

## Where to Add New Code

**New Streamlit workspace / view:**
- Add a `render_<name>_view(...)` function in `ui/views.py` (follow the section-banner comment style and `render_empty_state`/`render_stat_card` usage).
- Register it in the `WORKSPACES` list and the `if/elif` dispatch in `main.py:253-259` and `main.py:320-354`.
- Add any new `st.session_state` keys to the initialisation loop in `main.py:110-130` (never lazily mid-render).

**New UI primitive (card, badge, icon):**
- Add a function to `ui/components.py`; load icons via `get_svg_icon(name)` and add the SVG to `assets/icons/` (regenerate with `scripts/generate_icons.py`).
- Add styling tokens/CSS classes to `ui/theme.py` and reference the `COLOR_*` constants.

**New inference provider:**
- Subclass `BaseModelProvider` (`model_provider.py:64`) implementing `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`; place at repo root as `<backend>_provider.py`.
- Wire selection into `AiModel._detect_provider` (`local_llm.py:168`) and register the module in `py_modules` in `setup.py:685-708`.
- If cloud: enforce consent via the `_assert_consent` pattern and resolve keys with the `explicit → session → secrets → env` precedence (`litellm_provider.py:44-88`).

**New extraction / ingestion stage:**
- Add a root module returning canonical `Page`/`Chunk`/`EvidenceElement` models from `models.py`.
- Integrate into the ingestion loop between steps in `ui/views.py:147-223`, preserving per-document `try/except` + `st.error` isolation and the `sha12` chunk-id scheme.

**New persisted schema field/table:**
- Add a new `SCHEMA_V<n>_DDL` list and register it in `MIGRATIONS` (`doc_store.py:96-100`); add `isinstance` guards and `ON CONFLICT` upserts following existing methods.
- Extend the matching Pydantic model in `models.py`.

**New retrieval parameter/ranking change:**
- Modify `HybridRetriever.search_hybrid` (`hybrid_retriever.py:534`) and `compute_rrf` (`hybrid_retriever.py:40`), keeping dense and FTS ranked lists balanced; keep the `RetrievalResult`/`EvidenceSnippet` contract stable so `local_llm.py` and `ui/views.py` citations keep working.
- Keep `LOCAL_EMBEDDING`/`vector_dim=384` consistent with `all-MiniLM-L6-v2`.

**New support/telemetry helper:**
- Add to `resource_telemetry.py` (already holds GPU/process/latency helpers) rather than a new module.

**New tests:**
- Add `tests/test_<module>.py`; reuse fixtures from `tests/conftest.py` and mock all providers/network. Keep the suite offline.

**New script:**
- Add `scripts/<verb>_<noun>.py`; prepend repo root to `sys.path` and write JSON outputs under `.planning/research/`.

**Configuration / packaging changes:**
- Runtime dependency → `requirements.txt`; regenerate `requirements-lock.txt`; add a new top-level module to `py_modules` in `setup.py:685-708`; expose a CLI via the `entry_points.console_scripts` map (`setup.py:710-717`).

## Special Directories

**`tools/llama-server/`:**
- Purpose: Native llama.cpp binaries and Windows CUDA runtime DLLs.
- Generated: Yes. Committed: No (`tools/` gitignored; excluded from Docker build via `.dockerignore`).

**`models/`:**
- Purpose: GGUF weights for the local VLM.
- Generated: Yes. Committed: No.

**`data/`:**
- Purpose: SQLite + LanceDB runtime state.
- Generated: Yes. Committed: No. Excluded from Docker context; mounted as a volume in `docker-compose.yml`.

**`.cache/`:**
- Purpose: Per-document extraction cache keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes. Committed: No.

**`assets/icons/`:**
- Purpose: Committed monochrome SVG icon set consumed by `ui/components.py`.
- Generated: Regenerable via `scripts/generate_icons.py`, but committed for offline operation.

**`tests/data/corpus/`:**
- Purpose: Synthetic PDF fixtures (clean, scanned, tables, diagrams, multi-column, corrupt).
- Generated: Regenerable via `tests/data/corpus/generate_corpus.py` (CI runs it before pytest). Committed: Yes.

**`rag_assistant.egg-info/`:**
- Purpose: setuptools metadata from `pip install -e .`.
- Generated: Yes. Committed: No.

**`.planning/`:**
- Purpose: GSD planning + codebase map artefacts consumed by planning/execution commands.
- Generated: Yes. Committed: Yes (project history).

---

*Structure analysis: 2026-10-19*
