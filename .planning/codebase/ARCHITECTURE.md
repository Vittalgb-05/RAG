<!-- refreshed: 2026-10-21 -->
# Architecture

**Analysis Date:** 2026-10-21

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Presentation (Streamlit server-side UI)                                      │
│ `main.py` · `ui/views.py` · `ui/components.py` · `ui/theme.py`                │
│ `ui/sanitizer.py` · `.streamlit/config.toml` · `assets/icons/*.svg`           │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ render_* calls, st.session_state
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ UI Orchestration Services                                                    │
│ `ui/ingestion_service.py` (IngestionService)                                 │
│ `ui/lifecycle_service.py` (LifecycleService)                                 │
│ `ui/hydration.py` (hydrate_startup_state)                                    │
└───────────────┬──────────────────────────────────────────────┬───────────────┘
                │                                              │
                ▼                                              ▼
┌───────────────────────────────────────────┐  ┌───────────────────────────────┐
│ Ingestion & Retrieval Pipeline            │  │ Domain / Inference            │
│ `upload_validation.py`                    │  │ `local_llm.py` (AiModel, Gate)│
│ `docling_reader.py` → `pdf_reader.py`     │  │ `summarizer.py`               │
│ `ocr_fallback.py`                         │  │ `citation_validator.py`       │
│ `visual_analyzer.py`                      │  │ `prompt_budget.py`            │
│ `local_embedding.py` → `hybrid_retriever.py`│ │ `model_provider.py` (ABC)    │
│ `vector_index.py`                         │  │ provider adapters             │
└───────────────┬───────────────────────────┘  └──────────────┬────────────────┘
                │                                              │
                ▼                                              ▼
┌───────────────────────────────────────────┐  ┌───────────────────────────────┐
│ Persistence                               │  │ Runtime backends              │
│ `doc_store.py` → `data/documents.db`      │  │ llama-server 127.0.0.1:8080   │
│ LanceDB → `data/lancedb/`                 │  │ optional cloud APIs           │
│ `.cache/<sha256>/<CONFIG_VERSION>/`       │  │ `nvidia-smi`, psutil          │
└───────────────────────────────────────────┘  └───────────────────────────────┘
```

The system is a single-process, modular monolith. `main.py` is the composition root: it
constructs the `DocStore`, hydrates session state, builds the session-scoped `AiModel`,
and routes to one of four workspaces. All GPU-backed generation is serialized through a
process-wide `InferenceGate`. Document preprocessing (Docling, pypdf, RapidOCR, MiniLM
embeddings) runs on CPU so the full 4 GB VRAM envelope is reserved for the local VLM.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit entry point | Page config, theme, session defaults, hydration, provider wiring, workspace routing | `main.py` |
| Workspace renderers | Sidebar upload/document list, Chat, Summarizer, Library, Settings | `ui/views.py` |
| Reusable UI atoms | Brand mark, SVG icon cache, stat cards, status pills, empty states, citation chips | `ui/components.py` |
| Theme | AMOLED CSS tokens and injection | `ui/theme.py` |
| Output sanitizer | Strips scripts/embeds, neutralizes external links/images in local mode | `ui/sanitizer.py` |
| Startup hydration | Restores `doc_ids`, metadata and retriever from SQLite/LanceDB; repairs missing vectors | `ui/hydration.py` |
| Ingestion orchestration | Validate → dedupe → extract → OCR → VLM → persist → index → cache | `ui/ingestion_service.py` |
| Lifecycle orchestration | Delete/purge/re-index across SQLite, LanceDB, disk cache, session state | `ui/lifecycle_service.py` |
| Inference facade | Provider selection, retrieval assembly, prompt budgeting, streaming, citation validation | `local_llm.py` |
| GPU concurrency gate | Process-level reentrant lock defining one active inference operation | `local_llm.py` (`InferenceGate`) |
| Summarization | Five profiles, fast single-pass or token-budgeted map-reduce, SQLite cache | `summarizer.py` |
| Citation validation | `[E#]` precision, abstention, prompt-injection echo detection | `citation_validator.py` |
| Prompt budgeting | Token estimation, `<document_context>` isolation, oldest-first history truncation | `prompt_budget.py` |
| Provider contract | `BaseModelProvider` ABC plus `ProviderCapabilities` / `HealthStatus` schemas | `model_provider.py` |
| Local provider | HTTP/SSE client for llama-server with loopback/SSRF enforcement | `llama_cpp_provider.py` |
| Cloud provider | LiteLLM adapter with consent gate, API-key scrubbing, vision support | `litellm_provider.py` |
| Legacy cloud provider | Direct Groq client adapter used as a cloud fallback probe | `groq_provider.py` |
| Hybrid retrieval | Dense + FTS candidate pooling, RRF fusion, canonical `RetrievalResult` | `hybrid_retriever.py` |
| Embeddings | CPU-pinned MiniLM, 384-d L2-normalized vectors, shared process cache | `local_embedding.py` |
| Relational store | SQLite WAL metadata, pages, chunks, evidence, summaries, migrations v1–v4 | `doc_store.py` |
| Canonical models | Pydantic v2 schemas and cache path convention | `models.py` |
| Upload validation | Magic bytes, size/page caps, streaming SHA-256, stable `doc_id` | `upload_validation.py` |
| Structured extraction | Docling layout/markdown tables with pypdf fallback and chunking | `docling_reader.py` |
| Plain extraction | pypdf text extraction and page records | `pdf_reader.py` |
| OCR fallback | Conditional RapidOCR for low-text pages, CPU/threaded | `ocr_fallback.py` |
| Visual understanding | PyMuPDF region detection, 2× crops, VLM descriptions as evidence | `visual_analyzer.py` |
| Telemetry | VRAM/RAM sampling, latency tracking, telemetry snapshot | `resource_telemetry.py` |
| In-memory vectors | Pure-Python cosine/euclidean vector index used as LanceDB fallback | `vector_index.py` |
| Launcher | Preflight checks, llama-server spawn, Streamlit subprocess | `start.py` |
| Setup/packaging | Model downloads, llama-server install, dependency installation, CLI commands | `setup.py` |
| Logging helper | Suppresses the benign Streamlit `torch.classes` watcher traceback | `logging_setup.py` |

## Pattern Overview

**Overall:** Layered modular monolith with a composition root, service layer, canonical
Pydantic domain models, and a provider-adapter (strategy) boundary for inference.

**Key Characteristics:**
- **Composition root:** `main.py` owns object construction and session wiring; renderers
  receive dependencies as arguments instead of importing singletons.
- **Canonical domain schemas:** every boundary (extraction → SQLite → LanceDB → prompt →
  UI) uses models from `models.py`. `RetrievalResult` / `EvidenceSnippet` are shared by
  generation and citation rendering.
- **Service-layer transactions:** all persistence writes from the UI go through
  `IngestionService` (`ui/ingestion_service.py`) or `LifecycleService`
  (`ui/lifecycle_service.py`), never ad-hoc SQL in views.
- **Provider strategy:** `AiModel` holds a `BaseModelProvider` and can swap local
  llama.cpp ↔ cloud LiteLLM without changing callers (`local_llm.py:145-185`).
- **Graceful degradation:** Docling → pypdf, LanceDB → in-memory/JSON index, LanceDB FTS
  → Python BM25, no OCR/VLM when unavailable, local provider → cloud only with consent.
- **Single-GPU serialization:** all inference paths acquire `InferenceGate`.
- **Session-scoped state:** `AiModel`, retriever, consent, credentials, chat history, and
  document catalog live in `st.session_state` (see `main.py:112-132`).

## Layers

**Presentation (`main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`):**
- Purpose: render the Streamlit application and capture user intent.
- Location: repository root `main.py`, package `ui/`.
- Contains: page composition, four workspace renderers, HTML/CSS rendering helpers,
  markdown sanitization, consent dialog, telemetry cards.
- Depends on: UI orchestration services, `AiModel`, `DocStore`, `Summarizer`,
  `resource_telemetry`, canonical models.
- Used by: Streamlit runtime only.

**UI Orchestration (`ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`):**
- Purpose: coordinate multi-store workflows and session synchronization.
- Location: `ui/`.
- Contains: `IngestionService.ingest_pdf`, `LifecycleService.delete_document`,
  `purge_all`, `reindex_document`, `hydrate_startup_state`.
- Depends on: extraction/OCR/VLM modules, `DocStore`, `HybridRetriever`,
  `LocalEmbedding`, `models`.
- Used by: `ui/views.py` and `main.py`.

**Domain / Inference (`local_llm.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `model_provider.py`, provider modules):**
- Purpose: ground prompts, call models, validate citations, summarize.
- Location: repository root.
- Contains: `AiModel`, `InferenceGate`, `Summarizer`, `validate_citations`,
  `assemble_grounded_messages`, `BaseModelProvider` and three adapters.
- Depends on: `models`, retrieval, embeddings, third-party SDKs.
- Used by: presentation, ingestion (VLM), hydration.

**Ingestion & Extraction (`upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`):**
- Purpose: turn untrusted PDF bytes into validated `Chunk`, `Page`, `EvidenceElement`.
- Location: repository root.
- Contains: validation, layout-aware extraction, OCR fallback, visual region analysis.
- Depends on: pypdf, Docling, RapidOCR, PyMuPDF, `models`.
- Used by: `IngestionService`, hydration/reindex repair.

**Retrieval (`local_embedding.py`, `hybrid_retriever.py`, `vector_index.py`):**
- Purpose: embed and retrieve evidence with dense + keyword fusion.
- Location: repository root.
- Contains: MiniLM CPU embeddings, LanceDB table management, BM25 fallback, RRF.
- Depends on: sentence-transformers, LanceDB/PyArrow, `models`.
- Used by: `AiModel`, `IngestionService`, `LifecycleService`, `ui/views.py`.

**Persistence (`doc_store.py`, `models.py`):**
- Purpose: durable document metadata, chunks, pages, evidence, summaries, cache paths.
- Location: `data/documents.db`, `data/lancedb/`, `.cache/`, with code at repository root.
- Contains: per-operation SQLite connections in WAL mode, schema migrations, CRUD.
- Depends on: stdlib `sqlite3`, Pydantic.
- Used by: all orchestration layers.

**Runtime / CLI (`start.py`, `setup.py`, `scripts/`, `docs/`):**
- Purpose: launch, install, benchmark, and operate the system.
- Location: repository root and `scripts/`.
- Contains: launcher, model/server installer, benchmark scripts, operational docs.
- Depends on: subprocess, urllib, filesystem; not imported by the app at runtime.

## Data Flow

### Application Startup & Hydration

1. `python start.py` parses CLI flags and verifies Python ≥ 3.11 (`start.py:214-239`).
2. `ensure_directories()` creates `data/`, `.cache/`, `models/`, `tools/`
   (`start.py:57-66`, `start.py:240`).
3. With `--start-llama`, `start_llama_server_process()` spawns llama-server and polls
   `/health` for up to 10 s; otherwise it probes an existing server (`start.py:114-178`,
   `start.py:243-251`).
4. `launch_streamlit()` spawns `streamlit run main.py` (`start.py:181-211`).
5. `main.py` configures the page and injects the AMOLED theme (`main.py:98-106`).
6. Session defaults are seeded for document catalog, retriever, chat, cloud consent,
   uploader key, and workspace (`main.py:112-132`).
7. `DocStore(data/documents.db)` applies schema migrations (`main.py:140-142`,
   `doc_store.py:151-164`).
8. `hydrate_startup_state(doc_store)` loads indexed/failed documents, rebuilds metadata,
   constructs a `HybridRetriever`, and repairs missing vectors from SQLite chunks
   (`main.py:145`, `ui/hydration.py:13-74`).
9. `AiModel` is created/reused per session, then cloud mode is synchronized and health/
   capabilities are fetched (`main.py:148-192`).

### Ingestion (PDF → SQLite + LanceDB + cache)

1. `render_sidebar_documents` receives uploads and constructs `IngestionService`
   (`ui/views.py:64-80`).
2. `IngestionService.ingest_pdf` validates magic bytes/limits and derives
   `doc_<sha16>` (`ui/ingestion_service.py:78-95`, `upload_validation.py:64-113`).
3. SHA deduplication checks SQLite; if vectors are missing it re-embeds persisted chunks
   and indexes them before returning `already_indexed` (`ui/ingestion_service.py:97-137`).
4. Docling extracts layout/tables and chunks; on failure `PdfReader` (pypdf) is used
   (`ui/ingestion_service.py:139-171`, `docling_reader.py:95-320`).
5. Pages below 50 characters are OCR'd via RapidOCR (`ui/ingestion_service.py:173-185`,
   `ocr_fallback.py:35-49`, `ocr_fallback.py:318`).
6. Visual regions are detected and up to six are described by the local VLM, producing
   `EvidenceElement` rows (`ui/ingestion_service.py:187-208`, `visual_analyzer.py:49-309`).
7. Zero-chunk documents are recorded as `failed` (`ui/ingestion_service.py:210-233`).
8. SQLite is written transactionally: document, evidence, pages, chunks
   (`ui/ingestion_service.py:235-266`).
9. MiniLM embeds chunks; `HybridRetriever.index_chunks` writes LanceDB and the fallback
   index; visual evidence is indexed too (`ui/ingestion_service.py:268-309`,
   `hybrid_retriever.py:256-408`). On failure the document status is rolled back to
   `failed` (`ui/ingestion_service.py:283-309`).
10. Intermediate artifacts are written to
    `.cache/<sha256>/docling-1000-200-v1/{pages,chunks,manifest}.json`
    (`ui/ingestion_service.py:311-322`, `models.py:17-30`).
11. UI session state is updated (`doc_ids`, `indexed_files`, `document_metadata`) and the
    uploader key is rotated to prevent rerun loops (`ui/views.py:101-142`).

### Chat Q&A (retrieve → ground → stream → verify)

1. Chat view reads the question and optional focus document (`ui/views.py:337-376`).
2. If a previous user turn exists, it is prepended to the retrieval query
   (`ui/views.py:360-369`).
3. `HybridRetriever.search_hybrid` performs dense search, FTS/BM25 search, optional
   `doc_id` filtering, and RRF fusion into a `RetrievalResult`
   (`ui/views.py:373-379`, `hybrid_retriever.py:580-693`).
4. `AiModel.ask_a_question_from_pdf_stream` converts snippets to `[E#]` blocks with
   `RetrievalResult.formatted_evidence()` (`local_llm.py:237-283`, `models.py:185-194`).
5. `assemble_grounded_messages` budgets tokens, sanitizes XML boundaries, truncates
   history oldest-first, and wraps context in `<document_context>`
   (`local_llm.py:285-296`, `prompt_budget.py:57-142`).
6. `InferenceGate.acquire(timeout=60)` serializes generation; the provider streams tokens
   (`local_llm.py:298-311`).
7. `validate_response` checks every `[E#]` against the returned snippet set, detects
   abstention and injection echoes (`local_llm.py:341-359`,
   `citation_validator.py:115-230`).
8. The assistant turn stores content, sources, verification, snippet snapshots, and
   local/cloud attribution (`ui/views.py:443-453`); citation chips and an evidence drawer
   are rendered from the same snippets (`ui/views.py:304-335`, `ui/views.py:419-441`).

### Summarization

1. Summarizer view selects a document and one of five profiles
   (`ui/views.py:474-516`, `summarizer.py:31-105`).
2. `Summarizer.summarize_document` validates the profile and checks the SQLite cache
   keyed by `sha256 + profile + model_version` (`summarizer.py:301-337`).
3. Pages are reconstructed from chunks when not supplied (`summarizer.py:339-384`).
4. `InferenceGate.hold(timeout=120)` guards the whole operation
   (`summarizer.py:388-395`).
5. Documents ≤ 2,500 estimated tokens use single-pass; larger documents use sequential
   token-budgeted map-reduce with optional half-consolidation and a final reduce
   (`summarizer.py:205-299`).
6. Page references are extracted and clamped, and a `SummaryResult` is cached in SQLite
   (`summarizer.py:397-422`).
7. The UI displays the summary, offers Markdown export, and sanitizes rendering when in
   local mode (`ui/views.py:549-583`).

### Document Lifecycle (delete / purge / re-index)

- **Delete:** `LifecycleService.delete_document` removes SQLite rows, LanceDB rows, the
  document cache directory, and session references (`ui/lifecycle_service.py:31-87`).
- **Purge:** `purge_all` drops SQLite tables with `VACUUM`, drops the LanceDB table,
  removes `.cache/`, and clears session state (`ui/lifecycle_service.py:89-132`,
  `doc_store.py:619`).
- **Re-index:** `reindex_document` re-embeds persisted chunks and visual evidence from
  SQLite into LanceDB (`ui/lifecycle_service.py:134-166`).

### Cloud Consent & Provider Switch

1. Settings toggle requests consent if not already granted
   (`ui/views.py:713-736`).
2. The consent dialog explains transmitted excerpts vs. local-only artifacts
   (`main.py:200-244`).
3. With consent, `LiteLLMProvider` is constructed with `user_consented=True` and cached in
   session state; otherwise local mode is forced (`main.py:161-188`).
4. Every cloud call re-asserts consent and scrubs API keys from errors
   (`litellm_provider.py:135-148`, `litellm_provider.py:211`).
5. Revoking consent resets cloud state and closes the provider
   (`ui/views.py:794-798`, `main.py:56-91`).

## Key Abstractions

**`BaseModelProvider`:**
- Purpose: uniform text/stream/image/health/capabilities contract.
- Examples: `llama_cpp_provider.py:24`, `litellm_provider.py:104`,
  `groq_provider.py:18`.
- Pattern: abstract base class + strategy; `AiModel` selects the implementation.

**`InferenceGate`:**
- Purpose: enforce one active GPU inference operation across all sessions/threads.
- Location: `local_llm.py:26-90`.
- Pattern: class-level `threading.RLock` with `hold()` context manager; used by
  `AiModel` streaming (`local_llm.py:298-311`), `generate_text` (`local_llm.py:333-339`),
  and summarization (`summarizer.py:389`).

**`RetrievalResult` / `EvidenceSnippet`:**
- Purpose: single immutable representation shared by prompt assembly and UI citations.
- Location: `models.py:142-205`.
- Pattern: frozen Pydantic models; `formatted_evidence()` renders `[E1]...` blocks.

**`IngestionService`:**
- Purpose: one transaction-like pipeline for PDF ingestion with per-stage fault isolation.
- Location: `ui/ingestion_service.py:39-334`.
- Pattern: result object (`IngestionResult`) instead of exceptions for expected failures;
  optional dependency injection of retriever/embedding/cache dir.

**`LifecycleService`:**
- Purpose: keep four storage tiers consistent (SQLite, LanceDB, disk, session).
- Location: `ui/lifecycle_service.py:16-166`.
- Pattern: ordered best-effort deletion with warnings; returns `bool` for delete/reindex.

**`DocStore`:**
- Purpose: ACID metadata store with migration-managed schema.
- Location: `doc_store.py:113-652`.
- Pattern: short-lived connection per operation (`_connect` context manager) to coexist
  with Streamlit reruns and Windows file locking; WAL + busy timeout.

**`HybridRetriever`:**
- Purpose: persistent vector + FTS retrieval with RRF.
- Location: `hybrid_retriever.py:88-713`.
- Pattern: adapter over LanceDB with an always-maintained in-memory `VectorIndex` and
  JSON persistence fallback.

**`PromptBudget`:**
- Purpose: keep prompts within the conservative context window and isolate untrusted
  document text.
- Location: `prompt_budget.py`.
- Pattern: character-based token estimate (~4 chars/token), XML tag escaping, greedy
  newest-first history retention.

**`Summarizer`:**
- Purpose: hierarchical profile-driven summarization with cache.
- Location: `summarizer.py:153-422`.
- Pattern: fast-path/map-reduce strategy selected by estimated token count; cache key
  includes model version and `CONFIG_VERSION`.

## Entry Points

**`main.py`:**
- Location: `main.py:1-363`.
- Triggers: `streamlit run main.py` (directly or via `start.py`).
- Responsibilities: page setup, theme, session defaults, storage/hydration, provider
  lifecycle, sidebar, workspace routing.

**`start.py`:**
- Location: `start.py:214-266`.
- Triggers: `python start.py [--start-llama] [--port ...]`.
- Responsibilities: preflight, directory creation, optional llama-server management,
  Streamlit subprocess launch and cleanup.

**`setup.py`:**
- Location: `setup.py:586-660`.
- Triggers: `python setup.py`, `download-models`, `install-llama`, `download_models`,
  `setup_llama_server`; also serves as the packaging script.
- Responsibilities: dependency installation, GGUF/mmproj downloads, llama-server
  download/extraction, directory scaffolding.

**Benchmark scripts:**
- `scripts/benchmark_baseline.py`: extraction/embedding/vector latency baseline.
- `scripts/benchmark_multimodal.py`: factual/visual/table/citation/abstention quality.
- `scripts/profile_resources.py`: ingestion/retrieval/summarization resource profile.
- `scripts/generate_icons.py`: regenerates `assets/icons/*.svg`.

## Architectural Constraints

- **Threading:** Streamlit runs each session's script in its own thread. Inference
  concurrency is deliberately collapsed to one operation via `InferenceGate`
  (`local_llm.py:26-90`). OCR uses a bounded `ThreadPoolExecutor` for page-level work
  (`ocr_fallback.py:9`, `ocr_fallback.py:318`). Telemetry protects caches with locks
  (`resource_telemetry.py:20-30`).
- **Global state:** `InferenceGate` class-level lock/counters (`local_llm.py:34-36`);
  MiniLM model cache (`local_embedding.py:24`); GPU telemetry cache
  (`resource_telemetry.py:25-30`); latency history (`resource_telemetry.py:20-23`);
  SVG icon cache (`ui/components.py:11`); DocStore has no shared connection.
- **Session state:** document catalog, `AiModel`, retriever, embedding model, consent,
  credentials, and chat history are per-session (`main.py:112-132`). Do not promote these
  to module globals; doing so would leak consent/credentials between users.
- **SQLite access:** per-operation connections, WAL, 5 s busy timeout, foreign keys ON
  (`doc_store.py:132-149`). Long-lived connections are avoided by design.
- **Network boundary:** local provider rejects non-loopback hosts unless
  `allow_remote=True` (`llama_cpp_provider.py:60-73`); browser rendering strips external
  links/embeds in local mode (`ui/sanitizer.py:33-78`); cloud calls require consent
  (`litellm_provider.py:142-148`).
- **VRAM ceiling:** local embeddings are CPU-pinned (`local_embedding.py:64-70`), context
  window defaults to 4096 (`llama_cpp_provider.py:31`), and preprocessing avoids GPU.
- **Circular imports:** none observed. Dependency direction is
  `ui/views → local_llm/summarizer/retrieval/persistence`, `ui/services → pipeline`,
  and domain modules import `models`/`prompt_budget` rather than `ui`. Note that
  `summarizer.py` imports `InferenceGate` from `local_llm.py` (`summarizer.py:16`), so
  `local_llm` must not import `summarizer`.
- **Canonical serialization:** SQLite stores `bbox` as `bbox_json`; LanceDB rows are
  dicts derived from `Chunk.model_dump()`; `BBox` is rehydrated on read
  (`hybrid_retriever.py:660-685`, `doc_store.py:300-373`).

## Anti-Patterns

### Calling a provider without `InferenceGate`

**What happens:** A new code path calls `provider.generate_text`/`stream_text` directly.
**Why it's wrong:** Concurrent LLM/VLM calls can exceed the 4 GB VRAM envelope and crash
the local server; the gate is the only enforcement point.
**Do this instead:** Wrap the call in `with InferenceGate.hold(...)` or route through
`AiModel.generate_text` / `ask_a_question_from_pdf_stream`
(`local_llm.py:298-311`, `local_llm.py:333-339`, `summarizer.py:389`).

### Using deprecated retrieval facades

**What happens:** Calling `HybridRetriever.search()` / `get_context()` or
`LocalEmbedding.search_hybrid()`.
**Why it's wrong:** They emit `DeprecationWarning` and lose the canonical
`RetrievalResult` metadata needed for citation ranks and verification.
**Do this instead:** Call `HybridRetriever.search_hybrid()` and pass the resulting
`RetrievalResult` through generation and `validate_response`
(`hybrid_retriever.py:580-693`, `hybrid_retriever.py:695-713`).

### Validating against implicit prior evidence

**What happens:** Calling `validate_response(text)` without `retrieval_result`.
**Why it's wrong:** `AiModel` falls back to `last_retrieval_result`, which may belong to
a previous turn and produce false citation precision.
**Do this instead:** Always pass the `RetrievalResult` used for the current generation
(`local_llm.py:341-359`, `ui/views.py:409`).

### Mutating storage from view code

**What happens:** New UI code writes SQLite/LanceDB or deletes cache directories inline.
**Why it's wrong:** It bypasses atomic multi-tier cleanup, status rollback, and session
synchronization.
**Do this instead:** Use `IngestionService` for writes and `LifecycleService` for
delete/purge/re-index (`ui/ingestion_service.py:39-334`,
`ui/lifecycle_service.py:16-166`).

### Reintroducing unindexed PDF ingestion

**What happens:** Calling `ask_a_question_from_pdf_stream(pdf_path=...)` without a
retriever or `RetrievalResult`.
**Why it's wrong:** The direct path is explicitly removed and raises `ValueError`
(`local_llm.py:240-250`); it would bypass deduplication, indexing, and citations.
**Do this instead:** Ingest via `IngestionService`, then retrieve via
`HybridRetriever.search_hybrid`.

### Silent broad exception handling in new pipeline stages

**What happens:** Wrapping a new stage in `except Exception: pass`.
**Why it's wrong:** Existing stages use broad catches only to isolate optional features
(OCR, visual analysis) and still log warnings (`ui/ingestion_service.py:184-185`,
`ui/ingestion_service.py:207-208`). Silent catches hide data-loss bugs.
**Do this instead:** Log with `logger.warning` and record a stage-specific result/status,
or fail the `IngestionResult` explicitly.

### `print()` inside library modules

**What happens:** Some library code prints to stdout (`doc_store.py:164`,
`upload_validation.py:106`).
**Why it's wrong:** It bypasses structured logging and pollutes Streamlit/server output.
**Do this instead:** Use `logger = logging.getLogger(__name__)` and `logger.info` as the
rest of the codebase does.

## Error Handling

**Strategy:** Validate at boundaries, isolate optional stages, and return structured
status instead of failing the whole request.

**Patterns:**
- **Boundary validation:** `validate_pdf_bytes` raises `ValueError` with user-actionable
  messages (`upload_validation.py:64-113`); Pydantic models reject malformed IDs,
  checksums, coordinates (`models.py:33-235`).
- **Result objects:** `IngestionService` returns `IngestionResult(success=False, error=...)`
  for validation/extraction/persistence/indexing failures
  (`ui/ingestion_service.py:23-36`, `ui/ingestion_service.py:82-91`,
  `ui/ingestion_service.py:256-309`).
- **Status rollback:** If vector indexing fails after SQLite persistence, the document is
  rewritten as `failed` (`ui/ingestion_service.py:283-309`).
- **Fault isolation:** OCR and visual analysis failures do not abort ingestion; they log
  warnings and continue (`ui/ingestion_service.py:173-208`).
- **Health modeling:** providers return `HealthStatus` with `healthy|loading|unreachable|
  error` and actionable setup text (`model_provider.py:44-61`,
  `llama_cpp_provider.py:89-141`).
- **Consent enforcement:** cloud methods raise `PermissionError` before any network call
  (`litellm_provider.py:142-148`).
- **Credential scrubbing:** cloud exceptions redact the active API key
  (`litellm_provider.py:135-140`).
- **UI containment:** streaming exceptions are caught and stored as an interrupted
  assistant turn (`ui/views.py:394-466`).

## Cross-Cutting Concerns

**Logging:** Module-level `logging.getLogger(__name__)` throughout; the Streamlit entry
point installs a targeted filter for the `torch.classes` watcher warning via
`logging_setup.suppress_torch_classes_scan_warning()` (`main.py:26-41`,
`logging_setup.py:16-59`).

**Validation:** Pydantic v2 models enforce ID prefixes (`doc_`, `summ_`), SHA-256 format,
positive page numbers, and bounding-box ordering (`models.py`). Upload validation is
independent of Pydantic and runs before any parsing.

**Authentication/authorization:** No user accounts. "Authorization" is the explicit
cloud-consent gate plus the loopback-only local provider. API keys come from the
environment, `st.secrets`, or session-only input fields; they are never persisted.

**Privacy:** Local mode sanitizes rendered markdown, blocks external images/links, and
avoids network calls; embeddings and raw PDFs never leave the device
(`ui/sanitizer.py`, `main.py:200-244`, `docs/`).

**Telemetry:** VRAM via `nvidia-smi` (5 s cache), RSS via `psutil`, per-stage latency
tracking in `resource_telemetry.py`.

**Observability:** ingestion progress callbacks feed Streamlit status widgets
(`ui/ingestion_service.py:73-76`, `ui/views.py:94-99`); health/capabilities populate the
sidebar status pill (`main.py:254-277`).

---

*Architecture analysis: 2026-10-21*
