# Coding Conventions

**Analysis Date:** 2026-10-13

## Naming Patterns

**Files:**
- Flat `snake_case.py` files at repository root: `main.py`, `start.py`, `setup.py`, `models.py`, `local_llm.py`, `model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `doc_store.py`, `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `pdf_reader.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `resource_telemetry.py`, `upload_validation.py`.
- No deep nested package subdirectories for core logic — modular monolith structure with direct top-level imports.
- Test files mirror modules with `test_<module>.py` in `tests/`: `test_hybrid_retriever.py`, `test_doc_store.py`, `test_cloud_privacy.py`, `test_concurrency_lock.py`, etc.
- Benchmark scripts named `benchmark_<topic>.py` or `profile_<topic>.py` inside `scripts/`.
- Documentation in uppercase markdown: `README.md`, `CLAUDE.md`, `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`.

**Classes:**
- `PascalCase` for all classes: `AiModel`, `InferenceGate`, `BaseModelProvider`, `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`, `HybridRetriever`, `DocStore`, `DoclingReader`, `OcrEngine`, `VisualAnalyzer`, `LocalEmbedding`, `VectorIndex`, `Summarizer`, `LatencyTracker`.
- Pydantic v2 schemas: `BBox`, `Chunk`, `Page`, `Document`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`, `CitationVerificationResult`.
- Test doubles: Prefixed with `Mock*`, `Dummy*`, or `Deterministic*` (e.g., `MockLlamaCppProvider`, `MockGroqClient`, `DeterministicBenchmarkProvider`).

**Functions & Methods:**
- `snake_case` for all functions and methods: `compute_rrf`, `search_hybrid`, `generate_text`, `stream_text`, `analyze_image`, `check_health`, `extract_citations`, `validate_citations`, `assemble_grounded_messages`, `sanitize_xml_boundary`, `estimate_tokens`, `bound_chat_history`, `get_gpu_memory_info`, `get_process_memory_info`.
- Private helper methods: Prefixed with a single underscore (e.g., `_assert_consent`, `_resolve_api_key_for_model`, `_connect`, `_apply_migrations`, `_embed_one`).
- Test functions: Descriptive pattern `test_<component>_<scenario>_<expected>` (e.g., `test_cosine_distance_math`, `test_scanned_page_triggers_ocr_and_sets_provenance`, `test_unconsented_cloud_call_raises_permission_error`).

**Variables & Constants:**
- Local variables and instance attributes: `snake_case` (e.g., `doc_id`, `chunk_id`, `page_num`, `user_consented`, `context_window`, `is_local`).
- Global constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `MAX_FILE_MB`, `MAX_PAGES`, `CONFIG_VERSION`, `FAST_PATH_TOKEN_LIMIT`, `MAX_STAGE_HISTORY`, `_GPU_CACHE_TTL_SECONDS`).

**Type Hints & Schemas:**
- Modern Python 3.11+ union syntax (`str | None`, `int | float`) instead of legacy `Optional` / `Union`.
- Standard collection generics (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`) from built-ins and `collections.abc` (`Generator[str, None, None]`, `Callable`).
- Pydantic v2 `Field(..., description=...)` with boundary constraints (`ge=0`, `gt=0`, `min_length=1`) and `ConfigDict(frozen=True, extra="forbid")`.

## Code Style

**Formatting:**
- Enforced with Ruff formatter (`ruff format --check .` in CI).
- Target version: Python 3.11 (`pyproject.toml: target-version = "py311"`).
- Line length limit: 120 characters (`pyproject.toml: line-length = 120`).
- 4-space indentation; no tabs.

**Linting:**
- Configured via `[tool.ruff.lint]` in `pyproject.toml`:
  - Selected rule categories: `E` (pycodestyle errors), `F` (Pyflakes), `W` (warnings).
  - Ignored rules: `E501` (line length handled by formatter), `W291` (trailing whitespace), `W293` (blank line whitespace).
  - Excluded paths: `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`.
  - Per-file ignores: `"scripts/*" = ["E402"]` (allowing `sys.path.insert` preceding local imports).

## Import Organization

**Order:**
1. Standard library imports (alphabetical): `base64`, `collections`, `contextlib`, `hashlib`, `io`, `json`, `logging`, `math`, `os`, `pathlib`, `re`, `sqlite3`, `sys`, `time`, `typing`.
2. Third-party packages (alphabetical): `fitz`, `httpx`, `lancedb`, `litellm`, `pydantic`, `pypdf`, `rapidocr_onnxruntime`, `sentence_transformers`, `streamlit`.
3. Local application imports (alphabetical): `from doc_store import DocStore`, `from models import Chunk, Document`, `from model_provider import BaseModelProvider`.

**Grouping:**
- Strict blank line separation between standard library, third-party, and first-party blocks.
- Optional dependencies wrapped in top-level `try/except ImportError` blocks with `None` assignment fallback (e.g., `lancedb = None`, `fitz = None`, `litellm = None`).

## Error Handling

**Defensive Validation:**
- Fail fast with explicit built-in exceptions (`ValueError`, `TypeError`, `PermissionError`, `TimeoutError`).
- Ingestion bounds: Raise actionable `ValueError` on bad `%PDF-` magic bytes, files $>50$ MB, or documents $>500$ pages.
- SSRF Prevention: `LlamaCppProvider` verifies loopback IP addresses via `ipaddress` and raises `ValueError` if an external host is targeted without `allow_remote=True`.
- Privacy Gate: `LiteLLMProvider._assert_consent()` raises `PermissionError` immediately if called without recorded user consent.

**Fault Isolation:**
- Page-level fault isolation in ingestion: If an individual page fails OCR or extraction, mark the `Page` as `failed` with error details in `doc_store.py` and continue remaining pages.
- Fallback degradation: Docling fails $\to$ pypdf; LanceDB fails/uninstalled $\to$ in-memory `VectorIndex`; GPU telemetry unavailable $\to$ return `None` without crashing.

**Resource Locking:**
- `InferenceGate` ensures safe concurrent model execution:
  - Reentrant lock (`threading.RLock`) with acquisition timeouts (`timeout=120.0s`).
  - Context manager `gate.hold(timeout)` guarantees deterministic release even if an exception occurs during streaming.

## Logging & Feedback

**Logging:**
- Module loggers created via `logger = logging.getLogger(__name__)`.
- Log warnings on fallback triggers (e.g., Docling layout failure falling back to digital reader, or missing optional drivers).

**User-Facing UI Feedback:**
- Feedback in Streamlit UI uses native components, never stdout prints:
  - Errors: `st.error(...)` with actionable messages.
  - Progress: `st.status(...)` during multi-step indexing pipelines.
  - Notices: `st.info(...)` and `st.warning(...)` for telemetry or context truncation.
  - Provenance badges: Egress chips (`🔒 100% Offline Local Pipeline` vs `☁️ Cloud Inference`).

## Comments & Documentation

**Module Headers:**
- Every Python module starts with a triple-quoted docstring explaining its architectural purpose, key components, and functional boundaries.

**Docstrings:**
- Functions and classes include Google-style docstrings with `Args:`, `Returns:`, and `Raises:` sections.

**Code Comments:**
- Inline comments reserved for non-obvious algorithms, mathematical heuristics (e.g., token estimation at 4 chars/token, RRF smoothing constant $k=60$), or hardware constraints (e.g., 4 GB VRAM ceiling, TTL cache timing).

---

*Conventions analysis: 2026-10-13*
*Update after codebase style and linting changes*
