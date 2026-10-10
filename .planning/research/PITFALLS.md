# Pitfalls Research

**Domain:** Local-First Multimodal PDF Intelligence & RAG  
**Researched:** 2026-10-10  
**Confidence:** HIGH  

## Critical Pitfalls

### Pitfall 1: VRAM Exhaustion on 4GB RTX 3050 (CUDA OOM Crash)

**What goes wrong:**
Loading a VLM, context window, embeddings model, and OCR model simultaneously triggers `torch.cuda.OutOfMemoryError` or `llama.cpp: failed to allocate memory`, crashing the entire Python process or dropping GPU driver state.

**Why it happens:**
Developers assume 4 GB is sufficient for standard models without calculating total runtime footprint: 2B VLM GGUF Q4 (~1.5 GB), context KV-cache (8K tokens ~1.0 GB), multimodal vision projector (~0.6 GB), PyTorch runtime overhead (~0.5 GB), plus Windows desktop compositor allocations (~0.5-0.8 GB).

**How to avoid:**
1. Keep exactly ONE inference engine on GPU (llama-server with `-ngl` tuned to leave 500 MB VRAM headroom).
2. Pin Sentence-Transformers embeddings (`all-MiniLM-L6-v2`) and RapidOCR to CPU (`device="cpu"`).
3. Bound context window to 4096-8192 tokens.

**Warning signs:**
`nvidia-smi` showing > 3.6 GB allocated before running inference; sluggish Windows UI rendering.

**Phase to address:**
Phase 2 (Local Inference Setup) & Phase 6 (Performance Optimization).

---

### Pitfall 2: Divergent Retrieval Context Leading to Hallucinated Citations

**What goes wrong:**
The application answers a question and displays "Sources used", but the cited pages do not contain the claims in the answer, or the displayed sources do not match what the LLM read.

**Why it happens:**
`main.py` runs one retrieval call for user display (`search(prompt, k=10)`) and a different query for prompt context assembly (`get_context(f"{history} {prompt}", k=10)`), as identified in `CONCERNS.md #5`. Furthermore, without explicit citation verification, models frequently invent believable page numbers.

**How to avoid:**
1. A single shared `RetrievalResult` object passed to both prompt generation and UI rendering.
2. Require evidence IDs (`[E1]`, `[E2]`) in the generation prompt.
3. Post-generation regex citation validator checking cited IDs against actual retrieved records (enforce >=95% precision).

**Warning signs:**
Answers citing page numbers that do not match the evidence text chips displayed in Streamlit.

**Phase to address:**
Phase 5 (Summarization and QA) & Phase 1 (Canonical Document Models).

---

### Pitfall 3: Ingestion Pipeline Bottleneck & Memory Exhaustion from Large PDFs

**What goes wrong:**
Uploading a 100+ page or image-heavy PDF causes Streamlit to freeze or crashes the server with out-of-memory errors during parsing or embedding.

**Why it happens:**
Reading the entire file into memory with `uploaded_file.getvalue()`, running unconditional OCR on every page, and embedding all chunks in a single monolithic batch.

**How to avoid:**
1. Server-side magic-byte validation (`%PDF`) and file size/page limits.
2. Streamed page-by-page processing with Docling.
3. RapidOCR triggered *only* when page extractable character count is below threshold (< 50 characters).
4. Chunk mini-batching with progress updates and SQLite checkpointing.

**Warning signs:**
Progress bar freezing at 0% for > 30 seconds on standard uploads; RAM usage spiking into paging.

**Phase to address:**
Phase 1 (Canonical Document Models) & Phase 3 (Multimodal Ingestion).

---

### Pitfall 4: Treating Generated Visual Descriptions as Objective Ground Truth

**What goes wrong:**
The VLM analyzes a financial chart and misreads numbers (e.g. reading 14.5% as 18.2%), which then gets indexed into the vector store as objective fact and leads to erroneous answers.

**Why it happens:**
Small 2B VLMs can hallucinate precise numerical details in charts and dense diagrams.

**How to avoid:**
1. Tag visual descriptions with explicit metadata (`type="visual_description"`, model version, confidence flag).
2. Prioritize Docling extracted table data over visual interpretations for numerical queries.
3. Instruct the QA prompt to check table data first and warn when relying solely on visual approximations.

**Warning signs:**
Discrepancies between numbers reported in document tables and visual summary answers.

**Phase to address:**
Phase 3 (Multimodal Ingestion) & Phase 5 (Summarization and QA).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| In-memory `VectorIndex` list | Zero external setup | Data loss on restart, linear O(N) scan slowdown | Never in production; existing tech debt to eliminate |
| Relying on filename for deduplication | Simple hash table check | Silent stale index when uploading modified file with same name | Never; use SHA-256 content hashing |
| Hardcoding `k=10` and `chunk_size=1000` | Faster initial prototyping | Context overflow on long docs; brittle tuning | Never; centralize in `config/settings.yaml` |
| Calling cloud API without privacy consent | Easy fallback | Violates local-first privacy requirement | Never; requires explicit user opt-in |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **llama-server** | Assuming server is running; unhandled connection refusal | Health check endpoint (`GET /health`) with user-friendly setup instructions and auto-retry. |
| **Docling** | Forcing OCR on all documents | Configure pipeline options (`do_ocr=False`) by default; enable conditionally per page. |
| **LanceDB** | Not specifying persistent storage URI | Explicitly pass local directory path (`data/lancedb`) to `lancedb.connect()`. |
| **Streamlit State** | Re-instantiating heavy models in session state | Use `@st.cache_resource` for providers and database connections. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| **Concurrent GPU allocation** | Instant CUDA OOM crash | Offload embeddings & OCR to CPU; sequence inference | Breaks when 2 models hit GPU |
| **Unbounded Context Window** | Slow generation, high KV memory | Bound context to 4K–8K tokens; truncate history | Breaks past 8192 tokens |
| **Pure Python Vector Scan** | UI lags by seconds on search | Use LanceDB vector indexing with SIMD/ANN | Breaks past 2,000 chunks |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| **Prompt Injection via Document Text** | Malicious PDF overrides system prompt | Delimit document context with XML/Markdown tags; explicit non-override instruction. |
| **Exposing API Keys in Git / Code** | Secret leak | Load keys via `.env` and `python-dotenv`; ensure `.env` in `.gitignore`. |
| **Unsafe File Upload Handling** | Arbitrary file upload / zip-bomb | Verify `%PDF` magic bytes, enforce max file size limit. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| **Silent Processing Hangs** | User thinks app is frozen during Docling parse | Render step-by-step progress with page counts and status messages. |
| **Vague Hallucinated Citations** | User can't find referenced text in the PDF | Show clickable evidence snippets alongside page numbers. |
| **All-or-Nothing Upload Failure** | 1 unreadable page fails entire 50-page PDF | Page-level fault isolation: index valid pages and report failed page numbers. |

## "Looks Done But Isn't" Checklist

- [ ] **PDF Ingestion:** Often missing non-PDF magic-byte checks — verify uploading a renamed `.exe` is rejected.
- [ ] **Deduplication:** Often missing content hash check — verify re-uploading modified file with same name triggers re-index.
- [ ] **Citations:** Often displays raw page numbers without validating content — verify citation precision >= 95%.
- [ ] **Local Inference:** Often secretly makes outbound requests — verify app operates with network disabled.
- [ ] **Model Failure:** Often dumps raw stack trace — verify graceful error banner and fallback prompt.

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| VRAM Exhaustion | Phase 2 & Phase 6 | Benchmark peak VRAM under 3.5 GB during active inference. |
| Divergent Retrieval & Bad Citations | Phase 1 & Phase 5 | Automated test verifying citation precision >= 95% on test corpus. |
| Ingestion Bottlenecks | Phase 1 & Phase 3 | Ingest 20-page digital PDF in < 5 seconds; page-level failure recovery. |
| Visual Hallucinations | Phase 3 & Phase 5 | Visual descriptions tagged distinctly and checked against tables. |

## Sources

- Current codebase issues analyzed in `.planning/codebase/CONCERNS.md`.
- llama.cpp memory benchmarks on 4GB NVIDIA laptop GPUs.
- Docling performance benchmarks on digital vs scanned PDFs.

---
*Pitfalls research for: Local-First Multimodal PDF Intelligence System*  
*Researched: 2026-10-10*
