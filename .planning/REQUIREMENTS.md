# Requirements: Local-First Multimodal PDF Intelligence System

**Defined:** 2026-10-10  
**Core Value:** Fast, evidence-grounded document summarization and question answering with visual understanding and verifiable page-level citations, operating completely locally within a 4 GB VRAM envelope.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Ingestion & Structured Parsing

- [ ] **INGEST-01**: User can upload PDF files through the Streamlit interface with client and server-side magic-byte (`%PDF`) validation, size limit checks, and page count limits.
- [ ] **INGEST-02**: System validates document integrity, computes SHA-256 content hashes, detects duplicate uploads, and assigns stable document IDs independent of filename.
- [ ] **INGEST-03**: System processes documents using Docling to extract reading order, headings, section hierarchy, tables, and figure references.
- [ ] **INGEST-04**: System conditionally invokes local RapidOCR on pages with missing or unextractable text (< 50 characters) while bypassing OCR on clean digital pages.
- [ ] **INGEST-05**: System isolates extraction failures at page level so errors on individual pages do not abort processing of remaining valid pages.

### Document Storage & Canonical Modeling

- [ ] **STORE-01**: System persists document metadata, processing status, page counts, and extraction logs in an ACID-compliant local SQLite database.
- [ ] **STORE-02**: System represents all document elements, pages, and chunks using typed Pydantic canonical models with explicit bounding-box coordinates and source extraction metadata.
- [ ] **STORE-03**: System caches intermediate extraction artifacts, page renders, and crops on local disk keyed by SHA-256 and configuration versions.

### Local & Cloud Inference Infrastructure

- [ ] **INF-01**: System provides a unified `BaseModelProvider` interface supporting text generation, token streaming, image analysis, and capability inspection.
- [ ] **INF-02**: System implements a local `LlamaCppProvider` communicating with `llama-server` running a quantized 2B VLM (Qwen3-VL 2B GGUF Q4_K_M) with health checks and bounded context (4K-8K tokens).
- [ ] **INF-03**: System operates 100% offline without outbound network calls during local mode.
- [ ] **INF-04**: System implements an optional `LiteLLMProvider` enabling cloud model routing (Groq, OpenAI, Anthropic) only when explicitly configured and consented to by user.

### Visual Understanding

- [ ] **VIS-01**: System identifies visual elements (charts, diagrams, flowcharts, figures, visual tables) and renders high-fidelity image crops using PyMuPDF/Pillow.
- [ ] **VIS-02**: System queries local VLM with targeted prompts to generate structured visual descriptions for detected visual elements.
- [ ] **VIS-03**: System stores visual descriptions as distinct derived artifacts tagged with model and version provenance, preventing ungrounded visual approximations from contaminating ground-truth table data.

### Persistent Hybrid Retrieval

- [ ] **RETR-01**: System generates dense text embeddings using local Sentence-Transformers (`all-MiniLM-L6-v2`) pinned to CPU to protect the 4 GB GPU VRAM.
- [ ] **RETR-02**: System indexes document chunks and embeddings into a persistent on-disk LanceDB table that survives application restarts.
- [ ] **RETR-03**: System executes hybrid retrieval combining semantic vector search and full-text keyword search (BM25/FTS) with Reciprocal Rank Fusion (RRF).
- [ ] **RETR-04**: System provides a single shared `RetrievalResult` context consumed identically by both generation prompts and citation display components.

### Grounded Question Answering & Citations

- [ ] **QA-01**: User can ask natural-language questions and receive answers streamed live into the chat interface grounded in retrieved document evidence.
- [ ] **QA-02**: System formats prompts with explicit numbered evidence identifiers (`[E1]`, `[E2]`) and strict boundaries preventing prompt injection from document text.
- [ ] **QA-03**: System validates all generated citations against retrieved evidence records, enforcing a minimum 95% citation precision.
- [ ] **QA-04**: System detects unanswerable queries and explicitly abstains ("The document does not contain sufficient evidence") without inventing citations.

### Hierarchical Multi-Profile Summarization

- [ ] **SUMM-01**: User can generate document summaries across five distinct profiles: Overview, Detailed, Study Notes, Tables & Figures, and Findings.
- [ ] **SUMM-02**: System executes hierarchical map-reduce summarization for multi-page documents while maintaining source page references across reduction stages.
- [ ] **SUMM-03**: System caches generated summaries by document hash and profile type to deliver near-instant repeated requests.

### User Interface & Experience

- [ ] **UI-01**: User can view upload progress, parsing stage, and indexing status indicators inside Streamlit.
- [ ] **UI-02**: User can select summary profiles and view formatted markdown summaries with expandable source page references.
- [ ] **UI-03**: User can view interactive evidence chips and drawer alongside chat answers showing the exact cited text and page number.
- [ ] **UI-04**: User can toggle between Local and Cloud modes with explicit warning and credential configuration dialogs.

### Quality, Performance & Process Assurance

- [x] **QUAL-01**: System guarantees memory safety on 4 GB VRAM (RTX 3050 Laptop) by enforcing max one active LLM on GPU and cold/warm memory benchmarks.
- [ ] **QUAL-02**: System maintains an automated Pytest test suite covering ingestion, retrieval, citation precision, and provider fallbacks.
- [ ] **QUAL-03**: Agents and workflows execute structured git commits per planning, execution, review, and verification phases.
- [ ] **QUAL-04**: Agents inspect `.planning/codebase/` documentation prior to planning and update `CONCERNS.md` and CI/CD workflows across every phase.

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
| INGEST-03 | Phase 3 | Pending |
| INGEST-04 | Phase 3 | Pending |
| INGEST-05 | Phase 1 | Complete (Phase 1 verified) |
| STORE-01 | Phase 1 | Complete (Phase 1 verified) |
| STORE-02 | Phase 1 | Complete (Phase 1 verified) |
| STORE-03 | Phase 1 | Complete (Phase 1 verified) |
| INF-01 | Phase 2 | Pending |
| INF-02 | Phase 2 | Pending |
| INF-03 | Phase 2 | Pending |
| INF-04 | Phase 7 | Pending |
| VIS-01 | Phase 3 | Pending |
| VIS-02 | Phase 3 | Pending |
| VIS-03 | Phase 3 | Pending |
| RETR-01 | Phase 4 | Pending |
| RETR-02 | Phase 4 | Pending |
| RETR-03 | Phase 4 | Pending |
| RETR-04 | Phase 4 | Pending |
| QA-01 | Phase 5 | Pending |
| QA-02 | Phase 5 | Pending |
| QA-03 | Phase 5 | Pending |
| QA-04 | Phase 5 | Pending |
| SUMM-01 | Phase 5 | Pending |
| SUMM-02 | Phase 5 | Pending |
| SUMM-03 | Phase 5 | Pending |
| UI-01 | Phase 1 | Complete (Phase 1 verified) |
| UI-02 | Phase 5 | Pending |
| UI-03 | Phase 5 | Pending |
| UI-04 | Phase 7 | Pending |
| QUAL-01 | Phase 6 | Complete (Phase 6 verified) |
| QUAL-02 | Phase 0 & Phase 8 | Complete (Phase 0 verified) |
| QUAL-03 | Phase 0 through 8 | In Progress (Phase 0 & 1 verified) |
| QUAL-04 | Phase 0 through 8 | In Progress (Phase 0 & 1 verified) |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-10*  
*Last updated: 2026-10-10 after initial definition*
