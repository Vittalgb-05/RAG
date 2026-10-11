# Phase 2: Local Inference Pipeline — Verification Report

**Phase Goal**: Establish a robust local inference foundation using `llama-server` (llama.cpp) running Qwen3-VL 2B GGUF within a 4 GB VRAM budget (RTX 3050 Laptop GPU), offering unified provider abstraction (`BaseModelProvider`), SSE token streaming, prompt injection isolation, bounded context budgeting (4K tokens), and non-crashing UI health feedback.

---

## 1. Requirements Compliance Matrix

| Requirement | Description | Status | Evidence / Implementation |
| :--- | :--- | :---: | :--- |
| **INF-01** | Unified `BaseModelProvider` interface supporting text generation, token streaming, image analysis, and capability inspection. | **VERIFIED** | `model_provider.py`: `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus` schemas. Tested in `tests/test_model_provider.py` (10 tests). |
| **INF-02** | Local `LlamaCppProvider` communicating with `llama-server` running quantized 2B VLM with health checks and bounded context (4K tokens). | **VERIFIED** | `llama_cpp_provider.py`: Local REST HTTP client, SSE parser, base64 vision handler. `prompt_budget.py`: 4,096 token budgeting and oldest-first history truncation. Tested in `tests/test_llama_cpp_provider.py` (10 tests) and `tests/test_prompt_budget.py` (7 tests). |
| **INF-03** | 100% offline operation without outbound network calls during local mode. | **VERIFIED** | Local provider binds strictly to `http://127.0.0.1:8080`. All unit tests run offline via `httpx.MockTransport` without GPU or network egress. |

---

## 2. Design Locks Verification

| Design Lock | Spec Requirement | Verification Details |
| :--- | :--- | :--- |
| **D1: Pydantic v2 Schemas** | `ProviderCapabilities` and `HealthStatus` frozen with extra fields forbidden | Tested in `tests/test_model_provider.py`. Validation errors raised on mutation and undeclared keys. |
| **D2: Abstract Interface** | `BaseModelProvider` abstract base class with 5 methods | Prevents instantiation of uncompleted subclasses (`test_abstract_provider_instantiation_fails`). |
| **D3: Synchronous HTTP** | `httpx.Client` with explicit timeouts (2.0s connect, 60.0s read) | Configured in `LlamaCppProvider.__init__`. Handles `ConnectError` and timeouts gracefully. |
| **D4: SSE Streaming** | Incremental token yielding terminating on `data: [DONE]` | Tested in `tests/test_llama_cpp_provider.py::test_stream_text_multi_chunk`. |
| **D5: Actionable Setup Guidance** | Unreachable server provides exact `llama-server` launch command | Returns command with `-m models/... --mmproj ... -c 4096 -ngl 28 --port 8080`. |
| **D6: Multimodal Vision** | OpenAI-compatible vision payload with base64 image data URL | Verified in `tests/test_llama_cpp_provider.py::test_analyze_image_payload`. |
| **D7: Bounded Context** | 4,096 token limit, 3,072 input budget, 1,024 generation reservation | Implemented in `prompt_budget.py`. Context truncated when exceeding available room. |
| **D8: Oldest-First History Eviction** | Truncate conversation history oldest-first while preserving current turn | Tested in `tests/test_prompt_budget.py::test_assemble_grounded_messages_truncates_history_oldest_first`. |
| **D9: XML Injection Isolation** | Wrap retrieved text in `<document_context>` with strict negative directives | Tested in `tests/test_prompt_budget.py::test_injection_directive_contained_in_document_context`. |
| **D10: Non-Crashing Startup** | Unreachable server / missing Groq key does not raise uncaught startup crash | Tested in `tests/test_local_llm.py::test_ai_model_non_crashing_when_offline`. Resolves CONCERNS.md Risk #1. |
| **D11: Dynamic UI Status** | Streamlit sidebar status reflects local (green), cloud (blue), or offline (warning) | Wired into `main.py` lines 85–115 with chat input guard. |

---

## 3. Test Suite & Static Analysis Summary

- **Total Test Cases**: 85 passed (0 failures, 0 errors)
  - `tests/test_doc_store.py`: 9 passed
  - `tests/test_llama_cpp_provider.py`: 10 passed *(NEW)*
  - `tests/test_local_embedding.py`: 3 passed
  - `tests/test_local_llm.py`: 7 passed *(UPDATED)*
  - `tests/test_model_provider.py`: 10 passed *(NEW)*
  - `tests/test_models.py`: 15 passed
  - `tests/test_pdf_reader.py`: 9 passed
  - `tests/test_prompt_budget.py`: 7 passed *(NEW)*
  - `tests/test_upload_validation.py`: 8 passed
  - `tests/test_vector_index.py`: 7 passed
- **Static Analysis (`ruff check .`)**: Clean (0 errors)
- **Formatting (`ruff format --check .`)**: Clean (25 files formatted)

---

## 4. Hardware Runbook Deliverable

- Created `docs/LOCAL_INFERENCE.md` detailing:
  - RTX 3050 Laptop GPU (4 GB VRAM) memory budget (~3.26 GB peak, ~830 MB headroom).
  - Exact `llama-server` execution command with `-c 4096 -ngl 28 --port 8080`.
  - GGUF weights acquisition guidelines (`qwen3-vl-2b-instruct-q4_k_m.gguf` + `mmproj-f16.gguf`).
  - Troubleshooting shared GPU system memory paging on Windows.
