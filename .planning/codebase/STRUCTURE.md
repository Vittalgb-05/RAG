# Codebase Structure

**Analysis Date:** 2026-10-10

## Directory Layout

```
RAG/
├── main.py                  # Streamlit UI — entry point (253 lines)
├── local_llm.py             # AiModel: Groq RAG orchestration + streaming (82 lines)
├── local_embedding.py       # LocalEmbedding: embedding wrapper + index facade (72 lines)
├── vector_index.py          # VectorIndex: pure-stdlib vector store (236 lines)
├── pdf_reader.py            # PdfReader: PDF extraction + chunking (88 lines)
├── requirements.txt         # Pinned dependencies (6 entries)
├── README.md                # Project docs, architecture diagram, setup guide (238 lines)
├── application_screenshots/ # UI screenshots referenced by README (3 PNGs)
│   ├── image.png            # Active conversation screenshot
│   ├── image_2.png          # Upload / ready-state screenshot
│   └── mermaid_diagram.png  # Pipeline diagram image
├── .devcontainer/
│   └── devcontainer.json    # Python 3.11 container + Streamlit launch config
├── .planning/
│   └── codebase/            # GSD codebase maps (this directory)
└── .git/                    # Git history (not application code)
```

## Directory Purposes

**Repo root (`./`):**
- Purpose: Entire application — flat layout, no packages or submodules; all Python modules live at top level and import each other by bare module name.
- Contains: 4 Python source files, `requirements.txt`, `README.md`, plus support directories.
- Key files: `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `requirements.txt`

**`application_screenshots/`:**
- Purpose: Static documentation assets embedded in `README.md` only; never loaded by application code.
- Contains: `image.png` (active chat), `image_2.png` (upload screen), `mermaid_diagram.png` (pipeline diagram asset).
- Key files: `application_screenshots/image.png`, `application_screenshots/image_2.png`

**`.devcontainer/`:**
- Purpose: Reproducible dev environment for VS Code / GitHub Codespaces.
- Contains: Single `devcontainer.json` — base image `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`, Python + Pylance extensions, pip-install hook, Streamlit auto-start on port 8501.
- Key files: `.devcontainer/devcontainer.json`

**`.planning/codebase/`:**
- Purpose: GSD-generated codebase reference docs (`ARCHITECTURE.md`, `STRUCTURE.md`, etc.).
- Contains: Markdown analysis documents only; not imported by any Python module.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`

## Key File Locations

**Entry Points:**
- `main.py`: Sole runnable entry — `streamlit run main.py` (`README.md:186`, `main.py:253` comment, `.devcontainer/devcontainer.json:26-28` post-attach command). Owns page config, session state, upload loop, chat loop.

**Configuration:**
- `requirements.txt`: Pinned runtime deps — `streamlit==1.42.0`, `pypdf==5.3.0`, `python-dotenv==1.0.1`, `langchain-text-splitters==0.3.6`, `groq==0.15.0`, `sentence-transformers==3.4.1`.
- `.devcontainer/devcontainer.json`: Container image, extensions (`ms-python.python`, `ms-python.vscode-pylance`), `updateContentCommand` pip install, port 8501 forwarding.
- `.env` (not committed, gitignored): Local `GROQ_API_KEY` storage loaded via `load_dotenv()` in `main.py:66`; production equivalent is Streamlit `secrets` (`local_llm.py:25`).
- `.gitignore`: Excludes `.env`, `.venv`, caches (verify before committing secrets-adjacent files).

**Core Logic:**
- `pdf_reader.py`: Ingestion — `PdfReader` class.
- `local_embedding.py`: Embedding — `LocalEmbedding` class.
- `vector_index.py`: Storage/search — `VectorIndex` class.
- `local_llm.py`: Generation — `AiModel` class.

**Testing:**
- No test files, test directories, or test-runner config detected — `pytest`, `unittest`, `*.test.py`, `test_*` all absent. Verification is manual via Streamlit UI.

**Documentation:**
- `README.md`: What-is, screenshots, feature list, How-It-Works pipeline, ASCII architecture diagram (`README.md:94-132`), project structure, install/deploy, usage workflow, tech stack, limitations, future improvements.
- `application_screenshots/*.png`: README illustration assets.

## Naming Conventions

**Files:**
- Flat `snake_case` module names mapping 1:1 to the single class inside: `local_llm.py` → `AiModel`, `local_embedding.py` → `LocalEmbedding`, `vector_index.py` → `VectorIndex`, `pdf_reader.py` → `PdfReader`. Entry point is the bare `main.py` (Streamlit convention).

**Directories:**
- `lowercase` with underscores where needed (`application_screenshots`, `.devcontainer`, `.planning`). No Python packages — no `__init__.py` anywhere.

**Classes / Functions / Variables:**
- Classes use `PascalCase` (`AiModel`, `LocalEmbedding`, `VectorIndex`, `PdfReader`).
- Functions and methods use `snake_case` with verb-first names (`extract_text`, `get_paragraphs`, `build_index`, `get_embeddings`, `ask_a_question_from_pdf_stream`, `save_uploaded_pdf`, `load_ai_model`, `add_vector`, `add_document`).
- Private helpers use single-leading-underscore (`_embed_one`, `_embedding_fn`, `_cosine_distance`, `_euclidean_distance`, `_dot_product`, `_magnitude`, `_vector_dim`, `_distance_metric`).
- Session-state keys use `snake_case` (`indexed_files`, `document_metadata`, `local_embedding`, `chat_history`); chunk-dict keys likewise (`content`, `filename`, `page`, `chunk_id`).

## Where to Add New Code

**New Feature (e.g. new ingestion source, new query mode):**
- Primary code: Add the domain logic to the matching existing module (`pdf_reader.py` for parsing, `local_embedding.py`/`vector_index.py` for retrieval, `local_llm.py` for generation), then wire the UI trigger + rendering in `main.py` (sidebar block or chat-loop block).
- Tests: No test harness exists — verify manually via `streamlit run main.py`.

**New Component/Module (e.g. reranker, persistent store, eval script):**
- Implementation: Create a new top-level `snake_case` module (e.g. `reranker.py`) exposing one class, mirroring the existing one-file-one-class pattern; import by bare name (`from reranker import Reranker`) as done in `main.py:21-23` and `local_llm.py:3-4`.

**Utilities:**
- Shared helpers: No `utils/` directory exists — small UI helpers live inline in `main.py` (e.g. `save_uploaded_pdf` at `main.py:70-81`, `load_ai_model` at `main.py:59-67`); small domain helpers live as private methods on the owning class (e.g. `LocalEmbedding._embed_one` at `local_embedding.py:28-33`).

**Configuration / Dependencies:**
- Runtime deps: Append a pinned entry in `requirements.txt`.
- Secrets: Local key in untracked `.env` (`GROQ_API_KEY=...`); cloud key in Streamlit secrets — both consumed by `local_llm.py:23-27`, no code change needed for new env vars beyond reading them there.

## Per-File Responsibility Table

| File | Responsibility | Key classes / functions |
|------|----------------|------------------------|
| `main.py` | Streamlit UI + pipeline orchestration: page config, session-state init, cached model load, sidebar upload/index loop, chat replay + input, source badges, streamed rendering, Clear All reset | `load_ai_model() -> AiModel` (`st.cache_resource` singleton); `save_uploaded_pdf(uploaded_file) -> str` (unused tempfile helper); inline sidebar + chat-loop blocks |
| `local_llm.py` | Remote generation + RAG assembly: Groq client setup, query contextualisation, context retrieval, system/history/user message construction, streamed completion | `AiModel.__init__` (API-key resolution, `Groq()` client, `model_name="openai/gpt-oss-20b"`); `AiModel.ask_a_question_from_pdf_stream(pdf_path, prompt, local_embedding, chat_history)` (generator yielding `str` tokens) |
| `local_embedding.py` | Local embedding facade: MiniLM model lifecycle, batch L2-normalised encoding, index build, top-k search + context-string formatting | `LocalEmbedding.__init__(model_name="all-MiniLM-L6-v2", distance_metric="cosine")`; `_embed_one(text)`; `get_embeddings(texts)`; `build_index(chunks)`; `search(question, k)`; `get_context(question, k)` |
| `vector_index.py` | In-memory k-NN store: vector/document parallel lists, dimension locking, string-or-vector query path, cosine/Euclidean scan, math helpers, `len`/`repr` | `VectorIndex.__init__(distance_metric, embedding_fn)`; `add_document(document)`; `add_vector(vector, document)`; `search(query, k)`; `_cosine_distance`, `_euclidean_distance`, `_dot_product`, `_magnitude`; `__len__`, `__repr__` |
| `pdf_reader.py` | PDF ingestion: `pypdf` page extraction, whitespace cleanup, LangChain recursive splitting, per-chunk provenance metadata | `PdfReader.__init__(file_or_path, filename)`; `extract_text()`; `extract_small_portion_of_the_pdf(min, max)`; `get_paragraphs()` |
| `requirements.txt` | Dependency pins for local venv + Streamlit Cloud + dev container installs | N/A (data file, 6 pins) |
| `.devcontainer/devcontainer.json` | Containerised dev/launch config | N/A (JSON config) |

## Module Dependency Graph

```text
main.py
 ├──→ local_llm.py :: AiModel
 │       ├──→ local_embedding.py :: LocalEmbedding
 │       │       ├──→ vector_index.py :: VectorIndex  (via embedding_fn=_embed_one callback)
 │       │       └──→ sentence_transformers.SentenceTransformer (external)
 │       ├──→ pdf_reader.py :: PdfReader (fallback path only)
 │       └──→ groq.Groq (external)
 ├──→ local_embedding.py :: LocalEmbedding   (upload/index + source lookup)
 └──→ pdf_reader.py :: PdfReader             (upload path: BytesIO → chunks)

local_embedding.py ──→ vector_index.py :: VectorIndex
pdf_reader.py ──→ pypdf + langchain_text_splitters (external only, no project imports)
vector_index.py ──→ math, typing (stdlib only — zero project/external deps)
```

**Import facts:**
- `main.py:21-23` imports all three domain classes (`AiModel`, `LocalEmbedding`, `PdfReader`) but never imports `VectorIndex` directly — it reaches the store only through `LocalEmbedding.store` (`local_embedding.py:26`).
- `local_llm.py:3-4` imports `PdfReader` and `LocalEmbedding` for its headless fallback (`local_llm.py:41-45`); it never imports `VectorIndex` or `streamlit`-UI helpers.
- `local_embedding.py:7-8` imports `SentenceTransformer` + `VectorIndex`; direction is one-way, no cycles.
- `pdf_reader.py:1-5` and `vector_index.py:11-12` import only third-party/stdlib packages — they are the dependency leaves.
- `groq` is an optional import guarded by `try/except` with `Groq = None` fallback and an explicit `ImportError` in `AiModel.__init__` (`local_llm.py:6-9, 20-21`).

---

*Structure analysis: 2026-10-10*
