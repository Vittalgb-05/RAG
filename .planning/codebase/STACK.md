<!-- refreshed: 2026-10-17 -->
# Technology Stack

**Analysis Date:** 2026-10-17

## Languages

**Primary:**
- Python 3.11+ — all application code. Target declared in `pyproject.toml:3` (`target-version = "py311"`) and `setup.py:404` (`python_requires=">=3.11"`); classifiers list 3.11 and 3.12 (`setup.py:443-444`). Modules: `main.py`, `start.py`, `setup.py`, and 18 root-level domain modules (`local_llm.py`, `hybrid_retriever.py`, `doc_store.py`, etc.).

**Secondary:**
- SQL — embedded DDL strings in `doc_store.py:17-94` (no separate `.sql` files)
- JSON — `.devcontainer/devcontainer.json`; `.freebuff/project-id` (opaque UUID `4b7e3567-...`); runtime caches (`data/lancedb` fallback `fallback_store.json`, `data/lancedb_bench`)
- Markdown — docs only (`README.md`, `docs/RUNBOOK.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`)
- No JavaScript/TypeScript/CSS — UI is 100% Streamlit Python

## Runtime

**Environment:**
- CPython 3.11+ — no `runtime.txt`, no Dockerfile. Development in devcontainer `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`); CI uses `ubuntu-latest` with Python 3.11 (`.github/workflows/ci.yml:12,18-21`).
- External local inference process: `llama-server` (llama.cpp), a native CUDA binary bound to `127.0.0.1:8080` (`docs/LOCAL_INFERENCE.md:48-72`, `llama_cpp_provider.py:25`). Not a Python dependency — must be downloaded/compiled separately (`docs/RUNBOOK.md:76-107`).
- GPU: NVIDIA CUDA 11.8 or 12.x; locked to a 4 GB VRAM budget (RTX 3050 Laptop target).

**Package Manager:**
- pip (primary) — `pip install -r requirements-lock.txt` or `pip install -e .` (`setup.py:267-303`)
- uv — generates `requirements-lock.txt` via `uv pip compile --universal --python-version 3.11 requirements.txt` (`requirements-lock.txt:1-2`); CI installs with `astral-sh/setup-uv@v5` (`.github/workflows/ci.yml:23-31`)
- Lockfile: **present** — `requirements-lock.txt` (645 lines, fully pinned, universal Python 3.11)
- Virtualenv convention: `.venv` (gitignored, `.gitignore:2`); also `.pyvenv.cfg` style activation not committed

## Frameworks

**Core:**
- Streamlit `1.42.0` — entire UI layer (`main.py`): `st.set_page_config`, sidebar, `st.file_uploader`, `st.chat_input`/`st.chat_message`, `st.write_stream`, `st.status`, `st.cache_resource`, `st.secrets`
- Pydantic `2.11.9` — canonical immutable data models in `models.py` (Document, Page, Chunk, EvidenceElement, EvidenceSnippet, RetrievalResult, SummaryResult) and provider schemas in `model_provider.py`
- setuptools — packaging + console-script entry points + custom `download_models` command (`setup.py:397-449`)

**Document AI / Extraction:**
- Docling `>=2.0.0` (resolved `2.138.0`) — layout-aware PDF structure + Markdown table extraction, CPU pipeline `do_ocr=False, do_table_structure=True` (`docling_reader.py:22-31,104-109`)
- rapidocr-onnxruntime `>=1.3.0` (resolved `1.4.4`) backed by onnxruntime `1.31.0` — conditional CPU OCR fallback on low-text pages (`ocr_fallback.py:20-23`)
- PyMuPDF (`pymupdf`) `>=1.24.0` (resolved `1.28.2`) — page rasterization, visual-region detection, element cropping (`ocr_fallback.py:26`, `visual_analyzer.py:17-19`)
- pypdf `5.3.0` — baseline text extraction + validation probe (`pdf_reader.py:3`, `upload_validation.py:12`)
- langchain-text-splitters `0.3.6` — `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:35`, `docling_reader.py:172`, `ocr_fallback.py:315`)
- pillow `>=10.2.0` (resolved `11.3.0`) — image handling for OCR/VLM crops

**Embedding / Retrieval:**
- sentence-transformers `3.4.1` — local `all-MiniLM-L6-v2` embeddings, 384-dim, L2-normalized, CPU-pinned (`local_embedding.py:11,22-37,81`)
- LanceDB `>=0.17.0` (resolved `0.40.0`) + pyarrow `>=14.0.0` (resolved `23.0.1`) — persistent on-disk vector + FTS index (`hybrid_retriever.py:19-24`)
- numpy `>=1.26.0,<3.0.0` (resolved `2.4.6`) — embedding array handling

**Inference (local + cloud):**
- litellm `>=1.50.0` (resolved `1.105.0` on Python <3.14, `1.102.4` on >=3.14) — unified cloud adapter to Groq/OpenAI/Anthropic (`litellm_provider.py:18-21`)
- groq `0.15.0` — native Groq client (`groq_provider.py:12-15`)
- httpx `0.28.1` — HTTP client for local `llama-server` REST/SSE (`llama_cpp_provider.py:15,63-67`)

**Testing:**
- pytest `>=8.3.0` — configured in `pyproject.toml:20-27`; 24 test modules under `tests/`
- reportlab `>=4.2.0` — synthetic PDF corpus generation (`tests/data/corpus/generate_corpus.py`)
- ruff `>=0.9.0` — lint + format gate, also a runtime dev tool

**Build/Dev:**
- ruff `0.9.x` — configured in `pyproject.toml:1-17` (line-length 120, `E`/`F`/`W`, ignores `E501`/`W291`/`W293`)
- GitHub Actions — `.github/workflows/ci.yml` (checkout → setup Python 3.11 → uv install → ruff check/format → generate corpus → pytest)

## Key Dependencies

**Critical:**
| Package | Version (resolved) | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `1.42.0` | `main.py` | UI runtime; app does not run without it |
| `pydantic` | `2.11.9` | `models.py`, `model_provider.py` | Canonical schemas across every layer |
| `docling` | `2.138.0` | `docling_reader.py` | Primary layout/table extraction; falls back to pypdf if absent |
| `sentence-transformers` | `3.4.1` | `local_embedding.py` | Local embeddings; triggers HuggingFace download on first run |
| `lancedb` | `0.40.0` | `hybrid_retriever.py` | Persistent vector + FTS store; falls back to in-memory `VectorIndex` |
| `litellm` | `1.105.0` | `litellm_provider.py` | Only path to opted-in cloud inference |
| `groq` | `0.15.0` | `groq_provider.py` | Native Groq client for cloud fallback |
| `httpx` | `0.28.1` | `llama_cpp_provider.py` | Local loopback HTTP/SSE transport |
| `pymupdf` | `1.28.2` | `ocr_fallback.py`, `visual_analyzer.py` | Page rendering + visual cropping |
| `rapidocr-onnxruntime` | `1.4.4` | `ocr_fallback.py` | Scanned-page OCR (CPU) |
| `pypdf` | `5.3.0` | `pdf_reader.py`, `upload_validation.py` | Baseline extraction + page-count validation |
| `langchain-text-splitters` | `0.3.6` | `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py` | Chunking only (no chains/agents) |
| `psutil` | `6.1.1` | `resource_telemetry.py` | Process RSS/VMS telemetry |
| `python-dotenv` | `1.0.1` | `main.py:24,99` | Loads `.env` before provider key resolution |

**Infrastructure (transitive, significant):**
- `torch` `2.14.1`, `torchvision` `0.29.1`, `transformers` `4.57.6`, `tokenizers` `0.22.2`, `huggingface-hub` `0.36.2`, `accelerate` `1.15.0` — pulled by sentence-transformers/docling; model weights cached in HuggingFace cache (`README.md` cites `~/.cache/huggingface/`)
- `onnxruntime` `1.31.0`, `opencv-python` `5.0.0.93`, `opencv-python-headless` `5.0.0.93` — RapidOCR computer vision stack
- `aiohttp` `3.14.5`, `openai` `2.54.0`, `boto3`/`botocore` `1.43.111`, `requests` `2.34.2`, `tiktoken` `0.14.0`, `langsmith` `0.11.2` — pulled by litellm (broad cloud provider surface; see CONCERNS)
- `sqlite3` — Python standard library, no package (metadata store `doc_store.py`)

## Configuration

**Environment:**
- Local dev: `.env` in project root, loaded by `load_dotenv()` inside the cached model loader (`main.py:24,99`). `.env` is gitignored (`.gitignore:1`) and **absent from the working tree** — presence noted only, contents never read.
- Cloud keys precedence (`litellm_provider.py:39-79`, `groq_provider.py:37-47`): explicit arg → `st.session_state.cloud_api_keys` → `st.secrets[<PROVIDER>_API_KEY]` → `os.environ[<PROVIDER>_API_KEY]`.
- No `.streamlit/secrets.toml` present (no `.streamlit/` directory in repo).
- `.freebuff/project-id` contains an opaque project UUID (tooling metadata, not a secret).

**Data / State directories (gitignored, created at runtime):**
- `data/documents.db` — SQLite (`doc_store.py:); `data/lancedb/` and `data/lancedb_bench/` — LanceDB dirs
- `models/` — GGUF weights: `qwen3-vl-2b-instruct-q4_k_m.gguf`, `mmproj-f16.gguf` (`setup.py:44-63`); a partial `qwen3-vl-2b-instruct-q4_k_m.tmp` present in the working tree
- `.cache/` — extraction artifacts keyed by `<sha256>/<CONFIG_VERSION>` (`models.py:14,17-30`)

**Build:**
- `requirements.txt` (17 direct deps), `requirements-lock.txt` (resolved), `requirements-test.txt` (pytest/reportlab/ruff/psutil)
- `pyproject.toml` — ruff + pytest config only; no `[build-system]` / packaging metadata (packaging lives in `setup.py`)
- `setup.py` — `install_requires` read from `requirements.txt` (`setup.py:36-41,430`); `py_modules` lists all 22 root modules (`setup.py:406-429`)

## Platform Requirements

**Development:**
- Python 3.11+ / pip or uv / `.venv` (`docs/RUNBOOK.md:16-17`)
- Windows 11 or Linux; NVIDIA GPU with 4 GB VRAM and CUDA 11.8/12.x recommended (`docs/RUNBOOK.md:11-17`)
- 16 GB system RAM; ~10 GB SSD; `llama-server` native binary on PATH or repo root (`docs/RUNBOOK.md:76-80`)
- Windows HuggingFace symlink warning may require Developer Mode or `HF_HUB_DISABLE_SYMLINKS_WARNING=1` (`docs/RUNBOOK.md:67-70`)

**Production:**
- Intended deployment is a **single-user workstation** running Streamlit and `llama-server` on the same machine (`docs/RUNBOOK.md:240-245`)
- Hosted deployment caveat: a remote Streamlit instance cannot reach `127.0.0.1:8080`, so remote hosting requires dedicated model endpoints/tunneling (`README.md:216`, `docs/RUNBOOK.md:245`)
- No container image, no Streamlit Cloud config committed

## Entry Points

| Entry | Command | File |
|---|---|---|
| Launcher (pre-flight + Streamlit) | `python start.py [--port 8501 --host localhost --headless --llama-host 127.0.0.1 --llama-port 8080]` | `start.py:106-132` |
| Direct app | `streamlit run main.py` | `main.py` |
| Console script | `rag-assistant=start:main` | `setup.py:432-436` |
| Setup console script | `rag-setup=setup:main_cli` | `setup.py:434` |
| Model download script | `rag-download-models=setup:download_models_cli` | `setup.py:435` |
| Full setup | `python setup.py [setup\|--deps-only\|--models-only\|--skip-vlm\|--force\|--lockfile]` | `setup.py:452-485` |
| Devcontainer autostart | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:21-23` |
| Benchmarks | `python scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py` | `scripts/` |
| Tests | `pytest tests/ -v` | `pyproject.toml:20-22` |

---

*Stack analysis: 2026-10-17*
