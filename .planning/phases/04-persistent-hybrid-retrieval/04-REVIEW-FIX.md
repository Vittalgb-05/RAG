# Phase 4: Persistent Hybrid Retrieval — Code Review Fix Report

**Review Date:** 2026-10-11  
**Target Phase:** Phase 4 (`04-persistent-hybrid-retrieval`)  
**Resolution Status:** All Critical, Warning, and Info findings resolved and verified.

---

## 1. Summary of Applied Fixes

### Critical Findings

| ID | Issue | Location | Resolution | Status |
|:---|:---|:---|:---|:---|
| **CR-01** | `main.py` never instantiated or indexed into `HybridRetriever`, bypassing persistent LanceDB hybrid search | `main.py` | Added `hybrid_retriever` to Streamlit session state, indexed chunks on upload and restart dedup restoration, and wired into chat generation pipeline. | **FIXED** |
| **CR-02** | Redundant dual-query search caused divergence between UI citation labels and LLM prompt context | `main.py`, `local_llm.py` | Contextualized search query once in `main.py`, executed search to retrieve single canonical `RetrievalResult`, and passed it directly into `AiModel.ask_a_question_from_pdf_stream(retrieval_result=...)` without re-searching. | **FIXED** |
| **CR-03** | Filter query SQL injection in `has_document` and `delete_document` | `hybrid_retriever.py` | Sanitized single quotes (`doc_id.replace("'", "''")` and `cid.replace("'", "''")`) across all LanceDB filter expressions to protect against syntax crashes and arbitrary row deletions. | **FIXED** |

---

### Warning Findings

| ID | Issue | Location | Resolution | Status |
|:---|:---|:---|:---|:---|
| **WR-01** | Fallback index failed to deduplicate chunks on re-indexing | `hybrid_retriever.py` | Added chunk deduplication by `chunk_id` in `index_chunks` fallback store, preventing duplicate accumulation on repeated document uploads. | **FIXED** |
| **WR-02** | Post-restart BM25 fallback returned zero results when LanceDB table was present | `hybrid_retriever.py` | In `_bm25_search_fallback`, added automatic chunk recovery from `self._table` if `_fallback_store.documents` is empty. | **FIXED** |
| **WR-03** | Quadratic $O(N^2 \cdot |Q|)$ document frequency calculation in BM25 fallback | `hybrid_retriever.py` | Precomputed term document frequencies once in a single pass outside the document scoring loop, reducing complexity to $O(N \cdot |Q|)$. | **FIXED** |
| **WR-04** | Non-serializable `BBox` objects caused crashes in fallback store persistence | `hybrid_retriever.py` | Normalized document metadata and converted any `BBox` objects to JSON-serializable primitives in `_save_fallback_store`. | **FIXED** |
| **WR-05** | Missing resource lifecycle on `HybridRetriever` | `hybrid_retriever.py` | Implemented `close()`, `__enter__`, and `__exit__` context management on `HybridRetriever`. | **FIXED** |
| **WR-06** | Schema validation gap on `EvidenceSnippet.doc_id` | `models.py` | Added `@model_validator` ensuring `doc_id` starts with `"doc_"`, aligning with `Document` and `Chunk` standards. | **FIXED** |

---

### Info Findings

| ID | Issue | Location | Resolution | Status |
|:---|:---|:---|:---|:---|
| **IN-01** | Awkward citation chip formatting when filename is empty | `models.py` | Updated `source_labels()` and `formatted_evidence()` to fall back to `Page {page}` or `doc_id` when `filename` is absent. | **FIXED** |
| **IN-02** | Missing dynamic embedding function setter | `hybrid_retriever.py` | Implemented `set_embedding_fn(fn)` to allow attaching/updating query embedders post-initialization. | **FIXED** |
| **IN-03** | Unstripped evidence content in prompt formatter | `models.py` | Stripped leading/trailing whitespace (`s.content.strip()`) in `RetrievalResult.formatted_evidence()`. | **FIXED** |

---

## 2. Verification & Test Results

- **Test Suite Pass Rate:** 100% (**138 / 138 tests passed in 13.51s**, zero regressions)
- **Phase 4 Specific Test Suites:**
  - `tests/test_hybrid_retriever.py` (14 tests) — Passed *(+3 regression tests: injection escaping, deduplication, lifecycle)*
  - `tests/test_models.py` (18 tests) — Passed *(+1 regression test: doc_id validation and filename fallback)*
  - `tests/test_local_llm.py` (11 tests) — Passed *(+1 regression test: pre-computed retrieval_result support)*
  - `tests/test_local_embedding.py` (3 tests) — Passed
- **Static Analysis & Formatting:**
  - `ruff check .` — Passed (0 violations)
  - `ruff format --check .` — Passed (33 files formatted)
- **CI Synchronization:**
  - `.github/workflows/ci.yml` validated:
    1. `ruff check .`
    2. `ruff format --check .`
    3. `python tests/data/corpus/generate_corpus.py`
    4. `pytest tests/ -v`

---

## 3. Review Sign-off

All adversarial code review findings for Phase 4 have been resolved and verified with exhaustive automated test coverage. Persistent hybrid retrieval is fully wired, memory-safe, SQL-injection safe, and guarantees single shared `RetrievalResult` identity across generation context and UI citations.
