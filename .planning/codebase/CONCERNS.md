# Codebase Concerns

**Analysis Date:** 2026-10-21

Scope: full repository — root production modules, `ui/`, launcher/installer scripts, Docker/CI configuration, dependency manifests, and `tests/`. The codebase contains ~17,500 Python lines (7,488 in `tests/`) and 296 tests. No `TODO`, `FIXME`, `HACK`, or `XXX` markers were found in production code. Severity reflects user-visible impact under the project constraints: single-user laptop, 4 GB VRAM, Windows-first, and zero egress in local mode.

## Tech Debt

**UI render monolith (`ui/views.py`):**
- Issue: A single 852-line module owns the sidebar uploader, chat rendering, streamed inference, citation drawer, summarizer, document library, danger zone, and settings/diagnostics. Layout, session-state mutation, provider lifecycle, ingestion orchestration, and error presentation are interleaved.
- Files: `ui/views.py` (852 lines), `main.py` (363 lines)
- Impact: UI behavior cannot be exercised without importing Streamlit. No test imports `ui.views` or calls its `render_*` functions, so the streaming, sanitization, summary-cache, and upload-loop paths have no direct regression net. The view layer also mutates `st.session_state` keys that are initialized manually in `main.py`.
- Fix approach: Extract per-workspace controllers with explicit inputs (store, retriever, provider, session adapter), keep `ui/views.py` as thin composition, and move upload and summary generation into service calls that can be tested without Streamlit.

**Import-time side effects in `main.py`:**
- Issue: Importing `main.py` mutates `os.environ`, imports Streamlit, constructs a module-level `DocStore`, runs schema migrations, hydrates session state, constructs `AiModel`, probes provider health, and updates cloud state.
- Files: `main.py:14-18`, `main.py:142`, `main.py:145`, `main.py:148-190`
- Impact: The composition root is not safely importable for integration tests. A locked SQLite file, invalid `LLAMA_SERVER_URL`, or missing dependency becomes a full-page Streamlit traceback instead of a recoverable UI state.
- Fix approach: Introduce `bootstrap() -> AppContext` invoked once from a Streamlit entry guard, return typed startup errors, and keep module import side-effect free.

**Packaging and runtime installer conflated in `setup.py`:**
- Issue: `setup.py` is an 820-line setuptools script that also performs network downloads, archive extraction, binary installation, pre-caching, and CLI parsing.
- Files: `setup.py:57-77`, `setup.py:103-193`, `setup.py:308-346`, `setup.py:385`, `setup.py:700-730`
- Impact: Installing the package imports download/install machinery; security-sensitive network and archive logic lives in packaging code and is only exercised through mocked tests.
- Fix approach: Move model/binary installation into a dedicated `installer/` module with checksum verification and staged extraction; keep `setup.py` limited to metadata and entry points.

**Broad exception handling and silent degradation:**
- Issue: 86 `except Exception` handlers exist in production code, 20 in `ui/` alone. Several discard the error entirely (`except Exception: pass`), including database status rollback, FTS/index maintenance, and cache deletion.
- Files: `ui/ingestion_service.py:294-300`, `ui/lifecycle_service.py:49-53`, `ui/lifecycle_service.py:102-107`, `hybrid_retriever.py:216`, `hybrid_retriever.py:227`, `hybrid_retriever.py:364`, `hybrid_retriever.py:452`, `hybrid_retriever.py:668`, `local_llm.py:55-64`
- Impact: Failures are logged at debug/warning or not at all. The UI can report success while vectors, cache, or document status are inconsistent. A deleted document can remain retrievable because LanceDB deletion errors are swallowed (see Known Bugs).
- Fix approach: Catch specific exceptions, return typed failure results, and make destructive operations fail closed. Reserve best-effort cleanup for `finally` blocks with `logger.exception` and surface aggregate warnings to the caller.

**Deprecated compatibility facades:**
- Issue: `HybridRetriever.search()` and `get_context()` are deprecated wrappers around `search_hybrid()`, and `LocalEmbedding.search_hybrid()` remains as a second retrieval entry point.
- Files: `hybrid_retriever.py:695-712`, `local_embedding.py:121-146`
- Impact: Two retrieval APIs with different result shapes increase the chance that new code bypasses canonical `RetrievalResult` construction, citation numbering, or document filtering.
- Fix approach: Remove the facades, update callers to `search_hybrid(query, k, doc_ids)`, and add a single canonical retrieval contract test.

**Manual `CONFIG_VERSION` controls cache and summary invalidation:**
- Issue: `CONFIG_VERSION` is a manually maintained string controlling cache paths and summary cache keys. Chunking, extraction, or prompt changes silently reuse old artifacts unless the string is bumped.
- Files: `models.py:13-30`, `summarizer.py:330`, `summarizer.py:403`, `ui/views.py:552`
- Impact: A code change can display chunks or summaries produced by older extraction/chunking logic with no visible warning. Cache directories for old versions also accumulate on disk.
- Fix approach: Derive the version from a hash of chunking/extraction/prompt configuration, store it in SQLite and the vector table, and invalidate or migrate on mismatch.

**Embedding-model metadata is declared but unused:**
- Issue: `chunks.embedding_model` exists in SQLite (`doc_store.py:52`) and on the `Chunk` model (`models.py:72`), but no ingestion, OCR, Docling, or reindex path ever populates it. The LanceDB row schema has no embedding-model or embedding-dimension field at all.
- Files: `doc_store.py:300-345`, `hybrid_retriever.py:320-340`, `local_embedding.py:50-68`
- Impact: After swapping `all-MiniLM-L6-v2` or changing dimensions, old and new vectors can coexist with meaningless similarities and no way to detect which model produced a row.
- Fix approach: Populate `embedding_model`, add `embedding_dim`/`config_version` to the vector row schema, reject incompatible writes, and trigger a full reindex on model change.

## Known Bugs

**Live streamed assistant output bypasses sanitization (High):**
- Symptoms: During generation, `st.write_stream(response_stream)` renders model tokens directly as Markdown. Markdown image syntax such as `![x](https://attacker.example/pixel.png)` in model output causes the browser to request the URL in local mode. The same content is sanitized only on the next rerun, when chat history is re-rendered.
- Files: `ui/views.py:402` (stream), `ui/views.py:280-284` (history sanitization)
- Trigger: A PDF containing an injected instruction or a model inventing a Markdown image URL; any response containing remote Markdown images or links.
- Workaround: None in the UI. Users can avoid clicking generated links, but images load automatically.
- Fix approach: Buffer tokens and sanitize before each incremental render, or render plain text during streaming and only render Markdown after sanitization. Add a regression test asserting no remote URL reaches `st.write_stream`/`st.markdown` in local mode.

**User prompt rendered without sanitization (Medium):**
- Symptoms: The submitted prompt is rendered with `st.markdown(effective_prompt)`.
- Files: `ui/views.py:358`
- Trigger: A prompt containing Markdown image/link syntax, including pasted document text.
- Fix approach: Render the prompt as escaped text (`st.text` or `html.escape` with plain Markdown disabled) or pass it through `sanitize_display_markdown`.

**Stale summaries are presented as current (High):**
- Symptoms: Two independent staleness paths exist. The session cache key `summary_{doc_id}_{profile}` omits the model and `CONFIG_VERSION`, so switching local/cloud models shows the old summary until the session is cleared. Separately, the strict SQLite lookup with `model_version=expected_version` is followed by an unversioned fallback lookup, which returns a summary produced by a different provider, model, or config.
- Files: `ui/views.py:529`, `ui/views.py:550`, `ui/views.py:552-555`, `doc_store.py:487-534`, `doc_store.py:84`
- Trigger: Generate a summary, switch local/cloud model or bump `CONFIG_VERSION`, open the document again; or clear the session and reopen a document with an older cached summary.
- Impact: Users cannot tell whether a summary reflects the current model or configuration. The summary table's `UNIQUE(sha256, profile)` does not include `model_version`, so a new model also overwrites the previous row.
- Fix approach: Remove the unversioned fallback or display it with an explicit "stale — regenerate" badge; include model and config version in the session cache key; include `model_version` in the uniqueness key or keep historical versions.

**Gate-busy notice is persisted as an assistant answer (Medium):**
- Symptoms: When `InferenceGate.acquire(timeout=60.0)` fails, the stream generator yields a human warning string beginning with an emoji. The view treats it as model output, writes it to chat history, and runs citation validation on it, producing an "Unverified Citations (0%)" state.
- Files: `local_llm.py:298-301`, `ui/views.py:402-440`, `tests/test_concurrency_lock.py:169-177`
- Trigger: Summarize a large document (holding the gate for minutes) and send a chat message from any session.
- Impact: The warning is indistinguishable from an assistant response and pollutes the transcript; the test suite currently codifies this behavior.
- Fix approach: Return a typed busy status/exception instead of yielding text; have the view render a retryable info state without appending an assistant turn.

**Deleted documents can remain retrievable (High):**
- Symptoms: `LifecycleService.delete_document` removes the SQLite row but only logs LanceDB deletion failures and still returns `True`. Retrieval is unrestricted when the chat filter is "all" (`doc_id=None`), so stale vectors from the deleted document can still be returned and cited in a fresh or current session.
- Files: `ui/lifecycle_service.py:31-73`, `ui/lifecycle_service.py:49-53`, `hybrid_retriever.py:414-432`, `hybrid_retriever.py:615-625`
- Trigger: LanceDB file lock, table compaction error, process crash during deletion, or a delete while another session holds the table.
- Impact: Privacy-critical data that the user believes deleted can still appear in answers and citation chips.
- Fix approach: Delete vectors first (or use a SQLite tombstone and two-phase deletion), retry vector deletion on hydration, filter retrieval against SQLite-documented IDs even when `doc_id=None`, and report success only after both stores confirm.

**Re-ingestion leaves stale chunks and partial writes (High):**
- Symptoms: `record_chunks` and `record_pages_batch` only upsert by primary key. Re-processing a document whose extraction changes (Docling to pypdf fallback, OCR replacing page chunks, changed chunk boundaries) leaves old chunk IDs in SQLite and LanceDB. A failure after SQLite writes leaves chunks/pages/evidence behind while marking the document failed.
- Files: `ui/ingestion_service.py:237-309`, `ui/ingestion_service.py:283-309`, `doc_store.py:255-345`, `ocr_fallback.py:250-315`
- Trigger: Re-index a document after extraction behavior changes; simulate a LanceDB failure after SQLite commit; OCR a page whose prior chunks included headings/captions.
- Impact: Orphan chunks remain retrievable, inflate chunk counts, and can contradict newer extraction output.
- Fix approach: Delete all chunks/evidence/pages for `doc_id` in the same transaction before inserting, or diff against persisted chunk IDs. Wrap document status, chunks, pages, and evidence in one transaction and compensate vector writes on failure. Add a re-ingestion test that asserts no orphan chunks remain.

**Reindex reports failure after partial success (Medium):**
- Symptoms: `reindex_document` indexes text chunks first, then indexes evidence elements without embeddings. When `HybridRetriever.embedding_fn` is unset, the evidence call raises and the method returns `False`, although text chunks were already replaced. Reindex also never deletes chunks that no longer exist in SQLite.
- Files: `ui/lifecycle_service.py:134-166`, `hybrid_retriever.py:378-409`
- Trigger: Reindex a document with visual evidence while the retriever was constructed without `embedding_fn` (for example, a retriever hydrated without `set_embedding_fn`).
- Fix approach: Pass computed embeddings for evidence, delete existing vectors for the document first, and return a structured result separating text/evidence outcomes. Do not mutate the index until all inputs are validated.

**PNG crops are sent as JPEG (Medium):**
- Symptoms: `VisualAnalyzer.crop_visual_element` returns PNG bytes, but `LlamaCppProvider.analyze_image` labels every payload as `data:image/jpeg;base64`.
- Files: `visual_analyzer.py:148-198`, `llama_cpp_provider.py:286-295`
- Trigger: Any local visual analysis request.
- Impact: MIME sniffing may reject the image or decode it incorrectly depending on the llama-server build, reducing visual-description quality without an explicit error.
- Fix approach: Pass the actual MIME type from the crop function (or convert to JPEG explicitly) and add a provider test asserting the data URL prefix matches the bytes.

**Model weights and model name do not match (High for evaluation honesty):**
- Symptoms: `setup.py` downloads Qwen2-VL 2B weights and saves them as `qwen3-vl-2b-instruct-q4_k_m.gguf`. `README.md`, `docs/LOCAL_INFERENCE.md`, `start.py`, and `docker-compose.yml` refer to Qwen3-VL. The vision projector is likewise Qwen2-VL.
- Files: `setup.py:57-77`, `start.py:127-149`, `docker-compose.yml:38-39`, `README.md:17-18`, `README.md:153-157`, `docs/LOCAL_INFERENCE.md:1-18`
- Trigger: Fresh setup using documented commands.
- Impact: Users and evaluators believe they are running Qwen3-VL when the installed weights are Qwen2-VL. Capability, VRAM, and quality claims are not tied to the artifact actually executed.
- Fix approach: Choose one model generation, pin the exact Hugging Face revision and file hash, and use matching names in the registry, launcher, Compose file, and documentation.

**Invalid local provider URL can crash startup (Medium):**
- Symptoms: An invalid `LLAMA_SERVER_URL`/`LLAMA_SERVER_HOST` raises `ValueError` during `LlamaCppProvider.__init__`. `main.py` constructs `AiModel` at import time without catching it, so the app fails instead of showing an "invalid endpoint" diagnostic.
- Files: `llama_cpp_provider.py:44-73`, `local_llm.py:168-185`, `main.py:148-158`
- Trigger: Set `LLAMA_SERVER_URL=https://example.com` or a malformed host without `allow_remote=True`.
- Fix approach: Catch configuration errors in `AiModel`/bootstrap, return an `error` health status with remediation text, and validate environment values once at startup.

**Cloud health reports "ready" without a network check (Medium):**
- Symptoms: `GroqProvider.check_health` and `LiteLLMProvider.check_health` return `healthy` when a key/client exists, without validating the key or connectivity. The UI shows "Cloud ready"; the first query then fails with an authentication or network error.
- Files: `groq_provider.py:59-83`, `litellm_provider.py:150-173`
- Trigger: Expired or malformed API key, provider outage, blocked egress.
- Fix approach: Distinguish `configured` from `reachable`, perform a cheap authenticated probe on consent/activation, and cache the result with a TTL.

**Offline startup probes the local provider twice (Medium):**
- Symptoms: `main.py` calls `ai_model.check_health()` on every rerun. When the active local provider is unhealthy, `AiModel.check_health` constructs a second `LlamaCppProvider` and probes it again, doubling the connection timeout before the page renders.
- Files: `main.py:190`, `local_llm.py:187-207`, `llama_cpp_provider.py:89-141`
- Trigger: Start Streamlit without llama-server; interact with any widget.
- Impact: Roughly 4 seconds of added latency per rerun when the server is down.
- Fix approach: Probe once per rerun, cache health for a few seconds, and reuse the existing client/timeout budget.

## Security Considerations

**Local-mode egress is enforced by regex, not a browser boundary (High):**
- Risk: The sanitizer is a set of regexes. It misses reference-style Markdown images/links (`![x][ref]` plus `[ref]: https://...`), angle-bracket destinations (`[x](<https://...>)`), autolinks, `mailto:`/`data:` destinations, HTML `srcset`, `<video>/<source>`, `<svg>`, `<base>`, `<meta http-equiv=refresh>`, and attribute spacing such as `href = "https://..."`. Raw HTML in chat is escaped by default, but Markdown features are still rendered.
- Files: `ui/sanitizer.py:9-30`, `ui/sanitizer.py:33-79`, `ui/views.py:284`, `ui/views.py:402`, `tests/test_sanitizer.py`
- Current mitigation: Regex replacement of external Markdown/HTML images and links when `allow_external=False`; tests cover one example per pattern.
- Recommendations: Replace regex filtering with an allowlist-based Markdown renderer, or add a Content-Security-Policy restricting `img-src`/`connect-src` to `self` when a reverse proxy is used. Add tests for reference links, autolinks, `srcset`, `svg`, and `data:` URLs. Sanitize streamed output (see Known Bugs).

**Cloud summarization transmits entire documents, beyond the consent wording (High):**
- Risk: The consent dialog says user prompts and "retrieved document excerpts" are transmitted. Summarization does not retrieve excerpts; it loads every page, bundles up to 2,000 tokens per map call, and sends full document text to the cloud provider. There is no per-document confirmation, byte-count display, or audit record.
- Files: `main.py:200-219` (consent text), `summarizer.py:233-289` (map-reduce over all pages), `summarizer.py:378-391` (full-text token count), `ui/views.py:535`
- Current mitigation: Session-level consent toggle; cloud mode is off by default.
- Recommendations: Treat full-document summarization as a distinct consent scope with an explicit per-action dialog showing page count and provider; log provider, model, document hash, page range, and timestamp; never send visual crops or raw pages.

**Consent enforcement is uneven and in-memory only (High):**
- Risk: `LiteLLMProvider` enforces a boolean `user_consented` on each text/image call, but `GroqProvider` has no consent parameter or check. `AiModel._detect_provider` constructs and returns `GroqProvider` whenever `cloud_mode=True` and no explicit cloud provider is supplied; `set_cloud_mode(True)` without a provider can therefore select a provider with no consent gate.
- Files: `litellm_provider.py:142-148`, `groq_provider.py:18-52`, `groq_provider.py:99-161`, `local_llm.py:168-185`, `local_llm.py:145-166`
- Current mitigation: The Streamlit UI constructs a consented `LiteLLMProvider`; the direct `GroqProvider` path is not used by the settings UI.
- Recommendations: Remove the `GroqProvider` fallback or give it the same consent gate; make consent an explicit object carrying scope, provider, model, and expiry; require it in every cloud provider constructor; add tests that unconsented construction/generation fails for both providers.

**SSRF/loopback allowlist is hostname-based and permissive (Medium):**
- Risk: `LlamaCppProvider` accepts `host.docker.internal` and `llama-server` as "local" without DNS resolution, accepts `allow_remote=True` as a public flag, and does not require HTTPS or reject embedded credentials. `LLAMA_SERVER_URL`, `LLAMA_SERVER_HOST`, and `LLAMA_SERVER_PORT` are environment-controlled and not validated at bootstrap.
- Files: `llama_cpp_provider.py:44-83`
- Current mitigation: Default URL is loopback; remote endpoints require an explicit constructor flag that the UI does not expose.
- Recommendations: Resolve hostnames and reject any non-loopback address at connect time, allow only the exact configured host/port, reject URL userinfo, and document that `host.docker.internal` is trusted only in the Compose network. Add a DNS-rebinding test.

**Downloaded binaries and model weights are trusted without integrity verification (High):**
- Risk: `setup.py` downloads GGUF files and llama-server archives over HTTPS with only a minimum-size check. Archive extraction uses `zipfile.extractall`/`tarfile.extractall` without path-traversal filtering. The installed binary is "verified" only by running `--version`. Hugging Face URLs use mutable `resolve/main` branches with no revision or SHA-256 pin.
- Files: `setup.py:103-193`, `setup.py:308-346`, `setup.py:385`, `setup.py:427`, `setup.py:482`
- Current mitigation: HTTPS and size thresholds; optional mirror list.
- Recommendations: Pin commit revisions and publish SHA-256 hashes in the registry, verify before extraction/execution, extract with explicit member path validation, and sign or checksum release archives. Add tests for traversal entries and hash mismatch.

**Upload validation permits resource-exhaustion inputs (Medium):**
- Risk: Validation checks only `%PDF-` magic bytes, a 50 MB size cap, and a 500-page cap. There is no decompression-bomb detection, parse time budget, object-count limit, or encryption check. The same bytes are parsed by Docling and then again by pypdf, and OCR can rasterize up to 500 pages, so a crafted or merely huge PDF can consume CPU/RAM for minutes. `doc_id_for` truncates SHA-256 to 64 bits.
- Files: `upload_validation.py:15-16`, `upload_validation.py:64-113`, `docling_reader.py:127-130`, `ocr_fallback.py:112-114`, `ocr_fallback.py:390-405`
- Current mitigation: Size/page caps and a 2048x2048 per-page raster guard.
- Recommendations: Validate page tree/object counts, enforce a wall-clock ingestion budget with cancellation, skip re-parsing when a successful extraction exists, and use the full digest (or a longer prefix) for stable IDs. Set explicit memory limits for Docling and OCR workers.

**Deletion is logical, not physical (Medium):**
- Risk: SQLite `VACUUM` runs after `purge_all`, but WAL files are not checkpointed/truncated, and deleted rows can remain in free pages or the WAL until checkpoint. LanceDB deletes are logical until compaction; prior table versions remain in `data/lancedb`. `data/lancedb_bench` is not purged.
- Files: `doc_store.py:619-631`, `hybrid_retriever.py:233-260`, `hybrid_retriever.py:414-432`, `ui/lifecycle_service.py:76-107`
- Current mitigation: UI confirmation and a physical `VACUUM`.
- Recommendations: Run `PRAGMA wal_checkpoint(TRUNCATE)` and `VACUUM` after purge, compact/optimize LanceDB and clean old versions, remove benchmark directories, and document that SSD wear-leveling/OS caches may retain bytes.

**Credentials and session isolation (Medium):**
- Risk: API keys are held in plaintext in `st.session_state.cloud_api_keys`. There is no authentication or per-user authorization; every new Streamlit session can read the shared SQLite database and hydrated document list. Provider errors are scrubbed in `LiteLLMProvider` but not in `GroqProvider`.
- Files: `main.py:60-91`, `main.py:161-188`, `litellm_provider.py:44-88`, `litellm_provider.py:135-140`, `groq_provider.py:99-161`, `ui/views.py:782-792`
- Current mitigation: Single-user local deployment; keys are cleared when the session resets; `.env` and `data/` are gitignored and dockerignored.
- Recommendations: Document the single-user trust boundary, avoid persisting keys, scrub all provider exceptions, and add a reverse-proxy/auth layer before exposing Streamlit beyond loopback. Consider encrypting the SQLite store at rest.

**Runtime does not enforce offline model use (High):**
- Risk: `LocalEmbedding` constructs `SentenceTransformer("all-MiniLM-L6-v2")` with default settings. If the model is not in the Hugging Face cache, the first ingestion or hydration downloads it. There is no `local_files_only=True`, offline flag, runtime preflight check, or UI warning. Setup has a `precache_embedding_model()` step, but it is optional and not re-verified at runtime.
- Files: `local_embedding.py:24-68`, `setup.py:196-219`, `ui/hydration.py:46-55`, `ui/ingestion_service.py:267-270`
- Current mitigation: Documented CPU-only usage and a setup pre-cache command.
- Recommendations: Bundle or pre-download the embedding model during setup, set `HF_HUB_OFFLINE=1`/`local_files_only=True` at runtime, fail with actionable remediation if missing, and guard model loading with a process-wide lock (see Fragile Areas).

**Prompt injection and adversarial content remain heuristic (Medium):**
- Risk: Document text is wrapped in XML tags and the system prompt instructs the model to treat it as data, but `sanitize_xml_boundary` only escapes `<document_context>` tags. Visual descriptions and OCR text can contain instructions. Defense relies on the model plus substring checks for known phrases.
- Files: `prompt_budget.py:30-42`, `summarizer.py:193-203`, `summarizer.py:286-289`, `citation_validator.py:69-100`, `visual_analyzer.py:260-290`
- Current mitigation: System-prompt isolation, citation validation, and a known-directive denylist.
- Recommendations: Escape all structural delimiters, add an instruction-hierarchy test corpus, and treat injection detection as best-effort telemetry rather than a security guarantee. Do not execute or render model-provided links in local mode.

## Performance Bottlenecks

**Every rerun constructs `DocStore` and probes health:**
- Problem: Streamlit reruns `main.py` top-to-bottom. Each rerun opens SQLite, reads `PRAGMA user_version`, constructs `AiModel`/provider, and performs a health HTTP request. Failed probes repeat the request through a second provider.
- Files: `main.py:142`, `main.py:148-190`, `local_llm.py:187-207`
- Cause: Module-level initialization and uncached health checks.
- Improvement path: Cache `DocStore`, health, and capabilities with `@st.cache_resource`/TTL, and avoid constructing a provider just to check health. Target sub-100 ms reruns when the server is offline.

**Synchronous ingestion blocks the only UI thread:**
- Problem: Docling parsing, pypdf fallback, OCR over up to 500 pages, VLM analysis of six regions, embedding generation, and LanceDB writes all run inside the upload rerun. There is no job queue, progress cancellation, or time budget.
- Files: `ui/ingestion_service.py:56-329`, `ui/views.py:76-180`, `ocr_fallback.py:390-405`
- Cause: The ingestion service is called directly from the sidebar render path.
- Improvement path: Move ingestion to a background worker/queue, persist job state, and let the UI poll. Add a hard per-document timeout and cancellation that cleans up partial rows/vectors.

**OCR thread pool can exhaust RAM on large scans:**
- Problem: Up to four worker threads each decode the full PDF and rasterize pages at up to 2048x2048 while holding `pdf_bytes`; OCR models also allocate working memory per thread. A single `OcrEngine` instance is shared across all workers.
- Files: `ocr_fallback.py:53-160`, `ocr_fallback.py:318-417`
- Cause: Memory guards are per page, not per concurrent worker, and the same `pdf_bytes` is retained for every task. RapidOCR thread-safety is assumed, not enforced.
- Improvement path: Limit concurrency by available RAM (one or two workers on 8 GB systems), process pages in a streaming loop, release rasters immediately, and use a per-worker engine or a lock. Add a peak-RSS test with a synthetic large scan.

**BM25 fallback scans and tokenizes up to 10,000 rows per query:**
- Problem: When the in-memory fallback store is empty but LanceDB exists, `_bm25_search_fallback` loads up to 10,000 full chunk rows and tokenizes them in Python for every query.
- Files: `hybrid_retriever.py:489-549`
- Cause: No persistent inverted index when LanceDB FTS is unavailable, plus a hard row limit.
- Improvement path: Rely on LanceDB FTS as the primary lexical path, cache a bounded BM25 index per document set, and fail with a clear degraded-mode status instead of scanning 10k rows synchronously.

**FTS index is rebuilt on every ingestion:**
- Problem: Each `index_chunks` call invokes `create_fts_index(..., replace=True)`, rebuilding the full-text index even for one new document.
- Files: `hybrid_retriever.py:342-370`, `hybrid_retriever.py:479-487`, `hybrid_retriever.py:256-377`
- Cause: No incremental FTS update/optimize policy.
- Improvement path: Create FTS once per table version, use `optimize()` after batches, and batch ingestion writes before rebuilding.

**Summarization holds the global gate for minutes:**
- Problem: `summarize_document` takes `InferenceGate` once and performs many sequential map/reduce calls under it. Chat and visual analysis wait up to 60 seconds and then fail with a busy message; all sessions are affected.
- Files: `summarizer.py:233-289`, `summarizer.py:378-391`, `local_llm.py:26-90`
- Cause: A single coarse lock around a multi-call workflow.
- Improvement path: Reserve the gate per provider call with a fairness queue, expose progress/cancel, and let short chat requests preempt or interleave between summarization calls. If strict serialization is required, document the latency and provide a queued status instead of an error.

**Per-session retrievers duplicate LanceDB clients and caches:**
- Problem: Every session creates its own `HybridRetriever`, embedding function, and table handle; FTS rebuilds and merge-inserts are not coordinated.
- Files: `ui/hydration.py:46-75`, `hybrid_retriever.py:90-160`, `ui/views.py:205-220`
- Cause: Session-scoped state instead of a process-wide storage service.
- Improvement path: Share one retriever per database URI, protect writes with a lock, and keep per-session only view state.

**Visual region detection scans every page before analysis:**
- Problem: `detect_visual_regions` iterates all pages, calls `get_images()` and `get_drawings()`, and merges vector drawing rectangles before the 6-region VLM cap is applied. Long documents pay this cost even when no visual elements are analyzed.
- Files: `visual_analyzer.py:58-143`, `visual_analyzer.py:200-240`
- Cause: Detection and analysis budgets are decoupled.
- Improvement path: Add a page-count budget, early-exit when enough regions are found, and cache detection results per document hash.

**Pure-Python fallback vector search is linear:**
- Problem: `VectorIndex.search` computes distance against every stored vector in Python; with thousands of fallback chunks this becomes O(N) per query and blocks the UI thread.
- Files: `vector_index.py:92-136`, `hybrid_retriever.py:433-477`
- Cause: The fallback store is an in-memory list, not an ANN index.
- Improvement path: Treat LanceDB as required for production, cap fallback size, and surface a degraded-mode indicator instead of silently scanning.

## Fragile Areas

**SQLite migrations (`doc_store.py`):**
- Files: `doc_store.py:17-110`, `doc_store.py:151-164`
- Why fragile: Each version's DDL is executed statement-by-statement and committed after the version bump, without an explicit enclosing transaction or pre-migration backup. Python's `sqlite3` does not open a transaction for DDL by default, so DDL may autocommit individually; a crash can leave a partially migrated schema with the old `user_version`. There is no downgrade path or cross-process migration lock. Tests only verify a fresh database reaches version 4.
- Safe modification: Add new migrations as new version entries with `IF NOT EXISTS`; never edit an existing entry. Take a file backup before migrating, wrap DDL and the version bump in one transaction where SQLite permits, and acquire an exclusive lock.
- Test coverage: `tests/test_doc_store.py:127` asserts `user_version == 4` on a fresh DB only; no v1→v4 upgrade, partial-migration, or concurrent-open test.

**Schema lacks referential integrity for chunks and pages:**
- Files: `doc_store.py:30-55`
- Why fragile: `chunks` and `pages` have no foreign key to `documents`; evidence and summaries do. Deleting a document relies on explicit deletes, and a failed or partial write can leave orphan chunks/pages that are still returned by joins or retrieval.
- Safe modification: Add foreign keys with `ON DELETE CASCADE` in a v5 migration, backfill/clean orphans first, and keep `PRAGMA foreign_keys=ON` on every connection (already at `doc_store.py:145`).
- Test coverage: No orphan-cleanup test.

**Vector schema and embedding-model/version metadata are absent:**
- Files: `hybrid_retriever.py:300-340`, `local_embedding.py:27-68`, `models.py:13-30`
- Why fragile: The LanceDB table assumes 384-dimensional vectors and does not record which embedding model, chunker, or prompt produced each row. Swapping `all-MiniLM-L6-v2` or changing dimensions produces incompatible rows that may fail merges or silently return meaningless similarities. `CONFIG_VERSION` changes cache paths but not the vector table.
- Safe modification: Add `embedding_model`, `embedding_dim`, and `config_version` columns, reject incompatible writes, and trigger a full reindex on model change. Version the table name or store a metadata table.
- Test coverage: No model-swap or dimension-mismatch test.

**Session-state invariants are implicit:**
- Files: `main.py:60-140`, `ui/views.py:60-180`, `ui/hydration.py:18-27`, `ui/lifecycle_service.py:60-130`
- Why fragile: The UI depends on `uploader_key`, `doc_ids`, `failed_doc_ids`, `indexed_files`, `document_metadata`, `selected_chat_doc`, `selected_summary_doc`, `_startup_hydrated`, `summary_*`, and `active_cloud_provider` being present and mutually consistent. `_startup_hydrated` is set to `True` before the SQLite query, so a transient failure disables retry for that session. Manual resets update some keys but not all.
- Safe modification: Introduce a typed session-state schema with an initializer and a reset method, and set `_startup_hydrated` only after successful hydration.
- Test coverage: `tests/test_ui_smoke.py` initializes keys manually in a fixture; it does not test partial or failed hydration.

**Provider hot-swap and health semantics:**
- Files: `local_llm.py:145-207`, `main.py:161-187`, `litellm_provider.py:150-173`
- Why fragile: `set_cloud_mode` closes the active provider before selecting a replacement; a cached `cloud_provider` can point at a closed client if the mode is toggled outside the UI's reset path. Health checks are configuration-only for cloud providers. Capabilities can become stale after a model or key change.
- Safe modification: Make provider selection return a new object without closing until the swap succeeds, validate cached providers on reuse, and recompute capabilities whenever health/model changes.
- Test coverage: `tests/test_concurrency_lock.py` covers gate behavior; `tests/test_cloud_privacy.py:132` covers a switching matrix, but not closed-client reuse or stale capabilities.

**Inference serialization is in-process only:**
- Files: `local_llm.py:26-90`
- Why fragile: `InferenceGate` is a class-level `threading.RLock`. Running Streamlit with multiple processes/workers, or launching a second app instance, bypasses the VRAM guarantee entirely. A generator that is abandoned without `finally` (or a consumer that stops iterating after an exception) can leave the active counter nonzero until garbage collection closes the generator. The gate also treats a 60-second wait failure as a text response rather than a typed error.
- Safe modification: Use an OS-level lock/file or a single-worker deployment model, enforce `try/finally` around every generator, and make the counter recovery path reset only on process start. Document that Streamlit workers must remain 1.
- Test coverage: Thread-level tests only (`tests/test_concurrency_lock.py`); no multi-process or abandoned-generator test.

**llama-server lifecycle and Docker context mismatch:**
- Files: `start.py:119-170`, `start.py:235-263`, `docker-compose.yml:30-63`, `Dockerfile:25-27`
- Why fragile: `start.py` spawns llama-server with `stdout/stderr=DEVNULL`, no PID file, and terminates it only when `launch_streamlit` returns; a crash or forced kill can orphan the server holding VRAM. The launcher expects a model named `qwen3-...` while setup downloads Qwen2 weights. Docker Compose hardcodes `-c 4096`, while the provider default is 4096 and docs discuss 8192, so context assumptions drift.
- Safe modification: Write a PID/metadata file, register an `atexit`/signal cleanup, capture logs to a rotating file, and derive model/context flags from one shared configuration.
- Test coverage: `tests/test_start_launcher.py` mocks subprocess and covers the happy path; no real orphan/kill or Docker test.

**Windows is the primary target but CI is Ubuntu-only:**
- Files: `.github/workflows/ci.yml:8-45`, `ui/lifecycle_service.py:60-107`
- Why fragile: CI runs Python 3.11 on Ubuntu; production guidance targets Windows 11. Windows file locking makes `shutil.rmtree(..., ignore_errors=True)` fail silently, OCR/thread and path behavior differ, and `nvidia-smi` resolution is platform-specific.
- Safe modification: Add a Windows CI matrix (at least lint plus unit tests using temp dirs), replace `ignore_errors=True` with retry/backoff and explicit errors, and test cache deletion on Windows.
- Test coverage: None on Windows.

**Citation verification measures tag validity, not claim support:**
- Files: `citation_validator.py:102-220`
- Why fragile: `precision` is the fraction of `[E#]` tags that fall within the retrieved snippet range. A response can cite `[E1]` after an unsupported claim and still score 100%. `is_abstention` is a substring check, so a mixed answer containing a marker phrase and citations is classified as an invalid abstention. `detect_adversarial_injection` can flag benign text such as "system prompt:" in a legitimate discussion.
- Safe modification: Rename the UI metric to "citation tag validity", add claim-to-snippet entailment checks for high-stakes answers, make abstention detection require the whole response to abstain, and scope injection detection to instruction-like sentences.
- Test coverage: `tests/test_citation_validator.py` covers tag ranges and markers, not semantic support or mixed answers.

**Docling accelerator is left on auto:**
- Files: `docling_reader.py:120-135`
- Why fragile: The pipeline sets table structure but no explicit CPU device. On a CUDA host, Docling's accelerator auto-selection can allocate GPU memory for layout/table models outside `InferenceGate`, competing with llama-server under the 4 GB ceiling.
- Safe modification: Set an explicit CPU `AcceleratorOptions`/device in `PdfPipelineOptions` and assert in a test that the configured device is CPU. Document that all preprocessing is CPU-only.
- Test coverage: No VRAM/device-allocation test.

**Shared embedding-model cache is unsynchronized:**
- Files: `local_embedding.py:24-46`
- Why fragile: `_MODEL_CACHE` is a plain dict guarded by no lock. Two Streamlit sessions or hydration threads can both see a cache miss and construct duplicate `SentenceTransformer` instances, doubling RAM and initialization time. `clear_shared_model_cache()` does not coordinate with in-flight loads.
- Safe modification: Guard cache access with a process-wide `threading.Lock` and double-check after acquisition. Add a concurrency test with a mocked slow constructor.
- Test coverage: No concurrent model-load test.

**OCR engine sharing across threads:**
- Files: `ocr_fallback.py:53-160`, `ocr_fallback.py:389-405`
- Why fragile: A single `OcrEngine`/RapidOCR instance is passed to up to four worker threads. ONNX Runtime sessions may be thread-safe for inference, but lazy initialization inside `ocr_page_image` is not synchronized, and model state is shared.
- Safe modification: Initialize the recognizer before dispatch or guard initialization with a lock; document the thread-safety assumption and add a stress test with a mocked recognizer.
- Test coverage: `tests/test_ocr_fallback.py:338` exercises multithreaded batch processing with mocks, not the real ONNX runtime.

## Scaling Limits

**Single-user, unauthenticated session model:**
- Current capacity: One Streamlit process, one shared SQLite file, one LanceDB directory, no auth.
- Limit: Any client that reaches the port can read every hydrated document and create sessions; concurrent sessions contend for SQLite writes and LanceDB FTS.
- Scaling path: Add authentication and per-user document namespaces, or explicitly deploy behind loopback-only and document that this is not multi-tenant. Replace per-session retrievers with a shared storage service.

**Document size and page count:**
- Current capacity: 50 MB and 500 pages per PDF; OCR workers capped at four; raster guard 2048x2048 per visual crop.
- Limit: A 500-page scan can require hundreds of OCR pages, multiple full parses, and six VLM calls; peak RAM depends on PDF complexity and can exceed an 8 GB laptop. No time or memory budget exists beyond per-page raster limits.
- Scaling path: Add streaming page extraction, cap OCR pages by text coverage, process in a subprocess with an RSS limit, and expose a hard ingestion timeout.

**Context and VRAM:**
- Current capacity: 4,096-token provider context, 2,500-token fast summary path, 2,000-token map batches, one serialized inference call.
- Limit: Long documents require many sequential map calls; a 200-page report can hold the gate for minutes and block chat. Image analysis adds vision-encoder and image-token memory on top of the text model.
- Scaling path: Precompute summaries in the background, cache map outputs per page hash, expose progress, and consider a smaller image resolution/region budget. Do not raise `-ngl` or context without measuring peak VRAM.

**SQLite write contention:**
- Current capacity: Per-operation connections with a 5-second busy timeout; WAL mode; indexes added in v4.
- Limit: Concurrent uploads/reindex/delete from multiple sessions can hit `database is locked`; long `VACUUM` after purge blocks writers.
- Scaling path: Serialize writes through a single worker, use a longer/queued retry policy, and avoid `VACUUM` on the UI thread.

**LanceDB multi-session writers:**
- Current capacity: One table, FTS rebuilt on writes, per-session clients.
- Limit: Two sessions can call `create_fts_index(..., replace=True)` and merge-insert simultaneously; errors are often swallowed and the fallback store is read-modify-write per process.
- Scaling path: Serialize mutations through a process-wide lock/queue, share one retriever per URI, and make writes idempotent with explicit failure reporting.

## Dependencies at Risk

**Unpinned runtime requirements vs. a lockfile that Docker ignores:**
- Risk: `requirements.txt` uses open ranges for `docling`, `lancedb`, `pymupdf`, `pillow`, `pyarrow`, `litellm`, and `rapidocr`. The Dockerfile copies `requirements-lock.txt` but installs `requirements.txt`.
- Files: `requirements.txt:10-18`, `Dockerfile:25-27`, `.github/workflows/ci.yml:22-27`
- Impact: Docker builds are not reproducible and can receive breaking major versions; the host and container may run different Docling/LanceDB/LiteLLM behavior.
- Migration plan: Install `requirements-lock.txt` in Docker, add hashes (`--require-hashes`), pin all direct dependencies, and test the lock on Windows and Python 3.13 as well as 3.11.

**No artifact hashes in the lockfile:**
- Risk: `requirements-lock.txt` has no `--hash` entries (0 matches) and contains environment-specific markers, so resolution differs by platform/Python.
- Files: `requirements-lock.txt` (645 lines), `requirements-test.txt`
- Impact: A compromised or mutated package index can supply different bytes; Linux and Windows can resolve different wheels (notably `rapidocr` vs `rapidocr-onnxruntime`, Torch CUDA variants).
- Migration plan: Generate a hash-pinned universal lock per supported Python version/platform, verify with `pip install --require-hashes`, and add a CI job that installs from the lock on Windows.

**Fast-moving parsing and vector libraries:**
- Risk: Docling (`>=2.0.0`), LanceDB (`>=0.17.0`), LiteLLM (`>=1.50.0`), and PyMuPDF (`>=1.24.0`) have frequent API changes. The code depends on specific behaviors: `PdfPipelineOptions`, `merge_insert`, `create_fts_index`, `to_list`, and LiteLLM model routing.
- Files: `docling_reader.py:25-35`, `hybrid_retriever.py:342-370`, `litellm_provider.py:90-160`
- Impact: A fresh install can break extraction, vector upserts, or FTS with an exception that is logged and degraded rather than surfaced.
- Migration plan: Pin exact tested versions in the runtime lock, add contract tests for each external API, and gate upgrades behind a compatibility test job.

**Hugging Face assets are mutable and fetched at runtime:**
- Risk: Model and projector URLs use `resolve/main` with no revision; the embedding model is fetched on first use if setup was skipped.
- Files: `setup.py:57-77`, `local_embedding.py:37-42`
- Impact: Upstream file replacement changes behavior silently; a first run without network fails ingestion or violates the zero-egress claim.
- Migration plan: Pin revisions and SHA-256 in the registry, pre-download both GGUF and SentenceTransformer assets during setup, and set offline flags at runtime.

**Floating container image:**
- Risk: `docker-compose.yml` uses `ghcr.io/ggml-org/llama.cpp:server-cuda` without a digest.
- Files: `docker-compose.yml:30-33`
- Impact: Rebuilding can pull a different llama.cpp/server image with different flags or CUDA requirements; the 4 GB tuning may no longer hold.
- Migration plan: Pin the image by digest and document the tested CUDA/llama.cpp version.

**Torch/NumPy/Transformers compatibility:**
- Risk: The lock resolves `torch==2.14.1`, `torchvision==0.29.1`, `numpy==2.4.6`, and `transformers==4.57.6`. Sentence-Transformers and Docling both import Torch/Transformers; a platform-specific wheel mismatch can fail at import or produce different numerics.
- Files: `requirements-lock.txt:240`, `requirements-lock.txt:541`, `requirements-lock.txt:549`, `requirements-lock.txt:567`, `requirements.txt:8`
- Impact: CPU vs CUDA installs differ, and Docling may unexpectedly use GPU (see Fragile Areas). Python 3.13 has a separate RapidOCR path that CI does not exercise.
- Migration plan: Pin CPU-only Torch for preprocessing unless CUDA is explicitly enabled, test import on Windows and Linux, and add a Python 3.13 job.

## Missing Critical Features

**Runtime egress enforcement:**
- Problem: Local-mode privacy depends on the sanitizer, provider defaults, and the absence of explicit network calls. There is no firewall, proxy allowlist, CSP, or startup assertion that outbound sockets are blocked; SentenceTransformer and LiteLLM can make network calls outside the app's control.
- Blocks: A defensible "zero egress" guarantee and security review sign-off.

**Authentication and per-user isolation:**
- Problem: The app assumes a single trusted user. Any session that reaches port 8501 can hydrate the shared database and read all documents.
- Blocks: Shared-machine, team, or remote deployment; safe use on a laptop with other local users.

**Cloud visual-understanding parity:**
- Problem: Visual analysis runs only when the active provider reports `is_local` and `supports_vision`. In cloud mode, regions are detected but no descriptions are generated, and no cloud vision request is made. The consent text mentions transmitting visual summaries, but none are produced.
- Files: `ui/ingestion_service.py:187-205`, `visual_analyzer.py:240-258`, `litellm_provider.py:298-355`
- Blocks: The stated multimodal/cloud fallback value proposition; users may summarize a diagram-heavy PDF in cloud mode and receive no visual evidence with no warning.

**Vector schema/version migration and automatic reindex:**
- Problem: There is no recorded embedding model/dimension or config version in the vector table, and no automatic reindex when they change. `reindex_document` is manual and does not prune removed chunks.
- Blocks: Safe model upgrades and reliable retrieval after configuration changes.

**Background ingestion with cancellation and budgets:**
- Problem: Ingestion is synchronous, has no job identity, no cancel button, and no wall-clock/memory budget.
- Blocks: Usable large-document workflows, responsive UI, and cleanup after abandoned uploads.

**Artifact integrity and offline bootstrap:**
- Problem: No checksums/signatures for GGUF, projector, llama-server archives, or embedding weights; no single offline installer that prepares all assets and verifies them.
- Blocks: Reproducible installs and supply-chain review.

**Cloud data-flow audit log:**
- Problem: No record of which document pages, prompts, provider, model, or byte counts were sent, or when consent was granted/revoked.
- Blocks: User auditability and incident response for a privacy-first product.

**Cross-platform and end-to-end validation:**
- Problem: No Windows CI, no browser-level test of egress, no real Docling/RapidOCR run in CI, and no real-model visual/citation quality harness.
- Blocks: Confidence in the primary Windows target and in the 95% citation/visual-quality claims.

**Stale-summary regeneration UX:**
- Problem: When a summary's model version does not match, the UI silently shows the old summary instead of offering regeneration; the session cache key does not even detect the mismatch.
- Blocks: Users cannot tell whether a summary reflects the current model or configuration.

## Test Coverage Gaps

**UI render layer is untested:**
- What's not tested: `render_chat_view`, `render_sidebar_documents`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, and the streamed-response path.
- Files: `ui/views.py` (852 lines), `main.py`; no test imports `ui.views` or `main` (verified by searching `tests/`).
- Risk: The sanitizer bypass, stale-summary fallback, gate-busy persistence, upload-loop behavior, and settings consent transitions can regress without a failing test. `tests/test_main_ui.py` tests data contracts and services, not rendered UI.
- Priority: High.

**Streaming sanitization and browser egress:**
- What's not tested: Sanitization of tokens before `st.write_stream`, reference-style Markdown, autolinks, `srcset`, `data:` URLs, and the interaction between cloud consent and historical re-rendering.
- Files: `tests/test_sanitizer.py`, `tests/test_ui_smoke.py`; only single-pattern examples are covered.
- Risk: A local-mode document can cause a browser request to an external host.
- Priority: High.

**Schema upgrade and partial-write behavior:**
- What's not tested: v1→v4 migrations on an existing database, crash mid-migration, concurrent opens, orphan chunks/pages, re-ingestion with a changed chunk set, and rollback after vector failure.
- Files: `tests/test_doc_store.py:127`, `ui/ingestion_service.py:237-309`
- Risk: A user upgrading an existing install can end up with missing indexes or stale retrievable chunks.
- Priority: High.

**Cloud data-flow scope:**
- What's not tested: Full-document summarization egress, per-document consent, cloud health false positives, `GroqProvider` consent enforcement, and credential scrubbing on Groq errors.
- Files: `tests/test_cloud_privacy.py`, `tests/test_litellm_provider.py`, `tests/test_groq_provider.py`
- Risk: Data can leave the device beyond the consent wording, or a provider can be used without an explicit gate.
- Priority: High.

**Concurrency and multi-session behavior:**
- What's not tested: Multiple processes bypassing `InferenceGate`, concurrent LanceDB FTS rebuilds, concurrent SQLite writes/deletes, abandoned generators, and retriever sharing.
- Files: `tests/test_concurrency_lock.py` (thread-only), `tests/test_hybrid_retriever.py` (single-process)
- Risk: VRAM exhaustion or corrupted/partial indexes in realistic multi-tab use.
- Priority: Medium-High.

**Real extraction/OCR/vision paths:**
- What's not tested: CI runs Docling/RapidOCR only if their dependencies and synthetic corpus are present; the main suite mocks inference, embeddings, and OCR. There is no real VLM quality evaluation or full-document visual test.
- Files: `tests/conftest.py`, `tests/data/corpus/generate_corpus.py`, `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `scripts/benchmark_multimodal.py`
- Risk: Parser/OCR/VLM regressions and VRAM behavior appear only in manual use; the claimed visual understanding is not measured in CI.
- Priority: High for release confidence, Medium for unit CI.

**Launcher/installer failure paths:**
- What's not tested: Real llama-server spawn/orphan cleanup, invalid `LLAMA_SERVER_URL`, archive path traversal, checksum mismatch, partial downloads, and Windows binary resolution.
- Files: `tests/test_start_launcher.py`, `tests/test_setup_llama.py`; subprocesses and downloads are mocked.
- Risk: A failed install or orphaned server leaves the user with a broken or VRAM-occupied environment.
- Priority: Medium.

**Dependency and static-analysis gates:**
- What's not tested: Coverage thresholds, type checking, dependency vulnerability scanning, and warning-free execution. `pyproject.toml` selects only `E,F,W` Ruff rules, ignores `E501`, and `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]` suppresses warnings globally. No `pytest-cov`, mypy, or pyright configuration exists.
- Files: `pyproject.toml:84-112`, `requirements-test.txt`
- Risk: Dead code, type drift, and deprecated APIs accumulate silently; the suite can pass while large modules have no execution coverage.
- Priority: Medium.

**Citation and abstention edge cases:**
- What's not tested: Mixed answers containing abstention phrases and valid citations, claim-level support, benign "system prompt:" text, and citation tags inside code blocks.
- Files: `tests/test_citation_validator.py`, `citation_validator.py:102-220`
- Risk: The UI can label an ungrounded answer as verified or reject a legitimate answer.
- Priority: Medium.

**Test coverage cross-reference:**

| Area | Production files | Closest tests | Gap |
|------|------------------|---------------|-----|
| Chat/summary/library/settings rendering | `ui/views.py:180-852` | `tests/test_ui_smoke.py`, `tests/test_main_ui.py` (contracts only) | No render-path execution |
| App bootstrap | `main.py` | `tests/test_ui_smoke.py:109` (imports one function) | No startup/error-path test |
| Ingestion transactions | `ui/ingestion_service.py` | `tests/test_main_ui.py:337` (empty chunks), `:528` (upload loop) | No rollback/stale-chunk test |
| Lifecycle delete/purge/reindex | `ui/lifecycle_service.py` | `tests/test_main_ui.py:368,451` | No failure injection, no reindex test |
| Migrations | `doc_store.py:151-164` | `tests/test_doc_store.py:127` | Fresh DB only |
| Cloud egress scope | `summarizer.py`, providers | `tests/test_cloud_privacy.py` | No full-document summarization test |
| Launcher/installer | `start.py`, `setup.py` | `tests/test_start_launcher.py`, `tests/test_setup_llama.py` | Mocked happy paths only |
| Real OCR/vision | `ocr_fallback.py`, `visual_analyzer.py`, `docling_reader.py` | unit tests with mocks/corpus | No real-model quality/VRAM run |
| Sanitizer patterns | `ui/sanitizer.py` | `tests/test_sanitizer.py` | No reference/autolink/srcset/data: cases |
| Static analysis | `pyproject.toml`, CI | none | No coverage, type, or vulnerability scan |

---

*Concerns audit: 2026-10-21*
