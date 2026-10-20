# Coding Conventions

**Analysis Date:** 2026-10-21

## Naming Patterns

**Files:**
- Root application modules: flat `snake_case.py` named after the domain noun, no package nesting: `doc_store.py`, `hybrid_retriever.py`, `local_llm.py`, `models.py`, `visual_analyzer.py`, `summarizer.py`, `resource_telemetry.py`, `citation_validator.py`, `prompt_budget.py`.
- Presentation package: `ui/` with responsibility-suffixed modules: `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`, `ui/hydration.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`.
- Tests: `tests/test_<module_or_feature>.py` mirroring the production module name (`tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_ui_smoke.py`).
- Synthetic fixtures: `tests/data/corpus/generate_corpus.py` with generated `.pdf` files beside it.

**Classes:**
- `PascalCase`, noun-first: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`, `Summarizer`, `CitationVerificationResult`, `PromptBudget`-style helpers.
- Service classes end in `Service` when they orchestrate a workflow (`ui/ingestion_service.py`, `ui/lifecycle_service.py`).
- Exception-free result containers use `...Result` (`IngestionResult` in `ui/ingestion_service.py`, `CitationVerificationResult` in `citation_validator.py`) or Pydantic `...Result`/`...Status` models (`RetrievalResult`, `SummaryResult`, `HealthStatus` in `models.py` / `model_provider.py`).

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `validate_pdf_bytes`, `assemble_grounded_messages`, `compute_rrf`, `should_ocr_page`.
- Private helpers use a single leading underscore: `_connect`, `_apply_migrations`, `_escape_sql_literal`, `_report`, `_embed_one`, `_has_lancedb`.
- UI renderers are `render_<area>_<thing>` and return `None` or an HTML string: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`, `render_status_pill`, `render_citation_chip`, `render_empty_state`.
- Getters use `get_` (`get_svg_icon`, `get_capabilities`, `get_gpu_memory_info`); predicates use `is_`/`has_`/`should_` (`is_locked`, `has_document`, `should_ocr_page`).

**Variables and constants:**
- Module-level constants are `UPPER_SNAKE_CASE`: `CONFIG_VERSION`, `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `MAX_FILE_MB`, `MAX_PAGES`, `MAX_CHAT_TURNS`, `FAST_PATH_TOKEN_LIMIT`, `MAX_BATCH_TOKENS`, `CORPUS_DIR`, `CHART_PDF`.
- Theme tokens are `COLOR_*` (`ui/theme.py:6-15`).
- `snake_case` locals; single-letter names only for tight loops (`f`, `p`, `s`, `c`) or math (`k_rrf`).
- Typed module-level aliases for domain unions: `SummaryProfile = Literal[...]` (`models.py:208`).

**Types:**
- Pydantic v2 models in `models.py` are the canonical schema boundary; use `ConfigDict(frozen=True, extra="forbid")` for immutable value objects (see `BBox`, `Chunk`, `EvidenceSnippet`, `RetrievalResult`) and `extra="forbid"` for mutable records (`Page`, `Document`, `SummaryResult`).
- Cross-field invariants use `@model_validator(mode="after")` returning `"Self"`-style quoted annotations (`models.py:47`, `models.py:135`).
- Internal (non-boundary) result containers use `@dataclass`: `IngestionResult` (`ui/ingestion_service.py:23`) and `ValidatedUpload` (`upload_validation.py:51`, frozen).

## Code Style

**Formatting:**
- Ruff, configured in `pyproject.toml`:
  - `line-length = 120`
  - `target-version = "py311"`
  - `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`
- CI enforces both lint and format: `ruff check .` and `ruff format --check .` (`.github/workflows/ci.yml:33-36`).
- 4-space indentation, double quotes, trailing commas in multi-line calls, multi-line argument lists with one arg per line when the call is long.
- Long string concatenation uses implicit adjacent literals inside parentheses rather than `+` (see `ui/components.py:55-62`).
- No `from __future__ import annotations` in application modules; only `start.py:8` and `setup.py:14` use it. PEP 604 unions (`str | None`) and builtin generics (`list[dict[str, Any]]`) are used directly.

**Linting:**
- Rule selection is intentionally minimal: `select = ["E", "F", "W"]` with `ignore = ["E501", "W291", "W293"]` (`pyproject.toml:12-14`). E501 is ignored even though `line-length` is 120, so line length is soft and `ruff format` governs wrapping.
- `scripts/*` is exempted from `E402` (module-level imports after code) via per-file ignores (`pyproject.toml:16-17`).
- Optional native/SDK imports are guarded and assigned `None` with explicit `# type: ignore[...]` rather than being wrapped in lazy imports:
  ```python
  try:
      import lancedb
      import pyarrow as pa
  except ImportError:
      lancedb = None  # type: ignore[assignment]
      pa = None  # type: ignore[assignment]
  ```
  (`hybrid_retriever.py:22-28`; same pattern in `docling_reader.py:27-32`, `groq_provider.py:14-15`, `litellm_provider.py:25-26`, `ocr_fallback.py:27-32`).

## Import Organization

**Order:**
1. Standard library (`from collections.abc import Generator`, `from contextlib import contextmanager`, `import json`, `import logging`, `from pathlib import Path`, `import sqlite3`, `from typing import Any`).
2. Blank line, then third-party (`pydantic`, `streamlit`, `httpx`, `numpy`, `pytest`).
3. Blank line, then local flat modules (`from doc_store import DocStore`, `from models import Chunk, Document`) and `ui.*` modules.

Within a group, `from X import Y` statements precede plain `import X` statements and each subgroup is alphabetized — visible in `doc_store.py:9-15`, `local_llm.py:8-21`, `hybrid_retriever.py:8-18`. Tests typically do stdlib/third-party first (`from unittest.mock import MagicMock`, `import pytest`) then application imports (`tests/test_hybrid_retriever.py:3-9`).

**Path Aliases:**
- None. All imports are absolute module names from the repository root (`from ui.sanitizer import sanitize_display_markdown`). There is no `src/` layout and no `sys.path` manipulation in application code; tests rely on pytest's rootdir insertion.
- `ui/__init__.py` re-exports only the sanitizer: `__all__ = ["sanitize_markdown_for_local"]`.

## Error Handling

**Patterns:**
- **Domain validation raises `ValueError`.** Model validators and input parsers fail loudly with the offending value in the message: `raise ValueError(f"Invalid sha256 digest: {sha256!r}")` (`models.py:29`), `raise ValueError(f"Invalid BBox coordinates: ...")` (`models.py:50`).
- **Type guards raise `TypeError` with the actual type.** `DocStore` validates every public write: `raise TypeError(f"Expected Document instance, got {type(doc).__name__}")` (`doc_store.py:174`).
- **Consent violations raise `PermissionError`.** Cloud egress is blocked at the provider boundary: `raise PermissionError(...)` in `litellm_provider.py:145`; tested at `tests/test_cloud_privacy.py:34`.
- **Provider/transport failures are wrapped in `RuntimeError` with `from exc`.** `llama_cpp_provider.py` raises `RuntimeError("llama-server generation failed ...")`; `litellm_provider.py:239` raises `RuntimeError(f"Cloud provider generation error ({self.model_name}): {scrubbed}") from err`. Secrets are scrubbed before inclusion.
- **Missing capability raises `NotImplementedError`**, e.g. `GroqProvider.analyze_image` (`groq_provider.py:170`) and text-only cloud vision (`litellm_provider.py:322`).
- **Concurrency timeout raises `TimeoutError`** from `InferenceGate.hold` (`local_llm.py:84`); callers may instead poll `InferenceGate.acquire(...)` and degrade gracefully.
- **Orchestration services return result objects instead of raising.** `IngestionService.ingest_pdf` catches per-stage failures and returns `IngestionResult(success=False, error=...)` (`ui/ingestion_service.py:80-91`, `256-266`, `283-309`). UI code checks `result.success`/`result.error`; it does not wrap ingestion in try/except.
- **Degrade with fallback at integration boundaries.** LanceDB init failure switches to `VectorIndex` (`hybrid_retriever.py:121-130`); Docling failure falls back to `PdfReader` (`docling_reader.py:312-313`); OCR/visual/cache failures are logged and skipped so the rest of the document still indexes (`ui/ingestion_service.py:207-208`, `321-322`).
- **Cleanup uses `try/finally`.** `DocStore._connect` closes the connection in `finally` (`doc_store.py:146-149`); `InferenceGate.hold` releases in `finally` (`local_llm.py:87-90`); provider `close()` is idempotent.
- **Deliberate swallow-and-continue only in cleanup/probe paths**, always with `pass` and a narrow scope: closing a retriever in `main.py:64-67`, re-writing failure status in `ui/ingestion_service.py:299-300`, `InferenceGate.release` catching `RuntimeError` (`local_llm.py:62-63`).

**Rules to follow when adding code:**
- Do not introduce custom exception classes; the codebase uses stdlib exception types plus result objects.
- Never let a raw traceback reach Streamlit. Catch at the service boundary, log with context, return a typed result or a status pill.
- Never include API keys or user document text in exception messages or logs. Scrub with the project's `_scrub`-style helper before raising (`litellm_provider.py`).
- Re-raise with `from err` to preserve the chain.

## Logging

**Framework:** stdlib `logging`, no third-party logger.

**Patterns:**
- Every module that logs declares `logger = logging.getLogger(__name__)` immediately after imports (`local_llm.py:23`, `hybrid_retriever.py:20`, `ui/ingestion_service.py:20`, `ui/views.py:31`, `main.py:38`).
- Lazy `%s` formatting, never f-strings in log calls: `logger.warning("Failed to initialize LanceDB at %s: %s. Using in-memory fallback.", self.db_uri, err)` (`hybrid_retriever.py:128`).
- Level usage:
  - `logger.info` for lifecycle milestones (loaded chunks, connected index, migration applied).
  - `logger.warning` for recoverable degradation (fallback to in-memory, cache write failure, visual analysis warning).
  - `logger.error` for persistence/indexing failures that abort a stage (`ui/ingestion_service.py:257`, `hybrid_retriever.py:372`).
  - `logger.debug` for third-party index notices (`hybrid_retriever.py:347`, `370`).
- CLI entry points (`start.py`, `setup.py`, `scripts/*`) use `print()` with emoji status markers and write errors to `sys.stderr`; do not copy this into library modules.
- Streamlit watcher noise is filtered centrally by `logging_setup.suppress_torch_classes_scan_warning()` (`logging_setup.py:31-47`), called once from `main.py:41`. Add new suppression filters there, not at call sites.
- `logging_setup.TorchClassesScanLogFilter` is the model for targeted filters: subclass `logging.Filter`, match on `record.getMessage()`, keep it idempotent.

## Comments

**When to Comment:**
- Module docstrings state purpose plus the invariants/requirements enforced, with requirement IDs in parentheses: `"(RETR-01, RETR-02)"` (`hybrid_retriever.py:5`), `"(INF-03)"` (`ui/sanitizer.py:4`), `"(QUAL-01)"` (`local_llm.py:29`). Preserve this convention — it links code to plan requirements.
- Non-obvious tradeoffs are justified inline: why a filter is used instead of `setLevel` (`logging_setup.py:20-22`), why per-operation SQLite connections exist (`doc_store.py:132-140`), why mixed columns are parsed defensively (`docling_reader.py`).
- Orchestration functions use numbered step comments (`# 1. Validation`, `# 2. Deduplication check`, ...) (`ui/ingestion_service.py:78-311`, `summarizer.py:248-397`, `local_llm.py:174-183`).
- `ui/views.py` and `main.py` use banner comments to delimit sections:
  ```python
  # =====================================================================
  # 1. SIDEBAR DOCUMENT MANAGER & INGESTION
  # =====================================================================
  ```
  (`ui/views.py:45-47`, repeated at lines 180, 469, 586, 697).
- Test files use either a module docstring or a banner block:
  ```python
  # ------------------------------------------------------------------
  # Unit Tests for DocStore (doc_store.py)
  # Verifies SQLite persistence, WAL mode, migrations, ...
  # ------------------------------------------------------------------
  ```
  (`tests/test_doc_store.py:1-5`; also `tests/conftest.py:1-4`, `tests/data/corpus/generate_corpus.py:1-4`).

**JSDoc/TSDoc:** Not applicable (Python).

**Docstrings:**
- Every public module, class, and function has a docstring. Module docstrings are one-paragraph summaries; class docstrings state responsibility.
- Public methods with parameters use Google style `Args:` / `Returns:` / `Raises:` / `Yields:` with no type repetition: `cache_dir_for` (`models.py:17-30`), `compute_rrf` (`hybrid_retriever.py:45-58`), `assemble_grounded_messages` (`prompt_budget.py:65-78`), `BaseModelProvider.stream_text` (`model_provider.py:107-119`).
- Tiny UI/helper functions get a one-line imperative docstring (`ui/components.py:14`, `52`, `86`; `ui/sanitizer.py:33`).
- Abstract interface methods in `model_provider.py` document contracts, not implementations.

## Function Design

**Size:** No hard limit. Orchestration functions are long (80–200 lines) but are structured as numbered stages with early returns; keep each stage independently skippable. Small pure helpers live at module level (`_escape_sql_literal`, `compute_rrf`, `extract_page_references`, `estimate_tokens`, `sanitize_xml_boundary`).

**Parameters:**
- Keyword-friendly signatures with defaults; booleans default to the safe/local behavior (`cloud_mode: bool = False` in `local_llm.py:107`; `allow_external: bool = False` in `ui/sanitizer.py:33`).
- Dependency injection for testability: services and analyzers accept optional collaborators in `__init__` (`IngestionService.__init__` takes `doc_store`, `hybrid_retriever`, `local_embedding`, `cache_dir`; `VisualAnalyzer` takes `region_detector` and `cropper`; `HybridRetriever` takes `embedding_fn`). Add new external dependencies this way instead of importing globals inside functions.
- Callback parameters end in `_callback` and are optional (`progress_callback: Callable[[str], None] | None = None` in `ui/ingestion_service.py:59`).
- Providers receive explicit `transport` for tests (`LlamaCppProvider(transport=transport)` in `tests/test_llama_cpp_provider.py`).

**Return Values:**
- Single typed return on every public function, including `-> None` on renderers and mutators.
- Generators are annotated with `Generator[T, None, None]` from `collections.abc` (`doc_store.py:133`, `local_llm.py:73`, `model_provider.py:106`).
- Binary success/failure returns `bool` (`InferenceGate.acquire`); rich outcomes return a dataclass/Pydantic result (`IngestionResult`, `RetrievalResult`, `HealthStatus`).

## Module Design

**Exports:**
- Flat modules, no explicit `__all__` except `ui/__init__.py`. Consumers import specific names: `from models import Chunk, Document`.
- Canonical schemas are centralized in `models.py`; do not define ad-hoc dicts for chunks/documents/pages. Convert legacy dicts with `Chunk.model_validate(...)` at the boundary (`ui/ingestion_service.py:254`).
- Provider implementations subclass `BaseModelProvider` (`model_provider.py:64`) and implement all abstract methods: `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.

**Barrel Files:** Not used. `ui/__init__.py` only re-exports the sanitizer for convenience.

## Project-Specific Conventions

**GPU concurrency (`InferenceGate`):**
- Every LLM/VLM/summarization call must be wrapped in `with InferenceGate.hold(timeout=60.0):` (`local_llm.py:72-90`). This is a hard architectural rule (4 GB VRAM ceiling).
- Preprocessing (Docling, RapidOCR, embeddings) stays on CPU and must not acquire the gate.

**Transactional state mutation:**
- UI components never write database or vector state directly. All ingestion goes through `IngestionService` (`ui/ingestion_service.py`); all deletion/purge/re-index goes through `LifecycleService` (`ui/lifecycle_service.py`).
- Session-state mutation is centralized in `main.py` (`_reset_session_security_state`) and `ui/views.py` (`append_chat_turn`). Any destructive reset must rotate `st.session_state.uploader_key` (`main.py:70`) to avoid Streamlit re-processing cached uploads.

**Privacy boundary:**
- Any Markdown/HTML rendered from documents or model output must pass through `sanitize_display_markdown(...)` (`ui/sanitizer.py:81`). In local mode (`allow_external=False`) external images/links and `<script>`/`<iframe>`/`<object>`/`<embed>`/`<style>` are neutralized.
- Escaped user text rendered into custom HTML uses `html.escape` (`ui/components.py:72`, `91`, `98`).
- Cloud providers require explicit `user_consented=True`; default constructor behavior is local-only (`local_llm.py:104-123`).

**Streamlit rendering:**
- Prefer `st.html(markup)` with a `st.markdown(..., unsafe_allow_html=True)` fallback behind `hasattr(...)` (`ui/components.py:63-66`, `80-83`, `107-110`).
- Theme colors come from `ui/theme.py` tokens; do not hardcode new hex values in views. Existing components do inline styles with the token values (acceptable pattern in `ui/components.py`), while page-level CSS belongs in `THEME_CSS`.
- Zero emojis and local SVG icons only (`assets/icons/`), loaded by `get_svg_icon`.

## Adding New Code

**New inference provider:**
1. Implement `BaseModelProvider` in a new root module `<name>_provider.py` (see `llama_cpp_provider.py`, `groq_provider.py`).
2. Return `ProviderCapabilities` and `HealthStatus`; never raise from `check_health` — map failures to `status="unreachable" | "loading" | "error"`.
3. Accept an injectable transport/client for offline tests.
4. Assign it in `AiModel.set_cloud_mode` / `_detect_provider` (`local_llm.py`) rather than in UI code.

**New UI workspace:**
1. Add `render_<name>_view(...)` to `ui/views.py` in its own banner-delimited section.
2. Reuse `ui/components.py` primitives and `ui/theme.py` tokens.
3. Route from `main.py`; store all cross-rerun state in `st.session_state`.
4. Sanitize any document/model-derived Markdown.

**New persistence field:**
1. Add the field to the Pydantic model in `models.py`.
2. Add a new numbered `SCHEMA_V<n>_DDL` list and register it in `MIGRATIONS` (`doc_store.py:105-110`); never edit an existing migration.
3. Update the `DocStore` read/write mapping and add a round-trip test in `tests/test_doc_store.py`.

**New tests:** See `TESTING.md`; place them in `tests/test_<module>.py` and reuse `tests/conftest.py` fixtures.

---

*Convention analysis: 2026-10-21*
