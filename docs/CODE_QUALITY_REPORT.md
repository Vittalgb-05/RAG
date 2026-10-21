# Code Quality Report

**Date:** 2026-10-21
**Scope:** production Python under `core/`, `ingestion/`, `providers/`, `retrieval/`, `ui/`, plus root entry points and tests.
**Result:** healthy for a single-user local application; no blocking lint errors; several maintainability risks remain.

## 1. Size and shape

| Area | Files | Total lines (approx.) |
|---|---:|---:|
| `core/` | 9 | 2,863 |
| `ingestion/` | 5 | 1,435 |
| `retrieval/` | 4 | 1,209 |
| `providers/` | 4 | 1,028 |
| `ui/` | 7 | 1,930 |
| root (`main.py`, `start.py`, `setup.py`) | 3 | 1,546 |
| tests | 31 | 7,755 |
| scripts | 4 | 863 |

Roughly 10k lines of production code against 7.7k lines of tests. The modular-monolith boundaries match the architecture document: presentation (`ui/`, `main.py`), orchestration services (`ui/*_service.py`), domain (`core/`), ingestion/retrieval, and providers.

## 2. Automated gates

| Gate | Command | Result |
|---|---|---|
| Lint | `python -m ruff check .` | All checks passed |
| Format | `python -m ruff format --check .` | 73 files already formatted |
| Tests | `python -m pytest -q --no-header` | 318 passed in 42.76 s |
| Import smoke | exercised by tests and audit scripts | No import errors |

No type checker is configured. PEP 604 annotations and Pydantic models are used consistently on public boundaries, but mypy/pyright would still add value.

## 3. Strengths

- **Clear separation of concerns.** Provider ABC, retriever, doc store, summarizer, citation validator, and UI renderers have single, testable responsibilities.
- **Failure semantics improved by this audit.** Vector writes/deletes no longer fail silently; purge reports per-tier failures; ingestion is atomic; hydration isolates per-document repair.
- **Privacy is enforced in code, not documentation.** Loopback-only local provider, consent-gated cloud adapters, sanitizer, no telemetry.
- **Resource discipline is explicit.** `InferenceGate` serializes GPU work; Docling/OCR/embeddings are CPU-pinned; summarizer and prompt budgets are bounded.
- **Tests target behavior contracts**, including failure paths (refused connections, 503 loading, malformed payloads, cache invalidation, consent denial).

## 4. Issues found and fixed

| Severity | Issue | Quality impact | Fix |
|---|---|---|---|
| High | Duplicated/ambiguous index location (`retrieval/data/lancedb` vs `data/lancedb`) | Hidden state, restart data loss | Canonical path + non-destructive migration |
| High | Broad `except Exception` paths returned success on vector failures | False positives, orphan data | Typed `VectorIndexError` propagation |
| High | Non-transactional multi-write ingestion | Partial documents | `record_ingestion` transaction |
| High | Unconsented cloud construction | Privacy violation | Consent gate + `PermissionError` |
| Medium | Version-agnostic cache fallback | Stale summaries | Strict version match |
| Medium | Unbounded consolidation / unsplittable pages | Context overflow | Iterative bounded reduction |
| Medium | Prose splitting of tables | Corrupted table evidence | Header-repeating table splitter |
| Medium | `extractall` archive handling | Zip-slip/tar traversal | Path-validated safe extraction |
| Medium | Double health probe per rerun | Latency/VRAM churn | Single probe + 5 s UI cache |
| Medium | Startup flag set before work | Hydration never retried | Completion only after success |

## 5. Remaining maintainability concerns

| Priority | Concern | Recommendation |
|---|---|---|
| P2 | `retrieval/vector_index.py` overlaps `HybridRetriever` fallback responsibilities | Keep as an explicitly documented in-memory fallback, or delete after a deprecation cycle |
| P2 | `ui/views.py` is large (~800 lines) and mixes rendering with handlers | Extract chat/summarizer/library controllers when next touched |
| P2 | Broad exception blocks remain around optional integrations (OCR, telemetry, cache cleanup) | Keep, but ensure each logs context and never converts a data-integrity failure into success |
| P2 | No type checker in CI | Add `pyright`/`mypy` in report-only mode, then ratchet |
| P2 | Evaluation numbers predate the identity correction | Re-run `scripts/profile_resources.py` and `scripts/benchmark_*` on the RTX 3050 |
| P3 | Model filename is legacy (`qwen3-...`) while contents are Qwen2-VL | Retained for compatibility; identity verification is now authoritative. Rename only with a migration |
| P3 | Test suite depends on the local model files for one identity test | It is skip-guarded, so CI without weights remains green |

## 6. Style and conventions

- Ruff formatting and linting are clean at 120 columns, Python 3.11 target.
- Module docstrings and Google-style public method docstrings are consistently present.
- Naming follows the documented conventions (`snake_case` functions, `PascalCase` classes, `render_*` UI functions, `test_<behavior>_<condition>`).
- The new `core/model_identity.py` keeps GGUF parsing dependency-free (stdlib `struct`) and fails closed.

## 7. Bottom line

The codebase is above average for a local-first prototype: readable, modular, and now materially safer at its persistence and privacy boundaries. The main residual quality risk is **unverified runtime behavior on the target GPU**, not code structure. Treat the historical benchmark/evaluation numbers as stale until re-measured.
