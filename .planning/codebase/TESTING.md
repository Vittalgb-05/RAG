<!-- refreshed: 2026-10-19 -->
# Testing Patterns

**Analysis Date:** 2026-10-19

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt:1`); running on Python 3.11 in CI.
- Configuration lives in `pyproject.toml:20-27`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  python_files = ["test_*.py"]
  python_functions = ["test_*"]
  filterwarnings = [
      "ignore::UserWarning",
      "ignore::DeprecationWarning",
  ]
  ```
- No `pytest.ini`, `setup.cfg`, or `tox.ini`.

**Assertion Library:**
- Plain `assert` statements (no `unittest.TestCase` subclasses anywhere).
- `pytest.raises(Exc, match="...")` for error paths; `pytest.approx(..., abs=1e-5)` for float math.

**Run Commands:**
```bash
pytest                          # Run all tests (testpaths=tests)
pytest tests/ -v                # Verbose — what CI runs (.github/workflows/ci.yml:50)
pytest tests/test_doc_store.py  # Single module
pytest tests/test_local_llm.py::test_ai_model_prompt_assembly  # Single test
ruff check .                    # Lint (CI gate, .github/workflows/ci.yml:39)
ruff format --check .           # Format gate (CI, .github/workflows/ci.yml:41)
```
- Current suite: **254 tests passing** (per project state; `tests/` currently defines 267 `test_*` functions across 26 test modules).
- CI (`.github/workflows/ci.yml`) installs from `requirements-lock.txt` + `requirements-test.txt` via `uv`, runs `ruff check`/`ruff format --check`, then `python tests/data/corpus/generate_corpus.py`, then `pytest tests/ -v`.

**Test-only dependencies (`requirements-test.txt`):**
- `pytest>=8.3.0`, `reportlab>=4.2.0` (synthetic PDF corpus), `ruff>=0.9.0`, `psutil>=6.1.0`.

## Test File Organization

**Location:** dedicated `tests/` package (`tests/__init__.py`), one module per source module.

```
tests/
├── __init__.py
├── conftest.py                 # shared fixtures + mocking seams
├── data/corpus/
│   ├── generate_corpus.py      # reportlab corpus generator (run before pytest in CI)
│   ├── clean_digital.pdf
│   ├── scanned_sample.pdf
│   ├── dense_table.pdf
│   ├── chart_diagram.pdf
│   ├── multi_column.pdf
│   └── corrupt_invalid.pdf
├── test_<module>.py            # one per source module
└── test_logging_setup.py       # 254-suite member for logging_setup.py
```

**Naming:**
- Files: `test_<source_module>.py` (e.g. `test_doc_store.py` ↔ `doc_store.py`, `test_logging_setup.py` ↔ `logging_setup.py`).
- Functions: `test_<behaviour>_<condition>` describing the invariant, not the method name. Examples: `test_sha_unique_violation_on_reupload` (`tests/test_doc_store.py:41`), `test_ai_model_local_mode_does_not_silently_fallback_to_groq` (`tests/test_local_llm.py:131`), `test_suppress_is_idempotent` (`tests/test_logging_setup.py:42`), `test_vlm_analysis_error_isolation` (`tests/test_visual_analyzer.py:244`).
- Every test function has a one-line docstring stating what it verifies; many cite requirement/risk IDs, e.g. `"(QUAL-01)"`, `"(WR-02)"`, `"(INF-03, INF-04)"`, `"(CR-01)"`, `"(SEC-01)"`.
- Helper builders are module-private with the `_` prefix: `_make_retrieval_result` (`tests/test_citation_validator.py:14`).
- Return annotations (`-> None`) are present on roughly 111 of 267 test functions — follow the host file's style; newer modules (`test_local_llm.py`, `test_llama_cpp_provider.py`, `test_citation_validator.py`) annotate consistently.

## Test Structure

**Suite organization — flat module-level functions** (no test classes, no nested `describe`):

```python
"""Unit tests for citation validation and abstention detection."""

from citation_validator import (
    CitationVerificationResult,
    detect_adversarial_injection,
    extract_citations,
    is_abstention,
    validate_citations,
)
from models import EvidenceSnippet, RetrievalResult


def _make_retrieval_result(num_snippets: int = 3) -> RetrievalResult:
    """Helper to construct a canonical RetrievalResult with dummy snippets."""
    snippets = [EvidenceSnippet(...) for i in range(1, num_snippets + 1)]
    return RetrievalResult(query="test query", snippets=snippets, total_candidates=num_snippets, search_mode="hybrid")


def test_extract_citations() -> None:
    """Verify regex extraction of bracketed citations [En] in various formats."""
    assert extract_citations("Simple citation [E1].") == [1]
```
(Companion functions grouped by behaviour — extraction, abstention, precision, injection — within one file.)

**Patterns:**
- Arrange–act–assert with section comments (`# 1. Check ...`, `# 2. Check ...`) for multi-branch tests (`tests/test_citation_validator.py:132-168`).
- Multiple related `assert`s per test are normal; docstrings enumerate the intent.
- Boundary/edge cases are explicit tests rather than parameterised: e.g. `test_zero_magnitude_vector` (`tests/test_vector_index.py:105`), `test_analyze_image_empty_bytes_raises` (`tests/test_llama_cpp_provider.py:233`), `test_crop_visual_element_out_of_bounds_and_inverted_coords` (`tests/test_visual_analyzer.py:272`).
- Regression tests name the regression: `test_visual_analyzer_uses_modern_pymupdf_import` (`tests/test_visual_analyzer.py:386`), `test_ocr_fallback_uses_modern_pymupdf_import` (`tests/test_ocr_fallback.py:15`).

## Mocking

**Framework:** `unittest.mock` + pytest `monkeypatch`.

**Shared mock providers (preferred for LLM/VLM seams):** local classes subclassing `BaseModelProvider`, recording calls for assertions. Defined in `tests/conftest.py:100-164` (`MockLlamaCppProvider`) and re-declared locally for specialised behaviour: `MockSummarizerProvider` (`tests/test_summarizer.py:16`), `MockVisionProvider`/`MockTextOnlyProvider` (`tests/test_visual_analyzer.py:19,58`), `DummyProvider` (`tests/test_concurrency_lock.py:13`). This is the canonical way to test anything that depends on inference without a GPU.

**MagicMock `side_effect` for streams and failures:**
```python
mock_client.chat.completions.create.side_effect = mock_create   # generator of MockChunk
failing_provider.analyze_image = MagicMock(side_effect=RuntimeError("VLM GPU inference timeout"))
```
(`tests/conftest.py:43`, `tests/test_visual_analyzer.py:259`.)

**monkeypatch patterns:**
- `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")` / `monkeypatch.delenv("GROQ_API_KEY", raising=False)` (`tests/conftest.py:15`, `tests/test_local_llm.py:82`).
- `monkeypatch.setattr(LlamaCppProvider, "check_health", lambda self: unreachable_status)` to drive provider routing (`tests/test_local_llm.py:89,104,117`).
- `monkeypatch.setattr("streamlit.secrets", {}, raising=False)` to fake Streamlit context (`tests/test_local_llm.py:83`).
- `monkeypatch.setattr(socket, "create_connection", guarded_create_connection)` to assert **zero network egress** during local ingestion (`tests/test_cloud_privacy.py:64`) — the pattern to reuse for any privacy invariant test.
- `monkeypatch.setattr("visual_analyzer.fitz", FakeFitz)` to inject a fake third-party module when the real one may be absent (`tests/test_visual_analyzer.py:332`).

**HTTP mocking:** `httpx.MockTransport(handler)` with a handler asserting the request path and returning canned `httpx.Response` bodies (including SSE byte strings). See `tests/test_llama_cpp_provider.py:34,50,100,155` — the standard way to test `LlamaCppProvider` offline. Inject via `LlamaCppProvider(transport=transport)`.

**Fake third-party objects:** `FakeRect`/`FakePage`/`FakeDoc`/`FakeFitz` in `tests/test_visual_analyzer.py:287-331`; `MockDoc`/`MockTable`/`MockItem` in `tests/test_docling_reader.py:40-70`.

**What to mock:**
- All inference backends (LLM/VLM), network transports (`httpx.MockTransport`), `streamlit` context, GPU probing (`nvidia-smi`) and psutil, and any optional dependency not installed.
- Set environment/config to deterministic values via `monkeypatch` before constructing objects that read env.

**What NOT to mock:**
- Pydantic models, SQLite (`DocStore` runs against real temp-file DBs via `tmp_path`), the filesystem, pure-Python algorithm code (`VectorIndex` math, RRF/BM25, citation regex), and Streamlit presentation *data contracts* (asserted as plain dicts — see `tests/test_main_ui.py`).

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**
| Fixture | Purpose |
|---|---|
| `fake_env_groq_key` | Sets mock `GROQ_API_KEY` env var (`conftest.py:12-15`) |
| `mock_groq_client` | Mocks `groq.Groq` + streaming `create` yielding delta chunks (`conftest.py:18-52`) |
| `mock_sentence_transformer` | Mocks `SentenceTransformer` with deterministic 384-dim L2-normalised float32 vectors (`conftest.py:55-85`) |
| `sample_pdf_path` | Path to `tests/data/corpus/clean_digital.pdf` (`conftest.py:88-92`) |
| `mock_llama_provider` | `BaseModelProvider`-conformant mock with `stream_calls` recorder (`conftest.py:95-164`) |

**Fixture authoring conventions:**
- Monkeypatch target imported inside the fixture (not at module import) so a missing optional package is tolerated (`conftest.py:45-50`).
- Deterministic outputs — no randomness; embeddings derive from text length so assertions are stable (`conftest.py:63-78`).

**Local autouse fixture:** `ensure_gate_released` releases `InferenceGate` before and after every test in `tests/test_concurrency_lock.py:61-68` — the template for cleaning up process-global singletons/locks.

**Factories:** module-private builder helpers returning canonical models: `_make_retrieval_result(num_snippets=3)` (`tests/test_citation_validator.py:14`). Inline `Document`/`Chunk`/`Page`/`SummaryResult` construction with fixed `sha256="a"*64`-style digests is idiomatic in `test_doc_store.py`, `test_summarizer.py`, `test_visual_analyzer.py`.

**Corpus:** synthetic PDFs generated by `tests/data/corpus/generate_corpus.py` (reportlab); modules resolve them via `Path(__file__).resolve().parent / "data" / "corpus"` (`tests/test_visual_analyzer.py:14`, `tests/test_ocr_fallback.py:10`, `tests/test_docling_reader.py:11`). CI regenerates the corpus before the test run (`.github/workflows/ci.yml:45-46`).

**Isolation:** `tmp_path` is used for all on-disk state — SQLite DBs and LanceDB dirs (34 uses in `test_doc_store.py`, 24 in `test_hybrid_retriever.py`, plus `test_summarizer.py`, `test_setup_llama.py`, `test_start_launcher.py`, `test_main_ui.py`, `test_models.py`). Never write test data to the repo tree.

## Coverage

**Requirements:** None enforced. No `pytest-cov` dependency and no coverage config; `.coverage`/`htmlcov/` are gitignored (`.gitignore:12-13`) rather than configured.

**View Coverage (if added):**
```bash
pytest --cov=. --cov-report=term-missing
```

## Test Types

**Unit Tests (majority):** pure algorithm and contract tests — `test_vector_index.py`, `test_prompt_budget.py`, `test_citation_validator.py`, `test_models.py`, `test_upload_validation.py`, `test_logging_setup.py`. Fully offline; no I/O beyond `tmp_path`.

**Integration Tests (in-process, still offline):** real SQLite via `DocStore` (`test_doc_store.py`), LanceDB/fallback retrieval (`test_hybrid_retriever.py`), provider routing and hibernation (`test_local_llm.py`), summarization cache (`test_summarizer.py`), concurrency lock with real threads (`test_concurrency_lock.py`), privacy egress guard (`test_cloud_privacy.py`), and provider HTTP against `httpx.MockTransport` (`test_llama_cpp_provider.py`, `test_litellm_provider.py`, `test_groq_provider.py`).

**End-to-End:** None (no browser/Streamlit-app E2E). UI is tested at the **data-contract** level: `tests/test_main_ui.py` asserts the shape and formatting of chat-turn dicts, evidence cards, summary labels, and Clear-All session-state logic without launching Streamlit.

**Design principle:** the `tests/conftest.py:1-4` header states the intent — *"Allows 100% offline unit testing without GPU allocation or API calls."* Tests must not require a GPU, network, or `llama-server`.

## Common Patterns

**Structured health/status assertions:** providers return `HealthStatus`; tests assert `status` and message substrings rather than exceptions (`test_health_check_healthy/loading_503/unreachable/error_status` in `tests/test_llama_cpp_provider.py:27-84`).

**Async/concurrency testing:** `threading.Thread` + `threading.Event` to assert mutual exclusion and timeout behaviour (`tests/test_concurrency_lock.py:114-165`); a spy wrapper records `InferenceGate.is_locked()` during the guarded call:
```python
def spy_generate(*args, **kwargs):
    gate_was_locked.append(InferenceGate.is_locked())
    return orig_generate(*args, **kwargs)
provider.generate_text = spy_generate  # type: ignore[method-assign]
```
(`tests/test_concurrency_lock.py:178-186`.)

**Error testing:**
```python
with pytest.raises(ValueError, match="distance_metric must be 'cosine' or 'euclidean'"):
    VectorIndex(distance_metric="manhattan")
```
(`tests/test_vector_index.py:17`.) `match=` is used consistently to pin the message.

**Generator/stream testing:** `tokens = list(model.ask_a_question_from_pdf_stream(...))` then assert exact token list and joined string (`tests/test_local_llm.py:35-74`).

**Privacy/egress invariants:** monkeypatch `socket.create_connection` to raise, then exercise ingestion/embedding/search and assert results still produced (`tests/test_cloud_privacy.py:55-102`).

---

*Testing analysis: 2026-10-19*
