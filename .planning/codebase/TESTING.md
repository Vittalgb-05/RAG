# Testing Patterns

**Analysis Date:** 2026-10-10

## Test Framework

**Runner:** NONE FOUND — no test framework is installed or configured.

- `requirements.txt` contains exactly six runtime packages and zero test packages: `streamlit==1.42.0`, `pypdf==5.3.0`, `python-dotenv==1.0.1`, `langchain-text-splitters==0.3.6`, `groq==0.15.0`, `sentence-transformers==3.4.1`. No `pytest`, `unittest` extras, `coverage`, `tox`, `nox`, or mocking library.
- No config files exist: no `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `conftest.py`, `setup.py`, or CI test job. A repo-wide grep for `pytest|unittest|assert |def test_` returns zero hits outside this document.
- There is no `tests/` directory and no `*.test.*` / `test_*` / `*_test.py` / `*.spec.*` files anywhere in the repo (glob `**/*test*` returns nothing).

**Assertion library:** None (stdlib `assert` is not used in shipped code).

**Run commands:**
```bash
# There is no test suite, so there is no test command.
# The only verified run path is the app itself:
pip install -r requirements.txt
streamlit run main.py     # manual verification in the browser (default http://localhost:8501)
```

## Test File Organization

**Location:** NONE FOUND — no test files exist to establish a pattern.

**Naming:** Not applicable — nothing to follow. If introducing tests, use the standard pytest layout so the (currently absent) runner needs zero custom config:
```
tests/
├── test_vector_index.py
├── test_pdf_reader.py
├── test_local_embedding.py
└── test_local_llm.py
```

**Structure:** Not applicable — no existing suites to mirror.

## Test Structure

**Suite organization:** No existing pattern. The codebase's own closest analogue is the commented-out runnable examples at the bottom of `vector_index.py:228-236` and `pdf_reader.py:81-88` — treat those as informal usage specs when writing the first real tests, and update them if the API changes.

**Patterns:** None established (no setup/teardown/assertion idioms in repo).

## Mocking

**Framework:** None installed. If tests are added, add `pytest` first; `unittest.mock` (stdlib) is sufficient for the seams below — no extra mocking dependency is needed.

**What to mock (seams identified from source):**
- `groq.Groq.chat.completions.create` (`local_llm.py:73-78`) — never hit the paid/cloud API from tests; yield canned `delta.content` chunks.
- `sentence_transformers.SentenceTransformer.encode` (`local_embedding.py:40`) — embedding-model loads are slow and download weights on first run; stub with fixed 384-dim vectors.
- `streamlit.secrets` / `os.environ` (`local_llm.py:24-27`) — inject a fake `GROQ_API_KEY` per test.
- `pypdf.PdfReader` (`pdf_reader.py:14`) — feed synthetic in-memory PDFs or stub `pages[].extract_text()`.

**What NOT to mock:**
- `VectorIndex` math itself (`vector_index.py:150-207`) — it is pure stdlib (`math` only) and is the highest-value real-logic target; test it directly with hand-computed vectors.
- `RecursiveCharacterTextSplitter` behaviour (`pdf_reader.py:31-35`) — assert on observable chunk overlap/count rather than mocking the splitter.

## Fixtures and Factories

**Test data:** None exist. Suggested minimal fixtures when bootstrapping:
```python
# No existing fixture pattern — proposed starter shape only:
import io
DOCS = [
    {"content": "red", "filename": "a.pdf", "page": 1, "chunk_id": "a.pdf_p1_0"},
    {"content": "green", "filename": "a.pdf", "page": 1, "chunk_id": "a.pdf_p1_1"},
]
VECTORS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
```

**Location:** None — create `tests/fixtures/` (e.g. a tiny synthetic PDF) only when needed; do not commit real user PDFs or secrets.

## Coverage

**Requirements:** None enforced — no coverage tool, threshold, or gate.

**View coverage:** Not applicable. To introduce it:
```bash
pip install pytest pytest-cov
pytest --cov=. --cov-report=term-missing
```

## Test Types

**Unit tests:** NONE FOUND. Highest-value first targets (all currently untested):
- `VectorIndex` (`vector_index.py:40-144`) — `add_vector` dimension lock-in/mismatch, `add_document` validation branches, `search` ordering by ascending distance, `k` edge cases (`k<=0`, `k > count`), empty-index `[]`, string-query without embedding fn, cosine vs euclidean selection, zero-vector guards (`vector_index.py:186-189`), float-drift clamp (`vector_index.py:192-193`), `__len__`/`__repr__`.
- `PdfReader` (`pdf_reader.py:10-78`) — `filename` fallback chain (explicit arg → path basename → `.name` attr → `unknown.pdf`), whitespace collapse (`re.sub(r' +', ...)`), `chunk_size=1000/chunk_overlap=200` splitting, `chunk_id` format `{filename}_p{page}_{j}`, `pages_text` join, lazy `extract_text()` from `get_paragraphs()`/`extract_small_portion_of_the_pdf()`, `None` (image-only) page handling via `if page_text:`.
- `LocalEmbedding` (`local_embedding.py:28-72`) — empty-chunk early return, `str` vs `dict` input normalisation, batch-embed delegation, `_embed_one` list conversion, `get_context` `"\n\n---\n\n"` join, default `k=3` vs call-site `k=10`.
- `AiModel` (`local_llm.py:11-82`) — secrets→env→`ValueError` precedence, missing-`groq` `ImportError`, history contextualisation (`last_user_msgs[-1] + prompt`), system-prompt grounding assembly, message ordering (system → history → current prompt), streaming `yield` of `delta.content` including falsy-delta skips.

**Integration tests:** NONE FOUND. Untested paths: `PdfReader.get_paragraphs()` → `LocalEmbedding.build_index()` → `VectorIndex.search()` → `get_context()` end-to-end; `AiModel.ask_a_question_from_pdf_stream` fallback path that builds its own index when `local_embedding is None` (`local_llm.py:41-45`); multi-document accumulation and `Clear All` reset in `main.py:107-112,122-162`.

**E2E tests:** Not used — no Playwright/Selenium/Cypress. E2E is manual via the browser (see below).

## Manual Test Workflow (the actual QA process)

This is the only verification method the repo supports today (`README.md:191-208`, run footer `main.py:248-253`):

```bash
source .venv/Scripts/activate   # Windows (Git Bash); macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# create .env with: GROQ_API_KEY=gsk_your_groq_key_here  (gitignored per .gitignore:1)
streamlit run main.py
```

1. Wait for **"LLM ready — Groq Cloud"** sidebar status (`main.py:96-98`). Failure here means `GROQ_API_KEY` resolution failed (`local_llm.py:24-30`) — check `.env` / Streamlit secrets.
2. Upload one PDF → expect `st.status("Processing documents…")` → `Indexed N document(s)` plus per-file `st.success` with pages/chunks/timestamp (`main.py:124-170`).
3. Ask a question in `st.chat_input` → expect `Sources used` info line then token-by-token streamed answer (`main.py:215-239`).
4. Ask 2–3 follow-ups → history-aware retrieval should stay coherent (last-10-messages window, `main.py:231`).
5. Upload a second PDF → index should accumulate; `Clear All` (`main.py:107-112`) should reset `indexed_files`, `document_metadata`, `local_embedding`, `chat_history`.
6. Negative case: upload a corrupted/empty/non-PDF file → expect per-file `st.error` and remaining files still index (`main.py:137-139`).
7. First-run note: `all-MiniLM-L6-v2` downloads from HuggingFace Hub to `~/.cache/huggingface/`; slow first start is expected (`README.md:199`).

## Common Patterns

**Async testing:** Not applicable — the codebase is synchronous except for the streaming generator, which is consumed synchronously (`for chunk in stream: ... yield ...` in `local_llm.py:80-82`, rendered by `st.write_stream` in `main.py:239`).

**Error testing:** No pattern established. Priority error cases for the first suite: `ValueError` on bad `distance_metric` (`vector_index.py:27-28`), `TypeError`/`ValueError` on malformed vectors/documents (`vector_index.py:77-84`), dimension mismatch on add and query (`vector_index.py:89-92,126-129`), `k<=0` (`vector_index.py:131-132`), `ValueError` without embedding fn (`vector_index.py:51-52,115-116`), `TypeError` on bad query type (`vector_index.py:121`), `ImportError`/`ValueError` on missing `groq`/API key (`local_llm.py:19-30`).

## Coverage Gaps (priority-ordered)

- **High — `VectorIndex` distance correctness:** cosine/euclidean math, ascending-sort ordering, `k` truncation, and zero-vector handling have zero tests despite being the retrieval core (`vector_index.py:97-207`).
- **High — `AiModel` prompt assembly:** grounding system prompt, history ordering, and search-query contextualisation are untested; a regression silently degrades answer quality (`local_llm.py:47-70`).
- **High — API-key resolution:** the `st.secrets` → `.env` → raise chain (`local_llm.py:24-30`) is deployment-critical and untested; local-vs-cloud divergence would only surface at runtime.
- **Medium — `PdfReader` chunking/metadata:** chunk overlap, `chunk_id` uniqueness, page attribution, and `filename` fallback are untested (`pdf_reader.py:10-61`).
- **Medium — `main.py` session-state machine:** indexed-file dedup (`main.py:127`), metadata bookkeeping (`main.py:148-152`), history reset on new upload (`main.py:154-156`), sources extraction (`main.py:216-220`), and history windowing (`main.py:231`) can only be verified manually today.
- **Low — streaming plumbing:** generator passthrough (`local_llm.py:80-82`) and `st.write_stream` accumulation (`main.py:239`) need a Streamlit harness; defer until unit coverage exists.

---

*Testing analysis: 2026-10-10*
