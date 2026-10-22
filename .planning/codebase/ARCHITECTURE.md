<!-- refreshed: 2026-10-22 -->
# Architecture

**Analysis Date:** 2026-10-22

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Presentation — Streamlit composition root                                    │
│ `main.py` · `ui/views.py` · `ui/components.py` · `ui/theme.py`                │
│ `ui/sanitizer.py` · `ui/session_state.py` · `.streamlit/config.toml`          │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌─────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ UI Orchestration Services           │   │ Domain Services                      │
│ `ui/ingestion_service.py`           │   │ `core/local_llm.py` (AiModel, Gate)   │
│ `ui/lifecycle_service.py`           │   │ `core/summarizer.py`                  │
│ `ui/hydration.py`                   │   │ `core/query_intent.py`                │
│                                     │   │ `core/citation_validator.py`          │
│                                     │   │ `core/prompt_budget.py`               │
└───────────────┬─────────────────────┘   └──────────────────┬───────────────────┘
                │                                            │
                ▼                                            ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Ingestion Pipeline                                                           │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`              │
│ → `ingestion/pdf_reader.py` fallback → `ingestion/ocr_fallback.py`            │
│ → `ingestion/visual_analyzer.py`                                             │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌─────────────────────────────────────┐   ┌──────────────────────────────────────┐
│ Retrieval & Persistence             │   │ Inference Providers                  │
│ `retrieval/local_embedding.py`      │   │ `providers/model_provider.py` (ABC)   │
│ `retrieval/hybrid_retriever.py`     │   │ `providers/llama_cpp_provider.py`     │
│ `retrieval/vector_index.py`         │   │ `providers/litellm_provider.py`       │
│ `core/doc_store.py` (SQLite)        │   │ `providers/groq_provider.py`          │
│ `core/models.py`                    │   │                                      │
└─────────────────────────────────────┘   └──────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Local disk: `data/documents.db`, `data/lancedb/`, `data/logs/`                │
│ Runtime binaries: `tools/llama-server/`, model weights: `models/`             │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit composition root | Page config, session defaults, store/model construction, hydration, cloud sync, workspace routing | `main.py` |
| Chat workspace | Query contextualization, retrieval, streaming, citation chips, evidence drawer | `ui/views.py` (`render_chat_view`) |
| Summarizer workspace | Five profiles, session/SQLite cache lookup, markdown export | `ui/views.py` (`render_summarizer_view`) |
| Library workspace | Document inspect, re-index, delete, purge-by-confirmation | `ui/views.py` (`render_library_view`) |
| Settings workspace | Cloud consent/keys, VRAM/RAM telemetry, store counts, session/cache reset | `ui/views.py` (`render_settings_view`) |
| Ingestion orchestration | Validate → dedupe/repair → extract → OCR → visual VLM → SQLite → embeddings → vector index | `ui/ingestion_service.py` |
| Lifecycle orchestration | Atomic delete, full purge with VACUUM, re-index from SQLite chunks | `ui/lifecycle_service.py` |
| Startup hydration | Restore catalog/metadata, verify vectors, repair only missing docs | `ui/hydration.py` |
| Session reset | Shared teardown of documents, models, history, summaries, credentials | `ui/session_state.py` |
| Inference facade | Provider routing, retrieval assembly, prompt budgeting, gate ownership, citation validation | `core/local_llm.py` |
| Concurrency gate | Process-wide RLock serializing GPU inference | `core/local_llm.py` (`InferenceGate`) |
| Summary engine | Single-pass or map-reduce with page citations and SQLite cache | `core/summarizer.py` |
| Query intent | Follow-up rewrite, whole-document detection, page-diverse evidence selection | `core/query_intent.py` |
| Prompt budgeting | XML context isolation, oldest-first history truncation, truncation flags | `core/prompt_budget.py` |
| Citation validation | Rank validity, lexical support, abstention, injection detection, auto-attribution | `core/citation_validator.py` |
| SQLite store | Canonical documents/pages/chunks/evidence/summaries, WAL, migrations v1–v4 | `core/doc_store.py` |
| Hybrid retrieval | Dense + FTS + RRF, LanceDB persistence, durable fallback mirror, whole-document read | `retrieval/hybrid_retriever.py` |
| In-memory vector index | Pure-Python cosine/euclidean nearest neighbor | `retrieval/vector_index.py` |
| CPU embeddings | Shared `all-MiniLM-L6-v2`, 384-dim, L2-normalized | `retrieval/local_embedding.py` |
| Provider contract | `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus` | `providers/model_provider.py` |
| Local provider | llama-server HTTP/SSE, loopback enforcement, VLM image payloads | `providers/llama_cpp_provider.py` |
| Cloud provider | LiteLLM routing with consent gate and key scrubbing | `providers/litellm_provider.py` |
| Direct Groq provider | Groq SDK adapter with consent gate | `providers/groq_provider.py` |
| Upload validation | Magic bytes, 50 MB / 500 page caps, SHA-256, `doc_<sha16>` | `ingestion/upload_validation.py` |
| Structured extraction | Docling layout/tables, markdown table splitting, pypdf fallback | `ingestion/docling_reader.py` |
| Text extraction fallback | pypdf page extraction and chunking | `ingestion/pdf_reader.py` |
| OCR fallback | Conditional RapidOCR on low-text pages with raster/time budgets | `ingestion/ocr_fallback.py` |
| Visual analysis | PyMuPDF region detection, 2x crops, VLM descriptions under the gate | `ingestion/visual_analyzer.py` |
| Model identity | GGUF metadata parsing and LM/projector pair verification | `core/model_identity.py` |
| Telemetry | Cached `nvidia-smi`, psutil RSS, stage latency tracking | `core/resource_telemetry.py` |
| Logging | Idempotent root logging + rotating file, watcher-noise filter | `core/logging_setup.py` |
| Launcher | Loopback bind guard, llama-server probe/spawn, Streamlit subprocess | `start.py` |
| Installer | Dependency install, checksum-pinned model/llama-server acquisition | `setup.py` |

## Pattern Overview

**Overall:** Modular monolith with a Streamlit composition root, layered orchestration/domain/pipeline packages, and a provider abstraction.

**Key Characteristics:**
- Single process, single user, loopback-bound UI (`start.py:59` `refuse_unsafe_bind`, `.streamlit/config.toml`).
- One GPU inference operation at a time enforced by a class-level reentrant lock (`core/local_llm.py:26`).
- Pydantic v2 models are the canonical boundary between pipeline, persistence, prompts, and UI (`core/models.py`).
- SQLite is the source of truth; LanceDB is a rebuildable projection of SQLite chunks (`ui/hydration.py`, `ui/lifecycle_service.py`).
- Retrieval degrades through explicit tiers: LanceDB dense+FTS → in-memory mirror → Python BM25 (`retrieval/hybrid_retriever.py`).
- Ingestion and retrieval are tolerant of extraction failures but never claim success for unpersisted vectors (`retrieval/hybrid_retriever.py:571` raises `VectorIndexError`).
- Privacy is enforced at boundaries: local-only provider URL validation, cloud consent assertions, sanitized markdown, no external assets.

## Layers

**Presentation:**
- Purpose: Render four workspaces and own all Streamlit interaction/session state.
- Location: `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`, `ui/session_state.py`
- Contains: page routing, chat feed, uploader, citation chips, consent dialog, telemetry cards, CSS/SVG.
- Depends on: UI orchestration services, `AiModel`, `DocStore`, `Summarizer`, telemetry.
- Used by: Streamlit runtime only.

**UI Orchestration Services:**
- Purpose: Encapsulate multi-tier side effects so views stay declarative.
- Location: `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`
- Contains: ingestion transaction, delete/purge/re-index ordering, startup repair.
- Depends on: `DocStore`, `HybridRetriever`, `LocalEmbedding`, ingestion pipeline.
- Used by: `main.py` and `ui/views.py`.

**Domain Services:**
- Purpose: Provider-independent intelligence behavior.
- Location: `core/local_llm.py`, `core/summarizer.py`, `core/query_intent.py`, `core/prompt_budget.py`, `core/citation_validator.py`
- Contains: retrieval resolution, prompt assembly, gate ownership, map-reduce summarization, citation checks.
- Depends on: `RetrievalResult` models, provider ABC, retriever protocol (`search_hybrid`, `fetch_document_chunks`).
- Used by: `ui/views.py`, `main.py`, `ui/summarizer` path.

**Ingestion Pipeline:**
- Purpose: Convert untrusted PDF bytes into canonical pages, chunks, and visual evidence.
- Location: `ingestion/`
- Contains: validation, Docling/pypdf readers, OCR, visual analyzer.
- Depends on: pypdf, Docling, RapidOCR, PyMuPDF, `core/models.py`.
- Used by: `ui/ingestion_service.py`.

**Retrieval & Persistence:**
- Purpose: Persist metadata and serve hybrid evidence.
- Location: `retrieval/`, `core/doc_store.py`, `core/models.py`
- Contains: embeddings, LanceDB table management, fallback mirror, BM25, RRF, SQLite schema/migrations.
- Depends on: LanceDB/PyArrow, sentence-transformers, sqlite3.
- Used by: ingestion, hydration, lifecycle, chat, summarizer.

**Inference Providers:**
- Purpose: Normalize local and cloud model access behind one contract.
- Location: `providers/`
- Contains: `BaseModelProvider` ABC, llama-server client, LiteLLM adapter, Groq adapter.
- Depends on: httpx, LiteLLM, Groq.
- Used by: `AiModel`, `Summarizer`, `VisualAnalyzer`.

## Data Flow

### Ingestion Path

1. Upload widget rotates its key and dispatches files (`ui/views.py:383`, `ui/views.py:391`).
2. `process_uploaded_files` enforces the 50 MB UI cap, selects a local vision provider, and calls `IngestionService.ingest_pdf` (`ui/views.py:309`, `ui/views.py:317`).
3. Validation checks `%PDF-`, size, page count, scanned-page ratio, and derives `doc_<sha16>` (`ingestion/upload_validation.py:120`).
4. Deduplication queries SQLite by SHA-256; an indexed document with missing vectors is repaired from stored chunks before extraction (`ui/ingestion_service.py:98`, `ui/ingestion_service.py:114`).
5. Docling extracts layout/reading order/tables; failures fall back to `PdfReader` (`ui/ingestion_service.py:147`, `ui/ingestion_service.py:157`).
6. Low-text pages go through conditional OCR with per-page raster budgets and per-document page/time budgets (`ui/ingestion_service.py:178`, `ingestion/ocr_fallback.py:368`).
7. PyMuPDF detects visual regions; up to six are cropped and described by the local VLM under `InferenceGate` (`ui/ingestion_service.py:202`, `ingestion/visual_analyzer.py:217`, `ingestion/visual_analyzer.py:290`).
8. `DocStore.record_ingestion` atomically replaces the document, pages, chunks, and evidence in one SQLite transaction (`core/doc_store.py:352`).
9. Chunks are embedded on CPU and written to LanceDB; the durable mirror is updated write-through (`ui/ingestion_service.py:285`, `retrieval/hybrid_retriever.py:452`, `retrieval/hybrid_retriever.py:584`).
10. Visual evidence is indexed as additional chunks with `extraction="vlm"`; failed/placeholder descriptions are skipped (`ui/ingestion_service.py:295`, `retrieval/hybrid_retriever.py:588`).

`IngestionService.cache_dir` is retained for constructor compatibility but ingestion writes no intermediate extraction artifacts to `.cache`. Legacy cache directories are still removed by lifecycle operations (`ui/lifecycle_service.py:68`, `ui/lifecycle_service.py:130`) and by the Settings action (`ui/views.py:1270`).

### Chat / Retrieval Path

1. `render_chat_view` appends the user turn and builds a contextualized search query (`ui/views.py:681`, `ui/views.py:686`).
2. Document scope is chosen from the focus filter, filename auto-detection, or a single-document library (`ui/views.py:689`, `ui/views.py:703`).
3. `resolve_retrieval` decides between whole-document extraction and normal hybrid retrieval (`core/query_intent.py:203`).
4. `AiModel.ask_a_question_from_pdf_stream` assembles a bounded prompt and acquires the gate (`core/local_llm.py:247`, `core/local_llm.py:329`).
5. Provider tokens stream to the UI placeholder (`ui/views.py:742`).
6. Missing citations are auto-attributed by lexical overlap, then validated (`ui/views.py:750`, `core/citation_validator.py:418`, `core/citation_validator.py:293`).
7. Injection or withheld-grounding outcomes change only the UI notice; the response is still stored with verification metadata (`ui/views.py:756`, `ui/views.py:826`).
8. Citation chips and the evidence drawer render from the same `RetrievalResult` snippets used for generation (`ui/views.py:791`, `core/models.py:185`).

### Whole-Document Extraction Path

1. `is_whole_document_query` matches explicit inventory/enumeration phrasing only (`core/query_intent.py:90`).
2. `resolve_retrieval` requires a single string `doc_id` and a retriever exposing `fetch_document_chunks` (`core/query_intent.py:222`).
3. `HybridRetriever.fetch_document_chunks` reads all scoped rows, deduplicates by `chunk_id`, sorts by `(page, chunk_id)`, and falls back to the durable mirror when LanceDB returns nothing (`retrieval/hybrid_retriever.py:641`).
4. `select_page_diverse_snippets` budgets one snippet per page first, then additional rounds, truncating oversized text and re-ranking from 1 (`core/query_intent.py:123`).
5. The selected result is returned with `search_mode="document"` so prompt ranks and citation validation stay consistent (`core/query_intent.py:230`, `core/models.py:181`).

### Summarization Path

1. `Summarizer.summarize_document` validates the profile and checks the SQLite cache keyed by `sha256`, `profile`, and `model_name:CONFIG_VERSION` (`core/summarizer.py:487`, `core/summarizer.py:497`).
2. Pages are reconstructed from chunks and enriched with visual/table evidence (`core/summarizer.py:503`, `core/summarizer.py:548`).
3. Documents under 2,000 estimated tokens use single-pass; larger documents use token-bundled map-reduce (`core/summarizer.py:558`).
4. The entire generation runs inside `InferenceGate.hold(timeout=120)` (`core/summarizer.py:559`).
5. Page references are extracted and clamped, then the result is cached in SQLite (`core/summarizer.py:567`, `core/summarizer.py:587`).

### Lifecycle Path

1. Views require a retriever before mutating storage (`ui/views.py:128`).
2. Delete removes vectors first, then SQLite, then legacy cache, then session keys (`ui/lifecycle_service.py:32`).
3. Purge drops the LanceDB table, VACUUMs SQLite, removes the cache directory, and clears session state; any tier failure raises `RuntimeError` (`ui/lifecycle_service.py:102`).
4. Re-index deletes stale vectors, re-embeds persisted chunks, re-indexes evidence, and verifies retrievability (`ui/lifecycle_service.py:160`).

### Startup / Hydration Path

1. `main.py` installs logging before any UI work (`main.py:49`).
2. `DocStore` is constructed once per process via `st.cache_resource` (`main.py:129`).
3. `hydrate_startup_state` loads documents, adds indexed/failed IDs to session state, and constructs the retriever (`ui/hydration.py:34`).
4. Only documents whose vectors are missing are re-embedded; progress is reported and per-document failures are isolated (`ui/hydration.py:98`, `ui/hydration.py:127`).
5. `_startup_hydrated` is set only after retriever discovery/repair completes so failures can retry (`ui/hydration.py:166`).

**State Management:**
- Streamlit `session_state` owns UI-only state: documents, chat, summaries, cloud credentials, health snapshot, hydration flag.
- SQLite owns durable document/page/chunk/evidence/summary records.
- LanceDB owns vectors and FTS rows; `data/lancedb/fallback_store.json` mirrors them for recovery.
- Process-level singletons: `InferenceGate` lock/counters, the shared SentenceTransformer cache (`retrieval/local_embedding.py:25`), telemetry caches, and the `DocStore` resource cache.

## Key Abstractions

**`InferenceGate` — 4 GB VRAM serialization contract:**
- Location: `core/local_llm.py:26`
- State: class-level `threading.RLock`, active-thread counter, state lock.
- API: `acquire(timeout=60.0) -> bool`, `release()`, `is_locked()`, `hold(timeout=60.0)` context manager that raises `TimeoutError`.
- Ownership rules: `release()` catches `RuntimeError` for a non-owning thread and logs instead of corrupting the counter (`core/local_llm.py:54`).
- Call sites: streaming answers (`core/local_llm.py:329` with `try/finally`), non-streaming generation (`core/local_llm.py:367`), summarization (`core/summarizer.py:559`, timeout 120 s), per-visual-element VLM analysis (`ingestion/visual_analyzer.py:290`, timeout 60 s).
- Contract: every LLM/VLM GPU call must hold the gate; CPU work (Docling, OCR, embeddings, SQLite, LanceDB) does not.

**`BaseModelProvider` — provider contract:**
- Location: `providers/model_provider.py:64`
- Methods: `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`, `close`.
- Implementations: `LlamaCppProvider` (`providers/llama_cpp_provider.py:56`), `LiteLLMProvider` (`providers/litellm_provider.py:104`), `GroqProvider` (`providers/groq_provider.py:18`).
- Capabilities carry `context_window`, `supports_vision`, `is_local`, `supports_streaming`; prompt budgeting keys off `context_window`.

**`RetrievalResult` / `EvidenceSnippet` — shared evidence contract:**
- Location: `core/models.py:142`, `core/models.py:171`
- Immutable, ranked from 1, includes page, chunk, extraction backend, optional bbox, dense/FTS ranks.
- `formatted_evidence()` renders `[E#] (file, p. N)` blocks for prompts; `source_labels()` feeds UI chips.

**`HybridRetriever` — tiered retrieval and durable mirror:**
- Location: `retrieval/hybrid_retriever.py:169`
- Canonical URI: `<repo>/data/lancedb`; legacy `<package>/data/lancedb` is copied non-destructively on first default-URI use (`retrieval/hybrid_retriever.py:70`, `retrieval/hybrid_retriever.py:84`).
- Mirror: `fallback_store.json` under the DB URI; lazy-loaded only when LanceDB is unavailable or a query falls through (`retrieval/hybrid_retriever.py:227`).
- Write-through merge: `_mirror_upsert` merges by `chunk_id`, updating disk only while LanceDB is healthy; when the mirror is loaded it updates memory then persists (`retrieval/hybrid_retriever.py:312`).
- Deletion: `_mirror_delete_document` removes all chunks for a doc so stale JSON cannot resurrect deleted documents (`retrieval/hybrid_retriever.py:349`).
- Scoped search: `_doc_filter_clause` escapes quotes and pushes `doc_id IN (...)` into LanceDB before limits; both dense and BM25 fallbacks score the full scoped set before truncating (`retrieval/hybrid_retriever.py:60`, `retrieval/hybrid_retriever.py:735`, `retrieval/hybrid_retriever.py:830`).
- Health: `fts_status()` returns `available`, `degraded`, `last_error`, and `mode` (`lancedb-fts` / `bm25-fallback` / `unknown`) at `retrieval/hybrid_retriever.py:799`. The current `render_settings_view` does not display it; it is exercised by `tests/test_hybrid_retriever.py:715` and intended for diagnostics.

**`query_intent` — retrieval intent and whole-document evidence:**
- Location: `core/query_intent.py`
- `contextualize_query` is the single follow-up rewriter used by both UI and `AiModel`.
- `whole_document_char_budget` derives a character budget from the provider context window.
- `resolve_retrieval` is the shared UI/`AiModel` entry point, preventing retrieval-policy drift.

**`DocStore` — durable source of truth:**
- Location: `core/doc_store.py:139`
- Per-operation connections, WAL, foreign keys, busy timeout, and bounded retry on SQLITE_BUSY/LOCKED (`core/doc_store.py:178`).
- Migrations v1–v4 applied by `PRAGMA user_version` (`core/doc_store.py:131`, `core/doc_store.py:219`).
- `record_ingestion` is the atomic write boundary for ingestion (`core/doc_store.py:352`).

**`SummaryResult` cache key:**
- Keyed by `sha256 + profile + model_version`, where `model_version = "<provider model_name>:<CONFIG_VERSION>"` (`core/summarizer.py:494`, `core/models.py:14`).

## Entry Points

**Streamlit application:**
- Location: `main.py`
- Triggers: `streamlit run main.py` or `start.py` subprocess.
- Responsibilities: page config, theme, session defaults, `DocStore`/`AiModel` construction, hydration, cloud-provider sync, health probing, sidebar, workspace routing.

**Unified launcher:**
- Location: `start.py` (`main`, `start.py:273`)
- Triggers: `python start.py --start-llama`, `rag-assistant`.
- Responsibilities: Python version check, loopback bind refusal, directory creation, llama-server probe/spawn with GGUF identity verification, Streamlit subprocess, child cleanup.

**Setup CLI:**
- Location: `setup.py` (`main_cli`, `download_models_cli`, `setup_llama_server_cli`)
- Triggers: `python setup.py`, `rag-setup`, `rag-download-models`, `rag-setup-llama`, setuptools commands `download_models` / `setup_llama_server`.
- Responsibilities: dependency installation, checksum-pinned model and llama-server acquisition, safe archive extraction, editable install.

**Streamlit-cached resource:**
- Location: `main.py:129` `get_doc_store`
- Triggers: first script run per process.
- Responsibilities: open/migrate SQLite once and surface startup failures with remediation.

## Architectural Constraints

- **VRAM serialization (`InferenceGate`):** All local LLM text generation, summarization, and VLM image analysis must run under the gate. The lock is process-wide, reentrant per thread, and times out rather than queuing indefinitely.
- **Threading:** Streamlit runs the script per session/thread; OCR uses a bounded `ThreadPoolExecutor` (`ingestion/ocr_fallback.py:452`); telemetry uses sampling/cache locks (`core/resource_telemetry.py:26`). SQLite uses per-operation connections to avoid Windows file-lock issues (`core/doc_store.py:157`).
- **Global state:** `InferenceGate` class variables (`core/local_llm.py:34`), shared SentenceTransformer `_MODEL_CACHE` (`retrieval/local_embedding.py:25`), `_LATENCY_HISTORY` (`core/resource_telemetry.py:21`), GPU/telemetry caches, and `st.cache_resource` `DocStore` (`main.py:129`).
- **Single-user/no auth:** The UI has no authentication. `start.py` refuses non-loopback binds unless explicitly opted in (`start.py:59`); Docker maps only `127.0.0.1:8501` (`docker-compose.yml`).
- **Local provider endpoint restriction:** `LlamaCppProvider` rejects non-loopback hosts unless `allow_remote=True` (`providers/llama_cpp_provider.py:98`).
- **Cloud egress gate:** `AiModel` refuses cloud mode without a provider whose `user_consented` is true (`core/local_llm.py:131`); providers re-assert consent per call (`providers/litellm_provider.py:142`, `providers/groq_provider.py:62`).
- **One-way persistence dependency:** SQLite is authoritative; LanceDB and the mirror are rebuildable from SQLite chunks (`ui/hydration.py:134`, `ui/lifecycle_service.py:169`).
- **No ingestion extraction cache:** `IngestionService` does not write `.cache` artifacts; `.cache` remains only a legacy-cleaned/UI-cleared directory.
- **Fallback mirror cost:** the mirror is one JSON file rewritten per ingestion transaction (O(N) I/O), a deliberate tradeoff for crash-safe recovery without duplicate in-RAM vectors.
- **Streamlit detection points:** `st.session_state`, `st.cache_resource`, `st.status`, `st.rerun` are UI-only concerns and must not leak into `core/`, `ingestion/`, `retrieval/`, or `providers/`.

## Anti-Patterns

### Direct unindexed PDF inference

**What happens:** Passing `pdf_path` to `AiModel.ask_a_question_from_pdf_stream` without an indexed retriever.
**Why it's wrong:** It bypasses SQLite/LanceDB provenance and citation ranks; the method raises `ValueError` and emits a `DeprecationWarning` (`core/local_llm.py:273`).
**Do this instead:** Index through `IngestionService` / `HybridRetriever.index_chunks`, then pass a `RetrievalResult` or an indexed retriever (`core/local_llm.py:270`).

### UI-driven database mutation

**What happens:** Deleting rows directly through `DocStore` from a view.
**Why it's wrong:** Vectors, sessions, and legacy cache would diverge; a deleted document can be resurrected by hydration.
**Do this instead:** Route all mutations through `LifecycleService` after `_lifecycle_preflight` (`ui/views.py:128`, `ui/lifecycle_service.py:32`).

### Reporting indexing success before verification

**What happens:** Treating a vector write as successful without checking retrievability.
**Why it's wrong:** SQLite would mark a document indexed while LanceDB holds no rows.
**Do this instead:** Verify `has_document()` after every ingestion/re-index and raise `VectorIndexError` on LanceDB write failure (`ui/ingestion_service.py:289`, `retrieval/hybrid_retriever.py:571`).

### Calling a provider outside the gate

**What happens:** Invoking `provider.generate_text`, `stream_text`, or `analyze_image` directly from a view or service.
**Why it's wrong:** Concurrent GPU work can exceed the 4 GB VRAM envelope.
**Do this instead:** Go through `AiModel` (which owns the gate) or wrap explicitly in `InferenceGate.hold(...)` as `Summarizer` and `VisualAnalyzer` do (`core/summarizer.py:559`, `ingestion/visual_analyzer.py:290`).

### Version-agnostic summary reuse

**What happens:** Looking up summaries without the active model version.
**Why it's wrong:** A summary produced by a different provider/config would render as current.
**Do this instead:** Key session and SQLite lookups by `model_name:CONFIG_VERSION` (`ui/views.py:51`, `core/summarizer.py:494`).

## Error Handling

**Strategy:** Fail at the narrowest boundary, preserve the source of truth, and surface actionable UI errors instead of blank pages.

**Patterns:**
- Startup failures render remediation and `st.stop()` (`main.py:139`, `main.py:197`).
- Extraction falls back Docling → pypdf; a document with zero chunks is recorded as `failed` (`ui/ingestion_service.py:154`, `ui/ingestion_service.py:213`).
- OCR and visual-analysis failures are page/element-local and never abort text ingestion (`ui/ingestion_service.py:186`, `ingestion/visual_analyzer.py:295`).
- SQLite writes retry only transient busy/locked errors (`core/doc_store.py:194`).
- Vector deletion failures abort lifecycle operations before SQLite mutation (`ui/lifecycle_service.py:49`).
- Purge collects per-tier failures and raises a combined `RuntimeError` while still cleansing session state (`ui/lifecycle_service.py:110`).
- Provider health probes are caught and converted to `HealthStatus`/`ProviderCapabilities` fallbacks (`main.py:261`).
- Streaming generation releases the gate in `finally`, including abandoned generators (`core/local_llm.py:341`).
- Cloud errors scrub API keys before logging or re-raising (`providers/litellm_provider.py:135`).

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` per module; `configure_logging` installs one idempotent root configuration with rotating `data/logs/app.log` (`core/logging_setup.py:57`). `RAG_LOG_LEVEL` controls level. CLI launchers use `print()` for operator output.

**Validation:** Pydantic v2 `extra="forbid"` models at all boundaries (`core/models.py`); `%PDF-` magic bytes and size/page caps before extraction (`ingestion/upload_validation.py:120`); GGUF metadata verification before launching llama-server (`core/model_identity.py:124`, `start.py:184`).

**Authentication:** None. The application is single-user and loopback-bound; cloud credentials live in session state/environment and are scrubbed on clear (`ui/views.py:244`).

**Privacy / egress control:** Local-only provider endpoint validation (`providers/llama_cpp_provider.py:98`), consent assertions (`providers/litellm_provider.py:142`), markdown/HTML sanitization (`ui/sanitizer.py:130`), and no external assets (`assets/icons/*.svg`).

**Observability:** GPU VRAM via cached `nvidia-smi`, process RSS via psutil, latency history and snapshots (`core/resource_telemetry.py:33`, `core/resource_telemetry.py:287`).

**Resource bounds:** 50 MB / 500 pages per upload (`ingestion/upload_validation.py:18`), OCR per-document page/time budgets (`ingestion/ocr_fallback.py:32`), raster pixel/byte budgets (`ingestion/ocr_fallback.py:24`, `ingestion/visual_analyzer.py:20`), max six visual regions during ingestion (`ui/ingestion_service.py:206`).

---

*Architecture analysis: 2026-10-22*
