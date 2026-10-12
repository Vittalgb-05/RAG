# Technology Stack

**Analysis Date:** 2026-10-12

## Languages

**Primary:**
- Python 3.11+ — all application code (19 root modules: `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`, `doc_store.py`, `hybrid_retriever.py`, `model_provider.py`, `groq_provider.py`, `litellm_provider.py`, `llama_cpp_provider.py`, `models.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `upload_validation.py`, `visual_analyzer.py`, `resource_telemetry.py`)
- Local runtime observed: CPython 3.13.5; CI and devcontainer pin Python 3.11 (`.github/workflows/ci.yml:18-21`, `.devcontainer/devcontainer.json:4`)

**Secondary:**
- JSON — devcontainer config only (`.devcontainer/devcontainer.json`)
- Markdown — docs only (`README.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`, `docs/RUNBOOK.md`)
- YAML — CI only (`.github/workflows/ci.yml`)
- SQL (inline DDL strings, no `.sql` files) — schema definitions in `doc_store.py:17-100`
- No JavaScript/TypeScript, no CSS, no shell scripts — UI is 100% Streamlit Python

## Runtime

**Environment:**
- Local: CPython via `streamlit run main.py` (sole entry point, `main.py:1-854`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:21-22,24-32`)
- CI: `ubuntu-latest` + `actions/setup-python@v5` with `python-version: "3.11"` and pip cache (`.github/workflows/ci.yml:10-22`)

**Package Manager:**
- pip with three requirements files:
  - `requirements.txt` (17 lines) — runtime dependencies
  - `requirements-lock.txt` (27 lines) — deterministic production lockfile (header: "RAG Assistant Deterministic Production Lockfile")
  - `requirements-test.txt` (5 lines) — test & benchmarking dependencies
- Lockfile: present (`requirements-lock.txt`); no `poetry.lock`, `Pipfile.lock`, or `uv.lock`
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`)

## Frameworks

**Core:**
- Streamlit `==1.42.0` (`requirements.txt:1`) — entire UI layer: `st.set_page_config` (`main.py:46-51`), sidebar, `st.file_uploader`, `st.chat_input` / `st.chat_message`, `st.status`, `st.cache_resource`, `st.write_stream`
- sentence-transformers `==3.4.1` (`requirements.txt:6`) — local embedding wrapper (`local_embedding.py:11`); default model `all-MiniLM-L6-v2` (`local_embedding.py:22`), L2-normalised vectors (`local_embedding.py:52-57`)
- pypdf `==5.3.0` (`requirements.txt:2`) — fast-path PDF text extraction (`pdf_reader.py:3`)
- langchain-text-splitters `==0.3.6` (`requirements.txt:4`) — chunking via `RecursiveCharacterTextSplitter` (`pdf_reader.py:5`, `docling_reader.py:15`, `ocr_fallback.py:12`)
- pydantic `==2.11.9` (`requirements.txt:8`) — canonical schemas in `models.py:11`, `model_provider.py:12`, `citation_validator.py:11`; frozen configs (`ConfigDict(frozen=True, extra="forbid")`)
- httpx `==0.28.1` (`requirements.txt:9`) — HTTP client for local llama-server (`llama_cpp_provider.py:15`), pinned since Phase 8
- groq `==0.15.0` (`requirements.txt:5`) — cloud inference client (`groq_provider.py:13`); guarded `try/except ImportError` (`groq_provider.py:12-15`)
- python-dotenv `==1.0.1` (`requirements.txt:3`) — local `.env` loading via `load_dotenv()` (`main.py:23,91`)
- litellm `>=1.50.0` (`requirements.txt:17`) — multi-cloud adapter Groq/OpenAI/Anthropic (`litellm_provider.py:19`); guarded import (`litellm_provider.py:18-21`)
- docling `>=2.0.0` (`requirements.txt:10`) — structured layout + markdown tables (`docling_reader.py:23-25`); guarded import with `PdfReader` fallback (`docling_reader.py:22-31,95-96`)
- rapidocr-onnxruntime `>=1.3.0` (`requirements.txt:11`) — CPU-only scanned-page OCR (`ocr_fallback.py:19`); guarded import (`ocr_fallback.py:18-21`)
- pymupdf `>=1.24.0` (`requirements.txt:12`, imported as `fitz`) — PDF raster rendering (`ocr_fallback.py:24`, `visual_analyzer.py:18`); guarded imports in both modules
- pillow `>=10.2.0` (`requirements.txt:13`) — image handling (transitive via OCR/VLM paths)
- lancedb `>=0.17.0` (`requirements.txt:14`) + pyarrow `>=14.0.0` (`requirements.txt:15`) — persistent hybrid vector store (`hybrid_retriever.py:20-21`); guarded import with in-memory fallback (`hybrid_retriever.py:19-24,100-120`)
- numpy `>=1.26.0,<3.0.0` (`requirements.txt:7`) — embedding arrays (`local_embedding.py:52-57`, `tests/conftest.py` fixtures)
- psutil `==6.1.1` (`requirements.txt:16`) — process RSS/VMS telemetry (`resource_telemetry.py:109`, `scripts/benchmark_baseline.py:13`); pinned since Phase 8

**Testing:**
- pytest `>=8.3.0` (`requirements-test.txt:2`) — runner; config in `pyproject.toml:13-19` (`testpaths = ["tests"]`, `python_files = ["test_*.py"]`)
- reportlab `>=4.2.0` (`requirements-test.txt:3`) — synthetic corpus generation (`tests/data/corpus/generate_corpus.py`, invoked by CI at `.github/workflows/ci.yml:35-37`)
- ruff `>=0.9.0` (`requirements-test.txt:4`) — lint + format check (`pyproject.toml:1-10`; CI at `.github/workflows/ci.yml:30-33`)
- psutil `>=6.1.0` (`requirements-test.txt:5`) — benchmark memory measurement

**Build/Dev:**
- ruff (lint rule sets `E,F,W` ignoring `E501,W291,W293`; `scripts/*` gets `E402` per-file-ignore — `pyproject.toml:1-10`)
- No bundler, no `setup.py`/`setup.cfg`/`Makefile` — interpreted Python, `streamlit run` directly

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` — UI runtime; app does not run without it (`main.py:24`)
- `sentence-transformers==3.4.1` — embedding inference; triggers HuggingFace model download on first run
- `groq==0.15.0` — LLM inference streaming endpoint (`groq_provider.py:117-161`)
- `litellm>=1.50.0` — unified cloud adapter with consent gate (`litellm_provider.py:101-346`)
- `httpx==0.28.1` — only HTTP client in production code; local-loopback-guarded llama-server transport (`llama_cpp_provider.py:40-67`)
- `pydantic==2.11.9` — all cross-module contracts (`models.py`, `model_provider.py:15-61`, `citation_validator.py`)
- `lancedb>=0.17.0` / `pyarrow>=14.0.0` — on-disk hybrid retrieval; degrades gracefully when absent
- `docling>=2.0.0` — primary structured extractor (CPU-only, `do_ocr=False`, `do_table_structure=True` per `docling_reader.py:1-7`)
- `rapidocr-onnxruntime>=1.3.0` + `pymupdf>=1.24.0` — conditional OCR path for scanned pages

**Infrastructure:**
- `psutil==6.1.1` — `get_process_memory_info()` RSS/VMS (`resource_telemetry.py:100-122`)
- `numpy>=1.26.0,<3.0.0` — vector math
- `python-dotenv==1.0.1` — `.env` loading before provider key resolution
- `pillow>=10.2.0` — image bytes handling for VLM crops
- `pypdf==5.3.0` — fast digital-PDF path
- `langchain-text-splitters==0.3.6` — only langchain component used (chunking only, no chains/agents)
- Stdlib-only modules (no third-party import): `vector_index.py` (`math`, `typing` only), `prompt_budget.py` (`math`, `re`, `typing`), `upload_validation.py`

**Pin-consistency audit (`requirements.txt` vs `requirements-lock.txt`):**
- Consistent pins (same version in both files): `httpx==0.28.1` (lock:10), `psutil==6.1.1` (lock:16), `pydantic==2.11.9` (lock:18)
- DRIFTED pins (lock resolves newer/different versions):
  - `streamlit`: `==1.42.0` (txt:1) vs `==1.65.0` (lock:27)
  - `pypdf`: `==5.3.0` (txt:2) vs `==6.12.1` (lock:20)
  - `python-dotenv`: `==1.0.1` (txt:3) vs `==1.2.2` (lock:22)
  - `langchain-text-splitters`: `==0.3.6` (txt:4) vs `==1.1.3` (lock:12)
  - `groq`: `==0.15.0` (txt:5) vs `==1.1.1` (lock:7)
  - `sentence-transformers`: `==3.4.1` (txt:6) vs `==5.2.3` (lock:25)
  - `numpy`: `>=1.26.0,<3.0.0` (txt:7) vs `==2.5.2` (lock:14) — satisfies range
  - `pillow`: `>=10.2.0` (txt:13) vs `==12.1.1` (lock:15) — satisfies range
  - `pyarrow`: `>=14.0.0` (txt:15) vs `==23.0.1` (lock:17) — satisfies range
  - `litellm`: `>=1.50.0` (txt:17) vs `==1.105.0` (lock:13) — satisfies range
- MISSING from lock (in `requirements.txt` but absent in lock): `docling`, `rapidocr-onnxruntime`, `pymupdf` (`fitz`), `lancedb`
- Lock-only entries (not in `requirements.txt`): `anyio==4.8.0`, `certifi==2025.8.3`, `h11==0.14.0`, `httpcore==1.0.7`, `idna==3.10`, `pydantic-core==2.33.2`, `pytest==9.0.3`, `reportlab==4.4.10`, `ruff==0.15.12`, `sniffio==1.3.1`
- Net effect: CI installs `requirements.txt` + `requirements-test.txt` (`.github/workflows/ci.yml:24-28`), NOT the lockfile — the lockfile is currently documentary, not enforced by CI or devcontainer (`.devcontainer/devcontainer.json:20` installs `requirements.txt` only)

## Configuration

**Environment:**
- Local dev: `.env` file in project root (gitignored, `.gitignore:1`); loaded by `load_dotenv()` in `main.py:91`
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]` tried first in `groq_provider.py:40-44`, `litellm_provider.py:76-82`); no `.streamlit/secrets.toml` committed
- Key resolution order (canonical, `litellm_provider.py:39-85`): explicit arg → Streamlit `session_state.cloud_api_keys` → `st.secrets` → `os.environ`
- Never commit secrets: `.env` gitignored; contents never read or quoted

**Build:**
- `pyproject.toml` — ruff config (`line-length = 120`, `target-version = "py311"`) + pytest config (`testpaths`, `python_files`, warning filters)
- No build step — interpreted Python, no bundler

## Platform Requirements

**Development:**
- Python 3.11+ (devcontainer + CI pin 3.11; local host observed 3.13.5), pip, virtualenv (`.venv`)
- System dependency for OCR/VLM raster: PyMuPDF native wheel (via pip); `nvidia-smi` optional for GPU telemetry (graceful `None` when absent — `resource_telemetry.py:33-97`)
- A Groq API key for cloud fallback (free at `console.groq.com`); optional `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` for LiteLLM-routed models
- Run: `pip install -r requirements.txt` then `streamlit run main.py`
- Test: `python tests/data/corpus/generate_corpus.py` then `pytest tests/ -v`; lint: `ruff check .` + `ruff format --check .`

**Production:**
- Streamlit Community Cloud (or any host running `streamlit run main.py`); in-memory index + SQLite `DocStore` + on-disk LanceDB under gitignored `data/` (`.gitignore:10`)
- License: MIT — `LICENSE` (21 lines, "Copyright (c) 2026 RAG Assistant Contributors")

## Directory Map (tech-relevant)

- `main.py` — Streamlit front-end, session state, upload → index → chat → stream orchestration
- `model_provider.py` — `BaseModelProvider` ABC + `ProviderCapabilities` / `HealthStatus` pydantic contracts
- `local_llm.py` — `AiModel` + `InferenceGate` (single-active-inference RLock for 4 GB VRAM)
- `groq_provider.py` / `litellm_provider.py` / `llama_cpp_provider.py` — cloud-direct, cloud-routed, local-server providers
- `local_embedding.py` — sentence-transformers wrapper (CPU-pinned default) + `VectorIndex` facade
- `vector_index.py` — pure-stdlib in-memory cosine/Euclidean store
- `hybrid_retriever.py` — LanceDB persistent hybrid (dense + FTS + RRF k=60) with in-memory fallback
- `pdf_reader.py` / `docling_reader.py` / `ocr_fallback.py` — fast pypdf path, structured Docling path, conditional RapidOCR path
- `doc_store.py` — SQLite WAL metadata store (documents/pages/chunks/evidence_elements/summaries)
- `models.py` — canonical Pydantic v2 schemas (`CONFIG_VERSION = "docling-1000-200-v1"`)
- `summarizer.py` / `citation_validator.py` / `prompt_budget.py` / `upload_validation.py` / `visual_analyzer.py` / `resource_telemetry.py` — supporting services
- `tests/` — 24 test modules + `conftest.py` + `tests/data/corpus/` (6 PDFs incl. `corrupt_invalid.pdf`; `generate_corpus.py` via `reportlab`)
- `scripts/benchmark_baseline.py` / `scripts/profile_resources.py` — perf benchmarks (psutil-gated, write to `.planning/research/`)
- `docs/` — `EVALUATION.md`, `LOCAL_INFERENCE.md`, `RUNBOOK.md`
- `data/` — gitignored runtime dir (`documents.db`, `lancedb/` present locally)
- `.github/workflows/ci.yml` — lint → corpus generation → pytest pipeline

---

*Stack analysis: 2026-10-12*
