# Debug Session: Python 3.13 rapidocr-onnxruntime Dependency Setup Failure

**Session Slug:** `python-313-rapidocr-setup`  
**Date:** 2026-10-17  
**Status:** RESOLVED  

---

## 1. Symptoms & Initial Context

- **Trigger:** Running `python setup.py` on Windows using Python 3.13 (`Python313`).
- **Expected:** `python setup.py` installs dependencies cleanly or gracefully skips incompatible optional dependencies on Python 3.13+.
- **Actual:** `pip install -r requirements.txt` and `pip install -e .` fail with:
  ```text
  ERROR: Ignored the following versions that require a different python version: ... 1.4.4 Requires-Python >=3.6,<3.13
  ERROR: Could not find a version that satisfies the requirement rapidocr-onnxruntime>=1.3.0
  ERROR: No matching distribution found for rapidocr-onnxruntime>=1.3.0
  ```
- **Root Cause:** `rapidocr-onnxruntime` on PyPI explicitly specifies `Requires-Python >=3.6,<3.13` for all versions >= 1.3.0 up to 1.4.4. When running on Python 3.13, pip rejects all versions. Because `rapidocr-onnxruntime` is an optional fallback (gracefully handled via try/except in `ocr_fallback.py` and `setup.py`), it must be conditioned with PEP 508 environment markers `rapidocr-onnxruntime>=1.3.0; python_version < '3.13'`.
- **Secondary Issues Identified & Fixed:**
  1. Windows console `cp1252` encoding error when printing Unicode checkmarks/emojis in `setup.py` (`UnicodeEncodeError: 'charmap' codec can't encode character '\u2713'`). Resolved by reconfiguring `sys.stdout` and `sys.stderr` to `encoding='utf-8', errors='replace'`.
  2. Direct CLI flags (`--deps-only`, `--models-only`, `download_models`) passed to `python setup.py` were rejected by setuptools. Resolved by inspecting `raw_args` for custom sub-commands and flags in `setup.py`.
  3. Keras 3 deprecation warning during SentenceTransformer pre-caching when TensorFlow is installed. Resolved by configuring `os.environ.setdefault("USE_TF", "0")` and `os.environ.setdefault("USE_TORCH", "1")` in `setup.py` and `local_embedding.py`.
  4. Added `rapidocr` import fallback in `ocr_fallback.py` and `setup.py` for environments running on Python 3.13+ where docling installs `rapidocr>=3.10.0`.

---

## 2. Action Plan

- [x] Verify PEP 508 environment marker compatibility in `requirements.txt` and `setup.py`.
- [x] Update `requirements.txt` to: `rapidocr-onnxruntime>=1.3.0; python_version < '3.13'`.
- [x] Add UTF-8 console reconfiguration in `setup.py` to prevent `cp1252` `UnicodeEncodeError`.
- [x] Enhance CLI dispatch in `setup.py` to support `--deps-only`, `--models-only`, `download_models`, and full setup directly.
- [x] Set `USE_TF=0` and `USE_TORCH=1` in `setup.py` and `local_embedding.py`.
- [x] Add fallback from `rapidocr_onnxruntime` to `rapidocr` in `ocr_fallback.py` and `setup.py`.
- [x] Test `pip install -r requirements.txt` on Python 3.13.
- [x] Test `python setup.py --deps-only`, `python setup.py --models-only`, and full `python setup.py`.
- [x] Run test suite (`pytest`) to verify all 233 tests pass.
- [x] Run Ruff lint and format check (all 49 files clean).
- [x] Propose descriptive commit and push to remote.
