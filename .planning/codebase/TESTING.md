# Testing Patterns

**Analysis Date:** 2026-10-13

## Test Framework

**Runner:**
- Pytest $\ge 8.3.0$ (`requirements-test.txt`)
- Configuration (`pyproject.toml`):
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

**Assertion Libraries & Helpers:**
- Standard Python `assert` statements.
- `pytest.raises(ExceptionType, match="regex")` for expected exception testing.
- `pytest.approx(value, abs=1e-5)` for floating-point and vector cosine distance assertions.
- `reportlab>=4.2.0` for synthetic PDF generation.
- `psutil>=6.1.0` for process memory assertions.

**Run Commands:**
```bash
# Run complete test suite (226 tests)
pytest tests/ -v

# Run single test module
pytest tests/test_hybrid_retriever.py -v

# Run targeted test by name expression
pytest tests/ -k "test_citation_validator" -v

# Run with coverage report
pytest --cov=. --cov-report=term-missing tests/
```

## Test File Organization

**Location:**
- All tests live inside the `tests/` directory at the project root.
- Test files map directly to application modules with `test_<module>.py`.

**Structure:**
```
tests/
├── __init__.py                  # Package marker
├── conftest.py                  # Shared fixtures and mock seams (100% offline testing)
├── data/
│   └── corpus/
│       ├── generate_corpus.py   # Synthetic PDF generator using ReportLab
│       ├── clean_digital.pdf    # 20-page digital PDF text fixture
│       ├── dense_table.pdf      # Dense financial table PDF fixture
│       ├── chart_diagram.pdf    # Vector diagrams and charts fixture
│       ├── multi_column.pdf     # Multi-column layout document
│       ├── scanned_sample.pdf   # Low-text/scanned image PDF fixture
│       └── corrupt_invalid.pdf  # Header-corrupted invalid PDF fixture
├── test_cache_invalidation.py   # Cache invalidation, turn bounding, and purge logic
├── test_citation_validator.py   # Bracketed citation extraction, precision, and abstention
├── test_cloud_privacy.py        # Consent gating, provider switching, and zero-egress invariants
├── test_concurrency_lock.py     # InferenceGate mutual exclusion and timeouts
├── test_doc_store.py            # SQLite schema migrations, CRUD, and cascades
├── test_docling_reader.py       # Layout extraction and fallback to pypdf
├── test_hybrid_retriever.py     # LanceDB vector search, BM25 indexing, and RRF fusion
├── test_litellm_provider.py     # LiteLLM routing, context windows, and consent checks
├── test_llama_cpp_provider.py   # Local llama-server client and SSRF loopback defense
├── test_local_embedding.py      # CPU-pinned embedding generation and model caching
├── test_local_llm.py            # AiModel orchestration and streaming generation
├── test_main_ui.py              # Streamlit session state and UI display contracts
├── test_model_provider.py       # BaseModelProvider interface and capability schemas
├── test_models.py               # Pydantic v2 schemas and coordinate validation
├── test_ocr_fallback.py         # Conditional RapidOCR execution and DPI clamps
├── test_pdf_reader.py           # Text extraction, chunking, and corrupted PDF handling
├── test_prompt_budget.py        # Token budgets, history truncation, and XML sanitization
├── test_resource_telemetry.py   # nvidia-smi parsing, TTL caching, and psutil metrics
├── test_summarizer.py           # Map-reduce summarization profiles and page citations
├── test_upload_validation.py    # %PDF- headers, size limits, and SHA-256 calculation
├── test_vector_index.py         # In-memory linear scan cosine and Euclidean search
└── test_visual_analyzer.py      # Visual region detection, cropping, and VLM queries
```

## Test Structure & Patterns

**Suite Organization:**
- Header banner docstring explaining module scope.
- Top-level flat `test_*` functions without wrapper classes.
- Standard Arrange-Act-Assert structure:
  ```python
  def test_citation_validation_precision():
      # Arrange
      snippets = [
          EvidenceSnippet(content="Sample text", doc_id="doc_1", filename="test.pdf", page=1, chunk_id="chk_1", score=0.9, rank=1),
          EvidenceSnippet(content="Other text", doc_id="doc_1", filename="test.pdf", page=2, chunk_id="chk_2", score=0.8, rank=2),
      ]
      result = RetrievalResult(query="test", snippets=snippets)
      text = "This is verified factual information [E1]."

      # Act
      verif = validate_citations(text, result)

      # Assert
      assert verif.is_valid is True
      assert verif.precision == 1.0
      assert verif.valid_citations == ["[E1]"]
  ```

**Strict 100% Offline Invariant:**
- Tests NEVER make outbound HTTP requests or load live GPU models.
- Network calls are intercepted via `unittest.mock.MagicMock` or `httpx.MockTransport`.
- SentenceTransformers is mocked with deterministic numpy pseudo-vectors based on string lengths.
- Local `llama-server` is mocked with a canned token generator and status responses.

## Mocking & Shared Fixtures (`tests/conftest.py`)

- `fake_env_groq_key`: Sets a mock `GROQ_API_KEY="test-key-not-a-secret-mock-value"` in `monkeypatch`.
- `mock_groq_client`: Mocks `groq.Groq` and `chat.completions.create` yielding token deltas (`["This ", "is ", "a ", "grounded ", "answer."]`).
- `mock_sentence_transformer`: Replaces `SentenceTransformer` in `local_embedding` with a mock generating deterministic 384-dimensional normalized float32 vectors.
- `mock_llama_provider`: Provides a mock `LlamaCppProvider` yielding canned response tokens without a running `llama-server`.
- `temp_db_path`: Yields an isolated temporary SQLite database path that cleans up automatically after test execution.
- `temp_lancedb_dir`: Yields an isolated temporary LanceDB directory for vector store tests.

## Continuous Integration (`.github/workflows/ci.yml`)

1. **Step 1:** Checkout repository (`actions/checkout@v4`).
2. **Step 2:** Set up Python 3.11 (`actions/setup-python@v5`).
3. **Step 3:** Install `uv` with cache enabled (`astral-sh/setup-uv@v5`).
4. **Step 4:** Install locked dependencies (`uv pip install --system -r requirements-lock.txt` and `-r requirements-test.txt`).
5. **Step 5:** Run Ruff lint and format check (`ruff check .` and `ruff format --check .`).
6. **Step 6:** Synthesize test corpus (`python tests/data/corpus/generate_corpus.py`).
7. **Step 7:** Run full Pytest suite (`pytest tests/ -v`).

---

*Testing analysis: 2026-10-13*
*Update after test suite changes*
