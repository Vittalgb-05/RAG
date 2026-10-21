<!-- GSD:project-start source:PROJECT.md -->
## Project

**Local-First Multimodal PDF Intelligence System**

A local-first, privacy-respecting PDF intelligence application that delivers fast, accurate summarization and grounded question answering across digital, scanned, and visually complex documents (diagrams, charts, tables). Designed to run primarily on consumer hardware (single-user laptop with 4 GB GPU VRAM) with optional, explicitly configured cloud model fallback.

**Core Value:** Fast, evidence-grounded document summarization and question answering with visual understanding and verifiable page-level citations, operating completely locally within a 4 GB VRAM envelope.

### Constraints

- **Hardware / VRAM**: Strict 4 GB VRAM ceiling. Only one LLM/VLM active in memory at a time; serialized via `InferenceGate`; quantized GGUF (4-bit); conservative context window (4K–8K tokens). Preprocessing (Docling, RapidOCR, embeddings) offloaded to CPU to prevent VRAM exhaustion.
- **Platform**: Windows host OS with PowerShell (primary); Linux x86_64 / Docker Compose supported. Python 3.11+.
- **Privacy & Security**: Zero external network egress during local operation; external markdown links and unsafe embeds neutralized in local mode; credentials kept in `.env` / environment variables / session state; documents treated as untrusted input.
- **Architecture**: Modular monolith with decoupled presentation, orchestration services, domain logic, persistence, and inference providers.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

### Languages & Runtime
- **Python 3.11+** — all application code (`main.py`, `start.py`, `setup.py`, domain modules, `ui/` package, and `tests/`).
- **CPython 3.11** runtime on Windows 11 and Linux (`Dockerfile` based on `python:3.11-slim-bookworm`).
- **Streamlit 1.42.0** — web presentation server running on port `8501`.
- **llama.cpp / llama-server `b11718`** — native local inference server bound to `127.0.0.1:8080`.
- **pip** with universal lockfile `requirements-lock.txt` (uv-compiled for Python 3.11); editable packaging via `setup.py`.
- **No JavaScript, TypeScript, or CSS files** — UI is pure Python with dynamic AMOLED CSS injection in `ui/theme.py` and local monochrome SVGs in `assets/icons/`.

### Core Frameworks & Libraries
- **Streamlit 1.42.0** (`main.py`, `ui/*`) — Chatbot-first AMOLED user interface, workspace router, session hydration.
- **Pydantic 2.11.9** (`models.py`, `model_provider.py`) — Canonical data schemas (`Document`, `Page`, `Chunk`, `EvidenceElement`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`).
- **LanceDB 0.40.0 & PyArrow 23.0.1** (`hybrid_retriever.py`) — Persistent vector index and native Full-Text Search (FTS) with Reciprocal Rank Fusion (RRF).
- **SQLite (sqlite3 WAL mode)** (`doc_store.py`) — Relational metadata store at `data/documents.db` with schema migrations v1–v4, indexing `chunks(doc_id)` and `pages(doc_id)`, plus physical `VACUUM` on purge.
- **sentence-transformers 3.4.1** (`local_embedding.py`) — CPU-pinned `all-MiniLM-L6-v2` dense embeddings (384-dimensional, L2-normalized).
- **Docling 2.138.0** (`ingestion/docling_reader.py`) — Structured layout parsing, reading order, and markdown table extraction with automatic `pypdf` fallback.
- **pypdf 5.3.0** (`ingestion/pdf_reader.py`, `ingestion/upload_validation.py`) — Text extraction, page accounting, and magic-byte validation (`%PDF`).
- **RapidOCR** (`ingestion/ocr_fallback.py`) — CPU-friendly ONNX OCR fallback (`rapidocr-onnxruntime==1.4.4` for Python <3.13; `rapidocr==3.10.0` for >=3.13).
- **PyMuPDF 1.28.2 (`pymupdf` as `fitz`)** (`ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`) — PDF page rasterization and 2× visual bounding box cropping.
- **httpx 0.28.1** (`providers/llama_cpp_provider.py`) — HTTP/SSE client communicating with local llama-server with strict loopback/SSRF enforcement.
- **LiteLLM 1.105.0 & Groq 0.15.0** (`providers/litellm_provider.py`, `providers/groq_provider.py`) — Optional cloud model adapters with cryptographic/permission consent gates and key scrubbing.
- **psutil 6.1.1 & nvidia-smi** (`core/resource_telemetry.py`) — Hardware telemetry for RAM RSS and GPU VRAM with 5s caching.

### Testing & Code Quality
- **pytest >= 8.3.0** — 296 tests across 29 test suites in `tests/`, configured in `pyproject.toml`.
- **reportlab >= 4.2.0** — Synthetic PDF corpus generator (`tests/data/corpus/generate_corpus.py`).
- **Ruff >= 0.9.0** — Linter and code formatter (`pyproject.toml: line-length = 120`, target `py311`).
- **GitHub Actions** (`.github/workflows/ci.yml`) — CI pipeline running Ruff check, Ruff format check, corpus generation, and pytest.

### Key Entry Points & CLI
- `python start.py --start-llama` — Unified launcher running pre-flight hardware checks, launching llama-server, and starting Streamlit.
- `streamlit run main.py` — Direct Streamlit frontend launch.
- `python setup.py download-models` / `install-llama` — Automated setup CLI for model weights and server binaries.
- `docker-compose up` — Multi-container setup (app + optional CUDA llama-server service).
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

### Naming Patterns
- **Package Layout:** Organized by responsibility: `core/` (models, storage, LLM facade, summarizer, citation validator, prompt budgeting, telemetry), `retrieval/` (hybrid retriever, vector index, embeddings), `ingestion/` (upload validation, docling reader, pdf reader, OCR fallback, visual analyzer), `providers/` (model provider ABC, llama.cpp, LiteLLM, Groq), `ui/` (views, components, theme, services).
- **Root Entry Points:** Minimal root containing only `main.py`, `start.py`, and `setup.py`.
- **Classes:** `PascalCase`: `DocStore`, `HybridRetriever`, `AiModel`, `IngestionService`, `LifecycleService`, `InferenceGate`, `VisualAnalyzer`, `Summarizer`.
- **Data Models:** Pydantic v2 classes in `core/models.py` (`Chunk`, `Page`, `Document`, `EvidenceElement`, `RetrievalResult`, `SummaryResult`).
- **Functions:** `snake_case`, verb-first for actions (`ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`).
- **UI Renderers:** Named `render_<area>` returning `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`.
- **Tests:** `tests/test_<module_or_feature>.py` with test functions `test_<behavior>_<condition>`.

### Code Style & Tooling
- **Linting & Formatting:** Enforced via Ruff (`ruff check .` and `ruff format --check .`). Indentation is 4 spaces; strings and f-strings use double quotes; line length soft cap is 120 columns.
- **Type Annotations:** PEP 604 syntax (`str | None`, `list[dict[str, Any]]`) on all public boundaries. Abstract collections imported from `collections.abc` (`Callable`, `Generator`).
- **Docstrings:** Top-of-file `"""..."""` module docstrings on every module stating purpose and invariants. Google-style `Args:` / `Returns:` on public methods without type repetition.
- **Logging:** Structured logging via `logger = logging.getLogger(__name__)`. Benign watcher warnings suppressed via `core/logging_setup.py`.

### Architecture & Lifecycle Rules
- **GPU Concurrency Gate:** All LLM generation, VLM visual inspection, and summarization calls MUST acquire `InferenceGate.hold(timeout=60.0)` to respect the 4 GB VRAM ceiling.
- **Transactional State Mutation:** UI components never manipulate database records directly; all ingestion goes through `IngestionService` and all deletion/purging/re-indexing goes through `LifecycleService`.
- **Upload Loop Prevention:** `st.session_state.uploader_key` is dynamically rotated (`uploader_key += 1`) after processing uploads, and `new_docs_indexed` is incremented only for freshly ingested files.
- **Privacy & Egress Boundary:** In local mode, `ui/sanitizer.py` strips `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`, and neutralizes external Markdown/HTML links to prevent browser network egress.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

### System Overview
```text
┌───────────────────────────────────────────────────────────────────────────┐
│ Presentation (Streamlit script, chatbot-first, AMOLED theme)              │
│  `main.py`  ·  `ui/views.py`  ·  `ui/components.py`  ·  `ui/theme.py`      │
│  `ui/sanitizer.py`  ·  `.streamlit/config.toml`  ·  `assets/icons/*.svg`   │
└───────────────┬───────────────────────────────────────────┬───────────────┘
                │                                           │
                ▼                                           ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│ UI Orchestration Services         │   │ Core Domain Services              │
│ `ui/ingestion_service.py`         │   │ `core/local_llm.py` (AiModel)     │
│ `ui/lifecycle_service.py`         │   │ `core/summarizer.py` (map-reduce) │
│ `ui/hydration.py`                 │   │ `core/citation_validator.py`      │
│                                   │   │ `core/prompt_budget.py`           │
└───────────────┬───────────────────┘   └───────────────┬───────────────────┘
                │                                       │
                ▼                                       ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Ingestion & Retrieval Pipeline                                            │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`           │
│ → `ingestion/pdf_reader.py` (fallback) → `ingestion/ocr_fallback.py`       │
│ → `ingestion/visual_analyzer.py` (VLM crops)                              │
│ → `retrieval/local_embedding.py` (MiniLM) → `retrieval/hybrid_retriever.py`│
└───────────────┬───────────────────────────────────────────┬───────────────┘
                │                                           │
                ▼                                           ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│ Persistence                       │   │ Inference Providers               │
│ `core/doc_store.py` (SQLite)      │   │ `providers/model_provider.py`(ABC)│
│ `retrieval/hybrid_retriever.py`   │   │ `providers/llama_cpp_provider.py` │
│ `retrieval/vector_index.py`       │   │ `providers/litellm_provider.py`   │
│ `core/models.py` (cache_dir_for)  │   │ `providers/groq_provider.py`      │
└───────────────────────────────────┘   └───────────────────────────────────┘
```

### Layer Responsibilities
1. **Presentation (`main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`):**
   - Pure server-side Streamlit layout with custom AMOLED dark theme (`#050608`), 0 emojis, local SVG iconography.
   - Four primary workspaces: **Chat** (conversational evidence QA with citation chips and drawer), **Summarizer** (5 hierarchical profiles with export), **Document Library** (lifecycle inspect, re-index, delete, purge), and **Settings** (VRAM/RAM telemetry, model health, local/cloud privacy controls).
   - `main.py` serves as the composition root, managing session state, hydration, and routing.

2. **UI Orchestration Services (`ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`):**
   - `IngestionService`: Encapsulates validation, deduplication, structured extraction, OCR fallback, visual analysis, embedding, and storage transactions with progress reporting.
   - `LifecycleService`: Provides atomic single-document deletion, full database purging with physical `VACUUM`, and vector re-indexing across SQLite, LanceDB, disk cache, and session state.
   - `Hydration`: Rebuilds document catalog on initial browser load, verifies LanceDB vector integrity, and auto-repairs missing vectors from SQLite chunks.

3. **Domain Services (`local_llm.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`):**
   - `AiModel`: Facade orchestrating provider routing, conversation memory, retrieval context assembly, token streaming, and citation validation.
   - `InferenceGate`: Global concurrency lock strictly serializing LLM, VLM, and summarizer inference to guarantee the 4 GB VRAM envelope.
   - `Summarizer`: Multi-profile summarizer supporting fast single-pass and token-budgeted map-reduce with SQLite cache invalidation keyed to model version.
   - `CitationValidator`: Verifies `[E#]` citation precision (>=95% target), detects insufficient evidence, and flags prompt injections.
   - `PromptBudget`: Enforces conservative token budgets (4K–8K context) and XML `<document_context>` isolation.

4. **Ingestion & Retrieval Pipeline:**
   - `UploadValidation`: Enforces 50 MB / 500 page limits, `%PDF` magic bytes, and generates stable `doc_<sha16>` identifiers.
   - `DoclingReader`: Extracts document layout, reading order, and markdown tables; automatically falls back to `PdfReader` if layout parsing fails.
   - `OcrFallback`: Triggers RapidOCR ONNX engine selectively for scanned pages (< 50 characters) with image dimension and memory guards.
   - `VisualAnalyzer`: Detects figures/tables with PyMuPDF, rasterizes 2× crops, and generates visual descriptions via local VLM. Filters failed/placeholder outputs from being indexed.
   - `HybridRetriever`: Dual-pool candidate retrieval (LanceDB dense cosine vector search + BM25 Full-Text Search) fused via Reciprocal Rank Fusion (RRF). Falls back to in-memory `VectorIndex` if LanceDB is unavailable.

5. **Persistence & Storage:**
   - **SQLite (`data/documents.db`):** Source of truth for document metadata, chunks, pages, evidence elements, and summaries. Schema migrations v1–v4.
   - **LanceDB (`data/lancedb/`):** Persistent vector and FTS index.
   - **Local Disk Cache (`.cache/<sha256>/<version>/`):** Cached intermediate extractions (`pages.json`, `chunks.json`, `manifest.json`).

6. **Inference Providers:**
   - `BaseModelProvider` (ABC) defining text generation, streaming, image analysis, and health telemetry contracts.
   - `LlamaCppProvider`: Default local inference provider connecting to local llama-server on `127.0.0.1:8080`.
   - `LiteLLMProvider`: Optional cloud adapter supporting Groq, OpenAI, and Anthropic with mandatory user consent checks and API key scrubbing.
   - `GroqProvider`: Direct Groq client fallback.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
