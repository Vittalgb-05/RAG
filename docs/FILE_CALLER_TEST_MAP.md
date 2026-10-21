# File → Caller → Test Map

**Date:** 2026-10-21
**Purpose:** Make every source module's owner, entry direction, and automated coverage explicit. “Caller” lists the primary production importer; utility modules called widely are noted as shared.

## Entry points

| File | Responsibility | Called by | Tests |
|---|---|---|---|
| `main.py` | Streamlit composition root, session state, routing, health throttle | `streamlit run main.py` | `test_main_ui.py` (16), `test_ui_smoke.py` (9) |
| `start.py` | Pre-flight checks, artifact identity verification, llama-server launch, Streamlit launch | operator CLI | `test_start_launcher.py` (11) |
| `setup.py` | Model/llama-server downloads, safe extraction, GGUF validation, model precache | operator CLI | `test_setup_llama.py` (6) |

## Core domain

| File | Responsibility | Primary callers | Tests |
|---|---|---|---|
| `core/models.py` | Pydantic canonical models, `CONFIG_VERSION`, `cache_dir_for` | shared by all layers | `test_models.py` (20) |
| `core/doc_store.py` | SQLite schema/migrations, atomic `record_ingestion`, summaries, delete/purge | `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `core/summarizer.py` | `test_doc_store.py` (17), `test_cache_invalidation.py`, `test_audit_repairs.py` |
| `core/local_llm.py` | `AiModel` facade, provider routing, `InferenceGate`, retrieval context, streaming, consent | `main.py`, `ui/views.py` | `test_local_llm.py` (13), `test_concurrency_lock.py` (8), `test_cloud_privacy.py` (8) |
| `core/summarizer.py` | Profile prompts, cache, bounded map-reduce, page/table-safe batching | `ui/views.py`, `main.py` | `test_summarizer.py` (10), `test_audit_repairs.py` |
| `core/citation_validator.py` | `[E#]` extraction, precision gate, abstention, injection flags | `core/local_llm.py` | `test_citation_validator.py` (13) |
| `core/prompt_budget.py` | Token estimation, XML isolation, history truncation | `core/local_llm.py`, `core/summarizer.py` | `test_prompt_budget.py` (11) |
| `core/resource_telemetry.py` | RSS/VRAM sampling with caching | `main.py`, `ui/views.py` | `test_resource_telemetry.py` (14) |
| `core/logging_setup.py` | Structured logging and watcher-noise suppression | `main.py`, `start.py` | `test_logging_setup.py` (4) |
| `core/model_identity.py` | GGUF metadata parser and LM/projector compatibility verification | `start.py`, `setup.py` | `test_audit_repairs.py::test_local_model_identity...` |

## Ingestion

| File | Responsibility | Primary callers | Tests |
|---|---|---|---|
| `ingestion/upload_validation.py` | Size/page/magic-byte validation, SHA-256, stable `doc_<sha16>` | `ui/ingestion_service.py` | `test_upload_validation.py` (8) |
| `ingestion/docling_reader.py` | Docling layout/tables, CPU pinning, table-aware chunking, offsets | `ui/ingestion_service.py` | `test_docling_reader.py` (8), `test_audit_repairs.py` |
| `ingestion/pdf_reader.py` | pypdf fallback extraction | `ui/ingestion_service.py`, `ingestion/docling_reader.py` | `test_pdf_reader.py` (9) |
| `ingestion/ocr_fallback.py` | Conditional RapidOCR on low-text pages | `ui/ingestion_service.py` | `test_ocr_fallback.py` (13) |
| `ingestion/visual_analyzer.py` | Figure/table detection, 2× crops, local VLM descriptions | `ui/ingestion_service.py` | `test_visual_analyzer.py` (9) |

## Retrieval and persistence

| File | Responsibility | Primary callers | Tests |
|---|---|---|---|
| `retrieval/hybrid_retriever.py` | Canonical LanceDB path, migration, dense+FTS RRF, loud failures, fallback store | `main.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `core/local_llm.py` | `test_hybrid_retriever.py` (17), `test_audit_repairs.py` |
| `retrieval/local_embedding.py` | CPU-pinned MiniLM shared cache | `ui/ingestion_service.py`, `retrieval/hybrid_retriever.py`, `core/local_llm.py` | `test_local_embedding.py` (4) |
| `retrieval/vector_index.py` | Legacy in-memory cosine fallback (not the persistent path) | `retrieval/hybrid_retriever.py` fallback | `test_vector_index.py` (7) |

## Providers

| File | Responsibility | Primary callers | Tests |
|---|---|---|---|
| `providers/model_provider.py` | Provider ABC, capabilities, health contracts | shared | `test_model_provider.py` (12) |
| `providers/llama_cpp_provider.py` | Local llama-server `/health` + `/v1/chat/completions`, streaming, vision, loopback enforcement | `core/local_llm.py`, `main.py`, `start.py` | `test_llama_cpp_provider.py` (17) |
| `providers/litellm_provider.py` | Consented cloud adapter, key scrubbing | `core/local_llm.py`, `main.py` | `test_litellm_provider.py` (11), `test_cloud_privacy.py` |
| `providers/groq_provider.py` | Direct Groq adapter with explicit consent gate | `core/local_llm.py` (only with consented injection) | `test_groq_provider.py` (7), `test_audit_repairs.py` |

## UI orchestration and presentation

| File | Responsibility | Primary callers | Tests |
|---|---|---|---|
| `ui/ingestion_service.py` | Validate → extract → OCR → visualize → embed → index → persist transaction | `main.py`, `ui/views.py` | `test_ui_smoke.py`, `test_audit_repairs.py` (indirect), ingestion suites |
| `ui/lifecycle_service.py` | Vector-first delete, purge with failure reporting, verified reindex, cache cleanup | `ui/views.py`, `main.py` | `test_audit_repairs.py`, `test_main_ui.py` |
| `ui/hydration.py` | Startup catalog hydration, index repair, per-document isolation | `main.py` | `test_hydration.py` (1), `test_main_ui.py` |
| `ui/views.py` | Chat, summarizer, library, settings renderers and handlers | `main.py` | `test_ui_smoke.py`, `test_main_ui.py` |
| `ui/components.py` | Reusable chips, cards, status components | `ui/views.py` | `test_ui_smoke.py` |
| `ui/theme.py` | AMOLED CSS and icon rendering | `main.py` | `test_ui_smoke.py` |
| `ui/sanitizer.py` | Local-mode HTML/Markdown egress neutralization | `ui/views.py`, `ui/components.py` | `test_sanitizer.py` (7), `test_audit_repairs.py` |

## Coverage gaps (intentional or environmental)

| Area | Gap | Mitigation |
|---|---|---|
| Live llama-server | No running server during audit | Manual matrix in `ENDPOINT_INTEGRATION_MATRIX.md`; **UNTESTED** rows |
| GPU VRAM | No inference run | `InferenceGate` + CPU pinning; requires target-hardware measurement |
| Real OCR/VLM quality | Unit tests use mocks/synthetic PDFs | Manual corpus run required |
| Cloud APIs | Not called with real keys | Consent and error paths tested with mocks |
| `retrieval/vector_index.py` | Legacy fallback overlaps `HybridRetriever` | Retained for offline fallback; not the persistence path |
