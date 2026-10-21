<!-- refreshed: 2026-10-21 -->
# Architecture

**Analysis Date:** 2026-10-21

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION — Streamlit script, AMOLED theme, 4 workspaces                  │
│  `main.py` · `ui/views.py` · `ui/components.py` · `ui/theme.py`              │
│  `ui/sanitizer.py` · `.streamlit/config.toml` · `assets/icons/*.svg`         │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐
│ UI ORCHESTRATION SERVICES           │  │ DOMAIN SERVICES                     │
│ `ui/ingestion_service.py`           │  │ `core/local_llm.py` — AiModel       │
│ `ui/lifecycle_service.py`           │  │ `core/summarizer.py` — Summarizer   │
│ `ui/hydration.py`                   │  │ `core/citation_validator.py`        │
│                                     │  │ `core/prompt_budget.py`             │
└───────────────┬─────────────────────┘  └───────────────┬─────────────────────┘
                │                                        │
                ▼                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ INGESTION PIPELINE                                                           │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`             │
│   → `ingestion/pdf_reader.py` (fallback) → `ingestion/ocr_fallback.py`       │
│   → `ingestion/visual_analyzer.py`                                           │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌─────────────────────────────────────┐  ┌─────────────────────────────────────┐
│ RETRIEVAL                           │  │ PERSISTENCE                         │
│ `retrieval/local_embedding.py`      │  │ `core/doc_store.py` — SQLite        │
│ `retrieval/hybrid_retriever.py`     │  │ `data/documents.db`                 │
│ `retrieval/vector_index.py`         │  │ `retrieval/data/lancedb/` (default) │
│                                     │  │ `.cache/<sha256>/<CONFIG_VERSION>/` │
└───────────────┬─────────────────────┘  └─────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ INFERENCE PROVIDERS (BaseModelProvider ABC)                                 │
│ `providers/llama_cpp_provider.py` (default, loopback-only)                  │
│ `providers/litellm_provider.py` (consent-gated cloud)                       │
│ `providers/groq_provider.py` (direct cloud fallback)                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Composition root | Page config, theme injection, session-state defaults, DocStore + AiModel construction, cloud-mode sync, workspace routing | `main.py` |
| Sidebar renderer | PDF upload, uploader-key rotation, per-file ingestion, active-document list, delete buttons | `ui/views.py:50` |
| Chat renderer | Focus filter, retrieval call, streaming answer, citation chips, evidence drawer, verification captions | `ui/views.py:185` |
| Summarizer renderer | Profile selection, summary generation, SQLite cache lookup, markdown export | `ui/views.py:503` |
| Library renderer | Document listing, re-index, delete, purge-all danger zone | `ui/views.py:620` |
| Settings renderer | Cloud consent toggle, API-key entry, VRAM/RAM telemetry, cache reset | `ui/views.py:731` |
| Ingestion orchestrator | Validation → dedupe → extraction → OCR → visual analysis → SQLite → LanceDB → cache | `ui/ingestion_service.py:39` |
| Lifecycle orchestrator | Cross-store delete, purge, and re-index | `ui/lifecycle_service.py:16` |
| Startup hydration | Restore document catalog and repair missing vectors | `ui/hydration.py:13` |
| Inference facade | Provider routing, grounded message assembly, streaming, citation validation | `core/local_llm.py:93` |
| VRAM concurrency gate | Process-wide reentrant lock serializing all LLM/VLM/summarizer inference | `core/local_llm.py:26` |
| Summarizer | Single-pass vs map-reduce summarization with page-citation propagation and SQLite cache | `core/summarizer.py:153` |
| Prompt budgeter | Token estimation, XML `<document_context>` isolation, oldest-first truncation | `core/prompt_budget.py:65` |
| Citation validator | `[E#]` precision scoring, abstention detection, injection detection | `core/citation_validator.py:115` |
| Metadata store | SQLite WAL store with migrations v1–v4, chunks/pages/evidence/summaries | `core/doc_store.py:113` |
| Hybrid retriever | Dense + FTS candidate pools fused with RRF, LanceDB with in-memory/disk fallback | `retrieval/hybrid_retriever.py:110` |
| Embedding service | CPU-pinned `all-MiniLM-L6-v2`, 384-dim normalized vectors, process-level model cache | `retrieval/local_embedding.py:27` |
| In-memory vector index | Pure-Python cosine/euclidean nearest-neighbour fallback | `retrieval/vector_index.py:15` |
| Upload validator | `%PDF` magic bytes, 50 MB / 500 page caps, streaming SHA-256, `doc_<sha16>` | `ingestion/upload_validation.py:64` |
| Docling reader | Layout/reading-order/markdown-table extraction with pypdf fallback | `ingestion/docling_reader.py:35` |
| pypdf reader | Page-level text extraction and per-page fault isolation | `ingestion/pdf_reader.py:11` |
| OCR fallback | Conditional RapidOCR for pages < 50 chars, thread-pooled page batches | `ingestion/ocr_fallback.py:318` |
| Visual analyzer | Figure/vector-diagram detection, 2× PNG crops, VLM descriptions | `ingestion/visual_analyzer.py:31` |
| Provider contract | ABC + `ProviderCapabilities` / `HealthStatus` schemas | `providers/model_provider.py:64` |
| Local provider | llama-server HTTP/SSE client with loopback enforcement | `providers/llama_cpp_provider.py:24` |
| Cloud adapter | LiteLLM routing with hard consent gate and key scrubbing | `providers/litellm_provider.py:104` |
| Telemetry | nvidia-smi GPU sampling (5 s TTL), psutil RSS, stage latency tracking | `core/resource_telemetry.py:33` |
| Launcher | Pre-flight checks, optional llama-server spawn, Streamlit subprocess | `start.py:214` |
| Setup CLI | Dependency install, GGUF download, llama-server binary acquisition | `setup.py:535` |

## Pattern Overview

**Overall:** Modular monolith with layered presentation/orchestration/domain/infrastructure separation; a pipeline-and-facade architecture rather than microservices or full hexagonal/Clean Architecture.

**Key Characteristics:**
- Single Streamlit process, one script re-executed top-to-bottom per interaction (`main.py`). All mutable UI state lives in `st.session_state`; persistence lives outside it.
- Services are instantiated per operation (not module-level singletons): `IngestionService`, `LifecycleService`, `Summarizer` are constructed inside view handlers (`ui/views.py:75`, `ui/views.py:169`, `ui/views.py:564`).
- Provider abstraction via `BaseModelProvider` (`providers/model_provider.py:64`) keeps local llama.cpp and cloud LiteLLM/Groq interchangeable behind `AiModel`.
- Persistence is three-tier and intentionally redundant: SQLite is the source of truth, LanceDB is the searchable projection, `.cache/` holds raw extraction artifacts keyed by content hash.
- Fallback chains exist at every fragile boundary (Docling → pypdf, LanceDB → in-memory/disk vector index, FTS → BM25, mistyped/absent providers → re-probe).
- Hard safety invariants are encoded in code, not convention: `InferenceGate` lock, LiteLLM `_assert_consent()` (`providers/litellm_provider.py:142`), loopback-only llama URL (`providers/llama_cpp_provider.py:69`), and markdown sanitization (`ui/sanitizer.py:33`).

## Layers

**Presentation:**
- Purpose: Render the four workspaces and translate widget events into service calls.
- Location: `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`
- Contains: Streamlit layout code, HTML/CSS injection, local SVG icon formatting, citation chips, markdown sanitization.
- Depends on: `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `core/*`, `retrieval/*`.
- Used by: Streamlit runtime; `start.py` launches it.

**UI Orchestration:**
- Purpose: Coordinate multi-step workflows that span extraction, storage, indexing, and session state.
- Location: `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`
- Contains: `IngestionService.ingest_pdf` (`ui/ingestion_service.py:54`), `LifecycleService.delete_document/purge_all/reindex_document` (`ui/lifecycle_service.py:31`, `:89`, `:134`), `hydrate_startup_state` (`ui/hydration.py:13`).
- Depends on: `ingestion/*`, `retrieval/*`, `core/doc_store.py`, `core/models.py`.
- Used by: `ui/views.py`, `main.py`.

**Domain Services:**
- Purpose: Grounded generation, summarization, citation verification, and prompt budgeting.
- Location: `core/local_llm.py`, `core/summarizer.py`, `core/citation_validator.py`, `core/prompt_budget.py`
- Contains: `AiModel`, `InferenceGate`, `Summarizer`, `validate_citations`, `assemble_grounded_messages`.
- Depends on: `providers/*`, `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `core/models.py`.
- Used by: `ui/views.py`, `ui/ingestion_service.py` (via provider passed for VLM).

**Ingestion:**
- Purpose: Turn untrusted PDF bytes into canonical chunks, page records, and visual evidence.
- Location: `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py`
- Contains: Validators, extractors, OCR engine, region detector/cropper.
- Depends on: `core/models.py` (`Chunk`, `Page`, `EvidenceElement`, `BBox`), PyMuPDF, Docling, RapidOCR, LangChain splitter.
- Used by: `ui/ingestion_service.py`.

**Retrieval:**
- Purpose: Embed, index, and search chunks with hybrid dense+FTS fusion.
- Location: `retrieval/local_embedding.py`, `retrieval/hybrid_retriever.py`, `retrieval/vector_index.py`
- Contains: `LocalEmbedding`, `HybridRetriever`, `compute_rrf`, `VectorIndex`.
- Depends on: `core/models.py`, LanceDB/PyArrow, sentence-transformers.
- Used by: `ui/views.py` (chat), `ui/hydration.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `core/local_llm.py`.

**Persistence:**
- Purpose: Durable metadata and vectors.
- Location: `core/doc_store.py`, `data/documents.db`, `retrieval/data/lancedb/` (DEFAULT_DB_URI, `retrieval/hybrid_retriever.py:58`), `.cache/`
- Contains: SQLite DDL/migrations, CRUD for documents/pages/chunks/evidence/summaries.
- Depends on: stdlib `sqlite3`, `core/models.py`.
- Used by: nearly every service; UI never writes SQL directly.

**Inference Providers:**
- Purpose: Abstract local and cloud model I/O.
- Location: `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`
- Contains: ABC, capability/health schemas, HTTP/SSE local client, consent-gated cloud adapters.
- Depends on: `httpx`, `litellm`, `groq`.
- Used by: `core/local_llm.py`, `core/summarizer.py`, `ingestion/visual_analyzer.py`.

## Data Flow

### Primary Ingestion Path

1. Sidebar uploader accepts PDFs under a rotating widget key (`ui/views.py:63`, key rotated at `ui/views.py:124`).
2. `IngestionService.ingest_pdf` validates magic bytes, size, page count and derives `doc_<sha16>` (`ui/ingestion_service.py:81` → `ingestion/upload_validation.py:64`).
3. SHA-256 dedupe check against SQLite; if the document is already indexed, verify LanceDB vectors and repair from stored chunks when missing (`ui/ingestion_service.py:98`–`:137`).
4. `DoclingReader.extract_text` builds per-page `Page` records and `Chunk` dicts, falling back to `PdfReader` on import failure, conversion error, or empty output (`ingestion/docling_reader.py:117`, `:206`, `:332`).
5. `apply_conditional_ocr` re-processes pages with `< 50` chars or `empty`/`failed` status, rendering at 150 DPI and splitting OCR text into chunks (`ingestion/ocr_fallback.py:35`, `:318`).
6. `VisualAnalyzer.detect_visual_regions` + `analyze_visual_elements` produce `EvidenceElement`s for images and vector diagram clusters, capped at 6 during ingestion (`ui/ingestion_service.py:200`, `ingestion/visual_analyzer.py:202`).
7. Zero-chunk guard marks the document `failed` and returns early (`ui/ingestion_service.py:211`).
8. Atomic-ish SQLite writes: document row, evidence rows, page batch, chunk batch (`ui/ingestion_service.py:248`–`:255`).
9. `LocalEmbedding.get_embeddings` + `HybridRetriever.index_chunks` populate LanceDB and refresh the FTS index (`ui/ingestion_service.py:277`, `retrieval/hybrid_retriever.py:278`); failures roll the document status back to `failed` (`ui/ingestion_service.py:283`–`:309`).
10. Raw extraction artifacts are written to `.cache/<sha256>/docling-1000-200-v1/` as `pages.json`, `chunks.json`, `manifest.json` (`ui/ingestion_service.py:311`, `core/models.py:17`).

### Chat / Grounded QA Path

1. `render_chat_view` resolves the focus document filter and builds a search query, expanding 4-token-or-shorter follow-ups with the previous user turn (`ui/views.py:362`–`:378`).
2. `HybridRetriever.search_hybrid(query, k=8, doc_id=...)` runs dense search (`retrieval/hybrid_retriever.py:476`), FTS (`:594`), and RRF fusion (`:62`, `:700`), returning an immutable `RetrievalResult` of ranked `EvidenceSnippet`s.
3. `RetrievalResult.formatted_evidence()` renders numbered `[E1]` blocks with `(filename, p. N)` headers (`core/models.py:185`).
4. `AiModel.ask_a_question_from_pdf_stream` assembles bounded messages via `assemble_grounded_messages` (`core/local_llm.py:305`, `core/prompt_budget.py:65`), acquires `InferenceGate` (`core/local_llm.py:317`), and streams provider tokens (`:323`).
5. `st.write_stream` renders tokens; then `AiModel.validate_response` scores `[E#]` precision against the exact snippets shown to the model (`ui/views.py:420`–`:427`, `core/citation_validator.py:115`).
6. Citation chips and the evidence expander render only cited ranks when citations exist (`ui/views.py:439`–`:470`); the turn (content, snippets, verification, model provenance) is appended to `st.session_state.chat_history` (`ui/views.py:472`).

### Summarization Path

1. `render_summarizer_view` selects a document/profile and optionally bypasses cache (`ui/views.py:540`–`:556`).
2. `Summarizer.summarize_document` validates the profile, computes `model_version = "<model>:<CONFIG_VERSION>"`, and checks the SQLite summary cache (`core/summarizer.py:323`–`:337`).
3. Pages are reconstructed from supplied `Page`s or grouped from stored chunks (`core/summarizer.py:339`–`:379`).
4. `InferenceGate.hold(timeout=120.0)` wraps either single-pass (≤ 2,500 estimated tokens) or map-reduce (`core/summarizer.py:389`–`:395`).
5. Map-reduce bundles pages at ≤ 2,000 estimated tokens per batch, maps sequentially, optionally consolidates in halves, then reduces while preserving `(p. X)` citations (`core/summarizer.py:245`–`:299`).
6. Page references are extracted and clamped to the document's max page (`core/summarizer.py:397`–`:399`), the `SummaryResult` is persisted, and the UI renders/export it (`ui/views.py:566`–`:612`).

### Startup Hydration Path

1. `main.py` constructs `DocStore(data/documents.db)` at module scope (`main.py:139`–`:142`).
2. `hydrate_startup_state` short-circuits on the `_startup_hydrated` session flag (`ui/hydration.py:19`).
3. Indexed and failed documents are replayed into `st.session_state.doc_ids`, `indexed_files`, and `document_metadata`; a `HybridRetriever` is created and bound to a shared `LocalEmbedding` (`ui/hydration.py:30`–`:58`).
4. Each indexed document without vectors is re-embedded from SQLite chunks, otherwise flagged `needs_reindex` (`ui/hydration.py:63`–`:72`).

### Deletion / Purge Path

1. `LifecycleService.delete_document` captures SHA/filename, deletes SQLite rows, LanceDB rows, the hash cache directory, then scrubs session state (`ui/lifecycle_service.py:41`–`:85`).
2. `purge_all` clears SQLite + `VACUUM`, drops the LanceDB table, removes `.cache/`, and resets chat/session state (`ui/lifecycle_service.py:89`–`:132`).

**State Management:**
- Durable state: SQLite (`data/documents.db`), LanceDB (default `retrieval/data/lancedb/`; an existing index also sits at `data/lancedb/`, and benchmarks use `data/lancedb_bench/`), disk cache (`.cache/`).
- Ephemeral state: `st.session_state` keys initialized in `main.py:112`–`:132` — `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, `cloud_mode`, `user_consented`, `uploader_key`, `active_workspace`, `ai_model`, `active_cloud_provider`.
- Chat history is bounded to 50 turns by `bound_chat_history` (`ui/views.py:36`–`:42`, `core/prompt_budget.py:153`).

## Key Abstractions

**`AiModel` (`core/local_llm.py:93`):**
- Purpose: Single entry point for Q&A generation and citation verification regardless of backend.
- Examples: constructed per session at `main.py:148`; cloud mode toggled at `main.py:162`.
- Pattern: Facade + Strategy (delegates to `BaseModelProvider`); owns `last_retrieval_result` and `last_verification_result`.

**`InferenceGate` (`core/local_llm.py:26`):**
- Purpose: Guarantee at most one GPU-resident inference operation at a time inside the 4 GB VRAM budget.
- Examples: chat streaming (`core/local_llm.py:317`), non-streaming generation (`:352`), summarization (`core/summarizer.py:389`), VLM crops (`ingestion/visual_analyzer.py:277`).
- Pattern: Process-level `threading.RLock` with `hold()` context manager and timeout → `TimeoutError`.

**`BaseModelProvider` (`providers/model_provider.py:64`):**
- Purpose: Uniform contract for `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Examples: `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`.
- Pattern: Abstract Base Class + immutable Pydantic capability/health value objects.

**`RetrievalResult` / `EvidenceSnippet` (`core/models.py:171`, `:142`):**
- Purpose: One immutable ranking container shared between prompt construction and UI citation rendering, eliminating rank drift.
- Examples: produced by `HybridRetriever.search_hybrid` (`retrieval/hybrid_retriever.py:731`), consumed by `formatted_evidence()` and `validate_citations`.
- Pattern: Value object with render helpers (`formatted_evidence`, `source_labels`).

**Canonical document models (`core/models.py`):**
- `Document` (`:116`), `Page` (`:75`), `Chunk` (`:54`), `EvidenceElement` (`:91`), `BBox` (`:33`), `SummaryResult` (`:212`).
- Purpose: Validate IDs, page bounds, SHA-256 format, and bbox geometry at every storage boundary.
- Pattern: Frozen/forbidding Pydantic v2 models with `model_validator` invariants (`doc_`/`summ_` prefixes, hex digests).

**`HybridRetriever` (`retrieval/hybrid_retriever.py:110`):**
- Purpose: Persistent searchable projection with graceful degradation.
- Pattern: Adapter over LanceDB plus dual fallback (`VectorIndex` in memory, `fallback_store.json` on disk), RRF fusion of two retrieval modalities.

**`IngestionService` / `LifecycleService`:**
- Purpose: Transaction boundaries across heterogeneous stores.
- Pattern: Orchestrator/service layer; views never mutate SQLite or LanceDB directly.

## Entry Points

**Streamlit application:**
- Location: `main.py`
- Triggers: `streamlit run main.py`, or `python start.py` which spawns it (`start.py:181`).
- Responsibilities: Page config (`main.py:98`), theme (`:106`), session defaults (`:112`), DocStore/AiModel construction (`:139`–`:159`), cloud provider sync (`:162`–`:188`), consent dialog (`:200`–`:244`), sidebar (`:251`–`:328`), workspace routing (`:335`–`:362`).

**Launcher:**
- Location: `start.py`
- Triggers: `python start.py [--start-llama] [--port ...] [--ngl ...] [--ctx ...]`
- Responsibilities: Python ≥ 3.11 check (`start.py:49`), directory creation (`:57`), llama-server discovery/probe (`:69`, `:82`), optional background spawn (`:114`), Streamlit subprocess (`:181`), teardown (`:253`).

**Setup CLI:**
- Location: `setup.py`
- Triggers: `python setup.py`, `python setup.py download_models`, `python setup.py setup_llama_server`, or console scripts `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:638`+).
- Responsibilities: Dependency install, GGUF download to `models/`, llama-server extraction to `tools/llama-server/`, editable package install.

**Benchmark/profiling scripts:**
- `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py` — invoked manually, not imported by the app.

## Architectural Constraints

- **Threading:** Streamlit runs one script thread per session; `OcrEngine` serializes recognizer calls with `threading.Lock` (`ingestion/ocr_fallback.py:68`) and OCR pages with a `ThreadPoolExecutor` capped at 4 (`:390`). All model inference is serialized globally by `InferenceGate`.
- **Global state:** Module-level caches exist in `retrieval/local_embedding.py:24` (`_MODEL_CACHE`, process-level `SentenceTransformer`), `core/resource_telemetry.py:21`–`:30` (`_LATENCY_HISTORY`, GPU cache), and `ui/components.py:11` (`_ICON_CACHE`). `InferenceGate` holds class-level lock state (`core/local_llm.py:34`).
- **No cross-request DB connection reuse:** `DocStore._connect` opens and closes a connection per operation with WAL/busy timeout (`core/doc_store.py:132`–`:149`) to tolerate Windows locks and Streamlit's loop.
- **Circular imports:** `ingestion/visual_analyzer.py:275` imports `InferenceGate` lazily inside the analysis loop to avoid the `core.local_llm` → `retrieval` → `ingestion` dependency cycle at module import time.
- **VRAM ceiling:** context defaults to 4,096 tokens (`core/prompt_budget.py:69`, `providers/llama_cpp_provider.py:31`); summary fast-path/map budgets are 2,500/2,000 tokens (`core/summarizer.py:28`–`:29`); embeddings and OCR are CPU-pinned (`retrieval/local_embedding.py:55`, `ingestion/ocr_fallback.py:70`).
- **Local-only egress:** `LlamaCppProvider` rejects non-loopback hosts unless `allow_remote=True` (`providers/llama_cpp_provider.py:69`); cloud calls require explicit consent (`providers/litellm_provider.py:142`); UI markdown is sanitized unless cloud mode + consent (`ui/views.py:281`, `ui/sanitizer.py:33`).
- **Single active model:** Cloud mode swaps the provider on the session-scoped `AiModel` rather than running local and cloud concurrently (`core/local_llm.py:145`–`:166`).

## Anti-Patterns

### Mixed model/dict representations at service boundaries

**What happens:** Extractors return `Chunk` dicts (`ingestion/docling_reader.py:282`, `ingestion/pdf_reader.py:103`, `ingestion/ocr_fallback.py:287`), while `DocStore.record_chunks` requires `Chunk` instances (`core/doc_store.py:300`). `IngestionService` re-validates with `Chunk.model_validate(p)` (`ui/ingestion_service.py:254`).
**Why it's wrong:** Type errors surface late, fields silently drift between dict keys and model fields, and callers must know which representation each layer accepts.
**Do this instead:** Standardize on Pydantic models through orchestration and only call `model_dump()` at the storage/transport edge (as `HybridRetriever.index_chunks` already accepts both, `retrieval/hybrid_retriever.py:278`).

### Broad exception swallowing in retrieval fallbacks

**What happens:** LanceDB errors are logged at warning/debug and silently fall through to BM25 or the in-memory index (`retrieval/hybrid_retriever.py:506`–`:520`, `:618`–`:621`).
**Why it's wrong:** A corrupted or partially migrated index can look like "no results," and callers cannot distinguish an empty corpus from a failed backend without inspecting logs.
**Do this instead:** Surface degradation through `RetrievalResult.search_mode` (`"fallback"` already exists at `retrieval/hybrid_retriever.py:698`) and propagate a health flag to the Settings/chip UI.

### Duplicated follow-up query rewriting

**What happens:** The same short-follow-up heuristic (≤ 4 tokens matched against a pronoun set) is implemented in `core/local_llm.py:252`–`:281` and again in `ui/views.py:364`–`:378`.
**Why it's wrong:** The two copies can diverge, so the query used for retrieval and the query reasoned about by the model may differ.
**Do this instead:** Extract one helper (e.g., in `core/prompt_budget.py` or `retrieval/`) and call it from both paths, or make `AiModel` the sole owner of retrieval-query construction.

### Script-style top-level execution in `main.py`

**What happens:** Page config, model construction, and view routing execute at import time (`main.py:98` onward), so importing `main` runs the whole app.
**Why it's wrong:** The composition root is hard to unit test; `tests/test_main_ui.py` tests data contracts instead of importing `main`.
**Do this instead:** Move the body into a `main()`/`run_app()` function guarded by `if __name__ == "__main__":` (or `ui/app.py`) and keep `main.py` as a thin entry shim.

### UI importing concrete infrastructure directly

**What happens:** `ui/views.py` imports `Summarizer`, `IngestionService`, `LifecycleService`, `DocStore`, and telemetry functions and wires them itself (`ui/views.py:11`–`:29`).
**Why it's wrong:** Dependency wiring is repeated in three view functions, making provider/store substitution and testing harder.
**Do this instead:** Build a per-session service container in `main.py` (or a `ui/context.py`) and pass services into renderers, mirroring how `doc_store`/`ai_model` are already injected.

## Error Handling

**Strategy:** Fail soft at the document/page level, fail fast at the input-validation boundary, and roll back persistent status when indexing fails.

**Patterns:**
- **Validation-first:** `validate_pdf_bytes` raises `ValueError` with user-actionable text before any extraction (`ingestion/upload_validation.py:64`), converted into `IngestionResult.error` (`ui/ingestion_service.py:80`).
- **Layered fallback:** Docling → pypdf (`ingestion/docling_reader.py:117`, `:332`); LanceDB → `VectorIndex`/JSON (`retrieval/hybrid_retriever.py:143`–`:155`); FTS → pure-Python BM25 (`:621`); provider re-probe on unhealthy (`core/local_llm.py:187`–`:207`).
- **Page-level fault isolation:** pypdf records `status="failed"` and continues (`ingestion/pdf_reader.py:116`); OCR failures return the original page unchanged (`ingestion/ocr_fallback.py:302`).
- **Status rollback:** LanceDB indexing failure rewrites the document row to `status="failed"` (`ui/ingestion_service.py:286`–`:298`).
- **Gate timeout as user-visible message:** streaming yields a busy message instead of raising (`core/local_llm.py:318`–`:320`); non-streaming raises `TimeoutError` (`:82`–`:86`).
- **Sanitized cloud errors:** LiteLLM errors are scrubbed of API keys before logging/raising (`providers/litellm_provider.py:135`–`:140`).
- **UI containment:** chat streaming errors are displayed and recorded as an assistant turn rather than crashing the rerun (`ui/views.py:483`–`:495`).

## Cross-Cutting Concerns

**Logging:** Standard library `logging.getLogger(__name__)` per module; no central `dictConfig`. One targeted filter suppresses Streamlit's benign `torch.classes` watcher traceback (`core/logging_setup.py:16`), wired in `main.py:41`.

**Validation:** Pydantic v2 models validate IDs, SHA-256 patterns, page bounds, bbox geometry, and profile enums (`core/models.py`). SQLite rows and LanceDB rows are re-validated on read (`core/doc_store.py:221`, `retrieval/hybrid_retriever.py:714`).

**Authentication:** No user accounts. The only auth-like boundary is cloud consent (`main.py:200`–`:244`, `providers/litellm_provider.py:142`) plus per-session API keys held in `st.session_state.cloud_api_keys` (`main.py:91`).

**Privacy enforcement:** Markdown/HTML neutralization (`ui/sanitizer.py:33`), loopback URL validation (`providers/llama_cpp_provider.py:56`–`:73`), LiteLLM telemetry disabled (`providers/litellm_provider.py:19`–`:24`), and visual analysis restricted to local vision-capable providers (`ingestion/visual_analyzer.py:244`–`:251`).

**Observability:** `LatencyTracker`/`track_stage` (`core/resource_telemetry.py:194`, `:250`) and `get_system_telemetry_snapshot` (`:287`) expose GPU VRAM, process RSS/VMS, and per-stage averages; rendered in Settings (`ui/views.py:833`–`:851`).

---

*Architecture analysis: 2026-10-21*
