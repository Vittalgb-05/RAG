<!-- refreshed: 2026-10-26 -->
# Architecture

**Analysis Date:** 2026-10-26

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Presentation — single-page Streamlit script (server-rendered, AMOLED)        │
│ `main.py` · `ui/views.py` · `ui/components.py` · `ui/theme.py`               │
│ `ui/sanitizer.py` · `ui/session_state.py` · `assets/icons/*.svg`             │
└──────────────┬────────────────────────────────────────────┬──────────────────┘
               │ st.session_state, render_*()                │ upload / delete
               ▼                                             ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│ Domain services (`core/`)            │  │ UI orchestration (`ui/`)          │
│ `core/local_llm.py` (AiModel,        │  │ `ui/ingestion_service.py`         │
│  InferenceGate)                      │  │ `ui/lifecycle_service.py`         │
│ `core/summarizer.py`                 │  │ `ui/hydration.py`                 │
│ `core/query_intent.py`               │  │                                   │
│ `core/citation_validator.py`         │  │                                   │
│ `core/prompt_budget.py`              │  │                                   │
└──────────────┬───────────────────────┘  └───────────────┬───────────────────┘
               │ RetrievalResult                             │ Chunk/Page/Evidence
               ▼                                             ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────────┐
│ Retrieval (`retrieval/`)             │  │ Ingestion (`ingestion/`)          │
│ `hybrid_retriever.py` (LanceDB+BM25) │  │ `upload_validation.py`            │
│ `local_embedding.py` (MiniLM, CPU)   │  │ `docling_reader.py` → `pdf_reader.py`│
│ `vector_index.py` (fallback)         │  │ `ocr_fallback.py` · `visual_analyzer.py`│
└──────────────┬───────────────────────┘  └───────────────┬───────────────────┘
               │                                             │
               ▼                                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Persistence & inference adapters                                             │
│ `core/doc_store.py` (SQLite WAL) · `data/lancedb/` · `.cache/`               │
│ `providers/model_provider.py` (ABC) → `llama_cpp_provider.py` /              │
│ `litellm_provider.py` / `groq_provider.py`                                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Composition root | Page config, session defaults, DocStore cache, hydration, provider health, cloud consent, sidebar and view routing | `main.py` |
| Chat view | Prompt capture, query contextualization, retrieval, streamed generation, citation verification, evidence drawer | `ui/views.py` (`render_chat_view`, line 490) |
| Summarizer view | Profile selection, session/SQLite cache lookup, markdown export | `ui/views.py` (`render_summarizer_view`, line 923) |
| Library view | Catalog listing, per-document re-index/delete, purge-all danger zone | `ui/views.py` (`render_library_view`, line 1046) |
| Settings view | Cloud consent, API-key entry, VRAM/RAM telemetry, session/cache reset | `ui/views.py` (`render_settings_view`, line 1167) |
| Ingestion orchestration | Validate → dedupe/repair → Docling → pypdf fallback → conditional OCR → VLM → SQLite transaction → LanceDB index | `ui/ingestion_service.py` (`ingest_pdf`, line 54) |
| Lifecycle orchestration | Vector-first delete, purge across SQLite/LanceDB/cache/session, verified re-index | `ui/lifecycle_service.py` (lines 32, 102, 160) |
| Startup hydration | Rebuild session catalog from SQLite, detect missing vectors, re-embed only missing documents | `ui/hydration.py` (`hydrate_startup_state`, line 34) |
| Inference facade | Provider routing, retrieval-context assembly, token streaming, citation validation | `core/local_llm.py` (`AiModel`, line 103) |
| GPU concurrency gate | Process-wide reentrant lock serializing LLM/VLM/summarizer inference | `core/local_llm.py` (`InferenceGate`, line 26) |
| Summarization | Five profiles, single-pass vs bounded map-reduce, SQLite cache keyed by model + config version | `core/summarizer.py` (`Summarizer`, line 172) |
| Query intent | Follow-up rewriting, whole-document detection, page-diverse evidence budgeting | `core/query_intent.py` (lines 77, 110, 147, 227) |
| Citation validation | `[E#]` extraction, precision gate, abstention detection, injection detection | `core/citation_validator.py` (line 302) |
| Prompt budgeting | Token estimation, `<document_context>` isolation, oldest-first history truncation | `core/prompt_budget.py` (lines 75, 165) |
| Canonical models | Pydantic v2 schemas shared across layers, `CONFIG_VERSION`, cache path helper | `core/models.py` |
| SQLite store | Schema migrations v1–v4, atomic ingestion transaction, summaries, delete/purge | `core/doc_store.py` (`DocStore`, line 139) |
| Hybrid retrieval | LanceDB dense search + native FTS/BM25, RRF fusion, whole-document fetch, fallback mirror | `retrieval/hybrid_retriever.py` (`search_hybrid`, line 959) |
| Embeddings | CPU-pinned `all-MiniLM-L6-v2`, process-level model cache, 384-d normalized vectors | `retrieval/local_embedding.py` (line 51) |
| In-memory fallback index | Pure-stdlib cosine/euclidean search used when LanceDB is unavailable | `retrieval/vector_index.py` (line 15) |
| Upload validation | `%PDF-` magic bytes, 50 MB / 500 page caps, SHA-256, stable `doc_<sha16>` | `ingestion/upload_validation.py` (line 120) |
| Layout extraction | Docling CPU layout/table extraction with automatic pypdf fallback | `ingestion/docling_reader.py` (line 143) |
| pypdf extraction | Memory-safe text extraction and per-page fault isolation | `ingestion/pdf_reader.py` (line 49) |
| OCR fallback | RapidOCR only for pages under 50 characters, bounded pixels/pages/seconds, thread-pool pages | `ingestion/ocr_fallback.py` (`apply_conditional_ocr`, line 368) |
| Visual analysis | PyMuPDF region detection, 2× crops, local-only VLM descriptions, `EvidenceElement` output | `ingestion/visual_analyzer.py` (line 217) |
| Provider contract | `BaseModelProvider` ABC + `ProviderCapabilities` / `HealthStatus` | `providers/model_provider.py` |
| Local provider | llama-server HTTP/SSE client with loopback-only enforcement | `providers/llama_cpp_provider.py` (line 56) |
| Cloud providers | LiteLLM multi-vendor adapter and direct Groq adapter, both consent-gated | `providers/litellm_provider.py`, `providers/groq_provider.py` |

## Pattern Overview

**Overall:** Layered modular monolith with a Streamlit composition root, explicit service objects, immutable Pydantic contracts, and adapter-based inference.

**Key Characteristics:**
- One deployable process: Streamlit UI, SQLite, LanceDB, and llama-server client all run locally; llama-server is the only external process.
- Layering is directional in intent: `ui` → `core`/`retrieval`/`ingestion`/`providers` → `core.models`; no package imports `ui`.
- Construction happens at the edges: `main.py` builds `DocStore`, `AiModel`, and cloud providers; `IngestionService` and `LifecycleService` receive their collaborators via constructor injection.
- `RetrievalResult` is the single evidence contract shared by prompt assembly and UI citation chips (`core/models.py:171`).
- Fail-closed persistence: vector writes raise `VectorIndexError` rather than silently reporting success (`retrieval/hybrid_retriever.py:75`, `:571`).
- Local-first privacy boundary is enforced in code, not only documentation: loopback-only local provider (`providers/llama_cpp_provider.py:82`), consent-gated cloud providers, and Markdown/HTML sanitization (`ui/sanitizer.py`).
- Every GPU-bound operation goes through `InferenceGate` (`core/local_llm.py:26`); preprocessing is CPU-pinned (Docling, MiniLM, RapidOCR).

## Layers

**Presentation:**
- Purpose: Render the four workspaces and capture user intent; own Streamlit session state and widget lifecycle.
- Location: `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`, `ui/session_state.py`
- Contains: `render_*` functions, CSS injection, local SVG loading, Markdown sanitization, session reset.
- Depends on: `core`, `retrieval`, `ingestion` (for constants), `ui/ingestion_service.py`, `ui/lifecycle_service.py`.
- Used by: `streamlit run main.py` only.

**UI orchestration services:**
- Purpose: Execute multi-step document workflows without widget code.
- Location: `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`
- Contains: `IngestionService`, `IngestionResult`, `LifecycleService`, hydration/repair routine.
- Depends on: `core.doc_store`, `core.models`, `retrieval.hybrid_retriever`, `retrieval.local_embedding`, `ingestion.*`.
- Used by: `main.py` (hydration) and `ui/views.py` (upload, delete, re-index).
- Note: `ui/hydration.py` imports `streamlit` directly and mutates `st.session_state`; the other two services are framework-agnostic.

**Domain services:**
- Purpose: Retrieval-grounded generation, summarization, intent resolution, citation verification, prompt budgeting, telemetry, logging, model identity.
- Location: `core/`
- Contains: `AiModel`, `InferenceGate`, `Summarizer`, `validate_citations`, `assemble_grounded_messages`, `resolve_retrieval`, `DocStore`, `get_gpu_memory_info`, `configure_logging`, `verify_local_model_pair`.
- Depends on: `core.models`, `providers.model_provider`, `providers.llama_cpp_provider`, `retrieval.hybrid_retriever`, `retrieval.local_embedding`.
- Used by: presentation and UI orchestration services.

**Ingestion adapters:**
- Purpose: Turn untrusted PDF bytes into canonical `Chunk`, `Page`, and `EvidenceElement` records.
- Location: `ingestion/`
- Contains: validation, Docling reader, pypdf fallback, conditional OCR, visual analyzer.
- Depends on: `core.models`, `providers.model_provider` (type only), third-party Docling/pypdf/PyMuPDF/RapidOCR.
- Used by: `ui/ingestion_service.py`.

**Retrieval adapters:**
- Purpose: Persist embeddings and serve dense + keyword evidence.
- Location: `retrieval/`
- Contains: `HybridRetriever`, `LocalEmbedding`, `VectorIndex`, RRF implementation, LanceDB schema, fallback mirror.
- Depends on: `core.models`, LanceDB/PyArrow (optional), sentence-transformers.
- Used by: `core.local_llm`, `ui.ingestion_service`, `ui.lifecycle_service`, `ui.hydration`, `ui.views`.

**Inference adapters:**
- Purpose: Implement the `BaseModelProvider` contract for local and cloud backends.
- Location: `providers/`
- Contains: provider ABC and schemas, llama-server client, LiteLLM adapter, Groq adapter.
- Depends on: `providers.model_provider`, `httpx`, `litellm`, `groq` (optional).
- Used by: `core.local_llm`, `core.summarizer` (type only), `ingestion.visual_analyzer` (type only), `main.py` (cloud provider construction).

**Persistence:**
- Purpose: Durable source of truth and rebuildable vector index.
- Location: `core/doc_store.py`, `data/documents.db`, `data/lancedb/`, `.cache/`
- Contains: SQLite schema/migrations, LanceDB table `chunks`, JSON fallback mirror `data/lancedb/fallback_store.json`.
- Depends on: Python `sqlite3`, LanceDB, filesystem.
- Used by: all higher layers.

## Data Flow

### Primary Request Path (Chat Q&A)

1. Streamlit rerun enters the composition root and hydrates catalog/retriever if needed (`main.py:180`).
2. Chat workspace is rendered (`main.py:443` → `ui/views.py:490`).
3. User prompt is appended to history and contextualized for short follow-ups (`ui/views.py:701`, `core/query_intent.py:77`).
4. Document scope is resolved from the focus selector or filename mention in the prompt (`ui/views.py:709`).
5. Retrieval runs through `resolve_retrieval` (`ui/views.py:729` → `core/query_intent.py:227`):
   - Ordinary query → `HybridRetriever.search_hybrid` (`retrieval/hybrid_retriever.py:959`).
   - Exhaustive “list all …” query with one document → `fetch_document_chunks` + page-diverse budgeting (`retrieval/hybrid_retriever.py:641`, `core/query_intent.py:147`).
   - Exhaustive query with no single document → `search_mode="intent_mismatch"` and generation is skipped (`ui/views.py:741`).
6. `AiModel.ask_a_question_from_pdf_stream` assembles bounded messages (`core/local_llm.py:247` → `core/prompt_budget.py:75`), acquires `InferenceGate`, and streams provider tokens (`core/local_llm.py:329`).
7. Provider streams from llama-server or the consented cloud adapter (`providers/llama_cpp_provider.py:231`, `providers/litellm_provider.py:241`).
8. Tokens are rendered incrementally; missing citations are auto-attributed by lexical overlap (`ui/views.py:791` → `core/citation_validator.py:427`).
9. Response is verified (`core/citation_validator.py:302`); injection echoes are withheld, ungrounded answers are annotated but not silently deleted (`ui/views.py:802`).
10. Assistant turn stores content, verification, snippets, truncation metadata, and provider provenance in `st.session_state.chat_history` (`ui/views.py:881`).

### Ingestion Path

1. Sidebar uploader captures PDFs (`ui/views.py:415` → `render_file_upload_button`, line 387).
2. `process_uploaded_files` enforces the UI size cap and builds `IngestionService` with the session retriever/embedder (`ui/views.py:307`).
3. `IngestionService.ingest_pdf` (`ui/ingestion_service.py:54`):
   - `validate_pdf_bytes` checks `%PDF-`, 50 MB, 1–500 pages, computes SHA-256 and `doc_<sha16>` (`ingestion/upload_validation.py:120`).
   - SHA-256 dedupe; if SQLite says indexed but LanceDB lacks vectors, re-embed from stored chunks and repair (`ui/ingestion_service.py:98`).
   - Docling extraction on CPU with pypdf fallback (`ingestion/docling_reader.py:143`, `ui/ingestion_service.py:147`).
   - Conditional RapidOCR for low-text pages (`ingestion/ocr_fallback.py:368`).
   - Visual region detection and local-VLM descriptions, capped at 6 regions during ingestion (`ingestion/visual_analyzer.py:217`, `ui/ingestion_service.py:192`).
   - Atomic SQLite write of document + pages + chunks + evidence (`core/doc_store.py:352`).
   - Delete stale vectors for the `doc_id`, embed all chunks, upsert into LanceDB, verify retrievability, then index evidence (`ui/ingestion_service.py:272` → `retrieval/hybrid_retriever.py:452`).
4. Session metadata is updated; `uploader_key` is rotated to avoid reprocessing (`ui/views.py:344`, `ui/views.py:410`).

### Summarization Path

1. Summarizer view selects document and profile (`ui/views.py:923`).
2. `Summarizer.summarize_document` validates the profile and checks the SQLite cache keyed by `sha256 + profile + model_version` (`core/summarizer.py:465`).
3. Pages are reconstructed from chunks and enriched with visual evidence (`core/summarizer.py:503`, `:185`).
4. `InferenceGate.hold(timeout=120)` wraps generation (`core/summarizer.py:559`).
5. Documents ≤2,000 estimated tokens use a single pass; larger documents use sequential map-reduce with 2,000-token page bundles and bounded consolidation (`core/summarizer.py:411`).
6. Page references are extracted and clamped to real pages; `SummaryResult` is persisted and mirrored into session cache (`core/summarizer.py:567`, `ui/views.py:994`).

### Startup Hydration Path

1. `main.py` builds a process-wide `DocStore` via `@st.cache_resource` (`main.py:129`).
2. `hydrate_startup_state` lists documents, restores session catalog, creates a `HybridRetriever` if absent, and checks vector coverage per indexed document (`ui/hydration.py:34`).
3. Only documents with missing vectors are re-embedded from SQLite chunks; failures are isolated per document (`ui/hydration.py:98`).
4. `_startup_hydrated` is set only when retriever discovery/repair completes, so a hard failure retries on the next rerun (`ui/hydration.py:166`).

### Delete / Purge Path

1. Library or sidebar action delegates to `_delete_document` / `_purge_all` (`ui/views.py:165`, `:238`).
2. `LifecycleService.delete_document` deletes vectors first (aborts on failure), then SQLite rows, then the `cache_dir_for` directory, then session metadata (`ui/lifecycle_service.py:32`).
3. `LifecycleService.purge_all` purges vectors, SQLite (including `VACUUM`), `.cache/`, and session state; any tier failure is collected and raised after session cleansing (`ui/lifecycle_service.py:102`).

**State Management:**
- Persistent truth: SQLite `data/documents.db` (`core/doc_store.py`); LanceDB `data/lancedb/` is rebuildable from SQLite chunks.
- Session truth: `st.session_state` holds `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `chat_history`, `hybrid_retriever`, `local_embedding`, `ai_model`, cloud consent/keys, workspace, and summary cache keys.
- Process truth: one `DocStore` per process (`st.cache_resource`), one SentenceTransformer per `(model, device)` (`retrieval/local_embedding.py:25`), one `InferenceGate` lock (`core/local_llm.py:34`), telemetry caches (`core/resource_telemetry.py:22`).
- Cross-turn isolation: `AiModel` is session-scoped and `reset_turn_state()` clears prior retrieval/citation/truncation state (`core/local_llm.py:158`, `ui/session_state.py:16`).

## Key Abstractions

**Canonical Pydantic models:**
- Purpose: One validated schema per domain concept, shared by persistence, retrieval, prompts, and UI.
- Examples: `core/models.py` (`Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`).
- Pattern: `extra="forbid"`, frozen for immutable evidence (`BBox`, `Chunk`, `EvidenceSnippet`, `RetrievalResult`), validators enforce `doc_` prefixes and SHA-256 shape.

**RetrievalResult / EvidenceSnippet:**
- Purpose: Immutable evidence contract with rank, dense/FTS provenance, page, bbox, and character offsets.
- Examples: produced by `HybridRetriever.search_hybrid` and `fetch_document_chunks`; consumed by `formatted_evidence()` in prompts and citation chips in `ui/components.py`.
- Pattern: Adapter output normalized into a domain model so UI and prompt assembly cannot drift.

**BaseModelProvider:**
- Purpose: Uniform contract for text generation, streaming, vision analysis, health, and capabilities.
- Examples: `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`.
- Pattern: Abstract base class + frozen capability/health value objects; provider selection remains in `AiModel._detect_provider` and `main.py`.

**AiModel facade:**
- Purpose: Hide provider differences and centralize retrieval-context assembly, budgets, gating, and citation validation.
- Examples: `core/local_llm.py:103`.
- Pattern: Facade + strategy (provider), generator-based streaming, explicit per-turn state.

**InferenceGate:**
- Purpose: Enforce the 4 GB VRAM envelope by allowing one GPU inference at a time across threads and Streamlit sessions.
- Examples: `core/local_llm.py:26`; used by `AiModel`, `Summarizer`, and `VisualAnalyzer`.
- Pattern: Class-level `threading.RLock` + context manager with timeout.

**IngestionService / LifecycleService:**
- Purpose: Transaction scripts for multi-tier document operations.
- Examples: `ui/ingestion_service.py:39`, `ui/lifecycle_service.py:17`.
- Pattern: Constructor injection of store/retriever/embedder/cache; return typed result (`IngestionResult`) or boolean; never touch widgets.

**DocStore unit of work:**
- Purpose: Atomic multi-table writes and schema evolution.
- Examples: `core/doc_store.py:352` (`record_ingestion`), `:219` (`_apply_migrations`), `:178` (`_execute_write`).
- Pattern: Per-operation connections, WAL, busy retry with jitter, one transaction per ingestion.

**Cache path convention:**
- Purpose: Stable per-content cache namespace.
- Examples: `core/models.py:17` (`cache_dir_for(base, sha256) → base/<sha256>/<CONFIG_VERSION>`).
- Pattern: Content-addressed path used by lifecycle cleanup; no ingestion module currently writes intermediate extraction files there.

## Entry Points

**Streamlit application:**
- Location: `main.py`
- Triggers: `streamlit run main.py`, `python start.py`, or the Docker `CMD`.
- Responsibilities: page config, theme injection, session defaults, logging, DocStore/model/hydration initialization, health throttling, cloud consent dialog, sidebar, workspace routing.

**Unified launcher:**
- Location: `start.py` (`main`, line 273)
- Triggers: `python start.py [--start-llama]`
- Responsibilities: Python version check, loopback bind enforcement, directory creation, llama-server probe/launch, GGUF identity verification, Streamlit subprocess.

**Setup/packaging CLI:**
- Location: `setup.py`
- Triggers: `python setup.py`, `download_models`, `install-llama`, `pip install -e .`
- Responsibilities: dependency install, model/server download with checksum validation, package metadata.

**Operational scripts:**
- Location: `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`
- Triggers: manual invocation.
- Responsibilities: latency/memory benchmarks, multimodal quality evaluation, resource profiling, icon regeneration.

**Test entry point:**
- Location: `tests/` (pytest, config in `pyproject.toml`)
- Triggers: `pytest tests/ -v` (CI runs corpus generation first).
- Responsibilities: offline unit/integration coverage with mocked providers and synthetic PDFs.

## Architectural Constraints

- **Threading:** Streamlit executes the script on a single thread per rerun. OCR parallelizes page work with `ThreadPoolExecutor` (`ingestion/ocr_fallback.py`). GPU inference is serialized process-wide by `InferenceGate` (`core/local_llm.py:34`).
- **Global state:** `InferenceGate._lock` (`core/local_llm.py:34`), `_MODEL_CACHE` (`retrieval/local_embedding.py:25`), `_LATENCY_HISTORY` + GPU cache (`core/resource_telemetry.py:22`), `_ICON_CACHE` (`ui/components.py:10`), process-wide `DocStore` via `@st.cache_resource` (`main.py:129`).
- **Circular imports:** None at module import time. `ingestion/visual_analyzer.py:288` performs a function-local import of `core.local_llm.InferenceGate` to avoid an ingestion → domain → provider import cycle at startup.
- **Windows file locking:** SQLite uses per-operation connections and closes them in `finally` (`core/doc_store.py:157`); no long-lived connection is shared across reruns.
- **VRAM ceiling:** Docling pinned to CPU (`ingestion/docling_reader.py:183`), MiniLM pinned to CPU (`retrieval/local_embedding.py:56`), context window default 4,096 (`providers/llama_cpp_provider.py:67`), output reservation 1,536 (`core/prompt_budget.py:17`).
- **Local-only inference:** `LlamaCppProvider` rejects non-loopback endpoints unless `allow_remote=True` (`providers/llama_cpp_provider.py:82`); cloud providers refuse generation without `user_consented` (`providers/litellm_provider.py:142`, `providers/groq_provider.py:62`); visual analysis refuses non-local providers (`ingestion/visual_analyzer.py:259`).
- **No authentication:** the app is single-user; `start.py` refuses non-loopback binds unless explicitly overridden (`start.py:59`), and `.streamlit/config.toml` binds `127.0.0.1`.
- **Persistence ordering:** vectors are deleted before SQLite rows; vector write failure marks the document `failed` and returns an error rather than claiming success (`ui/lifecycle_service.py:49`, `ui/ingestion_service.py:300`).

## Anti-Patterns

### Provider construction scattered across the composition root and domain

**What happens:** `main.py:221` constructs `LiteLLMProvider` directly, while `AiModel._detect_provider` hardcodes `LlamaCppProvider()` (`core/local_llm.py:223`). There is no provider factory or registry.
**Why it's wrong:** Adding a provider or changing defaults requires edits in multiple layers; tests must monkeypatch concrete classes; configuration (base URL, context window) is split between `AiModel`, `main.py`, and environment variables.
**Do this instead:** Add a `providers/factory.py` with `create_provider(config) -> BaseModelProvider`, call it from `main.py` and `AiModel`, and keep provider-specific defaults inside each adapter.

### Presentation layer orchestrates multi-step domain workflows

**What happens:** `ui/views.py` (1,332 lines) performs retrieval, scope detection, generation, auto-attribution, citation verification, history mutation, and evidence rendering in `render_chat_view` (`ui/views.py:695-897`).
**Why it's wrong:** The chat workflow cannot be tested without Streamlit; logic is duplicated with `AiModel`’s internal retrieval branch (`core/local_llm.py:289-313`); changes to grounding behavior require editing a renderer.
**Do this instead:** Extract a framework-free `ChatTurnService` (e.g. `ui/chat_service.py` or `core/chat.py`) that accepts a retriever, `AiModel`, prompt, and history and returns a typed turn result; let `render_chat_view` only render it.

### Legacy retrieval facades and duck-typed retriever branches

**What happens:** `HybridRetriever.search()` and `.get_context()` are deprecated wrappers (`retrieval/hybrid_retriever.py:1074`, `:1084`); `LocalEmbedding.search_hybrid()` is deprecated (`retrieval/local_embedding.py:114`); `AiModel` still branches on `hasattr(... "get_context")`, `"search_hybrid"`, and `isinstance(..., HybridRetriever)` (`core/local_llm.py:289-313`).
**Why it's wrong:** Three retrieval shapes produce subtly different evidence objects and ranking semantics; deprecated paths can silently bypass `RetrievalResult` provenance used by citation validation.
**Do this instead:** Standardize on `search_hybrid(query, k, doc_id) -> RetrievalResult` and `fetch_document_chunks(doc_id) -> RetrievalResult`; delete the compatibility branches after updating callers, or isolate them behind a single adapter function.

### Navigation source-of-truth drift

**What happens:** The sidebar’s `WORKSPACES` list contains only `Chat` and `Document Library` (`main.py:383-386`), but the router handles four workspaces including `Summarizer` and `Settings` (`main.py:443-470`). The “Open Diagnostics” button sets `active_workspace = "Settings"` (`main.py:419`), which the radio then resets to `Chat` on the next rerun (`main.py:400-402`).
**Why it's wrong:** Reachable UI state depends on which control ran last; workspaces can become unreachable or silently redirect, and tests can pass while navigation is broken.
**Do this instead:** Define one `Workspace` enum/list used by both the radio and the router, and render navigation for every routable workspace (or remove unroutable entries).

### Framework leakage into infrastructure adapters

**What happens:** `providers/litellm_provider.py:59,76` and `providers/groq_provider.py:44` import `streamlit` to read `st.secrets`; `ui/hydration.py:7` imports `streamlit` and mutates `st.session_state`.
**Why it's wrong:** Provider and hydration logic cannot run outside a Streamlit runtime (CLI benchmarks, batch jobs, tests), and credential lookup policy is duplicated inside adapters.
**Do this instead:** Inject a `SecretProvider`/`SessionState` adapter from the composition root, or resolve keys in `main.py` and pass `api_key` into the provider constructor.

### Concurrency primitive hidden inside the LLM facade

**What happens:** `VisualAnalyzer.analyze_visual_elements` imports `InferenceGate` from `core.local_llm` inside the loop (`ingestion/visual_analyzer.py:288`), creating an ingestion → domain → provider dependency only when vision runs.
**Why it's wrong:** The layering inversion is invisible at import time, makes the ingestion package depend on the LLM facade, and complicates testing/mocking of vision analysis.
**Do this instead:** Move `InferenceGate` to a small `core/inference_gate.py` (or `core/concurrency.py`) and import it from `local_llm.py`, `summarizer.py`, and `visual_analyzer.py` alike.

### Script-style composition root

**What happens:** `main.py` executes initialization and rendering at module top level (page config, session loop, storage, hydration, provider sync, sidebar, routing) rather than inside a `main()` function.
**Why it's wrong:** Importing `main.py` for tests triggers Streamlit side effects; startup failures must be handled inline; logic cannot be reused by a non-Streamlit entry point.
**Do this instead:** Wrap orchestration in `def main()` and keep module-level code to imports/constants; extract startup checks into testable functions (`initialize_store()`, `initialize_model()`, `render_sidebar()`).

## Error Handling

**Strategy:** Fail closed at persistence and privacy boundaries; degrade gracefully for enrichment; always leave the UI with an actionable message rather than a blank page.

**Patterns:**
- Startup boundary: DocStore or model initialization failure renders remediation and calls `st.stop()` (`main.py:139-151`, `:197-207`).
- Per-stage ingestion isolation: validation, extraction, OCR, visual analysis, SQLite, and vector indexing each have their own `try/except`; enrichment failures are logged and do not discard successfully extracted text (`ui/ingestion_service.py:80-210`).
- Typed failures: `ValueError`/`TypeError` for invalid inputs, `VectorIndexError` for vector persistence (`retrieval/hybrid_retriever.py:75`), `TimeoutError` from `InferenceGate` (`core/local_llm.py:94`), `PermissionError` for unconsented cloud mode (`core/local_llm.py:134`).
- Retry policy: SQLite write transactions retry `SQLITE_BUSY`/`SQLITE_LOCKED` up to 3 times with exponential backoff and jitter (`core/doc_store.py:28`, `:178`).
- Best-effort cleanup: disk-cache deletion failures are warnings, not blockers (`ui/lifecycle_service.py:67`); purge collects tier failures and raises after session cleansing (`ui/lifecycle_service.py:156`).
- Provider health: throttled to one probe per 5 seconds per session; probe failure produces an offline `HealthStatus` instead of an exception (`main.py:249-283`).
- Answer grounding: injection echoes are blocked; missing/invalid citations produce a visible warning but the draft remains readable (`ui/views.py:806-828`, `core/citation_validator.py:221`).

## Cross-Cutting Concerns

**Logging:** `configure_logging` installs one idempotent configuration with stderr plus rotating file `data/logs/app.log` (`core/logging_setup.py:57`); level via `RAG_LOG_LEVEL`; every module uses `logging.getLogger(__name__)`. A filter suppresses the benign Streamlit `torch.classes` watcher traceback (`core/logging_setup.py:146`).

**Validation:** Pydantic `extra="forbid"` and custom validators (`core/models.py`); PDF magic-byte/size/page validation (`ingestion/upload_validation.py:120`); LanceDB SQL literal escaping (`retrieval/hybrid_retriever.py:55`); GGUF metadata identity verification (`core/model_identity.py:85`); untrusted document text isolated in `<document_context>` with tag escaping (`core/prompt_budget.py:44`).

**Authentication/Authorization:** Not applicable — no user accounts or sessions beyond Streamlit’s browser session. Cloud egress is gated by explicit consent plus provider-level `user_consented` checks; API keys live in session state or environment variables.

**Telemetry:** GPU VRAM via `nvidia-smi` with 5-second TTL, process RSS/VMS via psutil, and stage latency tracking (`core/resource_telemetry.py`); surfaced in Settings (`ui/views.py:1284`) and the sidebar (`main.py:406`).

**Output sanitization:** `sanitize_markdown_for_local` strips scripts/iframes/objects/embeds/styles, neutralizes event handlers, and blocks external Markdown/HTML destinations unless cloud mode is consented (`ui/sanitizer.py:130`, used at `ui/views.py:619`, `:1032`).

---

*Architecture analysis: 2026-10-26*
