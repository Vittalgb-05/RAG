# Testing Patterns

**Analysis Date:** 2026-10-21

## Test Framework

**Runner:**
- `pytest >= 8.3.0` (declared in `requirements-test.txt`; CI installs from that file).
- Config in `pyproject.toml`:
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
- No `addopts`, no custom markers, no plugin registration (`pytest-cov`, `pytest-xdist`, `pytest-asyncio` are **not** installed), no `pytest.ini`/`tox.ini` overrides.

**Assertion Library:**
- Plain `assert` statements plus `pytest.raises(...)` for exceptions. No `unittest.TestCase`, no third-party assertion helpers.
- Current suite: **296 tests collected** across **29 test modules** (plus `tests/conftest.py` and `tests/__init__.py`), ~7,275 lines under `tests/`.

**Run Commands:**
```bash
pytest tests/ -v                      # CI command (full suite)
python -m pytest tests/test_doc_store.py -q   # single module
python -m pytest -k "sanitize" -q     # keyword selection
python -m ruff check .                # lint gate
python -m ruff format --check .       # format gate
python tests/data/corpus/generate_corpus.py   # regenerate PDF fixtures
```
`README.md:226-232` documents `pytest tests/ -v`, `ruff check .`, and `ruff format --check .`.

## Test File Organization

**Location:**
- **Flat directory** `tests/` — files are not grouped by layer (no `tests/unit/`, `tests/integration/`). Each file maps to one production module or feature area.

**Naming:**
- `tests/test_<module_or_feature>.py`, mirroring the module under test:
  - `tests/test_doc_store.py` → `core/doc_store.py`
  - `tests/test_hybrid_retriever.py` → `retrieval/hybrid_retriever.py`
  - `tests/test_llama_cpp_provider.py` → `providers/llama_cpp_provider.py`
  - `tests/test_ui_smoke.py`, `tests/test_main_ui.py`, `tests/test_hydration.py` → `ui/` + `main.py`
  - `tests/test_setup_llama.py`, `tests/test_start_launcher.py` → `setup.py`, `start.py`
- There is one `tests/test_models.py` for all Pydantic schemas, and `tests/test_cloud_privacy.py` as the cross-cutting privacy/invariant suite.

**Structure:**
```
tests/
├── __init__.py                  # package marker (docstring only)
├── conftest.py                  # shared fixtures + env setup + mock seams
├── test_<module>.py             # 29 modules, flat
└── data/
    └── corpus/
        ├── generate_corpus.py   # reportlab generator (runs in CI)
        ├── clean_digital.pdf
        ├── multi_column.pdf
        ├── dense_table.pdf
        ├── scanned_sample.pdf
        ├── chart_diagram.pdf
        └── corrupt_invalid.pdf
```

**Module-level constants for fixture paths** are the standard pattern at the top of test modules:
```python
CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"
CLEAN_PDF = CORPUS_DIR / "clean_digital.pdf"
SCANNED_PDF = CORPUS_DIR / "scanned_sample.pdf"
```
(`tests/test_ocr_fallback.py:11-13`, also `tests/test_visual_analyzer.py`, `tests/test_docling_reader.py`, `tests/test_upload_validation.py`).

## Test Structure

**Suite Organization:**
- **Module-level functions only** for tests; no `class Test*` suites. Classes that do appear are mock providers/stubs, not test containers.
- Every test gets a one-line docstring naming the invariant and often the requirement ID:
  ```python
  def test_health_check_loading_503() -> None:
      """Test check_health when llama-server returns 503 while loading model weights."""
  ```
  (`tests/test_llama_cpp_provider.py:43-44`)
- Requirement-tagged names are used where traceability matters: `test_two_instance_interleave_R1` (`tests/test_doc_store.py:93`), `test_corrupt_invalid_rejected_WR07` (`tests/test_upload_validation.py:16`), `test_inference_gate_basic_acquire_release` (`tests/test_concurrency_lock.py:71`).
- Test body pattern: arrange fixtures → act → multiple focused asserts, with numbered comments for multi-phase scenarios:
  ```python
  # 1. Start in local mode
  # 2. Attempting cloud provider without consent raises PermissionError
  # 3. Explicit consent allows cloud operation
  # 4. Revoking consent switches AiModel back to local mode
  ```
  (`tests/test_cloud_privacy.py:24-50`)
- Type annotations on test functions are **mixed**: newer files use `-> None` (`tests/test_sanitizer.py`, `tests/test_concurrency_lock.py`), older files omit it (`tests/test_doc_store.py`, `tests/test_main_ui.py`). New tests should annotate `-> None` and annotate `tmp_path: Path`/`monkeypatch: pytest.MonkeyPatch` when used.

**Setup / Teardown:**
- `tmp_path` is the default isolation mechanism for SQLite and LanceDB — never write into the repo `data/` directory:
  ```python
  db_file = tmp_path / "test_docs.db"
  store = DocStore(db_file)
  ```
  (`tests/test_doc_store.py:14-16`); LanceDB: `HybridRetriever(db_uri=tmp_path / "lancedb_test")` (`tests/test_hybrid_retriever.py:50-51`).
- Module-local `@pytest.fixture(autouse=True)` resets process-global state before and after each test. Required for:
  - `InferenceGate` lock state (`tests/test_concurrency_lock.py:61-67`)
  - Streamlit `session_state` (`tests/test_ui_smoke.py:19-35`, `tests/test_hydration.py:12-19`)
  - telemetry caches / latency history (`tests/test_resource_telemetry.py:25-33`)
- Teardown is done in `yield` fixtures or `try/finally` when monkeypatching module attributes directly:
  ```python
  original_st = local_embedding.SentenceTransformer
  try:
      local_embedding.SentenceTransformer = mock_st_class
      ...
  finally:
      local_embedding.clear_shared_model_cache()
      local_embedding.SentenceTransformer = original_st
  ```
  (`tests/test_hybrid_retriever.py:27-36`)

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `patch`, `patch.object`, `patch.dict`) plus pytest's `monkeypatch`. No `pytest-mock`, no `responses`, no `vcrpy`.

**Patterns:**

1. **Shared fixtures in `tests/conftest.py`** (preferred for seams used by multiple modules):
   - `fake_env_groq_key` — `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")`
   - `mock_groq_client` — patches `providers.groq_provider.Groq`, yields canned streaming chunks (`MockDelta`/`MockChoice`/`MockChunk`)
   - `mock_sentence_transformer` — patches `retrieval.local_embedding.SentenceTransformer`, returns deterministic 384-dim L2-normalized float32 vectors
   - `sample_pdf_path` — path to `tests/data/corpus/clean_digital.pdf`
   - `mock_llama_provider` — full `BaseModelProvider` subclass with recorded `stream_calls`
   ```python
   @pytest.fixture
   def mock_sentence_transformer(monkeypatch):
       mock_model = MagicMock()
       def mock_encode(texts, normalize_embeddings=True, **kwargs):
           ...
       mock_model.encode.side_effect = mock_encode
       from retrieval import local_embedding
       monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name, **kwargs: mock_model)
       return mock_model
   ```
   (`tests/conftest.py:62-92`)

2. **Patch at the module under test's namespace**, not the vendor namespace:
   ```python
   with patch("providers.groq_provider.Groq", return_value=mock_client):
   with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
   with patch("subprocess.run", return_value=mock_res):
   ```
   (`tests/test_groq_provider.py:38`, `tests/test_hydration.py:40`, `tests/test_resource_telemetry.py:44`)

3. **`httpx.MockTransport` for provider HTTP behavior** — no network, full request/response control:
   ```python
   def handler(request: httpx.Request) -> httpx.Response:
       assert request.url.path == "/v1/chat/completions"
       captured_payload = json.loads(request.read())
       return httpx.Response(200, json={"choices": [{"message": {"content": "Generated reply."}}]})

   transport = httpx.MockTransport(handler)
   provider = LlamaCppProvider(transport=transport)
   ```
   (`tests/test_llama_cpp_provider.py:30-40,87-117`; constructor seam `transport=` is defined in `providers/llama_cpp_provider.py:33`)

4. **Injectable constructor seams instead of patching internals.** Production classes accept mockable collaborators:
   - `LlamaCppProvider(transport=...)`
   - `OcrEngine(recognizer=..., renderer=...)` → `MagicMock` (`tests/test_ocr_fallback.py:44-45`)
   - `VisualAnalyzer(region_detector=..., cropper=...)` → `MagicMock(return_value=[...])` (`tests/test_visual_analyzer.py:94-110`)
   - `DoclingReader(converter=...)` and private `_has_docling = False` (`tests/test_docling_reader.py:16-18`)

5. **Class-based provider stubs implementing `BaseModelProvider`** — used when behavior ordering/call recording matters. They record calls in instance lists asserted later:
   ```python
   class MockVisionProvider(BaseModelProvider):
       def __init__(self, model_name: str = "qwen3-vl-2b"):
           self.analyze_calls: list[dict] = []
       def analyze_image(self, image_bytes, prompt, max_tokens=512):
           self.analyze_calls.append({"image_len": len(image_bytes), "prompt": prompt})
           return "..."
   ```
   (`tests/test_visual_analyzer.py:19-55`; also `MockSummarizerProvider` in `tests/test_summarizer.py`, `DummyProvider` in `tests/test_concurrency_lock.py`, `MockLlamaCppProvider` in `tests/conftest.py:107-172`)

6. **`monkeypatch` for module-level seams and environment:**
   ```python
   monkeypatch.setattr(pypdf, "PdfReader", StubReader)         # tests/test_upload_validation.py
   monkeypatch.setattr(socket, "create_connection", guarded)   # tests/test_cloud_privacy.py:64
   monkeypatch.delenv("GROQ_API_KEY", raising=False)
   ```

**What to Mock:**
- All network clients and transports (`httpx`, `groq`, `litellm`).
- Model loading (`SentenceTransformer`), OCR engines, Docling converters, `nvidia-smi`/`subprocess.run`, `psutil`.
- Streamlit state (`monkeypatch.setattr(st, "session_state", fake_state, raising=False)`).
- Time/latency only where assertions depend on it (concurrency tests use real small `time.sleep(0.01)`; telemetry tests reset cache instead of patching clocks).

**What NOT to Mock:**
- SQLite (`DocStore`) — tests use real temp databases to verify WAL, migrations, foreign-key cascades, and `UNIQUE(sha256)` (`tests/test_doc_store.py`).
- PDF parsing for offline corpus files — real `pypdf`/Docling/PyMuPDF paths run against `tests/data/corpus/*.pdf` (`tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`).
- LanceDB persistence — real on-disk LanceDB under `tmp_path`, including reopen-across-instances checks (`tests/test_hybrid_retriever.py:100-126`).
- Security invariants — the privacy suite deliberately runs the real embedding/indexing path with `socket.create_connection` monkeypatched to raise, proving no egress (`tests/test_cloud_privacy.py:55-75`).

## Fixtures and Factories

**Shared fixtures (`tests/conftest.py`):**

| Fixture | Purpose |
|---|---|
| `fake_env_groq_key` | Sets a dummy `GROQ_API_KEY` via `monkeypatch.setenv` |
| `mock_groq_client` | Patches `providers.groq_provider.Groq`; canned streaming response |
| `mock_sentence_transformer` | Patches `SentenceTransformer`; deterministic 384-dim normalized vectors |
| `sample_pdf_path` | Absolute path to `tests/data/corpus/clean_digital.pdf` |
| `mock_llama_provider` | Healthy `BaseModelProvider` implementation with recorded `stream_calls` |

`conftest.py` also performs process-wide environment setup **before** importing numpy/pytest:
```python
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
```
(`tests/conftest.py:6-15`) — keep this block first when editing the file.

**Factories / helpers:**
- No factory library. Deterministic data builders are private helpers in the test module:
  ```python
  def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:
      """Generate a deterministic normalized float vector."""
      np.random.seed(seed)
      v = np.random.randn(dim).astype(np.float32)
      norm = np.linalg.norm(v)
      if norm > 0:
          v = v / norm
      return [float(x) for x in v]
  ```
  (`tests/test_hybrid_retriever.py:12-19`)
- Inline Pydantic construction is the norm for domain objects; use `"a" * 64` / `"1" * 64` for sha256 and fixed ISO timestamps (`"2026-10-11T01:00:00Z"`). IDs follow production prefixes (`doc_...`, `summ_...`) because validators enforce them.
- Test data location: `tests/data/corpus/`; generated by `tests/data/corpus/generate_corpus.py` and **also committed** to git.

**Corpus generator (`tests/data/corpus/generate_corpus.py`):**
- Uses `reportlab` (`SimpleDocTemplate`, `canvas`, `Table`) to build six PDFs:
  - `clean_digital.pdf` — 20 pages of headings/paragraphs with per-page verifiable claims (`target-{p}0 milliseconds`)
  - `multi_column.pdf` — 2-page two-column layout
  - `dense_table.pdf` — quarterly metrics table
  - `scanned_sample.pdf` — raster shapes only, zero extractable text
  - `chart_diagram.pdf` — flowchart with labeled boxes
  - `corrupt_invalid.pdf` — bytes without `%PDF` header
- Entry point `generate_all_corpus_files() -> dict[str, Path]` returns name→path map; `__main__` prints sizes. The generator is idempotent and runs in CI before pytest.

## Coverage

**Requirements:** None enforced. There is no `pytest-cov` dependency, no `--cov` in CI, no `[tool.coverage]` section, and no coverage threshold in `pyproject.toml`. `.gitignore` lists `.coverage` and `htmlcov/`, but neither is produced by any configured command.

**View Coverage (if added locally):**
```bash
pip install pytest-cov
python -m pytest tests/ --cov=core --cov=retrieval --cov=ingestion --cov=providers --cov=ui --cov-report=term-missing
```

**Documentation drift to be aware of:** `README.md:106` claims "248 tests"; current collection is **296**. Update the README when test counts change.

## Test Types

**Unit Tests (majority):**
- Pure functions and schemas: `tests/test_models.py` (validation, frozen/extra-forbid, legacy key compatibility), `tests/test_citation_validator.py`, `tests/test_prompt_budget.py`, `tests/test_sanitizer.py`.
- Persistence: `tests/test_doc_store.py` — migrations/user_version, `UNIQUE(sha256)`, WAL/interleaved instances, cascade deletes, summary cache invalidation, `VACUUM` purge.
- Retrieval: `tests/test_hybrid_retriever.py`, `tests/test_vector_index.py`, `tests/test_local_embedding.py`.
- Providers: `tests/test_llama_cpp_provider.py` (HTTP via `MockTransport`), `tests/test_litellm_provider.py`, `tests/test_groq_provider.py`, `tests/test_model_provider.py` (ABC contract + schema validation).
- UI/presentation contracts: `tests/test_ui_smoke.py`, `tests/test_main_ui.py`, `tests/test_hydration.py`, `tests/test_components` behavior covered inside `test_ui_smoke.py`.

**Integration-Style Tests (offline, in-process):**
- `tests/test_ocr_fallback.py`, `tests/test_docling_reader.py`, `tests/test_visual_analyzer.py` run real extractors over the synthetic corpus, often combined with `DocStore` + mock VLM.
- `tests/test_cloud_privacy.py` exercises `LocalEmbedding` → `HybridRetriever` → SQLite with outbound sockets blocked, and verifies consent transitions and per-provider key lookup.
- `tests/test_concurrency_lock.py` uses real threads and `time.sleep` to prove `InferenceGate` serialization, reentrancy, and timeout behavior.

**E2E / Browser Tests:** Not used. Streamlit render functions are exercised only through their pure helpers and via `tests/test_ui_smoke.py` (HTML-string assertions, `st.session_state` fixtures). No Playwright/Selenium.

**GPU / Live Model Tests:** Not used. Local inference is always mocked (`MockTransport`, provider stubs); `tests/conftest.py` is explicitly designed for "100% offline unit testing without GPU allocation or API calls".

**Markers:** No custom or built-in markers (`@pytest.mark.slow`, `integration`, etc.) are used anywhere. All 296 tests run in the default CI job.

## CI Pipeline

`.github/workflows/ci.yml` — single job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggered on push/PR to `main`:

1. `actions/checkout@v4`
2. `actions/setup-python@v5` with `python-version: "3.11"`
3. `astral-sh/setup-uv@v5` with caching
4. Install from lockfiles (reproducible):
   ```bash
   uv pip install --system -r requirements-lock.txt
   uv pip install --system -r requirements-test.txt
   uv pip install --system -e . --no-deps
   ```
5. `ruff check . && ruff format --check .`
6. `python tests/data/corpus/generate_corpus.py` (regenerates PDFs, ensuring generator works)
7. `pytest tests/ -v`

Notes:
- CI uses Python 3.11 while local development here is 3.13.5; keep tests version-agnostic and avoid 3.12+-only syntax.
- No matrix, no caching of the HF model cache, no coverage upload, no artifact upload of failures.

## Common Patterns

**Exception assertions with message match:**
```python
with pytest.raises(ValueError, match="Not a valid PDF: missing %PDF header"):
    validate_pdf_bytes(raw_bytes, "corrupt_invalid.pdf")

with pytest.raises(PermissionError, match="Cloud transmission blocked"):
    unconsented_cloud.generate_text("Test prompt")
```
(`tests/test_upload_validation.py:21`, `tests/test_cloud_privacy.py:34`)

**Pydantic validation failures:**
```python
with pytest.raises(ValidationError, match="doc_id must start with 'doc_'"):
    Document(...)
```
(`tests/test_models.py:272`)

**Streaming generators:** materialize with `list(...)` or iterate and join; assert captured payloads on the provider stub:
```python
tokens = list(provider.stream_text("prompt"))
assert "".join(tokens) == "This is a grounded answer."
```
Pattern derived from `MockLlamaCppProvider._tokens` (`tests/conftest.py:144-162`) and `tests/test_llama_cpp_provider.py` streaming tests.

**CLI output:** `capsys.readouterr()`:
```python
start.print_banner()
captured = capsys.readouterr()
assert "Local-First Multimodal PDF Intelligence System" in captured.out
```
(`tests/test_start_launcher.py:11-17`; also `tests/test_setup_llama.py:31-41`)

**Concurrency:** real `threading.Thread` + `InferenceGate`; assert serialization by call counts and elapsed ordering, and an explicit `TimeoutError` on non-blocking acquisition (`tests/test_concurrency_lock.py:150-200`).

**Determinism:** seed numpy (`np.random.seed(seed)`), fixed sha strings, fixed ISO timestamps, and canned token lists. No reliance on wall-clock dates.

**Temporary storage cleanup:** rely on `tmp_path` auto-cleanup; do not manually delete `data/` or `.cache/`. For `HybridRetriever`, instantiate with `db_uri=tmp_path / ...` so the real `data/lancedb` is untouched.

## Where to Add New Tests

- **New module in `core/`** → `tests/test_<module>.py`, unit-test pure functions first, then persistence/edge cases with `tmp_path`.
- **New provider** → `tests/test_<provider>_provider.py`; implement a `MockTransport` handler for HTTP providers and a class-based stub for ABC contract tests (`HealthStatus`, `ProviderCapabilities`).
- **New ingestion stage** → extend `tests/data/corpus/generate_corpus.py` if a new document shape is needed, add the file path constant at the top of the test module, and cover both success and fallback/failure isolation.
- **New UI behavior** → prefer extracting pure logic (formatting, state transitions, sanitization) into a testable function in `ui/` and testing it directly in `tests/test_main_ui.py` or a new `tests/test_<feature>.py`; add an autouse `clean_session_state` fixture if `st.session_state` is touched.
- **Privacy/egress behavior** → add to `tests/test_cloud_privacy.py` with `socket.create_connection` monkeypatched (never make real network calls).
- **Global mutable state** → add an autouse reset fixture mirroring `ensure_gate_released` / `reset_latencies`, and provide a `clear_*` helper in production code (as `retrieval/local_embedding.py:45` does with `clear_shared_model_cache`).

## Test Pitfalls To Avoid

**Mock provider schemas must match `extra="forbid"` models.**
- What happens: several test/dummy providers construct `HealthStatus(status="healthy", message="ok", provider_type="local")` (`tests/test_concurrency_lock.py:20`, `tests/test_summarizer.py:24`, `tests/test_main_ui.py:229`). `HealthStatus` in `providers/model_provider.py` defines only `status`, `message`, `latency_ms` and sets `extra="forbid"`, so any code path that actually calls `check_health()` on these stubs would raise `ValidationError`.
- Why it matters: the suite currently passes because those `check_health` methods are not invoked, but the stubs are latent failures.
- Do this instead: construct only schema fields — `HealthStatus(status="healthy", message="ok", latency_ms=1.0)` (as `tests/test_visual_analyzer.py` does).

**Tests that duplicate production logic instead of calling it.**
- What happens: `tests/test_main_ui.py` re-implements the "Clear All" purge and consent state transitions against a local `mock_session` dict.
- Why it matters: the test asserts the copy, not the shipped handler, so regressions in `main.py` go undetected.
- Do this instead: extract the transition into a function (e.g. in `ui/` or `main.py`) and call it from both the UI and the test.

**No parametrization.**
- What happens: near-identical cases are written as separate functions (e.g. `test_health_check_healthy`, `test_health_check_loading_503`, `test_health_check_unreachable`, `test_health_check_error_status` in `tests/test_llama_cpp_provider.py`).
- Why it matters: more boilerplate and drift between cases.
- Do this instead: use `@pytest.mark.parametrize` for table-driven input/output pairs (currently zero uses, so introduce it deliberately).

**Flat, unmarked suite.**
- What happens: all tests, including real LanceDB/model-loading paths, run in one CI job with no `integration` marker.
- Why it matters: slower feedback and no way to skip heavyweight tests locally.
- Do this instead: if adding slow tests, register a marker in `pyproject.toml` (`markers = [...]`) and document the deselection command; do not silently add multi-minute tests.

**Stale documentation counts.**
- What happens: `README.md` states 248 tests; actual collection is 296.
- Why it matters: misleading onboarding and CI expectations.
- Do this instead: update the README count when test modules are added.

---

*Testing analysis: 2026-10-21*
