# Codebase Structure

**Analysis Date:** 2026-10-13

## Directory Layout

```
RAG/
├── start.py                   # One-command CLI launcher with preflight checks and Streamlit launch
├── setup.py                   # Setuptools packaging and console script definition (rag-assistant=start:main)
├── main.py                    # Streamlit web interface: chat, summarization, telemetry, and privacy controls
├── local_llm.py               # AiModel orchestrator and InferenceGate GPU concurrency lock
├── litellm_provider.py        # LiteLLM multi-cloud adapter with strict privacy consent assertion gate
├── llama_cpp_provider.py      # Local llama-server client with loopback SSRF defense
├── groq_provider.py           # Direct Groq Cloud provider adapter
├── model_provider.py          # BaseModelProvider abstract interface and capability schemas
├── summarizer.py              # Hierarchical 5-profile map-reduce document summarization service
├── citation_validator.py      # Post-generation bracketed citation and abstention verification engine
├── prompt_budget.py           # Context token budgeting, XML injection defense, and history bounding
├── hybrid_retriever.py        # Persistent LanceDB on-disk storage with BM25 and Reciprocal Rank Fusion
├── local_embedding.py         # CPU-pinned SentenceTransformers embedding model with shared process cache
├── vector_index.py            # In-memory linear scan cosine similarity vector fallback
├── doc_store.py               # SQLite WAL document metadata, chunk, and summary cache store
├── models.py                  # Canonical Pydantic v2 domain schemas and data models
├── upload_validation.py       # PDF header (%PDF-), size limit (50 MB), and page cap (500) validation
├── docling_reader.py          # Structured layout parsing and markdown table extraction via Docling
├── ocr_fallback.py            # Conditional RapidOCR ONNX fallback for low-text and scanned PDF pages
├── visual_analyzer.py         # Visual element detection, 2x PNG cropping, and VLM multimodal analysis
├── pdf_reader.py              # Digital PDF text extraction fallback and recursive chunking
├── resource_telemetry.py      # Live GPU VRAM (5.0s TTL cache), process memory, and stage latency tracking
├── pyproject.toml             # Ruff lint/formatting rules and Pytest configuration
├── requirements.txt           # Primary application dependencies manifest
├── requirements-lock.txt      # Fully pinned, reproducible uv production lockfile (targeting Python 3.11)
├── requirements-test.txt      # Testing and benchmarking dependencies
├── LICENSE                    # MIT License
├── README.md                  # Project overview, setup instructions, and quickstart guide
├── CLAUDE.md                  # Project guidelines, developer instructions, and execution workflows
├── .gitignore                 # Excludes .env, data/, .cache/, models/, and build artifacts
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI: uv installation, ruff check/format, corpus gen, pytest
├── .devcontainer/
│   └── devcontainer.json      # Container configuration for Codespaces and VS Code Dev Containers
├── application_screenshots/   # UI screenshots and application captures
├── data/                      # Persistent storage directory (gitignored): documents.db and lancedb/
├── docs/                      # Technical documentation and guides
│   ├── EVALUATION.md          # Benchmark results and system acceptance record
│   ├── LOCAL_INFERENCE.md     # Local llama-server setup, GGUF weights, and VRAM budget guide
│   └── RUNBOOK.md             # Operational procedures, deployment, and troubleshooting
├── scripts/                   # Benchmarking and resource profiling scripts
│   ├── benchmark_baseline.py  # End-to-end baseline retrieval and generation benchmark
│   ├── benchmark_multimodal.py # Multimodal evaluation harness testing accuracy, citations, and abstentions
│   └── profile_resources.py   # 6-stage hardware profiling script measuring VRAM and memory footprints
└── tests/                     # Automated test suite (24 modules + fixtures + synthetic corpus)
    ├── __init__.py            # Test package identifier
    ├── conftest.py            # Shared pytest fixtures, offline mock seams, and test helpers
    ├── data/
    │   └── corpus/
    │       └── generate_corpus.py # Synthetic multi-page test PDF generator using ReportLab
    ├── test_cache_invalidation.py # Tests for cache invalidation, session purges, and turn bounding
    ├── test_citation_validator.py # Tests for citation precision verification and abstention detection
    ├── test_cloud_privacy.py     # Tests for privacy consent toggles, provider switching, and zero-egress invariants
    ├── test_concurrency_lock.py   # Tests for InferenceGate reentrant locking and timeout behavior
    ├── test_doc_store.py          # Tests for SQLite CRUD, schema migrations, cascade deletions, and WAL mode
    ├── test_docling_reader.py     # Tests for Docling structured layout extraction and fallback paths
    ├── test_hybrid_retriever.py   # Tests for LanceDB vector search, BM25 indexing, and RRF fusion
    ├── test_litellm_provider.py   # Tests for LiteLLM multi-provider routing and consent enforcement
    ├── test_llama_cpp_provider.py # Tests for local llama-server REST client and loopback SSRF guards
    ├── test_local_embedding.py    # Tests for CPU-pinned embedding generation and shared model caching
    ├── test_local_llm.py          # Tests for AiModel orchestration, streaming generation, and prompt assembly
    ├── test_main_ui.py            # Tests for Streamlit UI state management and display contracts
    ├── test_model_provider.py     # Tests for BaseModelProvider interface contracts and capability schemas
    ├── test_models.py             # Tests for Pydantic v2 schemas, bounding-box math, and validation
    ├── test_ocr_fallback.py       # Tests for conditional RapidOCR triggering, DPI clamps, and page isolation
    ├── test_pdf_reader.py         # Tests for pypdf digital text extraction and character chunking
    ├── test_prompt_budget.py      # Tests for token budgeting, XML sanitization, and history bounding
    ├── test_resource_telemetry.py # Tests for nvidia-smi parsing, TTL caching, and psutil monitoring
    ├── test_summarizer.py         # Tests for map-reduce summarization profiles and page citation tracking
    ├── test_upload_validation.py  # Tests for upload security checks, magic bytes, and SHA-256 generation
    ├── test_vector_index.py       # Tests for in-memory linear cosine search fallback
    └── test_visual_analyzer.py    # Tests for visual element detection, cropping, and VLM invocation
```

## Directory Purposes

**Root Directory (`.`):**
- Purpose: Core application modules and package configuration. Employs a flat modular architecture where each service or component resides in a dedicated module file.
- Key files: `start.py`, `setup.py`, `main.py`, `models.py`, `local_llm.py`, `doc_store.py`, `hybrid_retriever.py`, `pyproject.toml`, `requirements.txt`.

**`docs/`:**
- Purpose: System runbooks, hardware specifications, and evaluation records.
- Key files:
  - `docs/RUNBOOK.md`: Installation steps, lockfile usage, operational procedures, and troubleshooting.
  - `docs/LOCAL_INFERENCE.md`: VRAM allocation table (2.4 GB model + 690 MB DWM = 3450 MB peak on 4 GB GPU), quantization details, and llama-server launch flags.
  - `docs/EVALUATION.md`: Performance acceptance criteria and benchmark summaries.

**`scripts/`:**
- Purpose: Standalone benchmarking CLI tools for profiling hardware resources and measuring grounded QA performance.
- Key files:
  - `scripts/benchmark_multimodal.py`: Runs automated accuracy and citation benchmarks against synthetic test corpus.
  - `scripts/profile_resources.py`: Executes 6-stage profiling of VRAM, RSS memory, and stage latencies.

**`tests/`:**
- Purpose: Pytest unit and integration test suite designed for 100% offline execution without requiring GPU hardware or live internet access.
- Key files:
  - `tests/conftest.py`: Provides mock fixtures (`mock_groq_client`, `mock_sentence_transformer`, `mock_llama_provider`) and temporary directories.
  - `tests/data/corpus/generate_corpus.py`: Generates synthetic digital, table-heavy, and scanned test PDFs via ReportLab.

**`data/`:**
- Purpose: Local persistent runtime data storage (gitignored).
- Contents: `documents.db` (SQLite relational database) and `lancedb/` (LanceDB vector and full-text index).

## Key File Locations

**Entry Points:**
- `start.py`: Application CLI launcher orchestrating preflight health checks and starting the Streamlit server.
- `main.py`: Streamlit frontend web application.
- `setup.py`: Standard setuptools packaging script defining console command `rag-assistant`.

**Configuration:**
- `pyproject.toml`: Ruff code formatting/linting rules and Pytest configuration options.
- `requirements.txt` & `requirements-lock.txt`: Runtime dependency manifests.
- `.env` (local file, gitignored): Environment variables for cloud API keys.

**Core Ingestion & Storage:**
- `upload_validation.py`: PDF binary validation and SHA-256 computation.
- `docling_reader.py`: Deep layout parsing and markdown table reconstruction.
- `ocr_fallback.py`: RapidOCR ONNX fallback engine.
- `visual_analyzer.py`: Multimodal visual bounding-box extraction and cropping.
- `doc_store.py`: SQLite document and chunk database.
- `hybrid_retriever.py`: Persistent LanceDB hybrid vector and FTS retrieval engine.

**Inference & Grounding:**
- `model_provider.py`: Core inference interface and schema definitions.
- `llama_cpp_provider.py`: Local loopback `llama-server` adapter.
- `litellm_provider.py`: Consent-gated cloud inference router.
- `local_llm.py`: GPU inference serialization gate and `AiModel` pipeline coordinator.
- `summarizer.py`: Map-reduce multi-profile document summarization engine.
- `citation_validator.py`: Automated bracketed evidence citation precision verifier.
- `prompt_budget.py`: Token budget management and XML prompt isolation.

## Naming Conventions

**Files & Directories:**
- Python Modules: `snake_case.py` (e.g., `hybrid_retriever.py`, `docling_reader.py`).
- Test Modules: `test_<module_name>.py` located in `tests/` (e.g., `test_hybrid_retriever.py`).
- Benchmark Scripts: `benchmark_<name>.py` or `profile_<name>.py` in `scripts/`.
- Markdown Documentation: `UPPER_SNAKE_CASE.md` for architectural reference (e.g., `RUNBOOK.md`, `LOCAL_INFERENCE.md`, `ARCHITECTURE.md`).

**Code Identifiers:**
- Classes: `PascalCase` (e.g., `HybridRetriever`, `LlamaCppProvider`, `InferenceGate`, `EvidenceSnippet`).
- Functions & Methods: `snake_case` (e.g., `compute_rrf`, `search_hybrid`, `validate_citations`).
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_DB_URI`, `MAX_FILE_MB`, `CONFIG_VERSION`, `DEFAULT_RRF_K`).
- Schema IDs: Prefixed identifier strings:
  - Document IDs: `doc_<sha16>` (e.g., `doc_a1b2c3d4e5f67890`)
  - Chunk IDs: `chk_<sha16>_<idx>` (e.g., `chk_a1b2c3d4e5f67890_0001`)
  - Element IDs: `elem_<sha16>_<p>_<kind>_<idx>`

## Where to Add New Code

**Adding a New Model Provider:**
- Implementation: Create `<provider>_provider.py` implementing `BaseModelProvider` from `model_provider.py`.
- Registration: Integrate provider instantiate/routing inside `AiModel._detect_provider()` in `local_llm.py` and Streamlit provider selector in `main.py`.
- Tests: Add `tests/test_<provider>_provider.py` with mock HTTP/SDK fixtures.

**Adding a New Ingestion Parser or Preprocessor:**
- Implementation: Add parser module or function in root (e.g., `<format>_reader.py`), returning canonical `Page` and `Chunk` models from `models.py`.
- Integration: Hook parser into upload processing loop in `main.py`.
- Tests: Add corresponding `tests/test_<format>_reader.py` with mock file streams.

**Adding a New Summarization Profile:**
- Configuration: Add profile name to `VALID_SUMMARY_PROFILES` in `models.py`.
- Prompt Instructions: Add markdown structure and guidance to `PROFILE_SYSTEM_INSTRUCTIONS` in `summarizer.py`.
- UI: Profile automatically propagates to Streamlit selectbox in `main.py`.
- Tests: Update `tests/test_summarizer.py` verifying profile generation.

**Adding a New CLI Benchmark or Evaluation:**
- Implementation: Add `scripts/benchmark_<name>.py` using `argparse` and outputting structured JSON metrics.
- Tests: Add lightweight execution test in `tests/`.

---

*Structure analysis: 2026-10-13*
*Update after directory structure changes*
