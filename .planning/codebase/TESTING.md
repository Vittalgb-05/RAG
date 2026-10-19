# Testing Patterns

**Analysis Date:** 2026-10-19

## Test Framework

**Runner:**
- `pytest` (`pytest 9.0.3` in the current environment; `requirements-test.txt` declares `pytest>=8.3.0`).
- Configuration lives in `pyproject.toml` under `[tool.pytest.ini_options]`:
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
- No `pytest.ini`, `tox.ini`, or separate `conftest.py` outside `tests/`.
- `filterwarnings` globally suppresses `UserWarning` and `DeprecationWarning`; the suite therefore does not assert deprecation notices (even though `local_embedding.py` and `local_llm.py` emit them).

**Assertion Library:**
- Plain Python `assert` statements; no third-party assertion DSL.
- `pytest.raises(ExpectedError, match="...")` for exceptions.
- `pytest.approx(..., abs=1e-5)` for floating-point distance math in `tests/test_vector_index.py`.
- `capsys` for CLI/stdout assertions (`tests/test_start_launcher.py`, `tests/test_setup_llama.py`).

**Test-Only Dependencies (`requirements-test.txt`):**
- `pytest>=8.3.0` — runner.
- `reportlab>=4.2.0` — generates synthetic PDF corpus fixtures.
- `ruff>=0.9.0` — lint/format gate (same as CI).
- `psutil>=6.1.0` — telemetry tests / profiling.
- `pytest-cov` is installed in the local environment but is **not** declared in `requirements-test.txt` and has no configuration. Do not assume it exists in CI.

**Run Commands:**
```bash
pytest tests/ -v                 # Full suite (CI command)
pytest tests -q                  # Quiet full suite
pytest tests/test_doc_store.py -v
ruff check .                     # Lint gate
ruff format --check .            # Format gate
python tests/data/corpus/generate_corpus.py   # Regenerate synthetic PDFs
```

**Current Suite State:**
- 283 tests across 29 test modules.
- Full run on the analysis host: `283 passed in 41.71s` (`python -m pytest tests -q`).
- `README.md` and `docs/EVALUATION.md` still claim 248 tests / 24 suites; those numbers are stale relative to the tree. Use 283 as the current count.

## Test File Organization

**Location:**
- Flat `tests/` directory mirroring root modules; no unit/integration subdirectories.
- `tests/__init__.py` marks the package (`"""Tests package initialization."""`).
- Shared fixtures/mocks: `tests/conftest.py`.
- Synthetic and static corpus: `tests/data/corpus/` with `generate_corpus.py`, `clean_digital.pdf`, `scanned_sample.pdf`, `multi_column.pdf`, `dense_table.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`.
- UI tests live alongside backend tests: `tests/test_ui_smoke.py`, `tests/test_main_ui.py`, `tests/test_hydration.py`, `tests/test_sanitizer.py`, `tests/test_logging_setup.py`.

**Naming:**
- Files: `test_<module_under_test>.py` (`test_hybrid_retriever.py`, `test_llama_cpp_provider.py`, `test_doc_store.py`).
- Functions: `test_<observable_behavior>` — descriptive, no `test_1`/`test_works` names.
- Requirement IDs appear in module/function docstrings rather than names: `(RETR-01, RETR-02)`, `(INF-03, INF-04)`, `(QUAL-01)`, `(QA-03, QA-04)`.
- Test helper classes are local and named `Mock<Thing>Provider` / `Dummy<Thing>` (`MockVisionProvider`, `MockTextOnlyProvider`, `MockSummarizerProvider`, `DummyProvider`).

**Distribution (collected tests):**

| Test Module | Tests | Focus |
|---|---:|---|
| `tests/test_models.py` | 20 | Pydantic schemas, validation, serialization |
| `tests/test_llama_cpp_provider.py` | 17 | Local HTTP provider via `httpx.MockTransport` |
| `tests/test_doc_store.py` | 17 | SQLite persistence, migrations, dedup |
| `tests/test_hybrid_retriever.py` | 15 | LanceDB, RRF, fallback, deletion |
| `tests/test_resource_telemetry.py` | 14 | nvidia-smi parsing/caching, latency tracking |
| `tests/test_ocr_fallback.py` | 13 | Conditional OCR, page fault isolation |
| `tests/test_local_llm.py` | 13 | Provider selection, streaming, degraded startup |
| `tests/test_citation_validator.py` | 13 | Precision, abstention, injection detection |
| `tests/test_model_provider.py` | 12 | Abstract contract and schemas |
| `tests/test_start_launcher.py` | 11 | Launcher subprocess/health logic |
| `tests/test_prompt_budget.py` | 11 | Token budgeting, XML boundary defense |
| `tests/test_litellm_provider.py` | 11 | Consent gating, cloud adapter |
| `tests/test_summarizer.py` | 10 | Profiles, map-reduce, citations, cache |
| `tests/test_visual_analyzer.py` | 9 | Region detection, cropping, VLM provenance |
| `tests/test_ui_smoke.py` | 9 | SVG assets, pills, sanitizer, session reset |
| `tests/test_pdf_reader.py` | 9 | pypdf extraction/chunk overlap/corpus |
| `tests/test_upload_validation.py` | 8 | Magic bytes, caps, SHA/doc_id |
| `tests/test_main_ui.py` | 8 | Chat-turn/summary data contracts |
| `tests/test_docling_reader.py` | 8 | Docling extraction, table markdown, fallback |
| `tests/test_concurrency_lock.py` | 8 | `InferenceGate` threading/reentrancy |
| `tests/test_cloud_privacy.py` | 8 | Consent transitions, zero-egress invariant |
| `tests/test_vector_index.py` | 7 | Cosine/Euclidean math, guards |
| `tests/test_groq_provider.py` | 7 | Groq adapter streaming/health |
| `tests/test_setup_llama.py` | 6 | Installer orchestration (mocked subprocess) |
| `tests/test_cache_invalidation.py` | 6 | History bounding, cache versioning, telemetry |
| `tests/test_sanitizer.py` | 4 | Network-egress neutralization |
| `tests/test_logging_setup.py` | 4 | `logging.Filter` behavior/idempotency |
| `tests/test_local_embedding.py` | 4 | Shared model cache, index/context |
| `tests/test_hydration.py` | 1 | Startup hydration from SQLite (retriever mocked) |

## Test Structure

**Suite Organization:**
- Top-level test functions only; no test classes, no inheritance, no fixtures returning test classes.
- Arrange–act–assert with occasional numbered comments (`# 1. ...`, `# 2. ...`) mirroring the production pipeline stage.
- Every test has a one-line behavioral docstring beginning with `Verify` or `Test`.

```python
def test_sha_unique_violation_on_reupload(tmp_path):
    """Verify that uploading the same SHA with a different doc_id raises IntegrityError."""
    db_file = tmp_path / "test_docs.db"
    store = DocStore(db_file)

    sha = "2" * 64
    doc1 = Document(doc_id="doc_first", filename="first.pdf", sha256=sha, ...)
    store.upsert_document(doc1)

    doc2 = Document(doc_id="doc_second", filename="second.pdf", sha256=sha, ...)
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_document(doc2)
```

**Patterns:**
- Use `tmp_path` for every filesystem/database test (SQLite DBs, LanceDB directories, cache dirs). 114 references across the suite.
- Construct canonical Pydantic models directly instead of hand-written dict fixtures (`Document`, `Chunk`, `Page`, `EvidenceSnippet`, `SummaryResult`).
- Assert on public behavior and schema fields, not private implementation where a public accessor exists. Private access is used deliberately for migration/schema checks (`store._connect()` in `test_doc_store.py`) or distance internals.
- Add assertion messages when the invariant is subtle: `assert len(shared_words) >= 3, "Consecutive chunks on the same page must preserve text overlap"`.
- Tests are synchronous. Concurrency is tested with real `threading.Thread`/`Event` (`tests/test_concurrency_lock.py`), not async pytest.

## Mocking

**Framework:** stdlib `unittest.mock` (`MagicMock`, `patch`) plus pytest `monkeypatch`; no `pytest-mock`, `responses`, `respx`, or VCR.

**Shared fixtures (`tests/conftest.py`):**
- `fake_env_groq_key` — sets `GROQ_API_KEY` to a clearly fake value via `monkeypatch.setenv`.
- `mock_groq_client` — `MagicMock` client whose `chat.completions.create` yields canned delta chunks (`"This "`, `"is "`, ...); patches `groq_provider.Groq`.
- `mock_sentence_transformer` — patches `local_embedding.SentenceTransformer`; returns deterministic 384-dim normalized `float32` vectors derived from text length.
- `sample_pdf_path` — absolute path to `tests/data/corpus/clean_digital.pdf`.
- `mock_llama_provider` — full `BaseModelProvider` implementation returning healthy capabilities and deterministic tokens; records `stream_calls`.

**Mocking patterns:**
```python
# Patch in the consumer module namespace, not the source library
with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
    mock_retriever_cls.return_value.count_chunks.return_value = 5
    hydrate_startup_state(store)

# Environment and secrets
monkeypatch.setenv("LLAMA_SERVER_HOST", "host.docker.internal")
monkeypatch.delenv("GROQ_API_KEY", raising=False)
monkeypatch.setattr("streamlit.secrets", {}, raising=False)

# Local HTTP server: no sockets, full request/response assertions
transport = httpx.MockTransport(handler)
provider = LlamaCppProvider(transport=transport)
```

- `httpx.MockTransport` is the standard for `LlamaCppProvider` tests (`tests/test_llama_cpp_provider.py`): the handler asserts `request.url.path`, decodes `json.loads(request.read())`, and returns `httpx.Response(...)`.
- `patch("subprocess.run")` / `patch("shutil.which")` isolate `setup.py` and `start.py` from real installers and binaries.
- `monkeypatch.setattr("hybrid_retriever.lancedb", None)` exercises the no-LanceDB fallback path.
- `monkeypatch.setattr(socket, "create_connection", guarded_create_connection)` enforces zero egress during local ingestion (`tests/test_cloud_privacy.py`).

**What to Mock:**
- All network/cloud clients (`groq.Groq`, LiteLLM `completion`, `urllib.request.urlopen`, `socket.create_connection`).
- Subprocess and hardware probes (`subprocess.run` for `nvidia-smi`, `llama-server`, downloads).
- Heavy ML model loading (`SentenceTransformer`, Docling `DocumentConverter`, RapidOCR recognizer, PyMuPDF rendering) unless the test is explicitly about a real corpus artifact.
- Streamlit secrets/session state when the code reads them outside a real Streamlit runtime.

**What NOT to Mock:**
- SQLite — use a real `DocStore` on `tmp_path`.
- LanceDB persistence — use a real temporary directory (`HybridRetriever(db_uri=tmp_path / "lancedb_test")`).
- Pydantic validation, distance math, RRF math, regex/citation parsing, and pure transformation functions.
- PDF extraction against the static corpus when the test is validating parser behavior (`tests/test_pdf_reader.py` uses real `clean_digital.pdf`, `multi_column.pdf`, etc.).

**Preferred seam over patching:**
- Pass collaborators through constructor/value arguments: `AiModel(provider=mock_llama_provider)`, `Summarizer(provider=..., doc_store=...)`, `LlamaCppProvider(transport=...)`, `OcrEngine(recognizer=..., renderer=...)`, `VisualAnalyzer(region_detector=..., cropper=...)`, `DoclingReader(converter=...)`. Extend these seams for new code rather than patching module globals.

## Fixtures and Factories

**Fixture inventory (`tests/conftest.py`):** 5 fixtures (listed above). Total suite has 9 `@pytest.fixture` declarations; the rest are per-file `autouse` cleanup fixtures.

**Autouse isolation fixtures:**
- `tests/test_ui_smoke.py:clean_session_state` and `tests/test_hydration.py:clean_session_state` reset `st.session_state` before each test (all keys used by the app: `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, cloud flags, `uploader_key`, `active_workspace`, `_startup_hydrated`).
- `tests/test_concurrency_lock.py:ensure_gate_released` drains `InferenceGate` before and after every test.
- `tests/test_resource_telemetry.py:reset_latencies` clears latency history and GPU cache before/after.

**Test data/factories:**
- Deterministic vectors: `_make_unit_vector(seed, dim=384)` in `tests/test_hybrid_retriever.py`.
- Deterministic retrieval container: `_make_retrieval_result(num_snippets)` in `tests/test_citation_validator.py`.
- Deterministic mock providers: `MockSummarizerProvider` returns profile-aware markdown with `(p. X)` citations derived from the prompt; `MockVisionProvider` records `analyze_image` calls.
- Synthetic corpus is generated with ReportLab by `tests/data/corpus/generate_corpus.py`; CI runs it before pytest, but the checked-in PDFs mean tests also work without regeneration.
- No factory-boy, Faker, hypothesis, or shared fixture factories. Prefer small local helpers if a new test needs repeated object construction.

**Location:** fixtures in `tests/conftest.py` are auto-discovered by all tests; helper functions/classes stay private to their test module.

## Coverage

**Requirements:** None configured. There is no `--cov`, `coverage`, `addopts`, or minimum threshold in `pyproject.toml` or CI. `.coverage` and `htmlcov/` are gitignored, but no report is produced automatically.

**View Coverage:**
```bash
# Only if pytest-cov is installed (not declared in requirements-test.txt)
python -m pytest tests --cov=. --cov-report=term-missing
```
- `docs/EVALUATION.md` uses "100% pass rate", not line coverage. Do not treat it as a coverage guarantee.
- CI does not upload coverage artifacts.

**Known coverage gaps (add tests here when touching these areas):**
- `ui/views.py` — all five `render_*_view` functions are effectively untested; the suite covers their data contracts, components, sanitizer, and hydration instead (`tests/test_main_ui.py`, `tests/test_ui_smoke.py`).
- `main.py` — top-level Streamlit wiring (page config, session-state init, cloud-provider synchronization, workspace routing) is not exercised; only `_reset_session_security_state` is imported and tested (`tests/test_ui_smoke.py:109-118`).
- Real Docling / RapidOCR / PyMuPDF model inference — mocked or replaced with corpus parsing; no end-to-end extraction-quality assertion.
- Real `tools/llama-server` execution — `setup.py`/`start.py` are tested with `subprocess`, `shutil.which`, and `urllib.request.urlopen` mocked; binary compatibility is not CI-tested.
- Windows-specific behavior — CI runs `ubuntu-latest` only, although the app targets Windows/PowerShell and has Windows-specific launch/caching logic.
- Performance/VRAM SLAs in `docs/EVALUATION.md` are measured by scripts (`scripts/benchmark_*.py`, `scripts/profile_resources.py`), not asserted in pytest.

## Test Types

**Unit Tests (dominant):**
- Pure logic and schema validation: `tests/test_models.py`, `tests/test_vector_index.py`, `tests/test_prompt_budget.py`, `tests/test_citation_validator.py`, `tests/test_upload_validation.py`, `tests/test_sanitizer.py`, `tests/test_logging_setup.py`.
- Provider behavior with mocked transports/clients: `tests/test_llama_cpp_provider.py`, `tests/test_groq_provider.py`, `tests/test_litellm_provider.py`.
- Orchestration with injected fake providers: `tests/test_local_llm.py`, `tests/test_summarizer.py`, `tests/test_visual_analyzer.py`, `tests/test_ocr_fallback.py`.

**Integration-style Tests (in-process, offline):**
- Real SQLite + real temporary files: `tests/test_doc_store.py`, `tests/test_cache_invalidation.py`, `tests/test_hydration.py`.
- Real LanceDB on `tmp_path` with real RRF math and disk reopen: `tests/test_hybrid_retriever.py`.
- Real corpus PDFs through `PdfReader`/Docling mocks: `tests/test_pdf_reader.py`, `tests/test_docling_reader.py`.
- Privacy invariant: actual embedding + LanceDB indexing while `socket.create_connection` is patched to fail (`tests/test_cloud_privacy.py`).

**UI/Smoke Tests:**
- Component-level markup assertions without a browser: `tests/test_ui_smoke.py` (SVG local-only URLs, status pills, citation chips, sanitizer, session reset).
- Data-contract tests: `tests/test_main_ui.py` (chat turn schema, citation drawer formatting, summary serialization, provider attribute contract).
- No Playwright/Selenium/SeleniumBase browser E2E suite and no Streamlit AppTest usage. UI rendering is validated by direct function calls and Streamlit session-state mutation.

**E2E Tests:** Not present. No test starts Streamlit, `llama-server`, Docling, or a cloud API end to end.

## Common Patterns

**Exception testing:**
```python
with pytest.raises(ValueError, match="File too large"):
    validate_pdf_bytes(oversized_bytes, "large.pdf")

with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    provider.generate_text("prompt")
```
- Match on a stable substring, not the full message, and include regex escaping for parentheses when needed (`match=f"Too many pages \\({MAX_PAGES + 1} > {MAX_PAGES}\\)"`).

**Env/config testing:**
```python
monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")
monkeypatch.delenv("GROQ_API_KEY", raising=False)
monkeypatch.setattr("streamlit.secrets", {}, raising=False)
```

**Concurrency testing:**
- Real `threading.Thread` plus `threading.Event` to prove blocking/timeout behavior; assert gate state before/after (`tests/test_concurrency_lock.py`).
- Always pair with an autouse fixture that releases the gate to prevent cross-test deadlocks.

**CLI testing:**
- `capsys` for banners/status text (`tests/test_start_launcher.py`, `tests/test_setup_llama.py`).
- Patch `sys.argv` and assert the constructed command list for `launch_streamlit` (`assert "streamlit" in cmd`, `assert "--server.port=8501" in cmd`).

**Numeric testing:**
- `pytest.approx(value, abs=1e-5)` for cosine/Euclidean distances and similarity scores.
- Deterministic RNG seeding only inside helper vector factories; avoid global `np.random.seed` in new tests.

**Adding a new test file:**
1. Create `tests/test_<module>.py` with a module docstring stating scope and any requirement IDs.
2. Import the module under test directly (`from hybrid_retriever import HybridRetriever`); do not import `main.py` unless testing entry-point helpers, because importing it executes Streamlit setup and constructs `DocStore`/`AiModel`.
3. Use `tmp_path` for persistence, `monkeypatch` for env/global seams, and an injected fake `BaseModelProvider` for inference.
4. Keep it offline: no real cloud calls, no real socket connections, no real `llama-server`/`nvidia-smi` subprocesses.
5. If global state is touched (`st.session_state`, `InferenceGate`, latency/GPU caches), add an `autouse` cleanup fixture.
6. Run `ruff check .`, `ruff format .`, and `pytest tests -q` before finishing.

---

*Testing analysis: 2026-10-19*
