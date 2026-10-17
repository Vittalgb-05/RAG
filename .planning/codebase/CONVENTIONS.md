# Coding Conventions

**Analysis Date:** 2026-10-17

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at the repo root, one responsibility per file. Examples: `main.py`, `local_llm.py`, `model_provider.py`, `groq_provider.py`, `litellm_provider.py`, `llama_cpp_provider.py`, `doc_store.py`, `docling_reader.py`, `hybrid_retriever.py`, `visual_analyzer.py`, `ocr_fallback.py`, `citation_validator.py`, `prompt_budget.py`, `resource_telemetry.py`, `summarizer.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `upload_validation.py`, `models.py`.
- No packages, no `__init__.py` in the project root, no barrel/re-export files. Imports are direct module imports (`from local_llm import AiModel` in `main.py:32`).
- Only `tests/` is a package (`tests/__init__.py`); `scripts/` holds standalone harnesses (`scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`).

**Functions / Methods:**
- `snake_case` verbs throughout: `validate_pdf_bytes`, `sha256_bytes`, `doc_id_for` (`upload_validation.py:19,36,64`), `assemble_grounded_messages`, `bound_chat_history`, `estimate_tokens`, `sanitize_xml_boundary` (`prompt_budget.py:57,145,43,26`), `compute_rrf` (`hybrid_retriever.py:31`), `validate_citations`, `extract_citations`, `is_abstention`, `detect_adversarial_injection` (`citation_validator.py:115,86,102,70`), `get_gpu_memory_info`, `track_stage`, `get_system_telemetry_snapshot` (`resource_telemetry.py:33,251,287`).
- Private helpers use a single leading underscore: `_resolve_api_key_for_model`, `_detect_image_mime_type` (`litellm_provider.py:39,82`), `_embed_one` (`local_embedding.py:69`), `_cosine_distance` / `_euclidean_distance` / `_dot_product` / `_magnitude` (`vector_index.py:157,142,193,198`), `_detect_provider` (`local_llm.py:167`), `_load_fallback_store`, `_connect`, `_apply_migrations` (`doc_store.py:126`, `hybrid_retriever.py`).
- Class names are `PascalCase`, one primary class per module: `AiModel`, `InferenceGate` (`local_llm.py:93,26`), `BaseModelProvider` (`model_provider.py:64`), `GroqProvider`, `LiteLLMProvider`, `LlamaCppProvider`, `DocStore` (`doc_store.py:103`), `HybridRetriever` (`hybrid_retriever.py:79`), `Summarizer`, `LocalEmbedding`, `VectorIndex`, `PdfReader`, `DoclingReader`, `VisualAnalyzer`, `LatencyTracker` (`resource_telemetry.py:194`).

**Variables / Attributes:**
- `snake_case` for locals and instance attributes: `db_path`, `user_consented`, `cloud_mode`, `last_retrieval_result`, `truncation_meta` (`local_llm.py:103-131`), `page_records`, `page_chunks` (`pdf_reader.py:25-26`).
- Private instance state uses a leading underscore: `_vector_dim`, `_distance_metric`, `_embedding_fn` (`vector_index.py:31-33`), `_client`, `_has_lancedb`, `_fallback_store` (`hybrid_retriever.py:100-105`), `_lock`, `_active_threads` (`local_llm.py:34-35`).
- Module-level constants are `UPPER_CASE` and typed: `CONFIG_VERSION` (`models.py:14`), `MAX_FILE_MB`, `MAX_PAGES` (`upload_validation.py:15-16`), `DEFAULT_DB_URI`, `DEFAULT_RRF_K` (`hybrid_retriever.py:27-28`), `MAX_STAGE_HISTORY`, `_GPU_CACHE_TTL_SECONDS` (`resource_telemetry.py:23,26`), `MAX_CHAT_TURNS` (`main.py:43`), `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS` (`citation_validator.py:16,18`), `SYSTEM_GROUNDING_TEMPLATE` (`prompt_budget.py:13`), `SCHEMA_V1_DDL`/`SCHEMA_V2_DDL`/`SCHEMA_V3_DDL` (`doc_store.py:17-94`).
- Module-private registries are `_UPPER_CASE`: `_MODEL_CACHE` (`local_embedding.py:19`), `_LATENCY_HISTORY`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK` (`resource_telemetry.py:21,29,30`).

**Types:**
- `UPPER_CASE` / `PascalCase` Pydantic v2 models in `models.py`: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`.
- `Literal` type aliases: `SummaryProfile` (`models.py:208`); capability/health schemas `ProviderCapabilities`, `HealthStatus` (`model_provider.py:15,44`).
- Frozen dataclass for value objects: `ValidatedUpload` with `@dataclass(frozen=True)` (`upload_validation.py:51`).

## Code Style

**Formatting:**
- Enforced by `ruff format --check .` in CI (`.github/workflows/ci.yml:33-36`); configuration lives in `pyproject.toml`.
- Line length is `120` (`pyproject.toml:2`), target Python `py311` (`pyproject.toml:3`).
- 4-space indentation, double quotes for code strings, `snake_case` identifiers.
- Triple-quoted docstrings are mixed: `"""..."""` in new modules; single-quoted `'''...'''` survives only in the legacy `pdf_reader.py` methods. Match the host file rather than normalising.

**Linting:**
- Ruff configured in `pyproject.toml:1-17`. Rule families selected: `E`, `F`, `W`; ignored: `E501` (line length handled by formatter), `W291`, `W293` (trailing/blank-line whitespace).
- Per-file ignore `"scripts/*" = ["E402"]` (`pyproject.toml:16-17`) permits module-level code after imports in benchmark harnesses.
- Excludes `.planning`, `.cache`, `data`, `docs`, `*.md` (`pyproject.toml:4-10`).
- No `mypy`/`pyright`/`pylint`/`flake8` config; no type-checking step in CI.

## Import Organization

**Order (enforced by eye, not isort):**
1. `from __future__ import annotations` where present (`start.py:8`, `setup.py:14`).
2. Standard library block — `from collections.abc import ...`, `from contextlib import ...`, `import logging`, `import re`, `import sqlite3`, `from pathlib import Path`, `import threading`, `from typing import ...`.
3. Third-party block — `import streamlit as st`, `from dotenv import load_dotenv`, `import pydantic`, `import httpx`, `import numpy as np`.
4. Local block — `from doc_store import DocStore`, `from models import ...`.

Example canonical ordering in `main.py:15-39`; stdlib-only ordering in `vector_index.py:11-12`.

**Optional / guarded imports:**
- Optional third-party dependencies are wrapped in `try/except ImportError` and set to `None` with `# type: ignore[assignment]`:
  - `groq` in `groq_provider.py:12-15`
  - `litellm` in `litellm_provider.py:18-21`
  - `lancedb` + `pyarrow as pa` in `hybrid_retriever.py:19-24`
- Function-local imports are used deliberately to avoid hard deps / cycles: `import psutil` (`resource_telemetry.py:178`), `import streamlit as st` (`groq_provider.py:40`), `import json` (`hybrid_retriever.py:131`), `from models import EvidenceSnippet` inside a method (`local_embedding.py:113`), `import shutil`/`import io` inline (`main.py:343,16`).

**Path Aliases:** None. All imports are top-level absolute module names.

## Error Handling

**Exception taxonomy (fail fast, before mutating state):**
- `ValueError` for bad values: invalid sha256 (`models.py:29`, `upload_validation.py:47`), invalid BBox coordinates (`models.py:50`), bad `distance_metric`/dimension mismatch/empty store guard (`vector_index.py:27,87,122`), unknown summary profile (`summarizer.py:324`), empty image bytes (`litellm_provider.py:298`, `llama_cpp_provider.py:261`).
- `TypeError` for wrong runtime types: `doc_store.py:164,204,224,253,286,307,360,379,433,483,527,568,586`; `hybrid_retriever.py:277`; `vector_index.py:53,59,77,79,116`.
- `RuntimeError` for provider/network/IO failures, always chained with `from err`: `groq_provider.py:108,126,138,161`; `llama_cpp_provider.py:175,177,238,290,292`; `litellm_provider.py:197,222,246,278,300,336`.
- `PermissionError` is the privacy gate: cloud providers raise before any transmission when consent is absent (`litellm_provider.py:126-132`; asserted in `tests/test_litellm_provider.py:30-36` and `tests/test_cloud_privacy.py:34`).
- `NotImplementedError` for unsupported capabilities: Groq text model image analysis (`groq_provider.py:170`), non-vision cloud model (`litellm_provider.py:304`).
- `TimeoutError` for concurrency gate: `InferenceGate.hold` (`local_llm.py:84`).

**Patterns:**
- Wrap-and-re-raise with cause chaining: `except Exception as err: raise RuntimeError(f"...: {err}") from err` (`litellm_provider.py:220-222`, `llama_cpp_provider.py:175`).
- Guard clauses at the top of constructors and mutators, before assigning state (`vector_index.py:26-33`, `llama_cpp_provider.py:53-57`).
- Graceful degradation instead of raising for optional resources: LanceDB init failure falls back to a disk-backed `VectorIndex` (`hybrid_retriever.py:112-124`); GPU telemetry returns `None`/`[]` on `FileNotFoundError`/`SubprocessError` (`resource_telemetry.py:86-91,139-144`); psutil missing returns zeroed dict (`resource_telemetry.py:186-188`).
- Per-document fault isolation: the upload loop catches `ValueError` from validation and `Exception` from extraction, shows `st.error(...)`, and `continue`s to the next file (`main.py:407-411,492-494`).
- `except Exception: pass` is used narrowly around best-effort cleanup (closing a cloud provider, `main.py:313-316,361-364`; Streamlit secrets probing, `litellm_provider.py:66-67,75-76`).

## Logging

**Framework:** standard library `logging`, one module-level logger.

**Patterns:**
- Module logger declared as `logger = logging.getLogger(__name__)`: `citation_validator.py:14`, `docling_reader.py:20`, `hybrid_retriever.py:16`, `litellm_provider.py:16`, `local_embedding.py:16`, `local_llm.py:23`, `main.py:41`, `ocr_fallback.py:18`, `resource_telemetry.py:18`, `summarizer.py:21`, `visual_analyzer.py:15`.
- Scripts use a named logger: `logging.getLogger("benchmark_multimodal")` (`scripts/benchmark_multimodal.py:30`), `logging.getLogger("resource_profiler")` (`scripts/profile_resources.py:38`).
- Lazy `%`-style formatting, never f-strings in `logger` calls: `logger.info("LanceDB persistent retriever connected at %s", self.db_uri)` (`hybrid_retriever.py:117`), `logger.warning("Failed to initialize LanceDB at %s: %s. Using in-memory fallback.", ...)` (`hybrid_retriever.py:119`), `logger.error("LiteLLM generation failure (%s): %s", self.model_name, err)` (`litellm_provider.py:221`).
- `print()` is reserved for CLI/one-shot scripts and user-facing console output: `start.py`, `setup.py`, `pdf_reader.py:113`, `upload_validation.py:106`. Library/service modules log through `logger` or Streamlit, not `print`.
- User-facing feedback in the UI goes through Streamlit: `st.error`, `st.warning`, `st.info`, `st.success`, `st.toast`, `st.status`, `st.write`, `st.progress` (`main.py:397,410,418,493,500,532,557,573,372`).

## Comments

**When to Comment:**
- Explain *why*, not *what*. Numbered pipeline-step comments in the upload loop: `# 1. Single raw bytes read per file`, `# 2. Server-side validation ...`, `# 3. Deduplication check via SHA-256 ...` (`main.py:402-413`).
- Requirement-ID tags thread traceability through code: `(RETR-04)`, `(QA-03)`, `(QA-04)`, `(WR-02)`, `(WR-04)`, `(QUAL-01)`, `(INF-03)`, `(INF-04)`, `(UI-04)`, `(TEL-01)`, `(INGEST-02)`, `(INGEST-04)`, `(VIS-01)`. Examples: `main.py:70,311,391,430,453`, `citation_validator.py:121,165,204`, `local_llm.py:29,114,152`.
- Algorithm notes where the math is non-obvious: L2-normalisation rationale (`local_embedding.py:80`), zero-magnitude guard (`vector_index.py:177`), float-drift clamp (`vector_index.py:184`), RRF formula (`hybrid_retriever.py:38-39`), token-budget reasoning (`summarizer.py:24-27`).
- Section banners separate logical blocks: `# ---...---` above `# Public API`, `# Distance functions`, `# Vector math helpers` (`vector_index.py:35-37,138-140,189-191`); the same banner style is used in `tests/*.py` file headers.

**Docstrings:**
- Every module should carry a top-of-file summary. Present in `main.py:1-13`, `models.py:1-6`, `model_provider.py:1-6`, `local_llm.py:1-6`, `citation_validator.py:1-7`, `doc_store.py:1-7`, `hybrid_retriever.py:1-6`, `summarizer.py:1-8`, `resource_telemetry.py:1-6`, `prompt_budget.py:1-7`, `litellm_provider.py:1-6`, `llama_cpp_provider.py:1-6`, `groq_provider.py:1-4`, `local_embedding.py:1-5`, `upload_validation.py:1-6`, `vector_index.py:1-9`, `start.py:1-6`, `setup.py:1-12`. Exception: `pdf_reader.py` has no module docstring.
- Google-style `Args:` / `Returns:` / `Raises:` / `Yields:` blocks are the norm for public classes and functions in newer modules: `model_provider.py:85-95,107-118`, `citation_validator.py:70-129`, `prompt_budget.py:26-78`, `resource_telemetry.py:33-41`, `doc_store.py:108-130`, `hybrid_retriever.py:36-95`, `local_llm.py:39-116`, `llama_cpp_provider.py:31-39`, `litellm_provider.py:106-115`.
- Trivial dunder/one-liner methods may be docstring-free (`vector_index.py:193-199`); legacy `pdf_reader.py` methods use terse lower-case prose docstrings (`pdf_reader.py:13-15,29-34`).
- Keep the commented-out runnable examples at the bottom of pure-logic modules and update them when the API changes: `vector_index.py:216-228`, `pdf_reader.py:142-149`.

## Type Hints

- New modules are fully annotated, including `-> None` on mutators and `| None` unions: `main.py:91,616`, `local_llm.py:103-131,312-319`, `citation_validator.py:115-118`, `doc_store.py:108`, `resource_telemetry.py:33,194-247`.
- Builtin generics (`list[str]`, `dict[str, Any]`, `tuple[str, ...]`) are preferred in new code; `from collections.abc import Generator` replaces `typing.Generator` (`model_provider.py:9,106`, `local_llm.py:8,223`).
- Legacy module `vector_index.py` still uses `typing.Optional/List/Dict/Tuple/Any` (`vector_index.py:12`); extend in the surrounding style rather than rewriting.
- Method-local annotations on container literals: `distances: list[tuple...]`, `messages: list[dict[str, str]]`, `retained_history: list[dict[str, str]]` (`prompt_budget.py:120,138`, `local_llm.py:111`).
- `# type: ignore[...]` is used only at genuine optional-import or monkeypatch seams (`groq_provider.py:15`, `hybrid_retriever.py:23-24`, `tests/test_concurrency_lock.py:182`).

## Function Design

- Small, single-purpose functions (roughly 5–40 lines). Large blocks are sequential Streamlit layout (`main.py` sidebar) or benchmark reporting (`scripts/*`), not extraction candidates.
- Keyword-friendly signatures with safe defaults so existing call sites keep working: `generate_text(..., max_tokens=1024, temperature=0.2)` (`model_provider.py:78-84`), `assemble_grounded_messages(..., max_context_tokens=4096, max_output_tokens=1024)` (`prompt_budget.py:57-64`), `bound_chat_history(..., max_turns=50)` (`prompt_budget.py:145-148`).
- Accept-both-types + normalise-early is an established shape: `PdfReader(file_or_path, filename=None)` accepts path/stream/file (`pdf_reader.py:12-23`); `VectorIndex.search(query)` accepts a string or a precomputed vector (`vector_index.py:92-116`); `LocalEmbedding.build_index(chunks)` accepts `list[str]` or `list[dict]` (`local_embedding.py:83-95`); `HybridRetriever.index_chunks` accepts `Chunk` models or `dict`s (`hybrid_retriever.py:~270-288`).
- Streaming is expressed as generators yielding `str`: `stream_text` (`model_provider.py:98-119`), `ask_a_question_from_pdf_stream` (`local_llm.py:216-308`).
- Data-returning APIs return plain containers or Pydantic models, never `None`-on-error: `VectorIndex.search` returns `[]` on an empty store (`vector_index.py:105-106`); `LocalEmbedding.search_hybrid` returns a `RetrievalResult` (`local_embedding.py:108-133`).
- Thread-safety is explicit: module-level `threading.Lock` guards mutable registries (`resource_telemetry.py:22,29,30`) and `InferenceGate` uses an `RLock` + state lock (`local_llm.py:34-36`).

## Module Design

- One primary public class per module, imported by name — no `__all__`, factories, or re-exports. Wire new cross-module dependencies the same way (`from x import Y` at top level).
- Provider polymorphism goes through the `BaseModelProvider` ABC (`model_provider.py:64-156`); new backends subclass it and implement `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Shared data contracts live in `models.py` (Pydantic v2) and `model_provider.py`; do not redefine schemas locally. `RetrievalResult.formatted_evidence()` and `source_labels()` are the single source of truth for prompt-context and UI citation rendering (`models.py:185-205`).

## Streamlit Idioms (must-follow)

- `st.set_page_config(...)` is the first Streamlit call and lives at module top-level (`main.py:49-54`).
- All `st.session_state` keys are initialised in one `for key, default in [...]` loop near the top (`main.py:63-78`); add new keys there, never lazily mid-layout.
- Per-session resources (`AiModel`, `LocalEmbedding`, `HybridRetriever`) live in `st.session_state`, not module globals — the module docstring and comments explain cross-session isolation (`main.py:60-61,91-101`).
- Render patterns: `with st.sidebar:` layouts (`main.py:112`), `with st.status(...) as s:` staged work ending in `s.update(label=..., state="complete", expanded=False)` (`main.py:385,563-567`), `st.tabs([...])` for the main area (`main.py:629`), `st.chat_message`/`st.chat_input` for chat, `st.progress` for per-page progress (`main.py:451,498`).
- State mutation ends with `st.rerun()` after batch updates (`main.py:140,146,171,195,212,218,324,373,561`).
- Current-doc/workflow tags: any new UI feature should keep its requirement-ID comment (e.g. `(UI-04)`, `(QUAL-01)`).

## Config / Secrets Patterns (must-follow)

- Cloud API keys resolved in strict precedence: explicit arg → Streamlit `session_state` `cloud_api_keys` → `st.secrets` → `os.environ` (`litellm_provider.py:39-79`; Groq uses `st.secrets.get("GROQ_API_KEY")` then env, `groq_provider.py:37-47`).
- Never hardcode secrets; `.env` is gitignored and only its existence is noted. Session keys are kept in memory only (`main.py:75,203-212`).
- Local inference endpoints are loopback-only by default; non-loopback hosts raise `ValueError` unless `allow_remote=True` (`llama_cpp_provider.py:40-57`).
- Anchored storage paths are derived from `Path(__file__).resolve().parent` rather than CWD: `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR` (`main.py:85-87`), `DEFAULT_DB_URI` (`hybrid_retriever.py:27`), `REPO_ROOT` (`start.py:18`, `setup.py:28`).

## CLI / Script Conventions

- `start.py` and `setup.py` use `from __future__ import annotations`, `argparse`, and `if __name__ == "__main__": sys.exit(main())` (`start.py:106-132`).
- Console output uses plain `print()` with emoji status markers (✓/⚠️/❌/ℹ️) and fixed-width banner separators (`start.py:21-26`, `setup.py:233-235`).
- `setup.py` doubles as a setuptools packaging file and a model-acquisition CLI; `MODEL_REGISTRY` is `list[dict[str, Any]]` with `min_size_bytes` verification and mirror URLs (`setup.py:44-63,87-176`).

---

*Convention analysis: 2026-10-17*
