# Technology Stack

**Analysis Date:** 2026-10-13

## Languages

**Primary:**
- Python 3.11+ — All core application logic, models, ingestion pipelines, storage interfaces, inference providers, and user interface.
  - Core Modules: `main.py`, `start.py`, `setup.py`, `models.py`, `doc_store.py`, `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `local_embedding.py`, `vector_index.py`, `hybrid_retriever.py`, `model_provider.py`, `local_llm.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `prompt_budget.py`, `summarizer.py`, `citation_validator.py`, `upload_validation.py`, `resource_telemetry.py`
  - Strict type hints with Pydantic v2 schemas (`models.py`, `model_provider.py`, `upload_validation.py`)

**Secondary:**
- Markdown — Documentation and benchmarks (`README.md`, `docs/EVALUATION.md`, `docs/LOCAL_INFERENCE.md`, `docs/RUNBOOK.md`)
- JSON — Research artifacts and container configuration (`.devcontainer/devcontainer.json`, `.planning/research/RESOURCE_PROFILE.json`, `.planning/research/MULTIMODAL_BENCHMARK.json`)
- TOML — Tooling configuration (`pyproject.toml`)
- No TypeScript/JavaScript, CSS, or raw SQL source files — 100% Python codebase with declarative Streamlit frontend, stdlib `sqlite3` driver, and Python LanceDB bindings.

## Runtime

**Environment:**
- CPython 3.11 / 3.12 / 3.13 (`python_requires = ">=3.11"`)
- Local Execution: `python start.py` or `streamlit run main.py`
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json`) exposing port 8501
- Local LLM Backend: External `llama-server` process running `qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj` on `http://127.0.0.1:8080`
- CI Environment: `ubuntu-latest` running Python 3.11 via GitHub Actions (`.github/workflows/ci.yml`)

**Package Manager:**
- `pip` for development and user installation (`pip install -r requirements.txt`)
- `uv` for lockfile compilation and fast CI resolution (`uv pip compile requirements.txt -o requirements-lock.txt`, `uv pip install --system -r requirements-lock.txt`)
- Lockfile: `requirements-lock.txt` present and synchronized (targeting Python 3.11)
- Test Dependencies: `requirements-test.txt` (`pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0`)

## Frameworks

**Core:**
- Streamlit 1.42.0 — Web presentation layer, reactivity, streaming output, session state management (`main.py`)
- Pydantic 2.11.9 — Immutable schemas, runtime validation, serialization, and coordinate bounds (`models.py`, `model_provider.py`)
- Sentence-Transformers 3.4.1 — CPU-pinned embedding generation with `all-MiniLM-L6-v2` (`local_embedding.py`)
- LanceDB 0.40.0 (`lancedb>=0.17.0`) & PyArrow 23.0.1 (`pyarrow>=14.0.0`) — Persistent on-disk vector store and FTS BM25 hybrid retrieval (`hybrid_retriever.py`)
- SQLite (Python standard library `sqlite3`) — ACID document and page-level metadata persistence with WAL mode (`doc_store.py`)

**Document Processing:**
- Docling 2.138.0 (`docling>=2.0.0`) — Layout-aware document parsing, markdown table extraction, and structured reading order (`docling_reader.py`)
- RapidOCR ONNXRuntime 1.4.4 (`rapidocr-onnxruntime>=1.3.0`) — CPU-based conditional optical character recognition for scanned/low-text pages (`ocr_fallback.py`)
- PyMuPDF 1.28.2 (`pymupdf>=1.24.0`, `fitz`) — PDF raster rendering, visual drawing bounding-box extraction, and 2x crop generation (`visual_analyzer.py`, `ocr_fallback.py`)
- pypdf 5.3.0 — Fast digital PDF text extraction fallback (`pdf_reader.py`, `upload_validation.py`)
- LangChain Text Splitters 0.3.6 — Bounded character splitting via `RecursiveCharacterTextSplitter` (`docling_reader.py`, `ocr_fallback.py`, `pdf_reader.py`)
- Pillow 11.3.0 (`pillow>=10.2.0`) — Image format verification and in-memory manipulation (`visual_analyzer.py`)

**Inference & Connectivity:**
- HTTPX 0.28.1 — Async-capable HTTP transport for local `llama-server` communications and mock transport testing (`llama_cpp_provider.py`)
- LiteLLM 1.105.0 (`litellm>=1.50.0`) — Multi-provider cloud fallback router (Groq, OpenAI, Anthropic) with strict consent gating (`litellm_provider.py`)
- Groq 0.15.0 — Direct client for Groq cloud inference (`groq_provider.py`)

**Testing & Quality:**
- Pytest 8.3.0+ — Test execution framework with 24 test suites (`tests/`)
- ReportLab 4.2.0+ — Synthetic PDF document generator for testing and benchmarks (`tests/data/corpus/generate_corpus.py`)
- Ruff 0.9.0+ — High-performance code linting and formatting configured via `pyproject.toml`
- psutil 6.1.1 — Process memory and resource profiling (`resource_telemetry.py`)

**Build & Packaging:**
- Setuptools (`setup.py`) — Standard packaging defining package `rag-assistant` (v1.0.0) with console script `rag-assistant=start:main`
- Application Launcher (`start.py`) — Startup orchestration script validating Python 3.11+, scaffolding directories, verifying `llama-server`, and launching Streamlit

## Key Dependencies

**Critical:**
- `streamlit==1.42.0` — Interactive web application framework powering all UI workflows.
- `sentence-transformers==3.4.1` — CPU-pinned embedding model (`all-MiniLM-L6-v2`) generating 384-dimensional vector embeddings without GPU memory overhead.
- `lancedb>=0.17.0` + `pyarrow>=14.0.0` — Embedded columnar vector storage supporting hybrid vector + FTS search with Reciprocal Rank Fusion.
- `docling>=2.0.0` — Deep layout parsing recovering complex table structures and layout hierarchies.
- `rapidocr-onnxruntime>=1.3.0` — High-efficiency CPU OCR preventing pipeline stalling on scanned documents.
- `pymupdf>=1.24.0` — High-speed PDF rasterizer and vector drawing inspector for bounding-box detection.
- `pydantic==2.11.9` — Enforces strict runtime validation on documents, chunks, bounding boxes, and providers.
- `litellm>=1.50.0` & `groq==0.15.0` — Optional cloud fallback adapters guarded by explicit user privacy consent.

**Infrastructure:**
- `httpx==0.28.1` — HTTP client with connection pooling, timeout controls, and test mock transports.
- `psutil==6.1.1` — Real-time memory (RSS/VMS) telemetry ensuring safety within a 4 GB VRAM / constrained RAM envelope.
- `python-dotenv==1.0.1` — Environment variable management for API keys and endpoint configuration.

## Configuration

**Environment:**
- Local API Keys: Managed via `.env` in the repository root (gitignored) or injected via Streamlit secrets (`st.secrets`).
- Key Variables:
  - `GROQ_API_KEY`: API key for Groq inference (cloud mode only).
  - `OPENAI_API_KEY`: API key for OpenAI models via LiteLLM (cloud mode only).
  - `ANTHROPIC_API_KEY`: API key for Anthropic models via LiteLLM (cloud mode only).
  - `LLAMA_SERVER_URL`: Local llama.cpp endpoint (defaults to `http://127.0.0.1:8080`, restricted to loopback unless overridden).

**Build & Tooling:**
- `pyproject.toml`:
  - `[tool.ruff]`: Line length 120, target version `py311`, excludes `.planning`, `.cache`, `data`, `docs`, `*.md`.
  - `[tool.ruff.lint]`: Selects rules `E`, `F`, `W`; ignores `E501`, `W291`, `W293`; allows `E402` in `scripts/*`.
  - `[tool.pytest.ini_options]`: Test path `tests/`, file pattern `test_*.py`, ignores `UserWarning` and `DeprecationWarning`.
- `setup.py`: Packaging metadata, module list, Python `>=3.11` requirement, entry point `rag-assistant=start:main`.

## Platform Requirements

**Development:**
- Windows 10/11, macOS, or Linux with Python 3.11+.
- Hardware Envelope: Designed to operate strictly within a 4 GB GPU VRAM envelope (local Qwen3-VL 2B consumes ~2.4 GB VRAM; embeddings and OCR pinned to CPU RAM).
- Local Model Weights (optional for local inference):
  - `qwen3-vl-2b-instruct-q4_k_m.gguf`
  - `mmproj-qwen3-vl-2b-instruct-f16.gguf`
- Minimum RAM: 8 GB system RAM recommended (16 GB optimal).

**Production:**
- Standalone local deployment via `python start.py`.
- Cloud hosting supported on Streamlit Community Cloud (with cloud provider API keys and user consent enabled).
- Containerized development supported via `.devcontainer`.

---

*Stack analysis: 2026-10-13*
*Update after major dependency changes*
