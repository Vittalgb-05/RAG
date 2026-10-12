<!-- refreshed: 2026-10-12 -->
# Architecture

**Analysis Date:** 2026-10-12

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              Streamlit UI / Orchestrator                     │
│  `main.py` — tab_chat (grounded QA) + tab_summary            │
│  (summarizer) + sidebar upload + streaming render            │
├──────────────────┬──────────────────┬───────────────────────┤
│  Ingestion       │  Hybrid Retrieval│  Inference + Summary   │
│  `docling_reader │  `hybrid_        │  `local_llm.py`        │
│  .py`            │  retriever.py`   │  `model_provider.py`   │
│  `pdf_reader.py` │  `local_         │  `groq_provider.py`    │
│  `ocr_fallback   │  embedding.py`   │  `llama_cpp_provider   │
│  .py`            │  `vector_index   │  .py`                  │
│  `visual_        │  .py`            │  `prompt_budget.py`    │
│  analyzer.py`    │                  │  `summarizer.py`       │
│                  │                  │  `citation_validator   │
│                  │                  │  .py`                  │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence Layer                                           │
│  `doc_store.py` (SQLite `data/documents.db`: documents,     │
│   pages, chunks, evidence_elements, document_summaries v3)   │
│  `hybrid_retriever.py` (LanceDB `data/lancedb`) + `.cache/` │
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
| Streamlit App | Page config, session-state init, sidebar (model health + PDF upload + indexed-docs view + Clear All incl. `summary_*` purge), `st.tabs` wiring (`tab_chat` / `tab_summary`), chat replay with badges/drawer, summarizer tab (selectbox + radio + force-refresh), single shared `RetrievalResult` fetch, streaming render | `main.py` |
| AiModel | Provider auto-detection (llama-server → Groq), health re-probing, RAG orchestration, `retrieval_result`-first prompt assembly via `assemble_grounded_messages`, token-stream delegation, `validate_response` citation-validation façade | `local_llm.py` |
| Summarizer | Hierarchical multi-profile summarization: profile dispatch, fast-path vs map-reduce selection, sequential map → consolidate → reduce, `(p. X)` citation preservation, `SummaryResult` construction, `DocStore` cache check/save | `summarizer.py` |
| CitationValidator | Post-generation grounding gate: `extract_citations` (`[En]`), `is_abstention`, `validate_citations` → frozen `CitationVerificationResult` (≥95% precision, empty-response invalid, abstention-with-citations invalid) | `citation_validator.py` |
| HybridRetriever | Persistent hybrid retrieval: LanceDB dense vectors + FTS index, pure-Python BM25 fallback, RRF fusion (`compute_rrf`), `search_hybrid` → canonical `RetrievalResult`; disk-backed JSON fallback when LanceDB missing | `hybrid_retriever.py` |
| LocalEmbedding | CPU-pinned `SentenceTransformer` (`all-MiniLM-L6-v2`, 384-dim L2-normalised) wrapper; batch `build_index`, `_embed_one` query vectorizer shared with `HybridRetriever`; dense-only `search_hybrid` → `RetrievalResult` | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search` (linear-scan k-NN, cosine + Euclidean, dimension locking); serves as `HybridRetriever` fallback store | `vector_index.py` |
| Canonical Models | Pydantic v2 contracts: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult` (`formatted_evidence`, `source_labels`), `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` | `models.py` |
| DocStore | SQLite WAL metadata store (`documents`, `pages`, `chunks`, `evidence_elements` tables, `document_summaries` v3 table; migrations v1–v3); SHA-256 dedup, chunk restore, per-page records, `save_summary`/`get_summary`/`list_summaries_for_doc`/`delete_summaries_for_doc` | `doc_store.py` |
| DoclingReader | Structured extraction via Docling `DocumentConverter` (CPU-only, `do_ocr=False`, `do_table_structure=True`); graceful degrade to `PdfReader` (pypdf) | `docling_reader.py` |
| PdfReader | Legacy pypdf text extraction + `RecursiveCharacterTextSplitter` chunking (1000/200) with `{content, filename, page, chunk_id}` metadata | `pdf_reader.py` |
| Conditional OCR | RapidOCR fallback for low-text/scanned pages (INGEST-04) | `ocr_fallback.py` |
| VisualAnalyzer | Visual element detection, cropping, VLM analysis (VIS-01/02/03); results recorded via `DocStore.record_evidence_elements` | `visual_analyzer.py` |
| Upload Validation | Server-side `%PDF` header / size / page-limit checks, SHA-256 + `doc_id` derivation | `upload_validation.py` |
| Prompt Budget | Bounded context assembly: `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`[E1]` citation rules + abstention sentence), `sanitize_xml_boundary`, `estimate_tokens`, oldest-first history truncation | `prompt_budget.py` |
| Providers | `BaseModelProvider` ABC + `HealthStatus`/`ProviderCapabilities`; `LlamaCppProvider` (local Qwen3-VL 2B GGUF) and `GroqProvider` (cloud fallback) | `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py` |

## Pattern Overview

**Overall:** UI-orchestrated modular monolith with persistent hybrid retrieval, pluggable inference, post-generation citation validation, and cached hierarchical summarization.

**Key Characteristics:**
- Fully local retrieval path (CPU embeddings + on-disk LanceDB/SQLite, zero network egress); only generation may call Groq Cloud.
- Single unified multi-document index — one `LocalEmbedding` + one `HybridRetriever` accumulate chunks from all uploads; `doc_id`/`chunk_id`/`filename` metadata preserves per-document attribution.
- One-retrieval-per-question: `main.py` fetches a single shared `RetrievalResult` and passes the identical object to prompt assembly, generation, validation, and UI citations (RETR-04).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `str` fragments; `st.write_stream` renders incrementally and returns the full string for post-hoc validation.
- Validate-after-stream: citations are checked on the completed string via `AiModel.validate_response` → `validate_citations`; the `CitationVerificationResult` is persisted alongside the turn in `chat_history` and re-rendered on replay.
- Cache-before-compute summarization: `Summarizer.summarize_document` checks `DocStore.get_summary(sha256, profile, model_version)` before any LLM call; cache key is `(sha256, profile)` with model-version invalidation.
- Graceful degradation everywhere: Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, llama-server → Groq → offline diagnostic.

## Layers

**Presentation / Orchestration:**
- Purpose: File upload, index-status display, tabbed chat + summarizer UX, streamed answer rendering with verification badges and evidence drawers.
- Location: `main.py`
- Contains: `st.set_page_config` (`main.py:40-45`), session-state init loop (`main.py:54-63`), `load_ai_model` (`@st.cache_resource`, `main.py:71-79`), sidebar upload/index loop (`main.py:159-353`), `st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])` (`main.py:360`), chat tab (`main.py:362-534`), summary tab (`main.py:537-622`).
- Depends on: `local_llm.py:AiModel`, `local_embedding.py:LocalEmbedding`, `hybrid_retriever.py:HybridRetriever`, `docling_reader.py:DoclingReader`, `doc_store.py:DocStore`, `summarizer.py:Summarizer`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion / Extraction:**
- Purpose: Bytes-in, canonical `Chunk`/`Page` records out, with per-page fault isolation.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader.extract_text/get_paragraphs/get_page_records`, `PdfReader.extract_text/get_paragraphs`, `apply_conditional_ocr`, `VisualAnalyzer.analyze_visual_elements`, `validate_pdf_bytes`.
- Depends on: `docling`, `pypdf`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `models.py:Chunk/Page`.
- Used by: `main.py:226-264` (upload path) and `local_llm.py:134-138` (on-the-fly fallback path).

**Retrieval:**
- Purpose: Semantic + keyword lookup fused into ranked, provenance-carrying evidence.
- Location: `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`
- Contains: `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid`, `compute_rrf`, `_bm25_search_fallback`, `LocalEmbedding._embed_one/get_embeddings/build_index/search`, `VectorIndex.add_vector/add_document/search` plus `_cosine_distance/_euclidean_distance`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding only), optional `lancedb` + `pyarrow`; fallback store is stdlib-only.
- Used by: `main.py:276-285` (build), `main.py:450-469` (query), `local_llm.py:151-169` (in-LLM fallback retrieval).

**Inference / Generation:**
- Purpose: Grounded answer synthesis with conversational memory and bounded context.
- Location: `local_llm.py:111-190`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`
- Contains: `AiModel._detect_provider/check_health/ask_a_question_from_pdf_stream/validate_response`, `BaseModelProvider.stream_text/generate_text`, `assemble_grounded_messages`.
- Depends on: `HybridRetriever` / `LocalEmbedding` (retrieval input), `models.py:RetrievalResult` (context input), `citation_validator.py:validate_citations` (post-check).
- Used by: `main.py:474-481` (chat stream), `summarizer.py:225-230,260-265,276-283,293-298` (summary map/reduce via `provider.generate_text`).

**Summarization:**
- Purpose: Bounded, VRAM-safe, profile-shaped document synthesis with `(p. X)` citations and persistent caching.
- Location: `summarizer.py:152-418`
- Contains: `Summarizer.__init__`, `_bundle_pages` (`summarizer.py:165-193`), `_format_page_batch` (`summarizer.py:195-202`), `_summarize_single_pass` (`summarizer.py:204-230`), `_summarize_map_reduce` (`summarizer.py:232-298`), `summarize_document` (`summarizer.py:300-418`), `extract_page_references` (`summarizer.py:135-149`), `PROFILE_SYSTEM_INSTRUCTIONS` (`summarizer.py:30-104`), `MAP_PROMPT_TEMPLATE` / `REDUCE_PROMPT_TEMPLATE` (`summarizer.py:106-132`), `FAST_PATH_TOKEN_LIMIT = 2500` / `MAX_BATCH_TOKENS = 2000` (`summarizer.py:27-28`).
- Depends on: `model_provider.py:BaseModelProvider` (`generate_text`, `get_capabilities`), `models.py:Page/SummaryResult/VALID_SUMMARY_PROFILES`, `prompt_budget.py:estimate_tokens/sanitize_xml_boundary`, `doc_store.py:DocStore` (optional cache backend).
- Used by: `main.py:586-594` (summary tab generation).

**Citation Validation:**
- Purpose: Deterministic post-generation grounding gate independent of any LLM.
- Location: `citation_validator.py:52-181`
- Contains: `CITATION_REGEX` (`citation_validator.py:16`), `CANONICAL_ABSTENTION_MARKERS` (`citation_validator.py:18-32`), `CitationVerificationResult` (`citation_validator.py:35-49`), `extract_citations` (`citation_validator.py:52-65`), `is_abstention` (`citation_validator.py:68-78`), `validate_citations` (`citation_validator.py:81-181`).
- Depends on: `models.py:RetrievalResult` (snippet-count bound only), stdlib `re`, Pydantic v2.
- Used by: `local_llm.py:192-210` (`AiModel.validate_response`), exercised in `main.py:484`.

**Persistence:**
- Purpose: Survive restarts — document metadata, chunk text, vectors, evidence elements, summaries, disk cache.
- Location: `doc_store.py`, `hybrid_retriever.py:_save_fallback_store/_load_fallback_store`, `.cache/`
- Contains: `DocStore.upsert_document/record_page/record_chunks/record_evidence_elements/get_chunks_for_doc/save_summary/get_summary/list_summaries_for_doc/delete_summaries_for_doc`, `SCHEMA_V3_DDL` `document_summaries` table (`doc_store.py:73-94`, `UNIQUE(sha256, profile)`, FK `doc_id → documents(doc_id) ON DELETE CASCADE`), `MIGRATIONS = {1,2,3}` (`doc_store.py:96-100`), LanceDB `chunks` table, `fallback_store.json`, `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`.
- Depends on: stdlib `sqlite3` (WAL mode), optional `lancedb`.
- Used by: `main.py:83` (open), `main.py:268-318` (record pages/chunks/manifest/cache), `main.py:206-221` (CR-01 restore after restart), `main.py:602-605` (summary cache read), `summarizer.py:331-335,414-416` (summary cache check/save).

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted)

1. Upload + validate (`main.py:164-191`) — single `getvalue()` read per file; `MAX_FILE_MB` pre-check; `validate_pdf_bytes` (`upload_validation.py`) yields `doc_id`/`sha256`/`num_pages`.
2. Dedup via `DocStore.get_by_sha` (`main.py:190-222`) — session `doc_ids` set + SQLite `status == "indexed"` check; CR-01 path restores chunks from `DocStore.get_chunks_for_doc` into fresh `LocalEmbedding` + `HybridRetriever` when the session index is empty after restart.
3. Extraction (`main.py:230-266`) — `DoclingReader.extract_text` → `get_paragraphs`/`get_page_records`; `apply_conditional_ocr` patches scanned pages; `VisualAnalyzer.analyze_visual_elements` runs against the active provider and records elements; per-page `record_page` with `st.progress`; failed pages warn and continue.
4. Dual-index build (`main.py:274-285`) — `LocalEmbedding.build_index(paragraphs)` (in-memory dense) then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` (persistent LanceDB + fallback mirror with `chunk_id` dedup/upsert via `merge_insert`).
5. Persist (`main.py:287-318`) — `Chunk.model_validate` → `record_chunks`; `Document` → `upsert_document`; best-effort `.cache/<sha>/docling-1000-200-v1/*.json` write; session-state update + `st.rerun()`.

### Grounded QA Flow (question → streamed answer → validated citations → badges/drawer)

1. History-contextualized query (`main.py:438-448`) — `search_query = last_user_msg + " " + prompt` so follow-ups retrieve correctly; `history_to_pass` is the last 10 turns.
2. Single shared retrieval (`main.py:450-469`) — `active_retriever = hybrid_retriever or local_embedding`; if it exposes `search_hybrid`, one call `search_hybrid(search_query, k=5)` returns the canonical `RetrievalResult`; `sources = retrieval_res.source_labels()` plus `snippets_data = [s.model_dump() for s in retrieval_res.snippets]` (`main.py:467-469`). Legacy branch (`search(..., k=10)`) only applies to retrievers without `search_hybrid`.
3. Hybrid fusion inside `HybridRetriever.search_hybrid` (`hybrid_retriever.py:507-612`) — embed query via CPU embedding fn → `search_dense` (LanceDB vector search, `candidate_pool = max(k*2, 10)`) + `search_fts` (LanceDB FTS → pure-Python BM25 fallback) → `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k mapped to `EvidenceSnippet` items (with `rank`, `dense_rank`, `fts_rank`, `score=RRF`, `bbox` rehydrated from `bbox_json`) → frozen `RetrievalResult(query, snippets, total_candidates, search_mode)`.
4. Shared-identity generation (`main.py:474-481` → `local_llm.py:131-132`) — the same `retrieval_result` object is passed to `ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_res)`; the LLM uses `retrieval_result.formatted_evidence()` (`[E1] (file, p. N)` blocks) directly, skipping any second retrieval. Inside-LLM fallback (`local_llm.py:140-169`) only runs when no pre-computed result is supplied.
5. Bounded grounded prompt + stream (`local_llm.py:173-190`) — `assemble_grounded_messages` wraps context in `<document_context>` with the `[E1]`/`[E2]` citation rules and abstention sentence (`prompt_budget.py:12-22`), XML sanitization and token budgeting against the provider's `context_window`; `provider.stream_text(...)` yields tokens; `st.write_stream` renders and returns the full string (`main.py:481`).
6. Citation validation (`main.py:484` → `local_llm.py:192-210` → `citation_validator.py:81-181`) — `ai_model.validate_response(full_response, retrieval_res)` resolves the active result (explicit arg wins, else `last_retrieval_result`), runs `validate_citations`: empty text → `is_valid=False, precision=0.0`; abstention text + zero citations → `is_valid=True, precision=1.0, abstention_detected=True`; abstention + citations → invalid; otherwise precision = `valid_ranks / total_claimed` with `is_valid = precision >= 0.95` against `len(retrieval_result.snippets)` as the rank bound.
7. Badge + drawer render (`main.py:485-513`, replay `main.py:380-415`) — abstention → `ℹ️ Explicit abstention` caption; valid → `✅ Verified Grounding (P% citation precision)`; invalid → `⚠️ Unverified Citations (P%)`. Evidence chips `[E{rank}] filename (p. N)` plus `🔍 Cited Evidence & Source Context` expander iterate `snippets_data` (header with rank/filename/page/score, blockquoted content, optional `📐 Region: x0/y0/x1/y1` bbox caption). The turn is appended to `chat_history` with `{role, content, sources, verification, snippets}` (`main.py:515-523`); the exception path records an interruption note with `verification: None` (`main.py:524-534`).

### Summarization Flow (profile → map-reduce → cache → summary tab)

1. Tab wiring + selection (`main.py:537-580`) — `tab_summary` shows selectbox over `sorted(indexed_files)`, resolves `doc_id`/`sha256` from `document_metadata` with `doc_store.get_document` fallback (`main.py:544-552`), radio over the five `profile_map` keys (`overview`, `detailed`, `study_notes`, `tables_figures`, `findings`), `Generate Summary` button (disabled when inference unhealthy) + `Force re-generate` checkbox. Per-doc/profile session key `summary_{doc_id}_{profile}` (`main.py:580`).
2. Cache check (`summarizer.py:330-335`) — `summarize_document(doc_id, sha256, profile, force_refresh)` validates `profile ∈ VALID_SUMMARY_PROFILES` (`summarizer.py:322-325`), reads `provider.get_capabilities().model_name` as `model_version`, and returns `DocStore.get_summary(sha256, profile, model_version=model_version)` immediately on hit (zero provider calls). `get_summary` returns `None` on row miss or model-version mismatch (`doc_store.py:494-499`) and hydrates `SummaryResult(..., cached=True)` otherwise (`doc_store.py:504-514`).
3. Page resolution (`summarizer.py:337-380`) — if `pages is None`, reconstructs `Page` records from `chunks` arg or `doc_store.get_chunks_for_doc(doc_id)` grouped by page (`summarizer.py:342-359`); if caller-supplied `Page` records lack `page_text`, enriches from stored chunks (`summarizer.py:362-377`). Filters to pages with non-blank `page_text`; raises `ValueError` when none is extractable (`summarizer.py:380-382`). `main.py:588-593` calls with `pages=None`, so the DocStore-chunks path is the live one.
4. Fast path vs map-reduce (`summarizer.py:384-392`) — `total_tokens = Σ estimate_tokens(page_text)`; `≤ FAST_PATH_TOKEN_LIMIT (2500)` → `_summarize_single_pass` (one `provider.generate_text` with the profile's `PROFILE_SYSTEM_INSTRUCTIONS` + `<document_context>` page batch, `max_tokens=1500, temperature=0.2`); above → `_summarize_map_reduce`.
5. Map stage (`summarizer.py:244-266`) — `_bundle_pages(pages, MAX_BATCH_TOKENS=2000)` packs sequential pages by `estimate_tokens` (`summarizer.py:165-193`); each batch is rendered by `_format_page_batch` as `--- Page N ---` sections with `sanitize_xml_boundary` (`summarizer.py:195-202`) and sent through `MAP_PROMPT_TEMPLATE` (page-range + `(p. X)` citation mandate) with `max_tokens=800, temperature=0.2`. Executes strictly sequentially to respect the single-active-LLM VRAM constraint.
6. Consolidation + reduce (`summarizer.py:268-298`) — intermediates joined with `\n\n---\n\n`; if combined tokens exceed `FAST_PATH_TOKEN_LIMIT` and there are >3 intermediates, two half-consolidation `generate_text` calls (`max_tokens=1000`) precede the final `REDUCE_PROMPT_TEMPLATE` synthesis (citation-preservation instructions) under the profile system prompt (`max_tokens=1500, temperature=0.2`).
7. Reference extraction + persist (`summarizer.py:394-416`) — `extract_page_references(summary_text, max_page=...)` parses `(p. N)`/`(Page N)` via regex, dedups, sorts, clamps to `max_page` (`summarizer.py:135-149`); builds `SummaryResult(summary_id=summ_<hex16>, ..., cached=False)` (`summarizer.py:401-411`); `doc_store.save_summary(result)` upserts on `ON CONFLICT(sha256, profile)` (`doc_store.py:436-463`). Session cache `st.session_state[summary_cache_key] = summary_obj.model_dump()` (`main.py:594`).
8. Display (`main.py:600-622`) — prefers the session value, falls back to `doc_store.get_summary(selected_sha, selected_profile)` without model-version pin (`main.py:602-605`); cached rows show `⚡ Loaded from persistent SQLite cache (DocStore v3)`, fresh ones `✨ Generated fresh with {model_version}`; summary markdown renders verbatim, then `📄 Referenced Source Pages` expander lists `Page N` chips + `created_at`.

**State Management:**
- `st.session_state` (per-browser-session, survives full-script reruns): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict` (filename → `doc_id`/`sha256`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None`, `hybrid_retriever: HybridRetriever | None`, `chat_history: list` of `{role, content, sources, verification, snippets}` — initialised in `main.py:54-63`; plus dynamic `summary_{doc_id}_{profile}` keys holding `SummaryResult.model_dump()` dicts. `Clear All` closes the retriever, resets all keys, deletes every `summary_*` key, calls `st.rerun()` (`main.py:137-149`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` (`main.py:71-79`) constructs `AiModel` once; every rerun/session reuses it. The embedding model is NOT cached — `LocalEmbedding`/`SentenceTransformer` lives in session state, so each browser session loads its own copy.
- `AiModel` transient grounding state: `last_retrieval_result` (set on every `ask_a_question_from_pdf_stream`, `local_llm.py:171`) and `last_verification_result` (set on every `validate_response`, `local_llm.py:209`). Process-singleton caveat documented in `local_llm.py:20-28` — always pass an explicit `retrieval_result` to `validate_response` to avoid cross-session contamination.
- On-disk state: SQLite `data/documents.db` (DocStore incl. `document_summaries`), LanceDB `data/lancedb/` (or `fallback_store.json` there without LanceDB), `.cache/<sha256>/docling-1000-200-v1/`.

## Key Abstractions

**Chunk (unit of retrieval):**
- Purpose: Text plus provenance metadata threaded through every layer.
- Examples: produced in `docling_reader.py` / `pdf_reader.py:51-56`, validated as `models.py:Chunk`, stored in `vector_index.py:94-95` and LanceDB rows (`hybrid_retriever.py:296-309`), restored from `doc_store.py:303-325`.
- Pattern: Frozen Pydantic model — `content`, `filename`, `page`, `chunk_id`, `doc_id` required; `char_start`/`char_end`/`bbox`/`extraction`/`embedding_model` optional. `VectorIndex` requires the `content` key; `Chunk.chunk_id` is the LanceDB upsert key.

**RetrievalResult + EvidenceSnippet (shared prompt/UI/validation contract, RETR-04):**
- Purpose: Single immutable container consumed identically by LLM prompt assembly, UI citation rendering, and citation validation — eliminates double retrieval and prompt/citation/validation drift.
- Examples: constructed in `hybrid_retriever.py:607-612` and `local_embedding.py:104-109`; consumed in `local_llm.py:131-132` (`formatted_evidence`), `main.py:456-457` (`source_labels`), `main.py:467-469` (`model_dump` snippets), `citation_validator.py:114` (rank bound).
- Pattern: Frozen Pydantic models. `EvidenceSnippet` carries `content/doc_id/filename/page/chunk_id/score/rank/dense_rank/fts_rank/extraction/char_start/char_end/bbox` (`models.py:142-168`). `RetrievalResult` carries `query/snippets/total_candidates/search_mode ∈ {hybrid, dense, fts, fallback}` with `formatted_evidence()` (`[E1] (name, p. N)` blocks) and `source_labels()` (deduped `filename (p. N)` chips) (`models.py:171-205`).

**CitationVerificationResult (grounding verdict):**
- Purpose: Deterministic, LLM-independent verdict rendered as badges and persisted per turn.
- Examples: produced in `citation_validator.py:96-181`, stored via `local_llm.py:208-210` (`last_verification_result`), persisted in `chat_history` (`main.py:515-523`), rendered in `main.py:382-391` + `main.py:485-490`.
- Pattern: Frozen Pydantic model (`citation_validator.py:35-49`) — `is_valid`, `precision ∈ [0,1]`, `total_citations`, `valid_citations`/`hallucinated_citations` tags, `cited_ranks`, `abstention_detected`, `message`. Threshold `precision >= 0.95` (`citation_validator.py:163`).

**SummaryResult + SummaryProfile (cached synthesis contract):**
- Purpose: Profile-shaped markdown plus machine-readable page references and cache identity.
- Examples: produced in `summarizer.py:401-411`, persisted via `doc_store.py:425-463`, read in `summarizer.py:331-335` and `main.py:602-605`, rendered in `main.py:607-622`.
- Pattern: `SummaryProfile = Literal["overview","detailed","study_notes","tables_figures","findings"]`, `VALID_SUMMARY_PROFILES` tuple (`models.py:208-209`); `SummaryResult` carries `summary_id (summ_*)`, `doc_id (doc_*)`, `sha256`, `profile`, `summary_text`, `page_references: list[int]`, `created_at`, `model_version`, `cached` (`models.py:212-235`). SQLite row mirrors every field with `page_references_json` (`doc_store.py:73-94`).

**Unified multi-document index:**
- Purpose: One `search_hybrid` call spans all uploaded documents.
- Examples: `main.py:276-285` (incremental `build_index` + `index_chunks` per file), `main.py:368` (total-chunk aggregation).
- Pattern: Append-only growth with `chunk_id` upsert dedup (`hybrid_retriever.py:267-280`); no per-document isolation; deletion only via `delete_document(doc_id)` or full Clear All reset. Summarization is the exception: it scopes to one `doc_id` via DocStore chunk lookup.

**RRF fusion:**
- Purpose: Combine dense semantic ranking and BM25 keyword ranking without score calibration.
- Examples: `hybrid_retriever.py:31-76` (`compute_rrf`, `DEFAULT_RRF_K = 60`), wired in `hybrid_retriever.py:576-577`.
- Pattern: `RRF(d) = Σ 1/(k_rrf + rank_m(d))`; returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score; `search_mode` records which modalities contributed (`hybrid_retriever.py:567-574`).

**Token-stream generator:**
- Purpose: Decouple token production (provider) from rendering (Streamlit).
- Examples: `local_llm.py:111-190` (producer), `main.py:474-481` (consumer via `st.write_stream`).
- Pattern: Generator yielding `str` fragments; caller never buffers. Summarization uses the non-streaming sibling `provider.generate_text` instead (`summarizer.py`).

**Map-reduce page bundling:**
- Purpose: Fit arbitrarily long documents into a 4K context window without parallel LLM residency.
- Examples: `summarizer.py:165-193` (`_bundle_pages`), `summarizer.py:232-298` (`_summarize_map_reduce`).
- Pattern: Greedy sequential packing by `estimate_tokens` against `MAX_BATCH_TOKENS`; map → optional half-consolidation → reduce, every stage carrying `(p. X)` forward.

## Entry Points

**Streamlit app (sole runtime entry):**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` first (`main.py:40-45`); session-state init; cached model load; sidebar upload/index loop; `st.tabs` chat + summarizer loops.

**Chat tab (grounded QA):**
- Location: `main.py:362-534` (`with tab_chat:`)
- Triggers: Selecting `💬 Ask Your Document`; submitting `st.chat_input` (`main.py:424-427`, disabled until an index exists and inference is healthy).
- Responsibilities: History replay with badges/drawer, single shared `search_hybrid(k=5)`, `ask_a_question_from_pdf_stream` + `st.write_stream`, `validate_response`, live badge/drawer, `chat_history` append.

**Summary tab (grounded summarization):**
- Location: `main.py:537-622` (`with tab_summary:`)
- Triggers: Selecting `📑 Document Summarizer`; pressing `Generate Summary` (`main.py:570-576`).
- Responsibilities: Document selectbox, 5-profile radio, force-refresh flag, `Summarizer(provider=ai_model.provider, doc_store=doc_store).summarize_document(...)` under `st.status`, session + SQLite cache display with page-reference expander.

**On-the-fly Q&A fallback (legacy, not exercised by UI):**
- Location: `local_llm.py:134-138`
- Triggers: Calling `ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None` and no `retrieval_result`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then retrieval + generation. `main.py` always passes an existing retriever and `pdf_path=""`, so this path is dormant in production.

**Benchmark script:**
- Location: `scripts/benchmark_baseline.py`
- Triggers: Manual invocation.
- Responsibilities: Baseline retrieval/generation benchmarking (see `STRUCTURE.md`).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom per interaction; long work (model load, extraction, embedding, summarization) blocks and is masked with `st.status` spinners. Token streaming is incremental rendering, not background threading. Map-reduce is deliberately sequential (no `asyncio`/threads) per `summarizer.py:232-243`.
- **VRAM envelope:** Embeddings pinned to CPU (`device="cpu"` in `local_embedding.py:24-25,40`); only one LLM/VLM active at a time via the provider abstraction; 4K context default with 1024 reserved output tokens (`prompt_budget.py:56-76`); summarizer budgets (`FAST_PATH_TOKEN_LIMIT=2500`, `MAX_BATCH_TOKENS=2000`, map `800` / reduce `1500` / consolidate `1000` token caps) keep every provider call inside the window.
- **Global state:** `st.cache_resource`-cached `AiModel` + provider client shared across sessions (`main.py:71-79`); per-session `LocalEmbedding` + `SentenceTransformer` + `HybridRetriever` + `VectorIndex` vectors in `st.session_state`. `AiModel.last_retrieval_result` / `last_verification_result` are process-shared transient state — pass explicit `retrieval_result` per call (`local_llm.py:20-28`). No other module singletons — `VectorIndex` internals are instance-scoped (`vector_index.py:29-33`); `HybridRetriever` handles are instance-scoped (`hybrid_retriever.py:100-110`); `Summarizer` holds only `provider` + `doc_store` refs (`summarizer.py:155-163`).
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `docling_reader.py` → `pdf_reader.py`; `models.py` and `vector_index.py` have no project imports. `citation_validator.py` imports only `models.py:RetrievalResult`.
- **Persistence duality:** Every indexed chunk is written twice — in-memory `LocalEmbedding.store` and persistent `HybridRetriever` (LanceDB or `fallback_store.json`). The two are kept in sync only by the paired write in `main.py:276-285` and the CR-01 restore path; direct writes to one store bypass the other.
- **Summary cache identity:** Key is `(sha256, profile)` (`UNIQUE` in `doc_store.py:84`); `model_version` is a read-time invalidation predicate, not part of the key (`doc_store.py:494-499`). Same bytes under a new filename re-point `doc_id` on upsert; `list_summaries_for_doc` on the old id then misses.
- **Linear-scan fallback:** Without LanceDB, `VectorIndex.search` is O(n) per query (`vector_index.py:130-136`); BM25 fallback is O(N·|Q|) with precomputed document frequencies (`hybrid_retriever.py:449-476`).

## Anti-Patterns

### Dual-store write coupling in the UI layer

**What happens:** `main.py:276-285` manually writes every chunk batch to both `LocalEmbedding.build_index` and `HybridRetriever.index_chunks` in sequence.
**Why it's wrong:** The two stores can diverge — a failure between the two writes, or any future code path that writes to only one store, leaves in-memory and on-disk indexes inconsistent.
**Do this instead:** Encapsulate the paired write behind a single `index_chunks` façade (e.g. on `HybridRetriever`, which already mirrors into its fallback `VectorIndex` at `hybrid_retriever.py:267-280`), so callers cannot partially index. Reference the existing mirror logic as the consolidation point.

### Dormant `pdf_path` / on-the-fly indexing parameter

**What happens:** `ask_a_question_from_pdf_stream(pdf_path="", ...)` still accepts a path and can build a throwaway `PdfReader` + `LocalEmbedding` (`local_llm.py:134-138`); `main.py:475` always passes `pdf_path=""` with a live retriever.
**Why it's wrong:** Dead surface area that suggests an indexing path the UI never uses; risks confusion about which index answers a question.
**Do this instead:** Keep the parameter for backward compatibility (tests in `tests/test_local_llm.py` cover it) but treat `retrieval_result`/`local_embedding` as the canonical inputs — which is already the documented precedence in `local_llm.py:131-133`.

## Error Handling

**Strategy:** Validate at boundaries, isolate per-file/per-page failures, degrade gracefully across backends, invalidate rather than serve stale.

**Patterns:**
- Per-file upload guard — `try/except` around validation, `DoclingReader` extraction, OCR, and visual analysis in `main.py:183-266` shows `st.error` and `continue`s, so one corrupt PDF never aborts the batch; per-page `status == "failed"` records warn individually (`main.py:268-272`).
- Summary tab guard — `try/except` around `summarizer.summarize_document` inside `st.status` flips the status to `error` and shows `st.error(f"Summarization error: ...")` without touching other tabs (`main.py:587-598`); empty-text documents raise `ValueError` from the service layer (`summarizer.py:381-382`); unknown profiles raise `ValueError` before any provider call (`summarizer.py:322-325`).
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0` (`vector_index.py:26-27, 50-63, 76-87, 121-125`); `HybridRetriever.index_chunks` raises on chunk/embedding mismatch or missing embedding source (`hybrid_retriever.py:252-265`); Pydantic models reject bad `doc_id`/`sha256`/coordinates/summary ids (`models.py:47-51, 109-112, 135-138, 163-167, 229-235`); `DocStore.save_summary` requires a `SummaryResult` instance (`doc_store.py:432-433`).
- Validation-as-data — `validate_citations` never raises on bad input: empty responses, ungrounded claims, hallucinated ranks, and abstention-with-citations all return a populated `CitationVerificationResult` with `is_valid=False` (`citation_validator.py:96-181`); the chat exception path records `verification: None` explicitly rather than fabricating a pass (`main.py:526-534`).
- Backend degradation with logging — LanceDB init/search/FTS failures log warnings and fall back to in-memory/BM25 rather than raising (`hybrid_retriever.py:112-124, 389-403, 491-505`); Docling import/conversion failure degrades to pypdf (`docling_reader.py:22-31`); provider detection falls back to an offline diagnostic provider (`local_llm.py:58-79`).
- Generation-stream errors surface inline — network or rate-limit errors during `provider.stream_text` propagate to the `try/except` around the stream call in `main.py:473-534`, which renders an inline error and records an interruption note in history rather than crashing.

## Cross-Cutting Concerns

**Logging:** `logging` module in backend services (`logger.info/warning` in `hybrid_retriever.py`, `local_embedding.py`, `docling_reader.py`, `summarizer.py:334,388,391,416`, `citation_validator.py`); developer `print` for migration notices (`doc_store.py:154`); user-facing feedback exclusively via Streamlit (`st.error`/`st.info`/`st.success`/`st.status`/`st.warning`/`st.caption` badges in `main.py`).
**Validation:** `upload_validation.py` (bytes/header/size/page limits) at the edge; Pydantic v2 enforcement in `models.py` (incl. `SummaryResult.validate_ids`) and `citation_validator.py:CitationVerificationResult` for all persisted/retrieved/validation records; `VectorIndex` type/dimension guards; `Summarizer` profile whitelist + non-empty-text gate.
**Authentication:** Provider-key resolution inside `GroqProvider` (env/`st.secrets`); local llama-server needs no credentials. See `INTEGRATIONS.md`.
**Prompt safety:** `sanitize_xml_boundary` neutralizes `</document_context>` spoofing in both QA (`prompt_budget.py:25-39`, applied to context + prompt in `assemble_grounded_messages`) and summarization (`summarizer.py:200,290` on page batches and combined intermediates, plus the do-not-execute directives in every profile/map/reduce template); `SYSTEM_GROUNDING_TEMPLATE` instructs the model to treat all document text as untrusted data (`prompt_budget.py:12-22`); the chat `disabled=` gate plus `is_healthy` check prevent offline inference attempts (`main.py:418-427`).

---

*Architecture analysis: 2026-10-12*
