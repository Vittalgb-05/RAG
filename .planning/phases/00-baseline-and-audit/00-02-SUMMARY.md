---
phase: 00-baseline-and-audit
plan: 02
subsystem: testing
tags:
  - pytest
  - conftest
  - mocks
  - benchmarking
  - github-actions
  - ci
requires:
  - phase: 00-01
    provides: Test corpus and unit test foundations for vector search and PDF chunking
provides:
  - Shared Pytest mocking seams for Groq client and SentenceTransformer
  - Unit tests for LocalEmbedding and AiModel
  - Baseline performance benchmark script and empirical JSON metrics
  - GitHub Actions CI workflow running ruff and pytest on Python 3.11
affects:
  - 01-canonical-document-models
  - 02-local-inference
  - 04-persistent-retrieval
  - 06-performance-optimization
tech-stack:
  added:
    - pytest-mock
    - psutil
    - ruff
  patterns:
    - Offline mock fixtures for external inference SDKs
    - Empirical memory and latency profiling script
    - CI lint and test synchronization
key-files:
  created:
    - tests/conftest.py
    - tests/test_local_embedding.py
    - tests/test_local_llm.py
    - scripts/benchmark_baseline.py
    - .planning/research/BASELINE_BENCHMARK.json
    - pyproject.toml
    - .github/workflows/ci.yml
  modified:
    - main.py
key-decisions:
  - "Configured pyproject.toml with ruff lint settings tailored for project structure (ignoring line length in prompts)."
  - "Created conftest.py mocking seams to enable 100% offline unit tests without Groq credentials or GPU allocations."
  - "Captured empirical baseline showing pure Python vector scan takes >50ms at 1,000 vectors, proving necessity of LanceDB in Phase 4."
patterns-established:
  - "Pattern: GitHub Actions CI workflow runs ruff and pytest on every push and pull request."
requirements-completed:
  - QUAL-02
  - QUAL-03
  - QUAL-04
duration: 12min
completed: 2026-10-10
---

# Phase 0: Plan 02 Summary

**Shared Pytest mock fixtures, unit tests for LocalEmbedding and AiModel, baseline benchmarking script, and GitHub Actions CI workflow established.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-10-10T19:25:00Z
- **Completed:** 2026-10-10T19:37:00Z
- **Tasks:** 4
- **Files modified:** 8

## Accomplishments

1. **Shared Test Fixtures & Mock Seams:** Implemented `tests/conftest.py` with `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, and `fake_env_groq_key` ensuring test suite runs 100% offline.
2. **LocalEmbedding & AiModel Unit Tests:** 6 unit tests covering prompt assembly, streaming generator yield, batch index building, context formatting, and missing API key exception handling (`CONCERNS.md #1`).
3. **Empirical Baseline Benchmarking:** Implemented `scripts/benchmark_baseline.py` and produced `.planning/research/BASELINE_BENCHMARK.json`:
   - Extraction: 20 pages in 0.052s (~2.6 ms/page)
   - Chunks: 20 chunks generated
   - CPU Embeddings: 46.39 MB memory increase, ~13 ms/chunk
   - Vector Scan: 8.2 ms (100 vecs), 37.0 ms (500 vecs), 51.9 ms (1,000 vecs)
4. **GitHub Actions CI Workflow:** Configured `.github/workflows/ci.yml` running `ruff check .`, corpus generation, and `pytest tests/ -v` on Python 3.11.
5. **Full Test Suite Verification:** All 17 unit tests across all test modules passing in 9.43s.

## Task Commits

1. **Task 1 & 2: Mock fixtures and LocalEmbedding/AiModel unit tests** - `bc9108d` (test)
2. **Task 3 & 4: Benchmarking script, pyproject.toml, and CI workflow** - `2128966` (ci)

## Files Created/Modified

- `tests/conftest.py` - Shared mock fixtures for Groq and SentenceTransformer
- `tests/test_local_embedding.py` - Unit tests for LocalEmbedding
- `tests/test_local_llm.py` - Unit tests for AiModel prompt assembly and streaming
- `scripts/benchmark_baseline.py` - Reproducible baseline benchmark runner
- `.planning/research/BASELINE_BENCHMARK.json` - Empirical baseline performance data
- `pyproject.toml` - Ruff linter and pytest configuration
- `main.py` - Cleaned unused import and redundant f-string prefix
- `.github/workflows/ci.yml` - GitHub Actions CI workflow

## Decisions Made

- Configured `pyproject.toml` to ignore `E501` (line length in prompt strings) and `W291/W293` (whitespace in legacy docstrings) while enforcing all `E` and `F` error rules.
- Established CPU-pinned SentenceTransformer benchmarking to set an objective comparison for Phase 4 (LanceDB) and Phase 6 (Performance Optimization).

## Self-Check: PASSED
- `tests/conftest.py`, `tests/test_local_embedding.py`, `tests/test_local_llm.py`, `scripts/benchmark_baseline.py`, and `.github/workflows/ci.yml` exist on disk.
- Commits `bc9108d` and `2128966` recorded in git log.
- 17/17 tests pass.
- Ruff checks pass with 0 errors.
