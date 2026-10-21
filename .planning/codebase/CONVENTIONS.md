# Coding Conventions

**Analysis Date:** 2026-10-21

## Naming Patterns

**Files:**
- Production modules are `snake_case` and named for a single responsibility: `core/doc_store.py`, `retrieval/hybrid_retriever.py`, `ingestion/ocr_fallback.py`, `ui/ingestion_service.py`.
- Package roots are short nouns: `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`. Each has an `__init__.py` with a one-line package docstring and `__version__ = "1.0.0"` (`core/__init__.py`, `retrieval/__init__.py`, `ingestion/__init__.py`, `providers/__init__.py`). `ui/__init__.py` additionally re-exports `sanitize_markdown_for_local` via `__all__`.
- Root entry points are minimal and verb/role named: `main.py` (Streamlit composition root), `start.py` (launcher), `setup.py` (installer/packaging CLI).
- Test files are `tests/test_<production_module_or_feature>.py` (e.g. `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`).
- Test data lives under `tests/data/corpus/` with descriptive names (`clean_digital.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`).

**Functions:**
- `snake_case`, verb-first: `ingest_pdf`, `validate_pdf_bytes`, `index_chunks`, `analyze_visual_elements`, `hydrate_startup_state`.
- Private helpers are prefixed with `_`: `_connect`, `_apply_migrations`, `_build_chunks_schema`, `_escape_sql_literal`, `_replace_md_img`, `_make_unit_vector` (tests).
- UI renderers follow `render_<area>` and return `None`: `render_sidebar_documents`, `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view` in `ui/views.py`.
- Pure HTML-string producers are `get_*` / `render_*` returning `str` so they can be unit-tested without a browser: `get_svg_icon`, `get_brand_mark_svg`, `render_status_pill`, `render_citation_chip` in `ui/components.py`.
- Boolean predicates read as questions: `is_available`, `is_locked`, `should_ocr_page`, `has_document`, `is_abstention`, `safe_has_secret`.

**Variables:**
- `snake_case`. Module-level constants are `UPPER_SNAKE_CASE`: `MAX_FILE_MB = 50`, `MAX_PAGES = 500` (`ingestion/upload_validation.py`), `CONFIG_VERSION` (`core/models.py`), `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS` (`core/summarizer.py`), `DEFAULT_RRF_K = 60` (`retrieval/hybrid_retriever.py`).
- Module-private mutable state is `_UPPER_SNAKE` with an explicit lock when shared: `_MODEL_CACHE` (`retrieval/local_embedding.py`), `_LATENCY_HISTORY`, `_GPU_CACHE_TTL_SECONDS`, `_GPU_CACHE_LOCK` (`core/resource_telemetry.py`).
- `InferenceGate` class-level shared state: `_lock`, `_active_threads`, `_state_lock` (`core/local_llm.py`).

**Types:**
- `PascalCase` classes: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `Summarizer`, `VisualAnalyzer`, `IngestionService`, `LifecycleService`.
- Pydantic v2 models live in `core/models.py` (`Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`) and `providers/model_provider.py` (`ProviderCapabilities`, `HealthStatus`), plus `core/citation_validator.py` (`CitationVerificationResult`).
- Result/value containers also use frozen dataclasses where Pydantic validation is unnecessary: `ValidatedUpload` (`ingestion/upload_validation.py`), `IngestionResult` (`ui/ingestion_service.py`).
- String enums are modeled as `Literal[...]` unions rather than `Enum` classes: `Literal["ok", "empty", "failed"]` (`Page.status`), `Literal["hybrid", "dense", "fts", "fallback"]` (`RetrievalResult.search_mode`), `SummaryProfile = Literal[...]` (`core/models.py`).

**Tests:**
- Test functions are `test_<behavior>_<condition>`, often documenting the requirement or bug ID in the name: `test_doc_id_for_invalid_sha_rejected`, `test_two_instance_interleave_R1` (`tests/test_doc_store.py`), `test_corrupt_invalid_rejected_WR07` (`tests/test_upload_validation.py`).
- Test helper fixtures are nouns: `mock_llama_provider`, `mock_sentence_transformer`, `sample_pdf_path` (`tests/conftest.py`); `clean_session_state`, `ensure_gate_released`, `reset_latencies` (module-local autouse fixtures).
- Mock provider classes are `Mock<Role>Provider` / `Dummy<Role>Provider`: `MockLlamaCppProvider`, `MockVisionProvider`, `MockTextOnlyProvider`, `MockSummarizerProvider`, `DummyProvider`.

## Code Style

**Formatting:**
- Ruff is the single formatter and linter. Config in `pyproject.toml`:
  - `line-length = 120`
  - `target-version = "py311"`
  - `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`
- Indentation is 4 spaces; double quotes for strings and f-strings; trailing commas in multi-line calls; magic trailing comma respected.
- Current state verified: `python -m ruff check .` → "All checks passed!"; `python -m ruff format --check .` → "70 files already formatted".
- E501 is ignored, but the formatter still wraps to 120. Do not manually break lines the formatter will rejoin.
- No isort rule (`I`) is enabled; import grouping below is a manual convention, not tool-enforced.

**Linting:**
- `[tool.ruff.lint] select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]`.
- `scripts/*` ignores `E402` (`pyproject.toml`).
- Not enabled: bugbear (`B`), import sorting (`I`), docstring rules (`D`), type-checking rules (`TCH`). There is no `mypy`/`pyright` configuration and no `py.typed` marker.
- There are zero `TODO`/`FIXME`/`HACK`/`XXX` comments in `core/`, `retrieval/`, `ingestion/`, `providers/`, `ui/`, `tests/`, `main.py`, `start.py`, `setup.py`.

## Import Organization

**Order (observed and expected):**
1. Block comment or module docstring.
2. Standard library (`collections.abc`, `contextlib`, `dataclasses`, `datetime`, `hashlib`, `io`, `json`, `logging`, `math`, `pathlib`, `re`, `sqlite3`, `threading`, `time`, `typing`, `uuid`).
3. Third-party (`httpx`, `numpy`, `pydantic`, `pypdf`, `streamlit`, `sentence_transformers`, `litellm`, `langchain_text_splitters`).
4. First-party absolute imports (`core.*`, `retrieval.*`, `ingestion.*`, `providers.*`, `ui.*`).

Blank lines separate groups. Within a group, `from x import y` and `import x` are mixed alphabetically by module, not strictly isort-style.

**Always use absolute first-party imports** rooted at the repo, never relative imports:
```python
from core.models import Chunk, Document, Page
from ingestion.upload_validation import validate_pdf_bytes
from retrieval.hybrid_retriever import HybridRetriever
```

**Environment-before-import preamble:** `main.py`, `start.py`, `setup.py`, `tests/conftest.py`, and `retrieval/local_embedding.py` set framework env vars before importing heavy libraries (Ruff permits these `os.environ` assignments before imports):
```python
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

from dotenv import load_dotenv
import streamlit as st
```
In `tests/conftest.py` the equivalent assignments are at the very top before `pathlib`/`pytest` imports.

**Optional dependency pattern:** wrap third-party imports in `try/except ImportError` at module level and keep a `None` sentinel, then degrade at runtime:
```python
try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore[assignment]
    pa = None  # type: ignore[assignment]
```
Seen in `retrieval/hybrid_retriever.py`, `ingestion/docling_reader.py`, `ingestion/ocr_fallback.py` (two-level nested fallback), `providers/litellm_provider.py`, `providers/groq_provider.py`. `# type: ignore[assignment]` / `[assignment, misc]` is the standard annotation for these sentinels (34 occurrences repo-wide).

## Type Annotations

- Public boundaries are fully annotated with PEP 604 / builtin generics: `str | None`, `list[dict[str, str]]`, `dict[str, float] | None`, `Generator[str, None, None]`.
- Use `collections.abc` for abstract collections, not `typing`: `from collections.abc import Callable, Generator` (`ui/ingestion_service.py` still imports `Callable` from `typing` — prefer `collections.abc`).
- Use `typing.Any` only at genuinely dynamic boundaries (Streamlit `session_state`, injectable `converter`, `progress_callback` in `ingestion/visual_analyzer.py`).
- Annotate `__init__` and mutating/rendering methods with `-> None`.
- Use `from __future__ import annotations` only in the standalone CLI scripts `start.py` and `setup.py`; application modules rely on Python 3.11 runtime semantics.
- Return Pydantic models or frozen dataclasses rather than raw dicts on new boundaries (`IngestionResult`, `ValidatedUpload`, `HealthStatus`).

**Legacy exceptions to avoid copying:**
- `retrieval/vector_index.py` still uses `from typing import Optional, Any, List, Dict, Tuple` and omits return annotations on several methods: `def add_document(self, document: Dict[str, Any]):`.
- `ingestion/pdf_reader.py` has no module docstring and untyped constructor parameters: `def __init__(self, file_or_path, filename=None):`.
New code should follow `core/models.py` / `ingestion/docling_reader.py` style, not these files.

## Pydantic Model Conventions

- `model_config = ConfigDict(extra="forbid")` on every model; add `frozen=True` for immutable value objects (`Chunk`, `EvidenceSnippet`, `RetrievalResult`, `BBox`, `ProviderCapabilities`, `HealthStatus`, `CitationVerificationResult`).
- Every field uses `Field(..., description="...")`; use `ge=`, `min_length=`, `pattern=` for validation instead of ad-hoc checks (e.g. `sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$", ...)` in `core/models.py`).
- Cross-field business rules go in `@model_validator(mode="after")` returning `self`, with a `ValueError` that names the offending value:
```python
@model_validator(mode="after")
def validate_doc_id(self) -> "Document":
    if not self.doc_id.startswith("doc_"):
        raise ValueError(f"doc_id must start with 'doc_': {self.doc_id!r}")
    return self
```
- Prefix conventions are enforced in code and tests: document IDs `doc_<sha16>`, summary IDs `summ_<hex16>` (`core/models.py`, `ingestion/upload_validation.py`, `core/summarizer.py`).
- Serialize with `.model_dump()` at persistence/UI boundaries (`core/doc_store.py`, `ui/views.py`); reconstruct with `Model(**row)` / `model_validate`.

## Error Handling

**Strategy:** Built-in exceptions with actionable messages. There are **no custom exception classes** in the repo (`grep "^class .*Error"` returns nothing), and no exception hierarchy/module.

**Patterns:**
- **Validation / bad input → `ValueError` or `TypeError`**, always with the offending value and user-actionable context. Em dashes are used in user-facing upload messages:
  ```python
  raise ValueError(f"Not a valid PDF: missing %PDF header — {filename}.")
  raise ValueError(f"File too large ({mb:.1f} MB > {MAX_FILE_MB} MB) — {filename}.")
  ```
  (`ingestion/upload_validation.py`)
- **Type guards at storage boundaries → `TypeError`** with expected type named:
  ```python
  if not isinstance(doc, Document):
      raise TypeError(f"Expected Document instance, got {type(doc).__name__}")
  ```
  (`core/doc_store.py`)
- **Transport/parse failures → `RuntimeError` chained with `from exc`** so the cause is preserved:
  ```python
  except httpx.HTTPError as exc:
      raise RuntimeError(f"llama-server generation failed: {exc}") from exc
  ```
  (`providers/llama_cpp_provider.py:197-198`)
- **Privacy/consent violations → `PermissionError`** with a stable phrase tests match on: `"Cloud transmission blocked"` (`providers/litellm_provider.py`).
- **Lock contention → `TimeoutError`** from `InferenceGate.hold` (`core/local_llm.py:84`); callers in `ui/views.py` catch and surface it in chat.
- **Missing capability → `NotImplementedError`** (e.g. text-only providers rejecting `analyze_image`, `providers/groq_provider.py`).
- **Page-level fault isolation:** per-page extraction/OCR failures are caught and recorded on `Page(status="failed", error=str(err))` instead of aborting the document (`ingestion/pdf_reader.py`, `ingestion/docling_reader.py`, `ingestion/ocr_fallback.py:303`).
- **Graceful degradation over failure:** optional backends log a warning and switch modes rather than raising — LanceDB → in-memory `VectorIndex` (`retrieval/hybrid_retriever.py:148-154`), Docling → `PdfReader` (`ingestion/docling_reader.py:118`), nvidia-smi/psutil → zero/None telemetry (`core/resource_telemetry.py`).
- **Bare `except Exception` is intentionally used** for non-critical telemetry, optional imports, cleanup, and Streamlit state probes (e.g. `core/resource_telemetry.py:89`, `main.py` provider `close()` blocks). Do not use bare `except` for data-path logic where a specific exception is knowable.
- **`except RuntimeError` for lock release** in `InferenceGate.release` is defensive (double-release tolerated, `core/local_llm.py:62`).

## Logging

**Framework:** Standard library `logging`; no structured-logging library.

**Patterns:**
- One module-level logger per module: `logger = logging.getLogger(__name__)` (present in every module that logs: `core/local_llm.py`, `core/summarizer.py`, `core/citation_validator.py`, `core/resource_telemetry.py`, `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `ingestion/*`, `providers/litellm_provider.py`, `ui/*`).
- Prefer lazy `%`-style formatting (65 call sites), e.g.:
  ```python
  logger.warning("Failed to initialize LanceDB at %s: %s. Using in-memory fallback.", self.db_uri, err)
  ```
  (`retrieval/hybrid_retriever.py:150`)
- f-string logging exists only in `core/summarizer.py:336,391,394,420` (4 call sites). Match the `%`-style form in new code.
- Level usage:
  - `debug` — benign optional-backend noise (nvidia-smi unavailable, FTS index refresh notices).
  - `info` — lifecycle events (model loaded, cached summary reused, chunks persisted, migration applied via `print`).
  - `warning` — degraded-but-recoverable (fallback engaged, provider missing, non-local vision rejected).
  - `error` — persistence or page-processing failure.
- **`print()` is used only in CLIs, setup, and legacy paths** (104 occurrences): `start.py` banners/status, `setup.py`, `scripts/*`, plus `ingestion/pdf_reader.py:106`, `ingestion/upload_validation.py:106`, `core/doc_store.py:163`. Tests assert this output via `capsys`. New library code should log, not print.
- `core/logging_setup.py` defines `TorchClassesScanLogFilter` and `suppress_torch_classes_scan_warning()` to drop the benign `torch.classes` watcher traceback, using a filter (not `setLevel`) because Streamlit resets levels. Called once from `main.py`.

## Comments

**When to Comment:**
- Requirement/traceability IDs are embedded in comments and docstrings to tie code to specs: `(QUAL-01)`, `(RETR-02)`, `(INF-03)`, `(WR-02)`, `(CR-03)`, `(P1 audit)`. Examples: `core/local_llm.py:29` (`QUAL-01`), `retrieval/hybrid_retriever.py:60` (`CR-03`), `ui/hydration.py:15` (`CR-01`). Keep this pattern when implementing a numbered requirement.
- Numbered step comments inside long procedures: `# 1. Magic bytes check`, `# 2. Size limit check`, `# 1. Check persistent SQLite cache if store is configured` (`ingestion/upload_validation.py`, `core/summarizer.py`).
- Section banners for long modules:
  ```python
  # =====================================================================
  # 1. SIDEBAR DOCUMENT MANAGER & INGESTION
  # =====================================================================
  ```
  (`ui/views.py`), and dashed banners with numbered subsections in `retrieval/vector_index.py`. `main.py` uses `# --- ` banner blocks for configuration, session-state, storage, and consent sections.
- Explain *why* for non-obvious safety choices (lock ordering, schema inference, telemetry suppression) rather than restating code.
- Do not leave commented-out code. (`ingestion/pdf_reader.py` ends with a commented example block — do not replicate.)

**Docstrings:**
- Every production module starts with a `"""..."""` module docstring stating purpose and invariants. Multi-line for substantive modules (`core/doc_store.py`, `core/local_llm.py`, `retrieval/hybrid_retriever.py`, `ui/sanitizer.py`), one-line for small ones (`ui/components.py`).
- Public classes get a class docstring; non-obvious internals get a one-liner.
- Public methods use Google-style sections **without type repetition**:
  ```python
  """Synthesize a multi-profile document summary with page citations and caching.

  Args:
      doc_id: Unique document identifier starting with 'doc_'.
      profile: Target profile ('overview', 'detailed', ...).
      force_refresh: If True, bypasses cache and re-synthesizes.

  Returns:
      Canonical SummaryResult model.
  """
  ```
  (`core/summarizer.py:310-322`)
- Document raised exceptions with `Raises:` for public validators (`ingestion/upload_validation.py:75-76`, `core/local_llm.py:79-81`).
- Tests: each test function usually has a one-line docstring stating the invariant under test (e.g. `tests/test_sanitizer.py`, `tests/test_llama_cpp_provider.py`). Add one for every new test.
- Not enforced by tooling (no `D` rules); consistency is reviewed manually.

## Function and Module Design

**Size and shape:**
- Prefer small pure helpers with explicit inputs over hidden module state: `compute_rrf`, `extract_citations`, `estimate_tokens`, `sanitize_xml_boundary`, `should_ocr_page`, `sanitize_markdown_for_local`.
- Long orchestration methods are acceptable when they follow numbered phases and delegate detail to private helpers (`IngestionService.ingest_pdf`, `Summarizer.summarize_document`, `VisualAnalyzer.analyze_visual_elements`).
- Progress reporting uses an optional callback parameter rather than importing Streamlit into services:
  ```python
  progress_callback: Callable[[str], None] | None = None
  ```
  (`ui/ingestion_service.py`); `ingestion/visual_analyzer.py` uses `progress_callback: Any = None` with a documented `(current, total, label)` callable.

**Parameters and returns:**
- Keyword-friendly, explicit parameters with conservative defaults (`max_tokens: int = 1024`, `temperature: float = 0.2`, `timeout: float = 60.0`).
- Return canonical models, lists, or `bool` success flags; mutation-in-place methods return `None`.
- Context managers for resource lifetimes: `BaseModelProvider.__enter__/__exit__` (`providers/model_provider.py`), `DocStore._connect()` (`@contextmanager`), `InferenceGate.hold()` (`@contextmanager`), `track_stage()` (`core/resource_telemetry.py`).

**Module design:**
- One cohesive responsibility per module; no circular imports. Layers flow `ui → core → providers/retrieval/ingestion`; `retrieval` and `ingestion` import `core.models`, never `ui`.
- No barrel re-exports except `ui/__init__.py`; import from the defining module (`from core.models import Chunk`, not `from core import Chunk`).
- Abstract contracts: `BaseModelProvider(ABC)` in `providers/model_provider.py` with `@abstractmethod` methods; new providers must implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`, and should override `close()`.
- Global singletons: `InferenceGate` (class-level `threading.RLock`), `_MODEL_CACHE` (`retrieval/local_embedding.py`), `_LATENCY_HISTORY`/`_GPU_CACHE` (`core/resource_telemetry.py`). Any new shared mutable state must take a lock and expose a `clear_*`/reset helper for tests.

## UI Conventions (`ui/`)

- Streamlit page setup happens once in `main.py` (`st.set_page_config` must be the first Streamlit call); `inject_custom_theme()` immediately after.
- Session state keys are `snake_case`; internal/bookkeeping keys are `_`-prefixed (`_startup_hydrated`, `_cached_cloud_model`, `_cached_cloud_key`, `_show_consent_dialog`). Initialize defaults with a single `for key, default in [...]` table in `main.py`, not scattered `if "x" not in st.session_state` blocks.
- Views never touch persistence directly: ingestion goes through `IngestionService`, deletion/purge/reindex through `LifecycleService`, hydration through `hydrate_startup_state` (`ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `main.py`).
- Sanitize untrusted/LLM markdown before rendering: `sanitize_display_markdown(text, allow_external=cloud_mode)` (`ui/sanitizer.py`). Local mode must neutralize external links/images and strip `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`, `<link>`.
- Styling: AMOLED palette constants and injected CSS in `ui/theme.py`; monochrome SVG icons loaded from `assets/icons/` via `ui/components.py` with a process-level `_ICON_CACHE`. No emojis in UI strings (CLI banners in `start.py` are the exception).
- Upload-loop guard: rotate `st.session_state.uploader_key += 1` after processing and increment `new_docs_indexed` only for fresh files.
- Background: any LLM/VLM/summarizer call must be wrapped in `with InferenceGate.hold(...)` to respect the 4 GB VRAM ceiling (`core/local_llm.py`, `core/summarizer.py`, `ingestion/visual_analyzer.py`).

## Anti-Patterns Observed

**Untyped legacy modules.**
- What happens: `ingestion/pdf_reader.py` has no module docstring, untyped params, and `print()` reporting; `retrieval/vector_index.py` uses `typing.List/Dict/Optional` and omits return annotations.
- Why it's wrong: new code copied from these files fails the project's annotation/docstring conventions and produces noisy output in library context.
- Do this instead: mirror `ingestion/docling_reader.py` and `core/doc_store.py` — module docstring, PEP 604 types, logger + `%` formatting.

**f-string logging.**
- What happens: `core/summarizer.py` logs with f-strings in four places.
- Why it's wrong: eager formatting and inconsistent with the other 65 call sites; structured handlers cannot extract args.
- Do this instead: `logger.info("Summarizing %s using single-pass fast path (%d tokens)", doc_id, total_tokens)`.

**Broad `except Exception` in data paths.**
- What happens: widespread `except Exception` in `retrieval/hybrid_retriever.py` and `ui/*`.
- Why it's wrong: it can swallow programming errors alongside expected backend failures.
- Do this instead: keep broad catches only for optional backends/telemetry/cleanup and always log with `logger.warning(..., exc)`; use `(httpx.HTTPError, KeyError, IndexError)`-style tuples in new data paths (as in `providers/llama_cpp_provider.py`).

**Returning/storing untyped dicts on new boundaries.**
- What happens: older code passes dict chunks (`page_chunks: list[dict[str, Any]]`) and serializes models to dicts for session state.
- Why it's wrong: loses validation and field guarantees.
- Do this instead: construct `Chunk`/`Page`/`EvidenceElement` models, call `.model_dump()` only at the persistence/UI edge, and prefer `EvidenceSnippet`/`RetrievalResult` (`core/models.py`).

**Tests that re-implement production logic.**
- What happens: `tests/test_main_ui.py` simulates "Clear All" and consent transitions with local dicts instead of invoking the production handler.
- Why it's wrong: the test can pass while production code regresses.
- Do this instead: extract the state transition into a pure function in `ui/` and call it from the test (see TESTING.md).

---

*Convention analysis: 2026-10-21*
