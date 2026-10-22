# Testing Patterns

**Analysis Date:** 2026-10-22

## Test Framework

**Runner:**
- pytest `>= 8.3.0` (`requirements-test.txt`).
- Configuration: `pyproject.toml:21-28`
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
- No `pytest.ini`, `tox.ini`, or `setup.cfg` overrides.
- No custom markers are registered or used. `pytest.mark.parametrize` is used once (`tests/test_setup_checksums.py:125`); everything else is plain functions.

**Assertion Library:**
- Built-in `assert` statements; `pytest.raises(...)` for exception contracts.
- `unittest.mock` (`MagicMock`, `patch`, `monkeypatch`) for seams.

**Run Commands:**
```bash
pytest tests/ -v                 # Full suite (CI command)
pytest tests/test_hybrid_retriever.py -v   # Single suite
pytest -k "mirror or fallback"   # Substring selection
ruff check .                     # Lint
ruff format --check .            # Format check
python tests/data/corpus/generate_corpus.py  # Regenerate synthetic PDFs
```

**Current state:** 389 tests across 32 `tests/test_*.py` suites, all passing. Ruff `check` and `format --check` are clean across 76 files.

## Test File Organization

**Location:**
- Flat `tests/` directory; no mirroring of the `core/` / `ui/` package tree.
- One suite per module or cross-cutting behavior: `tests/test_doc_store.py` ↔ `core/doc_store.py`, `tests/test_hybrid_retriever.py` ↔ `retrieval/hybrid_retriever.py`.
- Feature/regression suites group behavior that spans modules: `tests/test_whole_document_extraction.py`, `tests/test_audit_repairs.py`, `tests/test_cloud_privacy.py`, `tests/test_cache_invalidation.py`, `tests/test_concurrency_lock.py`.

**Naming:**
- Files: `test_<module_or_feature>.py`.
- Functions: `test_<behavior>_<condition>`, e.g. `test_existing_file_with_wrong_hash_is_replaced`, `test_deleted_document_does_not_resurrect_from_fallback`, `test_fts_status_reports_degradation_and_warns_once`.
- Each test has a one-line docstring describing the invariant, often with a requirement tag: `"""Verify LocalEmbedding explicitly initializes SentenceTransformer on CPU (RETR-01)."""` (`tests/test_hybrid_retriever.py:25`).

**Structure:**
```
tests/
├── conftest.py                  # Shared offline fixtures and mocks
├── test_<module>.py             # Per-module unit tests (32 suites)
└── data/corpus/
    ├── generate_corpus.py       # reportlab synthetic PDF generator
    ├── clean_digital.pdf
    ├── multi_column.pdf
    ├── dense_table.pdf
    ├── chart_diagram.pdf
    ├── scanned_sample.pdf
    └── corrupt_invalid.pdf
```

**Suite sizes (lines):** `test_doc_store.py` 754, `test_hybrid_retriever.py` 738, `test_main_ui.py` 592, `test_ocr_fallback.py` 589, `test_visual_analyzer.py` 517.

## Test Structure

**Suite Organization:**
```python
"""Unit tests for InferenceGate process-level concurrency lock (QUAL-01)."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.local_llm import AiModel, InferenceGate
from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities


@pytest.fixture(autouse=True)
def ensure_gate_released() -> None:
    """Ensure InferenceGate is fully released before and after every test."""
    while InferenceGate.is_locked():
        InferenceGate.release()
    yield
    while InferenceGate.is_locked():
        InferenceGate.release()


def test_inference_gate_basic_acquire_release() -> None:
    """Test standard single-thread acquire and release."""
    assert not InferenceGate.is_locked()
    acquired = InferenceGate.acquire(timeout=1.0)
    assert acquired is True
    assert InferenceGate.is_locked()
    InferenceGate.release()
    assert not InferenceGate.is_locked()
```
(`tests/test_concurrency_lock.py:1-78`)

**Patterns:**
- **Arrange–Act–Assert with comments labeling non-obvious phases** (`tests/test_cloud_privacy.py:31-56` numbers the consent state machine steps).
- **`tmp_path` for every filesystem-backed test.** SQLite (`tmp_path / "test_docs.db"`), LanceDB (`tmp_path / "lancedb_test"`), and cache directories are always per-test. No shared on-disk state, no cleanup fixtures needed.
- **`autouse` fixtures reset global/module state** when a suite touches process-wide singletons:
  - `InferenceGate` lock (`tests/test_concurrency_lock.py:61`)
  - `st.session_state` (`tests/test_ui_smoke.py:27`, `tests/test_hydration.py:12`)
  - logging handlers (`tests/test_logging_setup.py:18`, calls `reset_logging()` after yield)
  - telemetry caches (`tests/test_resource_telemetry.py:25`)
- **Assertions check exact values and structural invariants**, not just truthiness: page ordering `list(range(1, 12))`, rank contiguity, RRF score arithmetic, persisted JSON contents, and warning counts.
- **Teardown by context managers:** providers are closed with `provider.close()` or `with LlamaCppProvider(transport=transport) as provider:` (`tests/test_llama_cpp_provider.py:269`); retrievers use `with HybridRetriever(...) as retriever:` (`tests/test_hybrid_retriever.py:384`).

## Mocking

**Framework:** `unittest.mock` + pytest `monkeypatch` + `httpx.MockTransport`.

**Patterns:**

*HTTP seam (preferred for the local inference provider):*
```python
def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/chat/completions"
    captured = json.loads(request.read())
    return httpx.Response(200, json={"choices": [{"message": {"content": "Generated reply."}}]})

transport = httpx.MockTransport(handler)
provider = LlamaCppProvider(transport=transport)
```
(`tests/test_llama_cpp_provider.py:30-34`, `:91-101`)

*Dependency substitution via constructor injection:*
```python
retriever = HybridRetriever(db_uri=tmp_path / "semantic_boost_db", embedding_fn=mock_embed)
```
(`tests/test_hybrid_retriever.py:246`) — prefer this over patching when the class accepts the dependency.

*Monkeypatching module attributes / optional dependencies:*
```python
monkeypatch.setattr("retrieval.hybrid_retriever.lancedb", None)
monkeypatch.setattr(setup_mod.urllib.request, "urlopen", fail_urlopen)
monkeypatch.setenv("RAG_REQUIRE_CHECKSUMS", "1")
```
(`tests/test_hybrid_retriever.py:160`, `tests/test_setup_checksums.py:58`, `:111`)

*Provider fakes:* tests implement `BaseModelProvider` subclasses that record calls and return deterministic text, rather than mocking every method:
- `MockLlamaCppProvider` (`tests/conftest.py:107-171`) records `stream_calls`.
- `DummyProvider` (`tests/test_concurrency_lock.py:13-58`).
- `MockSummarizerProvider` (`tests/test_summarizer.py:15-100`) branches on prompt markers to emulate map/reduce phases.

**What to Mock:**
- Network transport (`httpx.MockTransport`), model downloads (`urllib.request.urlopen`), and cloud SDK clients (`groq.Groq`).
- Expensive model loads (`SentenceTransformer`) and any GPU work.
- Optional native deps (`lancedb`, `fitz`, `RapidOCR`, `docling`) via `monkeypatch.setattr(module, "name", None)` to exercise fallback paths.

**What NOT to Mock:**
- `DocStore`, `HybridRetriever`, `VectorIndex`, or `Summarizer` business logic — these run for real against `tmp_path`.
- `InferenceGate` — tests exercise real `RLock` semantics with threads (`tests/test_concurrency_lock.py:114-200`).
- Pydantic validation — tests construct real models and assert `ValidationError` (`tests/test_models.py`).
- Exception types — assert the real `ValueError`/`PermissionError`/`TimeoutError`/`sqlite3.IntegrityError` rather than a generic `Exception`.

**Offline enforcement:**
- `tests/conftest.py:6-11` sets `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` before importing torch-dependent modules.
- `tests/test_cloud_privacy.py:58-64` monkeypatches `socket.create_connection` to raise `ConnectionRefusedError`, proving local ingestion/indexing performs no egress.
- Checksum tests assert that the network is **not** touched when a valid artifact already exists (`tests/test_setup_checksums.py:49-66`).

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**

| Fixture | Lines | Purpose |
|---|---|---|
| `fake_env_groq_key` | 19-22 | Sets mock `GROQ_API_KEY` via `monkeypatch.setenv`. |
| `mock_groq_client` | 26-59 | Patches `providers.groq_provider.Groq`; yields canned stream deltas. |
| `mock_sentence_transformer` | 63-92 | Deterministic 384-dim normalized vectors; patches `retrieval.local_embedding.SentenceTransformer`. |
| `sample_pdf_path` | 96-99 | Path to `tests/data/corpus/clean_digital.pdf`. |
| `mock_llama_provider` | 103-171 | Healthy `BaseModelProvider` fake with recorded `stream_calls`. |

**Local fixtures:**
- Suite-specific `autouse` resets (see above).
- `question_retriever` builds an 11-page synthetic exam booklet with a deterministic SHA-256 hashing embedding and real LanceDB + FTS (`tests/test_whole_document_extraction.py:54-72`).
- `_make_unit_vector(seed)` produces deterministic normalized vectors for retrieval tests (`tests/test_hybrid_retriever.py:14-21`).
- `_doc(...)` / `_indexed_document(...)` helpers construct domain records consistently (`tests/test_audit_repairs.py:28-39`, `tests/test_hydration.py:56`).

**Test data:**
- Synthetic PDFs generated with reportlab by `tests/data/corpus/generate_corpus.py`; CI regenerates them before running pytest (`.github/workflows/ci.yml`).
- No binary fixtures are required for unit tests except this corpus; most suites fabricate `Document`/`Page`/`Chunk` objects inline.
- Timestamps in fixtures are fixed ISO-8601 strings (`"2026-10-11T01:00:00Z"`), never `datetime.now()`.

## Coverage

**Requirements:** None enforced. `pytest-cov` is not in `requirements-test.txt`, and `pyproject.toml` has no `--cov` addopts or `fail_under` threshold. CI runs plain `pytest tests/ -v`.

**View Coverage:**
```bash
# Not configured; add pytest-cov before relying on this
pytest tests/ --cov=core --cov=ingestion --cov=retrieval --cov=providers --cov=ui
```

**Practical coverage expectations:** every source module has a corresponding suite (`core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`), with the exception of `ui/theme.py` (CSS injection) and the `scripts/` profiling utilities, which have no dedicated tests. The emphasis is behavioral coverage of safety invariants (privacy, concurrency, citation grounding, persistence) rather than line percentage.

## Test Types

**Unit Tests:**
- Majority of the suite. Pure functions, Pydantic validation, SQLite schema/migrations, vector index math, prompt budgeting, citation validation, sanitizer regexes.
- No network, GPU, or full application launch.

**Integration Tests:**
- Real `DocStore` + `HybridRetriever` + embeddings on `tmp_path` (e.g. `tests/test_cache_invalidation.py`, `tests/test_whole_document_extraction.py`).
- Provider request/response contracts via `httpx.MockTransport`.
- Startup hydration against a real SQLite DB with patched retriever/embedding classes (`tests/test_hydration.py:33-52`).

**End-to-End Tests:**
- No browser/Streamlit server E2E. `tests/test_ui_smoke.py` renders component markup and calls view helpers directly with a cleared `st.session_state`.
- `tests/test_start_launcher.py` tests launcher argument/loopback logic without spawning Streamlit.
- `tests/test_whole_document_extraction.py:159-186` is the closest structural end-to-end: real retrieval through `AiModel` to a fake provider stream.

**Performance / Concurrency Tests:**
- `tests/test_concurrency_lock.py` uses real `threading.Thread` + `threading.Event` to verify serialization, reentrancy, timeout, and unauthorized release.
- `tests/test_hybrid_retriever.py:683-712` indexes 10,000 chunks to verify scoped search is not capped.

## Common Patterns

**Deterministic embeddings:**
```python
def _embed(text: str) -> list[float]:
    vector = [0.0] * 384
    for token in text.lower().replace("?", " ").split():
        digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vector[digest % 384] += 1.0
    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]
```
(`tests/test_whole_document_extraction.py:44-51`)

**Asserting log behavior:**
```python
with caplog.at_level(logging.WARNING, logger="retrieval.hybrid_retriever"):
    retriever.create_fts_index()
    retriever.create_fts_index()

warnings = [r for r in caplog.records if "full-text search unavailable" in r.getMessage()]
assert len(warnings) == 1
```
(`tests/test_hybrid_retriever.py:727-738`)

**Exception contracts:**
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    unconsented_cloud.generate_text("Test prompt")
```
(`tests/test_cloud_privacy.py:39-40`)

**Thread coordination (no sleeps as synchronization):**
```python
t1_started = threading.Event()
t1_finish = threading.Event()
```
(`tests/test_concurrency_lock.py:117-118`; worker threads signal via `Event.set`/`wait`.)

**Parameterized environment parsing:**
```python
@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_require_checksums_is_disabled_by_default(monkeypatch, value):
    monkeypatch.setenv("RAG_REQUIRE_CHECKSUMS", value)
    assert setup_mod.require_pinned_checksums() is False
```
(`tests/test_setup_checksums.py:125-129`)

**Regression formatting:** failing scenarios are reproduced structurally without the original artifact. `tests/test_whole_document_extraction.py` rebuilds the EVS.pdf failure from 11 in-memory pages and asserts the render gate withholds uncited answers. `tests/test_audit_repairs.py` is a dedicated regression ledger for audit fixes (index path, silent vector loss, cache invalidation, consent, sanitizer gaps, model identity).

**Async testing:** Not applicable — the codebase is synchronous. Streaming is tested by consuming generators (`list(model.ask_a_question_from_pdf_stream(...))`, `tests/test_whole_document_extraction.py:166-173`), and concurrency is tested with threads.

**Windows/portability:** Tests avoid platform-specific paths by using `tmp_path` and `Path`; the CI runner is Ubuntu, while local development is Windows. No test asserts OS-specific separators.

---

*Testing analysis: 2026-10-22*
