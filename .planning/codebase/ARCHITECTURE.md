<!-- refreshed: 2026-10-11 -->
# Architecture

**Analysis Date:** 2026-10-11

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI / Orchestrator               │
│  `main.py` — sidebar upload + chat + streaming render       │
├──────────────────┬──────────────────┬───────────────────────┤
│  Ingestion       │  Hybrid Retrieval│  Inference             │
│  `docling_reader │  `hybrid_        │  `local_llm.py`        │
│  .py`            │  retriever.py`   │  `model_provider.py`   │
│  `pdf_reader.py` │  `local_         │  `groq_provider.py`    │
│  `ocr_fallback   │  embedding.py`   │  `llama_cpp_provider   │
│  .py`            │  `vector_index   │  .py`                  │
│  `visual_        │  .py`            │  `prompt_budget.py`     │
│  analyzer.py`    │                  │                        │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence Layer                                           │
│  `doc_store.py` (SQLite `data/documents.db`)                │
│  `hybrid_retriever.py` (LanceDB `data/lancedb`) + `.cache/` │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Canonical Contracts                                        │
│  `models.py` — Chunk / Page / Document / EvidenceSnippet /  │
│  RetrievalResult / BBox / EvidenceElement                   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session-state init, sidebar (model health + PDF upload + indexed-docs view + Clear All), chat replay, `st.chat_input` gating, single shared `RetrievalResult` fetch, source chips, streaming render | `main.py` |
| AiModel | Provider auto-detection (llama-server → Groq), health re-probing, RAG orchestration, `retrieval_result`-first prompt assembly via `assemble_grounded_messages`, token-stream delegation to active provider | `local_llm.py` |
| HybridRetriever | Persistent hybrid retrieval: LanceDB dense vectors + FTS index, pure-Python BM25 fallback, RRF fusion (`compute_rrf`), `search_hybrid` → canonical `RetrievalResult`; disk-backed JSON fallback when LanceDB missing | `hybrid_retriever.py` |
| LocalEmbedding | CPU-pinned `SentenceTransformer` (`all-MiniLM-L6-v2`, 384-dim L2-normalised) wrapper; batch `build_index`, `_embed_one` query vectorizer shared with `HybridRetriever`; dense-only `search_hybrid` → `RetrievalResult` | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search` (linear-scan k-NN, cosine + Euclidean, dimension locking); serves as `HybridRetriever` fallback store | `vector_index.py` |
| Canonical Models | Pydantic v2 contracts: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult` (`formatted_evidence`, `source_labels`) | `models.py` |
| DocStore | SQLite WAL metadata store (`documents`, `pages`, `chunks`, `evidence_elements` tables, migrations v1–v2); SHA-256 dedup, chunk restore, per-page records | `doc_store.py` |
| DoclingReader | Structured extraction via Docling `DocumentConverter` (CPU-only, `do_ocr=False`, `do_table_structure=True`); graceful degrade to `PdfReader` (pypdf) | `docling_reader.py` |
| PdfReader | Legacy pypdf text extraction + `RecursiveCharacterTextSplitter` chunking (1000/200) with `{content, filename, page, chunk_id}` metadata | `pdf_reader.py` |
| Conditional OCR | RapidOCR fallback for low-text/scanned pages (INGEST-04) | `ocr_fallback.py` |
| VisualAnalyzer | Visual element detection, cropping, VLM analysis (VIS-01/02/03); results recorded via `DocStore.record_evidence_elements` | `visual_analyzer.py` |
| Upload Validation | Server-side `%PDF` header / size / page-limit checks, SHA-256 + `doc_id` derivation | `upload_validation.py` |
| Prompt Budget | Bounded context assembly: `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation, `sanitize_xml_boundary`, `estimate_tokens`, oldest-first history truncation | `prompt_budget.py` |
| Providers | `BaseModelProvider` ABC + `HealthStatus`/`ProviderCapabilities`; `LlamaCppProvider` (local Qwen3-VL 2B GGUF) and `GroqProvider` (cloud fallback) | `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py` |

## Pattern Overview

**Overall:** UI-orchestrated modular monolith with persistent hybrid retrieval and pluggable inference.

**Key Characteristics:**
- Fully local retrieval path (CPU embeddings + on-disk LanceDB/SQLite, zero network egress); only generation may call Groq Cloud.
- Single unified multi-document index — one `LocalEmbedding` + one `HybridRetriever` accumulate chunks from all uploads; `doc_id`/`chunk_id`/`filename` metadata preserves per-document attribution.
- One-retrieval-per-question: `main.py` fetches a single shared `RetrievalResult` and passes the identical object to prompt assembly and UI citations (RETR-04).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `str` fragments; `st.write_stream` renders incrementally and returns the full string.
- Graceful degradation everywhere: Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, llama-server → Groq → offline diagnostic.

## Layers

**Presentation / Orchestration:**
- Purpose: File upload, index-status display, conversational chat, streamed answer rendering with source chips.
- Location: `main.py`
- Contains: `st.set_page_config`, session-state init loop, `load_ai_model` (`@st.cache_resource`), sidebar upload/index loop, `st.chat_message` / `st.chat_input` / `st.write_stream`, `st.status` wrappers.
- Depends on: `local_llm.py:AiModel`, `local_embedding.py:LocalEmbedding`, `hybrid_retriever.py:HybridRetriever`, `docling_reader.py:DoclingReader`, `doc_store.py:DocStore`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion / Extraction:**
- Purpose: Bytes-in, canonical `Chunk`/`Page` records out, with per-page fault isolation.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader.extract_text/get_paragraphs/get_page_records`, `PdfReader.extract_text/get_paragraphs`, `apply_conditional_ocr`, `VisualAnalyzer.analyze_visual_elements`, `validate_pdf_bytes`.
- Depends on: `docling`, `pypdf`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `models.py:Chunk/Page`.
- Used by: `main.py:226-254` (upload path) and `local_llm.py:124-128` (on-the-fly fallback path).

**Retrieval:**
- Purpose: Semantic + keyword lookup fused into ranked, provenance-carrying evidence.
- Location: `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`
- Contains: `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid`, `compute_rrf`, `_bm25_search_fallback`, `LocalEmbedding._embed_one/get_embeddings/build_index/search`, `VectorIndex.add_vector/add_document/search` plus `_cosine_distance/_euclidean_distance`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding only), optional `lancedb` + `pyarrow`; fallback store is stdlib-only.
- Used by: `main.py:268-277` (build), `main.py:404-419` (query), `local_llm.py:141-157` (in-LLM fallback retrieval).

**Inference / Generation:**
- Purpose: Grounded answer synthesis with conversational memory and bounded context.
- Location: `local_llm.py:101-180`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`
- Contains: `AiModel._detect_provider/check_health/ask_a_question_from_pdf_stream`, `BaseModelProvider.stream_text`, `assemble_grounded_messages`.
- Depends on: `HybridRetriever` / `LocalEmbedding` (retrieval input), `models.py:RetrievalResult` (context input).
- Used by: `main.py:427-434`.

**Persistence:**
- Purpose: Survive restarts — document metadata, chunk text, vectors, evidence elements, disk cache.
- Location: `doc_store.py`, `hybrid_retriever.py:_save_fallback_store/_load_fallback_store`, `.cache/`
- Contains: `DocStore.upsert_document/record_page/record_chunks/record_evidence_elements/get_chunks_for_doc`, LanceDB `chunks` table (`chunk_id`, `doc_id`, `filename`, `page`, `content`, `vector`, `extraction`, `char_start/end`, `bbox_json`), `fallback_store.json`, `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`.
- Depends on: stdlib `sqlite3` (WAL mode), optional `lancedb`.
- Used by: `main.py:155` (open), `main.py:260-310` (record pages/chunks/manifest/cache), `main.py:199-213` (CR-01 restore after restart).

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted)

1. Upload + validate (`main.py:151-180`) — single `getvalue()` read per file; `MAX_FILE_MB` pre-check; `validate_pdf_bytes` (`upload_validation.py`) yields `doc_id`/`sha256`/`num_pages`.
2. Dedup via `DocStore.get_by_sha` (`main.py:183-214`) — session `doc_ids` set + SQLite `status == "indexed"` check; CR-01 path restores chunks from `DocStore.get_chunks_for_doc` into fresh `LocalEmbedding` + `HybridRetriever` when the session index is empty after restart.
3. Extraction (`main.py:222-264`) — `DoclingReader.extract_text` → `get_paragraphs`/`get_page_records`; `apply_conditional_ocr` patches scanned pages; `VisualAnalyzer.analyze_visual_elements` runs against the active provider and records elements; per-page `record_page` with `st.progress`; failed pages warn and continue.
4. Dual-index build (`main.py:266-277`) — `LocalEmbedding.build_index(paragraphs)` (in-memory dense) then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` (persistent LanceDB + fallback mirror with `chunk_id` dedup/upsert via `merge_insert`).
5. Persist (`main.py:279-310`) — `Chunk.model_validate` → `record_chunks`; `Document` → `upsert_document`; best-effort `.cache/<sha>/docling-1000-200-v1/*.json` write; session-state update + `st.rerun()`.

### Secondary Flow — Query (question → streamed grounded answer, RETR-04)

1. History-contextualized query (`main.py:392-402`) — `search_query = last_user_msg + " " + prompt` so follow-ups retrieve correctly; `history_to_pass` is the last 10 turns.
2. Single shared retrieval (`main.py:404-419`) — `active_retriever = hybrid_retriever or local_embedding`; if it exposes `search_hybrid`, one call `search_hybrid(search_query, k=5)` returns the canonical `RetrievalResult`; `sources = retrieval_res.source_labels()` for UI chips. Legacy branch (`search(..., k=10)`) only applies to retrievers without `search_hybrid`.
3. Hybrid fusion inside `HybridRetriever.search_hybrid` (`hybrid_retriever.py:507-612`) — embed query via CPU embedding fn → `search_dense` (LanceDB vector search, `candidate_pool = max(k*2, 10)`) + `search_fts` (LanceDB FTS → pure-Python BM25 fallback) → `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k mapped to `EvidenceSnippet` items (with `rank`, `dense_rank`, `fts_rank`, `score=RRF`, `bbox` rehydrated from `bbox_json`) → frozen `RetrievalResult(query, snippets, total_candidates, search_mode)`.
4. Shared-identity generation (`main.py:427-434` → `local_llm.py:121-122`) — the same `retrieval_result` object is passed to `ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_res)`; the LLM uses `retrieval_result.formatted_evidence()` (`[E1] (file, p. N)` blocks) directly, skipping any second retrieval. Inside-LLM fallback (`local_llm.py:130-159`) only runs when no pre-computed result is supplied.
5. Bounded prompt + stream (`local_llm.py:163-180`) — `assemble_grounded_messages` wraps context in `<document_context>` with XML sanitization and token budgeting against the provider's `context_window`; `provider.stream_text(...)` yields tokens; `st.write_stream` renders and returns the full string, appended to `chat_history` with `sources` (`main.py:434-441`).

**State Management:**
- `st.session_state` (per-browser-session, survives full-script reruns): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict` (filename → `doc_id`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None`, `hybrid_retriever: HybridRetriever | None`, `chat_history: list` of `{role, content, sources}` — initialised in `main.py:53-62`. `Clear All` closes the retriever, resets all keys, calls `st.rerun()` (`main.py:132-141`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` (`main.py:70-78`) constructs `AiModel` once; every rerun/session reuses it. The embedding model is NOT cached — `LocalEmbedding`/`SentenceTransformer` lives in session state, so each browser session loads its own copy.
- On-disk state: SQLite `data/documents.db` (DocStore), LanceDB `data/lancedb/` (or `fallback_store.json` there without LanceDB), `.cache/<sha256>/docling-1000-200-v1/`.

## Key Abstractions

**Chunk (unit of retrieval):**
- Purpose: Text plus provenance metadata threaded through every layer.
- Examples: produced in `docling_reader.py` / `pdf_reader.py:51-56`, validated as `models.py:Chunk`, stored in `vector_index.py:94-95` and LanceDB rows (`hybrid_retriever.py:296-309`), restored from `doc_store.py:303-325`.
- Pattern: Frozen Pydantic model — `content`, `filename`, `page`, `chunk_id`, `doc_id` required; `char_start`/`char_end`/`bbox`/`extraction`/`embedding_model` optional. `VectorIndex` requires the `content` key; `Chunk.chunk_id` is the LanceDB upsert key.

**RetrievalResult + EvidenceSnippet (shared prompt/UI contract, RETR-04):**
- Purpose: Single immutable container consumed identically by LLM prompt assembly and UI citation rendering — eliminates double retrieval and prompt/citation drift.
- Examples: constructed in `hybrid_retriever.py:607-612` and `local_embedding.py:104-109`; consumed in `local_llm.py:121-122` (`formatted_evidence`) and `main.py:410-411` (`source_labels`); stored as `AiModel.last_retrieval_result` (`local_llm.py:161`).
- Pattern: Frozen Pydantic models. `EvidenceSnippet` carries `content/doc_id/filename/page/chunk_id/score/rank/dense_rank/fts_rank/extraction/char_start/char_end/bbox` (`models.py:141-167`). `RetrievalResult` carries `query/snippets/total_candidates/search_mode ∈ {hybrid, dense, fts, fallback}` with `formatted_evidence()` (`[E1] (name, p. N)` blocks) and `source_labels()` (deduped `filename (p. N)` chips) (`models.py:170-204`).

**Unified multi-document index:**
- Purpose: One `search_hybrid` call spans all uploaded documents.
- Examples: `main.py:268-277` (incremental `build_index` + `index_chunks` per file), `main.py:356-359` (total-chunk aggregation).
- Pattern: Append-only growth with `chunk_id` upsert dedup (`hybrid_retriever.py:267-280`); no per-document isolation; deletion only via `delete_document(doc_id)` or full Clear All reset.

**RRF fusion:**
- Purpose: Combine dense semantic ranking and BM25 keyword ranking without score calibration.
- Examples: `hybrid_retriever.py:31-76` (`compute_rrf`, `DEFAULT_RRF_K = 60`), wired in `hybrid_retriever.py:576-577`.
- Pattern: `RRF(d) = Σ 1/(k_rrf + rank_m(d))`; returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score; `search_mode` records which modalities contributed (`hybrid_retriever.py:567-574`).

**Token-stream generator:**
- Purpose: Decouple token production (provider) from rendering (Streamlit).
- Examples: `local_llm.py:101-180` (producer), `main.py:434` (consumer via `st.write_stream`).
- Pattern: Generator yielding `str` fragments; caller never buffers.

## Entry Points

**Streamlit app (sole runtime entry):**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` first (`main.py:39-44`); session-state init; cached model load; sidebar upload/index loop; main-area chat loop.

**On-the-fly Q&A fallback (legacy, not exercised by UI):**
- Location: `local_llm.py:124-128`
- Triggers: Calling `ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None` and no `retrieval_result`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then retrieval + generation. `main.py` always passes an existing retriever and `pdf_path=""`, so this path is dormant in production.

**Benchmark script:**
- Location: `scripts/benchmark_baseline.py`
- Triggers: Manual invocation.
- Responsibilities: Baseline retrieval/generation benchmarking (see `STRUCTURE.md`).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom per interaction; long work (model load, extraction, embedding) blocks and is masked with `st.status` spinners. Token streaming is incremental rendering, not background threading.
- **VRAM envelope:** Embeddings pinned to CPU (`device="cpu"` in `local_embedding.py:24-25,40`); only one LLM/VLM active at a time via the provider abstraction; 4K context default with 1024 reserved output tokens (`prompt_budget.py:53-68`).
- **Global state:** `st.cache_resource`-cached `AiModel` + provider client shared across sessions (`main.py:70-78`); per-session `LocalEmbedding` + `SentenceTransformer` + `HybridRetriever` + `VectorIndex` vectors in `st.session_state`. No other module singletons — `VectorIndex` internals are instance-scoped (`vector_index.py:29-33`); `HybridRetriever` handles are instance-scoped (`hybrid_retriever.py:100-110`).
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py` → `prompt_budget.py`, `model_provider.py`; `docling_reader.py` → `pdf_reader.py`; `models.py` and `vector_index.py` have no project imports.
- **Persistence duality:** Every indexed chunk is written twice — in-memory `LocalEmbedding.store` and persistent `HybridRetriever` (LanceDB or `fallback_store.json`). The two are kept in sync only by the paired write in `main.py:268-277` and the CR-01 restore path; direct writes to one store bypass the other.
- **Linear-scan fallback:** Without LanceDB, `VectorIndex.search` is O(n) per query (`vector_index.py:130-136`); BM25 fallback is O(N·|Q|) with precomputed document frequencies (`hybrid_retriever.py:449-476`).

## Anti-Patterns

### Dual-store write coupling in the UI layer

**What happens:** `main.py:268-277` manually writes every chunk batch to both `LocalEmbedding.build_index` and `HybridRetriever.index_chunks` in sequence.
**Why it's wrong:** The two stores can diverge — a failure between the two writes, or any future code path that writes to only one store, leaves in-memory and on-disk indexes inconsistent.
**Do this instead:** Encapsulate the paired write behind a single `index_chunks` façade (e.g. on `HybridRetriever`, which already mirrors into its fallback `VectorIndex` at `hybrid_retriever.py:267-280`), so callers cannot partially index. Reference the existing mirror logic as the consolidation point.

### Dormant `pdf_path` / on-the-fly indexing parameter

**What happens:** `ask_a_question_from_pdf_stream(pdf_path="", ...)` still accepts a path and can build a throwaway `PdfReader` + `LocalEmbedding` (`local_llm.py:124-128`); `main.py:428` always passes `pdf_path=""` with a live retriever.
**Why it's wrong:** Dead surface area that suggests an indexing path the UI never uses; risks confusion about which index answers a question.
**Do this instead:** Keep the parameter for backward compatibility (tests in `tests/test_local_llm.py` cover it) but treat `retrieval_result`/`local_embedding` as the canonical inputs — which is already the documented precedence in `local_llm.py:121-123`.

## Error Handling

**Strategy:** Validate at boundaries, isolate per-file/per-page failures, degrade gracefully across backends.

**Patterns:**
- Per-file upload guard — `try/except` around validation, `DoclingReader` extraction, OCR, and visual analysis in `main.py:176-258` shows `st.error` and `continue`s, so one corrupt PDF never aborts the batch; per-page `status == "failed"` records warn individually (`main.py:260-264`).
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0` (`vector_index.py:26-27, 50-63, 76-87, 121-125`); `HybridRetriever.index_chunks` raises on chunk/embedding mismatch or missing embedding source (`hybrid_retriever.py:252-265`); Pydantic models reject bad `doc_id`/`sha256`/coordinates (`models.py:47-51, 109-112, 135-138, 163-167`).
- Backend degradation with logging — LanceDB init/search/FTS failures log warnings and fall back to in-memory/BM25 rather than raising (`hybrid_retriever.py:112-124, 389-403, 491-505`); Docling import/conversion failure degrades to pypdf (`docling_reader.py:22-31`); provider detection falls back to an offline diagnostic provider (`local_llm.py:48-69`).
- No retry/timeout handling on the generation stream itself — network or rate-limit errors during `provider.stream_text` propagate to the `try/except` around the stream call in `main.py:426-450`, which renders an inline error and records an interruption note in history rather than crashing.

## Cross-Cutting Concerns

**Logging:** `logging` module in backend services (`logger.info/warning` in `hybrid_retriever.py`, `local_embedding.py`, `docling_reader.py`); developer `print` for migration notices (`doc_store.py:129`); user-facing feedback exclusively via Streamlit (`st.error`/`st.info`/`st.success`/`st.status`/`st.warning` in `main.py`).
**Validation:** `upload_validation.py` (bytes/header/size/page limits) at the edge; Pydantic v2 enforcement in `models.py` for all persisted/retrieved records; `VectorIndex` type/dimension guards.
**Authentication:** Provider-key resolution inside `GroqProvider` (env/`st.secrets`); local llama-server needs no credentials. See `INTEGRATIONS.md`.
**Prompt safety:** `sanitize_xml_boundary` neutralizes `</document_context>` spoofing; `SYSTEM_GROUNDING_TEMPLATE` instructs the model to treat all document text as untrusted data (`prompt_budget.py:11-31`).

---

*Architecture analysis: 2026-10-11*
