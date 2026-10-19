# Technology Stack

**Analysis Date:** 2026-10-19

## Languages

**Primary:**
- Python 3.11+ (target `py311`) — entire application. Entry point `main.py`, inference layer `local_llm.py`, providers `llama_cpp_provider.py` / `groq_provider.py` / `litellm_provider.py` / `model_provider.py`, extraction `docling_reader.py` / `pdf_reader.py` / `ocr_fallback.py` / `visual_analyzer.py`, retrieval `hybrid_retriever.py` / `vector_index.py`, persistence `doc_store.py`, models `models.py`, launchers `start.py` / `setup.py`.

**Secondary:**
- SQL (SQLite DDL inline as string constants) — `doc_store.py:17-100`
- JSON — `.devcontainer/devcontainer.json`, LanceDB fallback `data/lancedb/fallback_store.json`
- YAML — CI only (`.github/workflows/ci.yml`), Docker Compose (`docker-compose.yml`)
- Markdown — docs (`README.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`, `docs/RUNBOOK.md`)
- No JavaScript/TypeScript/CSS. UI is 100% Streamlit Python.

## Runtime

**Environment:**
- CPython 3.11+ (enforced in `start.py:49-54`, `setup.py:684`)
- Local: `streamlit run main.py` or the launcher `python start.py` (`start.py:181-211`); packaged console scripts `rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:710-717`, `rag_assistant.egg-info/entry_points.txt`)
- Container: `python:3.11-slim-bookworm` (`Dockerfile:3`), serving Streamlit on `0.0.0.0:8501` with a `/health`-backed healthcheck (`Dockerfile:39-46`)
- Dev container: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-runs `streamlit run main.py` on port 8501 (`.devcontainer/devcontainer.json:21-32`)

**Package Manager:**
- pip (pinned `requirements.txt`; editable install `pip install -e .` via `setup.py`)
- uv used to generate the deterministic lockfile and in CI: `uv pip compile --universal --python-version 3.11 requirements.txt -o requirements-lock.txt` (`requirements-lock.txt:1-2`), `uv pip install --system -r requirements-lock.txt` (`.github/workflows/ci.yml:23-31`)
- Lockfile: present — `requirements-lock.txt` (645 lines, fully pinned with `# via` provenance)
- Virtual env convention `.venv` (gitignored, `.gitignore:2`); no Poetry/Pipenv/PDM

## Frameworks

**Core:**
- Streamlit `==1.42.0` — entire UI layer: `st.set_page_config` (`main.py:101-106`), sidebar, file uploader, chat, `st.dialog` consent modal (`main.py:201-209`), `st.toggle`/`st.selectbox`/`st.text_input` cloud controls (`main.py:211-265`), `st.status` (`main.py:314`), `st.cache_resource` model loader
- Pydantic `==2.11.9` — canonical immutable data models and validation (`models.py:1-235`), provider capability/health schemas (`model_provider.py:15-61`), citation result schema (`citation_validator.py:11`)
- Docling `>=2.0.0` (locked `2.138.0`) — structured layout + markdown table extraction with CPU-only pipeline (`docling_reader.py:23-32,123-137`)

**Testing:**
- pytest `>=8.3.0` — config in `pyproject.toml:20-27` (`testpaths=["tests"]`, `test_*.py`); `tests/conftest.py` sets a mock `GROQ_API_KEY`
- reportlab `>=4.2.0` — synthetic test corpus PDF generation (`tests/data/corpus/generate_corpus.py`, invoked by CI `.github/workflows/ci.yml:38-40`)

**Build/Dev:**
- Ruff `>=0.9.0` — lint + format; `line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`, `ignore = ["E501","W291","W293"]` (`pyproject.toml:1-17`); CI runs `ruff check .` and `ruff format --check .` (`.github/workflows/ci.yml:33-36`)
- setuptools `setup.py` — packaging, dependency bootstrap, GGUF model downloader, native `llama-server` acquisition, custom `cmdclass` commands (`setup.py:59-820`)
- Docker / Docker Compose — reproducible runtime + optional CUDA `llama-server` sidecar (`Dockerfile`, `docker-compose.yml`)
- GitHub Actions — `.github/workflows/ci.yml` (lint + corpus generation + pytest)

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` — UI runtime; app cannot run without it (`requirements.txt:1`, `main.py:31`)
- `pydantic==2.11.9` — every persisted model, provider schema, and citation result (`requirements.txt:8`, `models.py:10`)
- `lancedb>=0.17.0` + `pyarrow>=14.0.0` — persistent on-disk vector + FTS store with RRF; graceful in-memory fallback when absent (`requirements.txt:14-15`, `hybrid_retriever.py:22-28,121-133`)
- `sentence-transformers==3.4.1` — local `all-MiniLM-L6-v2` embeddings, CPU-pinned to preserve VRAM (`requirements.txt:6`, `local_embedding.py:12-16,27-42,55`)
- `docling>=2.0.0` — reading-order, heading, and markdown-table extraction; degrades to `pypdf` on failure (`requirements.txt:10`, `docling_reader.py:116-121,309-314`)
- `litellm>=1.50.0` — unified cloud routing with privacy consent gate (`requirements.txt:17`, `litellm_provider.py:21-26,131-148`)
- `groq==0.15.0` — direct Groq cloud client used as fallback provider (`requirements.txt:5`, `groq_provider.py:12-15,51-52`)

**Infrastructure:**
- `httpx==0.28.1` — HTTP client for the local llama-server OpenAI-compatible REST endpoint, with loopback/SSRF guard (`requirements.txt:9`, `llama_cpp_provider.py:18,26-70`)
- `pymupdf>=1.24.0` — page rasterization and vector-drawing inspection; imported as `import pymupdf as fitz` (`requirements.txt:12`, `ocr_fallback.py:30`, `visual_analyzer.py:18`)
- `rapidocr-onnxruntime>=1.3.0` (marker `python_version < "3.13"`, `requirements.txt:11`) — CPU-only OCR via ONNX Runtime, used conditionally on low-text pages (`ocr_fallback.py:21-27,52-76`)
- `pillow>=10.2.0` — image handling (`requirements.txt:13`)
- `numpy>=1.26.0,<3.0.0` — embedding arrays (`requirements.txt:7`)
- `psutil==6.1.1` — process RSS/VMS telemetry (`requirements.txt:16`, `resource_telemetry.py:177-191`)
- `python-dotenv==1.0.1` — `.env` loading (`requirements.txt:3`, `main.py:30`)
- `pypdf==5.3.0` — text extraction + Google-style validation fallback (`requirements.txt:2`, `pdf_reader.py`, `upload_validation.py:12`)
- `langchain-text-splitters==0.3.6` — chunking only (`chunk_size=1000`, `chunk_overlap=200`); no chains/agents (`requirements.txt:4`, `docling_reader.py:16,193-197`, `ocr_fallback.py:15,339-343`)

**External native runtime (not a pip package):**
- `llama-server` (llama.cpp release `b11718`) — pre-built CUDA/CPU binary downloaded into `tools/llama-server` and probed by `start.py:69-79`, `setup.py:288-493`; the app talks to it over `http://127.0.0.1:8080`
- GGUF weights `qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16.gguf` (present in `models/`; registry/downloader at `setup.py:59-78`)

## Configuration

**Environment:**
- `.env` in project root (gitignored `.gitignore:1`) loaded by `load_dotenv()` (`main.py:30`); **no `.env` file present in the working tree** (existence check only)
- Streamlit secrets (`st.secrets`) preferred over env vars for API keys (`groq_provider.py:38-47`, `litellm_provider.py:74-88`). **No `.streamlit/` directory or `secrets.toml` present.**
- Runtime env vars: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (per-provider, `litellm_provider.py:50-55`, `main.py:227-229`); `LLAMA_SERVER_HOST`/`LLAMA_SERVER_PORT` (`docker-compose.yml:19-20`)
- Backend-forcing env vars: `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` (`main.py:26-28`, `start.py:34-36`, `Dockerfile:9-11`); `LITELLM_TELEMETRY=False` (`litellm_provider.py:19`)
- No build step — interpreted Python. No bundler, no `runtime.txt`/`packages.txt`.

**Build:**
- `requirements.txt` (pinned direct deps), `requirements-lock.txt` (uv-compiled full tree), `requirements-test.txt` (pytest/reportlab/ruff/psutil)
- `pyproject.toml` (Ruff + pytest config only; deps are NOT declared here — they live in `setup.py:676-730` reading `requirements.txt`)
- `setup.py:676-730` — package `rag-assistant` v1.0.0, `python_requires=">=3.11"`, `find_packages()`, explicit `py_modules` list, `install_requires` from `requirements.txt`, console-script entry points
- `Dockerfile`, `docker-compose.yml` (app service + optional `gpu`-profile `ghcr.io/ggml-org/llama.cpp:server-cuda` sidecar, `docker-compose.yml:29-51`)

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`)
- Windows host OS with PowerShell is the primary target (`README.md:119`); Developer Mode / admin may be needed for HuggingFace symlink-based model downloads
- Optional NVIDIA GPU (RTX 3050 4 GB VRAM target) with CUDA 12.x/11.8 drivers; `nvidia-smi` on PATH for telemetry and GPU detection (`setup.py:293-299`, `resource_telemetry.py:58-97`)
- `llama-server` binary on PATH or in `tools/llama-server` (`start.py:69-79`)
- HuggingFace model weights in `models/` and cached weights in `.cache/` / `~/.cache/huggingface/`

**Production:**
- Local single-user deployment on consumer hardware within a strict 4 GB VRAM ceiling; exactly one LLM/VLM resident at a time (`local_llm.py:26-90` InferenceGate)
- Containerized deployment via `Dockerfile`/`docker-compose.yml` (Streamlit on 8501; optional CUDA llama-server sidecar with `nvidia` device reservation)
- No persistent cloud volume required from the app itself; state lives in `data/` (SQLite `documents.db`, LanceDB) and `models/`
- Hosted-Streamlit caveat: an externally hosted instance cannot reach a loopback `llama-server`; remote use requires dedicated endpoints/private tunneling (`README.md:216`)

---

*Stack analysis: 2026-10-19*
