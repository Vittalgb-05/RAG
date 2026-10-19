<!-- refreshed: 2026-10-19 -->
# Architecture

**Analysis Date:** 2026-10-19

## System Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                UI / Entry Layer (Streamlit + launcher)                  │
│   `main.py` (chat, summarizer, telemetry, consent) · `start.py`        │
└──────┬───────────────────────┬────────────────────┬────────────────────┘
       │                       │                    │
       ▼                       ▼                    ▼
┌────────────────┐  ┌──────────────────────┐  ┌──────────────────────────┐
│ Ingestion      │  │ Retrieval            │  │ Generation Orchestration │
│ Pipeline       │  │ Engine               │  │ `local_llm.py` (AiModel) │
│ `docling_reader`│  │ `hybrid_retriever.py`│  │ `summarizer.py`          │
│ `ocr_fallback` │  │ `local_embedding.py` │  │ `citation_validator.py`  │
│ `visual_analyzer`│ │ `vector_index.py`    │  │ `prompt_budget.py`       │
│ `pdf_reader`   │  │ (fallback)           │  │ `InferenceGate`          │
└──────┬─────────┘  └──────────┬───────────┘  └────────────┬─────────────┘
       │                       │                           │
       ▼                       ▼                           ▼
┌────────────────────────────────────────┐  ┌──────────────────────────┐
│  Persistent Storage                     │  │ Provider Abstraction     │
│  `doc_store.py` (SQLite · pages ·       │  │ `model_provider.py` (ABC)│
│   chunks · evidence · summaries)        │  │ ├ llama_cpp_provider.py   │
│  `hybrid_retriever.py` (LanceDB + JSON  │  │ ├ litellm_provider.py     │
│   fallback at data/lancedb/)            │  │ └ groq_provider.py        │
└────────────────────────────────────────┘  └──────────────────────────┘
       ▲                                                        │
       └────────────── canonical models.py (Pydantic v2) ──────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, sidebar (consent gate, provider status, upload loop, telemetry), chat replay, streaming render, summarizer tab, session-state lifecycle | `main.py` |
| Launcher | Pre-flight checks (Python, dirs, llama-server probe/spawn), Streamlit subprocess boot | `start.py` |
| Setup / Packaging | Dependency install, GGUF model + llama-server download, console entry points | `setup.py` |
| AiModel | Provider selection/orchestration, `InferenceGate` serialization, grounded prompt assembly, streaming QA, citation validation entry | `local_llm.py` |
| InferenceGate | Process-level reentrant lock — exactly one GPU inference op at a time (4 GB VRAM safety) | `local_llm.py:26-90` |
| Provider ABC | `BaseModelProvider` contract + `ProviderCapabilities`/`HealthStatus` schemas | `model_provider.py` |
| Local provider | llama-server HTTP client (SSE streaming, vision, loopback SSRF guard) | `llama_cpp_provider.py` |
| Cloud provider | LiteLLM adapter (Groq/OpenAI/Anthropic) with mandatory consent gate + key scrubbing | `litellm_provider.py` |
| Groq provider | Direct Groq SDK adapter (cloud fallback) | `groq_provider.py` |
| Ingestion reader | Docling structured layout + markdown tables, graceful pypdf fallback | `docling_reader.py` |
| PDF fallback reader | pypdf text extraction, chunking, per-page fault isolation | `pdf_reader.py` |
| Conditional OCR | RapidOCR on pages <50 chars, thread-pool batch, page-level isolation | `ocr_fallback.py` |
| Visual analyzer | PyMuPDF region detection, 2x PNG cropping, local-VLM description → `EvidenceElement` | `visual_analyzer.py` |
| Upload validation | PDF magic-byte, size (50 MB), page (500) caps, streaming SHA-256, `doc_id` | `upload_validation.py` |
| DocStore | SQLite metadata/chunk/evidence/summary store, WAL, versioned migrations | `doc_store.py` |
| HybridRetriever | LanceDB dense + FTS/BM25 search, RRF fusion, JSON fallback store | `hybrid_retriever.py` |
| LocalEmbedding | SentenceTransformer (`all-MiniLM-L6-v2`) wrapper, shared process cache, L2-normalised 384-d | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory cosine/Euclidean k-NN fallback | `vector_index.py` |
| Summarizer | Single-pass + hierarchical map-reduce, 5 profiles, page citation extraction, SQLite caching | `summarizer.py` |
| Citation validator | `[En]` citation precision (>=95%) + abstention + injection detection | `citation_validator.py` |
| Prompt budget | Token budgeting, `<document_context>` XML isolation + boundary sanitisation, history truncation | `prompt_budget.py` |
| Models | Canonical Pydantic v2 schemas (`Document`, `Page`, `Chunk`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `BBox`) | `models.py` |
| Resource telemetry | GPU VRAM (nvidia-smi, TTL cache), process RSS/VMS, stage latency tracking | `resource_telemetry.py` |
| Logging setup | Targeted filter suppressing Streamlit `torch.classes` watcher traceback | `logging_setup.py` |
| Benchmark harnesses | Multimodal quality, baseline retrieval, resource profiling (output to `.planning/research/`) | `scripts/benchmark_multimodal.py`, `scripts/benchmark_baseline.py`, `scripts/profile_resources.py` |

## Pattern Overview

**Overall:** Modular monolith with an abstract provider strategy + Streamlit UI orchestration.

**Key Characteristics:**
- **UI-orchestrated pipeline.** `main.py` owns both loops (ingestion and query); domain modules are stateless helpers or per-session instances held in `st.session_state`.
- **Provider strategy.** All inference flows through `BaseModelProvider` (`model_provider.py`); local llama.cpp and cloud LiteLLM/Groq are interchangeable. `AiModel._detect_provider` (`local_llm.py:168-185`) selects based on `cloud_mode` + health.
- **Local-first privacy invariant.** Ingestion, OCR, embeddings, vector search, and default inference run in-process. Cloud egress requires explicit consent (`LiteLLMProvider._assert_consent`, `litellm_provider.py:142-148`) and is session-scoped.
- **Single-active-inference constraint.** `InferenceGate` (`local_llm.py:26-90`) serializes all GPU work via a class-level `threading.RLock`.
- **Graceful degradation everywhere.** docling→pypdf, LanceDB→JSON/`VectorIndex`, RapidOCR→skip, VLM→placeholder text, nvidia-smi→CPU-only caption.

## Layers

**UI / Entry Layer:**
- Purpose: file upload, index status, conversational QA, streaming render, summarization, telemetry, cloud consent.
- Location: `main.py`, `start.py`
- Contains: `st.set_page_config`, sidebar blocks, `st.file_uploader`, `st.chat_input`/`st.chat_message`/`st.write_stream`, `st.tabs`, `st.status`, consent dialog.
- Depends on: all domain modules below.
- Used by: end user via browser (`http://localhost:8501`), dev container post-attach, Docker CMD.

**Ingestion Layer:**
- Purpose: bytes-in → canonical `Chunk`/`Page`/`EvidenceElement` out.
- Location: `upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`
- Contains: `validate_pdf_bytes`, `DoclingReader.extract_text`, `PdfReader.extract_text`, `apply_conditional_ocr`, `VisualAnalyzer.analyze_visual_elements`.
- Depends on: `pypdf`, `docling`, `rapidocr`, `pymupdf`, `langchain-text-splitters`, `models.py`.
- Used by: `main.py:381-608` upload loop.

**Storage Layer:**
- Purpose: persistent metadata, chunks, evidence, summaries, and vectors.
- Location: `doc_store.py` (SQLite), `hybrid_retriever.py` (LanceDB + JSON fallback)
- Contains: `DocStore` CRUD + migrations, `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid`, `_save_fallback_store`.
- Depends on: `sqlite3`, `lancedb`, `pyarrow`, `models.py`.
- Used by: `main.py` upload loop and query loop, `summarizer.py` cache.

**Retrieval Layer:**
- Purpose: dense + lexical candidate generation and rank fusion.
- Location: `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`
- Contains: `compute_rrf`, `HybridRetriever.search_hybrid`, `LocalEmbedding.get_embeddings/_embed_one`, `VectorIndex.search`.
- Depends on: `sentence-transformers`, stdlib `math`.
- Used by: `main.py:777-781` and `local_llm.py:263-279`.

**Generation / Orchestration Layer:**
- Purpose: grounded answer synthesis and multi-profile summarization with citation validation.
- Location: `local_llm.py`, `summarizer.py`, `citation_validator.py`, `prompt_budget.py`
- Contains: `AiModel`, `Summarizer`, `validate_citations`, `assemble_grounded_messages`, `InferenceGate`.
- Depends on: provider abstraction, retrieval layer, `models.py`.

**Provider Layer:**
- Purpose: concrete inference backends behind one contract.
- Location: `model_provider.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`
- Contains: `BaseModelProvider`, `LlamaCppProvider`, `LiteLLMProvider`, `GroqProvider`.
- Depends on: `httpx`, `litellm`, `groq`, `pydantic`.

**Support Layer:**
- Purpose: cross-cutting telemetry, logging, canonical schemas.
- Location: `resource_telemetry.py`, `logging_setup.py`, `models.py`
- Used by: essentially every layer.

## Data Flow

### Primary Flow A — Ingestion (PDF upload → indexed vectors)

1. `st.file_uploader` returns files; size pre-check vs `MAX_FILE_MB` (`main.py:394-406`).
2. `validate_pdf_bytes(raw_bytes, filename)` — magic bytes, size, page count, SHA-256, `doc_id` (`upload_validation.py:64-113`, called `main.py:414`).
3. Dedup: session `doc_ids` set + `doc_store.get_by_sha(sha256)`; on hit after restart, chunks are restored from `DocStore.get_chunks_for_doc` and re-indexed (`main.py:419-452`).
4. `DoclingReader(...).extract_text(doc_id, sha12)` → `get_paragraphs()`, `get_page_records()`; falls back to `PdfReader` if docling missing/fails (`docling_reader.py:94-314`, called `main.py:466-473`).
5. `apply_conditional_ocr(...)` runs RapidOCR on low-text pages, thread-pool batched (`ocr_fallback.py:310-409`, called `main.py:476-483`).
6. `VisualAnalyzer.analyze_visual_elements(...)` detects/crops figures and describes them with the local VLM provider (`visual_analyzer.py:192-295`, called `main.py:485-527`).
7. Persist: `DocStore.upsert_document` → `record_evidence_elements` → `record_page` loop → `record_chunks` (`main.py:534-577`).
8. Embed: `LocalEmbedding.get_embeddings(texts)` (`local_embedding.py:81-86`) → `HybridRetriever.index_chunks(paragraphs, embeddings)` (`hybrid_retriever.py:256-368`, called `main.py:563-573`).
9. Best-effort disk cache write of `pages.json`/`chunks.json`/`manifest.json` under `.cache/<sha256>/<CONFIG_VERSION>/` (`main.py:579-590`, `models.py:17-30`).
10. Session metadata updated; `st.rerun()` (`main.py:592-608`).

### Primary Flow B — Query (question → streamed grounded answer)

1. `st.chat_input` → prompt; user turn appended via `append_chat_turn` (`main.py:748-758`).
2. Query contextualization: prepend last user message to the search query (`main.py:762-772`).
3. `HybridRetriever.search_hybrid(search_query, k=5)` → `RetrievalResult` (dense + BM25 + RRF) (`main.py:777-781`, `hybrid_retriever.py:534-639`).
4. `AiModel.ask_a_question_from_pdf_stream(...)` (`local_llm.py:217-311`):
   - `retrieval_result.formatted_evidence()` → `[E1]…` numbered blocks (`models.py:185-194`).
   - `assemble_grounded_messages(...)` wraps context in `<document_context>` and budgets tokens (`prompt_budget.py:57-142`).
   - `InferenceGate.acquire()` then `provider.stream_text(...)` yields tokens (`local_llm.py:298-311`).
5. `st.write_stream(response_stream)` renders incrementally (`main.py:805`).
6. `AiModel.validate_response(...)` → `validate_citations` precision/abstention/injection check (`citation_validator.py:115-230`).
7. UI renders citation badge, evidence chips, evidence drawer, egress badge; assistant turn appended (`main.py:807-862`).

### Secondary Flow — Summarization

1. Summarizer tab selects `doc_id` + profile (`main.py:878-931`).
2. `Summarizer.summarize_document(...)` → cache lookup `doc_store.get_summary(sha256, profile, model_version)` (`summarizer.py:301-337`).
3. Pages reconstructed from `doc_store.get_chunks_for_doc` if not supplied (`summarizer.py:339-379`).
4. Under `InferenceGate.hold(120s)`: single-pass if `<=2500` tokens else sequential map-reduce (`summarizer.py:386-395`).
5. `extract_page_references` parses `(p. X)`; `SummaryResult` saved via `doc_store.save_summary` (`summarizer.py:397-422`).

### Secondary Flow — Provider selection & cloud consent

1. Sidebar toggle → consent dialog (`main.py:173-224`); consent state in `st.session_state`.
2. `LiteLLMProvider(model_name, api_key, user_consented=True)` cached per-session (`main.py:282-300`).
3. `ai_model.set_cloud_mode(True, cloud_provider=...)` re-selects provider (`local_llm.py:145-166`).
4. `_resolve_api_key_for_model` precedence: explicit → session_state → `st.secrets` → `os.environ` (`litellm_provider.py:44-88`).

**State Management:**
- `st.session_state` keys (`main.py:115-131`): `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `hybrid_retriever`, `chat_history`, `cloud_mode`, `cloud_mode_toggle`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys`, plus `ai_model`, `active_cloud_provider`, `_cached_cloud_model`, `_cached_cloud_key`, `summary_*`.
- Module-level singletons: `doc_store = DocStore(DOC_STORE_PATH)` (`main.py:141`); `_MODEL_CACHE` (`local_embedding.py:24`); `InferenceGate` class lock (`local_llm.py:34`); `_LATENCY_HISTORY`/`_GPU_CACHE` (`resource_telemetry.py:21-30`).
- `_reset_session_security_state` and `Purge All Data` clear session + persistent stores (`main.py:66-94`, `main.py:355-379`).

## Key Abstractions

**BaseModelProvider:**
- Purpose: uniform contract for text gen, streaming, vision, health, capabilities.
- Examples: `model_provider.py:64-156`; implementations `llama_cpp_provider.py:23`, `litellm_provider.py:104`, `groq_provider.py:18`.
- Pattern: ABC with `contextmanager` support (`__enter__`/`__exit__` close HTTP resources).

**RetrievalResult / EvidenceSnippet:**
- Purpose: immutable, shared evidence container crossing generation ↔ UI (prevents cross-turn contamination).
- Examples: `models.py:142-205`; produced `hybrid_retriever.py:606-639`; consumed `local_llm.py:237-283`, validated `citation_validator.py:115`.
- Pattern: frozen Pydantic models; `formatted_evidence()` and `source_labels()` projection methods.

**Canonical Chunk:**
- Purpose: unit of extraction/indexing carrying provenance (`chunk_id`, `doc_id`, `page`, `char_start/end`, `bbox`, `extraction`).
- Examples: `models.py:54-72`; produced `docling_reader.py:249-288`, `ocr_fallback.py:269-279`, `pdf_reader.py:95-103`.
- Pattern: dict-compatible (`content`, `filename`, `page`, `chunk_id`) plus typed metadata.

**InferenceGate:**
- Purpose: serialize GPU inference to protect the 4 GB VRAM ceiling.
- Examples: `local_llm.py:26-90`; used `local_llm.py:298-311, 333`, `summarizer.py:389`.
- Pattern: class-level `RLock` + context manager `hold()` raising `TimeoutError`.

**DocStore migration runner:**
- Purpose: idempotent schema evolution.
- Examples: `doc_store.py:17-100` (V1 documents/pages/chunks, V2 evidence_elements, V3 document_summaries), applied by `_apply_migrations` via `PRAGMA user_version`.
- Pattern: version-keyed DDL dict + per-operation connection context manager.

## Entry Points

**Streamlit app:**
- Location: `main.py`
- Triggers: `streamlit run main.py` (README.md:193-195), devcontainer `postAttachCommand` (`.devcontainer/devcontainer.json:22`), Docker `CMD` (`Dockerfile:46`).
- Responsibilities: `st.set_page_config` must be first Streamlit call (`main.py:101-106`); session-state init; cached `AiModel`; sidebar upload loop; chat + summarizer tabs.

**Container launcher:**
- Location: `start.py`
- Triggers: `python start.py`; console script `rag-assistant=start:main` (`setup.py:712`).
- Responsibilities: Python version check, directory creation, llama-server probe/optional spawn, Streamlit subprocess (`.devcontainer`/README equivalence). Default flags `--port 8501 --host localhost --llama-host 127.0.0.1 --llama-port 8080 --ngl 28 --ctx 4096` (`start.py:214-266`).

**Setup CLIs:**
- Location: `setup.py`
- Triggers: `python setup.py [setup|download_models|setup_llama_server]`; console scripts `rag-setup=setup:main_cli`, `rag-download-models=setup:download_models_cli`, `rag-setup-llama=setup:setup_llama_server_cli` (`setup.py:710-717`).
- Responsibilities: dependency install, GGUF + llama-server download (`MODEL_REGISTRY` `setup.py:59-78`), setuptools custom commands.

**Helper entry (unused fallback):**
- Location: `local_llm.py:217-250`
- Triggers: `ask_a_question_from_pdf_stream(pdf_path=..., local_embedding=None)`.
- Responsibilities: direct unindexed ingestion path is **deprecated and raises** `ValueError`; callers must supply an indexed retriever or `RetrievalResult`.

## Architectural Constraints

- **Threading:** Streamlit single-script rerun model; long work masked with `st.status`. `InferenceGate` serializes GPU ops. OCR uses a `ThreadPoolExecutor` capped at `min(4, cpu_count, tasks)` (`ocr_fallback.py:382`). Background llama-server is a separate subprocess (`start.py:114-178`).
- **Global state:** `_MODEL_CACHE` (`local_embedding.py:24`), `InferenceGate._lock`/`_active_threads` (`local_llm.py:34-36`), `_LATENCY_HISTORY`/`_GPU_CACHE_LOCK` (`resource_telemetry.py:21-30`), module-level `doc_store` (`main.py:141`), `litellm.telemetry = False` (`litellm_provider.py:19-26`).
- **Circular imports:** None. Direction: `main.py` → {`local_llm`, `summarizer`, `doc_store`, `hybrid_retriever`, providers, ingestion}; `local_llm.py` → {`providers`, `hybrid_retriever`, `local_embedding`, `prompt_budget`, `citation_validator`, `models`}; `summarizer.py` → {`local_llm` (InferenceGate), `prompt_budget`, `models`}; `hybrid_retriever.py` → `vector_index`; `local_embedding.py` → `vector_index`; `docling_reader.py` → `pdf_reader` → `models`.
- **Dependency direction:** `models.py` is a leaf (no project imports). `vector_index.py` is stdlib-only. Provider modules depend only on `model_provider.py`.
- **Persistence paths are anchored to the app dir, not CWD:** `DOC_STORE_PATH = APP_DIR/data/documents.db`, `CACHE_DIR = APP_DIR/.cache` (`main.py:138-141`), `DEFAULT_DB_URI = <repo>/data/lancedb` (`hybrid_retriever.py:36`).
- **Optional-dependency imports are guarded:** `docling`, `rapidocr`, `pymupdf`, `lancedb`, `litellm`, `groq`, `psutil` all use `try/except ImportError` with explicit degradation.

## Anti-Patterns

### Deprecated compatibility facades retained alongside canonical APIs

**What happens:** `HybridRetriever.search()` / `get_context()` (`hybrid_retriever.py:641-659`), `LocalEmbedding.search_hybrid()` (`local_embedding.py:113-140`), and `ask_a_question_from_pdf_stream(pdf_path=...)` (`local_llm.py:237-250`) emit `DeprecationWarning` but remain callable.
**Why it's wrong:** New callers can silently adopt stale dense-only paths; the `pdf_path` branch raises but still duplicates branching logic.
**Do this instead:** Call `search_hybrid()` directly and pass an explicit `retrieval_result` into `AiModel`.

### Defensive re-indexing inside the upload dedup branch

**What happens:** On a dedup hit, `main.py:437-451` reconstructs a `HybridRetriever`, re-embeds persisted chunks, and mutates session state inline.
**Why it's wrong:** Diverges from the main indexing path and duplicates embed/index responsibilities that belong behind `HybridRetriever`/a store-rehydration helper.
**Do this instead:** Extract a single `rehydrate_index_from_store(doc_id)` helper reused by both dedup and normal paths.

### Duplicate capability/health probing per rerun

**What happens:** Every rerun calls `load_ai_model()`, `ai_model.check_health()`, `ai_model.get_capabilities()` (`main.py:279-311`), and `check_health` itself re-probes providers when unhealthy (`local_llm.py:193-207`).
**Why it's wrong:** Repeated HTTP probes to llama-server on every interaction.
**Do this instead:** Cache health/capabilities with a short TTL as done for GPU telemetry in `resource_telemetry.py:33-97`.

## Error Handling

**Strategy:** Fail fast with typed exceptions at module boundaries; isolate-and-continue for per-document / per-page work; degrade to documented fallbacks for optional dependencies.

**Patterns:**
- Per-file upload guard: `try/except Exception` around reader + OCR + VLM in `main.py:466-532`; failure sets `failed_doc_ids` and `continue`s.
- Per-page isolation: `pdf_reader.py:116-127`, `ocr_fallback.py:294-307` (`status="failed"`, error recorded).
- Constructor validation: `VectorIndex` raises `ValueError`/`TypeError` (`vector_index.py:27,52-60,76-92,121-132`); `BBox`/`Document` validators (`models.py:47-51,135-139`); `upload_validation.validate_pdf_bytes` raises actionable `ValueError`.
- Consent gate: `PermissionError` from `LiteLLMProvider._assert_consent` (`litellm_provider.py:142-148`); API-key scrubbing in errors (`litellm_provider.py:135-140`).
- Provider health confluence: `HealthStatus` (`healthy`/`loading`/`unreachable`/`error`) drives UI state (`main.py:310-342`).
- No retry/timeout wrapping around the streaming call site in `main.py:796-875` — a raised `RuntimeError` from a provider is caught and surfaced as `st.error`, with an interrupted-turn appended to history.

## Cross-Cutting Concerns

**Logging:** stdlib `logging` per module (`logger = logging.getLogger(__name__)`); user-facing feedback exclusively via `st.*`. `logging_setup.suppress_torch_classes_scan_warning()` silences the benign Streamlit watcher traceback (`main.py:51`).
**Validation:** Pydantic v2 canonical models (`models.py`) at all persistence and retrieval boundaries; `upload_validation` at the network edge.
**Authentication:** No user auth; cloud access is consent-gated + session-scoped keys only (never persisted). Local inference guarded by loopback SSRF restriction (`llama_cpp_provider.py:43-60`).
**Privacy:** `LITELLM_TELEMETRY=False` by default (`litellm_provider.py:19`); originals/embeddings/DB stay on-device; only excerpts/summaries egress with consent.
**Token budgeting:** `prompt_budget.assemble_grounded_messages` enforces context window with oldest-first history truncation and XML boundary sanitisation (`prompt_budget.py:57-142`).

---

*Architecture analysis: 2026-10-19*
