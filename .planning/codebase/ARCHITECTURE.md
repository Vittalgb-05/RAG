# Architecture

**Analysis Date:** 2026-10-13

## Pattern Overview

**Overall:** Local-First Multimodal Retrieval-Augmented Generation (RAG) Architecture with Strictly Bounded Local Resources and Opt-in Cloud Privacy Gating.

**Key Characteristics:**
- **Strict Local Hardware Envelope:** Designed to run 100% locally on consumer hardware within a 4 GB GPU VRAM ceiling (Qwen3-VL 2B quantized GGUF allocated ~2.4 GB VRAM; embeddings, layout parsing, OCR, and vector storage pinned strictly to CPU and system RAM).
- **Zero-Egress by Default:** Embeddings, vector index, SQLite metadata store, and local inference run with zero outbound network egress. Cloud execution (via LiteLLM / Groq) is strictly opt-in and blocked by a programmatic consent assertion gate (`_assert_consent()`).
- **Evidence-Grounded Attribution:** All answer generations require verifiable snippet-level bracketed citations (`[E1]`, `[E2]`) or page citations (`(p. X)`), validated post-generation by an automated citation verification engine (`citation_validator.py`).
- **Thread-Safe GPU Inference Gate:** A reentrant lock (`InferenceGate` in `local_llm.py`) serializes local model access to prevent concurrent prompt collisions and GPU out-of-memory crashes.

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        Streamlit UI & Orchestration                     │
│  `main.py` — Streamlit web interface with Tabbed Workspace:            │
│  - Tab 1: Grounded Chat & Question Answering                          │
│  - Tab 2: Hierarchical Document Summarization                         │
│  - Sidebar: PDF Upload, Telemetry Widget, Privacy & Provider Controls │
│  - Anchored absolute storage paths (`APP_DIR`, `DOC_STORE_PATH`)       │
│  - Session-scoped `AiModel` preventing cross-user routing bleed        │
│  - Clear Session (memory reset) vs Purge All Data (disk wipe)          │
├────────────────────┬────────────────────┬──────────────────────────────┤
│  Ingestion         │  Hybrid Retrieval  │  Inference & Generation      │
│  (100% Local)      │  (100% Local)      │  (Gated & Mode-Switched)     │
│  `upload_          │  `hybrid_          │  `model_provider.py`         │
│   validation.py`   │   retriever.py`    │   (BaseModelProvider ABC)    │
│  `docling_         │   (LanceDB table   │  `llama_cpp_provider.py`     │
│   reader.py`       │    + BM25 + RRF)   │   (Local loopback client)    │
│  `ocr_fallback.py` │  `local_           │  `litellm_provider.py`       │
│   (RapidOCR ONNX)  │   embedding.py`    │   (Consented cloud router)   │
│  `visual_          │   (Shared CPU      │  `groq_provider.py`          │
│   analyzer.py`     │    MiniLM-L6 cache)│   (Direct Groq provider)     │
│   (2x crop + VLM)  │  `vector_index.py` │  `local_llm.py`              │
│  `pdf_reader.py`   │   (In-memory       │   (InferenceGate + AiModel)  │
│   (Digital pypdf)  │    fallback)       │  `summarizer.py`             │
│                    │                    │  `prompt_budget.py`          │
│                    │                    │  `citation_validator.py`     │
└─────────┬──────────┴─────────┬──────────┴──────────────┬───────────────┘
          │                    │                         │
          ▼                    ▼                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Persistence & Telemetry Layer                     │
│  `doc_store.py` (SQLite WAL metadata store: documents, pages, chunks,  │
│   evidence_elements, summary_cache)                                    │
│  `hybrid_retriever.py` (LanceDB persistent storage at `data/lancedb`)   │
│  `resource_telemetry.py` (nvidia-smi TTL cache, psutil RSS/VMS,        │
│   stage latency tracker)                                               │
└────────────────────────────────────────────────────────────────────────┘
```

## Layers

### 1. Presentation & Application Layer (`main.py`, `start.py`, `setup.py`)
- **Purpose:** Entry points, browser UI reactivity, session management, and startup preflight orchestration.
- **Contains:** Streamlit application lifecycle, file upload handlers, telemetry expander widgets, privacy dialog modals, chat message history renderers, and launcher CLI routines.
- **Depends on:** Ingestion layer, Retrieval layer, Inference layer, and Telemetry layer.
- **Used by:** End-user interacting via web browser or command line.

### 2. Ingestion & Visual Analysis Layer (`upload_validation.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `pdf_reader.py`)
- **Purpose:** Securely accept, validate, parse, extract, OCR, and crop multimodal components from uploaded PDFs.
- **Contains:**
  - `upload_validation.py`: `%PDF-` magic-byte verification, 50 MB / 500 page caps, and deterministic SHA-256 chunk hashing.
  - `docling_reader.py`: Structured layout parsing recovering reading order and markdown tables.
  - `ocr_fallback.py`: Conditional RapidOCR ONNX fallback triggered when character density is `<50` chars/page.
  - `visual_analyzer.py`: PyMuPDF drawing and image detection, 2x zoom PNG cropping (capped to 2048x2048), and VLM prompt dispatch.
  - `pdf_reader.py`: Digital text extraction fallback and recursive text splitting (chunk size 1000, overlap 200).
- **Depends on:** `models.py` (data schemas) and `model_provider.py` (for VLM visual description calls).
- **Used by:** `main.py` ingestion routines.

### 3. Retrieval & Indexing Layer (`local_embedding.py`, `vector_index.py`, `hybrid_retriever.py`)
- **Purpose:** Vector embedding computation, persistent on-disk indexing, full-text inverted indexing, and hybrid Reciprocal Rank Fusion.
- **Contains:**
  - `local_embedding.py`: CPU-pinned `sentence-transformers` singleton (`all-MiniLM-L6-v2`) producing 384-dimensional normalized vectors.
  - `hybrid_retriever.py`: Persistent LanceDB on-disk storage (`data/lancedb`), BM25 full-text keyword indexing, and Reciprocal Rank Fusion (`compute_rrf` with $k=60$).
  - `vector_index.py`: In-memory linear scan cosine similarity fallback for environments where LanceDB binary drivers are unavailable.
- **Depends on:** `models.py` schemas (`Chunk`, `EvidenceSnippet`, `RetrievalResult`).
- **Used by:** `local_llm.py` and `main.py`.

### 4. Inference & Prompt Budget Layer (`model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `local_llm.py`, `prompt_budget.py`)
- **Purpose:** Hardware-gated text and token generation, prompt assembly with XML injection defense, and multi-provider routing.
- **Contains:**
  - `model_provider.py`: `BaseModelProvider` interface defining `generate_text`, `stream_text`, `analyze_image`, and `check_health`.
  - `llama_cpp_provider.py`: Local client communicating with `llama-server` on loopback `http://127.0.0.1:8080`.
  - `litellm_provider.py`: Cloud router to Groq, OpenAI, and Anthropic models with strict `_assert_consent()` privacy gating.
  - `groq_provider.py`: Direct Groq client implementation.
  - `local_llm.py`: Reentrant GPU lock (`InferenceGate`) and high-level orchestrator (`AiModel`).
  - `prompt_budget.py`: XML context encapsulation (`<document_context>`), context budget truncation, and prompt injection neutralization (`sanitize_xml_boundary`).
- **Depends on:** `models.py` and external or local inference servers.
- **Used by:** `main.py` and `summarizer.py`.

### 5. Verification & Grounding Layer (`citation_validator.py`, `summarizer.py`)
- **Purpose:** Enforce strict factual grounding, verify bracketed snippet citations against retrieved context, detect abstention, and run multi-profile hierarchical summarization.
- **Contains:**
  - `citation_validator.py`: Regex extraction of `[E1]`, `[E2]` citations, validation of citation bounds against `RetrievalResult`, precision enforcement ($\ge 95\%$), and canonical abstention phrase detection.
  - `summarizer.py`: Map-reduce summarization with token budget caps and page citation preservation `(p. X)`.
- **Depends on:** `models.py`, `prompt_budget.py`, and `local_llm.py`.
- **Used by:** `main.py`.

### 6. Persistence & Telemetry Layer (`doc_store.py`, `resource_telemetry.py`)
- **Purpose:** Relational document metadata storage, chunk persistence, summary caching, and live VRAM/system telemetry.
- **Contains:**
  - `doc_store.py`: SQLite 3 WAL metadata store (`data/documents.db`) managing documents, pages, chunks, evidence elements, and cached summaries.
  - `resource_telemetry.py`: Live NVIDIA GPU VRAM query via `nvidia-smi` (with 5.0-second TTL cache lock), process RSS/VMS tracking via `psutil`, and rolling stage execution latency tracking.
- **Depends on:** Standard library `sqlite3`, `psutil`, and system `nvidia-smi`.
- **Used by:** Ingestion, retrieval, summarization, and frontend UI.

## Data Flow

### Flow 1: Document Upload & Ingestion
1. **User Action:** User drops a PDF into the Streamlit file uploader (`main.py`).
2. **Validation:** `upload_validation.py` inspects binary headers for `%PDF-`, checks size ($\le 50$ MB), verifies page count ($\le 500$), and computes streaming SHA-256 (`doc_<sha16>`).
3. **Deduplication Check:** `doc_store.py` queries SQLite for an existing document with the same SHA-256. If found and indexed, existing chunks and metadata are reloaded immediately without reprocessing.
4. **Layout & Text Extraction:**
   - Primary: `docling_reader.py` parses document layout, headings, and tables into markdown.
   - Fallback/OCR: `ocr_fallback.py` executes RapidOCR ONNX on pages with $<50$ characters or failed status.
   - Text Splitting: Chunks are normalized into canonical `Chunk` models (size 1000, overlap 200).
5. **Visual Region Detection:** `visual_analyzer.py` inspects PDF drawing instructions, extracts 2x PNG crops, and optionally queries VLM via `analyze_image` to generate `EvidenceElement` records.
6. **Persistence & Indexing:** Chunks and pages are written to `doc_store.py` (SQLite). CPU embeddings are computed by `local_embedding.py` and written to `hybrid_retriever.py` (LanceDB `chunks` table).

### Flow 2: Grounded Question Answering
1. **User Action:** User submits a natural language question via `st.chat_input`.
2. **Hybrid Search:** `hybrid_retriever.py` performs simultaneous vector k-NN search and BM25 full-text keyword search across LanceDB, merging top candidates via Reciprocal Rank Fusion into an immutable `RetrievalResult`.
3. **Prompt Budgeting & Isolation:** `prompt_budget.py` wraps retrieved snippet texts inside `<document_context>` XML tags, escaping any hostile closing tags. Token budget is clamped (4096 tokens max for local model), trimming conversation history oldest-first.
4. **Inference Execution:**
   - `InferenceGate` reentrant lock is acquired.
   - The active `BaseModelProvider` (local `LlamaCppProvider` or consented `LiteLLMProvider`) streams tokens incrementally via Server-Sent Events (SSE).
   - `st.write_stream` renders tokens live in the Streamlit UI.
   - `InferenceGate` is released.
5. **Post-Generation Validation:** `citation_validator.py` parses all bracketed citations (`[E1]`, `[E2]`) from the assistant response:
   - Verifies citation precision against the retrieved evidence ranks ($\ge 95\%$).
   - Flags hallucinated citation numbers or abstention mismatches.
   - Persists the validated turn into `st.session_state.chat_history` alongside provider provenance metadata.

### Flow 3: Hierarchical Summarization
1. **User Action:** User selects one of five summary profiles (`overview`, `detailed`, `study_notes`, `tables_figures`, `findings`) and clicks "Generate Summary".
2. **Cache Check:** `doc_store.py` checks SQLite for a valid cached summary for `(doc_id, profile, config_version)`. If present and `force_refresh=False`, returned in $<50$ ms.
3. **Budget & Path Selection:**
   - If total document tokens fit within the fast-path limit ($\le 2500$ tokens), a single-pass prompt is executed.
   - If larger, a sequential map-reduce pipeline bundles pages into chunks ($\le 2000$ tokens), generates intermediate section summaries, and reduces them into a final synthesis.
4. **Page Citation Preservation:** Prompt instructions enforce `(p. X)` page citations across all reduction stages.
5. **Storage:** The final summary markdown and cited pages are persisted to `doc_store.py`.

## Key Abstractions

- **`BaseModelProvider` (`model_provider.py`):** Abstract interface providing polymorphism between zero-egress local backends (`LlamaCppProvider`) and cloud APIs (`LiteLLMProvider`, `GroqProvider`).
- **`InferenceGate` (`local_llm.py`):** Thread-safe reentrant lock synchronizing GPU access to preserve the 4 GB VRAM limit.
- **`HybridRetriever` (`hybrid_retriever.py`):** Encapsulates dense vector similarity and sparse keyword BM25 retrieval behind a unified RRF ranking interface.
- **`DocStore` (`doc_store.py`):** Single source of truth for persistent relational metadata, utilizing WAL mode and per-operation connection contexts.
- **`Canonical Schemas` (`models.py`):** Pydantic v2 immutable contracts (`Chunk`, `Page`, `Document`, `EvidenceSnippet`, `RetrievalResult`, `EvidenceElement`, `SummaryResult`).

## Entry Points

1. **`start.py` (Application Launcher):** One-command orchestration entry point. Verifies Python 3.11+, scaffolds required directories, checks `llama-server` health, and launches Streamlit.
2. **`main.py` (Streamlit App):** Interactive web application entry point executed by `streamlit run main.py`.
3. **`setup.py` (Console Script Entry Point):** Registers `rag-assistant=start:main` console script.
4. **`scripts/profile_resources.py`:** Standalone benchmarking CLI measuring live GPU VRAM and process memory under pipeline load.
5. **`scripts/benchmark_multimodal.py`:** Standalone benchmarking CLI evaluating multimodal retrieval accuracy, citation precision, and abstention behavior.

## Error Handling

- **Page-Level Ingestion Fault Isolation:** A corrupt or unreadable page inside a multi-page PDF records a failed `Page` status in `doc_store.py` and continues processing remaining pages without aborting the entire document upload.
- **Graceful OCR & Layout Fallback:** If Docling fails or is uninstalled, processing degrades to `pdf_reader.py` (pypdf). If RapidOCR fails on a scanned page, the page is recorded as empty/failed while the document remains indexable.
- **Database Connection Lifecycle:** SQLite operations in `doc_store.py` execute within a `with self._connect() as conn:` context, preventing lingering file handles on Windows.
- **Privacy Gating Assertion:** If cloud mode is invoked without explicit user consent, `LiteLLMProvider` raises a descriptive `PermissionError` before any network packet is dispatched.
- **SSRF Loopback Defense:** `LlamaCppProvider` parses target endpoints with `ipaddress` and rejects non-loopback addresses with `ValueError` unless `allow_remote=True` is explicitly configured.

## Cross-Cutting Concerns

- **Memory & VRAM Management:** 4 GB VRAM envelope strictly guarded: GPU allocations restricted to quantized VLM inference; all embeddings, OCR, and vector operations pinned to CPU/RAM. Live VRAM monitored via 5.0-second TTL cached `nvidia-smi` queries.
- **Prompt Injection Defense:** Untrusted document text enclosed within `<document_context>` XML delimiters; embedded closing tags escaped via `sanitize_xml_boundary`.
- **Egress & Provenance Transparency:** Visual UI indicators distinguish between offline local inference (`🔒 100% Offline Local Pipeline`) and external cloud processing (`☁️ Cloud Inference`), displaying exact model names and citation drawers for every response.

---

*Architecture analysis: 2026-10-13*
*Update after major architectural refactoring*
