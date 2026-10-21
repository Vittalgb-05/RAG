<!-- refreshed: 2026-10-21 -->
# Architecture

**Analysis Date:** 2026-10-21

## System Overview

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│ Presentation — Streamlit script, chatbot-first AMOLED workspace               │
│  `main.py`  ·  `ui/views.py`  ·  `ui/components.py`  ·  `ui/theme.py`          │
│  `ui/sanitizer.py`  ·  `.streamlit/config.toml`  ·  `assets/icons/*.svg`       │
└───────────────┬───────────────────────────────────────────────┬───────────────┘
                │                                               │
                ▼                                               ▼
┌─────────────────────────────────────┐   ┌─────────────────────────────────────┐
│ UI Orchestration Services           │   │ Domain Services                     │
│ `ui/ingestion_service.py`           │   │ `core/local_llm.py` (AiModel, Gate) │
│ `ui/lifecycle_service.py`           │   │ `core/summarizer.py` (map-reduce)   │
│ `ui/hydration.py`                   │   │ `core/citation_validator.py`        │
│ `ui/session_state.py`               │   │ `core/prompt_budget.py`             │
└───────────────┬─────────────────────┘   └───────────────┬─────────────────────┘
                │                                         │
                ▼                                         ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│ Ingestion & Retrieval Pipeline                                                │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`               │
│   → `ingestion/pdf_reader.py` (fallback) → `ingestion/ocr_fallback.py`         │
│   → `ingestion/visual_analyzer.py` (VLM crops)                                 │
│ `retrieval/local_embedding.py` (MiniLM, CPU) → `retrieval/hybrid_retriever.py` │
│ `retrieval/vector_index.py` (in-memory fallback)                               │
└───────────────┬───────────────────────────────────────────────┬───────────────┘
                │                                               │
                ▼                                               ▼
┌─────────────────────────────────────┐   ┌─────────────────────────────────────┐
│ Persistence                         │   │ Inference Providers                 │
│ `core/doc_store.py` (SQLite WAL)    │   │ `providers/model_provider.py` (ABC) │
│ `data/lancedb/` (LanceDB + FTS)     │   │ `providers/llama_cpp_provider.py`   │
│ `.cache/<sha256>/<version>/`        │   │ `providers/litellm_provider.py`     │
│ `core/models.py` (canonical models) │   │ `providers/groq_provider.py`        │
└─────────────────────────────────────┘   └─────────────────────────────────────┘
```

The composition root is `main.py`. `start.py` is the operational launcher; `setup.py` is the packaging/model-download CLI. Everything above runs in a single Python process (one Streamlit server, one llama-server child process).

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit composition root | Page config, session defaults, storage wiring, hydration, cloud-mode sync, health snapshot, sidebar, workspace routing | `main.py` |
| Workspace renderers | Chat, Summarizer, Document Library, Settings, sidebar uploader | `ui/views.py` |
| Ingestion orchestrator | Validation → dedup/repair → extraction → OCR → VLM → SQLite → vectors → cache, returning `IngestionResult` | `ui/ingestion_service.py` |
| Lifecycle orchestrator | Atomic delete, purge-all, re-index across SQLite, LanceDB, disk cache, and session state | `ui/lifecycle_service.py` |
| Startup hydration | Restore document catalog from SQLite, open the retriever, verify/repair missing vectors | `ui/hydration.py` |
| Session teardown | One canonical reset for chat, evidence, credentials, retriever, uploader | `ui/session_state.py` |
| Domain QA facade | Provider routing, retrieval-context assembly, token budgeting, streaming, post-hoc citation validation | `core/local_llm.py` |
| VRAM concurrency gate | Process-wide reentrant lock serializing all LLM/VLM/summarizer inference | `core/local_llm.py` (`InferenceGate`, lines 25–89) |
| Summarization | Five profiles, fast path + token-bounded map-reduce, page-reference extraction, SQLite cache | `core/summarizer.py` |
| Citation validation | `[E#]` extraction, ≥95% precision gate, abstention and injection detection | `core/citation_validator.py` |
| Prompt budgeting | 4K-context allocation, `<document_context>` isolation, oldest-first history truncation | `core/prompt_budget.py` |
| Canonical schemas | `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult` | `core/models.py` |
| SQLite store | WAL-mode metadata/chunks/pages/evidence/summaries, migrations v1–v4, transactional ingestion | `core/doc_store.py` |
| Hybrid retriever | LanceDB dense + FTS/BM25, RRF fusion, doc filters, JSON fallback mirror | `retrieval/hybrid_retriever.py` |
| Embeddings | CPU-pinned `all-MiniLM-L6-v2`, 384-dim, L2-normalized, process-level model cache | `retrieval/local_embedding.py` |
| Fallback index | Pure-stdlib cosine/euclidean vector index | `retrieval/vector_index.py` |
| Upload validation | `%PDF` magic bytes, 50 MB / 500 page caps, SHA-256 + `doc_<sha16>` | `ingestion/upload_validation.py` |
| Structured extraction | Docling layout/reading order/markdown tables; pypdf fallback | `ingestion/docling_reader.py`, `ingestion/pdf_reader.py` |
| Conditional OCR | RapidOCR only for pages below 50 chars; per-page fault isolation; thread pool | `ingestion/ocr_fallback.py` |
| Visual analysis | PyMuPDF region detection, 2× crops, local VLM descriptions, provenance tagging | `ingestion/visual_analyzer.py` |
| Provider contract | `BaseModelProvider` ABC + `ProviderCapabilities` + `HealthStatus` | `providers/model_provider.py` |
| Local provider | llama-server HTTP/SSE client with loopback/SSRF guard | `providers/llama_cpp_provider.py` |
| Cloud providers | Consent-gated LiteLLM (Groq/OpenAI/Anthropic) and direct Groq adapter | `providers/litellm_provider.py`, `providers/groq_provider.py` |
| Telemetry | `nvidia-smi` VRAM with 5 s TTL, process RSS, stage latency history | `core/resource_telemetry.py` |

## Pattern Overview

**Overall:** Layered modular monolith with a Streamlit script-style composition root, a thin service layer, canonical Pydantic domain models, and strategy/adapter-based inference providers.

**Key Characteristics:**
- **One process, many layers.** UI, orchestration, domain, ingestion, retrieval, persistence, and providers live in the same interpreter; boundaries are enforced by imports and conventions, not network calls.
- **Composition root owns lifetimes.** `main.py:67-114` configures Streamlit, initializes `DocStore`, and hydrates state before any view runs. `AiModel` is session-scoped (`main.py:117-128`) while `InferenceGate` is process-scoped.
- **Providers are interchangeable.** `BaseModelProvider` (`providers/model_provider.py:64-156`) is the only inference surface used by `AiModel`, `Summarizer`, and `VisualAnalyzer`; local vs cloud is a routing decision in `core/local_llm.py:197-213`.
- **Canonical immutable evidence.** `RetrievalResult` / `EvidenceSnippet` (`core/models.py:142-205`) are shared by prompt assembly and UI rendering, so the model and the user see the same numbered evidence.
- **Graceful degradation is designed in.** Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, RapidOCR per-page isolation, placeholder visual descriptions filtered out of the index, and vector-write failures marked `failed` instead of silently indexed.
- **Privacy is a routing constraint.** Local mode never constructs a cloud provider; cloud mode refuses to activate without `user_consented=True` (`core/local_llm.py:120-126`, `167-181`).

## Layers

**Presentation:**
- Purpose: Render the four workspaces and the sidebar; translate widget events into service calls.
- Location: `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`
- Contains: Streamlit renderers (`render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, `render_sidebar_documents`), AMOLED CSS, SVG icon helpers, Markdown/HTML sanitization.
- Depends on: UI orchestration services, `core.local_llm.AiModel`, `core.summarizer.Summarizer`, `core.doc_store.DocStore`, telemetry.
- Used by: The Streamlit runtime only. `main.py` dispatches at lines 321–349.

**UI Orchestration:**
- Purpose: Own multi-step workflows and cross-store consistency.
- Location: `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `ui/session_state.py`
- Contains: `IngestionService.ingest_pdf`, `LifecycleService.delete_document/purge_all/reindex_document`, `hydrate_startup_state`, `reset_in_memory_session`.
- Depends on: ingestion extractors, `HybridRetriever`, `LocalEmbedding`, `DocStore`, `cache_dir_for`.
- Used by: `ui/views.py` and `main.py`.

**Domain Services:**
- Purpose: Grounded generation, summarization policy, prompt/context budgeting, citation verification, telemetry.
- Location: `core/`
- Contains: `AiModel`, `InferenceGate`, `Summarizer`, `validate_citations`, `assemble_grounded_messages`, `DocStore`, `resource_telemetry`.
- Depends on: `providers.*`, `retrieval.hybrid_retriever`, `core.models`.
- Used by: Presentation and UI orchestration.

**Ingestion:**
- Purpose: Turn untrusted PDF bytes into validated, page-addressable chunks and visual evidence.
- Location: `ingestion/`
- Contains: validation, Docling extraction, pypdf fallback, OCR fallback, visual analyzer.
- Depends on: `core.models`, third-party parsers (`docling`, `pypdf`, `rapidocr`, `pymupdf`).
- Used by: `IngestionService`.

**Retrieval:**
- Purpose: Persist and query dense + lexical indexes; fuse rankings.
- Location: `retrieval/`
- Contains: `HybridRetriever`, `LocalEmbedding`, `VectorIndex`, `compute_rrf`.
- Depends on: `core.models`, `lancedb`/`pyarrow` (optional), `sentence-transformers`.
- Used by: `AiModel`, `IngestionService`, `LifecycleService`, `hydration`, `views`.

**Persistence:**
- Purpose: Durable source of truth and derived indexes.
- Location: `core/doc_store.py`, `data/documents.db`, `data/lancedb/`, `.cache/<sha256>/<version>/`
- Contains: ACID document/page/chunk/evidence/summary rows; vector table; extraction artifacts.
- Depends on: `sqlite3`, `lancedb`, filesystem.
- Used by: every layer above.

**Inference Providers:**
- Purpose: Normalize local and cloud model access behind one contract.
- Location: `providers/`
- Contains: ABC + capabilities/health, llama.cpp HTTP/SSE client, LiteLLM adapter, Groq adapter.
- Depends on: `httpx`, `litellm`, `groq`.
- Used by: `AiModel`, `Summarizer`, `VisualAnalyzer`.

## Data Flow

### Primary Request Path — Grounded Chat

1. User submits a prompt in Chat (`ui/views.py:346-352`); the view appends the user turn and bounds history to the last 10 turns (`ui/views.py:359-363`).
2. Short follow-ups are expanded with the previous user message (`ui/views.py:365-378`; the same logic is duplicated in `core/local_llm.py:271-300`).
3. A document scope is chosen explicitly or inferred by matching filename/stem in the prompt (`ui/views.py:380-389`).
4. Retrieval runs before generation: `search_hybrid(search_query, k=8, doc_id=doc_filter)` (`ui/views.py:395-398`).
5. Snippets are serialized for the UI and passed to the model as a canonical `RetrievalResult` (`ui/views.py:408-420`).
6. `AiModel.ask_a_question_from_pdf_stream` formats evidence as `[E1]…[En]` (`core/models.py:185-194`), assembles bounded messages (`core/prompt_budget.py:65-150`), acquires `InferenceGate` (`core/local_llm.py:336`), and streams provider tokens (`core/local_llm.py:342-349`).
7. The completed text is validated against the same retrieval result (`core/local_llm.py:379-397` → `core/citation_validator.py:115-230`), producing precision, cited ranks, abstention, and injection flags.
8. The view renders a grounding caption and only the cited citation chips, with an evidence drawer including bounding boxes when present (`ui/views.py:428-471`), then stores the assistant turn with verification metadata (`ui/views.py:473-483`).

**State Management:** Conversation, document catalog, retriever/embedding handles, cloud consent, and health snapshots live in `st.session_state` (`main.py:81-101`). Durable truth lives in SQLite; LanceDB is a derived index; `.cache/` is a derived artifact store. `AiModel.last_retrieval_result` / `last_verification_result` are per-turn caches reset by `reset_turn_state` (`core/local_llm.py:147-159`).

### PDF Ingestion

1. Sidebar uploader enforces a client-side 50 MB check, then calls `IngestionService.ingest_pdf` with the active local VLM provider (`ui/views.py:65-100`).
2. Validation: `%PDF-` magic bytes, size cap, pypdf page count, 1–500 page bounds, streaming SHA-256, `doc_<sha16>` (`ingestion/upload_validation.py:64-113`).
3. Dedup by SHA: if the document is `indexed` and vectors exist, return `already_indexed=True`; if vectors are missing, repair from SQLite chunks before falling through to full extraction (`ui/ingestion_service.py:97-139`).
4. Extraction: `DoclingReader` with CPU-pinned layout/table pipeline (`ingestion/docling_reader.py:173-198`); on import/conversion failure or zero items, `PdfReader` produces per-page chunks (`ingestion/docling_reader.py:165-171, 272-281, 415-421`; `ingestion/pdf_reader.py:46-132`).
5. Conditional OCR: pages with status `empty`/`failed` or <50 characters are rasterized at 150 DPI and OCR'd; multiple pages run in a ≤4-worker thread pool with per-page exception isolation (`ingestion/ocr_fallback.py:318-417`).
6. Visual analysis: PyMuPDF detects raster images and vector drawing clusters, crops at 2× with a 2048×2048 pixel budget, and calls the local VLM under `InferenceGate`; sample capped at 6 regions (`ingestion/visual_analyzer.py:49-146, 202-309`; `ui/ingestion_service.py:189-210`).
7. Zero usable content → a `failed` document row is written and an error `IngestionResult` returned (`ui/ingestion_service.py:212-237`).
8. SQLite commit: one transaction replaces document, pages, chunks, and evidence (`ui/ingestion_service.py:239-259` → `core/doc_store.py:291-436`).
9. Vector write: stale vectors for the doc are deleted, embeddings are computed in one batch, chunks are upserted, and the write is verified with `has_document`; failure marks the document `failed` and returns an error (`ui/ingestion_service.py:272-327`).
10. Visual elements are indexed as synthetic chunks with filename attribution; visual-index failure is logged but does not discard text (`ui/ingestion_service.py:295-299` → `retrieval/hybrid_retriever.py:494-524`).
11. Disk cache artifacts (`pages.json`, `chunks.json`, `manifest.json`) are written under `.cache/<sha256>/docling-1000-200-v1/` only after success (`ui/ingestion_service.py:329-340`; `core/models.py:17-30`).
12. The uploader key is rotated and the script reruns to clear the widget (`ui/views.py:124-143`).

### Hybrid Retrieval (Dense + FTS + RRF)

1. Query embedding: `embedding_fn(query)` (MiniLM, 384-dim, L2-normalized) (`retrieval/local_embedding.py:74-86`).
2. Candidate pool is widened: `max(k*5 if doc_id else k*4, 30)` (`retrieval/hybrid_retriever.py:764`).
3. Dense search over LanceDB with cosine metric and pushed-down `doc_id IN (...)` filter (`retrieval/hybrid_retriever.py:556-615`).
4. FTS search via `table.search(query, query_type="fts")`, falling back to a pure-Python BM25 implementation over stored chunks (`retrieval/hybrid_retriever.py:698-736, 627-696`).
5. A second in-Python doc filter is applied as defense-in-depth (`retrieval/hybrid_retriever.py:779-784`).
6. RRF: `score(d) = Σ 1/(60 + rank_m(d))` across dense and FTS, sorted descending (`retrieval/hybrid_retriever.py:120-165, 817-818`).
7. Top-k are materialized as immutable `EvidenceSnippet`s with `rank`, `dense_rank`, `fts_rank`, bbox, and extraction provenance (`retrieval/hybrid_retriever.py:820-853`).
8. `search_mode` reports `hybrid`, `dense`, `fts`, or `fallback` for diagnostics (`retrieval/hybrid_retriever.py:808-815`).
9. If LanceDB cannot initialize, the retriever uses a JSON-persisted `VectorIndex` mirror at `data/lancedb/fallback_store.json` (`retrieval/hybrid_retriever.py:196-231, 252-275`).

### Hierarchical Summarization

1. The view selects document, profile, and force-refresh, then constructs `Summarizer(provider=ai_model.provider, doc_store=doc_store)` (`ui/views.py:517-577`).
2. `summarize_document` validates the profile, derives `model_version = f"{model_name}:{CONFIG_VERSION}"`, and checks the SQLite cache keyed by `(sha256, profile)` with strict version match (`core/summarizer.py:398-412`; `core/doc_store.py:650-697`).
3. Pages come from the caller, or are reconstructed from chunks grouped by page when `page_text` is absent (`core/summarizer.py:414-455`).
4. Documents ≤2,000 estimated tokens take the single-pass path; larger documents take map-reduce (`core/summarizer.py:461-470`).
5. Map stage: pages are split if oversized, bundled to ≤2,000 tokens, and summarized sequentially with `(p. X)` citation instructions (`core/summarizer.py:170-226, 322-356`).
6. Consolidation folds intermediate summaries in ≤2,500-token groups, invoking the provider for groups that remain large (`core/summarizer.py:228-283`).
7. Reduce stage synthesizes the profile-specific markdown and preserves page citations (`core/summarizer.py:362-374`; profiles at lines 35–109).
8. The whole pipeline holds `InferenceGate` once for up to 120 s (`core/summarizer.py:464`), so nested provider calls cannot interleave with chat or VLM work.
9. Page references are extracted and clamped to the document's max page (`core/summarizer.py:140-154, 472-474`), the `SummaryResult` is persisted, and the view caches it in session state (`core/summarizer.py:480-495`; `ui/views.py:573-596`).

### Document Deletion, Re-index, Purge

1. **Delete** is vector-first: `retriever.delete_document(doc_id)` must succeed before SQLite is touched, otherwise the error propagates (`ui/lifecycle_service.py:48-53`).
2. SQLite removes chunks, pages, evidence, summaries, then the document row (`ui/lifecycle_service.py:55-56` → `core/doc_store.py:758-778`).
3. The SHA-scoped disk cache directory is removed best-effort (`ui/lifecycle_service.py:58-65`).
4. Session state discards ids, filenames, metadata, cached summary keys, and selections (`ui/lifecycle_service.py:67-87`).
5. **Re-index** rebuilds vectors from SQLite chunks: delete stale vectors, embed all chunk content, upsert, re-index evidence, then verify `has_document` (`ui/lifecycle_service.py:148-188`).
6. **Purge all** drops the LanceDB table, deletes all SQLite rows + `VACUUM`, removes and recreates `.cache/`, clears session containers/keys, and raises an aggregate `RuntimeError` if any tier failed (`ui/lifecycle_service.py:92-146`; `core/doc_store.py:780-791`).

### Startup Hydration

1. `main.py` constructs `DocStore(data/documents.db)` and calls `hydrate_startup_state` before any view renders (`main.py:108-114`).
2. Hydration is idempotent via `_startup_hydrated`; a failed document query leaves the flag unset so the next rerun retries (`ui/hydration.py:19-28`).
3. `status="failed"` documents go to `failed_doc_ids`; `status="indexed"` documents populate `doc_ids`, `indexed_files`, and `document_metadata` (`ui/hydration.py:30-50`).
4. The retriever and embedding model are created lazily and bound to session state; the embedding callable is injected into the retriever (`ui/hydration.py:52-62`).
5. For every indexed document, `has_document` is checked; missing vectors are rebuilt from SQLite chunks; failures set `needs_reindex=True` per document so one corrupt document cannot block the rest (`ui/hydration.py:64-85`).
6. `_startup_hydrated` is set only when retriever discovery/repair completed (`ui/hydration.py:88-92`).

### InferenceGate Serialization Constraint

1. `InferenceGate` is a class-level `threading.RLock` plus an active-thread counter (`core/local_llm.py:25-68`). It is reentrant because `Summarizer` holds it while calling providers directly, and nested acquisition must not deadlock.
2. Acquire/release API: `acquire(timeout)`, `release()`, `hold(timeout)` context manager; `hold` raises `TimeoutError` when the wait expires (`core/local_llm.py:37-89`).
3. Chat streaming acquires manually and releases in `finally` (`core/local_llm.py:336-349`). Because it is a generator, the lock is held for the entire token stream.
4. Non-streaming generation uses `with InferenceGate.hold(...)` (`core/local_llm.py:371`).
5. Summarization wraps the whole single-pass/map-reduce pipeline in `hold(timeout=120.0)` (`core/summarizer.py:464`).
6. Each VLM crop analysis is wrapped in `hold(timeout=60.0)` (`ingestion/visual_analyzer.py:274-281`).
7. Operational consequence: concurrent browser sessions queue behind one another; a long summary blocks chat and ingestion VLM work. This is deliberate to stay inside the 4 GB VRAM ceiling, and the chat path surfaces a "system is busy" message on timeout (`core/local_llm.py:336-339`).
8. `InferenceGate` is also asserted in the profiling harness (`scripts/profile_resources.py:251-258`) and covered by `tests/test_concurrency_lock.py`.

## Key Abstractions

**Canonical document models:**
- Purpose: One validated shape for extraction, storage, retrieval, prompts, and UI.
- Examples: `core/models.py` (`Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`).
- Pattern: Frozen/`extra="forbid"` Pydantic v2 models; IDs are validated by prefix (`doc_`, `summ_`).

**`BaseModelProvider`:**
- Purpose: Decouple domain logic from local vs cloud inference.
- Examples: `providers/model_provider.py:64-156`, implemented by `providers/llama_cpp_provider.py:30`, `providers/litellm_provider.py:104`, `providers/groq_provider.py:18`.
- Pattern: Abstract base class with `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`; capability metadata drives routing and UI state.

**`RetrievalResult` / `EvidenceSnippet`:**
- Purpose: Immutable evidence contract shared between prompt and UI.
- Examples: `core/models.py:142-205`; built in `retrieval/hybrid_retriever.py:820-853`.
- Pattern: Value object with `formatted_evidence()` and `source_labels()` rendering helpers.

**`InferenceGate`:**
- Purpose: Enforce the single-active-inference invariant for 4 GB VRAM.
- Examples: `core/local_llm.py:25-89`; consumers listed above.
- Pattern: Process-wide reentrant lock exposed as a context manager.

**`DocStore`:**
- Purpose: ACID source of truth with schema migration.
- Examples: `core/doc_store.py:113-813`; migrations at lines 17–110.
- Pattern: Repository with per-operation connections, WAL, `PRAGMA user_version` migrations, atomic `record_ingestion`.

**`HybridRetriever`:**
- Purpose: Durable hybrid search and index lifecycle.
- Examples: `retrieval/hybrid_retriever.py:168-873`.
- Pattern: Strategy over LanceDB with an in-memory `VectorIndex` + JSON mirror fallback; RRF fusion is a free function for testability.

**`IngestionService` / `LifecycleService`:**
- Purpose: Transactional workflow boundaries that the UI must not bypass.
- Examples: `ui/ingestion_service.py:39-352`, `ui/lifecycle_service.py:16-188`.
- Pattern: Command-style service methods returning `IngestionResult`/`bool`, with explicit cross-store ordering.

**`Summarizer`:**
- Purpose: Profile-driven hierarchical synthesis under a fixed context budget.
- Examples: `core/summarizer.py:157-497`.
- Pattern: Template Method over map/reduce stages with token-budget helper functions.

**Config version:**
- Purpose: Invalidate cached derivations when chunking/extraction policy changes.
- Examples: `CONFIG_VERSION = "docling-1000-200-v1"` (`core/models.py:14`), used in cache paths and summary versioning.
- Pattern: Versioned cache keys rather than ad-hoc cache clearing.

## Entry Points

**`main.py` — Streamlit application (primary runtime):**
- Location: `main.py`
- Triggers: `streamlit run main.py`, or `start.py` spawning Streamlit.
- Responsibilities: `st.set_page_config` first, theme injection, session defaults, SQLite/retriever hydration, session-scoped `AiModel`, cloud consent synchronization, 5 s health snapshot, sidebar, and workspace dispatch (`main.py:67-349`).

**`start.py` — operational launcher:**
- Location: `start.py`
- Triggers: `python start.py`, console script `rag-assistant`.
- Responsibilities: Python ≥3.11 check, directory creation, llama-server discovery/health probe, optional background launch with GGUF identity verification (`core/model_identity.py`), Streamlit subprocess, cleanup of the child process (`start.py:230-282`).

**`setup.py` — packaging and provisioning CLI:**
- Location: `setup.py`
- Triggers: `python setup.py ...`, console scripts `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:773-779`).
- Responsibilities: dependency install, model/projector download with size and GGUF checks, embedding/OCR pre-cache, llama-server installation, setuptools packaging.

**Diagnostics scripts:**
- Location: `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`
- Triggers: manual execution.
- Responsibilities: retrieval quality, multimodal evaluation, VRAM/RAM/latency profiling, icon regeneration.

## Architectural Constraints

- **Threading:** Streamlit runs each session's script on its own thread; OCR uses a bounded `ThreadPoolExecutor` (`ingestion/ocr_fallback.py:388-408`); telemetry uses locks and a 5 s cache; `InferenceGate` serializes all model work across threads and sessions.
- **Global state:** `InferenceGate` class attributes (`core/local_llm.py:33-35`), shared `SentenceTransformer` cache (`retrieval/local_embedding.py:24`), latency history and GPU cache (`core/resource_telemetry.py:21-30`), icon cache (`ui/components.py:12`), visual region cache (`ingestion/visual_analyzer.py:47`). All are process-wide and survive Streamlit reruns.
- **Import direction / circular imports:** `core.local_llm` imports `retrieval.hybrid_retriever`; `ingestion.visual_analyzer` imports `InferenceGate` lazily inside the analysis loop (`ingestion/visual_analyzer.py:275`) to avoid an ingestion ↔ core import cycle. Preserve this direction: `ui → core/ingestion/retrieval → core.models`.
- **VRAM ceiling:** One LLM/VLM operation at a time; 4,096-token context; 4-bit GGUF; `-ngl 28`; Docling, OCR, embeddings, and video-less rasterization pinned to CPU (`ingestion/docling_reader.py:181-186`, `retrieval/local_embedding.py:53-70`).
- **Context budgeting:** Input budget is `max_context_tokens - max_output_tokens` with prompt, context, then newest-first history truncation (`core/prompt_budget.py:92-148`). Do not bypass `assemble_grounded_messages` for chat prompts.
- **Untrusted input:** Document text is wrapped in `<document_context>` and tag-spoofing is escaped (`core/prompt_budget.py:34-48`). Rendered markdown is sanitized in local mode (`ui/sanitizer.py:73-140`).
- **Privacy boundary:** Local mode must not construct cloud providers (`core/local_llm.py:197-213`); cloud providers assert consent (`providers/litellm_provider.py:142-148`, `providers/groq_provider.py:62-68`); llama.cpp rejects non-loopback hosts unless explicitly overridden (`providers/llama_cpp_provider.py:62-79`).
- **Persistence ordering:** Ingestion writes SQLite then vectors and marks `failed` on vector error; deletion writes vectors first then SQLite; purge drops vectors first. This keeps SQLite authoritative and recoverable.
- **Windows filesystem locks:** SQLite uses a fresh connection per operation and closes deterministically (`core/doc_store.py:132-149`); do not hold long-lived connections.
- **Streamlit rerun model:** The whole script re-executes on every interaction. Expensive objects must be cached in `st.session_state`; health probes are throttled to 5 s (`main.py:159-178`).
- **Deterministic identity:** `doc_id = doc_<sha256[:16]>`, chunk IDs `{sha12}_p{page}_{idx:04d}`, element IDs `elem_{doc_id}_p{page}_{kind}_{idx:02d}`. Identity must not depend on filename.
- **Model identity:** `start.py` verifies GGUF architecture/projector metadata before launching llama-server (`start.py:140-149`; `core/model_identity.py:124-162`).

## Anti-Patterns

### Business logic in renderers

**What happens:** `render_chat_view` performs retrieval, query rewriting, doc-scope inference, citation filtering, and assistant-turn persistence directly (`ui/views.py:363-483`). Services are instantiated inside render functions (`ui/views.py:76-81, 170-175, 682-687`).
**Why it's wrong:** Logic is untestable without Streamlit, duplicated in `core/local_llm.py:271-320`, and re-created on every rerun.
**Do this instead:** Extract a `ChatService` that takes the query, history, scope, and returns `(RetrievalResult, CitationVerificationResult, text)`; keep renderers to widget wiring. Follow the existing service shape in `ui/ingestion_service.py` and `ui/lifecycle_service.py`.

### Duplicated fallback mirror

**What happens:** `HybridRetriever` always maintains an in-memory `VectorIndex` copy and rewrites `fallback_store.json` on every index/delete, even when LanceDB is healthy (`retrieval/hybrid_retriever.py:196-200, 381-394, 486-490, 552-554`).
**Why it's wrong:** Doubles memory for every chunk and embedding, adds O(n) I/O on each write, and can resurrect stale rows if the mirror drifts.
**Do this instead:** Treat SQLite chunks as the authoritative recovery source (as `ui/hydration.py:64-85` and `ui/lifecycle_service.py:148-188` already do) and rebuild the fallback only when LanceDB is unavailable. If the mirror is kept, write it only on fallback-mode transitions.

### Broad `except Exception` around multi-stage work

**What happens:** OCR, visual analysis, cache writes, and session cleanup catch `Exception`, log a warning, and continue (`ui/ingestion_service.py:186-187, 209-210, 339-340`; `ui/lifecycle_service.py:58-65`; `ui/hydration.py:82-84`).
**Why it's wrong:** Partial success becomes indistinguishable from full success unless callers inspect every result field; programming errors are hidden as warnings.
**Do this instead:** Catch the specific parser/IO exceptions you intend to degrade on, record an explicit degradation flag on `IngestionResult` (the existing `fallback_used` field is the model), and let unexpected exceptions propagate.

### Legacy retrieval shims in new code

**What happens:** `HybridRetriever.search`, `get_context`, and `LocalEmbedding.search_hybrid` remain as deprecated facades (`retrieval/hybrid_retriever.py:855-873`, `retrieval/local_embedding.py:113-149`).
**Why it's wrong:** New call sites can silently lose rank metadata, bbox provenance, and RRF fusion.
**Do this instead:** Always call `HybridRetriever.search_hybrid(...)` and pass the returned `RetrievalResult` explicitly to `AiModel`.

### Scattered constants and duplicate definitions

**What happens:** `MAX_CHAT_TURNS` is defined in both `main.py:45` and `ui/views.py:34`; upload caps live in `ingestion/upload_validation.py:15-16` but Streamlit's own cap is separately set in `.streamlit/config.toml`.
**Why it's wrong:** Drift makes UI and backend disagree about limits.
**Do this instead:** Import shared limits from the owning module (`from ingestion.upload_validation import MAX_FILE_MB`) as `ui/views.py:30` already does, and keep a single constant per concern.

### `print` in library code

**What happens:** `DocStore` migration, upload validation, and `PdfReader` print to stdout (`core/doc_store.py:164`, `ingestion/upload_validation.py:106`, `ingestion/pdf_reader.py:131`).
**Why it's wrong:** Bypasses logging configuration and pollutes Streamlit's console.
**Do this instead:** Use the module logger (`logger = logging.getLogger(__name__)`), as the majority of modules do.

## Error Handling

**Strategy:** Fail closed on privacy and vector persistence; degrade gracefully on extraction and visual enrichment; aggregate multi-tier failures rather than hiding them.

**Patterns:**
- **Validation errors** become user-actionable `IngestionResult.error` strings (`ui/ingestion_service.py:78-91`).
- **Extraction degradation:** Docling import/conversion failure or empty output falls back to pypdf (`ingestion/docling_reader.py:165-171, 272-281, 415-421`); the returned `fallback_used` flag is propagated to the UI.
- **Per-page isolation:** OCR catches per page and returns a `Page(status="failed", error=...)`, never aborting the document (`ingestion/ocr_fallback.py:302-315`).
- **Vector failures are fatal to ingestion:** `VectorIndexError` is raised and the document is marked `failed` so it cannot masquerade as indexed (`retrieval/hybrid_retriever.py:74-80, 476-484`; `ui/ingestion_service.py:300-327`).
- **Delete ordering:** vector deletion failure aborts before SQLite mutation (`ui/lifecycle_service.py:48-53`).
- **Purge aggregation:** collects tier failures, cleans session state anyway, then raises one `RuntimeError` (`ui/lifecycle_service.py:100-146`).
- **Inference failures:** gate timeout yields a user-facing busy message (`core/local_llm.py:336-339`); provider HTTP errors become `RuntimeError` (`providers/llama_cpp_provider.py:203-206`); the chat view catches streaming errors and appends an interrupted turn (`ui/views.py:484-496`).
- **Security rejections:** missing cloud consent raises `PermissionError` (`core/local_llm.py:122-126`, `177-181`); injection echoes fail validation (`core/citation_validator.py:150-163`).

## Cross-Cutting Concerns

**Logging:** Standard `logging.getLogger(__name__)` per module; no centralized formatter configuration in-app (Streamlit provides the handler). `core/logging_setup.py` filters the benign `torch.classes` watcher traceback, invoked from `main.py:42-43`. Startup/launcher output uses `print` intentionally (`start.py`).

**Validation:** Pydantic v2 models validate at every boundary (`core/models.py`, `providers/model_provider.py`); upload validation is explicit (`ingestion/upload_validation.py`); SQLite rows are re-validated on read; summary profiles are checked against `VALID_SUMMARY_PROFILES` (`core/summarizer.py:398-401`).

**Authentication / authorization:** No user accounts. The security boundary is local-vs-cloud consent plus loopback-only llama-server access. Cloud keys resolve in order: explicit arg → session state → Streamlit secrets → environment (`providers/litellm_provider.py:44-88`), and are scrubbed from error text (`providers/litellm_provider.py:135-140`).

**Privacy / sanitization:** `ui/sanitizer.py` removes scripts/embeds, blocks `javascript:`/`data:` schemes, and neutralizes external links, images, autolinks, `srcset`, CSS `url()`, and SVG references when `allow_external=False` (`ui/sanitizer.py:73-140`). Cloud mode permits external links only after consent (`ui/views.py:282-285, 606-607`).

**Telemetry:** VRAM via `nvidia-smi` with 5 s TTL and graceful `None` on CPU/CI (`core/resource_telemetry.py:33-97`); RSS via psutil (`core/resource_telemetry.py:169-192`); stage latency via `LatencyTracker` / `track_stage` (`core/resource_telemetry.py:194-275`).

---

*Architecture analysis: 2026-10-21*
