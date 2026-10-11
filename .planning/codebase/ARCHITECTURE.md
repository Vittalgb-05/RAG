<!-- refreshed: 2026-10-11 -->
# Architecture

**Analysis Date:** 2026-10-11

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     Streamlit UI  (`main.py`)                         │
│  sidebar: health badge · upload · indexed-docs   main: chat + stream  │
└───────┬───────────────────────┬───────────────────────┬──────────────┘
        │ upload bytes          │ query                 │ render tokens
        ▼                       ▼                       │
┌────────────────────┐  ┌────────────────────┐          │
│ upload_validation  │  │  local_llm.AiModel │          │
│  %PDF · size ·     │  │  provider select · │          │
│  pages · sha256    │  │  prompt budgeting  │          │
└───────┬────────────┘  └─────┬───────┬──────┘          │
        │                     │       │                 │
        ▼                     ▼       ▼                 │
┌──────────────┐  ┌──────────────┐  ┌──────────────────┐│
│  pdf_reader  │  │local_embedding│ │ model_provider   ││
│  PdfReader   │  │  (MiniLM CPU) │ │  ── groq_provider││
│  page chunks │  │  + VectorIndex│ │  ── llama_cpp_   ││
└──────┬───────┘  └──────┬───────┘ │     provider     ││
       │                 │         └────────┬─────────┘│
       ▼                 ▼                  ▼          │
┌────────────────────────────┐   ┌──────────────────┐  │
│  models.py (Pydantic)      │   │ llama-server /   │  │
│  Document·Page·Chunk·BBox  │   │ Groq Cloud       │──┘
└──────────┬─────────────────┘   └──────────────────┘
           ▼
┌────────────────────────────┐   ┌───────────────────────┐
│  doc_store.DocStore        │   │  VectorIndex (in-RAM) │
│  SQLite WAL · data/…db     │   │  cosine linear scan   │
└────────────────────────────┘   └───────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session state, sidebar health/upload/dedup orchestration, chat replay, streaming render, source display, Clear All | `main.py` |
| AiModel | Provider auto-detection, retrieval orchestration, grounded prompt assembly, token-stream generator | `local_llm.py` |
| BaseModelProvider | Abstract inference contract (generate, stream, analyze_image, health, capabilities) + `ProviderCapabilities`/`HealthStatus` schemas | `model_provider.py` |
| GroqProvider | Cloud Groq implementation; API-key resolution; no vision | `groq_provider.py` |
| LlamaCppProvider | Local llama-server HTTP client — health, SSE streaming, multimodal image analysis, connection lifecycle | `llama_cpp_provider.py` |
| prompt_budget | Bounded token budgeting, `<document_context>` injection isolation, oldest-first history truncation | `prompt_budget.py` |
| LocalEmbedding | SentenceTransformer wrapper (CPU, `all-MiniLM-L6-v2`), batch embed + build index, search/get_context facade | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; cosine/Euclidean; dimension locking; linear-scan k-NN | `vector_index.py` |
| PdfReader | pypdf extraction, whitespace cleanup, per-page fault isolation, chunk metadata construction, page records | `pdf_reader.py` |
| DocStore | SQLite (WAL) persistence of documents, pages, chunks; migrations; dedup lookup | `doc_store.py` |
| models | Canonical Pydantic v2 schemas (`Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`) + cache path helper | `models.py` |
| upload_validation | `%PDF` magic bytes, size/page caps, streaming SHA-256, stable `doc_id` | `upload_validation.py` |
| Baseline benchmark | Offline latency/memory measurement harness | `scripts/benchmark_baseline.py` |

## Pattern Overview

**Overall:** Layered modular monolith with a provider abstraction and a UI-orchestrated pipeline.

**Key Characteristics:**
- `main.py` owns both loops (ingestion and query); domain modules are stateless helpers except for cached/singleton objects held in session state or `st.cache_resource`.
- Fully local retrieval (embeddings + vector scan on CPU), pluggable generation — local llama-server preferred, Groq Cloud as configured fallback (`local_llm.py:36-56`).
- Generator-based streaming decouples token production (`stream_text`) from rendering (`st.write_stream`).
- Strict one-way dependencies; no circular imports.
- Every canonical entity is a frozen/validated Pydantic model, and legacy dict keys (`content`, `filename`, `page`, `chunk_id`) are preserved so `VectorIndex` (stdlib, dict-based) keeps working unchanged.

## Layers

**UI / Orchestration:**
- Purpose: file upload, dedup, index-status display, conversational chat, streamed rendering.
- Location: `main.py`
- Contains: `st.set_page_config` (`main.py:35`), session-state init (`main.py:49-57`), `load_ai_model()` cache (`main.py:65-72`), sidebar upload loop, chat loop.
- Depends on: `doc_store`, `local_embedding`, `local_llm`, `models`, `pdf_reader`, `upload_validation`.
- Used by: end user via browser at `http://localhost:8501`; devcontainer `postAttachCommand`.

**Ingestion:**
- Purpose: bytes-in, validated metadata + page-tagged text chunks out.
- Location: `upload_validation.py`, `pdf_reader.py`, `models.py`
- Contains: `validate_pdf_bytes` (`upload_validation.py:64`), `sha256_bytes` (`upload_validation.py:19`), `doc_id_for` (`upload_validation.py:36`), `PdfReader.extract_text/get_paragraphs/get_page_records` (`pdf_reader.py:29,124,133`).
- Depends on: `pypdf`, `langchain_text_splitters`, `re`, `hashlib`.
- Used by: `main.py:168-221`.

**Persistence:**
- Purpose: durable document/page/chunk metadata across restarts.
- Location: `doc_store.py` + `data/documents.db`
- Contains: `DocStore` (`doc_store.py:61`) — `_connect` (`:81`), `_apply_migrations` (`:98`), `upsert_document` (`:113`), `get_by_sha` (`:170`), `record_page` (`:202`), `record_chunks` (`:235`), `get_chunks_for_doc` (`:285`).
- Depends on: stdlib `sqlite3`, `models`.
- Used by: `main.py` upload loop (`main.py:171-245`).

**Retrieval:**
- Purpose: semantic embedding and nearest-neighbour lookup.
- Location: `local_embedding.py`, `vector_index.py`
- Contains: `LocalEmbedding` (`local_embedding.py:11`) — `_embed_one` (`:27`), `get_embeddings` (`:34`), `build_index` (`:41`), `search` (`:60`), `get_context` (`:66`); `VectorIndex` (`vector_index.py:15`) — `add_document` (`:39`), `add_vector` (`:65`), `search` (`:92`) + `_cosine_distance`/`_euclidean_distance` (`:157,:142`).
- Depends on: `sentence_transformers` (embedding layer only); `vector_index` uses stdlib `math` only.
- Used by: `main.py:227,343` and `local_llm.py:104`.

**Inference:**
- Purpose: grounded answer synthesis with conversational memory, across interchangeable backends.
- Location: `local_llm.py`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`
- Contains: `AiModel` (`local_llm.py:12`), `BaseModelProvider` (`model_provider.py:59`), `GroqProvider` (`groq_provider.py:18`), `LlamaCppProvider` (`llama_cpp_provider.py:18`), `assemble_grounded_messages` (`prompt_budget.py:34`).
- Depends on: `groq` (optional), `httpx`, `pydantic`.
- Used by: `main.py:89-90,356-364`.

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted)

1. `st.file_uploader` returns files; size pre-check against `MAX_FILE_MB` (`main.py:134-140`)
2. `validate_pdf_bytes(raw_bytes, filename)` → `%PDF` check, size/page caps, SHA-256, stable `doc_id` (`main.py:168-170`, `upload_validation.py:64-110`)
3. Dedup: `DocStore.get_by_sha` + session `doc_ids` guard; a dedup hit can restore chunks from SQLite into a fresh `LocalEmbedding` (`main.py:171-198`, restore at `:194`)
4. `PdfReader(io.BytesIO(raw), filename=...)` → `extract_text(doc_id, sha12)` → `get_paragraphs()` + `get_page_records()` (`main.py:200-212`)
5. Page records persisted with per-page progress; `failed` pages warned but do not abort (`main.py:217-221`)
6. `LocalEmbedding.build_index(paragraphs)` appends embeddings into the unified `VectorIndex` (`main.py:224-227`, `local_embedding.py:41-58`)
7. `DocStore.record_chunks` + `upsert_document`; best-effort JSON disk cache under `.cache/<sha>/<CONFIG_VERSION>/` (`main.py:230-256`, `cache_dir_for` at `models.py:17`)
8. Session state updated; `st.rerun()` to clear chat and re-render (`main.py:271-275`)

### Secondary Flow — Query (question → streamed grounded answer)

1. User submits via `st.chat_input` (disabled unless an index exists and the provider is healthy) (`main.py:322-331`)
2. Sources pre-fetched for display: `local_embedding.search(prompt, k=10)` (`main.py:343-347`)
3. `AiModel.ask_a_question_from_pdf_stream(...)` (`main.py:356-361`, signature `local_llm.py:73`)
4. Retrieval contextualized with the last user question, then `get_context(search_query, k=10)` (`local_llm.py:97-104`)
5. `assemble_grounded_messages(...)` builds `[system(with context), ...history, user]` within `caps.context_window` (`local_llm.py:106-111`, `prompt_budget.py:34-100`)
6. `provider.stream_text(...)` yields tokens — local SSE or Groq stream (`local_llm.py:116-121`)
7. `st.write_stream` renders incrementally and returns the full string appended to `chat_history` (`main.py:364-366`)

### Tertiary Flow — Standalone `AiModel` fallback

- If `local_embedding is None` and `pdf_path` is set, `AiModel` builds a `PdfReader` + `LocalEmbedding` inline (`local_llm.py:90-95`). `main.py` never hits this path (always passes an embedding and `pdf_path=""`).

**State Management:**
- `st.session_state` (per browser session): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict`, `local_embedding: LocalEmbedding | None`, `chat_history: list` — initialized in `main.py:49-57`; `Clear All` resets all five and reruns (`main.py:126-132`).
- `st.cache_resource` (per server process): the single `AiModel` instance (`main.py:65-72`).
- `LocalEmbedding`/`VectorIndex` are **not** cached across sessions — each browser session loads its own SentenceTransformer copy.
- Durable state lives in SQLite at `data/documents.db`.

## Key Abstractions

**Chunk (canonical retrieval unit):**
- Purpose: text plus provenance threaded through every layer.
- Examples: `pdf_reader.py:76-88` (construction), `models.py:54-73` (schema), `doc_store.py:235-283` (persistence).
- Pattern: frozen Pydantic model with legacy-compatible keys (`content`, `filename`, `page`, `chunk_id`) plus `doc_id`, `char_start/end`, `bbox`, `extraction`, `embedding_model`; `model_dump()` feeds `VectorIndex` unchanged.

**ModelProvider:**
- Purpose: swap inference backends without touching orchestration.
- Examples: `model_provider.py:59-141` (contract), `groq_provider.py:18`, `llama_cpp_provider.py:18`.
- Pattern: ABC + `ProviderCapabilities`/`HealthStatus` frozen schemas (`model_provider.py:15,39`); `AiModel` selects at construction and delegates `stream_text` (`local_llm.py:116-121`).

**Grounded prompt budget:**
- Purpose: guarantee the 4K context ceiling and neutralize prompt injection from documents.
- Examples: `prompt_budget.py:34-100`, asserted in `tests/test_prompt_budget.py`.
- Pattern: chars/4 heuristic token estimate (`prompt_budget.py:20`) → reserve output (`:54`) → truncate context with `[... truncated ...]` → drop oldest history first → wrap untrusted context in `<document_context>` with an explicit ignore-instructions directive (`SYSTEM_GROUNDING_TEMPLATE`, `:11`).

**Unified multi-document index:**
- Purpose: one `LocalEmbedding`/`VectorIndex` pair spans all uploaded PDFs; per-document attribution via chunk `filename`/`doc_id`.
- Examples: `main.py:224-227,343`, `local_embedding.py:41-58`.
- Pattern: append-only in-memory growth; full reset only via Clear All; durable chunks replayable from `DocStore` (`main.py:194`).

## Entry Points

**Streamlit app:**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local), devcontainer `postAttachCommand`, Streamlit Community Cloud
- Responsibilities: `st.set_page_config` must be the first Streamlit call (`main.py:35`); session-state init (`main.py:49-57`); cached `AiModel` (`main.py:65-72`); sidebar upload; chat loop.

**Benchmark harness:**
- Location: `scripts/benchmark_baseline.py`
- Triggers: `python scripts/benchmark_baseline.py`
- Responsibilities: measure extraction, chunking, CPU embedding, and linear-scan latencies; write `.planning/research/BASELINE_BENCHMARK.json`.

**Test corpus generator:**
- Location: `tests/data/corpus/generate_corpus.py`
- Triggers: `python tests/data/corpus/generate_corpus.py` (also a CI step)
- Responsibilities: emit 6 synthetic PDFs (clean digital, multi-column, dense table, scanned, chart, corrupt).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom on every interaction; long work (model load, embedding, extraction) blocks the script and is masked with `st.status`/`st.progress` (`main.py:87,160,217-221`). Streaming is incremental rendering, not background work.
- **Global state:** One process-wide `AiModel` via `@st.cache_resource` (`main.py:65-72`); per-session `LocalEmbedding` + `SentenceTransformer` + `VectorIndex` in `st.session_state`. `DocStore` opens/closes a connection per operation, so multiple sessions can interleave safely (`doc_store.py:81-95`; asserted by `tests/test_doc_store.py::test_two_instance_interleave_R1`).
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` → `{groq_provider, llama_cpp_provider, prompt_budget, local_embedding, pdf_reader}` → `{model_provider, vector_index, models}`.
- **In-memory vectors:** `VectorIndex` never touches disk; vectors are lost on server restart and must be re-embedded (chunks survive in SQLite).
- **VRAM ceiling:** exactly one GGUF model in VRAM; context bounded to 4096 (`llama_cpp_provider.py:25`, `prompt_budget.py:38`); embeddings pinned to CPU (`docs/LOCAL_INFERENCE.md`).
- **No network egress locally:** only the optional Groq provider makes outbound calls; llama-server is bound to `127.0.0.1` (`llama_cpp_provider.py:23`).

## Anti-Patterns

### Double retrieval per question

**What happens:** `main.py:343` calls `local_embedding.search(prompt, k=10)` to display sources, then `local_llm.py:104` calls `local_embedding.get_context(search_query, k=10)`, which embeds and scans again.
**Why it's wrong:** Duplicate embedding + full linear scan on every question; source display can also diverge from the query used for grounding (raw prompt vs history-contextualized prompt).
**Do this instead:** Have `AiModel` return or expose the retrieved chunks once and let the UI render those, rather than re-querying independently.

### Dead fallback parameters (`pdf_path`)

**What happens:** `ask_a_question_from_pdf_stream` accepts `pdf_path` and builds an inline `PdfReader` + `LocalEmbedding` when no index is supplied (`local_llm.py:90-95`), but `main.py` always passes `pdf_path=""` and an existing index (`main.py:356-361`).
**Why it's wrong:** Unused branch that lazily constructs ingestion concerns inside the inference layer.
**Do this instead:** Keep retrieval wiring in `main.py`; either remove the branch or cover it with an explicit dedicated entry point.

### Hand-rolled dispatch instead of the provider contract

**What happens:** `AiModel._detect_provider` constructs concrete `LlamaCppProvider`/`GroqProvider` and probes them directly (`local_llm.py:36-56`).
**Why it's wrong:** Provider selection logic is embedded in the orchestrator rather than configurable, so adding a backend requires editing `AiModel`.
**Do this instead:** Route selection through a factory/config so `BaseModelProvider` implementations stay pluggable.

## Error Handling

**Strategy:** Fail fast at boundaries with typed schemas; isolate and continue for per-page/per-file work; surface actionable health instead of crashing.

**Patterns:**
- Per-page fault isolation in `PdfReader.extract_text` — a failing page records a `failed` `Page` and the loop continues (`pdf_reader.py:64-110`; tested by `test_page_failure_isolated`).
- Upload validation raises `ValueError` with user-actionable text (`upload_validation.py:64-110`), caught in the UI and reported via `st.error` before `continue` (`main.py:168-172`).
- Constructor validation: `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0` (`vector_index.py:27,48-56,74-90,112-129`); `DocStore` raises `TypeError` on wrong model types (`doc_store.py:113-114,170-171,202-203`).
- Providers never raise on missing config — they return an `unreachable`/`error` `HealthStatus` (`groq_provider.py:54-78`, `llama_cpp_provider.py:55-100`), and `AiModel` starts degraded rather than failing (`local_llm.py:36-56`; tested by `test_ai_model_non_crashing_when_offline`).
- Generation errors raise `RuntimeError` from `LlamaCppProvider` (`llama_cpp_provider.py:156-158,218`), but `main.py` has **no** try/except around the stream call — such errors surface as a Streamlit exception page.

## Cross-Cutting Concerns

**Logging:** `print()` with a `[Module]` prefix for developer diagnostics; Streamlit widgets for anything user-visible.
**Validation:** Pydantic v2 everywhere (`models.py`, `model_provider.py`) with `extra="forbid"` and `frozen=True` where immutability matters; ad-hoc guards in `VectorIndex`.
**Authentication:** Not applicable — single-user local app; only the optional `GROQ_API_KEY`.
**Configuration:** `MAX_FILE_MB`/`MAX_PAGES` (`upload_validation.py:15-16`), `CONFIG_VERSION` (`models.py:14`), and provider defaults are module-level literals; context window flows from `ProviderCapabilities.context_window` into `prompt_budget`.

---

*Architecture analysis: 2026-10-11*
