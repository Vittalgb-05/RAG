<!-- refreshed: 2026-10-22 -->
# Codebase Concerns

**Analysis Date:** 2026-10-21 (repair status added 2026-10-22)

Severity reflects impact on the stated core value (fast, grounded, local-only PDF QA within 4 GB VRAM). Status is either **open** (confirmed defect/gap) or **verification gap** (behavior is plausible but unproven by tests/CI).

## Repair Status (2026-10-22)

Resolved in the 2026-10-21/22 repair batches (see `docs/REPAIR_LOG.md` and `docs/TEST_RESULTS.md`):

- Whole-document extraction / EVS question grounding (fixed retrieval scope, prompt, withhold gate, citation chips).
- Fallback mirror divergence and scoped 10k truncation; LanceDB FTS status surface added.
- Visual evidence excluded from summaries; summary session cache model-version drift; truncation notices.
- Sanitizer bypass classes; OCR/visual pixel and time budgets; PNG/JPEG MIME detection; non-loopback bind refusal.
- Missing application logging, `print()` in library modules, SQLite retry, gate release on generator close.
- Unpinned model/llama-server downloads, non-streaming checksum verification, broken lmstudio mirror, gated Qwen URLs in the runbook.
- Write-only extraction cache (write path removed; legacy cache cleanup retained).
- Deprecated `HybridRetriever.add_vector` shim; Ruff rules `B`, `UP`, and `SIM` enabled.
- Thesis rejection & false withholding on high-level queries: resolved via lexical citation auto-attribution (`auto_attribute_citations`) in `core/citation_validator.py` and non-blocking warning gate in `ui/views.py` (withholding strictly reserved for detected prompt injections).
- Truncated / "way too small" summarizations: resolved by expanding token budgets (intermediate map 1500, fast-path/reduce 2500, chat stream 2048) and rewriting synthesis prompts for rich multi-paragraph extractions in `core/summarizer.py`.
- Chat query reverse-ordering / DOM inversion: resolved by enforcing strict chronological sequence and immediate `st.rerun()` upon turn completion in `ui/views.py`.
- Clunky 4-workspace UI consolidated into a focused chatbot-first interface: 2 primary views (`Chat` and `Document Library`), unified single-button document insertion (`render_file_upload_button`), and collapsible system/privacy expander.
- Comprehensive `.gitignore` update covering SQLite WAL/SHM, LanceDB indexes, logs, and development scratch scripts.

Deferred by explicit scope decision (tracked, not fixed): encryption at rest, authentication, portable backup/restore, request cancellation, health auto-recovery, full CI OS/Python matrix, LanceDB image digest pinning, and splitting `setup.py` into a thin packaging shim plus installer module.


## Tech Debt

**Write-only extraction cache [Medium · open]**
- Issue: Ingestion serializes `pages.json`, `chunks.json`, and `manifest.json` under `.cache/<sha256>/<CONFIG_VERSION>/`, but nothing in the codebase ever reads them. `cache_dir_for` is imported only for writes (`ui/ingestion_service.py`) and deletion (`ui/lifecycle_service.py`). There is no cache-hit path, no repair-from-cache path, and no cache-version migration reader.
- Files: `ui/ingestion_service.py:331-338`, `ui/lifecycle_service.py:60-66`, `core/models.py:14-30`
- Impact: Duplicate plaintext copies of every document on disk (privacy surface), unnecessary I/O on every ingest, and misleading "cache" semantics. The `.cache/` "Clear Disk Cache" control in Settings implies a performance feature that does not exist.
- Fix approach: Either implement a real cache read path (skip Docling/OCR when SHA + `CONFIG_VERSION` match and hydrate `Page`/`Chunk` models) or delete the write path and `CONFIG_VERSION` cache key entirely. Do not leave write-only storage.

**`print()` in library code and no application logging configuration [Low–Medium · open]**
- Issue: Library modules write directly to stdout (`core/doc_store.py:164`, `ingestion/pdf_reader.py:131`, `ingestion/upload_validation.py:106`). The app never calls `logging.basicConfig`/`dictConfig`; `core/logging_setup.py` only installs a filter for benign watcher warnings. Under Streamlit, `logger.info` is below the default root level, so progress logs are dropped while `print()` output goes to the server console.
- Files: `core/doc_store.py:164`, `ingestion/pdf_reader.py:131`, `ingestion/upload_validation.py:106`, `core/logging_setup.py:1-45`, `main.py:1-120`
- Impact: No durable, level-controlled log stream; ingestion diagnostics are inconsistent; filenames and error strings bypass structured logging. Makes field debugging of OCR/Docling failures harder.
- Fix approach: Configure one root handler at startup (file + stderr, rotation) in `main.py`/`start.py`, replace `print()` with `logger`, and surface user-facing failures through return values/toasts rather than console output.

**Monolithic `setup.py` mixes packaging, network downloads, and process control [Medium · open]**
- Issue: `setup.py` is 883 lines containing setuptools metadata, GGUF download/mirror logic, archive extraction, llama-server install, dependency installation, and a custom CLI parser that inspects `sys.argv`. It also declares `py_modules=["main", "setup", "start"]`, installing a top-level module literally named `setup`.
- Files: `setup.py:1-883` (metadata ~`796-883`, downloads ~`157-257`, llama install ~`441-575`, CLI ~`796-883`)
- Impact: Any `pip install .` executes a large amount of incidental code; the packaging surface is hard to test and audit; the top-level `setup` module can collide with other packages. Network and subprocess behavior is coupled to installation.
- Fix approach: Keep `setup.py` to a thin shim; move downloads/installers into a `tools/` or `scripts/` CLI module, drop `setup` from `py_modules`, and add tests around archive extraction and download validation.

**Duplicated follow-up query rewriting [Low · open]**
- Issue: The exact short-follow-up heuristic (token count ≤ 4 plus pronoun/verb stopword set) is implemented twice: once in the UI before retrieval and once inside `AiModel`. In the live `render_chat_view` path the UI always supplies `retrieval_result`, so the `AiModel` copy is dead code that can silently drift.
- Files: `ui/views.py:363-378`, `core/local_llm.py:265-299`
- Impact: Two sources of truth for query contextualization; a fix in one place will not affect the other, and the dead branch is untested in the live path.
- Fix approach: Extract a single `contextualize_query()` helper (e.g., in `core/`), use it in both call sites, and unit-test pronoun cases (`"why?"`, `"more details"`, `"what about it"`).

**Deprecated retrieval facades and two parallel index implementations [Medium · open]**
- Issue: `LocalEmbedding` is retained as a legacy facade with deprecated `search_hybrid`/`get_context` methods, and `HybridRetriever` carries an `add_vector` compatibility shim. The fallback `VectorIndex` duplicates storage/search logic that LanceDB already provides.
- Files: `retrieval/local_embedding.py:113-156`, `retrieval/hybrid_retriever.py:526-528`, `retrieval/vector_index.py:1-140`, `ui/views.py` fallback path when no hybrid retriever is available
- Impact: Every retrieval feature must be implemented twice (dense search, doc filters, deletion, persistence), which is the root cause of the fallback divergence bugs below. Deprecation warnings are not enforced, so new code can still adopt the facade.
- Fix approach: Pick LanceDB + one explicit fallback behind a single interface; delete the legacy facade and shim once call sites are migrated; add a contract test suite run against both backends.

**Minimal lint rule set [Low · open]**
- Issue: Ruff selects only `E`, `F`, `W` and ignores `E501`, `W291`, `W293`. There are no `B` (bugbear), `S` (security), `UP` (pyupgrade), `SIM`, or `ARG` rules; line length is effectively unchecked despite `line-length = 120`.
- Files: `pyproject.toml` (`[tool.ruff.lint]`)
- Impact: Broad `except Exception`, mutable defaults, subprocess/`eval`-style hazards, and dead arguments are not flagged. Silent `except Exception: pass` patterns survive review (see Fragile Areas).
- Fix approach: Enable `B`, `UP`, `SIM`, and a targeted `S` set in `pyproject.toml`, fix the resulting violations, and remove the `E501` ignore once formatting is stable.

**Documentation drift about storage and launch flags [Low · open]**
- Issue: README's project structure lists flat modules (`models.py`, `local_llm.py`, …) while the code is packaged under `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`. README and `docs/EVALUATION.md:72` describe "SQLite FTS5 BM25", but keyword search is LanceDB FTS (`create_fts_index`) with an in-Python BM25 fallback. README recommends `llama-server -b 512 -ub 512`, but `start.py` launches with only `ngl`/`ctx` and never passes batch flags.
- Files: `README.md` (structure and architecture sections), `docs/EVALUATION.md:72`, `retrieval/hybrid_retriever.py:617-625`, `start.py:110-160`
- Impact: New contributors and operators reason about the wrong backend and hardware profile; the documented VRAM/batch tuning is not what the launcher actually applies.
- Fix approach: Update both docs to the package layout and LanceDB FTS, and either pass the recommended batch flags in `start.py` or remove them from the README. Add the doc-claimed numbers to a startup log line.

**Model naming inconsistency (`qwen3-vl-*` filenames for Qwen2-VL weights) [Low · open]**
- Issue: The downloader saves Qwen2-VL-2B-Instruct weights as `qwen3-vl-2b-instruct-q4_k_m.gguf`, and the code comments acknowledge the mismatch. `core/model_identity.py` exists specifically to read GGUF metadata because filenames are unreliable.
- Files: `setup.py:61-79`, `start.py:128-133`, `core/model_identity.py`
- Impact: Operator confusion, fragile manual commands, and a persistent trap for future model swaps.
- Fix approach: Rename artifacts to match the real model, keep a migration alias for existing installs, and continue using metadata (not filenames) for versioning.

## Known Bugs

**Fallback vector mirror is clobbered whenever LanceDB is available [High · open]**
- Issue: `_fallback_store` is only loaded from `fallback_store.json` when LanceDB is unavailable. When LanceDB initializes successfully, the in-memory fallback starts empty, yet `index_chunks`/`delete_document` still call `_save_fallback_store()`, overwriting the durable mirror with only the current session's chunks (or an empty list after a delete). The BM25 fallback then also searches only that partial set, because it uses `self._fallback_store.documents` whenever non-empty and only reads LanceDB when the fallback is empty.
- Files: `retrieval/hybrid_retriever.py:196-216`, `retrieval/hybrid_retriever.py:481-490`, `retrieval/hybrid_retriever.py:547-554`, `retrieval/hybrid_retriever.py:638-645`
- Impact: If LanceDB later fails to open or a query falls through to fallback, previously indexed documents are missing from results even though SQLite says they are indexed. Startup hydration then re-embeds the whole library (`ui/hydration.py`), causing long blocking starts. This directly undermines "retrieval never silently loses documents."
- Fix approach: Always load the fallback mirror at init (cheap relative to correctness) and merge rather than overwrite on save; or scope the mirror strictly as a write-through cache keyed by `doc_id` with explicit reconciliation against SQLite. Add a test that indexes with LanceDB, simulates an open failure, and asserts all documents remain searchable.

**10,000-chunk truncation and session-scoped BM25 silently drop evidence on larger corpora [Medium–High · open]**
- Issue: Scoped dense fallback requests `max(k, 10000)` results *before* filtering by `doc_id`, so a document whose chunks fall outside the global top 10,000 is returned as empty. The LanceDB BM25 fallback reads at most `limit(10000)` rows, and the in-memory BM25 path searches only whatever is in `_fallback_store`.
- Files: `retrieval/hybrid_retriever.py:601`, `retrieval/hybrid_retriever.py:638-649`
- Impact: Silent empty/partial answers for large libraries (single-doc filter or keyword fallback). Fails precisely at the scale where users most need document-scoped retrieval; no error is surfaced.
- Fix approach: Apply the `doc_id` filter before limiting (`where` clause in LanceDB, filtered vector scan in the fallback), and page/stream BM25 candidates instead of hard-limiting. Add a synthetic >10k-chunk test.

**Summarizer silently excludes visual evidence (figures/tables/charts) [Medium–High · open]**
- Issue: Visual analysis produces `EvidenceElement` rows stored in SQLite and indexed into LanceDB, but summaries are reconstructed exclusively from `chunks` (`doc_store.get_chunks_for_doc`). No summarizer code path reads `get_evidence_for_doc`, and `Document.num_chunks` counts text chunks only.
- Files: `core/summarizer.py:414-457`, `core/doc_store.py:583-600`, `ui/ingestion_service.py:252-259`, `ui/ingestion_service.py:295-298`
- Impact: The `tables_figures` profile and the product's "visual understanding" promise are not met for summaries: VLM descriptions of charts/diagrams never reach the synthesis prompt, and figure-only pages contribute nothing. Chat retrieval does surface them, so behavior is inconsistent between Chat and Summarizer.
- Fix approach: Merge evidence-element text into page reconstruction (tagged by kind/bbox), include it in the `tables_figures` profile at minimum, and assert in tests that a figure-only document yields non-empty evidence in the summary input.

**Context/history truncation is computed but never surfaced to the user [Low–Medium · open]**
- Issue: `PromptBudget` records `prompt_truncated`, `context_truncated`, and `history_truncated` in `AiModel.last_truncation_warning`, but the UI never reads or displays these flags, and chat turns do not persist them.
- Files: `core/prompt_budget.py:71-110`, `core/local_llm.py:136-159`, `core/local_llm.py:329`, `ui/views.py:400-496`
- Impact: Answers can be generated from silently truncated evidence with no indication that citations may be incomplete. Directly weakens the "evidence-grounded, verifiable" value proposition.
- Fix approach: Persist truncation metadata on the assistant turn and render a non-blocking notice ("context truncated; some pages were omitted") near the answer. Add a UI contract test for the flag.

**Summary session cache ignores the active model version [Low · open]**
- Issue: The UI short-circuits on `st.session_state[f"summary_{doc_id}_{profile}"]` before consulting the version-aware SQLite cache. Switching local↔cloud providers does not clear these keys, so a summary generated by the previous model is displayed as current.
- Files: `ui/views.py:560-588`, `core/summarizer.py:403-412`
- Impact: Misattributed summaries after a provider switch; the persistent cache is correct, but the session layer bypasses it. `Force re-generate` hides the problem rather than fixing it.
- Fix approach: Include `model_version` in the session key or validate the stored `model_version` before display; clear summary keys on provider change.

**PNG screenshots are sent to the VLM labelled `image/jpeg` [Low · open]**
- Issue: `analyze_image` base64-encodes PNG bytes but builds a `data:image/jpeg;base64,...` URL.
- Files: `providers/llama_cpp_provider.py:280-310`
- Impact: Depends on llama-server sniffing content; strict backends may reject the payload or mis-decode, producing placeholder visual descriptions (which are then filtered, hiding the failure).
- Fix approach: Emit `data:image/png;base64,` or detect the magic bytes and set the MIME accordingly; log decode failures at warning level.

## Security Considerations

**No integrity pinning for downloaded models, llama-server binaries, or container images [High · open]**
- Issue: `MODEL_REGISTRY` entries have no `sha256` key, so `expected_sha256` is always `None` and GGUF validation relies only on a minimum byte size plus the GGUF magic header. The llama-server archive download has no checksum verification, and `docker-compose.yml` references `ghcr.io/ggml-org/llama.cpp:server-cuda` by mutable tag rather than digest.
- Files: `setup.py:60-79`, `setup.py:327-340`, `setup.py:380-440`, `docker-compose.yml` (llama-server image)
- Impact: A compromised mirror, CDN, or tag could deliver arbitrary weights or a malicious server binary that then executes with user privileges and reads every document. This is the largest trust gap in an otherwise local-first design.
- Fix approach: Pin SHA-256 for every GGUF and archive, verify streaming hashes (not `read_bytes()`), pin the container image by digest, and fail closed on mismatch. Add tests with a deliberately wrong digest.

**First-run model downloads contradict the "zero external egress" promise [Medium · verification gap]**
- Issue: Docling layout/table models, the sentence-transformers MiniLM weights, and RapidOCR models are fetched on first use from HuggingFace (or the local HF cache) during ingestion/embedding. Only the GGUF/mmproj artifacts are pre-fetched by `setup.py`. No code path asserts that models are already present before serving a document.
- Files: `ingestion/docling_reader.py` (model init/converter), `retrieval/local_embedding.py` (model load), `setup.py:260-297` (precache helpers)
- Impact: A user who believes they are fully offline can trigger outbound requests with document-adjacent metadata on first ingest. In restricted networks this appears as an ingestion failure rather than a clear "models missing" error.
- Fix approach: Add a preflight check for all model caches; refuse ingestion with an actionable message if absent; document the one-time download step explicitly; optionally run with HF offline env vars once provisioned.

**Sanitizer is regex-based and has bypass classes [Low–Medium · verification gap]**
- Issue: `sanitize_display_markdown` strips a fixed tag list and rewrites links matching simple patterns. It does not handle angle-bracket destinations (`[x](<https://…>)`), entity-encoded schemes, or inline event attributes/`<svg>` payloads. Current risk is bounded because chat snippets are rendered with `st.markdown` default escaping and `unsafe_allow_html` is used only with locally-constructed HTML.
- Files: `ui/sanitizer.py:1-120`, `ui/views.py:469-470`, `ui/components.py` (static HTML)
- Impact: Any future use of `unsafe_allow_html` with model/PDF-derived text, or a missed Markdown destination form, becomes a clickable egress or script-injection vector. Tests cover only the currently known patterns.
- Fix approach: Move to an allowlist renderer (e.g., parse Markdown to AST and re-emit safe nodes, or use a sanitizer library), and add regression tests for angle-bracket links, entities, `onerror`/`onload`, and `<svg>`.

**Citation validation checks rank bounds, not evidential support [Medium · verification gap]**
- Issue: The validator extracts `[E#]`, rejects out-of-range ranks, and detects abstention plus a keyword list of adversarial directives. It never checks that the cited snippet actually supports the claim, so a model that cites `[E1]` for every sentence achieves 100% measured precision.
- Files: `core/citation_validator.py:30-60`, `core/citation_validator.py:200-240`, `tests/test_citation_validator.py`
- Impact: UI labels such as "Verified" overstate grounding; hallucinated content with valid-looking citations passes. The 95% precision target is measured against a weaker definition than users assume.
- Fix approach: Add claim-to-snippet entailment scoring (even a lightweight lexical/embedding check) and mark citations as "verified" only when supporting text overlaps; rename the current metric to "citation validity" in docs and UI.

**Prompt-injection defense is a fixed keyword list [Medium · verification gap]**
- Issue: `KNOWN_ADVERSARIAL_DIRECTIVES` matches a small set of phrases; document text is wrapped in `<document_context>` and XML-ish tags are escaped, but paraphrased or non-English instructions pass through.
- Files: `core/citation_validator.py:34-47`, `core/prompt_budget.py:70-130`
- Impact: A malicious PDF can still steer answers; detection is easily bypassed. The isolation helps, but the "injection detected" signal is not a reliable security control.
- Fix approach: Treat all document text as untrusted by instruction (strong system contract), add output-side checks (e.g., refusal to follow embedded commands, citation-required answers), and document that keyword detection is advisory only.

**No authentication; safety depends entirely on loopback binding [Low · open]**
- Issue: Streamlit has no auth layer. Docker publishes `127.0.0.1:8501`, which is safe by default, but any user changing the host binding exposes full document access and cloud API key entry to the network.
- Files: `docker-compose.yml`, `.streamlit/config.toml`, `main.py`
- Impact: Accidental LAN exposure grants read access to all indexed documents and the settings page.
- Fix approach: Document the single-user assumption prominently, refuse non-loopback binds unless an explicit flag is set, and consider Streamlit's built-in auth/OIDC for shared deployments.

**Untrusted-PDF resource amplification [Medium · open]**
- Issue: The pixel guard computes a scale to fit 2048×2048, then clamps zoom to a minimum of 0.5. For oversized PDF page geometry, 0.5 zoom can still yield tens of millions of pixels per page; four OCR workers plus VLM crops can allocate hundreds of MB, and OCR runs over every low-text page with no time budget.
- Files: `ingestion/ocr_fallback.py:108-125`, `ingestion/visual_analyzer.py:185-200`
- Impact: A crafted or simply enormous PDF can exhaust RAM/CPU during ingestion (distinct from the VRAM gate) or stall the UI for many minutes. The 50 MB/500-page caps do not bound rendered pixels or OCR time.
- Fix approach: Enforce a hard post-clamp pixel budget (skip/reject pages above it), cap total OCR pages/time per document, and add a memory guard around `get_pixmap`.

**Cloud credentials live in a process-wide environment and container env [Low · open]**
- Issue: Docker Compose forwards `GROQ_API_KEY`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY` into the container environment; the app also stores keys in `st.session_state` and passes keys to LiteLLM. Scrubbing exists for error paths, but environment exposure and process lifetime are not bounded.
- Files: `docker-compose.yml`, `providers/litellm_provider.py`, `ui/views.py:727-880`, `ui/session_state.py`
- Impact: Any child process or crash dump can inherit keys; multi-user Streamlit sessions share one server process.
- Fix approach: Prefer `st.secrets`/OS keyring over environment for cloud keys, allow clearing keys from the UI, and document that cloud mode is single-user.

## Performance Bottlenecks

**Fallback index rewrites and duplicates every vector [Medium · open]**
- Issue: `_save_fallback_store` serializes all documents and vectors to JSON on every `index_chunks` and `delete_document`. When LanceDB is active, the fallback store still holds a second in-memory copy of every embedding indexed this session.
- Files: `retrieval/hybrid_retriever.py:252-280`, `retrieval/hybrid_retriever.py:481-490`, `retrieval/hybrid_retriever.py:547-554`
- Impact: O(N) write amplification per upload/delete and ~1.5 KB RAM per chunk duplicated (≈75 MB per 50k chunks). Batch ingestion becomes progressively slower.
- Fix approach: Make the mirror append-only or delete-on-demand, write once per ingestion transaction, and avoid holding duplicate vectors when LanceDB is healthy.

**Startup hydration re-embeds the entire library [Medium · open]**
- Issue: On first load, `hydrate_startup_state` verifies LanceDB coverage per document and re-chunks+re-embeds any document whose vectors are missing. This runs synchronously before the UI is usable, and the fallback divergence above makes it trigger more often than intended.
- Files: `ui/hydration.py:1-100`, `main.py:100-130`
- Impact: Minute-scale blank/frozen startup for large libraries, with no progress indication or opt-out.
- Fix approach: Reconcile from SQLite chunk rows in batches with a progress bar, run in the background, and fix the fallback mirror so repair is exceptional rather than routine.

**BM25 fallback is O(N) per query and FTS index is rebuilt on every ingest [Medium · open]**
- Issue: The Python BM25 path tokenizes and scores every candidate on each query; the LanceDB FTS index is recreated with `create_fts_index(replace=True)` after ingestion batches, and failures are logged at `debug` only, silently routing every query to the slow path.
- Files: `retrieval/hybrid_retriever.py:617-625`, `retrieval/hybrid_retriever.py:627-696`, `retrieval/hybrid_retriever.py:440-476`
- Impact: Query latency grows linearly with corpus size and FTS unavailability is invisible; ingestion pauses grow with corpus size.
- Fix approach: Build/refresh FTS incrementally, warn once when FTS is unavailable (and surface it in Settings), and cap or index the BM25 candidate set.

**Sequential map-reduce summarization blocks the UI with no cancellation [Medium · open]**
- Issue: Long documents are split into sequential chunks, each requiring a generation call under `InferenceGate`. There is no cancel button, no overall deadline, and no incremental partial output. A 500-page document can occupy the gate for a very long time.
- Files: `core/summarizer.py:180-330`, `core/local_llm.py:24-35`, `ui/views.py:564-578`
- Impact: Users cannot stop a runaway summary; chat is blocked in the same process; a failed mid-way run discards all work already done.
- Fix approach: Persist completed map segments, support cancellation between segments, and surface progress with an elapsed estimate.

**Full OCR pass over scanned PDFs without a time budget [Medium · open]**
- Issue: Every page with fewer than 50 characters is rendered at up to 150 DPI and OCR'd; with four workers and a shared engine lock, a 500-page scan is a long CPU-bound operation with no progress or abort.
- Files: `ingestion/ocr_fallback.py:80-200`
- Impact: Multi-minute ingestion, high CPU, and UI stalls; users may retry uploads, multiplying work.
- Fix approach: Add per-document page/time budgets, stream progress to the status widget, and expose "text-only (skip OCR)" ingestion.

**Token estimation uses a flat ~4 chars/token heuristic [Low–Medium · open]**
- Issue: `estimate_tokens` divides character counts by four, which underestimates CJK, code, and table-heavy text. Budgets derived from it can exceed the configured context window.
- Files: `core/prompt_budget.py:40-65`, `core/summarizer.py:180-220`
- Impact: Context overflow errors or server-side truncation at the llama-server boundary, producing incomplete answers with no warning.
- Fix approach: Use a model-aware tokenizer for the active GGUF (or a conservative per-script ratio), and keep a hard backstop by measuring the assembled prompt.

## Fragile Areas

**Delete/purge UI paths have no error boundary and no confirmation [Medium · open]**
- Issue: Library "Delete" and "Purge All" call `LifecycleService` directly with no `try/except`. Vector-deletion failures raise, surfacing as a Streamlit traceback; a `None` retriever silently skips vector deletion and proceeds to delete SQLite, orphaning vectors that hydration can later resurrect. Single-document delete is one click, with no confirm dialog.
- Files: `ui/views.py:695-725`, `ui/lifecycle_service.py:44-70`, `ui/lifecycle_service.py:100-130`, `ui/hydration.py`
- Impact: Inconsistent failure UX, and a recoverable inconsistency can become a resurrected "deleted" document. Accidental deletion of a single document is easy and irreversible.
- Fix approach: Wrap lifecycle calls with `st.error` + retry guidance, treat a missing retriever as a hard preflight failure rather than a skip, and add a confirmation step for single-document deletion.

**71 broad `except Exception` blocks, several silent [Medium · open]**
- Issue: `except Exception` appears across `core/`, `ingestion/`, `retrieval/`, `providers/`, and `ui/`. Some handlers `pass` without logging (`retrieval/hybrid_retriever.py:299-300,310-311,469-470,581-582`, `ui/session_state.py:24,30,44`) or log at `debug` for consequential failures (FTS creation, BM25 source read).
- Files: `retrieval/hybrid_retriever.py`, `ui/ingestion_service.py`, `ui/hydration.py`, `ui/session_state.py`, `ingestion/pdf_reader.py:38`
- Impact: Degraded retrieval, missing OCR/VLM output, and failed repairs look like normal operation. Combined with no logging config, failures are effectively invisible in production.
- Fix approach: Narrow exception types at integration boundaries, log warnings with context on every fallback, and reserve silent handling for genuinely optional cleanup. Enable Ruff `BLE`/`B` rules to catch blind excepts.

**Process-local inference lock with multi-session/multi-tab access [Medium · open]**
- Issue: `InferenceGate` is a process-level `RLock`; it coordinates Streamlit sessions in one process but not multiple processes. Separately, each browser session constructs its own `HybridRetriever`/LanceDB connection, so concurrent sessions can write to the same LanceDB path.
- Files: `core/local_llm.py:24-60`, `main.py:100-130`, `ui/views.py:200-260`
- Impact: Multi-tab use can produce `Commit conflict`/lock errors in LanceDB, and a second process (or `start.py` interop) bypasses the VRAM guard entirely. Streaming generators abandoned by a disconnected client may hold the gate until garbage collection.
- Fix approach: Add OS-level or server-side serialization for GPU work, use one shared retriever per process, and release the gate in a `finally` that is guaranteed even when the stream is not fully consumed.

**Startup module-level side effects and heavy imports [Low–Medium · open]**
- Issue: `main.py` constructs `DocStore`, runs hydration, and syncs cloud state during reruns; `ui/views.py` constructs `AiModel()` at module import. `retrieval/local_embedding.py` mutates global env vars at import. Any import failure surfaces as a blank Streamlit error page.
- Files: `main.py:1-130`, `ui/views.py:1-60`, `retrieval/local_embedding.py:1-40`
- Impact: Hard to test (imports have side effects), slow cold start, and exception-prone startup on partially provisioned machines.
- Fix approach: Move construction behind cached factories (`@st.cache_resource`), lazy-load heavy models, and make startup failures render actionable guidance.

**Download path buffers entire model in memory when hash verification is enabled [Low · open]**
- Issue: When `expected_sha256` is finally supplied, verification computes `hashlib.sha256(temp_path.read_bytes())`, loading the full multi-GB GGUF into RAM despite the streaming download.
- Files: `setup.py:236-241`
- Impact: Latent OOM on low-RAM machines as soon as checksums are added (the fix for the high-severity supply-chain issue).
- Fix approach: Stream the file in 1 MB blocks into the hash object before the atomic rename.

**LanceDB FTS failures are only debug-logged [Low–Medium · open]**
- Issue: `create_fts_index` swallows exceptions at `debug`; `search_fts` falls back silently to BM25. There is no health indicator for keyword search.
- Files: `retrieval/hybrid_retriever.py:617-625`, `retrieval/hybrid_retriever.py:717-750`, `ui/views.py` Settings health panel
- Impact: Users see degraded retrieval quality with no signal; operators cannot distinguish "no matches" from "index unavailable."
- Fix approach: Record FTS status on the retriever, expose it in Settings, and warn once per session when search degrades.

## Scaling Limits

**Chunk-count ceiling for document-scoped and keyword fallback [Medium · open]**
- Current capacity: Works as designed up to ~10,000 chunks; typical 500-page documents yield 1,000–2,500 chunks, so a library of roughly 5–10 documents approaches the limit.
- Limit: Scoped fallback truncation and BM25 row limits at 10k chunks (`retrieval/hybrid_retriever.py:601,641`).
- Scaling path: Filter before limiting, paginate BM25, and add a >10k-chunk regression test.

**Single-GPU serialization bounds throughput [Medium · by design, but unmitigated]**
- Current capacity: One generation at a time under `InferenceGate`; `ngl=28`, `ctx=4096` for a 2B Q4 model on 4 GB VRAM.
- Limit: Summarization of long documents monopolizes the GPU for minutes; concurrent users queue or time out at the 60 s gate timeout. No queue position or ETA is shown.
- Scaling path: Segment-level caching/cancellation, smaller summary chunks, and a visible job queue with cancel. Consider a second worker only with an explicit VRAM budget.

**SQLite write contention across sessions [Low–Medium · open]**
- Current capacity: `timeout=5.0`/`busy_timeout=5000` with WAL per connection.
- Limit: Concurrent ingestion + delete across tabs can exceed the 5 s busy timeout; there is no retry/backoff, so the operation fails and is reported as an ingestion error.
- Scaling path: Add bounded retry with jitter around write transactions or serialize writes behind a process-level lock (single-user app).

**Hard upload caps [Low · open]**
- Current capacity: 50 MB and 500 pages (`ingestion/upload_validation.py`, `.streamlit/config.toml`).
- Limit: Larger or denser documents are rejected outright; scans at the page cap can still take many minutes of OCR.
- Scaling path: Keep caps but add a clear pre-flight estimate (page count, scanned-page ratio) and a documented path for splitting documents.

## Dependencies at Risk

**Unpinned runtime dependencies are the default install path [High · open]**
- Issue: `requirements.txt` uses only lower bounds for core libraries (`docling>=2.0.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`, `pymupdf`, `pillow`, `pyarrow`). `setup.py` defaults to `use_lockfile=False`, and the `Dockerfile` installs `requirements.txt`, so deployments do not use the pinned `requirements-lock.txt`.
- Files: `requirements.txt`, `requirements-lock.txt`, `setup.py:578-600`, `Dockerfile`
- Impact: Any upstream breaking or malicious release can enter a fresh install or image build without review, defeating the reproducibility the lockfile was created for.
- Fix approach: Make the lockfile the default everywhere (including Docker), add hash-checking mode, and provide an explicit `--dev-unpinned` escape hatch.

**Docling / LanceDB / LiteLLM move quickly [Medium · open]**
- Issue: These are the heaviest and fastest-changing dependencies; the lock pins Docling 2.138.0, but the declared floor is 2.0.0, spanning large API/behavior changes (layout models, table extraction, FTS support).
- Files: `requirements-lock.txt`, `requirements.txt`, `retrieval/hybrid_retriever.py`, `ingestion/docling_reader.py`
- Impact: Silent extraction-quality regressions and API drift on upgrade; Docling also pulls large model assets.
- Fix approach: Pin and test upgrades behind an extraction-quality fixture set; isolate Docling behind the existing reader adapter so replacements are contained.

**Dual OCR packages branch on Python version, with the 3.13 path untested [Medium · verification gap]**
- Issue: `rapidocr-onnxruntime` is used below 3.13 and `rapidocr` at 3.13+, but CI runs only Python 3.11 and the lockfile targets 3.11.
- Files: `requirements.txt`, `.github/workflows/ci.yml`, `ingestion/ocr_fallback.py`
- Impact: Python 3.13 users get a different OCR stack that has never run in CI; failures surface only at ingest time.
- Fix approach: Add a 3.13 CI job (at least import + OCR smoke test with a fixture image) or constrain `requires-python` to <3.13.

**Container base/image drift [Medium · open]**
- Issue: The CUDA llama-server image is pulled by mutable tag; the app image is based on `python:3.11-slim-bookworm` without a digest pin.
- Files: `docker-compose.yml`, `Dockerfile`
- Impact: Non-reproducible builds and unreviewed upstream changes, including CUDA/runtime breakage.
- Fix approach: Pin image digests and update them deliberately with a smoke test.

**Test tooling version skew [Low · open]**
- Issue: CI pins nothing for pytest (`>=8.3.0`), and local artifacts show a Python 3.13/pytest 9 environment while CI/lock target 3.11.
- Files: `requirements.txt`, `requirements-test.txt`, `.github/workflows/ci.yml`
- Impact: Tests may pass locally and fail in CI (or vice versa); warning-as-error behavior differs.
- Fix approach: Pin test dependencies in the lockfile and align the local interpreter with CI.

## Missing Critical Features

**No cancellation or stop control for generation/summarization [High · missing]**
- Problem: Once a chat response or summary starts, the user cannot stop it; the UI thread is blocked and the gate remains held.
- Blocks: Usable long-document workflows and recovery from a wrong profile/model choice without waiting for completion.

**Visual evidence is not part of summaries [High · missing]**
- Problem: VLM descriptions of figures/tables are retrievable in Chat but absent from all summary profiles, so the `tables_figures` profile cannot summarize charts or diagrams.
- Blocks: The core "visual understanding" value for summarization and any evaluation of figure coverage. (See Known Bugs for the mechanism.)

**No index backup/restore or portable export [Medium · missing]**
- Problem: There is no way to export the document catalog/vectors or restore after a failed purge. Only individual summaries can be downloaded as Markdown.
- Blocks: Migration between machines and recovery from accidental purge beyond re-ingesting everything.

**No automatic llama-server health recovery [Medium · missing]**
- Problem: If the local server dies or the model fails to load, the UI reports unavailable but does not restart or offer a one-click restart; `start.py` supervises only the process it spawned.
- Blocks: Unattended local use; users must drop to a terminal.

**No OCR confidence gating or low-quality-text flagging [Medium · missing]**
- Problem: OCR text is accepted regardless of confidence, and pages are not marked "low-confidence"; retrieval treats it as equal evidence.
- Files: `ingestion/ocr_fallback.py` (scores discarded), `core/models.py:75-88` (`Page` has no quality field)
- Blocks: Users cannot judge when an answer rests on poor OCR, and citations can point to garbled text.

**No retry/partial reprocess for failed documents [Medium · missing]**
- Problem: Failed ingestion leaves no per-page retry path; the only remedy is re-uploading the whole file, and a mid-document VLM/OCR failure is not recoverable selectively.
- Blocks: Efficient recovery for large documents with a few bad pages.

**No evaluation harness in CI [Medium · missing]**
- Problem: Retrieval/summarization quality scripts and fixtures exist, but CI runs only lint + unit tests; no golden-set regression gate protects quality claims (citation precision, retrieval recall).
- Blocks: Safe model/prompt/dependency upgrades and objective tracking of the 95% precision target.

**No encryption at rest [Low · missing]**
- Problem: SQLite, LanceDB, and the extraction cache store document text unencrypted; privacy is enforced only by locality and deletion.
- Blocks: Threat model coverage for shared/lost laptops, which the "privacy-respecting" positioning implies.

## Test Coverage Gaps

**UI views are untested [High · open]**
- What's not tested: None of `render_chat_view`, `render_summarizer_view`, `render_library_view`, or `render_settings_view` is executed by tests; there is no `streamlit.testing.v1.AppTest` usage. The 880-line `ui/views.py` is covered only indirectly through helper contracts.
- Files: `ui/views.py:1-880`, `tests/test_main_ui.py`, `tests/test_ui_smoke.py`
- Risk: Regressions in citation rendering, delete/purge flows, summary cache behavior, and cloud-key handling ship undetected.
- Priority: High.

**Ingestion happy path is only tested with an empty document [High · open]**
- What's not tested: The full Docling → OCR → visual analysis → embedding → SQLite → LanceDB transaction on a multi-page document, including `num_chunks`, evidence persistence, and failure recovery. Existing tests use a blank PDF that produces zero chunks.
- Files: `tests/test_main_ui.py:366`, `tests/test_main_ui.py:577`, `ui/ingestion_service.py:1-352`
- Risk: The primary user workflow can break while all tests pass.
- Priority: High.

**No real-backend integration tests [High · open]**
- What's not tested: Real llama-server streaming/SSE, real LanceDB FTS, real Docling conversion, real RapidOCR, and real VLM inference are all mocked or absent. `docs/AUDIT_SUMMARY.md` marks live checks as UNTESTED.
- Files: `tests/conftest.py` (mocks `SentenceTransformer`, `Groq`), `tests/test_hybrid_retriever.py`, `docs/AUDIT_SUMMARY.md`
- Risk: Contract drift with llama.cpp payloads (e.g., the `image/jpeg` mismatch), FTS API changes, and model-loading failures are invisible to CI.
- Priority: High.

**Installer/supply-chain code is untested [Medium · open]**
- What's not tested: `download_file_with_progress` (mirror fallback, size/hash validation, atomic rename), `safe_extract_archive`, and llama-server installation. No fixture archive or fake HTTP server is used.
- Files: `setup.py:157-260`, `setup.py:380-440`, `tests/test_setup_llama.py`
- Risk: The security-sensitive install path (now slated for checksum enforcement) has no regression protection.
- Priority: Medium.

**Fallback divergence and scale boundaries are untested [Medium · open]**
- What's not tested: Mirror behavior when LanceDB opens successfully in one session and fails in the next; >10k-chunk scoped search; BM25 source selection; FTS-index failure fallback.
- Files: `retrieval/hybrid_retriever.py`, `tests/test_hybrid_retriever.py`
- Risk: Silent evidence loss at scale and after backend failures.
- Priority: Medium.

**Sanitizer edge cases are untested [Medium · open]**
- What's not tested: Angle-bracket link destinations, HTML entities in schemes, event-handler attributes, and `<svg>` payloads beyond `use href`.
- Files: `tests/test_sanitizer.py`, `ui/sanitizer.py`
- Risk: Egress/script-injection bypasses if rendering assumptions change.
- Priority: Medium.

**Platform matrix is absent [Medium · open]**
- What's not tested: Windows (the primary supported OS), PowerShell launcher behavior, path handling, and Python 3.13.
- Files: `.github/workflows/ci.yml`, `start.py`, `setup.py`
- Risk: Windows-only breakage in file locks, subprocess flags, and Unicode paths reaches users first.
- Priority: Medium.

**No coverage measurement or security scanning [Low–Medium · open]**
- What's not tested: There is no coverage threshold, no `pip-audit`/dependency vulnerability scan, and no static security rule set.
- Files: `.github/workflows/ci.yml`, `pyproject.toml`
- Risk: Coverage erosion and known-vulnerable dependencies go unnoticed.
- Priority: Medium (add `coverage` reporting and `pip-audit` to CI).

---

*Concerns audit: 2026-10-21*
