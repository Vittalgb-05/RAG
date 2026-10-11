# Testing Patterns

**Analysis Date:** 2026-10-11

## Test Framework

**Runner:**
- `pytest` (`>=8.3.0` via `requirements-test.txt:2`; CI installs both requirements files)
- Config: `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`

**Assertion Library:**
- stdlib `assert` + `pytest.raises` / `pytest.approx` + `pydantic.ValidationError`. `unittest.mock.MagicMock` for injected collaborators. `sqlite3.IntegrityError` for constraint tests. No `pytest-mock` `mocker` fixture usage in the suite (`pytest-mock` is no longer installed — it was dropped from CI with the move to `requirements-test.txt`).

**Run Commands:**
```bash
pip install -r requirements.txt
pip install -r requirements-test.txt   # pytest, reportlab, ruff, psutil (CI line, .github/workflows/ci.yml:28)
python tests/data/corpus/generate_corpus.py            # REQUIRED first — tests read corpus PDFs from disk
pytest tests/ -v                                        # run all 44 tests
pytest tests/test_models.py -v                          # single file
pytest tests/test_doc_store.py tests/test_upload_validation.py -v   # Phase 1 slice
ruff check .                                            # lint gate (must pass before push)
ruff format --check .                                   # format gate (must pass before push)
```

## Test File Organization

**Location:**
- `tests/` package (marker `tests/__init__.py`: `"""Tests package initialization."""`)

**Naming:**
- `tests/test_<module>.py` mirroring each source module; shared fixtures in `tests/conftest.py`

**Structure:**
```
tests/
├── __init__.py                  # package marker
├── conftest.py                  # 4 shared fixtures (fake_env_groq_key, mock_groq_client,
│                                #   mock_sentence_transformer, sample_pdf_path)
├── test_vector_index.py         # 7 tests — distance math, guards, ranking, edge cases
├── test_pdf_reader.py           # 9 tests — extraction, chunking, BytesIO, scanned limit,
│                                #   corrupt rejection, dense table, chart, fault isolation, rename stability
├── test_local_embedding.py      # 3 tests — init, build_index, get_context (all mocked transformer)
├── test_local_llm.py            # 3 tests — missing-key, prompt assembly, streaming yield
├── test_models.py               # 10 tests — legacy-key compat, frozen/hash, extra-forbid,
│                                #   SHA pattern, JSON round-trip, bbox compat, page/evidence,
│                                #   config version, tracer slice, backward-compat read
├── test_doc_store.py            # 6 tests — round-trip, SHA-unique, page failure, interleave,
│                                #   user_version, chunk nullable columns
├── test_upload_validation.py    # 6 tests — corrupt rejection (WR-07), valid accept+hash,
│                                #   rename stability, oversize, over-page, streaming stability
└── data/corpus/
    ├── generate_corpus.py       # deterministic reportlab generator (6 synthetic PDFs)
    ├── clean_digital.pdf        # 20-page digital doc (regenerated artifact, committed)
    ├── multi_column.pdf         # 2-page two-column layout
    ├── dense_table.pdf          # quarterly financial table
    ├── scanned_sample.pdf       # raster-only, zero text layer (vector rects, no drawString)
    ├── chart_diagram.pdf        # architecture flowchart boxes
    └── corrupt_invalid.pdf      # raw invalid bytes (NOT_A_VALID_PDF_HEADER…)
```

**Suite size:** 44 tests collected (`pytest --collect-only`), 44/44 passing (`pytest tests/ -q` in ~10 s), alongside `ruff check .` clean and `ruff format --check .` clean (18 files, `ruff 0.15.12`). Phase 1 grew the suite 17 → 35 (plan 01-01: `test_models.py` + `test_doc_store.py`) → 44 (plan 01-02: `test_upload_validation.py` + 4 new `test_pdf_reader.py` tests + 3 new `test_models.py` tests), per `01-01-SUMMARY.md:52-54` and `01-02-SUMMARY.md:61-63`.

## Test Structure

**Suite Organization:**
```python
# ------------------------------------------------------------------
# Unit Tests for Canonical Models (models.py)
# Verifies schema validation, legacy dictionary key compatibility,
# immutability, extra-field forbidding, and JSON serialization.
# ------------------------------------------------------------------

import pytest
from pydantic import ValidationError
from models import BBox, Chunk, Document, EvidenceElement, Page, CONFIG_VERSION, cache_dir_for
from pathlib import Path


def test_chunk_dump_matches_legacy_keys():
    """Verify Chunk.model_dump() retains all 4 legacy dictionary keys with identical values."""
    chunk = Chunk(
        content="Sample extracted text chunk.",
        filename="report.pdf",
        page=1,
        chunk_id="report.pdf_p1_0",
        doc_id="doc_1234567890abcdef",
    )
    dumped = chunk.model_dump()

    # Legacy callers expect content, filename, page, chunk_id
    assert dumped["content"] == "Sample extracted text chunk."
    ...
```
(`tests/test_models.py:1-34` — the Phase 1 model shape: banner header, one `test_*` per behavior, one-line docstring, arrange/act/assert with comments stating the contract. `tests/test_doc_store.py:1-11` and `tests/test_upload_validation.py:1-13` follow the same shape.)

**Tracer-slice shape (the sanctioned cross-module test):**
```python
# tests/test_models.py:155-206 — Reader → Chunk → DocStore → read-back
def test_tracer_chunk_to_store_roundtrip(tmp_path, sample_pdf_path):
    from pdf_reader import PdfReader
    from doc_store import DocStore

    reader = PdfReader(sample_pdf_path)
    paragraphs = reader.get_paragraphs()
    chunk = Chunk(content=..., filename=..., page=..., chunk_id=..., doc_id=doc_id, extraction="pypdf")
    store = DocStore(tmp_path / "tracer.db")
    store.upsert_document(doc)
    store.record_chunks([chunk])
    assert store.get_document(doc_id) == doc
    assert store.get_chunks_for_doc(doc_id)[0] == chunk
```
- This is the only test that wires three layers together. New cross-layer contract tests must follow this shape (real producer output → model → isolated `tmp_path` store → equality round-trip).

**Patterns:**
- Setup: construct the real unit under test directly (`VectorIndex(...)`, `PdfReader(str(path))`, `LocalEmbedding()`, `AiModel()`, `Chunk(...)` / `Document(...)`, `DocStore(tmp_path / "….db")`, `validate_pdf_bytes(raw, name)`); request mocks as fixture args (`def test_ai_model_prompt_assembly(fake_env_groq_key, mock_groq_client):` in `tests/test_local_llm.py`).
- Teardown: none needed — `monkeypatch` auto-reverts env/attribute patches; `VectorIndex`/`PdfReader`/model instances are per-test locals; `DocStore` files live under ephemeral `tmp_path`; no temp files (corpus PDFs are pre-generated, read-only).
- Assertions: exact-value for ranking/content (`results[0][0]["content"] == "target"`), Pydantic equality (`assert retrieved == doc`), `pytest.approx(abs=1e-5)` for all float math, `pytest.raises(..., match=...)` for all error paths, substring checks for prompt/context inclusion (`"Document Text:" in system_msg`, `"---" in context`).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `monkeypatch.setattr`/`setenv`/`delenv`). All LLM/embedding seams centralized in `tests/conftest.py:1-88`; upload-validation tests patch `pypdf.PdfReader` locally; page-fault tests patch a page object's `extract_text`.

**Patterns:**
```python
# tests/conftest.py:18-48 — Groq streaming seam
@pytest.fixture
def mock_groq_client(monkeypatch):
    mock_client = MagicMock()

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    def mock_create(*args, **kwargs):
        for token in ["This ", "is ", "a ", "grounded ", "answer."]:
            yield MockChunk(token)

    mock_client.chat.completions.create.side_effect = mock_create

    import local_llm
    monkeypatch.setattr(local_llm, "Groq", lambda api_key=None: mock_client)
    return mock_client
```
```python
# tests/conftest.py:51-81 — embedding seam (deterministic 384-dim normalized float32)
@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    mock_model = MagicMock()

    def mock_encode(texts, normalize_embeddings=True, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        # ... deterministic pseudo-embeddings from text length, L2-normalized
        return np.array(vectors, dtype=np.float32)

    mock_model.encode.side_effect = mock_encode

    import local_embedding
    monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name: mock_model)
    return mock_model
```
```python
# tests/test_local_llm.py — injected-collaborator seam
mock_embedding = MagicMock()
mock_embedding.get_context.return_value = "Retrieved document text context line."
# ...
mock_embedding.get_context.assert_called_once()
call_args = mock_groq_client.chat.completions.create.call_args[1]
assert call_args["model"] == "openai/gpt-oss-20b"
assert call_args["stream"] is True
```
```python
# tests/test_pdf_reader.py:141-174 — page-fault injection seam (model for fault-isolation tests)
def test_page_failure_isolated(monkeypatch):
    # monkeypatch ONE page's extract_text to raise; assert the other 19 pages
    # still extract and record (failed page → Page(status="failed"), rest → "ok")
```
```python
# tests/test_upload_validation.py:61-76 — page-cap seam
class StubReader:
    def __init__(self, stream):
        self.pages = [None] * (MAX_PAGES + 1)

import pypdf
monkeypatch.setattr(pypdf, "PdfReader", StubReader)
with pytest.raises(ValueError, match=f"Too many pages \\({MAX_PAGES + 1} > {MAX_PAGES}\\)"):
    validate_pdf_bytes(raw_bytes, "page_heavy.pdf")
```

**What to Mock:**
- `local_llm.Groq` (the exact module attribute `AiModel` calls — never `groq.Groq`) with canned `choices[0].delta.content` token chunks (`tests/conftest.py`).
- `local_embedding.SentenceTransformer` (exact attribute used at import) with 384-dim normalized vectors — keeps the suite 100% offline with no GPU/HF download.
- `GROQ_API_KEY` via `fake_env_groq_key` (`monkeypatch.setenv` to an inert mock value, `tests/conftest.py:12-15`); absence via `monkeypatch.delenv("GROQ_API_KEY", raising=False)`.
- `LocalEmbedding` collaborators via `MagicMock` with `get_context.return_value`.
- Single-page `extract_text` failure for fault-isolation tests; `pypdf.PdfReader` stub for the page-cap test.

**What NOT to Mock:**
- `VectorIndex` math — pure stdlib, tested directly with hand-computed vectors (`tests/test_vector_index.py`).
- `RecursiveCharacterTextSplitter` — assert observable chunk size/metadata, not splitter internals.
- Corpus PDFs on disk — read the real generated files; regenerate with `generate_corpus.py` instead of stubbing `pypdf`.
- `hashlib.sha256` — compare `sha256_bytes` against it directly (`tests/test_upload_validation.py:79-84`).
- `DocStore` storage engine — use a real SQLite file under `tmp_path`, never a mocked store.

## Fixtures and Factories

**Test Data:**
```python
# tests/test_local_embedding.py — inline chunk dicts (minimal legal shape)
chunks = [
    {"content": "Document chunk number 1", "page": 1, "filename": "doc.pdf"},
    {"content": "Document chunk number 2", "page": 2, "filename": "doc.pdf"},
    {"content": "Document chunk number 3", "page": 3, "filename": "doc.pdf"},
]
embedding.build_index(chunks)
assert len(embedding.store) == 3
assert embedding.store._vector_dim == 384
```
```python
# tests/test_doc_store.py:13-37 — canonical Document construction (copy this shape)
doc = Document(
    doc_id="doc_1111111111111111",
    filename="test_doc.pdf",
    sha256="1" * 64,
    size_bytes=4096,
    num_pages=3,
    status="indexed",
    upload_time="2026-10-11T01:00:00Z",
    num_chunks=6,
)
store = DocStore(tmp_path / "test_docs.db")
store.upsert_document(doc)
assert store.get_document("doc_1111111111111111") == doc
```
- Fixture inventory (`tests/conftest.py`, unchanged count at 4): `fake_env_groq_key` (env key), `mock_groq_client` (streaming LLM), `mock_sentence_transformer` (384-dim embeddings), `sample_pdf_path` (resolves `tests/data/corpus/clean_digital.pdf`).
- Real-file assertions use the committed corpus: 20-page `clean_digital.pdf` with per-page headings and latency-metric claims (`tests/test_pdf_reader.py`, generator at `tests/data/corpus/generate_corpus.py`).
- Upload-validation tests read corpus bytes directly (`open(CORPUS_DIR / "clean_digital.pdf", "rb").read()`) and assert `result.doc_id == f"doc_{result.sha256[:16]}"`, `result.num_pages == 20` (`tests/test_upload_validation.py:26-37`).

**Location:**
- Shared fixtures: `tests/conftest.py`. Corpus factory: `tests/data/corpus/generate_corpus.py` (`get_corpus_dir`, six `generate_*_pdf` builders, `generate_all_corpus_files() -> dict[str, Path]`, `__main__` guard printing per-file byte sizes). Generated PDFs are committed artifacts; CI regenerates them before pytest (`.github/workflows/ci.yml:35-37`).

## Coverage

**Requirements:** None enforced — no coverage tool, threshold, or gate in CI.

**View Coverage:**
```bash
# Not wired up. To introduce it:
pip install pytest-cov
pytest --cov=. --cov-report=term-missing tests/
```

**Current state (44/44 passing):**
| File | Tests | What's covered |
|---|---|---|
| `tests/test_vector_index.py` | 7 | init/metric whitelist, cosine math (identical/orthogonal/opposite), euclidean math (3-4-5), `add_vector` guards + dimension lock-in, empty-store `[]`, euclidean ranking order, zero-magnitude guard |
| `tests/test_pdf_reader.py` | 9 | 20-page digital extraction + heading assertions, chunk metadata keys + `<= 1000` size, `BytesIO` + explicit-filename path, scanned-PDF `== []` limit, corrupt-constructor rejection, dense-table content, chart content, single-page fault isolation, hash chunk-ID rename stability |
| `tests/test_local_embedding.py` | 3 | init/model name + metric, `build_index` populates 3 vectors at dim 384, `get_context` delimiter + content inclusion |
| `tests/test_local_llm.py` | 3 | missing-key `ValueError`, prompt assembly (system `Document Text:` + history order + current question last), streaming token passthrough |
| `tests/test_models.py` | 10 | legacy-key exactness, frozen/hashability, extra-forbid, SHA-pattern rejection, JSON round-trip, bbox/embedding forward-compat, page/evidence contracts, `CONFIG_VERSION` + `cache_dir_for`, tracer Reader→Chunk→DocStore slice, legacy-dict adaptation |
| `tests/test_doc_store.py` | 6 | document round-trip (+ `get_by_sha`), SHA-unique `IntegrityError`, page-failure record, two-instance interleave, `user_version == 1`, chunk nullable `bbox_json`/`embedding_model` columns |
| `tests/test_upload_validation.py` | 6 | corrupt magic-byte rejection (closes Phase 0 WR-07), valid accept + hash metadata, rename stability, oversize rejection, over-page rejection, streaming-hash stability vs `hashlib` |

## Test Types

**Unit Tests:**
- Scope: one behavior per test, real unit + mocked boundaries (Groq, transformer, env, single-page failure, `PdfReader` stub). Run offline in ~10 s; no GPU, no API keys, no Streamlit harness. `DocStore` tests use real SQLite under `tmp_path` — the engine is stdlib, so no mock is needed.
- Per-file details: `VectorIndex` guard/message fragments pinned to implementation strings; `PdfReader` corpus preconditions fail with actionable messages; `LocalEmbedding` tests all take `mock_sentence_transformer`; `AiModel` tests take `fake_env_groq_key` + `mock_groq_client`; `DocStore` tests each build an isolated DB; upload-validation tests read real corpus bytes.

**Integration Tests:**
- One sanctioned slice: `test_tracer_chunk_to_store_roundtrip` (`tests/test_models.py:155-206`) — `PdfReader.get_paragraphs()` on the real `clean_digital.pdf` → canonical `Chunk` → `DocStore` persist → equality round-trip. All other end-to-end paths (`LocalEmbedding.build_index()` → `VectorIndex.search()` → `get_context()` over `model_dump()` dicts; `AiModel` fallback building its own index; multi-document accumulation + `Clear All`; dedup-hit-with-empty-index rebuild) remain untested (see gaps).

**E2E Tests:**
- Not used — no Playwright/Selenium/Cypress. E2E is manual via the browser (see below).

## Benchmark Script (non-test performance harness)

- `scripts/benchmark_baseline.py`: 4 staged measurements over `clean_digital.pdf` — `[1/4]` pypdf extraction (`time.perf_counter`, ms/page), `[2/4]` chunking (chunk count + ms), `[3/4]` real `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` load + batched `encode` latencies, `[4/4]` `VectorIndex` linear-scan latency over seeded 384-dim vectors, 5-search averages. Memory via `psutil.Process().memory_info().rss`. Output: `.planning/research/BASELINE_BENCHMARK.json`.
- Run: `python scripts/benchmark_baseline.py` (requires real model download + `psutil`; NOT part of pytest). Known measurement bug (Phase 0 WR-01): batch-size list collapses on the 20-chunk corpus so one entry overwrites another — dedupe before trusting the JSON.

## CI Workflow

- File: `.github/workflows/ci.yml` (41 lines). Triggers: `push`/`pull_request` on `main`.
- Job `test` (`ubuntu-latest`, Python 3.11 via `actions/setup-python@v5` with pip cache): install runtime + test deps (`pip install -r requirements.txt` then `pip install -r requirements-test.txt`), `ruff check .`, `ruff format --check .` (format gate added in Phase 1), `python tests/data/corpus/generate_corpus.py`, `pytest tests/ -v`.
- Step ordering is load-bearing: corpus generation MUST precede pytest since tests read corpus PDFs from disk.
- Test deps moved out of the workflow inline list into `requirements-test.txt` (`pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0`) — add new test-only packages there, never to `requirements.txt`. (`pytest-mock` was dropped; `numpy` moved to `requirements.txt` as `numpy>=1.26.0,<3.0.0`.)

## Manual Test Workflow (residual QA for untested paths)

Still required for `main.py` session-state/UI paths with no harness (`README.md`, run footer `main.py`):

```bash
source .venv/Scripts/activate   # Windows (Git Bash); macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# create .env with: GROQ_API_KEY=gsk_your_groq_key_here  (gitignored per .gitignore:1)
streamlit run main.py
```

1. Wait for **"LLM ready — Groq Cloud"** sidebar status. Failure means `GROQ_API_KEY` resolution failed.
2. Upload one PDF → `st.status("Processing documents…")` → per-file `Validating …` / `Extracting text …` with `st.progress` page bar → `Building index …` → `st.success("**…** indexed successfully (`doc_…`)")`.
3. Re-upload the same PDF → `st.info("Already indexed (`doc_…`) — skipped duplicate.")` (SHA dedup, `main.py:136-148`).
4. Ask a question → `Sources used` info line then token-by-token streamed answer.
5. Ask 2–3 follow-ups → history-aware retrieval stays coherent (last-10-messages window).
6. Upload a second PDF → index accumulates; `Clear All` resets `doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `chat_history`.
7. Negative cases: corrupted/empty/non-PDF file → per-file `st.error`, remaining files still index; oversized (>50 MB) / over-page (>500) files → validation `st.error` naming the cap.
8. First-run note: `all-MiniLM-L6-v2` downloads to `~/.cache/huggingface/`; slow first start is expected.

## Common Patterns

**Async Testing:**
- Not applicable — synchronous codebase except the streaming generator, consumed synchronously: `tokens = list(generator)` in tests, `for chunk in stream: ... yield ...` in production.

**Error Testing:**
```python
# tests/test_vector_index.py, tests/test_local_llm.py — the guard shape
with pytest.raises(TypeError, match="Vector must be a list of numbers"):
    idx.add_vector("not_a_list", {"content": "test"})  # type: ignore
with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
    AiModel()
# tests/test_models.py:50-51,57 — the Pydantic shape
with pytest.raises(ValidationError):
    chunk.content = "Mutated text"  # type: ignore
with pytest.raises(ValidationError, match="extra"):
    Document(..., unexpected_field="disallowed")
# tests/test_doc_store.py:65-66 — the constraint shape
with pytest.raises(sqlite3.IntegrityError):
    store.upsert_document(doc2)
# tests/test_upload_validation.py:22-23,57,75 — the validation shape
with pytest.raises(ValueError, match="Not a valid PDF: missing %PDF header"):
    validate_pdf_bytes(raw_bytes, "corrupt_invalid.pdf")
```
- Priority error cases already pinned: bad `distance_metric`, malformed vectors/documents, dimension mismatch, empty-store `[]`, missing-key `ValueError`, frozen-model `ValidationError`, extra-field `ValidationError`, bad-SHA `ValidationError`, SHA-unique `IntegrityError`, magic-byte/size/page-cap `ValueError`s. Still unpinned: `add_document`, string-query search with/without `embedding_fn`, `k <= 0`, query-dimension mismatch, empty-list vector `[]`.

## Test Coverage Gaps (from `.planning/phases/01-canonical-document-models/01-REVIEW.md`)

Phase 1's review (`01-REVIEW.md`, verdict NEEDS FIXES: 3 Critical, 8 Warnings, 6 Info) is the authoritative gap list. Severity as rated there:

**Critical (persistence story broken — fix as one coherent unit):**
- **CR-01 — dedup-hit path never restores embeddings:** `main.py:136-148` skips duplicates without rebuilding `st.session_state.local_embedding`, so after a restart every re-uploaded file is skipped forever and chat stays disabled. No test covers the dedup-hit-with-empty-index path. Fix: rebuild the session index from persisted chunks on dedup-hit (requires CR-03 fixed), plus a regression test with a pre-populated `DocStore` + empty session index.
- **CR-02 — `PdfReader` construction outside try/except:** only `validate_pdf_bytes` is wrapped (`main.py:126-130`); the constructor raises on malformed-but-`%PDF`-headered PDFs, aborting the whole batch. Fix: wrap construction + extraction + `Chunk` validation per file with `st.error + continue`.
- **CR-03 — `record_chunks` never called in production:** the upload flow persists pages + document but never chunks, so `get_chunks_for_doc()` returns `[]` for every real document and no restart-rebuild is possible. Fix: `doc_store.record_chunks([Chunk.model_validate(p) for p in paragraphs])` after `build_index` inside the per-file guard.

**Warnings:**
- **WR-01 — connections never closed:** `with self._connect() as conn:` commits/rolls back but does not close (`doc_store.py`). Fix: `contextlib.closing` or try/finally.
- **WR-02 — fault-isolation scope too narrow:** per-page guard covers only `page.extract_text()` (`pdf_reader.py:50-51`); `split_text` + `Chunk(...)` construction can still abort the document on whitespace-only splits (`Chunk.content` has `min_length=1`).
- **WR-03 — dedup check-then-insert TOCTOU race:** `get_by_sha` + `upsert_document` are separate connections; concurrent same-file uploads yield an uncaught `sqlite3.IntegrityError`. The suite pins the raise but no caller handles it.
- **WR-04 — full file buffered before the size check:** `uploaded_file.getvalue()` (`main.py:121`) copies everything into RAM before `MAX_FILE_MB` is enforced. Fix: pre-check `uploaded_file.size` first.
- **WR-05 — identity fields unvalidated:** `Document.doc_id` has no cross-check against `sha256`; `doc_id_for()` accepts any string; `Page.status` / `Document.status` / `EvidenceElement.kind` are unconstrained `str`. Fix: `@field_validator`/`model_validator` + `Literal` types.
- **WR-06 — lexical chunk-ID ordering:** `ORDER BY page ASC, chunk_id ASC` (`doc_store.py:283`) sorts `…_p1_10` before `…_p1_2`. Fix: zero-pad sequences or order by `char_start`/`rowid`.
- **WR-07 — disk cache is write-only:** `.cache/` dumps (`main.py:190-201`) are never read back, and `.cache/` is not in `.gitignore` (only `data/` is).
- **WR-08 — inconsistent timestamps:** ISO `+00:00` (persisted), `%H:%M:%S` time-only (session display, drops the date), and `Z`-suffixed test strings coexist; lexicographic `ORDER BY upload_time DESC` sorts mixed rows wrong. Fix: one canonical UTC ISO form, format for display only at render time.

**Info:**
- **IN-01 — `.lower()` no-op** (`upload_validation.py:32`): `hexdigest()` is already lowercase.
- **IN-02 — `BBox` accepts inverted/negative coordinates** (`models.py:29-41`): add a `model_validator` when a bbox producer exists.
- **IN-03 — filenames interpolated into Markdown UI** (`main.py`): prefer `st.code`/escaped rendering for raw filenames.
- **IN-04 — `cache_dir_for` permits path traversal** (`models.py:15-26`): assert `^[0-9a-f]{64}$` on the `sha256` argument.
- **IN-05 — oversize test allocates ~51 MB; page-cap test patches globally** (`tests/test_upload_validation.py:54-76`): patch `MAX_FILE_MB` small; patch the `upload_validation`-local `pypdf` reference.
- **IN-06 — `record_chunks` upsert refreshes only 3 of 9 columns** (`doc_store.py:240-247`): include positional columns in the update set.

**Residual manual-only (no harness):** `main.py` session-state machine (dedup display, metadata, history reset, sources, windowing); streaming/`st.write_stream` plumbing; `st.progress` rendering; `AiModel` fallback index path.

---

*Testing analysis: 2026-10-11*
