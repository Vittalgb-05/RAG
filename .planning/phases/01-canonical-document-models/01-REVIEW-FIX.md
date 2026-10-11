---
phase: 01-canonical-document-models
reviewed: 2026-10-11T02:30:00Z
fixed: 2026-10-11T05:25:00Z
status: resolved
fixes_applied:
  - CR-01
  - CR-02
  - CR-03
  - WR-01
  - WR-02
  - WR-03
  - WR-04
  - WR-05
  - WR-06
  - WR-07
  - WR-08
  - IN-01
  - IN-02
  - IN-03
  - IN-04
  - IN-06
verification:
  tests: 54 passed (100%)
  ruff_check: 0 errors
  ruff_format: clean
verdict: APPROVED
---

# Phase 01: Code Review Fix Report — Canonical Document Models

**Date Fixed:** 2026-10-11T05:25:00Z  
**Phase:** 01-canonical-document-models  
**Review Source:** `01-REVIEW.md`  
**Verdict:** APPROVED  

## Summary of Fixes Applied

All 3 Critical issues, 8 Warnings, and relevant Info findings identified during the adversarial code review of Phase 1 have been resolved and verified with unit tests.

### Critical Fixes

1. **CR-01 & CR-03: Persistence & Session Index Rebuild After Restart (`main.py`, `doc_store.py`)**
   - **Fix:** Added `doc_store.record_chunks([Chunk.model_validate(p) for p in paragraphs])` in the production upload pipeline (`main.py`).
   - On dedup hit when `st.session_state.local_embedding` is `None` (post-restart), chunks are retrieved via `doc_store.get_chunks_for_doc(doc_id)` and fed to `LocalEmbedding.build_index()`.
   - Verified with unit test `test_restore_chunks_to_embedding_from_doc_store` in `tests/test_doc_store.py`.

2. **CR-02: `PdfReader` Construction & Extraction Fault Isolation (`main.py`)**
   - **Fix:** Enclosed `PdfReader(pdf_stream, filename=filename)` construction and `extract_text()` in a per-file `try/except Exception as err:` block with `st.error(...)` and `continue`, ensuring that a corrupted/unreadable PDF cannot abort processing of other files in a batch.

### Warning Fixes

3. **WR-01: SQLite Connection Lifecycle Leak (`doc_store.py`)**
   - **Fix:** Converted `_connect()` into a `@contextmanager` generator yielding `conn` and guaranteeing `conn.close()` inside a `finally:` block. Normalized `self.db_path = Path(db_path).resolve()`.

4. **WR-02: Fault-Isolation Scope Widened (`pdf_reader.py`)**
   - **Fix:** Widened the per-page `try/except` to enclose text splitting and `Chunk` model construction. Filtered empty whitespace strings and isolated any splitter/validation failures to the specific `Page(status="failed")`.

5. **WR-03: TOCTOU Concurrency Guard (`main.py`, `doc_store.py`)**
   - **Fix:** Handled `sqlite3.IntegrityError` at `doc_store.upsert_document` in `main.py`, logging an informational message instead of surfacing an unhandled exception.

6. **WR-04: Size Pre-Check Before Memory Buffering (`main.py`)**
   - **Fix:** Added guard checking `uploaded_file.size > MAX_FILE_MB * 1024 * 1024` before calling `uploaded_file.getvalue()`.

7. **WR-05: Identity Field & Literal Validation (`models.py`, `upload_validation.py`)**
   - **Fix:** Enforced `^[0-9a-f]{64}$` regex in `doc_id_for()`.
   - Constrained `Page.status` to `Literal["ok", "empty", "failed"]`, `Document.status` to `Literal["pending", "indexed", "failed"]`, and `EvidenceElement.kind` to `Literal["text", "table", "chart", "image"]`.
   - Added `model_validator` in `Document` verifying `doc_id` begins with `doc_`.

8. **WR-06: Lexical Chunk Ordering (`pdf_reader.py`, `doc_store.py`)**
   - **Fix:** Updated chunk generation to 4-digit zero-padded index (`f"{chunk_prefix}_p{page_num}_{j:04d}"`).
   - Updated `get_chunks_for_doc` query to `ORDER BY page ASC, rowid ASC;`.

9. **WR-07: Cache Artifact Commits Prevented (`.gitignore`)**
   - **Fix:** Added `.cache/` to `.gitignore`.

10. **WR-08: Unified UTC ISO Timestamps (`main.py`)**
    - **Fix:** Standardized on `datetime.datetime.now(datetime.timezone.utc).isoformat()` for stored metadata, formatting only at render time.

### Info Hardening

11. **IN-01:** Removed redundant `.lower()` call on `hasher.hexdigest()` (`upload_validation.py`).
12. **IN-02:** Added `extra="forbid"` and non-negative/non-inverted coordinate validation to `BBox` (`models.py`).
13. **IN-03:** Escaped code markup for raw filenames in UI display (`main.py`).
14. **IN-04:** Added regex check to `cache_dir_for()` to prevent path traversal on untrusted hashes (`models.py`).
15. **IN-06:** Updated `ON CONFLICT(chunk_id)` in `record_chunks` and `ON CONFLICT(doc_id)` in `upsert_document` to refresh all mutable columns (`doc_store.py`).

---

## Verification Results

- **Pytest Suite:** 54 passed in 10.90s (10 new tests added covering all fixes: 0-page PDFs, invalid SHA formatting, path traversal, BBox bounds, Literal statuses, DocStore restoration).
- **Ruff Lint:** `ruff check .` passed with 0 errors.
- **Ruff Format:** `ruff format --check .` passed cleanly (18 files formatted).
