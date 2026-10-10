# Testing Patterns

**Analysis Date:** 2026-10-10

## Test Framework

**Runner:**
- `pytest` (version resolved at install time; CI installs unpinned `pytest` + `pytest-mock` — see gap WR-08 below)
- Config: `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`

**Assertion Library:**
- stdlib `assert` + `pytest.raises` / `pytest.approx`. `unittest.mock.MagicMock` for injected collaborators. No `pytest-mock` `mocker` fixture usage in the suite today (package installed in CI but unused).

**Run Commands:**
```bash
pip install -r requirements.txt
pip install pytest pytest-mock reportlab ruff psutil   # test-only deps (CI line, .github/workflows/ci.yml:28)
python tests/data/corpus/generate_corpus.py            # REQUIRED first — tests read corpus PDFs from disk
pytest tests/ -v                                        # run all 17 tests
pytest tests/test_vector_index.py -v                    # single file
ruff check .                                            # lint gate (must pass before push)
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
├── test_pdf_reader.py           # 4 tests — extraction, chunking, BytesIO, scanned limit
├── test_local_embedding.py      # 3 tests — init, build_index, get_context (all mocked transformer)
├── test_local_llm.py            # 3 tests — missing-key, prompt assembly, streaming yield
└── data/corpus/
    ├── generate_corpus.py       # deterministic reportlab generator (6 synthetic PDFs)
    ├── clean_digital.pdf        # 20-page digital doc (regenerated artifact, committed)
    ├── multi_column.pdf         # 2-page two-column layout
    ├── dense_table.pdf          # quarterly financial table
    ├── scanned_sample.pdf       # raster-only, zero text layer (vector rects, no drawString)
    ├── chart_diagram.pdf        # architecture flowchart boxes
    └── corrupt_invalid.pdf      # raw invalid bytes (NOT_A_VALID_PDF_HEADER…)
```

**Suite size:** 17 tests collected (`pytest --collect-only`), all passing alongside `ruff check .` clean (`ruff 0.15.12`).

## Test Structure

**Suite Organization:**
```python
# ------------------------------------------------------------------
# Unit Tests for VectorIndex
# Verifies distance math, guard clauses, ranking, and edge cases
# ------------------------------------------------------------------

import pytest
from vector_index import VectorIndex


def test_cosine_distance_math():
    """Test exact cosine distance for identical, orthogonal, and opposite vectors."""
    idx = VectorIndex(distance_metric="cosine")

    # Identical vectors -> cosine similarity = 1.0 -> distance = 0.0
    dist_same = idx._cosine_distance([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert pytest.approx(dist_same, abs=1e-5) == 0.0
    # ... orthogonal -> 1.0, opposite -> 2.0
```
(`tests/test_vector_index.py:1-35` — the model shape: banner header, one `test_*` per behavior, one-line docstring, arrange/act/assert with comments stating the math.)

**Patterns:**
- Setup: construct the real unit under test directly (`VectorIndex(...)`, `PdfReader(str(path))`, `LocalEmbedding()`, `AiModel()`); request mocks as fixture args (`def test_ai_model_prompt_assembly(fake_env_groq_key, mock_groq_client):` in `tests/test_local_llm.py:21`).
- Teardown: none needed — `monkeypatch` auto-reverts env/attribute patches; `VectorIndex`/`PdfReader` instances are per-test locals; no temp files (corpus PDFs are pre-generated, read-only).
- Assertions: exact-value for ranking/content (`results[0][0]["content"] == "target"`), `pytest.approx(abs=1e-5)` for all float math, `pytest.raises(..., match=...)` for all error paths, substring checks for prompt/context inclusion (`"Document Text:" in system_msg`, `"---" in context`).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `monkeypatch.setattr`/`setenv`). All seams centralized in `tests/conftest.py:1-88`.

**Patterns:**
```python
# tests/conftest.py:20-48 — Groq streaming seam
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
# tests/test_local_llm.py:26-27,44 — injected-collaborator seam
mock_embedding = MagicMock()
mock_embedding.get_context.return_value = "Retrieved document text context line."
# ...
mock_embedding.get_context.assert_called_once()
call_args = mock_groq_client.chat.completions.create.call_args[1]
assert call_args["model"] == "openai/gpt-oss-20b"
assert call_args["stream"] is True
```

**What to Mock:**
- `local_llm.Groq` (the exact module attribute `AiModel` calls — never `groq.Groq`) with canned `choices[0].delta.content` token chunks (`tests/conftest.py:46-47`). Mock fidelity verified against `local_llm.py:81` consumption shape (`00-REVIEW.md` per-file note).
- `local_embedding.SentenceTransformer` (exact attribute used at import) with 384-dim normalized vectors — keeps the suite 100% offline with no GPU/HF download (`tests/conftest.py:79-80`).
- `GROQ_API_KEY` via `fake_env_groq_key` (`monkeypatch.setenv`, `tests/conftest.py:13-16`); absence via `monkeypatch.delenv("GROQ_API_KEY", raising=False)` (`tests/test_local_llm.py:16`).
- `LocalEmbedding` collaborators via `MagicMock` with `get_context.return_value` (`tests/test_local_llm.py:26-27`).

**What NOT to Mock:**
- `VectorIndex` math (`vector_index.py:150-207`) — pure stdlib, tested directly with hand-computed vectors (`tests/test_vector_index.py:21-44`).
- `RecursiveCharacterTextSplitter` (`pdf_reader.py:31-35`) — assert observable chunk size/metadata, not splitter internals (`tests/test_pdf_reader.py:29-43`).
- Corpus PDFs on disk — read the real generated files; regenerate with `generate_corpus.py` instead of stubbing `pypdf`.

## Fixtures and Factories

**Test Data:**
```python
# tests/test_local_embedding.py:20-24 — inline chunk dicts (minimal legal shape)
chunks = [
    {"content": "Document chunk number 1", "page": 1, "filename": "doc.pdf"},
    {"content": "Document chunk number 2", "page": 2, "filename": "doc.pdf"},
    {"content": "Document chunk number 3", "page": 3, "filename": "doc.pdf"},
]
embedding.build_index(chunks)
assert len(embedding.store) == 3
assert embedding.store._vector_dim == 384
```
- Fixture inventory (`tests/conftest.py`): `fake_env_groq_key` (env key), `mock_groq_client` (streaming LLM), `mock_sentence_transformer` (384-dim embeddings), `sample_pdf_path` (resolves `tests/data/corpus/clean_digital.pdf`).
- Real-file assertions use the committed corpus: 20-page `clean_digital.pdf` with per-page `"Section {p}: Fundamentals of Intelligence Systems"` headings and `"System latency metric is target-{p}0 milliseconds"` claims (`tests/test_pdf_reader.py:15-26`, generator at `tests/data/corpus/generate_corpus.py:28-64`).

**Location:**
- Shared fixtures: `tests/conftest.py`. Corpus factory: `tests/data/corpus/generate_corpus.py` (`get_corpus_dir`, six `generate_*_pdf` builders, `generate_all_corpus_files() -> dict[str, Path]`, `__main__` guard printing per-file byte sizes). Generated PDFs are committed artifacts; CI regenerates them before pytest (`.github/workflows/ci.yml:34-36`).

## Coverage

**Requirements:** None enforced — no coverage tool, threshold, or gate in CI (gap WR-08, `00-REVIEW.md:23`).

**View Coverage:**
```bash
# Not wired up. To introduce it:
pip install pytest-cov
pytest --cov=. --cov-report=term-missing tests/
```

**Current state (17/17 passing):**
| File | Tests | What's covered |
|---|---|---|
| `tests/test_vector_index.py` | 7 | init/metric whitelist, cosine math (identical/orthogonal/opposite), euclidean math (3-4-5), `add_vector` guards + dimension lock-in, empty-store `[]`, euclidean ranking order, zero-magnitude guard |
| `tests/test_pdf_reader.py` | 4 | 20-page digital extraction + heading assertions, chunk metadata keys + `<= 1000` size, `BytesIO` + explicit-filename path, scanned-PDF `== []` limit |
| `tests/test_local_embedding.py` | 3 | init/model name + metric, `build_index` populates 3 vectors at dim 384, `get_context` delimiter + content inclusion |
| `tests/test_local_llm.py` | 3 | missing-key `ValueError`, prompt assembly (system `Document Text:` + history order + current question last), streaming token passthrough |

## Test Types

**Unit Tests:**
- Scope: one behavior per test, real unit + mocked boundaries (Groq, transformer, env). Run offline in seconds; no GPU, no API keys, no Streamlit harness.
- Per-file details: `VectorIndex` guard/message fragments pinned to implementation strings (`tests/test_vector_index.py:47-74`); `PdfReader` corpus preconditions fail with actionable messages (`assert pdf_path.exists(), "Corpus file ... must exist"`); `LocalEmbedding` tests all take `mock_sentence_transformer`; `AiModel` tests take `fake_env_groq_key` + `mock_groq_client`.

**Integration Tests:**
- None as discrete files — the closest end-to-end paths (`PdfReader.get_paragraphs()` → `LocalEmbedding.build_index()` → `VectorIndex.search()` → `get_context()`; `AiModel` fallback building its own index when `local_embedding is None` at `local_llm.py:41-45`; multi-document accumulation + `Clear All` in `main.py:107-112,122-162`) remain untested (see gaps).

**E2E Tests:**
- Not used — no Playwright/Selenium/Cypress. E2E is manual via the browser (see below).

## Benchmark Script (non-test performance harness)

- `scripts/benchmark_baseline.py` (171 lines): 4 staged measurements over `clean_digital.pdf` — `[1/4]` pypdf extraction (`time.perf_counter`, ms/page), `[2/4]` chunking (chunk count + ms), `[3/4]` real `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` load + batched `encode` latencies, `[4/4]` `VectorIndex` linear-scan latency over 100/500/1000 seeded (`np.random.seed(42)`) 384-dim vectors, 5-search averages. Memory via `psutil.Process().memory_info().rss`. Output: `.planning/research/BASELINE_BENCHMARK.json` (timestamp, hardware, extraction, chunking, embeddings_cpu, vector_search_linear_scan, memory_profile).
- Run: `python scripts/benchmark_baseline.py` (requires real model download + `psutil`; NOT part of pytest). Known measurement bug WR-01: `batch_sizes = [min(10,…), min(20,…), len(chunk_texts)]` collapses to `[10, 20, 20]` on the 20-chunk corpus, so `batch_latencies[f"batch_{b}"]` overwrites one entry and embeds 20 chunks twice — dedupe before trusting the JSON (`00-REVIEW.md:16,49`).

## CI Workflow

- File: `.github/workflows/ci.yml` (40 lines). Triggers: `push`/`pull_request` on `main`.
- Job `test` (`ubuntu-latest`, Python 3.11 via `actions/setup-python@v5` with pip cache): install runtime + test deps (`pip install -r requirements.txt` then `pip install pytest pytest-mock reportlab ruff psutil`), `ruff check .`, `python tests/data/corpus/generate_corpus.py`, `pytest tests/ -v`.
- Step ordering is load-bearing: corpus generation MUST precede pytest since tests read corpus PDFs from disk (`00-REVIEW.md` per-file note on `ci.yml`).

## Manual Test Workflow (residual QA for untested paths)

Still required for `main.py` session-state/UI paths with no harness (`README.md:191-208`, run footer `main.py:248-253`):

```bash
source .venv/Scripts/activate   # Windows (Git Bash); macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# create .env with: GROQ_API_KEY=gsk_your_groq_key_here  (gitignored per .gitignore:1)
streamlit run main.py
```

1. Wait for **"LLM ready — Groq Cloud"** sidebar status (`main.py:96-98`). Failure means `GROQ_API_KEY` resolution failed (`local_llm.py:24-30`).
2. Upload one PDF → `st.status("Processing documents…")` → `Indexed N document(s)` plus per-file `st.success` (`main.py:124-170`).
3. Ask a question → `Sources used` info line then token-by-token streamed answer (`main.py:215-239`).
4. Ask 2–3 follow-ups → history-aware retrieval stays coherent (last-10-messages window, `main.py:231`).
5. Upload a second PDF → index accumulates; `Clear All` (`main.py:107-112`) resets `indexed_files`, `document_metadata`, `local_embedding`, `chat_history`.
6. Negative case: corrupted/empty/non-PDF file → per-file `st.error`, remaining files still index (`main.py:137-139`).
7. First-run note: `all-MiniLM-L6-v2` downloads to `~/.cache/huggingface/`; slow first start is expected (`README.md:199`).

## Common Patterns

**Async Testing:**
- Not applicable — synchronous codebase except the streaming generator, consumed synchronously: `tokens = list(generator)` in tests (`tests/test_local_llm.py:78`), `for chunk in stream: ... yield ...` in production (`local_llm.py:80-82`).

**Error Testing:**
```python
# tests/test_vector_index.py:52-65, tests/test_local_llm.py:16-18 — the standard shape
with pytest.raises(TypeError, match="Vector must be a list of numbers"):
    idx.add_vector("not_a_list", {"content": "test"})  # type: ignore
with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
    AiModel()
```
- Priority error cases already pinned: bad `distance_metric`, malformed vectors/documents, dimension mismatch, empty-store `[]`, missing-key `ValueError`. Still unpinned (IN-06): `add_document`, string-query search with/without `embedding_fn`, `k <= 0`, query-dimension mismatch, empty-list vector `[]` (passes guard via vacuous `all()`, locks `dim=0`).

## Test Coverage Gaps (from `.planning/phases/00-baseline-and-audit/00-REVIEW.md`)

All items below cite the Phase 0 review (`00-REVIEW.md:14-30`); severity as rated there:

- **WR-01 (Warning, measurement validity) — benchmark duplicate batch keys:** `scripts/benchmark_baseline.py:79-87` runs the 20-chunk embedding twice and drops one JSON entry. Fix: `sorted(set(...))` batch sizes, re-run, confirm 3 distinct entries in `BASELINE_BENCHMARK.json`.
- **WR-03 (Warning, correctness) — overlap never verified:** `test_pdf_reader_chunking_overlap` (`tests/test_pdf_reader.py:29-43`) checks size/metadata but asserts no shared text between consecutive chunks despite its name. Fix: assert a shared substring across chunk boundaries.
- **WR-04 (Warning, coverage) — weak prompt-assembly assertions:** `tests/test_local_llm.py:21-62` asserts `"Document Text:"` but not `"Conversation History"` or the strict grounding instruction. Grounding regressions could pass silently.
- **WR-05 (Warning, coverage) — retrieval ordering untested:** `test_local_embedding_get_context` uses `k=2` and never asserts `search` call args; `"management" in context` passes regardless of ranking. Fix: assert `search` called with the `k=10` path.
- **WR-07 (Warning, coverage) — 4 of 6 corpus files untested:** `corrupt_invalid.pdf` rejection path (plan-required magic-byte test never written), `dense_table.pdf` numeric preservation, `chart_diagram.pdf`, and multi-column reading order (BytesIO test only checks a substring). Dead corpus weight + untested rejection path.
- **WR-02 (Warning, quality) — `numpy` unpinned:** used directly in `tests/conftest.py:9` and `scripts/benchmark_baseline.py:97`, arrives only transitively via `sentence-transformers`. Fix: pin `numpy` (+ test-only `pytest`, `pytest-mock`, `reportlab`, `psutil`) in requirements or `requirements-test.txt` referenced from `ci.yml`.
- **WR-06 (Warning, quality) — lint exemption masks dead code:** `pyproject.toml:10-11` silences `F401`/`F841` for all `tests/*`, hiding unused `os`/`ParagraphStyle` (`generate_corpus.py:6,18`, IN-01). Fix: narrow exemption, delete dead imports, re-run `ruff check .`.
- **WR-08 (Warning, quality) — thin CI:** only `ruff check` (E/F/W) + bare `pytest`; no mypy, no `ruff format --check`, no coverage gate; test deps installed ad hoc unpinned.
- **IN-02 (Info) — private-API coupling:** `tests/test_vector_index.py` binds to `_cosine_distance`/`_euclidean_distance`/`_distance_metric`/`_vector_dim`. Accepted white-box coupling; note before renaming.
- **IN-06 (Info) — uncovered `VectorIndex` paths:** `add_document`, string-query search, `k <= 0`, query-dimension mismatch, empty-list vector edge.
- **Residual manual-only (no harness):** `main.py` session-state machine (dedup `main.py:127`, metadata `main.py:148-152`, history reset `main.py:154-156`, sources `main.py:216-220`, windowing `main.py:231`); streaming/`st.write_stream` plumbing; `AiModel` fallback index path (`local_llm.py:41-45`).

---

*Testing analysis: 2026-10-10*
