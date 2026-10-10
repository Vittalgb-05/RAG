# Coding Conventions

**Analysis Date:** 2026-10-10

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at repo root, one class per file (except `main.py`, which is the Streamlit entry point): `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`.
- No packages, no `__init__.py`, no barrel files. Imports are direct module imports (e.g. `from local_llm import AiModel` in `main.py:21`).

**Classes:**
- `PascalCase`, one public class per module: `AiModel` (`local_llm.py:11`), `LocalEmbedding` (`local_embedding.py:11`), `VectorIndex` (`vector_index.py:15`), `PdfReader` (`pdf_reader.py:7`).

**Functions / methods:**
- `snake_case` throughout. Examples: `ask_a_question_from_pdf_stream` (`local_llm.py:36`), `build_index` / `get_embeddings` / `get_context` (`local_embedding.py:35,42,67`), `add_document` / `add_vector` / `search` (`vector_index.py:40,66,97`), `extract_text` / `get_paragraphs` (`pdf_reader.py:26,71`), `load_ai_model` / `save_uploaded_pdf` (`main.py:60,70`).
- Private helpers use a single leading underscore: `_embed_one` (`local_embedding.py:28`), `_cosine_distance` / `_euclidean_distance` / `_dot_product` / `_magnitude` (`vector_index.py:150,165,201,206`).
- Private state uses a single leading underscore: `_vector_dim`, `_distance_metric`, `_embedding_fn` (`vector_index.py:32-34`).

**Variables / attributes:**
- `snake_case` locals and attributes: `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py:46-49`), `page_chunks`, `pages_text`, `filename` (`pdf_reader.py:16-23`), `groq_client`, `model_name` (`local_llm.py:18,33`).
- Constants are inline literals, not module-level `UPPER_CASE` names — e.g. `chunk_size=1000, chunk_overlap=200` (`pdf_reader.py:32-33`), `k=10` call sites (`main.py:216,233`, `local_llm.py:54`), `max_tokens=1024` (`local_llm.py:77`).

**Types:**
- `typing` generics used only in `vector_index.py` (`List`, `Dict`, `Tuple`, `Optional`, `Any` — `vector_index.py:12` plus annotations on every public method). `local_embedding.py` uses builtin generics sparingly (`list[float]`, `list[str]`, `list[tuple[dict, float]]`). `main.py`, `local_llm.py`, `pdf_reader.py` are mostly untyped except isolated hints (`-> str`, `-> AiModel`, `pdf_path: str, prompt: str`).

## Code Style

**Formatting:**
- No formatter configured (no `pyproject.toml`, `.prettierrc`, `setup.cfg`, `tox.ini`, `.flake8` in repo). Style is hand-maintained.
- 4-space indentation, ~100–120 char soft line length (longest lines are f-strings/prompts, e.g. `local_llm.py:56-62`, `main.py:138,175`).
- Mixed quote style: double quotes for code/strings, single-quoted `'''...'''` docstrings in `main.py:61-77` and `local_llm.py:13,37`, double-quoted `"""..."""` docstrings in `local_embedding.py` and `vector_index.py`. When adding code, match the surrounding file rather than normalising repo-wide.

**Linting:**
- No linter configured and no lint step. No `ruff`/`flake8`/`pylint`/`mypy` config or CI job.

**Section banners:**
- Use the dashed banner comment to separate logical sections, with surrounding blank lines. Copy this exact shape when adding a section:
  ```python
  # ------------------------------------------------------------------
  # Sidebar — model status + document upload
  # ------------------------------------------------------------------
  ```
  Observed in `main.py:26-28,38-40,55-57,84-86,178-180` and `vector_index.py:36-38,146-148,197-199,209-211`, plus the `# Run` footer block (`main.py:248-253`, `vector_index.py:224-226`, `pdf_reader.py:81-83`).

## Import Organization

**Order (observed, follow this):**
1. Standard library (`os`, `tempfile`, `datetime`, `re`, `math`, `typing`).
2. Third-party (`streamlit`, `dotenv`, `sentence_transformers`, `pypdf`, `langchain_text_splitters`, `groq`).
3. First-party / local modules (`local_llm`, `local_embedding`, `pdf_reader`, `vector_index`).

**Examples:**
- `main.py:14-23` — stdlib block, blank line, third-party block, blank line, local block.
- `vector_index.py:11-12` — stdlib-only module (`math`, `typing`).
- `local_llm.py:1-9` — `os`, `streamlit`, local imports, then guarded `groq` import in `try/except ImportError` (`local_llm.py:6-9`).
- `pdf_reader.py:1-5` — `re`, `pypdf`, blank lines, `langchain_text_splitters`.

**Path aliases:**
- None. All imports are top-level absolute (`from vector_index import VectorIndex` in `local_embedding.py:8`).

**Exception to the rule:**
- One function-level import exists: `import io` inside the upload loop (`main.py:131`). Do not copy this — hoist new stdlib imports to the top-level block. The top-level pattern is the convention; the inline `import io` is a one-off.

## Error Handling

**Guard-clause validation (primary pattern — `vector_index.py`):**
- Fail fast with `TypeError` for wrong types and `ValueError` for bad values, before mutating state. New `VectorIndex` methods must follow this:
  ```python
  # `vector_index.py:77-84`, `vector_index.py:126-132`
  if not isinstance(vector, list) or not all(isinstance(x, (int, float)) for x in vector):
      raise TypeError("Vector must be a list of numbers.")
  if k <= 0:
      raise ValueError("k must be a positive integer.")
  ```
- Full guard inventory to mirror: metric whitelist (`vector_index.py:27-28`), missing embedding fn (`vector_index.py:51-52,115-116`), non-dict document / missing `content` key / non-string content (`vector_index.py:53-60,81-84`), dimension lock-in and mismatch (`vector_index.py:87-92,126-129`), bad query type (`vector_index.py:121`), vector-length checks in every distance helper (`vector_index.py:161-162,179-180,202-203`).
- Empty-store behaviour: `search()` returns `[]` instead of raising when nothing is indexed (`vector_index.py:110-111`).

**Optional-dependency pattern (`local_llm.py:6-9,19-21`):**
```python
try:
    from groq import Groq
except ImportError:
    Groq = None
# ... later, in AiModel.__init__:
if not Groq:
    raise ImportError("groq package is missing. Please run `pip install groq`.")
```
- Use this shape for any new optional third-party import: `try/except ImportError → None` at top, explicit `ImportError` with install hint at use site.

**Config-failure pattern (`local_llm.py:24-30`):**
- Missing `GROQ_API_KEY` raises `ValueError` with remediation text naming both secret locations. New required-config checks must raise with the same "what + where to set it" message shape.

**UI-level handling (`main.py:134-139`):**
- Per-file `try/except Exception as e` around `PdfReader` + `get_paragraphs()`, reporting via `st.error(f"... (Error: {e})")` then `continue` so one bad PDF never aborts the batch. New per-document processing must use this isolate-and-continue shape, never a bare `except:`.

**Defensive indexing (`main.py:151`, `local_llm.py:49-52`, `vector_index.py:186-189`):**
- `paragraphs[-1]["page"] if paragraphs else 0` guards empty PDFs; `if chat_history:` / `if last_user_msgs:` guards history contextualisation; zero-magnitude vectors return `0.0`/`1.0` instead of dividing by zero. Preserve these guards when touching the same code.

## Logging

**Framework:** `print()` to stdout/stderr only. No `logging` module, no log levels, no structured logging.

**Patterns:**
- Lifecycle prints with module prefix: `print(f"[LocalEmbedding] Loading {self.model_name}...")` (`local_embedding.py:22`), `print("[LocalEmbedding] Model ready.")` (`local_embedding.py:24`), `print(f"[LocalEmbedding] Indexed {len(chunks)} chunks.")` (`local_embedding.py:59`), `print(f"Successfully extracted text from {self.filename}. Total characters: {len(self.pages_text)}")` (`pdf_reader.py:60`), `print("running checks to make sure everything is good...")` (`local_llm.py:16`).
- User-facing feedback goes through Streamlit, never `print`: `st.error` / `st.info` / `st.success` / `st.status` / `st.write` (`main.py:96,129,138,144,167`). Rule: `print()` for developer diagnostics, `st.*` for anything the user should see.

## Comments

**When to comment:**
- Explain *why Streamlit behaves unusually*, not what the code does. Exemplar block (`main.py:41-43`): why the whole script reruns and why session state is the only persistence. Similar rationale comments at `main.py:66,75-76,93-94,195,203,222-224,229-231`.
- Algorithm notes where the math is non-obvious: L2-normalisation rationale (`local_embedding.py:39`), zero-vector guard (`vector_index.py:185`), float-drift clamp (`vector_index.py:192-193`).

**Docstrings:**
- Every module except `local_llm.py`/`pdf_reader.py` has a top-of-file `"""..."""` summary stating inputs/outputs (`main.py:1-12`, `local_embedding.py:1-5`, `vector_index.py:1-9`). New modules must include one.
- Public methods carry docstrings; `vector_index.py` + `local_embedding.py` use Google-style `Args:`/`Returns:` blocks (`vector_index.py:97-109`, `local_embedding.py:13-20`); `local_llm.py`/`pdf_reader.py`/`main.py` helpers use terse `'''...'''` one-to-three-liners (`local_llm.py:37-40`, `pdf_reader.py:71-75`, `main.py:61-77`). Match the host file's docstring flavour when editing.
- Keep the commented-out runnable examples at the bottom of pure-logic modules (`vector_index.py:228-236`, `pdf_reader.py:85-88`) and update them if the API changes — they are the closest thing this repo has to usage specs.

**JSDoc/TSDoc:**
- Not applicable (Python codebase; no JSDoc convention).

## Function Design

**Size:**
- Small single-purpose methods (5–25 lines). Largest functions are UI layout blocks in `main.py` (sidebar ~90 lines, chat handler ~40 lines) — these are sequential Streamlit layouts, not logic to extract, unless adding genuinely new UI sections.

**Parameters:**
- Keyword-friendly with sane defaults: `prompt: str = "tell me what is this pdf about", local_embedding=None, chat_history=None` (`local_llm.py:36`); `k: int = 3` (`local_embedding.py:61,67`, `vector_index.py:97`); `model_name: str = "all-MiniLM-L6-v2", distance_metric: str = "cosine"` (`local_embedding.py:13`). New retrieval parameters must default so existing call sites keep working.
- Dual-type flexibility where the codebase already does it: `PdfReader.__init__(self, file_or_path, filename=None)` accepts a path string, bytes stream, or file object (`pdf_reader.py:10-21`); `VectorIndex.search(query: Any, ...)` accepts a string or a precomputed vector (`vector_index.py:97-121`); `LocalEmbedding.build_index(chunks: list)` accepts `list[str]` or `list[dict]` (`local_embedding.py:42-54`). Extend with the same accept-both-types + normalise-early shape.

**Return values:**
- Data methods return plain containers: `list[dict]` chunks with `content`/`filename`/`page`/`chunk_id` keys (`pdf_reader.py:51-56`), `list[tuple[dict, float]]` of `(document, distance)` sorted ascending (`vector_index.py:97-144`), joined context string (`local_embedding.py:67-72`).
- Generation is a token generator (`yield chunk.choices[0].delta.content` in `local_llm.py:80-82`) consumed by `st.write_stream`, which returns the full string (`main.py:239`). New LLM entry points must yield strings (not return a completed string) to preserve streaming.
- No `None`-on-error: failures raise, empty results return `[]`/`""`-adjacent empties (`vector_index.py:110-111`, `local_embedding.py:46-47`).

## Module Design

**Exports:**
- Single public class per module, imported by name — no `__all__`, no factories, no re-exports. Wire new cross-module dependencies the same way (`from x import Y` at top level).

**Barrel files:**
- None and not wanted: the flat layout (`README.md:139-147` project structure) means a new module is just a new root-level file plus an import where used.

## Streamlit Idioms (must-follow)

- `st.set_page_config(...)` is the very first Streamlit call (`main.py:30-35`) — never insert a Streamlit call above it.
- Initialise all `st.session_state` keys via the key/default loop (`main.py:45-52`); add new keys there, never lazily mid-layout.
- Heavy singletons go behind `@st.cache_resource` (`main.py:59-67`); per-`load_dotenv()`-before-read ordering inside the cached function matters because `AiModel.__init__` reads the env.
- Render pattern: `with st.sidebar:` layout, `st.status` for staged work with `.update(label=..., state="complete", expanded=False)` on completion (`main.py:96-98,158-162`), `st.chat_message` + `st.markdown` for history replay (`main.py:196-200`), `st.chat_input(..., disabled=(...))` for gated input (`main.py:204-207`), `response_stream → st.write_stream(response_stream) → append to history` (`main.py:233-245`).
- State mutation ends with `st.rerun()` after batch updates (`main.py:112,156`).

## Config Patterns (must-follow)

- `load_dotenv()` is called inside the cached loader (`main.py:66`), and `AiModel` reads `st.secrets["GROQ_API_KEY"]` first with `except (KeyError, FileNotFoundError)` fallback to `os.environ.get("GROQ_API_KEY")` (`local_llm.py:23-27`). New secrets must follow this exact precedence: `st.secrets` → `.env`/`environ` → raise `ValueError` naming both locations.
- Never commit secrets: `.env` is gitignored (`.gitignore:1`); existence only is noted, contents are never read or quoted.

---

*Convention analysis: 2026-10-10*
