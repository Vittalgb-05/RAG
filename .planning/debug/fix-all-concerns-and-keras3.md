# Debug Session: Fix All CONCERNS.md Items & Keras 3 Import Error

**Session Slug:** `fix-all-concerns-and-keras3`  
**Date:** 2026-10-18  
**Status:** RESOLVED  

---

## 1. Symptoms & Root Causes

1. **Keras 3 / TensorFlow Import Crash (`main.py`):**
   - **Symptom:** `streamlit run main.py` or `python start.py` fails with:
     `ValueError: Your currently installed version of Keras is Keras 3, but this is not yet supported in Transformers.`
   - **Root Cause:** In `main.py`, `docling_reader` and `local_embedding` were imported before setting `USE_TF=0`, allowing `transformers` to detect TensorFlow/Keras 3 at module initialization.
   - **Fix:** Set `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` at the very top of `main.py` and `start.py` before third-party imports, and forward these variables to subprocess environments.

2. **CONCERNS.md Items Addressed:**
   - **Tech Debt:**
     - Extracted `_reset_session_security_state()` helper in `main.py` replacing duplicated ~15-line block in Clear Session and Purge Data.
     - Updated stale `@st.cache_resource` / process-singleton docstrings in `local_llm.py` to document session-scoped lifecycle.
     - Hoisted inline imports (`shutil` in `main.py`; `json`, `math`, `re` in `hybrid_retriever.py`; `EvidenceSnippet` in `local_embedding.py`).
     - Added `DeprecationWarning` to legacy facades (`LocalEmbedding.search_hybrid`, `HybridRetriever.search`/`get_context`).
     - Reconciled documentation claims in `docs/EVALUATION.md`, `README.md`, and `docs/RUNBOOK.md`.
   - **Known Bugs:**
     - Guarded `st.secrets` access in `main.py` with `safe_has_secret` and in `litellm_provider.py` with safe exception handling.
     - Keyed `document_metadata` by `doc_id` instead of filename in `main.py` to prevent filename collisions.
     - Auto-derived content-hash `doc_<sha16>` when `doc_id` is omitted in `docling_reader.py` and `pdf_reader.py`.
   - **Security Considerations:**
     - Disabled LiteLLM telemetry (`os.environ["LITELLM_TELEMETRY"] = "False"`, `litellm.telemetry = False`).
     - Added `num_retries=0` in `litellm_provider.py:stream_text` to eliminate duplicate token emission during streaming.
     - Redacted API key credentials from logs and exception messages via `_scrub_credentials`.
     - Validated and SQL-escaped LanceDB literal filters in `hybrid_retriever.py` (`_escape_sql_literal`).
     - Added `models/`, `*.gguf`, `*.tmp`, `*.onnx` to `.gitignore`.
   - **Fragility:**
     - Added reentrant/thread lock `_ocr_lock` inside `OcrEngine.ocr_page_image` in `ocr_fallback.py` to safeguard `ThreadPoolExecutor` workers.
   - **Test Coverage:**
     - Added `tests/test_groq_provider.py` (7 tests).
     - Added `tests/test_start_launcher.py` (8 tests).

---

## 2. Verification Results

- **Pytest:** 248 / 248 passed (100% pass rate in ~31s across all 24 test files).
- **Ruff:** 0 errors, 0 warnings; 51 files formatted cleanly.
- **Workflow:** `.github/workflows/ci.yml` fully synchronized with lockfile and pytest suite.
- **Startup:** Clean offline startup without Keras 3 / TensorFlow crashes.
