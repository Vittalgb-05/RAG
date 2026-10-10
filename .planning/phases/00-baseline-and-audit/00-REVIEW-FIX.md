---
phase: 00-baseline-and-audit
reviewed: 2026-10-10T20:00:00Z
fixed: 2026-10-11T01:50:00Z
iteration: 1
findings_in_scope: 12
fixed: 12
skipped: 0
status: clean
---

# Phase 00 (Baseline & Audit) — Code Review Fix Report

**Phase:** 00-baseline-and-audit  
**Status:** Clean (All in-scope findings resolved)  
**Iterations:** 1  
**Fixed:** 12 findings (8 Warnings, 4 Info / Hardening items)  
**Skipped:** 0  

## Fixed Findings

### WR-01: Deduplicate benchmark batch sizes and avoid key collisions
- **File:** `scripts/benchmark_baseline.py:79-87`
- **Fix:** Used set comprehension and sorting `sorted(list({b for b in raw_batches if 0 < b <= len(chunk_texts)}))` ensuring distinct batch sizes `[5, 10, 20]`. Re-ran benchmark to update `.planning/research/BASELINE_BENCHMARK.json`.

### WR-02: Pin numpy in dependencies
- **File:** `requirements.txt`, `requirements-test.txt`
- **Fix:** Explicitly added `numpy>=1.26.0,<3.0.0` to `requirements.txt` and created `requirements-test.txt` with pinned test tools (`pytest`, `reportlab`, `ruff`, `psutil`).

### WR-03: Assert chunk overlap preservation
- **File:** `tests/test_pdf_reader.py:30-67`
- **Fix:** Added multi-chunk single-page synthetic test asserting that consecutive chunks on the same page share overlapping text tokens (`shared_words >= 3`).

### WR-04: Grounding and Conversation History assertions in AiModel test
- **File:** `tests/test_local_llm.py:21-65`
- **Fix:** Added assertions verifying `"Conversation History"` and `"does not contain information"` in system prompt. Added `st.secrets` monkeypatch in `test_ai_model_missing_key_raises`.

### WR-05: LocalEmbedding get_context search spy and k=10 assertion
- **File:** `tests/test_local_embedding.py:31-48`
- **Fix:** Added `unittest.mock.patch.object` spy on `embedding.search` asserting `k=10` is passed by `get_context` and verifying delimiter formatting.

### WR-06: Remove test lint exemptions in pyproject.toml
- **File:** `pyproject.toml:9-11`
- **Fix:** Removed `"tests/*" = ["F401", "F841"]` per-file-ignores. Cleaned up unused imports and variables across all tests.

### WR-07: Corpus test coverage for corrupt, dense table, and chart PDFs
- **File:** `tests/test_pdf_reader.py:78-115`
- **Fix:** Added `test_pdf_reader_corrupt_pdf_rejects` (asserting `pytest.raises(Exception)` on `corrupt_invalid.pdf`), `test_pdf_reader_dense_table` (verifying table headers and numeric cells), and `test_pdf_reader_chart_diagram` (verifying diagram text captions).

### WR-08: CI workflow hardening and format check
- **File:** `.github/workflows/ci.yml:24-35`
- **Fix:** Changed CI dependency installation to use pinned `requirements-test.txt` and added `ruff format --check .` alongside `ruff check .`.

### IN-01: Remove unused imports in generate_corpus.py
- **File:** `tests/data/corpus/generate_corpus.py:6,18`
- **Fix:** Removed unused `import os` and `ParagraphStyle`.

### IN-03: Neutralize mock API key in conftest.py
- **File:** `tests/conftest.py:16`
- **Fix:** Replaced pseudo-secret prefix with `test-key-not-a-secret-mock-value`.

### IN-07: Add zero-division guards in benchmark_baseline.py
- **File:** `scripts/benchmark_baseline.py:48,90`
- **Fix:** Guarded `extraction_ms_per_page` with `max(1, total_pages)` and `ms_per_chunk` with `b > 0` check.

### Additional Maintenance: .gitignore hardening
- **File:** `.gitignore`
- **Fix:** Added ignores for `.pytest_cache/`, `.ruff_cache/`, `*.pyc`, `data/`, `build/`, `dist/`.

## Verification Results
- `pytest tests/ -v`: 20/20 passed (100% pass rate)
- `ruff check .`: 0 lint errors
- `ruff format --check .`: 0 format discrepancies
- `python scripts/benchmark_baseline.py`: successfully generated complete metrics report
