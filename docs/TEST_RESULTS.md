# Test Results

**Date:** 2026-10-21
**Host:** Windows 11, Python 3.13.5, RTX 3050 Laptop (4 GB) — no live llama-server.
**Baseline commit:** `dc701ec` (before repairs)
**Final working tree:** after the audit repair commits and documentation.

## 1. Summary

| Gate | Command | Result |
|---|---|---|
| Unit/contract suite | `python -m pytest -q --no-header` | **309 passed**, 0 failed, 0 skipped, 0 errors, **44.42 s** (re-run; 39.68 s on the immediately preceding run of the same tree) |
| Lint | `python -m ruff check .` | **All checks passed** |
| Format | `python -m ruff format --check .` | **72 files already formatted** |
| Collection | `python -m pytest --collect-only -q` | 309 tests collected |
| GGUF identity | `verify_local_model_pair(...)` | `[]` (no problems) |
| Live llama-server | `GET /health`, `GET /v1/models` | **UNTESTED** — connection timeout |
| Live inference/GPU | app flow | **UNTESTED** — server not running |

Baseline before any edits was 296 passed in 46.08 s. The repaired tree adds 13 regression tests and remains green.

## 2. Per-suite counts

| Suite | Tests | Suite | Tests |
|---|---:|---|---:|
| `test_models.py` | 20 | `test_llama_cpp_provider.py` | 17 |
| `test_hybrid_retriever.py` | 17 | `test_doc_store.py` | 17 |
| `test_main_ui.py` | 16 | `test_resource_telemetry.py` | 14 |
| `test_ocr_fallback.py` | 13 | `test_local_llm.py` | 13 |
| `test_citation_validator.py` | 13 | `test_audit_repairs.py` | 13 |
| `test_model_provider.py` | 12 | `test_start_launcher.py` | 11 |
| `test_prompt_budget.py` | 11 | `test_litellm_provider.py` | 11 |
| `test_summarizer.py` | 10 | `test_visual_analyzer.py` | 9 |
| `test_ui_smoke.py` | 9 | `test_pdf_reader.py` | 9 |
| `test_upload_validation.py` | 8 | `test_docling_reader.py` | 8 |
| `test_concurrency_lock.py` | 8 | `test_cloud_privacy.py` | 8 |
| `test_vector_index.py` | 7 | `test_sanitizer.py` | 7 |
| `test_groq_provider.py` | 7 | `test_setup_llama.py` | 6 |
| `test_cache_invalidation.py` | 6 | `test_logging_setup.py` | 4 |
| `test_local_embedding.py` | 4 | `test_hydration.py` | 1 |

**Total: 309.**

## 3. New regression coverage

`tests/test_audit_repairs.py` asserts:

1. Default LanceDB URI is `<repo>/data/lancedb`.
2. A legacy `retrieval/data/lancedb` index is copied without deleting the source.
3. A simulated LanceDB write failure raises `VectorIndexError` and still writes the fallback store.
4. `record_ingestion` replaces stale pages/chunks/evidence in one call.
5. Empty legacy summary `model_version` is rejected when a version is requested.
6. `GroqProvider` refuses generation/streaming without consent.
7. Local sanitizer removes bare URLs, autolinks, reference definitions, and `<video>` embeds.
8. Consented cloud mode preserves external links.
9. Oversized single pages split into bounded batches.
10. Long Markdown tables split by rows with repeated headers.
11. Installed GGUF files are a Qwen2-VL LM + compatible projector pair.
12. Vector delete failure aborts before SQLite deletion.
13. Purge surfaces vector failure while still clearing session state.

## 4. What the tests do **not** prove

| Area | Why not covered | Required manual check |
|---|---|---|
| Real llama.cpp generation/streaming | server unavailable | Start server; curl `/v1/chat/completions` blocking and streaming |
| Vision inference | server unavailable | Analyze `chart_diagram.pdf`; inspect caption + VRAM |
| Peak VRAM / thermal behavior | no live run | `nvidia-smi` sampling during ingestion + chat + summary |
| OCR accuracy | synthetic/mocks | Ingest `scanned_sample.pdf` and inspect text |
| Citation precision on real answers | requires generation | Ask grounded and unanswerable questions; inspect `[E#]` chips |
| Cloud provider calls | intentionally no egress/keys | Consent test already automated; live call only with user consent |
| Restart persistence against real data | no live app run | Ingest, restart, confirm vectors and summaries survive |

## 5. Reproduce

```powershell
python -m pytest -q --no-header
python -m ruff check .
python -m ruff format --check .
python -c "from core.model_identity import verify_local_model_pair; print(verify_local_model_pair('models/qwen3-vl-2b-instruct-q4_k_m.gguf','models/mmproj-f16.gguf') or 'identity OK')"
```

Expected: 309 passed; Ruff clean; `identity OK`. Live checks require `python start.py --start-llama` first.
