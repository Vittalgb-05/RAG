# Coding Conventions

**Analysis Date:** 2026-10-19

## Naming Patterns

**Modules and Files:**
- Flat `snake_case.py` modules at repo root for domain code: `doc_store.py`, `hybrid_retriever.py`, `model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py`.
- The UI is the only package: `ui/` with `__init__.py`, `theme.py`, `components.py`, `views.py`, `sanitizer.py`, `hydration.py`.
- CLI/packaging entry modules: `main.py` (Streamlit app), `start.py` (launcher), `setup.py` (installer + setuptools), `logging_setup.py`.
- Scripts use `<verb>_<noun>.py`: `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`.
- Tests use `tests/test_<module>.py` (`tests/test_doc_store.py`, `tests/test_ui_smoke.py`).
- Asset filenames are lowercase with underscores: `assets/brand_mark.svg`, `assets/icons/check.svg`.

**Classes:**
- `PascalCase`, one primary class per root module: `DocStore`, `HybridRetriever`, `LlamaCppProvider`, `GroqProvider`, `LiteLLMProvider`, `DoclingReader`, `OcrEngine`, `VisualAnalyzer`, `Summarizer`, `InferenceGate`, `AiModel`, `VectorIndex`, `PdfReader`.
- Pydantic schemas are `PascalCase` nouns in `models.py`: `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`; provider schemas live in `model_provider.py`: `ProviderCapabilities`, `HealthStatus`, `BaseModelProvider`.
- Tests do not use test classes; helper provider classes are local to the test module (`MockVisionProvider` in `tests/test_visual_analyzer.py`, `DummyProvider` in `tests/test_concurrency_lock.py`).

**Functions and Methods:**
- `snake_case` everywhere. Public verbs are explicit: `upsert_document`, `record_pages_batch`, `index_chunks`, `search_hybrid`, `compute_rrf`, `validate_citations`, `assemble_grounded_messages`, `detect_visual_regions`, `summarize_document`.
- Private helpers/state use a single leading underscore: `_detect_provider`, `_apply_migrations`, `_connect`, `_escape_sql_literal`, `_embed_one`, `_reset_session_security_state`, `_ICON_CACHE`.
- UI renderers are `render_*`: `render_workspace_view`, `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view` in `ui/views.py`; `render_brand_header`, `render_stat_card`, `render_status_pill`, `render_empty_state`, `render_citation_chip` in `ui/components.py`.
- UI accessors are `get_*`: `get_svg_icon`, `get_brand_mark_svg`, `get_gpu_memory_info`, `get_process_memory_info`, `get_shared_sentence_transformer`.
- Boolean predicates read as questions: `is_available`, `is_persistent`, `should_ocr_page`, `is_abstention`, `safe_has_secret`.

**Variables and Constants:**
- Locals and attributes are `snake_case`: `doc_store`, `retrieval_result`, `chat_history`, `fallback_used`, `user_consented`.
- Module constants are `UPPER_SNAKE_CASE`: `MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `CONFIG_VERSION`, `SYSTEM_GROUNDING_TEMPLATE`, `MAX_BATCH_TOKENS`, `MAX_CHAT_TURNS`, `WATCHER_LOGGER_NAME`, `CITATION_REGEX`.
- Theme tokens use a `COLOR_*` prefix: `COLOR_BG`, `COLOR_SURFACE`, `COLOR_ELEVATED`, `COLOR_BORDER`, `COLOR_PRIMARY`, `COLOR_SECONDARY`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_MUTED`, `COLOR_DANGER`, `COLOR_WARNING` in `ui/theme.py`.
- CSS classes are kebab-case and namespaced: `amoled-card`, `amoled-card-elevated`, `stat-value`, `stat-label`, `status-badge local`, `status-badge cloud`, `status-badge warning`, `status-badge error`.
- `Literal` string values are lowercase snake: `"healthy" | "unreachable" | "loading" | "error"`, `"overview" | "detailed" | "study_notes" | "tables_figures" | "findings"`.
- Test names describe behavior: `test_sha_unique_violation_on_reupload`, `test_local_only_ingestion_and_indexing_invariant`, `test_sanitizer_blocks_raw_html_img_tags`. Requirement IDs belong in docstrings, not names (`(RETR-02)`, `(INF-03)`, `(QUAL-01)`).

## Code Style

**Formatting and Linting:**
- Ruff is the only configured tool, in `pyproject.toml`:
  - `line-length = 120`
  - `target-version = "py311"`
  - `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`
- Lint rules: `select = ["E", "F", "W"]`; `ignore = ["E501", "W291", "W293"]`; `scripts/*` ignores `E402` because scripts inject the repo root into `sys.path` before local imports.
- No isort, mypy, pyright, pylint, flake8, or pre-commit configuration exists. Import ordering and typing are manual.
- CI enforces both gates in `.github/workflows/ci.yml`: `ruff check .` and `ruff format --check .`. Current tree is clean: `ruff check .` passes and `ruff format --check .` reports 64 files already formatted.
- Use 4-space indentation, double-quoted strings, trailing commas in multi-line calls, and parentheses for multi-line boolean expressions. Let `ruff format` decide layout; do not hand-wrap to 79 columns.
- Long prompt/template strings are intentionally allowed past 120 characters because `E501` is ignored; they live as module constants or triple-quoted templates (`prompt_budget.py:SYSTEM_GROUNDING_TEMPLATE`, `summarizer.py:PROFILE_SYSTEM_INSTRUCTIONS`).

**Type Hints:**
- New/current modules annotate public signatures with PEP 604 unions and builtin generics: `str | None`, `Path | str | None`, `list[dict[str, Any]]`, `dict[str, float] | None`, `Generator[str, None, None]`.
- Use `collections.abc` for runtime-importable generics (`Generator`, `Callable`), and `typing.Any` only at genuine boundaries (Streamlit objects, third-party handles).
- Return annotations are required in current modules; `-> None` is explicit for mutators/renderers.
- Pydantic v2 models declare fields with `Field(..., description=...)`, constraints (`ge`, `min_length`, `pattern`), and `model_config = ConfigDict(frozen=True, extra="forbid")` for immutable schemas. Use `@model_validator(mode="after")` for cross-field/identifier invariants (`models.py`).
- `frozen=True` dataclasses are used for simple value objects: `ValidatedUpload` in `upload_validation.py`.
- Legacy modules still use old typing and untyped signatures: `vector_index.py` imports `List, Dict, Tuple, Optional, Any` and leaves many methods unannotated; `pdf_reader.py` and parts of `local_embedding.py` are untyped. Do not copy this style into new code; use the modern modules (`doc_store.py`, `hybrid_retriever.py`, `llama_cpp_provider.py`, `ui/*`) as references.
- `from __future__ import annotations` appears only in `setup.py` and `start.py`; new modules do not need it on Python 3.11+ unless resolving forward references.

**Docstrings:**
- Every module opens with a triple-double-quoted summary that states purpose and often the invariant or output shape: `hybrid_retriever.py`, `doc_store.py`, `citation_validator.py`, `prompt_budget.py`, `logging_setup.py`, `ui/theme.py`.
- Public classes/functions use Google-style sections: `Args:`, `Returns:`, `Raises:`, `Yields:`. Examples: `BaseModelProvider.stream_text` (`model_provider.py`), `HybridRetriever.__init__` (`hybrid_retriever.py`), `TorchClassesScanLogFilter.filter` and `suppress_torch_classes_scan_warning` (`logging_setup.py`), `get_svg_icon` (`ui/components.py`).
- One-line docstrings are acceptable for short, obvious helpers (`close`, `__enter__`, `clear_shared_model_cache`).
- `logging_setup.py` uses Sphinx cross-reference prose (`:class:`TorchClassesScanLogFilter``) and documents the *reason* for the filter design.
- Legacy modules (`pdf_reader.py`, parts of `vector_index.py`) use informal or absent docstrings. Match the host module when editing; new modules should use the Google-style form.

**Comments:**
- Comments explain *why*, especially privacy/VRAM/security invariants: `# Local loopback & container networking endpoints`, `# Process-level model cache to avoid duplicate SentenceTransformer instances across sessions (P1 audit)`, `# Guard against any outbound socket connections`.
- Pipeline steps are numbered in orchestration code: `ui/views.py` uses `# 4. Text extraction`, `# 4b. Conditional RapidOCR fallback`, `# 5. Persist Document and Pages atomically`, `# 8. Best-effort disk cache write`; `doc_store.py` uses `# 1. Magic bytes check`-style numbering in validation.
- Large sections are separated by banner comments:
  - Root logic: `# ------------------------------------------------------------------`
  - UI views: `# =====================================================================` plus `# 1. WORKSPACE VIEW ...`
  - Legacy vector module: `# ------------------------------------------------------------------` and `# Public API`
- Requirement/audit IDs are cited inline where behavior is non-obvious (`INF-03`, `INF-04`, `WR-02`, `P1 audit`, `QUAL-01`, `RETR-04`). Preserve these when touching the associated logic.

**Line/Structure Style:**
- Small single-purpose methods; orchestration functions may be long when they are sequential UI layouts (`render_workspace_view` is the ingestion pipeline split into numbered stages).
- Prefer early returns for empty/invalid states (`if not chunks: return`, `if not pages: return`, `return []`).
- Use f-strings for user/error messages; use `%s` lazy formatting for logging only.

## Import Organization

**Order (all modules):**
1. Standard library, alphabetical by module (`collections.abc`, `contextlib`, `datetime`, `hashlib`, `json`, `logging`, `pathlib`, `sqlite3`, `typing`).
2. Blank line.
3. Third-party packages (`httpx`, `numpy`, `pydantic`, `streamlit`, `pypdf`, `langchain_text_splitters`).
4. Blank line.
5. Local absolute imports (`from doc_store import DocStore`, `from ui.components import ...`).

**Rules:**
- Use absolute imports only. Inside the `ui/` package, import as `from ui.components import render_status_pill` — never relative imports.
- Do not export through barrels. `ui/__init__.py` deliberately exports only the sanitizer entry point:
  ```python
  from ui.sanitizer import sanitize_markdown_for_local

  __all__ = ["sanitize_markdown_for_local"]
  ```
- Wrap optional heavy/third-party imports in `try/except ImportError` and set the symbol to `None`, with a `# type: ignore[assignment, misc]` comment: `docling_reader.py` (Docling), `ocr_fallback.py` (RapidOCR + PyMuPDF), `hybrid_retriever.py` (LanceDB/PyArrow), `groq_provider.py` (Groq), `litellm_provider.py` (LiteLLM), `visual_analyzer.py` (PyMuPDF).
- Set TensorFlow/Keras environment flags before importing torch-backed libraries:
  ```python
  os.environ.setdefault("USE_TF", "0")
  os.environ.setdefault("USE_TORCH", "1")
  os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
  ```
  Present in `main.py`, `local_embedding.py`, and `start.py`. Keep this ordering.
- CLI scripts insert the repo root before local imports and rely on the `E402` per-file ignore:
  ```python
  REPO_ROOT = Path(__file__).resolve().parent.parent
  sys.path.insert(0, str(REPO_ROOT))

  from pdf_reader import PdfReader
  ```

## Error Handling

**Raise the right built-in:**
- `TypeError` for wrong runtime types; check before mutating state. Examples: `DocStore.upsert_document` (`Expected Document instance, got ...`), `HybridRetriever.index_chunks` (`Expected Chunk or dict`), `VectorIndex.add_vector` (`Vector must be a list of numbers`).
- `ValueError` for invalid values, invalid configuration, or missing required data. Examples: `distance_metric must be 'cosine' or 'euclidean'`, `Cannot index chunks: neither embeddings nor embedding_fn was provided`, `Not a valid PDF: missing %PDF header`, `Invalid sha256 digest`.
- `RuntimeError` for provider/transport failures, wrapping the cause with `from exc`: `llama_cpp_provider.py` (`llama-server generation failed`), `groq_provider.py` (`Groq API error`), `litellm_provider.py` (`Cloud provider generation/streaming/vision error`).
- `PermissionError` for privacy consent failures (`litellm_provider.py:_assert_consent` → `Cloud transmission blocked`).
- `NotImplementedError` for unsupported capabilities (`GroqProvider.analyze_image`, `LiteLLMProvider.analyze_image` when vision is unsupported).
- `TimeoutError` for lock acquisition failure (`InferenceGate.hold` in `local_llm.py`).

**Graceful degradation at boundaries:**
- Optional dependency missing must not crash startup. Return a degraded result and log a warning: LanceDB unavailable → disk-backed/in-memory `VectorIndex` fallback (`hybrid_retriever.py:120-133`); PyMuPDF missing → skip visual detection (`visual_analyzer.py:79-81`); Docling failure → fall back to `PdfReader` and set `fallback_used` (`docling_reader.py`).
- `HybridRetriever.search_dense/search_fts/search_hybrid` catch backend errors, log `warning`, and fall back to the local implementation rather than raising.
- Health checks return `HealthStatus` objects instead of raising for expected offline/loading states (`llama_cpp_provider.check_health`, `groq_provider.check_health`).

**Isolation and continuation:**
- Per-page extraction failures are caught inside the page loop so remaining pages still index (`pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`).
- Per-file ingestion failures show `st.error(...)`, add the document to `st.session_state.failed_doc_ids`, and `continue` to the next upload (`ui/views.py:220-223`).
- Disk cache writes are best-effort: catch `OSError`, log a warning, and continue (`ui/views.py:268-279`).
- The chat stream is wrapped in `try/except Exception`; on failure the UI renders `st.error` and appends an interrupted assistant turn so history remains consistent (`ui/views.py:498-566`).
- Broad `except Exception` is acceptable only at I/O/third-party boundaries; never use a bare `except:`. Every broad handler either logs with context or returns a safe degraded value.

**Message and chaining rules:**
- Error messages are user-actionable and include the offending value/filename: `Too many pages (501 > 500) — file.pdf.`
- Preserve the original cause with `raise ... from exc` in provider adapters.
- Scrub credentials before logging cloud errors (`LiteLLMProvider._scrub_credentials`, `litellm_provider.py:135-141`).

## Logging

**Framework:** stdlib `logging`; no external logging library.

**Patterns:**
- Every substantive module declares `logger = logging.getLogger(__name__)` (`doc_store.py`, `hybrid_retriever.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `summarizer.py`, `local_llm.py`, `citation_validator.py`, `resource_telemetry.py`, `ui/hydration.py`, `ui/views.py`, `main.py`).
- Use lazy `%s` formatting, never f-strings in logger calls:
  ```python
  logger.warning("Could not query documents for hydration: %s", e)
  logger.warning("Failed to delete from retriever: %s", err)
  logger.info("Indexed %d chunks.", len(chunks))
  ```
- Level selection:
  - `info` — lifecycle and successful state transitions (model loaded, LanceDB table opened/created, fallback store loaded).
  - `warning` — recoverable degradation (LanceDB failure → fallback, disk cache write failure, hydration failure, delete failure, OCR init failure).
  - `error` — failed persistence or provider call before re-raising (`hybrid_retriever.py` LanceDB persist/delete, `litellm_provider.py` provider errors).
  - `debug` — telemetry/non-critical backend notices (`resource_telemetry.py`, `hybrid_retriever.py` FTS notices).
- User-facing feedback must use Streamlit (`st.error`, `st.warning`, `st.info`, `st.success`, `st.toast`, `st.status().update`), never `print` (`ui/views.py`, `main.py`).
- `print()` is reserved for CLI/installer/launcher output (`setup.py`, `start.py`), legacy modules (`pdf_reader.py:131`), the `DocStore` migration notice (`doc_store.py:154`), and upload validation diagnostics (`upload_validation.py`). New library modules should log instead.

**Targeted suppression (`logging_setup.py`):**
- Suppress a specific benign Streamlit watcher record with a `logging.Filter` subclass, not `Logger.setLevel`, because Streamlit calls `setLevel` on import and would clobber a level override:
  - `TorchClassesScanLogFilter(logging.Filter)` matches `_needle = "torch.classes"` in `record.getMessage()`.
  - `suppress_torch_classes_scan_warning()` attaches the filter idempotently to `streamlit.watcher.local_sources_watcher`.
  - `WATCHER_LOGGER_NAME` is a module constant.
- Apply this once in the entry point before importing Streamlit-dependent heavy modules: `main.py` calls `suppress_torch_classes_scan_warning()`.
- Follow the same shape for future narrow suppressions: one `Filter` subclass, one idempotent installer, one constant logger name, tests that inject `logging.LogRecord` objects.

## Function Design

**Size and shape:**
- Domain helpers are 5–25 lines. UI renderers can be 50–200 lines because they are sequential layout pipelines; extract only genuinely reusable UI or logic, not layout blocks.
- Prefer keyword arguments with safe defaults; new retrieval/generation parameters must default so existing call sites keep working:
  - `stream_text(..., max_tokens: int = 1024, temperature: float = 0.2)`
  - `search_hybrid(query, k: int = 5, doc_id: str | None = None)`
  - `summarize_document(..., profile: str = "overview", force_refresh: bool = False)`

**Injection seams for testability:**
- Accept collaborators as optional constructor/value arguments rather than importing hard-coded singletons:
  - `AiModel(provider=..., cloud_mode=..., cloud_provider=...)`
  - `HybridRetriever(embedding_fn=..., vector_dim=...)`
  - `LlamaCppProvider(transport=...)`
  - `DoclingReader(converter=...)`
  - `OcrEngine(recognizer=..., renderer=...)`
  - `VisualAnalyzer(region_detector=..., cropper=...)`
  - `Summarizer(provider=..., doc_store=...)`
- This is the preferred mocking strategy; see `tests/conftest.py` and `tests/test_llama_cpp_provider.py`.

**Return values:**
- Return canonical Pydantic models (`Document`, `RetrievalResult`, `CitationVerificationResult`, `SummaryResult`) or plain containers (`list[dict[str, Any]]`, `list[tuple[dict, float]]`, `str`).
- Do not return `None` to signal failure. Return an empty list/string for "no results" and raise for invalid input. Exceptions: getters that legitimately miss (`DocStore.get_document` → `None`, `get_gpu_memory_info` → `None` when telemetry is unavailable).

**Generators and context managers:**
- Streaming APIs are generators yielding `str` fragments: `BaseModelProvider.stream_text`, `AiModel.ask_a_question_from_pdf_stream`. Keep them lazy so `st.write_stream` can render incrementally.
- Resource/per-request lifecycles use context managers:
  - `@contextmanager DocStore._connect()` closes SQLite connections.
  - `@contextmanager InferenceGate.hold()` acquires/releases the process-wide GPU lock.
  - Providers implement `__enter__`/`__exit__` delegating to `close()`.

## Module Design

**Exports:**
- Root modules expose one main class or a small set of functions. No `__all__` in root modules.
- `ui/__init__.py` is minimal and explicitly exports only `sanitize_markdown_for_local`.
- Add new root modules as a flat file and list them in `setup.py` under `py_modules` so packaging and editable installs include them. Local imports are direct (`from doc_store import DocStore`).

**State:**
- Prefer instance state. Document any process-level cache and make it clearable for tests:
  - `_MODEL_CACHE` + `clear_shared_model_cache()` (`local_embedding.py`)
  - `_ICON_CACHE` (`ui/components.py`)
  - `_LATENCY_HISTORY` + `clear_latency_history()` (`resource_telemetry.py`)
  - `InferenceGate._lock` + `_active_threads` (`local_llm.py`)
- Protect mutable process-global state with a `threading.Lock`/`RLock` (`resource_telemetry.py` uses `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`, `_LATENCY_LOCK`; `InferenceGate` uses `_lock` + `_state_lock`).

**Streamlit conventions (`main.py`, `ui/views.py`):**
- `st.set_page_config(...)` must be the first Streamlit call — it is at `main.py:91-96`, after only env flags, imports, and the logging filter.
- Initialize every `st.session_state` key in one loop at module top (`main.py:106-124`); add new keys there, never lazily in the middle of a layout.
- The entry point owns wiring: `DocStore`, `AiModel`, health/capabilities, hydration, cloud-provider synchronization. Views receive `doc_store`, `ai_model`, `health`, `caps`, `cache_dir` and render only.
- Workspace routing is a string switch on `st.session_state.active_workspace` with the canonical labels `Workspace`, `Ask Documents`, `Summarizer`, `Document Library`, `Settings`.
- Mutating actions end with `st.rerun()` after state changes (`upload`, navigation, delete, purge, session reset).
- Give every widget a stable unique `key` (e.g. `f"lib_del_{doc.doc_id}"`, `f"pdf_uploader_{uploader_key}"`).
- Render HTML with `st.markdown(..., unsafe_allow_html=True)` only from vetted component helpers; sanitize LLM/document markdown through `sanitize_display_markdown` before rendering (`ui/views.py:398, 674`).
- New UI should live in `ui/components.py` (reusable markup) or `ui/views.py` (page layout) and use `COLOR_*`/`THEME_CSS` from `ui/theme.py`. Do not add ad-hoc hex colors inside views when a token exists; existing inline hex values in `ui/views.py` are legacy and should be reduced over time.

**Packaging/launcher conventions:**
- `setup.py` exposes console scripts: `rag-assistant=start:main`, `rag-setup=setup:main_cli`, `rag-download-models=setup:download_models_cli`, `rag-setup-llama=setup:setup_llama_server_cli`.
- `start.py` and `setup.py` use `argparse`, `__future__ annotations`, UTF-8 stdout/stderr reconfiguration for Windows consoles, and emoji/checkmark status output.
- `tools/llama-server/` is a vendored native runtime, not source code: `llama-server.exe`, `llama-*.exe`, `*.dll`, plus `LICENSE-LLVM-OpenMP`. It is gitignored and dockerignored. Do not edit or hand-manage it; acquire/verify it through `setup.py:setup_llama_server()` and launch/detect it through `start.py:get_llama_server_binary()`/`start_llama_server_process()`. Tests mock `subprocess.run`/`shutil.which` rather than executing binaries.

**Legacy exceptions to not propagate:**
- `pdf_reader.py`, `vector_index.py`, and portions of `local_embedding.py` predate the current style (old `typing` generics, few annotations, informal docstrings, `print` diagnostics). For new code, follow `doc_store.py`, `hybrid_retriever.py`, `llama_cpp_provider.py`, and the `ui/` package instead.
- `DocStore._apply_migrations` still uses `print`; new persistence code should use `logger.info`.

---

*Convention analysis: 2026-10-19*
