# Codebase Concerns

**Analysis Date:** 2026-10-12

## Review Fix Status — Phase 02 (Local Inference Pipeline)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/02-local-inference-pipeline/02-REVIEW.md` are **FIXED** per `02-REVIEW-FIX.md` and verified against current source:

- **CR-01 XML boundary escape — FIXED.** `sanitize_xml_boundary()` exists in `prompt_budget.py:25` and is applied to both user prompt (`prompt_budget.py:83`) and document context (`prompt_budget.py:94`). Test: `tests/test_prompt_budget.py::test_sanitize_xml_boundary`.
- **CR-02 unbounded user prompt — FIXED.** `assemble_grounded_messages` truncates oversized prompts; `local_llm.py` passes the bounded user turn to `stream_text` instead of the raw prompt. Test: `tests/test_prompt_budget.py::test_assemble_grounded_messages_truncates_huge_user_prompt`.
- **CR-03 unguarded `st.write_stream` — FIXED.** `main.py` wraps generator creation + `st.write_stream` in `try/except Exception`, renders `st.error`, and appends an `[interrupted]` history entry instead of crashing.
- **WR-01 stale provider lock-in — FIXED.** `local_llm.py` `check_health()` re-runs `_detect_provider()` when the current provider is unhealthy (dynamic self-healing). Test: `tests/test_local_llm.py` dynamic-recovery case. Note: re-probe only fires on unhealthy status, so a healthy-but-wrong (Groq fallback while llama-server later appears) session stays on Groq until health degrades — residual stickiness, see Fragile Areas.
- **WR-02 missing `close()` lifecycle — FIXED.** `model_provider.py` defines `close()` + context-manager protocol; `groq_provider.py` and `local_llm.py` implement it.
- **WR-03 Groq error encapsulation — FIXED.** `groq_provider.py` wraps SDK calls in `try/except Exception` → `RuntimeError("Groq API error: ...")`.
- **WR-04 `ProviderCapabilities` validation — FIXED.** `model_provider.py` constrains `model_name` (`min_length=1`) and `context_window` (`gt=0`).
- **WR-05 dual health probes — FIXED.** `main.py` evaluates provider health once per lifecycle block and reuses it for input gating; no second probe per rerun.
- **WR-06 empty image bytes — FIXED.** `llama_cpp_provider.py` raises `ValueError("image_bytes cannot be empty.")`.
- **IN-01/02/03 — FIXED.** Health-string formatting cleaned; `isinstance(content, str)` guard in `local_llm.py`; temperature clamped `max(0.0, min(2.0, ...))` in `llama_cpp_provider.py` and `groq_provider.py`.

## Review Fix Status — Phase 03 (Multimodal Ingestion & Conditional OCR)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/03-multimodal-ingestion-conditional-ocr/03-REVIEW.md` are **FIXED** per `03-REVIEW-FIX.md` and verified against current source:

- **CR-01 uninitialized `st.session_state.ai_model` — FIXED (variant).** The upload loop uses `getattr(st.session_state, "ai_model", None) or ai_model` (`main.py`) so cold-start/pre-session access can no longer raise `AttributeError` or silently disable VLM descriptions.
- **CR-02 missing FK pragma — FIXED.** `doc_store.py` executes `PRAGMA foreign_keys = ON;` in `_connect()`, so `evidence_elements(doc_id) ON DELETE CASCADE` is enforced.
- **CR-03 table prepending destroys reading order — FIXED.** `docling_reader.py` interleaves tables by document/bbox order instead of prepending; fallback aggregation is order-preserving.
- **WR-01 crop-failure misattribution — FIXED.** `visual_analyzer.py` emits `"[Visual element: cropping failed, image unavailable]"` distinct from the vision-unsupported path.
- **WR-02 unclipped bboxes — FIXED.** `visual_analyzer.py` clamps zoom (`max(0.5, ...)`), validates positive area, and intersects with `page.rect`, raising `ValueError` on empty intersection.
- **WR-03 empty bytes to ONNX — FIXED.** `ocr_fallback.py` guards `if not image_data: return "", 0.0` before the recognizer call.
- **WR-04 OCR discards partial text — FIXED.** `ocr_fallback.py` retains pre-existing digital chunks when OCR yields empty text.
- **WR-05 `EvidenceElement.doc_id` validation — FIXED.** `models.py` adds the `doc_`-prefix validator and `element_id` `min_length=1`, consistent with `Document`/`Chunk`.
- **WR-06 raw `print()` in DoclingReader — FIXED.** `docling_reader.py` uses `logging.getLogger(__name__)` (`logger.info/warning/error`).
- **IN-01 monotonic chunk ids — FIXED.** `ocr_fallback.py` uses a dedicated incrementing `chunk_idx` (`{sha12}_p{page}_{idx:04d}`).
- **IN-02 char offsets — FIXED for new extractors.** `docling_reader.py` and `ocr_fallback.py` populate `char_start`/`char_end` (asserted in `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`). **Residual:** the legacy `pdf_reader.py` path still does not populate offsets — see Tech Debt.
- **IN-03 dpi/zoom clamping — FIXED.** `ocr_fallback.py` (`eff_dpi = max(72, int(dpi))`), `visual_analyzer.py` (`zoom_clamped = max(0.5, float(zoom))`).

## Review Fix Status — Phase 04 (Persistent Hybrid Retrieval)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/04-persistent-hybrid-retrieval/04-REVIEW.md` are **FIXED** per `04-REVIEW-FIX.md` and verified against current source:

- **CR-01 HybridRetriever never wired into `main.py` — FIXED.** `main.py` imports `HybridRetriever`; `st.session_state.hybrid_retriever` is initialised, populated on fresh upload, restored on restart dedup-hit, closed + nulled on Clear All, and used as the primary retriever in the chat loop.
- **CR-02 redundant dual-query divergence — FIXED (primary path).** `main.py` contextualises the query once, executes one `search_hybrid` producing a single canonical `RetrievalResult`, displays `source_labels()` from it, and passes the same instance via `retrieval_result=`; `local_llm.py:121-122` consumes it without re-searching. **Residual:** the `retrieval_result=None` fallback inside `local_llm.py:123-159` still re-searches with its own contextualised query, and the `LocalEmbedding` (non-hybrid) chat branch still uses raw-vector `search` + filename-only chips — see Fragile Areas.
- **CR-03 LanceDB filter injection — FIXED.** Single-quote escaping (`replace("'", "''")`) applied at all three interpolation sites: `has_document` (`hybrid_retriever.py:219`), fallback `merge_insert` delete path (`hybrid_retriever.py:328`), and `delete_document` (`hybrid_retriever.py:357`). Regression test coverage in `tests/test_hybrid_retriever.py` per `04-REVIEW-FIX.md`.
- **WR-01 fallback dedup — FIXED.** `hybrid_retriever.py:267-280` replaces existing `chunk_id` entries in-place instead of appending.
- **WR-02 post-restart BM25 fallback — FIXED.** `hybrid_retriever.py:424-431` reads chunk rows back from `self._table` (capped at 10 000 rows) when `_fallback_store` is empty. **Residual cap:** corpora above 10 000 rows silently truncate the BM25 candidate pool — see Scaling Limits.
- **WR-03 quadratic BM25 df — FIXED.** `hybrid_retriever.py:449-452` precomputes `df_map` once outside the document loop (O(N·|Q|)).
- **WR-04 BBox serialization — FIXED.** `_save_fallback_store` (`hybrid_retriever.py:168-176`) converts `BBox` / `model_dump`-capable objects via `model_dump()`. Note: only the top-level `bbox` key is normalised; other future non-primitive metadata values would still break `json.dump` — see Fragile Areas.
- **WR-05 missing lifecycle — FIXED.** `HybridRetriever.close()` + `__enter__`/`__exit__` exist (`hybrid_retriever.py:149-160`). **Residual:** `close()` in LanceDB mode drops handles without an explicit flush/`_save_fallback_store`, and nothing in `main.py` calls it on normal session end — only Clear All (`main.py:137-139`).
- **WR-06 `EvidenceSnippet.doc_id` validation — FIXED.** `models.py:163-167` adds the `doc_`-prefix `@model_validator`, consistent with `Document`/`Chunk`/`EvidenceElement`.
- **IN-01 citation chip fallback — FIXED.** `models.py:190` (`formatted_evidence` falls back to `doc_id`) and `models.py:200` (`source_labels` falls back to `Page {page}`).
- **IN-02 embedding setter — FIXED.** `HybridRetriever.set_embedding_fn` exists (`hybrid_retriever.py:143-147`), including propagation to `_fallback_store._embedding_fn`.
- **IN-03 unstripped evidence — FIXED.** `models.py:192` uses `s.content.strip()`.

## Review Fix Status — Phase 05 (Grounded Summarization & QA)

All 3 Criticals, 10 Warnings, 5 Info items from `.planning/phases/05-grounded-summarization-and-qa/05-REVIEW.md` are **FIXED** per `05-REVIEW-FIX.md`. Re-verified against current source on 2026-10-12 (all line-level claims below confirmed via grep):

- **CR-01 `current_model._provider` typo — FIXED.** `main.py:255` accesses `current_model.provider` rather than `_provider`, unblocking PDF visual ingestion; covered by `tests/test_main_ui.py::test_ai_model_provider_attribute_contract`.
- **CR-02 `page_text=None` crash — FIXED.** `summarizer.py:180,199-200,380-384` guards `(getattr(p, "page_text", None) or "").strip()` in `_bundle_pages` and `_format_page_batch`, filters `valid_pages` on non-empty text, and enriches missing text from `doc_store.get_chunks_for_doc(doc_id)`.
- **CR-03 empty response grounded pass — FIXED.** `citation_validator.py:106-108` evaluates empty responses as `is_valid=False, precision=0.0, message="Empty response: no grounded content generated."`; verified by `tests/test_citation_validator.py::test_validate_citations_empty_response`.
- **WR-01 page provenance fabrication — FIXED.** `summarizer.py` preserves `page_refs = []` when no page citations are emitted; `main.py:622` renders `st.caption("ℹ️ *No explicit page references cited in summary.*")` instead of fabricating source pages. Test: `test_no_page_citations_yields_empty_list_without_fabrication` (`tests/test_summarizer.py:286`).
- **WR-02 summary cache model version invalidation — FIXED (partial, see residuals).** `DocStore.get_summary` takes optional `model_version` (`doc_store.py:469-497`) and returns `None` on version mismatch; wired in `summarizer.py:328-332`. **Residual:** `CONFIG_VERSION`/chunking/estimator changes still not keyed — see Phase 05 residuals.
- **WR-03 fast-path prompt-injection guard — FIXED.** `summarizer.py:110,130,219` carries non-execution directives in single-pass user prompt and profile instructions.
- **WR-04 `AiModel.validate_response` bypass & singleton state — FIXED (wiring) / DOCUMENTED (leak).** `main.py:484` invokes `ai_model.validate_response(full_response, retrieval_res)`; `local_llm.py:202` documents the process-singleton scoping caveat. **Residual:** `last_retrieval_result` (`local_llm.py:44,171,207`) is still shared process-wide — see residuals.
- **WR-05 Clear All summary session purge — FIXED.** `main.py:147` purges `summary_*` keys (`if k.startswith("summary_")`); verified by `tests/test_main_ui.py::test_clear_all_purges_summary_keys`.
- **WR-06 unbounded page references — FIXED.** `summarizer.py:135-148` clamps `extract_page_references` with `max_page: int | None = None`; verified by `tests/test_summarizer.py::test_extract_page_references_clamped`.
- **WR-07 abstention matcher over-firing — FIXED.** `citation_validator.py:18-28` tightens `CANONICAL_ABSTENTION_MARKERS` to require complete phrases; `citation_validator.py:78` matches against lowered text.
- **WR-08 empty document summarization — FIXED.** `summarizer.py:382` raises `ValueError("No extractable text found ...")` before inference or persistence; verified by `tests/test_summarizer.py` (`pytest.raises(ValueError, match="No extractable text found")`, `tests/test_summarizer.py:269`).
- **WR-09 XML boundary case/whitespace bypass — FIXED.** `prompt_budget.py` uses case-insensitive regex sanitization; verified by `tests/test_prompt_budget.py::test_sanitize_xml_boundary_case_and_whitespace`.
- **WR-10 mock fidelity gap — FIXED (partial, see residuals).** `MockSummarizerProvider` dynamically echoes batch page ranges and asserts full preservation of `[1, 2, 3, 4, 5]`. **Residual:** `test_main_ui.py` still asserts string formatting, never Streamlit widgets — see residuals.
- **IN-01 through IN-05 — FIXED/RESOLVED.** Unique-rank precision metric preserved per D2 design lock (IN-01); abstention message clarifies unexpected citations (IN-02); token thresholds documented with context window budget explanations (IN-03); doc_store cascade notes recorded (IN-04, still open — see residuals); case-insensitive `[e1]` regex compiled (`citation_validator.py:16`, `re.IGNORECASE`) (IN-05).

## Phase 05 Residuals (partial fixes — ordered by severity)

**Summary cache ignores pipeline version (WR-02 remainder):**
- Issue: cache key is now `(sha256, profile, model_version)` (`doc_store.py:469-497`, `summarizer.py:328-332`), but `CONFIG_VERSION` (`models.py`), chunking parameters (`chunk_size=1000, chunk_overlap=200`), and the `estimate_tokens` heuristic are still not part of the key. Same bytes re-chunked under a bumped pipeline still hit the stale row with a "cached" badge.
- Files: `doc_store.py:469-497`, `summarizer.py:328-332`, `models.py` (`CONFIG_VERSION`)
- Impact: silent stale summaries after any chunking/pipeline upgrade — the exact class WR-02 was meant to kill, narrowed to model upgrades only.
- Fix approach: add a `pipeline_version`/`config_version` column to the summaries table and include it in the `get_summary` lookup predicate, same shape as the `model_version` fix.

**Singleton `AiModel` retrieval state still shared process-wide (WR-04 remainder):**
- Issue: wiring is fixed (`main.py:484` passes the explicit result), but `last_retrieval_result` (`local_llm.py:44,171,207`) and the `@st.cache_resource` singleton loader remain; any future caller using the `retrieval_result=None` fallback validates against whoever queried last. Documented in the docstring (`local_llm.py:202`), not eliminated.
- Files: `local_llm.py:44,157-158,171,202-207`, `main.py:59-67`-area cached loader
- Impact: evidence cross-contamination on a shared server the moment a second call site uses the fallback; tests even enshrine the fallback (`tests/test_citation_validator.py:148-161`).
- Fix approach: scope retrieval state per-call (return it alongside the stream) or require explicit `retrieval_result` and raise when absent.

**`pages`/`chunks` tables still lack FK cascade (IN-04, deferred):**
- Issue: only `evidence_elements` and summaries cascade; `delete_document` orphans `pages`/`chunks` rows. `doc_store.py:68,85` show cascade on two tables; `pages`/`chunks` DDL has none. Explicitly deferred to Phase 6+/future cleanup per `05-REVIEW-FIX.md`.
- Files: `doc_store.py` (DDL + `delete_document`)
- Impact: orphan-row growth; stale page text can enrich future summaries via the `get_chunks_for_doc` fallback path.
- Fix approach: follow-up migration adding `ON DELETE CASCADE` FKs, same pattern as the evidence/summary tables.

**UI tests still assert formatting, never widgets (WR-10b remainder):**
- Issue: `tests/test_main_ui.py` (5 tests) covers the provider-attribute contract and Clear All purge logic but never imports `main.py`'s upload loop, tab layout, drawer rendering, or badge logic — the CR-01-class outage surface is still untestable.
- Files: `tests/test_main_ui.py`, `main.py` upload loop (~150+ lines)
- Impact: the next ingestion-wiring typo will again be green in CI and broken in the browser.
- Fix approach: extract the per-file upload processing into a testable helper and add a smoke test for the provider/visual wiring.

## Review Fix Status — Phase 06 (Performance Optimization & Resource Profiling)

All 1 Critical, 3 Warnings, 2 Info items from `.planning/phases/06-performance-optimization-and-resource-profiling/06-REVIEW.md` are **FIXED** per `06-REVIEW-FIX.md` and verified against current source:

- **CR-01 `InferenceGate.release()` counter corruption — FIXED.** `local_llm.py:55-63` now calls `cls._lock.release()` BEFORE decrementing `_active_threads`, so an unowned release raises `RuntimeError` immediately without corrupting the counter; `is_locked()` (`local_llm.py:66-69`) can no longer report False while the owner holds the lock. Regression test: `tests/test_concurrency_lock.py::test_unauthorized_release_does_not_corrupt_active_counter`.
- **WR-01 unlocked/unbounded `_LATENCY_HISTORY` — FIXED.** `resource_telemetry.py:22-23` adds `_LATENCY_LOCK = threading.Lock()` + `MAX_STAGE_HISTORY = 200`; all record/retrieve/clear/snapshot paths hold the lock (`resource_telemetry.py:139-143,165-169,174-180,193`). Covered by `tests/test_resource_telemetry.py` (10 tests).
- **WR-02 orphan leading assistant turn — FIXED.** `prompt_budget.py:131-152` adds `bound_chat_history(history, max_turns)` pruning leading `"assistant"` turns after tail-slicing; `assemble_grounded_messages` prunes `retained_history` the same way (`prompt_budget.py:121-122`); `main.py:389-395` routes all appends through `append_chat_turn` → `bound_chat_history(..., max_turns=MAX_CHAT_TURNS)`.
- **WR-03 bounding test fidelity — FIXED.** `tests/test_cache_invalidation.py:15-38` now imports and exercises production `bound_chat_history` directly (capacity bounding, assistant-pruning, empty-list contracts) instead of an inline slice.
- **IN-01/IN-02 — FIXED/DOCUMENTED.** Negative unauthorized-release test added (`tests/test_concurrency_lock.py:88-110`); `scripts/profile_resources.py:268` documents the 487.0 MB headless DWM fallback as an empirical Windows 11 baseline.

## Phase 06 Residuals (partial fixes + new risks — ordered by severity)

**Projected VRAM number is analytical, not measured (WR-era methodology gap, now the top release risk):**
- Issue: `scripts/profile_resources.py:267-278` computes `projected_peak_vram_mb` (3,445 MB) as an arithmetic sum of one live term (`dwm_overhead_mb` from `nvidia-smi`) plus four constants (`model_weights_mb=1450.0`, `vision_proj_mb=450.0`, `kv_cache_4k_mb=510.0`, `cuda_scratch_mb=350.0`). On headless/CI even the DWM term falls back to the 487.0 constant, so the CI-reported number is fully analytical. No llama-server process RSS/VRAM is ever sampled — the model is not loaded during profiling.
- Files: `scripts/profile_resources.py:258-296`, `.planning/research/RESOURCE_PROFILE.json:4-5`
- Impact: QUAL-01 compliance (≤ 3,800 MB) is asserted, not demonstrated; a real RTX 3050 run with the model resident could exceed the estimate (allocator fragmentation, driver variance, concurrent OCR pixmaps).
- Fix approach: before release, run `scripts/profile_resources.py` on the target RTX 3050 with llama-server resident and record live `nvidia-smi` used-MB at each stage into `RESOURCE_PROFILE.json`; treat 3,445 MB as a planning estimate until then.

**Sidebar telemetry spawns `nvidia-smi` on every Streamlit rerun (new, Phase 6):**
- Issue: `main.py:359` calls `get_gpu_memory_info()` (a `subprocess` `nvidia-smi` spawn with 2 s timeout, `resource_telemetry.py:26-71`) unconditionally on every full-script rerun with no `ttl`/`cache_resource` memoization. Every keystroke in chat input re-renders the sidebar and re-spawns the process.
- Files: `main.py:359-381`, `resource_telemetry.py:26-71`
- Impact: ~10–100 ms added to every rerun plus process-spawn churn; under a hung GPU driver the 2 s timeout blocks the whole UI thread (single-threaded Streamlit model).
- Fix approach: memoize with `@st.cache_data(ttl=5)` or equivalent so the gauge refreshes at most every few seconds; keep the CPU-only `None` path as-is.

**`InferenceGate` has no deadlock/timeout observability (residual):**
- Issue: `acquire(timeout=60.0)` (`local_llm.py:39-52`) blocks the single Streamlit script thread up to 60 s with no UI feedback; `hold()` raises bare `TimeoutError` with no badge or retry hint. No logging on acquire/release/timeout paths.
- Files: `local_llm.py:26-90`
- Impact: a stuck inference call freezes the UI for a minute, then surfaces an unhandled exception page.
- Fix approach: wrap the chat-loop gate hold in `st.status`/spinner with timeout → `st.error` + retry guidance; add debug logging on gate transitions.

**`MAX_CHAT_TURNS=50` bounds count, not tokens (residual):**
- Issue: `bound_chat_history` (`prompt_budget.py:131-152`) caps turn count, but 50 long turns can still exceed the 4 096-token input budget; the token-budget path (`prompt_budget.py:108-122`) then silently drops oldest turns mid-request without surfacing a "context truncated" indicator.
- Files: `prompt_budget.py:105-152`, `main.py:38,389-395`
- Impact: long sessions get silent context loss; no UI signal when truncation fires.
- Fix approach: surface a truncation indicator when either bound fires; consider sizing `MAX_CHAT_TURNS` from the token budget rather than a fixed 50.

## Phase 06 Readiness — VRAM Ceiling & Performance Risks (post-Phase 6 status)

**Runtime VRAM measurement now exists (Phase 6 — RESOLVED with methodology caveat):**
- Status: `resource_telemetry.py` (`get_gpu_memory_info` via `nvidia-smi` with 2 s timeout, `get_process_memory_info` via `psutil`, `LatencyTracker`, `get_system_telemetry_snapshot`) plus `scripts/profile_resources.py` (6-stage ingest → embed → hybrid-index → gate → footprint audit) and the sidebar `📊 System Telemetry & VRAM` widget (`main.py:359-384`, green < 3,500 / amber ≤ 3,800 / red > 3,800 MB) close the instrumentation gap.
- Files: `resource_telemetry.py`, `scripts/profile_resources.py`, `main.py:359-384`, `.planning/research/RESOURCE_PROFILE.json`
- Caveat: the headline 3,445 MB figure is analytical (see Phase 06 Residuals) — live per-rerun sampling exists, but release still needs a model-resident measurement on the RTX 3050.

**Unbounded caches, partially bounded (Phase 6 — chat history FIXED, disk caches open):**
- Status: session chat history is now bounded (`MAX_CHAT_TURNS=50` via `append_chat_turn`, `main.py:38,389-395`, tested in `tests/test_cache_invalidation.py:15-38`); summary cache has model-version invalidation (`doc_store.py:469-497`).
- Issue: SQLite summaries (`UNIQUE(sha256,profile)` upsert, never pruned) and LanceDB rows (`data/lancedb/`, append-mostly, no `compact_files`/`vacuum`) still grow monotonically; per-doc/profile `summary_*` session keys accumulate within the session.
- Files: `doc_store.py:438-460`, `hybrid_retriever.py:318-334`, `main.py:622-636`
- Impact: disk footprint grows without bound across long use; release hardening (Phase 8) still needs per-cache caps/compaction cadence.
- Fix approach: define per-cache caps (max summaries per doc, LanceDB compaction cadence); counts already exposed in the sidebar (`main.py:383-384`).

**Dual-index double-write per upload (Phase 6 — RESOLVED in the main path):**
- Status: per `06-02-SUMMARY.md`, redundant `LocalEmbedding.build_index(...)` calls were removed from the upload and dedup-restore paths — `main.py:218-224,285-288` now computes embeddings via `get_embeddings` and writes ONLY to `HybridRetriever.index_chunks(..., embeddings=...)`; `LocalEmbedding` is retained strictly as the CPU vectorizer (`embedding_fn=..._embed_one`). No `build_index` call remains in `main.py`.
- Residual: `local_llm.py:211` (the `retrieval_result=None` fallback branch) still calls `build_index`, and the `LocalEmbedding.store: VectorIndex` object still exists per session — the classes are not removed, only unused on the hot path.
- Files: `main.py:218-224,285-288`, `local_llm.py:211`, `local_embedding.py:59-76`
- Fix approach: remove the `local_llm.py:211` fallback branch (see Dead fallback branch below) and the `VectorIndex` will be fully dead code on all app paths.

**VLM + OCR resource pressure against the 4 GB ceiling (standing):**
- Problem: visual analysis (`visual_analyzer.py` crop → `analyze_image` → llama-server VLM) and RapidOCR (ONNX on CPU) add per-document latency and memory that the Phase 2 budget did not account for. Large pages at high zoom/DPI inflate pixmap + OCR tensor memory; concurrent uploads serialize on the single model.
- Files: `visual_analyzer.py:143-190` (render/crop/zoom), `ocr_fallback.py:80-135` (render at `eff_dpi`, ONNX recognizer), `llama_cpp_provider.py:220-268` (`analyze_image`)
- Cause: per-visual-element VLM round-trips; full-page rasterization before OCR; no batching or pixel budget; floor clamps exist (`max(72, ...)` DPI, `max(0.5, ...)` zoom) but no ceilings.
- Improvement path: add a DPI/pixel-area ceiling (e.g. 300 DPI), skip vision for thumbnails/decorations by bbox-area threshold, batch VLM calls or defer them to query time; measure before/after with the Phase 6 harness.

**BM25 fallback is full-corpus Python scoring:**
- Problem: `_bm25_search_fallback` tokenises every stored document per query and scores in pure Python (`hybrid_retriever.py:415-476`); the df fix removed the quadratic term but per-query cost is still O(N·|Q|) with regex tokenisation of all contents.
- Files: `hybrid_retriever.py:415-476`; LanceDB native FTS attempted first (`hybrid_retriever.py:491-504`)
- Cause: no persistent inverted index; fallback path pays full scan on every query when native FTS is unavailable.
- Improvement path: cache tokenised corpus between queries with invalidation on `index_chunks`/`delete_document`; ensure native FTS index creation (`create_fts_index`, `hybrid_retriever.py:405-413` — currently never called from `main.py`).

**Per-session embedding model copy:**
- Problem: `LocalEmbedding` is stored in `st.session_state`, so each browser session loads its own `SentenceTransformer`.
- Files: `main.py:49-57`-area session init, `local_embedding.py:12-23`
- Cause: not cached with `@st.cache_resource` (deliberate, to keep the index per-session).
- Improvement path: cache the model weights separately from the per-session index to share one weight set in RAM — directly reclaims RAM headroom for the VRAM-adjacent budget.

## Phase 07 Readiness — Cloud Fallback & Privacy Risks (two phases out)

**Groq fallback exists with no opt-in, no egress signal (core Phase 7 gap):**
- Issue: `groq_provider.py` + `local_llm.py:48-69` `_detect_provider` silently route generation (and therefore full document context) to Groq Cloud whenever the local server is unreachable. There is no explicit user opt-in, no per-request consent, no egress badge in the UI, and no setting to disable cloud. The local-first privacy guarantee ("zero external network egress during local operation") currently depends on the user noticing the provider badge.
- Files: `groq_provider.py:36-50`, `local_llm.py:48-69`, `main.py` provider badge rendering
- Impact: a user who believes they are fully local silently exfiltrates document text on llama-server outage; Phase 7 (LiteLLM adapter + explicit opt-in + privacy guardrails) must retrofit consent onto a default-on path.
- Fix approach: add an explicit cloud-enabled toggle (default off or explicit first-run consent), gate `_detect_provider` on it, and render an unmissable egress indicator whenever the active provider is remote.

**llama-server URL is injectable without validation (SSRF surface):**
- Risk: `LlamaCppProvider(base_url=...)` accepts an arbitrary URL (`llama_cpp_provider.py:23-36`) and `check_health`/streaming issue HTTP requests to it. No scheme/host allowlist; a caller passing an attacker-controlled `base_url` turns the provider into an SSRF primitive against internal services.
- Files: `llama_cpp_provider.py:23-45`, `local_llm.py:48-69` (only constructs the default loopback today)
- Current mitigation: all production construction uses the default `http://127.0.0.1:8080`; no user input reaches `base_url`.
- Recommendations: validate `base_url` (allow `http://127.0.0.1:*` / `http://localhost:*` only, or require explicit opt-in for remote hosts); add a test asserting non-loopback URLs are rejected unless explicitly permitted. Phase 7 must resolve this before any remote-server configuration UI ships.

**No LiteLLM adapter / provider seam for Phase 7:**
- Issue: `AiModel._detect_provider` constructs and probes concrete providers directly (`local_llm.py:48-69`) instead of consulting configuration/factory. Adding the planned LiteLLM adapter means editing the orchestrator again.
- Files: `local_llm.py:48-69`
- Impact: Phase 7 work starts with refactoring rather than extension.
- Fix approach: introduce a provider factory/config selection before Phase 7.

## Tech Debt (ordered by severity)

**Dual-index write path (Phase 6 — RESOLVED in the main path, classes retained):**
- Status: `main.py` no longer calls `LocalEmbedding.build_index` on upload or dedup-restore (`main.py:218-224,285-288` write only to `HybridRetriever.index_chunks` with precomputed embeddings); `HybridRetriever` is the sole authoritative index and `LocalEmbedding` is the CPU vectorizer only. The double-embedding/compute cost and the two-sources-of-truth divergence risk are gone on the hot path.
- Residual: `local_llm.py:211` still `build_index`es into an ephemeral `LocalEmbedding` on the `retrieval_result=None` fallback, and `LocalEmbedding.store: VectorIndex` still allocates per session — dead weight, not divergence.
- Files: `main.py:218-224,285-288`, `local_llm.py:211`, `local_embedding.py:43,59-76`
- Fix approach: delete the fallback branch (see Dead fallback branch) and remove `VectorIndex` from the session entirely.

**Clear All resets session but not persistent stores (still open after 06-02 hardening):**
- Issue: Clear All nulls `st.session_state.hybrid_retriever` (after `close()`), resets `doc_ids`/`indexed_files`/`document_metadata`/`chat_history` and deletes every `summary_*` key (`main.py:142-156`; hardened in 06-02), but never calls `delete_document` per doc, never drops the LanceDB `chunks` table, never deletes `data/lancedb/`, and never removes `DocStore` rows (`data/documents.db`).
- Files: `main.py:132-141`-area; persistent state lives in `data/lancedb/` and `DocStore(Path("data/documents.db"))`
- Impact: after Clear All, re-uploading the same PDFs hits the `DocStore` dedup path and restores from SQLite rather than re-extracting — the button reads as "forget everything" but is actually "clear session view". Stale LanceDB rows for never-re-uploaded docs remain queryable in future sessions that re-create the retriever. Disk usage grows monotonically.
- Fix approach: decide the intended semantic (session-clear vs full-purge) and implement accordingly — either delete per-`doc_id` from `HybridRetriever` + `DocStore` on Clear All, or rename the button to reflect session-only reset.

**Unpinned heavy + persistent dependencies (expanded in Phase 4):**
- Issue: `numpy>=1.26.0,<3.0.0`, `httpx>=0.28.0`, `docling>=2.0.0`, `rapidocr-onnxruntime>=1.3.0`, `pymupdf>=1.24.0`, `pillow>=10.2.0` remain open ranges, and Phase 4 adds `lancedb>=0.17.0` + `pyarrow>=14.0.0` — also open floors, both native/binary wheels with platform-sensitive builds.
- Files: `requirements.txt:7,9-15`
- Impact: non-reproducible installs; `lancedb`/`pyarrow` minor bumps can change table schema handling, FTS availability, or Windows wheel compatibility, silently shifting retrieval behaviour. Highest blast radius after the dual-index debt. Phase 8 (release hardening) must pin these.
- Fix approach: pin exact versions for `lancedb`, `pyarrow`, `docling`, `rapidocr-onnxruntime`, `pymupdf` (verify on Windows + CPU-only), or adopt a lockfile (none exists).

**Private `_embed_one` passed as the hybrid embedding function:**
- Issue: `main.py` wires `HybridRetriever(embedding_fn=st.session_state.local_embedding._embed_one)` — a private method of another module's class is now load-bearing for all hybrid queries.
- Files: `main.py:206,273`-area, `local_embedding.py:28` (`_embed_one`), `hybrid_retriever.py:143-147`
- Impact: renaming or changing the private helper silently breaks hybrid retrieval construction; `set_embedding_fn` exists as the public seam but construction still reaches through the underscore.
- Fix approach: expose a public `embed_one`/`embed_query` method on `LocalEmbedding` and construct the retriever from that (keeping `set_embedding_fn` for late binding).

**Legacy `PdfReader` chunk offsets never populated:**
- Issue: `Chunk.char_start`/`char_end` are populated by `docling_reader.py` and `ocr_fallback.py`, but the legacy `pdf_reader.py` construction path still leaves them `None`.
- Files: `pdf_reader.py:77-88` (construction), `models.py:68-69` (fields)
- Impact: citations for documents ingested via the legacy path resolve to page granularity only; mixed provenance (some chunks with offsets, some without) complicates the citation renderer.
- Fix approach: compute spans during `text_splitter.split_text` in `PdfReader.extract_text`, or route the legacy path through the same offset helper used by `docling_reader.py`.

**Hand-rolled provider dispatch:**
- Issue: `AiModel._detect_provider` constructs and probes concrete providers directly instead of consulting configuration/factory.
- Files: `local_llm.py:48-69`
- Impact: adding or reordering backends (LiteLLM in Phase 7) requires editing the orchestrator.
- Fix approach: introduce a provider factory/config selection.

**Dead fallback branch (still present, narrowed):**
- Issue: `ask_a_question_from_pdf_stream` can still build its own `PdfReader` + `LocalEmbedding` when no index is passed (`local_llm.py:124-128`), but `main.py` always passes `active_retriever` + `retrieval_result` (`main.py:427-433`-area). The untested inline-build path now additionally bypasses `HybridRetriever`/persistence entirely.
- Files: `local_llm.py:124-128`; caller in `main.py` chat loop
- Impact: duplicated ingestion concerns inside the inference layer; untested by the app; results from this path are dense-only and ephemeral.
- Fix approach: remove the branch or expose it as a documented standalone entry point.

**Working-directory-relative artifact paths:**
- Issue: `data/documents.db`, `data/lancedb/`, and `.cache` are resolved against the process CWD.
- Files: `main.py` upload loop (`DocStore(Path("data/documents.db"))`), cache handling, `hybrid_retriever.py` default `db_uri`
- Impact: launching Streamlit from a different directory silently creates databases/caches in the wrong place; LanceDB persistence (`data/lancedb/`, present on disk) is location-dependent, so a different CWD starts with an empty index while `DocStore` dedup claims docs are already indexed.
- Fix approach: anchor all three to `Path(__file__).resolve().parent`.

## Known Bugs

**Stale `mock_groq_client` fixture (still open):**
- Symptoms: `tests/conftest.py`'s `mock_groq_client` patches `local_llm.Groq`, but `local_llm` no longer imports `Groq` (it moved to `groq_provider.py`). Any test requesting the fixture raises `AttributeError`.
- Files: `tests/conftest.py:19-50`; the import now lives at `groq_provider.py:12-14`
- Trigger: add `mock_groq_client` as a test parameter.
- Workaround: none — the fixture is currently unused, so the suite passes. `fake_env_groq_key` (`tests/conftest.py:13-16`) is likewise unused.
- Fix approach: repoint the patch target at `groq_provider.Groq` or delete the dead fixtures.

**README describes a superseded architecture:**
- Symptoms: `README.md` states the app "uses Groq API for … Llama 3 generation" and lists only the original 5 modules, omitting `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`, `doc_store.py`, `models.py`, `upload_validation.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `hybrid_retriever.py`, `summarizer.py`, `citation_validator.py`, and local llama-server inference entirely.
- Files: `README.md` (feature list / "What Is This?" / file-responsibility table)
- Impact: onboarding documentation contradicts the code and the local-first persistent-hybrid design.
- Fix approach: rewrite the README against `STACK.md`/`ARCHITECTURE.md`; note it is user-facing and may be intentionally preserved for the cloud demo.

## Security Considerations

**Cloud fallback exfiltrates document context without consent (new, Phase 7 precursor — highest security item):**
- Risk: when llama-server is down, generation requests carrying full retrieved context go to Groq Cloud with no opt-in and no egress warning. See Phase 07 Readiness above.
- Files: `groq_provider.py:36-50`, `local_llm.py:48-69`
- Current mitigation: provider badge shows the active backend; `.env` is gitignored and the key is never printed.
- Recommendations: consent-gate the cloud path before Phase 7; treat every `stream_text` call site as an egress point in review.

**Prompt injection from document text (residual output-side gap):**
- Risk: retrieved PDF text is placed in the prompt; a malicious document could try to issue instructions. Input-side isolation is now fixed (CR-01 sanitize + CR-02 bounding + WR-03 fast-path directive + WR-09 case-insensitive regex), but there is no output-side check that the answer doesn't echo injected directives.
- Files: `prompt_budget.py:25-94` (grounding template with explicit non-execution directive and `<document_context>` isolation plus `sanitize_xml_boundary`), `summarizer.py:110,130,219`
- Current mitigation: context wrapped in `<document_context>` with boundary escaping; asserted by `tests/test_prompt_budget.py::test_sanitize_xml_boundary` and `test_injection_directive_escaped_in_document_context`.
- Recommendations: keep directives verbatim when editing templates; consider an output-side check that the answer doesn't echo injected directives. VLM descriptions (`visual_analyzer.py`) are also model-generated text entering the index — treat them as untrusted on retrieval.

**Untrusted PDF parsing in-process:**
- Risk: `pypdf`/Docling/PyMuPDF parse attacker-controlled bytes in the app process; no sandbox or resource isolation beyond the file/page caps.
- Files: `upload_validation.py:64-110` (`MAX_FILE_MB=50`, `MAX_PAGES=500`), `pdf_reader.py:29-113`, `docling_reader.py:135`, `ocr_fallback.py:67,127`
- Current mitigation: magic-byte check, size and page caps, per-page try/except.
- Recommendations: pin `pypdf` exactly (already `==5.3.0`) and keep it current for CVE fixes; extend exact pins to `pymupdf` (currently `>=1.24.0`, a native parser with memory-unsafe code); consider a parse timeout / subprocess for hostile input.

**llama-server URL is injectable without validation (SSRF surface):**
- Risk: `LlamaCppProvider(base_url=...)` accepts an arbitrary URL (`llama_cpp_provider.py:23-36`) and `check_health`/streaming issue HTTP requests to it. No scheme/host allowlist; a caller passing an attacker-controlled `base_url` turns the provider into an SSRF primitive against internal services.
- Files: `llama_cpp_provider.py:23-45`, `local_llm.py:48-69` (only constructs the default loopback today)
- Current mitigation: all production construction uses the default `http://127.0.0.1:8080`; no user input reaches `base_url`.
- Recommendations: validate `base_url` (allow `http://127.0.0.1:*` / `http://localhost:*` only, or require explicit opt-in for remote hosts); add a test asserting non-loopback URLs are rejected unless explicitly permitted.

**LanceDB filter escaping is quote-doubling only (residual after CR-03):**
- Risk: the CR-03 fix neutralises single-quote breakouts, but escaping is hand-rolled per call site rather than a shared helper; backslash/unicode edge cases and any future `where()`/`delete()` interpolation that forgets the `.replace` reintroduce the same class.
- Files: `hybrid_retriever.py:219,328,357`
- Current mitigation: quote-doubling at all three current sites, covered by regression tests per `04-REVIEW-FIX.md`.
- Recommendations: extract a `_escape_filter_literal()` helper and route every filter expression through it; add a negative test with `doc_1' OR '1'='1` against `delete_document` asserting other rows survive.

**Credential handling:**
- Risk: `GROQ_API_KEY` could leak into logs or commits.
- Files: `groq_provider.py:36-50`, `.gitignore:1`
- Current mitigation: `.env` is gitignored; the key is never printed; `.env` contents are never read into docs.
- Recommendations: none outstanding.

## Performance Bottlenecks

**Dual-index double-write per upload (Phase 6 — RESOLVED, see Tech Debt):**
- Status: main-path `build_index` calls removed; upload embeds once via `get_embeddings` and writes once to `HybridRetriever.index_chunks` (`main.py:218-224,285-288`). Retained here only as a pointer — the remaining per-upload cost is one embedding pass plus LanceDB `merge_insert`/delete-then-add, which is the designed single-write path, not debt.

**VLM + OCR resource pressure against the 4 GB VRAM ceiling (standing):**
- Problem: visual analysis and RapidOCR add per-document latency and memory the Phase 2 budget (≈ 3.26 GB) did not account for. See Phase 06 Readiness above.
- Files: `visual_analyzer.py:143-190`, `ocr_fallback.py:80-135`, `llama_cpp_provider.py:220-268`
- Cause: per-visual-element VLM round-trips; full-page rasterization before OCR; no batching or pixel budget.
- Improvement path: cap crop pixel area and OCR DPI (add a ceiling, e.g. 300 DPI), skip vision for thumbnails/decorations by bbox-area threshold, batch VLM calls or defer them to query time — all measured by the Phase 6 harness.

**BM25 fallback is full-corpus Python scoring:**
- Problem: `_bm25_search_fallback` tokenises every stored document per query in pure Python (`hybrid_retriever.py:415-476`); per-query cost is O(N·|Q|) with regex tokenisation of all contents.
- Files: `hybrid_retriever.py:415-476`; LanceDB native FTS attempted first (`hybrid_retriever.py:491-504`)
- Cause: no persistent inverted index; fallback path pays full scan on every query when native FTS is unavailable.
- Improvement path: cache tokenised corpus between queries with invalidation on `index_chunks`/`delete_document`; ensure native FTS index creation (`create_fts_index`) is called from `main.py`.

**Context cap truncates multimodal evidence first (standing):**
- Problem: `prompt_budget.py` bounds total input to 4096 tokens with oldest-first history truncation and `[... truncated ...]` markers. Visual element descriptions and OCR text compete with digital text for the same budget; long multimodal pages can evict conversational history or get silently truncated.
- Files: `prompt_budget.py:53-98`, `visual_analyzer.py:220-250`
- Cause: single flat budget shared by text + OCR + vision descriptions.
- Improvement path: prioritize/weight evidence (e.g. cap vision-description tokens per element), surface a "context truncated" indicator in the UI when truncation fires.

**Per-session embedding model copy:**
- Problem: `LocalEmbedding` is stored in `st.session_state`, so each browser session loads its own `SentenceTransformer`.
- Files: `main.py` session init, `local_embedding.py:12-23`
- Cause: not cached with `@st.cache_resource` (deliberate, to keep the index per-session).
- Improvement path: cache the model separately from the per-session index to share one weight set in RAM.

## Fragile Areas

**Non-hybrid chat branch reintroduces CR-02 divergence (residual):**
- Files: `main.py` chat loop (`active_retriever = hybrid or local_embedding`; `else` branch uses `search` + filename-only chips), `local_llm.py:141-159` (re-searches with its own contextualised query when `retrieval_result=None`)
- Why fragile: whenever `hybrid_retriever` is `None` (construction failure, import fallback), the UI chips and the LLM context are built from two different queries on two different code paths — exactly the divergence CR-02 eliminated on the hybrid path. Chips also degrade to filename-only (no page numbers) on this path.
- Safe modification: unify on the single-`RetrievalResult` shape for both branches (e.g. wrap `LocalEmbedding` results into a `RetrievalResult` in `main.py` and always pass `retrieval_result=`); keep the `else` branch as a degraded-mode shim only.
- Test coverage: `tests/test_local_llm.py` covers pre-computed `retrieval_result` support; the `None`-retriever degraded path through `main.py` is untested.

**Provider selection sticky on healthy fallback:**
- Files: `local_llm.py` health-check/re-probe logic; the `AiModel` singleton is created once via the `main.py` cached loader.
- Why fragile: self-healing re-probes only when the current provider is unhealthy. If the app starts on Groq (llama-server down) and the local server later comes up healthy, the app stays on Groq — `check_health()` reports healthy Groq, so the badge never hints a local model is available. Combined with the no-opt-in cloud path, stickiness extends silent-egress duration.
- Safe modification: add an explicit "prefer local when reachable" re-detect (manual refresh button or periodic background probe), keeping start-degraded behavior.
- Test coverage: `tests/test_local_llm.py` covers selection at construction and unhealthy→healthy recovery, not healthy-fallback→local switchback.

**Shared singleton retrieval state (Phase 05 remainder):**
- Files: `local_llm.py:44,157-158,171,202-207`
- Why fragile: `last_retrieval_result` is process-wide; the documented caveat relies on every caller passing explicit results. One fallback call site contaminates the next.
- Safe modification: require explicit `retrieval_result` or scope state per call; see Phase 05 residuals.
- Test coverage: fallback behavior is asserted (`tests/test_citation_validator.py:148-161`), entrenching the shared-state contract.

**Fallback-store JSON normalises only `bbox` (residual of WR-04/Phase 04):**
- Files: `hybrid_retriever.py:162-187`
- Why fragile: any future non-JSON-primitive metadata value (numpy types from embeddings-adjacent code, `datetime`, `Path`) on a chunk dict raises `TypeError` inside `json.dump` and is swallowed as a `logger.warning` — persistence silently stops working with no UI signal.
- Safe modification: add a generic `default=str`-style sanitiser or a recursive primitive-normalisation pass over the whole chunk dict, not just the `bbox` key; surface persistence failure beyond debug logs.
- Test coverage: BBox round-trip covered; arbitrary-metadata robustness not asserted.

**`close()` in LanceDB mode skips persistence flush:**
- Files: `hybrid_retriever.py:149-154`
- Why fragile: `close()` only calls `_save_fallback_store()` when LanceDB is absent; in LanceDB mode it nulls `_table`/`_db` with no flush or FTS-index checkpoint. Combined with Clear All nulling the retriever (`main.py:137-139`-area), a session can drop its handles while the on-disk table holds un-checkpointed FTS state.
- Safe modification: call `create_fts_index`-style checkpoint/flush in `close()` when a table is present, or document that LanceDB handles durability and remove the asymmetry.
- Test coverage: lifecycle open/close covered; durability-across-close with FTS not asserted.

**Heuristic token counting:**
- Files: `prompt_budget.py:20-25` (chars ÷ 4)
- Why fragile: under-counts code/PDF-mangled text; a bad estimate can exceed the real context window and truncate or error at the server. OCR output (noisy, fragmented) skews the heuristic further. Phase 6 KV-cache/context tuning will inherit this error.
- Safe modification: preserve the conservative reserve (`max_output_tokens`), and consider a real tokenizer for the local model.
- Test coverage: `tests/test_prompt_budget.py` verifies bounds but not fidelity to a tokenizer.

**Silent SSE frame drops:**
- Files: `llama_cpp_provider.py:196-215` (malformed `data:` frames `continue` without logging)
- Why fragile: dropped tokens are invisible; a partial answer looks complete.
- Safe modification: log skipped frames at debug level rather than swallowing silently.
- Test coverage: happy-path multi-chunk parsing is covered; malformed-frame handling is not asserted.

**Large sidebar orchestration loop (grown across Phases 4–5):**
- Files: `main.py` upload loop (~150+ lines incl. Docling/OCR/visual/LanceDB branches) mixes validation, dedup, extraction, OCR fallback, visual analysis, dual-index writes, persistence, caching, and state updates; chat loop adds summarizer + validator wiring (`main.py:484,594-622`).
- Why fragile: hard to unit-test; ordering bugs are easy to introduce (CR-01/Phase 05 class).
- Safe modification: extract the per-file processing into a testable helper.
- Test coverage: none for `main.py` orchestration paths.

## Scaling Limits

**VRAM ceiling (4 GB) — analytical estimate, needs model-resident measurement before release:**
- Current capacity: projected peak 3,445 MB vs 3,800 MB safety target (651 MB headroom), per `.planning/research/RESOURCE_PROFILE.json:4-5` — but the figure is an analytical sum (one live DWM term + four constants; fully constant on headless/CI). Phase 6 added live sampling (`resource_telemetry.py`, sidebar gauge `main.py:359-384`) and the `InferenceGate` single-resident-model invariant (`local_llm.py:26-90`), so the ceiling holds only if exactly one model stays resident and embeddings/OCR stay on CPU.
- Limit: any second model, larger context, or GPU-offloaded OCR triggers shared-memory paging (throughput collapses).
- Scaling path: keep exactly one model resident; reduce `-ngl`/`-c` if needed; cap crop/DPI budgets. Release gate: re-run `scripts/profile_resources.py` on the RTX 3050 with llama-server resident and replace the analytical projection with live numbers.

**BM25-from-table recovery capped at 10 000 rows:**
- Current capacity: `_bm25_search_fallback` reads at most 10 000 LanceDB rows into memory (`hybrid_retriever.py:427`).
- Limit: corpora above ~10k chunks silently exclude tail rows from keyword search after restart; dense search is unaffected (native index), so hybrid fusion degrades asymmetrically with no warning.
- Scaling path: paginate the recovery read or rebuild the fallback mirror incrementally; log when the cap truncates.

**SQLite single-file store:**
- Current capacity: fine for a single user; per-operation connections with WAL (`doc_store.py:81-95`) plus FK enforcement. Summaries table grows monotonically (no eviction).
- Limit: concurrent writers on network/OneDrive paths can still contend despite `busy_timeout`.
- Scaling path: keep the DB on a local disk; LanceDB/multi-user is out of scope.

**LanceDB on-disk growth is append-mostly:**
- Current capacity: `merge_insert("chunk_id")` upserts on re-index (`hybrid_retriever.py:318-324`), but the legacy delete-then-add path (`hybrid_retriever.py:325-334`) and Clear All semantics (no table purge — see Tech Debt) leave stale rows and tombstone growth in `data/lancedb/`.
- Limit: repeated re-index/delete cycles bloat the table; no compaction/vacuum is ever invoked.
- Scaling path: add periodic `compact_files`/`vacuum` (LanceDB maintenance) or a full re-index utility.

## Dependencies at Risk

**Unpinned multimodal + native + persistence stack (`docling`, `rapidocr-onnxruntime`, `pymupdf`, `pillow`, `lancedb`, `pyarrow`):**
- Risk: all declared as `>=` floors in `requirements.txt:7,9-15`; `docling` and `rapidocr-onnxruntime` drag in torch/onnxruntime/opencv transitives that are large, fast-moving, and platform-sensitive (Windows wheel availability, CUDA/CPU variants); `lancedb`/`pyarrow` add native query-engine + columnar-format coupling where a minor bump can change FTS availability or table-compat behaviour.
- Impact: a transitive bump can break layout parsing, OCR decoding, vector search, FTS search, or model-download behavior; `pymupdf`/`pillow` are native parsers with CVE history.
- Migration plan: pin exact working versions (verify on Windows + CPU-only), or add a lockfile; keep `pypdf==5.3.0` exact as-is. Owned by Phase 8 (release hardening).

**Transitive torch / transformers (via sentence-transformers):**
- Risk: not pinned in `requirements.txt`; large, fast-moving, and platform-sensitive.
- Impact: a transitive bump can break embeddings or download behavior.
- Migration plan: pin transitives or add a lock; the model itself (`all-MiniLM-L6-v2`) is stable.

**`reportlab` only in `requirements-test.txt`:**
- Risk: `tests/test_pdf_reader.py` imports `reportlab` at module top, so a plain `pip install -r requirements.txt` cannot run the suite.
- Impact: local test runs fail on collection unless test deps are installed.
- Migration plan: document/seed the test deps (CI already installs `requirements-test.txt`).

## Missing Critical Features

**Cloud opt-in + egress guardrails (Phase 7 scope, gap is current):**
- Problem: no consent toggle, no egress indicator beyond the provider badge, no per-request disclosure that context leaves the machine.
- Blocks: the local-first privacy promise under fallback conditions.
- Fix approach: Phase 7 LiteLLM adapter must ship with default-off/cloud-consent + visible remote-generation labeling.

**Output-side injection check:**
- Problem: input isolation is fixed (CR-01/CR-02 + sanitize + WR-03/WR-09), but no output guard verifies answers don't echo injected directives from documents or VLM descriptions.
- Blocks: full prompt-injection closure.
- Fix approach: add an answer-side scan (directive-echo detection) plus a test with an adversarial chunk.

**`base_url` allowlisting:**
- Problem: `LlamaCppProvider` accepts any `base_url` with no loopback restriction.
- Blocks: safe remote-server configuration.
- Fix approach: add scheme/host validation + explicit opt-in flag for non-loopback hosts.

**Retrieval quality evaluation:**
- Problem: Phase 4 ships BM25 + RRF fusion with no measured quality baseline (no recall@k / nDCG harness); `scripts/benchmark_baseline.py` measures scan latency only.
- Blocks: knowing whether hybrid actually beats dense-only, and tuning RRF weights / k per mode.
- Fix approach: extend the corpus generator (`tests/data/corpus/generate_corpus.py`, run in CI per `04-REVIEW-FIX.md`) with relevance judgements and a recall@k check.

**VRAM/RAM profiling harness (Phase 6 scope, gap is current):**
- Problem: no script or module samples GPU memory, RSS, or KV-cache utilization across pipeline stages.
- Blocks: every Phase 6 tuning decision.
- Fix approach: add `scripts/profile_resources.py` (or equivalent) sampling `nvidia-smi`/pynvml + `psutil` across ingest → embed → VLM → query before tuning.

## Test Coverage Gaps

**`main.py` UI orchestration (narrowed by Phase 6, still the top gap):**
- What's not tested: upload flow, dedup handling, Docling/OCR/visual/LanceDB branches, hybrid restore-on-restart, Clear All semantics (purge logic covered, orchestration not), cache writes, chat streaming, error paths, tab/drawer/badge rendering.
- New in Phase 6 (covered): chat-history bounding via production `bound_chat_history` (`tests/test_cache_invalidation.py:15-38`), `DocStore.count_documents/count_summaries` + sidebar telemetry contracts (`tests/test_cache_invalidation.py`), `InferenceGate` acquire/release/reentrancy/timeout/unauthorized-release (`tests/test_concurrency_lock.py`, 8 tests), telemetry parsing/fallbacks/snapshot (`tests/test_resource_telemetry.py`, 10 tests).
- Files: `main.py`
- Risk: regressions in orchestration are only caught manually (Phase 3 criticals, Phase 4 CR-01/CR-02, Phase 5 CR-01 all lived here).
- Priority: High

**Groq streaming success path:**
- What's not tested: `GroqProvider.stream_text`/`generate_text` happy path (only the unconfigured health path is asserted).
- Files: `groq_provider.py:94-149`; tests cover only `check_health`/capabilities (`tests/test_local_llm.py`).
- Risk: payload/stream parsing regressions in the fallback provider — the very path Phase 7 will build on.
- Priority: Medium (rises to High when Phase 7 starts).

**VLM/OCR integration paths:**
- What's not tested: end-to-end upload → OCR → visual description → indexed evidence; vision-unavailable degradation is unit-tested (`tests/test_visual_analyzer.py`) but the `main.py` wiring (provider → `VisualAnalyzer`) has no test.
- Files: `main.py` upload loop, `visual_analyzer.py:211-250`, `ocr_fallback.py:232-290`
- Risk: CR-01-class wiring regressions (provider never passed, vision silently off).
- Priority: High

**Hybrid degraded-mode paths:**
- What's not tested: `LocalEmbedding`-only chat branch, `retrieval_result=None` re-search inside `local_llm.py:123-159`, BM25-from-table recovery above/below the 10 000-row cap, `close()` durability with a live LanceDB table, filter escaping with adversarial `doc_id` on `delete_document`.
- Files: `main.py` chat loop, `local_llm.py:123-159`, `hybrid_retriever.py:346-363,424-431`
- Risk: the exact paths that execute when LanceDB is missing or sessions restart cold are the least asserted.
- Priority: High

**Summarizer pipeline-version and singleton paths:**
- What's not tested: cache behavior across `CONFIG_VERSION`/chunking changes (no test — no code either); cross-session `last_retrieval_result` contamination (documented, unasserted either way).
- Files: `doc_store.py:469-497`, `summarizer.py:328-332`, `local_llm.py:44,171,207`
- Risk: the two Phase 05 residuals have no regression net if a future change widens them.
- Priority: Medium

**Error/edge paths:**
- What's not tested: `GroqProvider.analyze_image` raising `NotImplementedError`; malformed SSE frames; `main.py` provider errors mid-stream.
- Files: `groq_provider.py:151-156`, `llama_cpp_provider.py:196-215`, `main.py` chat loop
- Risk: silent or ugly failures.
- Priority: Low–Medium

**No coverage measurement:**
- What's not tested: no `pytest-cov` in `requirements-test.txt` and no threshold config.
- Files: `pyproject.toml`, `requirements-test.txt`
- Risk: coverage can regress unnoticed.
- Priority: Low

---

*Concerns audit: 2026-10-12*
