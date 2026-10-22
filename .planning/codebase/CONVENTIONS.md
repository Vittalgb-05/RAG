<!-- refreshed: 2026-10-21 -->
# Coding Conventions

**Analysis Date:** 2026-10-21

## Naming Patterns

**Files:**
- Modules are `snake_case.py` and grouped by responsibility: `core/` (`doc_store.py`, `local_llm.py`, `summarizer.py`, `prompt_budget.py`), `ingestion/` (`upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`), `retrieval/` (`hybrid_retriever.py`, `vector_index.py`, `local_embedding.py`), `providers/` (`model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`), and `ui/` (`views.py`, `components.py`, `theme.py`, `sanitizer.py`, `ingestion_service.py`, `lifecycle_service.py`, `hydration.py`, `session_state.py`).
- Root entry points are the only top-level modules: `main.py` (Streamlit composition root), `start.py` (launcher), `setup.py` (model/server setup CLI).
- Test modules are `tests/test_<area>.py` and mirror the module or feature under test, not its directory path (e.g. `tests/test_doc_store.py`, `tests/test_llama_cpp_provider.py`, `tests/test_main_ui.py`).
- Optional/diagnostic code lives under `scripts/` (excluded from E402 linting) and `tools/`.

**Functions:**
- `snake_case`, verb-first for actions: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `assemble_grounded_messages`, `apply_conditional_ocr`.
- Boolean predicates use `is_*`, `has_*`, `should_*`, `supports_*`, `can_*`: `InferenceGate.is_locked()`, `HybridRetriever.has_document()`, `should_ocr_page()`, `validate_gguf_file()`.
- Private helpers are underscore-prefixed and module-local: `DocStore._connect`, `DocStore._apply_migrations`, `LocalEmbedding._embed_one`, `AiModel._detect_provider`, `_escape_sql_literal`, `_doc_filter_clause` in `retrieval/hybrid_retriever.py`, `_reset_session_security_state` in `main.py`.
- UI renderers are named `render_<area>` and return `None`: `render_chat_view`, `render_library_view`, `render_file_upload_button`, `render_sidebar_documents` in `ui/views.py`; `render_brand_header`, `render_status_pill`, `render_citation_chip` in `ui/components.py`.
- Citation verification and attribution helpers: `validate_citations`, `auto_attribute_citations` in `core/citation_validator.py`.
- Factories/converters use `get_*`, `build_*`, or `*_for`: `get_shared_sentence_transformer`, `build_index`, `cache_dir_for`, `doc_id_for`, `sha256_bytes`.

**Variables:**
- Locals and parameters are `snake_case`, descriptive rather than abbreviated: `raw_bytes`, `progress_callback`, `existing_doc`, `persisted_chunks`, `docling_reader`.
- Module constants are `UPPER_SNAKE_CASE`: `MAX_FILE_MB`, `MAX_PAGES` (`ingestion/upload_validation.py`), `CONFIG_VERSION` (`core/models.py`), `DEFAULT_DB_URI`, `LEGACY_DB_URI`, `DEFAULT_RRF_K` (`retrieval/hybrid_retriever.py`), `MAX_CHAT_TURNS` (`main.py`), `FAST_PATH_TOKEN_LIMIT`, `MAX_BATCH_TOKENS` (`core/summarizer.py`).
- Private mutable module state is underscore-prefixed and paired with a `threading.Lock` when shared: `_MODEL_CACHE` in `retrieval/local_embedding.py`, `_LATENCY_HISTORY` / `_GPU_CACHE_LOCK` / `_SAMPLING_LOCK` in `core/resource_telemetry.py`, `_ICON_CACHE` in `ui/components.py`.
- Dataclass and Pydantic fields are `snake_case` and preserve legacy dictionary keys consumed by the UI (`content`, `filename`, `page`, `chunk_id`, `doc_id` in `core/models.py`).

**Types:**
- Classes are `PascalCase`: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`, `Summarizer`, `LlamaCppProvider`.
- Pydantic v2 models live in `core/models.py` and `providers/model_provider.py`; plain frozen dataclasses are used for internal value objects (`ValidatedUpload` in `ingestion/upload_validation.py`, `ModelIdentity` in `core/model_identity.py`, `IngestionResult` in `ui/ingestion_service.py`).
- Type aliases are `PascalCase`: `SummaryProfile = Literal["overview", "detailed", "study_notes", "tables_figures", "findings"]` in `core/models.py`.
- Closed sets use `Literal[...]` on model fields and a parallel tuple constant for validation (`VALID_SUMMARY_PROFILES`).
- Custom exceptions subclass the closest built-in and carry actionable text: `VectorIndexError(RuntimeError)` in `retrieval/hybrid_retriever.py`.
- Use PEP 604 unions (`str | None`, `list[dict[str, str]]`) and built-in generics on all new code. `retrieval/vector_index.py` is the one legacy module still using `typing.Optional/List/Dict/Tuple`; do not copy that style.

## Code Style

**Formatting:**
- Ruff formatter, 4-space indentation, double-quoted strings, f-strings for interpolation.
- `pyproject.toml` config: `line-length = 120`, `target-version = "py311"`, excludes `.planning`, `.cache`, `data`, `docs`, `*.md`.
- E501 is ignored, so 120 columns is a soft cap; the formatter wraps long calls (see multi-line `Field(...)` declarations in `core/models.py` and provider signatures).
- W291/W293 (trailing/blank-line whitespace) are ignored, but the formatter keeps files clean. `ruff format --check .` currently passes for all 73 files.

```toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W"]
ignore = ["E501", "W291", "W293"]
```

**Linting:**
- `ruff check .` selects only Pyflakes/Pycodestyle families (`E`, `F`, `W`). Import sorting (`I`), bugbear (`B`), security (`S`), and docstring rules are **not** enabled.
- `scripts/*` gets an E402 exemption in `[tool.ruff.lint.per-file-ignores]` because scripts mutate `sys.path` before imports.
- CI enforces both `ruff check .` and `ruff format --check .` in `.github/workflows/ci.yml`.
- No type checker (mypy/pyright) is configured; annotations are documentation-enforced, not CI-enforced.

**Model style (Pydantic v2):**
- Canonical schemas are immutable where they cross boundaries: `model_config = ConfigDict(frozen=True, extra="forbid")`.
- Fields always carry `Field(..., description="...")` and constraints (`min_length`, `ge`, `pattern`).
- Cross-field invariants use `@model_validator(mode="after")` and return `Self`-equivalent quoted type.

```python
class Chunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(..., min_length=1, description="Extracted chunk text content.")
    filename: str = Field(..., description="Original filename of the source document.")
    page: int = Field(..., ge=1, description="1-indexed source page number.")
    chunk_id: str = Field(..., description="Unique chunk identifier.")
    doc_id: str = Field(..., description="Parent document identifier (e.g. doc_<sha16>).")
```

**Dataclass style:**
- Internal, non-validated transports use `@dataclass` / `@dataclass(frozen=True)`, not Pydantic.
- Result objects default optional failure fields to `None` / `False` rather than raising.

```python
@dataclass
class IngestionResult:
    """Result container for document ingestion workflow."""

    success: bool
    doc_id: str
    filename: str
    sha256: str
    num_pages: int
    num_chunks: int
    already_indexed: bool = False
    fallback_used: bool = False
    error: str | None = None
    upload_time: str = ""
```

## Import Organization

**Order:**
1. Standard library (`collections.abc`, `contextlib`, `logging`, `pathlib`, `sqlite3`, `typing`).
2. Third-party (`pydantic`, `httpx`, `streamlit`, `numpy`, `lancedb`, `pymupdf`).
3. Local absolute imports (`core.*`, `ingestion.*`, `retrieval.*`, `providers.*`, `ui.*`).

```python
from dataclasses import dataclass
import datetime
import io
import json
import logging
from pathlib import Path
from typing import Any, Callable

from core.doc_store import DocStore
from ingestion.docling_reader import DoclingReader
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding
from core.models import Chunk, Document, EvidenceElement, Page, cache_dir_for
```

- Within a group, imports are **not** strictly alphabetical (`from pathlib import Path` often precedes `import re`). Do not run an unsolicited isort pass; match the module you are editing.
- `core/doc_store.py` and `ui/components.py` omit blank lines between groups; new code should keep the blank-line separation shown above.

**Path Aliases:**
- None. All internal imports are absolute from the repository root; relative imports (`from .models import ...`) are not used anywhere in `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`, or the entry points.
- The repo is installed editable (`pip install -e . --no-deps` in CI), so `core`, `ui`, etc. resolve as top-level packages. Add new packages as top-level directories with an `__init__.py`.
- Optional heavy dependencies are imported in `try/except ImportError` blocks with `None` placeholders and `# type: ignore` (Docling in `ingestion/docling_reader.py`, LanceDB/PyArrow in `retrieval/hybrid_retriever.py`, RapidOCR in `ingestion/ocr_fallback.py`).

**Environment-before-import rule:**
- `main.py` and `retrieval/local_embedding.py` set `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` **before** importing `sentence_transformers`/Streamlit. Preserve this ordering when touching those modules; `tests/conftest.py` repeats it before importing NumPy/pytest fixtures.

## Error Handling

**Patterns:**
- **Validation errors are `ValueError` with user-actionable context** including the filename/identifier and the violated limit. `ingestion/upload_validation.py` is the reference:

```python
if not raw.startswith(b"%PDF-"):
    raise ValueError(f"Not a valid PDF: missing %PDF header — {filename}.")

if size_bytes > max_bytes:
    mb = size_bytes / (1024 * 1024)
    raise ValueError(f"File too large ({mb:.1f} MB > {MAX_FILE_MB} MB) — {filename}.")
```

- **Consent violations are `PermissionError`**, checked before any provider call: `AiModel.__init__`/`set_cloud_mode` in `core/local_llm.py` and `LiteLLMProvider`/`GroqProvider` adapters raise `PermissionError("Cloud transmission blocked ...")` unless `user_consented=True`.
- **Resource-contention failures are `TimeoutError`**: `InferenceGate.hold(timeout=...)` raises `TimeoutError(f"InferenceGate acquisition timed out after {timeout}s: ...")` rather than blocking indefinitely.
- **Provider/network failures are `RuntimeError` chained with `from`**, preserving the cause: `raise RuntimeError(f"llama-server generation failed: {exc}") from exc` in `providers/llama_cpp_provider.py`; same pattern in `providers/groq_provider.py` and `providers/litellm_provider.py` after API-key scrubbing.
- **Persistence violations are a custom `VectorIndexError`** so ingestion/re-index cannot report success after silent vector loss (`retrieval/hybrid_retriever.py`). Catch this and fail the operation; do not downgrade it to a warning.
- **User-facing ingestion failures return a result object, not an exception**: `IngestionService.ingest_pdf` returns `IngestionResult(success=False, ..., error=f"Validation error: {val_err}")`; the UI renders `result.error`. Use exceptions for programmer/integrity errors, result objects for expected bad input.
- **Best-effort cleanup may swallow exceptions after logging**: cache deletion, session-state teardown, and progress callbacks use `except Exception: logger.warning(...)` or `except Exception: pass` (e.g. `ui/lifecycle_service.py`, `ui/session_state.py`). Never apply that pattern around SQLite/LanceDB writes.
- **Degradation over crashes at the boundary**: provider health returns `HealthStatus(status="unreachable", message=...)`; retrieval falls back to the in-memory `VectorIndex`; Docling falls back to `PdfReader`. Keep the fallback observable in `message`/logs.

## Logging

**Framework:** Standard library `logging`, one module-level logger per module.

```python
logger = logging.getLogger(__name__)
```

- Present in every substantive module: `core/summarizer.py`, `core/local_llm.py`, `core/citation_validator.py`, `ingestion/docling_reader.py`, `retrieval/hybrid_retriever.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `main.py`, etc.
- Preferred style is lazy `%s` formatting: `logger.warning("Failed to initialize LanceDB at %s: %s. Using in-memory fallback.", self.db_uri, err)` in `retrieval/hybrid_retriever.py`.
- Exception: `core/summarizer.py` uses f-strings in `logger.info(f"...")`. For new code, prefer the `%s` style.
- Log level usage: `info` for lifecycle milestones (migrations, index open, summary cache hits), `warning` for recoverable degradation (fallback store, cache cleanup, vector repair), `error` for failed inference/storage operations, `debug` for high-volume diagnostics.
- `core/logging_setup.py` installs a targeted `logging.Filter` on `streamlit.watcher.local_sources_watcher` to drop the benign `torch.classes` startup traceback; it is invoked once from `main.py` via `suppress_torch_classes_scan_warning()`.
- No `logging.basicConfig`/`dictConfig` in the app; Streamlit owns handler configuration.
- Residual `print()` calls remain in library code (`core/doc_store.py` migration banner, `ingestion/pdf_reader.py`, `ingestion/upload_validation.py`) and CLI-facing modules (`start.py`, `setup.py`). New library code must use the module logger; reserve `print()` for CLI output.

## Comments

**When to Comment:**
- Numbered workflow steps inside multi-stage functions: `# 1. Magic bytes check`, `# 2. Size limit check` (`ingestion/upload_validation.py`); `# 1. Validation`, `# 2. Deduplication check ...`, `# 3. Extraction ...` (`ui/ingestion_service.py`).
- "Why" comments that justify non-obvious ordering or workarounds, e.g. in `ui/lifecycle_service.py`:

```python
# 1. Vector deletion first.  If this fails we abort before touching SQLite so
# the catalog and the index cannot disagree (a deleted document whose chunks
# are still retrievable is worse than a visible, retryable failure).
```

- Requirement traceability tags in comments and docstrings are pervasive and expected: `(QUAL-01)` VRAM/gate, `(RETR-01..04)` retrieval, `(INF-03/04)` privacy/cloud, `(UI-04)` consent, `(CR-01/CR-03)` audit repairs, `(P0-1)` upload loop, `(WR-02)` reset, `(TEL-01)` telemetry cache. When changing behavior tied to a tagged requirement, keep or update the tag.
- Section banners separate logical blocks in Streamlit pages and large test modules:

```python
# ------------------------------------------------------------------
# Page configuration (must be the first Streamlit call)
# ------------------------------------------------------------------
```

- Do not add new commented-out code. Existing dead snippets in `ingestion/pdf_reader.py:166-167` and `retrieval/vector_index.py:228` should be deleted, not imitated.

**Docstrings (Google-style; Python equivalent of JSDoc/TSDoc):**
- Every module opens with a triple-quoted summary of purpose and invariants; many state the failure mode (e.g. `core/model_identity.py`, `core/prompt_budget.py`, `ui/session_state.py`).
- Public functions/classes use Google-style `Args:` / `Returns:` / `Raises:` / `Yields:` sections; there are 82 `Returns:`, 8 `Raises:`, and 5 `Yields:` sections across source packages.
- Types are not repeated in docstring prose when they are in the signature.

```python
def cache_dir_for(base: Path, sha256: str) -> Path:
    """
    Compute disk cache path for a given document SHA-256 and config version.

    Args:
        base: Base directory for cache (e.g. Path(".cache")).
        sha256: 64-character lowercase hex digest of the document.

    Returns:
        Path: Dedicated directory base / sha256 / CONFIG_VERSION.
    """
```

- One-line docstrings are acceptable for trivial renderers and helpers (`"""Render modern evidence-grounded chatbot workspace."""`).
- `core/logging_setup.py` uses reStructuredText roles (`:class:`) in module docs; Google style is the dominant convention.

## Function Design

**Size:**
- Most helpers are short and single-purpose. Large files exist (`retrieval/hybrid_retriever.py` ~873 lines, `ui/views.py` ~880 lines, `core/doc_store.py` ~813 lines); new logic should be extracted into private helpers rather than extending `render_chat_view` (already ~318 lines) or `ingest_pdf`.
- Multi-stage orchestration is decomposed into stage functions (`validate_pdf_bytes`, `apply_conditional_ocr`, `VisualAnalyzer.extract_visual_elements`, `HybridRetriever.index_chunks`) that are independently testable.

**Parameters:**
- Optional collaborators are keyword-friendly positional defaults: `HybridRetriever(db_uri=None, embedding_fn=None)`, `IngestionService(doc_store, hybrid_retriever=None, local_embedding=None, cache_dir=None)`.
- Callbacks are optional and last: `progress_callback: Callable[[str], None] | None = None` (`ui/ingestion_service.py`), `progress_callback` in `ingestion/visual_analyzer.py`.
- Inject dependencies for testability (provider, retriever, embedding, transport, clock-free design). `LlamaCppProvider(transport=...)` and `OcrEngine(recognizer=..., renderer=...)` exist specifically so tests can inject fakes.

**Return Values:**
- Renderers return `None`.
- Mutating service calls return `bool` for "did it happen" (`DocStore.delete_document`, `LifecycleService.delete_document`) or a result dataclass for richer status (`IngestionResult`).
- Query helpers return canonical Pydantic containers (`RetrievalResult`, `Document | None`, `list[Chunk]`), never ad-hoc dicts at public boundaries. Legacy dict compatibility is handled inside models via `.model_dump()`.
- Generators are annotated `Generator[str, None, None]` (streaming providers) or `Generator[sqlite3.Connection, None, None]` (context managers).

**Concurrency rule (mandatory):**
- Any LLM generation, VLM image analysis, or summarization must be wrapped in the process-level gate:

```python
with InferenceGate.hold(timeout=120.0):
    ...
```

- See `core/summarizer.py` (`Summarizer.summarize`), `core/local_llm.py` (`AiModel.generate`/streaming), and `ingestion/visual_analyzer.py`. Omitting the gate risks exceeding the 4 GB VRAM envelope; the gate is reentrant per thread and globally serialized across threads.

## Module Design

**Exports:**
- Packages expose a module docstring and `__version__ = "1.0.0"` in `core/__init__.py`, `ingestion/__init__.py`, `retrieval/__init__.py`, and `providers/__init__.py`.
- `ui/__init__.py` is the only barrel and re-exports exactly one symbol: `sanitize_markdown_for_local` via `__all__`.
- Otherwise, import from the concrete module (`from core.models import Chunk`), not from the package root. Do not add broad barrel files.
- Module-level singletons/caches are acceptable only when guarded: `InferenceGate` class-level `RLock` (`core/local_llm.py`), `_MODEL_CACHE` with clear function (`retrieval/local_embedding.py`), telemetry caches with TTL and locks (`core/resource_telemetry.py`).

**Barrel Files:**
- Not used as an import strategy. Keep `__init__.py` declarative and minimal.

**Optional dependencies:**
- Guard at import and degrade gracefully, with an explicit `None` sentinel and a runtime capability flag:

```python
try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore[assignment]
    pa = None  # type: ignore[assignment]
```

- Consumers must check the sentinel and log the fallback (see `HybridRetriever.__init__`, `DoclingReader` fallback to `PdfReader`).

**Entry points:**
- Library modules never contain `if __name__ == "__main__"`. Only `setup.py`, `start.py`, `scripts/*.py`, and `tests/data/corpus/generate_corpus.py` do.
- `main.py` is a Streamlit script executed top-to-bottom: `st.set_page_config` must remain the first Streamlit call, followed by `inject_custom_theme()`, then session initialization.

---

*Convention analysis: 2026-10-21*
