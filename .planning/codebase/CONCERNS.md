# Codebase Concerns

**Analysis Date:** 2026-10-13

## Release Verdict — GO (with noted residuals)

**Prior NO-GO cleared:** audit commit `619814a` resolved the `requirements-lock.txt` ↔ `requirements.txt` desynchronization, the analytical-VRAM concern, the missing multimodal benchmark, and the session-only purge gap. All four verified against disk on 2026-10-13 (line-level evidence below). **No release-blocking item remains.** Residuals below are ordered by severity and are accepted as known risks, not blockers.

**Verification baseline:** `226 passed` per `.planning/debug/reliability-performance-audit.md:79-81` (`pytest tests/ -q`), `ruff check .` + `ruff format` clean, CI installs strictly from the lockfile (`.github/workflows/ci.yml:28-31`).

## Audit Fix Status — reliability-performance-audit (commit 619814a)

- **P0-1 Lockfile & manifest desync — FIXED and verified.** `requirements-lock.txt:1-3` is a `uv pip compile`-generated transitive lockfile; exact-pin agreement confirmed on disk for every `==` pin in `requirements.txt` (`streamlit==1.42.0` → `requirements-lock.txt:468`, `pypdf==5.3.0` → `:353`, `groq==0.15.0` → `:117`, `sentence-transformers==3.4.1` → `:443`, `python-dotenv==1.0.1` → `:364`, `httpx==0.28.1` → `:127`, `pydantic==2.11.9` → `:322`, `psutil==6.1.1` → `:309`). All former `>=` floors now resolve exactly: `docling==2.138.0` (`:77`), `rapidocr-onnxruntime==1.4.4` (`:393`), `pymupdf==1.28.2` (`:351`), `pillow==11.3.0` (`:284`), `lancedb==0.40.0` (`:185`), `pyarrow==23.0.1` (`:313`), `litellm==1.105.0` (`:197`), `numpy==2.5.2` (`:230`, inside `>=1.26.0,<3.0.0`). CI consumes the lockfile (`.github/workflows/ci.yml:28-31` via `astral-sh/setup-uv@v5`), so docs-path and CI-path can no longer diverge.
- **P0-2 Live VRAM profiling — FIXED (live-sampling path real; model-resident term still projected).** `resource_telemetry.py:34-90` queries `nvidia-smi` live with TTL + `_SAMPLING_LOCK` double-checked sampling; `scripts/profile_resources.py:268-278` uses the live `used_mb` as the DWM term. `.planning/research/RESOURCE_PROFILE.json` records measured RTX 3050 hardware (`total 4096.0 MB`, `used 690.0 MB`, `free 3273.0 MB`), projected peak `3450.0 MB`, headroom `646.0 MB`, `compliant_with_qual_01: true`. Residual: the 1450/450/510/350 MB model terms remain constants — no llama-server-resident RSS/VRAM is ever sampled (see Residual §1).
- **P0-3 Multimodal benchmark — FIXED and verified.** `scripts/benchmark_multimodal.py:1-284` evaluates `dense_table.pdf` / `chart_diagram.pdf` / `clean_digital.pdf`; `.planning/research/MULTIMODAL_BENCHMARK.json` exists with `metrics` + `cases` keys. Retrieval-quality evaluation gap is therefore closed for the shipped corpus (see Residual §4 for RRF-tuning remainder).
- **P1-1 Persistent deletion & cache identity — FIXED and verified.** `DocStore.delete_document` (`doc_store.py:575`) + `purge_all` (`doc_store.py:597`); `HybridRetriever.delete_document` (`hybrid_retriever.py:371`) + `purge_all` (`hybrid_retriever.py:228`); `main.py:297-369` splits "Clear Session" (session reset only) from "Purge All Data" (`doc_store.purge_all()` + retriever `purge_all()`/`close()` + `CACHE_DIR` rmtree + session reset). Paths anchored: `APP_DIR` / `DOC_STORE_PATH` / `CACHE_DIR` (`main.py:86-88`). Summary cache identity now includes pipeline version: `model_version = f"{model_name}:{CONFIG_VERSION}"` (`summarizer.py:330,403`). Tests: `tests/test_doc_store.py:586-659` (cascade + purge-all), `tests/test_hybrid_retriever.py:145,395-409` (deletion + purge-all).
- **P1-2 Redundant work & resource consumption — FIXED and verified.** Process-level `_MODEL_CACHE` + `get_shared_sentence_transformer` (`local_embedding.py:19-42`, wired at `:65`); OCR DPI clamp `min(300, max(72, ...))` (`ocr_fallback.py:97`); visual crop `max_regions: int = 20` cap (`visual_analyzer.py:198-225`); `truncation_meta` reporting (`prompt_budget.py:63-132`) consumed as `last_truncation_warning` (`local_llm.py:284`). Tests: `tests/test_local_embedding.py:49-58`, `tests/test_prompt_budget.py:163-172`, `tests/test_visual_analyzer.py:372-381`.
- **P1-3 Deployment scoping — FIXED and verified.** `AiModel` is session-scoped: `st.session_state.ai_model` via `get_session_ai_model` (`main.py:99-106`); no `@st.cache_resource` singleton remains. Single-user workstation design documented (`README.md:187`, `docs/RUNBOOK.md` remote caveats per audit).

## Review Fix Status — Phase 08 (Release Hardening & Evaluation)

All 5 findings from `.planning/phases/08-release-hardening-and-evaluation/08-REVIEW.md` remain **FIXED** (re-verified unchanged):

- **WR-01 Incomplete loopback validation — FIXED.** `llama_cpp_provider.py:44-56` (`ipaddress` loopback check, `allow_remote` opt-in).
- **WR-02 Clear All leaves cloud posture — FIXED**, now split across both buttons (`main.py:312-327` session path, `main.py:363-369` purge path).
- **WR-03 Missing LICENSE — FIXED.** `LICENSE` on disk; `README.md:9,213` resolve.
- **IN-01 Telemetry sampling lock — FIXED.** `resource_telemetry.py` TTL + sampling lock.
- **IN-02 Missing Clear All cloud test — FIXED.** `tests/test_main_ui.py:159-195`.

## Review Fix Status — Phases 02–07

No regressions detected; prior FIXED verdicts stand (Phases 02–07 review fixes per `02/03/04/05/06/07-REVIEW-FIX.md`). Two prior residuals are now **closed by 619814a**: summary-cache pipeline version (P1-1) and per-session embedding copy + DPI/zoom ceilings + silent truncation (P1-2). Remaining carried-forward residuals are folded into the sections below.

## Residual Risks (ordered by severity — none blocking)

**1. Projected VRAM peak still partly analytical (P0-2 remainder):**
- Issue: `scripts/profile_resources.py:267-278` uses one live term (DWM `used_mb`, measured `690.0 MB`) plus four constants (weights 1450 + projector 450 + KV 510 + scratch 350 MB). No llama-server-resident RSS/VRAM is ever sampled; headless/CI falls back to a `487.0 MB` constant (`profile_resources.py:269`).
- Files: `scripts/profile_resources.py:267-296`, `.planning/research/RESOURCE_PROFILE.json`
- Impact: `3450.0 MB` / `646.0 MB` headroom is a planning estimate with a live-measured base, not a model-resident measurement. True ceiling compliance is unproven until a resident run.
- Fix approach: run `scripts/profile_resources.py` on the target RTX 3050 with llama-server resident; record live `nvidia-smi` used-MB per stage into `RESOURCE_PROFILE.json`.

**2. Legacy `cloud_api_key` fallback still live (PRIV-02 / WR-01 remainder):**
- Issue: legacy string initialised at `main.py:73`-area, blanked (not deleted) on Clear Session (`main.py:325-326`), honoured as cross-provider fallback at `litellm_provider.py:67-71`. A stale legacy value supplies a mismatched provider's key on the fallback path.
- Files: `main.py:73,325-326`, `litellm_provider.py:56-71`
- Impact: low (per-provider dict hits first) but nonzero key-contamination path.
- Fix approach: delete the legacy read/write entirely, or record explicit acceptance with removal in the next minor.

**3. Consent invariant is UI-layer-only (no server-side enforcement or audit trail):**
- Issue: guarantee rests on `cloud_mode=False` default, `@st.dialog` consent gate, and `LiteLLMProvider._assert_consent` (`litellm_provider.py:132-136`); no persistent consent record, no per-request re-confirmation.
- Files: `main.py:137-160,219-237`-area, `litellm_provider.py:124-136`, `local_llm.py:162-180`-area
- Impact: no auditability for compliance claims; a future wiring mistake reintroduces silent egress.
- Fix approach: require the session consent flag at `set_cloud_mode` time; log grant/revoke with timestamp.

**4. RRF/hybrid tuning has no recall baseline (P0-3 remainder):**
- Issue: `scripts/benchmark_multimodal.py` proves accuracy/abstention/citation on the shipped corpus, but BM25 + RRF fusion ships with no recall@k / nDCG baseline; `scripts/benchmark_baseline.py` measures latency only.
- Files: `scripts/benchmark_multimodal.py`, `hybrid_retriever.py:415-504`
- Impact: cannot prove hybrid beats dense-only or tune RRF weights/k empirically.
- Fix approach: relevance judgements + recall@k on the generated corpus (`tests/data/corpus/generate_corpus.py`).

**5. Consent-dialog dismiss loop + OCR disclosure wording (Phase 07 remainders):**
- Issue: `show_consent_dialog()` re-fires while toggle-true and unconsented (framework dismiss runs no handler); dialog's stays-on-device list understates that consented cloud transmission includes OCR text/VLM descriptions inside retrieved excerpts.
- Files: `main.py:137-160`, `main.py:111-121`-area
- Impact: UX confusion; informed-consent fidelity gap. No egress risk (unconsented state still blocks `_assert_consent`).
- Fix approach: `on_dismiss` reconciliation resetting toggle/mode to `False`; name OCR/VLM explicitly in the "what leaves" wording.

**6. Singleton `AiModel` retrieval state shared process-wide (Phase 05 remainder):**
- Issue: `last_retrieval_result` (`local_llm.py:44,171,207`-area) is process state; any future `retrieval_result=None` fallback caller validates against whoever queried last.
- Files: `local_llm.py:44,157-158,171,202-207`-area
- Impact: evidence cross-contamination on a shared server the moment a second call site uses the fallback.
- Fix approach: scope retrieval state per-call or require explicit `retrieval_result`.

**7. Working-directory fragility narrowed but watch (P1-1 remainder):**
- Issue: `DOC_STORE_PATH` and `CACHE_DIR` are anchored (`main.py:86-88`); `HybridRetriever` default `db_uri` still resolves its `data/lancedb/` fallback relative to CWD when constructed without an explicit path (e.g. the purge-path `temp_retriever = HybridRetriever()` at `main.py:341-343`).
- Files: `hybrid_retriever.py` default `db_uri`, `main.py:341-343`
- Impact: launching from another directory forks the LanceDB location for that one path.
- Fix approach: default `db_uri` to `Path(__file__).resolve().parent / "data" / "lancedb"`.

**8. Dead fallback branch (narrowed, still present):**
- Issue: `ask_a_question_from_pdf_stream` can still build its own `PdfReader` + `LocalEmbedding` when no index is passed, bypassing `HybridRetriever`/persistence; `main.py` always passes `active_retriever` + `retrieval_result`.
- Files: `local_llm.py:124-128`-area; caller in `main.py` chat loop
- Impact: duplicated ingestion inside inference; dense-only ephemeral results; untested by the app.
- Fix approach: remove the branch or expose as a documented standalone entry point.

## Known Bugs

*No open Known Bugs. Prior items (mock fixture target, README module names) remain resolved; the audit's P0/P1 set is verified fixed above.*

## Security Considerations

**Loopback SSRF guard robust but `allow_remote` is an unguarded escape hatch:**
- Risk: any caller passing `allow_remote=True` with an attacker-controlled URL turns the provider into an SSRF primitive. No user input reaches `base_url`/`allow_remote` today (default `http://127.0.0.1:8080`).
- Files: `llama_cpp_provider.py:23-62`, `local_llm.py` (construction sites)
- Current mitigation: default-deny; loopback-only unless explicitly opted in.
- Recommendations: keep `allow_remote=True` out of any remote-server UI without explicit opt-in + allowlist.

**Prompt injection from document text (residual output-side gap):**
- Risk: input-side isolation fixed (sanitize + bounding + directives), but no output-side check verifies answers don't echo injected directives. VLM descriptions (`visual_analyzer.py`) are model-generated text entering the index — treat as untrusted on retrieval.
- Files: `prompt_budget.py:25-94`, `summarizer.py:110,130,219`-area
- Current mitigation: `<document_context>` isolation + boundary escaping, asserted by `tests/test_prompt_budget.py`.
- Recommendations: answer-side directive-echo scan with an adversarial-chunk test.

**Untrusted PDF parsing in-process:**
- Risk: `pypdf`/Docling/PyMuPDF parse attacker-controlled bytes in-process; no sandbox beyond caps.
- Files: `upload_validation.py:64-110` (`MAX_FILE_MB=50`, `MAX_PAGES=500`), `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`
- Current mitigation: magic-byte check, size/page caps, per-page try/except; `pypdf==5.3.0` exactly pinned and lockfile-verified; DPI/area ceilings added (`ocr_fallback.py:97`, `visual_analyzer.py:198-225`).
- Recommendations: none outstanding beyond a parse timeout/subprocess for hostile input (optional hardening).

**LanceDB filter escaping is quote-doubling only:**
- Risk: hand-rolled per-call-site escaping; a future `where()`/`delete()` interpolation that forgets `.replace` reintroduces the class.
- Files: `hybrid_retriever.py:219,328,357`-area
- Current mitigation: quote-doubling at all sites + regression tests (`tests/test_hybrid_retriever.py:337-341`).
- Recommendations: extract `_escape_filter_literal()` helper.

**Credential handling:**
- Risk: API keys in session memory / logs / commits.
- Files: `litellm_provider.py:50-90`-area, `main.py:72-73,191-202`-area, `.gitignore:1`
- Current mitigation: `.env` gitignored; keys never printed; per-provider dict; Clear Session + Purge All both cleanse (`main.py:312-327,363-369`).
- Recommendations: none outstanding beyond the legacy-fallback decision (Residual §2).

## Performance Bottlenecks

**VLM + OCR resource pressure against the 4 GB ceiling (standing, ceilings now in place):**
- Problem: visual analysis and RapidOCR add per-document latency/memory. Floor + ceiling clamps now exist (DPI `72–300`, zoom `0.5–3.0`, `max_regions=20`) but no pixel-area budget or batching.
- Files: `visual_analyzer.py:143-225`-area, `ocr_fallback.py:80-135`-area, `llama_cpp_provider.py:220-268`-area
- Cause: per-element VLM round-trips; full-page rasterization.
- Improvement path: pixel-area ceiling, bbox-area skip threshold, batch/defer VLM calls; measure with the Phase 6 harness.

**BM25 fallback is full-corpus Python scoring:**
- Problem: `_bm25_search_fallback` tokenises every document per query in pure Python (`hybrid_retriever.py:415-476`-area); O(N·|Q|) per query when native FTS is unavailable.
- Files: `hybrid_retriever.py:415-504`-area
- Cause: no persistent inverted index; `create_fts_index` never called from `main.py`.
- Improvement path: cache tokenised corpus with invalidation on `index_chunks`/`delete_document`; wire `create_fts_index` into `main.py`.

**Context cap truncates multimodal evidence first (standing, now visible):**
- Problem: `prompt_budget.py` bounds input to 4096 tokens; vision descriptions and OCR compete with digital text for one flat budget. Truncation is now surfaced (`truncation_meta` + UI warning per P1-2) rather than silent.
- Files: `prompt_budget.py:53-132`-area, `visual_analyzer.py:220-250`-area
- Cause: single shared budget.
- Improvement path: per-element vision-token caps.

## Fragile Areas

**Non-hybrid chat branch reintroduces CR-02 divergence:**
- Files: `main.py` chat loop (`active_retriever = hybrid or local_embedding`; `else` branch), `local_llm.py:141-159`-area
- Why fragile: when `hybrid_retriever` is `None`, UI chips and LLM context derive from two different queries; chips degrade to filename-only.
- Safe modification: wrap `LocalEmbedding` results into `RetrievalResult` in `main.py`; always pass `retrieval_result=`.
- Test coverage: pre-computed `retrieval_result` covered (`tests/test_local_llm.py`); degraded path untested.

**Provider selection sticky on healthy fallback:**
- Files: `local_llm.py` health-check/re-probe; session-scoped `AiModel` (`main.py:99-106`).
- Why fragile: re-probe fires only on unhealthy; starting on Groq (llama-server down) then local coming up stays on Groq silently.
- Safe modification: "prefer local when reachable" refresh button or background probe.
- Test coverage: construction + unhealthy→healthy covered; healthy-fallback→local switchback not.

**Fallback-store JSON normalises only `bbox`:**
- Files: `hybrid_retriever.py:162-187`-area
- Why fragile: future non-primitive metadata (numpy types, `datetime`, `Path`) raises `TypeError` inside `json.dump`, swallowed as `logger.warning` — persistence silently stops with no UI signal.
- Safe modification: recursive primitive-normalisation or `default=str`; surface failure beyond debug logs.
- Test coverage: BBox round-trip covered; arbitrary-metadata robustness not asserted.

**`close()` in LanceDB mode skips persistence flush:**
- Files: `hybrid_retriever.py:149-154`-area
- Why fragile: LanceDB mode nulls `_table`/`_db` with no flush/FTS checkpoint; session/purge paths can drop handles holding un-checkpointed FTS state.
- Safe modification: checkpoint/flush in `close()` when a table is present, or document LanceDB durability and remove the asymmetry.
- Test coverage: open/close covered; durability-across-close with FTS not asserted.

**Heuristic token counting:**
- Files: `prompt_budget.py:20-25` (chars ÷ 4)
- Why fragile: under-counts code/mangled text; OCR noise skews further; bad estimates can exceed the real window.
- Safe modification: preserve `max_output_tokens` reserve; consider a real tokenizer for the local model.
- Test coverage: bounds verified (`tests/test_prompt_budget.py`); tokenizer fidelity not asserted.

**Silent SSE frame drops:**
- Files: `llama_cpp_provider.py:196-215`-area (malformed `data:` frames `continue` without logging)
- Why fragile: dropped tokens invisible; partial answers look complete.
- Safe modification: log skipped frames at debug level.
- Test coverage: happy-path covered; malformed frames not asserted.

**Large sidebar orchestration loop (grown across Phases 4–7 + audit buttons):**
- Files: `main.py` upload loop (~150+ lines) + chat loop (summarizer + validator wiring) + dual Clear/Purge buttons (`main.py:297-369`)
- Why fragile: validation/dedup/extraction/OCR/visual/LanceDB/persistence/state in one untestable block; ordering bugs easy.
- Safe modification: extract per-file processing into a testable helper.
- Test coverage: none for orchestration paths (purge-logic unit tests only).

## Scaling Limits

**VRAM ceiling (4 GB) — live-based estimate, needs model-resident measurement:**
- Current capacity: projected `3450.0 MB` vs `3800 MB` target (`646.0 MB` headroom) per `.planning/research/RESOURCE_PROFILE.json` — live DWM base (`690.0 MB` measured) + analytical model terms. Live sampling exists (`resource_telemetry.py`, sidebar gauge); `InferenceGate` single-resident invariant holds only if one model stays resident and embeddings/OCR stay on CPU.
- Limit: second model, larger context, or GPU-offloaded OCR triggers shared-memory paging.
- Scaling path: one resident model; reduce `-ngl`/`-c` if needed; cap crop/DPI budgets. Follow-up: RTX 3050 model-resident measurement (Residual §1).

**BM25-from-table recovery capped at 10 000 rows:**
- Current capacity: at most 10 000 LanceDB rows read into memory (`hybrid_retriever.py:427`-area).
- Limit: larger corpora silently exclude tail rows from keyword search after restart; dense unaffected → asymmetric hybrid degradation with no warning.
- Scaling path: paginate recovery; log on truncation.

**SQLite single-file store:**
- Current capacity: single user fine; WAL + `busy_timeout` + FK enforcement (`doc_store.py:81-95`-area). Summaries table grows monotonically (no eviction).
- Limit: concurrent writers on network/OneDrive paths can contend.
- Scaling path: keep DB on local disk; multi-user out of scope.

**LanceDB on-disk growth is append-mostly:**
- Current capacity: `merge_insert("chunk_id")` upserts on re-index (`hybrid_retriever.py:318-324`-area); `purge_all`/`delete_document` now available (`hybrid_retriever.py:228,371`) and wired to Purge All Data (`main.py:336-343`).
- Limit: re-index/delete cycles bloat the table; no `compact_files`/`vacuum` ever invoked.
- Scaling path: periodic maintenance or full re-index utility.

**Unbounded disk caches (chat history FIXED; summary-eviction open):**
- Status: session history bounded (`MAX_CHAT_TURNS=50`); summary cache has model+pipeline-version invalidation (`summarizer.py:330,403`); Purge All Data clears SQLite + LanceDB + `.cache`.
- Issue: SQLite summaries (upsert, never pruned) + LanceDB rows (append-mostly) + per-doc/profile `summary_*` session keys grow monotonically between purges.
- Files: `doc_store.py:438-460`-area, `hybrid_retriever.py:318-334`-area, `main.py` summary session keys
- Fix approach: per-cache caps + LanceDB compaction cadence.

## Dependencies at Risk

**None blocking — lockfile verified.** Former NO-GO (lockfile/requirements divergence) is resolved; CI gates the lockfile. Remaining notes:

**Transitive torch / transformers (via sentence-transformers):**
- Risk: large and platform-sensitive, now exactly locked (`torch==2.14.1`, `transformers==4.57.6` per lockfile) — risk reduced to lockfile-staleness on future bumps.
- Impact: embedding/download breakage on major bumps.
- Migration plan: regenerate via `uv pip compile` on any `requirements.txt` change (CI will fail otherwise).

**`groq_provider.py` redundant beside `litellm_provider.py` (dead-code risk):**
- Risk: `GroqProvider` remains wired while `LiteLLMProvider` covers `groq/llama-3.3-70b-versatile` via the same API. Two Groq paths = two consent/error contracts (`_assert_consent` only on LiteLLM path).
- Files: `groq_provider.py`, `litellm_provider.py`, `local_llm.py:162-180`-area
- Impact: edits may fix one path and miss the other.
- Migration plan: route Groq exclusively through `LiteLLMProvider` and delete `groq_provider.py`, or assert consent on both.

**`reportlab` only in `requirements-test.txt`:**
- Risk: `tests/test_pdf_reader.py` imports `reportlab` at top; plain `requirements.txt` install cannot run the suite.
- Impact: local test runs fail on collection without test deps.
- Migration plan: document test-deps seeding (CI already installs `requirements-test.txt`).

## Missing Critical Features

*No release-blocking gaps. Former blockers (reproducible env, model-resident-adjacent VRAM evidence, persistent purge, benchmark) are closed. Remaining hardening items:*

**Model-resident VRAM measurement (Residual §1):**
- Problem: headline number blends live DWM + analytical model terms; no resident sampling.
- Blocks: full 4 GB ceiling sign-off (not release).
- Fix approach: RTX 3050 run with llama-server resident; live numbers into `RESOURCE_PROFILE.json`.

**Output-side injection check:**
- Problem: input isolation fixed; no answer-side guard against echoed directives from documents/VLM descriptions.
- Blocks: full prompt-injection closure.
- Fix approach: directive-echo scan + adversarial-chunk test.

**`allow_remote` governance for remote servers:**
- Problem: loopback validation correct, but `allow_remote=True` bypass exists with no UI/policy guardrails.
- Blocks: safe remote-server configuration.
- Fix approach: explicit opt-in + allowlist before any remote-server UI ships.

**Consent auditability:**
- Status: dialog gate + per-provider keys + `_assert_consent` + session isolation all shipped.
- Remaining: persistent record, dismiss-loop fix, OCR disclosure wording, legacy-key decision — see Residuals §2, §3, §5.
- Blocks: release-grade consent claims (hardening, not blocker).

## Test Coverage Gaps

**`main.py` UI orchestration (still the top gap):**
- What's not tested: upload flow, dedup, Docling/OCR/visual/LanceDB branches, hybrid restore-on-restart, Clear/Purge orchestration (purge-logic unit tests only), cache writes, chat streaming, error paths, tab/drawer/badge rendering.
- Covered: history bounding, telemetry contracts, `InferenceGate`, Clear/Purge cloud posture, consent session isolation (per audit P1-3 tests in `tests/test_main_ui.py`).
- Files: `main.py`
- Risk: orchestration regressions caught only manually (all prior criticals lived here).
- Priority: High

**Cloud streaming success paths (LiteLLM covered; legacy Groq open):**
- Tested: consent gating, retries, timeouts, MIME sniffing (`tests/test_litellm_provider.py`); consent transitions + isolation + idempotence (`tests/test_cloud_privacy.py`).
- Not tested: `GroqProvider.stream_text`/`generate_text` happy path (only unconfigured-health asserted).
- Files: `groq_provider.py:94-149`-area
- Risk: payload/stream regressions in the legacy provider — resolves itself if deleted.
- Priority: Medium

**VLM/OCR integration wiring:**
- Tested: vision-unavailable degradation (`tests/test_visual_analyzer.py`); isolation filter shape (`tests/test_cloud_privacy.py`); DPI/region caps (`tests/test_visual_analyzer.py:372-381`).
- Not tested: end-to-end upload → OCR → visual → indexed evidence; consent-dialog state machine.
- Files: `main.py` upload wiring, `visual_analyzer.py:211-250`-area, `ocr_fallback.py:232-290`-area
- Risk: CR-01-class wiring regressions green-in-CI/broken-in-browser.
- Priority: High

**Hybrid degraded-mode paths:**
- What's not tested: `LocalEmbedding`-only chat branch, `retrieval_result=None` re-search, BM25 recovery above/below 10k cap, `close()` durability with live table, adversarial-`doc_id` filter escaping on `delete_document`.
- Files: `main.py` chat loop, `local_llm.py:123-159`-area, `hybrid_retriever.py:346-363,424-431`-area
- Risk: the exact cold-start/degraded paths are the least asserted.
- Priority: High

**Summarizer pipeline-version and singleton paths:**
- Partially closed: pipeline-version invalidation now covered via `model_version` mismatch tests (pre-existing `tests/test_cache_invalidation.py` pattern); cross-session `last_retrieval_result` contamination still unasserted.
- Files: `doc_store.py:469-497`-area, `summarizer.py:328-336`-area, `local_llm.py` retrieval state
- Risk: Phase 05 singleton residual has no regression net.
- Priority: Medium

**Error/edge paths:**
- What's not tested: `GroqProvider.analyze_image` `NotImplementedError`; malformed SSE frames; `main.py` provider errors mid-stream.
- Files: `groq_provider.py:151-156`-area, `llama_cpp_provider.py:196-215`-area, `main.py` chat loop
- Risk: silent or ugly failures.
- Priority: Low–Medium

**No coverage measurement:**
- What's not tested: no `pytest-cov` in `requirements-test.txt`, no threshold config.
- Files: `pyproject.toml`, `requirements-test.txt`
- Risk: coverage regresses unnoticed.
- Priority: Low

---

*Concerns audit: 2026-10-13*
