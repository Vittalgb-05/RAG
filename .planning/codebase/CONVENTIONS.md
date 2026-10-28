# Coding Conventions

**Analysis Date:** 2026-10-28

## Naming Patterns

**Files:**
- `snake_case.py` module names, one module per responsibility: `core/doc_store.py`, `retrieval/hybrid_retriever.py`, `ingestion/ocr_fallback.py`, `ui/lifecycle_service.py`.
- Entry points at repo root only: `main.py` (Streamlit composition root), `start.py` (launcher CLI), `setup.py` (setup CLI).
- Test files: `tests/test_<module_or_feature>.py` (`tests/test_doc_store.py`, `tests/test_cloud_privacy.py`, `tests/test_ui_redesign_apptest.py`).
- Helper scripts and generated data live outside importable packages: `scripts/`, `tests/data/corpus/generate_corpus.py`, `tools/`.

**Classes:**
- `PascalCase`, noun-first and role-suffixed: `DocStore`, `HybridRetriever`, `IngestionService`, `LifecycleService`, `ChatTurnService`, `VisualAnalyzer`, `CitationValidator`, `BaseModelProvider`, `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`, `PdfReader`, `DoclingReader`.
- Pydantic schemas are bare nouns: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`, `CitationVerificationResult` (all in `core/models.py` plus `providers/model_provider.py`, `core/citation_validator.py`).
- Exceptions end in `Error`: `VectorIndexError(RuntimeError)` at `retrieval/hybrid_retriever.py:75`.
- Fresh dataclasses are frozen and named by result role: `ChatTurnPreparation`, `ChatTurnResult` (`ui/chat_controller.py:33`, `:49`); `ValidatedUpload` in `ingestion/upload_validation.py:105`; `ModelIdentity` in `core/model_identity.py:34`. Mutable result containers are the exception and are named `*Result` (`IngestionResult`, `ui/ingestion_service.py:23`).

**Functions and methods:**
- `snake_case`, verb-first for actions: `upsert_document`, `record_ingestion`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `validate_pdf_bytes`, `redact_text`, `estimate_tokens`, `assemble_grounded_messages`.
- Predicates use `is_`/`has_`/`should_`: `is_abstention`, `has_document`, `should_withhold_answer`, `should_ocr_page`, `is_whole_document_query`.
- Private helpers are `_`-prefixed and module-level when stateless: `_is_sqlite_busy` (`core/doc_store.py:35`), `_decode_destination` (`ui/sanitizer.py`), `_build_chunks_schema` (`retrieval/hybrid_retriever.py`), `_embed` in `tests/test_whole_document_extraction.py`.
- Workspace renderers are `render_<area>` and return `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`, `render_file_upload_button` (`ui/views.py`). Pure markup builders return `str` and keep the `render_<component>` name: `render_status_pill`, `render_citation_chip`, `render_chatgpt_citation_pill` (`ui/components.py:86`, `:113`, `:144`). Side-effect components return `None`: `render_brand_header`, `render_stat_card`, `render_empty_state` (`ui/components.py:52`, `:69`, `:95`). Asset loaders are `get_<asset> -> str` (`get_svg_icon`, `get_brand_mark_svg`).
- Session-summary helpers use the cache verb pair: `get_session_summary`, `store_session_summary`, `summary_session_key`, `clear_summary_session_cache` (`ui/views.py:39-81`).

**Variables, constants, fields:**
- `snake_case` for locals, parameters, and Pydantic/`dataclass` fields (`doc_id`, `sha256`, `num_chunks`, `char_start`, `auto_attributed_count`).
- Module constants are `UPPER_SNAKE`: `MAX_FILE_MB`, `MAX_PAGES` (`ingestion/upload_validation.py`), `DEFAULT_DB_URI`, `LEGACY_DB_URI`, `DEFAULT_RRF_K` (`retrieval/hybrid_retriever.py:70-72`), `CONFIG_VERSION` (`core/models.py:14`), `WRITE_MAX_ATTEMPTS` (`core/doc_store.py:29`), `_DANGEROUS_SCHEMES` (`ui/sanitizer.py`), `COLOR_BG`…`COLOR_WARNING` (`ui/theme.py:6-15`).
- Private module constants keep the leading underscore even in caps: `_WRITE_RETRY_BASE_DELAY`, `_SQLITE_BUSY_CODES`, `_HANDLER_MARKER`, `_SECRET_ENV_VARS`, `_TOKEN_PATTERN`.
- Environment-variable constants are named after the variable: `LOG_LEVEL_ENV = "RAG_LOG_LEVEL"`, `LOG_DIR_ENV = "RAG_LOG_DIR"` (`core/logging_setup.py:26-27`).

**Types and identifiers:**
- Domain identifiers are prefixed and validated: documents `doc_<sha16>`, summaries `summ_...`; enforced in model validators (`core/models.py:112`, `:138`, `:167`, `:243-245`).
- Test names are `test_<behavior>_<condition>` or `test_<behavior>_<requirement_id>`: `test_sha_unique_violation_on_reupload`, `test_two_instance_interleave_R1`, `test_unauthorized_release_does_not_corrupt_active_counter`, `test_corrupt_invalid_rejected_WR07`, `test_local_embedding_cpu_pinning`.
- Requirement IDs (`RETR-01`, `QUAL-01`, `INF-03`, `UI-04`, `TEL-01`, `WR-07`) are embedded in test module docstrings, function docstrings, and comments (~82 occurrences across `tests/`).

## Code Style

**Formatting:**
- Ruff is the single formatter and linter. Configuration in `pyproject.toml:1-18`:
  - `line-length = 120`, `target-version = "py311"`.
  - `select = ["E", "F", "W", "B", "UP", "SIM"]`; `ignore = ["E501", "W291", "W293"]`.
  - `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`.
  - Per-file ignores: `scripts/*` → `E402`; `start.py` → `UP036`.
- Ruff defaults apply for quoting: double quotes for strings and f-strings; 4-space indentation; trailing commas in multi-line calls.
- Import sorting (`I`) is **not** enabled, and no formatter beyond Ruff is configured. There is no `.pre-commit-config.yaml`.
- Enforced in CI (`.github/workflows/ci.yml`): `ruff check .` then `ruff format --check .` before tests. Run the same two commands locally before pushing.
- No type checker (mypy/pyright) is configured. Type hints are a convention, reviewed manually, not a gate.

**Typing:**
- PEP 604 unions and built-in generics everywhere: `str | None`, `Path | str`, `list[dict[str, str]] | None`, `dict[str, Any]`.
- Abstract collections come from `collections.abc`: `Callable`, `Generator`, `Iterable` (e.g. `core/doc_store.py:9`, `providers/model_provider.py:9`, `core/redaction.py`).
- `typing` is used only for `Any`, `Protocol`, `TypeVar`, `Literal`: `core/doc_store.py:18`, `ui/chat_controller.py:15`, `core/models.py:10`.
- `from __future__ import annotations` is used selectively (4 modules: `core/redaction.py:8`, `ui/chat_controller.py:9`, `start.py:8`, `setup.py:14`) for forward-reference ergonomics; it is not applied repo-wide. Match the surrounding module.
- Annotate all public boundaries: constructor args, public method params, returns. `-> None` on renderers and mutators.
- Generic helpers use a module-level `TypeVar`: `T = TypeVar("T")` then `_execute_write(operation: Callable[[sqlite3.Connection], T]) -> T` (`core/doc_store.py:23`, `:189`).
- Legacy exception: `ingestion/pdf_reader.py` is untyped (`def __init__(self, file_or_path, filename=None)` at line 16). Do not copy this style; new ingestion code is typed (`ingestion/upload_validation.py`, `ingestion/ocr_fallback.py`).

**Docstrings:**
- Every module opens with a `"""..."""` docstring stating purpose and invariants. The only module missing one is `ingestion/pdf_reader.py` (starts with `import hashlib`).
- Class docstrings state the contract and the reason the class exists, not just a restatement of the name:
  ```python
  class VectorIndexError(RuntimeError):
      """Raised when vectors could not be written to the active persistent backend.

      Callers must treat this as a failed ingestion/re-index rather than a success,
      otherwise the SQLite catalog reports documents as indexed while they are not
      retrievable (silent vector loss).
      """
  ```
  (`retrieval/hybrid_retriever.py:75-81`)
- Public methods use Google-style `Args:` / `Returns:` / `Yields:` without repeating types:
  ```python
  def acquire(cls, timeout: float = 60.0) -> bool:
      """Acquire exclusive inference access with a timeout.

      Args:
          timeout: Maximum seconds to wait for lock acquisition.

      Returns:
          True if acquired, False on timeout.
      """
  ```
  (`core/local_llm.py:41-49`)
- Module docstrings for multi-concern modules explain each concern in prose bullets (see `core/logging_setup.py:1-16`, `ui/sanitizer.py:1-11`).

**Comments:**
- Comments explain *why*, invariants, and failure consequences — not what the code does:
  ```python
  # Bounded retry policy for SQLite write transactions.  Streamlit reruns and
  # multi-tab use can produce transient SQLITE_BUSY/LOCKED errors; retrying a few
  # times with exponential backoff plus jitter resolves contention without
  # masking genuine failures (schema errors, constraint violations, disk errors).
  ```
  (`core/doc_store.py:25-28`)
- Requirement IDs tag the invariant under test: `# Guard against any outbound socket connections ... (INF-03)` (`tests/test_cloud_privacy.py:60`).
- Security-adjacent normalization is documented inline with the attack it closes (`ui/sanitizer.py:20-34`).
- Broad exception handlers carry a `# noqa: BLE001 - <reason>` comment (`core/summarizer.py:206`, `ui/views.py:276`, `:281`, `:287`). Note: Ruff's `BLE` ruleset is not in `select`, so these are documentation, not suppressions.

## Import Organization

**Order:**
1. Environment hardening (only where required before third-party import) — `main.py:14-18` and `tests/conftest.py:6-11` set `USE_TF`, `USE_TORCH`, `TF_ENABLE_ONEDNN_OPTS` before importing Streamlit/torch-backed libraries.
2. Standard library, alphabetized: `from collections.abc import ...`, `from contextlib import contextmanager`, `import logging`, `from pathlib import Path`, `import re`.
3. Blank line, then third-party: `import httpx`, `import lancedb`, `import numpy as np`, `import pydantic`, `import streamlit as st`.
4. Blank line, then first-party absolute imports: `from core.models import ...`, `from providers.model_provider import ...`, `from retrieval.hybrid_retriever import ...`, `from ui.views import ...`.

**Path Aliases / relative imports:**
- No relative imports anywhere (`from . import ...` never appears). Always absolute package imports, which works because the repo is installed editable (`pip install -e .`, `setup.py:820-827`).
- No path aliases or `sys.path` manipulation in application code; tests rely on the installed package plus `tests/__init__.py`.
- Import grouping is by hand, not lint-enforced; occasional ordering drift exists (`import contextlib` after first-party imports at `retrieval/hybrid_retriever.py:21`, `import pypdf` in the stdlib block at `ingestion/pdf_reader.py:5`). Keep the four-group convention when adding imports.

## Error Handling

**Validation and fail-fast (raise):**
- `ValueError` for invalid input and invariant violations: `cache_dir_for` rejects malformed digests (`core/models.py:28-30`), `BBox` rejects inverted coordinates (`:47-51`), summarizer rejects unknown profiles and unextractable documents (`core/summarizer.py:488`, `:554`).
- Pydantic v2 validators encode structural constraints: `model_config = ConfigDict(frozen=True, extra="forbid")` plus `Field(..., ge=1)` / `min_length=1` / `Literal[...]` (`core/models.py:33-100`, `providers/model_provider.py:15-61`). Do not add ad-hoc dict validation when a model exists.
- Domain-specific exceptions for lossy operations: `VectorIndexError` must propagate so SQLite is not told a document was indexed when vectors were not written (`retrieval/hybrid_retriever.py:437`, `:577`, `:634`; asserted in `tests/test_audit_repairs.py:70`).
- Consent violations use `PermissionError`: cloud providers refuse work without explicit consent (`providers/groq_provider.py:66`, `providers/litellm_provider.py:144`; tested in `tests/test_cloud_privacy.py:34`).
- Wrap and re-raise with `raise ... from err` to preserve the cause (13 such sites, e.g. `retrieval/hybrid_retriever.py`).
- Health probes return status objects instead of raising: `HealthStatus(status="healthy" | "unreachable" | "loading" | "error")` from `check_health` (`providers/model_provider.py:44-61`, `providers/llama_cpp_provider.py`).

**Boundary handling (catch + report):**
- Service and UI boundaries catch broadly (`except Exception as err`) so one document/provider failure cannot abort a Streamlit run. Each catch logs with context and surfaces a redacted message:
  ```python
  except Exception as err:
      logger.warning("Could not read deletion tombstones: %s", err, exc_info=True)
  ```
  (`ui/hydration.py:43`)
- UI errors must pass through `redact_text` before display: `st.error(f"Inference engine unavailable: {redact_text(health.message)}")` (`ui/views.py:676`), `st.error(f"Summarization error: {redact_text(str(sum_err))}")` (`ui/views.py:893`). Enforced by `tests/test_redaction.py`.
- Use `st.error` for failures, `st.warning` for degraded-but-usable state; keep messages actionable (include the remediation command for offline inference, `providers/llama_cpp_provider.py`).
- Never swallow vector or persistence failures: ingestion/re-index paths raise `RuntimeError`/`VectorIndexError` after a write that produced no retrievable data (`ui/ingestion_service.py:125`, `:290`, `ui/hydration.py:195`).
- Cleanup paths (closing providers, resetting state) use best-effort catches with `logger.warning`/`logger.debug` so teardown never masks the original error (`ui/session_state.py:36-60`).

## Logging

**Framework:** Standard library `logging`; no third-party logging dependency.

**Setup:**
- Application logging is installed once by `configure_logging()` in `core/logging_setup.py:57`, called from `main.py` via `core.logging_setup.configure_logging`.
- Level comes from `RAG_LOG_LEVEL` (default `INFO`); directory from `RAG_LOG_DIR` (default `data/logs`); rotating file handler `app.log` at 5 MB × 3 backups, plus stderr. Handlers are tagged with `_rag_logging_handler` so reconfiguration is idempotent and never removes framework handlers.
- CLI launchers (`start.py`, `setup.py`) intentionally keep `print()`-based operator output (~113 `print` calls); do not convert them to `logger`.

**Patterns:**
- Per-module logger: `logger = logging.getLogger(__name__)` — 25 occurrences across 20 modules in `core/`, `ui/`, `ingestion/`, `retrieval/`, `providers/`.
- Prefer lazy `%s` formatting (101 sites) over f-strings (4 sites). The f-string exceptions are all in `core/summarizer.py:500`, `:561`, `:564`, `:590`; new code should use `%s`.
- Include the identifier and the failure in the message: `logger.warning("Could not load visual evidence for %s: %s", doc_id, err)` (`core/summarizer.py:207`).
- Add `exc_info=True` when the stack trace matters (unexpected/IO failures in `ui/hydration.py:43`, `:107`, `:216`); use plain messages for expected optional-capability gaps (`core/resource_telemetry.py:87-190`).
- Levels: `info` for lifecycle milestones (migrations, cache hits, summaries persisted), `warning` for degraded/retryable conditions, `error` for failed hydration/repair, `debug` for optional telemetry and cleanup.
- Log messages must not contain credentials; errors crossing UI boundaries are scrubbed by `core/redaction.py` (`redact_text`).

## Function Design

**Size:** Small, single-purpose helpers with a docstring; orchestration lives in service classes (`ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/chat_controller.py`) rather than in the Streamlit renderers. Large renderers (`ui/views.py:render_chat_view`) delegate to helpers.

**Parameters:**
- Explicit, typed parameters over `**kwargs`; sentinel options are keyword-only after `*`:
  - `def delete_document(self, doc_id: str, *, record_tombstone: bool = False) -> bool:` (`core/doc_store.py:824`)
  - `def __init__(self, validator: CitationValidator, *, k: int = 8) -> None:` (`ui/chat_controller.py:76`)
  - `def configure_logging(level=None, log_dir=None, *, enable_file: bool = True, force: bool = False)` (`core/logging_setup.py:57-63`)
- Defaults are conservative and local-first (`temperature: float = 0.2`, `max_tokens: int = 1024`, `timeout: float = 60.0`).

**Return values:**
- Typed returns including `None` explicitly (`-> Path | None`, `-> bool`, `-> list[Chunk]`).
- Mutators return `None`; persistence/domain lookups return models or typed lists (`Document`, `list[Chunk]`). Retrieval APIs are the deliberate exception: `search_dense`, `search_fts`, and `search_hybrid` return `list[dict[str, Any]]` rows with `score`/`chunk_id`/`doc_id` metadata (`retrieval/hybrid_retriever.py:718-723`, `:918-923`).
- Generators are annotated `Generator[str, None, None]` for streaming (`providers/model_provider.py:106`, `core/local_llm.py`).
- Factory/composition roots return constructed services: `get_doc_store()`, `get_session_ai_model()` (`main.py:144`, `:201`).

**Resource management:**
- Providers implement `close()` plus context-manager protocol (`providers/model_provider.py:67-75`), and `tests` call `provider.close()` after each case.
- Context managers wrap stateful critical sections: `@contextmanager def hold(...)` for `InferenceGate` (`core/local_llm.py:82`), `@contextmanager def _connect(...)` for SQLite (`core/doc_store.py:168`), `@contextmanager def track_stage(...)` in `core/resource_telemetry.py:250`.
- All GPU-touching calls must acquire `InferenceGate.hold(timeout=60.0)`; this is a hard architectural convention, tested in `tests/test_concurrency_lock.py`.

## Module Design

**Exports:**
- Absolute imports of concrete modules; no deep re-export chains. `ui/__init__.py` is the only barrel and exposes exactly one symbol:
  ```python
  """UI package for AMOLED minimal PDF intelligence workspace."""

  from ui.sanitizer import sanitize_markdown_for_local

  __all__ = ["sanitize_markdown_for_local"]
  ```
- Package `__init__.py` files carry a one-line docstring and `__version__ = "1.0.0"` (`core/`, `ingestion/`, `retrieval/`, `providers/`). Do not add new `__all__` re-exports without a reason; import from the defining module.
- Protocols describe narrow callable seams instead of importing concrete services: `CitationValidator(Protocol)` in `ui/chat_controller.py:23-30` keeps the controller Streamlit-free and testable.

**Layering (enforce when adding modules):**
- `ui/*` may import `core/*`, `retrieval/*`, `providers/*`, `ingestion/*` — never the reverse.
- `ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, and `ui/sanitizer.py` must not import Streamlit; they receive session/state through arguments or callbacks. Streamlit-dependent modules are limited to `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/session_state.py`, and `ui/hydration.py` (which reads/writes `st.session_state` during startup repair).
- UI never writes database records directly; ingestion goes through `IngestionService`, deletes/purge/re-index through `LifecycleService`.
- Domain models live only in `core/models.py`; provider contracts only in `providers/model_provider.py`.

**Session state:**
- Reads via `st.session_state.get(...)`; teardown centralized in `reset_in_memory_session()` (`ui/session_state.py`). Never duplicate reset logic in a view.
- Upload processing rotates `st.session_state.uploader_key` after each batch to prevent Streamlit's re-run loop (`main.py`, `ui/views.py`; regression test `tests/test_main_ui.py:537`).
- Cache summaries under `summary_<doc>_<profile>_<model_version>` keys built by `summary_session_key()`; never ad-hoc string keys.

**Do not:**
- Do not add a dependency for parsing/validation that Pydantic or the standard library already covers (privacy/no-new-dependencies constraint, documented in `ui/sanitizer.py:6-11`).
- Do not introduce relative imports, `sys.path` hacks, or a second formatting tool.
- Do not bypass `InferenceGate`, `redact_text`, or `sanitize_markdown_for_local` on the paths where they are required.

---

*Convention analysis: 2026-10-28*
