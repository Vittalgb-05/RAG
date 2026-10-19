# Codebase Concerns

**Analysis Date:** 2026-10-19

## Verified Context

- The full suite passes locally on Python 3.13.5: `283 passed` (`python -m pytest tests/ -q`). The suite is offline and heavily mocked; passing tests do not exercise the real UI interaction path.
- Runtime entry points are `start.py` (launcher), `main.py` (Streamlit UI), and `Dockerfile` / `docker-compose.yml`. The UI is a five-workspace Streamlit app routed from `main.py:316-354`.
- `models/` (`*.gguf`), `tools/`, `data/`, and `.cache/` are gitignored (`.gitignore:10,17,18,23`); `git ls-files` contains no model weights or binaries. No `.env` file is present in the working tree and secret files were not read.
- PostgreSQL/FAISS are not used. Storage is SQLite (`data/documents.db`), LanceDB (`data/lancedb/`), JSON fallback (`data/lancedb/fallback_store.json`), and raw extraction JSON (`.cache/<sha>/`).

## Tech Debt

**Ingestion and chat orchestration live inside a 912-line Streamlit view module:**
- Issue: validation, Docling parsing, OCR, VLM analysis, SQLite writes, LanceDB indexing, cache writes, chat retrieval, citation rendering, library actions, and settings all live in `ui/views.py`. The upload loop alone is `ui/views.py:93-301`; chat submission is `ui/views.py:351-565`.
- Impact: no transaction boundary, no reusable service layer, no direct unit-test seam, and UI/back-end signature drift is undetected (see the critical `doc_id` bug below).
- Fix approach: extract an `IngestionService` (`validate -> extract -> OCR -> visuals -> persist -> index -> cache`) and a `ChatService` (`retrieve -> assemble -> stream -> validate`); leave `ui/views.py` as widget wiring. Add an end-to-end test that drives the service with `tests/data/corpus/`.

**Evidence elements are persisted but never consumed:**
- Issue: `doc_store.record_evidence_elements` is called at `ui/views.py:242-246`, but `DocStore.get_evidence_for_doc` (`doc_store.py:410-435`) has no production caller. VLM descriptions and table/visual elements never enter retrieval, chat context, or summarization.
- Impact: the core "visual understanding" capability is effectively write-only; answers cannot cite figures or table evidence, and the summarizer's "Tables & Figures" profile has no visual inputs.
- Fix approach: index evidence elements as retrievable snippets (or attach them to adjacent chunks), include them in `HybridRetriever` candidates with source labels such as `vlm:<model>`, and add a test that a figure-only question retrieves the figure description.

**Duplicate vector storage per session:**
- Issue: `HybridRetriever.index_chunks` always writes every vector into the in-memory `VectorIndex` fallback (`hybrid_retriever.py:297-310`) and then into LanceDB (`hybrid_retriever.py:312-364`). `LocalEmbedding` also owns an unused `VectorIndex` (`local_embedding.py:72`) and accepts an unused `db_uri` (`local_embedding.py:56,66`).
- Impact: each browser session duplicates the full vector set in Python memory; fallback JSON rewrites are O(N); the `LocalEmbedding.store` is dead weight.
- Fix approach: populate the fallback only when LanceDB is unavailable, or store only chunk metadata for BM25; remove `LocalEmbedding.store`/`db_uri` or make it the single backend explicitly.

**Legacy/dead API surface:**
- Issue: `HybridRetriever.search()` and `get_context()` emit deprecation warnings (`hybrid_retriever.py:641-659`); `LocalEmbedding.search_hybrid()` is deprecated (`local_embedding.py:113-121`); `ask_a_question_from_pdf_stream(pdf_path=...)` only raises (`local_llm.py:245-258`); `GroqProvider` remains a second cloud client alongside `LiteLLMProvider` (`local_llm.py:174-180`).
- Impact: multiple code paths hide the real contract, and the legacy `GroqProvider` bypasses the consent gate (see Security).
- Fix approach: delete the deprecated branches and the second cloud adapter, or make `GroqProvider` a thin wrapper with `user_consented` enforcement and migrate tests.

**Documentation and implementation drift:**
- Issue: `README.md:17` advertises "248 Passed" while the suite has 283 tests; the README architecture diagram claims "SQLite FTS5 BM25 Search" and a LanceDB "Hybrid Vector Index," but no SQLite FTS5 table exists and `create_fts_index` is never called (`hybrid_retriever.py:433-441`). The model is labeled Qwen3-VL, while `setup.py:59-68` downloads Qwen2-VL weights and saves them under a Qwen3 filename. `main.py:1-12` advertises "retry, re-index" in the library, but the library exposes only Open/Delete (`ui/views.py:737-758`).
- Impact: operators and future agents make wrong assumptions about indexing, model identity, and available actions.
- Fix approach: make README/tests/model names match the implementation, or implement the missing behavior; add a doc check to CI.

**Dependency/install-path drift:**
- Issue: `requirements.txt` leaves `docling`, `lancedb`, `litellm`, `pymupdf`, `pyarrow`, `pillow`, and OCR packages floating (`requirements.txt:10-18`). `Dockerfile:25-27` copies the lockfile but installs `requirements.txt`; `setup.py:496-533` also defaults to `requirements.txt`. The lockfile is compiled for Python 3.11 (`requirements-lock.txt:1-3`) while local development runs 3.13.5.
- Impact: Docker and `setup.py` installs are not reproducible; CI validates the lock, not the path users actually install.
- Fix approach: make `requirements-lock.txt` the single source for Docker, CI, and setup; add a lock-refresh check and a 3.13 CI job.

**Inconsistent logging and swallowed failures:**
- Issue: `print()` remains in production paths (`upload_validation.py:106`, `doc_store.py:154`, `pdf_reader.py:131`), while newer modules use `logging`. Failures are frequently downgraded to `logger.warning` or `pass` (`ui/views.py:243-246` evidence persistence, `hybrid_retriever.py:357-364` LanceDB writes, `main.py:78-85` provider close, `setup.py:32-41`).
- Impact: users see "indexed successfully" when a non-fatal persistence step failed; diagnostics are split between stdout and logs.
- Fix approach: standardize on module loggers, surface non-fatal persistence failures in the UI, and reserve silent handling for cleanup/telemetry only.

**Duplicated constants and state keys:**
- Issue: `MAX_CHAT_TURNS = 50` is defined independently in `main.py:44` and `ui/views.py:37`; session keys are initialized in `main.py:109-126` and re-read/reset across `main.py` and `ui/views.py`.
- Impact: tuning one copy silently diverges chat bounding behavior.
- Fix approach: move constants and session-key definitions into a shared `config.py`/`state.py` and import them.

**Heavy import-time dependencies:**
- Issue: `main.py:25` imports `litellm_provider`, which imports `litellm`; `ui/views.py:15` imports `docling_reader`, which imports Docling; `ui/hydration.py` constructs `LocalEmbedding` and loads SentenceTransformers when persisted chunks exist.
- Impact: cold-start latency and memory are paid before the first interaction; optional cloud/OCR stacks are loaded even when unused.
- Fix approach: lazy-import `litellm` and Docling at first use, and hydrate the embedding model only when a query or ingest actually needs it.

## Known Bugs

**Chat submission raises `TypeError` for every real retriever (Critical):**
- Symptoms: after at least one document is indexed, entering any question in "Ask Documents" raises `TypeError: HybridRetriever.search_hybrid() got an unexpected keyword argument 'doc_id'`.
- Files: `ui/views.py:481-483` calls `active_retriever.search_hybrid(search_query, k=5, doc_id=doc_filter)`; the real signatures are `HybridRetriever.search_hybrid(self, query, k=5, k_rrf=60)` (`hybrid_retriever.py:534-539`) and `LocalEmbedding.search_hybrid(self, question, k=5)` (`local_embedding.py:113`).
- Trigger: any chat prompt while `st.session_state.hybrid_retriever` or `st.session_state.local_embedding` exists; `doc_filter` is passed even when it is `None`.
- Workaround: none in the UI.
- Fix approach: add an optional `doc_id`/`doc_ids` parameter to `HybridRetriever.search_hybrid` and filter dense/FTS candidates before RRF (with SQL escaping), or remove the `doc_id` keyword and implement filtering at the call site. Add a UI-level test that invokes the chat path with a real `HybridRetriever` signature.

**Ingestion can persist `status="indexed"` with zero chunks (High):**
- Symptoms: embedding, LanceDB indexing, or chunk-recording failures occur after the document row is written; the library shows "Indexed" but chat has no evidence and the document cannot be retried.
- Files: document row is written as `status="indexed"` at `ui/views.py:227-240`; the extraction `try/except` ends at `ui/views.py:220-224`; embedding/indexing (`ui/views.py:251-266`) and cache writes (`ui/views.py:268-279`) run outside any guarded rollback.
- Trigger: `LocalEmbedding.get_embeddings` OOM, SentenceTransformers download failure, `HybridRetriever.index_chunks` exception, or `DocStore.record_chunks` failure.
- Impact: stale "indexed" metadata, no chunks, no failed-document signal, and repeated attempts are blocked by dedup.
- Fix approach: wrap all post-extraction steps in one guarded block; on failure delete/upsert the document as `status="failed"`, remove partial chunks, and offer Retry. Never write `status="indexed"` before durable chunks exist.

**Cloud provider selection still sends traffic to Groq (High):**
- Symptoms: choosing "OpenAI (GPT-4o mini)" or "Anthropic (Claude 3.5 Haiku)" in Settings leaves `cloud_model` at `groq/llama-3.3-70b-versatile`, so consent says one provider but requests use Groq (or fail because the OpenAI/Anthropic key is absent).
- Files: `main.py:122` initializes `cloud_model`; `main.py:166-172` passes `st.session_state.cloud_model` to `LiteLLMProvider`; `ui/views.py:844-852` updates only `cloud_provider`. `cloud_api_keys` is initialized but never populated by any UI input (`main.py:123`; only reset at `main.py:89`).
- Trigger: enabling Cloud Mode, selecting a non-Groq provider, then sending a query.
- Impact: privacy-relevant destination mismatch; non-Groq providers are unusable from the UI.
- Fix approach: centralize a `provider -> (model, env_var)` map; update `cloud_model` and validate the key on selection; add an API-key input or document env-only keys explicitly. Add tests for each provider selection.

**Persistent summary cache is never read by the UI (Medium):**
- Symptoms: after restarting or reselecting a document, a previously generated summary is not shown until "Generate Summary" is clicked again; the "Loaded from persistent SQLite cache" caption is effectively unreachable.
- Files: `Summarizer.summarize_document` stores `model_version=f"{model_name}:{CONFIG_VERSION}"` (`summarizer.py:330-337`, `summarizer.py:403-414`); the UI read path passes only `ai_model.model_name` (`ui/views.py:652`). `DocStore.get_summary` returns `None` when the stored non-empty version differs (`doc_store.py:481-516`).
- Trigger: reload the Summarizer for any document with a cached summary. Verified with a temporary store: stored `qwen3-vl-2b:docling-1000-200-v1`, lookup `qwen3-vl-2b` returns `None`.
- Impact: repeated summarization cost/tokens; misleading cache caption; cloud mode re-sends excerpts unnecessarily.
- Fix approach: pass `f"{ai_model.model_name}:{CONFIG_VERSION}"` (or route reads through `Summarizer`) and add a UI-level cache-hit test.

**Failed documents cannot be retried after deletion (Medium):**
- Symptoms: a PDF that failed ingestion remains blocked after the user deletes it and re-uploads the same file; the UI says "Reset session or delete to retry," but Delete does not clear the block.
- Files: failure set is checked at `ui/views.py:144-145`; Delete removes `doc_ids`, `indexed_files`, and `document_metadata` but not `failed_doc_ids` (`ui/views.py:744-758`).
- Fix approach: `st.session_state.failed_doc_ids.discard(doc.doc_id)` on delete and add an explicit Retry action that clears the failure and re-runs ingestion.

**LanceDB write failures are reported as successful indexing (Medium):**
- Symptoms: `index_chunks` catches LanceDB persistence errors, leaves the in-memory fallback populated, but does not persist the fallback when LanceDB is active; the upload still toasts success. After restart the chunks are gone.
- Files: `hybrid_retriever.py:357-364` logs the error and skips `_save_fallback_store()`; `close()` persists the fallback only when LanceDB is inactive (`hybrid_retriever.py:156-161`); `ui/views.py:292-293` reports success unconditionally.
- Fix approach: on LanceDB write failure, persist the fallback, mark the index degraded, and surface a warning; only toast success after a durable write.

**Large-document summarization can overflow the 4K context (Medium):**
- Symptoms: map-reduce summaries for long PDFs fail, truncate, or lose citations because the consolidation stage runs only one level and the reduce prompt is unbounded.
- Files: `summarizer.py:24-29` (`FAST_PATH_TOKEN_LIMIT=2500`, `MAX_BATCH_TOKENS=2000`), `summarizer.py:233-300` (one optional consolidation, then final reduce), `summarizer.py:226-231` / `summarizer.py:294-299` (1500 output tokens). The fast path allows 2500 input tokens plus system/user prompts and 1500 output in a 4096-token window.
- Trigger: documents over roughly 2,500 estimated tokens (fast path), especially hundreds of pages producing many map batches.
- Fix approach: recursively consolidate until the reduce input fits a computed budget (`context_window - output_reserve - system_prompt`), and use `estimate_tokens` to enforce it. Do not rely on llama-server to truncate silently.

**Dense evidence scores are not cosine scores and differ by backend (Low):**
- Symptoms: the score shown in the evidence drawer is not comparable across documents and changes when LanceDB falls back to the in-memory store.
- Files: LanceDB table is created without a metric (`hybrid_retriever.py:342`), then `score = 1 - _distance` assumes cosine (`hybrid_retriever.py:410-415`); the fallback uses `VectorIndex` cosine distance (`vector_index.py`).
- Impact: ranking is usually monotonic for unit vectors, but displayed confidence is misleading and thresholds based on score are unreliable.
- Fix approach: create the table with `metric="cosine"`, or convert L2 to cosine explicitly (`cos = 1 - d²/2` for unit vectors), and label the score consistently.

## Security Considerations

**Evidence snippets bypass the Markdown sanitizer (Medium/High):**
- Risk: retrieved chunk text is rendered as `st.markdown(f"> {content}")` without `sanitize_display_markdown` (`ui/views.py:435`, `ui/views.py:540`). A PDF containing `![x](https://attacker.example/pixel)` causes the browser to fetch that URL when the evidence drawer is opened, contradicting the "zero network egress" claim (`ui/views.py:512`).
- Files: `ui/views.py:435,540`; sanitizer exists at `ui/sanitizer.py` and is applied only to model output and summaries (`ui/views.py:398,674`).
- Current mitigation: Streamlit strips raw `<script>`, and citations/model responses are sanitized.
- Recommendations: apply `sanitize_display_markdown` to every snippet and filename; render evidence as plain text/code if Markdown is not required; consider a CSP for deployed instances.

**Filenames are interpolated into `unsafe_allow_html` blocks without escaping (Low/Medium):**
- Risk: a filename containing HTML (possible on Linux/container-mounted filesystems) is injected into citation chips (`ui/components.py:110-117`) and library cards (`ui/views.py:717-725`), enabling markup injection/XSS in the local UI.
- Files: `ui/components.py:110-117`, `ui/views.py:324`, `ui/views.py:717-725`; filenames come from the uploader at `ui/views.py:104` and are only validated for PDF magic/size/pages (`upload_validation.py:64-113`).
- Recommendations: HTML-escape filenames with `html.escape`, or render them via `st.text`/Markdown code spans instead of raw HTML.

**Untrusted PDFs are parsed in-process by multiple native parsers (Medium):**
- Risk: decompression bombs, malformed structures, and parser CVEs can crash or exhaust the Streamlit process. `pypdf.PdfReader` is constructed before the page cap is checked (`upload_validation.py:90-94`), then Docling, PyMuPDF, and RapidOCR parse the same bytes.
- Current mitigation: 50 MB / 500-page caps, `%PDF-` check, page-level try/except in Docling/OCR/visual code, and a 2048×2048 render guard (`ocr_fallback.py:112-121`, `visual_analyzer.py:179-197`).
- Recommendations: validate page dimensions and embedded-image counts before parsing, run extraction in a memory-limited worker process, and keep parser versions pinned/patched.

**`setup.py` archive extraction lacks traversal and checksum protection (Medium):**
- Risk: `zipfile.extractall` / `tarfile.extractall` can write outside `tools/llama-server` via `../` members or symlinks (`setup.py:342-346`). Model/archive downloads verify only a minimum byte size (`setup.py:122,174`), not SHA-256 or signatures, despite multiple mirrors (`setup.py:59-88`).
- Current mitigation: URLs are hardcoded to GitHub/Hugging Face mirrors over HTTPS.
- Recommendations: validate archive members and use `filter="data"` (Python 3.12+) or a temp-dir extraction; publish and verify checksums for all downloaded assets.

**Cloud consent is enforced only by the UI/provider wrapper (Medium):**
- Risk: `AiModel._detect_provider` constructs a `GroqProvider` when `cloud_mode=True` and no explicit provider is supplied (`local_llm.py:174-180`); `GroqProvider` has no `user_consented` check and no credential scrubbing (`groq_provider.py:18-52,99-161`). A programmatic caller can transmit document text with only an environment key.
- Current mitigation: `main.py` always passes a consented `LiteLLMProvider` (`main.py:159-178`), and `LiteLLMProvider` raises `PermissionError` without consent (`litellm_provider.py:142-148`).
- Recommendations: remove the implicit Groq construction, require an explicit consented cloud provider for `cloud_mode=True`, and add a defense-in-depth consent flag to every non-local provider.

**Purge/delete leave copies at rest and in session (Medium privacy):**
- Risk: `DocStore.purge_all` only issues `DELETE` statements (`doc_store.py:609-619`) without `VACUUM`, `PRAGMA secure_delete`, or WAL truncation; the SQLite file and `-wal`/`-shm` remain. Purge also leaves `.cache/<sha>/pages.json` and `chunks.json` (written at `ui/views.py:268-277`) and does not clear `chat_history` or `summary_*` session keys (`ui/views.py:768-778`). Single-document Delete leaves both the cache directory and session summary/chat entries (`ui/views.py:744-758`).
- Impact: extracted document text and prior answers survive a user-requested erase, despite the warning "permanently delete ... disk caches" (`ui/views.py:763-766`).
- Recommendations: remove the document's cache directory on Delete, clear `chat_history`/`summary_*` on purge, then `VACUUM` and remove WAL files (or recreate the DB); document secure-erase limits on SSDs.

**Container and UI exposure are not hardened (Medium in shared environments):**
- Risk: `Dockerfile:3` uses an unpinned `python:3.11-slim-bookworm` base; there is no `USER`, so the app runs as root; the CMD binds `0.0.0.0:8501` (`Dockerfile:46`). `docker-compose.yml:8` publishes `8501` and `:34` publishes the unauthenticated llama-server on `8080` (`--host 0.0.0.0` at compose line 43). The Streamlit UI has no authentication.
- Current mitigation: the project is documented as single-user/local.
- Recommendations: run as a non-root user, pin base/image digests, bind both services to `127.0.0.1` by default, and state clearly that the UI is for trusted local networks only.

**Prompt-injection and citation validation are heuristic (Medium):**
- Risk: `<document_context>` is escaped and the system prompt says to ignore directives (`prompt_budget.py:13-40`), but detection matches a fixed phrase list (`citation_validator.py:34-83`) and the validator checks only that `[En]` ranks are in range, not that claimed sentences are supported (`citation_validator.py:145-219`). Paraphrased injections and unsupported claims can pass; legitimate security documents quoting the phrases can be falsely rejected.
- Recommendations: treat injection detection as a warning, add claim/entailment coverage checks, and distinguish "document contains a directive" from "model followed it."

**First-run model downloads are not offline (Low/Medium):**
- Risk: SentenceTransformers, Docling layout/table models, and RapidOCR ONNX weights are fetched on first use (`local_embedding.py:50-86`, `setup.py:196-234`), so a nominally offline deployment makes outbound requests until caches are warm.
- Recommendations: pre-cache/ship weights in the installer, add an explicit offline/network-kill mode, and document which first-run downloads are expected.

## Performance Bottlenecks

**No vector ANN or FTS index is ever created (High at scale):**
- Problem: `create_fts_index()` exists but has no production call site (`hybrid_retriever.py:433-441`); no `create_index()` is called anywhere. Dense search performs a full LanceDB scan (`hybrid_retriever.py:405-421`), and FTS falls back to `_bm25_search_fallback`, which tokenizes every stored document and recomputes document frequencies per query (`hybrid_retriever.py:443-503`).
- Files: `hybrid_retriever.py:405-503`.
- Cause: index creation is optional/manual and never wired into `_init_table` or `index_chunks`.
- Improvement path: call `table.create_fts_index("content", replace=True)` after table creation/updates and `table.create_index(metric="cosine")` for vectors; benchmark with `scripts/benchmark_baseline.py`.

**Per-session vector duplication and JSON rewrites (Medium/High):**
- Problem: every session builds a `VectorIndex` containing all vectors (`hybrid_retriever.py:297-310`), and every fallback save serializes all documents and vectors to one JSON file (`hybrid_retriever.py:169-192`).
- Cause: fallback is always maintained even when LanceDB is healthy.
- Improvement path: keep the fallback disabled when LanceDB is active; use an append-only or SQLite-backed lexical index; avoid full JSON rewrites.

**Synchronous ingestion blocks the UI (High):**
- Problem: Docling conversion, OCR, up to 20 sequential VLM calls, embeddings, and indexing run inside one Streamlit script thread (`ui/views.py:154-293`). A scanned/figure-heavy 500-page PDF can block for minutes with no cancellation.
- Improvement path: move ingestion to a background worker/queue with progress and cancellation; persist job state so a browser refresh can resume.

**Sequential VLM calls per document (Medium):**
- Problem: `analyze_visual_elements` processes up to 20 regions one-by-one, each a full HTTP round trip with a base64 crop and a 60s gate timeout (`visual_analyzer.py:202-309`; `max_regions=20`). No description cache or batching exists.
- Improvement path: cache by `(doc_id, page, bbox, model)` in DocStore, batch where supported, and make the region cap configurable.

**Heavy cold start from eager imports and hydration (Medium):**
- Problem: `main.py` imports LiteLLM, `ui/views.py` imports Docling, and hydration loads SentenceTransformers when chunks exist (`ui/hydration.py:44-60`), all before the first query.
- Improvement path: lazy imports and lazy hydration; show a lightweight UI while models load.

**Health probing on every rerun (Low):**
- Problem: `ai_model.check_health()` runs at `main.py:188` on every rerun; when the local server is down, `LlamaCppProvider` performs an HTTP connect with a 2s timeout (`llama_cpp_provider.py:89-118`) and may re-probe providers (`local_llm.py:155-170`).
- Improvement path: cache health for a short TTL and reuse the cached result across reruns.

**OCR thread pool is serialized by a lock (Low/Medium):**
- Problem: `apply_conditional_ocr` uses a `ThreadPoolExecutor` (`ocr_fallback.py:391-400`), but `OcrEngine.ocr_page_image` wraps recognition in `self._ocr_lock` (`ocr_fallback.py:135-146`); only rendering overlaps.
- Improvement path: use a process pool or one recognizer per worker, or document that the pool parallelizes rendering only.

**BM25 fallback can load up to 10,000 rows with vectors (Medium):**
- Problem: when the in-memory fallback is empty, `_bm25_search_fallback` reads `self._table.search().limit(10000)` (`hybrid_retriever.py:452-460`), materializing vector columns for lexical search.
- Improvement path: query only `chunk_id`/`content` columns or create the FTS index.

## Fragile Areas

**Streamlit session-state coupling:**
- Files: `main.py:109-186`, `ui/views.py`, `ui/hydration.py`.
- Why fragile: document metadata, retriever, embedding model, chat history, cloud consent, summary keys, and uploader key are mutable globals coordinated across modules. Delete/purge/upload/hydration paths each update a different subset (e.g., purge at `ui/views.py:768-778` vs. reset at `main.py:57-89`).
- Safe modification: centralize state initialization/reset in one helper; add assertions/tests for key sets after each lifecycle action.
- Test coverage: lifecycle tests use mock sessions; none exercises a real Streamlit script rerun.

**UI/back-end contract drift:**
- Files: `ui/views.py:481-483`, `hybrid_retriever.py:534`, `local_embedding.py:113`.
- Why fragile: the UI uses `hasattr` duck typing and passes keyword arguments by convention; mock-based tests accept anything. The `doc_id` bug is the concrete failure.
- Safe modification: define a `RetrieverProtocol` (or typed interface) and call it directly; add contract tests with real signatures.

**LanceDB schema/metric/migration drift:**
- Files: `hybrid_retriever.py:194-205` opens an existing `chunks` table without schema migration; `hybrid_retriever.py:342` creates it without a metric; `hybrid_retriever.py:357-364` can leave a partially written table.
- Why fragile: an existing table keeps its old schema/metric; changes to chunk fields or distance semantics silently produce missing columns or inconsistent scores.
- Safe modification: version the table schema, recreate/rebuild when fields change, and assert schema on open.
- Test coverage: tests create fresh temp tables, so upgrades are not exercised.

**Partial ingestion state:**
- Files: `ui/views.py:154-293`.
- Why fragile: side effects span SQLite, LanceDB, `.cache`, and session state with no transaction or compensating delete. Any exception outside the extraction `try` leaves an inconsistent "indexed" record.
- Safe modification: model ingestion as a job with explicit `failed` status and cleanup; test failure injection at each step.

**Model/provider coupling:**
- Files: `main.py:122,159-178`, `ui/views.py:844-852`, `litellm_provider.py`, `local_llm.py:145-180`.
- Why fragile: provider identity, model string, consent state, and API key resolution are spread across session state, `AiModel`, and `LiteLLMProvider`; changing one does not update the others (the cloud-provider bug).
- Safe modification: encapsulate a `ProviderSelection` value object and rebuild the provider from it atomically.

**Optional parser degradation:**
- Files: `docling_reader.py:24-32`, `ocr_fallback.py:21-27`, `ui/views.py:161-165`.
- Why fragile: Docling/OCR imports are optional; failure falls back to basic text extraction or no OCR, and the UI may still report success for an empty document (`ui/views.py:292-293`).
- Safe modification: treat zero/low chunk counts as an ingestion failure with a visible warning; assert non-empty chunks in tests.

**Stateful deletion semantics:**
- Files: `ui/views.py:744-758`, `doc_store.py:587-619`.
- Why fragile: Delete and Purge are distributed across SQLite, LanceDB, `.cache`, session keys, and chat history; each path forgets a different subset.
- Safe modification: one `delete_document`/`purge_all` service that owns all stores and session cleanup.

## Scaling Limits

- **Document size:** 50 MB and 500 pages per upload (`upload_validation.py:15-16`), with up to 20 VLM regions (`visual_analyzer.py:208`). Larger documents are rejected, not streamed.
- **VRAM:** one 4K-context GGUF model with `-ngl 28` and a process-level `InferenceGate` (`local_llm.py:26-105`); concurrent chat/summarization serializes. Multiple worker processes would each hold their own gate and could exceed 4 GB.
- **Retrieval:** linear dense scan plus Python BM25 (`hybrid_retriever.py:405-503`); query latency grows with total chunks. No ANN/FTS index is built.
- **Memory:** per-session fallback vectors plus Python document dicts; at 10k chunks a 384-dim float vector set is ~15 MB, before dict/JSON overhead. Every new browser session repeats it (`hybrid_retriever.py:113-119,297-310`).
- **SQLite:** one writer at a time with WAL and a 5s busy timeout (`doc_store.py:131-135`); many concurrent sessions can hit lock contention during upload/summary writes.
- **Summary cost:** map-reduce performs one generation per 2,000-token batch plus consolidation/reduce calls (`summarizer.py:233-300`), all serialized; long documents can require hundreds of calls.

## Dependencies at Risk

**PyMuPDF is AGPL-3.0/commercial (High legal risk):**
- Risk: `pymupdf>=1.24.0` is used for OCR rendering and visual crops, while the project is MIT (`docs/LICENSES.md`). Network distribution or binary redistribution can trigger AGPL obligations.
- Impact: blocks closed-source distribution or requires a commercial license.
- Migration plan: replace rendering/cropping with a permissive stack (e.g., `pypdfium2` or `pdf2image` + Poppler) or obtain an Artifex license; keep the license disclosure current.

**Floating runtime dependencies (Medium):**
- Risk: `docling>=2.0.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`, `pymupdf`, `pyarrow`, `pillow`, and `rapidocr` are unpinned in `requirements.txt`; the lock is Python 3.11-only. Transitive ML packages (torch/transformers) are large and version-sensitive.
- Impact: `setup.py` and Docker installs can resolve breaking versions; CI may pass against a different stack than users run.
- Migration plan: install from the lock everywhere; refresh with `uv pip compile`; add a 3.13 lock/job.

**Two OCR package families (Medium):**
- Risk: `rapidocr-onnxruntime` for `<3.13` and `rapidocr` for `>=3.13` (`requirements.txt:11-12`) have different APIs and ONNX runtime behavior; only the import shim (`ocr_fallback.py:21-27`) masks the difference.
- Impact: OCR can be silently unavailable or behave differently by Python version; tests on 3.11 do not cover the 3.13 path.
- Migration plan: standardize on `rapidocr`/`onnxruntime` on all supported versions, add a 3.13 OCR integration test.

**Two cloud clients (Medium):**
- Risk: `groq` plus `litellm` duplicate provider logic and credential handling; `groq` is pinned to `0.15.0` while `litellm` floats. `GroqProvider` lacks consent/scrubbing.
- Impact: inconsistent privacy behavior and dependency surface.
- Migration plan: remove `groq_provider.py` and the direct `groq` dependency, or isolate it as a tested optional adapter.

**Unpinned container images (Medium):**
- Risk: `python:3.11-slim-bookworm` (`Dockerfile:3`) and `ghcr.io/ggml-org/llama.cpp:server-cuda` (`docker-compose.yml:30`) are mutable tags.
- Impact: non-reproducible builds and silent upstream changes.
- Migration plan: pin digests and update them deliberately.

**Lock/environment mismatch (Low/Medium):**
- Risk: `requirements-lock.txt:541` pins `torch==2.14.1`, while the local runtime has `torch 2.6.0+cu124`; tests pass on the local stack, not the locked one.
- Impact: CI and user environments can diverge on CUDA/torch behavior.
- Migration plan: run CI on both the lock and a representative GPU/Windows environment, or align the local env with the lock.

## Missing Critical Features

**Visual/table evidence is not used in answers or summaries:**
- Problem: VLM descriptions and table elements are stored (`doc_store.py:364-408`) but never retrieved (`get_evidence_for_doc` has no caller); chat and summarization use only text chunks.
- Blocks: the core promise of visual understanding and the "Tables & Figures" summary profile's ability to use actual figures/tables.

**No retry/re-index action for failed ingestion:**
- Problem: the library exposes only Open/Delete (`ui/views.py:737-758`), and Delete does not clear `failed_doc_ids`; `main.py:1-12` advertises retry/re-index.
- Blocks: recovery from transient OOM/parser failures without a full session reset.

**No cloud API-key entry and incomplete provider mapping:**
- Problem: `cloud_api_keys` is initialized and reset but never editable (`main.py:89,123`; no input in `ui/views.py:787-878`); provider selection does not update `cloud_model`.
- Blocks: usable OpenAI/Anthropic cloud mode from the UI.

**No page-image/source viewer for citations:**
- Problem: the evidence drawer shows text and optional bbox numbers only (`ui/views.py:431-442,536-541`); there is no rendered page/crop preview to visually verify a citation.
- Blocks: true "verifiable page-level citations" for scanned/visual documents.

**No authentication or multi-user isolation:**
- Problem: the Streamlit UI has no auth and binds `0.0.0.0` in Docker (`Dockerfile:46`); session state is the only isolation. This is acceptable for the stated single-user laptop target but unsafe on a shared network.
- Blocks: safe LAN/hosted deployment without an external auth proxy.

**No real lexical/vector indexes:**
- Problem: `create_fts_index` and vector index creation are never called (`hybrid_retriever.py:433-441`), so the advertised "hybrid vector index" is a full scan plus Python BM25.
- Blocks: sub-second retrieval at larger corpora.

## Test Coverage Gaps

**The chat submission path is untested with a real retriever:**
- What's not tested: `render_chat_view` prompt handling, `search_hybrid(..., doc_id=...)`, retrieval-result plumbing, and streaming/citation display.
- Files: `ui/views.py:351-565`; tests only cover sanitizer/chip/state helpers (`tests/test_ui_smoke.py`, `tests/test_main_ui.py`).
- Risk: the critical `TypeError` ships undetected.
- Priority: High.

**Ingestion orchestration and failure recovery are untested:**
- What's not tested: partial failures after the document row is written, embedding/index exceptions, cache-write failures, and retry behavior.
- Files: `ui/views.py:93-301`; parser tests use mocks/corpus pieces, not the full loop.
- Risk: "indexed with zero chunks" and orphaned metadata.
- Priority: High.

**Cloud provider/model/consent matrix is only partially tested:**
- What's not tested: Settings provider selection updating `cloud_model`, per-provider API-key resolution, and the consent dialog's effect on the actual request destination.
- Files: `ui/views.py:787-878`, `main.py:159-178`; `tests/test_cloud_privacy.py` and `tests/test_main_ui.py` test pieces but not the selectbox-to-model mapping.
- Risk: privacy-relevant misrouting.
- Priority: High.

**Deletion/purge residue is untested:**
- What's not tested: `.cache` removal, summary/chat session cleanup, SQLite WAL/VACUUM, and retry-set cleanup after Delete.
- Files: `ui/views.py:744-778`, `doc_store.py:587-619`.
- Risk: user believes data is erased when excerpts remain.
- Priority: Medium.

**Real parser and OCR integration is thin:**
- What's not tested: Docling/RapidOCR/PyMuPDF end-to-end on scanned and visual PDFs across Python 3.11/3.13, including zero-chunk detection.
- Files: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`; heavy dependencies and network are mocked.
- Risk: optional-dependency regressions and silent OCR absence.
- Priority: Medium.

**No coverage measurement or quality evaluation gate:**
- What's not tested: line/branch coverage thresholds; retrieval quality, citation precision/recall, or abstention accuracy on a labeled set.
- Files: `.github/workflows/ci.yml` runs Ruff plus `pytest` only; `scripts/benchmark_baseline.py` measures latency, not answer quality.
- Risk: green CI can coexist with broken user paths and degraded grounding.
- Priority: Medium.

**Platform matrix is incomplete:**
- What's not tested: Windows (the primary target) and Python 3.13 in CI; CI uses `ubuntu-latest` + Python 3.11 (`.github/workflows/ci.yml:10-21`), while local development is 3.13.5 and the lock targets 3.11.
- Risk: Windows path/encoding issues, OCR package differences, and torch/CUDA drift are caught only by users.
- Priority: Medium.

**No adversarial/security regression tests:**
- What's not tested: archive path traversal in `setup.py`, HTML/URL injection through filenames/evidence, oversized page rendering, and purge residue.
- Files: `setup.py:312-349`, `ui/views.py:435,540`, `ui/components.py:110-117`.
- Risk: sanitizer tests cover Markdown responses only, not the evidence/filename paths.
- Priority: Medium.

---

*Concerns audit: 2026-10-19*
