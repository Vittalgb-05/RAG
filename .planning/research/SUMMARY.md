# Project Research Summary

**Project:** Local-First Multimodal PDF Intelligence System  
**Domain:** Local Document Intelligence & Hybrid RAG (RTX 3050 Laptop 4GB VRAM)  
**Researched:** 2026-10-10  
**Confidence:** HIGH  

## Executive Summary

The project is an upgrade of an existing brownfield Streamlit text-only RAG application into a robust, local-first multimodal PDF intelligence system. The system must run on consumer-grade hardware (specifically an NVIDIA RTX 3050 Laptop GPU with a strict 4 GB VRAM ceiling) while supporting accurate document summarization, chart/diagram/table understanding, and grounded question answering with page-level citations.

The research confirms that a modular monolith architecture is optimal. Core technical pillars include **Docling** with conditional **RapidOCR** for layout-aware document extraction, **llama-server (llama.cpp)** running a quantized 2B vision-language model (e.g. Qwen3-VL 2B GGUF Q4_K_M) for local text and visual inference, **LanceDB** for embedded persistent hybrid search (vector + BM25/FTS), and **SQLite** for transactional metadata management. To guarantee system stability on 4 GB VRAM, embedding models and OCR must run on CPU, while llama-server uses bounded GPU offloading (`-ngl`) and context windows (4K–8K tokens).

The primary architectural risk is VRAM exhaustion and citation divergence between retrieval and generation. This is mitigated through strict resource sequencing (max one active LLM on GPU), a single shared retrieval pipeline for both prompt context and citation validation, and comprehensive automated test coverage with CI/CD alignment.

## Key Findings

### Recommended Stack

The application preserves Streamlit for the user interface while replacing the fragile in-memory components and raw cloud SDK calls with decoupled local services:

**Core technologies:**
- **Docling (`>=2.15.0`) + RapidOCR**: High-fidelity layout, table, and reading order extraction with OCR triggered conditionally only on low-text/scanned pages.
- **llama-server (llama.cpp)**: High-performance GGUF quantized VLM inference (Qwen3-VL 2B) with exact VRAM offload management and OpenAI-compatible streaming endpoints.
- **LanceDB (`>=0.17.0`)**: Serverless local hybrid retrieval combining dense vector search and full-text keyword search via Reciprocal Rank Fusion.
- **Sentence-Transformers (`>=3.4.1`)**: Local embeddings (`all-MiniLM-L6-v2`) pinned to CPU to keep the 4 GB GPU entirely free for the VLM.
- **SQLite3 + Pydantic v2**: ACID metadata storage and canonical data validation.
- **LiteLLM**: Uniform adapter for optional, user-consented cloud model execution.

### Expected Features

**Must have (table stakes):**
- Robust PDF ingestion with SHA-256 deduplication and magic-byte checks.
- Grounded question answering with live token streaming and verifiable page citations (>=95% precision).
- Multi-profile hierarchical summarization (Overview, Detailed, Study notes, Tables & figures, Findings).
- Table and structure preservation without flattening rows/columns.
- Persistent document storage across app restarts.

**Should have (competitive differentiators):**
- 100% local operation with zero external network egress.
- Selective visual reasoning over charts and diagrams without scanning every page.
- Explicit abstention when evidence is insufficient (no fabricated citations).
- Cloud fallback with explicit opt-in and privacy controls.

**Defer (v2+):**
- Enterprise multi-tenant authentication and distributed queuing (Celery/Kafka).
- Multi-document comparative reasoning across large document corpora.

### Architecture Approach

A modular monolith organized into clean layers: presentation (`app.py`), canonical models (`models/`), decoupled business services (`services/`), provider adapters (`providers/`), and persistent local stores (`data/`). 

**Major components:**
1. **Ingestion & Normalizer**: Validates PDFs, extracts layout/tables via Docling, triggers conditional OCR, and outputs canonical Pydantic models.
2. **Storage Layer**: LanceDB for hybrid search and SQLite for document/page metadata.
3. **Retrieval & Citation Engine**: Unified hybrid search delivering a single immutable evidence context to both the prompt builder and UI citation inspector.
4. **Provider Router**: Directs inference requests to local llama-server or cloud LiteLLM with strict privacy gates.

### Critical Pitfalls

1. **VRAM Exhaustion (CUDA OOM)**: Prevented by keeping embeddings and OCR on CPU, running only one LLM/VLM in GPU VRAM, and capping context length at 4K-8K tokens.
2. **Divergent Citations & Hallucinations**: Prevented by utilizing a single shared retrieval context for both prompt assembly and UI display, with regex citation verification.
3. **Monolithic Ingestion Freezes**: Prevented by streaming page extraction and conditional OCR gating (< 50 chars threshold).
4. **Visual Hallucinations**: Prevented by tagging visual descriptions with model provenance and prioritizing extracted tables over visual approximations for numbers.

## Implications for Roadmap

The SRS roadmap aligns directly with the architectural findings. Structured in 9 phases (Phase 0 to Phase 8):

### Phase 0: Baseline and Audit
- **Rationale**: Establish reproducible test corpus, benchmark existing brownfield pipeline, document entry points and existing bugs.
- **Delivers**: Test corpus, benchmark metrics, baseline test suite.
- **Avoids**: Regressions of working existing Streamlit UI features.

### Phase 1: Canonical Document Models & Storage Foundation
- **Rationale**: Clean data models prevent structural drift before introducing complex extraction or local inference.
- **Delivers**: Pydantic schemas (`Document`, `Page`, `EvidenceElement`, `Chunk`), SHA-256 hashing, SQLite metadata store.
- **Addresses**: FR-01, FR-05, and `CONCERNS.md #4`.

### Phase 2: Local Inference Pipeline
- **Rationale**: Early establishment of local model runtime validates hardware feasibility on RTX 3050 4GB.
- **Delivers**: `llama-server` runtime setup, Qwen3-VL 2B GGUF configuration, `BaseModelProvider`, streaming integration, offline verification.
- **Addresses**: FR-09, NFR-01, NFR-03.

### Phase 3: Multimodal Ingestion & Conditional OCR
- **Rationale**: Replace pypdf with Docling and RapidOCR; implement selective visual cropping and analysis.
- **Delivers**: Docling pipeline, RapidOCR fallback, visual element detection, VLM image analysis service.
- **Addresses**: FR-02, FR-03, FR-04.

### Phase 4: Persistent Hybrid Retrieval
- **Rationale**: Replace in-memory linear search with disk-backed LanceDB hybrid search before building higher-level QA.
- **Delivers**: LanceDB integration, dense embedding service (CPU-pinned), BM25 keyword search, Reciprocal Rank Fusion.
- **Addresses**: FR-08, `CONCERNS.md #2`, `CONCERNS.md #4`.

### Phase 5: Grounded Summarization & Question Answering
- **Rationale**: Combine hybrid retrieval and local inference into end-to-end user features.
- **Delivers**: 5 summary profiles with hierarchical map-reduce, grounded QA pipeline, citation verification engine (>=95% target), abstention handling.
- **Addresses**: FR-06, FR-07, `CONCERNS.md #5`.

### Phase 6: Performance Optimization & Resource Profiling
- **Rationale**: Validate that memory, latency, and throughput meet targets on the physical 4GB RTX 3050 GPU.
- **Delivers**: VRAM/RAM profiling benchmarks, KV-cache tuning, context window optimization, caching layers.
- **Addresses**: NFR-01, NFR-04.

### Phase 7: Optional Cloud Provider & Privacy Controls
- **Rationale**: Cloud fallback is added only after the local-first pipeline is stable and verified.
- **Delivers**: LiteLLM provider adapter, explicit UI cloud toggle, privacy guardrails, connection timeouts.
- **Addresses**: FR-09, NFR-03.

### Phase 8: Release Hardening & Evaluation
- **Rationale**: Ensure dependency reproducibility, complete test coverage, CI/CD synchronization, and documentation.
- **Delivers**: Pinned dependencies, comprehensive pytest regression suite, CI/CD pipeline, updated `CONCERNS.md` resolution audit.
- **Addresses**: NFR-05, acceptance criteria.

### Phase Ordering Rationale

- **Models and Storage First (Phases 1, 2, 4)**: Creates stable contracts before hooking up complex parsers.
- **Local Inference First (Phase 2)**: Fails early if GPU VRAM constraints prove problematic for llama-server.
- **Extraction & Retrieval (Phases 3, 4)**: Ensures clean evidence records exist before summarization and QA (Phase 5).
- **Optimization & Cloud (Phases 6, 7)**: Polishes latency and adds optional fallback without compromising local-first guarantees.

### Research Flags

- **Phase 2 (Local Inference):** Needs verification of llama.cpp build for Windows CUDA with multimodal projector support for Qwen3-VL 2B.
- **Phase 3 (Docling Ingestion):** Needs profiling of Docling dependency size and cold-start latency on Windows.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified library compatibility (Docling, LanceDB, llama.cpp, SQLite). |
| Features | HIGH | Directly grounded in comprehensive user SRS v1.0 specification. |
| Architecture | HIGH | Proven local RAG patterns; addresses all issues in `.planning/codebase/CONCERNS.md`. |
| Pitfalls | HIGH | Specific to the 4 GB VRAM ceiling and Windows execution environment. |

**Overall confidence:** HIGH

## Sources

### Primary (HIGH confidence)
- User Specification: *SRS — Local-First Multimodal PDF Intelligence System Version 1.0*.
- Workspace Architecture & Concerns: `.planning/codebase/ARCHITECTURE.md`, `CONCERNS.md`, `STACK.md`.
- Docling Official Documentation (`docling.org`).
- LanceDB Python API Documentation (`lancedb.github.io`).
- llama.cpp Server Documentation (`github.com/ggml-org/llama.cpp`).

---
*Research completed: 2026-10-10*  
*Ready for roadmap: yes*
