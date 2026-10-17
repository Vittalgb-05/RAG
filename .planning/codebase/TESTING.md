# Testing Patterns

**Analysis Date:** 2026-10-17

## Test Framework

**Runner:**
- `pytest>=8.3.0` (declared in `requirements-test.txt:1-5`).
- Config: `pyproject.toml:20-27` under `[tool.pytest.ini_options]`:
  - `testpaths = ["tests"]`
  - `python_files = ["test_*.py"]`
  - `python_functions = ["test_*"]`
  - `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- No `pytest.ini`, `tox.ini`, or `setup.cfg` test config. No custom marks registered, no `addopts`, no coverage plugin.

**Assertion Library:**
- Plain `assert` statements (no pytest-assertions plugin beyond the built-in rewrite).
- `pytest.raises(ExcType, match="...")` for error paths; `pytest.approx(value, abs=1e-5)` for float comparisons (`tests/test_vector_index.py:27,31,35,44`).
- Pydantic `ValidationError` (`from pydantic import ValidationError`) is the expected exception for schema tests (`tests/test_models.py:60-360`, `tests/test_model_provider.py`).

**Run Commands:**
```bash
pytest tests/ -v              # Full suite (233 tests collected across 22 test modules)
pytest tests/test_models.py -q
ruff check .                  # Lint (CI gate)
ruff format --check .         # Format check (CI gate)
```
There is no coverage command configured (no `pytest-cov` dependency, no `--cov` flag, no coverage threshold).

## Test File Organization

**Location:**
- All tests live in the top-level `tests/` directory (a Python package via `tests/__init__.py`). No tests co-located with source.
- One `test_<module>.py` per source module or concern — 22 test modules: `tests/test_models.py`, `tests/test_model_provider.py`, `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_local_llm.py`, `tests/test_local_embedding.py`, `tests/test_vector_index.py`, `tests/test_pdf_reader.py`, `tests/test_docling_reader.py`, `tests/test_upload_validation.py`, `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`, `tests/test_summarizer.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_resource_telemetry.py`, `tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py`, `tests/test_cloud_privacy.py`, `tests/test_concurrency_lock.py`, `tests/test_cache_invalidation.py`, `tests/test_main_ui.py`.

**Naming:**
- Files: `test_<module>.py`.
- Functions: `test_<behavior>[_<condition>]`, e.g. `test_inference_gate_blocks_parallel_threads`, `test_validate_citations_hallucinated_rank`, `test_sha_unique_violation_on_reupload`.
- Requirement IDs are embedded in names where relevant: `test_corrupt_invalid_rejected_WR07`, `test_hybrid_retriever_dense_indexing_and_search`, `test_two_instance_interleave_R1`.

**Structure:**
```
tests/
├── __init__.py
├── conftest.py              # shared fixtures + mock seams
├── test_<module>.py         # one file per source module (24 files)
└── data/
    └── corpus/              # synthetic PDF fixtures + generator
```

## Test Structure

**Suite Organization:**
- Flat module-level `def test_...()` functions — no test classes anywhere in the suite.
- Every test has a docstring stating the contract, frequently with a requirement tag. Example (`tests/test_concurrency_lock.py:71-78`):
```python
def test_inference_gate_basic_acquire_release() -> None:
    """Test standard single-thread acquire and release."""
    assert not InferenceGate.is_locked()
    acquired = InferenceGate.acquire(timeout=1.0)
    assert acquired is True
    assert InferenceGate.is_locked()
    InferenceGate.release()
    assert not InferenceGate.is_locked()
```
- Multi-stage tests use numbered inline comments to narrate the scenario (`tests/test_models.py:165-217`, `tests/test_cloud_privacy.py:22-52`, `tests/test_local_llm.py`).
- File headers use the repo banner comment style (`tests/test_models.py:1-5`, `tests/test_doc_store.py:1-5`, `tests/test_pdf_reader.py:1-6`, `tests/test_upload_validation.py:1-5`) or a single module docstring (`tests/test_citation_validator.py:1`, `tests/test_concurrency_lock.py:1`, `tests/test_cloud_privacy.py:1`).

**Patterns:**
- Arrange / act / assert in a single function body; no `setup_method`/`teardown_method`.
- Local testing classes subclass `BaseModelProvider` and are defined in the test module (`DummyProvider` in `tests/test_concurrency_lock.py:13-58`, `MockSummarizerProvider` in `tests/test_summarizer.py:16-80`, `DummyLocalProvider` in `tests/test_main_ui.py:227-243`).
- Integration-style tests exercise real components on an isolated `tmp_path` (`tests/test_doc_store.py`, `tests/test_hybrid_retriever.py:100-120`, `tests/test_cache_invalidation.py:45-90`).

## Mocking

**Framework:** `unittest.mock` — `MagicMock`, `patch`, plus pytest's `monkeypatch`/`tmp_path`.

**Patterns:**
- Monkeypatch source-module symbols rather than the class under test (`tests/test_local_embedding.py:56`, `tests/test_local_llm.py:89,104`):
```python
with patch("local_embedding.SentenceTransformer", return_value=mock_instance) as mock_st_cls:
    m1 = get_shared_sentence_transformer("all-MiniLM-L6-v2", "cpu")
    m2 = get_shared_sentence_transformer("all-MiniLM-L6-v2", "cpu")
    assert m1 is m2
    mock_st_cls.assert_called_once_with("all-MiniLM-L6-v2", device="cpu")
```
- Spy on method calls with `wraps=` to assert forwarding (`tests/test_local_embedding.py:41-45`):
```python
with patch.object(embedding, "search", wraps=embedding.search) as spy_search:
    context = embedding.get_context("memory management", k=10)
    spy_search.assert_called_once_with("memory management", k=10)
```
- MagicMock for recognizer/renderer seams: `OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)` and `assert_not_called()` to prove OCR is bypassed (`tests/test_ocr_fallback.py:31-78`).
- `monkeypatch.setattr` for class-level behaviours and env vars: `monkeypatch.setattr(LlamaCppProvider, "check_health", lambda self: unreachable_status)` (`tests/test_local_llm.py:89`), `monkeypatch.delenv("GROQ_API_KEY", raising=False)` (`tests/test_local_llm.py:82`), `monkeypatch.setattr(pypdf, "PdfReader", StubReader)` (`tests/test_upload_validation.py:73`).
- HTTP transport injection via `httpx.MockTransport` rather than patching network internals (`tests/test_llama_cpp_provider.py` uses `httpx`; provider accepts `transport=` per `llama_cpp_provider.py:28,65`).
- Network egress guard: replace `socket.create_connection` with a function that raises `ConnectionRefusedError` to prove zero outbound calls (`tests/test_cloud_privacy.py:61-64`).

**What to Mock:**
- Heavy/optional third-party runtimes: SentenceTransformer model loading (`mock_sentence_transformer`), Groq client (`mock_groq_client`), RapidOCR recognizer/renderer, PyMuPDF rendering.
- External network and inference providers: always via the `BaseModelProvider` seam or `httpx.MockTransport`.
- GPU/OS telemetry: `nvidia-smi`/`psutil` results are stubbed or allowed to degrade to `None`/zeros.

**What NOT to Mock:**
- Pydantic schemas, `DocStore`, `VectorIndex`, `HybridRetriever`, `prompt_budget`, `citation_validator` — these are exercised for real against `tmp_path`/in-memory data.
- The synthetic PDF corpus (real PDFs are parsed by the real `PdfReader`/`DoclingReader`).

## Fixtures and Factories

**Shared fixtures live in `tests/conftest.py`:**

| Fixture | Purpose | Lines |
|---|---|---|
| `fake_env_groq_key` | Sets `GROQ_API_KEY` via `monkeypatch.setenv` | `tests/conftest.py:12-15` |
| `mock_groq_client` | Mocks `groq.Groq` with a streaming chunk generator | `tests/conftest.py:18-52` |
| `mock_sentence_transformer` | Patches `local_embedding.SentenceTransformer` with deterministic 384-dim normalised vectors | `tests/conftest.py:55-85` |
| `sample_pdf_path` | Absolute path to `tests/data/corpus/clean_digital.pdf` | `tests/conftest.py:88-92` |
| `mock_llama_provider` | Healthy `BaseModelProvider` subclass with recorded `stream_calls` | `tests/conftest.py:95-165` |

**Local fixtures:**
- `autouse=True` cleanup for global state: `ensure_gate_released` drains `InferenceGate` before/after every test (`tests/test_concurrency_lock.py:61-68`); `tests/test_resource_telemetry.py:25` clears telemetry state.
- Built-in `pytest` fixtures are the default for isolation: `tmp_path` for SQLite DB files and LanceDB directories (`tests/test_doc_store.py:16`, `tests/test_hybrid_retriever.py:48`, `tests/test_cache_invalidation.py:82`), `monkeypatch` for env/attr, `tmp_path`-based `tempfile.TemporaryDirectory` in older tests (`tests/test_cache_invalidation.py:47`).

**Test Data / Factories:**
- Module-level helper factories build domain objects: `_make_retrieval_result(num_snippets)` (`tests/test_citation_validator.py:14-33`), `_make_unit_vector(seed, dim=384)` (`tests/test_hybrid_retriever.py:12-19`).
- Pydantic models are constructed inline with fixed literals; common sha256 values are written as `"a" * 64` etc. (`tests/test_models.py`, `tests/test_doc_store.py`).
- Synthetic corpus generator: `tests/data/corpus/generate_corpus.py` uses `reportlab` to build six PDFs — `clean_digital.pdf` (20 pages), `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf` (raster-only, no text layer), `chart_diagram.pdf`, and `corrupt_invalid.pdf` (invalid magic bytes). CI regenerates it before running the suite (`.github/workflows/ci.yml:38-40`).
- Tests locate the corpus via `CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"` (`tests/test_pdf_reader.py:15`, `tests/test_upload_validation.py:13`, `tests/test_ocr_fallback.py:10-12`).

## Coverage

**Requirements:** None enforced. No `pytest-cov`, no `.coveragerc`, no coverage threshold, no coverage badge beyond the README test-count badge.

**View Coverage:** Not configured. Add `pytest-cov` to `requirements-test.txt` and run `pytest --cov=. --cov-report=term-missing` to introduce coverage.

## Test Types

**Unit Tests:**
- Pure logic and contracts: `tests/test_vector_index.py`, `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`, `tests/test_models.py`, `tests/test_model_provider.py`, `tests/test_upload_validation.py`.

**Integration Tests:**
- Real persistence and retrieval on `tmp_path`: `tests/test_doc_store.py` (SQLite WAL, migrations, UNIQUE(sha256)), `tests/test_hybrid_retriever.py` (LanceDB disk persistence + fallback), `tests/test_cache_invalidation.py`, `tests/test_summarizer.py`, `tests/test_visual_analyzer.py`.
- Provider integration through the `BaseModelProvider` seam: `tests/test_local_llm.py`, `tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py`, `tests/test_cloud_privacy.py`.
- Concurrency invariants with real threads: `tests/test_concurrency_lock.py` (`threading.Thread`, `threading.Event`).
- Corpus-driven ingestion: `tests/test_pdf_reader.py`, `tests/test_ocr_fallback.py`.

**E2E Tests:**
- Not used. Streamlit is not driven with `streamlit.testing.v1.AppTest`; `tests/test_main_ui.py` validates UI data contracts and helper logic (chat-turn schema, chip/card formatting, Clear All purge, consent-state transitions) in pure Python.

## Common Patterns

**Async / streaming testing** — collect a generator into a list and assert token-by-token output (`tests/test_local_llm.py:59-74`):
```python
generator = model.ask_a_question_from_pdf_stream(pdf_path="", prompt="...", local_embedding=mock_embedding)
tokens = list(generator)
assert tokens == ["This ", "is ", "a ", "grounded ", "answer."]
assert "".join(tokens) == "This is a grounded answer."
```
Busy-gate path asserts the single warning token (`tests/test_concurrency_lock.py:190-198`).

**Error testing** — assert exception type *and* message fragment with `match=`; messages are user-actionable and stable (`tests/test_upload_validation.py:22,57,75`, `tests/test_vector_index.py:17,52`, `tests/test_litellm_provider.py:30`).

**Fault isolation testing** — patch a single page/region to raise and assert the rest still process (`tests/test_pdf_reader.py:141-173`, `tests/test_ocr_fallback.py:140`, `tests/test_visual_analyzer.py:354`).

**Global-state reset** — any test touching `InferenceGate`, latency history, or the model cache must reset it via an `autouse` fixture or an explicit `clear_*()` call in `try/finally` (`tests/test_hybrid_retriever.py:28-36`).

**Watch-out:** several tests build `HealthStatus(status=..., message=..., provider_type="local")` (`tests/test_concurrency_lock.py:20`, `tests/test_main_ui.py:229`, `tests/test_summarizer.py:24`), but `HealthStatus` (`model_provider.py:44-61`) declares only `status`, `message`, `latency_ms` with `extra="forbid"`. These pass only because the mocked `check_health` is never invoked in those tests; calling it would raise `ValidationError`. Keep mock health helpers field-accurate when adding tests that do call `check_health`.

---

*Testing analysis: 2026-10-17*
