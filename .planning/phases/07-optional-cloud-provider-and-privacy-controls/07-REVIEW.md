---
phase: 07-optional-cloud-provider-and-privacy-controls
reviewed: 2026-10-12T21:55:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - litellm_provider.py
  - local_llm.py
  - main.py
  - requirements.txt
  - tests/test_litellm_provider.py
  - tests/test_cloud_privacy.py
  - tests/test_local_llm.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: resolved
verdict: PASSED (FIXED)
---

# Phase 7 (07-optional-cloud-provider-and-privacy-controls) — Code Review Report

**Reviewed:** 2026-10-12  
**Depth:** standard (per-file Python analysis + cross-file tracing + privacy invariant audit)  
**Files Reviewed:** 7 (litellm_provider.py, local_llm.py, main.py, requirements.txt, tests/test_litellm_provider.py, tests/test_cloud_privacy.py, tests/test_local_llm.py)  
**Verdict:** NEEDS FIXES  
**Status:** issues_found  

## Summary

Reviewed all Phase 7 new and modified source files and unit tests against the two PLAN intents:
1. `07-01-PLAN.md`: Unified cloud adapter (`litellm_provider.py`) across Groq, OpenAI, and Anthropic with programmatic consent gating (`INF-04`) and elimination of silent cloud fallback in `AiModel._detect_provider()`.
2. `07-02-PLAN.md`: Streamlit UI privacy controls (`main.py`), explicit consent dialog (`@st.dialog`), dynamic credential handling, and transparent egress indicators (`UI-04`, `INF-03`).

The core architecture cleanly implements `BaseModelProvider(ABC)` with bounded retries and timeouts, and eliminates silent fallback. However, a deep cross-file trace revealed **1 Critical** privacy issue where document image crops were transmitted to cloud vision models during document upload if Cloud Mode was active (violating `INF-03`), **3 Warnings** regarding shared API key pollution across providers, connection pool churn in `set_cloud_mode`, and widget state synchronization in the consent modal, plus **2 Info** items regarding MIME type sniffing and regression test coverage.

## Severity Counts

- Critical: 1
- Warning: 3
- Info: 2
- Total: 6

## Findings Table

| ID | Severity | File:Line | Category | Description |
|---|---|---|---|---|
| CR-01 | Critical | main.py:377-383 | Privacy / Egress Invariant | VisualAnalyzer during PDF ingestion receives active cloud provider when Cloud Mode is on, transmitting raw image crops across network during upload (violating INF-03) |
| WR-01 | Warning | main.py:185-194 | State / Security | `st.session_state.cloud_api_key` shared globally across providers; switching from Groq to OpenAI transmits Groq key to OpenAI API |
| WR-02 | Warning | local_llm.py:139-153 & main.py:210-218 | Performance / Architecture | `set_cloud_mode` closes and reinstantiates provider on every rerun without change check, thrashing HTTP connection pools |
| WR-03 | Warning | main.py:143-154 | UI State Machine | `st.toggle` missing explicit widget key; cancelling or dismissing dialog leaves toggle ON in client widget tree |
| IN-01 | Info | litellm_provider.py:287-297 | Compatibility / API Contract | `analyze_image` hardcodes `image/png` data URI; JPEG/WebP bytes sent to Anthropic API risk HTTP 400 rejection |
| IN-02 | Info | tests/test_cloud_privacy.py | Test Coverage | Ingestion privacy test lacks assertion that VisualAnalyzer never routes to cloud during document upload |

---

## Critical Issues

### CR-01: VisualAnalyzer during PDF upload transmits image crops to cloud when Cloud Mode is active (INF-03)

**File:** `main.py:377-383`  
**Issue:**
```python
visual_analyzer = VisualAnalyzer()
current_model = getattr(st.session_state, "ai_model", None) or ai_model
active_provider = current_model.provider if current_model is not None else None
evidence_elements = visual_analyzer.analyze_visual_elements(
    pdf_bytes=raw_bytes,
    doc_id=doc_id,
    provider=active_provider,
)
```
When Cloud Mode is enabled with a vision-supported model (`openai/gpt-4o-mini` or `anthropic/claude-3-5-haiku`), `current_model.provider.get_capabilities().supports_vision` is `True`. During PDF upload processing in the sidebar, `visual_analyzer.analyze_visual_elements` passes `active_provider` to `provider.analyze_image(...)`.
This transmits cropped images of charts, diagrams, and figures over the public network to external cloud APIs during document ingestion.
This violates requirement `INF-03` ("Ingestion, conditional OCR, embeddings, and LanceDB hybrid retrieval remain 100% on-device (zero network egress)") and directly contradicts the explicit consent prompt presented to the user ("What stays 100% on your device: Original PDF document files, rendered page images & conditional OCR").

**Fix:**
Ingestion visual analysis must only ever execute against a local provider. If `current_model.provider` is not local (`not provider.get_capabilities().is_local`), pass `provider=None` to `visual_analyzer.analyze_visual_elements`:
```python
local_vlm_provider = (
    active_provider
    if (active_provider is not None and active_provider.get_capabilities().is_local)
    else None
)
evidence_elements = visual_analyzer.analyze_visual_elements(
    pdf_bytes=raw_bytes,
    doc_id=doc_id,
    provider=local_vlm_provider,
)
```

---

## Warnings

### WR-01: Shared `cloud_api_key` state sends mismatched API key when switching cloud providers

**File:** `main.py:185-194`  
**Issue:**
`st.session_state.cloud_api_key` is a single string. When a user inputs a Groq API key (`gsk_...`) and then switches the provider selectbox to OpenAI, `st.session_state.cloud_api_key` still contains the Groq key. On the next rerun, `LiteLLMProvider(model_name="openai/gpt-4o-mini", api_key="gsk_...")` is constructed with the Groq key, causing OpenAI API calls to fail with authentication errors.

**Fix:**
Store session keys in a per-provider dictionary `st.session_state.cloud_api_keys: dict[str, str] = {"groq": "", "openai": "", "anthropic": ""}` and index by `selected_provider_key`.

### WR-02: `set_cloud_mode` runs unconditionally on every rerun, thrashing HTTP connection pools

**File:** `local_llm.py:139-153` & `main.py:210-218`  
**Issue:**
On every Streamlit rerun, `ai_model.set_cloud_mode(...)` is invoked. `set_cloud_mode` unconditionally calls `self.close()` and `self._detect_provider()`, creating new `httpx.Client()` instances and discarding open HTTP connection pools on every user click.

**Fix:**
Add a state change check in `AiModel.set_cloud_mode`: if already in the target mode and the provider instance has not changed, return early as a no-op. In `main.py`, cache `st.session_state.active_cloud_provider` and only construct a new instance when model or API key changes.

### WR-03: `st.toggle` missing widget key allows modal re-trigger on dismiss

**File:** `main.py:143-154`  
**Issue:**
`st.toggle("Enable Cloud Inference", value=st.session_state.cloud_mode)` lacks a `key` parameter. If the user cancels or dismisses the consent modal without consenting, Streamlit's client widget state can retain `True`, re-triggering the consent modal on the subsequent rerun.

**Fix:**
Add `key="cloud_mode_toggle"` and explicitly set `st.session_state.cloud_mode_toggle = False` when the user cancels or dismisses without granting consent.

---

## Info Items

### IN-01: `LiteLLMProvider.analyze_image` hardcodes `data:image/png` media type

**File:** `litellm_provider.py:287-297`  
**Issue:**
`analyze_image` hardcodes `data:image/png;base64,...` regardless of whether `image_bytes` are JPEG or PNG. Strict APIs (specifically Anthropic Claude) inspect image magic bytes and reject requests with mismatched media types (`invalid_request_error: media_type must match image content`).

**Fix:**
Sniff the image magic bytes (`b'\xff\xd8'` -> `image/jpeg`, `b'RIFF'...b'WEBP'` -> `image/webp`, else `image/png`) to supply the exact MIME type.

### IN-02: Unit tests lack explicit check for visual analyzer local-only isolation during ingestion

**File:** `tests/test_cloud_privacy.py`  
**Issue:**
While embedding and vector search were verified for zero network egress, `VisualAnalyzer` was not explicitly verified to confirm it skips cloud calls during document ingestion when Cloud Mode is enabled.

**Fix:**
Add a dedicated test `test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` to `tests/test_cloud_privacy.py`.
