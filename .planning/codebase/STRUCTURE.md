# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
RAG/
├── main.py                      # Streamlit entry point + UI orchestration
├── local_llm.py                 # AiModel orchestrator (provider select, retrieval, stream)
├── model_provider.py            # BaseModelProvider ABC + ProviderCapabilities/HealthStatus
├── groq_provider.py             # Groq Cloud provider implementation
├── llama_cpp_provider.py        # Local llama-server HTTP provider implementation
├── prompt_budget.py             # Token budgeting + <document_context> injection isolation
├── local_embedding.py           # SentenceTransformer wrapper + index facade
├── vector_index.py              # Pure-stdlib in-memory vector store
├── pdf_reader.py                # pypdf extraction + langchain chunking
├── doc_store.py                 # SQLite (WAL) document/page/chunk persistence
├── models.py                    # Canonical Pydantic schemas + cache path helper
├── upload_validation.py         # %PDF/size/pages validation + SHA-256 doc_id
├── requirements.txt             # Pinned runtime dependencies
├── requirements-test.txt        # Test/benchmark dependencies (pytest, reportlab, ruff, psutil)
├── pyproject.toml               # ruff + pytest configuration only
├── README.md                    # User-facing docs (partially stale — see CONCERNS.md)
├── CLAUDE.md                    # Agent instructions with embedded codebase-map snapshots
├── scripts/
│   └── benchmark_baseline.py    # Offline latency/memory benchmark harness
├── tests/
│   ├── conftest.py              # Shared fixtures + offline mocking seams
│   ├── test_*.py                # 11 unit-test modules (one per root module)
│   └── data/corpus/
│       ├── generate_corpus.py   # reportlab generator for 6 synthetic PDFs
│       └── *.pdf                # Generated corpus (gitignored / regenerated)
├── docs/
│   └── LOCAL_INFERENCE.md       # Qwen3-VL/llama-server runbook (4 GB VRAM)
├── application_screenshots/     # README images
├── .github/workflows/ci.yml     # Lint + test CI
├── .devcontainer/               # Python 3.11 devcontainer + Streamlit auto-launch
└── .planning/                   # GSD planning artifacts (codebase maps, phases, research)
```

## Directory Purposes

**Repository root (`/`):**
- Purpose: Flat module layout — one public class per file, no packages.
- Contains: all 12 importable modules plus config files.
- Key files: `main.py` (entry), `local_llm.py` (orchestrator), `models.py` (schemas), `doc_store.py` (persistence).

**`scripts/`:**
- Purpose: Out-of-band developer tooling.
- Contains: `benchmark_baseline.py` (adds repo root to `sys.path`, measures extraction/chunk/embed/scan latency and RSS).
- Key files: `scripts/benchmark_baseline.py`

**`tests/`:**
- Purpose: pytest suite mirroring root modules 1:1.
- Contains: `conftest.py` fixtures (`fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`), plus one `test_<module>.py` per root module.
- Key files: `tests/conftest.py`, `tests/test_local_llm.py`, `tests/test_llama_cpp_provider.py`

**`tests/data/corpus/`:**
- Purpose: Synthetic PDF fixtures covering document archetypes.
- Contains: `generate_corpus.py` (reportlab) producing `clean_digital.pdf` (20 pages), `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`.
- Generated: Yes. Committed: generated PDFs are gitignored; only the generator is tracked.

**`docs/`:**
- Purpose: Operational runbooks.
- Contains: `docs/LOCAL_INFERENCE.md` — model download, `llama-server` launch flags, VRAM budget, health probe, troubleshooting.

**`.planning/`:**
- Purpose: GSD workflow artifacts.
- Contains: `codebase/` (these maps), `phases/`, `research/` (incl. `BASELINE_BENCHMARK.json`), `PROJECT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `STATE.md`, `config.json`.

**`.github/workflows/`:**
- Purpose: CI.
- Contains: `ci.yml` — ruff lint/format, corpus generation, pytest.

**`.devcontainer/`:**
- Purpose: Reproducible dev environment.
- Contains: `devcontainer.json` — Python 3.11 image, pip install hook, Streamlit launch on port 8501.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit app (`streamlit run main.py`) — must keep `st.set_page_config` as the first Streamlit call (`main.py:35`).
- `scripts/benchmark_baseline.py`: `python scripts/benchmark_baseline.py`.
- `tests/data/corpus/generate_corpus.py`: `python tests/data/corpus/generate_corpus.py`.

**Configuration:**
- `pyproject.toml`: `[tool.ruff]` (line-length 120, select E/F/W, ignore E501/W291/W293) and `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `python_files=["test_*.py"]`).
- `requirements.txt` / `requirements-test.txt`: dependency declarations.
- `.devcontainer/devcontainer.json`: dev environment + auto-launch command.
- `.github/workflows/ci.yml`: lint/test pipeline.
- `.env`: local `GROQ_API_KEY` (gitignored, not committed).

**Core Logic:**
- `main.py`: UI + ingestion/query orchestration.
- `local_llm.py`: `AiModel` — provider selection, retrieval, prompt assembly, streaming.
- `model_provider.py`: provider contract + capability/health schemas.
- `llama_cpp_provider.py` / `groq_provider.py`: concrete backends.
- `prompt_budget.py`: context budgeting + injection isolation.
- `models.py`: canonical schemas + `cache_dir_for`.
- `doc_store.py`: SQLite persistence.
- `upload_validation.py` / `pdf_reader.py`: ingestion front end.
- `local_embedding.py` / `vector_index.py`: retrieval.

**Testing:**
- `tests/conftest.py`: fixtures and mocking seams for fully offline runs.
- `tests/test_*.py`: unit tests per module.

## Naming Conventions

**Files:**
- Root modules: flat `snake_case.py`, one public class per file, no packages/`__init__.py` (`main.py`, `local_llm.py`, `model_provider.py`, …).
- Tests: `test_<module>.py` mirroring the module under test (`tests/test_doc_store.py`, `tests/test_vector_index.py`).
- Docs: `UPPER_SNAKE.md` for planning maps (`STACK.md`), `TitleCase.md` for runbooks (`docs/LOCAL_INFERENCE.md`).

**Directories:**
- Lowercase, singular-purpose (`scripts/`, `tests/`, `docs/`); planning dirs under `.planning/` are hyphenated lowercase (`phases/`, `codebase/`, `research/`).

## Where to Add New Code

**New inference backend:**
- Implementation: new root module `x_provider.py` subclassing `BaseModelProvider` (`model_provider.py:59`), returning `ProviderCapabilities`/`HealthStatus`.
- Wiring: extend `AiModel._detect_provider` (`local_llm.py:36`) or inject via `AiModel(provider=...)`.
- Tests: `tests/test_x_provider.py` mocking HTTP with `httpx.MockTransport` (see `tests/test_llama_cpp_provider.py`).

**New canonical model:**
- Implementation: add to `models.py` with `ConfigDict(frozen=True, extra="forbid")` and Pydantic validators; keep legacy dict-key compatibility in `model_dump()`.
- Tests: `tests/test_models.py`.

**New ingestion/extraction stage:**
- Implementation: extend `pdf_reader.py` and record `Page` status through `doc_store.record_page`; keep per-page fault isolation.
- Tests: `tests/test_pdf_reader.py`; add corpus archetypes in `tests/data/corpus/generate_corpus.py`.

**New UI section:**
- Implementation: `main.py` — add session-state keys to the init loop (`main.py:49-57`), render inside `with st.sidebar:` or the main area, end batch updates with `st.rerun()`.

**Shared helpers:**
- Prefer extending the owning module; there is no generic `utils.py`. Pure helpers live next to their domain (`models.cache_dir_for`, `upload_validation.sha256_bytes`).

## Special Directories

**`data/`:**
- Purpose: `documents.db` SQLite database at runtime.
- Generated: Yes. Committed: No (`.gitignore:9`).

**`.cache/`:**
- Purpose: per-document JSON cache (`pages.json`, `chunks.json`, `manifest.json`) keyed by `sha256/<CONFIG_VERSION>`.
- Generated: Yes. Committed: No (`.gitignore:18`).

**`tests/__pycache__`, `.pytest_cache`, `.ruff_cache`:**
- Generated: Yes. Committed: No.

**`tests/data/corpus/*.pdf`:**
- Generated by `generate_corpus.py`. Committed: No — CI regenerates before running tests.

---

*Structure analysis: 2026-10-11*
