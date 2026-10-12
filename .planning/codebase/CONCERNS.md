# Codebase Concerns

**Analysis Date:** 2026-10-12

## Release Verdict — Go / No-Go

**One NO-GO item blocks release sign-off:** the `requirements-lock.txt` ↔ `requirements.txt` version conflict (see Tech Debt §1). The lockfile disagrees with the pinned requirements on 6 packages, omits 4 shipped runtime deps, and is not consumed by CI — while `README.md:131` and `docs/RUNBOOK.md:48` instruct users to install from it. A user following the docs gets a different (and partly untested) dependency set than CI validated. Regenerate the lockfile from the CI-verified environment (or delete it and pin `requirements.txt` fully) before release.

All 5 findings from `.planning/phases/08-release-hardening-and-evaluation/08-REVIEW.md` are **FIXED** per `08-REVIEW-FIX.md` and re-verified against current source on 2026-10-12 (line-level claims below confirmed via grep/read; `08-REVIEW-FIX.md` reports 218/218 tests, `ruff check` + `ruff format --check` clean).

## Review Fix Status — Phase 08 (Release Hardening & Evaluation)

- **WR-01 Incomplete loopback validation — FIXED.** `llama_cpp_provider.py:44-56` normalises scheme-less input, accepts literal `localhost`, and validates IPs via `ipaddress.ip_address(host).is_loopback` (covers `127.0.1.1`, `127.0.0.2`, full `127.0.0.0/8`, `::1`); non-loopback raises `ValueError` unless `allow_remote=True` (`llama_cpp_provider.py:29,53-56`). Tests: `tests/test_llama_cpp_provider.py:272-275` (remote opt-in) plus loopback-variation cases per `08-REVIEW-FIX.md`.
- **WR-02 Clear All leaves cloud posture — FIXED.** `main.py:302-316` closes `active_cloud_provider`, nulls `_cached_cloud_model`/`_cached_cloud_key`, sets `cloud_mode=False`, `cloud_mode_toggle=False`, `user_consented=False`, resets `cloud_api_keys` to empty per-provider dict, and blanks the legacy `cloud_api_key`. Test: `tests/test_main_ui.py:159` (`test_clear_all_resets_cloud_posture_and_credentials`).
- **WR-03 Missing LICENSE — FIXED.** `LICENSE` exists in repo root (verified on disk); `README.md:9,213` badge/link now resolve. `README.md:77-91` also lists all current modules (`local_llm.py`, `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`, `resource_telemetry.py`) — the stale-module-names concern is resolved.
- **IN-01 Telemetry sampling lock — FIXED.** `resource_telemetry.py:30` adds `_SAMPLING_LOCK = threading.Lock()`; sampling path double-checks the timestamp inside the lock (`resource_telemetry.py:50`), eliminating redundant concurrent `nvidia-smi` spawns.
- **IN-02 Missing Clear All cloud test — FIXED.** `tests/test_main_ui.py:159-195` asserts provider close plus reset of all cloud flags, per-provider keys, and legacy key.

**Prior Phase 8 hardening (still verified present):** TEL-01 TTL caching (`resource_telemetry.py`, `_GPU_CACHE_TTL_SECONDS = 5.0`); SEC-01 loopback SSRF guard (now WR-01-hardened); PRIV-01 OCR/visual disclosure in consent dialog (`main.py:111-125`-area); PRIV-02 legacy write removal — **partially regressed, see Residual §2**; TEST-01 fixture repair (`tests/conftest.py:19-50` targets `groq_provider.Groq`); QUAL-02 `httpx==0.28.1` + `psutil==6.1.1` pins; DOC-01/DOC-02 (`README.md` overhaul, `docs/RUNBOOK.md`, `docs/EVALUATION.md`).

## Review Fix Status — Phase 02 (Local Inference Pipeline)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/02-local-inference-pipeline/02-REVIEW.md` are **FIXED** per `02-REVIEW-FIX.md` (verified in the prior audit):

- **CR-01 XML boundary escape — FIXED.** `sanitize_xml_boundary()` in `prompt_budget.py:25`, applied to user prompt and document context. Test: `tests/test_prompt_budget.py::test_sanitize_xml_boundary`.
- **CR-02 unbounded user prompt — FIXED.** `assemble_grounded_messages` truncates oversized prompts.
- **CR-03 unguarded `st.write_stream` — FIXED.** `main.py` wraps stream render in `try/except Exception` with `[interrupted]` history entry.
- **WR-01…WR-06, IN-01…IN-03 — FIXED.** Provider self-healing re-probe, `close()` lifecycle, Groq error encapsulation, `ProviderCapabilities` validation, single health probe per rerun, empty-image-bytes guard, formatting/instance guards, temperature clamping. Residual provider stickiness retained below (Fragile Areas).

## Review Fix Status — Phase 03 (Multimodal Ingestion & Conditional OCR)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/03-multimodal-ingestion-conditional-ocr/03-REVIEW.md` are **FIXED** per `03-REVIEW-FIX.md`:

- **CR-01 uninitialized `st.session_state.ai_model` — FIXED (variant).** Upload loop uses `getattr(st.session_state, "ai_model", None) or ai_model`.
- **CR-02 missing FK pragma — FIXED.** `doc_store.py` executes `PRAGMA foreign_keys = ON;` in `_connect()`.
- **CR-03 table prepending destroys reading order — FIXED.** `docling_reader.py` interleaves tables by document/bbox order.
- **WR-01…WR-06, IN-01…IN-03 — FIXED** (crop-failure attribution, bbox clipping, empty-bytes OCR guard, partial-text retention, `EvidenceElement.doc_id` validation, `logging` in DoclingReader, monotonic chunk ids, `char_start`/`char_end` for new extractors, dpi/zoom clamping). **Residual:** legacy `pdf_reader.py` still leaves `char_start`/`char_end` unset — see Tech Debt.

## Review Fix Status — Phase 04 (Persistent Hybrid Retrieval)

All 3 Criticals, 6 Warnings, 3 Info items from `.planning/phases/04-persistent-hybrid-retrieval/04-REVIEW.md` are **FIXED** per `04-REVIEW-FIX.md`:

- **CR-01 HybridRetriever never wired — FIXED.** `main.py` imports `HybridRetriever`; session init, upload population, restart restore, Clear All close+null, and primary-retriever chat use all present.
- **CR-02 dual-query divergence — FIXED (primary path).** Single `search_hybrid` → canonical `RetrievalResult` → `source_labels()` display + `retrieval_result=` pass-through (`local_llm.py:121-122`). **Residuals:** `retrieval_result=None` fallback re-search and non-hybrid chip path — see Fragile Areas.
- **CR-03 LanceDB filter injection — FIXED.** Quote-doubling at `hybrid_retriever.py:219,328,357`.
- **WR-01…WR-06, IN-01…IN-03 — FIXED** (fallback dedup, BM25-from-table recovery capped at 10 000 rows, O(N·|Q|) df precompute, BBox serialization, `close()` + context manager, `EvidenceSnippet.doc_id` validation, citation fallbacks, `set_embedding_fn`, evidence stripping). Residuals (10k cap, flush asymmetry, bbox-only normalisation) retained below.

## Review Fix Status — Phase 05 (Grounded Summarization & QA)

All 3 Criticals, 10 Warnings, 5 Info items from `.planning/phases/05-grounded-summarization-and-qa/05-REVIEW.md` are **FIXED** per `05-REVIEW-FIX.md`:

- **CR-01 `current_model._provider` typo — FIXED.** `main.py:255` uses `current_model.provider`. Test: `tests/test_main_ui.py::test_ai_model_provider_attribute_contract`.
- **CR-02 `page_text=None` crash — FIXED.** `summarizer.py:180,199-200,380-384` guards + enriches from `doc_store.get_chunks_for_doc`.
- **CR-03 empty-response grounded pass — FIXED.** `citation_validator.py:106-108` returns `is_valid=False, precision=0.0`.
- **WR-01…WR-10, IN-01…IN-05 — FIXED / DOCUMENTED** (provenance fabrication, model-version cache key, injection directives, `validate_response` wiring, Clear All summary purge, page-ref clamping, abstention matcher, empty-doc `ValueError`, case-insensitive sanitization, mock fidelity). Partial-fix residuals retained below.

## Review Fix Status — Phase 06 (Performance Optimization & Resource Profiling)

All 1 Critical, 3 Warnings, 2 Info items from `.planning/phases/06-performance-optimization-and-resource-profiling/06-REVIEW.md` are **FIXED** per `06-REVIEW-FIX.md`:

- **CR-01 `InferenceGate.release()` corruption — FIXED.** `local_llm.py:55-63` releases before decrementing. Test: `tests/test_concurrency_lock.py::test_unauthorized_release_does_not_corrupt_active_counter`.
- **WR-01 `_LATENCY_HISTORY` race — FIXED.** `resource_telemetry.py:22-23` (`_LATENCY_LOCK`, `MAX_STAGE_HISTORY = 200`).
- **WR-02 orphan assistant turn — FIXED.** `prompt_budget.py:131-152` (`bound_chat_history` pruning); `main.py:389-395` routes appends through it.
- **WR-03/IN-01/IN-02 — FIXED/DOCUMENTED.** Production-function bounding tests, unauthorized-release test, DWM baseline doc. Residuals (analytical VRAM figure, per-rerun telemetry spawn, gate observability, turn-count vs tokens) retained below.

## Review Fix Status — Phase 07 (Optional Cloud Provider & Privacy Controls)

All 1 Critical, 3 Warnings, 2 Info items from `.planning/phases/07-optional-cloud-provider-and-privacy-controls/07-REVIEW.md` are **FIXED** per `07-REVIEW-FIX.md`:

- **CR-01 cloud vision egress at ingestion — FIXED (two layers).** `main.py:406-415` local-only provider filter + `visual_analyzer.py:211-223` defense-in-depth rejection. Test: `tests/test_cloud_privacy.py::test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode`.
- **WR-01 shared key pollution — FIXED (dict-first).** `main.py:72,191-202` per-provider `cloud_api_keys`; `litellm_provider.py:56-65` resolution. **Residual:** legacy fallback read/write still live — see Residual §2.
- **WR-02 pool churn — FIXED.** `local_llm.py:146-152` idempotent no-op; `main.py:219-245` cached provider lifecycle.
- **WR-03 toggle desync — FIXED (button paths).** `key="cloud_mode_toggle"` + explicit resets (`main.py:131-134,147-160,204-208`). **Residual:** framework-dismiss loop — see Residual §3.
- **IN-01/IN-02 — FIXED.** MIME sniffing (`litellm_provider.py:88-98,314`); ingestion-privacy test (8 tests in `tests/test_cloud_privacy.py`).

---

## Tech Debt (ordered by severity)

**1. Lockfile conflicts with pinned requirements — NO-GO, fix before release:**
- Issue: `requirements-lock.txt` contradicts `requirements.txt` on six pins and omits shipped runtime deps:
  - `streamlit 1.42.0` vs `1.65.0`, `sentence-transformers 3.4.1` vs `5.2.3`, `pypdf 5.3.0` vs `6.12.1`, `groq 0.15.0` vs `1.1.1`, `langchain-text-splitters 0.3.6` vs `1.1.3`, `python-dotenv 1.0.1` vs `1.2.2`
  - Lockfile omits `docling`, `rapidocr-onnxruntime`, `pymupdf`, `lancedb` (all shipped features) and instead pins dev-only `pytest`, `ruff`, `reportlab`
- Files: `requirements-lock.txt:1-27`, `requirements.txt:1-17`
- Impact: `README.md:131` + `docs/RUNBOOK.md:48` tell users to `pip install -r requirements-lock.txt`, but CI (`.github/workflows/ci.yml:27-28`) installs `requirements.txt` + `requirements-test.txt` — docs and CI describe different environments, and the docs path is untested. `pypdf` 6.x vs 5.x and `sentence-transformers` 5.x vs 3.x are major-line jumps with real API-break risk.
- Fix approach: regenerate `requirements-lock.txt` from the exact CI-verified environment (`pip freeze` after the `requirements.txt` install passes), or delete the lockfile and point docs at `requirements.txt` until a real freeze exists. Add a CI step that installs from the lockfile (or diffs it) so the two cannot drift again.

**2. Unpinned heavy + native + cloud floors (still open, pre-existing QUAL-02 remainder):**
- Issue: `numpy>=1.26.0,<3.0.0`, `docling>=2.0.0`, `rapidocr-onnxruntime>=1.3.0`, `pymupdf>=1.24.0`, `pillow>=10.2.0`, `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `litellm>=1.50.0` remain open ranges. Only `httpx==0.28.1` and `psutil==6.1.1` were exactly pinned.
- Files: `requirements.txt:7,9-17`
- Impact: non-reproducible installs; native wheels (`lancedb`/`pyarrow`/`pymupdf`/onnxruntime) are Windows-sensitive; `litellm` moves fast with a large transitive tree.
- Fix approach: subsume into the lockfile fix (§1) — exact pins for all runtime deps verified on Windows + CPU-only.

**3. Clear All resets session but not persistent stores (still open):**
- Issue: Clear All (now cloud-aware, `main.py:289-317`) still never calls `delete_document` per doc, never drops the LanceDB `chunks` table or `data/lancedb/`, and never removes `DocStore` rows (`data/documents.db`). Re-upload hits the dedup path and restores from SQLite rather than re-extracting.
- Files: `main.py:289-317`; persistent state in `data/lancedb/`, `DocStore(Path("data/documents.db"))`
- Impact: "forget everything" button is session-clear only; stale rows remain queryable in future sessions; disk grows monotonically.
- Fix approach: decide session-clear vs full-purge semantics and implement (per-`doc_id` delete from `HybridRetriever` + `DocStore`) or rename the button to reflect session-only reset.

**4. Private `_embed_one` passed as the hybrid embedding function:**
- Issue: `main.py` wires `HybridRetriever(embedding_fn=st.session_state.local_embedding._embed_one)` — a private method is load-bearing for all hybrid queries.
- Files: `main.py:206,273`-area, `local_embedding.py:28`, `hybrid_retriever.py:143-147`
- Impact: renaming the private helper silently breaks hybrid construction.
- Fix approach: expose public `embed_one`/`embed_query` on `LocalEmbedding`; keep `set_embedding_fn` for late binding.

**5. Legacy `PdfReader` chunk offsets never populated:**
- Issue: `Chunk.char_start`/`char_end` populated by `docling_reader.py` and `ocr_fallback.py`, but the legacy `pdf_reader.py:77-88` path leaves them `None`.
- Files: `pdf_reader.py:77-88`, `models.py:68-69`
- Impact: legacy-path citations resolve to page granularity only; mixed provenance complicates the citation renderer.
- Fix approach: compute spans during `text_splitter.split_text`, or route through the `docling_reader.py` offset helper.

**6. Hand-rolled provider dispatch:**
- Issue: `AiModel._detect_provider` constructs/probes concrete providers directly instead of consulting a factory.
- Files: `local_llm.py:48-69`-area (dispatch), `local_llm.py:162-180`-area (selection)
- Impact: adding/reordering backends requires editing the orchestrator.
- Fix approach: provider factory/config selection.

**7. Dead fallback branch (narrowed, still present):**
- Issue: `ask_a_question_from_pdf_stream` can still build its own `PdfReader` + `LocalEmbedding` when no index is passed (`local_llm.py:124-128`), bypassing `HybridRetriever`/persistence; `main.py` always passes `active_retriever` + `retrieval_result`.
- Files: `local_llm.py:124-128`; caller in `main.py` chat loop
- Impact: duplicated ingestion inside inference; dense-only ephemeral results; untested by the app.
- Fix approach: remove the branch or expose as a documented standalone entry point.

**8. Working-directory-relative artifact paths:**
- Issue: `data/documents.db`, `data/lancedb/`, `.cache` resolve against process CWD.
- Files: `main.py` upload loop (`DocStore(Path("data/documents.db"))`), `hybrid_retriever.py` default `db_uri`
- Impact: launching from another directory silently forks databases; LanceDB persistence is location-dependent.
- Fix approach: anchor all three to `Path(__file__).resolve().parent`.

## Release Residuals (partial Phase 7/8 fixes — ordered by severity)

**1. Legacy `cloud_api_key` fallback still live (PRIV-02 / WR-01 remainder):**
- Issue: Phase 8 removed the legacy *write* from the key-entry path, but the legacy string survives three places: initialised at `main.py:73` (`("cloud_api_key", "")`), blanked (not deleted) on Clear All (`main.py:315-316`), and honoured as a cross-provider fallback at `litellm_provider.py:67-71` when the per-provider dict misses. A stale legacy value supplies a mismatched provider's key — the exact WR-01 failure mode on that path. The fallback chain is documented as deliberate (`CONVENTIONS.md` secrets-precedence rule), so this is a known-accepted residual, not an oversight — but it must be a conscious release decision.
- Files: `main.py:73,315-316`, `litellm_provider.py:56-71`
- Impact: low (dict hits first) but nonzero: cross-provider key contamination on the fallback path.
- Fix approach: delete the legacy read/write entirely (dict is initialised for all three providers at `main.py:72`); or record explicit acceptance with an expiry (e.g. remove in next minor).

**2. Consent invariant is UI-layer-only (no server-side enforcement or audit trail):**
- Issue: privacy guarantee rests on `cloud_mode=False` default (`main.py:67`), the `@st.dialog` consent gate (`main.py:137-160`), and `LiteLLMProvider._assert_consent` (`litellm_provider.py:132-136`). No persistent consent record, no per-request re-confirmation, and `main.py:231` constructs with literal `user_consented=True` — correctness depends on the outer `if cloud_mode and user_consented` gate (`main.py:219`).
- Files: `main.py:67-72,137-160,219-237`, `litellm_provider.py:124-136`, `local_llm.py:162-180`
- Impact: no auditability for compliance claims; a single future wiring mistake reintroduces silent egress.
- Fix approach: require the session consent flag at `set_cloud_mode` time; log grant/revoke with timestamp; extend negative tests to `AiModel.set_cloud_mode(True)` with an unconsented provider.

**3. Consent-dialog dismiss loop (WR-03 remainder):**
- Issue: `show_consent_dialog()` fires on every rerun while `cloud_toggle_val and not user_consented` (`main.py:154-155`). Framework dismiss (✕/ESC/outside-click) runs no handler, so the toggle stays `True` and the dialog re-fires — a re-trigger loop. No egress risk (unconsented state still blocks `_assert_consent`).
- Files: `main.py:137-160`
- Impact: user confusion; UX-level hardening item before release.
- Fix approach: `on_dismiss` reconciliation resetting `cloud_mode_toggle`/`cloud_mode` to `False`; state-machine unit test.

**4. OCR/VLM disclosure gap at query time:**
- Issue: dialog promises "Extracted text and image OCR" stays on-device (`main.py:116-118`) — true at ingestion — but once Cloud Mode is consented, retrieved excerpts sent to the cloud *include* those OCR texts and VLM descriptions. The "retrieved excerpts will be transmitted" line (`main.py:113-115`) covers it technically, but a user reading only the stays-on-device list may miss it.
- Files: `main.py:111-121`, `main.py:580,688` (cloud captions)
- Impact: informed-consent fidelity gap; low exploitability, medium trust impact.
- Fix approach: name OCR text/VLM descriptions explicitly in the dialog's "what leaves" wording (PRIV-01 follow-up).

**5. Summary cache ignores pipeline version (Phase 05 WR-02 remainder):**
- Issue: cache key is `(sha256, profile, model_version)` (`doc_store.py:469-497`, `summarizer.py:328-332`), but `CONFIG_VERSION` (`models.py`), chunking params, and the `estimate_tokens` heuristic are not keyed. Same bytes re-chunked under a bumped pipeline hit a stale row with a "cached" badge.
- Files: `doc_store.py:469-497`, `summarizer.py:328-332`, `models.py` (`CONFIG_VERSION`)
- Impact: silent stale summaries after chunking/pipeline upgrades.
- Fix approach: add `pipeline_version`/`config_version` column, include in lookup predicate.

**6. Singleton `AiModel` retrieval state shared process-wide (Phase 05 WR-04 remainder):**
- Issue: `last_retrieval_result` (`local_llm.py:44,171,207`) plus the `@st.cache_resource` singleton loader; any future `retrieval_result=None` fallback caller validates against whoever queried last. Documented (`local_llm.py:202`), not eliminated.
- Files: `local_llm.py:44,157-158,171,202-207`
- Impact: evidence cross-contamination on a shared server the moment a second call site uses the fallback.
- Fix approach: scope retrieval state per-call or require explicit `retrieval_result`.

## Known Bugs

*No open Known Bugs — the two previously listed items are resolved: the `mock_groq_client` fixture now targets `groq_provider.Groq` (`tests/conftest.py:19-50`, TEST-01), and `README.md` documents the production architecture including all current modules (`README.md:77-91`, DOC-01 + module-name verification above).*

## Security Considerations

**Loopback SSRF guard is robust but `allow_remote` is an unguarded escape hatch:**
- Risk: `LlamaCppProvider(base_url=...)` validation is now correct for loopback detection (`llama_cpp_provider.py:44-56`), but any caller passing `allow_remote=True` with an attacker-controlled URL turns the provider into an SSRF primitive. No user input reaches `base_url` or `allow_remote` today (all production construction uses the default `http://127.0.0.1:8080`).
- Files: `llama_cpp_provider.py:23-62`, `local_llm.py` (construction sites)
- Current mitigation: default-deny; loopback-only unless explicitly opted in.
- Recommendations: keep `allow_remote=True` out of any future remote-server configuration UI without an explicit user opt-in + scheme/host allowlist; add a test asserting the default constructor rejects a non-loopback URL.

**Prompt injection from document text (residual output-side gap):**
- Risk: input-side isolation is fixed (CR-01 sanitize + CR-02 bounding + WR-03 directive + WR-09 case-insensitive regex), but no output-side check verifies answers don't echo injected directives. VLM descriptions (`visual_analyzer.py`) are model-generated text entering the index — treat as untrusted on retrieval.
- Files: `prompt_budget.py:25-94`, `summarizer.py:110,130,219`
- Current mitigation: `<document_context>` isolation + boundary escaping, asserted by `tests/test_prompt_budget.py`.
- Recommendations: keep directives verbatim when editing templates; consider an answer-side directive-echo scan with an adversarial-chunk test.

**Untrusted PDF parsing in-process:**
- Risk: `pypdf`/Docling/PyMuPDF parse attacker-controlled bytes in-process; no sandbox beyond caps.
- Files: `upload_validation.py:64-110` (`MAX_FILE_MB=50`, `MAX_PAGES=500`), `pdf_reader.py:29-113`, `docling_reader.py:135`, `ocr_fallback.py:67,127`
- Current mitigation: magic-byte check, size/page caps, per-page try/except; `pypdf==5.3.0` exactly pinned.
- Recommendations: exact-pin `pymupdf` (native parser, currently `>=1.24.0`) as part of the lockfile fix; consider a parse timeout/subprocess for hostile input.

**LanceDB filter escaping is quote-doubling only (residual after CR-03):**
- Risk: hand-rolled per-call-site escaping rather than a shared helper; future `where()`/`delete()` interpolation that forgets `.replace` reintroduces the class.
- Files: `hybrid_retriever.py:219,328,357`
- Current mitigation: quote-doubling at all three sites + regression tests.
- Recommendations: extract `_escape_filter_literal()` helper; negative test with `doc_1' OR '1'='1` against `delete_document`.

**Credential handling:**
- Risk: API keys in session memory / logs / commits.
- Files: `litellm_provider.py:50-90` (resolution chain), `main.py:72-73,191-202`, `.gitignore:1`
- Current mitigation: `.env` gitignored; keys never printed; per-provider dict; Clear All now cleanses (`main.py:302-316`).
- Recommendations: none outstanding beyond the legacy-fallback decision (Residual §1).

## Performance Bottlenecks

**Projected VRAM number is analytical, not measured (top release-measurement risk):**
- Problem: `scripts/profile_resources.py:267-278` computes `projected_peak_vram_mb` (3,445 MB) as one live term (`dwm_overhead_mb` from `nvidia-smi`) plus four constants; on headless/CI even the DWM term falls back to a constant, so the CI number is fully analytical. No llama-server resident RSS/VRAM is ever sampled.
- Files: `scripts/profile_resources.py:258-296`, `.planning/research/RESOURCE_PROFILE.json:4-5`
- Cause: model not loaded during profiling.
- Improvement path: run `scripts/profile_resources.py` on the target RTX 3050 with llama-server resident; record live `nvidia-smi` used-MB per stage into `RESOURCE_PROFILE.json`. Treat 3,445 MB as a planning estimate until then. **Release gate along with the lockfile fix.**

**VLM + OCR resource pressure against the 4 GB ceiling (standing):**
- Problem: visual analysis (`visual_analyzer.py` crop → `analyze_image` → VLM) and RapidOCR (ONNX/CPU) add per-document latency/memory the Phase 2 budget did not account for. Floor clamps exist (`max(72, ...)` DPI, `max(0.5, ...)` zoom) but no ceilings.
- Files: `visual_analyzer.py:143-190`, `ocr_fallback.py:80-135`, `llama_cpp_provider.py:220-268`
- Cause: per-element VLM round-trips; full-page rasterization; no batching/pixel budget.
- Improvement path: DPI/pixel-area ceiling (e.g. 300 DPI), bbox-area skip threshold, batch/defer VLM calls; measure with the Phase 6 harness.

**BM25 fallback is full-corpus Python scoring:**
- Problem: `_bm25_search_fallback` tokenises every document per query in pure Python (`hybrid_retriever.py:415-476`); O(N·|Q|) per query when native FTS is unavailable.
- Files: `hybrid_retriever.py:415-476`; native FTS first (`hybrid_retriever.py:491-504`)
- Cause: no persistent inverted index; `create_fts_index` (`hybrid_retriever.py:405-413`) never called from `main.py`.
- Improvement path: cache tokenised corpus with invalidation on `index_chunks`/`delete_document`; wire `create_fts_index` into `main.py`.

**Context cap truncates multimodal evidence first (standing):**
- Problem: `prompt_budget.py` bounds input to 4096 tokens; vision descriptions and OCR compete with digital text for one flat budget; truncation is silent.
- Files: `prompt_budget.py:53-98`, `visual_analyzer.py:220-250`
- Cause: single shared budget.
- Improvement path: per-element vision-token caps; "context truncated" UI indicator.

**Per-session embedding model copy:**
- Problem: `LocalEmbedding` in `st.session_state` → each browser session loads its own `SentenceTransformer`.
- Files: `main.py` session init, `local_embedding.py:12-23`
- Cause: deliberate (per-session index), but weights could be shared.
- Improvement path: cache model weights via `@st.cache_resource` separately from the per-session index.

## Fragile Areas

**Non-hybrid chat branch reintroduces CR-02 divergence (residual):**
- Files: `main.py` chat loop (`active_retriever = hybrid or local_embedding`; `else` branch), `local_llm.py:141-159`
- Why fragile: when `hybrid_retriever` is `None`, UI chips and LLM context derive from two different queries on two paths; chips degrade to filename-only.
- Safe modification: wrap `LocalEmbedding` results into `RetrievalResult` in `main.py`; always pass `retrieval_result=`; keep `else` as degraded-mode shim.
- Test coverage: pre-computed `retrieval_result` covered (`tests/test_local_llm.py`); degraded path untested.

**Provider selection sticky on healthy fallback:**
- Files: `local_llm.py` health-check/re-probe; `AiModel` singleton via cached loader.
- Why fragile: re-probe fires only on unhealthy; starting on Groq (llama-server down) then local coming up stays on Groq silently. For the cloud direction this is now explicit mode-switch (superseded); local-switchback is the manual Revoke button.
- Safe modification: "prefer local when reachable" refresh button or background probe.
- Test coverage: construction + unhealthy→healthy covered; healthy-fallback→local switchback not.

**Shared singleton retrieval state (Phase 05 remainder):**
- Files: `local_llm.py:44,157-158,171,202-207`
- Why fragile: process-wide `last_retrieval_result`; one fallback call site contaminates the next.
- Safe modification: per-call scoping or mandatory explicit `retrieval_result`.
- Test coverage: fallback asserted (`tests/test_citation_validator.py:148-161`), entrenching the contract.

**Fallback-store JSON normalises only `bbox` (residual of WR-04/Phase 04):**
- Files: `hybrid_retriever.py:162-187`
- Why fragile: future non-primitive metadata (numpy types, `datetime`, `Path`) raises `TypeError` inside `json.dump`, swallowed as `logger.warning` — persistence silently stops with no UI signal.
- Safe modification: recursive primitive-normalisation or `default=str`; surface failure beyond debug logs.
- Test coverage: BBox round-trip covered; arbitrary-metadata robustness not asserted.

**`close()` in LanceDB mode skips persistence flush:**
- Files: `hybrid_retriever.py:149-154`
- Why fragile: LanceDB mode nulls `_table`/`_db` with no flush/FTS checkpoint; Clear All (`main.py:294-296`) can drop handles holding un-checkpointed FTS state.
- Safe modification: checkpoint/flush in `close()` when a table is present, or document LanceDB durability and remove the asymmetry.
- Test coverage: open/close covered; durability-across-close with FTS not asserted.

**Heuristic token counting:**
- Files: `prompt_budget.py:20-25` (chars ÷ 4)
- Why fragile: under-counts code/mangled text; OCR noise skews further; bad estimates can exceed the real window.
- Safe modification: preserve `max_output_tokens` reserve; consider a real tokenizer for the local model.
- Test coverage: bounds verified (`tests/test_prompt_budget.py`); tokenizer fidelity not asserted.

**Silent SSE frame drops:**
- Files: `llama_cpp_provider.py:196-215` (malformed `data:` frames `continue` without logging)
- Why fragile: dropped tokens invisible; partial answers look complete.
- Safe modification: log skipped frames at debug level.
- Test coverage: happy-path covered; malformed frames not asserted.

**Large sidebar orchestration loop (grown across Phases 4–7):**
- Files: `main.py` upload loop (~150+ lines) + chat loop (summarizer + validator wiring, `main.py:484,594-622`)
- Why fragile: validation/dedup/extraction/OCR/visual/LanceDB/persistence/state in one untestable block; ordering bugs easy (CR-01/Phase 05 class).
- Safe modification: extract per-file processing into a testable helper.
- Test coverage: none for orchestration paths (purge-logic unit tests only).

## Scaling Limits

**VRAM ceiling (4 GB) — analytical estimate, needs model-resident measurement before release:**
- Current capacity: projected 3,445 MB vs 3,800 MB target (651 MB headroom) per `.planning/research/RESOURCE_PROFILE.json:4-5` — analytical (see Bottlenecks). Live sampling exists (`resource_telemetry.py`, sidebar gauge `main.py:359-384`); `InferenceGate` single-resident invariant (`local_llm.py:26-90`) holds only if one model stays resident and embeddings/OCR stay on CPU.
- Limit: second model, larger context, or GPU-offloaded OCR triggers shared-memory paging.
- Scaling path: one resident model; reduce `-ngl`/`-c` if needed; cap crop/DPI budgets. Release gate: RTX 3050 model-resident measurement.

**BM25-from-table recovery capped at 10 000 rows:**
- Current capacity: at most 10 000 LanceDB rows read into memory (`hybrid_retriever.py:427`).
- Limit: larger corpora silently exclude tail rows from keyword search after restart; dense unaffected → asymmetric hybrid degradation with no warning.
- Scaling path: paginate recovery; log on truncation.

**SQLite single-file store:**
- Current capacity: single user fine; WAL + `busy_timeout` + FK enforcement (`doc_store.py:81-95`). Summaries table grows monotonically (no eviction).
- Limit: concurrent writers on network/OneDrive paths can contend.
- Scaling path: keep DB on local disk; multi-user out of scope.

**LanceDB on-disk growth is append-mostly:**
- Current capacity: `merge_insert("chunk_id")` upserts on re-index (`hybrid_retriever.py:318-324`); legacy delete-then-add (`hybrid_retriever.py:325-334`) + no-purge Clear All leave stale rows/tombstones in `data/lancedb/`.
- Limit: re-index/delete cycles bloat the table; no `compact_files`/`vacuum` ever invoked.
- Scaling path: periodic maintenance or full re-index utility.

**Unbounded disk caches (Phase 6 — chat history FIXED, disk open):**
- Status: session history bounded (`MAX_CHAT_TURNS=50`, `main.py:38,389-395`); summary cache has model-version invalidation (`doc_store.py:469-497`).
- Issue: SQLite summaries (upsert, never pruned) + LanceDB rows (append-mostly) + per-doc/profile `summary_*` session keys grow monotonically.
- Files: `doc_store.py:438-460`, `hybrid_retriever.py:318-334`, `main.py:622-636`
- Fix approach: per-cache caps + LanceDB compaction cadence; counts already in sidebar (`main.py:383-384`).

## Dependencies at Risk

**Lockfile / requirements divergence (NO-GO — see Tech Debt §1):**
- Risk: two files claim to define the environment and disagree on 6 pins; CI and docs consume different files.
- Impact: release installs are undefined — neither file alone is trustworthy.
- Migration plan: regenerate lockfile from CI-verified env; CI-gate the lockfile.

**Unpinned native + cloud floors (`docling`, `rapidocr-onnxruntime`, `pymupdf`, `pillow`, `lancedb`, `pyarrow`, `litellm`):**
- Risk: `>=` floors on large/fast-moving/native packages (`requirements.txt:7,9-17`); Windows wheel + CUDA/CPU-variant sensitivity; `lancedb`/`pyarrow` minor bumps can shift FTS/table-compat; `pymupdf`/`pillow` have CVE history.
- Impact: transitive bump can break parsing, OCR, search, or model download.
- Migration plan: exact pins verified on Windows + CPU-only (fold into lockfile fix).

**Transitive torch / transformers (via sentence-transformers):**
- Risk: unpinned; large and platform-sensitive.
- Impact: embedding/download breakage.
- Migration plan: pin transitives or lock; model (`all-MiniLM-L6-v2`) itself is stable.

**`groq_provider.py` redundant beside `litellm_provider.py` (dead-code risk):**
- Risk: `GroqProvider` (`groq_provider.py`) remains wired while `LiteLLMProvider` covers `groq/llama-3.3-70b-versatile` via the same API. Two Groq paths = two consent/error contracts (`_assert_consent` only on LiteLLM path).
- Files: `groq_provider.py`, `litellm_provider.py`, `local_llm.py:162-180`
- Impact: edits may fix one path and miss the other.
- Migration plan: route Groq exclusively through `LiteLLMProvider` and delete `groq_provider.py`, or document both and assert consent on both.

**`reportlab` only in `requirements-test.txt`:**
- Risk: `tests/test_pdf_reader.py` imports `reportlab` at top; plain `requirements.txt` install cannot run the suite.
- Impact: local test runs fail on collection without test deps.
- Migration plan: document test-deps seeding (CI already installs `requirements-test.txt`).

## Missing Critical Features

**Reproducible environment (NO-GO — see Tech Debt §1):**
- Problem: no trustworthy lockfile; docs/CI disagree.
- Blocks: release sign-off.
- Fix approach: regenerate + CI-gate `requirements-lock.txt`.

**Model-resident VRAM measurement:**
- Problem: 3,445 MB headline is analytical (constants + DWM term, no resident sampling).
- Blocks: 4 GB ceiling sign-off.
- Fix approach: RTX 3050 run with llama-server resident; live numbers into `RESOURCE_PROFILE.json`.

**Output-side injection check:**
- Problem: input isolation fixed; no answer-side guard against echoed directives from documents/VLM descriptions.
- Blocks: full prompt-injection closure.
- Fix approach: directive-echo scan + adversarial-chunk test.

**`allow_remote` governance for remote servers:**
- Problem: loopback validation correct, but `allow_remote=True` bypass exists with no UI/policy guardrails.
- Blocks: safe remote-server configuration.
- Fix approach: explicit opt-in + allowlist before any remote-server UI ships.

**Retrieval quality evaluation:**
- Problem: BM25 + RRF fusion ships with no recall@k / nDCG baseline; `scripts/benchmark_baseline.py` measures latency only.
- Blocks: knowing hybrid beats dense-only; tuning RRF weights/k.
- Fix approach: relevance judgements + recall@k on the generated corpus (`tests/data/corpus/generate_corpus.py`).

**Consent auditability (Phase 07 residual):**
- Status: dialog gate + per-provider keys + `_assert_consent` + captions/attribution all shipped (`main.py:108-245`, `litellm_provider.py:124-136`).
- Remaining: persistent record, dismiss-loop fix, OCR disclosure wording, legacy-key decision — see Release Residuals §1–4.
- Blocks: release-grade consent claims.

## Test Coverage Gaps

**`main.py` UI orchestration (still the top gap):**
- What's not tested: upload flow, dedup, Docling/OCR/visual/LanceDB branches, hybrid restore-on-restart, Clear All orchestration (purge logic covered: `tests/test_main_ui.py:140-195`), cache writes, chat streaming, error paths, tab/drawer/badge rendering.
- Covered in Phases 6–8: history bounding (`tests/test_cache_invalidation.py:15-38`), telemetry contracts, `InferenceGate` (`tests/test_concurrency_lock.py`, 8 tests), telemetry parsing/snapshot (`tests/test_resource_telemetry.py`, 10 tests), Clear All summary + cloud purge (`tests/test_main_ui.py:140-195`), loopback variations (`tests/test_llama_cpp_provider.py`).
- Files: `main.py`
- Risk: orchestration regressions caught only manually (all prior criticals lived here).
- Priority: High

**Cloud streaming success paths (LiteLLM covered; legacy Groq open):**
- Tested: consent gating, retries, timeouts, MIME sniffing (`tests/test_litellm_provider.py`, 11 tests); consent transitions + isolation + idempotence (`tests/test_cloud_privacy.py`, 8 tests).
- Not tested: `GroqProvider.stream_text`/`generate_text` happy path (only unconfigured-health asserted).
- Files: `groq_provider.py:94-149`
- Risk: payload/stream regressions in the legacy provider — resolves itself if deleted (see Dependencies at Risk).
- Priority: Medium

**VLM/OCR integration wiring:**
- Tested: vision-unavailable degradation (`tests/test_visual_analyzer.py`, 7 tests); isolation filter shape (`tests/test_cloud_privacy.py`).
- Not tested: end-to-end upload → OCR → visual → indexed evidence; `main.py:402-417` wiring; consent-dialog state machine.
- Files: `main.py:402-417`, `main.py:108-245`, `visual_analyzer.py:211-250`, `ocr_fallback.py:232-290`
- Risk: CR-01-class wiring regressions green-in-CI/broken-in-browser.
- Priority: High

**Hybrid degraded-mode paths:**
- What's not tested: `LocalEmbedding`-only chat branch, `retrieval_result=None` re-search (`local_llm.py:123-159`), BM25 recovery above/below 10k cap, `close()` durability with live table, adversarial-`doc_id` filter escaping on `delete_document`.
- Files: `main.py` chat loop, `local_llm.py:123-159`, `hybrid_retriever.py:346-363,424-431`
- Risk: the exact cold-start/degraded paths are the least asserted.
- Priority: High

**Summarizer pipeline-version and singleton paths:**
- What's not tested: cache behaviour across `CONFIG_VERSION`/chunking changes; cross-session `last_retrieval_result` contamination.
- Files: `doc_store.py:469-497`, `summarizer.py:328-332`, `local_llm.py:44,171,207`
- Risk: Phase 05 residuals have no regression net.
- Priority: Medium

**Error/edge paths:**
- What's not tested: `GroqProvider.analyze_image` `NotImplementedError`; malformed SSE frames; `main.py` provider errors mid-stream.
- Files: `groq_provider.py:151-156`, `llama_cpp_provider.py:196-215`, `main.py` chat loop
- Risk: silent or ugly failures.
- Priority: Low–Medium

**No coverage measurement:**
- What's not tested: no `pytest-cov` in `requirements-test.txt`, no threshold config.
- Files: `pyproject.toml`, `requirements-test.txt`
- Risk: coverage regresses unnoticed.
- Priority: Low

---

*Concerns audit: 2026-10-12*
