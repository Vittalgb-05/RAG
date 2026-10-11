# Technology Stack

**Analysis Date:** 2026-10-11

## Languages

**Primary:**
- Python 3.11+ — all application code: `main.py`, `local_llm.py`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `doc_store.py`, `models.py`, `upload_validation.py`, `scripts/benchmark_baseline.py`

**Secondary:**
- JSON — `.devcontainer/devcontainer.json`, `.planning/**`, disk cache payloads written by `main.py`
- Markdown — docs only (`README.md`, `docs/LOCAL_INFERENCE.md`, `CLAUDE.md`)
- SQL (SQLite DDL inline in Python) — `doc_store.py` (`SCHEMA_V1_DDL`, `MIGRATIONS`)
- No JavaScript/TypeScript/CSS — UI is 100% Streamlit Python

## Runtime

**Environment:**
- CPython 3.11 locally via `streamlit run main.py`
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`)
- CI: GitHub Actions `ubuntu-latest` with `actions/setup-python@v5` pinned to `"3.11"` (`.github/workflows/ci.yml:9-14`)
- Target inference host: Windows 11 + NVIDIA RTX 3050 Laptop GPU (4 GB VRAM), documented in `docs/LOCAL_INFERENCE.md`

**Package Manager:**
- pip
- Runtime lockfile: absent (no `requirements.lock`, `poetry.lock`, `uv.lock`, `Pipfile.lock`)
- Runtime deps in `requirements.txt`; test/benchmark deps in `requirements-test.txt`
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`)

## Frameworks

**Core:**
- Streamlit `1.42.0` — entire UI layer (`main.py`)
- Pydantic `2.11.9` — canonical data models and provider schemas (`models.py`, `model_provider.py`)
- httpx `>=0.28.0` — HTTP client for the local llama-server provider (`llama_cpp_provider.py`)
- sentence-transformers `3.4.1` — local CPU embeddings (`local_embedding.py`)

**Testing:**
- pytest `>=8.3.0` — test runner (`pyproject.toml` `[tool.pytest.ini_options]`)
- reportlab `>=4.2.0` — synthetic corpus PDF generation (`tests/data/corpus/generate_corpus.py`)
- psutil `>=6.1.0` — memory profiling in `scripts/benchmark_baseline.py`
- numpy (runtime dep) — deterministic mock embeddings in `tests/conftest.py`

**Build/Dev:**
- ruff `>=0.9.0` — linter + formatter (config in `pyproject.toml`)
- No bundler, no compile step, no `setup.py`/`setup.cfg`

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` — app does not run without it (`main.py`)
- `groq==0.15.0` — optional cloud fallback client, guarded import (`groq_provider.py:12-14`)
- `pydantic==2.11.9` — every model in `models.py` and `model_provider.py`
- `httpx>=0.28.0` — local provider transport, also mocks via `httpx.MockTransport` in tests
- `sentence-transformers==3.4.1` — embedding inference; triggers HuggingFace download on first run
- `pypdf==5.3.0` — PDF parsing in `pdf_reader.py` and `upload_validation.py`
- `langchain-text-splitters==0.3.6` — chunking only (`pdf_reader.py`); no chains/agents

**Infrastructure:**
- `numpy>=1.26.0,<3.0.0` — transitive from sentence-transformers, directly used in `tests/conftest.py` and `scripts/benchmark_baseline.py`
- `python-dotenv==1.0.1` — `.env` loading (`main.py`, called inside the cached loader)
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — transitive via sentence-transformers (not pinned here)
- No database driver beyond stdlib `sqlite3` (`doc_store.py`); no FAISS/LanceDB yet

## Configuration

**Environment:**
- `GROQ_API_KEY` resolved `st.secrets` → `os.environ`/`.env` (`groq_provider.py:36-50`)
- `.env` is gitignored (`.gitignore:1`); `load_dotenv()` runs inside `load_ai_model()` (`main.py:65-72`)
- Local llama-server endpoint default `http://127.0.0.1:8080` (`llama_cpp_provider.py:23`)
- Locked deployment caps: `MAX_FILE_MB = 50`, `MAX_PAGES = 500` (`upload_validation.py:15-16`)
- Chunking policy constant: `CONFIG_VERSION = "chunker-1000-200-pypdf"` (`models.py:14`)

**Build:**
- No build config. `pyproject.toml` holds only `[tool.ruff]` + `[tool.pytest.ini_options]`
- `[tool.ruff]`: `line-length = 120`, `target-version = "py311"`, lint `select = ["E","F","W"]`, `ignore = ["E501","W291","W293"]`, `scripts/*` ignores `E402`
- `.devcontainer/devcontainer.json:21` pip-installs `requirements.txt` + streamlit, then auto-launches `streamlit run main.py`
- `.github/workflows/ci.yml` installs `requirements.txt` + `requirements-test.txt`, runs `ruff check .`, `ruff format --check .`, generates the corpus, then `pytest tests/ -v`

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`)
- Optional NVIDIA driver 550.x+ / CUDA 12.x and llama.cpp CUDA build for local inference (`docs/LOCAL_INFERENCE.md`)
- Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download
- `reportlab` needed locally to generate the test corpus before running `tests/` (CI does this in a dedicated step)

**Production:**
- Streamlit Community Cloud (documented in `README.md`) with `GROQ_API_KEY` set in the Cloud secrets panel; in-memory index only, no persistent volume
- Primary intended deployment: local Windows workstation inside the 4 GB VRAM ceiling

---

*Stack analysis: 2026-10-11*
