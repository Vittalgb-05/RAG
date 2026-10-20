---
status: resolved
trigger: |
  October 20 Architecture Assessment and CONCERNS.md resolution:
  - Fix P0 Infinite upload rerun loop: rotate uploader_key and gate new_docs_indexed on non-deduped uploads.
  - Fix P0 Incomplete Purge and Delete: create LifecycleService to clean SQLite, LanceDB, .cache/, session state, and chat history.
  - Fix P0 Index consistency: verify LanceDB vectors during dedupe and startup hydration, auto-repair missing vectors, and add Re-index action.
  - Fix P0 Cloud consent dialog reopen loop: atomically synchronize settings_cloud_toggle with cloud_mode on cancel.
  - Fix P1 Failed visual analysis indexed as evidence: filter placeholder/error messages in index_evidence_elements().
  - Fix P1 Zero network egress / links: neutralize external markdown links and remove unsafe HTML embeds in local mode.
  - Fix P1 Visual evidence attribution: index true PDF filename rather than doc_id.
  - Fix P1 Docker & SQLite hardening: bind localhost (127.0.0.1), ignore secrets/models in .dockerignore, and index doc_id in SQLite schema v4.
created: 2026-10-20
updated: 2026-10-20
---

# Debug Session: October 20 Architecture Stabilization & Concerns Resolution

**Session Slug:** `october-20-architecture-stabilization`  
**Status:** Resolved  
**Test Suite:** 296 passed in 39.06s (100% passing)  

## Root Cause Analysis & Fixes

### 1. P0 — Infinite Upload Rerun Loop
- **Root Cause:** Streamlit's `st.file_uploader` retains uploaded file items across script runs unless its `key` changes. After successful upload, `ui/views.py` called `st.rerun()` with the same `uploader_key`. On rerun, deduplication returned `success=True`, incrementing `new_docs_indexed` again and triggering an infinite `st.rerun()` loop.
- **Fix:**
  - Added `already_indexed: bool = False` to `IngestionResult` (`ui/ingestion_service.py`).
  - Rotated `st.session_state.uploader_key += 1` immediately after processing uploads in `render_sidebar_documents` (`ui/views.py`).
  - Gated `new_docs_indexed += 1` so deduped files do not trigger rerun cascades.
  - Regression tested in `tests/test_main_ui.py::test_upload_loop_regression_uploader_key_rotated`.

### 2. P0 — Incomplete Purge & Document Deletion
- **Root Cause:** Single-document deletion and global purge in `ui/views.py` did not remove `.cache/<sha256>/` page/chunk files, `summary_*` session keys, or `chat_history`, leaving residual data on disk and in memory.
- **Fix:**
  - Introduced `ui/lifecycle_service.py` with `delete_document()` and `purge_all()` methods.
  - Single deletion cleans SQLite, LanceDB, `.cache/<sha256>`, `session_state.doc_ids`, `indexed_files`, `document_metadata`, `selected_chat_doc`, and `summary_<doc_id>_*` keys.
  - Purge cleans all SQLite tables, LanceDB table, `.cache/` root directory, session states, and `chat_history`, followed by `VACUUM` in SQLite.
  - Regression tested in `tests/test_main_ui.py::test_lifecycle_service_atomic_delete` and `test_lifecycle_service_purge_all`.

### 3. P0 — Index Consistency & Auto-Repair
- **Root Cause:** If `data/lancedb/` was removed or corrupted, SQLite reported documents as indexed, causing deduplication and hydration to bypass re-indexing.
- **Fix:**
  - In `IngestionService.ingest_pdf`, deduplication checks `retriever.has_document(doc_id)`; if missing, it automatically restores vectors from SQLite chunks.
  - In `hydrate_startup_state` (`ui/hydration.py`), every indexed document is verified against LanceDB. Missing vectors are auto-repaired or flagged with `needs_reindex = True`.
  - Added a per-document "Re-index" button in Library view (`ui/views.py`) invoking `LifecycleService.reindex_document()`.
  - Also hydrated `failed_doc_ids` to preserve honest failure states across sessions.

### 4. P0 — Cloud Consent Dialog Infinite Reopening
- **Root Cause:** Pressing "Cancel" in the cloud consent dialog set `cloud_mode = False`, but `settings_cloud_toggle` remained `True`, causing the consent dialog to reappear on the very next rerun.
- **Fix:**
  - Synchronized `st.session_state.settings_cloud_toggle = False` whenever `cloud_mode` is False or canceled (`ui/views.py`).
  - Synchronized toggle state during settings render.
  - Regression tested in `tests/test_main_ui.py::test_cloud_consent_cancel_state_reset`.

### 5. P1 — Failed Visual Analysis Indexed as Evidence
- **Root Cause:** When VLM timed out or failed, `visual_analyzer.py` returned `[Visual element: analysis failed: ...]`, which was previously embedded and indexed into LanceDB, allowing models to cite errors as document facts.
- **Fix:**
  - In `HybridRetriever.index_evidence_elements`, added filtering to skip placeholder and error descriptions (`[Visual element:`).
  - Regression tested in `tests/test_hybrid_retriever.py::test_evidence_element_failed_placeholder_skipped`.

### 6. P1 — Zero Network Egress & Sanitization
- **Root Cause:** In local mode, markdown links (`[text](url)`), `<a href>` tags, and unsafe embeds (`iframe`, `object`, `embed`, `style`, `link`) were not blocked, risking browser-initiated network requests.
- **Fix:**
  - In `ui/sanitizer.py`, added removal of unsafe embed elements.
  - In local mode (`not allow_external`), neutralized external markdown links to ` `text` *(external link blocked)*` and stripped `<a href>` tags.
  - Preserved internal anchor links (`#section`).
  - Regression tested in `tests/test_sanitizer.py`.

### 7. P1 — Visual Evidence Attribution & UI Routing
- **Fix:** Passed `filename=filename` through `IngestionService` into `HybridRetriever.index_evidence_elements()` so visual evidence is attributed to the real PDF filename rather than `doc_id`.
- **Fix:** In `render_library_view`, updated the "Chat" button to navigate directly to `"Chat"` instead of `"Ask Documents"`.

### 8. Docker Hardening & SQLite Performance
- **Fix:** Bound ports `8501` and `8080` to loopback `127.0.0.1` in `docker-compose.yml`.
- **Fix:** Added `.env`, `.env.*`, `models/`, `*.gguf`, `*.onnx`, `.planning/`, `tests/`, and `application_screenshots/` to `.dockerignore`.
- **Fix:** Added SQLite schema migration v4 in `doc_store.py` adding `idx_chunks_doc_id` and `idx_pages_doc_id`, plus `VACUUM` on purge.
- **Fix:** Ensured native FTS index creation on all primary write paths in `hybrid_retriever.py`.
