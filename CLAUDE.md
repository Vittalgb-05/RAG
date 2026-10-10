<!-- GSD:project-start source:PROJECT.md -->
## Project

**Local-First Multimodal PDF Intelligence System**

A local-first, privacy-respecting PDF intelligence application that delivers fast, accurate summarization and grounded question answering across digital, scanned, and visually complex documents (diagrams, charts, tables). Designed to run primarily on consumer hardware (single-user laptop with 4 GB GPU VRAM) with optional, explicitly configured cloud model fallback.

**Core Value:** Fast, evidence-grounded document summarization and question answering with visual understanding and verifiable page-level citations, operating completely locally within a 4 GB VRAM envelope.

### Constraints

- **Hardware / VRAM**: Strict 4 GB VRAM ceiling. Only one LLM/VLM active in memory at a time; quantized GGUF (4-bit); conservative context window (4K–8K tokens). Preprocessing (Docling, RapidOCR, embeddings) offloaded to CPU or sequenced to avoid VRAM exhaustion.
- **Platform**: Windows host OS with PowerShell; Python 3.11+.
- **Privacy & Security**: Zero external network egress during local operation; credentials kept in `.env` / environment variables; documents treated as untrusted input.
- **Architecture**: Modular monolith with decoupled services (ingestion, normalization, storage, retrieval, inference, UI).
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`)
- JSON — devcontainer config only (`.devcontainer/devcontainer.json`)
- Markdown — docs only (`README.md`)
- No JavaScript/TypeScript, no CSS, no SQL — UI is 100% Streamlit Python
## Runtime
- Local: CPython via `streamlit run main.py` (entry documented in `main.py:252-253`, `README.md:186`, `README.md:194`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py` (`.devcontainer/devcontainer.json:7-10`), serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:22-23,30-32`)
- Production: Streamlit Community Cloud (live demo at `https://rag1818.streamlit.app/` per `README.md:7`); no Dockerfile, no `packages.txt`, no `runtime.txt`
- pip with pinned `requirements.txt` (all `==` pins)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`; activation documented as `source .venv/Scripts/activate` on Windows Git Bash in `main.py:252`, `README.md:169`)
## Frameworks
- Streamlit `1.42.0` — entire UI layer: `st.set_page_config` (`main.py:30-35`), sidebar (`main.py:88-175`), `st.file_uploader` (`main.py:114-120`), `st.chat_input` / `st.chat_message` (`main.py:197-212`), `st.status` (`main.py:96`, `main.py:124`), `st.cache_resource` (`main.py:59-67`), `st.write_stream` (`main.py:239`), `st.secrets` (`local_llm.py:25`)
- sentence-transformers `3.4.1` — local embedding model wrapper (`local_embedding.py:7,23`); default model `all-MiniLM-L6-v2` (`local_embedding.py:13`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,40`)
- No NumPy / FAISS / scikit-learn as direct deps — `vector_index.py:8` is pure Python stdlib (`math`, `typing` only, `vector_index.py:11-12`); transitive deps (torch, transformers, huggingface-hub) arrive via sentence-transformers but are not pinned here
- pypdf `5.3.0` — PDF text extraction via `pypdf.PdfReader` (`pdf_reader.py:2,14`)
- langchain-text-splitters `0.3.6` — chunking via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:5,31-35`)
- groq `0.15.0` — cloud inference client `groq.Groq` (`local_llm.py:7-9,33`); guarded `try/except ImportError` with explicit install hint (`local_llm.py:6-9,20-21`)
- python-dotenv `1.0.1` — local `.env` loading via `load_dotenv()` (`main.py:19,66`)
- None detected — no pytest/unittest/jest/vitest config, no `tests/` directory, no `.eslintrc`/`ruff`/`mypy`/`pyproject.toml`/`setup.cfg`
## Key Dependencies
| Package | Version | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` | `main.py:18`, `local_llm.py:2` | UI runtime; app does not run without it |
| `pypdf` | `==5.3.0` | `pdf_reader.py:2,14` | PDF parsing; accepts file path or `BytesIO` stream (`main.py:132-135`, `pdf_reader.py:11`) |
| `python-dotenv` | `==1.0.1` | `main.py:19,66` | Loads `.env` for local dev before `AiModel()` reads env |
| `langchain-text-splitters` | `==0.3.6` | `pdf_reader.py:5,31` | Only langchain component used — chunking only, no chains/agents |
| `groq` | `==0.15.0` | `local_llm.py:7,33,73-78` | LLM inference; streaming chat completions endpoint |
| `sentence-transformers` | `==3.4.1` | `local_embedding.py:7,23,40` | Embedding inference; triggers HuggingFace model download on first run |
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — via sentence-transformers; model weights cached in `~/.cache/huggingface/` (`README.md:199`)
## Configuration
- Local dev: `.env` file in project root containing `GROQ_API_KEY` (`README.md:178-182`); loaded by `load_dotenv()` in `load_ai_model()` (`main.py:66`); `.env` is gitignored (`.gitignore:1`) and absent from working tree (verified — no `.env` file present)
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]` tried first in `local_llm.py:25`); no `.streamlit/secrets.toml` committed (verified — no `.streamlit/` directory)
- No build step — interpreted Python, no bundler, no `pyproject.toml`/`setup.py`/`Makefile`
- Devcontainer bootstrap: `[ -f requirements.txt ] && pip3 install --user -r requirements.txt; pip3 install --user streamlit` (`.devcontainer/devcontainer.json:21`)
## Platform Requirements
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download (`README.md:176`)
- A Groq API key (free at `console.groq.com`, `README.md:158`); HuggingFace token mentioned only in a code comment (`main.py:66` — `HF_TOKEN`) but never read in code; public `all-MiniLM-L6-v2` model needs no token
- Run: `pip install -r requirements.txt` then `streamlit run main.py` (`README.md:172-187`)
- Streamlit Community Cloud hosting Streamlit `1.42.0` app with `GROQ_API_KEY` set in the Cloud secrets panel; HuggingFace model re-downloaded and cached on first container boot (`README.md:199`); in-memory index only — no persistent volume required or used
## Entry Points
| Entry | Command | File |
|---|---|---|
| Streamlit app (sole entry point) | `streamlit run main.py` | `main.py:1-253` |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:22-23` |
| No CLI / module entry | No `if __name__ == "__main__"`, no `__main__.py`, no console-scripts | Not applicable |
- `main.py` — Streamlit front-end, session state, upload → index → chat → stream orchestration
- `local_llm.py` — `AiModel` class: Groq client init + `ask_a_question_from_pdf_stream` generator
- `local_embedding.py` — `LocalEmbedding` class: sentence-transformers wrapper + batch `build_index`
- `vector_index.py` — `VectorIndex` class: pure-stdlib in-memory cosine/Euclidean store
- `pdf_reader.py` — `PdfReader` class: pypdf extraction + langchain chunking with `{content, filename, page, chunk_id}` metadata
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Flat `snake_case.py` modules at repo root, one class per file (except `main.py`, which is the Streamlit entry point): `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`.
- No packages, no `__init__.py`, no barrel files. Imports are direct module imports (e.g. `from local_llm import AiModel` in `main.py:21`).
- `PascalCase`, one public class per module: `AiModel` (`local_llm.py:11`), `LocalEmbedding` (`local_embedding.py:11`), `VectorIndex` (`vector_index.py:15`), `PdfReader` (`pdf_reader.py:7`).
- `snake_case` throughout. Examples: `ask_a_question_from_pdf_stream` (`local_llm.py:36`), `build_index` / `get_embeddings` / `get_context` (`local_embedding.py:35,42,67`), `add_document` / `add_vector` / `search` (`vector_index.py:40,66,97`), `extract_text` / `get_paragraphs` (`pdf_reader.py:26,71`), `load_ai_model` / `save_uploaded_pdf` (`main.py:60,70`).
- Private helpers use a single leading underscore: `_embed_one` (`local_embedding.py:28`), `_cosine_distance` / `_euclidean_distance` / `_dot_product` / `_magnitude` (`vector_index.py:150,165,201,206`).
- Private state uses a single leading underscore: `_vector_dim`, `_distance_metric`, `_embedding_fn` (`vector_index.py:32-34`).
- `snake_case` locals and attributes: `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py:46-49`), `page_chunks`, `pages_text`, `filename` (`pdf_reader.py:16-23`), `groq_client`, `model_name` (`local_llm.py:18,33`).
- Constants are inline literals, not module-level `UPPER_CASE` names — e.g. `chunk_size=1000, chunk_overlap=200` (`pdf_reader.py:32-33`), `k=10` call sites (`main.py:216,233`, `local_llm.py:54`), `max_tokens=1024` (`local_llm.py:77`).
- `typing` generics used only in `vector_index.py` (`List`, `Dict`, `Tuple`, `Optional`, `Any` — `vector_index.py:12` plus annotations on every public method). `local_embedding.py` uses builtin generics sparingly (`list[float]`, `list[str]`, `list[tuple[dict, float]]`). `main.py`, `local_llm.py`, `pdf_reader.py` are mostly untyped except isolated hints (`-> str`, `-> AiModel`, `pdf_path: str, prompt: str`).
## Code Style
- No formatter configured (no `pyproject.toml`, `.prettierrc`, `setup.cfg`, `tox.ini`, `.flake8` in repo). Style is hand-maintained.
- 4-space indentation, ~100–120 char soft line length (longest lines are f-strings/prompts, e.g. `local_llm.py:56-62`, `main.py:138,175`).
- Mixed quote style: double quotes for code/strings, single-quoted `'''...'''` docstrings in `main.py:61-77` and `local_llm.py:13,37`, double-quoted `"""..."""` docstrings in `local_embedding.py` and `vector_index.py`. When adding code, match the surrounding file rather than normalising repo-wide.
- No linter configured and no lint step. No `ruff`/`flake8`/`pylint`/`mypy` config or CI job.
- Use the dashed banner comment to separate logical sections, with surrounding blank lines. Copy this exact shape when adding a section:
## Import Organization
- `main.py:14-23` — stdlib block, blank line, third-party block, blank line, local block.
- `vector_index.py:11-12` — stdlib-only module (`math`, `typing`).
- `local_llm.py:1-9` — `os`, `streamlit`, local imports, then guarded `groq` import in `try/except ImportError` (`local_llm.py:6-9`).
- `pdf_reader.py:1-5` — `re`, `pypdf`, blank lines, `langchain_text_splitters`.
- None. All imports are top-level absolute (`from vector_index import VectorIndex` in `local_embedding.py:8`).
- One function-level import exists: `import io` inside the upload loop (`main.py:131`). Do not copy this — hoist new stdlib imports to the top-level block. The top-level pattern is the convention; the inline `import io` is a one-off.
## Error Handling
- Fail fast with `TypeError` for wrong types and `ValueError` for bad values, before mutating state. New `VectorIndex` methods must follow this:
- Full guard inventory to mirror: metric whitelist (`vector_index.py:27-28`), missing embedding fn (`vector_index.py:51-52,115-116`), non-dict document / missing `content` key / non-string content (`vector_index.py:53-60,81-84`), dimension lock-in and mismatch (`vector_index.py:87-92,126-129`), bad query type (`vector_index.py:121`), vector-length checks in every distance helper (`vector_index.py:161-162,179-180,202-203`).
- Empty-store behaviour: `search()` returns `[]` instead of raising when nothing is indexed (`vector_index.py:110-111`).
- Use this shape for any new optional third-party import: `try/except ImportError → None` at top, explicit `ImportError` with install hint at use site.
- Missing `GROQ_API_KEY` raises `ValueError` with remediation text naming both secret locations. New required-config checks must raise with the same "what + where to set it" message shape.
- Per-file `try/except Exception as e` around `PdfReader` + `get_paragraphs()`, reporting via `st.error(f"... (Error: {e})")` then `continue` so one bad PDF never aborts the batch. New per-document processing must use this isolate-and-continue shape, never a bare `except:`.
- `paragraphs[-1]["page"] if paragraphs else 0` guards empty PDFs; `if chat_history:` / `if last_user_msgs:` guards history contextualisation; zero-magnitude vectors return `0.0`/`1.0` instead of dividing by zero. Preserve these guards when touching the same code.
## Logging
- Lifecycle prints with module prefix: `print(f"[LocalEmbedding] Loading {self.model_name}...")` (`local_embedding.py:22`), `print("[LocalEmbedding] Model ready.")` (`local_embedding.py:24`), `print(f"[LocalEmbedding] Indexed {len(chunks)} chunks.")` (`local_embedding.py:59`), `print(f"Successfully extracted text from {self.filename}. Total characters: {len(self.pages_text)}")` (`pdf_reader.py:60`), `print("running checks to make sure everything is good...")` (`local_llm.py:16`).
- User-facing feedback goes through Streamlit, never `print`: `st.error` / `st.info` / `st.success` / `st.status` / `st.write` (`main.py:96,129,138,144,167`). Rule: `print()` for developer diagnostics, `st.*` for anything the user should see.
## Comments
- Explain *why Streamlit behaves unusually*, not what the code does. Exemplar block (`main.py:41-43`): why the whole script reruns and why session state is the only persistence. Similar rationale comments at `main.py:66,75-76,93-94,195,203,222-224,229-231`.
- Algorithm notes where the math is non-obvious: L2-normalisation rationale (`local_embedding.py:39`), zero-vector guard (`vector_index.py:185`), float-drift clamp (`vector_index.py:192-193`).
- Every module except `local_llm.py`/`pdf_reader.py` has a top-of-file `"""..."""` summary stating inputs/outputs (`main.py:1-12`, `local_embedding.py:1-5`, `vector_index.py:1-9`). New modules must include one.
- Public methods carry docstrings; `vector_index.py` + `local_embedding.py` use Google-style `Args:`/`Returns:` blocks (`vector_index.py:97-109`, `local_embedding.py:13-20`); `local_llm.py`/`pdf_reader.py`/`main.py` helpers use terse `'''...'''` one-to-three-liners (`local_llm.py:37-40`, `pdf_reader.py:71-75`, `main.py:61-77`). Match the host file's docstring flavour when editing.
- Keep the commented-out runnable examples at the bottom of pure-logic modules (`vector_index.py:228-236`, `pdf_reader.py:85-88`) and update them if the API changes — they are the closest thing this repo has to usage specs.
- Not applicable (Python codebase; no JSDoc convention).
## Function Design
- Small single-purpose methods (5–25 lines). Largest functions are UI layout blocks in `main.py` (sidebar ~90 lines, chat handler ~40 lines) — these are sequential Streamlit layouts, not logic to extract, unless adding genuinely new UI sections.
- Keyword-friendly with sane defaults: `prompt: str = "tell me what is this pdf about", local_embedding=None, chat_history=None` (`local_llm.py:36`); `k: int = 3` (`local_embedding.py:61,67`, `vector_index.py:97`); `model_name: str = "all-MiniLM-L6-v2", distance_metric: str = "cosine"` (`local_embedding.py:13`). New retrieval parameters must default so existing call sites keep working.
- Dual-type flexibility where the codebase already does it: `PdfReader.__init__(self, file_or_path, filename=None)` accepts a path string, bytes stream, or file object (`pdf_reader.py:10-21`); `VectorIndex.search(query: Any, ...)` accepts a string or a precomputed vector (`vector_index.py:97-121`); `LocalEmbedding.build_index(chunks: list)` accepts `list[str]` or `list[dict]` (`local_embedding.py:42-54`). Extend with the same accept-both-types + normalise-early shape.
- Data methods return plain containers: `list[dict]` chunks with `content`/`filename`/`page`/`chunk_id` keys (`pdf_reader.py:51-56`), `list[tuple[dict, float]]` of `(document, distance)` sorted ascending (`vector_index.py:97-144`), joined context string (`local_embedding.py:67-72`).
- Generation is a token generator (`yield chunk.choices[0].delta.content` in `local_llm.py:80-82`) consumed by `st.write_stream`, which returns the full string (`main.py:239`). New LLM entry points must yield strings (not return a completed string) to preserve streaming.
- No `None`-on-error: failures raise, empty results return `[]`/`""`-adjacent empties (`vector_index.py:110-111`, `local_embedding.py:46-47`).
## Module Design
- Single public class per module, imported by name — no `__all__`, no factories, no re-exports. Wire new cross-module dependencies the same way (`from x import Y` at top level).
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
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, sidebar (model status + PDF upload + indexed-docs view), chat replay, chat input, source display, streaming render, session-state lifecycle, Clear All reset | `main.py` |
| AiModel | Groq client init + API-key resolution, RAG prompt assembly (system + history + user), retrieval orchestration, token-stream generator | `local_llm.py` |
| LocalEmbedding | SentenceTransformer wrapper (`all-MiniLM-L6-v2`), batch embedding with L2 normalisation, index build, search/get_context facade over VectorIndex | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search`; cosine + Euclidean distance; dimension locking; linear-scan k-NN | `vector_index.py` |
| PdfReader | PDF text extraction via `pypdf`, whitespace cleanup, `RecursiveCharacterTextSplitter` chunking (1000/200), chunk-dict construction with filename/page/chunk_id metadata | `pdf_reader.py` |
| Dev Container | Pinned Python 3.11 image, VS Code extensions, pip install hook, Streamlit auto-launch on port 8501 | `.devcontainer/devcontainer.json` |
## Pattern Overview
- UI-orchestrated pipeline — `main.py` owns the ingestion loop and the query loop; domain modules are stateless helpers except for the cached/singleton objects held in session state.
- Fully local retrieval, remote generation — embeddings (`sentence-transformers`) and vector search (`VectorIndex`) run in-process with no network; only LLM generation calls Groq Cloud (`local_llm.py:73-78`).
- Generator-based streaming — `ask_a_question_from_pdf_stream` is a Python generator yielding `delta.content` chunks; `st.write_stream` consumes it incrementally (`main.py:233-239`, `local_llm.py:80-82`).
- Single unified multi-document index — one `LocalEmbedding` instance accumulates chunks from all uploaded PDFs; `filename` metadata on each chunk preserves per-document attribution (`main.py:141-146`, `pdf_reader.py:51-56`).
## Layers
- Purpose: File upload, index-status display, conversational chat, streamed answer rendering.
- Location: `main.py`
- Contains: `st.set_page_config`, sidebar blocks, `st.file_uploader`, `st.chat_message` / `st.chat_input` / `st.write_stream`, `st.status` wrappers, `save_uploaded_pdf` helper.
- Depends on: `local_llm.py:AiModel`, `local_embedding.py:LocalEmbedding`, `pdf_reader.py:PdfReader`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.
- Purpose: Bytes-in, metadata-tagged text-chunks-out.
- Location: `pdf_reader.py`
- Contains: `PdfReader.__init__`, `PdfReader.extract_text`, `PdfReader.extract_small_portion_of_the_pdf`, `PdfReader.get_paragraphs`.
- Depends on: `pypdf.PdfReader`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `re`.
- Used by: `main.py:135-136` (upload path) and `local_llm.py:42-43` (fallback path when no index supplied).
- Purpose: Semantic embedding and nearest-neighbour lookup.
- Location: `local_embedding.py`, `vector_index.py`
- Contains: `LocalEmbedding.__init__/_embed_one/get_embeddings/build_index/search/get_context`; `VectorIndex.add_document/add_vector/search` plus `_cosine_distance/_euclidean_distance/_dot_product/_magnitude`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding layer only); vector store depends on stdlib `math` only.
- Used by: `main.py:142-145` (build) and `main.py:216` + `local_llm.py:54` (query).
- Purpose: Grounded answer synthesis with conversational memory.
- Location: `local_llm.py:36-82`
- Contains: `AiModel.__init__`, `AiModel.ask_a_question_from_pdf_stream`.
- Depends on: `groq.Groq`, `local_embedding.py:LocalEmbedding` (fallback construction), `pdf_reader.py:PdfReader` (fallback construction).
- Used by: `main.py:233-238`.
## Data Flow
### Primary Request Path — Ingestion (PDF upload → indexed vectors)
### Secondary Flow — Query (question → streamed grounded answer)
- `st.session_state` (per-browser-session, survives Streamlit full-script reruns): `indexed_files: set` (dedup guard), `document_metadata: dict` (filename → upload_time/pages/chunks), `local_embedding: LocalEmbedding | None` (the unified in-memory index), `chat_history: list` of `{role, content, sources}` dicts — all initialised in `main.py:45-52`. `Clear All` button resets all four keys and calls `st.rerun()` (`main.py:107-112`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` in `main.py:59-67` constructs `AiModel` (and its `Groq` client + `load_dotenv()`) exactly once; every rerun and every user session reuses the same instance. Embedding model is NOT cached this way — `LocalEmbedding`/`SentenceTransformer` lives inside `st.session_state`, so each browser session loads its own copy.
## Key Abstractions
- Purpose: Unit of retrieval — text plus provenance metadata threaded through every layer.
- Examples: produced in `pdf_reader.py:51-56`, stored in `vector_index.py:94-95`, read in `main.py:216-220` and `local_embedding.py:67-72`.
- Pattern: Plain `dict` with keys `content`, `filename`, `page`, `chunk_id` (e.g. `report.pdf_p2_3`). `VectorIndex` requires the `content` key (`vector_index.py:83-84`).
- Purpose: Single `LocalEmbedding`/`VectorIndex` pair accumulates chunks from every uploaded PDF so one `search()` call spans all documents.
- Examples: `main.py:141-145` (incremental `build_index` per new file), `main.py:187-191` (total-chunk count aggregation).
- Pattern: Append-only growth; no per-document isolation, no persistence, no deletion except full reset via Clear All.
- Purpose: Decouple token production (Groq) from token rendering (Streamlit).
- Examples: `local_llm.py:36-82` (producer), `main.py:233-239` (consumer via `st.write_stream`).
- Pattern: Generator function yielding `str` fragments; caller never buffers — `st.write_stream` both renders incrementally and returns the full string.
- Purpose: Cheap conversational memory for retrieval — prepend last user question so follow-ups ("what about Q2?") retrieve correctly.
- Examples: `local_llm.py:47-52`.
- Pattern: String concatenation of `last_user_msg + " " + prompt` before embedding; full message-list history is separately passed to the LLM (`local_llm.py:66-70`).
## Entry Points
- Location: `main.py`
- Triggers: `streamlit run main.py` (local, per `README.md:186` and `main.py:253` comment); dev container `postAttachCommand` in `.devcontainer/devcontainer.json:26-28`; Streamlit Community Cloud via live demo link.
- Responsibilities: Everything user-facing — `st.set_page_config` must be the first Streamlit call (`main.py:30-35`); then session-state init, cached model load, sidebar upload/index loop, main-area chat loop.
- Location: `local_llm.py:36-45`
- Triggers: Calling `AiModel().ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then proceeds with retrieval + generation. Not exercised by `main.py` (which always passes an existing index and `pdf_path=""`).
## Architectural Constraints
- **Threading:** Single-threaded Streamlit script model — the entire `main.py` reruns top-to-bottom on every interaction; long work (model load, embedding) blocks the script and is masked with `st.status` spinners (`main.py:96-98`, `main.py:124`). Token streaming is incremental rendering, not background threading (`main.py:239`).
- **Global state:** `st.cache_resource`-cached `AiModel` + `Groq` client shared across all sessions in the server process (`main.py:59-67`); per-session `LocalEmbedding` + `SentenceTransformer` model + `VectorIndex` vectors held in `st.session_state` (`main.py:45-52`). No other module-level singletons — `VectorIndex` internals (`vectors`, `documents`, `_vector_dim`) are instance-scoped (`vector_index.py:30-34`).
- **Circular imports:** None. Dependency direction is strictly one-way: `main.py` → `local_llm.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py` → `pdf_reader.py`; `pdf_reader.py` has no project imports.
- **In-memory only:** `VectorIndex` never touches disk; restarting the server or opening a new browser session loses the index and requires re-upload (`README.md:228`).
- **Linear scan:** `VectorIndex.search` computes distance against every stored vector and sorts (`vector_index.py:138-144`) — O(n) per query, no ANN structure.
## Anti-Patterns
### Double retrieval per question (duplicate embedding + scan)
### Dead fallback parameter (`pdf_path`, `save_uploaded_pdf`)
## Error Handling
- Per-file upload guard — `try/except` around `PdfReader` + `get_paragraphs` in `main.py:134-139` shows `st.error` with filename and exception text and `continue`s to the next file, so one corrupt PDF never aborts the batch.
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content` key, non-numeric vectors, dimension mismatch, `k <= 0` (`vector_index.py:27-28, 52-60, 77-92, 121-132`); `AiModel.__init__` raises `ImportError` (missing `groq` package) and `ValueError` (missing `GROQ_API_KEY`) (`local_llm.py:20-30`).
- No retry/timeout handling on the Groq stream — network or rate-limit errors during `chat.completions.create` propagate uncaught and surface as a Streamlit exception page (`local_llm.py:73-82` has no try/except; `main.py` has none around the stream call).
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
