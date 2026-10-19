# Codebase Structure

**Analysis Date:** 2026-10-19

## Directory Layout

```
RAG/
├── main.py                     # Streamlit frontend + application lifecycle (sole UI entry)
├── start.py                    # One-command launcher (pre-flight checks + Streamlit subprocess)
├── setup.py                    # Packaging, dependency install, model/llama-server download CLIs
├── local_llm.py                # AiModel orchestration + InferenceGate
├── model_provider.py           # BaseModelProvider ABC + capability/health schemas
├── llama_cpp_provider.py       # Local llama-server HTTP client (loopback SSRF guard)
├── litellm_provider.py         # LiteLLM cloud adapter (consent gate)
├── groq_provider.py            # Direct Groq SDK adapter
├── doc_store.py                # SQLite metadata/chunk/evidence/summary store
├── hybrid_retriever.py         # LanceDB + BM25 RRF retrieval (JSON fallback)
├── vector_index.py             # Pure-stdlib in-memory vector store
├── local_embedding.py          # SentenceTransformer wrapper + shared process cache
├── docling_reader.py           # Docling layout/table extraction (pypdf fallback)
├── pdf_reader.py               # pypdf extraction + chunking
├── ocr_fallback.py             # Conditional RapidOCR with page-level isolation
├── visual_analyzer.py          # Figure detection, cropping, VLM description
├── summarizer.py               # Single-pass + map-reduce multi-profile summarizer
├── citation_validator.py       # Citation precision / abstention / injection detection
├── prompt_budget.py            # Token budgeting + XML boundary security
├── models.py                   # Canonical Pydantic v2 schemas + cache_dir_for
├── upload_validation.py        # PDF magic-byte/size/page validation + SHA-256
├── resource_telemetry.py       # GPU VRAM, RAM, latency telemetry
├── logging_setup.py            # Streamlit torch.classes watcher-log filter
├── pyproject.toml              # Ruff + pytest configuration
├── requirements.txt            # Runtime deps (>= / == mix)
├── requirements-lock.txt       # Deterministic lockfile (Python 3.11)
├── requirements-test.txt       # Test-only deps
├── Dockerfile                  # python:3.11-slim-bookworm image
├── docker-compose.yml          # app service + optional GPU llama-server profile
├── README.md / CLAUDE.md / LICENSE
├── scripts/                    # Offline benchmark / profiling harnesses
├── tests/                      # pytest suite + synthetic corpus
├── docs/                       # RUNBOOK.md, EVALUATION.md, LOCAL_INFERENCE.md
├── .devcontainer/              # devcontainer.json (auto Streamlit on 8501)
├── .github/workflows/ci.yml    # Lint + format + test
├── models/                     # GGUF weights (gitignored binaries)
├── data/                       # documents.db + lancedb/ persistence
├── tools/llama-server/         # Bundled llama-server binaries + CUDA DLLs
├── .cache/                     # Per-document extraction cache (<sha>/<version>/)
└── .planning/                  # GSD planning artifacts (phases, research, codebase/)
```

## Directory Purposes

**Repository root (`RAG/`):**
- Purpose: Flat application package — every runtime module is a sibling `.py` file imported by name.
- Contains: All 21 application modules, packaging config, tests/scripts/docs as subdirectories.
- Key files: `main.py`, `local_llm.py`, `model_provider.py`, `models.py`.

**`scripts/`:**
- Purpose: Offline evaluation/profiling harnesses (not part of the runtime app).
- Contains: `benchmark_multimodal.py` (quality/grounding), `benchmark_baseline.py` (retrieval latency), `profile_resources.py` (VRAM/RAM); each inserts `REPO_ROOT` onto `sys.path` and writes JSON to `.planning/research/`.

**`tests/`:**
- Purpose: Fully offline pytest suite (~248 tests) with mocked inference/embeddings/GPU.
- Contains: `conftest.py` fixtures (`mock_llama_provider`, `mock_sentence_transformer`, `mock_groq_client`, `sample_pdf_path`), one `test_<module>.py` per application module, and `data/corpus/` synthetic PDFs.
- Key files: `tests/conftest.py`, `tests/data/corpus/generate_corpus.py`.

**`docs/`:**
- Purpose: Operator documentation.
- Contains: `RUNBOOK.md` (install/ops), `EVALUATION.md` (benchmarks), `LOCAL_INFERENCE.md` (llama-server tuning).

**`models/`:**
- Purpose: Local GGUF model weights and multimodal projector.
- Contains: `qwen3-vl-2b-instruct-q4_k_m.gguf`, `mmproj-f16.gguf` (large binaries, not source).

**`data/`:**
- Purpose: Runtime persistence.
- Contains: `documents.db` (SQLite), `lancedb/fallback_store.json` (vector fallback), `lancedb_bench/` (benchmark store).

**`tools/llama-server/`:**
- Purpose: Bundled native `llama-server.exe` + CUDA/ggml DLLs so the launcher works without a system install.
- Contains: Prebuilt binaries (`setup.py:288-289` pins release `b11718`).

**`.cache/`:**
- Purpose: Per-document extraction cache. Layout `<base>/<sha256>/<CONFIG_VERSION>/` with `pages.json`, `chunks.json`, `manifest.json`.

**`.devcontainer/`, `.github/`, `.planning/`:**
- devcontainer auto-launches Streamlit on port 8501; CI runs ruff + pytest on Python 3.11; `.planning/` holds GSD phase/research/state artifacts (not application code).

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit app (page config, sidebar, chat, summarizer, telemetry).
- `start.py`: launcher (`main()`), console script `rag-assistant`.
- `setup.py`: `main_cli`, `download_models_cli`, `setup_llama_server_cli`; console scripts `rag-setup`, `rag-download-models`, `rag-setup-llama`.

**Configuration:**
- `pyproject.toml`: ruff (line-length 120, `E/F/W`) + pytest (`testpaths=["tests"]`).
- `requirements.txt` / `requirements-lock.txt` / `requirements-test.txt`: dependency pins.
- `Dockerfile` / `docker-compose.yml`: container build + GPU llama-server profile.
- `.devcontainer/devcontainer.json`: dev environment + auto-start.
- `.github/workflows/ci.yml`: CI pipeline.
- Env vars: `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, `LLAMA_SERVER_HOST` / `LLAMA_SERVER_PORT`, `USE_TF=0` / `USE_TORCH=1`.

**Core Logic:**
- `main.py`: ingestion loop (`main.py:389-623`) and query loop (`main.py:753-875`), summarizer tab (`main.py:878-973`).
- `local_llm.py`: `AiModel` (`local_llm.py:93-359`) + `InferenceGate` (`local_llm.py:26-90`).
- `model_provider.py`: provider contract.
- `hybrid_retriever.py`: `compute_rrf` (`hybrid_retriever.py:40-85`) + `HybridRetriever` (`hybrid_retriever.py:88-659`).
- `models.py`: canonical schemas.

**Testing:**
- `tests/conftest.py`: shared fixtures/mocking seams.
- `tests/data/corpus/generate_corpus.py`: synthetic corpus generator (CI regenerates before pytest).

## Naming Conventions

**Files:**
- One `snake_case.py` module per concern at repo root; exactly one public class per module where a class exists.
- Tests: `tests/test_<module>.py` mirroring the module under test (e.g. `tests/test_hybrid_retriever.py` ↔ `hybrid_retriever.py`).
- Scripts: `scripts/<verb>_<noun>.py` (`benchmark_baseline.py`, `profile_resources.py`).

**Modules/Classes:**
- Classes: `PascalCase` (`AiModel`, `HybridRetriever`, `DocStore`, `DoclingReader`, `LlamaCppProvider`, `LiteLLMProvider`, `Summarizer`, `VisualAnalyzer`, `OcrEngine`, `VectorIndex`, `LocalEmbedding`).
- Private classes/helpers: underscore prefix (`_process_page_ocr`, `_resolve_api_key_for_model`, `_bM25`-style private methods).

**Symbols:**
- Functions/methods/variables: `snake_case` (`ask_a_question_from_pdf_stream`, `search_hybrid`, `index_chunks`, `indexed_files`, `hybrid_retriever`).
- Constants: `UPPER_CASE` module-level (`MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`, `VALID_SUMMARY_PROFILES`, `KNOWN_CONTEXT_WINDOWS`).
- Pydantic models: `PascalCase` (`Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`, `ProviderCapabilities`, `HealthStatus`).

## Where to Add New Code

**New inference backend (provider):**
- Implementation: add `my_provider.py` at repo root, subclass `BaseModelProvider` (`model_provider.py:64-156`) implementing `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Wire-up: register in `AiModel._detect_provider` (`local_llm.py:168-185`) and expose selection in the sidebar provider map (`main.py:226-230`).
- Tests: `tests/test_my_provider.py` (mirror `tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py`).

**New ingestion extractor:**
- Implementation: root module returning canonical `Chunk`/`Page` (`models.py`), following the isolate-and-continue pattern of `ocr_fallback.py` / `docling_reader.py`.
- Wire-up: call from the upload loop between extraction and persistence (`main.py:466-527`) and add the backend tag to `Chunk.extraction`.
- Tests: `tests/test_<extractor>.py` using `tests/data/corpus/` PDFs.

**New retrieval strategy / storage:**
- Implementation: extend `hybrid_retriever.py` (or add a peer module) returning `RetrievalResult`; keep the `VectorIndex` fallback path intact.
- Wire-up: consumed by `main.py:777-781` and `local_llm.py:263-279`; both dispatch on `search_hybrid`.
- Tests: `tests/test_hybrid_retriever.py`.

**New canonical schema:**
- Implementation: add a Pydantic model to `models.py` (frozen + `extra="forbid"` for immutable value objects; add `model_validator` for ID prefixes).
- Persistence: add a versioned DDL block to `doc_store.py` via the `MIGRATIONS` dict (`doc_store.py:96-100`) and a `record_*`/`get_*` pair.
- Tests: `tests/test_models.py`, `tests/test_doc_store.py`.

**New UI feature:**
- Implementation: add a `with st.tabs(...)` pane or sidebar block in `main.py`; register any new `st.session_state` keys in the init loop (`main.py:115-131`); never place `st.*` calls above `st.set_page_config` (`main.py:101-106`).
- Tests: `tests/test_main_ui.py`.

**Utilities / support:**
- Shared helpers: `prompt_budget.py` (token/security), `resource_telemetry.py` (metrics), `logging_setup.py` (log filtering), `upload_validation.py` (edge validation).

**New benchmark/eval script:**
- Implementation: `scripts/<name>.py`, insert `REPO_ROOT` on `sys.path`, write JSON to `.planning/research/`.

## Special Directories

**`.cache/`:**
- Purpose: Per-document extraction artifacts keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes (`main.py:579-590`; path via `models.cache_dir_for`).
- Committed: No (purged by `Purge All Data`, `main.py:371-375`).

**`data/`:**
- Purpose: SQLite DB + LanceDB/JSON vector persistence.
- Generated: Yes at runtime (`doc_store.py:108-120`, `hybrid_retriever.py:121-133`).
- Committed: `data/documents.db` and `data/lancedb/fallback_store.json` are present in the tree but are runtime state.

**`models/`:**
- Purpose: GGUF model weights.
- Generated: No — downloaded via `python setup.py download_models` (`setup.py:586-609`).
- Committed: Binaries present locally; typically gitignored.

**`tools/llama-server/`:**
- Purpose: Bundled native llama.cpp runtime.
- Generated: No — acquired via `python setup.py setup_llama_server` (`setup.py:612-635`).
- Committed: Binaries present locally; typically gitignored.

**`.planning/`:**
- Purpose: GSD workflow artifacts (PROJECT.md, ROADMAP.md, REQUIREMENTS.md, STATE.md, `phases/`, `research/`, `codebase/`, `debug/`).
- Generated: Yes (by GSD commands).
- Committed: Per `.planning/config.json` (`commit_docs: true`).

---

*Structure analysis: 2026-10-19*
