# Coding Conventions

**Analysis Date:** 2026-10-13

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at repo root, one primary class per file: `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `models.py`, `model_provider.py`, `doc_store.py`, `hybrid_retriever.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `resource_telemetry.py`, `upload_validation.py`, `groq_provider.py`, `litellm_provider.py`, `llama_cpp_provider.py`.
- No packages, no `__init__.py` in root, no barrel files. `tests/__init__.py` exists (1 line, empty marker) only so pytest treats `tests/` as a package.
- Test files mirror source one-to-one: `tests/test_<module>.py` (e.g. `tests/test_doc_store.py` → `doc_store.py`). Cross-cutting suites use feature names: `tests/test_cloud_privacy.py`, `tests/test_cache_invalidation.py`, `tests/test_concurrency_lock.py`, `tests/test_main_ui.py`.
- Benchmark/profiling scripts live in `scripts/`: `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`. Corpus generator lives with its data: `tests/data/corpus/generate_corpus.py`.

**Classes:**
- `PascalCase`, one public class per module: `AiModel` (`local_llm.py`), `LocalEmbedding` (`local_embedding.py`), `VectorIndex` (`vector_index.py`), `PdfReader` (`pdf_reader.py`), `DocStore` (`doc_store.py`), `HybridRetriever` (`hybrid_retriever.py`), `Summarizer` (`summarizer.py`), `InferenceGate` (`local_llm.py`), `BaseModelProvider` (`model_provider.py`), `LlamaCppProvider` (`llama_cpp_provider.py`), `GroqProvider` (`groq_provider.py`), `LiteLLMProvider` (`litellm_provider.py`).
- Pydantic v2 schemas in `models.py` are `PascalCase` immutable value objects: `BBox`, `Chunk`, `Document`, `Page`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`. Health/capability schemas in `model_provider.py`: `HealthStatus`, `ProviderCapabilities`.
- Test doubles follow `Mock*` / `Dummy*` / `Deterministic*` prefixes: `MockLlamaCppProvider` (`tests/conftest.py`), `DummyProvider` (`tests/test_concurrency_lock.py`), `DeterministicBenchmarkProvider` (`scripts/benchmark_multimodal.py`), `BenchmarkProvider` (`scripts/profile_resources.py`).

**Functions:**
- `snake_case` throughout. Examples: `ask_a_question_from_pdf_stream` (`local_llm.py`), `build_index` / `get_embeddings` / `get_context` (`local_embedding.py`), `add_document` / `add_vector` / `search` (`vector_index.py`), `extract_text` / `get_paragraphs` (`pdf_reader.py`), `load_ai_model` / `save_uploaded_pdf` (`main.py`), `validate_citations` (`citation_validator.py`), `compute_rrf` (`hybrid_retriever.py`), `bound_chat_history` (`prompt_budget.py`), `estimate_tokens` / `sanitize_xml_boundary` (`prompt_budget.py`), `cache_dir_for` (`models.py`).
- Test functions are `test_<unit>_<behaviour>`: `test_cosine_distance_math`, `test_add_vector_guards` (`tests/test_vector_index.py`), `test_pdf_reader_chunking_overlap` (`tests/test_pdf_reader.py`), `test_chat_history_bounding_drops_oldest_turns` (`tests/test_cache_invalidation.py`), `test_default_session_privacy_state_is_local_only` (`tests/test_cloud_privacy.py`).

**Variables:**
- `snake_case` locals and attributes: `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py`), `page_chunks`, `pages_text`, `filename` (`pdf_reader.py`), `groq_client`, `model_name` (`local_llm.py`).
- Private helpers use a single leading underscore: `_embed_one` (`local_embedding.py`), `_cosine_distance` / `_euclidean_distance` / `_dot_product` / `_magnitude` (`vector_index.py`).
- Private state uses a single leading underscore: `_vector_dim`, `_distance_metric`, `_embedding_fn` (`vector_index.py`).
- Constants are `UPPER_CASE` at module scope in new code: `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py`), `DEFAULT_DB_URI`, `MAX_CHAT_TURNS = 50` (`tests/test_cache_invalidation.py`). Legacy tunables remain inline literals: `chunk_size=1000, chunk_overlap=200` (`pdf_reader.py`), `k=10` call sites, `max_tokens=1024` (`local_llm.py`). When adding code, prefer a named `UPPER_CASE` constant (new-code pattern) over inline literals.

**Types:**
- `typing` + `collections.abc` generics on all new modules: `list[float]`, `list[str]`, `list[tuple[dict, float]]`, `Generator`, `Callable`, `Literal` status fields (`model_provider.py`, `models.py`, `hybrid_retriever.py`). Pydantic `Field(..., min_length=1, gt=0, description=...)` for every schema field (`models.py`, `model_provider.py`).
- Legacy modules (`main.py`, `local_llm.py`, `pdf_reader.py`) are mostly untyped except isolated hints (`-> str`, `-> AiModel`, `pdf_path: str, prompt: str`). New code must be fully annotated; do not copy the legacy untyped style.

## Code Style

**Formatting:**
- Ruff formatter is canonical, enforced in CI via `ruff format --check .` (`.github/workflows/ci.yml`). Target Python 3.11, `line-length = 120` (`pyproject.toml:1-3`).
- 4-space indentation. Match the surrounding file; never run a repo-wide reformat to fix one file.

**Linting:**
- Ruff lint, enforced in CI via `ruff check .` (`.github/workflows/ci.yml`). Config in `pyproject.toml:5-10`: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` — long lines and trailing whitespace are lint-ignored (formatter still normalises whitespace).
- Per-file ignore: `"scripts/*" = ["E402"]` (`pyproject.toml:9-10`) because benchmark scripts do `sys.path.insert(0, str(REPO_ROOT))` before project imports (`scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`). Do not add new E402 violations outside `scripts/`.
- No mypy/pyright config; type safety comes from Pydantic runtime validation (`extra="forbid"`, `frozen=True` on schemas) plus constructor guards.

## Import Organization

**Order:**
1. Stdlib block (`pathlib`, `re`, `json`, `sqlite3`, `uuid`, `datetime`, `threading`, `abc`, `contextlib`, `collections.abc`)
2. Third-party block (`pydantic`, `numpy`, `streamlit`, `pypdf`, `sentence_transformers`, `psutil`, `reportlab` in tests)
3. Local block (`from models import ...`, `from vector_index import VectorIndex`, `from model_provider import BaseModelProvider`)
4. One blank line between groups. Exemplars: `models.py`, `doc_store.py`, `hybrid_retriever.py`.

**Path Aliases:**
- None. All imports are top-level absolute (`from vector_index import VectorIndex` in `local_embedding.py`). No `src/` layout, no aliases.

**Repo-root bootstrap (scripts + tests only):**
- `scripts/*.py` and the corpus generator prepend the repo root: `REPO_ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(REPO_ROOT))`. This is the sanctioned pattern for out-of-tree entry points only — never add `sys.path` hacks to root-level application modules.
- One legacy function-level import remains: `import io` inside the upload loop (`main.py`). Do not copy this — hoist new imports to the top-level block.

## Error Handling

**Patterns:**
- Fail fast with `TypeError` for wrong types and `ValueError` for bad values, before mutating state. `VectorIndex` guard inventory to mirror: metric whitelist, missing embedding fn, non-dict document / missing `content` key / non-string content, dimension lock-in and mismatch, bad query type, vector-length checks in every distance helper (`vector_index.py`).
- Pydantic schemas reject unknown fields and bad values at construction: `model_config = ConfigDict(frozen=True, extra="forbid")` on `BBox`, `ProviderCapabilities`, `HealthStatus` (`models.py`, `model_provider.py`); `cache_dir_for` validates the sha256 hex shape and raises `ValueError` (`models.py`). New schemas must set `frozen=True, extra="forbid"`.
- Missing `GROQ_API_KEY` raises `ValueError` with remediation text naming both secret locations (`local_llm.py`). New required-config checks must raise with the same "what + where to set it" message shape.
- Per-file `try/except Exception as e` around `PdfReader` + `get_paragraphs()`, reporting via `st.error(f"... (Error: {e})")` then `continue` so one bad PDF never aborts the batch (`main.py`). New per-document processing must use this isolate-and-continue shape, never a bare `except:`.
- Empty-store behaviour: `search()` returns `[]` instead of raising when nothing is indexed (`vector_index.py`); zero-magnitude vectors return `0.0`/`1.0` instead of dividing by zero. Preserve these guards.
- Optional third-party imports use `try/except ImportError → None` at top with an explicit `ImportError` + install hint at the use site (pattern in `local_llm.py` for `groq`). New optional deps (OCR, docling, vision) must follow this shape.
- `InferenceGate` serialises local inference to one active model at a time (4 GB VRAM ceiling); tests use `DummyProvider` + threads to assert mutual exclusion (`tests/test_concurrency_lock.py`, `local_llm.py`). New local-model call paths must go through the gate, never call the provider directly in parallel.

## Logging

**Framework:** `logging` in new/service code; legacy `print()` in embedding/reader paths; `st.*` for user-facing feedback.

**Patterns:**
- New modules and all `scripts/*` use `logging.getLogger(__name__)` / named loggers: `logger = logging.getLogger("benchmark_multimodal")` (`scripts/benchmark_multimodal.py`), `logger = logging.getLogger("resource_profiler")` (`scripts/profile_resources.py`), `logging` imports in `citation_validator.py`, `summarizer.py`, `hybrid_retriever.py`. New code must use `logging`, not `print`.
- Legacy lifecycle prints retained (do not propagate): `print(f"[LocalEmbedding] Loading {self.model_name}...")` (`local_embedding.py`), `print(f"Successfully extracted text from ...")` (`pdf_reader.py`).
- User-facing feedback goes through Streamlit, never `print`/`logging`: `st.error` / `st.info` / `st.success` / `st.status` / `st.write` (`main.py`). Rule: `logging`/`print` for developer diagnostics, `st.*` for anything the user should see.

## Comments

**When to Comment:**
- Every module opens with a `# ---...` banner block stating purpose and offline/test stance (e.g. `tests/conftest.py:1-4`, `scripts/benchmark_baseline.py:1-6`, `tests/test_vector_index.py:1-4`). New modules and test files must include one.
- Explain *why Streamlit behaves unusually*, not what the code does (exemplar `main.py` rationale comments on full-script reruns and session-state persistence). Algorithm notes where math is non-obvious: L2-normalisation rationale (`local_embedding.py`), zero-vector guard and float-drift clamp (`vector_index.py`).
- Keep the commented-out runnable examples at the bottom of pure-logic modules (`vector_index.py`, `pdf_reader.py`) and update them if the API changes.

**Docstrings:**
- Public methods carry docstrings. New Pydantic/provider code uses full sentences with `Args:`/`Returns:` Google-style blocks (`models.py:cache_dir_for`, `vector_index.py:search`, `local_embedding.py`). Legacy helpers use terse `'''...'''` one-to-three-liners (`local_llm.py`, `pdf_reader.py`, `main.py` helpers). Match the host file's flavour when editing.
- Not applicable (Python codebase; no JSDoc convention).

## Function Design

**Size:** Small single-purpose methods (5–25 lines). Largest functions are UI layout blocks in `main.py` (sidebar ~90 lines, chat handler ~40 lines) — sequential Streamlit layouts, not logic to extract, unless adding genuinely new UI sections.

**Parameters:** Keyword-friendly with sane defaults: `prompt: str = "tell me what is this pdf about", local_embedding=None, chat_history=None` (`local_llm.py`); `k: int = 3` (`local_embedding.py`, `vector_index.py`); `model_name: str = "all-MiniLM-L6-v2", distance_metric: str = "cosine"` (`local_embedding.py`). New retrieval parameters must default so existing call sites keep working. Provider methods use the canonical signature `(prompt, system_prompt=None, history=None, max_tokens=1024, temperature=0.2)` (`model_provider.py`, `llama_cpp_provider.py`, conftest mock).

**Return Values:** Data methods return plain containers or Pydantic dumps: `list[dict]` chunks with `content`/`filename`/`page`/`chunk_id` keys (`pdf_reader.py`), `list[tuple[dict, float]]` of `(document, distance)` sorted ascending (`vector_index.py`), `model_dump()` dicts for chat-turn `verification`/`snippets` payloads (`tests/test_main_ui.py`). Generation is a token generator (`yield chunk.choices[0].delta.content` in `local_llm.py`) consumed by `st.write_stream`. New LLM entry points must yield strings, not return a completed string, to preserve streaming.

**Dual-type flexibility:** Where the codebase already does it, extend with the same accept-both-types + normalise-early shape: `PdfReader.__init__(self, file_or_path, filename=None)` accepts path/bytes/file-object (`pdf_reader.py`); `VectorIndex.search(query: Any, ...)` accepts string or precomputed vector (`vector_index.py`); `LocalEmbedding.build_index(chunks: list)` accepts `list[str]` or `list[dict]` (`local_embedding.py`). No `None`-on-error: failures raise, empty results return `[]`/`""`-adjacent empties.

## Module Design

**Exports:** Single public class per module, imported by name — no `__all__`, no factories, no re-exports. Wire new cross-module dependencies the same way (`from x import Y` at top level). The flat layout means a new module is just a new root-level file plus an import where used.

**Provider seam (must-follow):** All inference goes through the `BaseModelProvider` ABC (`model_provider.py`: `check_health`, `get_capabilities`, `generate_text`, `stream_text`, `analyze_image`). Backends (`LlamaCppProvider`, `GroqProvider`, `LiteLLMProvider`) implement it; `AiModel` selects local-first with explicit cloud fallback (`local_llm.py`); tests inject `MockLlamaCppProvider` / `DummyProvider` / `DeterministicBenchmarkProvider` instead of real servers. Never import an SDK client directly in UI or retrieval code — add a provider subclass.

**Schema seam (must-follow):** Cross-module data uses `models.py` Pydantic schemas (`Document`, `Chunk`, `Page`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`) with `model_dump()` at UI/serialisation boundaries. New persisted or rendered fields go on the schema first, with a migration test in `tests/test_models.py`.

**Barrel Files:** None and not wanted.

## Streamlit Idioms (must-follow)

- `st.set_page_config(...)` is the very first Streamlit call (`main.py`) — never insert a Streamlit call above it.
- Initialise all `st.session_state` keys via the key/default loop (`main.py`); add new keys there, never lazily mid-layout.
- Heavy singletons go behind `@st.cache_resource` (`main.py:load_ai_model`); per-`load_dotenv()`-before-read ordering inside the cached function matters because `AiModel.__init__` reads the env.
- Render pattern: `with st.sidebar:` layout, `st.status` for staged work with `.update(label=..., state="complete", expanded=False)` on completion, `st.chat_message` + `st.markdown` for history replay, `st.chat_input(..., disabled=(...))` for gated input, `response_stream → st.write_stream(response_stream) → append to history`.
- State mutation ends with `st.rerun()` after batch updates. Chat-turn dicts carry the `verification` + `snippets` contract asserted in `tests/test_main_ui.py` — keep those keys stable.

## Config Patterns (must-follow)

- `load_dotenv()` is called inside the cached loader (`main.py`), and `AiModel` reads `st.secrets["GROQ_API_KEY"]` first with `except (KeyError, FileNotFoundError)` fallback to `os.environ.get("GROQ_API_KEY")` (`local_llm.py`). New secrets must follow this exact precedence: `st.secrets` → `.env`/`environ` → raise `ValueError` naming both locations.
- Never commit secrets: `.env` is gitignored; existence only is noted, contents are never read or quoted. Test API keys use the `fake_env_groq_key` fixture value `test-key-not-a-secret-mock-value` (`tests/conftest.py`), never a real credential.

---

*Convention analysis: 2026-10-13*
