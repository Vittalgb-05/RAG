# Testing Patterns

**Analysis Date:** 2026-10-12

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt:2`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- Linter gate runs before tests in CI (see CI section)

**Assertion Library:**
- Plain `assert` with `pytest.raises(..., match=...)` for error contracts. No `unittest.TestCase` classes (one exception: `DummyProvider` helper classes defined inline in test modules, e.g. `tests/test_concurrency_lock.py`).

**Run Commands:**
```bash
pytest tests/ -v              # Run full suite (213 tests, ~24s)
pytest tests/test_litellm_provider.py -v   # Single suite
pytest tests/test_cloud_privacy.py -v      # Privacy suite
pytest tests/ --collect-only -q            # Inventory check (expect 213)
ruff check .                  # Lint gate (must pass before pytest in CI)
ruff format --check .         # Format gate (46 files)
python tests/data/corpus/generate_corpus.py  # Regenerate synthetic PDFs (CI does this first)
```

## Test File Organization

**Location:**
- Separate `tests/` directory mirroring root modules: `tests/test_<module>.py` ↔ `<module>.py`. No co-located tests. Shared fixtures in `tests/conftest.py`. `tests/__init__.py` present. Corpus generator + generated PDFs in `tests/data/corpus/`.

**Naming:**
- `test_<module>.py` files; `test_<behavior>[_<condition>]` functions with docstrings citing requirement IDs (e.g. `test_consent_gate_blocks_generation_by_default` cites `INF-04, D1` in `tests/test_litellm_provider.py:26`; privacy tests cite `UI-04, INF-03, INF-04` in `tests/test_cloud_privacy.py:1`).

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                        # 5 shared fixtures (see Seams)
├── test_cache_invalidation.py         # 6
├── test_citation_validator.py         # 11
├── test_cloud_privacy.py              # 8  (Phase-7 privacy invariants)
├── test_concurrency_lock.py           # 8
├── test_doc_store.py                  # 15
├── test_docling_reader.py             # 7
├── test_hybrid_retriever.py           # 14
├── test_litellm_provider.py           # 11 (Phase-7 adapter)
├── test_llama_cpp_provider.py         # 12
├── test_local_embedding.py            # 3
├── test_local_llm.py                  # 12
├── test_main_ui.py                    # 5  (UI data-structure contracts, no live Streamlit)
├── test_model_provider.py             # 12
├── test_models.py                     # 20
├── test_ocr_fallback.py               # 8
├── test_pdf_reader.py                 # 9
├── test_prompt_budget.py              # 10
├── test_resource_telemetry.py         # 10
├── test_summarizer.py                 # 10
├── test_upload_validation.py          # 8
├── test_vector_index.py               # 7
├── test_visual_analyzer.py            # 7
└── data/corpus/
    ├── generate_corpus.py             # reportlab generator, 6 PDFs
    ├── clean_digital.pdf              # 20-page digital baseline
    ├── chart_diagram.pdf
    ├── dense_table.pdf
    ├── multi_column.pdf
    ├── scanned_sample.pdf
    └── corrupt_invalid.pdf            # negative-path fixture
TOTAL: 213 collected (pytest --collect-only, 2026-10-12)
```

- Note: `07-02-SUMMARY.md` records 210/210 at plan-07-02 completion; `07-REVIEW-FIX.md` records 213/213 after the 3 review-regression tests were added (`test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode`, `test_ai_model_set_cloud_mode_idempotent_preserves_connections`, `test_per_provider_api_key_lookup`). Current disk state is **213 passed in ~24s** (verified 2026-10-12).

## Test Structure

**Suite Organization:**
```python
"""Unit tests for LiteLLMProvider and cloud privacy consent gating (INF-04, UI-04)."""  # header cites reqs

from unittest.mock import MagicMock
import pytest

from litellm_provider import LiteLLMProvider  # system under test, top-level import

class MockChoice: ...       # minimal SDK shape doubles, module-local
class MockDelta: ...
class MockCompletionResponse: ...

def test_consent_gate_blocks_generation_by_default() -> None:
    """Verify that unconsented provider calls immediately raise PermissionError (INF-04, D1)."""
    provider = LiteLLMProvider(api_key="mock-key", user_consented=False)
    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        provider.generate_text("Explain quantum computing")
```

**Patterns:**
- One behavior per function; docstring states the contract + requirement tag. Functions are typed `-> None`.
- Setup inline (construct SUT with mock literals like `api_key="mock-key"`), no class-based grouping except in `tests/test_concurrency_lock.py` (`DummyProvider`) and `tests/conftest.py:MockLlamaCppProvider`.
- Teardown via `provider.close()` / `model.close()` / `retriever.close()` at test end (connection-pool hygiene mirrors production `set_cloud_mode` discipline).
- Assertion pattern: direct state asserts (`assert caps.is_local is True`), `pytest.raises(..., match=...)` for every documented error contract, `is`-identity asserts for idempotence (`assert model.provider is initial_provider`).

## Mocking

**Framework:** `unittest.mock.MagicMock` + pytest `monkeypatch` fixture. `httpx.MockTransport` for the llama.cpp HTTP seam (`tests/test_llama_cpp_provider.py`).

**Patterns:**
```python
# SDK function swap (LiteLLM seam) — tests/test_litellm_provider.py:48-54
import litellm
mock_completion = MagicMock(return_value=MockCompletionResponse("Consented response"))
monkeypatch.setattr(litellm, "completion", mock_completion)

# Streaming seam — tests/test_litellm_provider.py:159
monkeypatch.setattr(litellm, "completion", MagicMock(return_value=iter(stream_chunks)))

# Missing-dependency seam — tests/test_litellm_provider.py:80-89
monkeypatch.setattr(litellm_provider, "litellm", None)

# Env/secret seam — tests/test_litellm_provider.py:60-63
monkeypatch.delenv("GROQ_API_KEY", raising=False)
monkeypatch.setattr("streamlit.secrets", {}, raising=False)

# Socket-egress guard (INF-03 invariant) — tests/test_cloud_privacy.py:60-64
def guarded_create_connection(*args, **kwargs):
    raise ConnectionRefusedError("Outbound network egress strictly forbidden during local ingestion (INF-03).")
monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
```

**Shared seams (`tests/conftest.py`, 161 lines):**
- `fake_env_groq_key` — `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")`.
- `mock_groq_client` — patches `local_llm.Groq` with a `MagicMock` whose `chat.completions.create` yields 5 canned `delta.content` chunks (`"This is a grounded answer."`).
- `mock_sentence_transformer` — patches `local_embedding.SentenceTransformer`; deterministic 384-dim L2-normalised `float32` vectors from text length (zero GPU, zero download, fully offline).
- `sample_pdf_path` — `tests/data/corpus/clean_digital.pdf` path.
- `mock_llama_provider` — full in-memory `BaseModelProvider` (`MockLlamaCppProvider`): `check_health`, `get_capabilities` (`qwen3-vl-2b`, ctx 4096, vision, local, streaming), `generate_text`, `stream_text` (records every call in `stream_calls` for prompt-assembly assertions), `analyze_image`. Used across `tests/test_local_llm.py` (7+ tests via `AiModel(provider=mock_llama_provider)`), `tests/test_concurrency_lock.py`, `tests/test_local_llm.py:147`.

**What to Mock:**
- All network: `litellm.completion`, `groq.Groq`, `httpx` transport, `socket.create_connection`.
- All heavy local models: `SentenceTransformer` (always via `mock_sentence_transformer`), llama-server HTTP (via `httpx.MockTransport` or `mock_llama_provider`).
- Env/secrets: `monkeypatch.setenv` / `delenv`, `st.session_state` fakes (`FakeSessionState(dict)` in `tests/test_cloud_privacy.py:233-242`), `streamlit.secrets`.
- Filesystem isolation: pytest `tmp_path` for `DocStore` SQLite files and `HybridRetriever` LanceDB dirs (`tests/test_doc_store.py`, `tests/test_cloud_privacy.py:75`).

**What NOT to Mock:**
- Pure logic under test: chunking, citation regex, prompt budgeting, BM25 fallback, Pydantic validation, consent state machine transitions.
- Real generated PDFs: `tests/test_pdf_reader.py` and `tests/test_upload_validation.py` read the actual synthetic corpus (including `corrupt_invalid.pdf` for negative paths).
- Real SQLite (`DocStore`) and real LanceDB-or-fallback persistence (`HybridRetriever`) against `tmp_path` — these are integration-grade.

## Fixtures and Factories

**Test Data:**
```python
# Deterministic embedding double — tests/conftest.py:59-74
def mock_encode(texts, normalize_embeddings=True, **kwargs):
    vec = np.zeros(384, dtype=np.float32)
    vec[0] = 1.0 + (len(t) % 10) * 0.1
    ...
```

**Location:**
- Shared doubles: `tests/conftest.py` (auto-discovered, no imports needed).
- Module-local doubles: `MockChoice`/`MockDelta`/`MockCompletionResponse` (`tests/test_litellm_provider.py:11-23`), `DummyProvider` (`tests/test_concurrency_lock.py`), `FakeSessionState` (`tests/test_cloud_privacy.py:233`).
- Binary fixtures: `tests/data/corpus/*.pdf` (generated, committed; CI regenerates via `python tests/data/corpus/generate_corpus.py`).

## Coverage

**Requirements:** No enforced threshold (no `fail_under`, no coverage config in `pyproject.toml`). Verification is pass-rate based: 213/213 per `07-REVIEW-FIX.md` and current disk run.

**View Coverage:**
```bash
# No coverage plugin configured; nearest equivalents:
pytest tests/ -v                       # full pass-rate report
pytest tests/ --collect-only -q        # 213-test inventory
ruff check . && ruff format --check .  # static gates (CI runs these first)
```

## Test Types

**Unit Tests:**
- Scope: every module has a suite; pure functions, Pydantic schemas (`tests/test_models.py`, 20 tests — largest suite), provider contracts (`tests/test_model_provider.py`, 12), budget/validation/citation logic. Offline by construction (mocked SDKs, mocked models).

**Integration Tests:**
- `tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` — real `LocalEmbedding` + real `HybridRetriever` (LanceDB on `tmp_path`) under a `socket.create_connection` kill-switch asserting zero egress across embed → index → hybrid search.
- `tests/test_cloud_privacy.py::test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` — `VisualAnalyzer` with a consented cloud provider injected; asserts `analyze_image` is never invoked and output degrades to `"vision analysis unsupported"` (CR-01/IN-02 regression test from `07-REVIEW.md`).
- `tests/test_doc_store.py` (15 tests) — real SQLite roundtrips, unique-violation, interleaved-instance (R1) checks on `tmp_path`.
- `tests/test_hybrid_retriever.py` (14 tests) — persistent store + CPU embedding pipeline (`RETR-01, RETR-02`).

**E2E Tests:**
- Not used. `tests/test_main_ui.py` (5 tests) covers only UI data-structure contracts (chat-turn schema, evidence-drawer card formatting, snippet/bbox shapes) without launching Streamlit. No Playwright/Selenium, no `streamlit run` harness.

## Common Patterns

**Async Testing:**
- Not applicable — codebase is synchronous; streaming is via sync generators (`yield`), consumed with `list(provider.stream_text(...))` in tests (`tests/test_litellm_provider.py:167`, `tests/test_cloud_privacy.py:34`).

**Error Testing:**
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):   # consent gate
with pytest.raises(NotImplementedError, match="Vision analysis is not supported"):  # non-vision model
with pytest.raises(ValueError, match="image_bytes cannot be empty"):       # empty input
with pytest.raises(RuntimeError, match="Cloud provider generation error"): # wrapped SDK failure
```

**Parametric/matrix Testing:**
```python
# Provider switching matrix — tests/test_cloud_privacy.py:132-148
providers = [
    ("groq/llama-3.3-70b-versatile", 131072, False),
    ("openai/gpt-4o-mini", 128000, True),
    ("anthropic/claude-3-5-haiku-20241022", 200000, True),
]
for model_name, expected_ctx, expected_vision in providers: ...
```

**Capability snapshot Testing:**
- Every provider suite asserts the full `ProviderCapabilities` tuple (`model_name`, `context_window`, `supports_vision`, `is_local`, `supports_streaming`) so contract drift fails loudly (`tests/test_litellm_provider.py:92-109`, `tests/test_cloud_privacy.py:140-147`).

## CI

**Pipeline:** `.github/workflows/ci.yml` — job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggers on `push`/`pull_request` to `main`. Steps in order:
1. `actions/checkout@v4`, `setup-python@v5` (3.11, pip cache).
2. `pip install -r requirements.txt` + `pip install -r requirements-test.txt`.
3. `ruff check .` then `ruff format --check .` (fail-fast lint gates).
4. `python tests/data/corpus/generate_corpus.py` (corpus regeneration — tests never depend on stale committed PDFs).
5. `pytest tests/ -v`.

## Test Coverage Gaps

**E2E / live-UI gap:**
- What's not tested: actual Streamlit rendering, `@st.dialog` consent flow, `st.toggle(key="cloud_mode_toggle")` dismissal sync (WR-03 fix is code-only), egress chips in a running browser. `tests/test_main_ui.py` asserts dict shapes only.
- Risk: widget-state regressions invisible to CI. Priority: Medium.

**Socket-guard narrowness:**
- What's not tested: the INF-03 guard patches only `socket.create_connection` (`tests/test_cloud_privacy.py:64`). Direct `socket.socket.connect`, `httpx` calls, or `urllib3` paths would bypass the kill-switch unnoticed.
- Risk: false confidence in "zero egress" if a dependency dials out via another syscall. Priority: Medium. Fix path: block at `socket.socket` level or run the invariant under `pytest-socket --block`.

**No GPU/VRAM test in CI:**
- What's not tested: 4 GB VRAM envelope, llama-server health/latency, OCR model load. CI is CPU-only `ubuntu-latest`; `mock_sentence_transformer` and `httpx.MockTransport` hide all accelerator behavior.
- Risk: perf/VRAM regressions undetected. Priority: Low (covered out-of-band by `scripts/profile_resources.py` / `scripts/benchmark_baseline.py`, which are manual harnesses, not CI gates).

**Schema-only chat-turn test:**
- What's not tested: `test_chat_turn_metadata_records_locality_and_cloud_egress` (`tests/test_cloud_privacy.py:105-129`) builds plain dicts and asserts their own literals — it does not exercise `main.py` turn construction, so drift between the test and the real schema passes silently.
- Risk: egress chips showing wrong locality. Priority: Low. Fix path: import the real turn-builder from `main.py` (requires Streamlit test harness).

**Thin embedding suite:**
- What's not tested: `tests/test_local_embedding.py` has only 3 tests (smallest suite); real `SentenceTransformer` load path, `_embed_one` normalisation edge cases, and `get_context` truncation are lightly covered.
- Risk: Low. Priority: Low.

---

*Testing analysis: 2026-10-12 (suite 213/213 verified on disk; 210/210 figure in 07-02-SUMMARY.md predates the 3 review-regression tests documented in 07-REVIEW.md / 07-REVIEW-FIX.md)*
