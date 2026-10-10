# Architecture Research

**Domain:** Local-First Multimodal PDF Intelligence & RAG  
**Researched:** 2026-10-10  
**Confidence:** HIGH  

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Streamlit Presentation Layer (app.py)                 │
├───────────────────┬─────────────────────┬───────────────────┬───────────────┤
│  Document Upload  │  Summary Profiles   │  Chat Interface   │ Citation View │
│  & File Validator │  & Markdown Render  │  & Token Stream   │ & Source Draw │
└─────────┬─────────┴──────────┬──────────┴─────────┬─────────┴───────┬───────┘
          │                    │                    │                 │
          ▼                    ▼                    ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Core Service Orchestration                         │
├────────────────────┬─────────────────────┬──────────────────┬───────────────┤
│ Ingestion & Parse  │ Summarization       │ QA & Grounding   │ Evidence &    │
│ (Docling/RapidOCR) │ Service             │ Service          │ Citations     │
└─────────┬──────────┴──────────┬──────────┴────────┬─────────┴───────┬───────┘
          │                     │                   │                 │
          ▼                     ▼                   ▼                 ▼
┌────────────────────────────────────────┐ ┌──────────────────────────────────┐
│             Storage Layer              │ │         Inference Layer          │
├──────────────────┬─────────────────────┤ ├────────────────┬─────────────────┤
│ LanceDB Store    │ SQLite Metadata     │ │ llama-server   │ LiteLLM Adapter │
│ (Hybrid Vector & │ (Docs, Hashes,      │ │ (Local Qwen-VL │ (Optional Cloud │
│  Full-Text Search│  Page Status, Refs) │ │  2B GGUF)      │  Fallback)      │
└──────────────────┴─────────────────────┘ └────────────────┴─────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Ingestion Service** | Validates PDF signatures, computes SHA-256 hash, runs Docling extraction, conditionally invokes RapidOCR for low-text pages, and extracts structured elements. | Python module with Docling `DocumentConverter` and RapidOCR ONNX runtime. |
| **Document Normalizer** | Transforms raw Docling elements into canonical Pydantic models (`Document`, `Page`, `EvidenceElement`, `Chunk`). | Pure Python Pydantic v2 schemas with strict field validation. |
| **Storage Layer** | Stores document metadata and status transactionally in SQLite; stores chunks and embeddings in LanceDB for hybrid search; persists visual crops in filesystem. | SQLite3 (`sqlite3` stdlib) + LanceDB (`lancedb.connect`). |
| **Retrieval Service** | Performs semantic dense vector search + BM25/FTS keyword search; merges candidates using Reciprocal Rank Fusion (RRF); filters by document/page. | LanceDB hybrid query API (`table.search().where().limit()`). |
| **Vision Service** | Detects chart/diagram/table elements; crops image segments; queries local VLM via llama-server; attaches structured descriptions with version provenance. | Pillow / PyMuPDF + HTTP client to `llama-server /v1/chat/completions`. |
| **Summarization Service** | Coordinates hierarchical map-reduce summarization across sections/pages for 5 defined profiles while preserving evidence links. | Structured prompt pipelines using llama-server context window. |
| **QA & Citation Service** | Formats grounded prompt with numbered evidence IDs; invokes streaming generation; validates answer citations against retrieved records (>=95% target). | Shared retrieval context, token streamer, regex citation validator. |
| **Model Provider Adapter** | Abstracts local llama-server and optional cloud LiteLLM behind a unified interface (`generate_text`, `analyze_image`, `stream_text`). | Unified Python abstract base class (`BaseModelProvider`). |

## Recommended Project Structure

```
c:\Users\OM Prakash\Documents\RAG\
├── app.py                     # Main Streamlit application entry point
├── config/
│   ├── __init__.py
│   ├── settings.py            # Pydantic Settings / YAML configuration loader
│   └── settings.yaml          # Default runtime thresholds, model paths, ports
├── models/
│   ├── __init__.py
│   ├── document.py            # Canonical Document, Page, and Chunk models
│   ├── evidence.py            # EvidenceElement, BoundingBox, VisualDescription
│   └── response.py            # SummaryResponse, QAResponse, Citation
├── services/
│   ├── __init__.py
│   ├── ingestion.py           # File validation, Docling parsing, conditional OCR
│   ├── normalization.py       # Conversion to canonical Pydantic models
│   ├── storage.py             # SQLite metadata store & LanceDB hybrid vector store
│   ├── embeddings.py          # Local Sentence-Transformers wrapper
│   ├── retrieval.py           # Hybrid search & reciprocal rank fusion
│   ├── vision.py              # Visual element detection & VLM inspection
│   ├── summarization.py       # Hierarchical multi-profile summarization
│   └── qa.py                  # Grounded QA and citation verification
├── providers/
│   ├── __init__.py
│   ├── base.py                # BaseModelProvider abstract interface
│   ├── llama_cpp.py           # Local llama-server HTTP client adapter
│   ├── litellm_provider.py    # Optional cloud model adapter
│   └── router.py              # Local-first routing and capability checker
├── data/                      # Local data artifacts (.gitignored)
│   ├── sqlite/                # SQLite metadata database (documents.db)
│   ├── lancedb/               # LanceDB persistent tables
│   ├── renders/               # Rendered page images and figure crops
│   └── cache/                 # Extraction and summary caches
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures, test corpus paths, mocks
    ├── test_ingestion.py      # PDF validation, Docling parsing, OCR gating
    ├── test_storage.py        # SQLite & LanceDB persistence and retrieval
    ├── test_providers.py      # llama-server & LiteLLM adapter tests
    ├── test_citations.py      # Citation validation and grounding tests
    └── test_summaries.py      # Summary hierarchy and profile tests
```

### Structure Rationale

- **Decoupled `services/` and `providers/`:** Business logic does not know or care whether inference is running on local llama-server or cloud LiteLLM.
- **Explicit `models/` Layer:** Pydantic schemas prevent data model drift between ingestion, storage, retrieval, and UI.
- **Isolated `data/` Directory:** Clean separation between codebase and binary runtime artifacts (databases, crops, caches), easily ignored by git.
- **Co-located `tests/` Suite:** High testability with fixtures for mocking external LLM endpoints and testing against sample PDFs.

## Architectural Patterns

### Pattern 1: Provider Abstraction with Local-First Routing

**What:** An abstract base provider interface (`BaseModelProvider`) implemented by `LlamaCppProvider` (local) and `LiteLLMProvider` (cloud), governed by a `ProviderRouter`.  
**When to use:** All LLM/VLM generation, streaming, and image analysis calls.  
**Trade-offs:** Adds a thin wrapper layer, but completely decouples business logic from specific API SDKs and guarantees local-first privacy enforcement.

**Example:**
```python
class BaseModelProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str, max_tokens: int) -> str: ...
    @abstractmethod
    def stream_text(self, prompt: str, system_prompt: str, max_tokens: int) -> Iterator[str]: ...
    @abstractmethod
    def analyze_image(self, image_bytes: bytes, prompt: str) -> str: ...
```

### Pattern 2: Single Shared Retrieval Context for Generation & Citations

**What:** The retrieval step produces a single `RetrievalResult` object containing numbered candidate chunks. Both the prompt context assembly and the UI "Sources used" display consume this exact same object.  
**When to use:** Every QA interaction (`services/qa.py`).  
**Trade-offs:** Resolves `CONCERNS.md #5` where different queries caused displayed sources to diverge from the model's actual context.

### Pattern 3: Conditional OCR & Selective Visual Inspection

**What:** Ingestion extracts digital layout first. RapidOCR is invoked only if page character count falls below a threshold (< 50 characters). Vision model is invoked only if an element is classified as a chart/diagram/figure.  
**When to use:** Ingestion and visual understanding pipeline.  
**Trade-offs:** Prevents GPU/CPU starvation on 20+ page digital documents while preserving visual comprehension where needed.

## Data Flow

### Request Flow

```
[User uploads PDF or asks Question]
    ↓
[Streamlit app.py] ──passes input──> [Service Layer]
                                         ↓
                     ┌───────────────────┴───────────────────┐
                     ▼                                       ▼
             [Document Ingestion]                   [Grounded QA Service]
                     ↓                                       ↓
             [Docling / RapidOCR]                    [LanceDB Hybrid Search]
                     ↓                                       ↓
             [Store SQLite & LanceDB]                [Shared Evidence Context]
                                                             ↓
                                                     [llama-server VLM]
                                                             ↓
                                                     [Stream to UI with Verified Citations]
```

### Key Data Flows

1. **Ingestion & Indexing Flow:**
   User drops PDF → Compute SHA-256 → Check SQLite (cache hit?) → Docling extracts sections/tables/figures → Conditional RapidOCR → Store canonical records in SQLite → Generate dense embeddings → Upsert chunks to LanceDB.
2. **Grounded QA Flow:**
   User enters question → LanceDB executes vector + BM25 search → RRF ranks top candidates → Build prompt with explicit `[Evidence ID: X]` tags → `LlamaCppProvider` streams tokens to Streamlit → Answer parsed for citations → Verify citations against `RetrievalResult` → Display answer + evidence expandable chips.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **Single User (Current)** | Modular monolith in single Python process; local SQLite + LanceDB; 1 LLM loaded in VRAM. |
| **Large Documents (100+ pages)** | Chunked batch ingestion with SQLite checkpointing; hierarchical map-reduce summarization. |
| **High Query Volume** | Run LanceDB in standalone disk index mode; separate CPU embedding process if GPU is saturated. |

## Anti-Patterns

### Anti-Pattern 1: In-Memory Unpersisted Vector Search
- **Mistake:** Storing raw python lists in Streamlit `session_state` without disk serialization (`vector_index.py`).
- **Why it's wrong:** Restarts force 100% re-embedding, high memory consumption, loss of session data.
- **Do this instead:** Persist vectors and metadata in LanceDB on disk.

### Anti-Pattern 2: Unchecked Concurrent GPU Workloads
- **Mistake:** Running Sentence-Transformers on CUDA while llama-server and Docling are actively allocating GPU memory.
- **Why it's wrong:** Instantly crashes on RTX 3050 (4 GB VRAM limit) with `CUDA out of memory`.
- **Do this instead:** Pin embeddings and OCR to CPU or sequence inference strictly.

## Sources

- Architecture assessment of current codebase (`.planning/codebase/ARCHITECTURE.md`).
- LanceDB Python API and persistent storage architecture.
- llama.cpp server multi-modal REST specification.

---
*Architecture research for: Local-First Multimodal PDF Intelligence System*  
*Researched: 2026-10-10*
