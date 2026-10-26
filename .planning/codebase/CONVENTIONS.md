# Coding Conventions

**Analysis Date:** 2026-10-26

## Naming Patterns

**Files:**
- Modules are `snake_case` and named for one responsibility: `core/doc_store.py`, `core/citation_validator.py`, `retrieval/hybrid_retriever.py`, `ingestion/ocr_fallback.py`, `ui/lifecycle_service.py`.
- One concern per module. Ingestion stages are split: `ingestion/upload_validation.py` (validate) → `ingestion/docling_reader.py` (extract) → `ingestion/ocr_fallback.py` (OCR) → `ingestion/visual_analyzer.py` (VLM crops).
- Tests are `test_<module_or_feature>.py` in `tests/` (e.g. `tests/test_doc_store.py`, `tests/test_citation_validator.py`, `tests/test_ui_smoke.py`).
- Root entry points are short verbs/nouns: `main.py`, `start.py`, `setup.py`. Operational scripts live in `scripts/` (`benchmark_baseline.py`, `profile_resources.py`).
- Package `__init__.py` files carry a one-line docstring and `__version__`; only `ui/__init__.py` re-exports a symbol.

**Functions:**
- `snake_case`, verb-first for actions: `ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`, `validate_citations`, `apply_conditional_ocr`.
- Predicates/questions read as booleans: `should_ocr_page`, `should_withhold_answer`, `is_abstention`, `_is_sqlite_busy`, `_is_external_destination`.
- UI renderers are `render_<area>` returning `None`: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents` in `ui/views.py`; `render_status_pill`, `render_citation_chip`, `render_stat_card` in `ui/components.py`.
- Private/internal helpers use a leading underscore: `_reset_session_security_state` (`main.py`), `_evaluate_lexical_support` (`core/citation_validator.py`), `_execute_write` (`core/doc_store.py`), `_migrate_legacy_index` (`retrieval/hybrid_retriever.py`).
- Test helpers use `_make_*` / `_embed` / `_doc` and live at module top: `_make_retrieval_result` (`tests/test_citation_validator.py`), `_make_unit_vector` (`tests/test_hybrid_retriever.py`), `_embed` (`tests/test_whole_document_extraction.py`).

**Variables:**
- `snake_case` for locals and attributes; module constants are `UPPER_SNAKE`: `MAX_FILE_MB`, `MAX_PAGES`, `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `FAST_PATH_TOKEN_LIMIT`, `WRITE_MAX_ATTEMPTS`, `CITATION_REGEX`.
- Private module constants get a leading underscore: `_WRITE_RETRY_BASE_DELAY`, `_SQLITE_BUSY_CODES`, `_MODEL_CACHE`, `_DANGEROUS_SCHEMES`.
- Config values are grouped as typed module constants with an explanatory comment, e.g. `core/summarizer.py:31-40`, `ingestion/upload_validation.py:17-24`.
- Environment variables use the `RAG_` prefix for app settings (`RAG_LOG_LEVEL`, `RAG_LOG_DIR`, `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`) and standard provider names for credentials (`GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLAMA_SERVER_URL`).

**Types:**
- `PascalCase` classes: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `Summarizer`, `CitationVerificationResult`, `IngestionService`, `LifecycleService`, `VisualAnalyzer`, `OcrEngine`.
- Cross-boundary schemas are Pydantic v2 models in `core/models.py` (`BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`) and `providers/model_provider.py` (`ProviderCapabilities`, `HealthStatus`).
- Internal result containers are frozen/plain dataclasses: `ValidatedUpload` (`ingestion/upload_validation.py:105`), `IngestionResult` (`ui/ingestion_service.py:23`).
- Closed sets use `Literal` aliases rather than enums: `SummaryProfile` (`core/models.py:219`), `status: Literal["ok", "empty", "failed"]`.
- Test doubles are `Mock*` / `Dummy*` + the base class name: `MockLlamaCppProvider` (`tests/conftest.py:107`), `DummyProvider` (`tests/test_concurrency_lock.py:13`), `MockVisionProvider` (`tests/test_visual_analyzer.py:21`), `MockSummarizerProvider` (`tests/test_summarizer.py:16`).

**Requirement / audit tags:**
- Docstrings and comments carry traceability IDs in parentheses: `(QUAL-01)` in `core/local_llm.py:29`, `(RETR-04)` in `core/models.py:145`, `(INF-03, INF-04)` in `core/local_llm.py:212`, `(P0-1)`, `(CR-01)`, `(WR-02)` in tests and implementation. New code should reference the requirement ID it enforces.

## Code Style

**Formatting:**
- Tool: Ruff formatter, configured in `pyproject.toml`.
- `line-length = 120`, `target-version = "py311"`.
- 4-space indentation; double-quoted strings; f-strings for interpolation; trailing commas in multi-line calls.
- Excluded from formatting/linting: `.planning`, `.cache`, `data`, `docs`, `*.md` (`pyproject.toml:4-10`).
- Canonical check: `ruff format --check .` (CI gate in `.github/workflows/ci.yml`).

**Linting:**
- Tool: Ruff, rule families `E`, `F`, `W`, `B` (bugbear), `UP` (pyupgrade), `SIM` (simplify) (`pyproject.toml:12-14`).
- Ignored rules: `E501` (long lines are tolerated in strings/tables), `W291`, `W293` (whitespace).
- Per-file ignores: `scripts/*` → `E402` (scripts set env vars before imports), `start.py` → `UP036`.
- No import-sorting rule (`I`) is enabled — import grouping is a review convention, not enforced.
- No static type checker (mypy/pyright) is configured. Type safety relies on PEP 604 annotations plus Pydantic validation.

**Typing:**
- PEP 604 unions everywhere: `str | None`, `Path | str | None`, `int | list[str] | None`.
- Built-in generics: `list[dict[str, str]]`, `dict[str, Any]`, `tuple[bool, str | None]`.
- Abstract collection types come from `collections.abc`: `Callable`, `Generator`, `Iterable` (e.g. `core/doc_store.py:9`, `core/local_llm.py:8`).
- All public functions and methods are annotated, including `-> None`; `TypeVar` used for generic store helpers (`T = TypeVar("T")`, `core/doc_store.py:22`).
- `# type: ignore[...]` is used sparingly and always with a rule code, e.g. `# type: ignore[method-assign]` in tests and `# type: ignore[assignment, misc]` for optional provider imports (`providers/groq_provider.py:14`).

**UI style rules:**
- Dark AMOLED palette lives in typed constants in `ui/theme.py:6-15` (`COLOR_BG = "#050608"`, `COLOR_PRIMARY = "#B9A3FF"`, `COLOR_SECONDARY = "#70D9C2"`, `COLOR_DANGER = "#FF7B72"`). Reuse these constants instead of hard-coded hex values in views.
- Iconography is local monochrome SVG from `assets/icons/` via `get_svg_icon` (`ui/components.py:14`); no remote assets or emoji in UI copy.
- Streamlit theme defaults are mirrored in `.streamlit/config.toml` (`base = "dark"`, `primaryColor`, `backgroundColor`).

## Import Organization

**Order:**
1. Environment guards first when a module imports heavy ML libraries — `os.environ.setdefault("USE_TF", "0")` etc. must run before `sentence_transformers` / `streamlit` imports, as in `retrieval/local_embedding.py:12-17`, `main.py:14-18`, and `tests/conftest.py:9-11`.
2. Standard library imports (`collections.abc`, `contextlib`, `dataclasses`, `datetime`, `hashlib`, `json`, `logging`, `pathlib`, `re`, `sqlite3`, `threading`, `time`, `typing`, `uuid`). Note: stdlib modules are alphabetized loosely, not strictly (`core/logging_setup.py:18-22` puts `collections.abc` first).
3. Third-party imports (`pydantic`, `streamlit`, `httpx`, `numpy`, `pypdf`, `pytest`).
4. First-party absolute imports grouped by package: `core.*`, then `ingestion.*`, `providers.*`, `retrieval.*`, `ui.*`.

**Example (`ui/views.py:3-31`):**
```python
import html
import logging
from pathlib import Path
import re
import shutil
from typing import Any

import streamlit as st

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from core.citation_validator import auto_attribute_citations, should_withhold_answer
...
from ui.sanitizer import sanitize_display_markdown
```

**Path Aliases:**
- None. All intra-project imports are absolute from the repository root (`from core.models import Chunk`). Relative imports (`from .models import ...`) are not used.
- Optional dependencies are guarded with `try/except ImportError` and a module-level `None` sentinel: `providers/groq_provider.py:12-15`, `providers/litellm_provider.py:21-25`.
- Tests import entry-point modules directly (`import start`, `from main import _reset_session_security_state`) and patch by dotted path (`patch("ui.hydration.HybridRetriever")`).

## Error Handling

**Patterns:**
- `ValueError` for invalid user input or violated data invariants, with the offending value and filename in the message: `ingestion/upload_validation.py:136`, `:143`, `:156`; `core/models.py:29`.
- `PermissionError` for privacy/consent gates. Cloud providers refuse to transmit until `user_consented=True`: `providers/groq_provider.py:57-62`, `core/local_llm.py:134-137`, `:189-192`.
- `RuntimeError` for backend/client failures (`providers/groq_provider.py`, `providers/litellm_provider.py`).
- Custom exception subclass only where callers must distinguish failure semantics: `VectorIndexError(RuntimeError)` in `retrieval/hybrid_retriever.py:75` signals that vectors were not persisted, so ingestion/re-index must be reported as failed rather than "indexed".
- Preserve cause chains with `raise ... from err`: `retrieval/hybrid_retriever.py` (LanceDB failures), `ingestion/upload_validation.py:150`, `providers/groq_provider.py`.
- Pydantic validation is the first line of defense: `ConfigDict(frozen=True, extra="forbid")` plus `@model_validator(mode="after")` for `doc_id`/`summary_id` prefixes and bbox ordering (`core/models.py:47-51`, `:109-113`, `:135-139`, `:240-246`).
- Broad `except Exception` is allowed only at untrusted-input or external-boundary points, where it must log and degrade rather than crash: OCR pre-flight sampling (`ingestion/upload_validation.py:40-56`), optional Streamlit session/secret probes (`providers/litellm_provider.py:60-90`), and LiteLLM provider error wrapping.
- Resource cleanup uses `try/finally`: `InferenceGate.release()` in `core/local_llm.py:341-345`; `DocStore._connect` closes the connection in `finally` (`core/doc_store.py:173-176`).
- Transient failures are retried only for known-transient errors, never blanket-retried. `DocStore._execute_write` retries `SQLITE_BUSY`/`SQLITE_LOCKED` with exponential backoff + jitter and re-raises everything else (`core/doc_store.py:178-217`).
- UI never surfaces raw exceptions; startup failures render remediation text and collapsible technical detail via `_render_startup_failure` (`main.py:70-76`).

**Canonical validation shape:**
```python
if not raw.startswith(b"%PDF-"):
    raise ValueError(f"Not a valid PDF: missing %PDF header — {filename}.")
```

**Canonical fallback shape:**
```python
try:
    resp = self._client.get("/health", timeout=2.0)
except (httpx.ConnectError, httpx.ConnectTimeout):
    ...
    return HealthStatus(status="unreachable", message=..., latency_ms=elapsed_ms)
```

## Logging

**Framework:** standard library `logging` (no third-party logger).

**Patterns:**
- One module logger per file: `logger = logging.getLogger(__name__)` (top of nearly every module).
- Application logging is installed once by `configure_logging()` from `core/logging_setup.py`, called before any startup work in `main.py:51`. It is idempotent, writes stderr plus a rotating `data/logs/app.log` (5 MB × 3 backups), and reads `RAG_LOG_LEVEL` / `RAG_LOG_DIR`.
- Lazy `%`-style formatting with a static message and arguments — never f-strings in log calls: `logger.warning("SQLite busy on %s (attempt %d/%d): %s. Retrying in %.3fs.", ...)` (`core/doc_store.py:205-212`).
- Level usage: `debug` for suppressed/benign diagnostics, `info` for state transitions (index opened, chunks persisted, validation result), `warning` for recoverable degradation (LanceDB unavailable → fallback, stale session summary discarded), `error` for failed operations that the caller must know about, `exception` for unexpected errors where a traceback is needed.
- Library code does not `print()`. `print()` is reserved for CLI operator output in `start.py`, `setup.py`, and `scripts/*` (e.g. `start.print_banner`).
- Secrets are never logged; credential-clearing paths scrub provider attributes instead (`ui/views.py:264` `clear_cloud_credentials`).
- Suppress known-benign third-party noise with filters, not by raising log levels globally: `TorchClassesScanLogFilter` (`core/logging_setup.py:146-177`).

## Comments

**When to Comment:**
- Explain *why* and the invariant, not *what* the next line does. Examples: the SQLite retry rationale (`core/doc_store.py:24-31`), the LanceDB canonical-path rationale (`retrieval/hybrid_retriever.py:69-73`), and the sanitizer's decoding parity with browsers (`ui/sanitizer.py:20-25`).
- Numbered inline steps in validators and multi-stage functions: `# 1. Magic bytes check` … `# 5. Content hashing` (`ingestion/upload_validation.py:134-163`), `# 1. Check for empty response` (`core/citation_validator.py:319`).
- Section banner comments in long modules and test suites:
  ```python
  # ------------------------------------------------------------------
  # Unit Tests for DocStore (doc_store.py)
  # Verifies SQLite persistence, WAL mode, migrations, ...
  # ------------------------------------------------------------------
  ```
  (`tests/test_doc_store.py:1-5`, `tests/test_models.py:1-5`, `main.py` sections.)
- Regression/audit identifiers in docstrings and inline comments so the rationale survives: `(QUAL-01)`, `(RETR-04)`, `(INF-04)`, `(P0-1)`, `(CR-01)`, `(WR-02)`.
- TODOs/FIXMEs are essentially absent from source — do not introduce them; file the issue in `.planning/` instead.

**JSDoc/TSDoc:** Not applicable (Python). Use Google-style docstrings:
- Every module starts with a `"""..."""` module docstring stating purpose and invariants (see `core/models.py:1-6`, `ui/sanitizer.py:1-11`).
- Public functions/methods have a one-line summary, blank line, then `Args:` / `Returns:` / `Raises:` sections without repeating types: `core/citation_validator.py:176-189`, `core/doc_store.py:178-192`, `ingestion/upload_validation.py:120-133`.
- Short private helpers may have a one-line docstring only (e.g. `_support_tokens`, `_destination`).
- When a behavior is subtle or was previously wrong, the docstring records the rationale and the failure mode it prevents (e.g. `InferenceGate.release`, `AiModel.check_health`, `get_session_summary`).

## Function Design

**Size:**
- Target small, single-purpose helpers; long logic is decomposed into private `_`-prefixed steps (`core/summarizer.py`: `_bundle_pages`, `_consolidate_summaries`, `_summarize_single_pass`, `_summarize_map_reduce`; `core/citation_validator.py`: `_evaluate_lexical_support`, `_support_tokens`).
- Large functions exist only as Streamlit layout renderers (`render_chat_view` in `ui/views.py:490`, `render_settings_view` at `ui/views.py:1167`) where sequential UI construction is intentional. Keep data/logic in helpers or services, not inside the render body.

**Parameters:**
- Inject collaborators through the constructor rather than importing/constructing them inside classes: `IngestionService(doc_store, hybrid_retriever, local_embedding, cache_dir)` (`ui/ingestion_service.py:51-64`), `Summarizer(provider, doc_store)` (`core/summarizer.py:175`), `AiModel(provider=..., cloud_mode=..., cloud_provider=...)` (`core/local_llm.py:114-119`).
- Optional behavior is keyword-only or defaulted, not positional booleans: `allow_external: bool = False`, `enable_file: bool = True`, `allow_remote: bool = False`.
- Test seams are explicit constructor parameters: `transport: httpx.BaseTransport | None` in `providers/llama_cpp_provider.py:64`, `recognizer`/`renderer` in `OcrEngine`.
- Callbacks are typed: `progress_callback: Callable[[str], None] | None` (`ui/ingestion_service.py:70`).

**Return Values:**
- Always annotated; use `None` for side-effect-only rendering (`render_*`, `inject_custom_theme`).
- Multi-field outcomes return a typed model/dataclass (`IngestionResult`, `ValidatedUpload`, `CitationVerificationResult`, `RetrievalResult`) — never a bare dict across module boundaries.
- Generators are annotated `Generator[str, None, None]` and must release resources in `finally` (`core/local_llm.py:247-345`).
- Non-fatal failures return `False`/`None` after logging rather than raising, when the caller is a UI status renderer (e.g. `_migrate_legacy_index`, `_reindex_document`).

## Module Design

**Exports:**
- No wildcard imports. Consumers import the concrete module path: `from core.doc_store import DocStore`, `from providers.model_provider import HealthStatus`.
- Public surface is the module's top-level names; private helpers stay `_`-prefixed.
- Only `ui/__init__.py` declares an explicit re-export (`__all__ = ["sanitize_markdown_for_local"]`).
- Constants used by other packages are exported plainly (`CONFIG_VERSION` in `core/models.py`, `MAX_FILE_MB` imported by `ui/views.py`).

**Barrel Files:**
- Not used as an architecture pattern. `core/__init__.py`, `ingestion/__init__.py`, `retrieval/__init__.py`, and `providers/__init__.py` contain only a docstring and `__version__ = "1.0.0"`. Do not add re-export barrels; import from the defining module.

## Domain Invariants Enforced by Convention

- **Single inference gate:** every LLM, VLM, or summarization call must run under `InferenceGate.hold(...)` or an explicit `InferenceGate.acquire()` / `release()` pair (`core/local_llm.py:26-100`). Streaming functions release the gate in `finally`.
- **CPU-pinned preprocessing:** Docling, OCR, and embeddings stay on CPU (`device="cpu"` default in `retrieval/local_embedding.py:56`); never move embeddings to GPU.
- **Shared evidence object:** generation and UI both consume `RetrievalResult`/`EvidenceSnippet`; do not invent a parallel citation dict shape (`core/models.py:142-216`).
- **Transactional persistence:** all document mutation goes through `DocStore` and `IngestionService`/`LifecycleService`; UI code must not write SQL directly (`ui/views.py` delegates to services).
- **Privacy boundary:** local mode must strip external links/embeds via `ui/sanitizer.py`; cloud providers require `user_consented=True` and must never log keys.
- **Versioned caches:** cache keys include `CONFIG_VERSION` and the active model version; stale summaries must be discarded, not displayed (`core/models.py:14`, `ui/views.py:52-80`).

---

*Convention analysis: 2026-10-26*
