# Coding Conventions

**Analysis Date:** 2026-10-22

## Naming Patterns

**Files:**
- `snake_case.py` for every module, grouped by responsibility: `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`.
- Test files: `tests/test_<module_or_feature>.py` (e.g. `tests/test_hybrid_retriever.py`, `tests/test_whole_document_extraction.py`, `tests/test_setup_checksums.py`).
- Root entry points are minimal and single-word: `main.py`, `start.py`, `setup.py`.
- Module-private helpers are prefixed with a single underscore: `_preflight_note`, `_resolve_level`, `_managed_handlers`, `_delete_document`, `_reindex_document`, `_purge_all`.
- Module constants are `UPPER_SNAKE_CASE` with explicit type annotations: `MAX_FILE_MB: int = 50` (`ingestion/upload_validation.py:18`), `FAST_PATH_TOKEN_LIMIT = 2000` (`core/summarizer.py:30`), `_MAX_LOG_BYTES = 5 * 1024 * 1024` (`core/logging_setup.py:37`).

**Functions:**
- `snake_case`, verb-first for actions: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `search_hybrid`, `fetch_document_chunks`.
- Predicate functions start with `is_`/`has_`/`should_` and return `bool`: `is_whole_document_query`, `has_document`, `is_persistent`, `should_withhold_answer`, `is_locked`.
- Getters use `get_`/`fetch_`; pure transforms use verb + noun: `validate_citations`, `sanitize_markdown_for_local`, `estimate_scanned_ratio`, `compute_rrf`.
- UI renderers are named `render_<area>` and return `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`, `render_brand_header`, `render_status_pill` (`ui/views.py`, `ui/components.py`).

**Variables:**
- `snake_case`; loop indices are meaningful (`page`, `chunk`, `snippet`, `handler`) rather than `i` where the entity matters.
- Boolean locals read as assertions: `is_valid`, `has_lancedb`, `cloud_mode`, `user_consented`, `abstention_detected`.
- Retrieved/domain objects mirror model field names (`doc_id`, `chunk_id`, `sha256`, `page_num`, `num_pages`).

**Types:**
- `PascalCase` Pydantic v2 models in `core/models.py`: `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`.
- `PascalCase` services/coordinators: `DocStore`, `HybridRetriever`, `AiModel`, `Summarizer`, `InferenceGate`, `IngestionService`, `LifecycleService`, `UploadValidation` (`ValidatedUpload`).
- Abstract contracts end in `Provider` or `Base`: `BaseModelProvider` (`providers/model_provider.py`).
- Domain exceptions are explicit and narrow: `VectorIndexError(RuntimeError)` (`retrieval/hybrid_retriever.py:75`).
- Frozen dataclasses are used for immutable value objects: `ValidatedUpload` (`ingestion/upload_validation.py:105`), GGUF metadata (`core/model_identity.py:34`).

**Tests:**
- Functions: `test_<behavior>_<condition>` (e.g. `test_existing_file_with_matching_hash_is_not_downloaded`, `test_deleted_document_stays_deleted_after_lancedb_open_failure`).
- Each test carries a one-line docstring stating the invariant under test.
- Regression tests cite the requirement/defect tag in the docstring or module header (`RETR-01`, `QUAL-01`, `WR-01`, `CR-03`, `INF-03`).

## Code Style

**Formatting:**
- Ruff is the single source of truth, configured in `pyproject.toml:1-18`.
- `line-length = 120`, `target-version = "py311"`.
- `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`.
- 4-space indentation; double-quoted strings and f-strings; blank line between module docstring and imports; two blank lines between top-level definitions.
- No `black`, `isort`, or `pre-commit` configuration is present. Ruff format is the formatter (`ruff format --check .` in `.github/workflows/ci.yml`).
- Ruff format conventions: trailing commas in multi-line calls/collections, parenthesized multi-line conditions, single quotes only when avoiding escaping inside a double-quoted string.

**Linting:**
- `select = ["E", "F", "W", "B", "UP", "SIM"]` (`pyproject.toml:13`).
- `ignore = ["E501", "W291", "W293"]` — line length is enforced by the formatter, not the linter; trailing whitespace rules are disabled.
- Per-file ignores: `scripts/*` ignores `E402` (imports after `sys.path` setup), `start.py` ignores `UP036` because it intentionally supports older Python interpreters before runtime validation (`pyproject.toml:16-18`).
- `# noqa: BLE001` is used deliberately at UI boundaries where a broad `except Exception` is required, always with a reason comment. Example: `ui/views.py:257` — "credentials must still be scrubbed best-effort".
- `# type: ignore[...]` is used for optional-import fallbacks (`lancedb = None  # type: ignore[assignment]`, `ingestion/ocr_fallback.py:81`) and for pydantic-validated literals; prefer narrowing or `cast` for new code.
- `# pragma: no cover` marks defensive/unreachable branches only, never normal logic (`core/logging_setup.py:100`, `main.py:165`).

**Type annotations:**
- PEP 604 unions everywhere: `str | None`, `list[dict[str, Any]]`, `Path | str | None`.
- Abstract collections are imported from `collections.abc` (`Callable`, `Generator`, `Iterable`), not `typing`.
- Public function signatures annotate parameters and returns; `-> None` is explicit on renderers and mutators.
- `from __future__ import annotations` is **not** the default. It appears only in `start.py:7`.
- Generic helpers use `TypeVar` (`T = TypeVar("T")`, `core/doc_store.py:22`).

**Docstrings:**
- Every module begins with a triple-quoted module docstring stating purpose and invariants (see `core/doc_store.py:1-7`, `core/logging_setup.py:1-16`, `ui/sanitizer.py:1-12`, `ingestion/upload_validation.py:1-6`).
- Public functions/classes use Google-style `Args:` / `Returns:` / `Raises:` sections without repeating types. Examples: `configure_logging` (`core/logging_setup.py:64-83`), `estimate_scanned_ratio` (`ingestion/upload_validation.py:28-39`), `validate_pdf_bytes` (`ingestion/upload_validation.py:121-133`).
- Short private helpers may use a single imperative sentence docstring.
- Document the reason for non-obvious safety choices, not a restatement of the code (e.g. the WAL/Windows-lock note in `core/doc_store.py:4-6`).

## Import Organization

**Order:**
1. Module docstring, then `from __future__ import annotations` (only where used, e.g. `start.py`).
2. Standard library (`collections.abc`, `contextlib`, `json`, `logging`, `pathlib`, `sqlite3`, `threading`, `typing`).
3. Third-party (`streamlit`, `httpx`, `pydantic`, `numpy`, `pytest`).
4. First-party absolute imports (`core.*`, `ingestion.*`, `providers.*`, `retrieval.*`, `ui.*`).

Imports within a group are **not strictly alphabetized** because Ruff's `I` (isort) rule is not enabled. Match the surrounding file's ordering rather than re-sorting. Do not use relative imports; all first-party imports are absolute from the repository root.

**Path aliases:**
- None. There are no `src` layouts or import aliases; packages are top-level directories installed editable via `setup.py`.
- Heavy optional dependencies are imported inside a `try/except ImportError` at module top with a `None` sentinel, then feature-guarded:
  ```python
  try:
      import lancedb
  except ImportError:
      lancedb = None  # type: ignore[assignment]
  ```
  See `retrieval/hybrid_retriever.py:44-51`, `ingestion/ocr_fallback.py:70-81`, `ingestion/docling_reader.py:24-34`.

## Error Handling

**Exception taxonomy (follow this when adding code):**
- `ValueError` — invalid user input or invalid business state, with a user-actionable message. Examples: `ingestion/upload_validation.py:136-156` ("Not a valid PDF…", "File too large…"), `core/models.py:112` (doc_id prefix), `core/summarizer.py:554` ("No extractable text found…").
- `TypeError` — programmer contract violation: wrong object type passed to a store/service boundary. `core/doc_store.py:241`, `core/doc_store.py:381-385`, `core/query_intent.py:234`.
- `PermissionError` — privacy/consent violations. Cloud generation without consent raises `PermissionError("Cloud transmission blocked…")` (`core/local_llm.py:134`, `:189`, `:217`).
- `TimeoutError` — `InferenceGate` acquisition failure (`core/local_llm.py:94`).
- `RuntimeError` — external process/transport failure after retries (llama-server HTTP failure in `providers/llama_cpp_provider.py`; raised as `RuntimeError` with the upstream status/body).
- `sqlite3.IntegrityError` — propagated unchanged for constraint violations (hashed duplicate content); tests assert it at `tests/test_doc_store.py:66`.
- Domain-specific subclasses only when callers must distinguish behavior: `VectorIndexError(RuntimeError)` (`retrieval/hybrid_retriever.py:75`).

**Patterns:**
- **Validate early at the boundary, then trust internal data.** `validate_pdf_bytes` performs all user-facing checks before any extraction (`ingestion/upload_validation.py:120-167`); Pydantic models validate identifiers and coordinates (`core/models.py:33-234`).
- **Preserve the cause:** use `raise ... from err` when translating exceptions (`ingestion/upload_validation.py:150`).
- **Log-and-degrade for optional enrichment.** Visual analysis, telemetry, and sanitizer cleanup failures are logged and skipped so the primary ingestion/chat path continues (`ui/ingestion_service.py:209`, `core/resource_telemetry.py:86-90`, `core/summarizer.py:206`).
- **Fail loudly for data loss.** Vector writes raise `VectorIndexError` instead of returning a false success count (`retrieval/hybrid_retriever.py`, regression test `tests/test_audit_repairs.py:82`).
- **UI boundary rule:** UI callbacks catch broad `Exception`, call `logger.exception(...)` with the entity id, then render an actionable `st.error(...)` including remediation and whether SQLite was left intact. Canonical examples: `_delete_document` (`ui/views.py:157-171`), `_reindex_document` (`ui/views.py:191-212`), `_purge_all` (`ui/views.py:224-238`). Broad catches outside a UI/startup boundary require a `# noqa: BLE001` reason.
- **Startup boundary:** `main.py:139-150` catches initialization failure, logs with `logger.exception`, and renders `_render_startup_failure` guidance rather than Streamlit's blank error page.
- **Transactions:** all multi-table writes go through a single `DocStore` transaction (`upsert_document_bundle`, `core/doc_store.py:377`); callers must not partially write metadata and chunks separately.

## Logging

**Framework:** Python stdlib `logging`, configured once by `configure_logging()` in `core/logging_setup.py:57`.

**Conventions:**
- One module-level logger per module, always `logger = logging.getLogger(__name__)`. 23 source modules follow this; see `core/doc_store.py:20`, `ui/views.py:34`, `ingestion/upload_validation.py:15`, `retrieval/hybrid_retriever.py:22`, `providers/llama_cpp_provider.py:24`.
- The two standalone benchmark scripts intentionally use explicit names: `logging.getLogger("benchmark_multimodal")` (`scripts/benchmark_multimodal.py:30`) and `logging.getLogger("resource_profiler")` (`scripts/profile_resources.py:38`).
- Lazy `%`-style formatting, never f-strings in log calls:
  ```python
  logger.info("Validated %s (%s, %d pages, %d bytes)", filename, doc_id, num_pages, size_bytes)
  ```
  (`ingestion/upload_validation.py:166`)
- Level usage:
  - `logger.exception(...)` inside `except` blocks at UI/startup boundaries (includes traceback).
  - `logger.warning(...)` for degraded-but-recoverable conditions: FTS unavailable (`retrieval/hybrid_retriever.py`), unsupported image format (`providers/llama_cpp_provider.py`), file logging disabled (`core/logging_setup.py:130`).
  - `logger.info(...)` for lifecycle milestones; `logger.debug(...)` for diagnostic/close errors.
- Log **once** per condition. FTS degradation is recorded on the retriever and warned exactly once (`tests/test_hybrid_retriever.py:715-738`). Do not log the same failure in both the service and the caller unless the caller adds UI context.
- `configure_logging` is idempotent and only owns handlers marked with `_rag_logging_handler`; never call `logging.basicConfig()` in application modules (`core/logging_setup.py:35`, `:84-94`).
- CLI launchers (`start.py`, `setup.py`) intentionally use `print()` for operator-facing output; application modules must use the logger.
- `RAG_LOG_LEVEL` and `RAG_LOG_DIR` control level and output directory (`core/logging_setup.py:26-28`). Tests set `RAG_LOG_LEVEL`/use `reset_logging()` rather than reconfiguring globally.

## Comments

**When to comment:**
- Explain **why**, safety invariants, and trade-offs — never narrate obvious code.
- Section banners separate large Streamlit modules:
  ```python
  # =====================================================================
  # 1. SIDEBAR DOCUMENT MANAGER & INGESTION
  # =====================================================================
  ```
  (`ui/views.py:282-284`; numbered sections continue through the file).
- Numbered step comments document ordered validation/extraction pipelines (`ingestion/upload_validation.py:134-163`, `core/doc_store.py:24-31`).
- Reference requirement tags inline where behavior is non-obvious: `(QUAL-01)`, `(RETR-03)`, `(INF-03)`, `(WR-02)`.
- Keep TODO/FIXME out of committed code; use `.planning/` artifacts or audit docs (`docs/AUDIT_SUMMARY.md`, `docs/REPAIR_LOG.md`) instead.

**JSDoc/TSDoc:** Not applicable (Python). Use Google-style docstrings as described above.

## Function Design

**Size:** Prefer small, single-purpose helpers. Large public entry points (e.g. `render_chat_view`, `ingestion_service.ingest_pdf`) delegate to private helpers rather than inlining branches. When a UI function grows, split it into `_render_*` / `_delete_*` / `_reindex_*` helpers in the same module.

**Parameters:**
- Keyword-friendly signatures for service constructors (`HybridRetriever(db_uri=..., embedding_fn=...)`, `AiModel(provider=..., cloud_mode=...)`).
- Dependency injection over module globals: services accept `doc_store`, `hybrid_retriever`, `local_embedding`, `cache_dir` explicitly (`ui/ingestion_service.py`, `ui/lifecycle_service.py`).
- Optional behavior is expressed as keyword-only params after `*` (`configure_logging(..., *, enable_file=True, force=False)`, `core/logging_setup.py:57-63`).
- Mutable defaults are never used; use `None` and construct inside the function.

**Return values:**
- Mutating UI actions return `bool` success (`_delete_document`, `_reindex_document`, `_purge_all`) so callers can decide whether to continue.
- Retrieval/generation return typed Pydantic results (`RetrievalResult`, `SummaryResult`, `CitationVerificationResult`) rather than loose dicts.
- Generators yield text deltas for streaming (`stream_text`, `ask_a_question_from_pdf_stream`) and must terminate cleanly; SSE parsing stops at `[DONE]` (`providers/llama_cpp_provider.py`).

## Module Design

**Exports:**
- No `__all__` declarations. Public API is implied by non-underscore names.
- `__init__.py` files are empty package markers; do not add re-exports.
- One responsibility per module; shared schemas live only in `core/models.py`.

**Barrel files:** Not used. Import from the defining module (`from core.models import Chunk`, not from `core`).

**Composition patterns:**
- Pydantic v2 for validated domain records and API contracts (`core/models.py`).
- `@dataclass(frozen=True)` for immutable internal value objects (`ingestion/upload_validation.py:105`).
- `contextmanager` for scoped resource acquisition (`InferenceGate.hold`, `core/local_llm.py:82`; retriever lifecycle in `retrieval/hybrid_retriever.py` uses `__enter__`/`__exit__`).
- ABC for provider contracts (`providers/model_provider.py`); new providers subclass `BaseModelProvider` and implement `check_health`, `get_capabilities`, `generate_text`, `stream_text`, `analyze_image`.

## Concurrency & Resource Discipline

- **Every** LLM/VLM/summarizer inference call must run inside `InferenceGate.hold(timeout=...)` to honor the 4 GB VRAM ceiling. Existing sites:
  - `core/local_llm.py:367`
  - `ingestion/visual_analyzer.py:290` (`timeout=60.0`)
  - `core/summarizer.py:559` (`timeout=120.0`)
- `InferenceGate` is a process-level `threading.RLock` with a reentrancy-safe active counter (`core/local_llm.py:26-100`). Do **not** replace it with a per-provider lock or bypass it for "small" calls.
- `hold()` raises `TimeoutError` rather than blocking forever; let it propagate to the UI boundary.
- Shared caches/registries use explicit locks: `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`, `_LATENCY_LOCK` (`core/resource_telemetry.py:22-31`).
- All SQLite writes go through the bounded retry helper (`WRITE_MAX_ATTEMPTS = 3`, exponential backoff + jitter, `core/doc_store.py:24-40`) — do not add ad-hoc retry loops.

## UI Conventions

- `st.session_state` keys are initialized once in a `(key, default)` loop in `main.py:101-121`; new keys must be added there and reset in `ui/session_state.py`.
- Rotate `st.session_state.uploader_key` after processing an upload to prevent Streamlit's re-processing loop (`main.py`, `ui/views.py`).
- Never mutate `DocStore`/vector indexes directly from a view. Use `IngestionService` for ingest and `LifecycleService` for delete/purge/re-index (`ui/views.py:145-241`).
- Render user/model content through `ui/sanitizer.py` (`sanitize_markdown_for_local`, `sanitize_display_markdown`) before `st.markdown(..., unsafe_allow_html=True)`; local mode must neutralize external links and images, scripts, iframes, objects, embeds, styles, and SVG payloads.
- No emojis in UI strings; use local SVG icons from `assets/icons/` via `get_svg_icon` / `get_brand_mark_svg`. No remote CDNs or web fonts.
- Colors and spacing live in `ui/theme.py` (AMOLED `#050608`, accent `#70D9C2`, cloud `#B9A3FF`, error `#FF7B72`). Do not hard-code new palette values in views.

## Security & Privacy Conventions

- Local mode must produce **zero** outbound network egress. Do not add telemetry, CDN assets, remote fonts, or implicit downloads to any local path.
- Treat all PDF text as untrusted. Preserve XML boundary escaping (`core/prompt_budget.py: sanitize_xml_boundary`) and citation validation (`core/citation_validator.py`).
- Cloud providers require explicit user consent and an API key; raise `PermissionError` on missing consent (`providers/litellm_provider.py`, `core/local_llm.py:134`).
- Never log, render, or persist API keys. Credentials live only in `st.session_state.cloud_api_keys` / environment and are scrubbed by `clear_cloud_credentials` (`ui/views.py:244-270`).
- Downloadable artifacts must be checksum-pinned (`setup.py` `MODEL_REGISTRY` / `LLAMA_ARCHIVE_SHA256`), and `RAG_REQUIRE_CHECKSUMS=1` fails closed before network access (`tests/test_setup_checksums.py:109-129`).

---

*Convention analysis: 2026-10-22*
