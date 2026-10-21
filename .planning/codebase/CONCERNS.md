# Codebase Concerns

**Analysis date:** 2026-10-21
**Refreshed:** 2026-10-21 after repair commits `4b0d685`, `5e9aad8`, `828e8a3`, `0f7b994`.
**Verification at refresh:** 318 tests passing, `ruff check` clean, `ruff format --check` clean.

This file now records only concerns that remain open. Resolved findings from the original 2026-10-21 audit are listed at the end for traceability.

## Open Concerns

### 1. Extraction cache is write-only

- **Issue:** `pages.json`, `chunks.json`, and `manifest.json` are written after ingestion, but no runtime path reads them.
- **Files:** `ui/ingestion_service.py:330-338`
- **Impact:** Duplicate disk usage for every document; no re-index or retry benefit; cache invalidation complexity with no consumer.
- **Fix approach:** Either read the cache as a fast re-index path (verify `manifest.json` hashes/model version first) or delete the writes.
- **Severity:** Medium.

### 2. Library code uses `print()` instead of logging

- **Issue:** Three non-CLI modules print directly, bypassing `core/logging_setup.py`.
- **Files:** `ingestion/pdf_reader.py:131`, `ingestion/upload_validation.py:106`, `core/doc_store.py:164`
- **Impact:** Diagnostics are not timestamped or leveled, and log redaction/filtering cannot apply.
- **Fix approach:** Replace with `logger = logging.getLogger(__name__)`; reserve `print` for `start.py`/`setup.py` CLI output.
- **Severity:** Low.

### 3. `setup.py` is an 883-line multi-purpose script

- **Issue:** Packaging metadata, dependency installation, model downloading, archive extraction, and CLI behavior share one file; requirements are parsed at build time.
- **Files:** `setup.py:1-883`
- **Impact:** `pip install -e .` executes operational code; the setup/download paths remain hard to test independently.
- **Fix approach:** Move operational logic to `scripts/setup_cli.py`; keep packaging metadata declarative in `pyproject.toml`.
- **Severity:** Medium.

### 4. Follow-up query rewriting is duplicated

- **Issue:** The short-follow-up heuristic exists in both `AiModel` and the Chat view; only the view's copy governs retrieval when `retrieval_result` is precomputed.
- **Files:** `core/local_llm.py:271-300`, `ui/views.py:365-380`
- **Impact:** Behavior can diverge by call path; future edits risk fixing only one copy.
- **Fix approach:** Extract one `contextualize_followup_query()` helper and call it from both paths.
- **Severity:** Low.

### 5. Deprecated retrieval facades remain shipped

- **Issue:** `HybridRetriever.search()` / `get_context()` and `LocalEmbedding.search()` / `get_context()` / `search_hybrid()` still exist with different score semantics, and `pyproject.toml` globally suppresses `DeprecationWarning`.
- **Files:** `retrieval/hybrid_retriever.py:855-870`, `retrieval/local_embedding.py:107-155`, `pyproject.toml` filterwarnings
- **Impact:** Two retrieval return types with opposite score conventions; deprecation drift is invisible.
- **Fix approach:** Remove the facades and stop globally suppressing `DeprecationWarning` for tests.
- **Severity:** Low.

### 6. Static analysis is intentionally minimal

- **Issue:** Ruff selects only `E`, `F`, `W` and ignores `E501`; no bugbear (`B`), security (`S`), import sorting (`I`), or type checker runs.
- **Files:** `pyproject.toml:11-15`
- **Impact:** Broad `except Exception`, mutable defaults, shadowing, and typing regressions are not caught.
- **Fix approach:** Add `B`, `S`, `I`, `UP` incrementally; run `mypy` on `core/` and `retrieval/`.
- **Severity:** Medium.

### 7. Documentation drift in README

- **Issue:** The README badge/tree describe stale test counts (309/248 while the suite has 318) and `start.py` is described as performing hardware preflight when it primarily checks runtime paths and Python version.
- **Files:** `README.md:10`, `README.md:76-110`, `start.py`
- **Impact:** Onboarding expectations are wrong and the counts will drift again.
- **Fix approach:** Generate counts in CI or replace exact counts with a link to the CI badge; describe launcher checks precisely.
- **Severity:** Low.

## Verification Gaps (not code defects)

These paths remain unverified because no live llama-server/GPU session was run:

- Real llama.cpp generation and token streaming.
- Peak VRAM and thermal behavior with Qwen2-VL 2B inside the 4 GB envelope.
- OCR accuracy on scanned documents and VLM quality on charts/diagrams.
- Citation precision on real generated answers.
- Restart persistence against a real ingested corpus.

See `docs/TEST_RESULTS.md` §4 for the required manual checks.

## Resolved in the 2026-10-21 Audit and Repair

| Concern | Resolution | Commit |
|---|---|---|
| Silent vector-persistence failure | `VectorIndexError`; failures propagate to callers | `a6dc76a` |
| Split LanceDB roots | Canonical `data/lancedb` plus copy-only legacy migration | `a6dc76a` |
| Non-atomic ingestion | `DocStore.record_ingestion` single transaction | `7044982` |
| Delete/purge reported success on failure | Vectors-first delete; purge aggregates failures | `a6dc76a` |
| Deleted documents resurfaced from fallback store | Fallback mirror rewritten on every index/delete; deletion test added | `5e9aad8` |
| Document-scoped search filtered after global top-K | Scope pushed into dense/FTS backends with post-filter defense | `5e9aad8` |
| Unbounded summarizer reduce prompt | 2,000-token fast path; iterative budgeted consolidation; oversized pages split | `5c50656` |
| Docling chunk offsets inconsistent | Offsets mapped to block-relative spans; monotonic-offset test added | `4b0d685` |
| Long Docling tables mangled | Row-aware table splitter repeats headers | `5c50656` |
| Sanitizer bypass (`data:`/`javascript:`, `srcset`, style `url()`, `<svg><use>`) | Dangerous schemes always stripped; fetch-capable attributes removed in local mode | `828e8a3` |
| Cloud consent bypass | Explicit consent required for LiteLLM and Groq generation/stream/vision | `c3518ce` |
| Stale summary cache after model switch | Strict `model_version` match; UI accepts only the exact version | `7044982` |
| Summary/retrieval state leaked across session reset | `AiModel.reset_turn_state()` + shared `reset_in_memory_session()` | `0f7b994` |
| Qwen2/Qwen3 identity misrepresentation | Qwen2-VL labels, GGUF metadata verification, launcher mismatch refusal | `e75733c`, `f33a6dc` |
| Unsafe archive extraction | Traversal/link-safe zip and tar extraction | `e75733c` |
| `pages` table write-only | `DocStore.get_pages_for_doc()` added | `7044982` |
| Docling GPU contention and first-run egress | CPU pinning and `DOCLING_ARTIFACTS_PATH` support | `5c50656` |
