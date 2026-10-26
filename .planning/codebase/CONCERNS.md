# Codebase Concerns

**Analysis Date:** 2026-10-26

## Tech Debt

**Monolithic chat view (`ui/views.py`, 1332 lines):**
- Issue: The largest module mixes Streamlit rendering, retrieval orchestration, citation attribution, verification, chat-history mutation, and provider dispatch. `render_chat_view` (`ui/views.py:490`) owns the whole chat workspace, and its prompt-submission handler spans `ui/views.py:690-915` (~225 lines); the module has grown from the ~800 lines noted in `docs/CODE_QUALITY_REPORT.md` §5 to 1332.
- Files: `ui/views.py`
- Impact: Any change to chat behavior risks unrelated views; hard to unit test without Streamlit runtime; review diffs are large.
- Fix approach: Extract per-workspace controllers (`ui/chat_controller.py`, `ui/summarizer_controller.py`, `ui/library_controller.py`) leaving `ui/views.py` as thin `render_*` functions, matching the existing `IngestionService` / `LifecycleService` pattern in `ui/ingestion_service.py` and `ui/lifecycle_service.py`.

**Dual vector-fallback implementations:**
- Issue: `retrieval/vector_index.py` (in-memory/numpy fallback) and `retrieval/hybrid_retriever.py` (`fallback_store.json` mirror, `_mirror_upsert` at `retrieval/hybrid_retriever.py:312`) both implement chunk storage, cosine search, and deletion semantics.
- Files: `retrieval/vector_index.py`, `retrieval/hybrid_retriever.py`
- Impact: Two sources of truth for fallback behavior; divergent delete/purge semantics are a realistic data-consistency bug class. Already flagged as P2 in `docs/CODE_QUALITY_REPORT.md`.
- Fix approach: Keep `HybridRetriever`'s mirror as the only durable fallback; demote `VectorIndex` to a pure in-memory upsert store with no deletion/indexing API, or delete it after a deprecation cycle and update `tests/test_hybrid_retriever.py`.

**Broad `except Exception` concentration:**
- Issue: `retrieval/hybrid_retriever.py` (19 occurrences), `ui/ingestion_service.py` (10), `ui/views.py` (9), `providers/litellm_provider.py` (5), `ui/hydration.py` (4), `ingestion/ocr_fallback.py` (4). Most log and re-raise or degrade intentionally, but two swallow silently: `count_chunks()` and `has_document()` use bare `except Exception: pass` (`retrieval/hybrid_retriever.py:405-409` and `:416-421`), falling back to the JSON mirror without logging.
- Files: `retrieval/hybrid_retriever.py`, `ui/ingestion_service.py`, `ui/views.py`, `providers/litellm_provider.py`
- Impact: A broken LanceDB table is indistinguishable from a healthy fallback read; index health drift goes unreported. If a data-integrity error is caught in a future edit, it can be converted into a false success (the exact defect `docs/CODE_QUALITY_REPORT.md` records as previously fixed).
- Fix approach: Narrow to `except (OSError, ValueError, RuntimeError)`; at minimum log at `warning` in `count_chunks`/`has_document` before falling back. Add a lint guard or review checklist requiring `raise`/`logger.*` in every `except Exception`.

**Environment surface undocumented:**
- Issue: No `.env.example` exists even though `.gitignore` explicitly whitelists it (`!.env.example`). Recognized variables are scattered: `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `LLAMA_SERVER_HOST`/`PORT`/`URL`, `DOCLING_ARTIFACTS_PATH`, `RAG_LOG_LEVEL`, `RAG_LOG_DIR`, `RAG_REQUIRE_CHECKSUMS`, plus the non-loopback opt-in in `start.py`.
- Files: `providers/litellm_provider.py:51-53`, `providers/groq_provider.py:44-51`, `core/logging_setup.py:26-28`, `start.py`, `setup.py:88-90`
- Impact: Setup friction and misconfiguration risk, especially for the non-loopback opt-in and checksum enforcement.
- Fix approach: Add `.env.example` listing every variable with safe defaults and a comment that `RAG_REQUIRE_CHECKSUMS=1` is recommended.

**Global pytest warning suppression:**
- Issue: `pyproject.toml:25-27` ignores all `UserWarning` and `DeprecationWarning` globally.
- Files: `pyproject.toml`
- Impact: The dependency stack (docling, lancedb, litellm, sentence-transformers) moves fast; suppressed deprecations will surface as hard breakage on upgrade with no CI signal.
- Fix approach: Replace global ignores with `filterwarnings = ["error::DeprecationWarning"]` plus targeted per-module ignores, or run one advisory CI job with warnings enabled.

## Known Bugs

**Auto-attributed citation count lost after rerun:**
- Symptoms: The immediate caption correctly distinguishes auto-attributed citations, but after the post-turn rerun the transcript caption reports "model-generated" for the same answer.
- Files: `ui/views.py:802-805` builds `verification_dict` with `auto_attributed_count`; `ui/views.py:826` renders it; `ui/views.py:889` stores `verification.model_dump()` — without the merged key — then `ui/views.py:897` reruns and re-renders from the stored dict via `verification_caption()` (`ui/views.py:84-124`).
- Trigger: Ask a question where the model omits `[E#]` and `auto_attribute_citations` inserts them, then observe the caption before vs. after the rerun.
- Workaround: None in UI; the underlying `verification` object still carries correct precision, only the label regresses.
- Fix: Store `verification_dict` instead of `verification.model_dump()` at `ui/views.py:889`.

**Auto-attributed citations are visually indistinguishable in chips:**
- Symptoms: Citation chips render for any rank in `cited_ranks`, which includes citations inserted lexically by `auto_attribute_citations`; users cannot tell model-grounded citations from heuristic ones.
- Files: `ui/views.py:846-868`, `core/citation_validator.py:427` (`auto_attribute_citations`), `core/citation_validator.py:22` (`SUPPORT_TOKEN_THRESHOLD = 0.35`)
- Trigger: Any answer that receives auto-attributed citations.
- Fix: Persist the auto-attributed rank set alongside `auto_attributed_count` and render those chips with a distinct label/badge.

**Raw exception text shown to the user and stored in chat history:**
- Symptoms: Streaming failures surface `st.error(f"Inference streaming failed: {err}")` and persist `*[Response generation interrupted: {err}]*` into the transcript.
- Files: `ui/views.py:899-915`
- Trigger: Provider timeout, malformed SSE chunk, or cloud API error.
- Impact: Leaks internal paths/host details into the chat log; for `GroqProvider` the message is unscrubbed (see Security Considerations).
- Fix: Log the exception, display a generic message, and store a fixed interruption marker.

## Security Considerations

**Unencrypted document content at rest:**
- Risk: Full chunk text and embeddings are stored in plaintext in `data/documents.db` (SQLite `chunks` table), `data/lancedb/chunks.lance`, and the JSON mirror `data/lancedb/fallback_store.json`; `_mirror_upsert` writes complete chunk text (`retrieval/hybrid_retriever.py:312-345`). Extracted page text lives in `.cache/<sha256>/<CONFIG_VERSION>/pages.json` (the SQLite `pages` table stores only status/counts, `core/doc_store.py:318-336`).
- Files: `core/doc_store.py`, `retrieval/hybrid_retriever.py`, `data/lancedb/fallback_store.json`
- Current mitigation: `data/` is gitignored; single-user loopback UI; no telemetry; `HybridRetriever.purge_all` unlinks `fallback_store.json` (`retrieval/hybrid_retriever.py:445-450`) and `DocStore.purge`/`VACUUM` clears SQLite rows.
- Recommendations: State this explicitly in `docs/RUNBOOK.md` (documents are plaintext on disk) and recommend OS-level disk encryption (BitLocker/LUKS). Note that `.cache/<sha256>/` extraction artifacts are removed only by `LifecycleService.delete_document`/`purge_all` (`ui/lifecycle_service.py:66-75`, `:130-137`); an interrupted delete leaves plaintext page/chunk JSON behind.

**Groq error paths do not scrub credentials:**
- Risk: `providers/litellm_provider.py` scrubs key material via `_scrub_credentials` before logging and re-raising (lines 135, 237-239, 294-296, 353-355), but `providers/groq_provider.py:143` and `:179` re-raise `RuntimeError(f"Groq API error: {exc}")` unscrubbed, and `ui/views.py:900` displays it.
- Files: `providers/groq_provider.py`, `ui/views.py`
- Current mitigation: Groq SDK errors typically do not echo the key; the leaked text is bounded by what the SDK includes.
- Recommendations: Extract the scrubber into a shared helper (e.g. `core/redaction.py`) and apply it in both providers plus the UI error path.

**Regex-based HTML sanitization, not an allowlist renderer:**
- Risk: `ui/sanitizer.py` is a pattern-hardening pass over Markdown/HTML (dangerous schemes, event handlers, `srcset`, CSS `url()`, SVG, `ping`, bare URLs). New or unusual payload shapes can bypass pattern coverage. Rendered paths use `unsafe_allow_html=True` for citation chips (`ui/views.py:863`).
- Files: `ui/sanitizer.py`, `ui/views.py:846-868`
- Current mitigation: Broad denial patterns, character-reference normalization, external-link neutralization by default (`allow_external=False`), and Streamlit's own Markdown renderer.
- Recommendations: Keep chip HTML fully server-generated (never include snippet text in `unsafe_allow_html` paths), and add sanitizer regression tests for any new payload reported.

**Unauthenticated UI and container bind address:**
- Risk: The app has no authentication. `Dockerfile` starts Streamlit with `--server.address=0.0.0.0`; safety depends on the host mapping being `127.0.0.1:8501`.
- Files: `Dockerfile`, `.streamlit/config.toml`, `start.py` (`is_loopback_host` guard, `RAG_ALLOW_NON_LOOPBACK` opt-in)
- Current mitigation: `start.py` refuses non-loopback binds; `.streamlit/config.toml` pins `address = "127.0.0.1"` with CORS/XSRF enabled.
- Recommendations: Document that changing `docker-compose` port mapping exposes an unauthenticated document store; consider a startup warning when `--allow-non-loopback` is used.

**Prompt-injection defense is heuristic:**
- Risk: Documents are untrusted; injection detection in `core/citation_validator.py` flags directives and `core/prompt_budget.py` isolates context in `<document_context>` XML, but detection is pattern-based.
- Files: `core/citation_validator.py`, `core/prompt_budget.py`, `core/local_llm.py`
- Current mitigation: Injection matches withhold the answer (`ui/views.py:809-816`) and save a fixed withheld marker; citations must exist in retrieved evidence.
- Recommendations: Add adversarial PDF cases to `tests/data/corpus/generate_corpus.py` and assert withholding behavior.

## Performance Bottlenecks

**Fallback mirror rewrite per ingestion (O(N) I/O):**
- Problem: Every ingestion transaction reads and rewrites the entire `fallback_store.json`, including all vectors.
- Files: `retrieval/hybrid_retriever.py:312-345`
- Cause: Single-file mirror chosen for crash-safety and to avoid in-RAM duplication (documented tradeoff in the docstring).
- Improvement path: Shard by `doc_id` (`fallback/<doc_id>.json`) or switch to SQLite-backed vector blob storage; measure with `scripts/profile_resources.py` before changing.

**CPU-bound ingestion latency:**
- Problem: Docling layout parsing plus RapidOCR fallback plus MiniLM embedding all run on CPU while the GPU is idle; large scanned PDFs take minutes.
- Files: `ingestion/docling_reader.py`, `ingestion/ocr_fallback.py`, `retrieval/local_embedding.py`
- Cause: Deliberate CPU offload to preserve the 4 GB VRAM envelope. `IngestionService` constructs a fresh `DoclingReader` per document (`ui/ingestion_service.py:149`), and `DoclingReader` lazily builds a new `DocumentConverter`/pipeline per instance (`ingestion/docling_reader.py:196`), so layout-model setup repeats for every upload instead of being shared.
- Improvement path: Inject a shared `DocumentConverter` via the existing `converter` parameter (`ingestion/docling_reader.py:44`), batch OCR pages, and keep per-stage progress reporting in `ui/ingestion_service.py`.

**Embedding model retained process-wide:**
- Problem: `_MODEL_CACHE` in `retrieval/local_embedding.py` keeps the SentenceTransformer resident for the process lifetime (hundreds of MB with the Torch runtime).
- Files: `retrieval/local_embedding.py`
- Cause: Avoid re-loading weights on every Streamlit rerun.
- Improvement path: `clear_shared_model_cache()` exists (`retrieval/local_embedding.py:46`) but is never called by `reset_in_memory_session`; consider invoking it on "Clear Session" to release RAM.

**Full-transcript re-render and re-sanitization per turn:**
- Problem: After every answer, `st.rerun()` re-renders the entire conversation and re-runs `sanitize_display_markdown` for every snippet in every prior turn.
- Files: `ui/views.py:895-897`, `ui/views.py:870-879`
- Cause: Uniform chronological rendering requirement.
- Improvement path: Cache sanitized snippet HTML per message in session state, or cap rendered history depth.

**`nvidia-smi` subprocess polling:**
- Problem: VRAM telemetry spawns `nvidia-smi` (Windows process creation ~30-80 ms); results are cached for 5 s under a lock.
- Files: `core/resource_telemetry.py:26`, `:45-54`, `:69`, `:120` (`timeout=2.0`)
- Cause: Only reliable cross-vendor VRAM source; `force_refresh=True` bypasses the cache.
- Improvement path: Acceptable as-is. Ensure UI paths pass the default (cached) mode and only the Settings "refresh" action forces a sample.

## Fragile Areas

**`InferenceGate` as the sole VRAM guarantee:**
- Files: `core/local_llm.py`, `core/summarizer.py`, `ingestion/visual_analyzer.py`
- Why fragile: Correctness depends on every new call site acquiring `InferenceGate.hold(...)` — `core/local_llm.py:83` provides the gate, `core/summarizer.py:559` uses `timeout=120.0`, and other call sites use `60.0`. Nothing enforces this structurally, and a single missed acquisition on a 4 GB card yields OOM or silent CPU spill.
- Safe modification: Any new generation/VLM path must call the gate; grep for `generate_text`/`analyze_image`/`stream_text` before adding call sites.
- Test coverage: Gate serialization/timeout/reentrancy is tested in `tests/test_concurrency_lock.py`; "every call site acquires the gate" is not asserted anywhere.

**Retrieval schema drift between LanceDB, mirror, and `EvidenceSnippet`:**
- Files: `retrieval/hybrid_retriever.py` (`_build_chunks_schema`, `fetch_document_chunks`), `core/models.py:142-168`
- Why fragile: Three parallel record shapes (PyArrow schema, JSON mirror, Pydantic snippet); nullable `char_start`/`char_end`/`bbox_json` are handled specially when the first batch is all-`None` (`retrieval/hybrid_retriever.py:535-545`).
- Safe modification: Change the schema in all three places at once and re-run `tests/test_hybrid_retriever.py`; bump `CONFIG_VERSION` in `core/models.py:14` only if extraction output changes (it invalidates caches).
- Test coverage: Bulk index/search/delete covered; migration from an older on-disk table is not covered.

**Cache keying and invalidation:**
- Files: `core/models.py:14-30` (`cache_dir_for`, `CONFIG_VERSION`), `core/summarizer.py`, `ui/hydration.py`
- Why fragile: `.cache/<sha256>/<CONFIG_VERSION>/` and summary caches keyed on `model_version`; changing `CONFIG_VERSION` or model identity silently orphans caches, while changing extraction without bumping it serves stale content.
- Safe modification: Bump `CONFIG_VERSION` for extraction/chunking changes. There is no cache-purge CLI (`scripts/` holds only `benchmark_baseline.py`, `benchmark_multimodal.py`, `generate_icons.py`, `profile_resources.py`); use `LifecycleService.purge_all` (`ui/lifecycle_service.py:130`) or delete `.cache/` manually. Invalidation behavior is covered by `tests/test_cache_invalidation.py`.

**Graceful degradation hidden behind fallbacks:**
- Files: `retrieval/hybrid_retriever.py`, `ingestion/docling_reader.py`, `providers/llama_cpp_provider.py`
- Why fragile: Docling → pypdf, LanceDB → JSON mirror, hybrid → dense-only, provider → cloud fallback all degrade silently by design. Behavior differences (e.g. no table structure from pypdf) are easy to miss in testing.
- Safe modification: Always assert `search_mode` / `extraction` fields in tests rather than assuming the primary path ran.

**Delete with no vector retriever leaves vectors intact:**
- Files: `ui/lifecycle_service.py:55-63`
- Why fragile: When `self.retriever is None`, `delete_document` deletes SQLite rows and the disk cache but only logs "Existing vectors may be resurrected by hydration." On the next hydration pass (`ui/hydration.py`), the surviving vectors can re-attach the deleted document's chunks to search results while metadata is gone.
- Safe modification: When triggers delete, either fail loudly or mark the doc id in a persistent tombstone that hydration and `HybridRetriever` consult; add a test covering delete-then-hydrate without a retriever.
- Test coverage: `tests/test_hydration.py` covers repopulation but not the explicit tombstone/tombstone-avoidance case.

## Scaling Limits

**Single-sequence inference:**
- Current capacity: One generation at a time via `InferenceGate`; llama-server launched with `-c 4096 -ngl 28` (`start.py:152`, `providers/llama_cpp_provider.py:157`).
- Limit: A second browser tab or a summarizer job queues behind the active stream; long summaries block chat.
- Scaling path: Documented limitation (`docs/EVALUATION.md` §7); would need a batch/queue surface or a larger-VRAM profile.

**Context horizon (4,096 tokens):**
- Current capacity: `context_window=4096` (`providers/llama_cpp_provider.py:63`), `DEFAULT_MAX_OUTPUT_TOKENS = 1536` (`core/prompt_budget.py:17`).
- Limit: Multi-document and whole-document questions rely on map-reduce; evidence beyond the budget is truncated with a caption (`ui/views.py:840-844`).
- Scaling path: Raise `--ctx` only after re-validating VRAM headroom on the target GPU.

**Whole-document chunk cap:**
- Current capacity: `fetch_document_chunks(doc_id, limit=500)` (`retrieval/hybrid_retriever.py:641`), `chunk_cap_reached` flag propagated to `RetrievalResult` (`core/models.py:191-194`).
- Limit: Documents with more than 500 chunks truncate at the cap; the UI warns via `chunk_cap_reached` (`ui/views.py:840-844`) but the answer still omits tail pages.
- Scaling path: Page-range paging or per-page summarization for very large documents.

**SQLite single-writer:**
- Current capacity: WAL mode with bounded retries (3 attempts, jitter) in `core/doc_store.py`.
- Limit: Concurrent ingest + summarizer cache writes can hit `SQLITE_BUSY`; retries mask but do not eliminate contention.
- Scaling path: Keep writes serialized through the UI services; do not add background writers.

## Dependencies at Risk

**Reproducibility gap between lockfile and unpinned requirements:**
- Risk: `requirements-lock.txt` is the claimed reproducible artifact, but `Dockerfile:25-27` installs `requirements.txt`, which carries open ranges: `docling>=2.0.0`, `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `litellm>=1.50.0`, `pymupdf>=1.24.0`, `numpy>=1.26.0,<3.0.0`.
- Impact: The Docker build and local `pip install -r requirements.txt` can resolve different versions than CI (which uses the lockfile), producing "works in CI, breaks in container" failures; the comment "100% reproducible environments" in `Dockerfile` is inaccurate.
- Migration plan: Install from `requirements-lock.txt` in the Dockerfile (as CI does) and regenerate the lock with `uv pip compile` when bumping.

**Fast-moving extraction stack (docling, onnxruntime/RapidOCR, PyMuPDF):**
- Risk: Docling `>=2.0.0` and `lancedb>=0.17.0` allow major-version jumps; the code already branches on LanceDB capabilities (`hasattr(self._table, "merge_insert")`, `retrieval/hybrid_retriever.py:552`) and on Python version for OCR (`rapidocr-onnxruntime` vs `rapidocr` in `requirements.txt`).
- Impact: Upgrade breakage concentrated in `ingestion/docling_reader.py`, `ingestion/ocr_fallback.py`, `retrieval/hybrid_retriever.py`.
- Migration plan: Pin upper bounds in `requirements.txt`, add a dedicated upgrade job, and keep `tests/test_hybrid_retriever.py` capability tests current.

**Legacy model filename vs. actual architecture:**
- Risk: Model file is named `qwen3-vl-...` while contents are Qwen2-VL; identity verification (`core/model_identity.py`, `tests/test_audit_repairs.py:209-220`) is the authoritative check but is skipped when weights are absent (CI).
- Impact: A mismatched LM/mmproj pair would pass CI and fail at runtime with confusing errors.
- Migration plan: Rename with a migration, or assert only in `setup.py download-models` with checksum-enforced artifacts.

**Optional `litellm` and `groq` in the core dependency set:**
- Risk: Both are installed unconditionally, pulling a large dependency tree into a local-first app that may never use cloud inference.
- Impact: Attack surface and install weight for a privacy-focused product.
- Migration plan: Move to an optional extra (`pip install .[cloud]`) and guard imports (already partially guarded via `Groq is None` checks).

## Missing Critical Features

**No `.env.example` / configuration reference:**
- Problem: Operators must read source to discover `RAG_LOG_LEVEL`, `RAG_REQUIRE_CHECKSUMS`, `LLAMA_SERVER_*`, and the non-loopback opt-in.
- Blocks: Reliable non-default deployments (Docker, LAN use, checksum-enforced installs).

**No conversation persistence:**
- Problem: `st.session_state.chat_history` is session-only; `core/doc_store.py` persists documents/chunks/pages/evidence/summaries but not conversation turns. A browser refresh after `reset_in_memory_session` loses all Q&A.
- Blocks: Revisiting prior evidence-grounded answers; audit of cited sources after the session ends.
- Files: `ui/session_state.py`, `core/doc_store.py`

**No automated type checking:**
- Problem: PEP 604 annotations are pervasive (`core/models.py`, `providers/model_provider.py`) but no `mypy`/`pyright` job exists in `.github/workflows/ci.yml` or `pyproject.toml`.
- Blocks: Catching provider interface drift (e.g. a new `BaseModelProvider` method) at CI time.

**No coverage measurement:**
- Problem: `tests/` holds ~9,700 lines / 395 test functions across 35 files, but no `pytest-cov` config or coverage gate exists.
- Blocks: Knowing which of `ui/`, `ingestion/`, `providers/` is actually exercised.

## Test Coverage Gaps

**UI handler paths in `ui/views.py`:**
- What's not tested: The chat handler's retrieval scoping, intent-mismatch branch (`ui/views.py:739-752`), citation chip rendering, and the verification-caption round trip after rerun.
- Files: `ui/views.py`, `tests/test_main_ui.py`
- Risk: The auto-attributed-count bug above survived precisely because this path is only exercised manually.
- Priority: High

**Real provider integrations:**
- What's not tested: Live llama-server streaming, LiteLLM/Groq HTTP error propagation and redaction, SSE partial-chunk handling.
- Files: `providers/llama_cpp_provider.py`, `providers/litellm_provider.py`, `providers/groq_provider.py`
- Risk: Redaction asymmetry and streaming error handling regress unnoticed; tests use mocks (`tests/conftest.py` sets a mock `GROQ_API_KEY`).
- Priority: Medium

**Ingestion failure/rollback paths:**
- What's not tested: Component failure mid-pipeline (Docling fails after some pages, embedding fails after DB insert) and the resulting partial-state cleanup in `ui/ingestion_service.py:260-320`.
- Files: `ui/ingestion_service.py`, `core/doc_store.py`
- Risk: Orphaned chunks or documents marked `indexed` without vectors.
- Priority: High

**Sanitizer adversarial payloads:**
- What's not tested: Novel XSS/egress payload shapes beyond the current pattern set.
- Files: `ui/sanitizer.py`
- Risk: A crafted PDF string reaching `unsafe_allow_html` paths.
- Priority: Medium

**Model identity with real weights:**
- What's not tested: `tests/test_audit_repairs.py:209` is skip-guarded on missing GGUF files, so CI never verifies the installed LM/projector pair.
- Files: `tests/test_audit_repairs.py`, `core/model_identity.py`
- Risk: A mismatched pair ships and fails only at runtime.
- Priority: Medium

**No performance regression guard:**
- What's not tested: Retrieval latency, ingestion throughput, and VRAM ceiling behavior after dependency bumps; `scripts/profile_resources.py` and `scripts/benchmark_*` are manual.
- Files: `scripts/profile_resources.py`, `docs/EVALUATION.md`
- Risk: Silent regressions on the target RTX 3050; recorded evaluation numbers are stale (noted in `docs/CODE_QUALITY_REPORT.md` §5).
- Priority: Medium

---

*Concerns audit: 2026-10-26*
