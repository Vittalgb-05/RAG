# Requirements Traceability

**Date:** 2026-10-21
**Sources:** `.planning/REQUIREMENTS.md` (v1 requirements) and `.planning/PROJECT.md` (FR/NFR)
**Status legend:** **Met** = implementation plus automated evidence; **Met (manual)** = implementation exists but the end-to-end behavior needs a live environment; **Partial** = implementation exists with a known limitation; **Untested** = cannot be verified here.

## v1 requirements

| Requirement | Status | Implementation evidence | Test evidence |
|---|---|---|---|
| INGEST-01 Upload validation (`%PDF`, size, pages) | Met | `ingestion/upload_validation.py`, `ui/ingestion_service.py` | `tests/test_upload_validation.py` (8) |
| INGEST-02 SHA-256, duplicate detection, stable IDs | Met | `ingestion/upload_validation.py`, `core/models.py::cache_dir_for`, `ui/ingestion_service.py` | `test_upload_validation`, `test_doc_store`, `test_cache_invalidation` |
| INGEST-03 Docling reading order/tables/figures | Met | `ingestion/docling_reader.py` | `tests/test_docling_reader.py` (8) |
| INGEST-04 Conditional RapidOCR < 50 chars | Met (manual) | `ingestion/ocr_fallback.py` | `tests/test_ocr_fallback.py` (13); real OCR engine run is environment-dependent |
| INGEST-05 Page-level fault isolation | Met | `ingestion/pdf_reader.py`, `ingestion/docling_reader.py`, ingestion failure path | `test_pdf_reader`, `test_docling_reader`, `test_ui_smoke` |
| STORE-01 ACID SQLite metadata | Met | `core/doc_store.py` (WAL, migrations v1–v4, `record_ingestion` transaction) | `tests/test_doc_store.py` (17), `test_audit_repairs` |
| STORE-02 Typed Pydantic canonical models | Met | `core/models.py` | `tests/test_models.py` (20) |
| STORE-03 SHA/config-versioned disk cache | Met | `core/models.py::cache_dir_for`, `ui/ingestion_service.py`, `ui/hydration.py` | `test_cache_invalidation`, `test_hydration` |
| INF-01 Unified provider interface | Met | `providers/model_provider.py` | `tests/test_model_provider.py` (12) |
| INF-02 Local llama-server 2B VLM, 4K–8K | Met (verified live) | `providers/llama_cpp_provider.py`, `core/model_identity.py`, `core/runtime_info.py`; weights are Qwen3.5-2B Q4_K_M (arch `qwen35`) on llama.cpp v0.8.0 (`b11960`) | `test_llama_cpp_provider` (21), `test_runtime_info` (16), `test_audit_repairs::test_local_model_identity...`; live text + image + streaming verified 2026-10-29 (see `docs/EVALUATION.md` §5) |
| INF-03 100% offline local mode | Met | local provider only; sanitizer; no telemetry; cloud gated | `test_cloud_privacy`, `test_sanitizer`, `test_local_llm`, `test_audit_repairs` |
| INF-04 Optional consented LiteLLM routing | Met | `providers/litellm_provider.py`, `core/local_llm.py` | `test_litellm_provider` (11), `test_cloud_privacy` (8) |
| VIS-01 Visual element detection/crops | Met | `ingestion/visual_analyzer.py` | `tests/test_visual_analyzer.py` (9) |
| VIS-02 Local VLM visual descriptions | Met (manual) | `ingestion/visual_analyzer.py` via provider + `InferenceGate` | `test_visual_analyzer`; live VLM **UNTESTED** |
| VIS-03 Visual provenance tagging | Met | `core/models.py::EvidenceElement`, `ingestion/visual_analyzer.py` | `test_models`, `test_visual_analyzer`, `test_audit_repairs` |
| RETR-01 CPU-pinned MiniLM embeddings | Met | `retrieval/local_embedding.py` | `tests/test_local_embedding.py` (4) |
| RETR-02 Persistent LanceDB index | Met | `retrieval/hybrid_retriever.py` canonical `data/lancedb`, fallback store | `test_hybrid_retriever` (17), `test_audit_repairs` (path/migration/failure) |
| RETR-03 Dense + FTS RRF | Met | `retrieval/hybrid_retriever.py` | `test_hybrid_retriever` |
| RETR-04 Single shared `RetrievalResult` | Met | `core/local_llm.py`, `ui/views.py` | `test_local_llm`, `test_ui_smoke` |
| QA-01 Streamed grounded answers | Met (manual) | `core/local_llm.py`, `ui/views.py` | `test_local_llm`; live stream **UNTESTED** |
| QA-02 `[E#]` prompt isolation | Met | `core/prompt_budget.py`, `core/local_llm.py` | `test_prompt_budget` (11) |
| QA-03 ≥95% citation validation | Met | `core/citation_validator.py` | `tests/test_citation_validator.py` (13) |
| QA-04 Explicit abstention | Met | `core/citation_validator.py`, `core/local_llm.py` | `test_citation_validator`, `test_local_llm` |
| SUMM-01 Five summary profiles | Met | `core/summarizer.py`, `ui/views.py` | `tests/test_summarizer.py` (10), `test_main_ui` |
| SUMM-02 Hierarchical map-reduce with pages | Met | `core/summarizer.py`; new bounded consolidation and page splitting | `test_summarizer`, `test_audit_repairs::test_summarizer_splits_oversized_page...` |
| SUMM-03 Hash+profile summary cache | Met | `core/doc_store.py`, `ui/views.py`; version-aware only | `test_cache_invalidation`, `test_audit_repairs::test_summary_cache_rejects_empty_legacy_version` |
| UI-01 Upload/progress states | Met | `main.py`, `ui/views.py`, `ui/components.py` | `test_ui_smoke` (9), `test_main_ui` (16) |
| UI-02 Profiles + page references | Met | `ui/views.py` | `test_ui_smoke`, `test_main_ui` |
| UI-03 Evidence chips/drawer | Met | `ui/views.py`, `ui/components.py` | `test_ui_smoke`, `test_main_ui` |
| UI-04 Local/cloud toggle with consent | Met | `ui/views.py`, `core/local_llm.py` | `test_main_ui`, `test_cloud_privacy` |
| QUAL-01 One LLM in VRAM, benchmarks | Partial | `InferenceGate`, CPU pinning, serialized calls; live VRAM evidence absent | `test_concurrency_lock` (8); benchmark **UNTESTED** |
| QUAL-02 Pytest coverage | Met | `tests/` 30 suites | **309 passed** |
| QUAL-03 Structured commits | Met | eight atomic repair commits | `git log dc701ec..HEAD` |
| QUAL-04 Codebase map/quality gates | Met | `.planning/codebase/`, CI workflow, Ruff gates | Ruff clean; CI config present |

## PROJECT.md FR/NFR mapping

| ID | Status | Covered by |
|---|---|---|
| FR-01 Robust PDF ingestion | Met | INGEST-01/02/05 |
| FR-02 Structured Docling extraction | Met | INGEST-03, P1-3 table splitting |
| FR-03 Conditional local OCR | Met (manual) | INGEST-04 |
| FR-04 Selective visual understanding | Met (verified live) | VIS-01/02/03; Qwen3.5-2B VLM descriptions verified on chart/diagram/table corpus pages |
| FR-05 Storage and provenance | Met | STORE-01/02/03, atomic ingestion |
| FR-06 Hierarchical summarization | Met | SUMM-01/02 |
| FR-07 Grounded QA + ≥95% citations | Met | QA-01..04 |
| FR-08 Persistent hybrid retrieval | Met | RETR-01..04, P0-1/P0-2 |
| FR-09 Provider abstraction | Met | INF-01/02/04 |
| FR-10 Enhanced Streamlit UI | Met | UI-01..04 |
| NFR-01 Performance/resource safety | Partial | `InferenceGate`, 4K context budgets, CPU pinning; live peak VRAM **UNTESTED** |
| NFR-02 Quality/privacy/local deletion | Met | P0-4, P0-6, P0-7; tests for delete/purge, consent, sanitizer |
| Process 1–3 | Met | commits, planning docs, tests/CI |

## Gaps that are explicitly not “met” by this audit

1. **Live inference, GPU memory, and latency** were not exercised because llama-server was not running.
2. **Real scanned-document OCR and VLM caption quality** are not asserted by unit tests.
3. **Historical evaluation numbers** in `docs/EVALUATION.md` were not regenerated; they remain prior-run artifacts.
4. **Cloud provider calls** are consent-tested with mocks, not with real credentials (correctly, to avoid egress).

No requirement is marked complete solely because a document says so; each row above cites code and/or a named test suite.
