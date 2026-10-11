# Technology Stack

**Analysis Date:** 2026-10-11

## Languages

**Primary:**
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `models.py`, `doc_store.py`, `upload_validation.py`)
  - Devcontainer pins Python 3.11 (`mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` in `.devcontainer/devcontainer.json:4`)
  - CI pins Python 3.11 via `actions/setup-python@v5` (`.github/workflows/ci.yml:18-22`)
  - Ruff targets `py311` (`pyproject.toml:3`)
- Python 3.11+ — all test code (`tests/conftest.py`, `tests/test_vector_index.py`, `tests/test_pdf_reader.py`, `tests/test_local_embedding.py`, `tests/test_local_llm.py`, `tests/test_models.py`, `tests/test_doc_store.py`, `tests/test_upload_validation.py`, `tests/data/corpus/generate_corpus.py`)
- Python 3.11+ — benchmark script (`scripts/benchmark_baseline.py`)

**Secondary:**
- JSON — devcontainer config only (`.devcontainer/devcontainer.json`), benchmark report output (`.planning/research/BASELINE_BENCHMARK.json`), disk-cache artifacts (`pages.json`, `chunks.json`, `manifest.json` under `.cache/`)
- SQL (DDL strings only) — schema/migration statements inside `doc_store.py:16-54` executed via stdlib `sqlite3`; no `.sql` files, no ORM
- Markdown — docs only (`README.md`)
- YAML — CI pipeline only (`.github/workflows/ci.yml`)
- TOML — lint/test config only (`pyproject.toml`)
- No JavaScript/TypeScript, no CSS — UI is 100% Streamlit Python

## Runtime

**Environment:**
- Local: CPython via `streamlit run main.py` (entry documented in `README.md:186`, `README.md:194`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py` (`.devcontainer/devcontainer.json:7-10`), serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:21-22`)
- Production: Streamlit Community Cloud (live demo at `https://rag1818.streamlit.app/` per `README.md:7`); no Dockerfile, no `packages.txt`, no `runtime.txt`
- CI: `ubuntu-latest` runner with Python 3.11 (`.github/workflows/ci.yml:12,18-22`)

**Package Manager:**
- pip with pinned `requirements.txt` (runtime) + lower-bounded `requirements-test.txt` (test/bench)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`)
- CI installs both files in one step: `pip install -r requirements.txt` then `pip install -r requirements-test.txt` (`.github/workflows/ci.yml:24-28`)

## Frameworks

**Core:**
- Streamlit `1.42.0` — entire UI layer: `st.set_page_config` (`main.py:35-40`), sidebar (`main.py:80-266`), `st.file_uploader` (`main.py:106-112`), `st.chat_input` / `st.chat_message` (`main.py:286-313`), `st.status` (`main.py:87`, `main.py:116`), `st.cache_resource` (`main.py:65-73`), `st.write_stream` (`main.py:327`), `st.secrets` (`local_llm.py:26`)

**Data validation:**
- pydantic `2.11.9` (pinned `==` in `requirements.txt:8`) — canonical schemas in `models.py:11` (`BaseModel`, `ConfigDict`, `Field`); models `BBox` (`models.py:33-51`, frozen), `Chunk` (`models.py:54-72`, frozen + `extra="forbid"`), `Page` (`models.py:75-87`, `extra="forbid"`), `EvidenceElement` (`models.py:90-105`), `Document` (`models.py:108-131`, `extra="forbid"`, sha256 regex `^[0-9a-f]{64}$`); config constant `CONFIG_VERSION = "chunker-1000-200-pypdf"` (`models.py:14`); disk-cache path helper `cache_dir_for(base, sha256)` → `base / sha256 / CONFIG_VERSION` (`models.py:17-30`)

**Persistence (stdlib, not a framework):**
- sqlite3 (CPython standard library — no pip package, no version pin) — `DocStore` in `doc_store.py:61-307`: per-operation connections with `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` (`doc_store.py:89-92`), schema-versioned migrations via `PRAGMA user_version` (`doc_store.py:98-111`), three tables `documents` / `pages` / `chunks` (`doc_store.py:16-54`, `MIGRATIONS = {1: SCHEMA_V1_DDL}` at `doc_store.py:56-58`); DB file `data/documents.db` created on first upload (`main.py:118`); `data/` is gitignored (`.gitignore:10`) and absent from a fresh checkout (verified — no `data/` directory exists until first upload)

**ML / Data:**
- sentence-transformers `3.4.1` — local embedding model wrapper (`local_embedding.py:7,22`); default model `all-MiniLM-L6-v2` (`local_embedding.py:12`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,39`)
- numpy `>=1.26.0,<3.0.0` (range-pinned in `requirements.txt:7`) — runtime transitive dependency of sentence-transformers; used directly only in test/benchmark code: deterministic pseudo-embeddings in `tests/conftest.py:8,59-74` and RSS/sample-vector helpers in `scripts/benchmark_baseline.py`
- No FAISS / scikit-learn as direct deps — `vector_index.py:11-12` is pure Python stdlib (`math`, `typing` only); transitive deps (torch, transformers, huggingface-hub, tokenizers) arrive via sentence-transformers but are not pinned here

**PDF / Text:**
- pypdf `5.3.0` — PDF text extraction via `pypdf.PdfReader` (`pdf_reader.py:3,16`); also used for the upload-validation page-count probe (`upload_validation.py:12,91`)
- langchain-text-splitters `0.3.6` — chunking via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:5,35-39`)
- reportlab (test-only, `>=4.2.0` in `requirements-test.txt:3`) — synthetic test-corpus generation (`tests/data/corpus/generate_corpus.py`); installed in CI via `requirements-test.txt`; never imported by application code

**LLM client:**
- groq `0.15.0` — cloud inference client `groq.Groq` (`local_llm.py:7,34`); guarded `try/except ImportError` with explicit install hint (`local_llm.py:6-9,21-22`)

**Config:**
- python-dotenv `1.0.1` — local `.env` loading via `load_dotenv()` (`main.py:21,72`)

**Testing:**
- pytest `>=8.3.0` (in `requirements-test.txt:2`) — test runner; executed as `pytest tests/ -v` (`.github/workflows/ci.yml:39-41`); configured in `pyproject.toml:13-20` (`testpaths=["tests"]`, `python_files=["test_*.py"]`, `python_functions=["test_*"]`, `UserWarning`/`DeprecationWarning` filters ignored); 54 tests across 7 files (`test_models.py` ×15, `test_pdf_reader.py` ×9, `test_doc_store.py` ×9, `test_upload_validation.py` ×8, `test_vector_index.py` ×7, `test_local_embedding.py` ×3, `test_local_llm.py` ×3 — counted from disk via AST)
- psutil `>=6.1.0` (in `requirements-test.txt:5`) — process/RSS/CPU profiling in the benchmark: `psutil.Process().memory_info().rss` (`scripts/benchmark_baseline.py:13,24`)

**Linting:**
- ruff `>=0.9.0` (in `requirements-test.txt:4`) — sole linter + formatter; CI runs `ruff check .` and `ruff format --check .` (`.github/workflows/ci.yml:30-33`); configured in `pyproject.toml:1-10` (`line-length=120`, `target-version="py311"`, rules `E,F,W` with `E501,W291,W293` ignored, per-file ignore `scripts/*: E402`)
- No mypy / pyright / pylint / flake8 / bandit config detected

## Key Dependencies

Pinned in `requirements.txt` (8 lines total):

| Package | Version | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` | `main.py:22`, `local_llm.py:2` | UI runtime; app does not run without it |
| `pypdf` | `==5.3.0` | `pdf_reader.py:3,16`, `upload_validation.py:12,91` | PDF parsing + validation page-count probe; accepts file path or `BytesIO` stream (`main.py:178-179`, `pdf_reader.py:12`) |
| `python-dotenv` | `==1.0.1` | `main.py:21,72` | Loads `.env` for local dev before `AiModel()` reads env |
| `langchain-text-splitters` | `==0.3.6` | `pdf_reader.py:5,35` | Only langchain component used — chunking only, no chains/agents |
| `groq` | `==0.15.0` | `local_llm.py:7,34,75-80` | LLM inference; streaming chat completions endpoint |
| `sentence-transformers` | `==3.4.1` | `local_embedding.py:7,22,39` | Embedding inference; triggers HuggingFace model download on first run |
| `numpy` | `>=1.26.0,<3.0.0` | Transitive via sentence-transformers; direct use only in `tests/conftest.py`, `scripts/benchmark_baseline.py` | Vector math backing for embeddings |
| `pydantic` | `==2.11.9` | `models.py:11`, consumed by `pdf_reader.py:7`, `doc_store.py:14`, `main.py:27` | Schema validation for `Chunk`/`Page`/`Document`; `model_dump`/`model_validate` bridge between SQLite rows, disk-cache JSON, and vector-index dicts |

**Test/bench-only (`requirements-test.txt`, 4 lower-bounded entries):**

| Package | Pin | Where used | Why it matters |
|---|---|---|---|
| `pytest` | `>=8.3.0` | `tests/test_*.py` (7 files, 54 tests), config `pyproject.toml:13-20` | Test runner; `pytest tests/ -v` is the CI gate |
| `reportlab` | `>=4.2.0` | `tests/data/corpus/generate_corpus.py` | Generates 6 synthetic corpus PDFs; CI runs `python tests/data/corpus/generate_corpus.py` before pytest (`.github/workflows/ci.yml:35-37`) |
| `ruff` | `>=0.9.0` | Config `pyproject.toml:1-10`, CI step `.github/workflows/ci.yml:30-33` | Lint + format gate (`ruff check .`, `ruff format --check .`) |
| `psutil` | `>=6.1.0` | `scripts/benchmark_baseline.py:13,24` | RSS/CPU/RAM profiling for the baseline benchmark report |

**Transitive (unpinned, pulled automatically):**
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — via sentence-transformers; model weights cached in `~/.cache/huggingface/` (`README.md:199`)

**Standard library (no install, no pin):**
- `sqlite3` — `DocStore` persistence (`doc_store.py:12`); WAL mode + busy timeout per connection (`doc_store.py:89-92`)
- `hashlib` — streaming SHA-256 in 1 MiB slices (`upload_validation.py:9,29-33`)
- `dataclasses` — frozen `ValidatedUpload` record (`upload_validation.py:8,51-61`)
- `pathlib`, `io`, `re`, `math`, `typing`, `datetime`, `json` — supporting roles in `main.py`, `pdf_reader.py`, `vector_index.py`

## Configuration

**Environment:**
- Local dev: `.env` file in project root containing `GROQ_API_KEY` (`README.md:181`); loaded by `load_dotenv()` in `load_ai_model()` (`main.py:72`); `.env` is gitignored (`.gitignore:1`) and absent from working tree (verified)
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]` tried first in `local_llm.py:26`); no `.streamlit/secrets.toml` committed (verified — no `.streamlit/` directory)
- Tests set a fake key via `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")` (`tests/conftest.py:15`) and delete it to assert the missing-key guard (`tests/test_local_llm.py`)

**Upload caps (`upload_validation.py:15-16`):**
- `MAX_FILE_MB: int = 50` — enforced twice: pre-buffer via `uploaded_file.size` (`main.py:124-132`) and post-buffer via `len(raw)` (`upload_validation.py:83-87`)
- `MAX_PAGES: int = 500` — enforced via pypdf page-count probe (`upload_validation.py:91-100`)

**Lint / test config (`pyproject.toml`, 20 lines total):**
- `[tool.ruff]`: `line-length = 120`, `target-version = "py311"` (`pyproject.toml:1-3`)
- `[tool.ruff.lint]`: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` (`pyproject.toml:5-7`)
- `[tool.ruff.lint.per-file-ignores]`: `scripts/* → ["E402"]` (allows the `sys.path.insert` before imports in `scripts/benchmark_baseline.py:16-17`) (`pyproject.toml:9-10`)
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings` ignores `UserWarning` + `DeprecationWarning` (`pyproject.toml:13-20`)

**CI config (`.github/workflows/ci.yml`, 41 lines total):**
- Triggers: `push` + `pull_request` on `main` (`.github/workflows/ci.yml:3-7`)
- Job `test` on `ubuntu-latest`, Python 3.11 with pip cache (`.github/workflows/ci.yml:10-22`)
- Steps in order: checkout (`actions/checkout@v4`) → setup-python (`actions/setup-python@v5`) → install `requirements.txt` + `requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v` (`.github/workflows/ci.yml:15-41`)

**Build:**
- No build step — interpreted Python, no bundler, no `setup.py`/`Makefile`; `pyproject.toml` holds tool config only (no `[project]`/`[build-system]` tables)
- Devcontainer bootstrap: `[ -f requirements.txt ] && pip3 install --user -r requirements.txt; pip3 install --user streamlit` (`.devcontainer/devcontainer.json:20`) — note: does not install `requirements-test.txt` separately

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download (`README.md:176`)
- A Groq API key (free at `console.groq.com`, `README.md:158`); HuggingFace token never read in code; public `all-MiniLM-L6-v2` model needs no token
- Run: `pip install -r requirements.txt` then `streamlit run main.py` (`README.md:173-186`)
- Tests: `pip install -r requirements.txt -r requirements-test.txt`, then `python tests/data/corpus/generate_corpus.py` followed by `pytest tests/ -v` (mirrors `.github/workflows/ci.yml:24-41`)
- Benchmark: `python scripts/benchmark_baseline.py` (requires `psutil` + generated corpus + `sentence-transformers` model download; writes `.planning/research/BASELINE_BENCHMARK.json` per `scripts/benchmark_baseline.py:1-6`)

**Production:**
- Streamlit Community Cloud hosting Streamlit `1.42.0` app with `GROQ_API_KEY` set in the Cloud secrets panel; HuggingFace model re-downloaded and cached on first container boot (`README.md:199`); vector index is in-memory only per session, but document/page/chunk metadata persists in SQLite (`data/documents.db`) and best-effort JSON under `.cache/` — neither is guaranteed a persistent volume on Community Cloud, so re-upload may still be required after restarts

## Entry Points

| Entry | Command | File |
|---|---|---|
| Streamlit app (sole app entry point) | `streamlit run main.py` | `main.py` (329 lines) |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:21-23` |
| Benchmark script | `python scripts/benchmark_baseline.py` | `scripts/benchmark_baseline.py` (174 lines) |
| Corpus generator | `python tests/data/corpus/generate_corpus.py` | `tests/data/corpus/generate_corpus.py` |
| Test suite | `pytest tests/ -v` | `tests/test_models.py` (15 tests), `tests/test_pdf_reader.py` (9), `tests/test_doc_store.py` (9), `tests/test_upload_validation.py` (8), `tests/test_vector_index.py` (7), `tests/test_local_embedding.py` (3), `tests/test_local_llm.py` (3) — 54 tests total |
| No CLI / module entry | No `if __name__ == "__main__"` in app modules, no `__main__.py`, no console-scripts | Not applicable |

**Module roles:**
- `main.py` (329 lines) — Streamlit front-end, session state, validate → dedup → extract → persist → index → chat → stream orchestration
- `models.py` (131 lines) — Pydantic v2 canonical schemas (`BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`) + `CONFIG_VERSION` + `cache_dir_for` helper
- `doc_store.py` (307 lines) — `DocStore` class: SQLite metadata persistence (`upsert_document`, `get_document`, `get_by_sha`, `list_documents`, `record_page`, `record_chunks`, `get_chunks_for_doc`)
- `upload_validation.py` (113 lines) — server-side upload gate: `%PDF` magic check, 50 MB / 500-page caps, streaming SHA-256, `doc_id_for` stable IDs, frozen `ValidatedUpload` record
- `local_llm.py` (84 lines) — `AiModel` class: Groq client init + `ask_a_question_from_pdf_stream` generator
- `local_embedding.py` (71 lines) — `LocalEmbedding` class: sentence-transformers wrapper + batch `build_index`
- `vector_index.py` (228 lines) — `VectorIndex` class: pure-stdlib in-memory cosine/Euclidean store
- `pdf_reader.py` (149 lines) — `PdfReader` class: pypdf extraction with per-page fault isolation (`Page` records) + langchain chunking emitting `Chunk.model_dump()` dicts with `doc_id` and hash-prefixed `chunk_id`
- `tests/conftest.py` (88 lines) — shared fixtures: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`
- `tests/data/corpus/` — 6 synthetic PDFs (`clean_digital.pdf` 20 pages, `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`) + `generate_corpus.py`
- `scripts/benchmark_baseline.py` (174 lines) — 4-stage perf benchmark (extraction → chunking → CPU embedding → linear-scan) writing `.planning/research/BASELINE_BENCHMARK.json`

---

*Stack analysis: 2026-10-11*
