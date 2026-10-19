<!-- refreshed: 2026-10-19 -->
# Architecture

**Analysis Date:** 2026-10-19

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│  Entry / Orchestration Layer                                                  │
│  `start.py` (launcher)   `setup.py` (install + model acquisition)             │
│  `main.py` (Streamlit script — page config, session state, routing)          │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ dispatches to
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  UI Package (`ui/`)                                                           │
│  `ui/views.py` (5 workspaces)  `ui/components.py`  `ui/theme.py`             │
│  `ui/hydration.py`  `ui/sanitizer.py`                                         │
└──────┬───────────────────┬───────────────────┬───────────────────────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌───────────────┐  ┌────────────────┐  ┌──────────────────────────────────────┐
│  Ingestion    │  │  Storage &     │  │  Inference / Generation              │
│  Pipeline     │  │  Retrieval     │  │                                      │
│ `upload_      │  │ `doc_store.py` │  │ `model_provider.py` (ABC)            │
│  validation`  │  │ (SQLite)       │  │  ├─ `llama_cpp_provider.py` (local)  │
│ `docling_     │  │ `hybrid_       │  │  ├─ `groq_provider.py` (cloud)       │
│  reader.py`   │  │  retriever.py` │  │  └─ `litellm_provider.py` (cloud)    │
│ `ocr_         │  │ (LanceDB+RRF)  │  │ `local_llm.py` (AiModel+Gate)        │
│  fallback.py` │  │ `vector_       │  │ `prompt_budget.py` `summarizer.py`   │
│ `visual_      │  │  index.py`     │  │ `citation_validator.py`              │
│  analyzer.py` │  │ `local_        │  │                                      │
│ `pdf_reader.py`│ │  embedding.py` │  │                                      │
└───────┬───────┘  └───────┬────────┘  └──────────────────┬───────────────────┘
        │                  │                              │
        ▼                  ▼                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Canonical Data Contracts — `models.py` (Pydantic v2)                         │
│  Document · Page · Chunk · EvidenceElement · EvidenceSnippet ·                │
│  RetrievalResult · SummaryResult                                              │
└──────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Persistence & Runtime                                                        │
│  `data/documents.db` (SQLite/WAL) · `data/lancedb/` (LanceDB or JSON fallback)│
│  `.cache/<sha256>/<config>/` (extracted pages/chunks manifest)                │
│  `tools/llama-server/` (native llama.cpp binaries) · `models/` (GGUF weights) │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit entry script | Page config, session-state init, `DocStore` construction, hydration call, AI-model wiring, cloud-provider reconciliation, sidebar nav, workspace routing | `main.py` |
| Workspace views | Render the 5 workspaces (Workspace, Ask Documents, Summarizer, Document Library, Settings); own the ingestion loop and the chat/summarize loops | `ui/views.py` |
| UI components | SVG icon loader + cache, brand header, stat cards, status pills, empty states, citation chips | `ui/components.py` |
| Theme | AMOLED design tokens and injected CSS | `ui/theme.py` |
| Hydration | Restore `document_metadata` and `HybridRetriever` from SQLite/LanceDB on first browser connection | `ui/hydration.py` |
| Sanitizer | Neutralize external image URLs and `<script>` in untrusted markdown before browser render | `ui/sanitizer.py` |
| Launcher | Python pre-flight, directory bootstrap, llama-server probe/spawn, Streamlit subprocess launch | `start.py` |
| Packaging / setup | Dependency install, GGUF model download, llama-server binary acquisition, console-scripts | `setup.py` |
| Upload validation | `%PDF` magic bytes, size/page caps (50 MB / 500 pages), streaming SHA-256, stable `doc_id_for` | `upload_validation.py` |
| Docling reader | Structured layout + markdown-table extraction, page grouping, chunk construction; degrades to `PdfReader` | `docling_reader.py` |
| PDF reader | Memory-safe pypdf text extraction + `RecursiveCharacterTextSplitter` fallback with per-page fault isolation | `pdf_reader.py` |
| OCR fallback | Conditional RapidOCR on low-text pages, thread-pool batching, per-page fault isolation | `ocr_fallback.py` |
| Visual analyzer | PyMuPDF region detection, 2× PNG cropping, VLM description via provider, provenance-tagged `EvidenceElement` | `visual_analyzer.py` |
| Doc store | SQLite (WAL) schema v1–v3 migrations for documents, pages, chunks, evidence elements, summaries | `doc_store.py` |
| Hybrid retriever | LanceDB persistent vector table + BM25 FTS + Reciprocal Rank Fusion, disk-JSON fallback | `hybrid_retriever.py` |
| Vector index | Pure-stdlib in-memory cosine/euclidean k-NN store (fallback backend) | `vector_index.py` |
| Local embedding | `sentence-transformers` MiniLM wrapper, CPU-pinned, process-level model cache | `local_embedding.py` |
| Provider interface | `BaseModelProvider` ABC + `ProviderCapabilities` + `HealthStatus` contracts | `model_provider.py` |
| Local provider | llama-server HTTP/SSE client (text, streaming, vision) with loopback SSRF guard | `llama_cpp_provider.py` |
| Groq provider | Direct Groq cloud adapter | `groq_provider.py` |
| LiteLLM provider | Multi-cloud adapter (Groq/OpenAI/Anthropic) with hard consent gate + key scrubbing | `litellm_provider.py` |
| AiModel | Provider detection/routing, `InferenceGate` GPU serialization, streaming Q&A, citation validation facade | `local_llm.py` |
| Prompt budget | Token estimation, context window allocation, `<document_context>` XML framing, oldest-first history truncation | `prompt_budget.py` |
| Summarizer | 5-profile single-pass/map-reduce summarization with SHA-256 caching and page-reference extraction | `summarizer.py` |
| Citation validator | `[E#]` precision gate (≥95%), abstention detection, adversarial-injection detection | `citation_validator.py` |
| Resource telemetry | TTL-cached `nvidia-smi` VRAM, psutil RSS/VMS, stage latency history, snapshots | `resource_telemetry.py` |
| Logging setup | Filters the benign Streamlit `torch.classes` watcher traceback | `logging_setup.py` |
| Canonical models | All Pydantic v2 schemas and `cache_dir_for` cache-path helper | `models.py` |

## Pattern Overview

**Overall:** Modular monolith with a layered, UI-orchestrated pipeline and a Strategy-based provider abstraction.

**Key Characteristics:**
- **UI-orchestrated pipeline.** `main.py` + `ui/views.py` drive both the ingestion loop and the query loop; domain modules are stateless helpers holding no cross-call state except explicit caches.
- **Provider abstraction (Strategy pattern).** `BaseModelProvider` (`model_provider.py:64`) defines `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`. Three concrete strategies exist; `AiModel._detect_provider` (`local_llm.py:168`) selects one.
- **Local-first, consent-gated cloud.** Default provider is `LlamaCppProvider` (loopback HTTP). Cloud routing requires `cloud_mode=True` AND `user_consented=True`; `LiteLLMProvider._assert_consent` (`litellm_provider.py:142`) enforces this at call time.
- **Canonical Pydantic contracts everywhere.** Every boundary (ingestion, storage, retrieval, generation, UI) passes `models.py` schemas, not ad-hoc dicts — except UI code which frequently calls `.model_dump()` at the render edge.
- **Graceful degradation at every optional dependency.** `docling`, `rapidocr`, `pymupdf`, `lancedb`, `pyarrow`, `groq`, `litellm`, `psutil`, `torch` are all guarded by `try/except ImportError → None` and fall back.
- **Generator-based streaming.** `AiModel.ask_a_question_from_pdf_stream` is a generator yielding token strings consumed by `st.write_stream` (`ui/views.py:507`).

## Layers

**Entry / Orchestration (`main.py`, `start.py`, `setup.py`):**
- Purpose: Bootstrapping, environment checks, session lifecycle, top-level routing.
- Location: repo root.
- Contains: Streamlit page config, `st.session_state` initialisation loop (`main.py:110-130`), module-scope `DocStore` (`main.py:140`), hydration call (`main.py:143`), provider/cloud reconciliation (`main.py:160-186`), workspace dispatch (`main.py:320-354`).
- Depends on: `ui/views.py`, `ui/components.py`, `ui/hydration.py`, `ui/theme.py`, `local_llm.py`, `doc_store.py`, `litellm_provider.py`, `logging_setup.py`.
- Used by: end user (browser), `start.py` subprocess.

**UI Package (`ui/`):**
- Purpose: Presentation and per-workspace orchestration.
- Location: `ui/`.
- Contains: `views.py` (5 render functions + `append_chat_turn`), `components.py`, `theme.py`, `hydration.py`, `sanitizer.py`, `__init__.py`.
- Depends on: all domain modules (`docling_reader`, `ocr_fallback`, `visual_analyzer`, `local_embedding`, `hybrid_retriever`, `summarizer`, `prompt_budget`, `resource_telemetry`, `upload_validation`, `models`).
- Used by: `main.py` only.

**Ingestion (`upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`):**
- Purpose: Bytes-in → validated, chunked, provenance-tagged text + visual evidence.
- Location: repo root (flat modules).
- Contains: validation, extraction, layout/table recovery, OCR fallback, VLM figure analysis.
- Depends on: `pypdf`, `docling`, `rapidocr`, `pymupdf`, `langchain-text-splitters`, `models`, `model_provider`.
- Used by: `ui/views.py:154-223` (primary) and `local_llm.py` (only as removed/deprecated path).

**Canonical Models (`models.py`):**
- Purpose: Single source of truth for all persisted/transport schemas.
- Location: `models.py`.
- Contains: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `SummaryProfile`, `CONFIG_VERSION`, `cache_dir_for`.
- Depends on: `pydantic` only.
- Used by: every other layer.

**Storage (`doc_store.py`, `hybrid_retriever.py`, `vector_index.py`):**
- Purpose: Durable document/vector persistence.
- Location: repo root; artefacts under `data/`.
- Contains: SQLite schema migrations (`doc_store.py:17-100`), LanceDB table management + RRF (`hybrid_retriever.py`), stdlib vector math (`vector_index.py`).
- Depends on: `sqlite3`, `lancedb`/`pyarrow` (optional), `models`.
- Used by: `ui/views.py`, `ui/hydration.py`, `summarizer.py`, `local_llm.py`.

**Retrieval / Embedding (`local_embedding.py`, `hybrid_retriever.py`):**
- Purpose: CPU dense embedding + hybrid ranking.
- Contains: `get_shared_sentence_transformer` process cache (`local_embedding.py:27`), `LocalEmbedding._embed_one` (`local_embedding.py:74`), `HybridRetriever.search_hybrid` (`hybrid_retriever.py:534`), `compute_rrf` (`hybrid_retriever.py:40`).
- Depends on: `sentence_transformers`, `models`, `vector_index`.
- Used by: `ui/views.py`, `ui/hydration.py`, `local_llm.py`.

**Inference / Generation (`model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `litellm_provider.py`, `local_llm.py`, `prompt_budget.py`, `summarizer.py`, `citation_validator.py`):**
- Purpose: Provider selection, GPU-safe serialized inference, prompt assembly, summarization, grounding verification.
- Contains: provider ABC + 3 implementations, `AiModel`, `InferenceGate`, `assemble_grounded_messages`, `Summarizer`, `validate_citations`.
- Depends on: optional SDKs (`groq`, `litellm`), `httpx`, `models`, `hybrid_retriever`, `prompt_budget`, `citation_validator`.
- Used by: `ui/views.py`.

**Support (`resource_telemetry.py`, `logging_setup.py`):**
- Purpose: Diagnostics/observability.
- Contains: `get_gpu_memory_info`, `LatencyTracker`/`track_stage`, `TorchClassesScanLogFilter`.
- Used by: `ui/views.py`, `main.py`, `scripts/*`.

## Data Flow

### Primary Flow — Document Ingestion (upload → indexed)

1. `st.file_uploader` returns `UploadedFile[]` in `render_workspace_view` (`ui/views.py:91-97`).
2. Size pre-check against `MAX_FILE_MB`, then `validate_pdf_bytes` (`ui/views.py:106-122`, `upload_validation.py:64`).
3. Dedup: `doc_store.get_by_sha(validated.sha256)` + `st.session_state.doc_ids` (`ui/views.py:125-145`).
4. Extraction: `DoclingReader(pdf_stream).extract_text(doc_id, sha12)` → `get_paragraphs()` + `get_page_records()` (`ui/views.py:154-159`, `docling_reader.py:95`).
5. Conditional OCR: `apply_conditional_ocr(...)` rewrites low-text pages (`ui/views.py:168-175`, `ocr_fallback.py:318`).
6. Visual analysis: `VisualAnalyzer.detect_visual_regions` → `analyze_visual_elements` under the local VLM provider, gated by `InferenceGate` (`ui/views.py:177-218`, `visual_analyzer.py:202`).
7. Persist: `Document` upsert, `record_evidence_elements`, `record_pages_batch` (`ui/views.py:227-249`, `doc_store.py:156/364/245`).
8. Embed + index: `LocalEmbedding.get_embeddings` → `HybridRetriever.index_chunks(paragraphs, embeddings)` (`ui/views.py:253-262`, `hybrid_retriever.py:256`).
9. Chunk persistence: `doc_store.record_chunks([Chunk.model_validate(p) ...])` (`ui/views.py:265-266`).
10. Best-effort disk cache: `pages.json`, `chunks.json`, `manifest.json` under `cache_dir_for(cache_dir, sha256)` (`ui/views.py:268-279`, `models.py:17`).
11. Session-state update + `st.rerun()` (`ui/views.py:281-297`).

### Secondary Flow — Grounded Q&A (question → streamed answer)

1. `st.chat_input` in `render_chat_view` (`ui/views.py:451`).
2. Append user turn; contextualize query with last user message (`ui/views.py:461-474`).
3. Retrieval: `HybridRetriever.search_hybrid(...)` → canonical `RetrievalResult` (`ui/views.py:480-484`, `hybrid_retriever.py:534`).
4. `AiModel.ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_result)` (`ui/views.py:500`, `local_llm.py:217`).
5. Prompt assembly: `assemble_grounded_messages` bounds tokens, wraps evidence in `<document_context>` (`local_llm.py:286`, `prompt_budget.py:57`).
6. `InferenceGate.acquire(timeout=60)` — process-wide single-inference lock (`local_llm.py:298`).
7. `provider.stream_text(...)` yields tokens via SSE/generator (`local_llm.py:304`, `llama_cpp_provider.py:202` / `litellm_provider.py:241`).
8. `st.write_stream(response_stream)` renders incrementally and returns the full string (`ui/views.py:507`).
9. `ai_model.validate_response` → `CitationVerificationResult` precision gate (`ui/views.py:514`, `citation_validator.py:115`).
10. Assistant turn (content, sources, verification, snippets, `is_cloud`, `model_name`) appended and bounded to `MAX_CHAT_TURNS=50` (`ui/views.py:543-553`, `ui/views.py:40-46`).

### Tertiary Flow — Multi-Profile Summarization

1. `render_summarizer_view` selects doc + profile, calls `Summarizer(provider=ai_model.provider, doc_store).summarize_document(...)` (`ui/views.py:631-642`).
2. Cache check: `doc_store.get_summary(sha256, profile, model_version)` (`summarizer.py:333`, `doc_store.py:477`).
3. Pages reconstructed from `doc_store.get_chunks_for_doc` when `page_text` is absent (it is not persisted in schema v1) (`summarizer.py:340-379`).
4. Under `InferenceGate.hold(timeout=120)`, choose single-pass if ≤ `FAST_PATH_TOKEN_LIMIT=2500` tokens, else sequential map-reduce (`summarizer.py:388-395`).
5. `extract_page_references` parses `(p. X)` citations; `SummaryResult` persisted via `save_summary` (`summarizer.py:397-419`, `doc_store.py:437`).

### Quaternary Flow — Startup Hydration

1. `main.py:143` calls `hydrate_startup_state(doc_store)`.
2. Guarded by `_startup_hydrated`; `doc_store.list_documents()` repopulates `doc_ids`/`indexed_files`/`document_metadata` (`ui/hydration.py:19-44`).
3. If `count_chunks() > 0`, construct `HybridRetriever()`, attach `LocalEmbedding()._embed_one`, store in session (`ui/hydration.py:47-56`).

**State Management:**
- **Per-session (`st.session_state`)**: `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, cloud consent keys (`cloud_mode`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys`), `uploader_key`, `active_workspace`, `ai_model`, `active_cloud_provider`, `_cached_cloud_*`, `_startup_hydrated`, `_show_consent_dialog`, `selected_chat_doc`, `selected_summary_doc`, `summary_*` keys. Initialised in `main.py:110-130`.
- **Per-process (module-level)**: `_MODEL_CACHE` SentenceTransformer (`local_embedding.py:24`), `InferenceGate._lock/_active_threads` (`local_llm.py:34-36`), `_LATENCY_HISTORY`/`_LAST_GPU_INFO` (`resource_telemetry.py:21-30`), `_ICON_CACHE` (`ui/components.py:10`), `doc_store` instance (`main.py:140`).
- Reset path: `_reset_session_security_state` (`main.py:57-89`) clears/`close()`s retriever + cloud provider and bumps `uploader_key`.

## Key Abstractions

**`BaseModelProvider` (Strategy contract):**
- Purpose: Uniform text/stream/vision/health interface across local and cloud backends.
- Examples: `llama_cpp_provider.py:24`, `groq_provider.py:18`, `litellm_provider.py:104`.
- Pattern: ABC with abstract + `close()`/context-manager defaults (`model_provider.py:64-156`). Capabilities advertised via frozen `ProviderCapabilities`.

**`InferenceGate` (process-wide GPU mutex):**
- Purpose: Guarantee at most one active GPU inference (chat, summarize, VLM) within the 4 GB VRAM envelope.
- Examples: `local_llm.py:26-90`; acquired in `local_llm.py:298`, `summarizer.py:389`, `visual_analyzer.py:277`.
- Pattern: Class-level `threading.RLock` + `_active_threads` counter; `.acquire()/.release()/.hold()` context manager raising `TimeoutError` on contention.

**`RetrievalResult` / `EvidenceSnippet` (retrieval contract):**
- Purpose: Immutable, ranked evidence shared identically by prompt assembly and UI citation rendering.
- Examples: built in `hybrid_retriever.py:606-639`; rendered in `ui/views.py:418-442`.
- Pattern: Frozen Pydantic models; `formatted_evidence()` emits `[E1] (file, p. N)` blocks (`models.py:185-194`); `source_labels()` feeds chips.

**Canonical document models:**
- Purpose: Content-addressed identity and typed metadata through all layers.
- Examples: `Document` (doc_id `doc_<sha16>`, sha256 identity), `Chunk` (`content/filename/page/chunk_id/doc_id/extraction/bbox`), `Page` (extraction status), `EvidenceElement` (`source="vlm:<model>"` provenance isolation).
- Pattern: `ConfigDict(frozen=True, extra="forbid")` for immutable value objects; validators enforce `doc_`/`summ_` prefixes and SHA-256 shape (`models.py:116-235`).

**`HybridRetriever` (persistent hybrid search):**
- Purpose: Serverless on-disk vector table + BM25 FTS fused by RRF, with disk-JSON fallback.
- Examples: `index_chunks` (`hybrid_retriever.py:256`), `search_hybrid` (`hybrid_retriever.py:534`), `compute_rrf` (`hybrid_retriever.py:40`).
- Pattern: `has_lancedb` flag toggles LanceDB vs `VectorIndex` fallback; `is_persistent()` reports which is active; `_save_fallback_store` writes `data/lancedb/fallback_store.json`.

**`Summarizer` (map-reduce strategy):**
- Purpose: 5-profile summarization safe for bounded VRAM.
- Examples: `summarize_document` (`summarizer.py:301`), `_summarize_single_pass` (`summarizer.py:205`), `_summarize_map_reduce` (`summarizer.py:233`).
- Pattern: Sequential map batches (`MAX_BATCH_TOKENS=2000`) → optional 2-half consolidation → reduce; every prompt mandates `(p. X)` citations.

**Chunk identity scheme:**
- Purpose: Stable, collision-resistant ids with page provenance.
- Pattern: `f"{sha12}_p{page}_{index:04d}"` in fallback/OCR paths (`docling_reader.py:251`, `ocr_fallback.py:276`) and pypdf path (`pdf_reader.py:94`).

## Entry Points

**`main.py` (Streamlit application script):**
- Location: `main.py`
- Triggers: `streamlit run main.py`; Docker `CMD` (`Dockerfile:46`); `start.py` subprocess (`start.py:181-198`); console-script `rag-assistant=start:main` (`setup.py:712`).
- Responsibilities: `st.set_page_config` first (`main.py:96-101`), theme inject, session init, hydration, provider/consent reconciliation, sidebar, workspace dispatch.

**`start.py` (one-command launcher):**
- Location: `start.py`
- Triggers: `python start.py [--start-llama ...]`; `if __name__ == "__main__"` (`start.py:265`).
- Responsibilities: Python-version check, directory bootstrap, llama-server probe (`check_llama_server`) or spawn (`start_llama_server_process`), then `launch_streamlit`.

**`setup.py` (install + acquisition, dual-mode):**
- Location: `setup.py`
- Triggers: `python setup.py [setup|download_models|setup_llama_server|--deps-only|...]` (`setup.py:733-817`); setuptools commands `download_models` / `setup_llama_server` (`setup.py:718-721`); console-scripts `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:713-715`).
- Responsibilities: dependency install, GGUF download with mirrors/progress, CUDA/CPU llama-server acquisition, editable install, directory bootstrap.

**Benchmark scripts (`scripts/`):**
- `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, `scripts/profile_resources.py`, `scripts/generate_icons.py`. Run directly; write JSON to `.planning/research/` (icons write to `assets/icons/`).

**Test suite (`tests/`):**
- 31 test modules driven by `pytest` config in `pyproject.toml:20-27`; fixtures in `tests/conftest.py` mock Groq, SentenceTransformer, and providers so the suite is offline.

## Architectural Constraints

- **Threading:** Streamlit's single-threaded script model reruns all of `main.py` per interaction. All GPU work is serialized through `InferenceGate` (class-level `RLock`), which is the only cross-thread coordination. OCR batches use a bounded `ThreadPoolExecutor(max_workers=min(4, cpu_count))` (`ocr_fallback.py:388-408`). Telemetry has its own locks (`resource_telemetry.py`).
- **Global state:** `_MODEL_CACHE` (SentenceTransformer), `InferenceGate` class state, `_LATENCY_HISTORY`/GPU cache, `_ICON_CACHE`, and the module-scope `doc_store` at `main.py:140` (re-created each rerun; SQLite migrations are idempotent by `PRAGMA user_version`). `AiModel` is session-scoped, not process-cached.
- **Circular imports:** None statically. `visual_analyzer.py` imports `local_llm.InferenceGate` lazily inside `analyze_visual_elements` (`visual_analyzer.py:275`) to avoid a cycle. Dependency direction is one-way: `main.py → ui/* → {ingestion, storage, generation} → models.py`.
- **In-memory-only `VectorIndex`:** The stdlib fallback index is lost on restart unless serialized to `data/lancedb/fallback_store.json` via `HybridRetriever._save_fallback_store` (`hybrid_retriever.py:169`).
- **Linear-scan fallback retrieval:** `VectorIndex.search` is O(n) over all vectors (`vector_index.py:131-136`); LanceDB provides ANN when available.
- **`Page.page_text` is transient.** SQLite `pages` table (v1 DDL) persists only status/char_count/error/num_chunks (`doc_store.py:30-40`); the summarizer reconstructs page text from stored chunks (`summarizer.py:340-379`).
- **Full-script reruns + uploader key rotation.** Deduplication and `uploader_key` rotation (`ui/views.py:295-297`, `main.py:71`) exist because Streamlit re-executes the script on every widget event.
- **VRAM ceiling drives policy:** CPU-pinned embeddings (`local_embedding.py:64-70`), `do_ocr=False` Docling pipeline with conditional RapidOCR (`docling_reader.py:127-132`), sequential map-reduce, one active provider at a time (`local_llm.py:164`).
- **Privacy invariant:** No egress unless consent; `visual_analyzer` explicitly rejects non-local providers (`visual_analyzer.py:244-251`); UI sanitizer strips external images/scripts (`ui/sanitizer.py`).

## Anti-Patterns

### UI ↔ retriever contract skew (`doc_id` filter)

**What happens:** `ui/views.py:483` calls `active_retriever.search_hybrid(search_query, k=5, doc_id=doc_filter)`, but `HybridRetriever.search_hybrid` (`hybrid_retriever.py:534`) accepts only `(query, k, k_rrf)` and has no `doc_id` parameter. The per-document "Focus Conversation" selector therefore raises `TypeError` whenever a concrete `HybridRetriever` is active.
**Why it's wrong:** The chat workspace advertises document filtering but the retrieval contract silently diverges; tests exercise `search_hybrid` without the extra kwarg (`tests/test_hybrid_retriever.py`), so the gap is not caught.
**Do this instead:** Either add an optional `doc_id` filter to `HybridRetriever.search_hybrid` and apply it to both `search_dense` and `search_fts` before RRF, or drop the argument at the UI call site and filter `RetrievalResult.snippets` after fusion.

### Deprecated facades retained alongside the canonical path

**What happens:** `HybridRetriever.search`/`get_context` (`hybrid_retriever.py:641-659`), `LocalEmbedding.search_hybrid` (`local_embedding.py:113`), and `AiModel.ask_a_question_from_pdf_stream(pdf_path=...)`'s direct-ingestion branch (which now raises, `local_llm.py:240-250`) all emit `DeprecationWarning` but remain callable.
**Why it's wrong:** Two retrieval APIs and three result shapes coexist (`list[(dict,float)]`, `RetrievalResult`, joined string), forcing `local_llm.py:263-281` to carry a 4-branch type-sniffing dispatch.
**Do this instead:** Converge on `HybridRetriever.search_hybrid → RetrievalResult` as the single retrieval entry point and delete the deprecated wrappers once callers migrate.

### Private-attribute coupling across modules

**What happens:** `ui/views.py:258` and `ui/hydration.py:53` pass `st.session_state.local_embedding._embed_one` directly; `HybridRetriever.set_embedding_fn` mutates `self._fallback_store._embedding_fn` (`hybrid_retriever.py:150-154`); `visual_analyzer` calls `LocalEmbedding`-adjacent privates only via the public provider API.
**Why it's wrong:** UI code depends on a private method of the embedding wrapper, so renaming internal helpers breaks the app with no type error.
**Do this instead:** Expose a public `LocalEmbedding.embed_query(text) -> list[float]` and use it at both call sites; have `set_embedding_fn` own the fallback-store wiring through a public method on `VectorIndex`.

### Duplicate cloud adapter paths

**What happens:** `GroqProvider` (`groq_provider.py:18`) and `LiteLLMProvider` (`litellm_provider.py:104`) both provide cloud text generation; `AiModel._detect_provider` uses `GroqProvider` only as an auto-fallback (`local_llm.py:178-181`) while the UI constructs `LiteLLMProvider` (`main.py:169`).
**Why it's wrong:** Two key-resolution implementations (`groq_provider.py:37-47` vs `litellm_provider.py:44-88`), two consent models (Groq has none; LiteLLM has a hard gate), and divergent health semantics.
**Do this instead:** Make `LiteLLMProvider` the single cloud adapter (it already covers Groq via `groq/...` model prefixes) and remove `GroqProvider`, or restrict `GroqProvider` to non-consented diagnostics only.

### Module-scope side effects in the Streamlit entry

**What happens:** `main.py:140` constructs `DocStore(...)` (opening SQLite + running migrations) and `main.py:156` constructs/loads `AiModel` at import time of every rerun; `startup_hydrated` guards only the hydration body.
**Why it's wrong:** Every widget interaction re-opens SQLite and re-probes providers, adding latency and making module import order significant.
**Do this instead:** Cache the `DocStore` and the session `AiModel` behind explicit guarded initializers (the pattern already used for `get_session_ai_model` at `main.py:146-151`).

## Error Handling

**Strategy:** Validate aggressively at boundaries; degrade gracefully at optional dependencies; isolate faults at the page/document granularity; fail fast with actionable messages for configuration errors.

**Patterns:**
- **Optional-import degradation:** `try/except ImportError → None` for `docling` (`docling_reader.py:23-32`), `rapidocr` (`ocr_fallback.py:21-27`), `pymupdf` (`ocr_fallback.py:29-32`, `visual_analyzer.py:18-21`), `lancedb`/`pyarrow` (`hybrid_retriever.py:22-28`), `groq` (`groq_provider.py:12-15`), `litellm` (`litellm_provider.py:21-26`).
- **Per-page fault isolation:** `PdfReader.extract_text` records `Page(status="failed", error=...)` and continues (`pdf_reader.py:116-127`); OCR isolates per page (`ocr_fallback.py:302-315`).
- **Per-document isolation in the UI:** the ingestion loop wraps extraction and `st.error(...)` + `continue` (`ui/views.py:154-223`).
- **Config fail-fast:** `LiteLLMProvider` raises `PermissionError` without consent (`litellm_provider.py:142-148`); missing API key surfaces as `HealthStatus(status="unreachable")` rather than a crash; `upload_validation` raises `ValueError` with user-facing text.
- **Cache/enrichment best-effort:** disk-cache writes catch `OSError` and log (`ui/views.py:278-279`); evidence-recording failures are logged and skipped (`ui/views.py:245-246`).
- **Streaming guard:** chat wraps the stream in `try/except` and appends an interrupted-turn marker (`ui/views.py:554-566`).
- **Gate contention:** `InferenceGate.hold` raises `TimeoutError`; the chat generator yields a busy message instead of crashing (`local_llm.py:298-301`).
- **No retry on general streams:** `llama_cpp_provider.stream_text` raises `RuntimeError` on `httpx` errors (`llama_cpp_provider.py:260-261`); `LiteLLMProvider` uses `num_retries=2` for non-streaming and `0` when streaming (`litellm_provider.py:228,281`).

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` in every domain module; lifecycle/diagnostic prints with `[DocStore]`/`[UploadValidation]`/`[LocalEmbedding]` prefixes; user-facing feedback exclusively via `st.*`. `logging_setup.suppress_torch_classes_scan_warning()` is called at `main.py:42`.

**Validation:** `upload_validation.validate_pdf_bytes` (magic bytes/size/pages/hash) → `models.py` Pydantic validators (prefixes, SHA-256 regex, bbox geometry, frozen/extra-forbid) → `doc_store` `isinstance` type guards.

**Authentication / privacy:** No user auth. Cloud access is governed by session consent (`user_consented`) + `_assert_consent`; API keys resolve in precedence order: explicit arg → `st.session_state.cloud_api_keys` → `st.secrets` → `os.environ` (`litellm_provider.py:44-88`); `_scrub_credentials` redacts keys from error text (`litellm_provider.py:135-140`); `LlamaCppProvider` rejects non-loopback URLs unless `allow_remote=True` (`llama_cpp_provider.py:69-73`).

**Observability:** `resource_telemetry` provides GPU/process/memory and per-stage latency, surfaced in the Settings workspace (`ui/views.py:862-882`); `LatencyTracker`/`track_stage` are available for instrumentation but not wired into the ingestion loop.

**Persistence lifecycle:** `DocStore` owns SQLite (WAL, FK on, `busy_timeout=5000`); `HybridRetriever` owns the vector table; `.cache/<sha256>/<CONFIG_VERSION>/` holds the extracted artefacts. Retention is manual — `delete_document` cascades in SQLite and deletes vector rows (`doc_store.py:587`, `hybrid_retriever.py:374`); `purge_all` clears both plus the fallback file (`ui/views.py:768-779`).

---

*Architecture analysis: 2026-10-19*
