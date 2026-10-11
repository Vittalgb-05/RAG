# Testing Patterns

**Analysis Date:** 2026-10-11

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt`)
- Config: `pyproject.toml` → `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`

**Assertion Library:**
- Plain `assert` statements with `pytest.raises(..., match=...)` and `pytest.approx(...)`. No third-party assertion library.

**Run Commands:**
```bash
# Generate the synthetic corpus first (required by several tests)
python tests/data/corpus/generate_corpus.py

pytest tests/ -v          # Run all tests
pytest tests/test_doc_store.py -v   # Single module
pytest -k prompt_budget -v          # Substring match
ruff check . && ruff format --check .   # Lint/format gate (CI)
```

**Global warning filters** (set in `pyproject.toml`): `ignore::UserWarning`, `ignore::DeprecationWarning`.

## Test File Organization

**Location:**
- Separate `tests/` directory mirroring root modules 1:1. `tests/__init__.py` makes it a package.

**Naming:**
- `test_<module>.py`; one file per root module (`tests/test_doc_store.py`, `tests/test_vector_index.py`, `tests/test_llama_cpp_provider.py`).

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                 # fixtures + mocking seams
├── test_doc_store.py           # 304 lines
├── test_models.py              # 297 lines
├── test_llama_cpp_provider.py  # 230 lines (httpx.MockTransport)
├── test_pdf_reader.py          # 202 lines (requires generated corpus)
├── test_local_llm.py           # 141 lines
├── test_model_provider.py      # 126 lines
├── test_prompt_budget.py       # 122 lines
├── test_upload_validation.py   # 111 lines (requires generated corpus)
├── test_vector_index.py        # 109 lines
├── test_local_embedding.py     #  45 lines
└── data/corpus/generate_corpus.py
```

## Test Structure

**Suite Organization:**
- Module-level free functions named `test_*` (no test classes), each with a one-line docstring stating the guarantee. Example from `tests/test_vector_index.py`:

```python
def test_cosine_distance_math():
    """Test exact cosine distance for identical, orthogonal, and opposite vectors."""
    idx = VectorIndex(distance_metric="cosine")
    dist_same = idx._cosine_distance([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
    assert pytest.approx(dist_same, abs=1e-5) == 0.0
```

**Patterns:**
- Fixture injection by parameter name (`def test_...(tmp_path, sample_pdf_path):`).
- Arrange-heavy tracer tests exercise a full slice end-to-end — `test_tracer_chunk_to_store_roundtrip` (`tests/test_models.py:155`) runs real PDF extraction → `Chunk` → SQLite insert → read-back.
- Temporary filesystem state via pytest's built-in `tmp_path`; never write into the repo.
- Floating-point comparisons always use `pytest.approx`.
- Concern IDs embedded in test names/docstrings tie back to review findings (`test_corrupt_invalid_rejected_WR07`, `test_two_instance_interleave_R1`, `test_cache_dir_for_traversal_rejected` for `IN-04`).

## Mocking

**Framework:** `unittest.mock` (`MagicMock`, `patch.object`) plus pytest `monkeypatch` and `httpx.MockTransport`.

**Patterns:**
```python
# HTTP mocking without a server — tests/test_llama_cpp_provider.py
def handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path == "/v1/chat/completions"
    return httpx.Response(200, json={"choices": [{"message": {"content": "Generated reply."}}]})

transport = httpx.MockTransport(handler)
provider = LlamaCppProvider(transport=transport)
result = provider.generate_text(prompt="Explain quantum physics", ...)
provider.close()
```

```python
# Class-level seam via monkeypatch — tests/test_local_llm.py
monkeypatch.setattr(LlamaCppProvider, "check_health", lambda self: unreachable_status)
model = AiModel()          # must NOT raise
assert model.check_health().status == "unreachable"
```

```python
# Spy forwarding verification — tests/test_local_embedding.py
with patch.object(embedding, "search", wraps=embedding.search) as spy_search:
    context = embedding.get_context("memory management", k=10)
    spy_search.assert_called_once_with("memory management", k=10)
```

**What to Mock:**
- All network I/O (`httpx.MockTransport`) and all model/GPU work (`mock_sentence_transformer`, `mock_llama_provider`).
- Provider health/selection seams (`monkeypatch.setattr(LlamaCppProvider, "check_health", ...)`).
- Environment/secrets (`monkeypatch.delenv("GROQ_API_KEY")`, `monkeypatch.setattr("streamlit.secrets", {})`).

**What NOT to Mock:**
- Pydantic validation, SQLite (`DocStore` uses real `tmp_path` databases), vector math, and text chunking are all exercised for real.
- `PdfReader` is run against real generated PDFs rather than stubbed, except when a specific failure is injected (`test_page_failure_isolated` monkeypatches one page's `extract_text`).

## Fixtures and Factories

**Test Data:**
```python
# tests/conftest.py
@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    """Returns deterministic 384-dimensional normalized float32 vectors."""
    ...
    monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name: mock_model)
    return mock_model

@pytest.fixture
def mock_llama_provider():
    """Healthy mock provider conforming to BaseModelProvider; records stream_calls."""
    ...
```

**Location:**
- `tests/conftest.py`: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`.
- PDF corpus factories: `tests/data/corpus/generate_corpus.py` (`generate_clean_digital_pdf`, `generate_dense_table_pdf`, …). **Caution:** `fake_env_groq_key` and `mock_groq_client` are currently unused and `mock_groq_client` patches `local_llm.Groq`, which no longer exists after provider extraction (see CONCERNS.md).

## Coverage

**Requirements:** None enforced — no `pytest-cov`, no coverage config, no threshold.

**View Coverage:**
```bash
pytest --cov=. --cov-report=term-missing   # pytest-cov not installed by default
```

## Test Types

**Unit Tests:**
- The whole suite is unit-scoped but some tests cross one real boundary (SQLite, PDF parsing) for tracer value.
- Fully offline: no GPU, no network, no API keys required (`tests/conftest.py:1-4`).

**Integration Tests:**
- The tracer test in `tests/test_models.py:155` and the restart-restore test in `tests/test_doc_store.py:176` integrate 3–4 real modules.

**E2E Tests:**
- Not used. There are no Streamlit UI tests; `main.py` is only exercised indirectly through the modules it calls.

## Common Patterns

**Error Testing:**
```python
with pytest.raises(ValueError, match="Not a valid PDF: missing %PDF header"):
    validate_pdf_bytes(raw_bytes, "corrupt_invalid.pdf")

with pytest.raises(ValueError, match="Inconsistent vector dimension"):
    idx.add_vector([1.0, 2.0], {"content": "short"})
```

**Streaming/Generator Testing:**
```python
tokens = list(model.ask_a_question_from_pdf_stream(pdf_path="", prompt="...", local_embedding=mock_embedding))
assert tokens == ["This ", "is ", "a ", "grounded ", "answer."]
```

**Corpus-Dependent Tests:**
- `tests/test_pdf_reader.py`, `tests/test_upload_validation.py`, and `tests/test_models.py` assume `tests/data/corpus/*.pdf` exist; run `python tests/data/corpus/generate_corpus.py` first (CI does this before pytest).

## CI Enforcement

`.github/workflows/ci.yml` runs, in order: install `requirements.txt` + `requirements-test.txt` → `ruff check .` → `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`. A lint or format failure blocks the test step.

---

*Testing analysis: 2026-10-11*
