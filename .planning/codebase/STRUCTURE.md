# Codebase Structure

**Analysis Date:** 2026-10-17

## Directory Layout

```
RAG/
├── start.py                    # One-command launcher (pre-flight + Streamlit subprocess)
├── setup.py                    # setuptools packaging, dependency install, model download CLIs
├── main.py                     # Streamlit frontend + full application lifecycle (915 lines)
├── model_provider.py           # BaseModelProvider ABC + ProviderCapabilities/HealthStatus
├── llama_cpp_provider.py       # Local llama-server client (Qwen3-VL 2B, loopback-only)
├── litellm_provider.py         # Cloud LiteLLM adapter (Groq/OpenAI/Anthropic) + consent gate
├── groq_provider.py            # Direct Groq SDK adapter (legacy/fallback)
├── local_llm.py                # AiModel orchestrator + InferenceGate concurrency primitive
├── summarizer.py               # 5-profile single-pass / map-reduce summarization
├── citation_validator.py       # [En] citation precision + abstention + injection checks
├── prompt_budget.py            # Token budgeting + <document_context> XML framing defense
├── hybrid_retriever.py         # LanceDB dense+FTS hybrid retrieval with RRF
├── local_embedding.py          # all-MiniLM-L6-v2 CPU embedding wrapper + shared cache
├── vector_index.py             # Pure-stdlib in-memory cosine/euclidean fallback index
├── doc_store.py                # SQLite metadata store (documents/pages/chunks/evidence/summaries)
├── docling_reader.py           # Docling layout + markdown table extraction (PdfReader fallback)
├── pdf_reader.py               # pypdf extraction + langchain chunking
├── ocr_fallback.py             # Conditional RapidOCR with per-page fault isolation
├── visual_analyzer.py          # PyMuPDF region detection/cropping + VLM analysis
├── upload_validation.py        # %PDF magic, size/page caps, SHA-256, doc_id derivation
├── resource_telemetry.py       # GPU VRAM (nvidia-smi), process RAM (psutil), latency tracking
├── models.py                   # Pydantic v2 canonical schemas + cache_dir_for helper
├── requirements.txt            # Production runtime dependencies (pinned ranges)
├── requirements-lock.txt       # Deterministic Python 3.11 deployment lockfile
├── requirements-test.txt       # Test-only deps (pytest, reportlab, ruff, psutil)
├── pyproject.toml              # Ruff lint/format config + pytest config
├── README.md                   # Architecture diagram, quickstart, privacy model
├── LICENSE                     # MIT
├── .github/
│   └── workflows/ci.yml        # Lint + format check + synthetic corpus + pytest
├── .devcontainer/
│   └── devcontainer.json       # Python 3.11 image + Streamlit auto-launch
├── data/                       # Runtime persistence (gitignored)
│   ├── documents.db            # SQLite database (DocStore)
│   └── lancedb/                # LanceDB tables + fallback_store.json
├── .cache/                     # Best-effort per-document JSON cache (gitignored)
├── models/                     # GGUF weights (gitignored, downloaded by setup.py)
├── docs/
│   ├── RUNBOOK.md              # Installation, hardware tuning, operations
│   ├── EVALUATION.md           # Benchmarks, VRAM profile, test metrics
│   └── LOCAL_INFERENCE.md      # llama-server flag reference for 4 GB GPUs
├── scripts/
│   ├── benchmark_multimodal.py # Multimodal evaluation harness
│   ├── benchmark_baseline.py   # Baseline retrieval performance suite
│   └── profile_resources.py    # VRAM/RAM hardware profiling harness
├── application_screenshots/    # UI screenshots + mermaid diagram image
└── tests/
    ├── conftest.py             # Shared offline fixtures (mocked providers/models)
    ├── data/corpus/            # Synthetic PDFs + generate_corpus.py
    ├── test_*.py               # 22 pytest modules (226 tests)
    └── ...
```

## Directory Purposes

**Repository root (flat module layout):**
- Purpose: All application modules live at the repo root as a single flat package — there is no `src/` or `app/` directory.
- Contains: 22 Python modules (see layout above), packaging/config files, and docs.
- Key files: `main.py`, `local_llm.py`, `model_provider.py`, `hybrid_retriever.py`, `doc_store.py`, `models.py`.

**`data/`:**
- Purpose: Runtime persistence for the SQLite metadata store and LanceDB vector tables.
- Contains: `documents.db` (SQLite WAL), `lancedb/` (LanceDB tables and `fallback_store.json` JSON fallback), plus benchmark variant `lancedb_bench/`.
- Key files: `data/documents.db`, `data/lancedb/fallback_store.json`.
- Note: gitignored (`.gitignore` line `data/`); created at runtime by `DocStore.__init__` (`doc_store.py:116`) and `HybridRetriever` (`hybrid_retriever.py:114`).

**`.cache/`:**
- Purpose: Best-effort per-document JSON cache keyed by SHA-256 and config version.
- Contains: `<sha256>/docling-1000-200-v1/{pages.json, chunks.json, manifest.json}`.
- Key files: path built by `cache_dir_for` (`models.py:17-30`); written at `main.py:534-545`.
- Note: gitignored; deleted by "Purge All Data" (`main.py:342-348`).

**`models/`:**
- Purpose: Destination for downloaded quantized GGUF weights (`qwen3-vl-2b-instruct-q4_k_m.gguf`, `mmproj-f16.gguf`).
- Contains: Model binaries (gitignored); created by `setup.py:ensure_project_directories`.
- Key files: `MODEL_REGISTRY` in `setup.py:44-63` defines download URLs.

**`docs/`:**
- Purpose: Operator-facing documentation.
- Contains: `RUNBOOK.md`, `EVALUATION.md`, `LOCAL_INFERENCE.md`.

**`scripts/`:**
- Purpose: Standalone benchmarking/profiling harnesses, not part of the app runtime.
- Contains: `benchmark_multimodal.py`, `benchmark_baseline.py`, `profile_resources.py`.
- Key files: per-file `E402` ruff exemption in `pyproject.toml:17`.

**`tests/`:**
- Purpose: Fully offline pytest suite with mocked inference/embeddings/GPU telemetry.
- Contains: `conftest.py` shared fixtures, `data/corpus/` synthetic PDFs, and 22 `test_*.py` modules (226 tests).

**`.github/workflows/`:**
- Purpose: CI pipeline.
- Contains: `ci.yml` — installs from lockfile via uv, runs `ruff check`/`ruff format --check`, regenerates the synthetic corpus, runs `pytest tests/ -v` on Python 3.11.

**`application_screenshots/`:**
- Purpose: UI reference images and the mermaid architecture image.

## Key File Locations

**Entry Points:**
- `main.py`: Sole Streamlit application entry (top-to-bottom script; `st.set_page_config` first at line 49).
- `start.py`: Launcher CLI (`main()` at `start.py:106`); `rag-assistant` console script.
- `setup.py`: `__main__` CLI dispatch (`setup.py:452`) and `setup(**setup_kwargs)` (`setup.py:449`); `rag-setup` / `rag-download-models` console scripts.

**Configuration:**
- `requirements.txt`: Runtime dependencies (`streamlit`, `pypdf`, `docling`, `rapidocr-onnxruntime`, `pymupdf`, `lancedb`, `litellm`, `sentence-transformers`, `pydantic`, `httpx`, `psutil`).
- `requirements-lock.txt`: Deterministic lockfile used by CI and recommended for installs.
- `pyproject.toml`: Ruff config (line-length 120, select `E,F,W`) + pytest config (`testpaths=["tests"]`).
- `setup.py`: Packaging metadata, `py_modules` list, console-script entry points, model registry.
- `.env`: Local secrets (gitignored, not committed) — note existence only, never read.

**Core Logic:**
- `main.py`: UI + orchestration (ingestion, query, summarization, telemetry).
- `local_llm.py`: `AiModel` + `InferenceGate` (provider selection, grounded streaming, validation).
- `model_provider.py`: `BaseModelProvider` contract all providers implement.
- `hybrid_retriever.py`: Retrieval engine (dense + BM25 + RRF).
- `doc_store.py`: SQLite persistence with schema migrations v1–v3.
- `models.py`: Canonical Pydantic schemas shared across layers.
- `summarizer.py`: Multi-profile summarization service.
- `prompt_budget.py` / `citation_validator.py`: Prompt safety + response verification.

**Testing:**
- `tests/conftest.py`: Offline fixtures — `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`.
- `tests/data/corpus/generate_corpus.py`: Regenerates synthetic PDF corpus (run by CI).
- `tests/test_*.py`: Per-module suites (e.g. `test_hybrid_retriever.py`, `test_summarizer.py`, `test_citation_validator.py`, `test_cloud_privacy.py`, `test_ocr_fallback.py`, `test_models.py`).

**Documentation:**
- `README.md`: System architecture mermaid, repository structure, quickstart, privacy model.
- `docs/RUNBOOK.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`.

## Naming Conventions

**Files:**
- Flat `snake_case.py` modules at the repo root — one public class or cohesive concern per file: `model_provider.py` (`BaseModelProvider`), `hybrid_retriever.py` (`HybridRetriever`), `doc_store.py` (`DocStore`), `visual_analyzer.py` (`VisualAnalyzer`), `upload_validation.py` (functions + `ValidatedUpload`).
- Provider files follow `<backend>_provider.py`: `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`.
- Extractor files follow `<source>_reader.py`: `docling_reader.py`, `pdf_reader.py`.
- Fallback/support files describe capability: `ocr_fallback.py`, `prompt_budget.py`, `citation_validator.py`, `resource_telemetry.py`.
- Tests follow `test_<module>.py` (pytest discovery via `pyproject.toml:20-23`).
- Scripts follow `<verb>_<noun>.py`: `benchmark_multimodal.py`, `profile_resources.py`.

**Classes:**
- `PascalCase`, one primary class per module: `AiModel`, `InferenceGate` (`local_llm.py`), `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`, `HybridRetriever`, `LocalEmbedding`, `VectorIndex`, `DocStore`, `DoclingReader`, `PdfReader`, `OcrEngine`, `VisualAnalyzer`, `Summarizer`, `LatencyTracker`.
- Pydantic schemas are nouns: `BBox`, `Chunk`, `Page`, `Document`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`, `CitationVerificationResult` (`models.py`, `model_provider.py`, `citation_validator.py`).

**Functions & Methods:**
- `snake_case` verb phrases: `ask_a_question_from_pdf_stream` (`local_llm.py:216`), `search_hybrid`/`index_chunks`/`compute_rrf` (`hybrid_retriever.py`), `validate_citations` (`citation_validator.py:115`), `assemble_grounded_messages`/`estimate_tokens`/`sanitize_xml_boundary` (`prompt_budget.py`), `validate_pdf_bytes`/`doc_id_for` (`upload_validation.py`), `get_gpu_memory_info`/`track_stage` (`resource_telemetry.py`).
- Private helpers use a single leading underscore: `_detect_provider` (`local_llm.py:167`), `_cosine_distance`/`_euclidean_distance`/`_dot_product`/`_magnitude` (`vector_index.py:142-199`), `_embed_one` (`local_embedding.py:69`), `_connect`/`_apply_migrations` (`doc_store.py:122,141`), `_bm25_search_fallback`/`_save_fallback_store` (`hybrid_retriever.py:440,162`), `_bundle_pages`/`_summarize_map_reduce` (`summarizer.py:166,233`), `_assert_consent`/`_resolve_api_key_for_model` (`litellm_provider.py:126,39`).

**Variables & Attributes:**
- `snake_case`: `page_records`, `page_chunks`, `hybrid_retriever`, `chat_history` (`main.py:63-76`), `embedding_fn`, `vector_dim`, `_fallback_store` (`hybrid_retriever.py:97-110`), `db_path` (`doc_store.py:115`).
- Literal constants are inline; only a few module-level `UPPER_CASE` names exist: `MAX_FILE_MB`/`MAX_PAGES` (`upload_validation.py:15-16`), `MAX_CHAT_TURNS` (`main.py:43`), `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS` (`summarizer.py:28-29`), `DEFAULT_RRF_K` (`hybrid_retriever.py:28`), `DEFAULT_CLOUD_MODEL`/`KNOWN_CONTEXT_WINDOWS` (`litellm_provider.py:23-29`), `CONFIG_VERSION` (`models.py:14`), `SCHEMA_V*_DDL`/`MIGRATIONS` (`doc_store.py:17-100`), `PROFILE_SYSTEM_INSTRUCTIONS` (`summarizer.py:31`).

**IDs & keys (domain conventions):**
- Document IDs: `doc_<sha16>` (16 hex chars) via `doc_id_for` (`upload_validation.py:36-48`).
- Chunk IDs: `<sha12|filename>_p<page>_<index:04d>` (`pdf_reader.py:76`, `docling_reader.py:227`, `ocr_fallback.py:244`).
- Evidence element IDs: `elem_<doc_id>_p<page>_<kind>_<idx:02d>` (`visual_analyzer.py:246`).
- Summary IDs: `summ_<uuid16>` (`summarizer.py:406`).
- Cache dirs: `<sha256>/<CONFIG_VERSION>` via `cache_dir_for` (`models.py:30`).

**Directories:**
- Lowercase, singular/plural nouns: `tests/`, `docs/`, `scripts/`, `data/`, `models/`, `.cache/`, `.github/workflows/`, `.devcontainer/`, `tests/data/corpus/`, `application_screenshots/`.

## Where to Add New Code

**New Feature (e.g., a new UI capability):**
- Primary code: add domain logic as a new root-level `snake_case.py` module; wire UI into `main.py` (sidebar or the relevant `st.tabs` block at `main.py:629-915`).
- Tests: add `tests/test_<module>.py`, reusing fixtures from `tests/conftest.py`.

**New Component/Module (e.g., a new ingestion extractor or provider):**
- Implementation: a new root-level module following the domain prefix convention (`<backend>_provider.py` for inference, `<source>_reader.py` for extractors).
- For a new inference provider: subclass `BaseModelProvider` (`model_provider.py:64`), implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`, and register it in `AiModel._detect_provider` (`local_llm.py:167`).
- Register any new root module in the `py_modules` list in `setup.py:406-429`.

**New Data Schema:**
- Add the Pydantic model to `models.py` (frozen `ConfigDict` for immutable boundaries), then thread it through `DocStore` if it needs persistence (add a migration list to `MIGRATIONS` in `doc_store.py:96-100`).

**Utilities / Shared Helpers:**
- Shared helpers: `prompt_budget.py` (token/text safety), `models.py` (schemas/path helpers), `resource_telemetry.py` (observability). Add a purpose-specific root module rather than a `utils/` package — the repo uses a flat layout.

**Configuration & Secrets:**
- Never commit secrets; `.env` is gitignored. New cloud keys must follow the resolution precedence in `litellm_provider.py:39-79` (`session_state` → `st.secrets` → `os.environ`).
- New runtime dependencies: add to `requirements.txt` and regenerate `requirements-lock.txt`; test-only deps go in `requirements-test.txt`.

## Special Directories

**`data/`:**
- Purpose: SQLite + LanceDB persistence.
- Generated: Yes (at runtime by `DocStore`/`HybridRetriever`).
- Committed: No (gitignored).

**`.cache/`:**
- Purpose: Per-document JSON extraction cache.
- Generated: Yes (`main.py:534-545`).
- Committed: No (gitignored).

**`models/`:**
- Purpose: Quantized GGUF model weights.
- Generated: Yes (downloaded by `setup.py`).
- Committed: No (gitignored).

**`tests/data/corpus/`:**
- Purpose: Synthetic PDFs (clean digital, scanned, multi-column, dense table, chart/diagram, corrupt) for offline testing.
- Generated: Yes (`tests/data/corpus/generate_corpus.py`); regenerated in CI.
- Committed: Yes (sample PDFs tracked).

**`.devcontainer/`:**
- Purpose: Dev container definition (Python 3.11 image, Streamlit auto-launch on port 8501 with CORS/XSRF disabled).
- Generated: No.
- Committed: Yes.

---

*Structure analysis: 2026-10-17*
