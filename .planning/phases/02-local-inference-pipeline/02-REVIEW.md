---
phase: 02-local-inference-pipeline
reviewed: 2026-10-11T13:55:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - model_provider.py
  - llama_cpp_provider.py
  - groq_provider.py
  - prompt_budget.py
  - local_llm.py
  - main.py
  - docs/LOCAL_INFERENCE.md
  - requirements.txt
  - tests/conftest.py
  - tests/test_model_provider.py
  - tests/test_llama_cpp_provider.py
  - tests/test_prompt_budget.py
  - tests/test_local_llm.py
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
verdict: NEEDS FIXES
---

# Phase 02: Code Review Report — Local Inference Pipeline

**Reviewed:** 2026-10-11T13:55:00Z  
**Depth:** standard (per-file analysis, security, lifecycle, concurrency, error boundaries)  
**Files Reviewed:** 11 core phase files + test suites  
**Verdict:** NEEDS FIXES (3 Critical issues, 6 Warnings, 3 Info items)

---

## Summary

Phase 2 successfully delivers the core provider abstraction (`BaseModelProvider`), local HTTP streaming client (`LlamaCppProvider`), token budgeting with XML tags, and Streamlit UI health integration with 85 passing tests and 0 ruff errors.

However, an adversarial audit revealed 3 Critical vulnerabilities and 6 Warnings that must be resolved:
1. **CR-01**: Document context XML boundary escaping gap allowing malicious PDFs with literal `</document_context>` to break isolation and execute prompt injection.
2. **CR-02**: User prompt context overflow gap where long user queries bypass budgeting and overflow model context capacity.
3. **CR-03**: Unguarded `st.write_stream` in `main.py` causing full UI crash if streaming connection drops mid-generation.
4. **WR-01 through WR-06**: Stale provider cache lock-in, missing polymorphic `close()`, unhandled Groq SDK exceptions, empty image payload validation, and duplicate health probe latency.

---

## Critical Issues

### CR-01: Prompt Injection XML Boundary Escape via Unsanitized Document Context
- **File:** `prompt_budget.py:66-75`
- **Category:** Security (Prompt Injection / Isolation Boundary)
- **Issue:** `assemble_grounded_messages` inserts `context_text` directly into `<document_context>{context_text}</document_context>`. If a malicious PDF contains the literal sequence `</document_context>`, it terminates the XML delimiter prematurely, allowing adversarial text to inject instructions as if they were top-level system commands.
- **Fix:** Sanitize `context_text` by replacing `<document_context>` and `</document_context>` with escaped tokens (`&lt;document_context&gt;` and `&lt;/document_context&gt;`) prior to formatting into the template.

### CR-02: User Prompt Context Window Overflow Hazard
- **File:** `prompt_budget.py:53-98`, `local_llm.py:118`
- **Category:** Robustness (Bounded Context Violation)
- **Issue:** While document context and history are bounded, `prompt` itself is never length-checked or truncated against `total_input_budget`. A large user prompt (e.g. pasted text > 4,000 tokens) causes `llama-server` to return HTTP 400 Bad Request or CUDA out of memory. Additionally, `AiModel` passes raw `prompt` to `stream_text` rather than the bounded user turn produced by `assemble_grounded_messages`.
- **Fix:** Truncate user prompt to fit within `total_input_budget - base_system_tokens`, and pass the bounded/sanitized prompt to the provider.

### CR-03: Unguarded `st.write_stream` Aborts Entire Streamlit Session on Mid-Stream Network Drops
- **File:** `main.py:364`
- **Category:** Reliability (Unhandled Runtime Exception)
- **Issue:** `full_response = st.write_stream(response_stream)` is executed without exception handling. If `llama-server` crashes, disconnects, or errors mid-stream, `RuntimeError` terminates the Streamlit rerun with an unhandled exception page.
- **Fix:** Wrap `st.write_stream` in `try/except Exception as err:`, display `st.error(...)`, and avoid crashing the browser session.

---

## Warnings

### WR-01: Stale Provider Lock-in Under `@st.cache_resource`
- **File:** `local_llm.py:35-56`, `main.py:88`
- **Category:** Lifecycle / UX
- **Issue:** If Streamlit starts when `llama-server` is offline, `AiModel` caches the initial state. When the user starts `llama-server` afterwards, `AiModel` remains stuck in the fallback or unreachable state unless re-probed.
- **Fix:** If the current provider is not healthy, `AiModel.check_health()` should re-run `_detect_provider()` so starting `llama-server` dynamically self-heals.

### WR-02: Missing Polymorphic `close()` Lifecycle on `BaseModelProvider`
- **File:** `model_provider.py:59`, `groq_provider.py:18`, `local_llm.py:17`
- **Category:** Resource Management
- **Issue:** `LlamaCppProvider` provides `close()`, but `BaseModelProvider` lacks a `close()` contract and `AiModel` does not implement cleanup. Consumers cannot close HTTP clients polymorphically.
- **Fix:** Add `close(self) -> None: pass` and context manager methods to `BaseModelProvider`, and implement `close()` on `AiModel`.

### WR-03: Uncaught Groq SDK API Errors Violate Error Encapsulation Contract
- **File:** `groq_provider.py:110, 138`
- **Category:** Error Boundaries
- **Issue:** `groq_client.chat.completions.create` calls are not wrapped in `try/except`, leaking `groq.APIError` directly to callers instead of standard `RuntimeError`.
- **Fix:** Wrap Groq SDK invocations in `try/except Exception as exc:` and raise `RuntimeError(f"Groq API error: {exc}") from exc`.

### WR-04: Lack of Field Constraints on `ProviderCapabilities`
- **File:** `model_provider.py:20-24`
- **Category:** Schema Validation
- **Issue:** `model_name` allows empty strings `""` and `context_window` allows non-positive integers `<= 0`.
- **Fix:** Add `min_length=1` to `model_name` and `gt=0` to `context_window`.

### WR-05: Redundant Dual Health Check Latency on Streamlit Reruns
- **File:** `main.py:89, 322`
- **Category:** Performance
- **Issue:** `ai_model.check_health()` is called twice per script execution (once in the sidebar and once for chat input disabling).
- **Fix:** Reuse the health status evaluated during sidebar loading.

### WR-06: `image_bytes` Empty Validation Gap in `analyze_image`
- **File:** `llama_cpp_provider.py:221`
- **Category:** Input Validation
- **Issue:** Passing empty bytes `b""` encodes to `""` and sends an invalid payload to `llama-server`.
- **Fix:** Check `if not image_bytes: raise ValueError("image_bytes cannot be empty")`.

---

## Info Items

### IN-01: Redundant Whitespace in Health Check Diagnostic String
- **File:** `llama_cpp_provider.py:91`
- Clean up multi-line f-string formatting.

### IN-02: Type Guard for `chat_history` String Elements
- **File:** `local_llm.py:100`
- Guard `isinstance(m.get("content"), str)` when formatting search query.

### IN-03: Explicit Temperature Clamping
- **File:** `llama_cpp_provider.py:146`, `groq_provider.py:114`
- Ensure `temperature` is clamped between `0.0` and `2.0`.

---

## Per-File Audit Summary

- **model_provider.py**: Needs `close()` interface and schema validation constraints (WR-02, WR-04).
- **llama_cpp_provider.py**: Needs empty image guard (WR-06) and temperature sanity check (IN-03).
- **groq_provider.py**: Needs error encapsulation (WR-03) and polymorphic `close()` (WR-02).
- **prompt_budget.py**: Needs XML tag escaping (CR-01) and prompt length budgeting (CR-02).
- **local_llm.py**: Needs dynamic re-probing on unhealthy state (WR-01), bounded prompt passing (CR-02), and chat content type guard (IN-02).
- **main.py**: Needs `st.write_stream` try/except wrapper (CR-03) and shared health check caching (WR-05).
