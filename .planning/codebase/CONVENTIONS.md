# Coding Conventions

**Analysis Date:** 2026-10-29

## Naming Patterns

**Files:**
- Python modules and packages use `snake_case`: `core/citation_validator.py`, `ui/chat_controller.py`, `retrieval/hybrid_retriever.py`, `ingestion/ocr_fallback.py`, `providers/llama_cpp_provider.py`.
- Packages group by responsibility: `core/`, `ui/`, `ingestion/`, `retrieval/`, `providers/`, with `tests/` mirroring modules.
- Tests use `test_<module_or_feature>.py`: `tests/test_doc_store.py`, `tests/test_grounding_contract.py`, `tests/test_ui_redesign_apptest.py`.
- Root entry points are deliberately minimal: `main.py`, `start.py`, `setup.py`.
- Static assets use lowercase names with underscores: `assets/icons/document.svg`, `assets/brand_mark.svg`.
- No JavaScript, TypeScript, or CSS source files. CSS is injected from `ui/theme.py`; SVG markup is read from `assets/icons/`.

**Functions:**
- `snake_case`, verb-first for actions: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `validate_citations`, `auto_attribute_citations`, `assemble_grounded_messages`.
- Private helpers are underscore-prefixed: `_build_report`, `_retrieve`, `_retrieve_document_wide`, `_attribute`, `_execute_write`, `_report_progress`, `_lifecycle_preflight`.
- UI view renderers use `render_<area>` and return `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_diagnostics_view`, `render_sidebar_documents`, `render_file_upload_button` in `ui/views.py`; `render_brand_header`, `render_stat_card`, `render_empty_state`, `render_notifications` in `ui/components.py`.
- Pure markup builders return `str` and are named for the artifact they produce: `render_citation_chip`, `render_chatgpt_citation_pill`, `render_status_pill`, `get_svg_icon`, `get_brand_mark_svg` in `ui/components.py`.
- Provider methods follow the `BaseModelProvider` contract exactly: `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities` in `providers/model_provider.py` and implementations under `providers/`.
- Service methods name the operation, not the layer: `IngestionService.ingest_pdf`, `LifecycleService.delete_document` / `purge_all` / `reindex_document`, `ChatTurnService.prepare` / `finalize` / `error_result` / `intent_mismatch_result` / `abstention_result`.

**Variables:**
- `snake_case`; booleans read as predicates: `is_healthy`, `has_docs`, `has_vectors`, `should_withhold_answer`, `incomplete_context`, `already_indexed`, `fallback_used`.
- Collections are plural nouns: `snippets`, `document_metadata`, `page_records`, `evidence_elements`, `failures`, `cited_ranks`.
- Loop/index variables are short only in local, obvious scopes: `for s in retrieval_result.snippets`, `for p in range(1, pages + 1)`, `k` for top-k.
- Exception variables are `err`, `exc`, or a specific `*_err`: `val_err`, `ext_err`, `ocr_err`, `vis_err`, `sum_err`, `probe_err`.
- Session-state keys use `snake_case`. Internal/transient flags are underscore-prefixed: `_startup_hydrated`, `_active_chat_scope`, `_queued_prompt`, `_scope_switch_index`. User-facing keys are unprefixed: `doc_ids`, `document_metadata`, `chat_history`, `cloud_mode`, `uploader_key`.
- Cache keys encode version dimensions: `summary_<doc_id>_<profile>_<model_version>` in `ui/views.py:summary_session_key`.
- Constants use `UPPER_SNAKE` with explicit types where useful: `DEFAULT_MAX_OUTPUT_TOKENS: int = 1536` in `core/prompt_budget.py`, `SUPPORT_WITHHOLD_THRESHOLD = 0.5` in `core/citation_validator.py`, `INSUFFICIENT_EVIDENCE_MESSAGE` in `core/local_llm.py` and `ui/chat_controller.py`, `MAX_FILE_MB` in `ingestion/upload_validation.py`.

**Types:**
- Classes are `PascalCase` and suffixed by role: `Service`, `Store`, `Reader`, `Provider`, `Gate`, `Analyzer`, `Validator`, `Result`, `Report`, `Status`, `Capabilities`, `Preparation`.
- Pydantic v2 models live in `core/models.py`, `core/citation_validator.py`, and `providers/model_provider.py`: `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `GroundingReport`, `SummaryResult`, `BBox`, `CitationVerificationResult`, `ProviderCapabilities`, `HealthStatus`.
- Immutable value objects use `model_config = ConfigDict(frozen=True, extra="forbid")`; mutable records use `extra="forbid"` only (`Document`, `Page`, `SummaryResult`).
- `Literal` aliases are `PascalCase`: `GroundingStatus` in `core/citation_validator.py`, `SummaryProfile` in `core/models.py`, plus inline `Literal[...]` fields for status/search-mode unions.
- Internal, non-serialized result containers use frozen dataclasses: `ChatTurnPreparation`, `ChatTurnResult` in `ui/chat_controller.py`; `IngestionResult` in `ui/ingestion_service.py`; `RuntimeVersion` in `core/runtime_info.py`; `ModelIdentity` in `core/model_identity.py`.
- Callable injection uses `typing.Protocol`: `CitationValidator` in `ui/chat_controller.py:48` mirrors `AiModel.validate_response`.
- Provider extension uses `abc.ABC` + `@abstractmethod`: `BaseModelProvider` in `providers/model_provider.py:64`.
- Type aliases for callbacks are `PascalCase`: `ProgressCallback = Callable[[int, int, str], None]` in `ui/hydration.py:16`.

## Code Style

**Formatting:**
- Ruff is the single formatter and linter. Configuration is in `pyproject.toml:1-18`.
- `line-length = 120`, `target-version = "py311"`.
- Ruff formatter defaults apply: 4-space indentation, double quotes, trailing commas in multi-line calls, two blank lines between top-level definitions.
- `E501` is ignored, so 120 columns is a soft cap enforced by the formatter rather than by lint.
- `W291` and `W293` (trailing whitespace) are ignored.
- `from __future__ import annotations` is used selectively, not globally: `core/redaction.py`, `ui/chat_controller.py`, `start.py`, `setup.py`, `tests/test_chat_controller.py`, `tests/test_retrieval_semantic.py`.
- Type annotations use PEP 604 and built-in generics everywhere: `str | None`, `list[dict[str, Any]]`, `tuple[str, str, str]`, `dict[str, float] | None`.
- Abstract collections come from `collections.abc`, not `typing`: `Callable`, `Generator`, `Iterable` (e.g. `core/local_llm.py:8`, `core/doc_store.py:9`, `providers/model_provider.py:9`, `ui/chat_controller.py:20`).
- `typing` is reserved for `Any`, `Literal`, `Protocol`, `TypeVar`, and similar typing-only constructs.
- There is no `mypy`, `pyright`, `black`, `isort`, `flake8`, or `pre-commit` configuration in the repository. Ruff is the only enforced style gate.
- No emojis in source, UI copy, or generated markup. The UI uses local monochrome SVGs from `assets/icons/`; `tests/test_ui_redesign_apptest.py` asserts button labels contain no codepoint above `0x1F000`.

**Linting:**
- `ruff check .` selects `["E", "F", "W", "B", "UP", "SIM"]` in `pyproject.toml:13`.
- `ruff format --check .` is run in CI and must pass.
- Per-file ignores: `scripts/*` allows `E402`; `start.py` allows `UP036` (`pyproject.toml:16-18`).
- Ruff excludes `.planning`, `.cache`, `data`, `docs`, and `*.md` from linting (`pyproject.toml:4-10`).
- Broad exception handlers are commonly annotated with a rationale comment, usually `# noqa: BLE001 - <reason>` (e.g. `core/summarizer.py:208`, `ui/views.py:283`, `ui/views.py:1309`). Note that `BLE` is not currently in the selected rule set, so the `noqa` is documentation-by-convention rather than an active suppression.
- Defensive/UI-boundary branches use `# pragma: no cover` (e.g. `ui/hydration.py:30`, `main.py:184`, `core/logging_setup.py:100`). Coverage is not measured, so these markers document intent rather than affect a report.

## Import Organization

**Order:**
1. Module docstring.
2. `from __future__ import annotations` when used.
3. Standard library imports, grouped alphabetically by module: `logging`, `os`, `re`, `uuid`, `from collections.abc import ...`, `from pathlib import Path`, `from typing import ...`.
4. Blank line, then third-party imports: `streamlit`, `pydantic`, `httpx`, `numpy`, `pytest`, `reportlab`, `lancedb`, `pyarrow`.
5. Blank line, then first-party absolute imports: `core.*`, `ui.*`, `ingestion.*`, `retrieval.*`, `providers.*`.
- Imports are absolute, not relative. No `from .models import ...` style is used in application modules.
- Lazy imports are used deliberately to break cycles or avoid loading heavy optional backends:
  - `from ingestion.pdf_reader import PdfReader` inside the extraction fallback in `ui/ingestion_service.py:157`.
  - `import streamlit as st` inside `providers/groq_provider.py:45` to tolerate CLI/test contexts.
  - `from ui.lifecycle_service import LifecycleService` inside tests such as `tests/test_audit_repairs.py:226`.
- Optional third-party dependencies are guarded with `try/except ImportError` and set to `None`, with `# type: ignore[assignment]`: `lancedb`/`pyarrow` in `retrieval/hybrid_retriever.py:25-52`, `pymupdf` in `ingestion/visual_analyzer.py:28-31`, `litellm` in `providers/litellm_provider.py:22-27`, `groq` in `providers/groq_provider.py:13-16`.

**Path Aliases:**
- None. There are no `src` layouts, `PYTHONPATH` aliases, or `@/`-style aliases. The repository root is the import root, and packages are imported by their real names.
- `ui/__init__.py` re-exports only `sanitize_markdown_for_local`; it is not a general barrel. Import submodules directly (`from ui.views import ...`, `from ui.components import ...`).

## Error Handling

**Patterns:**
- **Input/schema validation raises `ValueError`.** Pydantic `@model_validator(mode="after")` methods raise `ValueError` with the offending value (`core/models.py:29`, `:50`, `:112`, `:138`, `:167`, `:283-285`). `cache_dir_for` validates the SHA-256 shape before building a path.
- **Wrong Python types raise `TypeError`.** `DocStore` rejects non-model arguments with messages such as `"Expected Document instance, got ..."` (`core/doc_store.py:252`, `:350`, `:388-396`, `:544`, `:565`, `:616`, `:635`, `:687`). `VectorIndex` raises `TypeError` for non-dict documents and non-list vectors (`retrieval/vector_index.py:53-59`, `:77-81`).
- **Domain failures use a custom exception where callers must distinguish them.** `VectorIndexError(RuntimeError)` is defined in `retrieval/hybrid_retriever.py:75` and documents that callers must treat it as a failed ingestion/re-index, never as success.
- **Backend/transport failures raise `RuntimeError` with `from exc`.** Examples: `providers/llama_cpp_provider.py:237`, `:301`, `:364`; `providers/litellm_provider.py:238`, `:295`; `providers/groq_provider.py:147`, `:184`.
- **Consent violations raise `PermissionError`.** Cloud providers refuse generation without explicit consent (`providers/groq_provider.py:68`, `providers/litellm_provider.py:144`), and `AiModel` re-raises the same class at its boundary (`core/local_llm.py:143`, `:198`, `:226`).
- **Gate contention raises `TimeoutError`.** `InferenceGate.hold` raises `TimeoutError` when it cannot acquire within the timeout (`core/local_llm.py:101-105`).
- **Unsupported operations raise `NotImplementedError`.** Non-vision cloud models reject `analyze_image` (`providers/groq_provider.py:194`, `providers/litellm_provider.py:321`).
- **Pipeline stages isolate failures instead of aborting the document.** `IngestionService.ingest_pdf` catches validation/extraction failures and returns `IngestionResult(success=False, error=...)`; OCR and visual-analysis failures are logged as warnings and processing continues (`ui/ingestion_service.py:80-91`, `:147-173`, `:177-210`).
- **Storage mutations fail loudly.** `LifecycleService.delete_document` deletes vectors first and re-raises on failure so SQLite is not mutated into an inconsistent state (`ui/lifecycle_service.py:46-56`). `purge_all` collects tier failures, still clears session state, then raises `RuntimeError("Purge incomplete — ...")` (`ui/lifecycle_service.py:104-159`).
- **Deferred cleanup uses tombstones rather than silent loss.** When no retriever is available, deletion records a vector-cleanup tombstone; `ui/hydration.py:34-60` retries tombstones on next startup and keeps them if the purge fails.
- **UI boundaries catch, redact, and surface.** `ui/views.py` wraps lifecycle and summarization operations in `try/except Exception`, logs with `logger.exception(...)`, and displays `redact_text(str(err))` (`ui/views.py:171-267`, `:972`). Provider errors are scrubbed with `redact_text` before display/persistence (`providers/groq_provider.py:146`, `providers/litellm_provider.py:139`, `ui/chat_controller.py:444`).
- **No bare `except:`.** Broad catches are `except Exception` and are confined to boundaries (UI, optional enrichment, teardown). Narrow catches are used for expected operational failures: `sqlite3.OperationalError` for busy retries (`core/doc_store.py:211-219`), `OSError` for cache cleanup (`ui/lifecycle_service.py:75`), `(OSError, RuntimeError, ValueError, TypeError)` for deferred vector purge (`ui/hydration.py:58`).
- **Retries are bounded and targeted.** `DocStore._execute_write` retries only SQLITE_BUSY/LOCKED up to 3 attempts with exponential backoff plus jitter; non-busy errors re-raise immediately (`core/doc_store.py:189-219`).

## Logging

**Framework:** Python standard library `logging`. There is no Loguru, structlog, or third-party logging dependency.

**Patterns:**
- Every application module declares a module-level logger immediately after imports and constants:
  ```python
  import logging

  logger = logging.getLogger(__name__)
  ```
  Present in `main.py:53`, `core/citation_validator.py:16`, `core/doc_store.py:21`, `core/local_llm.py:28`, `core/summarizer.py:21`, `ui/views.py:36`, `ui/ingestion_service.py:20`, `ui/lifecycle_service.py:14`, `ui/hydration.py:13`, `ui/session_state.py:15`, all `ingestion/*` modules, both retrievers, and all providers.
- `main.py` installs the single application configuration before startup work: `configure_logging(log_dir=LOG_DIR)` (`main.py:51`). `core/logging_setup.py` installs one stderr handler plus an optional rotating file handler at `data/logs/app.log`, controlled by `RAG_LOG_LEVEL` and `RAG_LOG_DIR`. It is idempotent and marks its own handlers with `_rag_logging_handler`.
- Use lazy `%s` formatting, never f-strings in log calls: `logger.warning("OCR processing warning: %s", ocr_err)` (`ui/ingestion_service.py:187`), `logger.info("Successfully deleted document %s (%s)", doc_id, filename)` (`ui/lifecycle_service.py:101`).
- Level conventions:
  - `logger.info` for lifecycle/progress milestones (`ui/ingestion_service.py:76`, `ui/lifecycle_service.py:101`).
  - `logger.warning` for recoverable degradation or best-effort cleanup (`ui/lifecycle_service.py:77`, `ui/hydration.py:43`, `core/local_llm.py:74`).
  - `logger.error` with `exc_info=True` for storage/security failures that must be diagnosable (`ui/lifecycle_service.py:55`, `:120`, `:129`).
  - `logger.debug` for benign teardown failures (`core/logging_setup.py:101`, `ui/hydration.py:31`).
- CLI launchers (`start.py`, `setup.py`) intentionally use `print()` for operator-facing output; `core/logging_setup.py:5-9` documents this split.
- Credentials are never logged raw. Error text crosses provider/UI/log boundaries through `redact_text` from `core/redaction.py`, which scrubs known token formats, bearer tokens, key/value pairs, and named environment secrets.
- The Streamlit `torch.classes` watcher traceback is suppressed by a narrow `logging.Filter`, not by raising the global log level (`core/logging_setup.py:146-177`, `main.py:56`).

## Comments

**When to Comment:**
- Comments explain **why**, invariants, and failure modes, not line-by-line mechanics. Strong examples:
  - Vector-before-SQLite deletion ordering in `ui/lifecycle_service.py:46-48`.
  - Why summary requests must not fall back to unscoped retrieval in `ui/chat_controller.py:169-172`.
  - Why VLM descriptions are excluded from pages that already have text in `ui/chat_controller.py:682-687`.
  - Why rank validity and claim support are separate gates in `core/citation_validator.py:20-23`.
  - Why the SQLite retry policy exists in `core/doc_store.py:25-28`.
  - Why `AppTest` needs an absolute path in `tests/test_ui_redesign_apptest.py:34-35`.
- Security and resource-bound comments are explicit: untrusted-PDF raster budgets (`ingestion/ocr_fallback.py:24-35`, `ingestion/visual_analyzer.py:20-26`), XML boundary neutralization (`core/prompt_budget.py:54-68`), local-only egress (`ui/sanitizer.py:1-11`), cloud consent (`providers/litellm_provider.py:1-6`).
- Thresholds and magic numbers carry a rationale. `core/citation_validator.py:24-34` explains the support/withhold/auto-attribution thresholds and the regression that motivated them. `core/prompt_budget.py:13-17` explains why `DEFAULT_MAX_OUTPUT_TOKENS` is a single value.
- Section banners are used in large modules and tests to group related logic: `# ---- ... ----` in `core/citation_validator.py`, `tests/test_doc_store.py`, `tests/test_models.py`, `tests/test_runtime_info.py`, `tests/test_retrieval_semantic.py`.
- Avoid commented-out code and temporal narration. Comments describe current invariants, not “old behavior” except when naming the regression that a guard prevents.

**JSDoc/TSDoc:**
- Python docstrings, not JSDoc. Every application module starts with a `"""..."""` module docstring stating purpose and key invariants (e.g. `core/models.py:1-6`, `core/local_llm.py:1-6`, `core/citation_validator.py:1-7`, `ui/chat_controller.py:1-14`, `ui/sanitizer.py:1-11`, `retrieval/hybrid_retriever.py:1-6`, `providers/model_provider.py:1-6`).
- Public classes and public methods use Google-style `Args:`, `Returns:`, and `Raises:` sections, without repeating types already in the signature. Examples: `core/doc_store.py:155-161`, `core/local_llm.py:47-56`, `core/summarizer.py:177-202`, `providers/model_provider.py:77-119`, `ui/ingestion_service.py:54-71`, `ui/lifecycle_service.py:32-41`.
- Private helpers use one-line docstrings unless a non-obvious invariant needs explanation (`core/citation_validator.py:303`, `ui/chat_controller.py:107-114`, `ui/hydration.py:19-25`).
- Module docstrings frequently name the requirement IDs they satisfy (`RETR-01`, `QA-03`, `INF-04`, `QUAL-01`, `VIS-01`) and the prior failure they guard against. This is a project convention for traceability.
- Legacy exceptions: `ingestion/pdf_reader.py` has no module docstring and uses informal inline comments/docstrings; `retrieval/vector_index.py` has a good module docstring but several public methods lack return annotations. New code should follow the modern pattern, not these outliers.

## Function Design

**Size:**
- Prefer small, single-purpose helpers and extract multi-step orchestration into services. `ChatTurnService` is the model: `prepare`, `finalize`, `error_result`, `intent_mismatch_result`, `abstention_result`, plus private `_retrieve`, `_retrieve_document_wide`, `_attribute`, `_detect_document_mention` (`ui/chat_controller.py`).
- Long UI renderers are the main exception: `ui/views.py` is 1,548 lines, with `render_chat_view` roughly 380 lines, `render_summarizer_view` roughly 150, `render_library_view` roughly 145, and `render_settings_view` roughly 190. New orchestration logic should go into `ui/chat_controller.py`, `ui/ingestion_service.py`, or `ui/lifecycle_service.py` rather than growing these functions.
- Prefer one responsibility per private helper and return early for invalid/empty inputs (e.g. `ui/chat_controller.py:_retrieve`, `_retrieve_document_wide`).

**Parameters:**
- Multi-argument service methods use keyword-only parameters after `*` to prevent positional mistakes: `ChatTurnService.prepare(...)` and `finalize(...)` (`ui/chat_controller.py:138-147`, `:258-268`), `IngestionService.ingest_pdf` uses explicit names but its callers pass keywords.
- Optional collaborators default to `None`: `hybrid_retriever: HybridRetriever | None = None`, `local_embedding: LocalEmbedding | None = None`, `cache_dir: Path | None = None`.
- Callbacks are typed `Callable[...] | None` and invoked only after a `None` check: `progress_callback: Callable[[str], None] | None` (`ui/ingestion_service.py:59`), `on_response_ready`, `regenerate` (`ui/chat_controller.py:266-267`).
- Avoid boolean flag parameters where a named mode/`Literal` is clearer; `mode="qa"`/`"summary"`, `variant="local"`, and `status: Literal[...]` are preferred.

**Return Values:**
- Return typed models or frozen dataclasses rather than loose dicts at service boundaries: `IngestionResult`, `ChatTurnPreparation`, `ChatTurnResult`, `RetrievalResult`, `SummaryResult`, `GroundingReport`.
- Return `None` for “not found/not available” and document it (`get_session_summary` returns `dict[str, Any] | None`, `DocStore.get_document` returns `Document | None`).
- Return `bool` for success/failure where the caller only needs a yes/no (`LifecycleService.delete_document`, `InferenceGate.acquire`, `VectorIndex.has_document`).
- Return tuples for small multi-value results where a model would be overkill: `_retrieve -> tuple[RetrievalResult | None, list[str]]`, `_retrieve_document_wide -> tuple[RetrievalResult | None, list[str], bool]`, `extract_citations -> list[int]`.
- UI renderers return `None`; pure markup/format helpers return `str`.

## Module Design

**Exports:**
- Application packages use absolute imports and do not rely on `__all__` except at explicit public boundaries: `ui/chat_controller.py:731-737` exports `INSUFFICIENT_EVIDENCE_MESSAGE`, `ChatTurnPreparation`, `ChatTurnResult`, `ChatTurnService`, `EvidenceSnippet`; `ui/__init__.py:5` exports `sanitize_markdown_for_local`.
- Most modules expose all public names implicitly; consumers import the specific symbol from the defining module.
- `ui/sanitizer.py:249` keeps a backward-compatible alias `sanitize_display_markdown = sanitize_markdown_for_local`; new code may use either, but `ui/views.py` uses the alias.

**Barrel Files:**
- No general barrel files. `ui/__init__.py` is a narrow re-export only. Do not add a `core/__init__.py` barrel that imports heavy modules; it would load LanceDB, Streamlit, or model backends on package import.
- `tests/__init__.py` exists only to make `tests` a package.

**State Boundaries:**
- **UI must not mutate persistence directly.** `ui/views.py` may perform read-only queries (`doc_store.get_document`, `get_summary`, `list_documents`, `count_documents`, `count_summaries`) for rendering, but all writes go through services:
  - Ingestion: `IngestionService.ingest_pdf` in `ui/ingestion_service.py:39`.
  - Deletion/purge/re-index: `LifecycleService` in `ui/lifecycle_service.py:17`.
  - Chat turn orchestration: `ChatTurnService` in `ui/chat_controller.py:131`; it deliberately does not import Streamlit.
  - Summarization: `Summarizer.summarize_document` in `core/summarizer.py:174`; the view invokes it and caches the returned model.
- `ui/views.py` owns Streamlit session state and widgets; services accept `session_state` as an optional dict-like argument and synchronize it after storage operations (`LifecycleService.delete_document(..., session_state=...)`, `purge_all(..., session_state=...)`).
- `ui/hydration.py` rebuilds the session catalog and repairs missing vectors at startup; it is the only place that should rehydrate persisted documents into session state.
- **GPU concurrency:** every LLM generation, VLM image analysis, and summarization call must acquire `InferenceGate.hold(timeout=...)` or `InferenceGate.acquire(...)`. Observed call sites: `core/local_llm.py:356`, `:394`, `core/summarizer.py:569`, `ingestion/visual_analyzer.py:290`. Do not call a provider directly from a new path without the gate.
- **Grounding contract:** `ui/chat_controller.py` returns a `GroundingReport` with the request id, scope, document IDs, evidence count, citations, verification status/reason, and incomplete-context flag. UI source chips and grounding labels must be rendered from this report, not reconstructed from a separate retrieval result.
- **Session reset:** use `ui/session_state.py:reset_in_memory_session` rather than duplicating teardown. It clears documents, retrieval state, chat history, provider credentials, consent flags, and rotates `uploader_key`.
- **Upload loop prevention:** rotate `st.session_state.uploader_key` after processing uploads and only count freshly ingested files (`new_docs_indexed`) in `ui/views.py:process_uploaded_files`.

## Recent Working-Tree Conventions

The current working tree contains a large, uncommitted UI/grounding refactor. These patterns are the ones new code should follow:

- **`ui/chat_controller.py`** (heavily modified; 471 changed lines in the working-tree diff) now owns scope resolution, QA vs. document-wide summary selection, bounded regeneration, and citation verification. It imports no Streamlit, uses frozen dataclasses and a `Protocol` for the validator, and exposes `GroundingReport` as the single request/result contract. Its module docstring states the contract explicitly (`ui/chat_controller.py:1-14`).
- **`core/citation_validator.py`** (modified) separates rank validity from claim support. It adds the `GroundingStatus` `Literal`, `support_verified`, `uncited_claim_count`, `uncited_unsupported_count`, and `grounding_status` fields, with threshold constants and rationale comments. Tests pin the distinction in `tests/test_grounding_contract.py`.
- **`ui/theme.py`** (modified) centralizes AMOLED design tokens as module constants (`COLOR_BG`, `COLOR_SURFACE`, `COLOR_ELEVATED`, `COLOR_BORDER`, `COLOR_PRIMARY`, `COLOR_SECONDARY`, `COLOR_TEXT_PRIMARY`, `COLOR_TEXT_MUTED`, `COLOR_DANGER`, `COLOR_WARNING`) and builds `THEME_CSS` as an f-string. Comments explain Streamlit-version-specific selectors (e.g. avatar test-id rename).
- **`ui/views.py`** (modified) adds boundary comments for document switching, duplicate-submit guarding, evidence display, and cache versioning. `runtime_details()` and `render_diagnostics_view()` are new diagnostics renderers. Long render functions remain; extract new logic into services.
- **`tests/test_grounding_contract.py`** and **`tests/test_retrieval_semantic.py`** are new regression suites. They use module docstrings that name the failure being pinned, deterministic local helpers, and no GPU/network. This is the preferred style for new regression tests.
- **`tests/test_ui_redesign_apptest.py`** (modified) uses `streamlit.testing.v1.AppTest` with an absolute path to `main.py`, `default_timeout=45`, monkeypatched `AiModel.check_health`/`get_capabilities`, `assert not at.exception`, and explicit no-emoji assertions.

---

*Convention analysis: 2026-10-29*
