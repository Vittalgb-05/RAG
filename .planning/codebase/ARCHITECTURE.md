<!-- refreshed: 2026-10-28 -->
# Architecture

**Analysis Date:** 2026-10-28

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION — Streamlit script run top-to-bottom on every interaction        │
│  `main.py`  ·  `ui/views.py`  ·  `ui/components.py`  ·  `ui/theme.py`         │
│  `ui/sanitizer.py`  ·  `.streamlit/config.toml`  ·  `assets/icons/*.svg`      │
└──────────────┬────────────────────────────────────────────┬──────────────────┘
               │ calls                                      │ calls
               ▼                                            ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────────┐
│ UI ORCHESTRATION SERVICES        │   │ DOMAIN SERVICES                      │
│ `ui/chat_controller.py`          │   │ `core/local_llm.py`  (AiModel,       │
│ `ui/ingestion_service.py`        │   │                       InferenceGate) │
│ `ui/lifecycle_service.py`        │   │ `core/summarizer.py` (map-reduce)    │
│ `ui/hydration.py`                │   │ `core/citation_validator.py`         │
│ `ui/session_state.py`            │   │ `core/prompt_budget.py`              │
│                                  │   │ `core/query_intent.py`               │
└──────────────┬───────────────────┘   └───────────────┬──────────────────────┘
               │                                       │
               ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ PROCESSING PIPELINE                                                          │
│ `ingestion/upload_validation.py` → `ingestion/docling_reader.py`             │
│   → `ingestion/pdf_reader.py` (fallback) → `ingestion/ocr_fallback.py`       │
│   → `ingestion/visual_analyzer.py` (VLM crops)                               │
│ `retrieval/local_embedding.py` (MiniLM CPU) → `retrieval/hybrid_retriever.py`│
└──────────────┬────────────────────────────────────────────┬──────────────────┘
               │                                            │
               ▼                                            ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────────┐
│ PERSISTENCE                      │   │ INFERENCE PROVIDERS (adapter layer)  │
│ `core/doc_store.py`   SQLite WAL │   │ `providers/model_provider.py` (ABC)  │
│ `retrieval/hybrid_retriever.py`  │   │ `providers/llama_cpp_provider.py`    │
│   LanceDB + fallback JSON mirror │   │ `providers/litellm_provider.py`      │
│ `core/models.py` cache_dir_for() │   │ `providers/groq_provider.py`         │
│ `data/documents.db` `data/lancedb/` `.cache/<sha>/<version>/`                 │
└──────────────────────────────────┘   └──────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Launcher | Pre-flight checks, loopback bind refusal, optional llama-server spawn, Streamlit subprocess | `start.py` |
| Composition root | Page config, theme injection, session defaults, hydration, provider/health setup, workspace routing | `main.py` |
| Workspace views | Render Chat / Summarizer / Library / Settings; own widgets and reruns | `ui/views.py` |
| Chat turn service | Scope resolution, retrieval invocation, citation auto-attribution, verification; no Streamlit imports | `ui/chat_controller.py` |
| Ingestion service | Validate → dedupe → extract → OCR → VLM → SQLite → embeddings → LanceDB, with progress reporting | `ui/ingestion_service.py` |
| Lifecycle service | Atomic delete, purge-all (VACUUM), re-index across SQLite/LanceDB/cache/session | `ui/lifecycle_service.py` |
| Hydration | Rebuild catalog from SQLite, verify vector coverage, repair missing vectors, consume deletion tombstones | `ui/hydration.py` |
| Session reset | Central teardown of chat, retriever, embedding, provider, credentials | `ui/session_state.py` |
| AI facade | Provider routing, query contextualization, prompt assembly, streaming, gate acquisition | `core/local_llm.py` |
| GPU gate | Process-wide reentrant lock serializing all inference | `core/local_llm.py` (`InferenceGate`) |
| Summarizer | 5-profile single-pass / map-reduce summarization with SQLite cache | `core/summarizer.py` |
| Citation validator | `[E#]` precision, abstention, injection detection, auto-attribution | `core/citation_validator.py` |
| Prompt budget | Token accounting, oldest-first history truncation, XML isolation | `core/prompt_budget.py` |
| Query intent | Follow-up contextualization, whole-document detection, page-diverse selection, retrieval resolution | `core/query_intent.py` |
| Canonical schemas | Frozen Pydantic models for documents, pages, chunks, evidence, retrieval, summaries | `core/models.py` |
| SQLite store | Documents/pages/chunks/evidence/summaries/tombstones, migrations, retry-on-busy, VACUUM | `core/doc_store.py` |
| Upload validation | 50 MB / 500 page caps, `%PDF` magic bytes, `doc_<sha16>` identity, scanned pre-flight | `ingestion/upload_validation.py` |
| Docling reader | Layout/reading-order extraction, markdown tables, internal pypdf fallback | `ingestion/docling_reader.py` |
| pypdf reader | Memory-bounded plain-text extraction and 1000/200 chunking | `ingestion/pdf_reader.py` |
| OCR fallback | Conditional RapidOCR on pages with `< 50` chars, CPU-only, page/time caps | `ingestion/ocr_fallback.py` |
| Visual analyzer | PyMuPDF region detection, 2× crops, VLM descriptions tagged with provenance | `ingestion/visual_analyzer.py` |
| Embeddings | CPU-pinned `all-MiniLM-L6-v2`, 384-dim, L2-normalized, process-shared model | `retrieval/local_embedding.py` |
| Hybrid retriever | LanceDB dense + FTS, RRF fusion, durable JSON mirror, BM25 fallback | `retrieval/hybrid_retriever.py` |
| In-memory index | Pure-stdlib cosine/euclidean/dot vector index used by fallback and `LocalEmbedding` | `retrieval/vector_index.py` |
| Provider contract | ABC + `ProviderCapabilities` / `HealthStatus` Pydantic schemas | `providers/model_provider.py` |
| Local provider | llama-server HTTP/SSE client with loopback/SSRF guard | `providers/llama_cpp_provider.py` |
| Cloud provider | LiteLLM adapter with consent gate and credential scrubbing | `providers/litellm_provider.py` |
| Groq provider | Direct Groq SDK adapter with consent gate | `providers/groq_provider.py` |
| Telemetry | `nvidia-smi`/psutil sampling, 5 s cache, latency tracker | `core/resource_telemetry.py` |
| Logging | Idempotent root logger with rotating file handler | `core/logging_setup.py` |
| Redaction | Secret/token scrubbing for UI errors and logs | `core/redaction.py` |
| Model identity | GGUF metadata parsing/verification before server launch | `core/model_identity.py` |

## Pattern Overview

**Overall:** Modular monolith with a layered, ports-and-adapters core, driven by a single Streamlit script that re-executes top-to-bottom on every interaction.

**Key Characteristics:**
- **Script-driven composition root.** `main.py` is not an importable app factory; Streamlit executes it on each rerun. All wiring (store, hydration, model, provider, health snapshot, routing) happens at module scope in a fixed order (`main.py:101-538`).
- **Explicit service layer between views and domain.** `ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py` hold orchestration so views stay mostly declarative. `ui/chat_controller.py:1-7` documents that it deliberately does not import Streamlit.
- **Provider abstraction via ABC.** `BaseModelProvider` (`providers/model_provider.py:64`) declares `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`. `AiModel` (`core/local_llm.py:103`) owns routing and never talks to SDKs directly.
- **Canonical immutable data contracts.** `RetrievalResult` / `EvidenceSnippet` are frozen and shared verbatim between prompt assembly and UI citation rendering (`core/models.py:142-217`), eliminating a second "UI citation" representation.
- **Two-tier persistence with ordered mutation.** LanceDB vectors are mutated before SQLite so a failure leaves the catalog as the source of truth (`ui/lifecycle_service.py:46-67`, `ui/ingestion_service.py:300-327`).
- **Process-wide GPU serialization.** `InferenceGate` is a class-level `threading.RLock` used by chat streaming, non-streaming generation, summarization, and VLM analysis.
- **Fail-closed security boundaries.** No consent → no cloud call; non-loopback → no local provider; retriever unavailable → lifecycle mutations refused (`ui/views.py:147-161`).

## Layers

**Presentation:**
- Purpose: Render the five workspaces, own all Streamlit widgets/reruns, sanitize untrusted markdown.
- Location: `main.py`, `ui/views.py`, `ui/components.py`, `ui/theme.py`, `ui/sanitizer.py`
- Contains: Layout functions named `render_*`, SVG icon loaders, status pills, citation pills, AMOLED CSS string.
- Depends on: UI orchestration services, `core/*`, `providers/*`, `retrieval/*`, `ingestion/upload_validation.py` (constants only).
- Used by: Streamlit runtime only.

**UI Orchestration:**
- Purpose: Coordinate multi-step workflows and translate widget input into domain calls.
- Location: `ui/chat_controller.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py`, `ui/hydration.py`, `ui/session_state.py`
- Contains: `ChatTurnService`, `IngestionService`, `LifecycleService`, `hydrate_startup_state`, `reset_in_memory_session`.
- Depends on: `core/*`, `ingestion/*`, `retrieval/*`.
- Used by: `main.py`, `ui/views.py`.
- Exception: `ui/hydration.py` imports Streamlit directly and reads/writes `st.session_state` (`ui/hydration.py:49-206`); the other services take state as an argument.

**Domain / Core:**
- Purpose: Model-independent business rules — budgeting, grounding, verification, summarization, provider routing, schema validation.
- Location: `core/`
- Contains: Pydantic models, `AiModel`, `InferenceGate`, `Summarizer`, `validate_citations`, `assemble_grounded_messages`, `resolve_retrieval`, telemetry, logging, redaction, GGUF identity.
- Depends on: `retrieval/hybrid_retriever.py` (type + resolution), `providers/*`.
- Used by: UI orchestration, presentation, scripts.

**Ingestion:**
- Purpose: Turn untrusted PDF bytes into validated, chunked, page-attributed text and visual evidence.
- Location: `ingestion/`
- Contains: `validate_pdf_bytes`, `DoclingReader`, `PdfReader`, `apply_conditional_ocr`, `VisualAnalyzer`.
- Depends on: `core/models.py` only (no Streamlit, no retriever). `visual_analyzer.py` lazily imports `core.local_llm.InferenceGate` inside the analysis loop.
- Used by: `ui/ingestion_service.py`.

**Retrieval:**
- Purpose: Embed chunks, persist vectors/FTS, and return ranked `RetrievalResult` objects.
- Location: `retrieval/`
- Contains: `HybridRetriever`, `LocalEmbedding`, `VectorIndex`, `compute_rrf`.
- Depends on: `core/models.py` (`Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `BBox`), LanceDB/PyArrow, sentence-transformers.
- Used by: `ui/ingestion_service.py`, `ui/hydration.py`, `ui/lifecycle_service.py`, `core/local_llm.py`, `core/query_intent.py`.

**Persistence:**
- Purpose: Durable catalog and metadata of record.
- Location: `core/doc_store.py` (SQLite), `data/documents.db`; vector persistence lives in `retrieval/hybrid_retriever.py` (`data/lancedb/`).
- Contains: Schema DDL v1–v5, migrations keyed to `PRAGMA user_version`, `_execute_write` retry wrapper, VACUUM purge.
- Depends on: `core/models.py`.
- Used by: everything that reads documents, chunks, evidence, or summaries.

**Providers (adapters):**
- Purpose: Abstract local/cloud inference behind one contract.
- Location: `providers/`
- Contains: `BaseModelProvider`, `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`.
- Depends on: `httpx`, `litellm`, `groq`, and — leaking — Streamlit for secret lookup (`providers/litellm_provider.py:58-86`, `providers/groq_provider.py:43-49`).
- Used by: `core/local_llm.py`, `core/summarizer.py`, `ingestion/visual_analyzer.py` (via injected provider).

**Dependency direction (intended):**
`presentation → ui orchestration → core/ingestion/retrieval → providers → external SDK/HTTP`

## Data Flow

### Startup & Hydration

1. `start.py:main()` validates Python ≥ 3.11, refuses non-loopback binds unless explicitly allowed (`start.py:59-91`), ensures `data/`, `.cache/`, `models/`, `tools/` exist, optionally spawns llama-server (`start.py:167-247`), then launches `streamlit run main.py` as a subprocess (`start.py:250-280`).
2. `main.py:101` calls `st.set_page_config`, `main.py:109` injects the theme, `main.py:115-135` seeds session defaults.
3. `main.py:143-150` builds the process-wide `DocStore` behind `@st.cache_resource`; failures render an actionable error and `st.stop()` (`main.py:153-165`).
4. `main.py:194-198` calls `hydrate_startup_state` (`ui/hydration.py:83`), which:
   - loads documents from SQLite,
   - consumes deletion tombstones (vectors deleted while no retriever existed),
   - creates a session `HybridRetriever` + `LocalEmbedding` if absent,
   - re-embeds only documents that fail `retriever.has_document(doc.doc_id)` (`ui/hydration.py:149-214`).
5. `main.py:201-222` creates one `AiModel` per session; `main.py:224-261` synchronizes optional cloud provider when consent is present; `main.py:266-298` probes provider health with a 5 s TTL snapshot.

### Ingestion Path (upload → queryable)

1. Sidebar uploader `render_sidebar_documents` (`ui/views.py:414`) → `render_file_upload_button` (`ui/views.py:386`) rotates `uploader_key` and calls `process_uploaded_files` (`ui/views.py:306`).
2. `IngestionService.ingest_pdf` (`ui/ingestion_service.py:54`) runs the pipeline:
   - **Validate** — `validate_pdf_bytes` checks `%PDF` magic, ≤ 50 MB, ≤ 500 pages, computes SHA-256 → `doc_<sha16>` (`ingestion/upload_validation.py:120-176`).
   - **Dedupe/repair** — `doc_store.get_by_sha` then `retriever.has_document`; if chunks exist in SQLite but vectors are missing, re-embed from stored chunks instead of re-parsing (`ui/ingestion_service.py:97-139`).
   - **Extract** — `DoclingReader(...).extract_text()`; on exception falls back to `PdfReader` (`ui/ingestion_service.py:141-173`). Both use `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` and emit `chunk_id = f"{sha12}_p{page}_{index:04d}"` (`ingestion/pdf_reader.py:55-102`, `ingestion/docling_reader.py:339`).
   - **OCR** — `apply_conditional_ocr` OCRs pages with `< 50` chars, bounded to 200 pages / 300 s, with a ≤ 4-worker `ThreadPoolExecutor` and render-pixel guards (`ingestion/ocr_fallback.py:368-482`).
   - **Vision** — `VisualAnalyzer.detect_visual_regions` (PyMuPDF images + vector drawings) then `analyze_visual_elements(..., max_regions=6)`; each VLM call runs inside `InferenceGate.hold(60.0)` and is tagged `source="vlm:<model>"` (`ingestion/visual_analyzer.py:217-320`).
   - **Persist** — `doc_store.record_ingestion(...)` writes document + pages + chunks + evidence in one transaction after deleting stale child rows (`core/doc_store.py:363-510`).
   - **Index** — `retriever.delete_document(doc_id)` (clears stale vectors), `LocalEmbedding.get_embeddings`, `retriever.index_chunks`, then `has_document` verification. Visual evidence is indexed separately; its failure does not discard text chunks (`ui/ingestion_service.py:272-327`).
3. `process_uploaded_files` writes the retriever/embedding back into session state and updates `doc_ids`, `indexed_files`, `document_metadata` (`ui/views.py:343-362`), then reruns.

### Retrieval + Answer Path

1. `render_chat_view` reads the focus filter and prompt (`ui/views.py:489-672`), appends the user turn, and builds `ChatTurnService(ai_model.validate_response)` (`ui/views.py:680-693`).
2. `ChatTurnService.prepare` (`ui/chat_controller.py:80-128`):
   - `contextualize_query` rewrites short follow-ups using prior turns (`core/query_intent.py:77`),
   - detects a document mentioned in the prompt or uses the single-document scope,
   - calls `resolve_retrieval` (`core/query_intent.py:227`), which switches to `fetch_document_chunks` + `select_page_diverse_snippets` for exhaustive "list all…" questions, or returns `search_mode="intent_mismatch"` when no single document is scoped.
3. `HybridRetriever.search_hybrid` (`retrieval/hybrid_retriever.py:959`):
   - dense search with `embedding_fn` → `search_dense` (candidate pool `max(k*4..k*5, 30)`),
   - FTS search → LanceDB native FTS with pure-Python BM25 fallback (`search_fts` → `_bm25_search_fallback`),
   - doc-id filtering applied again in-process as defense in depth,
   - `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k `EvidenceSnippet` ranked 1..k, each carrying page, filename, extraction, char offsets, bbox.
4. `AiModel.ask_a_question_from_pdf_stream` (`core/local_llm.py:247`):
   - uses the supplied `RetrievalResult` (preferred) or resolves internally,
   - `assemble_grounded_messages` builds `[system, ...history, user]`, embeds evidence in `<document_context>` and truncates prompt → context → history oldest-first (`core/prompt_budget.py:75-162`),
   - acquires the gate manually (`core/local_llm.py:329`) because this is a generator, and releases in `finally` so `GeneratorExit` also frees it,
   - delegates to `provider.stream_text` (`providers/llama_cpp_provider.py:231` parses SSE `data:` lines).
5. Streaming tokens render live in `ui/views.py:716-721`; on completion `ChatTurnService.finalize` (`ui/chat_controller.py:130-211`) auto-attributes missing `[E#]` citations, runs `validate_citations`, withholds on injection, and returns a typed `ChatTurnResult` whose `assistant_turn` is appended to history and re-rendered via `st.rerun()`.
6. `RetrievalResult.snippets` saved on the assistant turn are exactly what the citation pills and Sources drawer render (`ui/views.py:739-773`), so displayed evidence cannot drift from prompt evidence.

### Summarization Path

1. `render_summarizer_view` (`ui/views.py:806`) resolves the document + SHA and builds `Summarizer(provider=ai_model.provider, doc_store=doc_store)` (`ui/views.py:872-883`).
2. `Summarizer.summarize_document` (`core/summarizer.py:465`):
   - cache lookup keyed by `(sha256, profile)` with `model_version = f"{model_name}:{CONFIG_VERSION}"` (`core/doc_store.py:715-762`) — a version mismatch is a cache miss,
   - reconstructs page text from chunks when pages are not supplied,
   - merges VLM/table evidence into page text (`core/summarizer.py:185-258`),
   - holds `InferenceGate` for the whole operation (`timeout=120`) and selects single-pass (≤ 2000 tokens) or sequential map-reduce (`core/summarizer.py:411-463`),
   - extracts `(p. X)` references clamped to real page numbers, persists `SummaryResult` to SQLite, and mirrors it into session state keyed `summary_<doc>_<profile>_<model_version>` (`ui/views.py:39-79`).

### Lifecycle Path (delete / purge / re-index)

1. View helpers enforce a retriever preflight (`ui/views.py:147-161`) — mutating SQLite without a vector backend is refused to prevent resurrected vectors.
2. `LifecycleService.delete_document` (`ui/lifecycle_service.py:32`): vector delete first (abort on failure) → SQLite delete (with tombstone if no retriever) → `.cache/<sha>/<version>/` removal → session-state purge including summary keys.
3. `purge_all` (`ui/lifecycle_service.py:104`): vector purge → SQLite `DELETE` + `VACUUM` → cache wipe → session clear; raises `RuntimeError` listing failed tiers.
4. `reindex_document` (`ui/lifecycle_service.py:162`): delete stale vectors → re-embed SQLite chunks → re-index → verify `has_document`.

**State Management:**
- **Process-wide (survives reruns and sessions):** `DocStore` (`@st.cache_resource`, `main.py:143`), `InferenceGate` class lock, `_MODEL_CACHE` for the SentenceTransformer (`retrieval/local_embedding.py:25`), `_ICON_CACHE` (`ui/components.py:11`).
- **Session-scoped (`st.session_state`):** `ai_model`, `hybrid_retriever`, `local_embedding`, `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `chat_history`, cloud consent/keys, active workspace, `uploader_key`, `_startup_hydrated`, health snapshot (`main.py:115-135`).
- **Durable:** SQLite (`data/documents.db`), LanceDB (`data/lancedb/chunks.lance`), fallback mirror (`data/lancedb/fallback_store.json`), disk cache (`.cache/<sha256>/<CONFIG_VERSION>/`).

## Key Abstractions

**`BaseModelProvider` (ports & adapters):**
- Purpose: One contract for text, streaming, vision, health, capabilities.
- Examples: `providers/llama_cpp_provider.py:56`, `providers/litellm_provider.py:105`, `providers/groq_provider.py:19`
- Pattern: Abstract base class + frozen capability/health Pydantic models.

```python
class BaseModelProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str, system_prompt: str | None = None,
                      max_tokens: int = 1024, temperature: float = 0.2) -> str: ...
    @abstractmethod
    def stream_text(self, prompt: str, system_prompt: str | None = None,
                    history: list[dict[str, str]] | None = None,
                    max_tokens: int = 1024, temperature: float = 0.2) -> Generator[str, None, None]: ...
    @abstractmethod
    def analyze_image(self, image_bytes: bytes, prompt: str, max_tokens: int = 512) -> str: ...
    @abstractmethod
    def check_health(self) -> HealthStatus: ...
    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities: ...
```

**`InferenceGate` (VRAM semaphore):**
- Purpose: Guarantee at most one GPU inference operation at a time, including nested/reentrant use.
- Examples: `core/local_llm.py:26-100`, used at `core/local_llm.py:329`, `core/summarizer.py:559`, `ingestion/visual_analyzer.py:290`

```python
with InferenceGate.hold(timeout=60.0):
    description = provider.analyze_image(image_bytes=crop_bytes, prompt=prompt)
```

Streaming uses manual acquire/release because the gate must span the generator lifetime:

```python
acquired = InferenceGate.acquire(timeout=60.0)
if not acquired:
    yield "⚠️ System is busy processing another inference request. Please retry in a moment."
    return
try:
    yield from self.provider.stream_text(...)
finally:
    InferenceGate.release()   # also runs on GeneratorExit
```

**`RetrievalResult` / `EvidenceSnippet` (single evidence contract):**
- Purpose: Immutable ranked evidence carried from retrieval → prompt → verification → UI.
- Examples: `core/models.py:142-217`; produced at `retrieval/hybrid_retriever.py:1041-1072`.
- Pattern: Frozen Pydantic models with `formatted_evidence()` rendering `[E1] (file.pdf, p. 4)` blocks and `source_labels()` for chips.

**`DocStore` transaction boundary:**
- Purpose: All multi-row writes are atomic and retried on `SQLITE_BUSY`.
- Examples: `core/doc_store.py:189-228` (`_execute_write`), `core/doc_store.py:363-510` (`record_ingestion`), `core/doc_store.py:893-909` (purge + VACUUM).

**`HybridRetriever` dual-backend:**
- Purpose: LanceDB primary; durable JSON mirror + in-memory `VectorIndex` for recovery.
- Examples: `retrieval/hybrid_retriever.py:169-225` (init), `:452-586` (write-through mirror), `:641-716` (whole-document read), `:959-1072` (RRF).

**`ChatTurnService` + frozen dataclasses:**
- Purpose: Keep the chat turn pipeline testable without Streamlit.
- Examples: `ui/chat_controller.py:33-71` (`ChatTurnPreparation`, `ChatTurnResult`), `:73-334`.

**`cache_dir_for` / `CONFIG_VERSION`:**
- Purpose: Content-addressed cache path that invalidates when chunking policy changes.
- Examples: `core/models.py:14-30`; used by `ui/lifecycle_service.py:72`.

## Entry Points

**`start.py` launcher:**
- Location: `start.py:283` (`main`), exposed as console script `rag-assistant=start:main` (`setup.py:820-827`).
- Triggers: `python start.py [...]`, `rag-assistant`, Docker `CMD` override, or direct IDE run.
- Responsibilities: Python version gate, loopback bind policy (`--allow-non-loopback` / `RAG_ALLOW_NON_LOOPBACK`), directory creation, llama-server discovery/probe/spawn with GGUF identity verification (`core/model_identity.py:124`), Streamlit subprocess lifecycle.

**`main.py` Streamlit script:**
- Location: `main.py`
- Triggers: `streamlit run main.py` from `start.py:257-267`, Dockerfile `CMD`, or `.streamlit/config.toml` server settings.
- Responsibilities: Composition root. Configures logging, builds `DocStore`, hydrates, constructs `AiModel`, syncs cloud mode, probes health, renders sidebar, routes to a workspace view (`main.py:509-538`).

**`setup.py` CLI:**
- Location: `setup.py:767-801` (`main_cli`, `download_models_cli`, `setup_llama_server_cli`), `setup_kwargs` at `setup.py:804`.
- Triggers: `python setup.py download_models`, `python setup.py setup_llama_server`, `rag-setup`, `rag-download-models`, `rag-setup-llama`.
- Responsibilities: model weight/projector download with checksums, llama-server binary installation, dependency install.

**Operational scripts:**
- `scripts/benchmark_multimodal.py` (`--live` flag), `scripts/benchmark_baseline.py`, `scripts/profile_resources.py` (also verifies `InferenceGate`), `scripts/generate_icons.py`.
- These insert the repo root into `sys.path` and import application modules directly.

**Docker:**
- `Dockerfile` builds a Python 3.11 image and runs Streamlit bound to `0.0.0.0` inside the container.
- `docker-compose.yml` maps only `127.0.0.1:8501` and offers an optional `gpu` profile running `ghcr.io/ggml-org/llama.cpp:server-cuda`.

## Architectural Constraints

- **Threading:** Streamlit runs each session's script on its own thread; there are no background jobs. OCR uses a bounded `ThreadPoolExecutor` (`max_workers = min(4, cpu_count, len(tasks))`, `ingestion/ocr_fallback.py:482`). All GPU-touching work is serialized by a process-wide `RLock`.
- **Global state:** `DocStore` singleton via `@st.cache_resource` (`main.py:143`); `InferenceGate._lock` / `_active_threads` class-level (`core/local_llm.py:34-36`); `_MODEL_CACHE` for the embedding model (`retrieval/local_embedding.py:25`); `_ICON_CACHE` (`ui/components.py:11`). `AiModel` and `HybridRetriever` are session-scoped.
- **Single active model:** The 4 GB VRAM ceiling prohibits concurrent chat + summary + VLM. `InferenceGate` is acquired by chat streaming, `generate_text`, whole map-reduce summarization, and each VLM crop — never by embeddings, OCR, or Docling (CPU-only by design).
- **Gate hold granularity:** `Summarizer.summarize_document` holds the gate for the *entire* map-reduce (`core/summarizer.py:559`), so a long summary blocks chat for up to 120 s per acquire attempt.
- **Streamlit boundary:** Domain and ingestion layers do not import Streamlit, with two documented exceptions: `ui/hydration.py` (by design) and provider secret lookup inside `litellm_provider.py` / `groq_provider.py`.
- **Persistence ordering:** Vector store is mutated before SQLite on delete/purge, and SQLite before vectors on ingest. Both orders are chosen so a partial failure leaves the catalog truthful rather than pointing at missing vectors.
- **Dual-write amplification:** Each ingestion reads/rewrites the entire `fallback_store.json` (`retrieval/hybrid_retriever.py:312-347`), an O(N) I/O per batch accepted for crash-safe recovery.
- **No authentication:** Single-user design. `start.py` refuses non-loopback binds; `.streamlit/config.toml` binds `127.0.0.1`; Compose maps loopback only.
- **No background processing:** Uploads and summaries are synchronous; the UI uses `st.status`/progress callbacks (`ui/views.py:316`, `main.py:168-190`).
- **Context budget is triple-enforced:** `DEFAULT_MAX_OUTPUT_TOKENS = 1536` in `core/prompt_budget.py:17` is reused by `whole_document_char_budget` (`core/query_intent.py:129-144`) and the streaming `max_tokens` (`core/local_llm.py:339`); changing one without the others over-commits the 4096-token window.
- **Chunking policy versioning:** `CONFIG_VERSION = "docling-1000-200-v1"` (`core/models.py:14`) participates in cache paths and summary cache keys, so chunking changes must bump it.

## Anti-Patterns

### God module for views

**What happens:** `ui/views.py` is 1,225 lines and mixes layout, widget state, lifecycle orchestration, error-boundary UI, telemetry rendering, and provider configuration (`ui/views.py:129-1225`).
**Why it's wrong:** Any workspace change risks unrelated regressions; the module cannot be imported without Streamlit; logic there is untestable except through UI smoke tests.
**Do this instead:** Follow the `ui/chat_controller.py` precedent — put decision logic in a Streamlit-free service returning typed dataclasses, and let the view only render and rerun. Next candidates to extract: summarizer flow (`ui/views.py:872-928`) and lifecycle wrappers (`ui/views.py:164-260`).

### Provider layer reaching into Streamlit secrets

**What happens:** `_resolve_api_key_for_model` imports Streamlit inside the provider to read `st.session_state.cloud_api_keys` and `st.secrets` (`providers/litellm_provider.py:58-86`); `GroqProvider.__init__` does the same (`providers/groq_provider.py:43-52`).
**Why it's wrong:** The adapter layer now depends on the presentation framework, making providers unusable/hard to test outside Streamlit and coupling secret resolution to UI state.
**Do this instead:** Resolve keys in the composition root (`main.py:224-244` already builds `LiteLLMProvider(api_key=...)`) and pass an explicit `api_key`. Keep provider constructors framework-free.

### Multiple legacy retrieval branches in the AI facade

**What happens:** `AiModel.ask_a_question_from_pdf_stream` still branches on `get_context`, `search_hybrid`, and arbitrary callables (`core/local_llm.py:289-313`) to support old retriever shapes, plus `HybridRetriever.search`/`get_context` emit `DeprecationWarning` (`retrieval/hybrid_retriever.py:1074-1092`).
**Why it's wrong:** Each branch produces a different evidence shape, and only the `HybridRetriever`/`RetrievalResult` path guarantees the citation ranks the validator and UI assume.
**Do this instead:** Require a `RetrievalResult` or a `HybridRetriever`, as `ui/chat_controller.py:290-319` already does. Delete the compatibility branches once tests no longer exercise them.

### Duplicated configuration constants across layers

**What happens:** `MAX_CHAT_TURNS = 50` is defined in both `main.py:57` and `ui/views.py:36`; `.cache` defaults are re-derived with `Path(__file__).resolve().parent.parent / ".cache"` in three services (`ui/ingestion_service.py:52`, `ui/lifecycle_service.py:30`, `ui/views.py:497`).
**Why it's wrong:** Values can drift silently; the second definition wins in whichever module imported it, producing inconsistent bounding.
**Do this instead:** Define shared constants once (e.g. a `core/config.py` or pass them from `main.py` alongside `cache_dir`), and import rather than redefine.

### Lazy import used to break a dependency cycle

**What happens:** `VisualAnalyzer.analyze_visual_elements` imports `InferenceGate` inside the loop (`ingestion/visual_analyzer.py:288-290`) because `core.local_llm` imports retrieval/ingestion-adjacent modules.
**Why it's wrong:** Hidden runtime dependency; import errors surface only when analysis runs, and the layering (ingestion → core) is invisible to readers.
**Do this instead:** Move `InferenceGate` into a dependency-free module such as `core/inference_gate.py` and import it at module top in both `local_llm.py`, `summarizer.py`, and `visual_analyzer.py`.

### Untyped session-state bag passed into services

**What happens:** `LifecycleService.delete_document` / `purge_all` accept `session_state: Any` and duck-type `.doc_ids`, `.keys()`, `.pop()` (`ui/lifecycle_service.py:32-101`, `:104-160`).
**Why it's wrong:** Any state-shape change breaks lifecycle cleanup at runtime, and static analysis cannot catch missed keys (e.g. forgetting `failed_doc_ids`).
**Do this instead:** Define a small `SessionStatePort` protocol (or a dataclass adapter built in `ui/views.py`) enumerating the fields lifecycle owns, and pass that.

## Error Handling

**Strategy:** Fail closed at security/storage boundaries, degrade gracefully for optional capabilities, and always render an actionable, redacted message instead of a blank Streamlit page.

**Patterns:**
- **Startup boundary:** store/model initialization failures render remediation and call `st.stop()` (`main.py:153-165`, `:211-221`).
- **Provider degradation:** health probe failure yields an `error` `HealthStatus` and a synthetic `unavailable` capability set rather than crashing (`main.py:275-297`); `LlamaCppProvider.check_health` maps 200/503/connection errors to healthy/loading/unreachable (`providers/llama_cpp_provider.py:118-170`).
- **Cloud fallback:** malformed cloud state resets to local mode with a redacted warning (`main.py:253-261`).
- **Transactional retry:** SQLite writes retry `SQLITE_BUSY` with exponential backoff + jitter (`core/doc_store.py:189-228`).
- **Ingestion fault isolation:** each stage (dedupe repair, Docling, OCR, VLM) catches its own failure and either downgrades (`fallback_used`) or records a `failed` document with extracted rows retained (`ui/ingestion_service.py:136-210`, `:300-327`).
- **Lifecycle fail-closed:** vector deletion failure aborts the delete before SQLite is touched (`ui/lifecycle_service.py:49-56`); missing retriever is refused in the UI (`ui/views.py:147-161`).
- **Truncation signaling:** `truncation_meta` flags propagate to the UI notice helper (`core/prompt_budget.py:97-152`, `ui/views.py:129-139`).
- **Redaction:** `redact_text` scrubs API keys/tokens before any error is shown or logged (`core/redaction.py:32`, used at `main.py:86`, `ui/chat_controller.py:223`).
- **Chat error turn:** streaming exceptions become a persisted, redacted assistant turn rather than losing the conversation (`ui/chat_controller.py:213-257`).

## Cross-Cutting Concerns

**Logging:**
- One idempotent root configuration installed before any startup work (`core/logging_setup.py:57`, called at `main.py:50`).
- Rotating file handler under `data/logs/` plus stderr; level from `RAG_LOG_LEVEL`; Streamlit watcher noise filtered by `suppress_torch_classes_scan_warning` (`core/logging_setup.py:146-177`).
- Module-level `logger = logging.getLogger(__name__)`; warnings are used for recoverable degradation, errors for failed persistence.

**Validation:**
- Pydantic v2 frozen models with `extra="forbid"` for every boundary object (`core/models.py`).
- `doc_id` must match `doc_<...>`, SHA-256 must be 64 lowercase hex, `BBox` coordinates must be ordered and non-negative.
- Upload validation rejects non-PDF, oversize, unreadable, and >500-page files before any extraction (`ingestion/upload_validation.py:120-176`).
- GGUF identity verification blocks launching a mismatched model/projector pair (`core/model_identity.py:124`, `start.py:193-202`).

**Authentication / consent:**
- No user authentication (single-user, loopback-only).
- Cloud egress requires an explicit consent dialog (`main.py:306-350`), `user_consented=True` on the provider, and `_assert_consent()` in every cloud generation/vision call (`providers/litellm_provider.py:141-147`, `providers/groq_provider.py:63-69`).
- API keys live only in session state and are cleared by `clear_cloud_credentials` (`ui/views.py:263-289`) and `reset_in_memory_session` (`ui/session_state.py:50-64`).

**Prompt-injection defense:**
- Evidence is wrapped in `<document_context>` and any spoofed tag is escaped (`core/prompt_budget.py:44-58`).
- The system template forbids executing document instructions (`core/prompt_budget.py:27`).
- Output is scanned for known adversarial directives; a hit withholds the answer (`core/citation_validator.py:180-193`, `ui/chat_controller.py:166-173`).

**Browser egress defense:**
- `sanitize_display_markdown` strips scripts/iframes/objects/embeds, blocks `javascript:`/`data:`/`file:` destinations, and neutralizes external links unless cloud mode + consent is active (`ui/sanitizer.py:130-249`, applied at `ui/views.py:603`, `:922`).

**Telemetry:**
- `get_gpu_memory_info` shells out to `nvidia-smi` with a 5 s cache and returns `None` on CPU-only hosts (`core/resource_telemetry.py:33-99`).
- `LatencyTracker` / `track_stage` provide stage timing used by scripts and settings (`core/resource_telemetry.py:194-278`).

---

*Architecture analysis: 2026-10-28*
