<!-- refreshed: 2026-10-29 -->
# Codebase Concerns

**Analysis Date:** 2026-10-29

Scope: full repository (`main.py`, `start.py`, `setup.py`, `core/`, `ingestion/`, `retrieval/`, `providers/`, `ui/`, `tests/`, `scripts/`, packaging + CI). Approximately 26,800 Python lines across application code, tests, and scripts. Every item below was read in source; line references are current at analysis time.

## Tech Debt

**C1 — Silent exception swallowing across every pipeline stage (High):**
- Issue: Broad `except Exception` blocks log at `debug`/`warning` and continue with degraded or fabricated-empty results. Failures become invisible to the operator and untestable.
- Files: `core/resource_telemetry.py:89,142,189`; `ingestion/docling_reader.py:140,224,415`; `ingestion/ocr_fallback.py:123,179,201,352`; `ingestion/pdf_reader.py:41,119`; `ingestion/upload_validation.py:42,53,149`; `ingestion/visual_analyzer.py:149,281,295`; `retrieval/hybrid_retriever.py:219,249,264,287,396,435,548,569,571,632,829,849`.
- Impact: A PDF that fails Docling → silently re-parsed by pypdf with worse fidelity; a failed LanceDB write → silently falls back to the JSON mirror; a failed embedding → that chunk is skipped with no user-visible signal that answers are incomplete. Root-cause debugging requires turning on `debug` logs (default `RAG_LOG_LEVEL=INFO`).
- Fix approach: Introduce typed degradation (`DegradationEvent(code, stage, doc_id, detail)`) collected per ingestion/turn and surfaced in `IngestionResult` (`ui/ingestion_service.py:28-40`) and the Diagnostics workspace. Narrow `except` clauses to the exceptions actually expected (`OSError`, `ValueError`, `ImportError`, `sqlite3.OperationalError`, `lancedb` errors). Reserve `except Exception` only where a doc must never abort others, and always `logger.warning(..., exc_info=True)`.

**C2 — `CONFIG_VERSION` is overloaded as both chunking and LLM-cache version (High):**
- Issue: `core/models.py:14` defines `CONFIG_VERSION = "docling-1000-200-v1"`, which only describes chunking (1000/200). It is reused as the summary/prompt cache discriminator at `core/summarizer.py:504` and `core/summarizer.py:583` (`model_version = f"{model_name}:{CONFIG_VERSION}:{length}"`), and duplicated in two places.
- Files: `core/models.py:14`, `core/summarizer.py:504,583`, `core/doc_store.py:690-701`, `ui/views.py:948`.
- Impact: Editing `PROFILE_SYSTEM_INSTRUCTIONS` or `MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE` (`core/summarizer.py:44,127,139`) does not invalidate cached summaries → users see stale text produced by an older prompt. Conversely, bumping the chunking version nukes all summaries and the whole `.cache/` tree unnecessarily. `SummaryResult.model_version` therefore does not mean what it claims.
- Fix approach: Split into `CHUNKING_VERSION` (cache dir only, `core/models.py:17-30`) and `PROMPT_VERSION`/`SUMMARY_LOGIC_VERSION`; compose `model_version` from `model_name + PROMPT_VERSION + length` via a single helper used by both call sites.

**C3 — Summary prompt/instruction drift between code and docs (Medium):**
- Issue: `docs/EVALUATION.md` §6–7 still describes personas "Executive, Technical, Action Items, ELI5, TL;DR" and JSON summary files; the implementation ships `overview / detailed / study_notes / tables_figures / findings` (`core/summarizer.py:5-6,44`) persisted in SQLite (`core/doc_store.py:679-712`).
- Files: `docs/EVALUATION.md`, `docs/REQUIREMENTS_TRACEABILITY.md`, `core/summarizer.py`, `core/models.py`.
- Impact: Evaluators score against nonexistent profiles; traceability marks QUAL-01/NFR-01 as "Partial" with live VRAM benchmarks "UNTESTED", so nobody can tell whether the 4 GB target was ever measured.
- Fix approach: Regenerate EVALUATION.md profile matrix from `VALID_SUMMARY_PROFILES`; add a doc test that asserts the documented profile list equals the code list; record actual benchmark output from `scripts/benchmark_baseline.py` in the traceability table.

**C4 — Schema migrations outrun the documented schema (Medium):**
- Issue: `core/doc_store.py` migrates through v5, while `CLAUDE.md` documents "schema migrations v1–v4".
- Files: `core/doc_store.py:60-140` (migration ladder), `CLAUDE.md` (stack/conventions blocks).
- Impact: Anyone writing a new migration copies the wrong baseline; reviewers miss the tombstone columns added in v5 (`deleted_at`, `indexed`/`vector_status`).
- Fix approach: Update `CLAUDE.md` and add an assertion in tests that `CURRENT_SCHEMA_VERSION` equals the highest documented migration.

**C5 — Dead and misnamed code in the PDF reader (Low):**
- Issue: `extract_small_portion_of_the_pdf(self, min=0, max=None)` shadows builtins, and a commented-out demonstration block remains.
- Files: `ingestion/pdf_reader.py:146-170`.
- Impact: Confusing public surface; `min`/`max` shadowing is a lint-adjacent trap, and callers passing `max=0` silently hit falsy-default logic.
- Fix approach: Rename to `extract_page_range(self, start_page=0, end_page=None)`, delete the commented demo block.

**C6 — Duplicated constants that must stay in sync (Low):**
- Issue: `MAX_CHAT_TURNS = 50` is defined twice (`main.py:58`, `ui/views.py:38`), and the 50 MB upload cap exists three times: `ingestion/upload_validation.py:18` (`MAX_FILE_MB`), `.streamlit/config.toml` (`maxUploadSize = 50`), and README copy.
- Files: `main.py:58`, `ui/views.py:38,300-304`, `ingestion/upload_validation.py:18`, `.streamlit/config.toml`.
- Impact: Changing one leaves a hidden second cap that rejects or accepts unexpectedly (Streamlit rejects before `validate_upload` runs, producing a different error message).
- Fix approach: Single source in `core/models.py` (already home to `CONFIG_VERSION`), imported by UI and used to document the config.toml value; note the duplication in `config.toml` comment.

**C7 — Providers layer imports Streamlit (Medium):**
- Issue: `providers/litellm_provider.py:60,77` does `import streamlit as st` inside `_resolve_api_key_for_model` to read `st.session_state`/`st.secrets`, and falls back to `os.environ` (`:88-89`).
- Files: `providers/litellm_provider.py:45-89`.
- Impact: Core inference code depends on the web framework; it cannot be unit-tested without a Streamlit runtime, and key precedence (session → secrets → env) is invisible at the call site. Silent env fallback can transmit to a cloud provider using a key the user forgot exists.
- Fix approach: Pass the resolved key explicitly from `main.py`/`ui/views.py` into `LiteLLMProvider(api_key=...)`; keep env fallback only when `RAG_ALLOW_ENV_KEYS=1` and log which source won.

**C8 — `EMBEDDING_MAX_LENGTH` is documented but not applied (Low):**
- Issue: `retrieval/local_embedding.py:29` defines `EMBEDDING_MAX_LENGTH = 256`, and the `get_embeddings()` docstring at `:93-98` claims it passes `max_length=EMBEDDING_MAX_LENGTH` to `encode()`, but the actual call at `:100-106` omits it. `tests/test_retrieval_semantic.py:59-64` only asserts the constant's value.
- Files: `retrieval/local_embedding.py:29,93-106`, `tests/test_retrieval_semantic.py:59-64`.
- Impact: The truncation boundary is whatever the tokenizer/model defaults to, not the documented 256; long chunks can embed differently than the comment promises, and the test gives false confidence.
- Fix approach: Pass `max_length=EMBEDDING_MAX_LENGTH, truncation=True` to `encode()`, or delete the constant/docstring claim and document the model default; add a test that encodes a >256-token string and asserts the expected truncation behavior.

**C9 — Unused `safe_has_secret` helper in the startup path (Low):**
- Issue: `main.py:74-78` defines `safe_has_secret()` but no caller exists. It also catches only `FileNotFoundError`, `KeyError`, and `AttributeError`, not `RuntimeError`, which Streamlit raises when secrets are accessed without a `secrets.toml`.
- Files: `main.py:74-78`, `providers/groq_provider.py:48`, `providers/litellm_provider.py:77-83`.
- Impact: Dead code suggests a safety check that is not actually used; a future caller can still crash on missing secrets.
- Fix approach: Remove it, or fix it to catch `RuntimeError` and use it consistently in every `st.secrets` access.

## Known Bugs

**B1 — Live chat streaming renders unsanitized model output (High):**
- Symptoms: During generation, tokens are written straight to markdown with no sanitization (`stream_placeholder.markdown("".join(response_chunks))` at `ui/views.py:778`), so an `![](http://attacker/x.png)` or `[x](http://attacker)` emitted by the model or echoed from a poisoned document triggers an outbound browser request before `sanitize_display_markdown` ever runs (it is applied only when history is re-rendered at `ui/views.py:620,683`).
- Files: `ui/views.py:774-778` (raw stream), `ui/views.py:620,683` (sanitized history path), `ui/sanitizer.py:130`.
- Trigger: Upload a PDF containing an image link or injection text that asks the model to reproduce it; observe the browser devtools network tab during streaming.
- Workaround: None; the post-`st.rerun()` render is safe, but the leak already happened.
- Fix: Sanitize each accumulated buffer before `markdown()` (throttle to every N tokens to bound cost), or stream into `st.write_stream` with a sanitizing wrapper. Add a regression test asserting `sanitize_display_markdown` is on the streaming path.

**B2 — User prompt is echoed with `st.markdown` unescaped (Medium):**
- Symptoms: `st.markdown(effective_prompt)` renders the raw user string, so a pasted question containing markdown image syntax or HTML triggers rendering/egress and can visually spoof UI chrome.
- Files: `ui/views.py:715-718`.
- Trigger: Paste `![](https://example.com/pixel.png)` as a question.
- Fix: Render prompts via `st.text`/`st.markdown(html.escape(...))` or through `sanitize_display_markdown`; prompts are user-authored and never need rich rendering.

**B3 — Cloud-mode fallback path can raise out of the error handler (Medium):**
- Symptoms: When cloud sync fails, the handler calls `ai_model.set_cloud_mode(False)` unguarded; that path calls `self.close()` then `_detect_provider()` (`core/local_llm.py:204-206,208-224`), which raises `ValueError` if `LLAMA_SERVER_URL` is configured as a non-loopback host. The exception escapes the `except` block, producing a Streamlit error page after `self.provider` was already closed.
- Files: `main.py:228-264`, `core/local_llm.py:193-224`.
- Trigger: Set `LLAMA_SERVER_URL=http://192.168.1.10:8080`, enable cloud mode with a bad key, then retry.
- Fix: Wrap the fallback in its own `try/except`, construct the new provider *before* `close()` (build-then-swap), and never leave `self.provider` referencing a closed client.

**B4 — OCR time budget is advisory; a hung inference blocks ingestion past the cap (Medium):**
- Symptoms: `MAX_OCR_SECONDS_PER_DOC = 300.0` is only checked before submitting a task (`ingestion/ocr_fallback.py:452-456,475`), and the drain loop calls `wait(pending, return_when=FIRST_COMPLETED)` with no timeout (`:505`). `ThreadPoolExecutor.__exit__` joins every worker, so a single pathological page can stall the whole ingestion well past 300 s with no cancellation path.
- Files: `ingestion/ocr_fallback.py:34-35,196-199,483-515`.
- Trigger: A very large vector/photo page (or a corrupted ONNX input) that makes `rapidocr` take minutes on one crop.
- Fix: Give `wait()` a deadline-driven `timeout=remaining`, treat unfinished futures as `time_budget_exceeded`, and use `executor.shutdown(wait=False, cancel_futures=True)` with an explicit note that orphaned threads may still run (document the residual risk); better, move OCR to a subprocess so it can be killed.

**B5 — `_ocr_lock` serializes all recognizer calls, so "batch OCR across threads" only parallelizes rasterization (Medium):**
- Symptoms: The comment claims multi-threaded batch speedup (`ingestion/ocr_fallback.py:481`), but `_ocr_lock` (`:117,197`) wraps recognizer invocation, so effective OCR throughput is single-threaded while up to 4 threads hold page rasters in memory. Peak RAM ≈ 4 × rendered page bytes (each up to `MAX_RENDER_BYTES = 64 MB`, `:27-30`).
- Files: `ingestion/ocr_fallback.py:27-30,117,196-204,480-483`.
- Impact: The stated performance fix does not deliver throughput gains on 4 GB-class machines and can inflate peak RSS to ~256 MB of rasters alone.
- Fix: Either honestly serialize (workers=1, simpler memory profile) or give each worker its own recognizer instance if `rapidocr` is thread-safe; verify with `scripts/profile_resources.py`.

**B6 — Scanned documents are re-converted by Docling on every `get_paragraphs()` call (Medium):**
- Symptoms: When `page_chunks` is empty (scanned PDF), `get_paragraphs()` re-runs `extract_text()` instead of reusing the stored manifest, doubling the most expensive CPU step per ingestion.
- Files: `ingestion/docling_reader.py:250-300` (extract path) and the `page_chunks` fallback branch.
- Trigger: Ingest a fully scanned PDF and call both `get_chunks()` and `get_paragraphs()` (the ingestion service does).
- Fix: Memoize the converted `DoclingDocument` per reader instance keyed by sha256, or have the ingestion service convert once and pass page chunks down.

**B7 — Duplicate `model_version` computation and a non-unique summary cache key (Medium):**
- Symptoms: `ON CONFLICT(sha256, profile)` (`core/doc_store.py:695`) means only one model version and one summary length per (document, profile) can exist; the second model or length overwrites the first, and `get_summary` then reports a version mismatch (`:738-743`) and re-summarizes on every switch back. `model_version` is also computed twice (`core/summarizer.py:504,583`) and includes `length` (`ui/views.py:948`).
- Files: `core/doc_store.py:679-760`, `core/summarizer.py:486-600`, `ui/views.py:41-81,948`.
- Impact: A/B-ing local vs cloud models, or generating a concise summary after a detailed one, silently destroys the other cache; `cached=True` results are unreachable after a switch.
- Fix: `ON CONFLICT(sha256, profile, model_version)` with the extra column in the unique index (migration v6) and a retention policy (keep N most recent per profile).

**B8 — Placeholder visual elements are persisted but never indexed (Low):**
- Symptoms: `[Visual element: ...]` fallback `EvidenceElement` rows are written to SQLite (`ui/ingestion_service.py:252-259`) yet filtered out of the vector index (`retrieval/hybrid_retriever.py:601-603`). SQLite and the retrieval index therefore disagree about which evidence exists; a later reindex can change the evidence pool without changing the catalog.
- Files: `ingestion/visual_analyzer.py:297-305`, `ui/ingestion_service.py:252-259`, `retrieval/hybrid_retriever.py:588-618`.
- Fix: Do not persist placeholders (or mark `indexed=False` and exclude them from every evidence query), and assert SQLite evidence count equals indexed evidence count after ingestion.

**B9 — `Document.model_validate(dict(row))` breaks on unknown columns (Low):**
- Symptoms: `Document` uses `extra="forbid"`; adding a column to `documents` and selecting `*` makes every read raise `ValidationError`.
- Files: `core/doc_store.py:290-295` (`SELECT *` + `Document.model_validate`), `core/models.py` (`model_config`).
- Fix: Select explicit columns, or switch the read model to `extra="ignore"`.

**B10 — Location heuristic misclassifies “currently working” as a location question (High):**
- Symptoms: `asks_for_current_location()` matches the bare word `currently` anywhere in a `where is …` question. Verified: `asks_for_current_location("where is Omprakash currently working")` returns `True`. When the résumé evidence has employment text but no explicit `based in`/`located in`/`lives in` phrase, `ChatTurnService.prepare()` abstains before generation (`ui/chat_controller.py:211-216`). Contractions are false negatives: `"where's Omprakash"` and `"what's his location"` both return `False`.
- Files: `core/query_intent.py:108-141` (question patterns), `ui/chat_controller.py:211-216,291-292` (guard and post-answer override), `tests/test_grounding_contract.py:230-243` (only tests `where does … work`).
- Trigger: Ask “Where is Omprakash currently working?” against a résumé that lists an employer but no residence line.
- Impact: A legitimate employment question is converted into “insufficient evidence”, which looks like a retrieval failure to the user.
- Fix: Exclude employment verbs/nouns (`work`, `working`, `employed`, `job`, `role`, `company`) from the location pattern; add contraction variants (`where's`, `what's`); add positive/negative tests for “currently working”, “where's X”, and “what's his location”.

**B11 — Markdown headings can force summaries to `partial` (Medium):**
- Symptoms: `_evaluate_lexical_support()` splits the entire response into sentences and counts every uncited sentence with at least three content tokens as an uncited claim (`core/citation_validator.py:370-403`). Summaries are markdown-heavy; a heading such as `## Technical Skills & Projects` yields three tokens (`technical`, `skills`, `projects`), increments `uncited_claims`, and forces `grounding_status = "partial"` (`:531-533`) even when every prose claim is cited.
- Files: `core/citation_validator.py:331-408,515-548`, `core/summarizer.py:44-125` (markdown heading templates), `ui/views.py:84-133` (caption rendering).
- Impact: Users see “Partially supported … uncited claim(s)” on well-grounded summaries; the signal loses credibility.
- Fix: Skip markdown heading lines and list labels during claim evaluation, or evaluate only sentences that end with terminal punctuation; add a regression test with a cited summary containing headings.

**B12 — Summary page references are never support-validated (High):**
- Symptoms: The dedicated Summarizer path trusts `(p. X)` strings. `core/summarizer.py` never calls `validate_citations`; `ui/views.py:1003-1021` only checks that page references exist and compares their count to the page total. A model can emit a plausible page number that is not in the evidence or does not support the adjacent sentence.
- Files: `core/summarizer.py:486-600`, `core/citation_validator.py:411-577`, `ui/views.py:1003-1021`.
- Impact: The UI labels a summary “partial coverage” but not “unsupported claim”; wrong page numbers survive into exported markdown, breaking the verifiable-citation promise.
- Fix: Add a summary-specific grounding pass that maps each `(p. X)` to the source page/evidence and checks lexical support, or emit `[E#]`-style evidence IDs during summarization and reuse `validate_citations`.

**B13 — Visual evidence vectors are not repaired during hydration (Medium):**
- Symptoms: Startup repair re-embeds text chunks only (`ui/hydration.py:178-197`); it never calls `get_evidence_for_doc()` or `index_evidence_elements()`. If the LanceDB evidence table is lost or corrupted, a “repaired” library silently loses figure/table retrieval. Manual `LifecycleService.reindex_document()` does reindex evidence (`ui/lifecycle_service.py:191-196`).
- Files: `ui/hydration.py:146-197`, `ui/lifecycle_service.py:162-206`, `core/doc_store.py` (`get_evidence_for_doc`).
- Impact: Figure/table questions return “not found” after a partial index loss even though the evidence rows still exist in SQLite.
- Fix: Include evidence elements in the hydration repair set and verify both text and evidence coverage before setting `_startup_hydrated`.

**B14 — Documents are marked `indexed` before vectors and evidence are written (Medium):**
- Symptoms: `IngestionService` commits SQLite with `status="indexed"` (`ui/ingestion_service.py:239-259`) and only then writes LanceDB (`:272-290`). A crash or LanceDB failure leaves an indexed catalog entry with no vectors until the next startup hydration. Evidence indexing failure is caught and logged without changing document status (`:292-299`).
- Files: `ui/ingestion_service.py:239-319`, `ui/hydration.py:146-197`, `retrieval/hybrid_retriever.py:588-618`.
- Impact: Chat can show the document in the library but retrieve nothing; visual evidence can be permanently absent even though the document says “indexed”.
- Fix: Persist `status="indexing"`, flip to `indexed` only after both vector writes verify, and surface evidence-index failures as a degraded status that repair can target.

**B15 — Environment and lockfile have drifted from each other (High):**
- Symptoms: `requirements-lock.txt` pins `docling==2.138.0` and `torch==2.14.1`, while the active Python 3.13.5 environment has `docling 2.140.0` and `torch 2.6.0+cu124`. `CLAUDE.md:36` still says `pypdf 5.3.0` while `requirements.txt:4` and the installed package are `6.21.4`. `docs/AUDIT_SUMMARY.md:32` still lists Streamlit `1.42.0`; `.planning/research/STACK.md` and several phase research files also reference `1.42.0`.
- Files: `requirements.txt`, `requirements-lock.txt:82,539`, `CLAUDE.md:24-36`, `docs/AUDIT_SUMMARY.md:32`, `docs/DEPENDENCY_AUDIT.md:15-16`, `.planning/research/STACK.md`.
- Impact: The verified lockfile is not what the host runs; Docling minor-version behavior and PyTorch/CUDA differences can change extraction and VRAM use. Documentation claims about the stack are not trustworthy.
- Fix: Reinstall from the lockfile on a clean Python 3.11 environment, regenerate the lock for 3.11 and 3.13, update `CLAUDE.md`/`AUDIT_SUMMARY.md` to the observed versions, and add a CI check that installed versions match the lock.

**B16 — Some summary profiles still force a research-paper structure onto résumés (Medium):**
- Symptoms: The `overview` profile explicitly adapts to résumés (`core/summarizer.py:45-46`), but `detailed` mandates “Background & Problem Context / Methodology / Critical Implications” (`:62-77`) and `findings` mandates risks and recommendations (`:108-124`). A résumé has none of those sections, so the model is invited to invent a “core thesis”, methodology, or limitations.
- Files: `core/summarizer.py:44-125`, `ui/views.py:913-919` (profile choices).
- Impact: The exact “core thesis / environmental studies / benchmarks” failure mode can recur under the `detailed` or `findings` profile even though `overview` is guarded.
- Fix: Add a document-type classifier (résumé, paper, exam, report) and select/adapt the profile template; add a “do not invent sections” guard to every profile; add a résumé fixture regression test for all five profiles.

## Security Considerations

**S1 — Zero-egress invariant is enforced by regex, not by an allowlist renderer (High):**
- Risk: `ui/sanitizer.py` decodes/rewrites destinations with regexes (`_decode_destination:19`, `_is_dangerous_destination:30`, `_is_external_destination:35`, `:130-200`). Known bypass classes: nested/encoded parens in reference definitions, `<style>` blocks with `url()`, CSS `@import`, SVG `<image href>`, and any HTML tag not in the strip list.
- Files: `ui/sanitizer.py`, `ui/views.py:407-463,569-571,654-678`, `ui/components.py` (multiple `unsafe_allow_html=True` or `st.html` calls).
- Current mitigation: `<script>/<iframe>/<object>/<embed>/<style>` stripped; external markdown/HTML links neutralized; document-derived strings passed through `html.escape` (`ui/views.py:1001`, `ui/components.py`).
- Recommendations: Post-render HTML through a real allowlist sanitizer (e.g. `bleach`/`nh3`) before `st.html`, or ban raw HTML in model output entirely (escape everything, render only markdown). Add a fuzz test corpus of bypass strings (`javascript:`, `data:text/html`, `&#x6a;avascript:`, `//evil`, `\\evil`).

**S2 — Cloud API keys live in plaintext session state and env (Medium):**
- Risk: `st.session_state.cloud_api_keys` holds keys for the session lifetime; `redact_text` is best-effort pattern matching (`core/redaction.py:16-29`) and does not know custom key formats. `LiteLLMProvider` reads env vars as a fallback (see C7), so a key in `.env` can be used without the user entering it in the consent flow.
- Files: `ui/views.py:1146-1155`, `core/redaction.py`, `providers/litellm_provider.py:45-89`, `.env.example`.
- Current mitigation: Consent dialog before any cloud call (`main.py:300-345`); keys never logged; `.env` git-ignored.
- Recommendations: Store keys only in `st.secrets`/keyring, drop session persistence on consent revoke (`ui/session_state.py:reset_in_memory_session`), extend redaction with a generic `(sk|gsk|api)[-_]?[A-Za-z0-9]{16,}` pattern, and add a test that no provider logs contain the key.

**S3 — No authentication, and non-loopback exposure is one env var away (Medium):**
- Risk: The app has no auth. `start.py:38-40` refuses non-loopback binds unless `RAG_ALLOW_NON_LOOPBACK=1`, and `.streamlit/config.toml` binds `127.0.0.1`, but the Dockerfile `CMD` binds `0.0.0.0` (`Dockerfile:46`) with `enableCORS = true`. `docker run -p 8501:8501` (rather than the provided compose file, which maps `127.0.0.1:8501`) publishes an unauthenticated document store to the LAN.
- Files: `Dockerfile:46`, `docker-compose.yml:6-9`, `.streamlit/config.toml`, `start.py:38-40`.
- Recommendations: Bind `127.0.0.1` in the Dockerfile and document overriding it; print a loud startup warning when `RAG_ALLOW_NON_LOOPBACK=1`; consider a local-only auth token for non-loopback mode.

**S4 — Untrusted-PDF resource amplification is only partially bounded (Medium):**
- Risk: Page/drawing/figure enumeration happens before caps are applied in the visual analyzer, and region caching is unbounded (`_region_cache`), so a crafted PDF with tens of thousands of vector drawings can consume CPU and RAM before `max_regions` truncates anything.
- Files: `ingestion/visual_analyzer.py:23-26,140-160,270-300`.
- Current mitigation: Render pixel/byte ceilings (`MAX_RENDER_PIXELS = 2048*2048`, `MAX_RENDER_BYTES = 64 MB`, `MIN_RENDER_ZOOM = 0.5`), 500-page / 50 MB upload caps, magic-byte check.
- Recommendations: Cap drawings examined per page, cap total regions examined (not just returned), bound `_region_cache` with an LRU, and abort analysis once the per-doc region cap is reached.

**S5 — Upload validation happens after a full parse (Low):**
- Risk: `MAX_PAGES = 500` is checked after pypdf has built the full page tree; a deep-object PDF can burn memory before rejection. `validate_pdf_bytes` requires `raw.startswith(b"%PDF-")`, so valid files with leading whitespace/BOM are rejected (false negative, not a leak).
- Files: `ingestion/upload_validation.py:20-60,120-160`.
- Recommendations: Read page count from the trailer/xref where possible, stream-validate, reject early on decompression ratio, and relax the magic-byte check to search the first 1 KB.

**S6 — Injection detection is heuristic and post-hoc (Low):**
- Risk: `core/citation_validator.py` flags directives after generation; a detected injection blanks the answer but the prompt already carried the document content (expected), and evasion is trivial via paraphrase.
- Files: `core/citation_validator.py` (pattern list), `ui/views.py:732-737`.
- Recommendations: Keep as defense-in-depth, but rely primarily on XML `<document_context>` isolation (`core/prompt_budget.py`) and on never rendering model output as trusted HTML.

## Performance Bottlenecks

**P1 — Unbounded map-reduce fan-out on long documents (High):**
- Issue: `MAX_BATCH_TOKENS = 2000` (`core/summarizer.py:31`), so a 500-page document becomes hundreds of sequential LLM calls (`for batch in batches:` at `:427`) with no cap and no cancellation; the reduce stage then walks a `while len(current) > 1` loop (`:331`).
- Files: `core/summarizer.py:288-335,411-460`.
- Impact: Hours-long summarization at ~4-bit 2B speeds on CPU/limited GPU; users see a frozen "Summarizing…" spinner with no progress or cancel. Gate timeouts (`InferenceGate.hold(timeout=60)` at `:559`) only apply to gate acquisition, not to the run.
- Improvement path: Emit progress (`st.status`) per batch; enforce a per-profile max batch count with a clear "summarize first N pages / narrow the selection" message; support `stop` via a session flag checked each iteration; consider a cheaper reduce-first strategy for very long docs.

**P2 — Intra-process-only VRAM gate (Medium):**
- Issue: `InferenceGate` is a class-level `threading.RLock` (`core/local_llm.py:35-43`), so it serializes only within one Python process. Multiple Streamlit processes (or `streamlit run` plus scripts) can hit the same `llama-server` concurrently and exceed the 4 GB envelope.
- Files: `core/local_llm.py:35-43,329,345,367`; `core/summarizer.py:559`; `ingestion/visual_analyzer.py:288-290`.
- Improvement path: Add a filesystem lock (`msvcrt`/`filelock` on `data/.inference.lock`) around gate acquisition, or make `llama-server` the authority via `--parallel 1 --cont-batching` and document that the app must be single-instance.

**P3 — Multiple unsynchronized LanceDB writers (Medium):**
- Issue: `DocStore` is process-wide (`@st.cache_resource`, `main.py:143-150`) but `hybrid_retriever` is per-session (`st.session_state`), so two browser tabs hold two `HybridRetriever` instances writing the same `data/lancedb`.
- Files: `main.py:143-150`, `retrieval/hybrid_retriever.py` (write paths), `ui/hydration.py:34`.
- Impact: Intermittent "table not found"/version-conflict errors during concurrent ingestion; possible partial writes.
- Improvement path: Cache the retriever resource process-wide alongside `DocStore`, or add a cross-process write lock around index mutations.

**P4 — In-memory fallback index is O(N) per query and the JSON mirror is O(N) per write (Medium):**
- Issue: When LanceDB is unavailable, `retrieval/vector_index.py:92-190` scans every vector in Python, and `retrieval/hybrid_retriever.py` rewrites the full JSON mirror on each ingestion, duplicating storage.
- Files: `retrieval/vector_index.py:92-190`, `retrieval/hybrid_retriever.py` (mirror persistence + `_has_lancedb` degradation at `:829-830` only warns).
- Impact: Query latency grows linearly (seconds at a few thousand chunks on CPU); the mirror roughly doubles `.cache` size for embedded content.
- Improvement path: Use NumPy matrix scoring with a cached `(N, 384)` float32 array; append-only NDJSON for the mirror instead of full rewrites; surface degradation in the UI status pill rather than only in logs.

**P5 — Eager embedding-model load and never-released global cache (Medium):**
- Issue: `_MODEL_CACHE` in `retrieval/local_embedding.py` is module-global and only cleared by `clear_shared_model_cache()`; the `SentenceTransformer` is constructed eagerly on first use and never unloaded, holding several hundred MB of RSS for the whole Streamlit process lifetime.
- Files: `retrieval/local_embedding.py` (`_MODEL_CACHE`, `ensure_model_loaded`, `clear_shared_model_cache`), `ui/session_state.py`.
- Improvement path: Lazily load on first query (not on view render), bound the cache to one entry, and drop it on idle/provider switch.

**P6 — Telemetry subprocess on a 5 s cadence (Low):**
- Issue: `nvidia-smi` is spawned with a 2 s timeout every 5 s per session (`core/resource_telemetry.py:89-142`, `main.py:_HEALTH_TTL_SECONDS = 5.0`). On laptops without a GPU each call still pays process-spawn cost and is swallowed at debug level.
- Files: `core/resource_telemetry.py`, `main.py:265-300`.
- Improvement path: Cache telemetry process-wide (not per session), back off to 30 s when `nvidia-smi` is absent, and skip entirely if Settings/Diagnostics is not visible.

**P7 — Docling models reloaded per reader instance (Low):**
- Issue: `DoclingReader` constructs a `DocumentConverter` per instance; UI re-creates readers per session, so layout models are re-initialized repeatedly.
- Files: `ingestion/docling_reader.py:90-140`, `ui/ingestion_service.py`.
- Improvement path: Module-level singleton converter guarded by a lock, with `DOCLING_ARTIFACTS_PATH` honored.

**P8 — BM25 fallback loads every row on every query (Medium):**
- Issue: `_bm25_candidate_docs()` calls `query_builder.limit(total)` to materialize every chunk in the scope before Python scoring (`retrieval/hybrid_retriever.py:832-857`). For an unscoped query this is the entire library; with the JSON mirror it copies every document dict per query.
- Files: `retrieval/hybrid_retriever.py:832-877`, `retrieval/vector_index.py`.
- Impact: Query latency and memory grow linearly with library size; at tens of thousands of chunks, hybrid search becomes CPU-bound and can stall a Streamlit rerun.
- Improvement path: Use LanceDB's native FTS/BM25 index for the primary path, keep a precomputed token-count/term-frequency cache for the fallback, and only materialize the top-N candidate rows.

## Fragile Areas

**F1 — `ui/views.py` is a 1,548-line monolith (High):**
- Files: `ui/views.py`.
- Why fragile: It mixes chat streaming, citation rendering, library lifecycle, summarizer orchestration, settings, and diagnostics. Chat streaming (`:710-856`) contains the unsanitized render (B1), the `st.rerun()` re-render contract, and the exception path all in one block; any edit risks breaking citation/session invariants.
- Safe modification: Add new UI behavior as a `render_*` function in a new module (`ui/views_chat.py`, `ui/views_settings.py`) and import it; do not extend the existing functions. Preserve the "session state only through `ui/session_state.py`" rule.
- Test coverage: `tests/test_ui_redesign_apptest.py` exercises the shell, workspace navigation, and citation captions via `AppTest`, but not the streaming sanitizer path, CSS selectors, or narrow viewport behavior.

**F2 — Retrieval degradation chain (Medium):**
- Files: `retrieval/hybrid_retriever.py:219,264,396,548,569,632,829-849`; `retrieval/vector_index.py`; `ui/hydration.py:34`.
- Why fragile: Four silent fallbacks stack (LanceDB → JSON mirror → in-memory index → empty results). Each layer catches exceptions differently, so a partial index can look like "no results" instead of an error, and `hybrid` vs `dense` vs `text` modes are not distinguishable from the UI.
- Safe modification: Change one layer at a time and assert `RetrievalResult` diagnostics (`retrieval_mode`, candidate counts) after each change; never widen an `except` here.
- Test coverage: Good unit coverage of ranking, thin coverage of degradation paths.

**F3 — Delete/purge ordering across three stores (Medium):**
- Files: `ui/lifecycle_service.py`, `core/doc_store.py:820-870` (tombstones), `retrieval/hybrid_retriever.py` (vector delete), `ui/hydration.py:34`.
- Why fragile: Vectors are deleted before SQLite rows; a crash in between leaves an `indexed` document whose vectors are gone. The tombstone mechanism masks this but makes "is this doc really gone?" hard to reason about, and `VACUUM` under WAL can hit locks that retries only partially cover.
- Safe modification: Mark tombstone first, delete vectors, then delete rows; add an idempotent repair pass and a test that simulates a crash between steps.

**F4 — OCR budget + thread lifecycle (Medium):**
- Files: `ingestion/ocr_fallback.py:433-521`.
- Why fragile: Deadline, caps, and the executor drain interact; `future.result()` inside the drain loop will re-raise anything the worker did not catch, aborting the rest of the document even though `_recognize` catches broadly (`:352`).
- Safe modification: Wrap `future.result()` in `try/except`, assert `page_results` covers every page index, and keep the per-page fallback-to-primary-output invariant.

**F5 — Provider/model identity assumptions (Medium):**
- Files: `core/model_identity.py:95-160`, `setup.py:63-84`, `providers/llama_cpp_provider.py:88-116`, `start.py:190-227`.
- Why fragile: `read_gguf_metadata` catches only `OSError`/`ValueError`, so a truncated header raises `struct.error` and crashes the launcher instead of producing a friendly message. The canonical filenames (`qwen3.5-2b-q4_k_m.gguf`, `qwen3.5-2b-mmproj-f16.gguf`) are duplicated in `start.py`, `setup.py`, `docker-compose.yml`, and older `.planning`/debug docs still reference the retired `qwen3-vl-*` pair.
- Safe modification: Catch `struct.error` and `EOFError` in `read_gguf_metadata`/`verify_local_model_pair`, and derive filenames from a single `MODEL_SPEC` constant used by `setup.py`, the launcher, and compose.

**F6 — Streamlit rerun/session-state contract (Low):**
- Files: `main.py:200-300,380-538`, `ui/session_state.py`, `ui/views.py:142-160`.
- Why fragile: Health snapshots are keyed on provider identity (`main.py:272-276`) and throttled by a session timestamp; `st.rerun()` after every chat turn re-executes the whole script. `_active_retriever()` falls back to `local_embedding` (`ui/views.py:142-144`), which has no `delete_document`, so the lifecycle preflight can block deletion in a session where only the embedding helper exists.
- Safe modification: Keep all persistence decisions in `LifecycleService`; do not read/write `st.session_state` from `core/`; add a session-reset test.

**F7 — AMOLED theme depends on undocumented Streamlit DOM selectors (Medium):**
- Files: `ui/theme.py` (`[data-testid=...]`, `:has(...)`, `.st-key-terminal_notifications`), `ui/components.py`, `.streamlit/config.toml`.
- Why fragile: Streamlit does not guarantee test IDs or DOM structure across releases. The code already carries a compatibility branch for the 1.66 avatar test-id rename (`ui/theme.py:120`); the next rename silently drops styling, and the fixed 960 px content width/narrow layout has no automated assertion. `tests/test_ui_redesign_apptest.py` asserts text/widget presence, not computed CSS or viewport behavior.
- Safe modification: Scope new styling through stable `st.container(key=...)` wrappers where possible, keep a selector inventory with the pinned Streamlit version, and add a browser-level visual smoke test (Playwright) for desktop and narrow widths before upgrading Streamlit.

## Scaling Limits

**L1 — Single-user, single-process assumption:**
- Current capacity: One `llama-server`, one Streamlit process, one SQLite writer, one LanceDB directory.
- Limit: Second tab → duplicate retrievers (P3); second process → gate bypass (P2); second app instance → SQLite `BUSY` beyond `WRITE_MAX_ATTEMPTS = 3` (`core/doc_store.py:29`).
- Scaling path: Document the single-instance contract in README; add file locks for inference and index writes; move long ingestion to a background worker with a queue.

**L2 — Chunk/vector growth:**
- Current capacity: 500 pages × ~2 chunks/page (1000 chars / 200 overlap) ≈ 1,000 chunks/doc.
- Limit: In-memory fallback becomes unusable past a few tens of thousands of chunks; JSON mirror rewrites get slow (P4).
- Scaling path: Batch embeddings, persist a NumPy matrix, and require LanceDB for collections above a threshold (fail loudly instead of degrading).

**L3 — Token budget headroom:**
- Current capacity: `DEFAULT_MAX_OUTPUT_TOKENS = 1536`, 4,096 window, 4-chars/token estimate (`core/prompt_budget.py:17`, estimator helper).
- Limit: Tables, code, and CJK text exceed the estimate by 1.5–2×, so prompts silently truncate (`last_truncation_warning`) or overrun the server window and get rejected.
- Scaling path: Use the model tokenizer when available (llama.cpp `/tokenize` endpoint) or a conservative 3-chars/token default for `tables_figures`, and reserve output tokens before budgeting input.

## Dependencies at Risk

**D1 — Loose pins in `requirements.txt` vs pinned lockfile (High):**
- Risk: `requirements.txt` allows `docling>=2.0.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`, `pyarrow>=14.0.0`, `pillow>=10.2.0,<13`, and `pymupdf>=1.24.0,<2.0`. The Docker image installs `requirements-lock.txt`, but local README flows install `requirements.txt` (and `setup.py` reads it for `install_requires`), so users can land on versions the code's `hasattr` guards were never tested against (LanceDB FTS API and `create_fts_index` deprecation already required a warning filter, `pyproject.toml:23-30`).
- Files: `requirements.txt`, `requirements-lock.txt`, `Dockerfile:24-26`, `setup.py:53-58`, `pyproject.toml`.
- Impact: Divergent behavior between Docker and native installs; hard-to-reproduce ingestion/retrieval bugs. Observed on this host: lockfile `docling==2.138.0` / `torch==2.14.1` vs installed `docling 2.140.0` / `torch 2.6.0+cu124`.
- Migration plan: Make `requirements-lock.txt` the only supported install path (README + CI), generate it for both 3.11 and 3.13 given the `rapidocr` split, and add a CI check that the installed environment matches the lock.

**D2 — Two OCR packages gated by Python version (Medium):**
- Risk: `rapidocr-onnxruntime` (<3.13) vs `rapidocr` (>=3.13) have different APIs; only the 3.11 path is exercised in CI (`ubuntu-latest`, 3.11).
- Files: `requirements.txt:11-12`, `ingestion/ocr_fallback.py` (import shim).
- Migration plan: Add a 3.13 CI leg or drop 3.13 support explicitly; assert the shim resolves on both.

**D3 — `docling` is a large, fast-moving dependency (Medium):**
- Risk: 2.x minors have changed `DocumentConverter` result shape; the code defensively probes attributes (`ingestion/docling_reader.py:140-224`), which hides breakage rather than failing at import. The lockfile pins `2.138.0`, but the host has `2.140.0`, and `CLAUDE.md` still claims `2.138.0`.
- Files: `requirements.txt:10`, `requirements-lock.txt:82`, `ingestion/docling_reader.py`.
- Migration plan: Pin a tested `docling==2.140.0` (or reinstall the locked `2.138.0`) consistently across the lockfile and docs, add an integration test that converts a fixture PDF and asserts non-empty markdown, and verify table/reading-order behavior on the chosen version.

**D4 — Cloud SDK surface pulled in unconditionally (Low):**
- Risk: `litellm` drags in `boto3`, `botocore`, `aiohttp`, `openai`, `tokenizers` etc. (visible in `requirements-lock.txt`), inflating install size and attack surface for a local-first tool.
- Files: `requirements.txt:18`, `providers/litellm_provider.py:20`.
- Migration plan: Move cloud providers behind an optional extra (`pip install .[cloud]`) and import lazily.

## Missing Critical Features

**M1 — No cancellation or progress for long operations:**
- Problem: Summarization and OCR expose no progress events and no stop control; a stuck generation requires killing Streamlit.
- Blocks: UAT of 500-page documents on 4 GB hardware.

**M2 — No cross-process inference coordination:**
- Problem: See P2. Users running the app plus `scripts/benchmark_*.py` can exceed VRAM and OOM mid-ingestion.
- Blocks: Reliable benchmarking and any multi-tab workflow.

**M3 — No automated index-integrity report:**
- Problem: Hydration silently repairs missing vectors (`ui/hydration.py:34`), but nothing reports how many documents are inconsistent, and the Diagnostics view does not expose churn/repair counts.
- Blocks: Trustworthy "my answers are missing content" support.

**M4 — Cloud egress audit trail:**
- Problem: Consent is a per-session boolean; nothing records which document excerpts were transmitted, when, or to which provider. `docs/REQUIREMENTS_TRACEABILITY.md` marks the privacy requirement partial for this reason.
- Blocks: Verifiable privacy claims.

## Test Coverage Gaps

**T1 — No coverage gate or timeout enforcement (High):**
- What's not tested: Nothing enforces a minimum coverage or a per-test timeout.
- Files: `pyproject.toml:21-31` (no `--cov`, no `timeout`), `.github/workflows/ci.yml` (ruff + generate corpus + pytest only).
- Risk: A PR can delete meaningful assertions and still pass; a hanging OCR/LLM test can stall CI for the default job limit.
- Priority: High.
- Fix: Add `pytest-cov` with `--cov-fail-under=80` and `pytest-timeout --timeout=120`, plus a coverage report artifact.

**T2 — Streaming sanitizer path untested (High):**
- What's not tested: The invariant "no unsanitized model text reaches the browser" has no test, which is why B1 exists.
- Files: `ui/views.py:774-778`, `ui/sanitizer.py`, `tests/`.
- Risk: Regression of the core privacy promise.
- Priority: High.

**T3 — OCR time-budget and thread-cancellation paths untested (Medium):**
- What's not tested: Deadline exhaustion, `future.result()` raising, and executor orphan behavior on a slow page.
- Files: `ingestion/ocr_fallback.py:433-521`.
- Risk: A hang ships unnoticed; the "300 s cap" claim is unverified.
- Priority: Medium.

**T4 — Degradation paths for LanceDB/embedding failures untested (Medium):**
- What's not tested: Missing `lancedb` package, FTS index creation failure, JSON mirror corruption, and the `VectorIndex` fallback correctness under ties.
- Files: `retrieval/hybrid_retriever.py`, `retrieval/vector_index.py`, `ui/hydration.py`.
- Risk: Silent "no results" in production.
- Priority: Medium.

**T5 — Cloud consent/key precedence untested (Medium):**
- What's not tested: Session key > secrets > env precedence, consent revocation cleanup, and the guarantee that no key appears in logs or error strings.
- Files: `main.py:228-264`, `providers/litellm_provider.py:45-89`, `core/redaction.py`.
- Risk: Unintended external transmission with a stale env key.
- Priority: Medium.

**T6 — UI/theme and scripts are only partially tested (Low):**
- What's not tested: `AppTest` covers shell/navigation/captions, but not `ui/theme.py` CSS selectors, `ui/components.py` SVG formatting, narrow viewports, or `scripts/*.py` (excluded from some lint paths via `pyproject.toml:18`).
- Files: `ui/theme.py`, `ui/components.py`, `tests/test_ui_redesign_apptest.py`, `scripts/`.
- Risk: Broken rendering after Streamlit test-id changes and stale benchmark scripts that silently report wrong numbers.
- Priority: Low.

**T7 — Cross-store lifecycle invariants untested (Low):**
- What's not tested: Crash between vector delete and row delete (F3), purge with an open reader, re-index of a doc whose vectors were manually removed.
- Files: `ui/lifecycle_service.py`, `core/doc_store.py:820-870`.
- Risk: Resurrection of deleted documents or orphaned vectors.
- Priority: Low.

**T8 — Recent grounding, repair, and embedding regressions are untested (High):**
- What's not tested: “where is X currently working” false positive (B10), markdown-heading `partial` false positive (B11), summary `(p. X)` support validation (B12), evidence-vector hydration repair (B13), ingestion status ordering (B14), résumé behavior under the `detailed`/`findings` profiles (B16), and the `EMBEDDING_MAX_LENGTH` wiring (the test at `tests/test_retrieval_semantic.py:59-64` only asserts the constant).
- Files: `tests/test_grounding_contract.py:230-243`, `tests/test_ui_smoke.py`, `tests/test_retrieval_semantic.py`, `ui/hydration.py`, `ui/ingestion_service.py`.
- Risk: The exact live failures that motivated this audit can return without a failing test.
- Priority: High.
- Fix: Add one regression per item above; assert the location heuristic returns `False` for employment questions, a cited heading-bearing summary is `grounded`, an out-of-evidence page reference is rejected, and a lost evidence table is repaired on hydration.

---

*Concerns audit: 2026-10-29*
