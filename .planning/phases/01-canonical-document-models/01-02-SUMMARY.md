---
phase: 01-canonical-document-models
plan: 01-02
status: completed
key_files:
  created:
    - upload_validation.py
    - tests/test_upload_validation.py
  modified:
    - pdf_reader.py
    - main.py
    - README.md
    - tests/test_pdf_reader.py
    - tests/test_models.py
requirements_covered:
  - INGEST-01
  - INGEST-02
  - INGEST-05
  - UI-01
  - STORE-01
  - STORE-03
---

# Phase 1 Plan 01-02 Summary: Upload Validation, SHA-256 Dedup & Progress UI

## Overview
Closed the upload trust gap and replaced mutable filename tracking with content-hash identity. Incoming PDFs are strictly validated server-side, deduplicated via SQLite `DocStore`, fault-isolated per page so corrupted pages do not crash document ingestion, and displayed with live staged progress in the Streamlit UI.

## Accomplished Tasks

1. **Upload Validation Module (`upload_validation.py`, INGEST-01, INGEST-02):**
   - Implemented `validate_pdf_bytes` with fail-fast validation:
     - `%PDF` header magic-byte verification.
     - 50 MB maximum file size cap (`MAX_FILE_MB = 50`).
     - 500 maximum page count limit (`MAX_PAGES = 500`).
   - Implemented streaming 1 MiB chunk SHA-256 computation (`sha256_bytes`) and stable `doc_id` derivation (`doc_<sha16>`).

2. **Validation & Deduplication Tests (`tests/test_upload_validation.py`):**
   - Verified magic-byte rejection on `corrupt_invalid.pdf` (closing WR-07).
   - Verified metadata extraction, rename stability (`test_rename_yields_same_doc_id`), oversize payload rejection, and page-count cap enforcement.

3. **Page Fault Isolation & Hash-based Chunk IDs (`pdf_reader.py`, INGEST-05):**
   - Wrapped per-page extraction in `try/except` to record `Page(status="failed", error=...)` without aborting document ingestion.
   - Migrated chunk IDs to rename-stable hash format: `f"{sha12}_p{page}_{j}"` with backward-compatible filename fallback.
   - Added `get_page_records()` accessor.

4. **Fault Isolation & Migration Tests (`tests/test_pdf_reader.py`, `tests/test_models.py`):**
   - Tested single-page error isolation (`test_page_failure_isolated`) verifying that an error on page 2 allows the remaining 19 pages to extract and record properly.
   - Tested chunk ID stability across file renames (`test_hash_chunk_ids_stable_across_rename`).
   - Tested legacy dictionary reading backward compatibility (`test_chunk_backward_compat_read`).

5. **Streamlit UI Wiring (`main.py`, UI-01, STORE-01, STORE-03):**
   - Integrated `doc_ids` session set and server-side validation.
   - Connected `DocStore` deduplication: duplicate uploads display `st.info` and skip redundant vector embedding.
   - Added `st.progress` page-by-page progress bars inside `st.status`.
   - Persisted extraction metadata to SQLite `data/documents.db` and wrote structured extraction caches to `.cache/<sha256>/<config_version>/`.

6. **Documentation (`README.md`):**
   - Documented upload caps (50 MB, 500 pages), deduplication policy, page fault isolation, and `.cache/` directory layout.

## Verification
- Test Suite: 44/44 tests passing (`pytest tests/ -v`)
- Linter & Formatting: Clean (`ruff check .`, `ruff format --check .`)
