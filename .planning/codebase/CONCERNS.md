---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# Codebase Concerns

**Analysis Date:** 2026-11-14

Findings below were verified against source and, where noted, by constructing the Pydantic models or tracing the exact call path. Severity is scoped to the current local-first, single-user deployment: **P0** blocks a primary user flow, **P1** breaks a secondary flow or hides state, **P2** degrades quality or maintainability.

## Tech Debt

**Three divergent grounding contracts:**
- Issue: `GroundingReport` (`core/models.py:226`) is the internal contract, `Grounding` (`api/schemas/common.py:43`) is the wire contract, and `Grounding` in `frontend/src/lib/api/types.ts:136` is a third copy. They are not compatible: the report has `verification_status` and a string `scope`, while the API schema requires `status`, `caption`, and a `Scope` object.
- Impact: the same payload cannot be validated by the API and rendered by the UI; this has already produced the chat-history and grounding-badge failures below.
- Fix approach: add one explicit `GroundingReport -> Grounding` mapper (or make the report the response model) and derive the frontend type from the OpenAPI schema.

**Page text is modeled but never persisted:**
- Issue: `Page.page_text` (`core/models.py:89`) is populated by Docling (`ingestion/docling_reader.py:403`), but the `pages` table has no `page_text` column (`core/doc_store.py:59-67`) and both insert paths omit it (`core/doc_store.py:415-423`, `core/doc_store.py:535-547`).
- Impact: stored pages can only report `char_count`/status; page readers and summary generation cannot recover their text from SQLite.
- Fix approach: add `page_text` with a schema migration and persist it in `record_pages_batch`/`record_ingestion`, or remove the field and always reconstruct pages from `Chunk` rows.

**Inert configuration and duplicated logging setup:**
- Issue: `Settings.allow_non_loopback` (`api/config.py:14`) is never read by the API (enforcement lives separately in `start.py:72-90`). `Settings.store_originals` (`api/config.py:19`) is never consumed by ingestion. `core/logging_setup.configure_logging` (rotating handler, `core/logging_setup.py:118`) is used only by tests; runtime uses a separate implementation with a plain `FileHandler` (`api/main.py:30-41`).
- Impact: settings appear operational but do nothing; the two logging paths diverge and the reviewed/rotated one is not the one production runs.
- Fix approach: wire or delete the dead settings; call `core.logging_setup.configure_logging` from `api/main.py` and delete the duplicate.

**README describes a removed architecture:**
- Issue: `README.md:6`, `README.md:31`, `README.md:78`, `README.md:231` document a Streamlit UI driven by root-level `main.py` and `ui/`, which no longer exist; the runtime is FastAPI (`api/main.py`) plus Next.js (`frontend/`).
- Impact: setup and run instructions are wrong; onboarding follows dead paths.
- Fix approach: regenerate the architecture/run sections from `STRUCTURE.md` and the actual launcher (`start.py`).

**Silent chat persistence failures:**
- Issue: `_finish` wraps `append_chat_message` in `except Exception: pass` (`api/routers/chat.py:95-113`).
- Impact: a locked/corrupt SQLite database silently loses conversation history with no log line.
- Fix approach: log at `error` with the session/message ids and surface a non-fatal warning to the client.

**Summary length vocabulary is inconsistent:**
- Issue: `SummaryLength` accepts `concise|standard|detailed` (`api/schemas/summaries.py:8`), but `Summarizer` treats everything except `concise` as detailed (`core/summarizer.py:410-427`, `core/summarizer.py:504-510`), while the cache key includes the raw string (`core/summarizer.py:30-32`).
- Impact: `standard` and `detailed` generate identical output but occupy different cache rows.
- Fix approach: normalize length before hashing (`standard -> detailed`) or define three real prompt profiles.

**Diagnostics log endpoint ignores its filter and reads the whole file:**
- Issue: `level` is accepted but never used (`api/routers/system.py:178`), and `readlines()` loads the entire log before slicing (`api/routers/system.py:188-190`).
- Impact: log requests are O(file size) and the level filter is a no-op.

**Job state is process-local and unbounded:**
- Issue: `JobManager._jobs` is a plain dict (`api/jobs.py:83`) and each `Job.events` list grows without trimming (`api/jobs.py:41`, `api/jobs.py:51`).
- Impact: memory grows for the process lifetime and all job history is lost on restart; see also Scaling Limits.

## Known Bugs

**P0 — Every ingestion aborts on `Document(status="indexing")`:**
- Symptoms: upload is accepted, then the job fails with `Input should be 'pending', 'indexed' or 'failed'`; no document row is written and the library stays empty. Verified by constructing `Document(status="indexing")`, which raises `ValidationError`.
- Files: `services/ingestion.py:248-257` (constructs `Document(status="indexing")` outside the persistence `try`), `core/models.py:130-132` (`Literal["pending", "indexed", "failed"]`), `services/lifecycle.py:147` (writes the same invalid value through raw SQL).
- Trigger: upload any PDF and run the ingestion job.
- Workaround: none through the API. The model must permit `indexing` (and `list_documents` must read it) or ingestion must start at `pending`.

**P0 — `POST /summaries` cannot start a summary:**
- Symptoms: 500 before the job is queued. Three independent blockers on the same path: `p.text` does not exist on `Page`; `Summarizer(doc_store=..., ai_model=...)` uses a keyword the constructor does not accept; `summarize_document(raw_text=...)` is not in its signature.
- Files: `api/routers/summaries.py:107` (`p.text`), `api/routers/summaries.py:111` (`core/summarizer.py:188` defines `__init__(provider, doc_store)`), `api/routers/summaries.py:112-113` (`core/summarizer.py:514-525` accepts `doc_id, sha256, pages, chunks...`).
- Trigger: `POST /api/v1/summaries` for any document with stored pages.
- Workaround: none. The endpoint must pass `provider=c.ai_model` and reconstruct pages from chunks via `get_chunks_for_doc`.

**P0 — `GET /documents/{doc_id}/pages/{page_num}` always fails:**
- Symptoms: `AttributeError: 'DocStore' object has no attribute 'get_page'`. Even with a `get_page` method, the response reads `page.page_number` and `page.text`, which do not exist on `Page`, and `page_text` is never persisted (see Tech Debt).
- Files: `api/routers/documents.py:140`, `api/routers/documents.py:149-150`; `core/doc_store.py:597` (only `get_pages_for_doc` exists); `core/models.py:84-89` (`page_num`, `page_text`).
- Trigger: any page-text request from the document reader.
- Workaround: none. Implement `get_page` or filter `get_pages_for_doc`, and return `page_num` plus reconstructed text.

**P1 — `GET /chat/sessions/{id}` fails for any session containing an answer:**
- Symptoms: 500 validation error; chat history disappears after reload or after the SSE stream refetches the session.
- Files: `api/routers/chat.py:92` and `api/routers/chat.py:108` persist `GroundingReport.model_dump()` under the `grounding` column; `api/routers/chat.py:170-172` reconstructs `Grounding(**g_raw)`; the required fields are declared in `api/schemas/common.py:43-55` but absent from `core/models.py:226-269`.
- Trigger: default `persist_chat=True`, send one message, then `GET /api/v1/chat/sessions/{id}`.
- Workaround: `RAG_PERSIST_CHAT=0` avoids the failure but discards history.

**P1 — Grounding badge never renders on a live answer:**
- Symptoms: the `final` SSE event sends the raw `GroundingReport` under `grounding` (`api/routers/chat.py:115-123`) with `verification_status`/string `scope` and no `status`/`caption`; `GroundingBadge` reads `grounding.status` (`frontend/src/components/chat/grounding-badge.tsx:15`). The chat page then discards the payload and refetches the broken session (`frontend/src/app/(shell)/chat/page.tsx:345-350`).
- Trigger: any streamed answer.
- Workaround: none; map the report to the UI schema before emitting.

**P1 — Health endpoint always reports `unreachable`:**
- Symptoms: `/api/v1/health` returns `unreachable` with `'AiModel' object has no attribute 'get_provider_status'`.
- Files: `api/routers/system.py:38-53`; no `get_provider_status` exists in `core/local_llm.py` or `providers/`.
- Trigger: every health check (also drives the Docker `HEALTHCHECK`, `Dockerfile:54-55`).
- Workaround: none; implement the probe or derive health from `get_capabilities()`/`is_locked()`.

**P1 — Embedding constellation fallback raises `AttributeError`:**
- Symptoms: when LanceDB export fails or is unavailable, the endpoint iterates `self._store`, an attribute that does not exist (the fallback is `self._fallback_store`), so `/visualize/embeddings` returns 500.
- Files: `retrieval/hybrid_retriever.py:1145`; attributes are defined at `retrieval/hybrid_retriever.py:195-205`; caller at `api/routers/visualize.py:54-62`.
- Trigger: no LanceDB installation or a failed LanceDB query.
- Workaround: none.

**P1 — Evidence Lens page images always 404:**
- Symptoms: the endpoint returns "Original PDF not stored" even when `RAG_STORE_ORIGINALS=1`; no upload, ingestion, or lifecycle code writes `data/originals/<sha256>.pdf`.
- Files: `api/config.py:19` (flag only), `api/routers/documents.py:176-182` (only reader), no writer in `services/ingestion.py`; frontend URL in `frontend/src/components/chat/evidence-lens-modal.tsx:21`.
- Trigger: opening Evidence Lens for any document.
- Workaround: none.

**P1 — VLM figure/table analysis never runs from the web upload path:**
- Symptoms: ingestion only runs VLM analysis when `vlm_provider` is supplied (`services/ingestion.py:59`, `services/ingestion.py:200-214`), but the sole caller omits it (`api/routers/documents.py:85-89`). Detected regions are discarded, so no evidence elements/captions are indexed from the UI.
- Trigger: upload a PDF containing figures or tables through the API.
- Workaround: none; pass `c.ai_model` (when local and vision-capable) into `ingest_pdf`.

**P2 — `EMBEDDING_MAX_LENGTH` is documented but not applied:**
- Symptoms: the docstring promises `max_length=EMBEDDING_MAX_LENGTH` (256), but `get_embeddings` calls `model.encode` without it (`retrieval/local_embedding.py:89-106`), so truncation follows the tokenizer default (often 512) and differs from the stated invariant.
- Trigger: chunks or queries longer than the training boundary.
- Workaround: pass `max_length=EMBEDDING_MAX_LENGTH` to `encode`.

**P2 — Summary cache can miss forever once multiple model versions exist:**
- Symptoms: `get_summary` selects by `sha256` and `profile` only, without `model_version` in the SQL or an `ORDER BY` (`core/doc_store.py:812-824`), then rejects the returned row if its version differs. Schema V7 intentionally preserves older rows (`core/doc_store.py:169-200`), so the first row can remain stale and every request regenerates despite a fresh row existing.
- Trigger: a model/prompt upgrade that changes `compute_summary_model_version`.
- Workaround: add `model_version = ?` to the `WHERE` clause (falling back only when the caller passes `None`).

## Security Considerations

**No authentication; the client header is not a security control:**
- Risk: every indexed document, chat history, cloud settings page, and API-key configuration endpoint is readable by anyone who can reach the port. `require_client_header` only checks `X-RAG-Client: web` on mutating methods (`api/deps.py:15-25`); it is trivially spoofed and does not cover reads.
- Files: `api/deps.py`, `api/main.py:74-79`, `api/routers/settings.py`.
- Current mitigation: loopback bind default (`api/config.py:12`), launcher refusal for non-loopback (`start.py:77-105`), `TrustedHostMiddleware` (`api/main.py:61`), CORS restricted to localhost (`api/config.py:15`, `api/main.py:63-70`).
- Recommendations: keep the loopback default; if remote access is ever supported, add real authentication; do not treat the header as authorization.

**Docker image bypasses the launcher's loopback guard:**
- Risk: the container starts with `--host 0.0.0.0` (`Dockerfile:58`) and no authentication. `TrustedHostMiddleware` still rejects non-localhost `Host` headers by default (`api/config.py:16`), but `RAG_ALLOWED_HOSTS` is operator-configurable and the launcher safety check is never executed in this path.
- Files: `Dockerfile:54-58`, `api/main.py:61`, `start.py:77-105`.
- Recommendation: bind `127.0.0.1` in the container by default and require an explicit, documented override (or authentication) before publishing the port.

**LanceDB filter built without escaping in `export_embeddings`:**
- Risk: `doc_ids` from the query string are interpolated directly into `doc_id IN (...)` (`retrieval/hybrid_retriever.py:1122-1124`), unlike every other filter path, which uses `_escape_sql_literal`/`_doc_filter_clause` (`retrieval/hybrid_retriever.py:56-64`, `:663`, `:744`, `:843`, `:941`). A crafted value can rewrite the predicate and export embeddings scoped to other documents.
- Files: `retrieval/hybrid_retriever.py:1107-1125`, `api/routers/visualize.py:55-62`.
- Recommendation: replace the inline join with `_doc_filter_clause(doc_ids)`.

**Unhandled exceptions return internal details:**
- Risk: the catch-all handler returns `str(exc)` in the RFC 9457 `detail` (`api/errors.py:126-132`), exposing file paths, SQL, and library internals to any local client.
- Files: `api/errors.py:65-132`.
- Recommendation: return a generic message with the `request_id`; keep the detail in the server log.

**Upload body is read before the size limit is checked:**
- Risk: `await file_obj.read()` buffers the entire request before `validate_pdf_bytes` enforces `MAX_FILE_MB=50` (`api/routers/documents.py:61-65`, `core/limits.py:4`). Multiple files per request and no server body cap allow memory exhaustion from a local client.
- Recommendation: enforce `Content-Length`/streaming limits at the ASGI layer and reject oversized files before buffering.

**Cloud credential handling is otherwise sound:**
- `CloudState._keys` is memory-only (`api/cloud_state.py:23`), keys are `SecretStr`, and `.env` is excluded from the Docker context (`.dockerignore`). The remaining exposure is transport: the settings POST sends keys over plain HTTP on loopback, which is acceptable only while the loopback-only deployment invariant holds.

## Performance Bottlenecks

**Pure-Python BM25 loads and re-tokenizes every row per query:**
- Problem: when LanceDB FTS is unavailable, `_bm25_candidate_docs` reads the entire table (or the entire in-memory mirror) and `_bm25_search_fallback` scores all documents on every search.
- Files: `retrieval/hybrid_retriever.py:832-870`, `retrieval/hybrid_retriever.py:859-957`.
- Cause: no persisted inverted index or cached term statistics.
- Improvement path: build an FTS index at ingestion or cache document term frequencies between queries.

**JSON fallback mirror is rewritten on every ingestion:**
- Problem: `_mirror_upsert` reads the whole JSON file and rewrites it for each index call, which is O(N) I/O per document and grows with the corpus.
- Files: `retrieval/hybrid_retriever.py:312-350`, `retrieval/hybrid_retriever.py:277-288`.
- Cause: single-file durable mirror (acknowledged in the docstring).
- Improvement path: per-document mirror files or an append-only log with compaction.

**N+1 queries in the document library:**
- Problem: `GET /documents` calls `retriever.has_document()` and `doc_store.get_evidence_for_doc()` once per document.
- Files: `api/routers/documents.py:24-49`.
- Cause: per-row enrichment in the request loop.
- Improvement path: batch the vector-existence check and join/aggregate evidence counts in one query.

**Blocking CPU/IO inside `async` handlers:**
- Problem: `search_hybrid` runs inline (`api/routers/search.py:21`), `export_embeddings` + NumPy PCA run inline (`api/routers/visualize.py:54-62`), and PDF validation/parsing runs inline (`api/routers/documents.py:65`). Each stalls the event loop; with the single worker this delays every concurrent request.
- Improvement path: move these calls to `starlette.concurrency.run_in_threadpool` or `asyncio.to_thread`.

**RapidOCR model is re-initialized per document:**
- Problem: `apply_conditional_ocr` constructs `OcrEngine()` when no engine is passed (`ingestion/ocr_fallback.py:403`), and the constructor loads `RapidOCR()` (`ingestion/ocr_fallback.py:119-122`). `services/ingestion.py:183-190` never passes an engine.
- Cause: no process-level OCR engine singleton.
- Improvement path: build one engine in `AppContainer` and inject it into `IngestionService`.

**Diagnostics reads the entire, non-rotating log:**
- Problem: `logging.FileHandler` is used without rotation (`api/main.py:39`) and `/diagnostics/logs` calls `readlines()` before slicing (`api/routers/system.py:188-190`).
- Improvement path: use `RotatingFileHandler` from `core/logging_setup` and read only the tail.

**Unbounded job event history:**
- Problem: every progress update appends `JobEvent` and neither the job dict nor its events are pruned (`api/jobs.py:41`, `:83`, `:91`).
- Cause: jobs are retained indefinitely for polling.
- Improvement path: cap `events` (ring buffer) and evict completed jobs after a TTL.

## Fragile Areas

**Status is a stringly-typed contract split across four places:**
- Files: `core/models.py:130` (`pending|indexed|failed`), `api/routers/documents.py:32-34` (accepts `indexing`), `core/doc_store.py:395-404` (`update_document_status` accepts any string), `services/lifecycle.py:147` (writes `indexing`).
- Why fragile: `list_documents`/`get_document` validate every row with `Document.model_validate`; a single unvalidated status (including the one lifecycle intentionally writes) makes the entire library endpoint raise. A crash during reindex leaves the row permanently unreadable.
- Safe modification: add a DB `CHECK` constraint, validate in `update_document_status`, and align the `Document` literal/DTO.
- Test coverage: no test writes an invalid status and re-reads the catalog.

**`Page` rows are validated against `SELECT *`:**
- Files: `core/doc_store.py:606-611`, `core/models.py:76-89`.
- Why fragile: `Page` uses `extra="forbid"`, so adding any column to `pages` without updating the model breaks all page reads.
- Safe modification: select explicit columns or relax the model for storage rows.

**Grounding serialization is triplicated:**
- Files: `core/models.py:226-269`, `api/schemas/common.py:43-55`, `frontend/src/lib/api/types.ts:136-145`.
- Why fragile: no shared schema or adapter; a change in one contract silently breaks the others. This is the root cause of the P1 chat/grounding bugs.
- Safe modification: generate the frontend type from OpenAPI and add a contract test that round-trips a persisted message.

**`InferenceGate` is process-global and cross-thread release is only logged:**
- Files: `core/local_llm.py:35-88`.
- Why fragile: `release()` from a thread that does not own the `RLock` is ignored with a warning (`core/local_llm.py:71-78`). Work scheduled on a different thread that acquires and releases on another leaves the gate permanently locked; `is_locked()` is derived from an acquisition counter, not an owner.
- Safe modification: always use `InferenceGate.hold()` in the acquiring thread and assert balanced release; add a timeout/fail-safe path.
- Test coverage: `tests/test_concurrency_lock.py` covers single-thread and foreign release, not nested or exception-path leaks.

**PyMuPDF document handle is never closed in the page-image endpoint:**
- Files: `api/routers/documents.py:184-193` (`doc_fitz = fitz.open(...)` with no `finally: doc_fitz.close()`).
- Why fragile: on Windows the open handle keeps the PDF locked; repeated Evidence Lens requests leak file descriptors. Other call sites use `try/finally` (`ingestion/visual_analyzer.py:84-...`, `ingestion/ocr_fallback.py:155-...`), so this is an outlier.
- Safe modification: wrap in `with fitz.open(orig_path) as doc_fitz:`.

**Chat persistence errors are swallowed:**
- Files: `api/routers/chat.py:95-113`.
- Why fragile: DB failures (locked, disk full, schema drift) are invisible and the API still reports success.

**Summary cache lookup ignores the version in SQL:**
- Files: `core/doc_store.py:792-824`, `core/doc_store.py:169-200`.
- Why fragile: correctness depends on row order and on there being exactly one version per `(sha256, profile)`. Multiple versions are explicitly supported by the V7 schema.

## Scaling Limits

**Single-worker background pool:**
- Current capacity: one job at a time (`api/jobs.py:82`, `ThreadPoolExecutor(max_workers=1)`).
- Limit: one large PDF ingestion or summary blocks every queued upload/reindex/summary; the SSE progress for queued jobs shows no work.
- Scaling path: separate bounded pools per job class, or a durable queue.

**One GPU inference at a time:**
- Current capacity: process-wide `InferenceGate` (`core/local_llm.py:35-41`) designed for a 4 GB VRAM envelope.
- Limit: concurrent chat/summary requests serialize; the second caller waits up to 60 seconds and then fails with `gpu_busy`.
- Scaling path: intentional for the target hardware; document the limit and return queue position.

**In-memory job registry:**
- Current capacity: unbounded `_jobs` dict and per-job event list (`api/jobs.py:41`, `:83`).
- Limit: memory grows with every upload/summary for the process lifetime; restart loses all job state and progress polling.
- Scaling path: TTL eviction, capped event buffers, or persisted job records.

**SQLite write serialization:**
- Current capacity: per-operation connections, WAL, 5 s busy timeout (`core/doc_store.py:241-246`).
- Limit: `record_ingestion` holds a single write transaction for the whole document (`core/doc_store.py:440-580`); concurrent writes retry and can fail after 5 seconds.
- Scaling path: batch/queue writes or move to a server database if multi-user support is ever added.

**Fallback search is linear:**
- Current capacity: fancy indexing works for a handful of documents, but BM25 fallback reads every row (`retrieval/hybrid_retriever.py:846-848`) and the JSON mirror rewrites on each ingest.
- Limit: corpus sizes in the tens of thousands of chunks make fallback searches and ingests noticeably slow.
- Scaling path: require LanceDB with an FTS index, or add a persisted inverted index.

**No pagination on list endpoints:**
- Files: `core/doc_store.py:383-393` (`list_documents`), `api/routers/chat.py:127-140` (sessions), `api/routers/documents.py:24-49`.
- Limit: responses grow with the library/history and the N+1 enrichment amplifies the cost.

## Dependencies at Risk

**CI and Docker resolve different dependency sets:**
- Risk: CI installs `requirements.txt` (`.github/workflows/ci.yml:30`), which uses broad floors (`docling>=2.0.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`, `fastapi>=0.115.0`; `requirements.txt:3-27`), while the Docker image installs `requirements-lock.txt` (`Dockerfile:34-36`). A new major release can pass CI and fail in the locked image, or vice versa.
- Impact: unreproducible test results and surprise production breakage.
- Migration plan: install `requirements-lock.txt` in CI (or a hash-pinned lock generated from the same resolver).

**PyMuPDF is capped below a major version:**
- Risk: `pymupdf>=1.24.0,<2.0` with an explicit note that 2.x is not regression-tested against crop/rasterization (`requirements.txt:18-20`).
- Impact: security and feature upgrades are blocked; multiple call sites depend on 1.x behavior (`ingestion/visual_analyzer.py`, `ingestion/ocr_fallback.py`, `api/routers/documents.py`).
- Migration plan: add PyMuPDF 2.x to the test matrix, then widen the cap.

**OCR package changes across Python versions:**
- Risk: `rapidocr-onnxruntime` for Python <3.13 and `rapidocr` for >=3.13 (`requirements.txt:16-17`) are different distributions with different result types; only Python 3.11 runs in CI (`.github/workflows/ci.yml:18-21`).
- Impact: Python 3.13 installs are untested and the parser shims in `ingestion/ocr_fallback.py` may drift.
- Migration plan: add a 3.13 CI job or pin a single OCR backend.

**Heavy, model-downloading dependency chain:**
- Risk: `docling` pulls `docling-ibm-models`, `torch`, and related packages (`requirements-lock.txt:82-92`, `:146`); `sentence-transformers==3.4.1` also requires torch and downloads weights on first use.
- Impact: large installs, slow cold starts, and failures on offline hosts; hydration/ingestion can block on downloads.
- Migration plan: document/prefetch model artifacts during setup (as `setup.py` already does for GGUF/OCR) and fail fast when absent.

**Rapidly changing cloud SDKs:**
- Risk: `groq==0.15.0` is pinned to an old client while `litellm>=1.50.0` floats; both are used by the cloud provider path (`providers/groq_provider.py`, `providers/litellm_provider.py`).
- Impact: upstream API changes or transitive conflicts can break cloud mode independently of the local path.
- Migration plan: pin both in the lock and exercise them in a scheduled compatibility job.

## Missing Critical Features

**Original PDF retention:**
- Problem: no code persists uploaded bytes, so page-image rendering and any "open the original" workflow cannot work even when `store_originals` is enabled. The flag is dead (`api/config.py:19`), and only the reader exists (`api/routers/documents.py:176`).
- Blocks: Evidence Lens page images, visual verification, re-OCR/re-extraction after model upgrades without re-upload.

**Persisted page text:**
- Problem: the `pages` table stores only counts/status (`core/doc_store.py:59-67`), so page-level reading and page-based summaries have no source of truth.
- Blocks: `GET /documents/{id}/pages/{n}` and `POST /summaries` as designed; summaries must reconstruct from chunks.

**Provider health/status probe:**
- Problem: `AiModel` exposes capabilities but no health/status method; `/health` calls a nonexistent API (`api/routers/system.py:38-53`).
- Blocks: accurate readiness reporting, Docker health checks, and UI status.

**Authentication/authorization:**
- Problem: none exists; the design assumes a single trusted local user (`start.py:80-82`). The Docker path binds all interfaces without the launcher guard.
- Blocks: safe multi-user or remote deployment.

**Request body limits:**
- Problem: uploads are buffered before size validation (`api/routers/documents.py:61-65`), and no ASGI body limit is configured.
- Blocks: robust operation under accidental or malicious large payloads.

## Test Coverage Gaps

**Ingestion service has no end-to-end coverage:**
- What's not tested: `IngestionService.ingest_pdf` from validation through persistence/indexing; no test imports the service.
- Files: `tests/` (no `test_ingestion.py`), `services/ingestion.py`.
- Risk: the P0 `status="indexing"` failure ships despite 485 passing tests.
- Priority: High.

**Summary generation path is untested:**
- What's not tested: `POST /summaries` job creation and `Summarizer.summarize_document` through the API; `tests/test_summaries_api.py` only covers cache-hit, not-found, and clear.
- Files: `tests/test_summaries_api.py:35-60`, `api/routers/summaries.py`.
- Risk: three simultaneous signature/attribute errors go unnoticed.
- Priority: High.

**Document page endpoints are only checked for route existence:**
- What's not tested: response shape and behavior of `GET /documents/{id}/pages/{n}` and `/image`.
- Files: `tests/test_openapi_contract.py:19-21` lists paths only; `api/routers/documents.py:133-199`.
- Risk: the missing `get_page`/wrong field names and permanent 404 for images are invisible.
- Priority: High.

**Chat history serialization is untested after an answer:**
- What's not tested: `GET /chat/sessions/{id}` after `_finish` persists a `GroundingReport`; `tests/test_chat_api_sse.py:44-82` streams then deletes without reading the session.
- Files: `tests/test_chat_api_sse.py`, `api/routers/chat.py:92-172`.
- Risk: every real session with history returns 500.
- Priority: High.

**Embedding export fallback is untested:**
- What's not tested: `HybridRetriever.export_embeddings` when LanceDB is unavailable or a query fails.
- Files: `retrieval/hybrid_retriever.py:1107-1160`, `api/routers/visualize.py`.
- Risk: the `self._store` `AttributeError` is only seen at runtime.
- Priority: Medium.

**Health endpoint provider failure is untested:**
- What's not tested: the exception path in `_build_health`.
- Files: `api/routers/system.py:32-55`.
- Risk: the endpoint has never reported a healthy provider.
- Priority: Medium.

**Evidence Lens/originals retention is untested:**
- What's not tested: whether any component writes `data/originals/<sha256>.pdf`; no test asserts the file exists after upload.
- Files: `api/routers/documents.py:165-199`, `api/config.py:19`.
- Risk: the feature is permanently broken with a 404 that looks like a configuration issue.
- Priority: Medium.

**Frontend has no automated tests:**
- What's not tested: API client mapping, SSE event handling, grounding rendering, Evidence Lens behavior.
- Files: `frontend/package.json:5-11` (no test script or test runner); CI only runs typecheck/build (`.github/workflows/ci.yml:79-84`).
- Risk: schema drift (already present for grounding) is not caught until manual use.
- Priority: Medium.

**Test-count claim has drifted:**
- What's not tested: nothing new, but the README badge says 479 passed (`README.md:10`) while the suite collects 485 tests.
- Files: `README.md:10`, `tests/`.
- Risk: low, but it undermines the badge as a signal.
- Priority: Low.

---

*Concerns audit: 2026-11-14*
