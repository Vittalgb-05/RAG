# Debug Session: Setup Packaging, Model Download & Codebase Concerns Resolution

**Session Slug:** `setup-dependencies-models-and-concerns`  
**Date:** 2026-10-14  
**Status:** RESOLVED  

---

## 1. Objectives & Scope

1. **`setup.py` Enhancement:**
   - Ensure `setup.py` can set up all dependencies (via `pip` or setuptools) and download all required models:
     - Qwen2-VL-2B Instruct GGUF (`qwen3-vl-2b-instruct-q4_k_m.gguf`)
     - Multimodal projector adapter GGUF (`mmproj-f16.gguf`)
     - Pre-cache SentenceTransformers embedding model (`all-MiniLM-L6-v2`) in local HuggingFace cache.
     - Pre-cache RapidOCR ONNX models.
   - Support both direct execution (`python setup.py`, `python setup.py setup`, `python setup.py download_models`) and standard setuptools command `python setup.py download_models`.

2. **Fix All Concerns in `.planning/codebase/CONCERNS.md`:**
   - **Tech Debt 1:** Analytical vs. Resident Model VRAM Measurement: Enhance `resource_telemetry.py` and `scripts/profile_resources.py` with `nvidia-smi --query-compute-apps` live sampling for running `llama-server`.
   - **Tech Debt 2:** Legacy `cloud_api_key` Fallback in Session State: Remove `cloud_api_key` string fallback from `main.py` and `litellm_provider.py`; enforce `cloud_api_keys` dictionary exclusively.
   - **Tech Debt 3:** Direct `PdfReader` Ingestion Path in `local_llm.py`: Remove unindexed standalone `PdfReader` fallback branch in `AiModel.ask_a_question_from_pdf_stream`; require an indexed retriever or explicit `RetrievalResult`.
   - **Security 1:** SSRF Guard on Local Llama Server: Ensure `allow_remote` cannot be bypassed by untrusted input.
   - **Security 2:** Prompt Injection Output-Side Validation: Implement output validation in `citation_validator.py` to detect if assistant responses echo adversarial injection directives.
   - **Performance Bottleneck 1:** Scanned Page OCR: Add multi-threaded batch OCR processing via `ThreadPoolExecutor` in `ocr_fallback.py`.
   - **Performance Bottleneck 3:** First-Run Embedding Model Download: Automated via `setup.py` pre-caching.

---

## 2. Investigation & Action Plan

- [x] Inspect existing `setup.py`, `local_llm.py`, `litellm_provider.py`, `main.py`, `resource_telemetry.py`, `scripts/profile_resources.py`, `citation_validator.py`, and `ocr_fallback.py`.
- [x] Implement enhanced `setup.py` with dependency installer, model downloader, and `DownloadModelsCommand`.
- [x] Implement live compute apps VRAM telemetry in `resource_telemetry.py` and integrate with `scripts/profile_resources.py`.
- [x] Remove legacy `cloud_api_key` fallback in `litellm_provider.py` and `main.py`; update corresponding tests.
- [x] Remove unindexed direct `PdfReader` branch in `local_llm.py`; update tests.
- [x] Implement output-side prompt injection detection in `citation_validator.py` and test suite.
- [x] Implement multi-threaded OCR batching in `ocr_fallback.py` and verify test suite.
- [x] Update `CONCERNS.md` and `docs/RUNBOOK.md`.
- [x] Run Ruff and Pytest across the entire test suite.
- [x] Propose descriptive commit.

---

## 3. Resolution & Verification Summary

1. **`setup.py` & Model Acquisition:**
   - Enhanced `setup.py` with:
     - Streaming downloads with fallback mirrors for `qwen3-vl-2b-instruct-q4_k_m.gguf` and `mmproj-f16.gguf`.
     - Automatic pre-caching of `all-MiniLM-L6-v2` (`precache_embedding_model`) and RapidOCR ONNX models (`precache_ocr_model`).
     - Setuptools `DownloadModelsCommand` (`python setup.py download_models`) with `--models-dir`, `--force`, and `--skip-vlm` options.
     - Direct execution workflows: `python setup.py`, `python setup.py setup`, `--deps-only`, `--models-only`.

2. **Codebase Concerns Addressed:**
   - **Tech Debt 1:** Added `get_compute_apps_gpu_memory()` and `get_resident_model_gpu_memory()` to `resource_telemetry.py` querying `nvidia-smi --query-compute-apps`; integrated with `scripts/profile_resources.py`.
   - **Tech Debt 2:** Stripped legacy `cloud_api_key` fallback; enforced provider-scoped `cloud_api_keys` dictionary in `main.py`, `litellm_provider.py`, and test fixtures.
   - **Tech Debt 3:** Removed unindexed direct `PdfReader` branch in `local_llm.py`; caller must provide an indexed retriever or explicit `RetrievalResult`.
   - **Security 1:** Enforced strict loopback host validation in `llama_cpp_provider.py` preventing SSRF bypass.
   - **Security 2:** Added output-side prompt injection detection in `citation_validator.py` (`detect_adversarial_injection`, `KNOWN_ADVERSARIAL_DIRECTIVES`), rejecting echoed adversarial directives with `injection_detected=True`.
   - **Performance Bottleneck 1:** Multi-threaded OCR batching via `ThreadPoolExecutor` in `ocr_fallback.py` for multi-page documents while maintaining exact page ordering and fault isolation.
   - **Performance Bottleneck 3:** Embedding and OCR weights pre-caching automated via `setup.py`.

3. **Verification:**
   - Lint & Format: `ruff check .` (All checks passed) & `ruff format --check .` (All 49 files formatted).
   - Test Suite: All 233 automated test cases passing in 28.8s (`pytest tests/`).
   - GitHub Workflows: Verified `.github/workflows/ci.yml` is in sync with project structure and passes.

