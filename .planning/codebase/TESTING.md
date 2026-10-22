<!-- refreshed: 2026-10-21 -->
# Testing Patterns

**Analysis Date:** 2026-10-21

## Test Framework

**Runner:**
- `pytest` (`>=8.3.0` in `requirements-test.txt`; local environment runs `pytest 9.0.3`).
- Config: `pyproject.toml` → `[tool.pytest.ini_options]`.

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

- No `addopts`, no custom markers, no pytest plugins (`pytest-asyncio`, `pytest-mock`, `pytest-cov` are **not** installed). Mocking uses stdlib `unittest.mock` plus pytest's built-in `monkeypatch`.
- Root conftest: `tests/conftest.py`. Package marker: `tests/__init__.py`.
- CI: `.github/workflows/ci.yml` runs on Ubuntu with Python 3.11, installs `requirements-lock.txt` + `requirements-test.txt` + editable package via `uv`, generates the corpus, then runs `pytest tests/ -v`. Local analysis ran Python 3.13.5; the target/runtime is 3.11+.

**Assertion Library:**
- Plain `assert` statements. No `unittest.TestCase`, no third-party assertion helpers.
- `pytest.raises(..., match="...")` for exceptions, `pytest.approx` for floats, `capsys` for CLI output, `MagicMock.assert_called_once_with` / `assert_called_once` for call assertions.

**Run Commands:**
```bash
python tests/data/corpus/generate_corpus.py   # required once; CI runs this before pytest
python -m pytest tests/ -v                    # full suite (392 tests)
python -m pytest tests/ -q                    # concise
python -m pytest tests/test_doc_store.py -v   # single module
python -m pytest tests/ -k "inference_gate"   # single behavior group
ruff check . && ruff format --check .         # lint/format gate
```

- Current result: `392 passed in 39.59s` with no failures, warnings, or skips on a machine with local GGUF weights and cached embedding model.

## Test File Organization

**Location:**
- Separate `tests/` tree at the repo root; tests are **not** co-located with source.
- 32 `test_*.py` modules, 392 test functions, plus `tests/conftest.py` and `tests/__init__.py`.
- `tests/test_audit_repairs.py` is a cross-cutting regression suite for audit fixes; feature suites otherwise map 1:1 to a source module or area.

**Naming:**
- Files: `tests/test_<module_or_feature>.py` (e.g. `test_hybrid_retriever.py`, `test_llama_cpp_provider.py`, `test_main_ui.py`, `test_ui_smoke.py`).
- Functions: `test_<behavior>_<condition>` (`test_inference_gate_reentrancy_in_same_thread`, `test_sha_unique_violation_on_reupload`, `test_health_check_loading_503`, `test_visual_element_detection_and_cropping`).
- Requirement/audit tags frequently appear in the docstring and occasionally in the name: `test_two_instance_interleave_R1`, `test_corrupt_invalid_rejected_WR07`; docstrings carry `(QUAL-01)`, `(RETR-04)`, `(INF-03)`, `(P0-1)`.
- Test classes are **not** used to group tests. Classes in test files are fakes/mocks (`DummyProvider`, `MockVisionProvider`, `MockSummarizerProvider`) or fixtures (`_FailingTable`).

**Structure:**
```text
tests/
├── __init__.py
├── conftest.py                     # shared fixtures + offline env setup
├── data/
│   └── corpus/
│       ├── generate_corpus.py      # reportlab generator (run before pytest)
│       ├── clean_digital.pdf
│       ├── scanned_sample.pdf
│       ├── dense_table.pdf
│       ├── multi_column.pdf
│       ├── chart_diagram.pdf
│       └── corrupt_invalid.pdf
├── test_<area>.py                  # 30 modules
└── test_audit_repairs.py           # cross-cutting regressions
```

**Largest suites (by test count):**

| Tests | Module |
|------:|--------|
| 20 | `tests/test_models.py` |
| 20 | `tests/test_hybrid_retriever.py` |
| 17 | `tests/test_llama_cpp_provider.py` |
| 17 | `tests/test_doc_store.py` |
| 16 | `tests/test_main_ui.py` |
| 14 | `tests/test_resource_telemetry.py` |
| 14 | `tests/test_local_llm.py` |
| 13 | `tests/test_ocr_fallback.py`, `tests/test_citation_validator.py`, `tests/test_audit_repairs.py` |

## Test Structure

**Suite Organization:**
- Module docstring states the unit under test and requirement IDs, then imports, then fixtures, then flat test functions.

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


def test_inference_gate_reentrancy_in_same_thread() -> None:
    """Test reentrancy: same thread can acquire multiple times without deadlocking."""
    with InferenceGate.hold(timeout=1.0):
        assert InferenceGate.is_locked()
        with InferenceGate.hold(timeout=1.0):
            assert InferenceGate.is_locked()
        assert InferenceGate.is_locked()
    assert not InferenceGate.is_locked()
```

**Patterns:**
- **Setup:** fixtures (module-level for specialized fakes, `tests/conftest.py` for shared ones); `autouse=True` only for global-state reset.
- **Teardown:** `yield` fixtures; explicit release loops for `InferenceGate`; `st.session_state.clear()` for Streamlit; `clear_latency_history()` / `clear_gpu_cache()` for telemetry.
- **Arrange/Act/Assert:** often labeled with numbered comments in workflow tests:

```python
# 1. Start in local mode
model = AiModel(cloud_mode=False)
assert model.provider.get_capabilities().is_local is True

# 2. Attempting cloud provider without consent raises PermissionError
...
```

- **Assertion style:** one behavior per test, multiple focused asserts on the same output. Compare canonical models directly (`assert retrieved == doc`), inspect serialized dicts for UI contracts (`turn["snippets"][0]["rank"] == 1`), and assert on error message fragments with `match=`.
- **Return annotations:** `-> None` is used in newer suites (137 of 318 tests); older suites omit it (`tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`). New tests should include `-> None`.
- **Test docstrings:** every test has a one-line docstring describing the invariant, often with requirement tags. Keep this convention.

## Mocking

**Framework:** stdlib `unittest.mock` (`MagicMock`, `patch`) + pytest `monkeypatch`. Usage counts: 75 `monkeypatch` references, 48 `with patch(...)` blocks.

**Patterns:**

1. **Contract-faithful fake providers (preferred).** Shared `mock_llama_provider` subclasses the real ABC so interface drift fails loudly:

```python
@pytest.fixture
def mock_llama_provider():
    """Provides a healthy mock local inference provider conforming to BaseModelProvider."""
    from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities

    class MockLlamaCppProvider(BaseModelProvider):
        def check_health(self) -> HealthStatus:
            return HealthStatus(status="healthy", message="Mock llama-server ready.", latency_ms=1.5)

        def stream_text(self, prompt, system_prompt=None, history=None, max_tokens=1024, temperature=0.2):
            self.stream_calls.append({...})
            for token in self._tokens:
                yield token
    return MockLlamaCppProvider()
```

2. **HTTP transports instead of a live server.** `providers/llama_cpp_provider.py` accepts an `httpx` transport, so tests exercise request/response handling with `httpx.MockTransport`:

```python
def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/health"
    return httpx.Response(503, json={"status": "loading model"})

transport = httpx.MockTransport(handler)
provider = LlamaCppProvider(transport=transport)
status = provider.check_health()
assert status.status == "loading"
```

3. **Monkeypatch module attributes for optional backends and network guards:**

```python
monkeypatch.setattr("retrieval.hybrid_retriever.lancedb", None)  # exercise in-memory fallback

def guarded_create_connection(*args, **kwargs):
    raise ConnectionRefusedError("Outbound network egress strictly forbidden ...")

monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
```

4. **MagicMock for third-party model clients** whose surface is large and irrelevant: `sentence_transformers.SentenceTransformer` (`tests/conftest.py::mock_sentence_transformer` returns deterministic 384-dim normalized vectors), `litellm.completion` (`tests/test_litellm_provider.py`), `groq.Groq` (`tests/conftest.py::mock_groq_client`).
5. **`patch("subprocess.run")` for OS-level probes**: `nvidia-smi` in `tests/test_resource_telemetry.py` and `tests/test_setup_llama.py`; Streamlit launch/llama-server process spawn in `tests/test_start_launcher.py`.

**What to Mock:**
- Network egress (cloud APIs, llama-server HTTP), GPU/nvidia-smi, model weight loading, and OS process spawning.
- Heavy optional parsers when the test targets orchestration rather than parsing quality: Docling `DocumentConverter` is mocked (`tests/test_docling_reader.py`), and OCR recognizer/renderer are `MagicMock`s (`tests/test_ocr_fallback.py`); the fallback `PdfReader` path runs for real.
- Time/latency-sensitive provider calls where the test asserts timeout behavior (`monkeypatch.setattr(InferenceGate, "acquire", MagicMock(return_value=False))`).

**What NOT to Mock:**
- SQLite (`sqlite3` + `DocStore`), LanceDB persistence, PyMuPDF rasterization, pypdf parsing, Pydantic validation, sanitizer regexes, and prompt-budget math. These run against real implementations so contract drift and schema/SQL bugs surface.
- Use `tmp_path` for any on-disk store; never write to the repo's `data/` or `.cache/`.
- Prefer a hand-written fake subclassing `BaseModelProvider` over `MagicMock` when the test depends on provider semantics (health status, capabilities, streaming order).
- **Do not copy the stale `HealthStatus(..., provider_type="local")` construction** found in `tests/test_concurrency_lock.py:20`, `tests/test_main_ui.py:229`, and `tests/test_summarizer.py:24`. `HealthStatus` is `extra="forbid"` and has no `provider_type` field, so those `check_health()` methods would raise if invoked. Build statuses with `status`, `message`, and optional `latency_ms` only.

## Fixtures and Factories

**Test Data:**
- Synthetic PDF corpus generated by `tests/data/corpus/generate_corpus.py` (reportlab) — six deterministic documents covering digital text, scanned pages, tables, multi-column layout, figures/charts, and an invalid file. CI regenerates it before pytest.
- Canonical models are constructed directly with valid IDs and 64-char hashes:

```python
sha = "1" * 64
doc = Document(
    doc_id="doc_1111111111111111",
    filename="test_doc.pdf",
    sha256=sha,
    size_bytes=4096,
    num_pages=3,
    status="indexed",
    upload_time="2026-10-11T01:00:00Z",
    num_chunks=6,
)
```

- Deterministic embeddings/vectors instead of randomness: `mock_sentence_transformer` derives values from text length; `_make_unit_vector(seed)` in `tests/test_hybrid_retriever.py` seeds NumPy and L2-normalizes.

**Location:**
- Shared fixtures: `tests/conftest.py`.

| Fixture | Purpose |
|---------|---------|
| `fake_env_groq_key` | Sets a mock `GROQ_API_KEY` via `monkeypatch.setenv`. |
| `mock_groq_client` | Replaces `providers.groq_provider.Groq` with a streaming mock yielding five tokens. |
| `mock_sentence_transformer` | Replaces `SentenceTransformer` with deterministic 384-dim normalized vectors; prevents model download/GPU use. |
| `sample_pdf_path` | Absolute path to `tests/data/corpus/clean_digital.pdf`. |
| `mock_llama_provider` | Healthy local provider fake subclassing `BaseModelProvider`, recording stream calls. |

- Module-local autouse resets: `ensure_gate_released` (`tests/test_concurrency_lock.py`), `clean_session_state` (`tests/test_ui_smoke.py`), `reset_latencies` (`tests/test_resource_telemetry.py`), hydration reset (`tests/test_hydration.py`).
- `tmp_path` is the dominant isolation mechanism (141 uses) for SQLite files, LanceDB directories, and cache roots. Older tests use `tempfile.TemporaryDirectory()` (`tests/test_cache_invalidation.py`); prefer `tmp_path`.
- Lightweight factories are plain module-level helpers: `_doc()` (`tests/test_audit_repairs.py`), `_make_unit_vector()` (`tests/test_hybrid_retriever.py`), `MockVisionProvider` / `MockTextOnlyProvider` (`tests/test_visual_analyzer.py`).

**Environment setup (critical):**
- `tests/conftest.py` sets `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` **before** importing NumPy/pytest. `retrieval/local_embedding.py` repeats the same guard. Keep environment mutation at the top of conftest; moving it below imports reintroduces TensorFlow/Keras noise.

**Corpus and model prerequisites:**
- Several tests assert corpus files exist and would fail rather than skip if the corpus is missing (`tests/test_pdf_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`). Always run the generator first.
- `tests/test_cloud_privacy.py` and `tests/test_doc_store.py` instantiate the real CPU `LocalEmbedding` (SentenceTransformer `all-MiniLM-L6-v2`), so a cached embedding model is required; most other embedding tests use `mock_sentence_transformer`.
- `tests/test_audit_repairs.py::test_local_model_identity_matches_declared_architecture` is skipped unless `models/qwen3-vl-2b-instruct-q4_k_m.gguf` and `models/mmproj-f16.gguf` exist. This is the only `skipif` in the suite.

## Coverage

**Requirements:** None enforced.
- No `pytest-cov` / `coverage` dependency in `requirements-test.txt` or `pyproject.toml`.
- No `--cov`, `fail_under`, coverage config, or CI coverage upload. CI gates only on lint/format and test pass/fail.
- `README.md` advertises "318 tests" and `docs/EVALUATION.md` reports "24 test suites"; the current tree has 30 test modules / 318 tests. Treat the docs as stale when counting.

**View Coverage:**
```bash
# Not configured in this repo. To inspect locally:
pip install pytest-cov
python -m pytest tests/ --cov=core --cov=retrieval --cov=ingestion --cov=providers --cov=ui
```

**Known coverage gaps:**
- **Streamlit view rendering.** No test imports or calls `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, or `render_sidebar_documents` (`ui/views.py`, ~880 lines). Tests cover data contracts (`tests/test_main_ui.py`), components, sanitizer, hydration, and session reset instead. There is no `streamlit.testing.v1.AppTest` usage.
- **Live local inference.** No test starts `llama-server` or loads the GGUF; `LlamaCppProvider` is verified through `httpx.MockTransport`. GGUF metadata parsing is checked only when model files are present, otherwise skipped.
- **GPU/VRAM behavior.** `nvidia-smi` and `psutil` telemetry are tested with mocked `subprocess.run`; the 4 GB envelope and `InferenceGate` are validated logically, not under real VRAM pressure.
- **Cloud providers.** No live Groq/OpenAI/Anthropic calls; consent gates and request shaping are tested with mocks.
- **Launcher/setup side effects.** `start.py` process spawning and `setup.py` downloads/archive extraction are mocked; no real download, extraction, or server boot is exercised.
- **End-to-end ingestion.** `IngestionService` is tested for failure/atomicity paths, but there is no full ingest → embed → LanceDB → retrieve → answer test with the real Docling pipeline.
- **Platform matrix.** CI is Ubuntu-only; Windows-primary behaviors (SQLite WAL file locking, path handling) are not covered in CI.
- **Static/security checks.** No mypy/pyright, no `pip-audit`/`bandit`, no secret scanning in CI.

## Test Types

**Unit Tests:**
- Majority of the suite. Pure functions and classes tested directly: `core/citation_validator.py`, `core/prompt_budget.py`, `core/models.py`, `ui/sanitizer.py`, `retrieval/vector_index.py`, `providers/*`, `setup.py`, `start.py`.
- Global-state components are tested concurrently with real threads (`tests/test_concurrency_lock.py`) and with autouse state resets.

**Integration Tests:**
- Offline integration-style tests run real storage/parsing components against `tmp_path` and the synthetic corpus: SQLite `DocStore` (migrations, WAL, integrity errors), LanceDB `HybridRetriever` (dense search, FTS/RRF, persistence, deletion, fallback), PyMuPDF cropping, pypdf/Docling fallback, and Pydantic round-trips.
- External boundaries (HTTP, cloud SDKs, GPU probes, optional model converters) are mocked, so these are "integration within the process," not system integration.

**E2E Tests:**
- Not used. No browser automation, no Streamlit `AppTest`, no live llama-server/Streamlit pair.

## Common Patterns

**Async Testing:**
- Not applicable — the codebase is synchronous. Concurrency is tested with `threading.Thread` + `threading.Event`, acquiring the gate with a short timeout and asserting the second acquire fails:

```python
def t1_worker() -> None:
    with InferenceGate.hold(timeout=2.0):
        t1_started.set()
        t1_finish.wait(timeout=2.0)

def t2_worker() -> None:
    t1_started.wait(timeout=2.0)
    acquired = InferenceGate.acquire(timeout=0.05)
    acquired_by_t2.append(acquired)

...
assert acquired_by_t2 == [False], "Thread 2 should have timed out while Thread 1 held the gate"
```

**Streaming Testing:**
- Consume the generator fully and assert on the token list / provider call record:
  `tokens = list(model.ask_a_question_from_pdf_stream(...))`; `assert len(mock_llama_provider.stream_calls) == 1`.

**Error Testing:**
- Assert exception type plus an actionable message fragment (`match=`), and verify state afterward:

```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    provider.generate_text("Explain quantum computing")

with pytest.raises(TimeoutError, match="InferenceGate acquisition timed out"):
    with InferenceGate.hold(timeout=0.05):
        pass

with pytest.raises(sqlite3.IntegrityError):
    store.upsert_document(doc2)  # same sha256, different doc_id
```

- Validation tests enumerate invalid inputs (bad magic bytes, oversized files, bad SHA, `doc_` prefix, negative bbox) and assert `pydantic.ValidationError` / `ValueError`.
- Fault-isolation tests inject a per-item failure (e.g. renderer raises on page 2) and assert other pages still succeed.

**Fault injection:**
- Failure seams are constructor-injected (`converter=`, `transport=`, `recognizer=`, `renderer=`, `provider=`) or patched at module scope. Use these instead of patching private internals.
- Filesystem failure paths are simulated with `monkeypatch.setattr` on the collaborator (e.g. force `VectorIndexError` and assert SQLite rows survive).

**Determinism and isolation checklist for new tests:**
- Use `tmp_path` for every DB/index/cache path; never touch `data/` or `.cache/`.
- Reset process-global state (`InferenceGate`, `st.session_state`, telemetry caches) with an autouse fixture.
- Use fixed hashes (`"a" * 64`), fixed timestamps, and seeded vectors.
- Mock only the external boundary; keep real SQLite/LanceDB/Pydantic in the loop.
- Add `-> None` and a requirement-tagged one-line docstring.
- Run `ruff check .`, `ruff format .`, then `python -m pytest tests/ -q` before committing.

---

*Testing analysis: 2026-10-21*
