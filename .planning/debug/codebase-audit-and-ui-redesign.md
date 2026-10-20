---
status: resolved
trigger: |
  Comprehensive codebase audit and UI redesign:
  - Fix P0 blockers: Purge/clear uploader retention, startup hydration from DocStore, GPU concurrency gate for visual analyzer, Docker local-inference environment resolution, PDF rendering resource limits & external image sanitization.
  - Implement AMOLED minimal premium UI redesign (.streamlit/config.toml, ui/ package, assets/ SVGs, 5 workspaces, no emojis, subtle animations).
created: 2026-10-19
updated: 2026-10-19
---

# Debug & Redesign Session: Codebase Audit and AMOLED UI Redesign

**Session Slug:** `codebase-audit-and-ui-redesign`
**Status:** Resolved
**Test Suite:** 283 passed in 38.26s

## Root Cause & Scope Resolution

### 1. P0 — Correctness, Privacy & Release Blockers
- **P0-1 (Purge/Clear Session File Retention):** Streamlit's file uploader retained previous files across session resets with static widget keys.
  - *Fix:* Bound uploader key dynamically to `key=f"pdf_uploader_{st.session_state.uploader_key}"`. Incremented `st.session_state.uploader_key` and reset `failed_doc_ids` on Clear Session and Purge.
- **P0-2 (Startup Hydration):** Persisted documents in SQLite and LanceDB were not hydrated into session state on initial browser connection.
  - *Fix:* Implemented `ui.hydration.hydrate_startup_state(doc_store)` which loads indexed documents into `st.session_state.doc_ids`, `indexed_files`, `document_metadata`, and binds `HybridRetriever`.
- **P0-3 (Visual GPU Concurrency):** Visual inference previously bypassed the concurrency lock, risking out-of-memory errors on 4 GB VRAM.
  - *Fix:* Wrapped `provider.analyze_image` in `InferenceGate.hold(timeout=60.0)` inside `visual_analyzer.py` so image analysis is strictly serialized with chat and summary generation.
- **P0-4 (Python 3.13 RapidOCR Compatibility):** `requirements.txt` previously lacked a Python 3.13 conditional entry for RapidOCR.
  - *Fix:* Added `rapidocr>=3.0.0; python_version >= "3.13"` to `requirements.txt`.
- **P0-5 (Docker Local-Inference Connection):** `llama_cpp_provider.py` did not consume `LLAMA_SERVER_HOST`/`LLAMA_SERVER_PORT` and rejected container hostnames.
  - *Fix:* In `llama_cpp_provider.py`, added resolution from `LLAMA_SERVER_URL` or `LLAMA_SERVER_HOST` + `LLAMA_SERVER_PORT`. Expanded the loopback validator to accept container internal hosts (`host.docker.internal`, `llama-server`).
- **P0-6 (PyMuPDF Licensing Disclosure):** PyMuPDF requires AGPL-3.0 or commercial licensing, while the project declared MIT.
  - *Fix:* Created `docs/LICENSES.md` providing comprehensive disclosures and dual-licensing guidance for PyMuPDF and model weights.
- **P0-7 (Untrusted PDF Resource Caps):** Added strict 2048x2048 pixel dimension bounding and byte-size pre-checks in `ocr_fallback.py` to prevent memory explosion during OCR rendering.
- **P0-8 (Local-Mode Egress Sanitization):** Untrusted PDF text or model outputs could contain remote markdown images.
  - *Fix:* Created `ui/sanitizer.py` with `sanitize_display_markdown()` to neutralize remote images and script tags in local mode.

### 2. P1 — Data Integrity & Performance
- **P1-5 (Model-Versioned Summary Cache):** Updated cache lookup in `Summarizer` and `ui/views.py` to pass `model_version=active_model_name` so model upgrades do not serve outdated summaries.
- **P1-6 (Docling Fallback Quality Loss Warning):** Updated `DoclingReader` to track `self.fallback_used = True` and render explicit degradation warnings in the UI.
- **P1 Performance (Batch Page Writes & Region Caching):** Added `doc_store.record_pages_batch(page_records)` for single atomic SQLite transactions and implemented `_region_cache` in `VisualAnalyzer` to eliminate redundant PyMuPDF passes.

### 3. AMOLED Minimal UI Redesign
- **Color Palette & Design Tokens:**
  - Background: `#050608` (AMOLED Black)
  - Surface: `#0C0D12`
  - Elevated Surface: `#14151D`
  - Border: `#252632`
  - Primary Accent: `#B9A3FF` (Restrained Violet)
  - Secondary Accent: `#70D9C2` (Teal for healthy local status)
  - Primary Text: `#F5F3FF`
  - Muted Text: `#9693A6`
- **Iconography & Typography:**
  - 0 emojis in UI.
  - 20 local monochrome SVGs in `assets/icons/` and custom brand mark `assets/brand_mark.svg`.
- **5 Modular Workspaces:**
  1. `Workspace`: Large drag-and-drop upload surface, collection metrics, engine status, and recent documents.
  2. `Ask Documents`: Evidence-grounded chat, document focus filter, clickable citation chips, expandable evidence drawer, token streaming.
  3. `Summarizer`: 5 analytical profiles, section navigation, versioned summary cache lookup, markdown export.
  4. `Document Library`: Lifecycle manager with search/filter, status badges, single-document delete (`doc_store.delete_document` + LanceDB delete), and purge confirmation.
  5. `Settings & Diagnostics`: Privacy mode toggle, cloud consent dialog, hardware telemetry (GPU VRAM gauge, RAM RSS), cache management.
- **Architectural Cleanup:**
  - Refactored `main.py` from 973 lines to ~300 lines.
  - Modularized components into `ui/theme.py`, `ui/components.py`, `ui/views.py`, `ui/hydration.py`, `ui/sanitizer.py`.

### 4. Code Leak Resolution & Chatbot-First Refactor (Current Session)
- **Leaking HTML/Code in Sidebar:** Streamlit treats 4+ space-indented lines inside `st.markdown(unsafe_allow_html=True)` as Markdown `<pre><code>` code blocks, leaking raw `<div>` tags into the UI.
  - *Fix:* Replaced `st.markdown` with `st.html()` / `st.sidebar.html()` in `ui/components.py` and `main.py`, and escaped interpolated labels and filenames using `html.escape()`.
- **Chatbot-First Interface:** Default landing page is now conversational Chat, with documents uploaded and managed directly in the sidebar or via prompt dropzone, suggestion chips ("Summarize thesis", "Extract key tables", "Analyze methodology", "Risks & limitations"), and grounded verifiable citations.
- **`search_hybrid` `TypeError` Resolved:** Added `doc_id: str | list[str] | None = None` to `HybridRetriever.search_hybrid()` and `LocalEmbedding.search_hybrid()`, allowing seamless document filtering during chat retrieval.
- **Visual & Table Evidence Indexed:** Implemented `HybridRetriever.index_evidence_elements()`, converting VLM visual and table descriptions into searchable chunks with `extraction="vlm"` and bbox metadata.
- **Service Layer Extraction:** Extracted `IngestionService` into `ui/ingestion_service.py` with fault isolation, atomic SQLite/LanceDB transactions, and honest failure reporting (no fake "indexed 0 documents" success for empty/unscannable files).
- **Summary Cache Version Key Reconciled:** Replaced plain `ai_model.model_name` with `f"{ai_model.model_name}:{CONFIG_VERSION}"` in `ui/views.py` so cached summaries are properly retrieved from SQLite.
- **Failed Document Retry:** Deleting a failed document now discards its ID from `st.session_state.failed_doc_ids`, enabling clean retries.
- **Streamlit CORS Warning:** Updated `.streamlit/config.toml` to `enableCORS = true` alongside `enableXsrfProtection = true`.

## Verification & Test Results
- `pytest tests/test_hybrid_retriever.py -v`: 17 passed
- `pytest tests/test_main_ui.py -v`: 12 passed
- Full repository test suite: `pytest -q`: **289 passed in 39.11s**
- Linting: `ruff check .` -> clean (0 issues), `ruff format --check .` -> clean (65 files formatted).

