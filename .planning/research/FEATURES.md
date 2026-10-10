# Feature Research

**Domain:** Local-First Multimodal PDF Intelligence & RAG  
**Researched:** 2026-10-10  
**Confidence:** HIGH  

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **PDF Ingestion & Validation** | Users upload varied PDFs; bad files must fail gracefully with clear reasons. | LOW | Magic byte check, SHA-256 deduplication, size/page bounds. |
| **Grounded QA with Streaming** | Users expect real-time chat answers directly answering questions about the PDF. | MEDIUM | Streaming tokens into Streamlit UI, grounded prompt construction. |
| **Verifiable Page Citations** | Answers must cite exact source pages; users must be able to inspect supporting text. | MEDIUM | Shared retrieval pipeline between citation metadata and LLM context. |
| **Multi-Profile Summarization** | Users need both quick executive summaries and deep study notes. | MEDIUM | Hierarchical chunk/section reduction with page reference preservation. |
| **Persistent Document Indexing** | Uploaded documents must remain indexed across app restarts without re-embedding. | MEDIUM | LanceDB vector store + SQLite document registry. |
| **Table Understanding** | Real-world reports (financial, technical) are table-heavy; text flattening destroys relationships. | MEDIUM | Docling markdown table extraction + cell relationship preservation. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **100% Local Multi-Modal Inference on 4GB VRAM** | Complete privacy and zero API costs on consumer laptops (RTX 3050 4GB). | HIGH | Selective VLM inference via llama-server (Qwen3-VL 2B GGUF) with bounded context. |
| **Selective Visual & Diagram Analysis** | Inspects charts, graphs, and architecture diagrams without wasting VRAM on every page. | HIGH | Heuristic visual element detection, crop generation, and tagged visual descriptions. |
| **Conditional OCR Pipeline** | Fast digital PDF parsing (< 5s for 20 pages) while still handling scanned pages seamlessly. | MEDIUM | Docling native layout analysis + RapidOCR fallback only when text density is low. |
| **Strict Evidence Abstention** | Never hallucinates or invents fake citations; explicitly states when evidence is missing. | MEDIUM | Bounded context, citation verification gate, >=95% citation precision. |
| **Seamless Cloud Fallback with User Consent** | Transparent fallback to Groq/Claude/OpenAI via LiteLLM only when explicitly authorized. | LOW | Strict privacy gate: zero silent network transmission. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Unconditional Vision on Every Page** | Sounds like full document visual comprehension. | Instantly exhausts 4 GB VRAM, explodes processing time to 15+ minutes per PDF. | Selective visual routing: only process pages/elements flagged with charts, diagrams, or low text. |
| **Multi-Agent Conversational Frameworks** | Trendy ("AI agents collaborating to analyze document"). | Induces recursive LLM calls, unpredictable latency, token budget blowouts, and fragile prompt state. | Deterministic service pipeline with clear contracts and single-turn structured generation. |
| **Web Search Fallback for Missing Facts** | Seems helpful when document doesn't contain the answer. | Corrupts document grounding; users can no longer trust whether an answer is in the PDF. | Explicit abstention: "The uploaded document does not contain sufficient information to answer this question." |
| **Direct Embedding of Generated Figure Captions into Raw Evidence** | Seems convenient for vector search. | Generated descriptions can hallucinate numbers; mixing them with raw text misleads retrieval. | Tag and store visual descriptions as distinct derived artifacts with model/version provenance. |

## Feature Dependencies

```
[PDF Ingestion & Validation (FR-01)]
    └──requires──> [Document Storage & Metadata (FR-05)]
                       └──requires──> [Structured Extraction (FR-02)]
                                          ├──requires (conditional)──> [Local OCR (FR-03)]
                                          └──enables──> [Selective Visual Analysis (FR-04)]
                                          └──enables──> [Persistent Hybrid Retrieval (FR-08)]
                                                            └──enables──> [Hierarchical Summarization (FR-06)]
                                                            └──enables──> [Grounded QA & Citations (FR-07)]

[Model Provider Abstraction (FR-09)] ──powers──> [FR-04, FR-06, FR-07]
[Enhanced Streamlit UI (FR-10)] ──────surfaces──> [All Functional Features]
```

### Dependency Notes

- **FR-08 (Hybrid Retrieval) requires FR-02 (Structured Extraction):** LanceDB indexing relies on normalized chunks, bounding boxes, and document hashes from Docling extraction.
- **FR-07 (Grounded QA) requires FR-08 (Hybrid Retrieval) and FR-09 (Model Provider):** Retrieval produces the exact evidence context passed to llama-server.
- **FR-04 (Visual Analysis) requires FR-09 (Model Provider):** Vision reasoning requires llama-server multimodal projector loaded.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to deliver the core value:

- [ ] **FR-01**: Robust PDF ingestion, SHA-256 deduplication, and validation.
- [ ] **FR-05**: SQLite document metadata registry and local filesystem storage.
- [ ] **FR-02**: Docling structured extraction (reading order, headings, tables).
- [ ] **FR-03**: RapidOCR conditional OCR for scanned/unextractable pages.
- [ ] **FR-09**: llama-server local provider with Qwen3-VL 2B GGUF.
- [ ] **FR-08**: LanceDB persistent hybrid search (vector + FTS).
- [ ] **FR-04**: Selective visual element detection and local VLM description.
- [ ] **FR-06**: Hierarchical summarization profiles (Overview, Detailed, Study Notes).
- [ ] **FR-07**: Grounded QA with verified page citations and abstention.
- [ ] **FR-10**: Modernized Streamlit UI with citation drawers and status indicators.

### Add After Validation (v1.x)

Features to add once core local workflow is validated:

- [ ] **Cloud Provider Switching (LiteLLM)**: Explicit user toggle for Groq/Claude/OpenAI cloud models.
- [ ] **Reciprocal Rank Fusion Tuning**: Empirical benchmarking of dense vs BM25 weights.
- [ ] **Visual Bounding Box Highlighter**: Interactive PDF viewer highlighting cited snippets.

### Future Consideration (v2+)

Features to defer until product-market fit is established:

- [ ] Multi-document cross-comparison.
- [ ] Enterprise multi-user support with authentication.
- [ ] Document export to structured knowledge graphs.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Robust Ingestion & Deduplication | HIGH | LOW | P1 |
| Docling Structured & Table Extraction | HIGH | MEDIUM | P1 |
| Persistent LanceDB Hybrid Retrieval | HIGH | MEDIUM | P1 |
| Local llama-server VLM Integration | HIGH | HIGH | P1 |
| Grounded QA & Page-Level Citations | HIGH | MEDIUM | P1 |
| Conditional RapidOCR | MEDIUM | MEDIUM | P1 |
| Hierarchical Summarization Profiles | HIGH | MEDIUM | P1 |
| Selective Visual Analysis | HIGH | HIGH | P1 |
| Streamlit Modernized UI | HIGH | MEDIUM | P1 |
| Cloud Inference Adapter (LiteLLM) | MEDIUM | LOW | P2 |
| Interactive Visual Highlighting | MEDIUM | MEDIUM | P2 |
| Multi-Document Search | LOW | HIGH | P3 |

## Competitor Feature Analysis

| Feature | NotebookLM | ChatPDF / AskYourPDF | Our Local System |
|---------|------------|----------------------|------------------|
| **Local Privacy** | Cloud only (Google) | Cloud only | 100% local-first, zero egress |
| **Hardware Overhead** | Zero local | Zero local | Optimized for 4 GB VRAM (RTX 3050) |
| **Visual Understanding** | High (Gemini) | Text-focused, weak on charts | Selective local 2B VLM analysis |
| **Table Extraction** | Good | Often flattens tables to raw strings | Docling structured markdown tables |
| **Evidence Provenance** | Excellent citations | Inconsistent page citations | Strict shared retrieval & citation verification |
| **Cost** | Free/Subscription | Monthly subscription | Free & open source |

## Sources

- SRS Specification v1.0.
- Analysis of local RAG implementations (Docling + LanceDB + llama.cpp).
- NotebookLM feature evaluation and citation mechanics.

---
*Feature research for: Local-First Multimodal PDF Intelligence System*  
*Researched: 2026-10-10*
