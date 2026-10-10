# Local-First Multimodal PDF Intelligence System

## What This Is

A local-first, privacy-respecting PDF intelligence application that delivers fast, accurate summarization and grounded question answering across digital, scanned, and visually complex documents (diagrams, charts, tables). Designed to run primarily on consumer hardware (single-user laptop with 4 GB GPU VRAM) with optional, explicitly configured cloud model fallback.

## Core Value

Fast, evidence-grounded document summarization and question answering with visual understanding and verifiable page-level citations, operating completely locally within a 4 GB VRAM envelope.

## Requirements

### Validated

<!-- Inferred from existing brownfield codebase -->
- ✓ Streamlit web interface with document upload, sidebar configuration, and chat message stream (`main.py`) — existing
- ✓ Basic digital PDF text extraction via pypdf (`pdf_reader.py`) — existing
- ✓ Local sentence-transformers embeddings (`all-MiniLM-L6-v2`, 384-dim) (`local_embedding.py`) — existing
- ✓ In-memory cosine similarity vector search (`vector_index.py`) — existing
- ✓ Streaming cloud LLM question answering via Groq API (`local_llm.py`) — existing

### Active

<!-- Scope from SRS v1.0 specification and project requirements -->
- [ ] **FR-01: Robust PDF Ingestion** — SHA-256 content hashing, stable internal document IDs, magic-byte validation, file size/page limits, page-level fault isolation, and duplicate upload prevention
- [ ] **FR-02: Structured Extraction with Docling** — Native extraction of reading order, section hierarchy, tables, and figure references; digital extraction by default without redundant OCR
- [ ] **FR-03: Conditional Local OCR** — RapidOCR engine triggered only for scanned pages or missing text layers, preserving OCR confidence and avoiding re-runs
- [ ] **FR-04: Selective Visual Understanding** — Heuristic detection of visual elements (charts, diagrams, tables, figures); selective rendering and local VLM inspection (e.g. Qwen3-VL 2B GGUF via llama-server); distinct tagging of visual interpretations
- [ ] **FR-05: Document Storage & Provenance** — SQLite transactional metadata store and local filesystem artifact storage; strict local retention
- [ ] **FR-06: Hierarchical Summarization** — Multiple summary profiles (Overview, Detailed, Study notes, Tables & figures, Findings) with hierarchical reduction preserving page references
- [ ] **FR-07: Grounded Question Answering** — Evidence retrieval before generation; single shared retrieval context for generation and citations; strict citation validation (>=95% precision) and explicit abstention when evidence is insufficient
- [ ] **FR-08: Persistent Hybrid Retrieval** — LanceDB vector + full-text search with Reciprocal Rank Fusion (RRF), page/document metadata filtering, and persistent on-disk storage
- [ ] **FR-09: Model Provider Abstraction** — Common interface (`generate_text`, `analyze_image`, `stream_text`, `get_model_capabilities`) supporting local llama-server and optional cloud via LiteLLM
- [ ] **FR-10: Enhanced Streamlit UI** — Preserve and modernize existing UI; add summary profile selector, citation inspector, evidence snippet drawer, local/cloud mode toggle, and processing status
- [ ] **NFR-01: Performance & Resource Safety** — Max 1 active LLM in VRAM; cold/warm benchmark tracking; bounded context (4K-8K); embedding models on CPU if needed to protect 4 GB VRAM
- [ ] **NFR-02: Quality & Privacy** — Local inference by default; zero silent network transmission; local artifact deletion
- [ ] **Process Rule 1: Phase Git Commits** — Enforce descriptive git commits across planning, execution, review, and verification phases
- [ ] **Process Rule 2: Codebase Map Grounding** — Agents must inspect `.planning/codebase/` documents during planning and implementation
- [ ] **Process Rule 3: Test Suite & Quality Gates** — Comprehensive pytest test suite updated across phases; CI/CD synchronization; continuous tracking and mitigation of `CONCERNS.md`

### Out of Scope

<!-- Explicit boundaries to protect 4 GB VRAM budget and local single-user scope -->
- Multi-user enterprise deployment, authentication, or multi-tenant database partitioning — single-user local application
- Distributed processing (Kubernetes, Celery, Kafka, Redis) — unnecessary overhead and operational complexity for a local monolith
- Multi-agent orchestration frameworks (LangChain agents, AutoGen, CrewAI) — deterministic modular services preferred for predictable latency and debugging
- Training or fine-tuning foundation models — pre-trained quantized GGUF weights only
- Guaranteed perfect handwriting OCR — out of initial scope for RapidOCR / lightweight OCR
- Unconditional visual analysis of every page — would instantly saturate 4 GB GPU VRAM and throttle processing throughput
- Automatic or silent cloud transmission — strict local-first privacy requirement; cloud requires explicit configuration and user consent
- Web search as substitute for document evidence — document-grounded intelligence only

## Context

- **Current Architecture**: Streamlit frontend (`main.py`) talks directly to in-memory `VectorIndex`, `LocalEmbedding`, and Groq API. No persistent storage or automated test suite.
- **Hardware Constraints**: NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM, modern multicore CPU, 16 GB RAM, Windows environment.
- **Document Complexity**: Needs to handle digital text, scanned reports, technical papers with figures, financial tables, and mixed multi-column layouts.
- **Known Codebase Concerns**:
  - In-memory index data loss on restart (`CONCERNS.md #2`)
  - Divergent retrieval contexts between generation and displayed source chips (`CONCERNS.md #5`)
  - Unbounded file uploads and lack of server-side validation (`CONCERNS.md #3`)
  - Fragile error handling causing full app crash on API or model failure (`CONCERNS.md #1`)
  - Linear brute-force Python vector search (`CONCERNS.md #4`)

## Constraints

- **Hardware / VRAM**: Strict 4 GB VRAM ceiling. Only one LLM/VLM active in memory at a time; quantized GGUF (4-bit); conservative context window (4K–8K tokens). Preprocessing (Docling, RapidOCR, embeddings) offloaded to CPU or sequenced to avoid VRAM exhaustion.
- **Platform**: Windows host OS with PowerShell; Python 3.11+.
- **Privacy & Security**: Zero external network egress during local operation; credentials kept in `.env` / environment variables; documents treated as untrusted input.
- **Architecture**: Modular monolith with decoupled services (ingestion, normalization, storage, retrieval, inference, UI).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Modular Monolith over Microservices | Low operational overhead for single-user local deployment; simple packaging and debugging | — Pending |
| llama-server (llama.cpp) for local inference | Native GGUF quantization, precise GPU offload layer control (`-ngl`), OpenAI-compatible REST API, VLM support | — Pending |
| Docling for structured extraction | State-of-the-art document layout parsing, markdown conversion, native table extraction, and image bounding boxes | — Pending |
| RapidOCR for conditional OCR | Lightweight, CPU-friendly OCR fallback; runs locally without heavy dependencies | — Pending |
| LanceDB for persistent vector store | Embedded, serverless, fast local hybrid search (vector + BM25/FTS) with low memory footprint | — Pending |
| SQLite for metadata store | Standard, reliable transactional ACID storage for document registry, status, and evidence models | — Pending |
| LiteLLM for cloud provider adapter | Unified fallback interface for OpenAI, Anthropic, Groq without polluting core business logic | — Pending |
| Retain and modernize Streamlit UI | Preserves existing user investment and familiarity while upgrading user experience and components | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-10 after initialization*
