<!-- refreshed: 2026-10-17 -->
# Architecture

**Analysis Date:** 2026-10-17

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                    Presentation / UI Layer (`main.py`)                    │
│  Streamlit tabs: Chat & QA · Multi-Profile Summarizer · Telemetry        │
│  `main.py` (915 lines) · launcher `start.py` · packaging `setup.py`       │
└───────────┬──────────────────────┬──────────────────────┬────────────────┘
            │                      │                      │
            ▼                      ▼                      ▼
┌───────────────────────┐ ┌───────────────────┐ ┌─────────────────────────┐
│  Ingestion            │ │  Retrieval        │ │  Inference              │
│  `docling_reader.py`  │ │ `hybrid_retriever`│ │ `local_llm.py` AiModel  │
│  `pdf_reader.py`      │ │ `local_embedding` │ │  + `InferenceGate`      │
│  `ocr_fallback.py`    │ │ `vector_index.py` │ │ `summarizer.py`         │
│  `visual_analyzer.py` │ │                   │ │ `model_provider.py` ABC │
│  `upload_validation`  │ │                   │ │  └─ llama_cpp / litellm │
└───────────┬───────────┘ └─────────┬─────────┘ └────────────┬────────────┘
            │                       │                        │
            ▼                       ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Persistence / Storage Layer                        │
│  SQLite `doc_store.py` (`data/documents.db`)                              │
│  LanceDB dir (`data/lancedb/`, fallback `data/lancedb/fallback_store.json`)│
│  Disk cache (`.cache/<sha256>/docling-1000-200-v1/`)                      │
└─────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Cross-cutting: `models.py` schemas · `prompt_budget.py` ·                │
│  `citation_validator.py` · `resource_telemetry.py` · `upload_validation`  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit UI / lifecycle | Page config, session-state init, sidebar (privacy/consent, provider status, upload, telemetry), chat + summarizer tabs, ingestion & query orchestration | `main.py` |
| One-command launcher | Python version check, directory creation, llama-server probe, Streamlit subprocess launch | `start.py` |
| Packaging & model acquisition | setuptools config, GGUF/embedding/OCR download, console-script entry points | `setup.py` |
| Canonical schemas | Pydantic v2 models: `BBox`, `Chunk`, `Page`, `Document`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult` | `models.py` |
| Provider contract | `BaseModelProvider` ABC, `ProviderCapabilities`, `HealthStatus` | `model_provider.py` |
| Local inference provider | llama-server HTTP/SSE client (Qwen3-VL 2B), loopback SSRF guard, vision analysis | `llama_cpp_provider.py` |
| Cloud inference provider | LiteLLM adapter (Groq/OpenAI/Anthropic), consent gate, vision support detection | `litellm_provider.py` |
| Legacy Groq provider | Direct Groq SDK adapter conforming to `BaseModelProvider` | `groq_provider.py` |
| Inference orchestration | `AiModel` provider detection/fallback, `InferenceGate` single-inference lock, grounded streaming Q&A, response validation | `local_llm.py` |
| Summarization service | 5 profiles, single-pass vs map-reduce, page-reference extraction, SHA cache | `summarizer.py` |
| Citation validation | `[En]` citation precision gate (>=95%), abstention + injection detection | `citation_validator.py` |
| Prompt budgeting | Token estimation, context-window allocation, `<document_context>` XML framing defense, history truncation | `prompt_budget.py` |
| Hybrid retrieval | LanceDB dense + FTS/BM25 search, Reciprocal Rank Fusion, disk-backed fallback store | `hybrid_retriever.py` |
| Embedding service | Shared process-level `all-MiniLM-L6-v2` (CPU-pinned), batch L2-normalised embeddings | `local_embedding.py` |
| In-memory vector store | Pure-stdlib cosine/euclidean k-NN, dimension locking, fallback backend | `vector_index.py` |
| Document metadata store | SQLite CRUD + schema migrations for documents/pages/chunks/evidence/summaries | `doc_store.py` |
| Structured extraction | Docling layout + markdown table parsing with graceful `PdfReader` fallback | `docling_reader.py` |
| PDF text extraction | Memory-safe pypdf extraction + langchain chunking, per-page fault isolation | `pdf_reader.py` |
| Conditional OCR | RapidOCR on low-text pages, ThreadPoolExecutor batching, per-page fault isolation | `ocr_fallback.py` |
| Visual analysis | PyMuPDF region detection + 2x crops + VLM description tagged with model provenance | `visual_analyzer.py` |
| Upload validation | `%PDF` magic, size/page caps, streaming SHA-256, `doc_<sha16>` ID derivation | `upload_validation.py` |
| Resource telemetry | nvidia-smi VRAM (TTL-cached), psutil RSS/VMS, stage latency profiling | `resource_telemetry.py` |

## Pattern Overview

**Overall:** Local-first modular monolith with a Streamlit-orchestrated pipeline and an abstract provider strategy for inference.

**Key Characteristics:**
- **Layered/pipeline orchestration** — `main.py` owns ingestion and query loops; domain modules are stateless helpers (except cached/shared singletons).
- **Strategy pattern for inference** — all providers implement `BaseModelProvider` (`model_provider.py:64`); `AiModel._detect_provider` selects local vs cloud (`local_llm.py:167`).
- **Pure-local data plane, optional-cloud control plane** — ingestion, OCR, embeddings, and retrieval never egress; only generation can route to cloud behind an explicit consent gate (`litellm_provider.py:126`).
- **Canonical immutable schemas at every boundary** — `Chunk`/`Page`/`EvidenceElement`/`EvidenceSnippet`/`RetrievalResult`/`SummaryResult` are frozen or validated Pydantic models (`models.py`).
- **Graceful degradation everywhere** — every optional dependency (`docling`, `rapidocr`, `fitz`, `lancedb`, `litellm`, `groq`, `psutil`, `nvidia-smi`) has an explicit fallback path.
- **Fault isolation** — extraction and OCR catch per-page/per-file errors so one bad page never aborts a batch (`pdf_reader.py:98`, `ocr_fallback.py:270`, `main.py:492`).

## Layers

**Presentation Layer:**
- Purpose: File upload, consent/privacy controls, provider status, telemetry display, conversational chat, summary generation.
- Location: `main.py`, `start.py`
- Contains: `st.set_page_config`, `st.session_state` initialization, sidebar blocks, `st.file_uploader`, `st.tabs`, `st.chat_message`/`st.chat_input`/`st.write_stream`, `st.status` wrappers.
- Depends on: all domain modules (ingestion, retrieval, inference, persistence, telemetry).
- Used by: End user via browser at `http://localhost:8501`; launched by `start.py:main` (`start.py:106`).

**Orchestration / Inference Layer:**
- Purpose: Provider abstraction and selection, single-inference concurrency control, grounded prompt assembly, streaming generation, response validation, summarization.
- Location: `model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `local_llm.py`, `summarizer.py`
- Contains: `BaseModelProvider`, `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`, `AiModel`, `InferenceGate`, `Summarizer`.
- Depends on: `prompt_budget.py`, `citation_validator.py`, `models.py`, `hybrid_retriever.py` (type import).
- Used by: `main.py:226` (via `get_session_ai_model`), `main.py:750` (chat stream), `main.py:879` (Summarizer construction).

**Retrieval Layer:**
- Purpose: Semantic embedding and hybrid dense+lexical nearest-neighbour lookup over persisted chunks.
- Location: `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`
- Contains: `HybridRetriever` (+`compute_rrf`), `LocalEmbedding` (+`get_shared_sentence_transformer`), `VectorIndex`.
- Depends on: `models.py` (`BBox`, `Chunk`, `EvidenceSnippet`, `RetrievalResult`), LanceDB/pyarrow (optional), sentence-transformers.
- Used by: `main.py:508-512` (indexing), `main.py:729-732` (query), `local_llm.py:263-271` (fallback retrieval path).

**Ingestion Layer:**
- Purpose: Bytes-in, canonical metadata-tagged chunks/pages/evidence out.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader`, `PdfReader`, `OcrEngine`/`apply_conditional_ocr`, `VisualAnalyzer`, `validate_pdf_bytes`.
- Depends on: `models.py`, pypdf, docling (optional), rapidocr-onnxruntime (optional), PyMuPDF/fitz (optional).
- Used by: `main.py:408` (validate), `main.py:458-488` (extract + OCR + visual), `docling_reader.py:72` (delegates to `PdfReader`).

**Persistence Layer:**
- Purpose: Durable storage of document metadata, pages, chunks, evidence elements, and summaries; durable vector index.
- Location: `doc_store.py` (SQLite), LanceDB directory `data/lancedb/`
- Contains: `DocStore` (schema migrations v1–v3), `HybridRetriever` LanceDB table `chunks`.
- Depends on: stdlib `sqlite3`, `lancedb`/`pyarrow` (optional).
- Used by: `main.py:88` (singleton `doc_store`), `hybrid_retriever.py:115`, `summarizer.py:334,419`.

**Cross-Cutting Layer:**
- Purpose: Shared schemas, prompt safety, response verification, resource observability.
- Location: `models.py`, `prompt_budget.py`, `citation_validator.py`, `resource_telemetry.py`
- Contains: Pydantic models, `assemble_grounded_messages`, `sanitize_xml_boundary`, `validate_citations`, `LatencyTracker`, GPU/process memory probes.
- Used by: all layers (schemas); inference + summarizer (prompt/validation); `main.py:583-608` (telemetry display).

## Data Flow

### Primary Flow — Ingestion (PDF upload → persisted indexed chunks)

1. `st.file_uploader` collects PDFs (`main.py:375-381`); per-file size pre-check via `uploaded_file.size` (`main.py:392-400`).
2. `validate_pdf_bytes(raw_bytes, filename)` checks `%PDF` magic, size cap (50 MB), page cap (500), computes SHA-256 and `doc_id` (`upload_validation.py:64-113`).
3. Dedup check: `doc_store.get_by_sha(...)` + `st.session_state.doc_ids` (`main.py:415-445`); on a restart dedup hit, chunks are rehydrated from SQLite into a fresh `HybridRetriever` (`main.py:431-444`).
4. `DoclingReader(pdf_stream, filename).extract_text(doc_id=..., sha12=...)` yields `paragraphs` (chunk dicts) and `page_records` (`main.py:458-463`); falls back to `PdfReader` internally on missing Docling or conversion error (`docling_reader.py:95-100,288-293`).
5. `apply_conditional_ocr(...)` runs RapidOCR only on pages below the 50-char threshold, optionally batched via `ThreadPoolExecutor(max_workers<=4)` (`ocr_fallback.py:286-385`).
6. `VisualAnalyzer().analyze_visual_elements(...)` detects raster/vector regions, crops 2x PNGs, and calls the active **local** provider's `analyze_image` (`main.py:476-490`, `visual_analyzer.py:192-287`); results persisted via `doc_store.record_evidence_elements`.
7. Chunks embedded via `local_embedding.get_embeddings` and written to `HybridRetriever.index_chunks` (LanceDB `chunks` table + in-memory fallback) (`main.py:504-512`).
8. Chunks persisted to SQLite (`Chunk.model_validate` → `doc_store.record_chunks`) and a `Document` row upserted (`main.py:514-532`).
9. Best-effort disk cache written to `.cache/<sha256>/docling-1000-200-v1/{pages,chunks,manifest}.json` (`main.py:534-545`, path from `models.py:17-30`).

### Secondary Flow — Query (question → streamed grounded answer)

1. User submits via `st.chat_input` (disabled unless index exists and provider healthy) (`main.py:700-703`).
2. Query contextualised with the previous user question (`main.py:714-724`).
3. Retrieval executes **once** via `HybridRetriever.search_hybrid(query, k=5)` producing an immutable `RetrievalResult` (`main.py:729-732`); the same object feeds both the prompt and the UI citation rendering (RETR-04).
4. `AiModel.ask_a_question_from_pdf_stream(...)` receives the pre-computed `retrieval_result`; it calls `formatted_evidence()` (numbered `[E1]` blocks) and `assemble_grounded_messages(...)` for token-budgeted XML-framed messages (`local_llm.py:236-295`, `prompt_budget.py:57-142`).
5. `InferenceGate.acquire(timeout=60)` serializes GPU inference (`local_llm.py:297-310`); `provider.stream_text(...)` yields tokens.
6. `st.write_stream(response_stream)` renders incrementally and returns the full string (`main.py:757`).
7. `ai_model.validate_response(full_response, retrieval_res)` runs `validate_citations` (precision/abstention/injection) (`main.py:766`, `citation_validator.py:115-230`).
8. Turn (with `verification`, `snippets`, `is_cloud`, `model_name`) is appended to `st.session_state.chat_history` bounded to `MAX_CHAT_TURNS = 50` (`main.py:804-814`, `prompt_budget.py:145-166`).

### Tertiary Flow — Summarization

1. Summarizer tab selects a document + one of 5 profiles (`main.py:838-860`).
2. `Summarizer(provider=ai_model.provider, doc_store=doc_store).summarize_document(...)` (`main.py:879-886`).
3. Cache lookup by `sha256 + profile + model_version` (`summarizer.py:333-337`); pages reconstructed from stored chunks if not supplied (`summarizer.py:340-379`).
4. Under `InferenceGate.hold(timeout=120)`: single-pass if estimated tokens <= 2500, else sequential map-reduce (`summarizer.py:388-395`).
5. `extract_page_references` parses `(p. X)` citations clamped to valid pages (`summarizer.py:136-150,397-399`); result saved to SQLite (`summarizer.py:417-420`).

### Provider Selection Flow

1. `get_session_ai_model()` lazily constructs a **session-scoped** `AiModel` (not `@st.cache_resource`) with `load_dotenv()` before construction (`main.py:91-105`).
2. `AiModel._detect_provider` returns the cloud provider if `cloud_mode` is set and a consented `LiteLLMProvider` is cached in session, otherwise probes local `LlamaCppProvider` (`local_llm.py:167-184`).
3. `main.py` rebuilds the cached `LiteLLMProvider` only when provider/model/key changes and calls `ai_model.set_cloud_mode(...)` (`main.py:229-255`).
4. `check_health()` re-probes and can hot-swap providers if the backend becomes reachable after startup (`local_llm.py:186-206`).

**State Management:**
- **Session state** (`st.session_state`, per browser session, survives Streamlit reruns): `doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, `cloud_mode`, `cloud_mode_toggle`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys`, plus dynamic `ai_model`, `active_cloud_provider`, `_cached_cloud_model`, `_cached_cloud_key`, `summary_*` keys — initialized at `main.py:63-78`.
- **Process-level shared state**: `_MODEL_CACHE` for SentenceTransformer (`local_embedding.py:19`), `InferenceGate._lock` class-level `RLock` (`local_llm.py:34`), `_LATENCY_HISTORY`/`_GPU_CACHE` (`resource_telemetry.py:21-30`).
- **Persistent state**: SQLite `data/documents.db` (via `DocStore`), LanceDB directory `data/lancedb/`, JSON fallback `data/lancedb/fallback_store.json`, disk cache `.cache/`.
- **Reset**: "Clear Session" resets session keys and closes providers (`main.py:298-324`); "Purge All Data" calls `doc_store.purge_all()`, `hybrid_retriever.purge_all()`, and deletes `.cache` (`main.py:326-373`).

## Key Abstractions

**`BaseModelProvider` (inference strategy):**
- Purpose: Uniform contract for local and cloud inference (text, streaming, vision, health, capabilities).
- Examples: `llama_cpp_provider.py:20`, `litellm_provider.py:95`, `groq_provider.py:18`.
- Pattern: ABC with `abstractmethod`s (`model_provider.py:64-156`); `AiModel` depends only on the interface, enabling provider injection in tests (`tests/conftest.py:96-165`).

**`RetrievalResult` / `EvidenceSnippet` (single source of truth for evidence):**
- Purpose: Immutable ranked evidence shared identically between prompt assembly and UI citations.
- Examples: produced in `hybrid_retriever.py:606-639`, consumed in `models.py:185-205` (`formatted_evidence`), `main.py:743-745`.
- Pattern: Frozen Pydantic models with `rank`, `dense_rank`, `fts_rank`, `bbox` provenance (`models.py:142-183`).

**Canonical chunk dict (cross-layer data currency):**
- Purpose: Unit of retrieval carrying text + provenance (`content`, `filename`, `page`, `chunk_id`).
- Examples: produced in `docling_reader.py:228-267`, `pdf_reader.py:77-85`, `ocr_fallback.py:245-255`; stored in `vector_index.py:89-90`, LanceDB (`hybrid_retriever.py:321-334`).
- Pattern: Validated into `Chunk` at persistence boundaries (`models.py:54-72`) while remaining dict-shaped for embedding APIs.

**`InferenceGate` (VRAM concurrency primitive):**
- Purpose: Process-level reentrant lock guaranteeing at most one active GPU inference, protecting the 4 GB VRAM envelope.
- Examples: `local_llm.py:26-90`; used by streaming QA (`local_llm.py:297`), `generate_text` (`local_llm.py:332`), and summarization (`summarizer.py:389`).
- Pattern: Class-level `RLock` + `hold()` contextmanager with timeout → `TimeoutError`.

**`HybridRetriever` (retrieval facade with dual backend):**
- Purpose: Persistent LanceDB dense+lexical retrieval with RRF, degrading to a pure-Python `VectorIndex` JSON store.
- Examples: `hybrid_retriever.py:79-649`; fallback file `data/lancedb/fallback_store.json`.
- Pattern: Prefers LanceDB; on import/runtime failure falls back to `VectorIndex` persisted as JSON (`hybrid_retriever.py:112-124,162-187`).

## Entry Points

**Streamlit app (`main.py`):**
- Location: `main.py` (single module, top-to-bottom script execution).
- Triggers: `streamlit run main.py` (README `README.md:194`); `start.py:launch_streamlit` subprocess (`start.py:73-103`); `.devcontainer` post-attach command.
- Responsibilities: `st.set_page_config` first (`main.py:49-54`), session-state init, provider construction/health, sidebar upload loop, chat loop, summarizer tab, telemetry.

**Launcher (`start.py`):**
- Location: `start.py:106-128` (`main()` under `if __name__ == "__main__"`).
- Triggers: `python start.py` CLI; console-script `rag-assistant=start:main` (`setup.py:432-434`).
- Responsibilities: Python >=3.11 check, directory creation (`data/`, `.cache/`, `models/`), llama-server health probe, Streamlit subprocess launch.

**Setup / model acquisition (`setup.py`):**
- Location: `setup.py:452-486` (`__main__` CLI dispatch) + `setup(**setup_kwargs)` (`setup.py:449`).
- Triggers: `python setup.py`, `python setup.py download_models`, console-scripts `rag-setup`, `rag-download-models`.
- Responsibilities: dependency install, GGUF/embedding/OCR acquisition, editable package registration, setuptools packaging.

**No other entry points:** no `__main__.py`, no CLI in domain modules; `local_llm.AiModel` is library-level.

## Architectural Constraints

- **Threading:** Streamlit single-threaded rerun model — the entire `main.py` runs top-to-bottom per interaction; long operations block and are masked with `st.status`. The only worker parallelism is `ThreadPoolExecutor(max_workers=min(4, cpu_count))` in `ocr_fallback.apply_conditional_ocr` (`ocr_fallback.py:356-376`). GPU inference is serialized process-wide by `InferenceGate` (`local_llm.py:26`). `resource_telemetry` uses locks around cached `nvidia-smi` sampling (`resource_telemetry.py:29-30,50-55`).
- **Global state:** `_MODEL_CACHE` shared SentenceTransformer per `(model, device)` (`local_embedding.py:19,22-37`); `InferenceGate._lock`/`_active_threads` class-level (`local_llm.py:34-35`); `_LATENCY_HISTORY`, `_LAST_GPU_INFO`, `_LAST_GPU_SAMPLE_TIME` module-level (`resource_telemetry.py:21-30`); `st.session_state` per session (`main.py:63-78`). `DocStore` is a module-level singleton in `main.py:88`.
- **Circular imports:** None. Dependency direction is one-way with `models.py` as a leaf. `local_llm.py` imports `hybrid_retriever.py` and `local_embedding.py` for type/generic use; `hybrid_retriever.py` imports `vector_index.py`; `docling_reader.py` imports `pdf_reader.py`. `local_embedding.py` does a local (function-level) import of `models.EvidenceSnippet` (`local_embedding.py:113`) to avoid a cycle.
- **Local-only ingestion invariant:** `VisualAnalyzer.analyze_visual_elements` rejects non-local providers for vision analysis (`visual_analyzer.py:232-239`); visual elements are only described by the local VLM.
- **Cloud egress gate:** `LiteLLMProvider._assert_consent` raises `PermissionError` before any `generate_text`/`stream_text`/`analyze_image` (`litellm_provider.py:126-132,195,244,296`).
- **VRAM ceiling / single active model:** quantization, conservative 4096 context (`llama_cpp_provider.py:27`), CPU-pinned embeddings (`local_embedding.py:49,59-60`), and the `InferenceGate` all enforce the 4 GB envelope.
- **Persistence compatibility:** `DocStore` uses per-operation SQLite connections with WAL + `busy_timeout` for Windows/Streamlit compatibility (`doc_store.py:122-139`); schema migrates via `PRAGMA user_version` (`doc_store.py:141-154`).

## Anti-Patterns

### Duplicated cloud provider implementations

**What happens:** Two overlapping cloud adapters exist — `groq_provider.py` (direct Groq SDK) and `litellm_provider.py` (LiteLLM covering Groq/OpenAI/Anthropic). `main.py` uses `LiteLLMProvider` exclusively (`main.py:30,238`), while `AiModel._detect_provider` still falls back to `GroqProvider` when cloud mode is on but no explicit provider was injected (`local_llm.py:177-180`).
**Why it's wrong:** Two code paths for cloud generation diverge in capability/consent behavior (`GroqProvider` has no consent gate and reports `supports_vision=False`; `LiteLLMProvider` enforces consent). Silent Groq fallback could bypass the UI consent dialog.
**Do this instead:** Route all cloud inference through `LiteLLMProvider` and remove the `GroqProvider` fallback in `AiModel._detect_provider` (`local_llm.py:177-180`), or force an explicit consented provider to always be injected.

### Ballooning UI orchestrator module

**What happens:** `main.py` is 915 lines and mixes layout, consent dialog, ingestion loop, embedding/indexing, chat streaming, citation rendering, and summarization UI.
**Why it's wrong:** Hard to test in isolation and easy to introduce ordering bugs (e.g. `st.set_page_config` must remain first, `import io` is inline at `main.py:131`).
**Do this instead:** Extract ingestion orchestration into a dedicated service module and keep `main.py` limited to layout + wiring; follow the existing `save_uploaded_pdf`/`append_chat_turn` helper extraction pattern.

### Dual index holders in session state

**What happens:** Both `st.session_state.local_embedding` and `st.session_state.hybrid_retriever` are maintained, and `main.py` and `local_llm.py` both branch on which one is present (`main.py:729-741`, `local_llm.py:262-278`).
**Why it's wrong:** Two retrieval facades with subtly different result shapes (`search` vs `search_hybrid`) invite divergence in what evidence reaches the prompt vs the UI.
**Do this instead:** Standardize on `HybridRetriever.search_hybrid` returning `RetrievalResult` as the single retrieval entry point; keep `LocalEmbedding`/`VectorIndex` only as the fallback backend inside `HybridRetriever`.

### Legacy compatibility facades

**What happens:** `HybridRetriever.search` / `get_context` / `add_vector` wrap `search_hybrid` for backwards compatibility (`hybrid_retriever.py:367-369,641-649`); `LocalEmbedding` still exposes `build_index`/`search`/`get_context` (`local_embedding.py:83-140`).
**Why it's wrong:** Legacy surfaces drift from the canonical `RetrievalResult` path and risk being used by new code with degraded provenance (no RRF ranks/bbox).
**Do this instead:** New code must call `search_hybrid`; treat `search`/`get_context` facades as deprecated and remove once callers migrate.

## Error Handling

**Strategy:** Fail fast on invalid config/inputs; degrade gracefully on missing optional dependencies; isolate faults at the smallest scope (page/file/element).

**Patterns:**
- **Optional import guard:** `try/except ImportError → None` at module top for `docling`, `rapidocr`, `fitz`, `lancedb`/`pyarrow`, `litellm`, `groq` (`docling_reader.py:22-31`, `ocr_fallback.py:20-28`, `hybrid_retriever.py:19-24`, `litellm_provider.py:18-21`, `groq_provider.py:12-15`).
- **Constructor validation:** `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k<=0` (`vector_index.py:26,50-59,76-81,86-87,121-125`); `DocStore` methods raise `TypeError` on wrong model types (`doc_store.py:163-164,252-253,306-307,359-360,432-433`).
- **Per-page fault isolation:** `PdfReader` catches per-page extraction errors into a `Page(status="failed", error=...)` (`pdf_reader.py:98-109`); OCR isolates per-page failures (`ocr_fallback.py:270-283`).
- **Per-file upload isolation:** `main.py` wraps extraction in try/except, shows `st.error`, and `continue`s (`main.py:492-494`).
- **Provider HTTP error wrapping:** llama.cpp raises `RuntimeError` on HTTP/malformed payloads (`llama_cpp_provider.py:174-177,237-238,289-292`); cloud adapters log + re-raise `RuntimeError` (`litellm_provider.py:220-222,276-278`).
- **Consent enforcement:** `LiteLLMProvider._assert_consent` raises `PermissionError` (`litellm_provider.py:126-132`).
- **Graceful telemetry degradation:** nvidia-smi/psutil failures return `None`/zeros (`resource_telemetry.py:86-91,186-191`).
- **User-facing feedback via Streamlit, developer diagnostics via `logging`/`print`:** `st.error`/`st.warning`/`st.info` in UI (`main.py:409,493,500,545`); `logger` in domain modules (`docling_reader.py:20`, `hybrid_retriever.py:16`, `summarizer.py:21`).

## Cross-Cutting Concerns

**Logging:** Per-module `logging.getLogger(__name__)` in domain modules (`docling_reader.py:20`, `ocr_fallback.py:18`, `hybrid_retriever.py:16`, `visual_analyzer.py:15`, `summarizer.py:21`, `citation_validator.py:14`, `resource_telemetry.py:18`, `litellm_provider.py:16`, `local_llm.py:23`, `main.py:41`). `print()` remains only in `pdf_reader.py:113`, `upload_validation.py:106`, and `doc_store.py:154`. UI surfaces use Streamlit widgets.

**Validation:** Upload validation (`upload_validation.py`), Pydantic model validators (`models.py:47-51,109-113,135-139,164-168,229-234`), DocStore type checks (`doc_store.py`), vector dimension checks (`vector_index.py`), and provider capability checks (`llama_cpp_provider.py:302-306`, `visual_analyzer.py:227-239`).

**Authentication / Privacy:** No user auth (single-user workstation). Cloud API keys resolved with precedence `explicit arg → session_state.cloud_api_keys → st.secrets → os.environ` (`litellm_provider.py:39-79`; `groq_provider.py:37-47`). Keys are session-memory only, never persisted (README `README.md:210`). Cloud routing requires explicit dialog consent (`main.py:120-166`) enforced programmatically by `_assert_consent`.

**Token budgeting:** Centralized in `prompt_budget.assemble_grounded_messages` (context-window allocation, output reserve, oldest-first history truncation) and `estimate_tokens` (~4 chars/token heuristic) (`prompt_budget.py:43-142`); truncation flags surfaced to the UI via `AiModel.last_truncation_warning` (`local_llm.py:127-131`, `main.py:799-802`).

**Prompt-injection defense:** Document/user text wrapped in `<document_context>` and boundary tags escaped via `sanitize_xml_boundary` (`prompt_budget.py:26-40`); output-side detection in `citation_validator.detect_adversarial_injection` (`citation_validator.py:34-83`).

---

*Architecture analysis: 2026-10-17*
