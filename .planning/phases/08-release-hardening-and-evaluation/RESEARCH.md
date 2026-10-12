# Phase 8: Release Hardening & Evaluation — Technical Research

**Target Phase:** Phase 8 (`08-release-hardening-and-evaluation`)  
**Requirements:** `QUAL-02`, `QUAL-03`, `QUAL-04`  
**Date:** 2026-10-12  

---

## 1. Executive Summary & Goals

Phase 8 is the final milestone phase of the Local-First Multimodal PDF Intelligence System roadmap. With canonical data modeling (Phase 1), local VLM inference (Phase 2), Docling layout parsing & RapidOCR (Phase 3), LanceDB persistent hybrid retrieval (Phase 4), grounded summarization & citation verification (Phase 5), 4 GB VRAM performance profiling (Phase 6), and optional LiteLLM cloud privacy controls (Phase 7) fully implemented and verified, Phase 8 hardens the codebase for release.

### Core Objectives
1. **Dependency Pinning & Reproducible Environment (`QUAL-02`):**
   - Pin all runtime dependencies in `requirements.txt` and generate a verified frozen lockfile (`requirements-lock.txt`) to eliminate version drift on both Windows 11 and Ubuntu CI.
   - Verify graceful degradation boundaries for platform-specific dependencies (e.g. LanceDB on Python 3.13 / Windows vs Python 3.11).
2. **Comprehensive Regression Suite & CI/CD Synchronization (`QUAL-02`, `QUAL-04`):**
   - Run and verify the full automated Pytest regression suite (213+ tests across 23 modules) with 100% pass rate.
   - Validate GitHub Actions workflow (`.github/workflows/ci.yml`) enforcing clean `ruff check`, `ruff format --check`, synthetic corpus generation, and test execution.
3. **CONCERNS.md Technical Debt Audit & Resolution (`QUAL-04`):**
   - Resolve standing technical debt identified in `.planning/codebase/CONCERNS.md`:
     - **Telemetry Rerun Overhead:** Throttle/cache `nvidia-smi` subprocess invocations (`resource_telemetry.py` / `main.py`) to eliminate UI thread latency spikes on rapid user interactions.
     - **Provider SSRF Guard:** Enforce loopback validation on `LlamaCppProvider` (`127.0.0.1` / `localhost`) to prevent arbitrary outbound network redirection.
     - **Consent Auditability & Clarification:** Add timestamped session/store audit logs for consent actions, and clarify in the consent notice that retrieved text excerpts transmitted to the cloud will include extracted OCR and visual figure descriptions.
     - **Legacy Artifact Cleanup:** Remove obsolete `cloud_api_key` string legacy writes from `main.py`, and clean up dead/stale test fixtures (`mock_groq_client` in `tests/conftest.py`).
4. **Architecture Documentation & Deployment Runbooks:**
   - Update `README.md` to accurately represent the production multimodal architecture (replacing the initial brownfield 5-file description).
   - Author comprehensive release runbooks (`docs/RUNBOOK.md` and `docs/EVALUATION.md`) detailing Windows RTX 3050 hardware configuration, llama-server setup, benchmarking results, and known limitations.

---

## 2. Technical Research & Architecture Audit

### 2.1 Dependency Pinning & Lockfile Strategy

#### Current Dependency State (`requirements.txt`)
Currently, `requirements.txt` contains 17 lines:
- 6 pinned exact versions: `streamlit==1.42.0`, `pypdf==5.3.0`, `python-dotenv==1.0.1`, `langchain-text-splitters==0.3.6`, `groq==0.15.0`, `sentence-transformers==3.4.1`, `pydantic==2.11.9`.
- 10 open range floors: `numpy>=1.26.0,<3.0.0`, `httpx>=0.28.0`, `docling>=2.0.0`, `rapidocr-onnxruntime>=1.3.0`, `pymupdf>=1.24.0`, `pillow>=10.2.0`, `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `psutil>=6.1.0`, `litellm>=1.50.0`.

#### Recommendation:
- In `requirements.txt`, preserve practical minimum versions while pinning exact tested production releases for high-risk transitive packages (`httpx==0.28.1`, `psutil==6.1.1`, `pydantic==2.11.9`, `pyarrow==23.0.1`).
- Provide an explicit `requirements-lock.txt` generated from the verified working environment, guaranteeing reproducible installation across bare-metal environments and containerized deployments.

---

### 2.2 CONCERNS.md Resolution Inventory

| Concern ID | File:Lines | Description | Proposed Resolution |
|---|---|---|---|
| **TEL-01** | `resource_telemetry.py` / `main.py:508-535` | `get_gpu_memory_info()` spawns `nvidia-smi` on every Streamlit rerun without caching, adding 10-100ms UI latency | Add `@st.cache_data(ttl=5)` or a timestamp-throttled cached probe so `nvidia-smi` executes at most once every 5 seconds. |
| **SEC-01** | `llama_cpp_provider.py:23-45` | `base_url` accepts arbitrary URLs without validation, creating an SSRF primitive if user input reaches provider setup | Validate `base_url`: enforce host is loopback (`127.0.0.1` or `localhost`), or require explicit opt-in flag for remote hosts. |
| **PRIV-01** | `main.py:111-135` | Consent dialog lists "What stays on-device: Extracted text and image OCR", but retrieved excerpts sent in Cloud Mode contain OCR chunks | Update disclosure text in `_render_consent_dialog_content` to clarify that retrieved chunks transmitted during Cloud QA include relevant OCR text and figure summaries. |
| **PRIV-02** | `main.py:67-73, 201` | Legacy `st.session_state.cloud_api_key` string written on every keystroke alongside `cloud_api_keys` dict | Clean up legacy fallback: rely exclusively on `st.session_state.cloud_api_keys[provider_key]`. |
| **TEST-01** | `tests/conftest.py:19-50` | `mock_groq_client` patches `local_llm.Groq`, but `Groq` moved to `groq_provider.py` | Repoint patch to `groq_provider.Groq` or remove dead fixture if unused. |
| **DOC-01** | `README.md` | README describes legacy brownfield prototype (5 files, Groq-only) | Rewrite `README.md` with modern architecture diagrams, multimodal pipeline, local-first privacy guarantees, and usage guide. |
| **DOC-02** | `docs/` | Missing operational runbooks and formal evaluation metrics | Author `docs/RUNBOOK.md` (setup, VRAM tuning, llama-server run commands) and `docs/EVALUATION.md` (benchmark data, test results). |

---

### 2.3 Telemetry Caching Architecture (TEL-01)

Streamlit re-executes `main.py` from top to bottom on every user keystroke or UI interaction. Spawning `nvidia-smi` on every rerun causes unnecessary process creation churn.
Solution:
In `resource_telemetry.py`:
```python
_LAST_GPU_INFO: dict[str, Any] | None = None
_LAST_GPU_SAMPLE_TIME: float = 0.0
_GPU_CACHE_TTL_SECONDS: float = 5.0

def get_gpu_memory_info(force_refresh: bool = False) -> dict[str, Any] | None:
    global _LAST_GPU_INFO, _LAST_GPU_SAMPLE_TIME
    now = time.monotonic()
    if not force_refresh and _LAST_GPU_INFO is not None and (now - _LAST_GPU_SAMPLE_TIME) < _GPU_CACHE_TTL_SECONDS:
        return _LAST_GPU_INFO
    ...
```
This reduces `nvidia-smi` spawns by over 95% during active typing while keeping the VRAM gauge accurate within 5 seconds.

---

### 2.4 SSRF Protection for Local Llama Server (SEC-01)

`LlamaCppProvider` defaults to `http://127.0.0.1:8080`.
To enforce local-only execution and prevent SSRF:
```python
from urllib.parse import urlparse

ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

def _validate_local_endpoint(base_url: str, allow_remote: bool = False) -> None:
    parsed = urlparse(base_url)
    if not allow_remote and parsed.hostname not in ALLOWED_LOCAL_HOSTS:
        raise ValueError(
            f"Restricted endpoint: {base_url} is not a local loopback address. "
            "Local inference must run on 127.0.0.1 or localhost."
        )
```
This hardens `LlamaCppProvider` against arbitrary network egress.

---

### 2.5 Documentation & Runbook Plan

1. **`README.md`:**
   - Visual architecture overview (Docling -> RapidOCR -> LanceDB -> Qwen3-VL 2B / LiteLLM).
   - Quickstart guide (clone, virtualenv, install, run).
   - Offline setup for NVIDIA RTX 3050 Laptop GPU (4 GB VRAM).
   - Privacy guarantees & Cloud Mode opt-in instructions.
   - Comprehensive feature breakdown.
2. **`docs/RUNBOOK.md`:**
   - Step-by-step installation instructions for Windows and Linux.
   - Downloading GGUF models (`qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16.gguf`).
   - Launching `llama-server` with optimized parameters (`-ngl 28`, `-c 4096`).
   - Troubleshooting common issues (CUDA OOM, port conflicts, missing OCR dependencies).
3. **`docs/EVALUATION.md`:**
   - Summary of the 213+ automated test cases.
   - Performance benchmarks:
     - Extraction throughput (Docling vs pypdf).
     - Hybrid retrieval latency (< 50ms warm cache).
     - Citation verification precision (≥ 95% target satisfied).
     - VRAM envelope breakdown on RTX 3050.

---

## 3. Plan Decomposition for Phase 8

Phase 8 will be decomposed into two distinct, high-impact plans:

- **Plan 08-01: Regression Suite Verification, Security Hardening & Dependency Pinning (`QUAL-02`, `QUAL-04`)**
  - Implement telemetry TTL caching in `resource_telemetry.py` (TEL-01).
  - Implement loopback URL validation in `llama_cpp_provider.py` (SEC-01).
  - Update consent notification disclosure in `main.py` (PRIV-01) and clean up legacy `cloud_api_key` (PRIV-02).
  - Clean up test fixtures in `tests/conftest.py` (TEST-01).
  - Generate frozen `requirements-lock.txt` and finalize `requirements.txt`.
  - Execute full regression test suite with 100% pass rate.
  - Verify `.github/workflows/ci.yml` passes clean.

- **Plan 08-02: CONCERNS.md Final Audit, Documentation Modernization & Runbooks (`QUAL-03`, `QUAL-04`)**
  - Rewrite `README.md` to reflect the complete production architecture.
  - Author `docs/RUNBOOK.md` (installation, GPU setup, troubleshooting).
  - Author `docs/EVALUATION.md` (test report, benchmark verification, limitations).
  - Update `.planning/codebase/CONCERNS.md` marking resolved technical debt items.
  - Update `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` reflecting completed v1 requirements.
