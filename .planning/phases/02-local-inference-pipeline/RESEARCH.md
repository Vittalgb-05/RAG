# Phase 2: Local Inference Pipeline — Research

**Researched:** 2026-10-11  
**Domain:** Local VLM/LLM inference via llama-server (llama.cpp) + BaseModelProvider abstraction + offline streaming on 4 GB VRAM  
**Confidence:** HIGH (verified against current codebase, llama.cpp OpenAI-compatible server specs, and RTX 3050 hardware budget)  

## Summary

Phase 2 transitions the application from a cloud-only Groq prototype to a true local-first, privacy-respecting multimodal intelligence system (INF-01, INF-02, INF-03).
Currently, `local_llm.py:AiModel` directly instantiates `groq.Groq` and hardcodes `openai/gpt-oss-20b`. If `GROQ_API_KEY` is missing or the network is offline, the app raises an unhandled `ValueError` at startup (`CONCERNS.md #1`).

To achieve 100% offline local inference without exceeding the 4 GB VRAM ceiling of the NVIDIA RTX 3050 Laptop GPU:
1. We introduce a unified `BaseModelProvider` interface (`model_provider.py`) defining contracts for non-streaming generation, token streaming generators, image inspection, capability introspection, and health checking.
2. We implement `LlamaCppProvider` (`llama_cpp_provider.py`), an HTTP client communicating with `llama-server` (the native C++ REST server of llama.cpp) over local HTTP (`http://127.0.0.1:8080/v1`).
3. We configure bounded context window allocation (4096–8192 tokens) with token-budget truncation to prevent context overflows (`CONCERNS.md #2`).
4. We wrap provider initialization and health checks in `main.py` so that if `llama-server` is not running, the application displays an actionable setup banner with exact launch commands instead of throwing an unhandled exception.
5. We provide a `GroqProvider` implementing `BaseModelProvider` to preserve backward compatibility as an optional cloud alternative.
6. We implement comprehensive offline unit tests with `pytest` and `httpx` mock transports to ensure 100% test isolation with zero live server dependencies in CI.

---

## 1. Current-State Analysis (Verified by Direct Code Reads)

### 1.1 Existing Inference Coupling (`local_llm.py`)
- **Direct Groq Dependency:** `local_llm.py:7` imports `groq.Groq`. `AiModel.__init__` reads `st.secrets["GROQ_API_KEY"]` or `os.environ["GROQ_API_KEY"]`.
- **Fatal Startup Failure:** If `GROQ_API_KEY` is not found, line 31 raises `ValueError("GROQ_API_KEY is not set...")`. Because `main.py:88` invokes `load_ai_model()` at page load, the entire Streamlit page crashes immediately before the user can even view the UI or choose a local model.
- **Unbounded Context Window:** `local_llm.py:49-72` concatenates the last user message, `k=10` retrieval chunks (~10,000 characters), and up to 10 conversational turns with no token counting or length checks. Only output tokens are bounded (`max_tokens=1024`).
- **Prompt Injection Vulnerability:** Document chunks are interpolated directly into the system message without XML delimiters or adversarial guardrails.

### 1.2 Presentation Layer Integration (`main.py`)
- **Model Status Indicator:** `main.py:86-90` hardcodes `ai_model.model_name` with a static green badge: `st.sidebar.success("Model: Groq (openai/gpt-oss-20b)")`.
- **Streaming Consumer:** `main.py:321-327` passes the generator returned by `ai_model.ask_a_question_from_pdf_stream(...)` to `st.write_stream(...)`.
- **Session State:** `st.session_state.chat_history` stores list of `{"role": str, "content": str, "sources": list[str]}`.

---

## 2. Core Architectural Design & Contracts

### 2.1 Unified Provider Interface (`model_provider.py`)
Per requirement **INF-01**, all inference providers must implement a uniform interface with capability inspection and health checks.

```python
class ProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    model_name: str
    context_window: int
    supports_vision: bool
    is_local: bool
    supports_streaming: bool = True

class HealthStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["healthy", "unreachable", "loading", "error"]
    message: str
    latency_ms: float | None = None

class BaseModelProvider(ABC):
    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        """Generate complete text response synchronously."""

    @abstractmethod
    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        """Stream token strings incrementally."""

    @abstractmethod
    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Analyze an image crop using VLM multimodal capabilities."""

    @abstractmethod
    def check_health(self) -> HealthStatus:
        """Probe provider availability and return status."""

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect model capabilities, context limit, and local/cloud status."""
```

### 2.2 `LlamaCppProvider` Implementation (`llama_cpp_provider.py`)
Per requirement **INF-02**, the local provider interfaces with `llama-server`.
- **Transport:** Synchronous HTTP via `httpx.Client(timeout=...)` with connection timeouts (2.0s for health checks, 60.0s read timeout for generation).
- **Endpoint Structure:**
  - `GET /health` or `GET /v1/models` for health checks.
  - `POST /v1/chat/completions` for text generation and token streaming (via SSE).
  - Multimodal messages: standard OpenAI vision schema:
    ```json
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "Describe the diagram."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
      ]
    }
    ```
- **Streaming Parser:** Consumes `text/event-stream` line-by-line:
  - Ignores empty lines and comments (`: keep-alive`).
  - Detects `data: [DONE]` to terminate.
  - Parses JSON payloads: extracts `chunk["choices"][0]["delta"]["content"]`.
- **Fault Tolerance:** If `llama-server` is unreachable, `check_health()` returns `HealthStatus(status="unreachable", message="llama-server not detected on http://127.0.0.1:8080. Start with: llama-server -m ...")`.

---

## 3. Hardware & VRAM Budget (RTX 3050 Laptop 4 GB)

### 3.1 Model Selection & VRAM Footprint
The target hardware is an NVIDIA GeForce RTX 3050 Laptop GPU with 4,096 MB VRAM.
Under Windows 11, the Windows Desktop Window Manager (DWM) typically reserves 400–600 MB VRAM, leaving ~3,500 MB usable VRAM.

| Component | Precision / Configuration | VRAM Allocation | Notes |
|---|---|---|---|
| **Base VLM Weights** | Qwen3-VL 2B GGUF Q4_K_M | ~1,450 MB | Offloaded to GPU (`-ngl 28`) |
| **Vision Projector (`mmproj`)** | F16 / Q8_0 projector GGUF | ~450 MB | Loaded into VRAM for image encoding |
| **KV Cache (4,096 tokens)** | FP16 or Q8_0 KV cache | ~512 MB | Bounded via `-c 4096` |
| **CUDA Runtime Overhead** | PyTorch / Driver workspace | ~350 MB | Standard runtime context allocation |
| **Windows Desktop Compositor** | DWM / Display buffer | ~500 MB | OS baseline reservation |
| **Total Peak VRAM** | — | **~3,262 MB** | **Safe within 4,096 MB (< 80% ceiling)** |

### 3.2 Recommended `llama-server` Launch Command
```bash
llama-server ^
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf ^
  --mmproj models/qwen3-vl-2b-instruct-mmproj-f16.gguf ^
  -c 4096 ^
  -ngl 28 ^
  --port 8080 ^
  --host 127.0.0.1
```
For CPU-only fallback or testing without GPU:
```bash
llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf -c 4096 -ngl 0 --port 8080
```

---

## 4. Bounded Context & Token Budget Management

To satisfy **INF-02** ("bounded context 4K-8K tokens") and mitigate **CONCERNS.md #2**:
- Total Context Window: 4,096 tokens.
- Maximum Generation Output: 1,024 tokens.
- Available Input Budget: 3,072 tokens (~12,000 characters).
- Budget Priority Allocator:
  1. System Prompt & Grounding Rules: ~300 tokens (fixed).
  2. Current User Question: ~100 tokens (priority).
  3. Retrieved Document Chunks: up to 2,000 tokens (up to ~8,000 characters).
  4. Conversation History: fills remaining budget (truncated oldest-first).

---

## 5. Offline Verification & Testing Strategy (INF-03)

Per **INF-03**, local mode must function 100% offline without outbound network calls.
In the automated test suite:
1. `tests/test_model_provider.py`:
   - Tests `ProviderCapabilities` and `HealthStatus` schema contracts, immutability, and validation.
2. `tests/test_llama_cpp_provider.py`:
   - Uses `httpx.MockTransport` to simulate `llama-server` responses:
     - Health check endpoint `/health` (success, 503 loading, connection refused).
     - Non-streaming completion `/v1/chat/completions`.
     - SSE streaming completion with token chunks and `data: [DONE]`.
     - Multimodal image encoding payload format verification.
     - Timeout handling and graceful error messages.
3. Zero network calls or GPU allocation are required to pass tests in CI.

---

## 6. Codebase Map Alignment & Mitigation

- **CONCERNS.md #1 (Unhandled Groq startup crash):** Mitigated by introducing `check_health()` and decoupling `main.py` startup from hardcoded Groq initialization.
- **CONCERNS.md #2 (Context overflow & prompt injection):** Mitigated by bounded token budgeting and clear `<document_context>` XML tagging.
- **CONVENTIONS.md adherence:**
  - Flat root modules: `model_provider.py` and `llama_cpp_provider.py`.
  - Pydantic v2 schemas: `ProviderCapabilities` and `HealthStatus` use `frozen=True, extra="forbid"`.
  - Strict type hints with builtin generics (`str | None`, `list[dict]`, `Generator`).
  - Unit tests placed in `tests/test_model_provider.py` and `tests/test_llama_cpp_provider.py`.
- **INTEGRATIONS.md adherence:**
  - `httpx` client used for communication with local REST server.
  - Shared fixtures in `tests/conftest.py` extended to support mock provider transports.
