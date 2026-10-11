# Codebase Concerns

**Analysis Date:** 2026-10-11

> Refresh context: Phase 1 (`01-canonical-document-models`) verification claims 44/44 passed (`.planning/phases/01-canonical-document-models/01-VERIFICATION.md`), but the follow-up code review returned **NEEDS FIXES with 3 Criticals** (`.planning/phases/01-canonical-document-models/01-REVIEW.md`). This document orders Phase 1 criticals first, then remaining warnings, then prior-debt status (fixed vs still open).

## Top Risks (Ordered by Severity)

### 1. CRITICAL — Dedup-hit path never restores embeddings; restart is a permanent dead end
- Files: `main.py:136-148`, `doc_store.py:272-282` (`get_chunks_for_doc`), `main.py:243-265` (chat gate)
- Risk: **Critical.** On a dedup hit (`doc_id in session OR DocStore row with status == "indexed"`) the handler only updates display metadata and `continue`s — it never rebuilds `st.session_state.local_embedding`. After any server restart the session index is `None` (session state is volatile), so every previously indexed file hits the DocStore branch, is skipped as a duplicate, the index stays `None`, and chat stays disabled with no in-UI recovery short of wiping `data/documents.db`. Combined with Risk #3 (chunks table empty in prod) there is not even stored data to rebuild from. The `dedup-hit-on-empty-index` case is NOT fixed.
- Fix approach: On dedup hit with empty session index, rebuild from persisted chunks (`LocalEmbedding()` + `doc_store.get_chunks_for_doc()` per known id + `build_index`); requires Risk #3 fixed first. At minimum surface `st.warning("Index is empty after restart — re-upload to re-index")` instead of a silent skip. Add regression test: pre-populated `DocStore` + empty session index → dedup-hit yields a queryable index.

### 2. CRITICAL — `PdfReader` construction outside try/except aborts entire batch on malformed PDF
- Files: `main.py:156-162`, `pdf_reader.py:16` (ctor calls `pypdf.PdfReader`), `main.py:126-130` (only `validate_pdf_bytes` is guarded)
- Risk: **Critical.** Only `validate_pdf_bytes` is wrapped (`try/except ValueError`). `PdfReader(pdf_stream, ...)` raises on malformed/encrypted/trailer-broken PDFs even when the `%PDF` magic-byte check passed (`test_pdf_reader_corrupt_pdf_rejects` proves the ctor itself raises). One such file raises uncaught, kills the whole `for uploaded_file` loop, and surfaces a Streamlit exception page — violating the isolate-and-continue contract the phase claims.
- Fix approach: Wrap ctor + `extract_text` + `get_paragraphs` + `get_page_records` in one per-file `try/except Exception → st.error(...) + continue` (see `01-REVIEW.md:89-99`).

### 3. CRITICAL — `record_chunks` never called in prod; `chunks` table dead, no rebuild possible
- Files: `main.py:170-188`, `doc_store.py:228-247` (`record_chunks` defined, zero prod callers), `main.py:190-201` (`.cache/chunks.json` is the only chunk record and is never read)
- Risk: **Critical.** Upload flow calls `doc_store.record_page()` per page and `doc_store.upsert_document()` once, but never `doc_store.record_chunks()`. `get_chunks_for_doc()` therefore returns `[]` for every real document; STORE-01 "chunk persistence" is proven only with synthetic unit-test data (`tests/test_doc_store.py:149-168`). No restart-rebuild path (Risk #1) is possible.
- Fix approach: After `build_index`, call `doc_store.record_chunks([Chunk.model_validate(p) for p in paragraphs])` inside the same per-file guard (requires `from models import Chunk` in `main.py`); wrap steps 5+6 in one try so a chunk-store failure cannot orphan pages without a document row.

### 4. SQLite connection lifecycle + TOCTOU race + ordering + cache risks (WR-01/WR-03/WR-06/WR-07 bundle)
- Files: `doc_store.py:77-79,127,156,176,190,214,268,282`, `main.py:134,188` + `doc_store.py:118-141`, `doc_store.py:283`, `main.py:190-201`, `.gitignore:1-17`
- Risk: **High.** (a) Every method uses `with self._connect() as conn:` — a `sqlite3.Connection` context manager commits/rolls back but does **not** close, so FDs/WAL handles accumulate under Streamlit's rerun-per-interaction model, risking `database is locked` on Windows. (b) `get_by_sha` (read) and `upsert_document` (write) are separate connections with no spanning transaction — two concurrent sessions uploading the same file both miss the check and the loser gets an uncaught `sqlite3.IntegrityError` (test `test_sha_unique_violation_on_reupload` pins the raise; no caller handles it). (c) `ORDER BY page ASC, chunk_id ASC` sorts `..._p1_10` before `..._p1_2` — any rebuild-from-store restores chunks out of order. (d) `.cache/` dumps (`pages.json`/`chunks.json`/`manifest.json`) are written best-effort every upload but never read (STORE-03 half-delivered); `.cache/` is **not** in `.gitignore` (only `data/` is) so cache artifacts will be committed.
- Fix approach: `contextlib.closing` + explicit `commit()`; catch `IntegrityError` at the `upsert_document` call site and route to the dedup-hit UI path; zero-pad chunk sequence (`_{j:04d}`) or order by `char_start`/`rowid`; implement cache read-or-remove policy and add `.cache/` to `.gitignore`.

### 5. Unhandled Groq API / startup failures crash the whole app (prior risk, still open)
- Files: `local_llm.py:23-33`, `local_llm.py:73-81`, `main.py:86-88`, `main.py:289-295`
- Risk: **High.** `AiModel.__init__` raises `ValueError`/`ImportError` on missing key/package; the streaming call `groq_client.chat.completions.create(...)` has zero `try/except` (401/429/500, revoked key, model retirement of `openai/gpt-oss-20b`). Both run inside `st.status` / `st.write_stream` with no error boundary — one failure shows a raw traceback and kills the session.
- Fix approach: Wrap `load_ai_model()` and the stream call site in `try/except` with `st.error` + `st.stop()`; retry with backoff for transient errors; make model name an env var (`GROQ_MODEL`) with 404 handling.

### 6. Prompt assembly can overflow context and is injection-prone; displayed sources can lie (prior risk, still open)
- Files: `local_llm.py:47-70`, `main.py:274-278`
- Risk: **Medium-High.** Retrieval uses hardcoded `k=10` chunks of ~1000 chars plus up to 10 history messages with no token counting before sending to Groq (`max_tokens=1024` caps output only). `main.py` computes displayed sources from `search(prompt, k=10)` while generation uses `get_context(last_msg + prompt, k=10)` — different queries, so citations may not match grounding. The "answer only from document" instruction is trivially overridable (no delimiters/sanitization).
- Fix approach: Single shared retrieval call for display + generation; token-budget truncation (newest first); `<document>` delimiters + injection-resistant system prompt.

## Tech Debt

**Phase 1 persistence story broken end-to-end (CR-01 + CR-03 — one coherent fix):**
- Issue: Chunks never persisted in prod and dedup-hit never rebuilds, so the "SQLite-backed restart resilience" claim is false despite 44/44 unit tests passing. Verification (`01-VERIFICATION.md`) tested `DocStore` in isolation; no test covers the dedup-hit-with-empty-index integration path.
- Files: `main.py:136-148`, `main.py:170-201`, `doc_store.py:228-282`
- Impact: Restart = permanent chat-disabled dead end for all previously indexed files.
- Fix approach: Fix CR-03 and CR-01 together per `01-REVIEW.md` fix priority #1, plus the missing regression test.

**SQLite connections never closed (WR-01):**
- Issue: `with self._connect() as conn:` in 8 methods (`doc_store.py:77,127,156,176,190,214,268,282`) never closes the connection.
- Files: `doc_store.py:77-79`, `doc_store.py:80-82` (`_connect` def)
- Impact: FD/WAL-handle leak; `database is locked` under rerun + per-page writes, especially on Windows.
- Fix approach: `with closing(self._connect()) as conn:` + explicit `conn.commit()`.

**Disk cache is write-only (WR-07):**
- Issue: `pages.json`/`chunks.json`/`manifest.json` written best-effort (`main.py:190-201`) but no code path reads them; stale caches accumulate with no invalidation beyond `CONFIG_VERSION`; `.cache/` unignored.
- Files: `main.py:190-201`, `models.py:15-26` (`cache_dir_for`), `.gitignore`
- Impact: Dead store + accidental commits of cache artifacts.
- Fix approach: Implement read path (skip re-extraction when manifest matches) or downgrade to marked debug dumps; add `.cache/` to `.gitignore` regardless.

**Inconsistent timestamp formats break ordering and display (WR-08):**
- Issue: Three formats coexist — ISO with `+00:00` (persisted `Document.upload_time`, `main.py:177`), `%H:%M:%S` time-only session metadata (`main.py:144,208` — drops the date), `Z`-suffixed strings in tests. `list_documents ORDER BY upload_time DESC` (`doc_store.py:191`) compares lexicographically where `'Z' (0x5A) > '+' (0x2B)` regardless of time.
- Files: `main.py:142-144,177,208`, `doc_store.py:191`
- Impact: Wrong sort order; ambiguous cross-day display.
- Fix approach: Store/display one canonical form (`datetime.now(timezone.utc).isoformat()`); format for display only at render time.

**Fault-isolation scope too narrow (WR-02):**
- Issue: Per-page `try/except` in `pdf_reader.py:50-51` wraps only `page.extract_text()`. `text_splitter.split_text()` + `Chunk(...)` construction (`pdf_reader.py:83-93`) sit outside it; `Chunk.content` has `min_length=1` and content is `p.strip()`, so whitespace-only splitter output raises `ValidationError` and aborts the whole document despite INGEST-05.
- Files: `pdf_reader.py:48-105`
- Impact: One bad page/split kills the document; contradicts the fault-isolation claim.
- Fix approach: Extend the guard over split + validate per page (record `Page(status="failed")`, `continue`); or pre-filter `if not p.strip(): continue`.

**Identity fields unvalidated (WR-05):**
- Issue: `Document.doc_id` is bare `str` with no cross-check against `sha256` (a row with mismatched `doc_id`/`sha256` validates fine, breaking the `doc_ + sha[:16]` invariant); `doc_id_for()` accepts any string with no 64-hex enforcement; `Page.status`/`Document.status`/`EvidenceElement.kind` are unconstrained `str` (`"bogus"` passes).
- Files: `models.py:57,74,90,104-109`, `upload_validation.py:35-45`
- Impact: Silent invariant breakage; typo statuses pass validation.
- Fix approach: `@field_validator`/`model_validator` for doc_id↔sha consistency; validate sha shape in `doc_id_for`; use `Literal` types for status/kind.

**Lexical `chunk_id` ordering (WR-06):**
- Issue: `ORDER BY page ASC, chunk_id ASC` (`doc_store.py:283`) misorders 10+ chunks per page.
- Files: `doc_store.py:283`, `pdf_reader.py` (chunk-id construction)
- Impact: Rebuild-from-store corrupts context assembly order.
- Fix approach: Zero-pad sequence (`f"{sha12}_p{page_num}_{j:04d}"`) or order by `char_start`/`rowid`.

**Linear brute-force scan in pure Python (prior debt, still open):**
- Issue: `VectorIndex.search` (`vector_index.py:137-144`) scans every vector with Python-level loops. Baseline measured 8.25 ms @ 100 vecs → 51.91 ms @ 1000 vecs (superlinear, past 50 ms budget at 1k).
- Files: `vector_index.py:137-144`, `vector_index.py:201-207`
- Impact: Multi-second scans at tens of thousands of chunks; query-time transformer pass dominates small indexes, scan dominates large ones.
- Fix approach: Short term NumPy-vectorize; long term ANN (`hnswlib`/`faiss`) per `README.md:237`.

**Hardcoded retrieval/generation knobs, no token budgeting (prior debt, still open):**
- Issue: `k=10` at two call sites, `chunk_size=1000`/`chunk_overlap=200`, `max_tokens=1024`, history `[-10:]` — no shared config, no token counting.
- Files: `main.py:216`, `main.py:231`, `local_llm.py:54`, `local_llm.py:77`, `pdf_reader.py:31-35`
- Impact: Context overflow; tuning touches 4 files; display/generation drift.
- Fix approach: Central config dataclass + token-budget truncation (oldest first).

**Per-session embedding model, no persistence (prior debt, partially addressed — NOT closed):**
- Issue: Phase 1 added SQLite metadata + disk-cache *writes* but the vector index is still pure in-memory (`vector_index.py:30-34`) with no save/load and no read-back. Each session still constructs its own `LocalEmbedding()` → `SentenceTransformer` (~14.73 s load, +~766 MB RSS per baseline). The `.cache/chunks.json` dump is never consumed.
- Files: `main.py:48-56`, `main.py:172-174`, `local_embedding.py:13-26`, `vector_index.py:30-34`
- Impact: Full re-embed every restart; N sessions = N × ~800 MB.
- Fix approach: `@st.cache_resource` the `SentenceTransformer`; keep only `VectorIndex` in session state; add disk serialization keyed by content hash; wire the cache read path.

## Known Bugs

**Dedup-hit on empty index skips forever (CR-01 — new, highest priority):**
- Symptoms: After restart, re-uploading any previously indexed file shows "Already indexed — skipped duplicate", index stays `None`, chat stays disabled, no recovery path.
- Files: `main.py:136-148`
- Trigger: Any restart followed by any re-upload of a known file.
- Workaround: Wipe `data/documents.db` (loses all metadata) or upload a never-before-seen file.

**One malformed PDF aborts the whole batch (CR-02 — new):**
- Symptoms: A `%PDF`-headered but trailer-broken/encrypted file kills the `for uploaded_file` loop with a Streamlit exception page; remaining valid files in the same batch never process.
- Files: `main.py:156-162`, `pdf_reader.py:16`
- Trigger: Upload a malformed PDF alongside valid ones.
- Workaround: Upload files one at a time to isolate the bad file.

**Same-name / stale-index and empty-PDF issues (prior, still open):**
- Symptoms: Phase 1 fixed *content* dedup (SHA-256 via `DocStore.get_by_sha`, `main.py:134`), but session display is still filename-keyed (`indexed_files`, `document_metadata`); removing a file from the uploader does not remove its vectors (only nuclear `Clear All`); `chat_history` wiped without warning on every new upload (`main.py:214-216`); empty-text PDFs still marked indexed with `chunks: 0`.
- Files: `main.py:136-148`, `main.py:203-211`, `main.py:214-216`
- Trigger: Filename reuse across different content (display confusion); uploader deselection; scanned-PDF upload.
- Workaround: `Clear All` (wipes everything).

**Sources badge may not match generation context (prior, still open):**
- Symptoms: "Sources used" from `search(prompt)` while answer grounded in `get_context(last_msg + prompt)` — cites unused files or omits used ones.
- Files: `main.py:274-278`, `local_llm.py:47-54`
- Trigger: Any follow-up where history changes ranking.
- Workaround: None — needs a single shared retrieval call.

## Security Considerations

**Full file buffered before size check (WR-04 — new):**
- Risk: `uploaded_file.getvalue()` (`main.py:121`) copies the entire payload into RAM before `validate_pdf_bytes` checks `len(raw) > MAX_FILE_MB*...` (`upload_validation.py:79-84`). A 500 MB upload is fully resident before rejection.
- Files: `main.py:121`, `upload_validation.py:79-84`
- Current mitigation: 50 MB post-read rejection; Streamlit `getvalue()` forces one copy.
- Recommendations: Pre-check `uploaded_file.size` and reject without reading bytes; note `tests/test_upload_validation.py:54-58` allocates ~51 MB per run — consider patching `MAX_FILE_MB` down in tests.

**Filenames interpolated into Markdown UI — markup injection (IN-03):**
- Risk: `st.write(f"Validating \`{filename}\`…")` etc. render attacker-controlled filenames as Markdown; `st.success(f"**{filename}** ...")` (`main.py:212`) wraps in bold markers, not code spans, so `[x](url)` payloads can render links/images.
- Files: `main.py:125,153,168,171,194,201,212`
- Current mitigation: Backticks on most paths (not all).
- Recommendations: Prefer `st.code`/escaped rendering for raw filenames.

**`cache_dir_for` permits path traversal (IN-04):**
- Risk: `base / sha256 / CONFIG_VERSION` (`models.py:15-26`) with unsanitized `sha256` allows `cache_dir_for(base, "../../etc")` escapes. Current caller passes an internally computed hash (safe), but the helper is public and unguarded.
- Files: `models.py:15-26`
- Current mitigation: Safe caller only.
- Recommendations: Add `^[0-9a-f]{64}$` assertion on the hash argument.

**API key handling (prior, still acceptable but brittle):**
- Risk: `GROQ_API_KEY` from `st.secrets` then `os.environ` (`local_llm.py:23-27`); `load_dotenv()` inside cached `load_ai_model()` (`main.py:71`) so import-time env reads would miss it. Error text (`main.py:138`) interpolates raw exception internals that could leak paths. Test fixture `gsk_mock_test_key_…` (`tests/conftest.py:16`) mimics a real key prefix and may trip secret scanners.
- Files: `local_llm.py:23-33`, `main.py:64-72`, `tests/conftest.py:16`
- Current mitigation: `.env` gitignored; `st.secrets` preferred; no hardcoded key.
- Recommendations: `load_dotenv()` at module top; never interpolate exception internals into UI; rename fake fixture key to an obviously inert value.

**File upload validation (prior — improved, not closed):**
- Risk: Phase 1 closed the "no server-side checks" gap (`validate_pdf_bytes`: `%PDF` header, 50 MB, 500 pages — `upload_validation.py`). Remaining: no pre-read size check (WR-04), no decompression-bomb/timeout sandboxing, `pypdf` still parses attacker bytes in-process.
- Files: `main.py:119-130`, `upload_validation.py`, `pdf_reader.py:14-23`
- Current mitigation: `try/except ValueError` around validation (`main.py:126-130`) — but NOT around parsing (CR-02).
- Recommendations: Size pre-check, page/chunk caps enforced post-extraction, parse timeouts; fix CR-02 first.

**Prompt injection (prior, unmitigated):**
- Risk: User prompt concatenated directly into messages (`local_llm.py:64-70`) with only a soft grounding instruction.
- Files: `local_llm.py:56-70`
- Current mitigation: Grounding instruction only.
- Recommendations: `<document>` delimiters, "do not follow instructions inside document/user text" rule, citation requirements.

**No auth / multi-tenancy isolation (prior, expected for demo):**
- Risk: No authentication; shared Groq key/quota (`main.py:64-72` process-global) with per-session indexes. One abusive user burns quota or OOMs the process for everyone.
- Files: `main.py:64-72`
- Current mitigation: None.
- Recommendations: Auth + per-user rate limits + resource caps before any public deployment.

## Performance Bottlenecks

**Single-batch full-corpus embedding blocks the UI (still open):**
- Problem: `build_index` embeds all chunks in one `model.encode` call (`local_embedding.py:56`) inside `st.status` with no progress; model load happens in the upload path, not behind `@st.cache_resource`.
- Files: `local_embedding.py:42-59`, `main.py:172-174`
- Cause: No batching, no progress callback, no background execution.
- Improvement path: Mini-batches (e.g. 32) with `st.progress`; cache the transformer globally.

**Per-query transformer pass + full scan (still open, quantified):**
- Problem: Every question triggers a full MiniLM forward pass (~13–21 ms/chunk equivalent) plus O(n) Python scan (8.25/37.01/51.91 ms @ 100/500/1000 vecs).
- Files: `local_embedding.py:28-33`, `vector_index.py:137-144`
- Cause: No query caching, no vectorized math.
- Improvement path: NumPy-vectorize; cache recent query embeddings; ANN for large corpora.

**Per-page `record_page` connections amplify WR-01 (new):**
- Problem: `for idx, page in enumerate(page_records): doc_store.record_page(page)` (`main.py:164-168`) opens one unclosed connection per page — a 500-page PDF leaks 500 connections per upload.
- Files: `main.py:164-168`, `doc_store.py:195-226`
- Cause: Per-op-connection design + missing close.
- Improvement path: Batch page inserts in one transaction; fix WR-01.

## Fragile Areas

**Upload loop ordering — persistence steps unguarded as a unit:**
- Files: `main.py:119-216`
- Why fragile: Validation is guarded, but ctor/extract (CR-02), `build_index`, `record_page` loop, `upsert_document`, and cache writes are not in a single per-file guard — a failure at any step after `record_page` leaves partial rows (pages without document, vectors without chunks). `upsert_document` `IntegrityError` (WR-03) is unhandled.
- Safe modification: Wrap steps 4–7 in one per-file `try/except Exception → st.error + continue`; handle `IntegrityError` as dedup-hit; keep `build_index` + `record_chunks` adjacent so they cannot diverge.
- Test coverage: None for `main.py` — the CR-01 gap has no test (pre-populated `DocStore` + empty session index case missing).

**Streamlit rerun semantics + `st.rerun()` in upload loop:**
- Files: `main.py:45-56`, `main.py:113-222`
- Why fragile: Whole script reruns per interaction; correctness depends on session-state init order and `st.rerun()` after indexing (`main.py:214-216`). `Clear All` (`main.py:97-103`) wipes index + history without confirmation.
- Safe modification: Never touch session keys outside the init block without a guard; add confirmation for destructive actions.
- Test coverage: None for `main.py`.

**Error paths funnel to generic handlers:**
- Files: `main.py:126-130`, `main.py:289-295`, `local_llm.py:73-81`
- Why fragile: Only validation has `try/except`; embedding OOM/torch errors, Groq 401/429/500, and stream interrupts propagate as tracebacks mid-`st.write_stream`, leaving half-rendered bubbles and unsaved history.
- Safe modification: Wrap generation in `try/except`, append error to `chat_history`, offer retry.
- Test coverage: Only missing-key `ValueError`; no 401/429/500 or interrupt tests.

**PDF extraction edge cases (partially improved):**
- Files: `pdf_reader.py:26-105`
- Why fragile: `None`/whitespace pages silently dropped with no user-visible count (page-count metadata in `main.py:209` uses `validated.num_pages` from the probe, masking skipped pages); no OCR fallback; `re.sub(r' +', ...)` doesn't normalize tabs/newlines; only 2 of 6 corpus files exercised (dense-table/chart/multi-column unverified per prior review).
- Safe modification: Count skipped pages, surface "N pages had no extractable text"; handle `pypdf.errors.PdfReadError` explicitly; strip empty chunks before embedding.
- Test coverage: Partial — overlap, corrupt-rejection (ctor-level, now covered), dense-table, chart, multi-column still missing.

## Scaling Limits

**In-memory per-session index (unchanged):**
- Current capacity: ~1k vectors ≈ 52 ms/query pure Python; comfortable ceiling low-thousands of chunks + ~766 MB model RAM per session.
- Limit: Tens of thousands of chunks → multi-second scans; concurrent sessions multiply model RAM.
- Scaling path: NumPy/FAISS + disk persistence + per-hash dedup cache (`README.md:236-237`); Phase 1's `DocStore` covers metadata only, not vectors.

**Groq Cloud quota (unchanged):**
- Current capacity: Single shared key, `max_tokens=1024`, 10 history messages per request.
- Limit: 429s under concurrency; history inflates input tokens linearly.
- Scaling path: Per-user keys/quotas, history summarization, token-budget enforcement.

**Single-process Streamlit server (unchanged):**
- Current capacity: Demo-scale single user.
- Limit: No horizontal scaling; one giant PDF blocks all sessions.
- Scaling path: Background ingestion worker; per-user process limits.

## Dependencies at Risk

**Unpinned transitive stack (still open):**
- Risk: `requirements.txt` pins 6–7 direct deps but `torch`/`transformers`/`tokenizers`/`huggingface-hub` float; `numpy>=1.26.0,<3.0.0` range is loose (flagged in review); `numpy` imported directly (`tests/conftest.py:9`, `scripts/benchmark_baseline.py:97`) with availability via transitive install. No lockfile. CI (`.github/workflows/ci.yml`) installs test deps ad hoc unpinned; `pydantic==2.11.9` pin is exact (good).
- Impact: Non-reproducible installs; surprise breakage.
- Migration plan: Lockfile (`pip-compile`/`uv.lock`) or explicit pins for `torch` + `transformers` + `numpy`; pinned `requirements-test.txt`; CPU-only wheel index docs.

**`groq==0.15.0` + `openai/gpt-oss-20b` (still open):**
- Risk: Pinned SDK may lag API; model ID is rename-sensitive (README still says "Llama 3" in places). Server-side retirement = 404 on every question with no fallback.
- Impact: Total Q&A outage, cryptic error.
- Migration plan: `GROQ_MODEL` env var with default; 404 → "model unavailable" message.

**`langchain-text-splitters==0.3.6` for one function (low priority, unchanged):**
- Risk: Heavy tree for one `RecursiveCharacterTextSplitter` call; import-path churn risk.
- Impact: Install bloat; potential breakage.
- Migration plan: Vendor a small splitter if churn bites.

## Missing Critical Features

**Phase 1 fix-pack (blocks Phase 1 sign-off):**
- Problem: CR-01 + CR-03 (persist chunks + rebuild on dedup-hit) as one fix with the missing regression test; CR-02 (per-file guard); WR-01 (connection close); WR-03 (`IntegrityError` handling); WR-04 (size pre-check); WR-07 (cache policy + `.gitignore`); WR-08 (timestamp unification). Then WR-05/WR-06 + info items.
- Blocks: Any claim that persistence/restarts work; Phase 2+ built on a hollow foundation otherwise.

**No app-level tests for `main.py` (still open — highest-value gap):**
- Problem: 44 unit tests cover library modules, but `main.py` (upload/index/chat/rerun/session — where all 3 Criticals live) has zero tests. No test covers dedup-hit-with-empty-index, batch abort on malformed PDF, or `record_chunks`-called-in-prod.
- Blocks: Safe refactor of every Top Risk fix.

**No vector persistence / embedding cache read path (still open):**
- Problem: Documented in `README.md:228,236`; Phase 1 wrote metadata + cache files but reads neither.
- Blocks: Multi-document libraries, restart resilience, Cloud sleep/wake.

**No observability (still open):**
- Problem: Only `print()` (`local_llm.py:16`, `local_embedding.py:22-24`, `pdf_reader.py:60`); no logging framework, error tracking, or latency metrics.
- Blocks: Production diagnosis, quota monitoring, perf tuning.

## Test Coverage Gaps

**Integration paths with zero coverage (new — the reason verification passed but review failed):**
- What's not tested: Dedup-hit with empty session index (CR-01); `record_chunks` invoked from the prod upload path (CR-03); malformed-PDF-in-batch isolation at the `main.py` level (CR-02); `IntegrityError`-on-concurrent-reupload handling (WR-03); cache read-back (WR-07).
- Files: `main.py:136-201`, `doc_store.py:118-141,228-282`
- Risk: Unit-green / integration-broken persists for every future phase unless integration tests are added.
- Priority: High.

**Still entirely untested (prior, unchanged priority):**
- What's not tested: `main.py` rerun/session logic; Groq failure modes (401/429/500, stream interrupts, model 404); per-file isolation; benchmark zero-division edges (`scripts/benchmark_baseline.py:48,90`); `add_vector([])` dimension-0 lock (`vector_index.py:77-92`).
- Files: `main.py`, `local_llm.py:73-81`, `scripts/benchmark_baseline.py:48,90`, `vector_index.py:77-92`
- Risk: NumPy migration, persistence, prompt rework can regress silently.
- Priority: High for `main.py` + failure modes; Medium for edge guards.

**Brittle/weak existing tests (carried forward + new):**
- What's weak: `test_sha_unique_violation_on_reupload` pins a raise no caller handles (WR-03); oversize test allocates ~51 MB + over-page test relies on global `pypdf` monkeypatch (IN-05); `record_chunks` conflict refresh covers only 3 of 9 columns (IN-06 — re-chunk under new config keeps stale page/offsets); `sha256_bytes(...).lower()` no-op (IN-01); `BBox` accepts inverted/negative coords (IN-02 — dormant until Phase 3/4); private-API coupling in `tests/test_vector_index.py`.
- Files: `tests/test_upload_validation.py:54-76`, `doc_store.py:240-247`, `upload_validation.py:32`, `models.py:29-41`, `tests/test_vector_index.py`
- Risk: False-clean signals; order-dependent parallel-test failures; stale geometry on re-chunk.
- Priority: Medium/Low — fix opportunistically with the Phase 1 fix-pack.

---

*Concerns audit: 2026-10-11*
