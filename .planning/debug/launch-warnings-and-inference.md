---
status: resolved
trigger: |
  C:\Users\OM Prakash\Documents\RAG>python start.py
  ====================================================================
    Local-First Multimodal PDF Intelligence System
    Hybrid Search - RapidOCR - Docling - Qwen3-VL 2B - Verifiable Citations
  ====================================================================
    Local llama-server not detected at http://127.0.0.1:8080
       The UI will launch in local offline mode (or user-consented cloud mode).
       To launch llama-server, run: llama-server -m models/... --mmproj models/... --port 8080

  Launching Streamlit web application on http://localhost:8501 ...
     Press Ctrl+C to stop the server.

  warning: The `fitz` API is deprecated and will be removed in future. Use `import pymupdf` instead.
  2026-10-18 00:55:37.527 Examining the path of torch.classes raised:
  Traceback (most recent call last):
    File ".../streamlit/watcher/local_sources_watcher.py", line 217, in get_module_paths
      potential_paths = extract_paths(module)
    File ".../streamlit/watcher/local_sources_watcher.py", line 210, in <lambda>
      lambda m: list(m.__path__._path),
    File ".../torch/_classes.py", line 13, in __getattr__
      proxy = torch._C._get_custom_class_python_wrapper(self.name, attr)
  RuntimeError: Tried to instantiate class '__path__._path', but it does not exist! Ensure that it is registered via torch::class_

  UI banner observed: "Warning icon Inference: Offline (setup required)"
  "Cannot connect to llama-server at http://127.0.0.1:8080. Start it with:
   llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port 8080"
created: 2026-10-18
updated: 2026-10-18
---

# Debug Session: Launch Warnings and Offline Inference

**Session Slug:** `launch-warnings-and-inference`

## Symptoms

**Expected behavior:**
- `python start.py` launches the Streamlit app without noisy console tracebacks.
- The app reports a usable inference backend (local llama-server when the model is available), so summarization / Q&A / visual analysis work end-to-end.

**Actual behavior:**
- Two startup warnings appear on every launch:
  1. `fitz` API deprecation warning ("Use `import pymupdf` instead").
  2. Streamlit file-watcher traceback: `RuntimeError: Tried to instantiate class '__path__._path', but it does not exist!` raised while examining `torch.classes`.
- The UI shows `Warning icon Inference: Offline (setup required)` and a message that llama-server at `http://127.0.0.1:8080` is unreachable, so local inference features cannot run.

**Error messages:**
- `warning: The 'fitz' API is deprecated and will be removed in future. Use 'import pymupdf' instead.`
- `RuntimeError: Tried to instantiate class '__path__._path', but it does not exist! Ensure that it is registered via torch::class_` (origin: `streamlit/watcher/local_sources_watcher.py:210-217` -> `torch/_classes.py:13`).
- `Cannot connect to llama-server at http://127.0.0.1:8080` / `Inference: Offline (setup required)`.

**Timeline:**
- The `torch.classes` traceback has appeared since the project began (always happened) and on every launch.
- Inference-offline state is present because no llama-server process is running at `127.0.0.1:8080`.

**Reproduction:**
- Run `python start.py` from the repo root on Windows (Python 3.13). Warnings appear at startup; the offline-inference banner appears in the Streamlit UI.

## Current Focus

- hypothesis: (resolved)
- test: (resolved)
- expecting: (resolved)
- next_action: none — session resolved
- reasoning_checkpoint: (none)

## Evidence

- timestamp: 2026-10-18 — `grep` located the legacy import in exactly two modules: `ocr_fallback.py:30` and `visual_analyzer.py:18` (`import fitz  # PyMuPDF`). No other `fitz` usage in application code (`tests/test_visual_analyzer.py:287` only *simulates* a fitz shim).
- timestamp: 2026-10-18 — Installed PyMuPDF is `1.28.2` on Python `3.13.5`. Reproduced the warning directly: `python -c "import fitz"` prints `warning: The `fitz` API is deprecated...`. Confirmed source: `site-packages/fitz/__init__.py` ends with `message_warning('The `fitz` API is deprecated...')` — i.e. a **stderr print**, not a `warnings.warn`, so `filterwarnings` cannot suppress it; only avoiding the import will.
- timestamp: 2026-10-18 — Verified the modern replacement binds identical symbols with no warning: `python -c "import pymupdf as fitz; print(fitz.Rect, fitz.Matrix, fitz.open)"` → `pymupdf.Rect`, `pymupdf.Matrix`, `pymupdf.Document`, exit clean.
- timestamp: 2026-10-18 — `streamlit/watcher/local_sources_watcher.py` (Streamlit `1.42.0`): `get_module_paths()` probes each imported module via `lambda m: list(m.__path__._path)` (line 210). `torch/_classes.py:13` defines a module-level `__getattr__` that raises `RuntimeError` for unknown attributes, so the preceding `except AttributeError` (line 218) does **not** catch it. The `except Exception` at line 221 catches it and only calls `_LOGGER.warning(..., exc_info=True)` → the app continues normally. The traceback is therefore **benign/cosmetic**, not a crash.
- timestamp: 2026-10-18 — Confirmed no module-level exclusion hook exists for the scan (`server.folderWatchBlacklist` filters file *paths* only, applied after `get_module_paths`), so the only non-invasive fixes are quieting that logger or disabling the watcher.
- timestamp: 2026-10-18 — `streamlit/logger.py:get_logger()` calls `logger.setLevel(_global_log_level)` on first creation, so a `Logger.setLevel(ERROR)` applied before the watcher module is imported gets clobbered. A `logging.Filter` is not reset this way — chose the filter approach.
- timestamp: 2026-10-18 — Offline inference: `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (986 MB) and `models/mmproj-f16.gguf` (1.33 GB) **are present**. `command -v llama-server` → not found; `connect_ex(('127.0.0.1', 8080))` → closed. `start.py:check_llama_server` and `llama_cpp_provider.check_health` correctly report unreachable; model name in code (`qwen3-vl-2b` → `models/qwen3-vl-2b-instruct-q4_k_m.gguf`) matches the file on disk.

## Eliminated

- hypothesis: The torch.classes traceback is an unhandled crash masking a functional bug — ELIMINATED. It is caught by `except Exception` in Streamlit and logged at WARNING; the app and file watcher keep working.
- hypothesis: The offline banner is caused by a code defect in health/provider selection — ELIMINATED. The health check probes the correct endpoint and correctly reports "unreachable"; the root cause is environmental (llama-server not installed/running).
- hypothesis: The model filenames referenced by code/docs are wrong — ELIMINATED. Code, docs, and on-disk filenames agree on `qwen3-vl-2b-instruct-q4_k_m.gguf` / `mmproj-f16.gguf`.
- hypothesis: `filterwarnings`/a warnings filter could hide the fitz message — ELIMINATED. It is a `message_warning` stderr print, not a `warnings.warn`.
- hypothesis: `Logger.setLevel(ERROR)` on the watcher logger is a stable fix — ELIMINATED. Streamlit's `get_logger` resets the level on module import.

## Resolution

- root_cause: |
    1. **fitz deprecation (cosmetic, code defect):** `ocr_fallback.py` and `visual_analyzer.py` imported the legacy `fitz` shim; PyMuPDF 1.24+ prints a deprecation warning to stderr on that import.
    2. **torch.classes traceback (cosmetic, upstream Streamlit/torch interaction):** Streamlit's startup module scan probes `torch.classes.__path__._path`; `torch.classes` raises `RuntimeError` (not `AttributeError`) when probed, so Streamlit logs a benign traceback it already caught.
    3. **Offline inference (environment, NOT a code defect):** the `llama-server` binary is not installed/on PATH and no server is listening on `127.0.0.1:8080`; model weights are present. The UI's "Offline (setup required)" banner is correct behaviour.
- fix: |
    1. Replaced `import fitz` with `import pymupdf as fitz` in `ocr_fallback.py` and `visual_analyzer.py` (keeps the `fitz` local alias so all call sites and the `monkeypatch.setattr("visual_analyzer.fitz", ...)` test seam are unchanged, but never imports the deprecated shim).
    2. Added `logging_setup.py` with `TorchClassesScanLogFilter` (drops only messages containing `torch.classes`) and `suppress_torch_classes_scan_warning()` (idempotent installer). `main.py` calls it at import; the Streamlit file watcher and every other log record are left untouched.
    3. No code change — environment remediation: install `llama-server` (llama.cpp) and launch it per `docs/LOCAL_INFERENCE.md` §4, e.g. `llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port 8080`. (Documentation nit, out of scope: `docs/RUNBOOK.md:89,103-106` still labels the model "Qwen2-VL" and links the Qwen2-VL HF repo while downloading to the `qwen3` filename.)
- verification: |
    - `python -m ruff check .` → All checks passed.
    - `python -m pytest -q` → 254 passed (full suite, incl. new regression tests).
    - New tests: `tests/test_logging_setup.py` (filter drops the torch.classes record, passes unrelated records, installer is idempotent, and an end-to-end check that `get_module_paths(torch.classes)` emits no warning while a legitimate warning still flows); `tests/test_visual_analyzer.py::test_visual_analyzer_uses_modern_pymupdf_import` and `tests/test_ocr_fallback.py::test_ocr_fallback_uses_modern_pymupdf_import` assert each module's `fitz` alias is the `pymupdf` module.
    - Watcher simulation over all 8387 loaded modules after importing `main`: **0** `torch.classes` traceback records with the filter installed vs **1** with filters cleared — proves the filter is the operative fix.
    - `python -c "import main"` (and importing the two modules directly) emits **0** `fitz`/`deprecated` lines.
    - Environment check: models present; `llama-server` absent from PATH; port 8080 closed → confirms symptom 3 is setup, not code.
- files_changed: |
    ocr_fallback.py, visual_analyzer.py, main.py, logging_setup.py (new), tests/test_logging_setup.py (new), tests/test_visual_analyzer.py, tests/test_ocr_fallback.py
