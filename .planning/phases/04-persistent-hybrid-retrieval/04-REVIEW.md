---
phase: 04-persistent-hybrid-retrieval
reviewed: 2026-10-11T19:25:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - hybrid_retriever.py
  - models.py
  - local_embedding.py
  - local_llm.py
  - main.py
  - requirements.txt
  - tests/test_hybrid_retriever.py
  - tests/test_models.py
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
verdict: NEEDS FIXES
---

# Phase 04: Code Review Report — Persistent Hybrid Retrieval

**Reviewed:** 2026-10-11T19:25:00Z  
**Depth:** standard (per-file analysis, security, lifecycle, concurrency, error boundaries)  
**Files Reviewed:** 8 core phase files + test suites  
**Verdict:** NEEDS FIXES (3 Critical issues, 6 Warnings, 3 Info items)

---

## Summary

Phase 4 establishes persistent embedded vector and keyword retrieval via `HybridRetriever` (`hybrid_retriever.py`), CPU-pinned Sentence-Transformers embeddings (`local_embedding.py`), BM25 full-text keyword search with Reciprocal Rank Fusion (RRF), and the canonical immutable `RetrievalResult` contract (`models.py`). 133 tests pass offline and ruff formatting is clean.

However, an adversarial audit revealed 3 Critical vulnerabilities and 6 Warnings that must be resolved:
1. **CR-01**: `main.py` never instantiates or indexes into `HybridRetriever`, leaving the production Streamlit application running entirely on ephemeral in-memory `VectorIndex` and bypassing LanceDB persistent hybrid search completely (violating RETR-02 and RETR-03).
2. **CR-02**: Redundant dual-query divergence in chat loop violates RETR-04 and Design Lock D2: `main.py` searches for UI chips with raw prompt, while `local_llm.py` executes search again with contextualized prompt, causing UI sources and generation context to diverge into two separate `RetrievalResult` instances.
3. **CR-03**: LanceDB SQL/filter injection vulnerability in `has_document`, `delete_document`, and `index_chunks`: unescaped single quotes in `doc_id` or `chunk_id` allow syntax crashes or arbitrary row deletion across tables.
4. **WR-01 through WR-06**: Chunk duplication in fallback index on re-indexing, post-restart BM25 fallback failure in LanceDB mode, quadratic $O(N^2 \cdot |Q|)$ BM25 document frequency calculation, unhandled `BBox` serialization in fallback store, missing `close()` lifecycle, and schema validation gaps.

---

## Critical Issues

### CR-01: `main.py` Never Instantiates `HybridRetriever`, Bypassing Persistent Hybrid Storage
- **File:** `main.py:197, 255, 373`
- **Category:** Functional Defect / Architectural Integrity
- **Issue:** `main.py` imports and instantiates only `LocalEmbedding` (which contains an in-memory `VectorIndex`). `HybridRetriever` is never imported, initialized in session state, or populated during document upload. Consequently, documents are never indexed into LanceDB (`data/lancedb/`), and user queries never benefit from BM25 full-text search or Reciprocal Rank Fusion in the running UI.
- **Fix:** In `main.py`, initialize `st.session_state.hybrid_retriever = HybridRetriever(embedding_fn=st.session_state.local_embedding._embed_one)` during app lifecycle/upload, index chunks into `hybrid_retriever` on ingestion and on restart dedup restoration, and pass it to `AiModel`.

### CR-02: Redundant Dual-Query Search Violates RETR-04 Single Shared `RetrievalResult` Identity
- **File:** `main.py:373-399` & `local_llm.py:126-140`
- **Category:** Design Lock Violation / Divergence
- **Issue:** RETR-04 and Design Lock D2 strictly require a single shared `RetrievalResult` instance to feed both generation context and UI source chips. Currently, `main.py` executes search once using `prompt` to obtain UI chip source labels, and then passes control to `AiModel.ask_a_question_from_pdf_stream`, which executes search a SECOND time using a modified query (`f"{last_user_msgs[-1]} {prompt}"`). This redundant execution wastes CPU cycles and creates divergence where UI chips do not match the evidence used by the LLM prompt.
- **Fix:** Update `AiModel.ask_a_question_from_pdf_stream` to accept an optional pre-computed `retrieval_result: RetrievalResult | None = None`. If provided, it uses it directly without re-searching. In `main.py`, contextualize the query once, retrieve `RetrievalResult`, display sources, and pass the exact same instance into `ask_a_question_from_pdf_stream`.

### CR-03: Filter Query Injection in `has_document` and `delete_document`
- **File:** `hybrid_retriever.py:190, 289, 315`
- **Category:** Security / Data Integrity
- **Issue:** LanceDB table methods `where()` and `delete()` accept SQL-like filter strings. String interpolation without sanitization (`f"doc_id = '{doc_id}'"` and `f"chunk_id IN ({quoted_ids})"`) exposes the database to filter injection or syntax errors if document IDs contain single quotes (e.g., `doc_O'Reilly` or malicious payloads like `doc_1' OR '1'='1`), which could delete all rows in the table.
- **Fix:** Sanitize single quotes by escaping them (`doc_id.replace("'", "''")` and `cid.replace("'", "''")`) before interpolating into filter strings.

---

## Warnings

### WR-01: Fallback Index Fails to Deduplicate Chunks on Re-indexing
- **File:** `hybrid_retriever.py:237-240`
- **Category:** Data Integrity / Duplicate Accumulation
- **Issue:** While LanceDB uses `merge_insert` or deletion by `chunk_id`, the fallback store unconditionally appends to `_fallback_store.documents` and `vectors`. When re-uploading an existing document or re-indexing, `_fallback_store` accumulates duplicate chunks, doubling `count_chunks()` and distorting BM25 term frequencies.
- **Fix:** In `index_chunks`, deduplicate incoming chunks against `_fallback_store` by removing any pre-existing chunks with matching `chunk_id` before appending.

### WR-02: Post-Restart BM25 Fallback Fails Under LanceDB Mode
- **File:** `hybrid_retriever.py:381, 449`
- **Category:** Reliability / Fallback
- **Issue:** On application restart with an existing LanceDB table, `self._table` is opened, but `self._fallback_store` remains empty. If LanceDB native Tantivy FTS is unavailable or fails, `search_fts` falls back to `_bm25_search_fallback`, which reads `self._fallback_store.documents` (which is empty). Thus, keyword search returns zero results after restart.
- **Fix:** In `_bm25_search_fallback`, if `self._has_lancedb` and `self._table` is present, read stored chunk documents from `self._table` if `self._fallback_store.documents` is empty.

### WR-03: Quadratic Document Frequency Calculation in BM25 Fallback
- **File:** `hybrid_retriever.py:408`
- **Category:** Performance / Algorithmic Complexity
- **Issue:** In `_bm25_search_fallback`, `df = sum(1 for dtoks in doc_tokens if qt in dtoks)` is evaluated inside the inner loop for each document. For $N$ documents and $|Q|$ terms, this performs $O(N^2 \cdot |Q|)$ operations, causing noticeable latency on larger document corpora.
- **Fix:** Precompute `df` for each query term in a single pass outside the document loop: `df_map = {qt: sum(1 for dtoks in doc_tokens if qt in dtoks) for qt in query_terms}`.

### WR-04: Non-Serializable `BBox` in Fallback Store Persistence
- **File:** `hybrid_retriever.py:150-156`
- **Category:** Serialization Safety
- **Issue:** `_save_fallback_store` dumps `self._fallback_store.documents` directly using `json.dump`. If any document contains a Pydantic `BBox` object (rather than primitive dict or `bbox_json`), `json.dump` raises `TypeError: Object of type BBox is not JSON serializable`.
- **Fix:** Normalize all document metadata to JSON-serializable primitives (e.g. converting `bbox` via `model_dump()`) before dumping.

### WR-05: Missing Resource Lifecycle on `HybridRetriever`
- **File:** `hybrid_retriever.py:79-125`
- **Category:** Lifecycle / Resource Management
- **Issue:** Unlike `DocStore` and `AiModel`, `HybridRetriever` provides no `close()` method, `__enter__`, or `__exit__`. In long-running processes or multi-test fixtures, unclosed table handles or references can delay resource cleanup.
- **Fix:** Implement `close()`, `__enter__`, and `__exit__` on `HybridRetriever` to flush fallback storage and clean up database handles.

### WR-06: Schema Validation Gap on `EvidenceSnippet.doc_id`
- **File:** `models.py:150`
- **Category:** Schema Consistency
- **Issue:** `Document`, `Chunk`, and `EvidenceElement` enforce that `doc_id` starts with `"doc_"`, but `EvidenceSnippet` defines `doc_id: str` without validation, permitting arbitrary strings.
- **Fix:** Add a `@field_validator("doc_id")` or pattern ensuring `doc_id.startswith("doc_")` with a fallback for test mocks.

---

## Info Items

### IN-01: Awkward Citation Chip Formatting on Missing Filename
- **File:** `models.py:193`
- **Category:** UX / Formatting
- **Issue:** If `filename` is empty or omitted, `source_labels()` produces ` (p. 1)`.
- **Fix:** Fall back to `f"Page {s.page}"` or `f"{s.doc_id} (p. {s.page})"` when `filename` is empty.

### IN-02: Missing Dynamic Embedding Function Setter on `HybridRetriever`
- **File:** `hybrid_retriever.py:85-98`
- **Category:** Usability
- **Issue:** If `HybridRetriever` is instantiated before the embedding model is loaded, there is no setter method to attach `embedding_fn` later without accessing private attributes.
- **Fix:** Add `set_embedding_fn(fn: Callable[[str], list[float]]) -> None`.

### IN-03: Unstripped Evidence Content in Prompt Formatter
- **File:** `models.py:185`
- **Category:** Prompt Cleanliness
- **Issue:** Snippet content with excessive trailing/leading newlines causes irregular spacing in prompt blocks.
- **Fix:** Use `s.content.strip()` in `formatted_evidence()`.
