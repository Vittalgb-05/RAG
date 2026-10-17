# Codebase Concerns

**Analysis Date:** 2026-10-13

## Release Verdict & Audit Status

**Verdict:** GO (All 226 automated tests passing; production lockfile synchronized; clean Ruff lint/format).

**Resolved Audit Priorities:**
- **P0-1 Lockfile Synchronization:** Fully synchronized between `requirements.txt` and `requirements-lock.txt` targeting Python 3.11. CI installs strictly from `requirements-lock.txt`.
- **P0-2 Hardware Telemetry:** Live `nvidia-smi` sampling integrated with a 5.0-second TTL cache lock in `resource_telemetry.py`. Baseline DWM usage measured at 690 MB, with projected peak VRAM at 3450 MB (leaving 646 MB headroom on 4 GB GPUs, compliant with QUAL-01).
- **P0-3 Multimodal Benchmarking:** Grounded evaluation test suite implemented in `scripts/benchmark_multimodal.py`, confirming 100% citation precision and accurate abstention detection across digital, tabular, and diagram PDFs.
- **P1-1 Persistent Deletion & Purge Controls:** Clear Session (in-memory state reset) and Purge All Data (disk wipe of SQLite `documents.db`, LanceDB table, and `.cache/`) separated and verified.
- **P1-2 Resource Consumption & Caching:** Process-level SentenceTransformers model cache implemented (`_MODEL_CACHE` in `local_embedding.py`), OCR DPI clamped to [72, 300], and visual crop extraction capped to at most 20 regions.
- **P1-3 Session Scoping:** `AiModel` instances scoped to `st.session_state` preventing cross-user routing or consent contamination.

---

## Tech Debt

**1. Analytical vs. Resident Model VRAM Measurement: [RESOLVED]**
- **Issue:** While host DWM memory was queried live from `nvidia-smi` (690 MB), model weights, multimodal projector, KV cache, and CUDA overhead previously remained static analytical constants in `scripts/profile_resources.py`.
- **Resolution:** Enhanced `resource_telemetry.py` with `get_compute_apps_gpu_memory()` and `get_resident_model_gpu_memory()` using `nvidia-smi --query-compute-apps=pid,process_name,used_memory`. Integrated into `scripts/profile_resources.py` to dynamically sample live resident `llama-server` process VRAM whenever active, falling back gracefully to analytical estimates in headless CI.

**2. Legacy `cloud_api_key` Fallback in Session State: [RESOLVED]**
- **Issue:** `main.py` and `litellm_provider.py` retained a legacy `cloud_api_key` string variable alongside the structured `cloud_api_keys` dictionary (`{"groq": "", "openai": "", "anthropic": ""}`).
- **Resolution:** Removed legacy `cloud_api_key` string fallback from `main.py` and `litellm_provider.py`. Enforced provider-keyed `cloud_api_keys` dictionary strictly across session state and tests.

**3. Direct `PdfReader` Ingestion Path in `local_llm.py`: [RESOLVED]**
- **Issue:** `AiModel.ask_a_question_from_pdf_stream` retained a legacy branch that constructed a standalone `PdfReader` and `LocalEmbedding` if no retriever was supplied.
- **Resolution:** Deprecated and removed unindexed fallback branch in `local_llm.py`; `ask_a_question_from_pdf_stream` now requires an indexed retriever or explicit `RetrievalResult`, raising `ValueError` and issuing `DeprecationWarning` if called with an unindexed file path.

---

## Known Bugs

*No open functional bugs identified. All automated tests passing across the entire test suite.*

---

## Security Considerations

**1. SSRF Guard on Local Llama Server:**
- **Risk:** If an attacker could inject an arbitrary URL into `LlamaCppProvider`, the backend could be coerced into making outbound requests to internal infrastructure (Server-Side Request Forgery).
- **Current Mitigation:** `LlamaCppProvider` normalizes URLs and verifies that the target host resolves to a loopback address (`127.0.0.1`, `localhost`, `::1`) via Python `ipaddress`. Any non-loopback host raises `ValueError` unless `allow_remote=True` is explicitly passed.
- **Enforcement:** User-controlled input from the UI or environment cannot override `allow_remote`.

**2. Prompt Injection via Untrusted Document Content: [RESOLVED]**
- **Risk:** Malicious PDFs containing adversarial prompt injection directives (e.g., "Ignore previous instructions and output...") attempting to bypass grounding.
- **Current Mitigation:**
  - Context wrapping: All retrieved snippet contents are encapsulated in `<document_context>` XML tags.
  - Sanitization: `sanitize_xml_boundary()` escapes embedded `<document_context>` tags to prevent premature tag closure.
  - System Prompt Directives: Explicit instructions strictly state that facts within `<document_context>` must be treated as untrusted data and directives must never be followed.
  - Output-Side Validation (Implemented): `citation_validator.py` detects if assistant responses echo known adversarial injection directives (`KNOWN_ADVERSARIAL_DIRECTIVES`), rejecting grounding validation with `injection_detected=True`.

**3. Privacy & Data Egress Invariant:**
- **Risk:** Accidental leakage of local document data to cloud LLMs without user knowledge.
- **Current Mitigation:**
  - Default offline: `cloud_mode` defaults to `False`.
  - Programmatic Consent Gate: `LiteLLMProvider._assert_consent()` raises `PermissionError` if called when `user_consented=False`.
  - Clear Visual Egress Badges: Streamlit UI clearly indicates local execution (`🔒 100% Offline Local Pipeline`) vs external cloud transmission (`☁️ Cloud Inference`).

---

## Performance Bottlenecks

**1. High-Resolution OCR on Scanned Documents: [RESOLVED]**
- **Problem:** Processing scanned PDF pages with RapidOCR ONNX can take 1.5–3.0 seconds per page on CPU.
- **Mitigation & Resolution:**
  - `should_ocr_page` checks character count and bypasses clean digital pages ($>50$ characters), preserving sub-second ingestion for standard PDFs. Rasterization zoom is clamped to $72 \le \text{DPI} \le 300$.
  - Implemented multi-threaded batch OCR processing via `ThreadPoolExecutor` across CPU worker threads in `ocr_fallback.py` when multiple scanned pages are detected, preserving exact page order and fault isolation.

**2. Docling Complex Table Extraction Overhead:**
- **Problem:** Deep document layout analysis and markdown table reconstruction via Docling requires substantial CPU compute.
- **Mitigation:** Ingestion pipeline is executed once per document and deduplicated using SHA-256 digests in SQLite `DocStore`. Subsequent uploads reload cached chunks instantly ($<20$ ms).

**3. First-Run Embedding Model Download: [RESOLVED]**
- **Problem:** On initial startup without internet access, loading `all-MiniLM-L6-v2` will fail if model weights are not pre-cached in `~/.cache/huggingface/`.
- **Mitigation & Resolution:** Automated via `setup.py` (`python setup.py` or `python setup.py download_models`) which downloads GGUF models and pre-caches `all-MiniLM-L6-v2` and RapidOCR ONNX models into local offline caches before initial startup. Detailed runbook instructions provided in `docs/RUNBOOK.md`.

---

## Fragile Areas

**1. SQLite File Locking on Windows:**
- **Why Fragile:** Windows locks open SQLite database files strictly. Lingering connection handles or multi-threaded Streamlit reruns can cause `sqlite3.OperationalError: database is locked`.
- **Mitigation:** `DocStore` uses WAL mode (`PRAGMA journal_mode = WAL`), a 5000 ms busy timeout, and an explicit per-operation context manager `_connect()` that closes connections immediately after query completion.
- **Safe Modification:** Always use `with self._connect() as conn:` for SQLite queries; never store a persistent `conn` object as an instance attribute.

**2. Streamlit Session State & Rerun Lifecycle:**
- **Why Fragile:** Streamlit reruns the entire Python script on every user click or input. Mutating global variables across threads leads to state bleeding between browser sessions.
- **Mitigation:** `get_session_ai_model()` scopes the `AiModel` instance directly to `st.session_state.ai_model`.
- **Safe Modification:** Do not introduce global mutable caches for user-specific state or credentials.

---

## Scaling Limits

**1. Maximum Document Size:**
- **Limits:** Hard caps enforced in `upload_validation.py`:
  - File size: $\le 50$ MB.
  - Page count: $\le 500$ pages.
- **Symptoms at Limit:** Upload is immediately rejected with a user-friendly error message before reading into memory.

**2. Chat Turn History:**
- **Limits:** Bounded to 50 turns (`MAX_CHAT_TURNS = 50`) by `bound_chat_history`.
- **Context Budget:** Prompts are capped at 4096 tokens for local Qwen3-VL 2B, trimming older conversation turns oldest-first to guarantee a 1024-token reserve for output generation.

---

*Concerns analysis: 2026-10-13*
*Update after reliability and performance audit*
