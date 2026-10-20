# Testing Patterns

**Analysis Date:** 2026-10-20

## Test Framework

**Runner:**
- `pytest` (`>=8.3.0`, `requirements-test.txt:2`); local environment has pytest 9.0.3 (per `tests/__pycache__/*pytest-9.0.3*`).
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:20-27`.
  - `testpaths = ["tests"]`
  - `python_files = ["test_*.py"]`
  - `python_functions = ["test_*"]`
  - `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]` — warnings are globally silenced; do not rely on warnings for assertions.
- No plugins configured (no `pytest-cov`, `pytest-asyncio`, `pytest-xdist`, `pytest-mock`).

**Assertion Library:**
- Plain `assert` statements (pytest assertion rewriting). No `unittest.TestCase`, no Hamcrest.
- Exception assertions use `pytest.raises(ExceptionType, match="stable message fragment")`.

**Run Commands:**
```bash
pip install -r requirements.txt -r requirements-test.txt
python tests/data/corpus/generate_corpus.py   # required before corpus-dependent tests (CI does this)
pytest tests/ -v                              # full suite (CI command)
pytest tests/test_main_ui.py -v               # one module
pytest tests/ -q                              # quiet
pytest --collect-only -q                      # count tests without running
ruff check . && ruff format --check .         # lint/format gates (CI)
```

**Current suite size:** 289 tests collected (`pytest --collect-only -q`, 2026-10-20). The suite spans 29 test modules; the heaviest are `tests/test_doc_store.py` (17), `tests/test_hybrid_retriever.py` (17), `tests/test_llama_cpp_provider.py` (17), and `tests/test_models.py` (20). `docs/EVALUATION.md:14-17` and `README.md:10,106,225` still claim **248** tests / 24 suites — those numbers are stale; re-collect before quoting them.

## Test File Organization

**Location:**
- All tests live in a separate top-level `tests/` package (`tests/__init__.py` present), not co-located with source.
- One file per production module, named `test_<module>.py`: `tests/test_hybrid_retriever.py` ↔ `hybrid_retriever.py`, `tests/test_doc_store.py` ↔ `doc_store.py`, `tests/test_ocr_fallback.py` ↔ `ocr_fallback.py`, `tests/test_main_ui.py` ↔ `main.py` + `ui/views.py` contracts, `tests/test_logging_setup.py` ↔ `logging_setup.py`.
- Cross-cutting invariant suites are named by concern rather than module: `tests/test_cloud_privacy.py` (network egress + consent), `tests/test_concurrency_lock.py` (`InferenceGate`), `tests/test_cache_invalidation.py` (summary cache versions), `tests/test_ui_smoke.py` (UI regression smoke).

**Naming:**
- Test functions: `test_<behavior>_<condition>` in `snake_case`, no `test_` class grouping anywhere (0 test classes in the repo).
- Helpers: `_`-prefixed module-level functions, e.g. `_make_unit_vector` (`tests/test_hybrid_retriever.py:14`).
- Fixtures: noun/adjective names describing the seam: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`; autouse cleanup fixtures `clean_session_state`, `ensure_gate_released`.

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                 # shared fixtures + global env guards
├── test_<module>.py            # 29 suites
└── data/
    └── corpus/
        ├── generate_corpus.py  # reportlab generator (not collected)
        ├── clean_digital.pdf
        ├── scanned_sample.pdf
        ├── dense_table.pdf
        ├── multi_column.pdf
        ├── chart_diagram.pdf
        └── corrupt_invalid.pdf
```

## Test Structure

**Module header:** Most suites begin with a module docstring naming the subsystem and requirement IDs, e.g. `"""Unit tests for HybridRetriever persistent vector storage and CPU embedding pipeline (RETR-01, RETR-02)."""` (`tests/test_hybrid_retriever.py:1`). Older suites use a `# ---` banner comment instead (`tests/test_models.py:1-5`). New files should use the docstring form.

**Suite organization:** Flat top-level functions, no classes, no `setup_method`. Fixtures provide setup; cleanup is `finally` blocks or autouse fixtures.

```python
"""Unit tests for HybridRetriever persistent vector storage and CPU embedding pipeline (RETR-01, RETR-02)."""

from unittest.mock import MagicMock

import numpy as np

from hybrid_retriever import DEFAULT_DB_URI, HybridRetriever, compute_rrf
from models import BBox, Chunk, EvidenceElement, RetrievalResult


def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:
    """Generate a deterministic normalized float vector."""
    np.random.seed(seed)
    v = np.random.randn(dim).astype(np.float32)
    norm = np.linalg.norm(v)
    if norm > 0:
        v = v / norm
    return [float(x) for x in v]


def test_hybrid_retriever_dense_indexing_and_search(tmp_path):
    """Verify chunks are indexed and nearest neighbors returned by cosine similarity."""
    retriever = HybridRetriever(db_uri=tmp_path / "lancedb_test")
    ...
    assert retriever.count_chunks() == 3
    assert results[0]["chunk_id"] == "chk_gpu_01"
    assert results[0]["score"] >= 0.95
```

**Patterns:**
- Public-API tests: construct the real object, call a public method, assert on the returned Pydantic model or dict.
- Arrange/Act/Assert with numbered narrative comments for multi-phase behavior: `# 1. Initialize...`, `# 2. Attempting...`, `# 3. Explicit consent...` (`tests/test_cloud_privacy.py:31-62`; `tests/test_main_ui.py:159-191`).
- Assertions are behavioral, not structural: count/index/score equality, `model_dump()` key checks, `assert_called_once_with(...)`, message substrings.
- Cleanup is explicit where global state is mutated (`tests/test_hybrid_retriever.py:22-35` restores `local_embedding.SentenceTransformer` and clears `_MODEL_CACHE` in `finally`).
- Every test claims a requirement tag in its docstring when it guards a specific invariant (`(RETR-03)`, `(WR-01)`, `(P0-2)`, `(INF-03)`), and regression tests name the defect ID.

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `patch`) plus pytest's `monkeypatch`. No `pytest-mock` `mocker` fixture.

**Global test env guards** — set before any heavy import in `tests/conftest.py:6-11`:
```python
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
```
This prevents TensorFlow/Keras import overhead and keeps tests offline.

**Pattern 1 — `monkeypatch.setattr` on a module attribute (preferred for module-level seams):**
```python
import local_embedding

monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name, **kwargs: mock_model)
```
(`tests/conftest.py:89-92`)

Dotted-path form when the target module is not imported in the test:
```python
monkeypatch.setattr("hybrid_retriever.lancedb", None)
```
(`tests/test_hybrid_retriever.py:158`)

**Pattern 2 — `patch("<module>.<Symbol>")` context manager (preferred for constructor seams):**
```python
with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
    mock_instance = MagicMock()
    mock_instance.count_chunks.return_value = 5
    mock_retriever_cls.return_value = mock_instance
    with patch("ui.hydration.LocalEmbedding") as mock_embed_cls:
        mock_embed_cls.return_value = MagicMock()
        hydrate_startup_state(store)
```
(`tests/test_hydration.py:40-49`, mirrored in `tests/test_ui_smoke.py:139-146`)

**Pattern 3 — fake provider subclasses instead of mocking the whole provider contract** (preferred when testing `AiModel` routing/locking):
```python
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities

class DummyProvider(BaseModelProvider):
    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="ok", provider_type="local")

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(model_name="dummy-model", context_window=4096, ...)

    def stream_text(self, prompt, system_prompt=None, history=None, max_tokens=1024):
        yield "token1 "
        yield "token2"
```
(`tests/test_concurrency_lock.py:13-57`; reusable version `mock_llama_provider` in `tests/conftest.py:102-172`)

**Pattern 4 — deterministic fake embeddings** (no model download, no GPU):
```python
def mock_encode(texts, normalize_embeddings=True, **kwargs):
    vectors = []
    for i, t in enumerate(texts):
        vec = np.zeros(384, dtype=np.float32)
        vec[0] = 1.0 + (len(t) % 10) * 0.1
        vec[1] = 0.5 + (i % 5) * 0.1
        if normalize_embeddings:
            vec = vec / np.linalg.norm(vec)
        vectors.append(vec)
    return np.array(vectors, dtype=np.float32)
```
(`tests/conftest.py:70-87`)

**Pattern 5 — HTTP mocking with `httpx.MockTransport`** (no live llama-server; assert on request path):
```python
def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/health"
    return httpx.Response(200, json={"status": "ok"})

provider = LlamaCppProvider(transport=httpx.MockTransport(handler))
```
(`tests/test_llama_cpp_provider.py:28-40`)

**Pattern 6 — network egress guard** (prove local-mode code cannot open sockets):
```python
def guarded_create_connection(*args, **kwargs):
    raise PermissionError("Cloud transmission blocked")
monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
```
(`tests/test_cloud_privacy.py:55-64`)

**Pattern 7 — fake Streamlit session state** when `st.session_state` is not available outside a Streamlit script run:
```python
fake_state = {"cloud_api_keys": {"groq": "mock-key"}}
monkeypatch.setattr(st, "session_state", fake_state, raising=False)
```
(`tests/test_cloud_privacy.py:242`)

**What to mock:**
- Any network boundary (`socket.create_connection`, provider HTTP transports, `groq.Groq`, `litellm`).
- Heavy models (`SentenceTransformer`, Docling converter, RapidOCR, VLM `analyze_image`).
- Process-global caches and locks when testing cleanup: call `clear_shared_model_cache()` and drain `InferenceGate` in fixtures.
- Filesystem roots: always pass `tmp_path` for `DocStore(db_path)` and `HybridRetriever(db_uri=tmp_path / ...)`; never write into repo `data/` or `.cache/`.

**What NOT to mock:**
- Pydantic models, `compute_rrf`, `bound_chat_history`, sanitizers, citation validation, and other pure logic — exercise the real implementation.
- `DocStore` SQLite behavior — tests use a real SQLite file under `tmp_path` (`tests/test_doc_store.py`), not a mocked connection.
- Streamlit session-state mechanics in `tests/test_main_ui.py` — that suite intentionally models session dictionaries rather than mocking `st` (see gaps below).

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**

| Fixture | Lines | Purpose |
|---|---|---|
| `fake_env_groq_key` | 19-22 | `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")` |
| `mock_groq_client` | 25-59 | `MagicMock` Groq client whose `chat.completions.create` yields 5 token chunks; monkeypatches `groq_provider.Groq` |
| `mock_sentence_transformer` | 62-92 | Deterministic 384-dim normalized embeddings; monkeypatches `local_embedding.SentenceTransformer` |
| `sample_pdf_path` | 95-99 | Absolute path to `tests/data/corpus/clean_digital.pdf` |
| `mock_llama_provider` | 102-172 | Healthy `MockLlamaCppProvider(BaseModelProvider)` recording `stream_calls`, configurable token list/health |

**Module-local autouse fixtures:**
- `clean_session_state` — resets every `st.session_state` key before each UI test (`tests/test_ui_smoke.py:19-35`, `tests/test_hydration.py:12-20`). Add new session keys here when `main.py` gains them.
- `ensure_gate_released` — drains `InferenceGate` before and after each lock test (`tests/test_concurrency_lock.py:61-68`).

**Test data:**
- Synthetic PDF corpus is generated by `tests/data/corpus/generate_corpus.py` using ReportLab. CI runs it before pytest (`.github/workflows/ci.yml`), so tests can assume the six PDFs exist.
- DB fixtures are created per-test with `tmp_path`: `DocStore(tmp_path / "test.db")`, `HybridRetriever(db_uri=tmp_path / "lancedb_test")`.
- Deterministic vectors via `_make_unit_vector(seed)`; many tests pass explicit embeddings to `index_chunks` so no model is loaded.
- Fake secrets are deliberately non-secret-looking values (`"test-key-not-a-secret-mock-value"`, `"gsk_secret"`). Keep this convention; never use a realistic key.

**Location:** No factory library; helper functions live at the top of the suite that needs them (`_make_unit_vector`, `handler` functions, `DummyProvider`). Move a helper to `tests/conftest.py` only when two or more suites need it.

## Coverage

**Requirements:** None enforced. There is no `pytest-cov` dependency, no `[tool.coverage]` section, no `.coveragerc`, no coverage step in `.github/workflows/ci.yml`, and no coverage badge.

**View Coverage:**
```bash
pytest --cov=. --cov-report=term-missing   # not currently installed; add pytest-cov first
```

`docs/EVALUATION.md` reports qualitative gate metrics (pass rate, offline isolation, lint cleanliness) but not line/branch coverage. Treat coverage claims as qualitative until a coverage tool is added.

## Test Types

**Unit tests (majority):**
- Pure logic and schema validation: `tests/test_models.py`, `tests/test_vector_index.py`, `tests/test_prompt_budget.py`, `tests/test_citation_validator.py`, `tests/test_upload_validation.py`, `tests/test_sanitizer.py`, `tests/test_logging_setup.py`.
- Provider behavior via mocked transports/fakes: `tests/test_groq_provider.py`, `tests/test_llama_cpp_provider.py` (`httpx.MockTransport`), `tests/test_litellm_provider.py`, `tests/test_model_provider.py`.
- Concurrency and lifecycle: `tests/test_concurrency_lock.py`, `tests/test_hybrid_retriever.py:380-414` (context manager/`close()`).

**Integration-style tests (real SQLite/LanceDB, `tmp_path`):**
- `tests/test_doc_store.py` (schema, migrations, cascade delete, summaries), `tests/test_hybrid_retriever.py` (persistence across re-instantiation, RRF, FTS fallback, SQL-injection escaping), `tests/test_cache_invalidation.py`, `tests/test_cloud_privacy.py` (end-to-end local-only invariant with socket guard).

**Regression / contract tests:**
- `tests/test_main_ui.py` verifies session-state schemas, evidence card formatting, provider attribute names, Clear All purges, cache version keys, and `IngestionService` failure reporting.
- `tests/test_ui_smoke.py` verifies local SVG assets, status pills, citation chips, sanitizer behavior, uploader-key increment, hydration, deletion, and stale-summary invalidation.
- `tests/test_hydration.py` verifies startup restoration.

**End-to-end / browser tests:** Not present. No Playwright/Selenium/Streamlit AppTest. Streamlit views are tested through their extracted data contracts and helpers, not by rendering the app.

## Common Patterns

**Generator / streaming assertions:**
```python
chunks = list(provider.stream_text("hello"))
assert "".join(chunks) == "This is a grounded answer."
```
Provider mocks build chunk objects with `delta.content` (`tests/conftest.py:33-50`) or use `MagicMock(choices=[MagicMock(delta=MagicMock(content="Hello "))])` (`tests/test_groq_provider.py:64-69`).

**Error testing:**
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    unconsented_cloud.generate_text("Test prompt")
```
(`tests/test_cloud_privacy.py:34`)

Also used for validation (`ValidationError`, `ValueError`), provider errors (`RuntimeError` with model context), and lock timeouts (`TimeoutError`, `tests/test_concurrency_lock.py:159`). Always include `match=` so the assertion covers the message contract, not just the type.

**Persistence/lifecycle testing:**
```python
with HybridRetriever(db_uri=tmp_path / "lifecycle_db") as retriever:
    retriever.set_embedding_fn(lambda text: dummy_vec)
assert retriever._db is None
assert retriever._table is None
```
(`tests/test_hybrid_retriever.py:380-393`)

**Isolation cleanup:** tests that mutate module globals restore them in `finally`; tests that use process locks drain them via autouse fixture. Follow both patterns for any new global state.

**Async testing:** Not used — the codebase is synchronous. Do not introduce `asyncio` tests without adding a runner.

## Gaps and Fragility

**UI tests do not render the UI.** `tests/test_main_ui.py` re-implements formatting and purge logic inline (e.g. `chip_labels = [f"[E{s['rank']}] ..."]`, `tests/test_main_ui.py:72-79`) and simulates session resets with plain dicts (`tests/test_main_ui.py:142-191`). These tests can pass while the real `ui/views.py` code drifts. New UI behavior should call the actual helper from `ui/views.py`/`ui/components.py` (extract a pure function if needed) rather than duplicating its expression.

**Importing `main` executes Streamlit calls.** `tests/test_ui_smoke.py:109` imports `_reset_session_security_state` from `main`, which runs `st.set_page_config` and theme injection at module import. Works under pytest's bare-mode Streamlit but is fragile; prefer moving reusable reset logic into a non-Streamlit module.

**No coverage measurement.** Untested areas can regress silently; `pytest-cov` is not in `requirements-test.txt`.

**Stale documentation counts.** README/EVALUATION claim 248 tests across 24 suites; collection reports 289 across 29 modules (`tests/test_main_ui.py`, `tests/test_ui_smoke.py`, `tests/test_sanitizer.py`, `tests/test_logging_setup.py`, `tests/test_hydration.py` are the newer additions). Update both docs when counts change.

**No markers or sharding.** All tests run in one process with no `slow`/`integration` markers and no `-n auto`; the hybrid-retriever and OCR suites touch real LanceDB/SQLite and dominate runtime.

**Slow collection.** `pytest --collect-only -q` takes ~50 seconds because importing test modules pulls in torch/sentence-transformers/streamlit. Keep heavy imports inside test functions or fixtures when adding new suites.

**Private-attribute assertions.** Several tests assert on internals (`retriever._fallback_store.documents[0]`, `retriever._db`, `retriever._table`, `tests/test_hybrid_retriever.py:374,391-392`). Renaming private state will break tests; prefer a public accessor for new behavior.

---

*Testing analysis: 2026-10-20*
