# Testing Patterns

**Analysis Date:** 2026-10-12

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt:2`; locked `pytest==9.0.3` in `requirements-lock.txt`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- Linter gate runs before tests in CI (see CI section)

**Assertion Library:**
- Plain `assert` with `pytest.raises(..., match=...)` for error contracts. No `unittest.TestCase` classes (one exception: `DummyProvider` helper classes defined inline in test modules, e.g. `tests/test_concurrency_lock.py`).

**Run Commands:**
```bash
pytest tests/ -v              # Run full suite (218 tests, ~26-29s)
pytest tests/test_llama_cpp_provider.py -v   # Loopback/SSRF suite (15 tests)
pytest tests/test_resource_telemetry.py -v   # TTL/caching suite (11 tests)
pytest tests/test_main_ui.py -v              # UI contracts incl. Clear-All cloud test (6 tests)
pytest tests/test_cloud_privacy.py -v        # Privacy suite (8 tests)
pytest tests/ --collect-only -q              # Inventory check (expect 218)
ruff check .                  # Lint gate (must pass before pytest in CI)
ruff format --check .         # Format gate (46 files)
python tests/data/corpus/generate_corpus.py  # Regenerate synthetic PDFs (CI does this first)
```

## Test File Organization

**Location:**
- Separate `tests/` directory mirroring root modules: `tests/test_<module>.py` ↔ `<module>.py`. No co-located tests. Shared fixtures in `tests/conftest.py` (165 lines). `tests/__init__.py` present. Corpus generator + generated PDFs in `tests/data/corpus/`.

**Naming:**
- `test_<module>.py` files; `test_<behavior>[_<condition>]` functions with docstrings citing requirement IDs (e.g. `test_consent_gate_blocks_generation_by_default` cites `INF-04, D1` in `tests/test_litellm_provider.py:26`; privacy tests cite `UI-04, INF-03, INF-04` in `tests/test_cloud_privacy.py:1`). Phase-8 tests cite `SEC-01` (loopback), `TEL-01` (TTL), `WR-02` (Clear-All cloud reset).

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                        # 4 shared fixtures (see Seams)
├── test_cache_invalidation.py         # 6
├── test_citation_validator.py         # 11
├── test_cloud_privacy.py              # 8  (Phase-7 privacy invariants)
├── test_concurrency_lock.py           # 8
├── test_doc_store.py                  # 15
├── test_docling_reader.py             # 7
├── test_hybrid_retriever.py           # 14
├── test_litellm_provider.py           # 11 (Phase-7 adapter)
├── test_llama_cpp_provider.py         # 15 (12 base + 3 SEC-01 loopback, Phase-8)
├── test_local_embedding.py            # 3
├── test_local_llm.py                  # 12
├── test_main_ui.py                    # 6  (5 base + 1 WR-02 Clear-All cloud test, Phase-8)
├── test_model_provider.py             # 12
├── test_models.py                     # 20 (largest suite)
├── test_ocr_fallback.py               # 8
├── test_pdf_reader.py                 # 9
├── test_prompt_budget.py              # 10
├── test_resource_telemetry.py         # 11 (10 base + 1 TEL-01 TTL test, Phase-8)
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
TOTAL: 218 collected (pytest --collect-only, 2026-10-12; 218 passed in ~28.7s)
```

- History: `07-02-SUMMARY.md` records 210/210; `07-REVIEW-FIX.md` records 213/213 after 3 review-regression tests; `08-01-SUMMARY.md` records **217/217** after the 4 Phase-8 hardening tests (`test_get_gpu_memory_info_ttl_caching` + 3 loopback tests); `08-REVIEW-FIX.md` records **218/218** after `test_clear_all_resets_cloud_posture_and_credentials` (WR-02/IN-02). Current disk state is **218 passed** (verified 2026-10-12).

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

**Phase-8 test shapes (copy for new hardening tests):**
```python
# SEC-01 loopback matrix — tests/test_llama_cpp_provider.py:279-295
def test_endpoint_loopback_accepted_addresses() -> None:
    """Test standard local loopback addresses are accepted by default."""
    accepted = [
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://[::1]:8080",
        "http://127.0.1.1:8080",   # Linux /etc/hosts convention
        "http://127.0.0.2:8080",   # 127.0.0.0/8 block
        "127.0.0.1:8080",          # scheme-less input
    ]
    for url in accepted:
        provider = LlamaCppProvider(base_url=url)
        assert provider.base_url == url.rstrip("/")
        provider.close()

# TEL-01 TTL caching — tests/test_resource_telemetry.py:48-67
def test_get_gpu_memory_info_ttl_caching() -> None:
    clear_gpu_cache()  # reset module TTL state, never touch globals directly
    info1 = get_gpu_memory_info()
    info2 = get_gpu_memory_info()          # cache hit: no second nvidia-smi spawn
    info3 = get_gpu_memory_info(force_refresh=True)  # bypass: re-samples
```

**Patterns:**
- One behavior per function; docstring states the contract + requirement tag (Phase-8: `SEC-01`, `TEL-01`, `WR-02`). Functions are typed `-> None` (except `tests/test_main_ui.py`, which is untyped — match host file).
- Setup inline (construct SUT with mock literals like `api_key="mock-key"`), no class-based grouping except in `tests/test_concurrency_lock.py` (`DummyProvider`) and `tests/conftest.py:MockLlamaCppProvider`.
- Teardown via `provider.close()` / `model.close()` / `retriever.close()` at test end (connection-pool hygiene mirrors production `set_cloud_mode` discipline). TTL tests call `clear_gpu_cache()` at start (`tests/test_resource_telemetry.py:27,30`).
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

# TTL subprocess counting seam — tests/test_resource_telemetry.py (monkeypatched subprocess.run + clear_gpu_cache)
clear_gpu_cache()
info1 = get_gpu_memory_info()
info2 = get_gpu_memory_info()  # assert single spawn
```

**Shared seams (`tests/conftest.py`, 165 lines):**
- `fake_env_groq_key` — `monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")`.
- `mock_groq_client` — patches `groq_provider.Groq` (retargeted per `08-01-SUMMARY.md` TEST-01; previously targeted `local_llm.Groq`) with a `MagicMock` whose `chat.completions.create` yields 5 canned `delta.content` chunks (`"This is a grounded answer."`).
- `mock_sentence_transformer` — patches `local_embedding.SentenceTransformer`; deterministic 384-dim L2-normalised `float32` vectors from text length (zero GPU, zero download, fully offline).
- `sample_pdf_path` — `tests/data/corpus/clean_digital.pdf` path.
- `mock_llama_provider` — full in-memory `BaseModelProvider` (`MockLlamaCppProvider`): `check_health`, `get_capabilities` (`qwen3-vl-2b`, ctx 4096, vision, local, streaming), `generate_text`, `stream_text` (records every call in `stream_calls` for prompt-assembly assertions), `analyze_image`. Used across `tests/test_local_llm.py` (7+ tests via `AiModel(provider=mock_llama_provider)`), `tests/test_concurrency_lock.py`, `tests/test_local_llm.py:147`.

**What to Mock:**
- All network: `litellm.completion`, `groq_provider.Groq`, `httpx` transport, `socket.create_connection`, `subprocess.run` (nvidia-smi in TTL tests).
- All heavy local models: `SentenceTransformer` (always via `mock_sentence_transformer`), llama-server HTTP (via `httpx.MockTransport` or `mock_llama_provider`).
- Env/secrets: `monkeypatch.setenv` / `delenv`, `st.session_state` fakes (`FakeSessionState(dict)` in `tests/test_cloud_privacy.py:233-242`; plain-dict `mock_session` in `tests/test_main_ui.py:159-185`), `streamlit.secrets`.
- Filesystem isolation: pytest `tmp_path` for `DocStore` SQLite files and `HybridRetriever` LanceDB dirs (`tests/test_doc_store.py`, `tests/test_cloud_privacy.py:75`).
- Module TTL state: reset via `clear_gpu_cache()`, never by assigning `resource_telemetry._LAST_GPU_SAMPLE*` directly.

**What NOT to Mock:**
- Pure logic under test: chunking, citation regex, prompt budgeting, BM25 fallback, Pydantic validation, consent state machine transitions, `ipaddress.is_loopback` branching (loopback tests assert real validation outcomes).
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
- Module-local doubles: `MockChoice`/`MockDelta`/`MockCompletionResponse` (`tests/test_litellm_provider.py:11-23`), `DummyProvider` (`tests/test_concurrency_lock.py`), `FakeSessionState` (`tests/test_cloud_privacy.py:233`), plain-dict `mock_session` (`tests/test_main_ui.py:159`).
- Binary fixtures: `tests/data/corpus/*.pdf` (generated, committed; CI regenerates via `python tests/data/corpus/generate_corpus.py`).

## Coverage

**Requirements:** No enforced threshold (no `fail_under`, no coverage config in `pyproject.toml`). Verification is pass-rate based: 218/218 per `08-REVIEW-FIX.md` and current disk run.

**View Coverage:**
```bash
# No coverage plugin configured; nearest equivalents:
pytest tests/ -v                       # full pass-rate report
pytest tests/ --collect-only -q        # 218-test inventory
ruff check . && ruff format --check .  # static gates (CI runs these first)
```

## Test Types

**Unit Tests:**
- Scope: every module has a suite; pure functions, Pydantic schemas (`tests/test_models.py`, 20 tests — largest suite), provider contracts (`tests/test_model_provider.py`, 12), budget/validation/citation logic. Offline by construction (mocked SDKs, mocked models).
- Phase-8 hardening units: `test_endpoint_loopback_validation_rejected` / `test_endpoint_loopback_validation_allowed_with_flag` / `test_endpoint_loopback_accepted_addresses` (`tests/test_llama_cpp_provider.py:262-295`, SEC-01); `test_get_gpu_memory_info_ttl_caching` (`tests/test_resource_telemetry.py:48-67`, TEL-01); `test_clear_all_resets_cloud_posture_and_credentials` (`tests/test_main_ui.py:159-185`, WR-02/IN-02).

**Integration Tests:**
- `tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` — real `LocalEmbedding` + real `HybridRetriever` (LanceDB on `tmp_path`) under a `socket.create_connection` kill-switch asserting zero egress across embed → index → hybrid search.
- `tests/test_cloud_privacy.py::test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` — `VisualAnalyzer` with a consented cloud provider injected; asserts `analyze_image` is never invoked and output degrades to `"vision analysis unsupported"` (CR-01/IN-02 regression test from `07-REVIEW.md`).
- `tests/test_doc_store.py` (15 tests) — real SQLite roundtrips, unique-violation, interleaved-instance (R1) checks on `tmp_path`.
- `tests/test_hybrid_retriever.py` (14 tests) — persistent store + CPU embedding pipeline (`RETR-01, RETR-02`).

**E2E Tests:**
- Not used. `tests/test_main_ui.py` (6 tests) covers only UI data-structure contracts (chat-turn schema, evidence-drawer card formatting, snippet/bbox shapes, provider-attribute contract, summary-key purge, cloud-posture reset simulation) without launching Streamlit. No Playwright/Selenium, no `streamlit run` harness. The WR-02 test simulates the Clear-All handler on a plain dict rather than driving `main.py` widgets (see gaps).

## Common Patterns

**Async Testing:**
- Not applicable — codebase is synchronous; streaming is via sync generators (`yield`), consumed with `list(provider.stream_text(...))` in tests (`tests/test_litellm_provider.py:167`, `tests/test_cloud_privacy.py:34`).

**Error Testing:**
```python
with pytest.raises(PermissionError, match="Cloud transmission blocked"):   # consent gate
with pytest.raises(NotImplementedError, match="Vision analysis is not supported"):  # non-vision model
with pytest.raises(ValueError, match="image_bytes cannot be empty"):       # empty input
with pytest.raises(ValueError, match="Restricted endpoint"):               # SEC-01 non-loopback (tests/test_llama_cpp_provider.py:262-276)
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

# Loopback acceptance matrix — tests/test_llama_cpp_provider.py:279-295 (SEC-01)
accepted = ["http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080",
            "http://127.0.1.1:8080", "http://127.0.0.2:8080", "127.0.0.1:8080"]
```

**Capability snapshot Testing:**
- Every provider suite asserts the full `ProviderCapabilities` tuple (`model_name`, `context_window`, `supports_vision`, `is_local`, `supports_streaming`) so contract drift fails loudly (`tests/test_litellm_provider.py:92-109`, `tests/test_cloud_privacy.py:140-147`).

## CI

**Pipeline:** `.github/workflows/ci.yml` — job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggers on `push`/`pull_request` to `main`. Steps in order:
1. `actions/checkout@v4`, `setup-python@v5` (3.11, pip cache).
2. `pip install -r requirements.txt` + `pip install -r requirements-test.txt` (float files — **not** the lockfile).
3. `ruff check .` then `ruff format --check .` (fail-fast lint gates).
4. `python tests/data/corpus/generate_corpus.py` (corpus regeneration — tests never depend on stale committed PDFs).
5. `pytest tests/ -v`.

**Lockfile sync (Phase-8 QUAL-02):**
- `requirements-lock.txt` (27 pinned `==` entries, header-commented) is the deterministic production/runbook install path (`README.md:131`, `docs/RUNBOOK.md:48`: `pip install -r requirements-lock.txt`), generated per `08-01-SUMMARY.md` QUAL-02 alongside the `httpx==0.28.1` / `psutil==6.1.1` pins in `requirements.txt`.
- CI intentionally installs the float files and is verified in sync with the lockfile strategy (per `08-01-SUMMARY.md` §5 and `08-REVIEW-FIX.md` §2: "`.github/workflows/ci.yml` verified and passing with lockfile and test suite"). There is no `pip install -r requirements-lock.txt` step and no lockfile-drift check in `ci.yml` — sync is procedural (pin in `requirements.txt`, regenerate lockfile), not enforced. When adding a dependency, update both.
- Static gates at fix time: `ruff check .` 0 errors, `ruff format --check .` 46/46 clean (`08-REVIEW-FIX.md` §2; re-verified 2026-10-12).

## Test Coverage Gaps

**E2E / live-UI gap:**
- What's not tested: actual Streamlit rendering, `@st.dialog` consent flow, `st.toggle(key="cloud_mode_toggle")` dismissal sync (WR-03 fix is code-only), egress chips in a running browser. `tests/test_main_ui.py` asserts dict shapes only — including the new WR-02 test, which replays Clear-All assignments on a plain `mock_session` dict rather than driving `main.py:288-320` widgets (flagged as `IN-02` in `08-REVIEW.md`, closed by the simulation test per `08-REVIEW-FIX.md` IN-02, but still not a widget-level test).
- Risk: widget-state regressions invisible to CI. Priority: Medium.

**Socket-guard narrowness:**
- What's not tested: the INF-03 guard patches only `socket.create_connection` (`tests/test_cloud_privacy.py:64`). Direct `socket.socket.connect`, `httpx` calls, or `urllib3` paths would bypass the kill-switch unnoticed.
- Risk: false confidence in "zero egress" if a dependency dials out via another syscall. Priority: Medium. Fix path: block at `socket.socket` level or run the invariant under `pytest-socket --block`.

**No GPU/VRAM test in CI:**
- What's not tested: 4 GB VRAM envelope, llama-server health/latency, OCR model load. CI is CPU-only `ubuntu-latest`; `mock_sentence_transformer` and `httpx.MockTransport` hide all accelerator behavior. The TEL-01 TTL test mocks `subprocess.run` — no real `nvidia-smi` runs in CI. Concurrent-expiry double-spawn (IN-01 in `08-REVIEW.md`) is fixed by `_SAMPLING_LOCK` double-checked locking (`resource_telemetry.py:50-60`) but has no dedicated concurrency test — only the sequential TTL test.
- Risk: perf/VRAM regressions undetected. Priority: Low (covered out-of-band by `scripts/profile_resources.py` / `scripts/benchmark_baseline.py`, which are manual harnesses, not CI gates).

**Schema-only chat-turn test:**
- What's not tested: `test_chat_turn_metadata_records_locality_and_cloud_egress` (`tests/test_cloud_privacy.py:105-129`) builds plain dicts and asserts their own literals — it does not exercise `main.py` turn construction, so drift between the test and the real schema passes silently.
- Risk: egress chips showing wrong locality. Priority: Low. Fix path: import the real turn-builder from `main.py` (requires Streamlit test harness).

**Thin embedding suite:**
- What's not tested: `tests/test_local_embedding.py` has only 3 tests (smallest suite); real `SentenceTransformer` load path, `_embed_one` normalisation edge cases, and `get_context` truncation are lightly covered.
- Risk: Low. Priority: Low.

**No lockfile-drift gate:**
- What's not tested/enforced: nothing in CI fails if `requirements-lock.txt` drifts from `requirements.txt` (no hash check, no `pip install --constraint` step). Sync relies on the contributor regenerating the lockfile per QUAL-02 procedure.
- Risk: production (`requirements-lock.txt`) silently diverging from CI-tested (`requirements.txt`) versions. Priority: Low. Fix path: add a CI step diffing `pip freeze` against the lockfile or installing with `-c requirements-lock.txt`.

---

*Testing analysis: 2026-10-12 (suite 218/218 verified on disk; 217/217 figure in 08-01-SUMMARY.md predates the WR-02 regression test documented in 08-REVIEW.md / 08-REVIEW-FIX.md)*
