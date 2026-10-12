# Phase 7: Optional Cloud Provider & Privacy Controls — Technical Research

**Target Phase:** Phase 7 (`07-optional-cloud-provider-and-privacy-controls`)  
**Requirements:** `INF-04`, `UI-04`  
**Date:** 2026-10-12  

---

## 1. Executive Summary & Goals

Phase 7 introduces optional, privacy-preserving cloud model routing via **LiteLLM** (`INF-04`) accompanied by strict user consent, privacy guardrails, and transparent UI indicators (`UI-04`).

### Core Objectives
1. **Unified Cloud Provider (`litellm_provider.py`):**
   - Implement `LiteLLMProvider` as a concrete implementation of `BaseModelProvider(ABC)` (`model_provider.py`).
   - Support routing to major cloud providers: **Groq** (`groq/llama-3.3-70b-versatile`), **OpenAI** (`openai/gpt-4o-mini`), and **Anthropic** (`anthropic/claude-3-5-haiku-20241022`).
   - Enforce robust timeout (30s) and retry bounds (`num_retries=2`) to guarantee UI responsiveness.
   - Encapsulate vendor exceptions (`litellm.exceptions`) into structured error schemas and `RuntimeError`.
2. **Strict Privacy Consent Gate (`INF-04`, `UI-04`):**
   - Enforce programmatic privacy gates: any attempt to execute inference without explicit `user_consented=True` immediately raises `PermissionError`.
   - Eliminate the standing technical debt in `CONCERNS.md` where `AiModel._detect_provider()` silently routed document content to Groq on local server outages. Local offline mode must remain strictly offline by default.
3. **Local Ingestion & Retrieval Isolation (`INF-03`):**
   - Guarantee that document parsing (`docling_reader.py`, `pdf_reader.py`), OCR (`ocr_fallback.py`), embeddings (`LocalEmbedding`), and LanceDB vector indexing (`HybridRetriever`) remain 100% local on the CPU/GPU. Zero document bytes or vector embeddings are transmitted to any cloud provider during ingestion or search.
4. **Transparent Streamlit UI Controls (`UI-04`):**
   - Provide a Cloud Mode toggle in the sidebar (default: OFF).
   - Show an explicit confirmation modal/dialog detailing the privacy boundary when toggled on.
   - Allow dynamic configuration of cloud provider, model, and API keys for the session.
   - Display prominent egress indicators (e.g. `☁️ Cloud: Groq (llama-3.3-70b)`) in both the sidebar status widget and chat messages.

---

## 2. Technical Architecture & Component Design

### 2.1 LiteLLM Provider Adapter (`litellm_provider.py`)

`LiteLLMProvider` implements `BaseModelProvider(ABC)` with all 5 required methods:

```python
class LiteLLMProvider(BaseModelProvider):
    """Unified cloud LLM provider adapter using LiteLLM with strict consent checks."""

    def __init__(
        self,
        model_name: str = "groq/llama-3.3-70b-versatile",
        api_key: str | None = None,
        user_consented: bool = False,
        timeout: float = 30.0,
        num_retries: int = 2,
    ) -> None: ...
```

#### Provider Capabilities & Model Defaults
- **Groq:** `groq/llama-3.3-70b-versatile` (Context: 128K, Speed: ~250 tok/s, Vision: False)
- **OpenAI:** `openai/gpt-4o-mini` (Context: 128K, Vision: True)
- **Anthropic:** `anthropic/claude-3-5-haiku-20241022` (Context: 200K, Vision: True)

#### Concrete Methods Implementation
1. **`generate_text(...)`:**
   - Verifies `self.user_consented is True`. If False, raises `PermissionError`.
   - Calls `litellm.completion(model=self.model_name, messages=messages, api_key=self.api_key, timeout=self.timeout, num_retries=self.num_retries, temperature=clamped_temp, max_tokens=max_tokens)`.
   - Extracts `response.choices[0].message.content or ""`.
2. **`stream_text(...)`:**
   - Verifies `self.user_consented is True`. If False, raises `PermissionError`.
   - Calls `litellm.completion(..., stream=True)`.
   - Iterates chunks yielding `chunk.choices[0].delta.content or ""` without buffering.
3. **`analyze_image(...)`:**
   - Verifies `self.user_consented is True`. If False, raises `PermissionError`.
   - If model does not support vision (e.g. standard Llama text models), raises `NotImplementedError` or returns graceful unsupported notice matching `GroqProvider`.
   - For vision models (`gpt-4o-mini`, `claude-3-5-haiku`), formats image as base64 data-URI payload in `messages`.
4. **`check_health(...)`:**
   - Checks presence of required API key for the chosen model prefix.
   - Returns `HealthStatus(status="healthy", ...)` if key is present, or `HealthStatus(status="unreachable", message="Missing API key for ...")` if unconfigured.
   - Does not perform network inference during health probe to avoid incurring unnecessary token costs or rate limits.
5. **`get_capabilities(...)`:**
   - Returns `ProviderCapabilities(model_name=self.model_name, context_window=ctx, supports_vision=has_vision, is_local=False, supports_streaming=True)`.

### 2.2 Privacy Consent State Machine & Invariant

```text
┌────────────────────────────────────────────────────────┐
│                   Default App State                    │
│   cloud_mode = False, user_consented = False           │
│   AiModel delegates strictly to LlamaCppProvider       │
│   (Zero external network traffic; 100% offline)        │
└──────────────────────────┬─────────────────────────────┘
                           │ User toggles Cloud Mode
                           ▼
┌────────────────────────────────────────────────────────┐
│               Privacy Confirmation Dialog              │
│  "Warning: Cloud mode will transmit document context   │
│   to external APIs. Ingestion & vectors stay local."   │
│  Buttons: [Cancel / Stay Local]  [I Consent & Enable]  │
└──────────────┬───────────────────────────┬─────────────┘
               │ Cancel                    │ Consent
               ▼                           ▼
┌─────────────────────────────┐  ┌────────────────────────────────────┐
│   Revert toggle to False    │  │ cloud_mode = True                  │
│   Remain 100% Local         │  │ user_consented = True              │
│                             │  │ LiteLLMProvider active             │
│                             │  │ Status Badge: ☁️ Cloud (Model)     │
└─────────────────────────────┘  └────────────────────────────────────┘
```

### 2.3 Elimination of Silent Cloud Fallback (`CONCERNS.md` Fix)

In `local_llm.py`:
- Refactor `AiModel.__init__`:
  ```python
  def __init__(
      self,
      provider: BaseModelProvider | None = None,
      cloud_provider: BaseModelProvider | None = None,
      cloud_mode: bool = False,
  ) -> None:
  ```
- When `cloud_mode=False`: `_detect_provider()` ONLY probes `LlamaCppProvider`. If unreachable, it returns `LlamaCppProvider` in offline diagnostic state. It **never** falls back to Groq Cloud silently.
- When `cloud_mode=True` and cloud provider is configured: `AiModel` routes inference through the consented cloud provider.

---

## 3. Codebase Alignment & Risk Mitigation

| Codebase Map File | Phase 7 Alignment |
|---|---|
| **ARCHITECTURE.md** | Introduces `litellm_provider.py` under the Provider abstraction layer; retains `HybridRetriever` and `LocalEmbedding` as 100% local components; updates `AiModel` provider selection. |
| **CONCERNS.md** | Resolves standing concern **"Groq fallback exists with no opt-in, no egress signal"** by gating cloud calls behind explicit user consent and visible UI badges. |
| **CONVENTIONS.md** | Adheres to the Optional-Dependency pattern for `litellm` (`try/except ImportError → None`); enforces strict Pydantic v2 schemas; implements `BaseModelProvider` ABC; clamps temperature. |
| **INTEGRATIONS.md** | Documents LiteLLM integration contracts, model mappings (Groq, OpenAI, Anthropic), API key resolution order (`st.session_state` → `st.secrets` → `.env`), and timeout bounds. |
| **STACK.md** | Adds `litellm>=1.50.0` to `requirements.txt`. |
| **STRUCTURE.md** | Places `litellm_provider.py` at repository root; tests in `tests/test_litellm_provider.py` and `tests/test_cloud_privacy.py`. |
| **TESTING.md** | 100% offline tests using `unittest.mock.patch` over `litellm.completion` to verify success, streaming, error encapsulation, and permission rejection without live network credentials. |

---

## 4. Phase 7 Plan Breakdown

- **Plan 07-01: LiteLLM Cloud Provider Adapter & Privacy Consent Gate**
  - Implement `litellm_provider.py`.
  - Update `local_llm.py` (`AiModel`) to enforce explicit cloud mode switching and eliminate silent fallback.
  - Author comprehensive test suite in `tests/test_litellm_provider.py`.
- **Plan 07-02: Streamlit Cloud/Local Switch, Privacy Dialog & Egress Indicators**
  - Implement sidebar Cloud Mode toggle with `st.dialog` / consent confirmation.
  - Implement dynamic API key and model selector dialog in `main.py`.
  - Add transparent egress indicators in sidebar telemetry and chat turn responses.
  - Author integration and UI contract tests in `tests/test_cloud_privacy.py`.
