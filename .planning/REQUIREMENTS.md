# Requirements: Local-First Multimodal PDF Intelligence System

**Defined:** 2026-10-10  
**Core Value:** Fast, evidence-grounded document summarization and question answering with visual understanding and verifiable page-level citations, operating completely locally within a 4 GB VRAM envelope.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Ingestion & Structured Parsing

- [x] **INGEST-01**: User can upload PDF files through the Streamlit interface with client and server-side magic-byte (`%PDF`) validation, size limit checks, and page count limits.
- [x] **INGEST-02**: System validates document integrity, computes SHA-256 content hashes, detects duplicate uploads, and assigns stable document IDs independent of filename.
- [x] **INGEST-03**: System processes documents using Docling to extract reading order, headings, section hierarchy, tables, and figure references.
- [x] **INGEST-04**: System conditionally invokes local RapidOCR on pages with missing or unextractable text (< 50 characters) while bypassing OCR on clean digital pages.
- [x] **INGEST-05**: System isolates extraction failures at page level so errors on individual pages do not abort processing of remaining valid pages.

### Document Storage & Canonical Modeling

- [x] **STORE-01**: System persists document metadata, processing status, page counts, and extraction logs in an ACID-compliant local SQLite database.
- [x] **STORE-02**: System represents all document elements, pages, and chunks using typed Pydantic canonical models with explicit bounding-box coordinates and source extraction metadata.
- [x] **STORE-03**: System caches intermediate extraction artifacts, page renders, and crops on local disk keyed by SHA-256 and configuration versions.

### Local & Cloud Inference Infrastructure

- [x] **INF-01**: System provides a unified `BaseModelProvider` interface supporting text generation, token streaming, image analysis, and capability inspection.
- [x] **INF-02**: System implements a local `LlamaCppProvider` communicating with `llama-server` running a quantized 2B VLM (Qwen2-VL 2B GGUF Q4_K_M; filename retained as legacy `qwen3-vl-2b-instruct-q4_k_m.gguf`) with health checks and bounded context (4K-8K tokens).
- [x] **INF-03**: System operates 100% offline without outbound network calls during local mode.
- [x] **INF-04**: System implements an optional `LiteLLMProvider` enabling cloud model routing (Groq, OpenAI, Anthropic) only when explicitly configured and consented to by user.

### Visual Understanding

- [x] **VIS-01**: System identifies visual elements (charts, diagrams, flowcharts, figures, visual tables) and renders high-fidelity image crops using PyMuPDF/Pillow.
- [x] **VIS-02**: System queries local VLM with targeted prompts to generate structured visual descriptions for detected visual elements.
- [x] **VIS-03**: System stores visual descriptions as distinct derived artifacts tagged with model and version provenance, preventing ungrounded visual approximations from contaminating ground-truth table data.

### Persistent Hybrid Retrieval

- [x] **RETR-01**: System generates dense text embeddings using local Sentence-Transformers (`all-MiniLM-L6-v2`) pinned to CPU to protect the 4 GB GPU VRAM.
- [x] **RETR-02**: System indexes document chunks and embeddings into a persistent on-disk LanceDB table that survives application restarts.
- [x] **RETR-03**: System executes hybrid retrieval combining semantic vector search and full-text keyword search (BM25/FTS) with Reciprocal Rank Fusion (RRF).
- [x] **RETR-04**: System provides a single shared `RetrievalResult` context consumed identically by both generation prompts and citation display components.

### Grounded Question Answering & Citations

- [x] **QA-01**: User can ask natural-language questions and receive answers streamed live into the chat interface grounded in retrieved document evidence.
- [x] **QA-02**: System formats prompts with explicit numbered evidence identifiers (`[E1]`, `[E2]`) and strict boundaries preventing prompt injection from document text.
- [x] **QA-03**: System validates all generated citations against retrieved evidence records, enforcing a minimum 95% citation precision.
- [x] **QA-04**: System detects unanswerable queries and explicitly abstains ("The document does not contain sufficient evidence") without inventing citations.

### Hierarchical Multi-Profile Summarization

- [x] **SUMM-01**: User can generate document summaries across five distinct profiles: Overview, Detailed, Study Notes, Tables & Figures, and Findings.
- [x] **SUMM-02**: System executes hierarchical map-reduce summarization for multi-page documents while maintaining source page references across reduction stages.
- [x] **SUMM-03**: System caches generated summaries by document hash and profile type to deliver near-instant repeated requests.

### User Interface & Experience

- [x] **UI-01**: User can view upload progress, parsing stage, and indexing status indicators inside Streamlit.
- [x] **UI-02**: User can select summary profiles and view formatted markdown summaries with expandable source page references.
- [x] **UI-03**: User can view interactive evidence chips and drawer alongside chat answers showing the exact cited text and page number.
- [x] **UI-04**: User can toggle between Local and Cloud modes with explicit warning and credential configuration dialogs.

### Quality, Performance & Process Assurance

- [x] **QUAL-01**: System guarantees memory safety on 4 GB VRAM (RTX 3050 Laptop) by enforcing max one active LLM on GPU and cold/warm memory benchmarks.
- [x] **QUAL-02**: System maintains an automated Pytest test suite covering ingestion, retrieval, citation precision, and provider fallbacks.
- [x] **QUAL-03**: Agents and workflows execute structured git commits per planning, execution, review, and verification phases.
- [x] **QUAL-04**: Agents inspect `.planning/codebase/` documentation prior to planning and update `CONCERNS.md` and CI/CD workflows across every phase.

## v2 Requirements

Deferred to future releases.

### Advanced Capabilities

- **V2-01**: Interactive PDF visual bounding-box overlay highlighting cited sentences directly inside an in-browser PDF viewer.
- **V2-02**: Cross-document multi-PDF search and comparative summarization.
- **V2-03**: Local fine-tuning and domain adaptation pipeline for technical figures.

## Out of Scope

Explicitly excluded to protect the 4 GB VRAM hardware budget and local single-user scope.

| Feature | Reason |
|---------|--------|
| Multi-user enterprise deployment & auth | Single-user local desktop application; multi-tenancy adds unnecessary database overhead. |
| Distributed microservices (Celery, Kafka, Redis) | Modular monolith in Python runs efficiently as a single process on local hardware. |
| Multi-agent orchestration frameworks (LangChain agents) | Unpredictable recursive LLM loops and token blowouts; deterministic service architecture preferred. |
| Training/fine-tuning foundation models | Local RTX 3050 4GB GPU is suitable for 4-bit quantized inference, not model training. |
| Unconditional vision analysis of every page | Would immediately exhaust VRAM and throttle processing time; selective analysis is strictly enforced. |
| Silent cloud data transmission | Strict privacy policy: local-first by default; zero telemetry or unconsented network egress. |
| Web search fallback | Answers must be strictly grounded in the uploaded document to prevent unverified web facts. |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 1 | Complete (Phase 1 verified) |
| INGEST-02 | Phase 1 | Complete (Phase 1 verified) |
| INGEST-03 | Phase 3 | Complete (Phase 3 verified) |
| INGEST-04 | Phase 3 | Complete (Phase 3 verified) |
| INGEST-05 | Phase 1 | Complete (Phase 1 verified) |
| STORE-01 | Phase 1 | Complete (Phase 1 verified) |
| STORE-02 | Phase 1 | Complete (Phase 1 verified) |
| STORE-03 | Phase 1 | Complete (Phase 1 verified) |
| INF-01 | Phase 2 | Complete (Phase 2 verified) |
| INF-02 | Phase 2 | Complete (Phase 2 verified) |
| INF-03 | Phase 2 | Complete (Phase 2 verified) |
| INF-04 | Phase 7 | Complete (Phase 7 verified) |
| VIS-01 | Phase 3 | Complete (Phase 3 verified) |
| VIS-02 | Phase 3 | Complete (Phase 3 verified) |
| VIS-03 | Phase 3 | Complete (Phase 3 verified) |
| RETR-01 | Phase 4 | Complete (Phase 4 verified) |
| RETR-02 | Phase 4 | Complete (Phase 4 verified) |
| RETR-03 | Phase 4 | Complete (Phase 4 verified) |
| RETR-04 | Phase 4 | Complete (Phase 4 verified) |
| QA-01 | Phase 5 | Complete (Phase 5 verified) |
| QA-02 | Phase 5 | Complete (Phase 5 verified) |
| QA-03 | Phase 5 | Complete (Phase 5 verified) |
| QA-04 | Phase 5 | Complete (Phase 5 verified) |
| SUMM-01 | Phase 5 | Complete (Phase 5 verified) |
| SUMM-02 | Phase 5 | Complete (Phase 5 verified) |
| SUMM-03 | Phase 5 | Complete (Phase 5 verified) |
| UI-01 | Phase 1 | Complete (Phase 1 verified) |
| UI-02 | Phase 5 | Complete (Phase 5 verified) |
| UI-03 | Phase 5 | Complete (Phase 5 verified) |
| UI-04 | Phase 7 | Complete (Phase 7 verified) |
| QUAL-01 | Phase 6 | Complete (Phase 6 verified) |
| QUAL-02 | Phase 0 & Phase 8 | Complete (Phase 8 verified) |
| QUAL-03 | Phase 0 through 8 | Complete (Phase 8 verified) |
| QUAL-04 | Phase 0 through 8 | Complete (Phase 8 verified) |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-10*  
*Last updated: 2026-10-12 (Phase 8 complete)*
