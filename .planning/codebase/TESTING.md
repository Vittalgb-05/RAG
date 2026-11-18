---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# Testing Patterns

**Analysis Date:** 2026-11-14

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt`); local interpreter ran pytest `9.0.2`.
- Config in `pyproject.toml:21`:
  ```toml
  [tool.pytest.ini_options]
  testpaths = ["tests"]
  python_files = ["test_*.py"]
  python_functions = ["test_*"]
  filterwarnings = [
      "ignore:table_names\\(\\) is deprecated.*:DeprecationWarning",
      "ignore:create_fts_index is deprecated.*:DeprecationWarning",
      "ignore:Direct unindexed PDF ingestion.*:DeprecationWarning",
  ]
  ```
  The warning filters are intentionally message-scoped. `tests/test_packaging.py::test_pytest_warning_filters_are_targeted` fails the build if someone adds a blanket `ignore::UserWarning` / `ignore::DeprecationWarning`.

**Assertion Library:**
- Plain `assert` with pytest introspection. `pytest.raises(..., match="...")` for error paths.

**Async support:**
- `pytest-asyncio` is used via `@pytest.mark.asyncio` in `tests/test_stream_bridge.py` (local version 1.3.0).
- It is **not** declared in `requirements-test.txt`, and no `asyncio_mode` is configured, so async tests rely on strict-mode marker handling and a preinstalled plugin. Add `pytest-asyncio>=0.24` to `requirements-test.txt` before relying on async tests in a fresh environment.

**Run Commands:**
```bash
# Full suite (what CI runs)
pytest tests/ -v

# One module while iterating
python -m pytest tests/test_hybrid_retriever.py -q --no-header

# Collection sanity check
python -m pytest --collect-only -q

# Lint / format gates that accompany the tests
ruff check .
ruff format --check .

# Regenerate synthetic PDF corpus (CI does this before pytest)
python tests/data/corpus/generate_corpus.py

# Verify the checked-in OpenAPI artifact
python -m api.export_openapi --check
```

**Current size:** 485 tests collected on 2026-11-14 across 43 modules in `tests/` (`pytest --collect-only -q`). Numbers in `README.md`, `CLAUDE.md`, and `docs/TEST_RESULTS.md` (296 / 318 / 389 / 479) are historical and stale.

**No tooling for:** coverage (`pytest-cov` absent, no `.coveragerc`), parallel execution (`pytest-xdist` absent), markers registry, coverage thresholds, or a Python type checker.

## Test File Organization

**Location:**
- All Python tests are flat under `tests/` — there are no per-package `tests/` directories.
- Shared fixtures and environment pins live in `tests/conftest.py`.
- Synthetic fixtures are binary PDFs in `tests/data/corpus/` with their generator `tests/data/corpus/generate_corpus.py` (reportlab).

**Naming:**
- Files: `test_<module_or_feature>.py` matching the production module or the contract under test (`test_doc_store.py`, `test_upload_validation.py`, `test_openapi_contract.py`, `test_grounding_contract.py`).
- Functions: `test_<behavior>_<condition>`; audit/issue-regression tests may append an id (`test_corrupt_invalid_rejected_WR07`, `test_two_instance_interleave_R1`, `test_local_embedding_cpu_pinning`).

**Structure:**
```text
tests/
├── conftest.py                     # 5 shared fixtures + TF/Torch env pins
├── test_*.py                       # 43 modules, 485 tests
└── data/corpus/
    ├── generate_corpus.py          # reportlab generator (CI runs this)
    ├── clean_digital.pdf           # 20-page digital text
    ├── scanned_sample.pdf          # OCR fallback input
    ├── dense_table.pdf
    ├── chart_diagram.pdf
    ├── multi_column.pdf
    └── corrupt_invalid.pdf
```

**Module header style — two variants are in use:**
```python
"""Unit tests for HybridRetriever persistent vector storage and CPU embedding pipeline (RETR-01, RETR-02)."""
```
```python
# ------------------------------------------------------------------
# Unit Tests for DocStore (doc_store.py)
# Verifies SQLite persistence, WAL mode, migrations, UNIQUE(sha256)
# constraint handling, page failure tracking, and chunk storage.
# ------------------------------------------------------------------
```
Use the single-docstring style for new files; it is the majority in `api/` and contract suites.

## Test Structure

**Plain functions, no test classes.** There are zero `unittest.TestCase` subclasses. Grouping is done with section comments inside a module.

**Suite organization (representative):**
```python
"""Integration tests for document summarization endpoints and cache invalidation."""

from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.deps import get_container
from core.models import Document, SummaryResult
from core.summarizer import compute_summary_model_version


@pytest.fixture
def client_with_summary_container(tmp_path):
    from api.config import Settings
    from api.container import AppContainer

    s = Settings(data_dir=tmp_path / "data", cache_dir=tmp_path / ".cache")
    container = AppContainer.build(s)

    mock_ai = MagicMock()
    mock_caps = MagicMock()
    mock_caps.is_local = True
    mock_caps.model_name = "local"
    mock_ai.get_capabilities.return_value = mock_caps
    container.ai_model = mock_ai

    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app, base_url="http://127.0.0.1")
    yield client, container
    app.dependency_overrides.clear()
    container.shutdown()
```

Tests then exercise the real router, real `DocStore`, and real SQLite under `tmp_path`, with only the AI model mocked (`tests/test_summaries_api.py`).

**Patterns:**
- Setup: constructor injection with `tmp_path` databases; no `setUp`/`tearDown` methods.
- Teardown: `yield` fixtures that clear `app.dependency_overrides` and call `container.shutdown()`; `autouse` fixtures for process-global state.
- Assertions: multiple focused single-line asserts with messages on the non-obvious ones (`assert res.status_code == 200, res.text`).
- Numbered flow comments label multi-step scenarios (`# 1. Create chat session`, `# 2. List sessions`, ... in `tests/test_chat_api_sse.py`).

**Global-state guards:**
```python
# tests/test_concurrency_lock.py
@pytest.fixture(autouse=True)
def ensure_gate_released() -> None:
    """Ensure InferenceGate is fully released before and after every test."""
    while InferenceGate.is_locked():
        InferenceGate.release()
    yield
    while InferenceGate.is_locked():
        InferenceGate.release()
```
```python
# tests/test_logging_setup.py
@pytest.fixture(autouse=True)
def _clean_application_logging():
    """Remove module-owned handlers after each test so tmp dirs are not reused."""
    yield
    reset_logging()
```

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `AsyncMock`, `patch`) plus pytest's `monkeypatch`.

**Patterns:**
- Patch the module symbol, not the library:
  ```python
  # tests/test_upload_validation.py
  class StubReader:
      def __init__(self, stream):
          self.pages = [None] * (MAX_PAGES + 1)

  import pypdf
  monkeypatch.setattr(pypdf, "PdfReader", StubReader)
  ```
- Restore manually when `monkeypatch` is not a fixture:
  ```python
  # tests/test_hybrid_retriever.py
  original_st = local_embedding.SentenceTransformer
  try:
      local_embedding.clear_shared_model_cache()
      local_embedding.SentenceTransformer = mock_st_class
      embedder = LocalEmbedding(model_name="all-MiniLM-L6-v2")
      assert embedder.device == "cpu"
  finally:
      local_embedding.clear_shared_model_cache()
      local_embedding.SentenceTransformer = original_st
  ```
- Replace providers with hand-written stubs implementing the real ABC — this catches interface drift, unlike `MagicMock`:
  ```python
  # tests/test_visual_analyzer.py
  class MockVisionProvider(BaseModelProvider):
      def check_health(self) -> HealthStatus:
          return HealthStatus(status="healthy", message="Mock vision ready.", latency_ms=1.0)
      def get_capabilities(self) -> ProviderCapabilities:
          return ProviderCapabilities(model_name=self._model_name, context_window=4096, ...)
      def analyze_image(self, image_bytes: bytes, prompt: str, max_tokens: int = 512) -> str:
          self.analyze_calls.append({"image_len": len(image_bytes), "prompt": prompt})
          return "Architecture flowchart showing Ingestion, Hybrid Search, and Local VLM processing stages."
  ```
- Shared canned mocks live in `tests/conftest.py`: `mock_groq_client`, `mock_sentence_transformer` (deterministic 384-d normalized vectors), `mock_llama_provider`.
- Egress is blocked by patching the socket layer, proving local-only behavior:
  ```python
  # tests/test_cloud_privacy.py
  def guarded_create_connection(*args, **kwargs):
      raise ConnectionRefusedError("Outbound network egress strictly forbidden during local ingestion (INF-03).")
  monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
  ```
- Fail-closed stubs raise `AssertionError` if a code path unexpectedly hits the network (`tests/test_setup_checksums.py`).
- Environment mutation always goes through `monkeypatch.setenv` (`fake_env_groq_key` in `tests/conftest.py`, `RAG_LOG_LEVEL` and `RAG_REQUIRE_CHECKSUMS` tests).

**What to Mock:**
- External processes and network clients: Groq client, LiteLLM, `SentenceTransformer`, HTTP calls to llama-server, `urlopen`.
- Model inference at the `AiModel` / provider boundary for API tests.
- GPU/telemetry (`psutil`, `nvidia-smi`) when asserting formatting rather than hardware.

**What NOT to Mock:**
- SQLite (`DocStore` runs against `tmp_path` files), LanceDB (`HybridRetriever` runs against `tmp_path/lancedb*`), Pydantic validation, citation parsing, redaction, sanitization, and prompt-budget logic. These are tested for real.
- Do not `patch("module.Thing")` by string when the test also needs the symbol's identity; use `monkeypatch.setattr(module, "Thing", ...)`.

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**
| Fixture | Purpose |
|---|---|
| `fake_env_groq_key` | sets a non-secret `GROQ_API_KEY` |
| `mock_groq_client` | streaming `chat.completions.create` chunks |
| `mock_sentence_transformer` | deterministic normalized embeddings, patches `retrieval.local_embedding` |
| `sample_pdf_path` | path to `tests/data/corpus/clean_digital.pdf` |
| `mock_llama_provider` | healthy `BaseModelProvider` implementation recording `stream_text` calls |

**Environment pins at import time (`tests/conftest.py:6`)** — keep these before importing ML libraries:
```python
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
```

**Local fixtures** are defined in the module that needs them: `client_with_mock_container` (`tests/test_chat_api_sse.py`), `client_with_summary_container` (`tests/test_summaries_api.py`), `question_retriever` (`tests/test_whole_document_extraction.py`).

**Test data factories:** plain module-level helpers, no `factory_boy`:
```python
# tests/test_citation_validator.py
def _make_retrieval_result(num_snippets: int = 3) -> RetrievalResult:
    snippets = [
        EvidenceSnippet(content=f"Content for snippet {i}", doc_id="doc_test", ...)
        for i in range(1, num_snippets + 1)
    ]
    return RetrievalResult(query="test query", snippets=snippets, total_candidates=num_snippets, search_mode="hybrid")
```
```python
# tests/test_audit_repairs.py
def _doc(doc_id: str = "doc_audit_1", sha: str = "a" * 64) -> Document:
    return Document(doc_id=doc_id, filename="audit.pdf", sha256=sha, size_bytes=1024,
                    num_pages=2, status="indexed", upload_time="2026-10-21T00:00:00Z", num_chunks=1)
```

**Repository-relative paths** are computed, never hardcoded:
```python
REPO_ROOT = Path(__file__).resolve().parents[1]          # tests/test_packaging.py
CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"  # tests/test_upload_validation.py
```

**Corpus generation:** `tests/data/corpus/generate_corpus.py` builds the six PDFs with reportlab. CI regenerates before pytest; the PDFs are also committed, so local runs do not require regeneration.

## Coverage

**Requirements:** None enforced. No coverage plugin, config, threshold, or CI reporting.
- `# pragma: no cover` appears twice in `tests/test_doc_store.py` on unreachable `yield` statements; it has no effect without a coverage tool.
- `docs/TEST_RESULTS.md` holds a manual per-suite table, but it predates the FastAPI migration and the current 485-test suite.

**View Coverage (not configured):**
```bash
# add pytest-cov first; there is no configured report today
python -m pytest tests/ --cov=api --cov=core --cov=ingestion --cov=providers --cov=retrieval --cov=services
```

## Test Types

**Unit tests (majority):**
- Pure functions and domain objects: `tests/test_models.py`, `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`, `tests/test_query_intent.py`, `tests/test_sanitizer.py`, `tests/test_redaction.py`.
- Storage with real SQLite/LanceDB in `tmp_path`: `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_audit_repairs.py`.

**API integration tests:**
- `starlette.testclient.TestClient` against the real `api.main:app`, with `app.dependency_overrides[get_container]` pointing at an `AppContainer.build(Settings(data_dir=tmp_path/...))`.
- Real routers, real SQLite, mocked AI model: `tests/test_chat_api_sse.py`, `tests/test_summaries_api.py`.
- SSE asserted by reading raw frames: `assert "text/event-stream" in stream_resp.headers["content-type"]`, `"event: token" in body` (`tests/test_chat_api_sse.py`).

**Contract / regression tests:**
- `tests/test_openapi_contract.py` asserts the full expected path+method matrix and that `openapi.json` matches `app.openapi()`.
- `tests/test_grounding_contract.py` pins anti-hallucination behavior and forbidden few-shot content.
- `tests/test_audit_repairs.py` is the regression ledger for audit fixes (index path, atomic ingestion, consent, sanitizer, cache versioning).
- `tests/test_packaging.py` asserts `.env.example`, `Dockerfile`, and pytest warning-filter policy.

**Concurrency tests:**
- Real threads against `InferenceGate`, with sleeps bounded to 0.01s inside dummy providers and an `autouse` unlock fixture (`tests/test_concurrency_lock.py`).
- SSE worker cancellation uses bounded polling (`for _ in range(30): await asyncio.sleep(0.05)`) instead of a fixed sleep (`tests/test_stream_bridge.py`).

**Async tests:**
```python
@pytest.mark.asyncio
async def test_sse_from_worker_success():
    def worker(emit, stop):
        emit("token", {"token": "A", "index": 0})
        emit("token", {"token": "B", "index": 1})
        emit("done", {"metrics": {"tokens": 2}})

    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)

    events = []
    async for frame in sse_from_worker(worker, req, on_error=lambda e: {"msg": str(e)}):
        events.append(frame)

    assert len(events) == 3
    assert "event: token" in events[0]
    assert '"token": "A"' in events[0]
    assert "event: done" in events[2]
```

**E2E / browser tests:** None. No Playwright, Cypress, or jsdom setup.

**Frontend tests:** None. `frontend/package.json` has no test script and no test runner is installed. The only frontend gates are:
```bash
cd frontend
pnpm typecheck   # tsc --noEmit
pnpm build       # Next static export (output: "export")
```
(`.github/workflows/ci.yml`, `frontend` job).

**Live inference / GPU tests:** Not automated. Tests run fully offline. One identity test is skip-guarded when model weights are absent:
```python
@pytest.mark.skipif(
    not (REPO_ROOT / "models" / "qwen3.5-2b-q4_k_m.gguf").exists(),
    reason="local GGUF artifacts are not installed",
)
def test_local_model_identity_matches_declared_architecture() -> None:
```
`docs/TEST_RESULTS.md` records the manual checks live tests cannot cover (real generation, VLM captions, VRAM peaks, OCR accuracy, restart persistence).

## Common Patterns

**Error testing:**
```python
with pytest.raises(ValueError, match="Not a valid PDF: missing %PDF header"):
    validate_pdf_bytes(raw_bytes, "corrupt_invalid.pdf")
```
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    unconsented_cloud.generate_text("Test prompt")
```
Match strings are asserted deliberately — keep messages stable or update the test with the message change.

**Filesystem isolation:**
- `tmp_path` appears in roughly 270 lines across the suite; every database, LanceDB directory, cache directory, and log directory is per-test.
- API tests pass `Settings(data_dir=tmp_path / "data", cache_dir=tmp_path / ".cache")`; never let a test touch the repo `data/` directory.

**Log/stdout assertions:**
```python
# tests/test_logging_setup.py
def test_doc_store_migration_is_logged_not_printed(tmp_path, capsys):
    DocStore(tmp_path / "migration_logging.db")
    captured = capsys.readouterr()
    assert "[DocStore]" not in captured.out
```
`capsys`/`caplog` are used in 54 places; `caplog` is preferred when asserting structured events, `capsys` when asserting that nothing was printed.

**Parametrization:** used sparingly (2 sites: `tests/test_runtime_info.py`, `tests/test_setup_checksums.py`). For table-driven value checks prefer a `for` loop with an assertion inside, matching the existing style in `tests/test_summarizer.py::test_all_five_summary_profiles`.

**Deterministic vectors:** build them with a seeded RNG or analytic construction instead of real embeddings:
```python
def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:
    np.random.seed(seed)
    v = np.random.randn(dim).astype(np.float32)
    return [float(x) for x in v / np.linalg.norm(v)]
```

**Subprocess / installer tests:** import `setup.py` as a module (`import setup as setup_mod`) and patch `setup_mod.urllib.request.urlopen`; do not execute installers (`tests/test_setup_checksums.py`). Symlink-dependent tests are guarded by `symlink_supported = pytest.mark.skipif(not _can_symlink(), ...)` (`tests/test_setup_llama.py`).

## CI Pipeline

`.github/workflows/ci.yml` (backend job, Python 3.11 on Ubuntu):
1. Install `requirements.txt`, `requirements-test.txt`, and `pip install -e . --no-deps`.
2. `ruff check .`
3. `ruff format --check .`
4. `python -m api.export_openapi --check`
5. `python tests/data/corpus/generate_corpus.py`
6. `pytest tests/ -v`

Frontend job: `pnpm install --frozen-lockfile`, `pnpm typecheck`, `pnpm build`.

To reproduce CI locally, run the same commands from the repo root. The suite requires the repo root on `sys.path` (editable install) because all imports are absolute (`from core.models import ...`) and `tests/test_openapi_contract.py` reads `openapi.json` relative to the current working directory.

## Known Testing Gaps

- **Frontend:** no unit, component, or E2E tests; regressions are caught only by `tsc` and the static build.
- **Async dependency:** `pytest.mark.asyncio` is used but `pytest-asyncio` is not pinned in `requirements-test.txt`.
- **No coverage gate:** large services (`core/doc_store.py`, `core/summarizer.py`, `services/chat_turn.py`) have behavior tests but no measured threshold.
- **No type checking:** no mypy/pyright in CI (`docs/CODE_QUALITY_REPORT.md` also flags this).
- **Live inference untested:** llama-server, VLM output, and VRAM ceilings are verified manually only.
- **Count drift:** README badge (479), README body (389/318), `CLAUDE.md` (296), `docs/TEST_RESULTS.md` (389) all disagree with the current 485 collected.

---

*Testing analysis: 2026-11-14*
