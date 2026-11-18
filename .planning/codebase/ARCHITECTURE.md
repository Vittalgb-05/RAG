---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
<!-- refreshed: 2026-11-14 -->
# Architecture

**Analysis Date:** 2026-11-14

## System Overview

The running system is a **local-first, single-process FastAPI backend plus a statically exported Next.js frontend**. A process-wide singleton container (`api/container.py`) owns every stateful dependency; all HTTP routes, background jobs, and SSE streams read from that container.

```text
┌───────────────────────────────────────────────────────────────────────────────┐
│ Presentation — Next.js 15 static export (`frontend/`)                          │
│ `src/app/(shell)/{chat,library,summarizer,constellation,settings,diagnostics}`  │
│ `src/components/{shell,chat,motion}` · `src/lib/{api,store}` · zustand · RQ    │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ fetch + SSE, `X-RAG-Client: web`
                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│ API layer — FastAPI (`api/`)                                                   │
│ `main.py` (create_app/lifespan) · `routers/*` · `schemas/*` · `deps.py`         │
│ `errors.py` (RFC 9457) · `streaming.py` (thread→SSE) · `jobs.py` · `cloud_state`│
└───────────────────────────────┬───────────────────────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│ AppContainer singleton (`api/container.py`)                                    │
│ DocStore · LocalEmbedding · HybridRetriever · AiModel · ChatTurnService         │
│ IngestionService · LifecycleService · JobManager · CloudState · chat_lock       │
└───────┬───────────────────────────────┬───────────────────────────┬───────────┘
        ▼                               ▼                           ▼
┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────┐
│ Orchestration services│   │ Domain / retrieval        │   │ Ingestion         │
│ `services/chat_turn.py`│  │ `core/*` (llm, summarizer,│   │ `ingestion/*`     │
│ `services/ingestion.py`│  │ citations, prompt budget, │   │ docling → pypdf → │
│ `services/lifecycle.py`│  │ query intent, sanitizer)  │   │ OCR → VLM crops   │
│ `services/hydration.py`│  │ `retrieval/*` (hybrid)    │   │                   │
└───────┬───────────────┘   └─────────────┬─────────────┘   └─────────┬─────────┘
        ▼                                 ▼                           ▼
┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────┐
│ Persistence           │   │ Inference providers       │   │ Native runtime    │
│ SQLite `data/documents.db` │ `providers/model_provider`│   │ llama-server      │
│ LanceDB `data/lancedb/`│  │ llama.cpp · LiteLLM · Groq│   │ 127.0.0.1:8080    │
│ cache `data/.cache/`  │   │ (cloud = consent-gated)   │   │ (or cloud HTTPS)  │
└───────────────────────┘   └───────────────────────────┘   └───────────────────┘
```

**Important drift note:** `README.md`, `CLAUDE.md` (generated GSD block), `docs/ENDPOINT_INTEGRATION_MATRIX.md`, and `docs/RUNBOOK.md` still describe a **Streamlit** UI (`main.py`, `ui/`, port 8501). Those files no longer exist. The authoritative runtime is `api/`, `services/`, `core/`, `retrieval/`, `ingestion/`, `providers/`, and `frontend/`. Treat documentation claims about `ui/` or Streamlit as stale.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| App factory / lifespan | Builds `AppContainer` on startup, starts hydration thread, mounts routers under `/api/v1`, optionally serves `frontend/out` at `/` | `api/main.py` |
| Singleton container | Constructs and owns DocStore, embeddings, retriever, AiModel, CloudState, JobManager, services; exposes `chat_lock`, `ready`, `hydration` | `api/container.py` |
| Dependency helpers | `get_container(request)` from `app.state`; `require_client_header` enforces `X-RAG-Client: web` on mutations | `api/deps.py` |
| Settings | Pydantic-settings, env prefix `RAG_`, loopback defaults, `serve_frontend`, `store_originals` | `api/config.py` |
| Problem-details errors | RFC 9457 `application/problem+json`; maps `PermissionError`→403, `TimeoutError`→503 `gpu_busy`, `VectorIndexError`→503, `ValueError`→422; redacts detail | `api/errors.py` |
| SSE bridge | Runs a worker on one dedicated thread and forwards `emit(event, data)` to an `asyncio.Queue`; keepalives; disconnect → `stop` event | `api/streaming.py` |
| Job manager | Single-worker `ThreadPoolExecutor`, job records, append-only event list, cooperative cancel, SSE polling | `api/jobs.py` |
| Cloud state | In-memory API keys (`SecretStr`), consent enforcement, build-first provider swap, egress ledger | `api/cloud_state.py` |
| Chat turn service | Scope resolution, retrieval choice (QA vs whole-document summary), auto-attribution, citation verification, bounded regeneration, abstention | `services/chat_turn.py` |
| Ingestion service | Validation → dedupe/repair → Docling/pypdf extraction → OCR → VLM evidence → SQLite → embeddings → LanceDB, with progress stages | `services/ingestion.py` |
| Lifecycle service | Deletion across vectors→SQLite→cache, purge, reindex from stored chunks | `services/lifecycle.py` |
| Hydration | Startup restore/repair of vectors, consumption of deletion tombstones | `services/hydration.py` |
| AI model facade | Provider selection/swapping, prompt assembly, `InferenceGate` acquisition, streaming, citation validation | `core/local_llm.py` |
| Summarizer | Five profiles, single-pass vs map-reduce, SQLite cache keyed by model+prompt+length | `core/summarizer.py` |
| Citation validator | `[E#]` precision, lexical claim support, injection detection, abstention rules | `core/citation_validator.py` |
| Prompt budgeting | Token accounting, `<document_context>` isolation, oldest-first history trimming | `core/prompt_budget.py` |
| Query intent | Contextualize query, summary/exhaustive detection, page-diverse selection, `resolve_retrieval` | `core/query_intent.py` |
| SQLite store | Documents/pages/chunks/evidence/summaries/chat sessions, WAL, bounded retry, migrations v1–v4 | `core/doc_store.py` |
| Hybrid retriever | LanceDB dense + BM25 FTS fused by RRF, document fetch, evidence indexing, embedding export, in-memory fallback | `retrieval/hybrid_retriever.py` |
| Embeddings | CPU-pinned `all-MiniLM-L6-v2`, 384-d, process-level model cache | `retrieval/local_embedding.py` |
| Pure-Python index | Cosine/euclidean in-memory fallback, no external deps | `retrieval/vector_index.py` |
| Providers | `BaseModelProvider` ABC + llama.cpp, LiteLLM, Groq adapters | `providers/model_provider.py`, `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py` |
| Ingestion primitives | Upload validation/hashing, Docling reader, pypdf reader, conditional OCR, visual analyzer | `ingestion/upload_validation.py`, `ingestion/docling_reader.py`, `ingestion/pdf_reader.py`, `ingestion/ocr_fallback.py`, `ingestion/visual_analyzer.py` |

## Pattern Overview

**Overall:** Modular monolith with an explicit composition root, layered dependency direction, and process-wide singleton state.

**Key Characteristics:**
- One Python process serves API, background jobs, and static UI; there is no worker fleet, no message broker, and no multi-process cache.
- All mutable singletons are constructed once in `AppContainer.build()` (`api/container.py:45`) and injected through FastAPI `Depends(get_container)`.
- Generation is thread-affine: `InferenceGate` is a process-level `RLock` (`core/local_llm.py:35`), so SSE workers run on a single dedicated thread (`api/streaming.py:47`) rather than on the event loop.
- Contracts are Pydantic models at every boundary: `core/models.py` for domain data, `api/schemas/*` for HTTP payloads.
- Providers are a strategy family behind `BaseModelProvider` (`providers/model_provider.py:64`), swapped at runtime by `AiModel.swap_provider` (`core/local_llm.py:218`).

## Layers

**Presentation (frontend):**
- Purpose: Render chat, library, summarizer, constellation, settings, diagnostics.
- Location: `frontend/src/`
- Contains: App Router pages under `src/app/(shell)/`, presentational components, TanStack Query hooks, SSE client, zustand UI store.
- Depends on: HTTP API only (`src/lib/api/client.ts`, `src/lib/api/sse.ts`), base URL from `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`).
- Used by: browser; also served by FastAPI when `RAG_SERVE_FRONTEND` is true and `frontend/out` exists (`api/main.py:81`).

**API layer:**
- Purpose: HTTP surface, request validation, error shaping, SSE transport, job orchestration.
- Location: `api/`
- Contains: `main.py`, `routers/`, `schemas/`, `deps.py`, `errors.py`, `streaming.py`, `jobs.py`, `cloud_state.py`, `container.py`, `config.py`, `export_openapi.py`.
- Depends on: `services/`, `core/`, `retrieval/`, `ingestion/`, `providers/`.
- Used by: frontend, CLI (`rag-api` console script), Docker healthcheck.

**Service layer:**
- Purpose: Multi-step workflows that coordinate storage, retrieval, and inference.
- Location: `services/`
- Contains: `chat_turn.py`, `ingestion.py`, `lifecycle.py`, `hydration.py`.
- Depends on: `core/`, `retrieval/`, `ingestion/`, providers.
- Used by: `api/container.py` and routers.

**Domain layer:**
- Purpose: Business rules independent of transport.
- Location: `core/`
- Contains: canonical models, SQLite store, LLM facade/gate, summarizer, citation validator, prompt budget, query intent, sanitizer, redaction, telemetry, runtime/model identity, logging.
- Depends on: `retrieval/` (only `core/local_llm.py` imports `HybridRetriever`/`LocalEmbedding`), `providers/`.
- Used by: services and API.

**Ingestion & retrieval:**
- Purpose: PDF-to-index and query-to-evidence mechanics.
- Location: `ingestion/`, `retrieval/`
- Contains: validators/readers/OCR/VLM cropping; embeddings, hybrid retriever, pure-Python index.
- Depends on: `core/models.py`, optional native libraries (Docling, PyMuPDF, RapidOCR, LanceDB, sentence-transformers).
- Used by: `services/ingestion.py`, `services/lifecycle.py`, `services/hydration.py`, `core/local_llm.py`, API routers (`search`, `visualize`).

**Inference providers:**
- Purpose: Text/vision generation and health probing behind one ABC.
- Location: `providers/`
- Contains: ABC + capability/health schemas, llama.cpp HTTP/SSE client with loopback guard, LiteLLM adapter, Groq adapter.
- Depends on: `httpx`, optional `litellm`/`groq` SDKs.
- Used by: `core/local_llm.py`, `api/cloud_state.py`, `services/ingestion.py` (VLM), `core/summarizer.py`.

**Persistence:**
- Purpose: Durable metadata, vectors, summaries, chat history, caches.
- Location: `core/doc_store.py`, `retrieval/hybrid_retriever.py`, `data/`
- Contains: SQLite (`data/documents.db`), LanceDB (`data/lancedb/`), extraction cache (`data/.cache/<sha256>/<CONFIG_VERSION>/`), optional originals (`data/originals/<sha256>.pdf`).
- Depends on: filesystem only.
- Used by: services, hydration, diagnostics.

## Data Flow

### Primary Request Path — grounded chat answer

1. Frontend posts to `/api/v1/chat/sessions/{id}/messages/stream` with `X-RAG-Client: web` (`frontend/src/lib/api/sse.ts:15`, `frontend/src/app/(shell)/chat/page.tsx`).
2. Router takes non-blocking `chat_lock`; returns `409 generation_in_progress` if another answer is running (`api/routers/chat.py:247`).
3. Loads recent turns via `DocStore.recent_chat_turns` and the provider context window via `AiModel.get_capabilities()` (`api/routers/chat.py:255`).
4. A worker thread is started by `sse_from_worker` and emits `status`/`meta` events (`api/streaming.py:26`, `api/routers/chat.py:262`).
5. `ChatTurnService.prepare` resolves document scope (explicit scope → filename mention → single-document default), classifies summary vs QA, retrieves evidence, and produces `ChatTurnPreparation` (`services/chat_turn.py:138`).
6. Summary mode reads the whole selected document via `HybridRetriever.fetch_document_chunks`, keeps text-first evidence, selects page-diverse snippets inside `whole_document_char_budget` (`services/chat_turn.py:647`, `core/query_intent.py:237`).
7. QA mode calls `resolve_retrieval` → `HybridRetriever.search_hybrid` (dense + FTS + RRF), returning a `RetrievalResult` with ranked `[E#]` snippets (`core/query_intent.py:335`, `retrieval/hybrid_retriever.py:959`).
8. `AiModel.ask_a_question_from_pdf_stream` formats evidence (`RetrievalResult.formatted_evidence`), assembles system+history+bounded prompt with XML isolation, acquires `InferenceGate`, and streams provider tokens (`core/local_llm.py:276`, `core/prompt_budget.py`).
9. Tokens are emitted as `token` events; on completion `ChatTurnService.finalize` auto-attributes strong lexical matches, validates citations, optionally regenerates once, may withhold/abstain, and builds a `GroundingReport` (`services/chat_turn.py:258`).
10. Router sanitizes markdown when local mode is active (`core/sanitizer.py`), persists user+assistant messages via `DocStore.append_chat_message`, and emits `final` with answer, grounding, sources, usage (`api/routers/chat.py:67`).

### Ingestion Path

1. `POST /api/v1/documents` reads uploads and validates synchronously (`validate_pdf_bytes`: `%PDF` magic bytes, 50 MB, 500 pages, SHA-256, `doc_<sha16>` id) (`api/routers/documents.py:52`, `ingestion/upload_validation.py:118`).
2. Duplicate check by SHA; if SQLite says indexed but vectors are missing, ingestion attempts repair from stored chunks (`services/ingestion.py:101`).
3. Otherwise a single-worker job is submitted (`api/jobs.py:86`).
4. `IngestionService.ingest_pdf` reports staged progress (`validate` 5% → `dedupe` 10% → `extract` 40% → `ocr` 55% → `visual` 70% → `persist` 80% → `embed` 92% → `index` 100%) (`services/ingestion.py:55`).
5. Extraction: Docling structured read, automatic pypdf fallback (`ingestion/docling_reader.py`, `ingestion/pdf_reader.py`); conditional RapidOCR on low-text pages (`ingestion/ocr_fallback.py:368`); PyMuPDF crop + VLM description into `EvidenceElement` (`ingestion/visual_analyzer.py`).
6. Document recorded with status `indexing`, then chunks/pages/evidence written to SQLite (`core/doc_store.py:440`).
7. Embeddings generated (`retrieval/local_embedding.py`), vectors written and verified (`has_document`), evidence elements indexed, status flipped to `indexed`; failures mark `failed` (`services/ingestion.py:279`).
8. Frontend follows `GET /api/v1/jobs/{job_id}/events` (SSE, 250 ms polling of in-memory events) (`api/jobs.py:151`).

### Summary Path

1. `POST /api/v1/summaries` validates document, checks SQLite cache by `model:PROMPT_VERSION:length` (`api/routers/summaries.py:74`, `core/summarizer.py:30`).
2. Submits `summarize` job; `Summarizer.summarize_document` chooses single-pass for small inputs or token-budgeted map-reduce (`core/summarizer.py:514`).
3. Every model call is serialized through `InferenceGate`; result is cached in `document_summaries` and returned via `GET /summaries/{doc_id}/{profile}`.

### Retrieval X-Ray / Constellation

- `POST /api/v1/search` calls `search_hybrid(..., explain=True)` and maps rank/score breakdown to `ExplanationItem` (`api/routers/search.py:14`).
- `GET /api/v1/visualize/embeddings` exports chunk vectors and projects them to 3D with NumPy SVD PCA, cached in `_PROJECTION_CACHE` (`api/routers/visualize.py:22`).
- `POST /api/v1/visualize/query-trace` embeds the query, projects with the cached basis, and returns top retrieved chunk IDs (`api/routers/visualize.py:86`).

### Startup / Hydration

1. Uvicorn imports `api.main:app`; `lifespan` builds settings, logging, `AppContainer`, directories (`api/main.py:44`).
2. `AppContainer.start_background_hydration` spawns daemon thread; `hydrate_startup_state` repairs missing vectors and consumes deletion tombstones, then sets `ready` (`api/container.py:85`, `services/hydration.py:44`).
3. `/api/v1/health` reports `loading` until `ready` is set (`api/routers/system.py:32`).

### Cloud Mode Toggle

1. `PUT /api/v1/settings/cloud` → `CloudState.apply` enforces consent, stores key in memory only, builds a `LiteLLMProvider` **before** swapping (`api/cloud_state.py:57`).
2. `AiModel.swap_provider` assigns the new provider, closes the old one, updates the model name (`core/local_llm.py:218`).
3. `DELETE /api/v1/settings/cloud/credentials` revokes keys and reverts to local (`api/routers/settings.py:69`).
4. Each transmission can be recorded in the in-memory egress ledger (`api/cloud_state.py:26`, exposed at `/privacy/ledger`).

**State Management:**
- Server: `AppContainer` singletons + SQLite/LanceDB/disk. Chat concurrency guarded by `chat_lock`; generation by `InferenceGate`; job execution by a 1-worker pool.
- Client: TanStack Query cache for server data; zustand `useAppStore` for UI state (sidebar, palette, selected source, consent modal, active doc) (`frontend/src/lib/store/use-app-store.ts`).

## Key Abstractions

**`RetrievalResult` / `EvidenceSnippet`:**
- Purpose: One immutable evidence set shared by prompt assembly and UI citations, so an answer cannot be paired with a different retrieval.
- Examples: `core/models.py:143`, `core/models.py:174`
- Pattern: Frozen Pydantic v2 models; `formatted_evidence()` renders `[E#]` blocks, `source_labels()` renders chips.

**`GroundingReport`:**
- Purpose: Single request-scoped contract carrying request id, scope, document ids, evidence count, citation ranks, verification status/reason, truncation and injection flags.
- Examples: `core/models.py:226`, built in `services/chat_turn.py:107`, serialized into assistant messages.
- Pattern: Frozen model; computed once in `finalize`, rendered by frontend badge/heatmap.

**`BaseModelProvider`:**
- Purpose: Provider-agnostic text generation, token streaming, image analysis, health, capabilities.
- Examples: `providers/model_provider.py:64`, `providers/llama_cpp_provider.py:68`, `providers/litellm_provider.py`, `providers/groq_provider.py`
- Pattern: ABC + frozen `ProviderCapabilities`/`HealthStatus` schemas.

**`InferenceGate`:**
- Purpose: Process-level reentrant lock guaranteeing at most one GPU inference operation at a time (4 GB VRAM ceiling).
- Examples: `core/local_llm.py:35`; held in `ask_a_question_from_pdf_stream`, `generate_text`, and summarizer calls.
- Pattern: Class-level `RLock` + active-thread counter; `hold(timeout)` context manager.

**`AppContainer`:**
- Purpose: Composition root and dependency carrier.
- Examples: `api/container.py:27`
- Pattern: Dataclass with `build()` classmethod and `shutdown()` ordering (jobs → ai_model → retriever → doc_store).

**`HybridRetriever`:**
- Purpose: Persistent dense+lexical retrieval with RRF and graceful degradation.
- Examples: `retrieval/hybrid_retriever.py:169`; key methods `index_chunks` (452), `fetch_document_chunks` (641), `search_hybrid` (959), `export_embeddings` (1107).
- Pattern: Optional LanceDB; falls back to `VectorIndex` mirror + SQLite-backed BM25 fallback; raises `VectorIndexError` rather than silently losing vectors.

**`DocStore`:**
- Purpose: SQLite source of truth for catalog, chunks, pages, evidence, summaries, chat sessions/messages, deletion tombstones.
- Examples: `core/doc_store.py:214`
- Pattern: Per-operation connections, WAL, bounded retry on `SQLITE_BUSY`/`LOCKED`, DDL migrations applied on connect.

**`JobManager` / `JobHandle`:**
- Purpose: Serialize ingestion/reindex/summarize work and expose progress/cancel.
- Examples: `api/jobs.py:78`, handle at `api/jobs.py:64`
- Pattern: One worker thread; workers call `handle.progress(stage, pct, message)`; consumers stream `GET /jobs/{id}/events`.

## Entry Points

**`api.main:app` / `create_app()`:**
- Location: `api/main.py:55`
- Triggers: `uvicorn api.main:app`, Docker `CMD`, `rag-api` console script (`api/main.py:90`), tests.
- Responsibilities: settings, logging, middleware (`TrustedHostMiddleware`, `CORSMiddleware`), error handlers, router mounting, optional static frontend mount.

**`start.py`:**
- Location: `start.py`
- Triggers: `python start.py [--port 8000] [--host 127.0.0.1]`
- Responsibilities: module preflight, loopback enforcement (`RAG_ALLOW_NON_LOOPBACK` opt-in), optional llama-server launch, uvicorn launch via `launch_server` (`start.py:354`); reports whether `frontend/out` exists (`start.py:368`).

**`setup.py`:**
- Location: `setup.py`
- Triggers: `python setup.py [setup|download_models|install_llama]`, `pip install -e .`.
- Responsibilities: dependency provisioning (venv fallback for PEP 668), model/binary download with checksums, packaging; console scripts at `setup.py:1257` (`rag-api=api.main:run`).

**`api.export_openapi`:**
- Location: `api/export_openapi.py`
- Triggers: `python -m api.export_openapi [--check]`
- Responsibilities: write/verify `openapi.json`; CI fails on drift (`.github/workflows/ci.yml:39`).

**Frontend routes:**
- Location: `frontend/src/app/(shell)/*/page.tsx`
- Triggers: static export navigation; `/` redirects to `/chat` (`frontend/src/app/page.tsx`).
- Responsibilities: Chat, Library, Summarizer, Constellation, Settings, Diagnostics.

## Architectural Constraints

- **Process model:** Single uvicorn process; no multiprocessing, no external queue. All state that must survive restart lives in SQLite/LanceDB/disk. In-memory job list and cloud ledger are lost on restart.
- **Threading:** `InferenceGate` is thread-affine (an `RLock` cannot be released by a foreign thread; `release()` warns instead — `core/local_llm.py:64`). Consequently chat streaming runs the worker on one dedicated thread (`api/streaming.py:47`) and `JobManager` uses exactly one worker thread (`api/jobs.py:82`).
- **Global state:** module-level singletons/caches exist in `retrieval/local_embedding.py:32` (`_MODEL_CACHE`), `core/local_llm.py:43` (`InferenceGate`), `api/routers/chat.py:31` (`_ACTIVE_STOPS`), `api/routers/visualize.py:19` (`_PROJECTION_CACHE`), `core/resource_telemetry.py:21` (latency/GPU caches).
- **Dependency direction:** `api → services → core/retrieval/ingestion/providers`. `core` does not import `api` or `services` (verified). One upward edge exists: `core/local_llm.py` imports `retrieval.hybrid_retriever` and `retrieval.local_embedding` (lines 16–18).
- **Network boundary:** server binds `127.0.0.1` by default; CORS limited to localhost:3000; `TrustedHostMiddleware` guards DNS rebinding; `LlamaCppProvider` enforces loopback/SSRF checks; cloud egress requires explicit consent + `user_consented=True`.
- **Client mutation guard:** every `POST/PUT/PATCH/DELETE` under `/api/v1` requires `X-RAG-Client: web` (`api/deps.py:15`), and the frontend sets it in both `client.ts` and `sse.ts`.
- **Streaming contract:** SSE events used by chat are `status`, `meta`, `token`, `replace`, `final`, `error`; job events are `started`, `progress`, `done`, `error`, `cancelled`; telemetry emits `telemetry`.
- **Static UI coupling:** FastAPI serves `frontend/out` only when `RAG_SERVE_FRONTEND=true`; otherwise frontend must run separately (Next dev on :3000) against `NEXT_PUBLIC_API_URL`.
- **Build-time coupling:** `openapi.json` is a committed artifact checked in CI; adding/removing routes without re-exporting breaks the backend job.

## Anti-Patterns

### Untyped cross-boundary calls that drift from the service contract

**What happens:** Routers call service methods by attribute name without a shared Protocol or interface check. Observed mismatches: `api/routers/chat.py:288` calls `c.chat.abstention_turn(prepared)`, while `services/chat_turn.py:545` defines `abstention_result`; `api/routers/summaries.py:111` constructs `Summarizer(doc_store=..., ai_model=...)`, while `core/summarizer.py:188` accepts `(provider, doc_store)`; `api/routers/system.py:39` calls `c.ai_model.get_provider_status()`, which `core/local_llm.py` does not define.
**Why it's wrong:** Python resolves these only at runtime, so contract drift surfaces as `AttributeError`/`TypeError` inside SSE workers, where it is converted into a generic 500 problem instead of a compile-time failure.
**Do this instead:** When adding a router call, read the target service signature first (`services/chat_turn.py`, `core/summarizer.py`, `core/local_llm.py`). Prefer adding a narrow `Protocol` next to the service (as `CitationValidator` is defined at `services/chat_turn.py:48`) and type the container fields against it.

### Dual retrieval paths with duplicated semantics

**What happens:** `ChatTurnService._retrieve` supports both a rich `HybridRetriever.search_hybrid` path and a legacy `retriever.search(query, k)` path (`services/chat_turn.py:616`), and `HybridRetriever` itself maintains a LanceDB path plus a `VectorIndex` mirror/BM25 fallback (`retrieval/hybrid_retriever.py:227`, `859`).
**Why it's wrong:** Ranking, source labeling, and truncation flags differ between paths, so behavior depends on which object was injected.
**Do this instead:** Route new retrieval consumers through `resolve_retrieval(...)` and `HybridRetriever.search_hybrid`; treat the fallback branches as degradation-only code and keep their return shape (`RetrievalResult`) identical.

### Stale documentation treated as architecture

**What happens:** `README.md`, `CLAUDE.md`, `docs/ENDPOINT_INTEGRATION_MATRIX.md`, and `docs/RUNBOOK.md` describe Streamlit, `main.py`, `ui/`, and "no FastAPI routes".
**Why it's wrong:** Following them leads to editing non-existent files or reintroducing the removed presentation layer.
**Do this instead:** Use `api/main.py`, `api/routers/*`, `services/*`, and `frontend/src/app/(shell)/*` as the source of truth; update docs in the same change when behavior moves.

### Long synchronous work inside request handlers

**What happens:** Document listing probes vector presence per document (`api/routers/documents.py:30`), telemetry spawns `nvidia-smi`, and search/constellation run embeddings and SVD inline.
**Why it's wrong:** These are synchronous CPU/IO operations in `async def` handlers; they block the event loop for all concurrent SSE streams.
**Do this instead:** Keep heavy ingestion/summarization in `JobManager`; for new expensive endpoints, use `run_in_threadpool` or submit a job and stream progress.

## Error Handling

**Strategy:** Domain code raises typed exceptions; the API layer converts everything to RFC 9457 problem documents and redacts secrets at the boundary.

**Patterns:**
- `ApiError(status, code, detail)` for explicit HTTP semantics (`api/errors.py:14`).
- `problem_from_exc` mapping: `PermissionError`→403 `consent_required`, `TimeoutError`→503 `gpu_busy`, `VectorIndexError`→503 `index_unavailable`, `ValueError`→422 with `not_a_pdf`/`upload_too_large`/`too_many_pages`, `RuntimeError`→502 `provider_unreachable`, fallback 500 (`api/errors.py:65`).
- Global handlers installed in `install_error_handlers`; validation errors flattened into one detail string (`api/errors.py:135`).
- SSE failures are emitted as a terminal `error` event via `on_error=problem_from_exc` rather than tearing down the stream (`api/routers/chat.py:353`).
- Credential redaction applied to problem details, logs endpoint output, and failed-generation messages (`core/redaction.py`, `api/routers/system.py:191`, `services/chat_turn.py:444`).
- Ingestion isolates failures per stage and always records a terminal status (`indexing`→`indexed` or `failed`) (`services/ingestion.py:259`).

## Cross-Cutting Concerns

**Logging:** `configure_logging` sets a stream + `data/logs/rag.log` file handler with `%(asctime)s %(levelname)s [%(name)s] %(message)s` (`api/main.py:30`). Modules use `logging.getLogger(__name__)`. `core/logging_setup.py` suppresses benign third-party watcher warnings. Diagnostics exposes redacted tail logs.

**Validation:** Pydantic v2 models everywhere — HTTP bodies (`api/schemas/*`, `extra="forbid"` in several), domain records (`core/models.py`), provider capabilities. Upload validation is separate and pre-model (`ingestion/upload_validation.py`). Prompt-time defenses: XML boundary sanitization and explicit "treat context as untrusted" instructions (`core/prompt_budget.py`).

**Authentication / authorization:** No user accounts. Security is a local-trust model: loopback binding, trusted hosts, CORS allowlist, and the `X-RAG-Client` mutation header. Cloud authorization is explicit consent + in-memory key (`api/cloud_state.py`).

**Privacy / egress:** Local mode sanitizes rendered markdown (`core/sanitizer.py` applied at `api/routers/chat.py:78`), blocks non-loopback llama endpoints, keeps keys only in memory, and records egress in an in-memory ledger.

**Performance / resource control:** `InferenceGate` serializes GPU work; `DEFAULT_MAX_OUTPUT_TOKENS=1536` and token budgets keep prompts inside 4K context (`core/prompt_budget.py:17`); embeddings are CPU-pinned; OCR and VLM crops have pixel/byte guards (`ingestion/visual_analyzer.py:23`); telemetry caches `nvidia-smi` for 5 s.

---

*Architecture analysis: 2026-11-14*
