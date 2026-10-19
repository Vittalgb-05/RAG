---
status: resolved
trigger: |
  Page 3 OCR processing failed: 'RapidOCROutput' object is not iterable
  Usage of TableItem.export_to_markdown() without `doc` argument is deprecated.
  [UploadValidation] Validated R2_Omprakash_Panda_The_Bear_House.pdf (doc_624238d0f471e917, 29 pages, 5085248 bytes)
  ... stuck in an infinite upload rerun loop, UI crawl, suspected GPU underutilization.
created: 2026-10-19
updated: 2026-10-19
---

# Debug Session: Upload Infinite Rerun Loop, RapidOCROutput Failure, and Ingestion Crawl

**Session Slug:** `upload-loop-rapidocr-and-crawl`

## Symptoms

**Expected behavior:**
- Uploading a PDF (including large/scanned documents like 29-page `R2_Omprakash_Panda_The_Bear_House.pdf`) extracts text and tables cleanly.
- RapidOCR processes low-text / scanned pages without raising `TypeError`.
- Docling exports tables without deprecation warnings.
- The document is indexed into DocStore and LanceDB, recorded in session state, and the app transitions cleanly to indexed chat/QA without infinite re-extraction loops.
- GPU acceleration is leveraged for VLM image analysis and LLM chat.

**Actual behavior:**
- Terminal loops every ~2 minutes repeating extraction from scratch.
- RapidOCR fails on pages with `'RapidOCROutput' object is not iterable`.
- Docling prints `Usage of TableItem.export_to_markdown() without doc argument is deprecated.` on every table item.
- The app appears to crawl and loop endlessly during upload; `documents.db` remains empty.

**Error messages:**
- `Page X OCR processing failed: 'RapidOCROutput' object is not iterable`
- `Usage of TableItem.export_to_markdown() without 'doc' argument is deprecated.`
- `sqlite3.IntegrityError: FOREIGN KEY constraint failed` (when attempting to insert `evidence_elements` before parent `documents` row).

**Reproduction:**
- Launch `python start.py --start-llama` and upload a multi-page PDF with images/drawings (e.g., `R2_Omprakash_Panda_The_Bear_House.pdf`).

## Root Cause Analysis

Four distinct interacting defects caused this failure cascade:

1. **RapidOCR Output Incompatibility (`RapidOCROutput` not iterable)**:
   - On Python 3.13 with modern `rapidocr`, calling `ocr(image_bytes)` returns a dataclass instance `RapidOCROutput` (containing `.txts`, `.scores`, `.boxes`, etc.) rather than a raw nested list or tuple.
   - `ocr_fallback.py:ocr_page_image` attempted `for item in result_list:` on `RapidOCROutput`, raising `TypeError: 'RapidOCROutput' object is not iterable` on all scanned/low-text pages.

2. **Foreign Key Inversion in Ingestion Pipeline**:
   - `doc_store.py` schema defines `FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE` on `evidence_elements`.
   - In `main.py`, visual analysis results were passed to `doc_store.record_evidence_elements(evidence_elements)` *before* `doc_store.upsert_document(doc_model)` was called.
   - SQLite enforces `PRAGMA foreign_keys = ON;`, raising `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.

3. **Premature `new_pdf_uploaded = True` Triggering Infinite Rerun**:
   - In `main.py`, `new_pdf_uploaded = True` was assigned at the top of the upload loop before extraction and indexing ran.
   - When the Foreign Key `IntegrityError` was caught by `except Exception as err: continue`, execution skipped inserting the document, updating `st.session_state.doc_ids`, or saving chunks.
   - The outer loop checked `if new_pdf_uploaded: st.rerun()`, causing Streamlit to restart the script.
   - Because the document was never added to `doc_ids` or `documents.db`, Streamlit encountered the file in `st.file_uploader` and attempted extraction again, causing an endless ~2-minute re-ingestion loop.

4. **Docling Table Markdown Deprecation Spam & Lack of Visual Progress Indication**:
   - `docling_reader.py` invoked `item.export_to_markdown()` without passing `doc=docling_doc`, emitting 10 deprecation warnings per run.
   - Visual analysis sequentially processed up to 20 images without progress feedback in the UI, making GPU VLM inference appear as an unresponsive freeze.

## Changes Made

1. **`ocr_fallback.py`**:
   - Updated `ocr_page_image` to detect `hasattr(target, 'txts')` and unpack `target.txts` and `target.scores` directly from `RapidOCROutput`.
   - Added `isinstance(target, (list, tuple))` guard to gracefully ignore unsupported non-iterable returns without raising `TypeError`.
   - Added unit tests in `tests/test_ocr_fallback.py` for `RapidOCROutput` parsing and empty handling.

2. **`docling_reader.py`**:
   - Added `_export_table_markdown(table_obj, doc=docling_doc)` helper that forwards the parent document context to `TableItem.export_to_markdown(doc=...)` and falls back gracefully for legacy mocks.
   - Added unit test in `tests/test_docling_reader.py` verifying doc parameter forwarding.

3. **`visual_analyzer.py`**:
   - Added `progress_callback: Callable[[int, int, str], None] | None = None` support to `analyze_visual_elements` for real-time progress reporting during batch VLM processing.

4. **`main.py`**:
   - Added `failed_doc_ids` set in `st.session_state` to prevent re-processing failed uploads in loops.
   - Moved `new_pdf_uploaded = True` so it is only assigned after successful indexing.
   - Reordered database operations: `doc_store.upsert_document(doc_model)` is called before `doc_store.record_evidence_elements(evidence_elements)` to satisfy SQLite foreign key constraints.
   - Added `st.status` feedback with real-time visual element progress indicator showing local VLM GPU analysis.

## Verification

1. **Full Test Suite**:
   - `pytest -q` ran 267 tests across the repository.
   - Result: `267 passed in 35.39s` (0 failures, 0 errors).
2. **End-to-End Pipeline on Actual PDF**:
   - Ran `verify_actual_pdf.py` against `R2_Omprakash_Panda_The_Bear_House.pdf` (29 pages, 5.08 MB).
   - Extracted 124 paragraphs across 29 pages via Docling without any deprecation warnings.
   - Conditional OCR completed with 0 errors.
   - Detected 20 visual elements.
   - Successfully upserted document, 20 evidence elements, 29 page records, and 124 chunks into SQLite with foreign keys enabled and 0 integrity errors.
3. **GPU Verification**:
   - Verified `tools/llama-server/llama-server.exe` runs with CUDA 12 (`ggml-cuda.dll`), offloading 28 layers to NVIDIA RTX 3050 Laptop GPU at ~318 t/s.
