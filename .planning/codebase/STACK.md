# Technology Stack

**Analysis Date:** 2026-10-10

## Languages

**Primary:**
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`)
  - Devcontainer pins Python 3.11 (`mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` in `.devcontainer/devcontainer.json:4`)
  - README badge declares Python 3.11+ (`README.md:9`); prerequisites table requires Python 3.11+ (`README.md:156`)
  - Local shell reports Python 3.13.5, so any 3.11+ interpreter works; no version pin in `requirements.txt`

**Secondary:**
- JSON — devcontainer config only (`.devcontainer/devcontainer.json`)
- Markdown — docs only (`README.md`)
- No JavaScript/TypeScript, no CSS, no SQL — UI is 100% Streamlit Python

## Runtime

**Environment:**
- Local: CPython via `streamlit run main.py` (entry documented in `main.py:252-253`, `README.md:186`, `README.md:194`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py` (`.devcontainer/devcontainer.json:7-10`), serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:22-23,30-32`)
- Production: Streamlit Community Cloud (live demo at `https://rag1818.streamlit.app/` per `README.md:7`); no Dockerfile, no `packages.txt`, no `runtime.txt`

**Package Manager:**
- pip with pinned `requirements.txt` (all `==` pins)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`; activation documented as `source .venv/Scripts/activate` on Windows Git Bash in `main.py:252`, `README.md:169`)

## Frameworks

**Core:**
- Streamlit `1.42.0` — entire UI layer: `st.set_page_config` (`main.py:30-35`), sidebar (`main.py:88-175`), `st.file_uploader` (`main.py:114-120`), `st.chat_input` / `st.chat_message` (`main.py:197-212`), `st.status` (`main.py:96`, `main.py:124`), `st.cache_resource` (`main.py:59-67`), `st.write_stream` (`main.py:239`), `st.secrets` (`local_llm.py:25`)

**ML / Data:**
- sentence-transformers `3.4.1` — local embedding model wrapper (`local_embedding.py:7,23`); default model `all-MiniLM-L6-v2` (`local_embedding.py:13`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,40`)
- No NumPy / FAISS / scikit-learn as direct deps — `vector_index.py:8` is pure Python stdlib (`math`, `typing` only, `vector_index.py:11-12`); transitive deps (torch, transformers, huggingface-hub) arrive via sentence-transformers but are not pinned here

**PDF / Text:**
- pypdf `5.3.0` — PDF text extraction via `pypdf.PdfReader` (`pdf_reader.py:2,14`)
- langchain-text-splitters `0.3.6` — chunking via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:5,31-35`)

**LLM client:**
- groq `0.15.0` — cloud inference client `groq.Groq` (`local_llm.py:7-9,33`); guarded `try/except ImportError` with explicit install hint (`local_llm.py:6-9,20-21`)

**Config:**
- python-dotenv `1.0.1` — local `.env` loading via `load_dotenv()` (`main.py:19,66`)

**Testing / Linting / Typing:**
- None detected — no pytest/unittest/jest/vitest config, no `tests/` directory, no `.eslintrc`/`ruff`/`mypy`/`pyproject.toml`/`setup.cfg`

## Key Dependencies

Pinned in `requirements.txt` (6 lines total):

| Package | Version | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` | `main.py:18`, `local_llm.py:2` | UI runtime; app does not run without it |
| `pypdf` | `==5.3.0` | `pdf_reader.py:2,14` | PDF parsing; accepts file path or `BytesIO` stream (`main.py:132-135`, `pdf_reader.py:11`) |
| `python-dotenv` | `==1.0.1` | `main.py:19,66` | Loads `.env` for local dev before `AiModel()` reads env |
| `langchain-text-splitters` | `==0.3.6` | `pdf_reader.py:5,31` | Only langchain component used — chunking only, no chains/agents |
| `groq` | `==0.15.0` | `local_llm.py:7,33,73-78` | LLM inference; streaming chat completions endpoint |
| `sentence-transformers` | `==3.4.1` | `local_embedding.py:7,23,40` | Embedding inference; triggers HuggingFace model download on first run |

**Transitive (unpinned, pulled automatically):**
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — via sentence-transformers; model weights cached in `~/.cache/huggingface/` (`README.md:199`)

## Configuration

**Environment:**
- Local dev: `.env` file in project root containing `GROQ_API_KEY` (`README.md:178-182`); loaded by `load_dotenv()` in `load_ai_model()` (`main.py:66`); `.env` is gitignored (`.gitignore:1`) and absent from working tree (verified — no `.env` file present)
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]` tried first in `local_llm.py:25`); no `.streamlit/secrets.toml` committed (verified — no `.streamlit/` directory)

**Build:**
- No build step — interpreted Python, no bundler, no `pyproject.toml`/`setup.py`/`Makefile`
- Devcontainer bootstrap: `[ -f requirements.txt ] && pip3 install --user -r requirements.txt; pip3 install --user streamlit` (`.devcontainer/devcontainer.json:21`)

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download (`README.md:176`)
- A Groq API key (free at `console.groq.com`, `README.md:158`); HuggingFace token mentioned only in a code comment (`main.py:66` — `HF_TOKEN`) but never read in code; public `all-MiniLM-L6-v2` model needs no token
- Run: `pip install -r requirements.txt` then `streamlit run main.py` (`README.md:172-187`)

**Production:**
- Streamlit Community Cloud hosting Streamlit `1.42.0` app with `GROQ_API_KEY` set in the Cloud secrets panel; HuggingFace model re-downloaded and cached on first container boot (`README.md:199`); in-memory index only — no persistent volume required or used

## Entry Points

| Entry | Command | File |
|---|---|---|
| Streamlit app (sole entry point) | `streamlit run main.py` | `main.py:1-253` |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:22-23` |
| No CLI / module entry | No `if __name__ == "__main__"`, no `__main__.py`, no console-scripts | Not applicable |

**Module roles:**
- `main.py` — Streamlit front-end, session state, upload → index → chat → stream orchestration
- `local_llm.py` — `AiModel` class: Groq client init + `ask_a_question_from_pdf_stream` generator
- `local_embedding.py` — `LocalEmbedding` class: sentence-transformers wrapper + batch `build_index`
- `vector_index.py` — `VectorIndex` class: pure-stdlib in-memory cosine/Euclidean store
- `pdf_reader.py` — `PdfReader` class: pypdf extraction + langchain chunking with `{content, filename, page, chunk_id}` metadata

---

*Stack analysis: 2026-10-10*
