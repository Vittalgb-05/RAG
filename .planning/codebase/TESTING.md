# Testing Patterns

**Analysis Date:** 2026-10-13

## Test Framework

**Runner:**
- pytest ≥ 8.3.0 (`requirements-test.txt:2`)
- Config: `pyproject.toml:13-19` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- Corpus/report helpers: `reportlab≥4.2.0` (synthetic PDF generation), `psutil≥6.1.0` (memory assertions), `ruff≥0.9.0` (lint gate, same file)

**Assertion Library:**
- Plain pytest asserts + `pytest.raises(..., match=...)` for guards, `pytest.approx(..., abs=1e-5)` for float math. No hamcrest/snapshots/property-based libs.

**Run Commands:**
```bash
uv pip install --system -r requirements-lock.txt   # runtime pins (CI step 1)
uv pip install --system -r requirements-test.txt   # pytest/reportlab/ruff/psutil (CI step 2)
ruff check . && ruff format --check .              # lint + format gate (CI step 3)
python tests/data/corpus/generate_corpus.py        # regenerate 6-PDF synthetic corpus (CI step 4)
pytest tests/ -v                                   # full suite, ~226 tests (CI step 5)
pytest tests/test_vector_index.py -v               # single module
pytest tests/test_doc_store.py tests/test_hybrid_retriever.py -v  # retrieval slice
```

## Test File Organization

**Location:**
- Separate `tests/` directory mirroring each root module: `tests/test_<module>.py` ↔ `<module>.py`. Package marker `tests/__init__.py` (empty).

**Naming:**
- `test_*.py` files, `test_*` functions (enforced by `pyproject.toml:15-16`). Descriptive behaviour names: `test_cosine_distance_math`, `test_pdf_reader_chunking_overlap`, `test_chat_history_bounding_drops_oldest_turns`.

**Structure:**
```
tests/
├── __init__.py                  # package marker (empty)
├── conftest.py                  # 4 shared fixtures / mocking seams (165 lines)
├── data/corpus/                 # synthetic PDFs + generate_corpus.py
│   ├── generate_corpus.py       # builds all 6 corpus PDFs via reportlab
│   ├── clean_digital.pdf        # 20-page digital text (primary fixture)
│   ├── dense_table.pdf          # financial tables for table-lookup tests
│   ├── chart_diagram.pdf        # diagrams for visual/QA tests
│   ├── multi_column.pdf         # recovery-policy doc for docling tests
│   ├── scanned_sample.pdf       # OCR-path input
│   └── corrupt_invalid.pdf      # not-a-PDF bytes for error-path tests
├── test_vector_index.py         # 7 tests, distance math + guards
├── test_pdf_reader.py           # 9 tests, extraction/chunking/corrupt handling
├── test_local_embedding.py      # 4 tests, CPU pinning + normalisation
├── test_local_llm.py            # 12 tests, prompt assembly + streaming
├── test_model_provider.py       # 12 tests, ABC contract + health/capabilities
├── test_llama_cpp_provider.py   # 15 tests, local server client
├── test_litellm_provider.py     # 11 tests, cloud fallback client
├── test_groq_provider.py        # (via test_local_llm mock_groq_client seam)
├── test_models.py               # 20 tests, Pydantic schema validation
├── test_doc_store.py            # 17 tests, LanceDB + SQLite persistence
├── test_hybrid_retriever.py     # 15 tests, RRF fusion + CPU pipeline
├── test_docling_reader.py       # 7 tests, layout-aware extraction
├── test_ocr_fallback.py         # 8 tests, RapidOCR scanned path
├── test_visual_analyzer.py      # 8 tests, VLM diagram analysis
├── test_summarizer.py           # 10 tests, multi-profile summarization
├── test_citation_validator.py   # 11 tests, [E1]-style precision checks
├── test_prompt_budget.py        # 11 tests, token budget + history bounding
├── test_resource_telemetry.py   # 11 tests, RAM/VRAM/latency tracking
├── test_upload_validation.py    # 8 tests, untrusted-input guards
├── test_cloud_privacy.py        # 8 tests, local-only default + no-egress
├── test_cache_invalidation.py   # 6 tests, cache keys + history bounding
├── test_concurrency_lock.py     # 8 tests, InferenceGate mutual exclusion
└── test_main_ui.py              # 8 tests, chat-turn schema contract
```

## Test Structure

**Suite Organization:**
```python
# ------------------------------------------------------------------
# Unit Tests for VectorIndex
# Verifies distance math, guard clauses, ranking, and edge cases
# ------------------------------------------------------------------

import pytest
from vector_index import VectorIndex


def test_vector_index_initialization():
    """Verify initialization options and metric whitelist."""
    idx = VectorIndex(distance_metric="cosine")
    assert idx._distance_metric == "cosine"
    with pytest.raises(ValueError, match="distance_metric must be 'cosine' or 'euclidean'"):
        VectorIndex(distance_metric="manhattan")
```
- Banner header → imports → flat `test_*` functions. No classes except test-double providers (`DummyProvider` in `tests/test_concurrency_lock.py`, `MockLlamaCppProvider` in `tests/conftest.py`). Every test has a one-line docstring stating the invariant under test.

**Patterns:**
- Arrange-act-assert inline, no setup/teardown helpers beyond conftest fixtures. Guard tests use `pytest.raises(TypeError|ValueError, match=...)` (`tests/test_vector_index.py:test_add_vector_guards`).
- Float assertions use `pytest.approx(..., abs=1e-5)` (`tests/test_vector_index.py:test_cosine_distance_math` — identical→0.0, orthogonal→1.0, opposite→2.0; 3-4-5 triangle→5.0).
- Deterministic vectors via seeded RNG, never live models: `_make_unit_vector(seed)` with `np.random.seed(seed)` (`tests/test_hybrid_retriever.py`); length-keyed pseudo-embeddings in conftest (`tests/conftest.py:63-78`).
- Real-file tests assert on known corpus strings: `"Section 1: Fundamentals of Intelligence Systems" in text`, 20-page count, `len(chunks) >= 20`, per-chunk `content/filename/page/chunk_id` keys (`tests/test_pdf_reader.py`).

## Mocking

**Framework:** `unittest.mock.MagicMock` + `pytest.monkeypatch` (via fixtures). No responses/httpx-mock/fakeredis.

**Patterns:**
```python
@pytest.fixture
def mock_groq_client(monkeypatch):
    mock_client = MagicMock()
    # ... MockDelta/MockChoice/MockChunk wrappers ...
    def mock_create(*args, **kwargs):
        for token in ["This ", "is ", "a ", "grounded ", "answer."]:
            yield MockChunk(token)
    mock_client.chat.completions.create.side_effect = mock_create
    monkeypatch.setattr(groq_provider, "Groq", lambda api_key=None: mock_client)
    return mock_client


@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    mock_model = MagicMock()
    def mock_encode(texts, normalize_embeddings=True, **kwargs):
        # deterministic 384-dim L2-normalised float32 vectors
        ...
    mock_model.encode.side_effect = mock_encode
    monkeypatch.setattr(local_embedding, "SentenceTransformer",
                        lambda model_name, **kwargs: mock_model)
    return mock_model
```
- (`tests/conftest.py:18-85`). Both seams patch the *import site* (`groq_provider.Groq`, `local_embedding.SentenceTransformer`), not the SDK package — new seamable deps must be imported into a module namespace so `monkeypatch.setattr` can replace them.
- Provider seam: `mock_llama_provider` fixture returns a `MockLlamaCppProvider(BaseModelProvider)` with canned `stream_text` tokens, `check_health`, `get_capabilities`, `analyze_image` (`tests/conftest.py:96-165`). Benchmark scripts define their own `DeterministicBenchmarkProvider` / `BenchmarkProvider` subclasses rather than importing the fixture.
- Env seam: `fake_env_groq_key` sets `GROQ_API_KEY=test-key-not-a-secret-mock-value` (`tests/conftest.py:12-15`). Threading tests build local `DummyProvider` classes inline (`tests/test_concurrency_lock.py`).

**What to Mock:**
- Network: Groq/LiteLLM/llama-server clients (all streaming generators yield the 5 canned tokens `"This is a grounded answer."`).
- GPU/heavy models: `SentenceTransformer` (deterministic 384-dim vectors), Docling RapidOCR pipelines.
- Environment: API keys, `st.secrets` file absence.

**What NOT to Mock:**
- Pure stdlib math (`VectorIndex` distances — assert exact values), chunk-dict shapes, Pydantic validation, SQLite/LanceDB in tmp dirs (`tests/test_doc_store.py` uses real `DocStore` in `tempfile` dirs), real synthetic corpus PDFs on disk.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def sample_pdf_path():
    path = Path(__file__).resolve().parent / "data" / "corpus" / "clean_digital.pdf"
    return str(path)
```
- (`tests/conftest.py:88-92`). Corpus paths are resolved from `__file__`, never relative CWD — new file-based tests must use the same `Path(__file__).resolve().parent / "data" / ...` idiom.
- Inline factories: `_make_unit_vector(seed, dim=384)` (`tests/test_hybrid_retriever.py`), `BBox(...)` + `EvidenceSnippet(...)` + `CitationVerificationResult(...)` chat-turn assembly (`tests/test_main_ui.py`), 75-turn alternating user/assistant history builder (`tests/test_cache_invalidation.py`).

**Location:**
- Shared fixtures: `tests/conftest.py` (4 fixtures: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `mock_llama_provider`, plus `sample_pdf_path`).
- Corpus: `tests/data/corpus/` — 6 PDFs + `generate_corpus.py` (reportlab `SimpleDocTemplate`/`canvas`; CI regenerates before pytest so checked-in PDFs are a cache, not the source of truth).

## Coverage

**Requirements:** None enforced — no `--cov`, no `fail_under`, no codecov step in CI. Coverage is by convention (every root module has a mirror suite; ~226 `test_*` functions across 23 files).

**View Coverage:**
```bash
# No coverage gate exists; ad-hoc only:
pip install pytest-cov
pytest tests/ --cov=. --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Scope: distance math, guard clauses, schema validation, prompt assembly, RRF fusion, token budgets, citation precision, upload guards, telemetry parsing. Fully offline via conftest seams; no GPU, no API keys, no servers. This is ~90% of the suite.

**Integration Tests:**
- Scope: real `DocStore` (LanceDB + SQLite) in tmp dirs (`tests/test_doc_store.py`, 661 lines — largest suite), real `HybridRetriever` over seeded vectors, real corpus PDFs through `PdfReader`/`DoclingReader`/OCR fallback, `InferenceGate` thread-contention with real locks, Streamlit chat-turn contract against real `models.py` + `citation_validator.py` dumps. Still hermetic (localhost/tmp only).

**E2E Tests:**
- Not pytest. The three `scripts/*` harnesses are the E2E/benchmark layer, run manually (not in CI):
  - `scripts/benchmark_baseline.py` (174 lines) — pypdf extraction latency, chunk counts, CPU embedding time, linear-search latency, RSS; writes `.planning/research/BASELINE_BENCHMARK.json`.
  - `scripts/benchmark_multimodal.py` (292 lines) — factual accuracy, diagram comprehension, table lookups, citation precision, abstention on verified corpus PDFs with `DeterministicBenchmarkProvider`; writes `.planning/research/MULTIMODAL_BENCHMARK.json`.
  - `scripts/profile_resources.py` (342 lines) — cold vs warm ingestion, LanceDB hybrid retrieval, multi-profile summarization, process RAM + GPU VRAM vs 4 GB ceiling with `BenchmarkProvider`; writes `.planning/research/RESOURCE_PROFILE.json`.

## CI

**Pipeline:** `.github/workflows/ci.yml` — job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggers on `push`/`pull_request` to `main`, 5 ordered steps:
1. `actions/checkout@v4` + `actions/setup-python@v5` (3.11) + `astral-sh/setup-uv@v5` (cached).
2. **Lockfile-synced install:** `uv pip install --system -r requirements-lock.txt` (pinned transitive closure compiled by `uv pip compile requirements.txt`) **then** `uv pip install --system -r requirements-test.txt`. Runtime pins never float in CI — adding a runtime dep requires recompiling `requirements-lock.txt` via `uv pip compile requirements.txt -o requirements-lock.txt` (header, `requirements-lock.txt:1-2`).
3. `ruff check .` + `ruff format --check .` — lint/format gate fails the build before tests run.
4. `python tests/data/corpus/generate_corpus.py` — corpus regenerated every run; tests assert on generated content.
5. `pytest tests/ -v` — full suite, verbose.

## Common Patterns

**Async Testing:**
- Not used. Concurrency is thread-based (`InferenceGate`); tests use `threading.Thread` + `time.sleep` barriers and assert `call_count` / mutual exclusion (`tests/test_concurrency_lock.py`). No `asyncio`, no `anyio` marker.

**Error Testing:**
```python
with pytest.raises(ValueError, match="distance_metric must be 'cosine' or 'euclidean'"):
    VectorIndex(distance_metric="manhattan")
with pytest.raises(TypeError, match="Vector must be a list of numbers"):
    idx.add_vector("not_a_list", {"content": "test"})  # type: ignore
```
- Guard tests pair each constructor/mutator check with a `match=` regex on the message (`tests/test_vector_index.py`). Corrupt-input tests feed `tests/data/corpus/corrupt_invalid.pdf` and assert graceful error/empty rather than raise (`tests/test_pdf_reader.py`). Privacy tests assert `cloud_mode=False` default and block socket egress (`tests/test_cloud_privacy.py`).

## Test Coverage Gaps

**Untested — `main.py` Streamlit control flow:**
- What's not tested: sidebar upload loop, `st.status`/`st.chat_input`/`st.write_stream` wiring, `@st.cache_resource` singleton lifecycle, `st.rerun()` paths. `tests/test_main_ui.py` covers only the chat-turn dict schema contract, never renders Streamlit.
- Risk: UI regressions (missing keys, broken rerun) pass CI silently.
- Priority: Medium (schema contract pins the data; wiring is manual-QA).

**Untested — live-model quality drift:**
- What's not tested in CI: real `SentenceTransformer` weights, real Docling layout output, real llama-server/Groq latency and answer quality. All pinned behind deterministic mocks.
- Files: `local_embedding.py`, `docling_reader.py`, `llama_cpp_provider.py`, `groq_provider.py` live paths.
- Risk: mock/real divergence (e.g. embedding dim change) caught only by manual benchmark runs.
- Priority: Medium — mitigated by the three `scripts/*` harnesses; promote one to a nightly CI job to close the gap.

**Untested — benchmark output assertions:**
- What's not tested: no test reads `.planning/research/*.json` or asserts benchmark thresholds; `scripts/*` have zero `test_*` coverage.
- Risk: performance regressions (VRAM ceiling breach, retrieval latency) invisible to CI.
- Priority: Low (manual gate per milestone; add threshold asserts when budgets stabilise).

---

*Testing analysis: 2026-10-13*
