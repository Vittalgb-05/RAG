# Technology Stack

**Analysis Date:** 2026-10-11

## Languages

**Primary:**
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`)
  - Devcontainer pins Python 3.11 (`mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` in `.devcontainer/devcontainer.json:4`)
  - CI pins Python 3.11 via `actions/setup-python@v5` (`.github/workflows/ci.yml:18-21`)
  - Ruff targets `py311` (`pyproject.toml:3`)
- Python 3.11+ — all test code (`tests/conftest.py`, `tests/test_vector_index.py`, `tests/test_pdf_reader.py`, `tests/test_local_embedding.py`, `tests/test_local_llm.py`, `tests/data/corpus/generate_corpus.py`)
- Python 3.11+ — benchmark script (`scripts/benchmark_baseline.py`)

**Secondary:**
- JSON — devcontainer config only (`.devcontainer/devcontainer.json`)
- Markdown — docs only (`README.md`)
- YAML — CI pipeline only (`.github/workflows/ci.yml`)
- TOML — lint/test config only (`pyproject.toml`)
- No JavaScript/TypeScript, no CSS, no SQL — UI is 100% Streamlit Python

## Runtime

**Environment:**
- Local: CPython via `streamlit run main.py` (entry documented in `main.py:252-253`, `README.md:186`, `README.md:194`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py` (`.devcontainer/devcontainer.json:7-10`), serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:22-23,30-32`)
- Production: Streamlit Community Cloud (live demo at `https://rag1818.streamlit.app/` per `README.md:7`); no Dockerfile, no `packages.txt`, no `runtime.txt`
- CI: `ubuntu-latest` runner with Python 3.11 (`.github/workflows/ci.yml:12,18-21`)

**Package Manager:**
- pip with pinned `requirements.txt` (all `==` pins)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`; activation documented as `source .venv/Scripts/activate` on Windows Git Bash in `main.py:252`, `README.md:169`)
- CI installs runtime + test deps in one step: `pip install -r requirements.txt` then `pip install pytest pytest-mock reportlab ruff psutil` (`.github/workflows/ci.yml:24-28`)

## Frameworks

**Core:**
- Streamlit `1.42.0` — entire UI layer: `st.set_page_config` (`main.py:30-35`), sidebar (`main.py:88-175`), `st.file_uploader` (`main.py:114-120`), `st.chat_input` / `st.chat_message` (`main.py:197-212`), `st.status` (`main.py:96`, `main.py:124`), `st.cache_resource` (`main.py:59-67`), `st.write_stream` (`main.py:239`), `st.secrets` (`local_llm.py:25`)

**ML / Data:**
- sentence-transformers `3.4.1` — local embedding model wrapper (`local_embedding.py:7,23`); default model `all-MiniLM-L6-v2` (`local_embedding.py:13`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,40`)
- No NumPy / FAISS / scikit-learn as direct runtime deps — `vector_index.py:8` is pure Python stdlib (`math`, `typing` only, `vector_index.py:11-12`); transitive deps (torch, transformers, huggingface-hub) arrive via sentence-transformers but are not pinned here
- NumPy is used in test/benchmark code only: deterministic pseudo-embeddings in `tests/conftest.py:9,66-75` and random-vector scan fixtures in `scripts/benchmark_baseline.py:97-108` (NumPy arrives transitively via sentence-transformers/pytest stack; not pinned in `requirements.txt`)

**PDF / Text:**
- pypdf `5.3.0` — PDF text extraction via `pypdf.PdfReader` (`pdf_reader.py:2,14`)
- langchain-text-splitters `0.3.6` — chunking via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:5,31-35`)
- reportlab (unpinned, CI/test-only) — synthetic test-corpus generation via `SimpleDocTemplate`, `canvas`, `Table`/`TableStyle` (`tests/data/corpus/generate_corpus.py:8-19`); installed in CI via `pip install ... reportlab ...` (`.github/workflows/ci.yml:28`); never imported by application code

**LLM client:**
- groq `0.15.0` — cloud inference client `groq.Groq` (`local_llm.py:7-9,33`); guarded `try/except ImportError` with explicit install hint (`local_llm.py:6-9,20-21`)

**Config:**
- python-dotenv `1.0.1` — local `.env` loading via `load_dotenv()` (`main.py:19,66`)

**Testing:**
- pytest (unpinned, CI/test-only) — test runner; installed in CI (`.github/workflows/ci.yml:28`), executed as `pytest tests/ -v` (`.github/workflows/ci.yml:38-40`); configured in `pyproject.toml:13-20` (`testpaths=["tests"]`, `python_files=["test_*.py"]`, `python_functions=["test_*"]`, `UserWarning`/`DeprecationWarning` filters ignored)
- pytest-mock (unpinned, CI/test-only) — mock fixture plugin; installed in CI (`.github/workflows/ci.yml:28`); the suite currently uses stdlib `unittest.mock.MagicMock` + `monkeypatch` directly (`tests/conftest.py:8`, `tests/test_local_llm.py:7`) rather than the `mocker` fixture
- psutil (unpinned, script-only) — process masking/memory profiling in the benchmark: `psutil.Process().memory_info().rss`, `psutil.cpu_count`, `psutil.virtual_memory` (`scripts/benchmark_baseline.py:13,24,133-134`); installed in CI (`.github/workflows/ci.yml:28`)

**Linting:**
- ruff (unpinned, CI-only) — sole linter; installed in CI (`.github/workflows/ci.yml:28`), executed as `ruff check .` (`.github/workflows/ci.yml:30-32`); configured in `pyproject.toml:1-11` (`line-length=120`, `target-version="py311"`, rules `E,F,W` with `E501,W291,W293` ignored, per-file ignores `scripts/*: E402` and `tests/*: F401,F841`)
- No mypy / pyright / pylint / flake8 / bandit config detected

## Key Dependencies

Pinned in `requirements.txt` (6 lines total):

| Package | Version | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` | `main.py:18`, `local_llm.py:2` | UI runtime; app does not run without it |
| `pypdf` | `==5.3.0` | `pdf_reader.py:2,14` | PDF parsing; accepts file path or `BytesIO` stream (`main.py:132-135`, `pdf_reader.py:11`) |
| `python-dotenv` | `==1.0.1` | `main.py:19,66` | Loads `.env` for local dev before `AiModel()` reads env |
| `langchain-text-splitters` | `==0.3.6` | `pdf_reader.py:5,31` | Only langchain component used — chunking only, no chains/agents |
| `groq` | `==0.15.0` | `local_llm.py:7,33,73-78` | LLM inference; streaming chat completions endpoint |
| `sentence-transformers` | `==3.4.1` | `local_embedding.py:7,23,40` | Embedding inference; triggers HuggingFace model download on first run |

**Dev / CI-only (unpinned, installed in `.github/workflows/ci.yml:28`):**

| Package | Where used | Why it matters |
|---|---|---|
| `pytest` | `tests/test_*.py` (4 files, 16 tests), config `pyproject.toml:13-20` | Test runner; `pytest tests/ -v` is the CI gate |
| `pytest-mock` | Installed but no `mocker` fixture used yet; suite uses `unittest.mock` + `monkeypatch` (`tests/conftest.py:8`) | Reserved mock plugin for future tests |
| `reportlab` | `tests/data/corpus/generate_corpus.py:8-19` | Generates 6 synthetic corpus PDFs; CI runs `python tests/data/corpus/generate_corpus.py` before pytest (`.github/workflows/ci.yml:34-36`) |
| `ruff` | Config `pyproject.toml:1-11`, CI step `.github/workflows/ci.yml:30-32` | Lint gate (`ruff check .`) runs before tests |
| `psutil` | `scripts/benchmark_baseline.py:13,24,133-134` | RSS/CPU/RAM profiling for the baseline benchmark report |

**Transitive (unpinned, pulled automatically):**
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — via sentence-transformers; model weights cached in `~/.cache/huggingface/` (`README.md:199`)
- `numpy` — via sentence-transformers/pytest stack; used directly only in `tests/conftest.py` and `scripts/benchmark_baseline.py`

## Configuration

**Environment:**
- Local dev: `.env` file in project root containing `GROQ_API_KEY` (`README.md:178-182`); loaded by `load_dotenv()` in `load_ai_model()` (`main.py:66`); `.env` is gitignored (`.gitignore:1`) and absent from working tree
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]` tried first in `local_llm.py:25`); no `.streamlit/secrets.toml` committed (no `.streamlit/` directory)
- Tests set a fake key via `monkeypatch.setenv("GROQ_API_KEY", "gsk_mock_test_key_...")` (`tests/conftest.py:13-16`) and delete it to assert the missing-key guard (`tests/test_local_llm.py:11-18`)

**Lint / test config (`pyproject.toml`, 20 lines total):**
- `[tool.ruff]`: `line-length = 120`, `target-version = "py311"` (`pyproject.toml:1-3`)
- `[tool.ruff.lint]`: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` (`pyproject.toml:5-7`)
- `[tool.ruff.lint.per-file-ignores]`: `scripts/* → ["E402"]` (allows the `sys.path.insert` before imports in `scripts/benchmark_baseline.py:16-20`), `tests/* → ["F401", "F841"]` (`pyproject.toml:9-11`)
- `[tool.pytest.ini_options]`: `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings` ignores `UserWarning` + `DeprecationWarning` (`pyproject.toml:13-20`)

**CI config (`.github/workflows/ci.yml`, 40 lines total):**
- Triggers: `push` + `pull_request` on `main` (`.github/workflows/ci.yml:3-7`)
- Job `test` on `ubuntu-latest`, Python 3.11 with pip cache (`.github/workflows/ci.yml:10-22`)
- Steps in order: checkout (`actions/checkout@v4`) → setup-python (`actions/setup-python@v5`) → install runtime+test deps → `ruff check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v` (`.github/workflows/ci.yml:14-40`)

**Build:**
- No build step — interpreted Python, no bundler, no `setup.py`/`Makefile`; `pyproject.toml` holds tool config only (no `[project]`/`[build-system]` tables)
- Devcontainer bootstrap: `[ -f requirements.txt ] && pip3 install --user -r requirements.txt; pip3 install --user streamlit` (`.devcontainer/devcontainer.json:21`)

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download (`README.md:176`)
- A Groq API key (free at `console.groq.com`, `README.md:158`); HuggingFace token mentioned only in a code comment (`main.py:66` — `HF_TOKEN`) but never read in code; public `all-MiniLM-L6-v2` model needs no token
- Run: `pip install -r requirements.txt` then `streamlit run main.py` (`README.md:172-187`)
- Tests: `pip install pytest pytest-mock reportlab ruff psutil`, then `python tests/data/corpus/generate_corpus.py` followed by `pytest tests/ -v` (mirrors `.github/workflows/ci.yml:24-40`)
- Benchmark: `python scripts/benchmark_baseline.py` (requires `psutil` + generated corpus + `sentence-transformers` model download; writes `.planning/research/BASELINE_BENCHMARK.json`)

**Production:**
- Streamlit Community Cloud hosting Streamlit `1.42.0` app with `GROQ_API_KEY` set in the Cloud secrets panel; HuggingFace model re-downloaded and cached on first container boot (`README.md:199`); in-memory index only — no persistent volume required or used

## Entry Points

| Entry | Command | File |
|---|---|---|
| Streamlit app (sole app entry point) | `streamlit run main.py` | `main.py:1-253` |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:22-23` |
| Benchmark script | `python scripts/benchmark_baseline.py` | `scripts/benchmark_baseline.py:170-171` (`if __name__ == "__main__": run_benchmark()`) |
| Corpus generator | `python tests/data/corpus/generate_corpus.py` | `tests/data/corpus/generate_corpus.py:210-214` (`if __name__ == "__main__": generate_all_corpus_files()`) |
| Test suite | `pytest tests/ -v` | `tests/test_vector_index.py` (7), `tests/test_pdf_reader.py` (4), `tests/test_local_embedding.py` (3), `tests/test_local_llm.py` (3) — 17 tests total |
| No CLI / module entry | No `if __name__ == "__main__"` in app modules, no `__main__.py`, no console-scripts | Not applicable |

**Module roles:**
- `main.py` — Streamlit front-end, session state, upload → index → chat → stream orchestration
- `local_llm.py` — `AiModel` class: Groq client init + `ask_a_question_from_pdf_stream` generator
- `local_embedding.py` — `LocalEmbedding` class: sentence-transformers wrapper + batch `build_index`
- `vector_index.py` — `VectorIndex` class: pure-stdlib in-memory cosine/Euclidean store
- `pdf_reader.py` — `PdfReader` class: pypdf extraction + langchain chunking with `{content, filename, page, chunk_id}` metadata
- `tests/conftest.py` — shared fixtures: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`
- `tests/data/corpus/generate_corpus.py` — 6-file synthetic corpus builder (20-page `clean_digital.pdf`, `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`)
- `scripts/benchmark_baseline.py` — 4-stage perf benchmark (extraction → chunking → CPU embedding → linear-scan) writing `.planning/research/BASELINE_BENCHMARK.json`

---

*Stack analysis: 2026-10-11*
