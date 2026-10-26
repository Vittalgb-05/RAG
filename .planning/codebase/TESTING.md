# Testing Patterns

**Analysis Date:** 2026-10-26

## Test Framework

**Runner:**
- pytest `>= 8.3.0` (`requirements-test.txt:2`)
- Config: `pyproject.toml` under `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`.
- There is no `pytest.ini`, `setup.cfg`, or separate tox config; `pyproject.toml` is authoritative. pytest plugins beyond the core are not installed (no `pytest-cov`, `pytest-asyncio`, `pytest-xdist`, `pytest-mock`).

**Assertion Library:**
- Plain built-in `assert` statements.
- Exception assertions use `pytest.raises(...)`, frequently with `match=` and inline context managers.
- Pydantic failures are asserted as `pydantic.ValidationError` (`tests/test_models.py:60`, `:70`).
- No custom assertion helpers; domain-model factories (`_make_*`) and hand-written comparison strings perform the same role.

**Run Commands:**
```bash
pytest tests/ -v                       # Full suite (CI command)
pytest -q --no-header                  # Quiet local run (used in docs/TEST_RESULTS.md)
pytest tests/test_citation_validator.py -v   # Single module
pytest tests/test_doc_store.py -k sha_unique -v   # Single test by name
python tests/data/corpus/generate_corpus.py      # Regenerate synthetic PDF corpus (required before PDF tests)
ruff check . && ruff format --check .            # Lint/format gates
```
- No watch mode is configured (pytest-watch not installed).
- `tests/data/corpus/*.pdf` are generated artifacts; CI regenerates them before running pytest (`.github/workflows/ci.yml`).

## Test File Organization

**Location:**
- Separate `tests/` package at the repository root (not co-located with source). `tests/__init__.py` exists so tests are importable as a package.
- Shared fixtures live only in `tests/conftest.py`; module-local fixtures are defined in the test file that needs them.
- Synthetic input data lives in `tests/data/corpus/` and is produced by `tests/data/corpus/generate_corpus.py` (reportlab).

**Naming:**
- `tests/test_<module_or_feature>.py` — 33 test modules currently present.
- Feature grouping is used when a suite spans multiple modules: `test_ui_smoke.py`, `test_cloud_privacy.py`, `test_whole_document_extraction.py`, `test_audit_repairs.py`, `test_cache_invalidation.py`.
- Test function names are behavior-first sentences: `test_validate_citations_hallucinated_rank`, `test_uploader_key_increments_on_session_reset`, `test_deleted_document_stays_deleted_after_lancedb_open_failure`, `test_configure_logging_degrades_when_log_dir_is_unwritable`. Audit IDs appear where relevant in the docstring, e.g. "(P0-1)", "(CR-01)".

**Structure:**
```
tests/
├── __init__.py                  # Package marker (docstring only)
├── conftest.py                  # Shared fixtures: env guards, mocks, sample PDFs
├── data/
│   └── corpus/
│       ├── generate_corpus.py   # reportlab generator (clean digital, scanned, table, chart, multi-column, corrupt)
│       ├── clean_digital.pdf
│       ├── scanned_sample.pdf
│       ├── dense_table.pdf
│       ├── chart_diagram.pdf
│       ├── multi_column.pdf
│       └── corrupt_invalid.pdf
├── test_audit_repairs.py        # Regression suite tied to audit findings
├── test_cache_invalidation.py
├── test_citation_validator.py
├── test_cloud_privacy.py
├── test_concurrency_lock.py
├── test_doc_store.py
├── test_docling_reader.py
├── test_groq_provider.py
├── test_hybrid_retriever.py
├── test_hydration.py
├── test_litellm_provider.py
├── test_llama_cpp_provider.py
├── test_local_embedding.py
├── test_local_llm.py
├── test_logging_setup.py
├── test_main_ui.py
├── test_model_provider.py
├── test_models.py
├── test_ocr_fallback.py
├── test_pdf_reader.py
├── test_prompt_budget.py
├── test_query_intent.py
├── test_resource_telemetry.py
├── test_sanitizer.py
├── test_setup_checksums.py
├── test_setup_llama.py
├── test_start_launcher.py
├── test_summarizer.py
├── test_ui_smoke.py
├── test_upload_validation.py
├── test_vector_index.py
├── test_visual_analyzer.py
└── test_whole_document_extraction.py
```

Suites mirror production ownership: `core/` → `test_doc_store.py`, `test_citation_validator.py`, `test_local_llm.py`, `test_summarizer.py`, `test_prompt_budget.py`, `test_query_intent.py`, `test_models.py`, `test_logging_setup.py`, `test_resource_telemetry.py`; `ingestion/` → `test_upload_validation.py`, `test_docling_reader.py`, `test_pdf_reader.py`, `test_ocr_fallback.py`, `test_visual_analyzer.py`; `retrieval/` → `test_hybrid_retriever.py`, `test_vector_index.py`, `test_local_embedding.py`; `providers/` → `test_model_provider.py`, `test_llama_cpp_provider.py`, `test_litellm_provider.py`, `test_groq_provider.py`; `ui/` → `test_sanitizer.py`, `test_hydration.py`, `test_main_ui.py`, `test_ui_smoke.py`.

## Test Structure

**Suite Organization:**
- Tests are module-level functions; test classes are not used. Classes in test files are always test doubles implementing `BaseModelProvider` (`DummyProvider`, `MockVisionProvider`, `MockSummarizerProvider`, `FailingRetriever`).
- Each module starts with a docstring describing the contract under test; longer suites use a banner comment.
- Arrange → act → assert is written inline, with comments delimiting phases for complex flows.

**Example (`tests/test_citation_validator.py:14-33, 55-69`):**
```python
def _make_retrieval_result(num_snippets: int = 3) -> RetrievalResult:
    """Helper to construct a canonical RetrievalResult with dummy snippets."""
    snippets = [
        EvidenceSnippet(
            content=f"Content for snippet {i}",
            doc_id="doc_test",
            filename="test.pdf",
            page=i,
            chunk_id=f"chk_{i}",
            score=0.9 - (i * 0.1),
            rank=i,
        )
        for i in range(1, num_snippets + 1)
    ]
    return RetrievalResult(query="test query", snippets=snippets, total_candidates=num_snippets, search_mode="hybrid")


def test_validate_citations_perfect_precision() -> None:
    """Verify 100% precision when all cited ranks exist in retrieval results."""
    rr = _make_retrieval_result(num_snippets=4)
    response = "The system achieved 95% precision [E1] and operates under 4 GB VRAM [E2][E3]."

    result = validate_citations(response, rr)
    assert isinstance(result, CitationVerificationResult)
    assert result.is_valid is True
    assert result.precision == 1.0
    assert result.valid_citations == ["[E1]", "[E2]", "[E3]"]
```

**Patterns:**
- **Setup via fixtures:** shared environment guards and mocks in `tests/conftest.py`; per-suite `autouse` fixtures reset process/session state: `clean_session_state` (`tests/test_ui_smoke.py:27-43`), `ensure_gate_released` (`tests/test_concurrency_lock.py:61-68`), `_clean_application_logging` (`tests/test_logging_setup.py:18-22`).
- **Teardown via yield:** `yield` fixtures restore global state after the test (`tests/test_concurrency_lock.py`, `tests/test_logging_setup.py`).
- **Filesystem isolation:** `tmp_path` is the default for any test that touches SQLite, LanceDB, caches, logs, or downloaded binaries (`tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_logging_setup.py`, `tests/test_setup_llama.py`). Tests never write into the repo's `data/` or `.cache/`.
- **Assertion style:** one logical assertion cluster per behavior; `is True` / `is False` for booleans, `==` for values, `in` for substrings of human-readable diagnostics; failure messages added when the assertion is non-obvious (`pytest` message strings on `assert len(...) == 2, "Duplicate handlers were installed"`).
- **Truthfulness of diagnostics:** tests assert on user-visible message fragments (`"hallucinated [E5]"`, `"Valid explicit abstention"`, `"support not confirmed"`), not just codes.
- **Type annotations:** test functions are usually annotated `-> None` in newer suites; older suites omit the annotation.

## Mocking

**Framework:**
- `unittest.mock` (`MagicMock`, `patch`, `patch.object`) for object replacement.
- pytest `monkeypatch` for environment variables, module attributes, and targeted setattr/`delenv`.
- `httpx.MockTransport` for the local llama-server HTTP surface — the production constructor accepts `transport` explicitly (`providers/llama_cpp_provider.py:64`, used throughout `tests/test_llama_cpp_provider.py`).

**Patterns:**
```python
# 1. Fake provider implementing the real ABC (tests/conftest.py:107)
class MockLlamaCppProvider(BaseModelProvider):
    def stream_text(self, prompt, system_prompt=None, history=None, max_tokens=1024, temperature=0.2):
        self.stream_calls.append({...})
        yield from self._tokens


# 2. monkeypatch a module-level symbol (tests/conftest.py:91)
monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name, **kwargs: mock_model)

# 3. patch a collaborator class by dotted path (tests/test_ui_smoke.py:159)
with patch("ui.hydration.HybridRetriever") as mock_retriever_cls:
    mock_retriever = MagicMock()
    mock_retriever.count_chunks.return_value = 8
    mock_retriever_cls.return_value = mock_retriever
    hydrate_startup_state(store)

# 4. module-level flag patch (tests/test_concurrency_lock.py:194)
monkeypatch.setattr(InferenceGate, "acquire", MagicMock(return_value=False))
```

**What to Mock:**
- Network and external APIs: `httpx` transport (`MockTransport`), `urllib.request.urlopen` (`tests/test_start_launcher.py`), Groq/LiteLLM clients (`tests/test_groq_provider.py`, `tests/test_litellm_provider.py`).
- Heavy model loading: `SentenceTransformer` (`tests/conftest.py:63-92`), OCR recognizer/renderer (`tests/test_ocr_fallback.py`), PyMuPDF page rendering where pixel output is irrelevant, VLM providers (`tests/test_visual_analyzer.py`).
- Hardware telemetry: `psutil`, `nvidia-smi` subprocess calls, and GPU memory probes (`tests/test_resource_telemetry.py`).
- Streamlit runtime: `st.session_state` values and collaborator classes under `ui.hydration` (`tests/test_ui_smoke.py`).
- Slow or timing-dependent collaborators (`time.sleep` inside `DummyProvider` keeps concurrency tests fast).

**What NOT to Mock:**
- Pydantic models and validators — construct real `Document`, `Chunk`, `EvidenceSnippet` objects so schema regressions surface.
- `DocStore` / SQLite — use a real database file under `tmp_path` to exercise migrations, WAL, indexes, and `UNIQUE(sha256)` (`tests/test_doc_store.py`).
- Citation validation, sanitizer regexes, RRF/fusion math, prompt budgeting, and query-intent heuristics — these are the behaviors under test and are asserted on real inputs.
- Filesystem semantics — use real `tmp_path` directories rather than mocking `Path`.
- Deterministic numeric logic — use fixed vectors (`_make_unit_vector(seed)`) and deterministic hashing embeddings (`_embed` in `tests/test_whole_document_extraction.py:43`) instead of stubbing results.

## Fixtures and Factories

**Test Data:**
```python
# tests/conftest.py:95-99 — committed synthetic corpus
@pytest.fixture
def sample_pdf_path():
    """Returns the path to the synthetic clean_digital.pdf."""
    path = Path(__file__).resolve().parent / "data" / "corpus" / "clean_digital.pdf"
    return str(path)


# tests/conftest.py:95 — healthy Fake provider with recorded stream calls
def test_ai_model_validate_response_integration(mock_llama_provider) -> None:
    model = AiModel(provider=mock_llama_provider)
    ...
```

Deterministic-data conventions:
- `_make_unit_vector(seed, dim=384)` uses `np.random.seed(seed)` then L2-normalizes (`tests/test_hybrid_retriever.py:13-19`).
- `_make_retrieval_result(num_snippets)` builds ranked `EvidenceSnippet`s with decreasing scores (`tests/test_citation_validator.py:14`).
- `_embed(text)` is a 384-dim SHA-256 token-hashing embedding used to avoid downloading MiniLM (`tests/test_whole_document_extraction.py:43-50`).
- Corpus PDFs are generated, not hand-edited: `tests/data/corpus/generate_corpus.py` emits six PDFs (clean digital, multi-column, dense table, chart/diagram, scanned, corrupt). Regenerate rather than patching commit binaries.

**Location:**
- Shared fixtures: `tests/conftest.py` (`fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`).
- Suite-local fixtures: `question_retriever` (`tests/test_whole_document_extraction.py:54`), autouse state-reset fixtures in `tests/test_ui_smoke.py`, `tests/test_concurrency_lock.py`, `tests/test_logging_setup.py`, `tests/test_hydration.py`, `tests/test_resource_telemetry.py`.
- Binary test inputs: `tests/data/corpus/`.

## Coverage

**Requirements:** None enforced. No `pytest-cov` dependency, no `[tool.coverage]` section, no threshold in CI. The quality gate is lint + format + a fully green suite (`.github/workflows/ci.yml`).
- Recorded baseline in `docs/TEST_RESULTS.md`: 389 tests passed across 32 suites (2026-10-22). The repository now contains 33 test modules; the exact collected count changes with new tests.
- Requirement traceability for quality gates is tracked in `docs/REQUIREMENTS_TRACEABILITY.md` (QUAL-02) and `docs/EVALUATION.md`.

**View Coverage:**
```bash
# Not configured today. If pytest-cov is added:
pytest --cov=core --cov=ingestion --cov=retrieval --cov=providers --cov=ui --cov-report=term-missing
```

- Behavioral KPIs are asserted instead of line coverage where the product defines them: citation precision ≥ 95% (`tests/test_citation_validator.py`), cache invalidation on model-version change (`tests/test_cache_invalidation.py`, `tests/test_ui_smoke.py:201`), and single-active-inference enforcement (`tests/test_concurrency_lock.py`).

## Test Types

**Unit Tests:**
- The majority. Pure functions and models: `tests/test_models.py`, `tests/test_query_intent.py`, `tests/test_prompt_budget.py`, `tests/test_citation_validator.py`, `tests/test_sanitizer.py`, `tests/test_upload_validation.py`.
- Storage/retrieval units against a real temp database: `tests/test_doc_store.py`, `tests/test_vector_index.py`, `tests/test_hybrid_retriever.py`.
- Providers with transport-level fakes: `tests/test_llama_cpp_provider.py` (httpx MockTransport), `tests/test_litellm_provider.py`, `tests/test_groq_provider.py`, `tests/test_model_provider.py`.
- Ingestion stages with mocked engines and synthetic PDFs: `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_docling_reader.py`, `tests/test_pdf_reader.py`.

**Integration Tests:**
- Composition-level, still offline: `tests/test_ui_smoke.py` (hydration + lifecycle + summary cache + session reset against a real `DocStore`), `tests/test_whole_document_extraction.py` (real `HybridRetriever` with deterministic embeddings and FTS), `tests/test_audit_repairs.py` (cross-module regressions: vector failure propagation, atomic ingestion, sanitizer hardening, checksum gating), `tests/test_hydration.py`, `tests/test_main_ui.py`.
- Streamlit is exercised by importing renderer/helper functions directly and manipulating `st.session_state`; the app is not launched as a server.

**E2E Tests:**
- Not used. No browser automation, no Playwright/Selenium, no live llama-server test in CI.
- Known environmental gaps documented in `docs/FILE_CALLER_TEST_MAP.md:67-75`: live llama-server endpoints, real GPU VRAM behavior, real OCR/VLM quality, and real cloud API calls are **UNTESTED** by the automated suite.
- Optional artifact-dependent test is skipped conditionally: `test_local_model_identity_matches_declared_architecture` uses `@pytest.mark.skipif(not GGUF.exists(), reason="local GGUF artifacts are not installed")` (`tests/test_audit_repairs.py:209-215`).

## Common Patterns

**Async Testing:**
- Not applicable — the production code is synchronous. Concurrency is tested with real threads and `threading.Event` synchronization, not asyncio:
```python
def t1_worker() -> None:
    with InferenceGate.hold(timeout=2.0):
        t1_started.set()
        t1_finish.wait(timeout=2.0)

def t2_worker() -> None:
    t1_started.wait(timeout=2.0)
    acquired_by_t2.append(InferenceGate.acquire(timeout=0.05))
```
(`tests/test_concurrency_lock.py:120-129`)

- Generator lifecycle is tested explicitly by closing or throwing into a partially consumed stream and asserting the gate released (`tests/test_concurrency_lock.py:200-226`).

**Error Testing:**
```python
with pytest.raises(sqlite3.IntegrityError):
    store.upsert_document(doc2)          # tests/test_doc_store.py:66-67

with pytest.raises(TimeoutError, match="InferenceGate acquisition timed out"), InferenceGate.hold(timeout=0.05):
    pass                                  # tests/test_concurrency_lock.py:159-160

with pytest.raises(ValidationError, match="extra"):
    Document(doc_id="doc_123", ..., unexpected="x")   # tests/test_models.py:68-70
```

**Logging / stdout assertions:**
```python
with caplog.at_level(logging.WARNING, logger="retrieval.hybrid_retriever"):
    ...
assert any("full-text search unavailable" in r.getMessage() for r in caplog.records)   # tests/test_hybrid_retriever.py:715-737

captured = capsys.readouterr()
assert "Local llama-server detected" in captured.out                                    # tests/test_start_launcher.py
```

**Parametrization:**
- Used sparingly, only where a single behavior has equivalent inputs:
```python
@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_require_checksums_is_disabled_by_default(monkeypatch, value):
    monkeypatch.setenv("RAG_REQUIRE_CHECKSUMS", value)
    assert setup_mod.require_pinned_checksums() is False
```
(`tests/test_setup_checksums.py:125-129`)

**Environment isolation:**
- `tests/conftest.py` sets `USE_TF=0`, `USE_TORCH=1`, `TF_ENABLE_ONEDNN_OPTS=0` before importing ML modules so pytest never initializes TensorFlow/Keras.
- Credentials are always fake/mock values (`"test-key-not-a-secret-mock-value"`), and tests that depend on a clean environment call `monkeypatch.delenv("GROQ_API_KEY", raising=False)`.
- Stateful singletons (`InferenceGate`, logging handlers, Streamlit `session_state`, shared embedding cache) must be reset by an autouse/yield fixture; new tests touching them should follow the same pattern.

**Adding a new test suite:**
1. Create `tests/test_<module>.py` with a module docstring naming the contract.
2. Reuse `conftest.py` fixtures where possible; add a `tmp_path`-based fixture for storage.
3. Mock only the boundary (HTTP transport, model loader, telemetry) — assert on real domain objects.
4. Tag the requirement/audit ID in the test docstring.
5. Ensure `ruff check .` and `ruff format --check .` pass; CI runs both before pytest.

---

*Testing analysis: 2026-10-26*
