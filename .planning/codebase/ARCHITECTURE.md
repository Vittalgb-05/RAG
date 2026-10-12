<!-- refreshed: 2026-10-12 -->
# Architecture

**Analysis Date:** 2026-10-12

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              Streamlit UI / Orchestrator                     │
│  `main.py` — tab_chat (grounded QA) + tab_summary            │
│  (summarizer) + sidebar upload + telemetry widget            │
├──────────────────┬──────────────────┬───────────────────────┤
│  Ingestion       │  Hybrid Retrieval│  Inference (gated)     │
│  `docling_reader │  `hybrid_        │  `local_llm.py`        │
│  .py`            │  retriever.py`   │  (InferenceGate)       │
│  `pdf_reader.py` │  (sole index)    │  `model_provider.py`   │
│  `ocr_fallback   │  `local_         │  `groq_provider.py`    │
│  .py`            │  embedding.py`   │  `llama_cpp_provider   │
│  `visual_        │  (embed-fn only) │  .py`                  │
│  analyzer.py`    │  `vector_index   │  `prompt_budget.py`    │
│                  │  .py` (mirror)   │  `summarizer.py`       │
│                  │                  │  `citation_validator   │
│                  │                  │  .py`                  │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence + Telemetry Layer                               │
│  `doc_store.py` (SQLite `data/documents.db`: documents,     │
│   pages, chunks, evidence_elements, document_summaries v3)   │
│  `hybrid_retriever.py` (LanceDB `data/lancedb`) + `.cache/`  │
│  `resource_telemetry.py` (nvidia-smi/psutil/LatencyTracker)  │
│  `scripts/profile_resources.py` (offline benchmark harness)  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Canonical Contracts                                         │
│  `models.py` — Chunk / Page / Document / EvidenceSnippet /  │
│  RetrievalResult / BBox / EvidenceElement / SummaryResult /  │
│  SummaryProfile + VALID_SUMMARY_PROFILES                     │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session-state init, sidebar (model health + PDF upload + indexed-docs view + Clear All incl. `summary_*` purge), `st.tabs` wiring (`tab_chat` / `tab_summary`), telemetry expander widget, chat replay with badges/drawer, `MAX_CHAT_TURNS` bounding via `append_chat_turn`, single shared `RetrievalResult` fetch, streaming render | `main.py` |
| InferenceGate | Process-level reentrant lock (`threading.RLock` + counter) guaranteeing max one active GPU inference op; `acquire`/`release`/`is_locked`/`hold` (timeout → `TimeoutError`); guards QA streaming and summarization map/reduce | `local_llm.py:26-90` |
| AiModel | Provider auto-detection (llama-server → Groq), health re-probing, RAG orchestration, `retrieval_result`-first prompt assembly via `assemble_grounded_messages`, InferenceGate-guarded `ask_a_question_from_pdf_stream` + `generate_text`, `validate_response` citation-validation façade | `local_llm.py:93-319` |
| Resource Telemetry | `get_gpu_memory_info` (nvidia-smi CSV parse → `total/used/free_mb` + `utilization_pct`, `None` on headless/CI), `get_process_memory_info` (psutil RSS/VMS MB, zeros fallback), `LatencyTracker`/`track_stage`/`record_stage_latency` (thread-safe `defaultdict`, `MAX_STAGE_HISTORY=200`), `get_system_telemetry_snapshot` (timestamp + gpu + process + per-stage count/avg/min/max) | `resource_telemetry.py:26-211` |
| Telemetry Widget | Sidebar `📊 System Telemetry & VRAM` expander: `st.metric` GPU VRAM + progress bar + 3-tier health caption (🟢 <3.5GB / 🟡 3.5–3.8GB / 🔴 >3.8GB, else CPU-only caption), process RSS caption, persistent-cache counts via `count_documents`/`count_summaries` | `main.py:357-386` |
| Resource Profiler | Offline 6-stage benchmark harness (ingestion → CPU embeddings → LanceDB retrieval cold/warm → summary cache SLA → InferenceGate check → VRAM budget audit) writing `.planning/research/RESOURCE_PROFILE.json` with projected-peak VRAM vs 3800 MB target | `scripts/profile_resources.py:94-342` |
| HybridRetriever (sole index) | Persistent hybrid retrieval: LanceDB dense vectors + FTS index, pure-Python BM25 fallback, RRF fusion (`compute_rrf`), `search_hybrid` → canonical `RetrievalResult`; in-memory `VectorIndex` mirror with `chunk_id` upsert dedup; disk-backed `fallback_store.json` when LanceDB missing | `hybrid_retriever.py:79-626` |
| LocalEmbedding (embed-fn provider) | CPU-pinned `SentenceTransformer` (`all-MiniLM-L6-v2`, 384-dim L2-normalised) wrapper; `_embed_one` is the shared query/index embedding function injected into `HybridRetriever`; `build_index`/`search`/`search_hybrid`/`get_context` retained as fallback dense path | `local_embedding.py:19-116` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search` (linear-scan k-NN, cosine + Euclidean, dimension locking); serves as `HybridRetriever` fallback mirror (`hybrid_retriever.py:104-108`) | `vector_index.py` |
| Canonical Models | Pydantic v2 contracts: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult` (`formatted_evidence`, `source_labels`), `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` | `models.py` |
| DocStore | SQLite WAL metadata store (`documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` v3; migrations v1–v3); SHA-256 dedup, chunk restore, `save_summary`/`get_summary` (model-version invalidation)/`list_summaries_for_doc`/`delete_summaries_for_doc`/`delete_document` cascade, `count_documents`/`count_summaries` for telemetry widget | `doc_store.py` |
| Summarizer | Hierarchical multi-profile summarization: profile dispatch, fast-path vs map-reduce selection, `InferenceGate.hold(timeout=120.0)`-guarded generation, `(p. X)` citation preservation, `SummaryResult` construction, 4-tier cache check/save (`force_refresh` bypass) | `summarizer.py:301-420` |
| CitationValidator | Post-generation grounding gate: `extract_citations` (`[En]`), `is_abstention`, `validate_citations` → frozen `CitationVerificationResult` (≥95% precision, empty-response invalid, abstention-with-citations invalid) | `citation_validator.py` |
| Chat Bounding | `MAX_CHAT_TURNS = 50` + `append_chat_turn` (append → `bound_chat_history`) + `bound_chat_history` (tail-slice to 50, strip leading orphan assistant turns) + token-level oldest-first truncation inside `assemble_grounded_messages` | `main.py:38,389-395`, `prompt_budget.py:57-152` |
| Providers | `BaseModelProvider` ABC + `HealthStatus`/`ProviderCapabilities`; `LlamaCppProvider` (local Qwen3-VL 2B GGUF) and `GroqProvider` (cloud fallback) | `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py` |
| DoclingReader | Structured extraction via Docling `DocumentConverter` (CPU-only, `do_ocr=False`, `do_table_structure=True`); graceful degrade to `PdfReader` (pypdf) | `docling_reader.py` |
| PdfReader | Legacy pypdf text extraction + `RecursiveCharacterTextSplitter` chunking (1000/200) with `{content, filename, page, chunk_id}` metadata | `pdf_reader.py` |
| Conditional OCR | RapidOCR fallback for low-text/scanned pages (INGEST-04) | `ocr_fallback.py` |
| VisualAnalyzer | Visual element detection, cropping, VLM analysis (VIS-01/02/03); results recorded via `DocStore.record_evidence_elements` | `visual_analyzer.py` |
| Upload Validation | Server-side `%PDF` header / size / page-limit checks, SHA-256 + `doc_id` derivation | `upload_validation.py` |
| Prompt Budget | Bounded context assembly: `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`[E1]` citation rules + abstention sentence), `sanitize_xml_boundary`, `estimate_tokens`, oldest-first history truncation, `bound_chat_history` turn cap | `prompt_budget.py` |

## Pattern Overview

**Overall:** UI-orchestrated modular monolith with persistent hybrid retrieval, single-active-LLM concurrency gating, live resource telemetry, multi-tier cache invalidation, and bounded chat memory.

**Key Characteristics:**
- Fully local retrieval path (CPU embeddings + on-disk LanceDB/SQLite, zero network egress); only generation may call Groq Cloud.
- Single-active-LLM invariant — every token-producing call (QA stream, `generate_text`, summarizer map/reduce) executes while holding `InferenceGate`; concurrent inference either waits (up to timeout) or yields a busy-retry notice instead of colliding in 4 GB VRAM.
- HybridRetriever-as-sole-index — one `search_hybrid(k=5)` call in `main.py` spans all uploaded documents; `LocalEmbedding` is retained only as the CPU embedding-function provider (`_embed_one`) injected into the retriever, plus a dormant dense-only fallback path.
- One-retrieval-per-question: `main.py` fetches a single shared `RetrievalResult` and passes the identical object to prompt assembly, generation, validation, and UI citations (RETR-04).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `str` fragments; `st.write_stream` renders incrementally and returns the full string for post-hoc validation.
- Validate-after-stream: citations are checked on the completed string via `AiModel.validate_response` → `validate_citations`; the `CitationVerificationResult` is persisted alongside the turn in `chat_history` and re-rendered on replay.
- Multi-tier cache invalidation: Tier 1 session (`summary_{doc_id}_{profile}` dicts, purged by Clear All) → Tier 2 disk `.cache/<sha>/<CONFIG_VERSION>/*.json` (best-effort extraction cache) → Tier 3 SQLite `document_summaries` keyed `(sha256, profile)` with read-time `model_version` invalidation + `force_refresh` bypass → Tier 4 LanceDB/`fallback_store.json` vector persistence; telemetry counts surface Tier 3 size.
- Bounded chat memory at two levels: turn-count cap (`MAX_CHAT_TURNS=50` via `bound_chat_history`) and token-budget truncation (oldest-first inside `assemble_grounded_messages` against `context_window - 1024` reserved).
- Graceful degradation everywhere: Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, llama-server → Groq → offline diagnostic, nvidia-smi/psutil → `None`/zeros in CI.

## Layers

**Presentation / Orchestration:**
- Purpose: File upload, index-status display, tabbed chat + summarizer UX, streamed answer rendering with verification badges and evidence drawers, live VRAM/RAM/cache telemetry.
- Location: `main.py`
- Contains: `st.set_page_config` (`main.py:44-49`), session-state init loop (`main.py:58-67`), `load_ai_model` (`@st.cache_resource`, `main.py:75-83`), sidebar upload/index loop (`main.py:164-353`), telemetry expander (`main.py:357-386`), `append_chat_turn` bounding helper (`main.py:389-395`), `st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])` (`main.py:402`), chat tab (`main.py:404-576`), summary tab (`main.py:579-664`).
- Depends on: `local_llm.py:AiModel`, `local_embedding.py:LocalEmbedding`, `hybrid_retriever.py:HybridRetriever`, `docling_reader.py:DoclingReader`, `doc_store.py:DocStore`, `summarizer.py:Summarizer`, `resource_telemetry.py:get_gpu_memory_info/get_process_memory_info`, `prompt_budget.py:bound_chat_history`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion / Extraction:**
- Purpose: Bytes-in, canonical `Chunk`/`Page` records out, with per-page fault isolation.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader.extract_text/get_paragraphs/get_page_records`, `PdfReader.extract_text/get_paragraphs`, `apply_conditional_ocr`, `VisualAnalyzer.analyze_visual_elements`, `validate_pdf_bytes`.
- Depends on: `docling`, `pypdf`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `models.py:Chunk/Page`.
- Used by: `main.py:230-266` (upload path) and `local_llm.py:207-211` (on-the-fly fallback path).

**Retrieval (HybridRetriever as sole index):**
- Purpose: Semantic + keyword lookup fused into ranked, provenance-carrying evidence through a single index object.
- Location: `hybrid_retriever.py`, `local_embedding.py` (embed-fn only), `vector_index.py` (mirror)
- Contains: `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid`, `compute_rrf`, `_bm25_search_fallback`, `LocalEmbedding._embed_one/get_embeddings`, `VectorIndex.add_vector/add_document/search` plus `_cosine_distance/_euclidean_distance`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding only), optional `lancedb` + `pyarrow`; fallback store is stdlib-only.
- Used by: `main.py:278-288` (build: `LocalEmbedding.get_embeddings` batch → `HybridRetriever.index_chunks` with `chunk_id` upsert dedup), `main.py:495-499` (query: `active_retriever.search_hybrid(search_query, k=5)`), `main.py:212-225` (CR-01 restore: re-embed persisted chunks → fresh `HybridRetriever`), `local_llm.py:224-238` (in-LLM fallback retrieval).

**Inference / Generation (InferenceGate-guarded):**
- Purpose: Grounded answer synthesis with conversational memory, bounded context, and single-active-LLM concurrency safety.
- Location: `local_llm.py:26-90` (gate), `local_llm.py:184-299` (stream + non-stream paths), `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`
- Contains: `InferenceGate.acquire/release/is_locked/hold`, `AiModel._detect_provider/check_health/ask_a_question_from_pdf_stream/generate_text/validate_response`, `BaseModelProvider.stream_text/generate_text`, `assemble_grounded_messages`, `bound_chat_history`.
- Depends on: `HybridRetriever` / `LocalEmbedding` (retrieval input), `models.py:RetrievalResult` (context input), `citation_validator.py:validate_citations` (post-check).
- Used by: `main.py:516-522` (chat stream), `summarizer.py:388-394` (summary map/reduce via gate-held `provider.generate_text`).

**Summarization:**
- Purpose: Bounded, VRAM-safe, profile-shaped document synthesis with `(p. X)` citations and multi-tier caching.
- Location: `summarizer.py:301-420`
- Contains: `Summarizer.summarize_document` (profile whitelist → Tier-3 cache check → page resolve/enrich → `InferenceGate.hold(timeout=120.0)` fast/map-reduce → `extract_page_references` → `save_summary`), `_bundle_pages` (`summarizer.py`), `_format_page_batch`, `_summarize_single_pass`, `_summarize_map_reduce`, `extract_page_references`, `PROFILE_SYSTEM_INSTRUCTIONS`, `MAP_PROMPT_TEMPLATE` / `REDUCE_PROMPT_TEMPLATE`, `FAST_PATH_TOKEN_LIMIT = 2500` / `MAX_BATCH_TOKENS = 2000`.
- Depends on: `local_llm.py:InferenceGate`, `model_provider.py:BaseModelProvider` (`generate_text`, `get_capabilities`), `models.py:Page/SummaryResult/VALID_SUMMARY_PROFILES`, `prompt_budget.py:estimate_tokens/sanitize_xml_boundary`, `doc_store.py:DocStore` (Tier-3 cache backend).
- Used by: `main.py:630-635` (summary tab generation).

**Citation Validation:**
- Purpose: Deterministic post-generation grounding gate independent of any LLM.
- Location: `citation_validator.py:52-181`
- Contains: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations`.
- Depends on: `models.py:RetrievalResult` (snippet-count bound only), stdlib `re`, Pydantic v2.
- Used by: `local_llm.py:301-319` (`AiModel.validate_response`), exercised in `main.py:526`.

**Persistence + Telemetry:**
- Purpose: Survive restarts (document metadata, chunk text, vectors, evidence elements, summaries, disk cache) and expose live resource pressure (VRAM/RAM/latency).
- Location: `doc_store.py`, `hybrid_retriever.py:_save_fallback_store/_load_fallback_store`, `resource_telemetry.py`, `.cache/`, `scripts/profile_resources.py`
- Contains: `DocStore.upsert_document/record_page/record_chunks/record_evidence_elements/get_chunks_for_doc/save_summary/get_summary/list_summaries_for_doc/delete_summaries_for_doc/delete_document/count_documents/count_summaries`, `SCHEMA_V3_DDL` `document_summaries` table (`doc_store.py:73-94`, `UNIQUE(sha256, profile)`, FK `doc_id → documents(doc_id) ON DELETE CASCADE`), `MIGRATIONS = {1,2,3}` (`doc_store.py:96-100`), LanceDB `chunks` table, `fallback_store.json`, `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`, `get_gpu_memory_info/get_process_memory_info/LatencyTracker/track_stage/get_system_telemetry_snapshot`.
- Depends on: stdlib `sqlite3` (WAL mode), optional `lancedb`, `nvidia-smi` subprocess, optional `psutil`.
- Used by: `main.py:87` (open), `main.py:268-332` (record pages/chunks/manifest/cache), `main.py:212-225` (CR-01 restore after restart), `main.py:357-384` (telemetry widget reads), `main.py:644-647` (summary cache read), `summarizer.py:332-336,415-418` (summary cache check/save).

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted)

1. Upload + validate (`main.py:169-192`) — single `getvalue()` read per file; `MAX_FILE_MB` pre-check; `validate_pdf_bytes` (`upload_validation.py`) yields `doc_id`/`sha256`/`num_pages`.
2. Dedup via `DocStore.get_by_sha` (`main.py:194-226`) — session `doc_ids` set + SQLite `status == "indexed"` check; CR-01 path restores chunks from `DocStore.get_chunks_for_doc` into fresh `LocalEmbedding` + `HybridRetriever` (re-embed via `get_embeddings`, `index_chunks`) when the session index is empty after restart.
3. Extraction (`main.py:230-270`) — `DoclingReader.extract_text` → `get_paragraphs`/`get_page_records`; `apply_conditional_ocr` patches scanned pages; `VisualAnalyzer.analyze_visual_elements` runs against the active provider and records elements; per-page `record_page` with `st.progress`; failed pages warn and continue.
4. Sole-index build (`main.py:278-288`) — `LocalEmbedding.get_embeddings([p["content"] ...])` batch on CPU, then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` which writes BOTH the persistent LanceDB table (or `fallback_store.json`) and the in-memory `VectorIndex` mirror with `chunk_id` upsert dedup (`hybrid_retriever.py:269-282`). `LocalEmbedding.build_index`/`store` is NOT written on this path — the embedding object serves only as the `_embed_one` function provider.
5. Persist (`main.py:290-332`) — `Chunk.model_validate` → `record_chunks`; `Document` → `upsert_document`; best-effort `.cache/<sha>/docling-1000-200-v1/*.json` write; session-state update + `st.rerun()`.

### InferenceGate Single-Active-LLM Flow (concurrency control)

1. Gate primitive (`local_llm.py:26-90`) — class-level `threading.RLock` (`_lock`) + `_active_threads` counter under `_state_lock`. `acquire(timeout)` blocks on the RLock then increments; `release()` releases and decrements (swallows stray `RuntimeError`); `is_locked()` reads the counter; `hold(timeout)` context manager raises `TimeoutError("InferenceGate acquisition timed out after ...")` on failure and always releases.
2. QA streaming path (`local_llm.py:258-271`) — after prompt assembly, `ask_a_question_from_pdf_stream` calls `InferenceGate.acquire(timeout=60.0)`; on failure it yields `"⚠️ System is busy processing another inference request. Please retry in a moment."` and returns WITHOUT calling the provider; on success it `yield from provider.stream_text(...)` inside `try/finally: InferenceGate.release()`.
3. Non-streaming path (`local_llm.py:273-299`) — `AiModel.generate_text(..., timeout=60.0)` wraps `provider.generate_text` in `with InferenceGate.hold(timeout=timeout)`, so contention raises `TimeoutError` to the caller.
4. Summarization path (`summarizer.py:387-394`) — `summarize_document` wraps the entire fast-path-or-map-reduce generation block in `with InferenceGate.hold(timeout=120.0)` (longer timeout for multi-call map-reduce); every `provider.generate_text` inside map/consolidate/reduce therefore executes under the same single-active-LLM lock, strictly sequentially.
5. Reentrancy note — because the underlying lock is an RLock, nested `hold` on the SAME thread re-enters (covered in `tests/test_concurrency_lock.py`); cross-thread contention blocks to timeout. The busy-yield (stream) vs raise (non-stream) asymmetry is intentional: interactive chat degrades to a retry notice, programmatic callers get an exception.

### Telemetry Pipeline (nvidia-smi/psutil → sidebar widget → profiler artifact)

1. GPU probe (`resource_telemetry.py:26-71`) — `get_gpu_memory_info` runs `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits` (`timeout=2.0`), parses the first line into `{total_mb, used_mb, free_mb, utilization_pct}`; returns `None` on `FileNotFoundError`/`SubprocessError`/`ValueError`/`IndexError` (headless/CI) with a `logger.debug`.
2. Process probe (`resource_telemetry.py:74-96`) — `get_process_memory_info` reads `psutil.Process().memory_info()` into `{rss_mb, vms_mb}`; returns zeros on missing `psutil` or any error.
3. Latency registry (`resource_telemetry.py:99-181`) — `LatencyTracker(stage_name)` context manager times with `perf_counter`, records `elapsed_ms`/`success`/`error` into thread-safe `_LATENCY_HISTORY` capped at `MAX_STAGE_HISTORY=200`; `track_stage`/`record_stage_latency` are convenience wrappers; `get_latency_history`/`clear_latency_history` copy/clear under `_LATENCY_LOCK`; `get_system_telemetry_snapshot` aggregates per-stage `{count, avg_ms, min_ms, max_ms}` with an ISO timestamp.
4. Live widget (`main.py:357-386`) — sidebar `with st.expander("📊 System Telemetry & VRAM")` calls both probes + `doc_store.count_documents()`/`count_summaries()` (`doc_store.py:590-610`) every rerun: GPU present → `st.metric("GPU VRAM", "{used:.0f} / {total:.0f} MB", "{pct:.1f}% used")` + `st.progress(used/total)` + tiered caption (🟢 `<3500` / 🟡 `3500–3800` / 🔴 `>3800`); GPU absent → `ℹ️ CPU-only Mode` caption; always shows `Process RAM (RSS)` caption and `Persistent Cache: {docs} docs · {sums} summaries` caption.
5. Offline profiler (`scripts/profile_resources.py:94-342`) — `run_resource_profile()` executes 6 stages against `tests/data/corpus/` (cold/warm ingestion, CPU embedding rate, LanceDB index + cold/warm `search_hybrid`, summary cold-generate vs warm-cache with `<50ms` SLA assert, `InferenceGate` hold-cycle check, projected-peak VRAM budget `dwm + 1450 + 450 + 510 + 350` vs `3800 MB` target) and writes `.planning/research/RESOURCE_PROFILE.json`.

### Multi-Tier Cache Invalidation

1. Tier 1 — session (`main.py:622,643,151-153`) — `st.session_state[f"summary_{doc_id}_{profile}"] = summary_obj.model_dump()` on generate; read-first on display; Clear All deletes every `summary_*` key plus resets `doc_ids`/`indexed_files`/`document_metadata`/`local_embedding`/`hybrid_retriever`/`chat_history` and closes the retriever.
2. Tier 2 — disk extraction cache (`main.py:311-321`, `models.py`) — best-effort `.cache/<sha256>/docling-1000-200-v1/{pages,chunks,manifest}.json` write per upload (`STORE-03`); `OSError` → `st.warning`, never fatal; keyed by SHA-256 + `CONFIG_VERSION`, so chunking/config changes naturally miss.
3. Tier 3 — SQLite summary cache (`summarizer.py:331-336`, `doc_store.py:425-514`) — `summarize_document` returns `DocStore.get_summary(sha256, profile, model_version=provider.model_name)` immediately on hit (zero provider calls) unless `force_refresh=True`; key is `(sha256, profile)` (`UNIQUE` in `doc_store.py:84`); `model_version` is a read-time invalidation predicate (`doc_store.py:494-499` returns `None` on mismatch → regenerate + `ON CONFLICT(sha256, profile) DO UPDATE` upsert in `save_summary`); `list_summaries_for_doc`/`delete_summaries_for_doc` scope by `doc_id`; `delete_document` cascades via FK.
4. Tier 4 — vector persistence (`hybrid_retriever.py:110-124,149-187`) — LanceDB `chunks` table when available (upsert via `merge_insert` on `chunk_id`); otherwise `fallback_store.json` under `data/lancedb/` rewritten on `close()` and reloaded in `_load_fallback_store`; `delete_document(doc_id)` evicts from both mirror and table.

### Grounded QA Flow (question → gated stream → validated citations → badges/drawer)

1. Bounded history + contextualized query (`main.py:476-490`) — new user turn appended via `append_chat_turn` (turn-cap enforced immediately); `history_to_pass = chat_history[:-1][-10:]`; `search_query = last_user_msg + " " + prompt` so follow-ups retrieve correctly.
2. Single shared retrieval (`main.py:492-511`) — `active_retriever = hybrid_retriever or local_embedding`; if it exposes `search_hybrid`, one call `search_hybrid(search_query, k=5)` returns the canonical `RetrievalResult`; `sources = retrieval_res.source_labels()` plus `snippets_data = [s.model_dump() for s in retrieval_res.snippets]`. Legacy `search(k=10)` branch only applies to retrievers without `search_hybrid`.
3. Hybrid fusion inside `HybridRetriever.search_hybrid` (`hybrid_retriever.py:511-616`) — embed query via CPU embedding fn → `search_dense` (LanceDB vector search, `candidate_pool = max(k*2, 10)`) + `search_fts` (LanceDB FTS → pure-Python BM25 fallback) → `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k mapped to `EvidenceSnippet` items (with `rank`, `dense_rank`, `fts_rank`, `score=RRF`, `bbox` rehydrated from `bbox_json`) → frozen `RetrievalResult(query, snippets, total_candidates, search_mode)`.
4. Shared-identity gated generation (`main.py:516-522` → `local_llm.py:204-271`) — the same `retrieval_result` object is passed to `ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_res)`; the LLM uses `retrieval_result.formatted_evidence()` (`[E1] (file, p. N)` blocks) directly under `InferenceGate.acquire(60s)`; the in-LLM fallback (`local_llm.py:206-242`) only runs when no pre-computed result is supplied.
5. Bounded grounded prompt + stream (`local_llm.py:246-271`) — `assemble_grounded_messages` wraps context in `<document_context>` with the `[E1]`/`[E2]` citation rules and abstention sentence (`prompt_budget.py:13-23`), XML sanitization and token budgeting against the provider's `context_window`; `provider.stream_text(...)` yields tokens; `st.write_stream` renders and returns the full string (`main.py:523`).
6. Citation validation (`main.py:526` → `local_llm.py:301-319` → `citation_validator.py`) — `ai_model.validate_response(full_response, retrieval_res)` resolves the active result (explicit arg wins, else `last_retrieval_result`), runs `validate_citations`: empty text → `is_valid=False, precision=0.0`; abstention text + zero citations → `is_valid=True, precision=1.0, abstention_detected=True`; abstention + citations → invalid; otherwise precision = `valid_ranks / total_claimed` with `is_valid = precision >= 0.95` against `len(retrieval_result.snippets)` as the rank bound.
7. Badge + drawer render (`main.py:527-576`, replay `main.py:417-457`) — abstention → `ℹ️ Explicit abstention` caption; valid → `✅ Verified Grounding (P% citation precision)`; invalid → `⚠️ Unverified Citations (P%)`. Evidence chips `[E{rank}] filename (p. N)` plus `🔍 Cited Evidence & Source Context` expander iterate `snippets_data`. The turn is appended via `append_chat_turn` (re-bounding to 50); the exception path records an interruption note with `verification: None`.

### Summarization Flow (profile → gated map-reduce → cache → summary tab)

1. Tab wiring + selection (`main.py:579-622`) — `tab_summary` shows selectbox over `sorted(indexed_files)`, resolves `doc_id`/`sha256` from `document_metadata` with `doc_store.get_document` fallback, radio over the five `profile_map` keys, `Generate Summary` button (disabled when inference unhealthy) + `Force re-generate` checkbox. Per-doc/profile session key `summary_{doc_id}_{profile}`.
2. Tier-3 cache check (`summarizer.py:331-336`) — `summarize_document(doc_id, sha256, profile, force_refresh)` validates `profile ∈ VALID_SUMMARY_PROFILES`, reads `provider.get_capabilities().model_name` as `model_version`, and returns `DocStore.get_summary(sha256, profile, model_version=model_version)` immediately on hit (zero provider calls, zero gate acquisition).
3. Page resolution (`summarizer.py:338-378`) — if `pages is None`, reconstructs `Page` records from `chunks` arg or `doc_store.get_chunks_for_doc(doc_id)` grouped by page; if caller-supplied `Page` records lack `page_text`, enriches from stored chunks. Filters to pages with non-blank `page_text`; raises `ValueError` when none is extractable. `main.py:630-635` calls with `pages=None`, so the DocStore-chunks path is the live one.
4. Fast path vs map-reduce under gate (`summarizer.py:385-394`) — `total_tokens = Σ estimate_tokens(page_text)`; `≤ FAST_PATH_TOKEN_LIMIT (2500)` → `_summarize_single_pass`; above → `_summarize_map_reduce`; the dispatch executes inside `with InferenceGate.hold(timeout=120.0)`.
5. Map stage — `_bundle_pages(pages, MAX_BATCH_TOKENS=2000)` packs sequential pages by `estimate_tokens`; each batch is rendered as `--- Page N ---` sections with `sanitize_xml_boundary` and sent through `MAP_PROMPT_TEMPLATE` (page-range + `(p. X)` citation mandate) with `max_tokens=800, temperature=0.2`. Executes strictly sequentially to respect the single-active-LLM constraint.
6. Consolidation + reduce — intermediates joined with `\n\n---\n\n`; if combined tokens exceed `FAST_PATH_TOKEN_LIMIT` and there are >3 intermediates, two half-consolidation `generate_text` calls (`max_tokens=1000`) precede the final `REDUCE_PROMPT_TEMPLATE` synthesis under the profile system prompt (`max_tokens=1500, temperature=0.2`).
7. Reference extraction + persist (`summarizer.py:396-418`) — `extract_page_references(summary_text, max_page=...)` parses `(p. N)`/`(Page N)` via regex, dedups, sorts, clamps; builds `SummaryResult(summary_id=summ_*, ..., cached=False)`; `doc_store.save_summary(result)` upserts on `ON CONFLICT(sha256, profile)`. Session cache `st.session_state[summary_cache_key] = summary_obj.model_dump()` (`main.py:636`).
8. Display (`main.py:642-664`) — prefers the session value, falls back to `doc_store.get_summary(selected_sha, selected_profile)` without model-version pin; cached rows show `⚡ Loaded from persistent SQLite cache (DocStore v3)`, fresh ones `✨ Generated fresh with {model_version}`; summary markdown renders verbatim, then `📄 Referenced Source Pages` expander lists `Page N` chips + `created_at`.

**State Management:**
- `st.session_state` (per-browser-session, survives full-script reruns): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict` (filename → `doc_id`/`sha256`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None` (CPU embed-fn holder), `hybrid_retriever: HybridRetriever | None` (sole retrieval index), `chat_history: list` of `{role, content, sources, verification, snippets}` capped at `MAX_CHAT_TURNS=50` — initialised in `main.py:58-67`; plus dynamic `summary_{doc_id}_{profile}` keys. `Clear All` closes the retriever, resets all keys, deletes every `summary_*` key, calls `st.rerun()` (`main.py:142-154`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` (`main.py:75-83`) constructs `AiModel` once; every rerun/session reuses it. The embedding model is NOT cached — `LocalEmbedding`/`SentenceTransformer` lives in session state, so each browser session loads its own copy.
- `AiModel` transient grounding state: `last_retrieval_result` (set on every `ask_a_question_from_pdf_stream`, `local_llm.py:244`) and `last_verification_result` (set on every `validate_response`, `local_llm.py:318`). Process-singleton caveat documented in `local_llm.py:93-101` — always pass an explicit `retrieval_result` to `validate_response` to avoid cross-session contamination.
- `InferenceGate` class state (`local_llm.py:34-36`): `_lock: RLock` + `_active_threads: int` under `_state_lock` — the only cross-session mutable concurrency state; every other store (`VectorIndex` vectors/documents, `HybridRetriever` handles, `Summarizer` refs) is instance-scoped.
- On-disk state: SQLite `data/documents.db` (DocStore incl. `document_summaries`), LanceDB `data/lancedb/` (or `fallback_store.json` there without LanceDB), `.cache/<sha256>/docling-1000-200-v1/`.

## Key Abstractions

**Chunk (unit of retrieval):**
- Purpose: Text plus provenance metadata threaded through every layer.
- Examples: produced in `docling_reader.py` / `pdf_reader.py`, validated as `models.py:Chunk`, stored in LanceDB rows (`hybrid_retriever.py:298-311`) and mirrored in `vector_index.py`, restored from `doc_store.py`.
- Pattern: Frozen Pydantic model — `content`, `filename`, `page`, `chunk_id`, `doc_id` required; `char_start`/`char_end`/`bbox`/`extraction`/`embedding_model` optional. `Chunk.chunk_id` is the LanceDB upsert key.

**RetrievalResult + EvidenceSnippet (shared prompt/UI/validation contract, RETR-04):**
- Purpose: Single immutable container consumed identically by LLM prompt assembly, UI citation rendering, and citation validation — eliminates double retrieval and prompt/citation/validation drift.
- Examples: constructed in `hybrid_retriever.py:611-616` and `local_embedding.py:104-109`; consumed in `local_llm.py:204-205` (`formatted_evidence`), `main.py:499` (`source_labels`), `main.py:509-511` (`model_dump` snippets), `citation_validator.py` (rank bound).
- Pattern: Frozen Pydantic models. `EvidenceSnippet` carries `content/doc_id/filename/page/chunk_id/score/rank/dense_rank/fts_rank/extraction/char_start/char_end/bbox` (`models.py`). `RetrievalResult` carries `query/snippets/total_candidates/search_mode ∈ {hybrid, dense, fts, fallback}` with `formatted_evidence()` (`[E1] (name, p. N)` blocks) and `source_labels()` (deduped `filename (p. N)` chips).

**InferenceGate (single-active-LLM lock):**
- Purpose: Enforce the 4 GB VRAM invariant (only one LLM/VLM resident operation at a time) across QA streaming, direct generation, and summarization without a central scheduler.
- Examples: acquired in `local_llm.py:258` (stream), held in `local_llm.py:293` (`generate_text`), held in `summarizer.py:388` (map-reduce, 120s timeout); verified in `tests/test_concurrency_lock.py` and `scripts/profile_resources.py:249-256`.
- Pattern: Class-level `threading.RLock` + counter with `acquire(timeout)/release/is_locked/hold(timeout)` API; stream path degrades to a busy-retry yield, non-stream paths raise `TimeoutError`.

**Telemetry snapshot (VRAM/RAM/latency contract):**
- Purpose: One call capturing everything the widget and profiler need without importing Streamlit.
- Examples: produced in `resource_telemetry.py:184-211` (`get_system_telemetry_snapshot`), consumed live field-by-field in `main.py:359-384`, aggregated to JSON in `scripts/profile_resources.py:289-331`.
- Pattern: Plain dict `{timestamp, gpu: {...}|None, process: {rss_mb, vms_mb}, stages: {stage: {count, avg_ms, min_ms, max_ms}}}`; `LatencyTracker` is both the measurement instrument and the registry writer.

**CitationVerificationResult (grounding verdict):**
- Purpose: Deterministic, LLM-independent verdict rendered as badges and persisted per turn.
- Examples: produced in `citation_validator.py`, stored via `local_llm.py:317-319` (`last_verification_result`), persisted in `chat_history` (`main.py:557-565`), rendered in `main.py` badges/drawers.
- Pattern: Frozen Pydantic model — `is_valid`, `precision ∈ [0,1]`, `total_citations`, `valid_citations`/`hallucinated_citations` tags, `cited_ranks`, `abstention_detected`, `message`. Threshold `precision >= 0.95`.

**SummaryResult + SummaryProfile (cached synthesis contract):**
- Purpose: Profile-shaped markdown plus machine-readable page references and cache identity.
- Examples: produced in `summarizer.py:403-413`, persisted via `doc_store.py:425-463`, read in `summarizer.py:332-336` and `main.py:644-647`, rendered in `main.py:649-664`.
- Pattern: `SummaryProfile = Literal["overview","detailed","study_notes","tables_figures","findings"]`, `VALID_SUMMARY_PROFILES` tuple (`models.py`); `SummaryResult` carries `summary_id (summ_*)`, `doc_id (doc_*)`, `sha256`, `profile`, `summary_text`, `page_references: list[int]`, `created_at`, `model_version`, `cached`. SQLite row mirrors every field with `page_references_json` (`doc_store.py:73-94`).

**Unified sole retrieval index:**
- Purpose: One `search_hybrid` call spans all uploaded documents; exactly one object owns ranking state.
- Examples: `main.py:283-288` (incremental `index_chunks` per file into the session `HybridRetriever`), `main.py:410` (total-chunk aggregation), `main.py:495` (`active_retriever = hybrid or local` with hybrid preferred).
- Pattern: Append-only growth with `chunk_id` upsert dedup (`hybrid_retriever.py:269-282`); no per-document isolation; deletion only via `delete_document(doc_id)` or full Clear All reset. Summarization is the exception: it scopes to one `doc_id` via DocStore chunk lookup, never via the retriever.

**RRF fusion:**
- Purpose: Combine dense semantic ranking and BM25 keyword ranking without score calibration.
- Examples: `hybrid_retriever.py:31-76` (`compute_rrf`, `DEFAULT_RRF_K = 60`), wired in `hybrid_retriever.py:580`.
- Pattern: `RRF(d) = Σ 1/(k_rrf + rank_m(d))`; returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score; `search_mode` records which modalities contributed (`hybrid_retriever.py:571-578`).

**Token-stream generator (gate-held):**
- Purpose: Decouple token production (provider) from rendering (Streamlit) while holding VRAM exclusivity for the whole stream duration.
- Examples: `local_llm.py:184-271` (producer holds `InferenceGate` from before first token until generator exhaustion), `main.py:516-523` (consumer via `st.write_stream`).
- Pattern: Generator yielding `str` fragments; gate is released in the generator's `finally`, so early abandonment still unlocks. Summarization uses the non-streaming sibling `provider.generate_text` under `hold` instead.

**Map-reduce page bundling:**
- Purpose: Fit arbitrarily long documents into a 4K context window without parallel LLM residency.
- Examples: `summarizer.py` (`_bundle_pages`, `_summarize_map_reduce`).
- Pattern: Greedy sequential packing by `estimate_tokens` against `MAX_BATCH_TOKENS`; map → optional half-consolidation → reduce, every stage carrying `(p. X)` forward, all inside one `InferenceGate.hold`.

**Bounded chat history (turn cap + token budget):**
- Purpose: Cap unbounded session memory growth and keep every prompt inside the provider context window.
- Examples: `main.py:38` (`MAX_CHAT_TURNS = 50`), `main.py:389-395` (`append_chat_turn`), `prompt_budget.py:131-152` (`bound_chat_history`), `prompt_budget.py:105-122` (oldest-first token truncation), `main.py:481` (`history_to_pass = chat_history[:-1][-10:]` retrieval window).
- Pattern: Hard tail-slice to 50 turns with orphan-assistant pruning on every append; soft token truncation per request; narrow 10-turn window actually sent for history-contextualized retrieval.

## Entry Points

**Streamlit app (sole runtime entry):**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` first (`main.py:44-49`); session-state init; cached model load; sidebar upload/index loop; telemetry widget; `st.tabs` chat + summarizer loops.

**Chat tab (grounded QA):**
- Location: `main.py:404-576` (`with tab_chat:`)
- Triggers: Selecting `💬 Ask Your Document`; submitting `st.chat_input` (`main.py:466-469`, disabled until an index exists and inference is healthy).
- Responsibilities: History replay with badges/drawer, single shared `search_hybrid(k=5)`, gate-held `ask_a_question_from_pdf_stream` + `st.write_stream`, `validate_response`, live badge/drawer, `append_chat_turn` (bounded).

**Summary tab (grounded summarization):**
- Location: `main.py:579-664` (`with tab_summary:`)
- Triggers: Selecting `📑 Document Summarizer`; pressing `Generate Summary` (`main.py:624`).
- Responsibilities: Document selectbox, 5-profile radio, force-refresh flag, gate-held `Summarizer(provider=ai_model.provider, doc_store=doc_store).summarize_document(...)` under `st.status`, 4-tier cache display with page-reference expander.

**On-the-fly Q&A fallback (legacy, not exercised by UI):**
- Location: `local_llm.py:207-211`
- Triggers: Calling `ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None` and no `retrieval_result`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then retrieval + generation. `main.py` always passes an existing retriever and `pdf_path=""`, so this path is dormant in production.

**Benchmark + profiler scripts:**
- Location: `scripts/benchmark_baseline.py`, `scripts/profile_resources.py:94-342`
- Triggers: Manual invocation (`python scripts/profile_resources.py`).
- Responsibilities: Baseline retrieval/generation benchmarking; 6-stage VRAM/latency/cache/concurrency audit writing `.planning/research/RESOURCE_PROFILE.json` (see STRUCTURE.md).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom per interaction; long work (model load, extraction, embedding, summarization) blocks and is masked with `st.status` spinners. Token streaming is incremental rendering, not background threading. Map-reduce is deliberately sequential (no `asyncio`/threads). The ONLY cross-thread primitive is `InferenceGate` (`threading.RLock` + counter, `local_llm.py:34-36`); `LatencyTracker` history is the only other lock-protected shared state (`resource_telemetry.py:22-23`).
- **Single-active-LLM invariant:** At most one gate-held inference op at a time (QA stream 60s timeout, `generate_text` 60s, summarizer 120s). Stream contention yields a retry notice; non-stream contention raises `TimeoutError`. RLock reentrancy means same-thread nesting does not deadlock — cross-thread nesting blocks.
- **VRAM envelope:** Embeddings pinned to CPU (`device="cpu"` in `local_embedding.py:24,40`); only one LLM/VLM active at a time via `InferenceGate`; 4K context default with 1024 reserved output tokens (`prompt_budget.py:57-77`); summarizer budgets (`FAST_PATH_TOKEN_LIMIT=2500`, `MAX_BATCH_TOKENS=2000`, map `800` / reduce `1500` / consolidate `1000` token caps) keep every provider call inside the window; telemetry widget enforces operational awareness with 3.5/3.8 GB alert tiers (`main.py:374-379`).
- **Global state:** `st.cache_resource`-cached `AiModel` + provider client shared across sessions (`main.py:75-83`); per-session `LocalEmbedding` + `SentenceTransformer` + `HybridRetriever` + `VectorIndex` mirror in `st.session_state`. `AiModel.last_retrieval_result` / `last_verification_result` are process-shared transient state — pass explicit `retrieval_result` per call (`local_llm.py:93-101`). `InferenceGate._lock/_active_threads` is process-shared concurrency state (`local_llm.py:34-36`).
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py:InferenceGate` (import is gate-only, no cycle since `local_llm.py` never imports `summarizer.py`); `docling_reader.py` → `pdf_reader.py`; `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` have no project imports. `citation_validator.py` imports only `models.py:RetrievalResult`.
- **Persistence quadruplicity:** Every indexed chunk exists in up to four places — session `HybridRetriever` mirror, LanceDB table or `fallback_store.json`, SQLite `chunks` table, `.cache/*.json`. The four are kept in sync only by the paired write in `main.py:278-288` + persist block + CR-01 restore; direct writes to one store bypass the others.
- **Summary cache identity:** Key is `(sha256, profile)` (`UNIQUE` in `doc_store.py:84`); `model_version` is a read-time invalidation predicate, not part of the key (`doc_store.py:494-499`). Same bytes under a new filename re-point `doc_id` on upsert; `list_summaries_for_doc` on the old id then misses. `force_refresh=True` bypasses the read but still overwrites the row on save.
- **Chat memory bounds:** Hard cap `MAX_CHAT_TURNS=50` turns in session state (`main.py:38`, `prompt_budget.py:131-152`); 10-turn window sent for retrieval contextualization (`main.py:481`); token-budget truncation per request (`prompt_budget.py:105-122`). Growing past 50 user+assistant turns evicts oldest-first; leading orphan assistant turns are pruned so history never starts mid-exchange.
- **Linear-scan fallback:** Without LanceDB, `VectorIndex.search` is O(n) per query; BM25 fallback is O(N·|Q|) with precomputed document frequencies (`hybrid_retriever.py:453-456`).

## Anti-Patterns

### Dual-write ingestion still split across two statements in the UI layer

**What happens:** `main.py:287-288` calls `LocalEmbedding.get_embeddings` then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` as two separate statements, and the mirror write into `VectorIndex` happens implicitly inside `index_chunks` (`hybrid_retriever.py:269-282`).
**Why it's wrong:** A failure between the embedding call and the index call, or any future path that calls one without the other, leaves the embed-fn holder and the sole index inconsistent; readers must know the mirror exists to reason about `count_chunks`.
**Do this instead:** Encapsulate the embed-then-index pair behind a single façade (e.g. `HybridRetriever.index_texts(chunks)` that embeds via its own `embedding_fn` internally), so callers cannot partially index. Reference the existing `embedding_fn` injection (`main.py:283-286`) as the consolidation point.

### Dormant `pdf_path` / on-the-fly indexing parameter

**What happens:** `ask_a_question_from_pdf_stream(pdf_path="", ...)` still accepts a path and can build a throwaway `PdfReader` + `LocalEmbedding` (`local_llm.py:207-211`); `main.py:516-522` always passes `pdf_path=""` with a live retriever.
**Why it's wrong:** Dead surface area that suggests an indexing path the UI never uses; risks confusion about which index answers a question.
**Do this instead:** Keep the parameter for backward compatibility (tests in `tests/test_local_llm.py` cover it) but treat `retrieval_result`/`local_embedding` as the canonical inputs — which is already the documented precedence in `local_llm.py:184-205`.

### Telemetry widget re-probes GPU on every rerun

**What happens:** `main.py:359-360` spawns an `nvidia-smi` subprocess (2s timeout) plus a `psutil` probe on every Streamlit rerun, including every keystroke-driven chat replay.
**Why it's wrong:** Subprocess spawn per rerun adds latency to the chat loop and can serialize behind a hung driver call; the value changes slowly relative to interaction frequency.
**Do this instead:** Cache the GPU probe with `@st.cache_resource(ttl=5)` or `ttl=10` so the widget reads a seconds-fresh snapshot instead of forking per rerun. Keep the `None`-means-CPU-only handling unchanged.

## Error Handling

**Strategy:** Validate at boundaries, isolate per-file/per-page failures, degrade gracefully across backends, invalidate rather than serve stale, never hold the gate on failure paths.

**Patterns:**
- Gate-safe failure — the stream path releases `InferenceGate` in a `finally` (`local_llm.py:270-271`) so provider exceptions never wedge the lock; contention itself yields a retry string instead of raising, keeping the chat loop alive. `hold()` users (`generate_text`, summarizer) get `TimeoutError`, which the summary tab catches as `st.error` without touching chat (`main.py:638-640`).
- Telemetry never raises — `get_gpu_memory_info` returns `None` and `get_process_memory_info` returns zeros on any probe failure (`resource_telemetry.py:66-71,91-96`); the widget branches on `None` instead of try/except (`main.py:364-381`).
- Per-file upload guard — `try/except` around validation, `DoclingReader` extraction, OCR, and visual analysis in `main.py:183-270` shows `st.error` and `continue`s, so one corrupt PDF never aborts the batch; per-page `status == "failed"` records warn individually (`main.py:272-276`).
- Summary tab guard — `try/except` around `summarizer.summarize_document` inside `st.status` flips the status to `error` and shows `st.error(f"Summarization error: ...")` without touching other tabs (`main.py:624-640`); empty-text documents raise `ValueError` from the service layer (`summarizer.py:382-383`); unknown profiles raise `ValueError` before any provider call or gate acquisition (`summarizer.py:323-326`).
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0`; `HybridRetriever.index_chunks` raises on chunk/embedding mismatch or missing embedding source (`hybrid_retriever.py:252-266`); Pydantic models reject bad `doc_id`/`sha256`/coordinates/summary ids; `DocStore.save_summary` requires a `SummaryResult` instance (`doc_store.py:432-433`).
- Validation-as-data — `validate_citations` never raises on bad input: empty responses, ungrounded claims, hallucinated ranks, and abstention-with-citations all return a populated `CitationVerificationResult` with `is_valid=False`; the chat exception path records `verification: None` explicitly rather than fabricating a pass (`main.py:566-576`).
- Backend degradation with logging — LanceDB init/search/FTS failures log warnings and fall back to in-memory/BM25 rather than raising (`hybrid_retriever.py:112-124,389-403,491-509`); Docling import/conversion failure degrades to pypdf (`docling_reader.py`); provider detection falls back to an offline diagnostic provider (`local_llm.py:131-152`).
- Generation-stream errors surface inline — network or rate-limit errors during gate-held `provider.stream_text` propagate to the `try/except` around the stream call in `main.py:515-576`, which renders an inline error and records an interruption note in history (still turn-bounded via `append_chat_turn`) rather than crashing.

## Cross-Cutting Concerns

**Logging:** `logging` module in backend services (`logger.info/warning` in `hybrid_retriever.py`, `local_embedding.py`, `docling_reader.py`, `summarizer.py`, `citation_validator.py`, `resource_telemetry.py:logger.debug` on probe failures); developer `print` for migration notices (`doc_store.py`) and profiler stage output (`scripts/profile_resources.py`); user-facing feedback exclusively via Streamlit (`st.error`/`st.info`/`st.success`/`st.status`/`st.warning`/`st.caption`/`st.metric` badges in `main.py`).
**Validation:** `upload_validation.py` (bytes/header/size/page limits) at the edge; Pydantic v2 enforcement in `models.py` (incl. `SummaryResult.validate_ids`) and `citation_validator.py:CitationVerificationResult` for all persisted/retrieved/validation records; `VectorIndex` type/dimension guards; `Summarizer` profile whitelist + non-empty-text gate; `DocStore.get_summary` model-version invalidation predicate.
**Authentication:** Provider-key resolution inside `GroqProvider` (env/`st.secrets`); local llama-server needs no credentials. See `INTEGRATIONS.md`.
**Concurrency:** `InferenceGate` is the single concurrency primitive (RLock + counter, `local_llm.py:26-90`); `LatencyTracker` history lock is the only other shared-mutable guard (`resource_telemetry.py:22-23`). No `asyncio`, no thread pools, no background workers anywhere in the app path.
**Prompt safety:** `sanitize_xml_boundary` neutralizes `</document_context>` spoofing in both QA (`prompt_budget.py:26-40`, applied to context + prompt in `assemble_grounded_messages`) and summarization (page batches and combined intermediates), plus the do-not-execute directives in every profile/map/reduce template; `SYSTEM_GROUNDING_TEMPLATE` instructs the model to treat all document text as untrusted data (`prompt_budget.py:13-23`); the chat `disabled=` gate plus `is_healthy` check prevent offline inference attempts (`main.py:460-469`).
**Chat memory safety:** `MAX_CHAT_TURNS=50` hard cap via `append_chat_turn`/`bound_chat_history` (`main.py:38,389-395`, `prompt_budget.py:131-152`) prevents unbounded `st.session_state` growth; per-request token budgeting (`prompt_budget.py:57-129`) prevents context-window overflow regardless of turn count.

---

*Architecture analysis: 2026-10-12*
