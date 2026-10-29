<!-- refreshed: 2026-10-29 -->
# Architecture

**Analysis Date:** 2026-10-29

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Presentation — Streamlit script, chatbot-first AMOLED UI                     │
│  `main.py` (composition root + router)                                       │
│  `ui/views.py` · `ui/components.py` · `ui/theme.py` · `ui/sanitizer.py`       │
│  `ui/session_state.py` · `.streamlit/config.toml` · `assets/icons/*.svg`      │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌──────────────────────────────────────┐   ┌──────────────────────────────────┐
│ UI Orchestration Services            │   │ Domain Services                  │
│ `ui/chat_controller.py` (ChatTurn)   │   │ `core/local_llm.py` (AiModel,     │
│ `ui/ingestion_service.py`            │   │  InferenceGate)                  │
│ `ui/lifecycle_service.py`            │   │ `core/summarizer.py`             │
│ `ui/hydration.py`                    │   │ `core/citation_validator.py`     │
│ `ui/session_state.py`                │   │ `core/query_intent.py`           │
│                                      │   │ `core/prompt_budget.py`          │
└───────────────┬──────────────────────┘   └───────────────┬──────────────────┘
                │                                          │
                ▼                                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Ingestion & Retrieval Pipeline                                               │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`             │
│   → `ingestion/pdf_reader.py` (fallback) → `ingestion/ocr_fallback.py`        │
│   → `ingestion/visual_analyzer.py` (VLM crops)                               │
│ `retrieval/local_embedding.py` (MiniLM, CPU) → `retrieval/hybrid_retriever.py`│
│   (LanceDB dense + FTS, RRF) → `retrieval/vector_index.py` (fallback)        │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌──────────────────────────────────────┐   ┌──────────────────────────────────┐
│ Persistence                          │   │ Inference Providers              │
│ `core/doc_store.py` → `data/documents.db` (SQLite WAL, v1–v5)                │
│ `retrieval/hybrid_retriever.py` → `data/lancedb/` + JSON mirror              │
│ `core/models.py` → `.cache/<sha256>/<CONFIG_VERSION>/`                       │
│                                      │   │ `providers/model_provider.py` (ABC)│
│                                      │   │ `providers/llama_cpp_provider.py` │
│                                      │   │ `providers/litellm_provider.py`   │
│                                      │   │ `providers/groq_provider.py`      │
└──────────────────────────────────────┘   └──────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Composition root / router | Page config, session defaults, hydration, provider sync, health probe cache, workspace dispatch | `main.py:103`, `main.py:117`, `main.py:199`, `main.py:502` |
| Chat workspace | Scope selector, conversation feed, streaming, citation pills, sources drawer | `ui/views.py:496` |
| Summarizer workspace | Document picker, 5 profiles, length toggle, SQLite/session cache, markdown export | `ui/views.py:877` |
| Document Library | Upload, inspect, re-index, per-document delete, purge-all | `ui/views.py:1030` |
| Settings | Cloud consent toggle, provider/key entry, VRAM/RAM telemetry, storage paths | `ui/views.py:1203` |
| Diagnostics | Redacted provider health, runtime/model paths, log tail | `ui/views.py:1391` |
| Chat turn service | Scope resolution, retrieval, auto-attribution, bounded regeneration, grounding report | `ui/chat_controller.py:131` |
| Ingestion service | Validate → dedupe/repair → extract → OCR → VLM → SQLite → vectors | `ui/ingestion_service.py:39` |
| Lifecycle service | Atomic delete/purge/re-index across SQLite, LanceDB, cache, session | `ui/lifecycle_service.py:17` |
| Hydration | Restore catalog, consume deletion tombstones, repair missing vectors | `ui/hydration.py:83` |
| Session reset | Single teardown path for chat, evidence, credentials, provider handles | `ui/session_state.py:18` |
| Inference facade | Provider routing, prompt budgeting, streaming, gate acquisition, citation validation | `core/local_llm.py:112` |
| VRAM gate | Process-wide reentrant lock serializing all LLM/VLM/summary inference | `core/local_llm.py:35` |
| Summarizer | Single-pass vs map-reduce over page batches, version-keyed cache | `core/summarizer.py:476` |
| Citation validator | Rank validity, lexical claim support, abstention, injection detection | `core/citation_validator.py:411` |
| Prompt budget | Token estimation, `<document_context>` isolation, oldest-first history trimming | `core/prompt_budget.py:85` |
| Query intent | Follow-up contextualization, summary/exhaustive/location intent, page-diverse selection | `core/query_intent.py:325` |
| SQLite store | Documents, pages, chunks, evidence, summaries, tombstones; migrations v1–v5 | `core/doc_store.py:150` |
| Hybrid retriever | Dense + BM25 candidate pools fused by RRF; whole-document reads | `retrieval/hybrid_retriever.py:169` |
| Embeddings | CPU-pinned `all-MiniLM-L6-v2`, 384-d, L2-normalized, process cache | `retrieval/local_embedding.py:58` |
| Providers | ABC + local llama-server client, LiteLLM cloud adapter, Groq direct client | `providers/model_provider.py:64`, `providers/llama_cpp_provider.py:68` |
| Telemetry / runtime info | VRAM/RSS sampling with 5s cache, llama.cpp version probe, GGUF metadata | `core/resource_telemetry.py:33`, `core/runtime_info.py:94` |

## Pattern Overview

**Overall:** Modular monolith with a server-rendered Streamlit script acting as composition root, layered UI-orchestration services, pure domain services, and pluggable inference providers behind an ABC.

**Key Characteristics:**
- One deployable process (Streamlit) plus one external local process (`llama-server`). No HTTP API layer of its own; the browser talks to Streamlit over its websocket.
- `main.py` is executed top-to-bottom on every interaction. All initialization (logging, DB, hydration, provider, health) is therefore idempotent or cached.
- Domain logic is Streamlit-free by construction in `core/`, `ingestion/`, `retrieval/`; UI-facing services split into "pure" (`ui/chat_controller.py` imports no Streamlit) and "session-coupled" (`ui/views.py`, `ui/hydration.py`, `ui/lifecycle_service.py`).
- Pydantic v2 models (`extra="forbid"`, mostly `frozen=True`) are the only data contract crossing layers: `Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `GroundingReport`, `SummaryResult`, `ProviderCapabilities`, `HealthStatus`.
- Every inference call is funneled through `InferenceGate` so only one model operation occupies VRAM at a time.
- Local-only by default: loopback enforcement in the provider, loopback bind enforcement in the launcher, and browser-egress neutralization in the sanitizer.

## Layers

**Presentation (`main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`):**
- Purpose: Render workspaces, own widget state, translate user actions into service calls.
- Location: `main.py`, `ui/`
- Contains: Streamlit page config, sidebar navigation, five render functions, SVG/CSS helpers, markdown sanitization.
- Depends on: UI orchestration services, domain services, `core/doc_store.py`, `core/resource_telemetry.py`.
- Used by: the Streamlit runtime only.

**UI Orchestration (`ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `ui/session_state.py`):**
- Purpose: Multi-step workflows that span several domain objects and storage tiers.
- Location: `ui/`
- Contains: `ChatTurnService.prepare/finalize`, `IngestionService.ingest_pdf`, `LifecycleService.delete/purge/reindex`, `hydrate_startup_state`, `reset_in_memory_session`.
- Depends on: `core/`, `ingestion/`, `retrieval/`.
- Used by: `main.py` and `ui/views.py`.

**Domain (`core/`):**
- Purpose: Prompt assembly, inference routing, citation verification, summarization, intent classification, persistence, telemetry.
- Location: `core/`
- Contains: `AiModel`/`InferenceGate`, `Summarizer`, `validate_citations`, `resolve_retrieval`, `assemble_grounded_messages`, `DocStore`.
- Depends on: `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`, `providers/`, `core/models.py`.
- Used by: UI orchestration services and views.

**Ingestion (`ingestion/`):**
- Purpose: Turn untrusted PDF bytes into canonical `Page`/`Chunk`/`EvidenceElement` records.
- Location: `ingestion/`
- Contains: `validate_pdf_bytes`, `DoclingReader`, `PdfReader`, `apply_conditional_ocr`, `VisualAnalyzer`.
- Depends on: `core/models.py`, `providers/model_provider.py` (VLM only), PyMuPDF/RapidOCR/Docling.
- Used by: `ui/ingestion_service.py`.

**Retrieval (`retrieval/`):**
- Purpose: Dense embeddings, persistent hybrid index, whole-document reads, in-memory fallback.
- Location: `retrieval/`
- Contains: `LocalEmbedding`, `HybridRetriever`, `VectorIndex`, `compute_rrf`.
- Depends on: `core/models.py`, LanceDB/PyArrow/sentence-transformers.
- Used by: `core/local_llm.py`, `ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`.

**Persistence (`core/doc_store.py`, `retrieval/hybrid_retriever.py`, `core/models.py`):**
- Purpose: Durable source of truth (SQLite) and derived search index (LanceDB) plus on-disk extraction cache.
- Location: `data/documents.db`, `data/lancedb/`, `.cache/<sha256>/<CONFIG_VERSION>/`
- Contains: Relational rows, vectors + FTS, cached JSON artifacts.
- Depends on: stdlib `sqlite3`, LanceDB.
- Used by: every layer above.

**Inference Providers (`providers/`):**
- Purpose: Uniform text/stream/vision/health/capability interface over local and cloud backends.
- Location: `providers/`
- Contains: `BaseModelProvider`, `LlamaCppProvider` (loopback HTTP/SSE), `LiteLLMProvider` (consent-gated), `GroqProvider`.
- Depends on: `httpx`, `litellm`, `groq`, and (leak) Streamlit secrets.
- Used by: `core/local_llm.py`, `core/summarizer.py`, `ingestion/visual_analyzer.py`.

## Data Flow

### Primary Request Path — Chat QA

1. User submits `st.chat_input`; duplicate-submit guard and queued-prompt pop (`ui/views.py:693-708`).
2. Scope resolution: focus dropdown → `selected_filter`, document-switch boundary resets turn state (`ui/views.py:525-543`).
3. `ChatTurnService.prepare` builds request id, contextualizes the query, detects summary intent, resolves `doc_filter`/`retrieval_scope` (`ui/chat_controller.py:138-256`, `core/query_intent.py:77`, `core/query_intent.py:206`).
4. Retrieval: `resolve_retrieval` → `HybridRetriever.search_hybrid` (dense top-`k*4..5` + FTS top-`k*4..5`, doc filter pushed into backend, RRF at `k_rrf=60`) (`core/query_intent.py:325`, `retrieval/hybrid_retriever.py:959-1072`).
5. Prompt assembly: `AiModel.ask_a_question_from_pdf_stream` formats `[E#]` blocks via `RetrievalResult.formatted_evidence()`, then `assemble_grounded_messages` reserves 1536 output tokens, sanitizes XML boundaries, truncates context/history (`core/models.py:196`, `core/prompt_budget.py:85-176`).
6. Generation: `InferenceGate.acquire(timeout=60)` → `provider.stream_text` → tokens yielded to the UI placeholder; gate released in `finally` (`core/local_llm.py:356-372`).
7. Finalization: lexical auto-attribution, `validate_citations`, optional single bounded regeneration, location-mismatch abstention, `GroundingReport` construction (`ui/chat_controller.py:258-416`, `core/citation_validator.py:411`, `core/citation_validator.py:579`).
8. Render: only snippets whose `rank` is cited and not unsupported become pills/sources; footer label comes from `verification_caption` (`ui/views.py:622-681`, `ui/views.py:84`).
9. Turn appended to `st.session_state.chat_history` and bounded to 50 turns (`ui/views.py:299-305`), then `st.rerun()`.

### Chat Document-Wide Summary Path

1. `is_summary_request` detects summary intent; `mode="summary"` (`ui/chat_controller.py:157`).
2. `_retrieve_document_wide` reads all chunks in page order (`retrieval/hybrid_retriever.py:641`), prefers text chunks over VLM descriptions per page, then fits evidence with `select_page_diverse_snippets` (`ui/chat_controller.py:647-713`, `core/query_intent.py:245`).
3. `AiModel` uses `SUMMARY_SYSTEM_TEMPLATE` and drops chat history entirely (`core/local_llm.py:340-341`, `core/prompt_budget.py:40`).
4. Empty evidence yields deterministic `INSUFFICIENT_EVIDENCE_MESSAGE` without calling the model (`core/local_llm.py:333-335`).

### Summarizer Workspace Path (map-reduce)

1. User picks document, profile, length (`ui/views.py:897-933`).
2. Cache lookup by `f"{model_name}:{CONFIG_VERSION}:{length}"` (`core/summarizer.py:504-511`).
3. Pages reconstructed from stored chunks, enriched with VLM/table evidence (`core/summarizer.py:513-559`).
4. `InferenceGate.hold(timeout=120)`; ≤ 2000 estimated tokens → single pass, else map-reduce in ≤ 2000-token page bundles (`core/summarizer.py:566-575`, `core/summarizer.py:30-31`).
5. Page references extracted and clamped, `SummaryResult` persisted to SQLite, session cache written (`core/summarizer.py:577-600`, `ui/views.py:963-968`).

### Ingestion Path (PDF upload)

1. `process_uploaded_files` size pre-check, builds `IngestionService` from session retriever/embedder (`ui/views.py:313-348`).
2. `validate_pdf_bytes`: `%PDF-` magic, ≤ 50 MB, ≤ 500 pages, pypdf readability, scanned-ratio preflight, SHA-256 → `doc_<sha16>` (`ingestion/upload_validation.py:120-176`).
3. Dedupe by SHA; if the document exists but vectors are missing, re-embed from SQLite chunks before re-extracting (`ui/ingestion_service.py:98-139`).
4. Extraction: `DoclingReader` (CPU, `do_ocr=False`, table structure on) with `PdfReader` fallback (`ingestion/docling_reader.py:37`, `ui/ingestion_service.py:147-173`).
5. Conditional OCR on pages with < 50 chars, bounded to 200 pages / 300 s, thread pool over pages (`ingestion/ocr_fallback.py:368-452`).
6. Visual analysis: detect regions with PyMuPDF, crop at 2× within pixel/byte budgets, call VLM under `InferenceGate` (max 6 regions) (`ingestion/visual_analyzer.py:41-60`, `ingestion/visual_analyzer.py:288-291`).
7. Atomic SQLite write of document + pages + chunks + evidence (`core/doc_store.py:363`).
8. Embeddings on CPU → `HybridRetriever.index_chunks` (drops stale vectors first) → `index_evidence_elements` → `has_document` verification (`ui/ingestion_service.py:272-299`).
9. Failure marks the document `status="failed"` so hydration offers repair instead of claiming success (`ui/ingestion_service.py:300-327`).

### Lifecycle Path (delete / purge / re-index)

1. `_lifecycle_preflight` refuses to mutate SQLite when no retriever is available (`ui/views.py:154-168`).
2. `LifecycleService.delete_document`: vectors first (abort on failure), then SQLite (+ tombstone when no retriever), then cache dir, then session state (`ui/lifecycle_service.py:32-102`).
3. `purge_all`: vectors → SQLite delete + `VACUUM` → cache dir → session state; collects failures and raises `RuntimeError` (`ui/lifecycle_service.py:104-160`, `core/doc_store.py:893`).
4. `reindex_document`: read chunks from SQLite, delete vectors, re-embed, re-index evidence, verify (`ui/lifecycle_service.py:162-206`).
5. Startup consumes tombstones and repairs missing vectors (`ui/hydration.py:34-81`, `ui/hydration.py:83-221`).

**State Management:**
- Process-wide: `DocStore` via `@st.cache_resource` (`main.py:148`), SentenceTransformer cache (`retrieval/local_embedding.py:30`), `InferenceGate` class lock (`core/local_llm.py:43`), icon cache (`ui/components.py:14`).
- Per-session: `AiModel` (`main.py:206`), `HybridRetriever`, `LocalEmbedding`, `document_metadata`, `chat_history`, `chat_sessions`, cloud consent/keys, health snapshot, uploader keys (`main.py:117-140`).
- Persistent: SQLite `data/documents.db`, LanceDB `data/lancedb/`, extraction cache `.cache/`, logs `data/logs/app.log`.

## Key Abstractions

**`BaseModelProvider` (ABC):**
- Purpose: Uniform contract for text, streaming, vision, health, capabilities.
- Examples: `providers/model_provider.py:64`, `providers/llama_cpp_provider.py:68`, `providers/litellm_provider.py:105`, `providers/groq_provider.py:19`.
- Pattern: Adapter + Strategy. `AiModel` selects the strategy; consent is enforced inside cloud adapters (`providers/litellm_provider.py:141`, `providers/groq_provider.py:65`).

**`InferenceGate`:**
- Purpose: Guarantee at most one GPU-resident inference operation per process (4 GB VRAM envelope).
- Examples: `core/local_llm.py:35-109`; used by streaming (`core/local_llm.py:356`), non-streaming (`core/local_llm.py:394`), summarizer (`core/summarizer.py:569`), VLM crops (`ingestion/visual_analyzer.py:288`).
- Pattern: Class-level `threading.RLock` + active-thread counter; `hold()` context manager raising `TimeoutError`.

**`RetrievalResult` / `EvidenceSnippet` / `GroundingReport`:**
- Purpose: One immutable evidence contract shared by prompt assembly, citation validation, and UI rendering.
- Examples: `core/models.py:142`, `core/models.py:171`, `core/models.py:219`.
- Pattern: Frozen Pydantic value objects; ranks assigned once at retrieval and reused verbatim as `[E#]` tags.

**`ChatTurnPreparation` / `ChatTurnResult`:**
- Purpose: Split a chat turn into a pre-generation decision object and a post-generation render object.
- Examples: `ui/chat_controller.py:58`, `ui/chat_controller.py:80`.
- Pattern: Two-phase service returning typed dataclasses; the view never re-derives evidence.

**`DocStore`:**
- Purpose: Transactional catalog and child-row store.
- Examples: `core/doc_store.py:150`, atomic `record_ingestion` (`core/doc_store.py:363`), versioned `MIGRATIONS` (`core/doc_store.py:141`).
- Pattern: Repository with per-operation connections, WAL, bounded busy retry (`core/doc_store.py:189-228`).

**`HybridRetriever`:**
- Purpose: Persistent dual-modality search with graceful degradation.
- Examples: `retrieval/hybrid_retriever.py:169`, `search_hybrid` (`:959`), `fetch_document_chunks` (`:641`), `compute_rrf` (`:121`).
- Pattern: Backend abstraction with LanceDB primary + JSON-mirrored `VectorIndex` fallback (`retrieval/hybrid_retriever.py:206`, `:277`).

## Entry Points

**Launcher `python start.py`:**
- Location: `start.py:292` (`main`)
- Triggers: operator shell, `rag-assistant` console script (`setup.py:827-833`).
- Responsibilities: banner, Python version check, refuse non-loopback bind unless opted in (`start.py:58`), create directories, optionally spawn `llama-server` with `-ngl 28 -c 4096`, probe health, then `streamlit run main.py` and terminate the child on exit (`start.py:292-352`).

**Streamlit script `main.py`:**
- Location: `main.py` (module body, 1-542)
- Triggers: every browser interaction (Streamlit rerun), `streamlit run main.py`, Docker `CMD` (`Dockerfile`).
- Responsibilities: env hardening, logging install, page config, theme injection, session defaults, DB init, hydration, `AiModel` init, cloud provider sync, TTL-cached health probe, sidebar, workspace dispatch, notification flush.

**Setup CLI `python setup.py`:**
- Location: `setup.py:774` (`main_cli`), plus `download_models_cli` (`:779`), `setup_llama_server_cli` (`:795`), setuptools commands (`:722`, `:748`).
- Triggers: operator setup, `rag-setup`, `rag-download-models`, `rag-setup-llama`.
- Responsibilities: dependency install, directory creation, GGUF/embedding/OCR downloads with checksums, llama.cpp binary install.

**Workspace router:**
- Location: `main.py:502-540`; workspace constants `main.py:59-65`.
- Triggers: sidebar radio, sidebar buttons, library "Chat" action (`ui/views.py:1104-1107`).
- Responsibilities: `normalize_workspace` aliasing, off-nav workspaces (Settings/Diagnostics) preserved through `_nav_value`, dispatch to the five render functions.

## Architectural Constraints

- **Threading:** Streamlit executes the script on a single session thread. Parallelism exists only in OCR page batches via `ThreadPoolExecutor` (`ingestion/ocr_fallback.py:452`). `InferenceGate` is a class-level `threading.RLock`, so it serializes across session threads but is reentrant within a thread and cannot coordinate separate processes.
- **Global state:** `InferenceGate._lock/_active_threads` (`core/local_llm.py:43-45`), `_MODEL_CACHE` (`retrieval/local_embedding.py:30`), `_ICON_CACHE` (`ui/components.py:14`), `@st.cache_resource get_doc_store` (`main.py:148`), `_HEALTH_TTL_SECONDS` snapshot in session state (`main.py:271`).
- **One model in memory:** only `LlamaCppProvider` (HTTP client to a separate server process) is used locally; embeddings and OCR are CPU-only by configuration (`retrieval/local_embedding.py:58-75`, `ingestion/docling_reader.py` pipeline options, `ingestion/ocr_fallback.py`).
- **CPU-offloaded preprocessing:** embeddings pinned to `device="cpu"`, Docling `do_ocr=False` with CPU pipeline, RapidOCR ONNX on CPU. VRAM is reserved for the VLM/LLM server.
- **Local-only default:** `LlamaCppProvider` rejects non-loopback hosts unless `allow_remote=True` (`providers/llama_cpp_provider.py:97-110`); `.streamlit/config.toml` binds `127.0.0.1`; `start.py` refuses non-loopback binds (`start.py:58-90`); browser egress neutralized by `ui/sanitizer.py:130`.
- **Cloud is explicit:** `AiModel` raises `PermissionError` when cloud mode lacks a provider with `user_consented=True` (`core/local_llm.py:142-146`, `:197-201`); LiteLLM/Groq adapters re-assert consent per call.
- **Untrusted document text:** all evidence is wrapped in `<document_context>` with tag-spoofing escaped (`core/prompt_budget.py:54-68`, `:148`), system prompts forbid obeying embedded instructions (`core/prompt_budget.py:27`, `:47`), and outputs are scanned for injection (`core/citation_validator.py:237`).
- **Frozen contracts:** `Chunk`, `EvidenceSnippet`, `RetrievalResult`, `GroundingReport`, `ProviderCapabilities`, `HealthStatus` are frozen; `extra="forbid"` prevents silent schema drift (`core/models.py`).
- **SQLite connection model:** one connection per operation, WAL, `busy_timeout=5000`, 3-attempt retry with jitter; `VACUUM` runs outside the delete transaction (`core/doc_store.py:169-228`, `:893-909`).
- **No auth:** single-user app; loopback binding is the security boundary (documented in `.streamlit/config.toml`).

## Anti-Patterns

### God module in the presentation layer

**What happens:** `ui/views.py` is 1548 lines / 24 functions and owns all five workspaces, session mutation (124 `st.session_state` references), 27 `st.rerun()` calls, cloud settings, lifecycle error boundaries, and citation rendering.
**Why it's wrong:** Any workspace change risks unrelated views; the module cannot be unit-tested without Streamlit's script runtime, and orchestration logic (e.g. `process_uploaded_files`) is entangled with widget code.
**Do this instead:** Follow the `ui/chat_controller.py` precedent — extract Streamlit-free orchestration into `ui/*_service.py` returning dataclasses, and split workspaces into `ui/views_<area>.py` modules that `main.py` imports.

### Two independent retrieval paths

**What happens:** `ChatTurnService.prepare` already resolves a `RetrievalResult` and passes it to `AiModel`, but `AiModel.ask_a_question_from_pdf_stream` will retrieve again when `retrieval_result is None`, using a three-way duck-typed branch (`HybridRetriever` → `resolve_retrieval`; object with `get_context`; object with `search_hybrid`) at `core/local_llm.py:286-326`.
**Why it's wrong:** Scope rules, budgets, and ranking can differ between the two paths, so evidence shown in the UI may not be the evidence sent to the model.
**Do this instead:** Always pass `retrieval_result=prepared.retrieval_result` (as `ui/views.py:765-773` does) and keep `AiModel` retrieval-free; if the fallback must stay, route it through `core/query_intent.resolve_retrieval` only.

### Provider layer depends on Streamlit

**What happens:** `providers/litellm_provider.py:58` and `:75` and `providers/groq_provider.py:43` import `streamlit` inside functions to read `st.session_state.cloud_api_keys` and `st.secrets`.
**Why it's wrong:** The provider layer is otherwise framework-independent; this creates a hidden presentation dependency, makes key resolution order implicit, and requires broad `except Exception` blocks around imports.
**Do this instead:** Resolve credentials in the composition root (`main.py:230-249` already builds `LiteLLMProvider` with an explicit `api_key`) and pass them into providers as constructor arguments; keep env/secrets lookup in a small `core/credentials.py` adapter.

### Duck-typed session state in services

**What happens:** `LifecycleService.delete_document(session_state: Any = None)` and `purge_all(session_state: Any = None)` mutate arbitrary attributes with `hasattr` guards (`ui/lifecycle_service.py:32-102`, `:141-156`).
**Why it's wrong:** There is no contract for what session state must contain; a rename in `main.py:117-140` silently degrades cleanup, which is exactly the leak class these services exist to prevent.
**Do this instead:** Define a small `SessionCatalog` protocol/dataclass (doc_ids, failed_doc_ids, indexed_files, document_metadata, summary keys) and have `main.py` adapt `st.session_state` to it.

### Dead and duplicated UI code

**What happens:** `render_cloud_api_tab` (`ui/views.py:1444-1548`) duplicates the cloud section of `render_settings_view` (`:1257-1327`); `render_sidebar_documents` (`:421`) has no production caller; `truncation_notice` (`:136`) is covered by tests (`tests/test_ui_smoke.py:274`) but never rendered, so `truncation_warning` is stored on every assistant turn and never shown.
**Why it's wrong:** Two copies of consent/key logic can drift; dead renderers look authoritative to future contributors; computed truncation flags create a false impression that the user is warned.
**Do this instead:** Delete the unused renderers and either render `truncation_notice` in the chat footer or stop persisting the flag.

### Version-conditional Streamlit shims

**What happens:** `hasattr(st, "dialog")` (`main.py:344`), `hasattr(st, "html")` (`main.py:568`, `ui/views.py:568`, `:653`, `:830`, `:1088`, `:1252`, `:1265`, `:1484`).
**Why it's wrong:** Every new component must remember the shim, and the fallback path (`st.markdown(..., unsafe_allow_html=True)`) has different sanitization semantics.
**Do this instead:** Pin a minimum Streamlit version in `requirements.txt` and use `st.html`/`st.dialog` directly; centralize any fallback in `ui/components.py`.

### Control flow encoded in session-state flags

**What happens:** `_nav_value`, `_scope_switch_index`, `_last_submit`, `_queued_prompt`, `_active_chat_scope`, `_show_consent_dialog`, `uploader_key_<suffix>`, `pending_delete_doc_id` form an implicit state machine across `main.py` and `ui/views.py`, with `st.rerun()` as the transition operator.
**Why it's wrong:** Reruns re-execute the whole script, so a missed flag reset produces duplicate ingestion or a bounced workspace; the semantics are undocumented and only discoverable by reading both files.
**Do this instead:** Consolidate the chat/ingestion workflow flags into a single documented dataclass in `ui/session_state.py` with explicit `reset_*` helpers, mirroring `reset_in_memory_session`.

### Dual vector storage

**What happens:** `HybridRetriever` writes every chunk to LanceDB and also to `data/lancedb/fallback_store.json` through `_write_mirror`/`_mirror_upsert` (`retrieval/hybrid_retriever.py:206`, `:277`, `:312`).
**Why it's wrong:** Two copies of all embeddings must stay consistent; a partial write or manual LanceDB deletion leaves the fallback resurrecting "deleted" data (the reason tombstones exist in `core/doc_store.py:132-139`).
**Do this instead:** Treat SQLite chunks as the rebuild source (as `ui/hydration.py:178-206` already does) and make the mirror an explicit, rebuildable cache with a generation marker rather than a parallel write path.

## Error Handling

**Strategy:** Fail at boundaries, never blank the page; log with redaction; prefer deterministic abstention over ungrounded output.

**Patterns:**
- Startup boundary: DB/model init failures render an actionable error with redacted technical detail and `st.stop()` (`main.py:85-91`, `:158-170`, `:216-226`).
- Provider probe boundary: health failure becomes an offline `HealthStatus` instead of an exception (`main.py:280-299`).
- Service boundaries: `IngestionService` returns `IngestionResult(success=False, error=...)` for validation, extraction, DB, and indexing failures (`ui/ingestion_service.py:80-91`, `:164-173`, `:260-270`, `:300-327`).
- Lifecycle boundary: vector deletion failure aborts before SQLite mutation; purge aggregates failures and raises (`ui/lifecycle_service.py:46-67`, `:158-159`).
- Generation boundary: `ChatTurnService.error_result` produces a redacted, persistable assistant turn (`ui/chat_controller.py:434-493`).
- Grounding boundary: unsupported answers are withheld and replaced with the canonical abstention string (`ui/chat_controller.py:358-373`, `core/citation_validator.py:282`).
- Redaction: `redact_text` is applied to every error surfaced to the UI or log tail (`core/redaction.py:32`, `ui/views.py:1436`).

## Cross-Cutting Concerns

**Logging:** Single `configure_logging(log_dir=...)` call installs stderr + rotating file handler at `data/logs/app.log`, level from `RAG_LOG_LEVEL` (`main.py:51`, `core/logging_setup.py`). Every module uses `logger = logging.getLogger(__name__)` (25 modules).

**Validation:** Pydantic v2 for all cross-layer data (`core/models.py`); `validate_pdf_bytes` for untrusted uploads (`ingestion/upload_validation.py:120`); `sanitize_xml_boundary` for prompt injection (`core/prompt_budget.py:54`); `sanitize_markdown_for_local` for browser egress (`ui/sanitizer.py:130`); GGUF metadata verification in `core/model_identity.py:95`.

**Authentication:** None. The app is single-user and loopback-bound; cloud credentials live in `st.session_state.cloud_api_keys` or env/secrets and are scrubbed by `clear_cloud_credentials` (`ui/views.py:270`) and `reset_in_memory_session` (`ui/session_state.py:50-64`).

**Telemetry:** `get_gpu_memory_info` / `get_process_memory_info` with 5s cache (`core/resource_telemetry.py:33`, `:169`), `LatencyTracker`/`track_stage` (`core/resource_telemetry.py:194`, `:251`), runtime version probe (`core/runtime_info.py:94`), and benchmark scripts writing to `.planning/research/` (`scripts/profile_resources.py`, `scripts/benchmark_multimodal.py`).

---

*Architecture analysis: 2026-10-29*
