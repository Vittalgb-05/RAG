# Testing Patterns

**Analysis Date:** 2026-10-29

## Test Framework

**Runner:**
- `pytest >= 8.3.0` (`requirements-test.txt:2`).
- Configuration lives in `pyproject.toml:21-30` under `[tool.pytest.ini_options]`:
  - `testpaths = ["tests"]`
  - `python_files = ["test_*.py"]`
  - `python_functions = ["test_*"]`
  - Targeted `filterwarnings` for three known third-party deprecations (`table_names()`, `create_fts_index`, `Direct unindexed PDF ingestion`).
- There is no `pytest.ini`, `tox.ini`, or `setup.cfg`. `pyproject.toml` is the only pytest configuration.
- `tests/__init__.py` makes `tests` an importable package; `tests/conftest.py` is the shared fixture/mocking seam.
- `tests/conftest.py:6-11` sets `USE_TF=0`, `USE_TORCH=1`, and `TF_ENABLE_ONEDNN_OPTS=0` before importing application modules, forcing the PyTorch backend and suppressing TensorFlow/Keras integrations.
- Current inventory: **40 test modules** and **479 collected tests** (`python -m pytest tests --collect-only -q`, 2026-10-29). The count includes parametrized expansions. README and `docs/EVALUATION.md` contain stale counts (see “Coverage” below).

**Assertion Library:**
- Built-in `assert` statements (`~1,500` assertions across the suite).
- `pytest.raises(...)` for expected exceptions (`~80` occurrences).
- `pytest.mark.parametrize` is used sparingly: `tests/test_runtime_info.py:166`, `tests/test_setup_checksums.py:125`.
- `pytest.mark.skipif` is used once: `tests/test_audit_repairs.py:209` skips the local GGUF identity test when model artifacts are absent.
- No custom pytest markers are registered; no `pytest.mark.live`, `pytest.mark.integration`, or `pytest.mark.slow` exists.

**Run Commands:**
```bash
# Generate the synthetic PDF corpus first (CI does this before pytest)
python tests/data/corpus/generate_corpus.py

# Full suite
pytest tests/ -v

# Lint and format gates
ruff check .
ruff format --check .
```

CI (`.github/workflows/ci.yml`) runs on Python 3.11 with `uv`, installs `requirements-lock.txt`, `requirements-test.txt`, and `pip install -e . --no-deps`, then runs Ruff check, Ruff format check, corpus generation, and `pytest tests/ -v`.

## Test File Organization

**Location:**
- Flat `tests/` directory, one file per application module or feature area. No nested test packages beyond `tests/data/`.
- `tests/conftest.py` holds cross-cutting fixtures; module-specific fixtures live in the test file that needs them.
- `tests/data/corpus/` holds six synthetic PDFs plus `generate_corpus.py`; the PDFs are committed but regenerated in CI.
- `tests/__init__.py` is a one-line package marker.

**Naming:**
- `test_<module_or_feature>.py`: `test_doc_store.py`, `test_hybrid_retriever.py`, `test_citation_validator.py`, `test_prompt_budget.py`, `test_ui_smoke.py`, `test_ui_redesign_apptest.py`, `test_grounding_contract.py`.
- Test functions are descriptive behavior statements, commonly `test_<subject>_<condition>`:
  - `test_validate_citations_hallucinated_rank`
  - `test_hybrid_retriever_anchored_default_path`
  - `test_lifecycle_delete_aborts_before_sqlite_on_vector_failure`
  - `test_apptest_initial_shell_and_welcome_state`
  - `test_uncited_claims_prevent_a_full_grounding_verdict`
- Many older tests use a shorter behavior name (`test_extract_citations`, `test_is_abstention`, `test_status_pill_rendering`); the strict two-part pattern is common but not universal.
- Newer test modules annotate test functions with `-> None`; older modules often omit return annotations. Both styles pass Ruff.
- Helper functions are underscore-prefixed and descriptive: `_make_retrieval_result`, `_resume_retrieval`, `_multi_chunk_resume`, `_snippet`, `_result`, `_make_unit_vector`, `_indexed_document`.

**Structure:**
```text
tests/
├── __init__.py
├── conftest.py                  # shared fixtures and SDK mocks
├── test_*.py                    # 40 flat test modules
└── data/
    └── corpus/
        ├── generate_corpus.py   # reportlab synthetic PDF generator
        ├── clean_digital.pdf    # 20 pages, clear headings/paragraphs
        ├── multi_column.pdf     # 2-page two-column layout
        ├── dense_table.pdf      # structured financial table
        ├── scanned_sample.pdf   # raster-only, no extractable text
        ├── chart_diagram.pdf    # flowchart/diagram
        └── corrupt_invalid.pdf  # invalid magic bytes
```

The corpus generator creates deterministic PDFs for extraction, OCR, table, and diagram tests. `tests/test_docling_reader.py:11-13`, `tests/test_ocr_fallback.py:10-12`, and the `sample_pdf_path` fixture in `tests/conftest.py:95-99` depend on these files. CI regenerates them before running pytest.

## Test Structure

**Suite Organization:**
```python
"""Regression tests for the evidence-grounding contract.

These tests pin the failure that produced fabricated content across every
document ... and the summary/QA pipeline split that followed.
"""

from core.citation_validator import (
    auto_attribute_citations,
    extract_citations,
    should_withhold_answer,
    validate_citations,
)
from core.models import EvidenceSnippet, RetrievalResult


def _resume_retrieval() -> RetrievalResult:
    """Build a one-snippet retrieval result grounded in the resume excerpt."""
    return RetrievalResult(...)


def test_fabricated_sentence_is_not_auto_attributed() -> None:
    """A sentence sharing no real content with the evidence must stay uncited."""
    draft = "Sustainable development balances ecological protection and economic growth."
    attributed = auto_attribute_citations(draft, _resume_retrieval())
    assert extract_citations(attributed) == []
    assert attributed == draft
```

This is the preferred new-test shape: module docstring naming the regression, typed helpers, one behavior per test, a docstring stating the invariant, and focused assertions.

**Patterns:**
- **Module docstring first.** Newer suites start with a `"""..."""` that states what the file verifies and, for regressions, the exact failure being pinned (`tests/test_grounding_contract.py:1-6`, `tests/test_whole_document_extraction.py:1-9`, `tests/test_retrieval_semantic.py:1-11`, `tests/test_runtime_info.py:1`).
- **Banner comments** group sections in large legacy-style files: `tests/test_doc_store.py:1-5`, `tests/test_models.py:1-5`, `tests/test_local_embedding.py:1-4`, `tests/test_runtime_info.py:16-19`, `tests/test_retrieval_semantic.py:30-32`.
- **Deterministic helpers** build canonical models rather than raw dicts: `_make_retrieval_result` (`tests/test_citation_validator.py:14-33`), `_resume_retrieval` (`tests/test_grounding_contract.py:43-60`), `_snippet`/`_result` (`tests/test_chat_controller.py:12-40`).
- **`tmp_path` for isolated persistence.** SQLite databases and LanceDB directories always live under `tmp_path`: `DocStore(tmp_path / "test_docs.db")`, `HybridRetriever(db_uri=tmp_path / "lancedb_test")`. No test writes to the real `data/documents.db` or `data/lancedb/`.
- **Session-state isolation.** `tests/test_ui_smoke.py:27-43` and `tests/test_hydration.py:12-21` use an `autouse` fixture that clears and reinitializes `st.session_state` before each test. `tests/test_logging_setup.py:18-22`, `tests/test_concurrency_lock.py:61-68`, and `tests/test_resource_telemetry.py:25-32` use autouse teardown fixtures for global logging, gate, and telemetry state.
- **No test classes.** Tests are module-level functions; fakes are plain classes or subclasses of production abstractions.
- **Explicit contract assertions.** Tests assert exact labels, page numbers, citation tags, status strings, and Pydantic dump shapes rather than only truthiness: `assert turn["verification"]["precision"] == 1.0`, `assert "[E1] paper.pdf · p. 7" in direct_chip`, `assert result.grounding_status == "unsupported"`.

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `patch`) plus pytest's built-in `monkeypatch`. No `pytest-mock`, `responses`, `respx`, `vcrpy`, or `freezegun` dependency.

**Patterns:**
```python
# 1. Fake provider subclassing the production ABC
class DummyProvider(BaseModelProvider):
    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="ok")
    def generate_text(...) -> str:
        return "generated response"

# 2. Module-level SDK replacement via monkeypatch
monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name, **kwargs: mock_model)
monkeypatch.setattr(groq_provider, "Groq", lambda api_key=None: mock_client)

# 3. HTTP transport mock for llama-server
transport = httpx.MockTransport(handler)
provider = LlamaCppProvider(transport=transport)

# 4. AppTest with monkeypatched health/capabilities
monkeypatch.setattr(
    "core.local_llm.AiModel.check_health",
    lambda self: HealthStatus(status="healthy", message="All systems operational"),
)
at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "main.py"), default_timeout=45)
```

Observed mocking seams:
- **Inference providers:** `MockLlamaCppProvider` in `tests/conftest.py:102-171` subclasses `BaseModelProvider` and records `stream_calls`; it is consumed by `tests/test_local_llm.py`. `DummyProvider` in `tests/test_concurrency_lock.py:13-58` covers gate behavior.
- **Retrievers:** duck-typed fakes exposing only the methods under test: `FakeHybridRetriever` with `search_hybrid` (`tests/test_chat_controller.py:43-50`), `_Retriever`/`_DocumentRetriever`/`_CappedRetriever` in `tests/test_grounding_contract.py:250-260`, `:336-343`, `:375-383`, and `FailingRetriever` in `tests/test_audit_repairs.py:228-230`, `:246-248`.
- **Embeddings:** `mock_sentence_transformer` in `tests/conftest.py:62-92` returns deterministic 384-dimensional normalized float32 vectors; `test_retrieval_semantic.py` replaces `SentenceTransformer` and clears the shared cache in `finally` blocks.
- **Cloud SDKs:** `monkeypatch.setattr(litellm, "completion", mock_completion)` in `tests/test_litellm_provider.py`; `monkeypatch.setattr(groq_provider, "Groq", ...)` in `tests/conftest.py:52-57`.
- **HTTP:** `httpx.MockTransport` for `/health`, `/v1/chat/completions`, streaming, and malformed payload cases in `tests/test_llama_cpp_provider.py:30-100`.
- **Subprocess/hardware:** `patch("subprocess.run", ...)` for `nvidia-smi` and `llama-server --version`; `patch("psutil.Process", ...)` for RAM telemetry (`tests/test_resource_telemetry.py:35-115`, `tests/test_runtime_info.py:37-63`).
- **Network egress:** `monkeypatch.setattr(socket, "create_connection", guarded_create_connection)` in `tests/test_cloud_privacy.py:60-64` makes any outbound socket call fail during local ingestion/indexing/search.
- **Streamlit:** `AppTest` for the full app; `patch("streamlit.html")`/`patch("streamlit.markdown")` for isolated component markup (`tests/test_ui_redesign_apptest.py:236-244`); `monkeypatch.setattr(st, "session_state", fake_state, raising=False)` for session helpers (`tests/test_cloud_privacy.py:242-258`).

**What to Mock:**
- Network calls (llama-server, LiteLLM, Groq, HTTP transports).
- GPU/VRAM telemetry and `nvidia-smi`/`psutil` calls.
- SentenceTransformer model loading and embedding computation.
- Subprocess launches (`start.py`, `setup.py`, runtime version probing).
- Cloud consent/secrets and Streamlit session state where the real runtime is unavailable.
- Time/latency-sensitive caches when asserting call counts (e.g. `get_gpu_memory_info` TTL in `tests/test_resource_telemetry.py:50-69`).

**What NOT to Mock:**
- Pydantic validation and serialization; tests construct real `Document`, `Chunk`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`.
- Pure domain logic: citation extraction/validation, query intent, prompt budgeting, sanitization, RRF math, redaction.
- SQLite persistence: tests use real `DocStore` against `tmp_path`.
- LanceDB persistence: tests use real `HybridRetriever(db_uri=tmp_path / ...)` and real FTS/dense indexing, except when explicitly simulating backend failure.
- FastAPI/Streamlit-free service logic: `ChatTurnService` tests use real service instances with fake retrievers/validators.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def sample_pdf_path():
    """Returns the path to the synthetic clean_digital.pdf."""
    path = Path(__file__).resolve().parent / "data" / "corpus" / "clean_digital.pdf"
    return str(path)
```

Shared fixtures in `tests/conftest.py`:
- `fake_env_groq_key` — sets a mock `GROQ_API_KEY`.
- `mock_groq_client` — mocks `groq.Groq` and streams five canned tokens.
- `mock_sentence_transformer` — deterministic 384-dim embeddings.
- `sample_pdf_path` — path to `tests/data/corpus/clean_digital.pdf`.
- `mock_llama_provider` — healthy `BaseModelProvider` fake with canned tokens and call recording.

Local factories/helpers:
- `_make_retrieval_result` (`tests/test_citation_validator.py:14`).
- `_resume_retrieval` and `_multi_chunk_resume` (`tests/test_grounding_contract.py:43`, `:156`).
- `_snippet` and `_result` (`tests/test_chat_controller.py:12`, `:31`).
- `_make_unit_vector` (`tests/test_hybrid_retriever.py:15`, `tests/test_retrieval_semantic.py:35`).
- `_indexed_document` (`tests/test_hydration.py:60`).
- `QUESTION_PAGES` and `question_retriever` (`tests/test_whole_document_extraction.py:29-72`).

**Location:**
- Cross-cutting fixtures: `tests/conftest.py`.
- Module-specific fixtures: in the test module that owns them (`base_app` in `tests/test_ui_redesign_apptest.py:15`, `question_retriever` in `tests/test_whole_document_extraction.py:54`).
- Synthetic PDF corpus and generator: `tests/data/corpus/`.
- No factory-boy, Faker, hypothesis, or fixture JSON/YAML files.

## Coverage

**Requirements:** None enforced.

- No `pytest-cov` in `requirements-test.txt` or `requirements-lock.txt`.
- No `[tool.coverage]` section in `pyproject.toml`, no `.coveragerc`, no `--cov` in `.github/workflows/ci.yml`.
- CI does not publish coverage artifacts or enforce a threshold.
- The only coverage-adjacent annotations are targeted `# pragma: no cover` comments on defensive/UI-boundary branches (`ui/hydration.py:30`, `:79`; `main.py:184`, `:192`; `core/logging_setup.py:100`, `:142`). They document intent but are not evaluated.
- Test inventory is therefore the only quality gate. Actual count is 479 tests / 40 modules; `README.md` says “389 tests” (line 106) and “318 tests” (line 254), and `docs/EVALUATION.md` says “248 test cases / 24 test suites.” These are stale and should not be used as current metrics.

**View Coverage:**
```bash
# Not configured. To measure, install pytest-cov and run:
pytest tests/ --cov=core --cov=ui --cov=ingestion --cov=retrieval --cov=providers
```
There is no baseline to compare against; adding coverage would first require a configuration decision (which packages, branch vs. statement, threshold).

## Test Types

**Unit Tests:**
- The majority of the suite. Pure functions and single classes are tested in isolation with fakes: `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`, `tests/test_query_intent.py`, `tests/test_models.py`, `tests/test_sanitizer.py`, `tests/test_redaction.py`, `tests/test_chat_controller.py`.
- No GPU, network, or real model required for the core unit tests.

**Integration Tests:**
- **SQLite + LanceDB:** real `DocStore` on `tmp_path`, real `HybridRetriever` with temp LanceDB directories, real FTS/dense indexing and RRF fusion (`tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_retrieval_semantic.py`, `tests/test_whole_document_extraction.py`).
- **Ingestion pipeline:** real corpus PDFs through `DoclingReader`, `PdfReader`, OCR fallback, and `VisualAnalyzer` with mocked VLM providers (`tests/test_docling_reader.py`, `tests/test_pdf_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`).
- **Provider contracts:** `LlamaCppProvider` through `httpx.MockTransport`; `LiteLLMProvider`/`GroqProvider` with mocked SDK calls; `BaseModelProvider` capability/health schema tests (`tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py`, `tests/test_groq_provider.py`, `tests/test_model_provider.py`).
- **Storage/lifecycle:** deletion, purge, re-index, hydration, vector failure propagation, and tombstone behavior (`tests/test_hydration.py`, `tests/test_audit_repairs.py`, `tests/test_ui_smoke.py`).
- **UI:** `streamlit.testing.v1.AppTest` runs `main.py` as a script, navigates workspaces, clicks buttons, asserts session state, and checks rendered markdown (`tests/test_ui_redesign_apptest.py`). `tests/test_ui_smoke.py` is a session-state/component smoke suite, not an `AppTest` suite; it tests session reset, hydration, summary cache invalidation, sanitizer behavior, and credential scrubbing.

**E2E Tests:**
- No browser E2E framework (Playwright/Selenium) and no live `llama-server`/GPU E2E test in the default suite.
- `AppTest` is the closest to end-to-end: it executes the real Streamlit entry point with mocked model health/capabilities. It does not exercise real PDF upload through the browser, real token streaming from llama-server, or real VRAM behavior.

**Live vs Deterministic Boundaries:**
- **Default suite is deterministic and offline for the main paths.** Network, GPU, embeddings, and cloud SDKs are mocked; `tests/conftest.py` forces PyTorch and suppresses TensorFlow.
- **The only explicit live-artifact gate** is `tests/test_audit_repairs.py:209-221`: it skips the GGUF identity test unless `models/qwen3.5-2b-q4_k_m.gguf` exists. It does not run a model; it reads GGUF metadata.
- **No live-model test marker.** `grep` finds no `pytest.mark.live`, `pytest.mark.integration`, `pytest.mark.slow`, or live llama-server test. `tests/test_llama_cpp_provider.py` always uses `httpx.MockTransport`.
- **Live benchmarking is separate from pytest.** `scripts/benchmark_multimodal.py` defaults to `DeterministicBenchmarkProvider`; `--live` attempts a resident `llama-server` and falls back to the deterministic provider if health is not `healthy` (`scripts/benchmark_multimodal.py:145-156`, `:291-292`). `docs/EVALUATION.md` reports manual hardware measurements, not pytest assertions.
- **A few tests instantiate the real `LocalEmbedding`.** `tests/test_cloud_privacy.py:58` and `tests/test_doc_store.py:235` call `LocalEmbedding()` without the `mock_sentence_transformer` fixture. `tests/test_retrieval_semantic.py` explicitly mocks it. This means the “100% offline” claim in `docs/EVALUATION.md` is not absolute: those tests may download/cache `all-MiniLM-L6-v2` if the model is not already present.
- **No test asserts VRAM ceilings, latency SLAs, or throughput.** Those numbers in `docs/EVALUATION.md` are manual benchmark results, not regression tests.

## Common Patterns

**Async Testing:**
- No `async`/`await` tests. Provider streaming is a synchronous generator.
- Streaming assertions consume the generator explicitly:
  ```python
  chunks = list(provider.stream_text("prompt"))
  assert "".join(chunks) == "expected text"
  ```
- Concurrency is tested with real threads and events:
  ```python
  t1_started = threading.Event()
  t1_finish = threading.Event()
  t1 = threading.Thread(target=t1_worker)
  t2 = threading.Thread(target=t2_worker)
  ...
  assert not t2_started.wait(timeout=0.2)
  ```
  See `tests/test_concurrency_lock.py:102-160`. The autouse `ensure_gate_released` fixture drains `InferenceGate` before and after each test to prevent cross-test lock leakage.

**Error Testing:**
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    unconsented_cloud.generate_text("Test prompt")
```
- `pytest.raises(..., match=...)` is used for stable message fragments: `RuntimeError, match="Purge incomplete"` (`tests/test_audit_repairs.py:262`), `VectorIndexError, match="Failed to persist"` (`tests/test_audit_repairs.py:84`).
- Backend failures are simulated by raising inside a fake or monkeypatched callable, then asserting both the exception and the resulting state: e.g. vector failure leaves the SQLite row intact (`tests/test_audit_repairs.py:224-239`); purge failure still clears session state (`:242-265`).
- Empty/blank/edge inputs are tested explicitly: empty response validation (`tests/test_citation_validator.py`), blank snippets (`tests/test_grounding_contract.py:130-153`), invalid magic bytes (`tests/test_upload_validation.py`), corrupt PDF (`tests/data/corpus/corrupt_invalid.pdf`).

**Environment and Time:**
- `monkeypatch.setenv` for configuration: `GROQ_API_KEY`, `RAG_LOG_LEVEL`, `RAG_REQUIRE_CHECKSUMS`, `RAG_ALLOW_NON_LOOPBACK`, `LLAMA_SERVER_HOST`, `LLAMA_SERVER_PORT`.
- `monkeypatch.setattr` for module constants and clocks/backoff: `doc_store_module._WRITE_RETRY_BASE_DELAY = 0.0`, `_WRITE_RETRY_JITTER = 0.0` (`tests/test_doc_store.py:704-706`).
- Short real sleeps (10–20 ms) are used only in thread/telemetry tests; there is no fake clock dependency.

## Invariants Pinned by Tests

The suite is strongest where it pins a product invariant or a past regression:

- **Grounding and citation integrity** (`tests/test_grounding_contract.py`, `tests/test_citation_validator.py`, `tests/test_whole_document_extraction.py`):
  - System/summary prompts contain no contaminated few-shot examples.
  - Summary assembly uses `SUMMARY_SYSTEM_TEMPLATE`, not the QA template.
  - Fabricated sentences are not auto-attributed; supported sentences are.
  - Rank-valid but unsupported citations are `grounding_status == "unsupported"` and withheld.
  - `rank_only` citations are never presented as grounded.
  - Uncited claims prevent a full `grounded` verdict.
  - Current-location questions abstain when evidence names only an employer/school.
  - Whole-document questions bypass top-k and reach page-diverse extraction; truncation sets `incomplete_context`.
- **Retrieval correctness** (`tests/test_hybrid_retriever.py`, `tests/test_retrieval_semantic.py`):
  - Default LanceDB path is repo-anchored (`data/lancedb`), not CWD-relative.
  - RRF fuses dense-only and FTS-only candidates.
  - `EMBEDDING_MAX_LENGTH == 256` for `all-MiniLM-L6-v2`.
  - `get_embeddings` uses `convert_to_numpy=True` and normalized vectors.
  - Vector write failure raises `VectorIndexError` instead of silently reporting success.
- **Storage/lifecycle integrity** (`tests/test_doc_store.py`, `tests/test_audit_repairs.py`, `tests/test_hydration.py`, `tests/test_ui_smoke.py`):
  - SHA-256 uniqueness and upsert behavior.
  - WAL mode, migrations, busy retry/backoff, and transaction rollback.
  - Vector deletion failure aborts before SQLite mutation.
  - Purge reports tier failures and still clears session state.
  - Hydration restores the catalog and repairs missing vectors.
  - Summary cache invalidates on model-version mismatch.
- **Privacy and security** (`tests/test_cloud_privacy.py`, `tests/test_sanitizer.py`, `tests/test_redaction.py`, `tests/test_ui_smoke.py`):
  - Default mode is local-only; cloud requires explicit consent.
  - Unconsented cloud generation raises `PermissionError`.
  - Local ingestion/indexing/search performs no socket egress.
  - External links/images/scripts/iframes are neutralized in local mode and allowed with consent.
  - Credentials are scrubbed from errors and logs.
- **Concurrency/VRAM** (`tests/test_concurrency_lock.py`):
  - `InferenceGate` serializes inference, is reentrant for the owning thread, times out with `TimeoutError`, and cannot be released by a foreign thread.
- **Runtime/model identity** (`tests/test_runtime_info.py`, `tests/test_audit_repairs.py`):
  - llama-server version/build parsing, missing-binary handling, stale-install reporting.
  - GGUF metadata and LM/projector pair compatibility (skipped when artifacts are absent).
- **Packaging/quality gates** (`tests/test_packaging.py`):
  - `.env.example` documents recognized configuration without secrets.
  - Dockerfile installs from `requirements-lock.txt`, not `requirements.txt`.
  - Pytest warning filters are targeted, not global.

## Test Coverage Gaps

- **No coverage measurement or threshold.** There is no way to detect an untested module or a coverage regression in CI.
- **No live-model integration test.** No test exercises real token streaming, real VLM image analysis, real VRAM pressure, or real `llama-server` failure recovery. The closest is mocked `httpx` behavior.
- **No browser E2E.** `AppTest` covers the Streamlit script but not file upload widgets, real PDFs through the browser, or CSS/visual regressions.
- **OCR/Docling quality is not asserted against real scanned documents.** `tests/test_ocr_fallback.py` uses a synthetic raster-only PDF and mocked OCR engine paths; extraction quality/accuracy on real scans is untested.
- **Some tests instantiate the real embedding model.** `tests/test_cloud_privacy.py:58` and `tests/test_doc_store.py:235` can download `all-MiniLM-L6-v2`, contradicting the “fully offline” documentation claim and making CI dependent on model cache/network.
- **Performance and resource ceilings are manual.** No test asserts VRAM < 4 GB, ingestion < 10 s, or retrieval latency SLAs; those are in `docs/EVALUATION.md` only.
- **Multi-process concurrency is untested.** `InferenceGate` is process-local (`threading.RLock`); tests cover threads, not multiple processes or multiple browser sessions competing for one GPU.
- **UI render coverage is partial.** `tests/test_main_ui.py` and `tests/test_ui_smoke.py` assert data contracts and selected markup, but most `render_*` branches (settings, diagnostics, error states, upload progress) are not exhaustively exercised.
- **Documentation counts are stale.** README (389/318), `docs/EVALUATION.md` (248 tests / 24 suites), and the actual suite (479 tests / 40 modules) disagree; CI does not validate documentation counts.

---

*Testing analysis: 2026-10-29*
