# Codebase Concerns

**Analysis Date:** 2026-10-21

## Highest-Risk Items

1. **Silent vector-persistence failure** — `HybridRetriever.index_chunks` swallows every LanceDB exception and still returns the indexed count, so ingestion reports success while retrieval has no evidence (`retrieval/hybrid_retriever.py:375-419`).
2. **Split LanceDB roots** — production code writes to `retrieval/data/lancedb` while documentation, Docker volumes, and the existing on-disk index all point at `data/lancedb` (`retrieval/hybrid_retriever.py:58`, `ui/views.py:860`, `docker-compose.yml:11`). Existing vectors are orphaned and `data/lancedb` is never purged.
3. **Unbounded summarizer reduce prompt** — map-reduce consolidation bypasses `core/prompt_budget.py`, so long documents can send multi-thousand-token prompts into a 4,096-token local context (`core/summarizer.py:269-299`).
4. **Sanitizer is regex-based and bypassable** — reference-style links/images, `data:`/`javascript:` URLs, `srcset`, inline `style="url(...)"`, and `<svg><use href>` survive neutralization (`ui/sanitizer.py:10-30`, `53-76`).
5. **GroqProvider has no consent gate** — unlike `LiteLLMProvider`, it will transmit document context whenever an ambient `GROQ_API_KEY` exists, and `AiModel._detect_provider` can auto-select it (`providers/groq_provider.py:18-52`, `core/local_llm.py:174-181`).
6. **Docling runs with `device='auto'` and auto-downloaded models** — preprocessing can contend for GPU VRAM outside `InferenceGate` and perform first-run network egress (`ingestion/docling_reader.py:127-132`).

## Tech Debt

**Dual, undocumented LanceDB locations:**
- Issue: `DEFAULT_DB_URI` resolves to `<repo>/retrieval/data/lancedb`, but `CLAUDE.md`, the Settings view, and `docker-compose.yml` all document/mount `data/lancedb`. A populated `data/lancedb/chunks.lance` (2 MB) and an empty `retrieval/data/lancedb/` both exist in the workspace.
- Files: `retrieval/hybrid_retriever.py:58`, `ui/views.py:860`, `docker-compose.yml:11`, `CLAUDE.md:147`
- Impact: Existing users lose their vector index after the package refactor; hydration silently re-embeds everything into the new path; purge leaves the old index on disk; Docker persistence mounts the wrong directory so the index is lost on container recreation.
- Fix approach: define one `DATA_DIR`/`LANCEDB_DIR` constant (e.g. in `core/models.py`), add a startup migration that moves/merges legacy tables, mount the same path in Compose, and assert the exact resolved path in tests.

**Ingestion is not atomic despite the docstring:**
- Issue: `upsert_document`, `record_evidence_elements`, `record_pages_batch`, and `record_chunks` each open their own `sqlite3` connection and commit independently (`core/doc_store.py:132-149`). A failure after step 1 leaves a document row marked `indexed`/`num_chunks=N` with zero chunks.
- Files: `ui/ingestion_service.py:235-266`, `core/doc_store.py:166-348`
- Impact: Library shows documents that cannot be retrieved; repair logic in `ui/ingestion_service.py:97-137` only partially compensates; evidence/chunk rows can be orphaned when indexing fails (`ui/ingestion_service.py:283-309`).
- Fix approach: add a `DocStore.ingest_transaction(...)` that accepts document, pages, chunks, and evidence in one connection/transaction, and use `status="partial"` or delete-on-failure instead of flipping to `failed` while leaving rows behind.

**`pages` table is write-only:**
- Issue: Page records are persisted (`core/doc_store.py:31-39`, `255-298`) but there is no read API, and `Page.page_text` is not a column. Nothing consumes page status/errors.
- Files: `core/doc_store.py:31-39`, `ui/ingestion_service.py:252`
- Impact: Wasted rows, page-level extraction failures invisible to users, and summaries must always be reconstructed from chunks rather than clean page text.
- Fix approach: either add `get_pages_for_doc()` plus UI surfacing, or drop the table and store page metadata in the manifest/cache only.

**Cache is write-only:**
- Issue: `pages.json`, `chunks.json`, and `manifest.json` are written after indexing (`ui/ingestion_service.py:311-322`) but no code path reads them.
- Files: `ui/ingestion_service.py:311-322`, `core/models.py:17-30`
- Impact: Duplicate disk usage for every document, no retry/recovery benefit, and cache invalidation complexity for an unused artifact.
- Fix approach: implement cache reads as the fast re-index path, or remove cache writes.

**Legacy compatibility surface left in place:**
- Issue: `HybridRetriever.search()`/`get_context()` and `LocalEmbedding.search_hybrid()` are deprecated but still shipped; `AiModel` still carries an unreachable "direct unindexed PDF" branch (`core/local_llm.py:240-250`). `retrieval/vector_index.py:12` uses `typing.List/Dict/Tuple`.
- Files: `retrieval/hybrid_retriever.py:739-756`, `retrieval/local_embedding.py:114-149`, `core/local_llm.py:240-250`, `retrieval/vector_index.py:12`
- Impact: Two retrieval return types with opposite score semantics; deprecation warnings are globally suppressed so drift is invisible.
- Fix approach: delete the legacy facades, type `VectorIndex` with builtin generics, and add a removal deadline.

**Duplicated follow-up-query rewriting:**
- Issue: The "short follow-up" heuristic exists in both `AiModel` and the Chat view, but only the view's copy affects retrieval when `retrieval_result` is precomputed.
- Files: `core/local_llm.py:252-280`, `ui/views.py:364-377`
- Impact: Behavior differs depending on call path; future edits will fix one copy only.
- Fix approach: move query rewriting into a single function used by `render_chat_view`.

**`print()` instead of logging in library code:**
- Issue: `print` calls bypass configured logging and pollute Streamlit stdout.
- Files: `ingestion/upload_validation.py:106`, `ingestion/pdf_reader.py:131`, `core/doc_store.py:164`
- Impact: Diagnostics are not timestamped/leveled; log filtering/redaction cannot apply.
- Fix approach: replace with module loggers; reserve `print` for `start.py`/`setup.py` CLI output.

**`setup.py` is an 801-line multi-purpose script:**
- Issue: It mixes packaging metadata, dependency installation, model downloading, archive extraction, and a CLI; `requirements` are parsed from `requirements.txt` at build time.
- Files: `setup.py:1-801`
- Impact: Packaging side effects and CLI/download code are hard to test; `pip install -e .` loads the whole script.
- Fix approach: move operational logic to `scripts/setup_cli.py`, keep `setup.py`/`pyproject.toml` declarative.

**Model naming misrepresentation (Qwen2 vs Qwen3):**
- Issue: Docs, UI copy, prompts, and `LlamaCppProvider` claim "Qwen3-VL 2B", but `setup.py` and README download Qwen2-VL 2B weights and save them under a `qwen3-vl-...` filename. `docs/RUNBOOK.md:95` admits the rename.
- Files: `setup.py:59-78`, `providers/llama_cpp_provider.py:1-30`, `main.py:323`, `README.md:17-18`, `docs/RUNBOOK.md:95`
- Impact: Capability/benchmark claims are attributed to the wrong model; a Qwen3 upgrade would not actually change behavior unless the filename is replaced manually.
- Fix approach: pick one real model, use its canonical filename, and update telemetry/provenance (`model_version`) to report the true checkpoint.

**Documentation drift:**
- Issue: README badge says 248 tests while the suite has 296; the repository tree lists pre-refactor root modules (`resource_telemetry.py`), and `start.py` is described as doing "pre-flight hardware checks" but only checks Python version and directories.
- Files: `README.md:10`, `README.md:76-106`, `start.py:49-66`, `start.py:214-262`
- Impact: Onboarding and operational expectations are wrong; no VRAM preflight actually exists.
- Fix approach: generate the tree/test-count snippets in CI or remove volatile claims.

**Weak static-analysis configuration:**
- Issue: Ruff selects only `E,F,W`, ignores `E501`, and there is no type checker or security linter (`S`), no bugbear (`B`), no import sorting.
- Files: `pyproject.toml:1-16`
- Impact: Broad `except Exception` (93 occurrences across app code; 20 in `retrieval/hybrid_retriever.py` alone), mutable defaults, and shadowing are not caught. No `mypy`/`pyright` despite pervasive typing.
- Fix approach: enable `B`, `S`, `I`, `UP`; add `mypy --strict` on `core/`; add `pip-audit`.

## Known Bugs

**UI bypasses summary cache invalidation:**
- Symptoms: After changing models, the Summarizer shows an old cached summary and labels it with the new model version.
- Files: `ui/views.py:558`, `ui/views.py:579-585`
- Trigger: Generate a summary, switch local→cloud (or change model), reopen the profile.
- Cause: On exact-version miss, the view falls back to `doc_store.get_summary(sha, profile)` with no `model_version` filter, undoing the invalidation implemented in `core/summarizer.py:333-337`.
- Fix approach: remove the unversioned fallback or display it explicitly as "stale; regenerate".

**Map-reduce prompt can exceed the local context window:**
- Symptoms: llama-server truncates the reduce prompt, drops citations, or errors on long PDFs; summary quality collapses.
- Files: `core/summarizer.py:166-194`, `core/summarizer.py:269-299`
- Trigger: Documents producing >3 map batches whose consolidated halves exceed ~2,500 estimated tokens; also any single page larger than `MAX_BATCH_TOKENS` is placed alone in a batch unsplit (`core/summarizer.py:180-194`).
- Cause: `combined_text`, `half1`, and `half2` are sent directly to `provider.generate_text` without `assemble_grounded_messages` or any budget check.
- Fix approach: recursively consolidate through a budgeted reducer, split oversized pages/chunks, and assert `estimate_tokens(prompt) <= context_window - max_tokens`.

**Docling chunk offsets are inconsistent:**
- Symptoms: `char_start`/`char_end` point at the wrong span or stop advancing within a page.
- Files: `ingestion/docling_reader.py:291-295`
- Trigger: Any page split into multiple prose chunks.
- Cause: `current_offset = sc_start + 1` instead of `sc_end` (the OCR path correctly uses `sc_end` at `ingestion/ocr_fallback.py:274`).
- Fix approach: set `current_offset = sc_end`; add a test asserting monotonic, non-overlapping offsets.

**Docling tables longer than 2,000 characters are mangled:**
- Symptoms: Large markdown tables are treated as prose and split by `RecursiveCharacterTextSplitter`, losing row/column structure.
- Files: `ingestion/docling_reader.py:255`
- Trigger: Wide/long tables.
- Fix approach: do not use a length cutoff to classify tables; detect table provenance/label instead (or allow long table chunks).

**Delete/purge reports success even when vector erasure fails:**
- Symptoms: "Deleted" toast and removed library entry, but the document's text can still be retrieved and cited.
- Files: `ui/lifecycle_service.py:45-53`, `ui/lifecycle_service.py:89-99`, `ui/views.py:702-704`, `ui/views.py:721-723`, `retrieval/hybrid_retriever.py:457-474`
- Trigger: LanceDB delete/drop throws (locked table, version mismatch, corrupted index).
- Cause: LanceDB exceptions are logged and ignored; `delete_document` returns only the SQLite result; the view unconditionally toasts success.
- Fix approach: propagate/aggregate storage-tier results, verify `has_document()` is false after delete, and surface partial-erasure failures to the user.

**Deleted documents can resurface from a stale fallback store:**
- Symptoms: Content of a deleted document appears in retrieval after LanceDB fails to initialize.
- Files: `retrieval/hybrid_retriever.py:141`, `retrieval/hybrid_retriever.py:157-170`, `retrieval/hybrid_retriever.py:457-474`, `retrieval/hybrid_retriever.py:271-276`
- Trigger: LanceDB unavailable on a later run while an older `fallback_store.json` exists.
- Cause: When LanceDB is active, deletes update only the in-memory fallback and never rewrite/remove the on-disk JSON; that stale file is loaded on a future fallback.
- Fix approach: on every mutation, also persist/rewrite (or delete) `fallback_store.json`, or remove the dual store entirely.

**`LocalEmbedding` reports distance as score:**
- Symptoms: Dense-only results are ordered/sorted incorrectly by consumers that assume "higher is better".
- Files: `retrieval/local_embedding.py:126-143`, `core/models.py:155`, `retrieval/vector_index.py:131-136`
- Trigger: Any caller of the deprecated `LocalEmbedding.search_hybrid`.
- Cause: `VectorIndex.search` returns cosine distance (lower is better) but it is assigned to `EvidenceSnippet.score`, whose contract says higher is better.
- Fix approach: convert to similarity (`1 - distance`) or delete the deprecated method.

**Document-scoped chat filtering happens after retrieval:**
- Symptoms: Selecting one document can yield empty or incomplete evidence even when that document contains the answer.
- Files: `ui/views.py:396`, `retrieval/hybrid_retriever.py:649-667`
- Cause: `search_hybrid` fetches a global candidate pool (30–40) and only then filters by `doc_id` in Python; the selected document may not appear in the global top-K.
- Fix approach: push the filter into LanceDB (`.where(...)`) and into BM25 scoring, or retrieve per-document pools.

**Re-index can leave orphaned vectors:**
- Symptoms: Duplicate/stale chunks remain searchable after re-indexing a document that was previously extracted with a different chunking scheme.
- Files: `ui/lifecycle_service.py:134-163`, `retrieval/hybrid_retriever.py:391-409`
- Cause: Re-index upserts by new `chunk_id` but never deletes vectors whose IDs are no longer produced.
- Fix approach: delete all vectors for `doc_id` before re-indexing, in one logical operation.

**`check_health` can close the active provider:**
- Symptoms: After a failed health probe, the active provider's HTTP client is closed while still assigned to `AiModel.provider`, causing subsequent requests to fail.
- Files: `core/local_llm.py:187-207`
- Trigger: `cloud_mode=True` with a provider whose `check_health()` returns unhealthy (`_detect_provider` returns the same object, then it is closed).
- Fix approach: never close a provider that is still referenced; close only newly created instances.

**Session reset leaves retrieved evidence in memory:**
- Symptoms: "Clear Session" empties chat UI but `ai_model.last_retrieval_result`/`last_verification_result` still hold snippets from the previous conversation.
- Files: `main.py:56-91`, `core/local_llm.py:126-132`
- Fix approach: reset the AiModel's per-turn state (or recreate it) in `_reset_session_security_state`.

**Partial "Reset In-Memory Session" semantics:**
- Symptoms: The Settings reset leaves retrieval state, `_startup_hydrated`, and cached models untouched, unlike "Clear Session".
- Files: `ui/views.py:867-872`
- Fix approach: call one shared reset routine.

## Security Considerations

**Regex sanitizer is bypassable (verified):**
- Risk: A malicious PDF or injected model output can cause browser-triggered fetches or clickable hostile URLs, violating the "zero egress in local mode" invariant.
- Files: `ui/sanitizer.py:10-30`, `ui/sanitizer.py:53-76`
- Verified bypasses: `[x][r]` + `[r]: https://…`, `<https://…>` autolinks, `[x](data:…)`, `[x](javascript:…)`, `<img srcset=…>`, `<div style="background:url(https://…)">`, `<svg><use href=…>`, `<script>…</script >` (closing-tag whitespace).
- Current mitigation: sanitized content is rendered with default `st.markdown` (HTML escaped), but Markdown links and reference-style images still render (`ui/views.py:284`, `ui/views.py:327-330`).
- Recommendations: use a real Markdown/HTML sanitizer (e.g. `bleach` or `markdown-it` with a URL allowlist), remove all `http(s)`/protocol-relative URLs regardless of syntax, and add regression fixtures for the cases above.

**No bind-address pinning in the app config:**
- Risk: `streamlit run main.py` is a documented entry point, and `.streamlit/config.toml` does not set `server.address`. Streamlit's default listener can expose the private document workspace on the LAN with no authentication.
- Files: `.streamlit/config.toml:9-13`, `Dockerfile:46`, `start.py:221`
- Current mitigation: `start.py` defaults to `localhost`; Compose publishes to `127.0.0.1`. Direct `streamlit run` bypasses both.
- Recommendations: set `server.address = "127.0.0.1"` in config, require explicit opt-in for remote binding, and document the threat model.

**Groq fallback transmits without consent:**
- Risk: Cloud egress of document excerpts with no `PermissionError` gate and no UI consent record.
- Files: `providers/groq_provider.py:18-52`, `core/local_llm.py:174-181`
- Current mitigation: the UI routes through a consented `LiteLLMProvider`; the Groq path is only reached programmatically or if `cloud_mode=True` is set without a provider.
- Recommendations: add the same `user_consented` check to `GroqProvider`, or remove it and keep LiteLLM as the only cloud adapter.

**LiteLLM telemetry can be re-enabled by environment:**
- Risk: Third-party telemetry/analytics network calls from a local-first app.
- Files: `providers/litellm_provider.py:18-26`
- Cause: `os.environ.setdefault("LITELLM_TELEMETRY", "False")` yields to any pre-set value; `litellm.telemetry = False` is a single library-global.
- Recommendations: force the value (overwrite) before import, set `LITELLM_LOG=ERROR`, and add a socket-blocking test around imported cloud modules.

**Loopback allowlist trusts hostnames:**
- Risk: `host.docker.internal` and `llama-server` are accepted by name without resolving/validating the resulting IP; DNS/hosts compromise can redirect inference (and therefore document text) off-host.
- Files: `providers/llama_cpp_provider.py:60-73`; `allow_remote=True` bypass at `providers/llama_cpp_provider.py:33`, `69-73`
- Current mitigation: remote hosts are rejected by default and `allow_remote` is not exposed through configuration.
- Recommendations: resolve the hostname and validate every resolved address with `ipaddress.is_loopback`/private ranges; keep the named exceptions Docker-only.

**Untrusted PDFs are parsed in-process with no isolation:**
- Risk: Decompression bombs, pathological page trees, and parser bugs (pypdf/Docling/PyMuPDF/RapidOCR) can hang or OOM the Streamlit process. Validation only checks `%PDF-`, byte size, and page count; embedded JavaScript, `/Launch`, `/OpenAction`, `/EmbeddedFile`, and XFA are not scanned. Page-count rejection happens only after `pypdf.PdfReader` has parsed the page tree.
- Files: `ingestion/upload_validation.py:78-106`, `ingestion/docling_reader.py:125-138`, `ingestion/pdf_reader.py:17`, `ingestion/ocr_fallback.py:106`
- Current mitigation: 50 MB / 500 page caps.
- Recommendations: pre-parse structural checks, run extraction in a worker subprocess with memory/time limits, and reject PDFs with active content.

**Archive extraction is vulnerable to path traversal:**
- Risk: Downloaded llama.cpp archives are extracted with `zipfile.extractall()`/`tarfile.extractall()` without member path validation (Zip Slip / tar slip). Downloads are verified only by minimum size, not checksum.
- Files: `setup.py:337-352`, `setup.py:174-184`
- Recommendations: validate each member path against `dest_dir.resolve()`, reject symlinks/absolute paths, and verify published SHA-256 checksums (or Sigstore) before extraction.

**Groq errors are not credential-scrubbed:**
- Risk: Provider error text shown to users/logs may contain sensitive request context; unlike LiteLLM, no redaction is applied.
- Files: `providers/groq_provider.py:125-126`, `providers/groq_provider.py:160-161`, contrast `providers/litellm_provider.py:135-140`
- Recommendations: apply a shared scrubber before raising/logging.

**Runtime model download during "local" ingestion:**
- Risk: Docling's layout/table models auto-download from Hugging Face when `artifacts_path` is `None`; first conversion in a supposedly offline session performs external network access.
- Files: `ingestion/docling_reader.py:127-132` (verified `PdfPipelineOptions().artifacts_path is None` and `device='auto'`)
- Recommendations: pre-cache Docling artifacts in `setup.py`, pin `artifacts_path`, and fail fast with an offline-friendly message when missing.

## Performance Bottlenecks

**All chunks are duplicated in Python memory even when LanceDB is active:**
- Problem: `index_chunks` always appends every chunk and 384-float vector to `_fallback_store` before writing LanceDB; this store is never trimmed.
- Files: `retrieval/hybrid_retriever.py:319-333`, `retrieval/hybrid_retriever.py:136-139`
- Impact: Python floats cost ~32 bytes each; 100k chunks ≈ 1.2 GB RSS, plus `VectorIndex` lists. On a 4 GB-VRAM consumer laptop this is the dominant memory growth path.
- Improvement: only maintain the fallback when LanceDB is unavailable; otherwise keep a lazy, disk-backed fallback.

**Brute-force vector search in pure Python:**
- Problem: Every dense query computes cosine distance against all stored vectors and recomputes both magnitudes (sqrt) each time.
- Files: `retrieval/vector_index.py:130-136`, `retrieval/vector_index.py:157-199`
- Impact: ~7.7M float ops + N sqrt calls per query at 10k chunks; latency grows linearly with corpus size and duplicates work already done by `normalize_embeddings=True`.
- Improvement: use NumPy matrix multiply for the fallback, precompute norms, or rely exclusively on LanceDB ANN.

**FTS index rebuilt on every indexing batch:**
- Problem: `create_fts_index("content", replace=True)` is called after table creation and after every subsequent `index_chunks` call.
- Files: `retrieval/hybrid_retriever.py:387-413`, `retrieval/hybrid_retriever.py:522-530`
- Impact: Upload cost scales with total corpus size, not with the new document.
- Improvement: build/refresh the FTS index once per batch of uploads or on an explicit maintenance step.

**BM25 fallback scans up to 10k rows and tokenizes the corpus per query:**
- Problem: When FTS is unavailable, it reads up to 10,000 rows from LanceDB and builds token counts for every document on every query.
- Files: `retrieval/hybrid_retriever.py:532-592`
- Impact: Multi-second queries and large transient allocations; `table.search()` without a query can also fail and silently return no FTS results.
- Improvement: persist an inverted index (or a lightweight SQLite FTS5 index) instead of recomputing BM25 per query.

**Per-page PDF re-open during OCR:**
- Problem: `render_page_image` calls `fitz.open(stream=pdf_bytes)` for each page; a 500-page scan re-parses the whole PDF 500 times.
- Files: `ingestion/ocr_fallback.py:103-127`, `ingestion/ocr_fallback.py:318-345`
- Impact: O(pages²) parsing time on OCR-heavy documents.
- Improvement: open the document once and reuse it, or pass the open `fitz.Document` into the worker.

**OCR thread pool provides little parallelism and multiplies memory:**
- Problem: Up to 4 workers rasterize pages concurrently, but all OCR inference is serialized behind `self._ocr_lock` (`ingestion/ocr_fallback.py:143`), and each worker holds its own document parse plus a full page pixmap.
- Files: `ingestion/ocr_fallback.py:68`, `ingestion/ocr_fallback.py:143-154`, `ingestion/ocr_fallback.py:388-408`
- Impact: Peak memory spikes without throughput gain; low-confidence OCR text (`_score` is discarded) is indexed as ground truth.
- Improvement: reopen once, batch pages through a single ONNX session, and gate on confidence.

**Health check on every Streamlit rerun:**
- Problem: `AiModel.check_health()` is called on each interaction; when llama-server is down it performs two probes with 2s connect timeouts, and `_detect_provider` constructs a new `httpx.Client` each time.
- Files: `main.py:190`, `core/local_llm.py:187-207`, `providers/llama_cpp_provider.py:97`
- Impact: 2–4 seconds of added latency per UI action while offline, plus client churn.
- Improvement: cache health status for a few seconds, reuse one client, and probe asynchronously.

**Settings telemetry spawns redundant `nvidia-smi` processes:**
- Problem: `get_system_telemetry_snapshot` calls GPU memory (cached 5s) plus `get_compute_apps_gpu_memory()` twice (directly and via `get_resident_model_gpu_memory`), none cached.
- Files: `core/resource_telemetry.py:287-310`, `core/resource_telemetry.py:100-144`, `core/resource_telemetry.py:147-166`
- Impact: Up to 2 subprocesses × 2s timeout per render on the Settings page.
- Improvement: cache compute-apps data under the same TTL and derive resident memory from the cached result.

**Heavy libraries imported eagerly:**
- Problem: `core/local_llm.py` imports `LocalEmbedding`, which imports `sentence_transformers`/Torch and mutates `os.environ` at import time; `main.py` imports `AiModel` unconditionally.
- Files: `core/local_llm.py:14-21`, `retrieval/local_embedding.py:12-16`
- Impact: Seconds of startup time and hundreds of MB RSS even in cloud-only or library-only usage; global env mutation affects the whole process.
- Improvement: lazy-import embedding/model code inside the paths that need it and move env setup into `main.py`.

**Whole-document visual scan runs even when VLM analysis cannot be used:**
- Problem: `detect_visual_regions` iterates every page's images and drawings before checking whether a local vision provider exists.
- Files: `ui/ingestion_service.py:189-206`, `ingestion/visual_analyzer.py:73-146`
- Impact: CPU cost for `get_drawings()` on complex PDFs is paid and discarded in cloud mode or when no provider is supplied.
- Improvement: check provider capability first; make vision analysis an explicit ingest option.

**Blocking ingestion on the Streamlit script thread:**
- Problem: validation, Docling, OCR, VLM, and embeddings all run inline in the UI callback.
- Files: `ui/views.py:73-99`, `ui/ingestion_service.py:54-334`
- Impact: The workspace freezes for the entire ingestion (minutes on large/scanned PDFs) and cannot be cancelled.
- Improvement: move ingestion to a background worker/thread with progress polling and cancellation.

## Fragile Areas

**`InferenceGate` guarantees are process-local and timeout-bounded:**
- Files: `core/local_llm.py:26-90`, `core/local_llm.py:317-330`, `core/summarizer.py:389`
- Why fragile: A class-level `RLock` only serializes threads in one Python process; a second Streamlit instance, `scripts/profile_resources.py`, or a separate benchmark bypasses it entirely. Chat waits only 60s while summaries may hold the gate for many minutes; on timeout the UI yields a "System is busy" string (`core/local_llm.py:319`) which is then treated as an ungrounded assistant answer.
- Safe modification: keep `hold()` around every provider call, use a file lock/VRAM metric for cross-process safety, and surface busy/timeout as a UI error rather than model text.
- Test coverage: `tests/test_concurrency_lock.py` covers single-process acquire/release only.

**LanceDB/PyArrow API drift is masked by fallbacks:**
- Files: `retrieval/hybrid_retriever.py:29-43`, `retrieval/hybrid_retriever.py:387-409`, `retrieval/hybrid_retriever.py:609`
- Why fragile: Code probes `merge_insert`, `query_type="fts"`, `_distance`, `_score`, and `create_fts_index(replace=True)` across versions. Requirements allow `lancedb>=0.17.0` and `pyarrow>=14.0.0`, so an install can silently fall back to in-memory/BM25 instead of failing loudly. The Arrow schema permanently fixes `vector` at 384 dimensions.
- Safe modification: pin versions, assert table schema/dimension at startup, and fail the health check when the persistent backend is unavailable.
- Test coverage: tests use temp DBs with the installed version only; no cross-version matrix.

**Docling integration depends on unstable private-ish APIs:**
- Files: `ingestion/docling_reader.py:23-32`, `ingestion/docling_reader.py:145-192`, `ingestion/docling_reader.py:332-338`
- Why fragile: `iterate_items`, `prov[0].page_no`, `doc.pages`, `doc.tables`, and `export_to_markdown(doc=...)` change between Docling releases. Any exception falls back to plain `pypdf`, silently losing tables and reading order with only a warning.
- Safe modification: pin Docling, validate a canonical conversion in CI with a real PDF, and distinguish "fallback expected" from "bug: report and abort".
- Test coverage: `tests/test_docling_reader.py` uses `MagicMock` converters exclusively; real Docling conversion is untested.

**SQLite migrations run on every `DocStore` construction with no version guard or transaction boundary:**
- Files: `core/doc_store.py:113-130`, `core/doc_store.py:151-164`
- Why fragile: `DocStore` is instantiated on every Streamlit rerun, and each migration executes DDL then bumps `user_version` per version. A crash mid-version relies on implicit rollback; a database with `user_version > 4` (created by a newer build) is silently accepted and later queries can fail on missing/renamed columns. `VACUUM` in `purge_all` (`core/doc_store.py:630`) can fail with "database is locked" while other connections are open, and is unguarded in the UI path.
- Safe modification: wrap all pending migrations in a single explicit transaction, refuse `user_version` above the supported max, and isolate `VACUUM` in a maintenance window with error handling.
- Test coverage: `tests/test_doc_store.py` verifies a fresh DB reaches v4, not legacy upgrade or forward-version cases.

**Session-scoped heavy objects have no teardown:**
- Files: `main.py:148-159`, `ui/hydration.py:51-74`
- Why fragile: Each session creates its own `AiModel`/`LlamaCppProvider` `httpx.Client`, `HybridRetriever`, and embedding model reference. Abandoned browser sessions are not reliably cleaned up, and hydration repair runs synchronously in every new session, potentially re-embedding the entire corpus concurrently.
- Safe modification: use process-level singletons guarded by locks; limit repair to explicit user action or a single background job.

**Prompt-boundary defense is one-tag deep:**
- Files: `core/prompt_budget.py:34-48`, `core/prompt_budget.py:65-150`
- Why fragile: Only `<document_context>` tags are escaped; `<|im_start|>`-style special tokens, fake `system:` turns, and zero-width characters pass through. Token budgeting uses `len(text)/4`, which badly underestimates CJK and code/table-heavy documents, so truncation may not happen when needed.
- Safe modification: strip/escape role markers and special tokens, use the provider tokenizer (or a conservative per-script ratio), and assert the final token count.

## Scaling Limits

**In-memory vector duplication:**
- Current capacity: roughly 100k chunks before Python object overhead reaches ~1 GB RSS (12 KB/chunk average).
- Limit: 4 GB total system RAM on the target laptop, shared with Docling/OCR/Torch.
- Scaling path: drop the always-on fallback store; use LanceDB only and stream fallback entries from disk.

**Single-inference serialization:**
- Current capacity: one generation/vision/summarization at a time per process.
- Limit: a long map-reduce summary (hundreds of pages) blocks chat for the full duration; 60s chat gate times out.
- Scaling path: chunked/streamed summarize with per-stage gate acquisition, cancellable jobs, and a queue with user-visible state.

**Visual evidence coverage:**
- Current capacity: ingestion analyzes at most 6 regions (`ui/ingestion_service.py:204`), while the analyzer default is 20 (`ingestion/visual_analyzer.py:208`).
- Limit: documents with many figures silently lose visual grounding after the first few regions.
- Scaling path: expose a user-configurable budget, record skipped regions, and analyze in later passes.

**Upload concurrency:**
- Current capacity: one 50 MB PDF plus its Docling/OCR copies in memory per file; multiple selected files are all held by the uploader.
- Limit: selecting several scanned PDFs can hold hundreds of MB and trigger OOM before any validation rejects them.
- Scaling path: process files one at a time, write to temp files instead of holding `bytes`, and enforce a batch limit.

**Document-scoped retrieval:**
- Current capacity: global candidate pool 30–40 before `doc_id` filtering.
- Limit: libraries with many documents return empty scoped results.
- Scaling path: server-side filtering and per-document indexing.

## Dependencies at Risk

**Loose runtime ranges vs. a lockfile that CI alone uses:**
- Risk: `requirements.txt` allows `docling>=2.0.0`, `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `pymupdf>=1.24.0`, `litellm>=1.50.0`, `rapidocr>=1.3.0/3.0.0`, and `numpy>=1.26,<3`; `requirements-lock.txt` pins `docling==2.138.0`, `lancedb==0.40.0`, `pyarrow==23.0.1`, `pymupdf==1.28.2`, `litellm==1.105.0`.
- Files: `requirements.txt:1-19`, `requirements-lock.txt:83-521`, `Dockerfile:26-27`, `setup.py:496-521`
- Impact: Docker images and `python setup.py setup` install unpinned versions, contradicting the "reproducible" claim; a fresh install can break Docling/LanceDB integration in ways CI never sees.
- Migration plan: install from the lockfile everywhere (Dockerfile, `run_full_setup`), add `--require-hashes`, and add Dependabot/Renovate with a compatibility test job.

**`litellm` behavior changes:**
- Risk: Telemetry, retry, and provider-adapter behavior have changed across releases; the code relies on a module-global `litellm.telemetry` and implicit provider routing.
- Files: `providers/litellm_provider.py:18-26`, `providers/litellm_provider.py:221-239`
- Impact: Silent network calls or changed error shapes can break privacy guarantees and scrubbing.
- Migration plan: pin, force telemetry off post-import, and wrap with an egress-blocking test.

**Torch/Transformers/NumPy transitive stack:**
- Risk: `torch==2.14.1`, `transformers==4.57.6`, and `numpy==2.4.6` are locked but not declared in `requirements.txt`; `sentence-transformers==3.4.1` is sensitive to both.
- Files: `requirements.txt:7`, `requirements-lock.txt:240-567`
- Impact: Unpinned installs can resolve incompatible Torch/NumPy combinations, producing import or CPU-kernel failures.
- Migration plan: declare the tested ranges explicitly or require the lockfile.

**Dual RapidOCR APIs keyed on Python version:**
- Risk: `rapidocr-onnxruntime` (<3.13) and `rapidocr` (>=3.13) return different result shapes; CI runs 3.11 while local runs appear to be 3.13.
- Files: `requirements.txt:12-13`, `ingestion/ocr_fallback.py:21-27`, `ingestion/ocr_fallback.py:154-197`
- Impact: The result-parsing branches diverge between the tested and deployed interpreters.
- Migration plan: standardize on one Python version (3.11) across dev/CI/Docker, or add a 3.13 CI job.

**`pymupdf`/`docling` native wheels:**
- Risk: Both ship compiled dependencies; Windows wheels lag releases and `pymupdf>=1.24.0` may pull behavior changes in rasterization/drawing APIs.
- Files: `requirements.txt:14-15`, `ingestion/ocr_fallback.py:29-32`, `ingestion/visual_analyzer.py:18-21`
- Impact: The primary Windows platform is not in CI, so platform-specific failures surface only for users.
- Migration plan: add a Windows CI job and pin exact versions.

**No dependency/security scanning:**
- Risk: No `pip-audit`, no lockfile hashes, no automated updates.
- Files: `.github/workflows/ci.yml:1-45`
- Impact: Known CVEs in PDF/ONNX/Torch stacks go unnoticed.
- Migration plan: add `pip-audit --strict` and a scheduled dependency job.

## Missing Critical Features

**Tokenizer-accurate context budgeting:**
- Problem: `estimate_tokens` is a 4-chars-per-token heuristic (`core/prompt_budget.py:51-62`) used for the hard 4K VRAM envelope.
- Blocks: Reliable operation on non-English documents and dense tables; prompts can exceed the real context window despite passing the budget check.

**Embedding/vector versioning and migration:**
- Problem: `Chunk.embedding_model` is never populated (`core/doc_store.py:52`, `ui/ingestion_service.py:254`) and the LanceDB schema hardcodes 384 dimensions (`retrieval/hybrid_retriever.py:29-43`). Changing the embedding model silently mixes incompatible vectors.
- Blocks: Safe model upgrades and re-index-on-model-change.

**Cancellation and timeouts for long-running operations:**
- Problem: Ingestion and summarization cannot be cancelled and have no overall deadline; only the gate has a timeout.
- Blocks: Usable UX on large/scanned PDFs; recovery from a hung parser.

**Authentication / multi-user isolation:**
- Problem: The app assumes a single trusted user; there is no login and all sessions share the same SQLite store and vector index.
- Blocks: Any shared-host or LAN deployment; even local multi-account use exposes all documents.

**Encryption at rest / secure deletion:**
- Problem: Documents, chunk text, summaries, and vectors are stored in plaintext SQLite/LanceDB/JSON; deletion does not securely erase file pages.
- Blocks: Strong privacy guarantees beyond process-local access control.

**OCR/vision quality gates:**
- Problem: OCR confidence is discarded and placeholder visual analyses are persisted; users cannot see which evidence came from low-quality extraction.
- Blocks: Auditable answer quality for scanned documents.

**Operational health for storage tiers:**
- Problem: Only the model provider has health checks. LanceDB/Docling/OCR availability is discovered by silent fallback at use time.
- Blocks: Users cannot tell whether hybrid retrieval is actually active or degraded to BM25/in-memory.

## Test Coverage Gaps

**Sanitizer bypass vectors:**
- What's not tested: Reference-style links/images, autolinks, `data:`/`javascript:` schemes, `srcset`, inline `style` URLs, SVG `<use>`.
- Files: `ui/sanitizer.py:10-30`, `tests/test_sanitizer.py:1-54`
- Risk: The core privacy invariant regresses silently; tests currently assert only `https://` inline links/images.
- Priority: High

**Summarizer map-reduce budgeting:**
- What's not tested: Consolidation path with enough batches to exceed `FAST_PATH_TOKEN_LIMIT`, oversized single pages, prompts exceeding the provider context.
- Files: `core/summarizer.py:166-299`, `tests/test_summarizer.py:166-200`
- Risk: Local inference overflows/truncates on exactly the documents this app targets.
- Priority: High

**Vector persistence failure semantics:**
- What's not tested: `index_chunks` when `create_table`/`merge_insert`/FTS raises; delete when LanceDB delete fails; stale `fallback_store.json` resurrection.
- Files: `retrieval/hybrid_retriever.py:375-419`, `retrieval/hybrid_retriever.py:457-474`
- Risk: Ingestion reports success while evidence is missing or resurrects deleted content.
- Priority: High

**Real Docling and OCR conversion:**
- What's not tested: Actual `DocumentConverter` output across Docling versions, real RapidOCR result shapes on Python 3.11 vs 3.13, real PyMuPDF rendering.
- Files: `tests/test_docling_reader.py:1-40`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`
- Risk: Mock-only coverage hides API/schema drift on the primary platform.
- Priority: High

**Legacy/forward SQLite migrations:**
- What's not tested: Upgrading a v1/v2 database with existing rows, duplicate `(sha256, profile)` rows before v3, `user_version > 4`, concurrent `DocStore` construction, `VACUUM` while another connection is open.
- Files: `core/doc_store.py:105-164`, `core/doc_store.py:619-630`, `tests/test_doc_store.py:127-133`
- Risk: Startup crash or data loss for users upgrading builds.
- Priority: Medium

**Deletion/purge failure paths and UI reporting:**
- What's not tested: LanceDB delete failure, partial SQLite failure mid-ingestion, `delete_document` returning `False`, false-success toasts.
- Files: `ui/lifecycle_service.py:31-166`, `ui/ingestion_service.py:248-309`, `ui/views.py:694-723`
- Risk: Users believe data is erased when it is still searchable.
- Priority: High

**Cloud consent coverage for Groq:**
- What's not tested: `GroqProvider` refusing transmission without consent; `AiModel` auto-fallback to Groq.
- Files: `providers/groq_provider.py:18-52`, `core/local_llm.py:174-181`, `tests/test_cloud_privacy.py`
- Risk: Unconsented egress regression.
- Priority: High

**Summary cache version fallback and citation filtering in views:**
- What's not tested: The unversioned cache fallback (`ui/views.py:581-585`), citation chip filtering by `cited_ranks`, scoped retrieval emptiness.
- Files: `ui/views.py:440-462`, `ui/views.py:579-585`
- Risk: Stale/misattributed summaries and missing citations are invisible to tests.
- Priority: Medium

**Coverage measurement and platform matrix:**
- What's not tested/enforced: No `pytest-cov`, no coverage threshold, no Windows job; CI is Linux + Python 3.11 only.
- Files: `.github/workflows/ci.yml:1-45`, `requirements-test.txt:1-5`, `pyproject.toml:18-31`
- Risk: Untested paths and the primary Windows platform are unmeasured; global warning suppression hides deprecation debt.
- Priority: Medium

---

*Concerns audit: 2026-10-21*
