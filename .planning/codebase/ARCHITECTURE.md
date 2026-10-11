<!-- refreshed: 2026-10-11 -->
# Architecture

**Analysis Date:** 2026-10-11

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (`main.py`)                  │
│  sidebar: upload → chat replay → st.chat_input → streaming  │
└──────┬──────────────┬──────────────┬────────────┬───────────┘
       │              │              │            │
       ▼              ▼              ▼            ▼
┌─────────────┐ ┌───────────┐ ┌────────────┐ ┌─────────────────┐
│ Validation  │ │ PdfReader │ │ DocStore   │ │ LocalEmbedding  │
│ `upload_    │ │ `pdf_     │ │ `doc_      │ │ `local_embed-   │
│ validation  │ │ reader.py`│ │ store.py`  │ │ ding.py` +      │
│ .py`        │ │           │ │            │ │ `vector_index   │
│             │ │           │ │            │ │ .py`            │
└─────────────┘ └─────┬─────┘ └─────┬──────┘ └────────┬────────┘
                      │             │                 │
                      ▼             ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Persistence Layer                               │
│  SQLite `data/documents.db` (DocStore, WAL) +               │
│  `.cache/<sha256>/<config>/` (pages.json/chunks.json/       │
│  manifest.json) — `models.py:cache_dir_for`                 │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Inference (`local_llm.py:AiModel`) → Groq Cloud stream      │
│  consumed by `st.write_stream` (`main.py:327`)              │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, sidebar (model status + upload + indexed-docs view), 8-step upload loop (pre-check→validate→dedup→extract→record→index→persist→cache→state), chat replay, gated chat input, source display, streaming render, session-state lifecycle, Clear All reset | `main.py` |
| Upload Validation | `%PDF` magic check, 50 MB size cap, 500-page cap, chunked SHA-256 hashing, stable `doc_<sha16>` IDs, `ValidatedUpload` dataclass | `upload_validation.py` |
| Canonical Models | Pydantic v2 schemas `BBox`/`Chunk`/`Page`/`EvidenceElement`/`Document`, `CONFIG_VERSION`, `cache_dir_for()` | `models.py` |
| DocStore | SQLite metadata store (documents/pages/chunks tables), WAL mode, `PRAGMA user_version` migrations, upserts, SHA dedup lookup, chunk batch writes, chunk rehydration reads | `doc_store.py` |
| PdfReader | pypdf text extraction with per-page try/except fault isolation, whitespace cleanup, `RecursiveCharacterTextSplitter` chunking (1000/200), hash-prefixed chunk IDs, `Page` record emission | `pdf_reader.py` |
| LocalEmbedding | SentenceTransformer wrapper (`all-MiniLM-L6-v2`), batch embed with L2 normalisation, `build_index`/`search`/`get_context` facade over VectorIndex | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search`; cosine + Euclidean; dimension locking; linear-scan k-NN | `vector_index.py` |
| AiModel | Groq client init + API-key resolution, RAG prompt assembly (system + history + user), query contextualisation, token-stream generator | `local_llm.py` |
| Benchmark | Offline perf harness: extraction/chunking/CPU-embed/linear-scan latency + RSS profiling → `BASELINE_BENCHMARK.json` | `scripts/benchmark_baseline.py` |
| CI | Lint (ruff check + format) → corpus generation → pytest on Python 3.11 / ubuntu-latest | `.github/workflows/ci.yml` |
| Dev Container | Pinned Python 3.11 image, VS Code extensions, pip install hook, Streamlit auto-launch on port 8501 | `.devcontainer/devcontainer.json` |

## Pattern Overview

**Overall:** UI-orchestrated RAG pipeline with typed persistence layer.

**Key Characteristics:**
- Fully local retrieval, remote generation — embeddings and vector search run in-process; only LLM generation calls Groq Cloud (`local_llm.py:75-80`).
- Validate-then-dedup-then-extract — every upload passes `validate_pdf_bytes` before any indexing work; SHA-256 content hash is the identity key, filenames are display-only (`main.py:137-143`).
- Pre-check before buffering — `uploaded_file.size` is compared against `MAX_FILE_MB` before `getvalue()` so oversized files never enter memory (`main.py:124-135`).
- Typed pipeline with legacy-compatible dicts — `Chunk(...).model_dump()` dicts flow into `LocalEmbedding`/`VectorIndex` so the retrieval path still operates on plain dicts while persistence uses Pydantic models (`pdf_reader.py:77-85`, `models.py:54-72`).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `delta.content` chunks; `st.write_stream` renders incrementally (`main.py:321-327`, `local_llm.py:82-84`).
- Single unified multi-document index — one `LocalEmbedding` instance accumulates chunk dicts from all PDFs; `filename`/`doc_id` metadata preserves attribution (`main.py:197-199`).
- Restart-tolerant dedup — on a dedup hit with an empty session index, chunk models are rehydrated from `DocStore.get_chunks_for_doc` and rebuilt into a fresh `LocalEmbedding` (`main.py:161-168`).

## Layers

**Presentation (Streamlit UI):**
- Purpose: File upload, validation feedback, per-page progress, index-status display, conversational chat, streamed answer rendering.
- Location: `main.py` (329 lines)
- Contains: `st.set_page_config`, sidebar blocks, `st.file_uploader`, `st.progress`, `st.status`, `st.chat_message` / `st.chat_input` / `st.write_stream`.
- Depends on: `upload_validation.py:validate_pdf_bytes` + `MAX_FILE_MB`, `doc_store.py:DocStore`, `pdf_reader.py:PdfReader`, `local_embedding.py:LocalEmbedding`, `local_llm.py:AiModel`, `models.py:Chunk/Document/cache_dir_for`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Validation:**
- Purpose: Reject non-PDFs, oversized files, over-long documents before any expensive work; produce content identity.
- Location: `upload_validation.py` (113 lines)
- Contains: `validate_pdf_bytes`, `sha256_bytes`, `doc_id_for`, `ValidatedUpload`, `MAX_FILE_MB = 50`, `MAX_PAGES = 500`.
- Depends on: `pypdf.PdfReader` (page-count/readability probe only), stdlib `hashlib`/`io`.
- Used by: `main.py:140` (upload loop step 2); size constant reused for the pre-buffer pre-check at `main.py:124-132`.

**Ingestion (extraction + chunking):**
- Purpose: Bytes-in, metadata-tagged chunk-dicts-out plus per-page status records.
- Location: `pdf_reader.py` (149 lines)
- Contains: `PdfReader.__init__`, `PdfReader.extract_text(doc_id, sha12)`, `PdfReader.extract_small_portion_of_the_pdf`, `PdfReader.get_paragraphs`, `PdfReader.get_page_records`.
- Depends on: `pypdf.PdfReader`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `re`, `models.py:Chunk/Page`.
- Used by: `main.py:178-184` (upload path with `doc_id` + `sha12` args) and `local_llm.py:44-45` (legacy fallback when no index supplied).

**Persistence:**
- Purpose: Cross-restart document/page/chunk metadata + best-effort disk cache of extracted artefacts.
- Location: `doc_store.py` (307 lines), `models.py` (131 lines), `data/documents.db`, `.cache/`
- Contains: `DocStore.__init__/_connect/_apply_migrations/upsert_document/get_document/get_by_sha/list_documents/record_page/record_chunks/get_chunks_for_doc`; `SCHEMA_V1_DDL`, `MIGRATIONS`; Pydantic `Document/Page/Chunk/BBox/EvidenceElement`.
- Depends on: stdlib `sqlite3` + `pathlib` + `contextlib`/`collections.abc` only; models validated via `Document.model_validate` / `Chunk.model_validate` on read.
- Used by: `main.py:118,147,189-190,202-219` (store open, dedup, page records, chunk + doc persistence).

**Retrieval (embedding + search):**
- Purpose: Semantic embedding and nearest-neighbour lookup over the unified in-memory index.
- Location: `local_embedding.py` (71 lines), `vector_index.py` (228 lines)
- Contains: `LocalEmbedding.__init__/_embed_one/get_embeddings/build_index/search/get_context`; `VectorIndex.add_document/add_vector/search` plus `_cosine_distance/_euclidean_distance/_dot_product/_magnitude`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding layer only); vector store depends on stdlib `math` only.
- Used by: `main.py:197-199` (build), `main.py:306` + `local_llm.py:56` (query, `k=10`).

**Inference (grounded generation):**
- Purpose: Grounded answer synthesis with conversational memory.
- Location: `local_llm.py:36-84`
- Contains: `AiModel.__init__`, `AiModel.ask_a_question_from_pdf_stream`.
- Depends on: `groq.Groq`, `local_embedding.py:LocalEmbedding` (fallback construction), `pdf_reader.py:PdfReader` (fallback construction).
- Used by: `main.py:321-326`.

**Test / Benchmark / CI:**
- Purpose: Offline verification and performance baselining.
- Location: `tests/` (7 modules + `conftest.py` + corpus), `scripts/benchmark_baseline.py` (174 lines), `.github/workflows/ci.yml` (41 lines), `pyproject.toml` (20 lines)
- Contains: `conftest.py` mock seams (`mock_groq_client`, `mock_sentence_transformer`, `fake_env_groq_key`); synthetic corpus under `tests/data/corpus/` (7 PDFs + `generate_corpus.py`); RSS/latency benchmark harness; ruff + pytest CI job.
- Depends on: `pytest`, `reportlab` (corpus generation), `ruff`, `psutil` (`requirements-test.txt`).
- Used by: Contributors and CI; never imported by `main.py`.

## Data Flow

### Primary Request Path — Ingestion (upload → indexed + persisted)

1. Size pre-check before buffering — `uploaded_file.size` vs `MAX_FILE_MB * 1024 * 1024`; oversized files get `st.error` + `continue` without ever calling `getvalue()` (`main.py:124-132`).
2. Single raw-bytes read — `uploaded_file.getvalue()` once per file (`main.py:135`).
3. Server-side validation — `validate_pdf_bytes(raw_bytes, filename)` enforces `%PDF` header (`upload_validation.py:79-80`), 50 MB cap (`upload_validation.py:83-87`), pypdf readability probe + 500-page cap (`upload_validation.py:90-100`); raises `ValueError` with user-actionable message, caught per-file with `st.error` + `continue` (`main.py:137-143`).
4. Dedup check — `doc_id = validated.doc_id` (`doc_<sha16>`); `doc_store.get_by_sha(validated.sha256)` against `data/documents.db` plus `st.session_state.doc_ids` membership; duplicates rehydrate session metadata and `continue` without re-embedding (`main.py:145-168`). On a dedup hit after restart (empty session index), persisted chunks are restored via `doc_store.get_chunks_for_doc(doc_id)` → `LocalEmbedding().build_index(...)` (`main.py:161-167`).
5. Text extraction with fault isolation — `PdfReader(io.BytesIO(raw_bytes), filename)` → `extract_text(doc_id=doc_id, sha12=sha256[:12])` loops pages with per-page try/except (`failed`), blank detection (`empty`), hash-prefixed chunk IDs `{sha12}_p{page}_{j:04d}`; `get_paragraphs()` returns legacy chunk dicts, `get_page_records()` returns `Page` models (`main.py:176-184`, `pdf_reader.py:48-113`). Construction + extraction are jointly guarded: any exception yields `st.error` + `continue` (`main.py:176-187`).
6. Page persistence + progress — each `Page` written via `doc_store.record_page(page)`; `st.progress((idx+1)/len)` advances; failed pages surface `st.warning` but never abort the file (`main.py:189-193`).
7. Embedding build — lazily construct `LocalEmbedding()` once per session, `build_index(paragraphs)` batch-embeds and appends to the unified `VectorIndex` (`main.py:195-199`, `local_embedding.py:41-58`).
8. Chunk + metadata persistence — `Chunk.model_validate(p)` per paragraph → `doc_store.record_chunks(chunk_models)` in one transaction (`main.py:201-203`, `doc_store.py:235-283`); then `Document(...)` with `status="indexed"` upserted via `doc_store.upsert_document`, with `sqlite3.IntegrityError` caught as already-recorded (`main.py:205-219`).
9. Best-effort disk cache — `.cache/<sha256>/<CONFIG_VERSION>/` gets `pages.json` (Page dumps), `chunks.json` (chunk dicts), `manifest.json` (Document dump); `OSError` caught with `st.warning`, never fails ingestion (`main.py:221-232`, `models.py:17-30`).
10. Session state + reset — `doc_ids`/`indexed_files`/`document_metadata` updated with ISO-8601 `upload_time`, `st.success` shown; after the batch, `chat_history` cleared and `st.rerun()` so stale answers never mix with the new index (`main.py:234-247`).

### Secondary Flow — Query (question → streamed grounded answer)

1. Chat gate — `st.chat_input(disabled=(local_embedding is None))` blocks questions before any index exists (`main.py:294-297`).
2. History append + source pre-fetch — user prompt appended, `local_embedding.search(prompt, k=10)` collects `filename` set for the Sources banner before generation (`main.py:299-310`).
3. Query contextualisation — last user message prepended to current prompt for retrieval (`local_llm.py:49-54`); `get_context(query, k=10)` joins top chunks with `\n\n---\n\n` (`local_embedding.py:66-71`).
4. Prompt assembly — system message carries retrieved Document Text with strict grounding instruction; full history list spliced in; current prompt appended (`local_llm.py:58-72`, `main.py:319`).
5. Streaming generation — `groq_client.chat.completions.create(..., stream=True, max_tokens=1024)` yields `delta.content`; `st.write_stream` renders incrementally and returns the full string, appended to `chat_history` with sources (`local_llm.py:75-84`, `main.py:321-329`).

**State Management:**
- `st.session_state` (per-browser-session, survives Streamlit full-script reruns): `doc_ids: set` (content-hash dedup guard), `indexed_files: set` (display names), `document_metadata: dict` (filename → `doc_id`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None` (unified in-memory index), `chat_history: list` of `{role, content, sources}` — all initialised in `main.py:49-57`. `Clear All` resets all five keys and calls `st.rerun()` (`main.py:98-104`).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` in `main.py:65-73` constructs `AiModel` (and its `Groq` client + `load_dotenv()`) exactly once. Embedding model is NOT cached — `LocalEmbedding`/`SentenceTransformer` lives in session state, so each browser session loads its own copy.
- SQLite (`data/documents.db`, gitignored, auto-created by `DocStore.__init__` — absent from a fresh checkout): cross-restart source of truth for dedup (`UNIQUE(sha256)`), page statuses, chunk metadata for rehydration; per-operation connections with WAL + 5 s busy timeout for Windows/Streamlit safety (`doc_store.py:80-96`).
- Disk cache (`.cache/<sha256>/chunker-1000-200-pypdf/`, absent from a fresh checkout): derived artefacts only (pages/chunks/manifest JSON); safe to delete, rebuilt on re-upload.

## Key Abstractions

**Chunk dict (retrieval unit):**
- Purpose: Unit of retrieval — text plus provenance metadata threaded through every layer.
- Examples: produced in `pdf_reader.py:77-85` via `Chunk(...).model_dump()`, stored in `vector_index.py:89-90`, read in `main.py:306-310` and `local_embedding.py:66-71`.
- Pattern: Plain `dict` with keys `content`, `filename`, `page`, `chunk_id` plus canonical `doc_id`/`extraction`; `VectorIndex` requires the `content` key (`vector_index.py:80-81`).

**Canonical Pydantic models:**
- Purpose: Validated, serialisable contracts for persistence and disk cache; frozen where hashability matters (`Chunk`, `BBox`), `extra="forbid"` everywhere.
- Examples: `models.py:33-131` (`BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`); `cache_dir_for` in `models.py:17-30`; `doc_id` must start with `doc_` (`models.py:127-131`).
- Pattern: Construct at layer boundaries (`pdf_reader.py:77-96`, `main.py:202-215`), validate on DB read (`doc_store.py:168,188,306`).

**Unified multi-document index:**
- Purpose: Single `LocalEmbedding`/`VectorIndex` pair accumulates chunks from every uploaded PDF so one `search()` call spans all documents.
- Examples: `main.py:197-199` (incremental `build_index` per new file), `main.py:278` (total-chunk aggregation).
- Pattern: Append-only in-memory growth; no per-document isolation, no embedding persistence, no deletion except full reset via Clear All. SQLite holds metadata + chunk text — vectors are never persisted, only rebuilt.

**ValidatedUpload + doc_id:**
- Purpose: Decouple content identity from filename; `doc_<sha256[:16]>` is stable across renames and sessions.
- Examples: `upload_validation.py:51-62`; consumed in `main.py:146-160`.
- Pattern: Hash computed with 1 MiB streaming slices (`upload_validation.py:19-33`); magic/size checks precede the pypdf readability probe so cheap rejections stay cheap.

**Page records:**
- Purpose: Per-page extraction observability — `ok`/`empty`/`failed` with char counts, error text, chunk counts.
- Examples: emitted in `pdf_reader.py:53-109`, persisted in `main.py:189-190` via `doc_store.record_page`, cached to `pages.json` (`main.py:225-226`).
- Pattern: `PRIMARY KEY (doc_id, page_num)` upsert (`doc_store.py:30-39,202-233`); UI progress bar advances per record regardless of status.

**Token-stream generator:**
- Purpose: Decouple token production (Groq) from token rendering (Streamlit).
- Examples: `local_llm.py:36-84` (producer), `main.py:321-327` (consumer via `st.write_stream`).
- Pattern: Generator function yielding `str` fragments; caller never buffers — `st.write_stream` both renders incrementally and returns the full string.

**History contextualisation:**
- Purpose: Cheap conversational memory for retrieval — prepend last user question so follow-ups ("what about Q2?") retrieve correctly.
- Examples: `local_llm.py:49-54`.
- Pattern: String concatenation of `last_user_msg + " " + prompt` before embedding; full message-list history separately passed to the LLM (`local_llm.py:68-70`).

## Entry Points

**Streamlit app (sole production entry):**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local, per `README.md`); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` must be the first Streamlit call (`main.py:35-40`); then session-state init, cached model load, sidebar upload/index loop (`main.py:114-263`), main-area chat loop (`main.py:273-329`).

**Legacy self-contained RAG fallback:**
- Location: `local_llm.py:43-47`
- Triggers: Calling `AiModel().ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None`.
- Responsibilities: Builds `PdfReader` → `LocalEmbedding` inline, then proceeds with retrieval + generation. Not exercised by `main.py` (which always passes an existing index and `pdf_path=""`).

**Benchmark harness:**
- Location: `scripts/benchmark_baseline.py:28-170`
- Triggers: `python scripts/benchmark_baseline.py` (requires real `sentence-transformers` + `psutil`, corpus present).
- Responsibilities: Times extraction/chunking/CPU-embedding/linear-scan, profiles RSS, writes `.planning/research/BASELINE_BENCHMARK.json`.

**Test corpus generator:**
- Location: `tests/data/corpus/generate_corpus.py` (213 lines)
- Triggers: CI step before pytest (`.github/workflows/ci.yml:35-37`); manual `python tests/data/corpus/generate_corpus.py`.
- Responsibilities: Synthesises `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf` (+ `table.pdf` variant) via `reportlab` so tests never depend on committed binaries.

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — the entire `main.py` reruns top-to-bottom on every interaction; long work (model load, embedding) blocks the script and is masked with `st.status` spinners (`main.py:87-89,116`). Token streaming is incremental rendering, not background threading (`main.py:327`).
- **Global state:** `st.cache_resource`-cached `AiModel` + `Groq` client shared across all sessions in the server process (`main.py:65-73`); per-session `LocalEmbedding` + `SentenceTransformer` model + `VectorIndex` vectors held in `st.session_state` (`main.py:49-57`). No other module-level singletons — `VectorIndex` internals (`vectors`, `documents`, `_vector_dim`) are instance-scoped (`vector_index.py:29-33`); `DocStore` holds only `db_path` and opens per-operation connections via the `_connect` context manager (`doc_store.py:73-96`).
- **Circular imports:** None. Dependency direction is strictly one-way: `main.py` → `upload_validation.py` / `doc_store.py` → `models.py`; `main.py` → `local_llm.py` → `local_embedding.py` → `vector_index.py`; `main.py` → `pdf_reader.py` → `models.py`; `pdf_reader.py` has no project imports beyond `models.py`.
- **In-memory vectors only:** `VectorIndex` never touches disk; restarting the server or opening a new browser session loses the embedding index and requires re-upload or dedup-restore from `DocStore` chunk text (`main.py:161-167`). SQLite + `.cache/` preserve metadata and extracted text, but vectors are always recomputed.
- **Linear scan:** `VectorIndex.search` computes distance against every stored vector and sorts (`vector_index.py:130-136`) — O(n) per query, no ANN structure.
- **SQLite concurrency:** Per-operation connections with `PRAGMA journal_mode=WAL` + `busy_timeout=5000` closed in `finally` (`doc_store.py:80-96`); no long-lived connections, no connection pooling — required for Windows file locks and Streamlit rerun loops.
- **Schema versioning:** `PRAGMA user_version` gates the `MIGRATIONS` dict (`doc_store.py:56-58,98-111`); current version 1 with `documents` / `pages` / `chunks` tables (`doc_store.py:16-54`). New tables/columns require a new migration entry, never inline `ALTER` in call sites.

## Anti-Patterns

### Double retrieval per question (duplicate embedding + scan)

**What happens:** `main.py:306` calls `local_embedding.search(prompt, k=10)` for the Sources banner, then `ask_a_question_from_pdf_stream` calls `get_context(search_query, k=10)` which searches again with a contextualised query.
**Why it's wrong:** Two embedding + linear-scan passes per question; the displayed sources can differ from the sources actually used for generation.
**Do this instead:** Single `search()` in `main.py`, pass the retrieved docs (or their joined context) into the LLM call — see `local_embedding.py:66-71` for the join format to preserve.

### Dead fallback parameter (`pdf_path`, legacy path)

**What happens:** `main.py:321-326` always passes `pdf_path=""` with a live index, so `local_llm.py:43-47`'s self-contained `PdfReader` → `LocalEmbedding` fallback never executes in production.
**Why it's wrong:** Untested production-adjacent code path that constructs unmocked `LocalEmbedding` (GPU/model download) if ever triggered.
**Do this instead:** Keep the fallback for tests/REPL use only, or remove the parameter and require `local_embedding` explicitly.

## Error Handling

**Strategy:** Validate early with actionable messages; isolate per-file and per-page failures; best-effort caching never fails ingestion.

**Patterns:**
- Upload pre-check + validation raise `ValueError` naming the file and the violated rule (`upload_validation.py:79-80,87,94,97,100`); `main.py:129-132,141-143` catches per-file with `st.error` + `continue` — including the pre-buffer size gate.
- Extraction guard — joint try/except around `PdfReader` construction + `extract_text` in `main.py:177-187` shows `st.error` and `continue`s; per-page try/except in `pdf_reader.py:50-109` records `Page(status="failed", error=...)` and continues; blank pages record `status="empty"` (`pdf_reader.py:52-63`); the UI warns per failed page but indexes the rest (`main.py:192-193`).
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content` key, non-numeric vectors, dimension mismatch, `k <= 0` (`vector_index.py:26-27,50-59,76-87,121-125`); `AiModel.__init__` raises `ImportError` (missing `groq`) and `ValueError` (missing `GROQ_API_KEY`) (`local_llm.py:21-31`); `DocStore` raises `TypeError` on wrong model types (`doc_store.py:120-121,160-161,180-181,209-210,242-243,263-264`).
- Race-tolerant upsert — `sqlite3.IntegrityError` on `upsert_document` is caught and reported as already-recorded instead of crashing the batch (`main.py:216-219`).
- Empty-store behaviour: `search()` returns `[]` instead of raising when nothing is indexed (`vector_index.py:105-106`); `record_chunks([])` is a no-op (`doc_store.py:244-245`).
- Disk cache writes wrapped in try/except `OSError` with `st.warning` (`main.py:222-232`) — cache failure is cosmetic.
- No retry/timeout handling on the Groq stream — network or rate-limit errors during `chat.completions.create` propagate uncaught and surface as a Streamlit exception page (`local_llm.py:75-80` has no try/except; `main.py` has none around the stream call).

## Cross-Cutting Concerns

**Logging:** `print()` with module prefixes for developer diagnostics (`[UploadValidation]` in `upload_validation.py:106`, `[DocStore]` in `doc_store.py:111`, `[LocalEmbedding]` in `local_embedding.py:21,23,58`, extraction summary in `pdf_reader.py:113`); all user-facing feedback via `st.error`/`st.info`/`st.success`/`st.warning`/`st.status`/`st.progress` (`main.py`).
**Validation:** Size pre-check at upload boundary (`main.py:124-132`) + magic-byte + size + page-count in `upload_validation.py`; Pydantic field constraints (`min_length`, `ge`, `pattern` for sha256, `doc_` prefix validator) at model boundary (`models.py`); constructor guards at store/index boundary (`doc_store.py`, `vector_index.py`).
**Authentication:** No app-level auth; Groq key resolved `st.secrets` → `os.environ` inside cached loader (`local_llm.py:25-31`, `main.py:72-73`); `.env` gitignored.

---

*Architecture analysis: 2026-10-11*
