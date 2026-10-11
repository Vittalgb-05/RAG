# Coding Conventions

**Analysis Date:** 2026-10-11

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at repo root, one public class per file: `main.py`, `local_llm.py`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `doc_store.py`, `models.py`, `upload_validation.py`.
- No packages, no `__init__.py` at root, no barrel files. Imports are direct module imports (`from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities` in `groq_provider.py:8`).
- Tests are `test_<module>.py` under `tests/` (`tests/test_doc_store.py`, `tests/test_llama_cpp_provider.py`).

**Classes:**
- `PascalCase`: `AiModel` (`local_llm.py:12`), `BaseModelProvider` (`model_provider.py:59`), `GroqProvider` (`groq_provider.py:18`), `LlamaCppProvider` (`llama_cpp_provider.py:18`), `LocalEmbedding` (`local_embedding.py:11`), `VectorIndex` (`vector_index.py:15`), `PdfReader` (`pdf_reader.py:10`), `DocStore` (`doc_store.py:61`), plus Pydantic models `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `ProviderCapabilities`, `HealthStatus`, and `ValidatedUpload` dataclass.

**Functions / Variables:**
- `snake_case` throughout: `ask_a_question_from_pdf_stream`, `assemble_grounded_messages`, `validate_pdf_bytes`, `sha256_bytes`, `doc_id_for`, `get_capabilities`, `stream_text`, `analyze_image`, `get_chunks_for_doc`, `cache_dir_for`.

**Private members:**
- Single leading underscore: helpers `_detect_provider` (`local_llm.py:36-56`), `_embed_one` (`local_embedding.py:27`), `_connect`/`_apply_migrations` (`doc_store.py:81,98`), `_cosine_distance`/`_euclidean_distance`/`_dot_product`/`_magnitude` (`vector_index.py:157,142,193,198`); state `_client` (`groq_provider.py`, `llama_cpp_provider.py:39`), `_vector_dim`/`_distance_metric`/`_embedding_fn` (`vector_index.py:30-33`).

**Constants:**
- `UPPER_SNAKE` module-level literals for locked config: `MAX_FILE_MB`, `MAX_PAGES` (`upload_validation.py:15-16`), `CONFIG_VERSION` (`models.py:14`), `SCHEMA_V1_DDL`, `MIGRATIONS` (`doc_store.py:16,56`), `SYSTEM_GROUNDING_TEMPLATE` (`prompt_budget.py:11`).

## Code Style

**Formatting:**
- ruff `>=0.9.0` is configured but **not** a hard gate locally — CI runs `ruff check .` and `ruff format --check .` (`.github/workflows/ci.yml:32-33`).
- `line-length = 120`, `target-version = "py311"` (`pyproject.toml`).
- 4-space indentation; long f-strings/prompts are the only lines that stretch, and `E501` is ignored.

**Linting:**
- `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]`, with `scripts/*` allowed `E402` (path-mutation imports) — `pyproject.toml`.
- Mixed quote style: double quotes for code/strings; both `"""..."""` docstrings (`models.py`, `model_provider.py`, `doc_store.py`, `local_embedding.py`) and `'''...'''`-era terse docstrings (`local_llm.py`, `pdf_reader.py`). Match the host file rather than normalizing.
- Banner comments separate logical sections:
  ```python
  # ------------------------------------------------------------------
  # Section title
  # ------------------------------------------------------------------
  ```
  See `main.py` (session state / cached helpers / sidebar / main content), `vector_index.py` (Public API / Distance functions / Vector math helpers / Dunder methods).

## Import Organization

**Order:**
1. stdlib (`io`, `json`, `sqlite3`, `base64`, `hashlib`, `math`, `time`, `contextlib`, `collections.abc`)
2. third-party (`streamlit`, `pydantic`, `httpx`, `groq`, `pypdf`, `sentence_transformers`)
3. local modules (`from models import ...`, `from vector_index import VectorIndex`)

Blank line between groups — see `main.py`, `llama_cpp_provider.py:7-14`, `doc_store.py:7-12`.

**Optional imports:**
- Guard risky third-party imports and degrade to `None`, then explain at the use site:
  ```python
  try:
      from groq import Groq
  except ImportError:
      Groq = None  # type: ignore[assignment, misc]
  ```
  (`groq_provider.py:12-14`), with the failure surfaced as a `HealthStatus` message rather than an exception.

**Path aliases:**
- None. `scripts/benchmark_baseline.py` mutates `sys.path` instead, justified by the `E402` per-file ignore.

## Error Handling

**Patterns:**
- Raise `TypeError` for wrong types and `ValueError` for bad values at constructor/boundary entry, before mutating state:
  - `VectorIndex.__init__` metric whitelist (`vector_index.py:27`); `add_vector` type/dimension guards (`vector_index.py:74-90`); `search` query type + dimension + `k` guards (`vector_index.py:112-129`).
  - `DocStore` `isinstance` guards on `Document`/`Page`/`Chunk` (`doc_store.py:113-114,202-203,235-241`).
  - `cache_dir_for` / `doc_id_for` reject invalid SHA-256 (`models.py:17-30`, `upload_validation.py:36-42`).
- User-facing validation raises `ValueError` with actionable text including the filename (`upload_validation.py:64-101`), caught in `main.py:168-172` and shown with `st.error` before `continue`.
- Isolate-and-continue for enumeration: `PdfReader.extract_text` wraps each page in `try/except Exception`, records a `failed` `Page` with the error string, and continues (`pdf_reader.py:64-110`). Never use a bare `except:`.
- Providers do **not** raise on missing config/connectivity — they return `HealthStatus` (`groq_provider.py:54-78`, `llama_cpp_provider.py:55-100`), so the app starts degraded (`local_llm.py:36-56`).
- Generation/stream failures raise `RuntimeError` with the backend name (`llama_cpp_provider.py:156-158,218`); callers must handle them (currently `main.py` does not — see CONCERNS.md).
- Empty results return empties, not `None`/errors: `VectorIndex.search` returns `[]` on an empty store (`vector_index.py:98-99`); `LocalEmbedding.build_index` returns early on empty input (`local_embedding.py:45-46`); `DocStore.record_chunks` returns early on `[]` (`doc_store.py:243-244`).
- Guard against division/shape hazards: zero-magnitude cosine returns `0.0`/`1.0` (`vector_index.py:177-181`); float-drift clamp (`vector_index.py:184`).

## Logging

**Framework:** plain `print()` (stdlib) — no logging library.

**Patterns:**
- Module-prefixed lifecycle lines: `print(f"[LocalEmbedding] Loading {self.model_name}...")` (`local_embedding.py:21-23,58`), `print(f"[DocStore] Applied migration ...")` (`doc_store.py:98-110`), `print(f"[UploadValidation] Validated ...")` (`upload_validation.py:106`), `print(f"Successfully extracted text from {self.filename} ...")` (`pdf_reader.py:113`).
- Rule: `print()` for developer diagnostics only; anything the user should see goes through Streamlit (`st.status`, `st.error`, `st.warning`, `st.info`, `st.success`, `st.progress`) — never `print`. See `main.py:87,144,157,170,178,202,214,221,260,271,291,317,335,352`.

## Comments

**When to Comment:**
- Explain **why** something is non-obvious or unusual, not what the code does. Examples: why per-operation SQLite connections exist (`doc_store.py:1-6` module docstring); why history is contextualized into the search query (`local_llm.py:97-102`); why L2 normalization is used (`local_embedding.py:38`).
- Algorithm notes at the math: zero-vector guard and clamp (`vector_index.py:177-184`); token-budget reservation (`prompt_budget.py:54`).
- Inline review markers reference concern IDs in `main.py` (`WR-04` at `:151`, `CR-01` at `:189`, `CR-02` at `:204`, `CR-03` at `:229`) and in the tests — preserve them when editing the same lines.

**Docstrings:**
- Module-level triple-quoted summaries on most modules stating purpose + inputs/outputs: `main.py`, `models.py`, `doc_store.py`, `prompt_budget.py`, `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `upload_validation.py`, `vector_index.py`, `local_embedding.py`. New modules must include one.
- Public methods use Google-style `Args:`/`Returns:`/`Raises:`/`Yields:` blocks (`model_provider.py:59-141`, `doc_store.py:113-283`, `prompt_budget.py:20-100`, `llama_cpp_provider.py:55-220`).
- Terse one-to-three-line docstrings for helpers in `main.py` (`load_ai_model` at `:66-72`) and `pdf_reader.py` (`get_paragraphs` at `:124-127`). Match the host file's flavour.

## Function Design

**Size:** Small single-purpose methods (5–30 lines). The largest function is the sidebar upload loop in `main.py` (~140 lines) — a sequential Streamlit layout, not logic to extract.

**Parameters:** Keyword-friendly with sane defaults so existing call sites keep working: `k: int = 3` (`local_embedding.py:60,66`, `vector_index.py:92`), `max_context_tokens=4096, max_output_tokens=1024` (`prompt_budget.py:37-38`), `max_tokens: int = 1024, temperature: float = 0.2` (provider methods), `pdf_path: str = ""` (`local_llm.py:73`).

**Return Values:** Plain containers and typed schemas — `list[dict]` chunks (`pdf_reader.get_paragraphs`), `list[tuple[dict, float]]` sorted ascending (`vector_index.search`), joined context string (`local_embedding.get_context:66-69`), Pydantic instances (`DocStore.get_document`), `HealthStatus`/`ProviderCapabilities` (providers). No `None`-on-error: raise or return an empty container.

**Generators:** Token streaming is always a generator yielding `str`: `BaseModelProvider.stream_text` (`model_provider.py:84-105`), `GroqProvider.stream_text` (`groq_provider.py:119`), `LlamaCppProvider.stream_text` (parses SSE `data:` frames, `llama_cpp_provider.py:160-218`), consumed by `st.write_stream`. Keep new LLM entry points generator-based.

## Module Design

**Exports:** One public class (plus its schemas) per module; imported by name. No `__all__`, no factories, no re-exports.

**Barrel files:** Not used and not wanted — a new capability is a new root-level module plus explicit imports where used.

**Dual-type flexibility:** Normalize early and accept both shapes where the codebase already does: `PdfReader.__init__(file_or_path, filename=None)` accepts a path, `Path`, bytes stream, or file object (`pdf_reader.py:12-27`); `VectorIndex.search` accepts a string or a precomputed vector (`vector_index.py:100-110`); `LocalEmbedding.build_index` accepts `list[str]` or `list[dict]` (`local_embedding.py:49-55`).

**Type hints:** Modern union syntax and builtin generics — `str | None`, `list[dict[str, str]]`, `Generator[str, None, None]` from `collections.abc`. Annotate public signatures; keep `main.py`/`pdf_reader.py` lighter.

## Streamlit Idioms (must-follow)

- `st.set_page_config(...)` is the very first Streamlit call (`main.py:35`) — never insert a Streamlit call above it.
- Initialize all `st.session_state` keys via the key/default loop (`main.py:49-57`); add new keys there, never lazily mid-layout.
- Heavy singletons behind `@st.cache_resource` (`main.py:65-72`); call `load_dotenv()` inside the cached loader before constructing `AiModel`.
- Staged work uses `st.status(...)` (`main.py:87,144`) and completes with `.update(label=..., state="complete", expanded=False)`.
- Render pattern: `with st.sidebar:`, `st.chat_message` + `st.markdown` replay, `st.chat_input(..., disabled=...)` (`main.py:328-331`), then `response_stream → st.write_stream(...) → append to history` (`main.py:356-366`).
- Batch state mutations end with `st.rerun()` (`main.py:132,275`).

## Config Patterns (must-follow)

- Secrets precedence is `st.secrets["GROQ_API_KEY"]` (`groq_provider.py:42`) → `os.environ["GROQ_API_KEY"]`/`.env`, with absence degrading to a `HealthStatus` (`groq_provider.py:54-78`), not an exception.
- `.env` is gitignored; never commit or quote its contents.
- Context/build-version constants are module-level literals (`CONFIG_VERSION`, `MAX_FILE_MB`, `MAX_PAGES`); change them by editing the constant and its test.

---

*Convention analysis: 2026-10-11*
