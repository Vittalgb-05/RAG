<!-- refreshed: 2026-10-20 -->
# Architecture

**Analysis Date:** 2026-10-20

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Entry & launch layer                                                         │
│  `start.py` (rag-assistant)   `setup.py` (rag-setup / model + llama setup)   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ streamlit run main.py
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Presentation layer — `main.py` + `ui/`                                       │
│  `main.py` page config · session init · hydration · cloud consent · routing  │
│  `ui/views.py` Chat | Summarizer | Library | Settings | sidebar uploader     │
│  `ui/components.py` · `ui/theme.py` · `ui/sanitizer.py` · `ui/hydration.py`  │
└───────────────┬──────────────────────────────────────────┬──────────────────┘
                │ upload bytes                             │ question
                ▼                                          ▼
┌──────────────────────────────────┐      ┌───────────────────────────────────┐
│ Ingestion — `ui/ingestion_service`│     │ Orchestration services            │
│  validate → dedup → Docling      │      │  `local_llm.AiModel`              │
│  → conditional OCR → VisualAnalyzer│    │  `summarizer.Summarizer`          │
│  → SQLite → embeddings → LanceDB │      │  `citation_validator`             │
└──────┬───────────────────┬───────┘      │  `prompt_budget`                  │
       │                   │              └──────────────┬────────────────────┘
       ▼                   ▼                             ▼
┌──────────────────┐  ┌──────────────────┐   ┌────────────────────────────────┐
│ `doc_store.DocStore` │ `hybrid_retriever`│   │ Retrieval facade               │
│ SQLite (WAL)     │  │ LanceDB + BM25   │◄──┤ `HybridRetriever.search_hybrid`│
│ documents/pages/ │  │ + RRF            │   │ `LocalEmbedding` (MiniLM CPU)  │
│ chunks/evidence/ │  │ fallback JSON    │   └──────────────┬─────────────────┘
│ summaries        │  └──────────────────┘                  │ RetrievalResult
└──────────────────┘                                        ▼
                                             ┌────────────────────────────────┐
                                             │ Inference providers            │
                                             │ `BaseModelProvider` contract   │
                                             │  ├─ `LlamaCppProvider` (local) │
                                             │  ├─ `LiteLLMProvider` (cloud)  │
                                             │  └─ `GroqProvider` (legacy)    │
                                             └────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Launcher | Pre-flight Python check, directory bootstrap, optional llama-server spawn, Streamlit subprocess | `start.py` |
| Packaging / installer CLI | Setuptools metadata, console entry points, model + llama-server download commands, dependency install | `setup.py` |
| App shell | `st.set_page_config`, session-state defaults, `DocStore` construction, startup hydration, cloud-consent dialog, workspace routing | `main.py` |
| Sidebar + views | Document uploader/active list, chat, summarizer, document library, settings/diagnostics | `ui/views.py` |
| Ingestion orchestrator | Validate → dedupe → extract → OCR → visual analysis → persist → embed → index → cache | `ui/ingestion_service.py` |
| Startup hydration | Restore document metadata and `HybridRetriever` from SQLite/LanceDB on first session connection | `ui/hydration.py` |
| UI primitives | Brand header, status pills, stat cards, empty states, SVG icon loader, citation chips | `ui/components.py` |
| Theme | AMOLED color tokens + injected CSS, reduced-motion overrides | `ui/theme.py` |
| Rendering sanitizer | Strip `<script>` and block external Markdown/HTML images unless cloud consent is active | `ui/sanitizer.py` |
| Inference facade | Provider selection, local/cloud routing, retrieval→prompt assembly, gate-guarded token stream, citation verification | `local_llm.py` |
| Provider contract | `BaseModelProvider`, `ProviderCapabilities`, `HealthStatus` | `model_provider.py` |
| Local provider | llama-server HTTP/SSE client, loopback-only endpoint guard, vision analysis | `llama_cpp_provider.py` |
| Cloud provider | LiteLLM adapter for Groq/OpenAI/Anthropic with consent assertion + key redaction | `litellm_provider.py` |
| Legacy cloud provider | Direct `groq` SDK adapter used only by `AiModel._detect_provider` cloud fallback | `groq_provider.py` |
| Structured extraction | Docling layout/table extraction with automatic `PdfReader` fallback | `docling_reader.py` |
| pypdf extraction | Page-by-page text extraction + LangChain chunking; fallback extractor | `pdf_reader.py` |
| Conditional OCR | RapidOCR on low-text pages only, thread-pooled, per-page fault isolation | `ocr_fallback.py` |
| Visual understanding | Detect raster/vector regions, crop PNG, call local VLM, emit `EvidenceElement` | `visual_analyzer.py` |
| SQLite store | Schema migrations, documents/pages/chunks/evidence/summaries CRUD, WAL per-operation connections | `doc_store.py` |
| Hybrid retrieval | Dense LanceDB search + BM25 full-text, RRF fusion, doc filter, JSON fallback store | `hybrid_retriever.py` |
| Embeddings | Shared process-cached `all-MiniLM-L6-v2` on CPU; legacy in-memory `VectorIndex` facade | `local_embedding.py` |
| In-memory vector index | Pure-stdlib cosine/euclidean k-NN; used by fallback store and legacy dense path | `vector_index.py` |
| Summarization | 5 profiles, single-pass vs sequential map-reduce, page-reference extraction, SQLite cache | `summarizer.py` |
| Citation verification | `[E#]` extraction, ≥95% precision gate, abstention + injection detection | `citation_validator.py` |
| Prompt budgeting | Token estimation, `<document_context>` framing, prompt/context/history truncation | `prompt_budget.py` |
| Telemetry | `nvidia-smi` VRAM with 5 s cache, process RSS/VMS, stage latency history | `resource_telemetry.py` |
| Upload validation | `%PDF-` magic bytes, 50 MB / 500 page caps, streaming SHA-256, stable `doc_<sha16>` id | `upload_validation.py` |
| Canonical schemas | Pydantic v2 `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `CONFIG_VERSION` | `models.py` |
| Logging helper | Suppress Streamlit's benign `torch.classes` watcher traceback | `logging_setup.py` |

## Pattern Overview

**Overall:** Local-first, layered modular monolith served as a Streamlit script, with an orchestrator-service core and pluggable inference providers.

**Key Characteristics:**
- **Chatbot-first UI, feature workspaces behind it** — Chat is the default workspace; Summarizer, Library, and Settings are peers selected in the sidebar (`main.py:287-308`, `main.py:331-358`).
- **UI-owned orchestration** — retrieval and ingestion are invoked from `ui/views.py`; domain modules stay free of Streamlit except `ui/*` and the thin provider/telemetry seams.
- **Everything persisted is content-addressed** — `doc_<sha16>` IDs and `sha256` drive dedup, chunk IDs, cache paths, and summary cache keys (`upload_validation.py:36-48`, `models.py:17-30`).
- **Hybrid retrieval with a single canonical result object** — `RetrievalResult` is produced once by `HybridRetriever.search_hybrid`, rendered as citations, and passed into generation and validation (`models.py:171-205`).
- **Sequential single-model inference** — `InferenceGate` serializes chat, summarization, and VLM calls to honor the 4 GB VRAM ceiling (`local_llm.py:26-90`).
- **Graceful optional-dependency degradation** — Docling, RapidOCR, PyMuPDF, LanceDB, LiteLLM, and Groq all import guarded and fall back rather than crash (`docling_reader.py:23-32`, `ocr_fallback.py:21-32`, `hybrid_retriever.py:22-28`, `litellm_provider.py:21-26`).

## Layers

**Entry / launch layer:**
- Purpose: Start the app, acquire models, and provide operator CLIs.
- Location: `start.py`, `setup.py`
- Contains: `start.main`, `start.start_llama_server_process`, `start.launch_streamlit`, `setup.run_full_setup`, `setup.download_all_models`, `setup.setup_llama_server`, console-script entry points.
- Depends on: stdlib only (subprocess, urllib, argparse, setuptools).
- Used by: `rag-assistant`, `rag-setup`, `rag-download-models`, `rag-setup-llama` console scripts (`setup.py:710-717`).

**Presentation layer:**
- Purpose: Render the workspace and translate widgets into service calls.
- Location: `main.py`, `ui/`
- Contains: page config, session defaults, routing, view renderers, reusable HTML components, CSS theme, Markdown sanitizer, hydration.
- Depends on: `doc_store`, `local_llm`, `summarizer`, `hybrid_retriever`, `resource_telemetry`, `prompt_budget`, `models`, `upload_validation`, `ui.*`.
- Used by: browser at `http://localhost:8501`.

**Ingestion pipeline:**
- Purpose: Turn untrusted PDF bytes into validated, metadata-tagged, indexed chunks and visual evidence.
- Location: `ui/ingestion_service.py` (orchestrator), `upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`
- Contains: `IngestionService.ingest_pdf`, `ValidatedUpload`, `DoclingReader`, `PdfReader`, `OcrEngine`, `apply_conditional_ocr`, `VisualAnalyzer`.
- Depends on: pypdf, Docling (optional), RapidOCR + PyMuPDF (optional), `DocStore`, `HybridRetriever`, `LocalEmbedding`, `models`.
- Used by: `ui/views.py:72-137` (sidebar uploader only; there is no other ingestion entry).

**Storage layer:**
- Purpose: Durable document metadata, chunks, evidence, summaries, and vectors.
- Location: `doc_store.py`, `data/documents.db`, `hybrid_retriever.py`, `data/lancedb/`
- Contains: `DocStore` CRUD + migrations; LanceDB `chunks` table; JSON fallback store.
- Depends on: sqlite3, lancedb/pyarrow (optional), `models`.
- Used by: ingestion, hydration, retrieval, summarizer, library view, settings counters.

**Retrieval layer:**
- Purpose: Convert a question into ranked, provenance-rich evidence.
- Location: `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`
- Contains: dense search, BM25 fallback/FTS, `compute_rrf`, `search_hybrid`, embedding cache.
- Depends on: LanceDB (optional), sentence-transformers (CPU), `models`, `vector_index`.
- Used by: `ui/views.py:372-390` (chat) and `local_llm.py:263-277` (legacy fallback path).

**Inference / generation layer:**
- Purpose: Grounded answer synthesis and multi-profile summarization.
- Location: `local_llm.py`, `model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `prompt_budget.py`, `citation_validator.py`, `summarizer.py`
- Contains: `AiModel`, `InferenceGate`, provider implementations, prompt assembly, citation verification, `Summarizer`.
- Depends on: httpx, LiteLLM/groq (optional), `models`, `prompt_budget`, `citation_validator`.
- Used by: `ui/views.py` chat and summarizer views.

**Support layer:**
- Purpose: Cross-cutting validation, schemas, telemetry, logging.
- Location: `models.py`, `upload_validation.py`, `resource_telemetry.py`, `logging_setup.py`
- Contains: Pydantic canonical models, upload limits, GPU/RAM/latency telemetry, log filter.
- Depends on: pydantic, psutil, stdlib.
- Used by: every layer.

## Data Flow

### Ingestion — PDF upload to indexed evidence

1. `main.py` constructs `DocStore(APP_DIR / "data" / "documents.db")` and runs hydration (`main.py:136-142`).
2. Sidebar uploader collects `UploadedFile` objects keyed by `uploader_key` (`ui/views.py:62-70`).
3. Per file, the size cap is checked twice, then `IngestionService.ingest_pdf` is called with raw bytes and an optional local VLM provider (`ui/views.py:84-98`).
4. Validation enforces `%PDF-`, size, readability, page count, and computes `sha256` + `doc_id` (`ui/ingestion_service.py:78-90`, `upload_validation.py:64-112`).
5. Dedup short-circuits already-indexed SHA-256 content (`ui/ingestion_service.py:96-108`).
6. `DoclingReader.extract_text` produces page-grouped chunks and `Page` records; any Docling exception or empty result falls back to `PdfReader` (`ui/ingestion_service.py:110-142`, `docling_reader.py:117-215`).
7. `apply_conditional_ocr` runs RapidOCR only on pages under 50 chars, preserves clean digital pages, and isolates page failures (`ui/ingestion_service.py:144-156`, `ocr_fallback.py:318-417`).
8. `VisualAnalyzer` detects image/vector regions and, if the provider is local + vision-capable, analyzes up to 6 regions into `EvidenceElement`s (`ui/ingestion_service.py:158-174`, `visual_analyzer.py:202-309`).
9. Empty documents are persisted as `status="failed"` and returned early (`ui/ingestion_service.py:176-199`).
10. `DocStore` writes the document, evidence elements, pages, and chunks in a guarded block (`ui/ingestion_service.py:201-232`).
11. `LocalEmbedding.get_embeddings` embeds chunk text on CPU; `HybridRetriever.index_chunks` upserts into LanceDB/fallback; visual evidence is indexed as pseudo-chunks (`ui/ingestion_service.py:234-248`, `hybrid_retriever.py:256-400`).
12. Page/chunk/manifest JSON is written under `.cache/<sha256>/<CONFIG_VERSION>/` (`ui/ingestion_service.py:277-288`, `models.py:17-30`).
13. `ui/views.py` binds `local_embedding`/`hybrid_retriever` back into session state, records metadata, then `st.rerun()` (`ui/views.py:100-137`).

### Query — question to streamed, verified answer

1. Chat input or a queued suggestion produces the prompt (`ui/views.py:342-355`).
2. The previous user turn is prepended to form the retrieval query (`ui/views.py:359-368`).
3. `HybridRetriever.search_hybrid(query, k=5, doc_id=...)` runs dense + FTS candidates, applies the optional document filter, and fuses with RRF (`ui/views.py:372-378`, `hybrid_retriever.py:566-679`).
4. The resulting `RetrievalResult.snippets` are converted to `snippets_data`; `source_labels()` supplies human-readable sources (`ui/views.py:378-390`).
5. `AiModel.ask_a_question_from_pdf_stream` receives the pre-computed `retrieval_result`, formats `[E1]…` blocks, and assembles a bounded prompt (`ui/views.py:394-400`, `local_llm.py:237-296`).
6. `assemble_grounded_messages` frames evidence in `<document_context>`, sanitizes tag spoofing, truncates prompt/context/history to the provider context window (`prompt_budget.py:57-142`).
7. `InferenceGate.acquire` serializes GPU access, then `provider.stream_text` yields tokens (`local_llm.py:298-311`); local SSE is parsed in `llama_cpp_provider.py:241-261`, cloud in `litellm_provider.py:273-296`.
8. `st.write_stream` renders and returns the full response (`ui/views.py:401`).
9. `AiModel.validate_response` checks `[E#]` precision, abstention, and injection echo (`ui/views.py:408-416`, `citation_validator.py:115-230`).
10. Citation chips + evidence expander render provenance; assistant turn stores content, sources, verification, snippets, cloud flag, model name (`ui/views.py:418-465`).

### Summarization

1. Summarizer view selects a document + one of five profiles and calls `Summarizer.summarize_document` (`ui/views.py:487-546`).
2. Cache lookup is keyed by `sha256 + profile`, invalidated by `f"{model_name}:{CONFIG_VERSION}"` (`summarizer.py:328-337`, `doc_store.py:477-526`).
3. Pages are reconstructed from stored chunks when not supplied; empty text raises (`summarizer.py:339-384`).
4. Under `FAST_PATH_TOKEN_LIMIT` (2500) one pass runs; otherwise sequential map → optional half consolidation → reduce, all inside `InferenceGate` (`summarizer.py:386-399`, `summarizer.py:233-299`).
5. Page references are regex-extracted and clamped to real pages; the result is persisted to `document_summaries` (`summarizer.py:397-420`).

### Startup hydration

1. `hydrate_startup_state` runs once per session (`_startup_hydrated` flag) (`ui/hydration.py:19-22`).
2. Indexed documents repopulate `doc_ids`, `indexed_files`, `document_metadata` (`ui/hydration.py:24-44`).
3. If `hybrid_retriever` is absent, a `HybridRetriever` is opened; when chunks exist, `LocalEmbedding` is created and its `_embed_one` bound as the query embedding function (`ui/hydration.py:46-58`).

**State Management:**
- `st.session_state` (per browser session): `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, `cloud_mode`, `cloud_mode_toggle`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys`, `uploader_key`, `active_workspace`, `_startup_hydrated`, `_show_consent_dialog`, plus `ai_model`, `selected_chat_doc`, `selected_summary_doc`, `summary_*`, `_queued_prompt` created later (`main.py:109-129`, `ui/views.py:528`).
- Process-global (shared across sessions): `InferenceGate` lock/state (`local_llm.py:34-36`), `_MODEL_CACHE` in `local_embedding.py:24`, GPU/latency caches in `resource_telemetry.py:21-30`, `_ICON_CACHE` in `ui/components.py:11`.
- Disk: SQLite `data/documents.db`; LanceDB `data/lancedb/`; fallback `data/lancedb/fallback_store.json`; cache `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`.

## Key Abstractions

**`BaseModelProvider` + `ProviderCapabilities`:**
- Purpose: Uniform text generation, token streaming, image analysis, health, and capability inspection across local and cloud backends.
- Examples: `model_provider.py:64-156`, `llama_cpp_provider.py:24-315`, `litellm_provider.py:104-359`, `groq_provider.py:18-170`, test double in `tests/conftest.py:103-172`.
- Pattern: Abstract methods raise/return plain types; capabilities are an immutable Pydantic model; `AiModel` selects one provider instance and delegates.

**Canonical Pydantic models:**
- Purpose: Single schema across extraction, storage, retrieval, prompting, and UI.
- Examples: `Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult` (`models.py:33-235`).
- Pattern: `extra="forbid"`, frozen for value objects, `doc_`/`summ_` prefix validators, `model_dump()` at legacy dict boundaries.

**`RetrievalResult` / `EvidenceSnippet`:**
- Purpose: The contract between retrieval, prompt assembly, citation validation, and rendering.
- Examples: `models.py:142-205`, produced in `hybrid_retriever.py:646-679`, consumed in `local_llm.py:237-238` and `citation_validator.py:148`.
- Pattern: `rank` is the 1-based `[E#]` identity; `formatted_evidence()` builds prompt text; `source_labels()` builds UI labels.

**`IngestionService` / `IngestionResult`:**
- Purpose: One method that owns the whole pipeline and returns success/failure metadata instead of raising for per-document errors.
- Examples: `ui/ingestion_service.py:23-300`, consumed at `ui/views.py:93-119`.
- Pattern: Dataclass result, progress callback, ordered stages, rollback document status on index failure.

**`HybridRetriever`:**
- Purpose: Persistent dense + lexical retrieval with a transparent fallback when LanceDB is absent.
- Examples: `hybrid_retriever.py:88-699`, `compute_rrf` at `hybrid_retriever.py:40-85`.
- Pattern: LanceDB table `chunks` mirrored by an in-memory `VectorIndex` + JSON file; every write updates both; reads prefer LanceDB and fall back.

**`InferenceGate`:**
- Purpose: Process-wide reentrant lock guaranteeing one GPU inference at a time.
- Examples: `local_llm.py:26-90`; used by chat (`local_llm.py:298`), summarization (`summarizer.py:389`), and VLM analysis (`visual_analyzer.py:275-281`).
- Pattern: Class-level `RLock` + active-thread counter; `hold()` context manager raises `TimeoutError` on contention; chat path yields a busy message instead.

**Two chunk representations:**
- Purpose: Canonical `Chunk` models internally, plain dicts at legacy/vector boundaries.
- Examples: `pdf_reader.py:95-104` stores `Chunk.model_dump()`; `hybrid_retriever.index_chunks` accepts both (`hybrid_retriever.py:275-282`); `ingestion_service` revalidates dicts into `Chunk` before SQLite (`ui/ingestion_service.py:220-221`).
- Pattern: New code should accept `Chunk | dict`, normalize early, and emit `Chunk` for persistence.

## Entry Points

**`start.py` — recommended operator entry:**
- Location: `start.py:214-266`
- Triggers: `python start.py [--start-llama]`, or console script `rag-assistant` (`setup.py:711-712`).
- Responsibilities: Python ≥3.11 check, directory creation, optional llama-server spawn/health poll, then `python -m streamlit run main.py`.

**`main.py` — Streamlit app entry:**
- Location: `main.py:95-358`
- Triggers: `streamlit run main.py`; devcontainer `postAttachCommand` (`.devcontainer/devcontainer.json`); Docker `CMD` (`Dockerfile:46`).
- Responsibilities: Must be the first Streamlit call (`set_page_config`), session defaults, `DocStore`, hydration, session `AiModel`, cloud provider sync, consent dialog, sidebar, workspace dispatch.
- Note: `main.py` is a top-level script with no `main()` or `if __name__ == "__main__"`; importing it executes the app.

**`setup.py` — setup/packaging entry:**
- Location: `setup.py:638-820`
- Triggers: `python setup.py [setup|download_models|setup_llama_server|--deps-only|--models-only|--llama-only]`, setuptools commands, and console scripts `rag-setup`, `rag-download-models`, `rag-setup-llama` (`setup.py:710-720`).
- Responsibilities: dependency install, GGUF model download with mirrors, llama-server archive acquisition (CUDA/CPU), package registration.

**`scripts/` — operator/benchmark entries:**
- `scripts/benchmark_multimodal.py` — deterministic multimodal evaluation harness.
- `scripts/benchmark_baseline.py` — retrieval baseline timings.
- `scripts/profile_resources.py` — VRAM/RAM/latency profiling and `InferenceGate` verification.
- `scripts/generate_icons.py` — regenerates the committed `assets/icons/*.svg` set.

**Not entry points:** `ui/*` modules are import-only; `tests/*` are pytest-only.

## Architectural Constraints

- **Threading:** Streamlit runs one script thread per session; multiple browser sessions can execute concurrently. All model inference is serialized by `InferenceGate`. OCR uses a bounded `ThreadPoolExecutor` (max 4) for CPU work (`ocr_fallback.py:388-408`). LanceDB and SQLite are accessed synchronously.
- **Global state:** `InferenceGate` class lock/state (`local_llm.py:34-36`), embedding model cache (`local_embedding.py:24`), GPU/telemetry caches and latency history (`resource_telemetry.py:21-30`), icon cache (`ui/components.py:11`). `doc_store` is module-level in `main.py:139` and re-created on every rerun.
- **Circular imports:** None observed. Dependency direction: `main.py` → `ui.views` → {`ui.ingestion_service`, `local_llm`, `summarizer`, `hybrid_retriever`, `doc_store`}; `local_llm` → {`groq_provider`, `llama_cpp_provider`, `hybrid_retriever`, `local_embedding`, `prompt_budget`, `citation_validator`}; `ui.ingestion_service` → {`docling_reader`, `ocr_fallback`, `visual_analyzer`, `hybrid_retriever`, `local_embedding`}. `visual_analyzer` imports `InferenceGate` lazily inside the function (`visual_analyzer.py:275`) to avoid a cycle.
- **VRAM envelope:** Only one LLM/VLM call at a time; embeddings are pinned to CPU (`local_embedding.py:55,64`); context window defaults to 4096 (`llama_cpp_provider.py:31`); summarization is sequential by design (`summarizer.py:236`); visual regions capped (`ui/ingestion_service.py:166-171`).
- **Local-first invariant:** Local provider only accepts loopback/container hostnames unless `allow_remote=True` (`llama_cpp_provider.py:44-73`); `VisualAnalyzer` refuses non-local providers (`visual_analyzer.py:239-251`); cloud calls require explicit `user_consented` (`litellm_provider.py:142-148`) and UI consent (`main.py:197-240`); browser rendering blocks external images unless consented (`ui/sanitizer.py:19-49`).
- **Persistence is additive, never in-place editing:** indexes are keyed by `chunk_id`; re-index upserts; document deletion must remove SQLite rows + LanceDB chunks + session metadata together (`ui/views.py:163-176`, `ui/views.py:643-655`).
- **Optional dependencies:** Docling / RapidOCR / PyMuPDF / LanceDB / LiteLLM / groq are soft dependencies with runtime fallbacks; new optional integrations should follow the guarded-import pattern.
- **No authentication layer:** single-user local app; there is no login/session auth. "Security state" means cloud consent and API keys in session memory.

## Anti-Patterns

### Top-level Streamlit script

**What happens:** `main.py` executes app setup at import time and has no `main()` guard.
**Why it's wrong:** Importing `main` (tests, tooling, any reuse) starts page configuration and touches `st.session_state`; it also makes the file hard to unit test beyond smoke checks.
**Do this instead:** Keep new logic in importable modules (`ui/*`, services) and treat `main.py` as a thin shell. Do not add reusable functions to `main.py` that other modules must import.

### Retrieval can run twice / stale fallback path

**What happens:** `ui/views.py` retrieves and passes `retrieval_result` into `AiModel`, but `AiModel.ask_a_question_from_pdf_stream` still contains a retrieval branch for `local_embedding` and the deprecated `pdf_path` path (`local_llm.py:237-281`).
**Why it's wrong:** Two owners for retrieval invite divergence (different `k`, different doc filters), and the `pdf_path` branch raises whenever no retriever is supplied (`local_llm.py:240-250`).
**Do this instead:** Retrieve once in the caller and pass `RetrievalResult`. New call sites should pass `retrieval_result=` explicitly; do not revive the `pdf_path` flow.

### Duplicate cloud providers

**What happens:** `LiteLLMProvider` is the UI-created cloud provider (`main.py:168-172`), while `AiModel._detect_provider` can construct `GroqProvider` when cloud mode is on without an explicit provider (`local_llm.py:174-181`).
**Why it's wrong:** Two code paths with different models, context windows, key resolution, and vision support; the Groq path bypasses LiteLLM's consent assertion and key scrubbing.
**Do this instead:** Route all cloud inference through `LiteLLMProvider` (which asserts consent), or explicitly deprecate/remove `GroqProvider` and its `_detect_provider` branch.

### Dead/duplicated configuration constants

**What happens:** `MAX_CHAT_TURNS = 50` exists in both `main.py:43` and `ui/views.py:32`; `safe_has_secret` in `main.py:46-53` is unused.
**Why it's wrong:** Two sources of truth drift silently; unused helpers suggest an abandoned security path.
**Do this instead:** Keep the constant in the module that enforces it (`ui/views.py` or `prompt_budget`) and delete unused helpers.

### `LocalEmbedding` owns an unused index

**What happens:** `LocalEmbedding.__init__` always builds a `VectorIndex` (`local_embedding.py:72`), but the app path embeds via `get_embeddings` and indexes directly into `HybridRetriever` (`ui/ingestion_service.py:243-244`). `build_index`/`store` are only used by tests and legacy code.
**Why it's wrong:** Duplicate in-memory storage, memory overhead, and two retrieval semantics (raw distance vs RRF score).
**Do this instead:** Treat `LocalEmbedding` as an embedding provider (`get_embeddings`, `_embed_one`). Use `HybridRetriever` for storage/search; keep the `VectorIndex` facade only behind the documented fallback store.

### Monolithic `setup.py`

**What happens:** Packaging metadata, dependency installation, network downloaders, archive extraction, and an 800-line CLI live in `setup.py`.
**Why it's wrong:** Every packaging/build invocation imports installer code and network helpers; the file is difficult to test in isolation and mixes concerns.
**Do this instead:** Move installer logic to a dedicated module (e.g. `installer/`) and keep `setup.py` to metadata + thin console entry points. Do not add new operational logic to `setup.py`.

### Inconsistent display sanitization

**What happens:** Historical chat content and summary text call `sanitize_display_markdown(..., allow_external=allow_ext)` (`ui/views.py:283, 576`), but the live assistant evidence text calls it without `allow_external` (`ui/views.py:438`).
**Why it's wrong:** Behavior differs between replayed and freshly generated answers; in cloud mode, legitimate external images are blocked only on the fresh render.
**Do this instead:** Pass the same `allow_external` value to every `sanitize_display_markdown` call in a view.

### Broad exception swallowing

**What happens:** Numerous `except Exception: pass` blocks hide failures (e.g. `main.py:63-67`, `main.py:179-184`, `ui/views.py:167-170`, `ui/views.py:645-648`).
**Why it's wrong:** Cleanup failures, retriever deletion failures, and provider close errors become invisible.
**Do this instead:** Log at `warning`/`debug` with the operation and identifier (as `ui/views.py:649` does), and let unexpected errors propagate at service boundaries.

## Error Handling

**Strategy:** Fail fast at validation boundaries; isolate and continue per document/page; return structured failure results to the UI; degrade to fallbacks for optional subsystems.

**Patterns:**
- Upload validation raises `ValueError` with actionable text (`upload_validation.py:79-100`); `IngestionService` converts it into `IngestionResult(success=False, error=...)` (`ui/ingestion_service.py:78-90`).
- Per-document ingestion never aborts the batch; `ui/views.py` collects failures and reports them in the status widget (`ui/views.py:121-134`).
- Page-level isolation in extraction (`pdf_reader.py:116-127`) and OCR (`ocr_fallback.py:302-315`).
- Docling failure or empty output transparently falls back to pypdf and records `fallback_used` (`docling_reader.py:117-123, 205-215, 312-318`).
- LanceDB failure falls back to an in-memory + JSON store (`hybrid_retriever.py:121-133`), and search catches per-call failures (`hybrid_retriever.py:438-463`).
- Missing optional packages surface as provider health states, not crashes (`groq_provider.py:65-79`, `litellm_provider.py:156-173`).
- Cached summary invalidation returns `None` on model/config mismatch (`doc_store.py:506-511`).
- Chat streaming errors are caught and recorded as an assistant turn with an interruption marker (`ui/views.py:453-465`).
- `InferenceGate` timeout yields a user-visible busy message in chat (`local_llm.py:298-301`) and raises in synchronous summarization (`summarizer.py:389`).

## Cross-Cutting Concerns

**Logging:** Module-level `logging.getLogger(__name__)` used across services; developer diagnostics via `logger.info/warning/error`; `print()` remains in low-level modules (`pdf_reader.py:131`, `doc_store.py:154`, `upload_validation.py:106`); user-facing feedback is exclusively Streamlit (`st.error/info/status/toast`). `logging_setup.suppress_torch_classes_scan_warning()` is called before the app renders (`main.py:41`).

**Validation:** Pydantic v2 models validate at every persistent boundary; upload validation enforces file-level constraints; prompt budgeting sanitizes `<document_context>` spoofing; the UI sanitizer removes scripts and external images; citation validation verifies evidence ranks after generation.

**Authentication / authorization:** No user auth. Cloud access is gated by an explicit consent dialog (`main.py:197-240`) plus a provider-level `PermissionError` (`litellm_provider.py:142-148`). API keys resolve in order session input → Streamlit secrets → environment (`litellm_provider.py:44-88`, `groq_provider.py:37-48`) and are redacted from cloud error messages (`litellm_provider.py:135-140`).

**Resource control:** Single-flight inference (`InferenceGate`), CPU-only embeddings, bounded visual regions, bounded OCR workers, 5 s GPU telemetry cache, 50-turn chat history bound (`prompt_budget.bound_chat_history`).

---

*Architecture analysis: 2026-10-20*
