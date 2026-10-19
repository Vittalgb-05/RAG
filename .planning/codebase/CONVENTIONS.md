<!-- refreshed: 2026-10-19 -->
# Coding Conventions

**Analysis Date:** 2026-10-19

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at repository root — one module per domain concern, never nested packages. Examples: `local_llm.py`, `hybrid_retriever.py`, `doc_store.py`, `prompt_budget.py`, `citation_validator.py`, `resource_telemetry.py`, `logging_setup.py`, `visual_analyzer.py`, `ocr_fallback.py`.
- Provider modules are named after the backend: `groq_provider.py`, `litellm_provider.py`, `llama_cpp_provider.py`, all implementing `model_provider.py:BaseModelProvider`.
- Entry/orchestration scripts at root: `main.py` (Streamlit app), `start.py` (launcher), `setup.py` (env bootstrap script, NOT a packaging manifest).
- `tests/` is the only package directory (`tests/__init__.py` present); test modules are `tests/test_<module>.py`.
- No `__init__.py` at repo root; no barrel files.

**Classes:**
- `PascalCase`. Core service classes: `AiModel` (`local_llm.py:93`), `LocalEmbedding` (`local_embedding.py:50`), `HybridRetriever` (`hybrid_retriever.py:88`), `VectorIndex` (`vector_index.py`), `PdfReader` (`pdf_reader.py:11`), `DoclingReader` (`docling_reader.py`), `Summarizer` (`summarizer.py:153`), `DocStore` (`doc_store.py:103`), `VisualAnalyzer` (`visual_analyzer.py`), `InferenceGate` (`local_llm.py:26`), `LatencyTracker` (`resource_telemetry.py:194`).
- Provider classes end in `Provider`: `GroqProvider`, `LiteLLMProvider`, `LlamaCppProvider`.
- Pydantic v2 schemas are `PascalCase` and live in `models.py`: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, and `model_provider.py`: `ProviderCapabilities`, `HealthStatus`, plus `citation_validator.py:CitationVerificationResult`.

**Functions & variables:**
- `snake_case` throughout. Examples: `ask_a_question_from_pdf_stream` (`local_llm.py:217`), `search_hybrid` (`hybrid_retriever.py:534`), `assemble_grounded_messages` (`prompt_budget.py:57`), `validate_citations` (`citation_validator.py:115`), `summarize_document` (`summarizer.py:301`), `validate_pdf_bytes` (`upload_validation.py:64`).
- Private helpers/state use a single leading underscore: `_embed_one` (`local_embedding.py:74`), `_detect_provider` (`local_llm.py:168`), `_apply_migrations` (`doc_store.py:141`), `_connect` (`doc_store.py:123`), `_bm25_search_fallback` (`hybrid_retriever.py:443`), `_escape_sql_literal` (`hybrid_retriever.py:31`), `_resolve_api_key_for_model` (`litellm_provider.py`), `_sha256` (`pdf_reader.py:26`).
- Module-level constants are `UPPER_CASE`: `CONFIG_VERSION` (`models.py:14`), `VALID_SUMMARY_PROFILES` (`models.py:209`), `SCHEMA_V1_DDL`/`MIGRATIONS` (`doc_store.py:17,96`), `DEFAULT_RRF_K` (`hybrid_retriever.py:37`), `MAX_FILE_MB`/`MAX_PAGES` (`upload_validation.py:15-16`), `CITATION_REGEX` (`citation_validator.py:16`), `PROFILE_SYSTEM_INSTRUCTIONS` (`summarizer.py:31`), `WATCHER_LOGGER_NAME` (`logging_setup.py:13`), `MAX_CHAT_TURNS` (`main.py:53`), `_LATENCY_HISTORY` (`resource_telemetry.py:21`).
- Module-level `logger` is named exactly `logger`: `logger = logging.getLogger(__name__)` in 14 modules (see Logging).

**Types:**
- Modern PEP 604 unions (`str | None`, `Path | str | None`) and builtin generics (`list[dict[str, str]]`, `dict[str, Any]`, `tuple[str, ...]`). `Generator` imported from `collections.abc` in provider/generator signatures (`model_provider.py:9`, `llama_cpp_provider.py:9`).
- Pydantic v2 `Field(..., description="...")` for every field, with `model_config = ConfigDict(frozen=True, extra="forbid")` for immutable value objects and `extra="forbid"` for mutable records.

## Code Style

**Formatting:**
- Ruff is the single source of truth: `pyproject.toml:1-17`.
  - `line-length = 120`, `target-version = "py311"`.
  - `extend-exclude = [".planning", ".cache", "data", "docs", "*.md"]`.
- 4-space indentation, double-quoted strings.
- CI enforces both lint and format check (`.github/workflows/ci.yml:39-42`):
  ```bash
  ruff check .
  ruff format --check .
  ```

**Linting:**
- Ruff rule selection in `pyproject.toml:12-14`: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` (line length and whitespace rules off because `ruff format` owns them).
- Per-file ignore: `"scripts/*" = ["E402"]` (`pyproject.toml:16-17`).
- No mypy/pylint/bandit configuration in repo. `# type: ignore[...]` comments are applied narrowly where optional deps or dynamic assignment require them (e.g. `groq_provider.py:15`, `hybrid_retriever.py:27-28`, `summarizer.py:409`).

## Import Organization

**Order (three blocks separated by blank lines):**
1. Standard library (`import logging`, `from pathlib import Path`, `from collections.abc import Generator`).
2. Third-party (`import httpx`, `import streamlit as st`, `from pydantic import BaseModel`).
3. Local absolute imports (`from models import Chunk`, `from model_provider import BaseModelProvider`).

Reference layouts: `main.py:14-40`, `local_llm.py:8-21`, `doc_store.py:9-15`, `prompt_budget.py:9-11`.

**Path Aliases:**
- None. All imports are absolute from repo root (`from vector_index import VectorIndex` in `hybrid_retriever.py:18`); no relative imports outside tests.

**Optional dependency pattern (must follow):**
```python
try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore[assignment, misc]
```
Seen in `groq_provider.py:12-15`, `hybrid_retriever.py:23-28`. At use site, raise a domain error or degrade with an install hint rather than crashing at import.

**Environment guards at import time:**
- `local_embedding.py:12-14` and `main.py:26-28` call `os.environ.setdefault("USE_TF", "0")` etc. before importing `sentence_transformers`. Place any backend-selection `setdefault` calls above the affected third-party import.

## Docstring Style

- Every module opens with a triple-quoted module docstring stating purpose, inputs/outputs, and requirement tags. Examples: `main.py:1-12`, `model_provider.py:1-6`, `prompt_budget.py:1-7`, `logging_setup.py:1-9`, `resource_telemetry.py:1-6`.
- Public functions/methods carry Google-style `Args:` / `Returns:` / `Raises:` / `Yields:` blocks. Exemplars: `prompt_budget.py:57-78`, `llama_cpp_provider.py:189-211`, `doc_store.py:156-165`, `citation_validator.py:115-129`, `logging_setup.py:31-43`.
- Schema fields are self-documenting via `Field(description=...)`, so class docstrings stay one-liners (`models.py:33-36`).
- Older helpers (`main.py` `safe_has_secret`, `pdf_reader.py`) use terse one-to-three-line docstrings; match the host file's flavour when editing rather than normalising repo-wide.

## Error Handling

**Fail-fast validation (raise before mutating state):**
- `TypeError` for wrong types, `ValueError` for bad values. Examples: `doc_store.py:163-164` (`raise TypeError(f"Expected Document instance, got {type(doc).__name__}")`), `upload_validation.py:79-100`, `vector_index.py` guards, `summarizer.py:323-326` (unknown profile), `llama_cpp_provider.py:56-60` (non-loopback endpoint rejected for SSRF).
- Pydantic `@model_validator(mode="after")` enforces invariants: `models.py:47-51` (BBox coords), `models.py:109-113` (doc_id prefix), `models.py:229-234` (summary/doc id prefixes).

**Wrapping third-party failures (preserve cause):**
```python
except httpx.HTTPError as exc:
    raise RuntimeError(f"llama-server generation failed: {exc}") from exc
```
Seen `llama_cpp_provider.py:184-187,247-248`, `groq_provider.py:125-126,160-161`. Always use `raise ... from exc`.

**Isolate-and-continue (batch processing):**
- Per-item `try/except Exception as err` inside loops that logs (`logger.warning`/`logger.error`) and `continue`s, so one bad page/region/chunk never aborts the batch. Examples: `pdf_reader.py:116-127` (per-page), `hybrid_retriever.py:127-130` (LanceDB init fallback), `visual_analyzer.py:259-269` (per-region VLM failure), `main.py` upload loop. Never use a bare `except:`.

**Graceful degradation for optional infra:**
- Broad `except Exception as err` with a logged fallback is deliberate at telemetry and persistence boundaries: `resource_telemetry.py:86-91` (nvidia-smi unavailable → `None`), `hybrid_retriever.py:363-364` (LanceDB write fail → fallback store), `doc_store.py` JSON decode guards.
- Empty results return `[]`/`None` rather than raising (`vector_index.py` search on empty store).

**Config errors name the remediation:** missing required config raises with the exact location: `groq_provider.py:73` — `"GROQ_API_KEY is not configured in environment or Streamlit secrets."`

**Domain-specific guard:** cloud transmission without consent raises `PermissionError` (`litellm_provider.py`, asserted in `tests/test_cloud_privacy.py:34`).

**Concurrency:** `InferenceGate.hold()` raises `TimeoutError` when the single-inference lock cannot be acquired (`local_llm.py:82-86`).

## Logging

**Framework:** standard-library `logging`.

**Module logger (required):**
```python
logger = logging.getLogger(__name__)
```
Present in `citation_validator.py:14`, `docling_reader.py:21`, `hybrid_retriever.py:20`, `litellm_provider.py:16`, `local_embedding.py:21`, `local_llm.py:23`, `main.py:48`, `ocr_fallback.py:19`, `resource_telemetry.py:18`, `summarizer.py:21`, `visual_analyzer.py:15`. Use this exact form in new modules.

**Levels & formatting:**
- Use lazy `%`-style formatting (preferred, avoids work when disabled): `logger.info("LanceDB persistent retriever connected at %s", self.db_uri)` (`hybrid_retriever.py:126`), `logger.warning("Failed to crop visual element %s: %s", element_id, e)` (`visual_analyzer.py:259`).
- Levels: `debug` for expected-unavailable telemetry (`resource_telemetry.py:87,140,187,190`), `info` for lifecycle/state transitions, `warning` for degradation/fallback, `error` for failures.
- Minor inconsistency to avoid reproducing: `summarizer.py:336,391,394,420` use f-string log args; prefer `%`-style as elsewhere.

**Streamlit watcher filter (`logging_setup.py`):**
- `TorchClassesScanLogFilter(logging.Filter)` uses a class-level `_needle = "torch.classes"` and `filter(record)` returns `False` only when the needle appears in `record.getMessage()` (`logging_setup.py:16-28`).
- A `Filter` is used rather than `Logger.setLevel` because Streamlit's `get_logger` calls `setLevel` on first module import and would clobber a level change — documented in the class docstring (`logging_setup.py:16-22`).
- `suppress_torch_classes_scan_warning(logger_name=...)` is idempotent (checks for an existing `TorchClassesScanLogFilter` before adding) and returns the logger (`logging_setup.py:31-47`).
- Invoked once at import time in `main.py:51` (`suppress_torch_classes_scan_warning()`), after `logger = logging.getLogger(__name__)` at `main.py:48`. Follow this attach-once, idempotent pattern for any new global log filters.

**Legacy `print()` (do not extend in library modules):**
- Remaining `print()` calls in importable library modules: `doc_store.py:154` (`[DocStore] Applied migration ...`), `pdf_reader.py:131`, `upload_validation.py:106` (`[UploadValidation] ...`). CLI scripts (`setup.py`, `start.py`, `scripts/*`) legitimately use `print()` for user-facing console output. New library diagnostics must use `logger`.

## Comments

- Comments explain *why*, especially non-obvious Streamlit rerun behaviour, VRAM/lock semantics, and algorithm rationale. Examples: `local_llm.py:153` (`# Avoid unnecessary reconnection / recreation if state has not changed (WR-02)`), `resource_telemetry.py:51` (double-check under lock), `prompt_budget.py:84` (token budget math), `hybrid_retriever.py:476` (precompute document frequencies).
- Requirement/risk tags are embedded inline to trace to planning artifacts: `(RETR-03)`, `(QUAL-01)`, `(INF-03)`, `(CR-02)`, `(WR-02)`, `(TEL-01)`, `(SEC-01)`, `(UI-04)`, `(VIS-03)`. Preserve these when editing tagged code.
- Section banner comment in tests and some modules:
  ```python
  # ------------------------------------------------------------------
  # Unit Tests for DocStore (doc_store.py)
  # ...
  # ------------------------------------------------------------------
  ```
  (`tests/test_doc_store.py:1-5`, `tests/test_vector_index.py:1-4`).
- Keep the commented-out runnable examples at the bottom of pure-logic modules (`pdf_reader.py:160-166`) and update them if the API changes.

## Function & Module Design

- Small single-purpose functions; the largest functions are Streamlit UI layout blocks and the hierarchical summarizer, not extraction candidates.
- Data containers returned as plain types or Pydantic models: `list[dict]` chunks, `list[tuple[dict, float]]` search results (`vector_index.py`), `RetrievalResult` (`hybrid_retriever.py:534`).
- Streaming is generator-based: methods `yield` string tokens (`local_llm.py:217-311`, `llama_cpp_provider.py:189-248`). New LLM entry points must yield strings, not buffer and return.
- Abstract contract in `model_provider.py:BaseModelProvider` (`ABC` + `@abstractmethod`); context-manager protocol (`__enter__`/`__exit__` → `close()`) implemented by `AiModel`, `HybridRetriever`, `LlamaCppProvider`.
- Single public class per module; wire new cross-module dependencies with top-level `from x import Y`. No `__all__`, factories, or re-exports.
- Optional constructor injection for testability: providers accept `transport: httpx.BaseTransport | None` (`llama_cpp_provider.py:31`), `VisualAnalyzer` accepts `region_detector`/`cropper` (`visual_analyzer.py`).
- Process-level caches are module globals with explicit clear helpers: `_MODEL_CACHE` + `clear_shared_model_cache()` (`local_embedding.py:24,45`), `_LATENCY_HISTORY` + `clear_latency_history()` (`resource_telemetry.py:21,273`).

## Configuration Patterns

- Secrets precedence (must follow): Streamlit `st.secrets` → environment/.env → raise naming both. `groq_provider.py:37-52`; `main.py:safe_has_secret` guards missing `st.secrets`.
- Never commit secrets: `.env` is gitignored (`.gitignore:1`) — note existence only, never read or quote contents.

---

*Convention analysis: 2026-10-19*
