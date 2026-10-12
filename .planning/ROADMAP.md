# Roadmap: Local-First Multimodal PDF Intelligence System

## Overview

This roadmap transforms an existing in-memory Streamlit RAG prototype into a local-first, privacy-respecting multimodal PDF intelligence system tailored for an NVIDIA RTX 3050 Laptop GPU (4 GB VRAM). The journey progresses systematically from baseline auditing and canonical data modeling through local quantized VLM inference, Docling multimodal ingestion, LanceDB hybrid retrieval, grounded summarization and QA with verified citations, hardware performance profiling, optional cloud provider portability, and release hardening.

## Phases

**Phase Numbering:**
- Integer phases (0, 1, 2...): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 0: Baseline and Audit** - Benchmark existing brownfield pipeline, assemble test corpus, and verify initial test/CI setup
- [x] **Phase 1: Canonical Document Models & Storage Foundation** - Implement Pydantic data models, SQLite metadata store, and robust file validation
- [x] **Phase 2: Local Inference Pipeline** - Deploy llama-server runtime with Qwen3-VL 2B GGUF, provider abstraction, and streaming support
- [ ] **Phase 3: Multimodal Ingestion & Conditional OCR** - Integrate Docling layout parser, conditional RapidOCR, and selective visual element analysis
- [ ] **Phase 4: Persistent Hybrid Retrieval** - Integrate LanceDB with local dense embeddings (CPU-pinned) and BM25 full-text search
- [ ] **Phase 5: Grounded Summarization & Question Answering** - Build hierarchical summary profiles, evidence-grounded streaming QA, and citation verification
- [ ] **Phase 6: Performance Optimization & Resource Profiling** - Benchmark VRAM/RAM on RTX 3050, tune context and KV-cache, and establish cache limits
- [ ] **Phase 7: Optional Cloud Provider & Privacy Controls** - Implement LiteLLM adapter with explicit user opt-in and privacy guardrails
- [ ] **Phase 8: Release Hardening & Evaluation** - Pin dependencies, execute full regression suite, synchronize CI/CD, and document runbooks

## Phase Details

### Phase 0: Baseline and Audit
**Goal**: Establish a reproducible baseline, audit existing codebase components and known bugs, assemble a representative test corpus, and configure the test harness.  
**Depends on**: Nothing (first phase)  
**Requirements**: QUAL-02, QUAL-03, QUAL-04  
**Success Criteria**:
  1. A representative test corpus exists containing clean digital, scanned, multi-column, table-heavy, and chart-heavy PDFs.
  2. Baseline extraction throughput and retrieval latency of the existing Streamlit app are measured and documented.
  3. Pytest test harness is initialized with baseline regression tests.
**Plans**: 2 plans

Plans:
- [x] 00-01: Audit codebase entry points, inventory bugs, and create representative test corpus
- [x] 00-02: Setup Pytest test harness, establish baseline performance benchmarks, and configure CI pipeline

### Phase 1: Canonical Document Models & Storage Foundation
**Goal**: Introduce typed Pydantic schemas, persistent SQLite metadata storage, and server-side upload validation to eliminate data loss and memory blowup risks.  
**Depends on**: Phase 0  
**Requirements**: INGEST-01, INGEST-02, INGEST-05, STORE-01, STORE-02, STORE-03, UI-01  
**Success Criteria**:
  1. User can upload PDFs with client/server magic-byte (`%PDF`) validation, size caps, and SHA-256 deduplication.
  2. Document records, page states, and element metadata are stored transactionally in SQLite and persist across restarts.
  3. Streamlit UI displays upload validation status and page-by-page progress indicators.
**Plans**: 2 plans

Plans:
- [x] 01-01: Implement canonical Pydantic schemas (Document, Page, EvidenceElement, Chunk) and SQLite metadata store
- [x] 01-02: Implement robust upload validation, SHA-256 deduplication, and Streamlit ingestion progress UI

### Phase 2: Local Inference Pipeline
**Goal**: Establish the local LLM/VLM inference engine using llama-server (llama.cpp) with Qwen3-VL 2B GGUF without cloud dependencies.  
**Depends on**: Phase 1  
**Requirements**: INF-01, INF-02, INF-03  
**Success Criteria**:
  1. `BaseModelProvider` interface is implemented and verified with local `LlamaCppProvider`.
  2. Local `llama-server` streams tokens for generation queries completely offline with zero external network access.
  3. Health checks and fallback notifications detect if the local inference server is unavailable and provide clear setup guidance.
**Plans**: 2 plans

Plans:
- [x] 02-01: Define unified BaseModelProvider interface and implement LlamaCppProvider HTTP client with health checks
- [x] 02-02: Configure llama-server with Qwen3-VL 2B GGUF Q4_K_M, verify offline token streaming and bounded context

### Phase 3: Multimodal Ingestion & Conditional OCR
**Goal**: Integrate Docling for structured document layout and table parsing, conditional RapidOCR for scanned pages, and selective visual element analysis.  
**Depends on**: Phase 1, Phase 2  
**Requirements**: INGEST-03, INGEST-04, VIS-01, VIS-02, VIS-03  
**Success Criteria**:
  1. Digital PDFs extract text, headings, and markdown tables in under 5 seconds for 20 pages without triggering unnecessary OCR.
  2. Scanned or low-text pages (< 50 characters) conditionally invoke RapidOCR without failing the document.
  3. Visual elements (charts, diagrams) are detected, cropped, and analyzed by the local VLM with distinct provenance tags.
**Plans**: 3 plans

Plans:
- [x] 03-01: Integrate Docling DocumentConverter for structured layout, heading hierarchy, and table extraction
- [x] 03-02: Implement conditional RapidOCR fallback and page-level fault isolation
- [x] 03-03: Implement visual element detection, PyMuPDF cropping, and local VLM figure description service

### Phase 4: Persistent Hybrid Retrieval
**Goal**: Replace the in-memory linear vector scan with persistent LanceDB hybrid search (dense embeddings + BM25 keyword search) using Reciprocal Rank Fusion.  
**Depends on**: Phase 1, Phase 3  
**Requirements**: RETR-01, RETR-02, RETR-03, RETR-04  
**Success Criteria**:
  1. Sentence-Transformers embedding model runs on CPU, preserving 100% of GPU VRAM for the VLM.
  2. LanceDB stores vectors and full-text inverted indices on disk, persisting across application restarts.
  3. Hybrid search with Reciprocal Rank Fusion returns top relevant candidates in under 1 second.
  4. A single immutable `RetrievalResult` object is shared between generation context and UI citation rendering.
**Plans**: 2 plans

Plans:
- [x] 04-01: Setup persistent LanceDB vector store and CPU-pinned Sentence-Transformers embedding pipeline
- [x] 04-02: Implement hybrid search with BM25 FTS, Reciprocal Rank Fusion, and shared RetrievalResult contract

### Phase 5: Grounded Summarization & Question Answering
**Goal**: Deliver five distinct summary profiles via hierarchical map-reduce and evidence-grounded streaming QA with verified page citations and abstention.  
**Depends on**: Phase 2, Phase 4  
**Requirements**: SUMM-01, SUMM-02, SUMM-03, QA-01, QA-02, QA-03, QA-04, UI-02, UI-03  
**Success Criteria**:
  1. User can generate 5 distinct summary profiles (Overview, Detailed, Study Notes, Tables & Figures, Findings) preserving page references.
  2. User can stream QA answers grounded strictly in retrieved evidence with citation precision >= 95%.
  3. Unanswerable questions produce explicit abstention notices without fabricated citations.
  4. Streamlit UI displays clickable source chips and expandable evidence drawers showing exact cited snippets.
**Plans**: 3 plans

Plans:
- [x] 05-01: Implement hierarchical multi-profile summarization service with map-reduce page tracking and cache
- [x] 05-02: Implement grounded QA prompt pipeline with injection guards, streaming response, and citation validator
- [x] 05-03: Enhance Streamlit UI with summary profile selector, interactive evidence chips, and citation drawer

### Phase 6: Performance Optimization & Resource Profiling
**Goal**: Measure, tune, and document system resource consumption to guarantee stability within the 4 GB VRAM ceiling on the RTX 3050 Laptop GPU.  
**Depends on**: Phase 5  
**Requirements**: QUAL-01  
**Success Criteria**:
  1. Peak GPU VRAM during active VLM inference remains strictly under 3.8 GB on the RTX 3050 Laptop GPU.
  2. Context window (4K–8K tokens) and KV-cache are tuned with zero CUDA out-of-memory errors during multi-page workloads.
  3. Multi-tier caches for extraction, embeddings, and summaries achieve near-instant response on repeated requests.
**Plans**: 2 plans

Plans:
- [x] 06-01: Profile and benchmark VRAM/RAM under cold and warm workloads on RTX 3050, tuning llama.cpp -ngl and context
- [x] 06-02: Implement multi-tier cache invalidation, memory limits, and performance monitoring telemetry

### Phase 7: Optional Cloud Provider & Privacy Controls
**Goal**: Provide optional cloud model fallback via LiteLLM with strict user consent, privacy guardrails, and transparent UI indicators.  
**Depends on**: Phase 2, Phase 5  
**Requirements**: INF-04, UI-04  
**Success Criteria**:
  1. User can toggle Cloud Mode in Streamlit UI with explicit consent prompts and credential configuration.
  2. Ingestion, embeddings, and LanceDB indexing remain 100% local even when cloud inference is activated.
  3. Document content is never transmitted to cloud providers without active, explicit user authorization.
**Plans**: 2 plans

Plans:
- [ ] 07-01: Implement LiteLLM cloud provider adapter supporting Groq, OpenAI, and Anthropic with timeout/retry bounds
- [ ] 07-02: Add Streamlit cloud/local mode switch, privacy guardrails, and credential management dialog

### Phase 8: Release Hardening & Evaluation
**Goal**: Pin tested dependencies, run the complete Pytest regression suite, verify CI/CD pipelines, audit CONCERNS.md resolutions, and prepare release documentation.  
**Depends on**: Phase 6, Phase 7  
**Requirements**: QUAL-02, QUAL-03, QUAL-04  
**Success Criteria**:
  1. Pinned dependencies and reproducible environment configuration verified on Windows.
  2. Automated test suite passes 100% across ingestion, storage, retrieval, citations, and providers.
  3. All top risks and technical debt in `.planning/codebase/CONCERNS.md` are audited, resolved, and documented.
  4. Complete documentation published for setup, GPU configuration, evaluation results, and known limitations.
**Plans**: 2 plans

Plans:
- [ ] 08-01: Complete end-to-end regression evaluation on test corpus and verify CI/CD workflow synchronization
- [ ] 08-02: Audit CONCERNS.md resolution, finalize requirements lockfile, and write architecture/setup runbooks

## Progress

**Execution Order:**
Phases execute in numeric order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Baseline and Audit | 2/2 | Complete | 2026-10-11 |
| 1. Canonical Document Models & Storage Foundation | 2/2 | Complete | 2026-10-11 |
| 2. Local Inference Pipeline | 2/2 | Complete | 2026-10-11 |
| 3. Multimodal Ingestion & Conditional OCR | 3/3 | Complete | 2026-10-11 |
| 4. Persistent Hybrid Retrieval | 2/2 | Complete | 2026-10-11 |
| 5. Grounded Summarization & Question Answering | 3/3 | Complete | 2026-10-11 |
| 6. Performance Optimization & Resource Profiling | 0/2 | Not started | - |
| 7. Optional Cloud Provider & Privacy Controls | 0/2 | Not started | - |
| 8. Release Hardening & Evaluation | 0/2 | Not started | - |
