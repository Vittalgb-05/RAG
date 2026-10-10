<!-- refreshed: 2026-10-10 -->
# Architecture

**Analysis Date:** 2026-10-10

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                  Streamlit UI Layer (main.py)                │
├──────────────────┬──────────────────┬───────────────────────┤
│  Sidebar         │  Chat Interface  │  Status / Index View  │
│  `main.py:88-176`│ `main.py:182-245`│  `main.py:164-170`     │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│              Ingestion + Retrieval Layer                     │
│  `pdf_reader.py:PdfReader` → `local_embedding.py:LocalEmbedding` │
│         → `vector_index.py:VectorIndex`                      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Generation Layer                                            │
│  `local_llm.py:AiModel.ask_a_question_from_pdf_stream`       │
│  → Groq Cloud API (openai/gpt-oss-20b, stream=True)          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Streaming Render                                            │
│  `main.py:239` `st.write_stream(response_stream)`             │
│  → live tokens in browser                                    │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, sidebar (model status + PDF upload + indexed-docs view), chat replay, chat input, source display, streaming render, session-state lifecycle, Clear All reset | `main.py` |
| AiModel | Groq client init + API-key resolution, RAG prompt assembly (system + history + user), retrieval orchestration, token-stream generator | `local_llm.py` |
| LocalEmbedding | SentenceTransformer wrapper (`all-MiniLM-L6-v2`), batch embedding with L2 normalisation, index build, search/get_context facade over VectorIndex | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search`; cosine + Euclidean distance; dimension locking; linear-scan k-NN | `vector_index.py` |
| PdfReader | PDF text extraction via `pypdf`, whitespace cleanup, `RecursiveCharacterTextSplitter` chunking (1000/200), chunk-dict construction with filename/page/chunk_id metadata | `pdf_reader.py` |
| Dev Container | Pinned Python 3.11 image, VS Code extensions, pip install hook, Streamlit auto-launch on port 8501 | `.devcontainer/devcontainer.json` |

## Pattern Overview

**Overall:** Layered Retrieval-Augmented Generation (RAG) with thin UI orchestration over local retrieval + remote generation.

**Key Characteristics:**
- UI-orchestrated pipeline — `main.py` owns the ingestion loop and the query loop; domain modules are stateless helpers except for the cached/singleton objects held in session state.
- Fully local retrieval, remote generation — embeddings (`sentence-transformers`) and vector search (`VectorIndex`) run in-process with no network; only LLM generation calls Groq Cloud (`local_llm.py:73-78`).
- Generator-based streaming — `ask_a_question_from_pdf_stream` is a Python generator yielding `delta.content` chunks; `st.write_stream` consumes it incrementally (`main.py:233-239`, `local_llm.py:80-82`).
- Single unified multi-document index — one `LocalEmbedding` instance accumulates chunks from all uploaded PDFs; `filename` metadata on each chunk preserves per-document attribution (`main.py:141-146`, `pdf_reader.py:51-56`).

## Layers

**Presentation (Streamlit UI):**
- Purpose: File upload, index-status display, conversational chat, streamed answer rendering.
- Location: `main.py`
- Contains: `st.set_page_config`, sidebar blocks, `st.file_uploader`, `st.chat_message` / `st.chat_input` / `st.write_stream`, `st.status` wrappers, `save_uploaded_pdf` helper.
- Depends on: `local_llm.py:AiModel`, `local_embedding.py:LocalEmbedding`, `pdf_reader.py:PdfReader`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion (PDF → chunks):**
- Purpose: Bytes-in, metadata-tagged text-chunks-out.
- Location: `pdf_reader.py`
- Contains: `PdfReader.__init__`, `PdfReader.extract_text`, `PdfReader.extract_small_portion_of_the_pdf`, `PdfReader.get_paragraphs`.
- Depends on: `pypdf.PdfReader`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `re`.
- Used by: `main.py:135-136` (upload path) and `local_llm.py:42-43` (fallback path when no index supplied).

**Retrieval (chunks → vectors → top-k):**
- Purpose: Semantic embedding and nearest-neighbour lookup.
- Location: `local_embedding.py`, `vector_index.py`
- Contains: `LocalEmbedding.__init__/_embed_one/get_embeddings/build_index/search/get_context`; `VectorIndex.add_document/add_vector/search` plus `_cosine_distance/_euclidean_distance/_dot_product/_magnitude`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding layer only); vector store depends on stdlib `math` only.
- Used by: `main.py:142-145` (build) and `main.py:216` + `local_llm.py:54` (query).

**Generation (context + history → streamed answer):**
- Purpose: Grounded answer synthesis with conversational memory.
- Location: `local_llm.py:36-82`
- Contains: `AiModel.__init__`, `AiModel.ask_a_question_from_pdf_stream`.
- Depends on: `groq.Groq`, `local_embedding.py:LocalEmbedding` (fallback construction), `pdf_reader.py:PdfReader` (fallback construction).
- Used by: `main.py:233-238`.

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed vectors)

1. User drops PDF(s) onto `st.file_uploader` (`main.py:114-120`).
2. For each filename not in `st.session_state["indexed_files"]`, bytes are wrapped in `io.BytesIO` (`main.py:131-132`).
3. `PdfReader(pdf_stream, filename=...)` extracts per-page text with `pypdf` and splits via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` into `{content, filename, page, chunk_id}` dicts (`pdf_reader.py:26-61`, `main.py:135-136`).
4. Lazily create the unified index once: `st.session_state.local_embedding = LocalEmbedding()` (`main.py:141-142`, `local_embedding.py:13-26` — loads `all-MiniLM-L6-v2`, creates empty `VectorIndex` with `embedding_fn=_embed_one`).
5. `LocalEmbedding.build_index(paragraphs)` batch-embeds all chunk texts (`normalize_embeddings=True`) and calls `VectorIndex.add_vector` per chunk (`local_embedding.py:42-59`, `vector_index.py:66-95` — first vector locks `_vector_dim = 384`).
6. Metadata recorded (`upload_time`, `pages`, `chunks`), filename added to `indexed_files`, chat history cleared, `st.rerun()` replays UI in indexed state (`main.py:147-156`).

### Secondary Flow — Query (question → streamed grounded answer)

1. User submits question via `st.chat_input` (disabled until an index exists) (`main.py:204-207`); appended to `chat_history` and rendered (`main.py:209-213`).
2. Pre-retrieval for source attribution: `local_embedding.search(prompt, k=10)` embeds the raw prompt via `_embed_one`, linear-scans all vectors by cosine distance, returns `(doc, dist)` tuples; distinct `filename` values become the "Sources used" badge (`main.py:216-220`, `local_embedding.py:61-65`, `vector_index.py:97-144`).
3. Last 10 history messages sliced for context window control (`main.py:231`).
4. `AiModel.ask_a_question_from_pdf_stream(pdf_path="", prompt, local_embedding, chat_history)` called (`main.py:233-238`).
5. Inside the generator: search query contextualised as `f"{last_user_msg} {prompt}"` (`local_llm.py:47-52`); `local_embedding.get_context(search_query, k=10)` joins top-10 chunk contents with `\n\n---\n\n` (`local_embedding.py:67-72`).
6. System prompt assembled with strict grounding instruction + `Document Text` block; messages list = `[system] + history + [user prompt]` (`local_llm.py:56-70`).
7. `groq_client.chat.completions.create(messages, model="openai/gpt-oss-20b", stream=True, max_tokens=1024)` opens the token stream (`local_llm.py:73-78`); each `chunk.choices[0].delta.content` is yielded (`local_llm.py:80-82`).
8. `st.write_stream(response_stream)` renders tokens live and returns the concatenated string, which is appended to `chat_history` with its `sources` list (`main.py:239-245`).

**State Management:**
- `st.session_state` (per-browser-session, survives Streamlit full-script reruns): `indexed_files: set` (dedup guard), `document_metadata: dict` (filename → upload_time/pages/chunks), `local_embedding: LocalEmbedding | None` (the unified in-memory index), `chat_history: list` of `{role, content, sources}` dicts — all initialised in `main.py:45-52`. `Clear All` button resets all four keys and calls `st.rerun()` (`main.py:107-112`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` in `main.py:59-67` constructs `AiModel` (and its `Groq` client + `load_dotenv()`) exactly once; every rerun and every user session reuses the same instance. Embedding model is NOT cached this way — `LocalEmbedding`/`SentenceTransformer` lives inside `st.session_state`, so each browser session loads its own copy.

## Key Abstractions

**Chunk dict:**
- Purpose: Unit of retrieval — text plus provenance metadata threaded through every layer.
- Examples: produced in `pdf_reader.py:51-56`, stored in `vector_index.py:94-95`, read in `main.py:216-220` and `local_embedding.py:67-72`.
- Pattern: Plain `dict` with keys `content`, `filename`, `page`, `chunk_id` (e.g. `report.pdf_p2_3`). `VectorIndex` requires the `content` key (`vector_index.py:83-84`).

**Unified multi-document index:**
- Purpose: Single `LocalEmbedding`/`VectorIndex` pair accumulates chunks from every uploaded PDF so one `search()` call spans all documents.
- Examples: `main.py:141-145` (incremental `build_index` per new file), `main.py:187-191` (total-chunk count aggregation).
- Pattern: Append-only growth; no per-document isolation, no persistence, no deletion except full reset via Clear All.

**Streaming generator contract:**
- Purpose: Decouple token production (Groq) from token rendering (Streamlit).
- Examples: `local_llm.py:36-82` (producer), `main.py:233-239` (consumer via `st.write_stream`).
- Pattern: Generator function yielding `str` fragments; caller never buffers — `st.write_stream` both renders incrementally and returns the full string.

**Contextualised query:**
- Purpose: Cheap conversational memory for retrieval — prepend last user question so follow-ups ("what about Q2?") retrieve correctly.
- Examples: `local_llm.py:47-52`.
- Pattern: String concatenation of `last_user_msg + " " + prompt` before embedding; full message-list history is separately passed to the LLM (`local_llm.py:66-70`).

## Entry Points

**Streamlit app:**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local, per `README.md:186` and `main.py:253` comment); dev container `postAttachCommand` in `.devcontainer/devcontainer.json:26-28`; Streamlit Community Cloud via live demo link.
- Responsibilities: Everything user-facing — `st.set_page_config` must be the first Streamlit call (`main.py:30-35`); then session-state init, cached model load, sidebar upload/index loop, main-area chat loop.

**Fallback programmatic entry (no UI):**
- Location: `local_llm.py:36-45`
- Triggers: Calling `AiModel().ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then proceeds with retrieval + generation. Not exercised by `main.py` (which always passes an existing index and `pdf_path=""`).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — the entire `main.py` reruns top-to-bottom on every interaction; long work (model load, embedding) blocks the script and is masked with `st.status` spinners (`main.py:96-98`, `main.py:124`). Token streaming is incremental rendering, not background threading (`main.py:239`).
- **Global state:** `st.cache_resource`-cached `AiModel` + `Groq` client shared across all sessions in the server process (`main.py:59-67`); per-session `LocalEmbedding` + `SentenceTransformer` model + `VectorIndex` vectors held in `st.session_state` (`main.py:45-52`). No other module-level singletons — `VectorIndex` internals (`vectors`, `documents`, `_vector_dim`) are instance-scoped (`vector_index.py:30-34`).
- **Circular imports:** None. Dependency direction is strictly one-way: `main.py` → `local_llm.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py` → `pdf_reader.py`; `pdf_reader.py` has no project imports.
- **In-memory only:** `VectorIndex` never touches disk; restarting the server or opening a new browser session loses the index and requires re-upload (`README.md:228`).
- **Linear scan:** `VectorIndex.search` computes distance against every stored vector and sorts (`vector_index.py:138-144`) — O(n) per query, no ANN structure.

## Anti-Patterns

### Double retrieval per question (duplicate embedding + scan)

**What happens:** `main.py:216` calls `local_embedding.search(prompt, k=10)` to compute the "Sources used" badge, then `ask_a_question_from_pdf_stream` internally calls `local_embedding.get_context(search_query, k=10)` which runs a second `search` over the same index (`local_llm.py:54`).
**Why it's wrong:** Every question pays for two full embedding + linear-scan passes; the two queries can even disagree because the second prepends chat history (`local_llm.py:47-52`) while the first does not.
**Do this instead:** Return sources from the single retrieval inside `AiModel` (e.g. return `(generator, sources)` or attach provenance to the yielded chunks), following the single-source pattern already established by `get_context` in `local_embedding.py:67-72`.

### Dead fallback parameter (`pdf_path`, `save_uploaded_pdf`)

**What happens:** `main.py:70-81` defines `save_uploaded_pdf` (tempfile write) and `main.py:234` still passes `pdf_path=""`, but the upload path now feeds `PdfReader` from an in-memory `io.BytesIO` (`main.py:131-135`) so the tempfile helper is never called and the `local_embedding is None` fallback branch in `local_llm.py:41-45` is unreachable from the UI.
**Why it's wrong:** Dead code misleads future maintainers about how bytes reach the reader and keeps an unused disk-IO path in the codebase.
**Do this instead:** Delete `save_uploaded_pdf` and make `pdf_path` handling explicit — either remove the parameter (UI always supplies an index) or keep the file-path constructor path in `pdf_reader.py:10-21` as the documented headless entry.

## Error Handling

**Strategy:** Fail-soft at the UI boundary; fail-loud (raise) in domain modules.

**Patterns:**
- Per-file upload guard — `try/except` around `PdfReader` + `get_paragraphs` in `main.py:134-139` shows `st.error` with filename and exception text and `continue`s to the next file, so one corrupt PDF never aborts the batch.
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content` key, non-numeric vectors, dimension mismatch, `k <= 0` (`vector_index.py:27-28, 52-60, 77-92, 121-132`); `AiModel.__init__` raises `ImportError` (missing `groq` package) and `ValueError` (missing `GROQ_API_KEY`) (`local_llm.py:20-30`).
- No retry/timeout handling on the Groq stream — network or rate-limit errors during `chat.completions.create` propagate uncaught and surface as a Streamlit exception page (`local_llm.py:73-82` has no try/except; `main.py` has none around the stream call).

## Cross-Cutting Concerns

**Logging:** `print()` to server stdout only — model-load banners in `local_llm.py:16,32` and `local_embedding.py:22,24,59`, extraction summary in `pdf_reader.py:60`. No logging framework, no log levels, nothing user-visible in the UI (status widgets use `st.status`/`st.write` instead).
**Validation:** Chunk-dict `content`-key enforcement at the store boundary (`vector_index.py:55-56, 83-84`); upload file-type restriction via `st.file_uploader(type=["pdf"])` (`main.py:114-120`); empty-chunk-list early return in `build_index` (`local_embedding.py:43-44`); empty-index early return `[]` in `search` (`vector_index.py:110-111`). No content sanitisation beyond whitespace collapsing (`pdf_reader.py:43`).
**Authentication:** API key resolved as `st.secrets["GROQ_API_KEY"]` first (Streamlit Cloud), `os.environ["GROQ_API_KEY"]` second (local `.env` via `load_dotenv()` in `main.py:66`) (`local_llm.py:23-30`). Key is passed only to the `Groq` constructor and never logged or rendered. No user authentication — any visitor with the URL can upload and chat.

---

*Architecture analysis: 2026-10-10*
