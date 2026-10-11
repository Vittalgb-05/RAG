# Codebase Concerns

**Analysis Date:** 2026-10-11

> Refresh context: Phase 1 review (`01-REVIEW.md`, NEEDS FIXES / 3 Criticals) was resolved by `01-REVIEW-FIX.md` in commit `da24920` (+ `5275f56` docs). All 3 Criticals, all 8 Warnings, and IN-01/02/03/04/06 verified fixed on disk. This document records fix status first, then residual + prior-debt risks that remain open.

## Top Risks (Ordered by Severity)

### 1. HIGH — Unhandled Groq API / startup failures crash the whole app (prior risk, still open)
- Files: `local_llm.py:19-34`, `local_llm.py:75-84`, `main.py:86-88`
- Risk: **High.** `AiModel.__init__` raises `ValueError`/`ImportError` on missing key/package; `groq_client.chat.completions.create(...)` has zero `try/except` (401/429/500, revoked key, retirement of `openai/gpt-oss-20b`). Both run inside `st.status` / `st.write_stream` with no error boundary — one failure shows a raw traceback and kills the session.
- Fix approach: Wrap `load_ai_model()` and the stream call site in `try/except` with `st.error` + `st.stop()`; retry with backoff for transient errors; make model name an env var (`GROQ_MODEL`) with 404 handling.

### 2. HIGH — Prompt assembly can overflow context and is injection-prone; displayed sources can lie (prior risk, still open)
- Files: `local_llm.py:50-72`, `main.py:274-278` (approx — sources badge vs generation query)
- Risk: **High.** Retrieval uses hardcoded `k=10` chunks of ~1000 chars plus up to 10 history messages with no token counting before sending to Groq (`max_tokens=1024` caps output only). Displayed sources and generation may use different queries (`search(prompt)` vs `get_context(last_msg + prompt)`), so citations may not match grounding. The "answer only from document" instruction is trivially overridable (no delimiters/sanitization).
- Fix approach: Single shared retrieval call for display + generation; token-budget truncation (newest first); `<document>` delimiters + injection-resistant system prompt.

### 3. MEDIUM-HIGH — Linear brute-force scan in pure Python (prior debt, still open)
- Files: `vector_index.py:137-144`, `vector_index.py:201-207`
- Risk: **Medium-High.** `VectorIndex.search` scans every vector with Python-level loops. Baseline measured 8.25 ms @ 100 vecs → 51.91 ms @ 1000 vecs (superlinear, past 50 ms budget at 1k).
- Fix approach: Short term NumPy-vectorize; long term ANN (`hnswlib`/`faiss`) per `README.md:237`.

### 4. MEDIUM — Per-session embedding model, no vector persistence (partially addressed, NOT closed)
- Files: `main.py:48-56`, `main.py:195-203`, `local_embedding.py:13-26`, `vector_index.py:30-34`
- Risk: **Medium.** Phase 1 + fix-pack added SQLite metadata/chunk persistence and dedup-hit rebuild (`main.py:161-168`, `doc_store.py:235-296`), but the vector index is still pure in-memory with no save/load. Each session still constructs its own `LocalEmbedding()` → `SentenceTransformer` (~14.73 s load, +~766 MB RSS per baseline). The `.cache/chunks.json` dump is still write-only (never read).
- Fix approach: `@st.cache_resource` the `SentenceTransformer`; keep only `VectorIndex` in session state; add disk serialization keyed by content hash; wire the cache read path.

### 5. MEDIUM — Same-name / stale-index and empty-PDF UX issues (prior, still open)
- Files: `main.py:149-168`, `main.py:234-243`
- Risk: **Medium.** Content dedup is SHA-256 based (`DocStore.get_by_sha`, `main.py:147`) but session display is still filename-keyed (`indexed_files`, `document_metadata`); removing a file from the uploader does not remove its vectors (only nuclear `Clear All`); empty-text PDFs marked indexed with `chunks: 0`.
- Fix approach: Filename→doc_id display mapping; per-document removal; reject or warn on zero-chunk index.

### 6. LOW-MEDIUM — Residual hardening gaps after fix-pack
- Files: `main.py:189-191` (per-page `record_page` loop still one connection per page), `models.py` (doc_id↔sha cross-check is prefix-only, not full invariant), `tests/test_upload_validation.py:54-58` (~51 MB allocation per run)
- Risk: **Low-Medium.** Fix-pack closed the correctness gaps but left efficiency/strictness residue: per-page connections (N pages = N connections, now at least closed via `_connect` finally-block), `Document` validator checks `doc_id` prefix only, oversize test still allocates ~51 MB in-process.
- Fix approach: Batch page inserts in one transaction; full `doc_id == doc_ + sha[:16]` model validator; monkeypatch `MAX_FILE_MB` down in the oversize test.

## Fix Status — Phase 1 Review Criticals (all verified FIXED on disk)

**CR-01 FIXED — Dedup-hit rebuild (`main.py:161-168`):** On dedup hit with `local_embedding is None`, handler fetches `doc_store.get_chunks_for_doc(doc_id)` and rebuilds via `LocalEmbedding().build_index(...)`. Verified present on disk.

**CR-02 FIXED — Per-file extraction guard (`main.py:176-187`):** `PdfReader` construction + `extract_text` + `get_paragraphs` + `get_page_records` wrapped in `try/except Exception → st.error + continue`. Verified present on disk.

**CR-03 FIXED — Chunk persistence in prod (`main.py:201-203`):** `doc_store.record_chunks([Chunk.model_validate(p) for p in paragraphs])` called after `build_index`, before `upsert_document`. Verified present on disk.

## Fix Status — Warnings & Info (all verified FIXED on disk)

- **WR-01 FIXED (`doc_store.py:80-96`):** `_connect()` is now a `@contextmanager` with `try/finally: conn.close()`.
- **WR-02 FIXED (`pdf_reader.py`):** Per-page guard widened over split + `Chunk` construction; whitespace-only splits filtered, failures recorded as `Page(status="failed")`.
- **WR-03 FIXED (`main.py:216-219`):** `upsert_document` wrapped in `try/except sqlite3.IntegrityError → st.info(...)`.
- **WR-04 FIXED (`main.py:123-132`):** `uploaded_file.size` pre-check rejects oversize files before `getvalue()`.
- **WR-05 FIXED (`models.py`, `upload_validation.py`):** `doc_id_for` enforces `^[0-9a-f]{64}$`; `Page.status`/`Document.status`/`EvidenceElement.kind` constrained to `Literal`; `Document` model validator checks `doc_id` prefix.
- **WR-06 FIXED (`pdf_reader.py:76`, `doc_store.py:296`):** Chunk sequence zero-padded (`_{j:04d}`); `get_chunks_for_doc` orders by `page ASC, rowid ASC`.
- **WR-07 FIXED (`.gitignore:17`):** `.cache/` now ignored. Note: cache read-back path still absent (write-only residue — see Risk #4).
- **WR-08 FIXED (`main.py:157,205,238`):** Timestamps standardized on `datetime.now(timezone.utc).isoformat()`.
- **IN-01/02/03/04/06 FIXED:** Redundant `.lower()` removed; `BBox` geometry validation added; filenames rendered in code spans; `cache_dir_for` rejects traversal; `record_chunks`/`upsert_document` conflicts refresh all mutable columns.

## Tech Debt

**Hardcoded retrieval/generation knobs, no token budgeting (still open):**
- Issue: `k=10` at call sites, `chunk_size=1000`/`chunk_overlap=200`, `max_tokens=1024`, history window — no shared config, no token counting.
- Files: `local_llm.py:56`, `local_llm.py:79`, `pdf_reader.py:31-35`
- Impact: Context overflow; tuning touches multiple files; display/generation drift.
- Fix approach: Central config dataclass + token-budget truncation (oldest first).

**Disk cache still write-only (WR-07 residue):**
- Issue: `pages.json`/`chunks.json`/`manifest.json` written best-effort (`main.py:221-232`) but no code path reads them; `.gitignore` fix stops commits but not stale accumulation.
- Files: `main.py:221-232`, `models.py:15-26`
- Impact: Dead store; restart still requires re-embed (chunk rows in SQLite ARE read back — cache files are not).
- Fix approach: Implement read path (skip re-extraction when manifest matches `CONFIG_VERSION`) or downgrade to marked debug dumps.

**Single-batch full-corpus embedding blocks the UI (still open):**
- Issue: `build_index` embeds all chunks in one `model.encode` call inside `st.status` with no progress; model load happens in the upload path, not behind `@st.cache_resource`.
- Files: `local_embedding.py:42-59`, `main.py:195-199`
- Impact: UI freeze on large PDFs; repeated ~15 s model loads per session.
- Fix approach: Mini-batches (e.g. 32) with `st.progress`; cache the transformer globally.

## Known Bugs

**Sources badge may not match generation context (prior, still open):**
- Symptoms: "Sources used" from one retrieval call while answer grounded in another (`last_msg + prompt`) — cites unused files or omits used ones.
- Files: `local_llm.py:50-56`
- Trigger: Any follow-up where history changes ranking.
- Workaround: None — needs a single shared retrieval call.

## Security Considerations

**File upload validation (improved, not closed):**
- Risk: `validate_pdf_bytes` enforces `%PDF` header, 50 MB (now pre-checked via `size`), 500 pages (`upload_validation.py`). Remaining: no decompression-bomb/timeout sandboxing, `pypdf` still parses attacker bytes in-process.
- Files: `main.py:134-143`, `upload_validation.py`, `pdf_reader.py:14-23`
- Current mitigation: Pre-read size check (WR-04 fix) + per-file extraction guard (CR-02 fix) + page-level isolation (WR-02 fix).
- Recommendations: Parse timeouts; page/chunk caps enforced post-extraction.

**Prompt injection (unmitigated):**
- Risk: User prompt concatenated directly into messages (`local_llm.py:66-72`) with only a soft grounding instruction.
- Files: `local_llm.py:58-72`
- Current mitigation: Grounding instruction only.
- Recommendations: `<document>` delimiters, "do not follow instructions inside document/user text" rule, citation requirements.

**API key handling (acceptable but brittle):**
- Risk: `GROQ_API_KEY` from `st.secrets` then `os.environ` (`local_llm.py:25-28`); error text may interpolate raw exception internals.
- Files: `local_llm.py:25-31`
- Current mitigation: `.env` gitignored; `st.secrets` preferred; no hardcoded key.
- Recommendations: Never interpolate exception internals into UI.

**No auth / multi-tenancy isolation (expected for demo):**
- Risk: No authentication; shared Groq key/quota with per-session indexes. One abusive user burns quota or OOMs the process for everyone.
- Files: `main.py`
- Current mitigation: None.
- Recommendations: Auth + per-user rate limits + resource caps before any public deployment.

## Performance Bottlenecks

**Per-query transformer pass + full scan (still open, quantified):**
- Problem: Every question triggers a full MiniLM forward pass plus O(n) Python scan (8.25/37.01/51.91 ms @ 100/500/1000 vecs).
- Files: `local_embedding.py:28-33`, `vector_index.py:137-144`
- Cause: No query caching, no vectorized math.
- Improvement path: NumPy-vectorize; cache recent query embeddings; ANN for large corpora.

**Per-page `record_page` connections (residue after WR-01 fix):**
- Problem: `for page in page_records: doc_store.record_page(page)` (`main.py:189-191`) still opens one (now properly closed) connection per page — a 500-page PDF does 500 connect/write/close cycles per upload.
- Files: `main.py:189-191`, `doc_store.py:195-226`
- Cause: Per-op-connection design retained.
- Improvement path: Batch page inserts in one transaction.

## Fragile Areas

**Upload loop persistence ordering:**
- Files: `main.py:115-244`
- Why fragile: Steps 4–7 (extract → pages → embed → chunks → document → cache) are sequential with per-step guards but no atomicity — a failure after `record_page` leaves partial rows (pages without document). `build_index` (in-memory) and `record_chunks` (SQLite) are adjacent but can still diverge on mid-step crash.
- Safe modification: Wrap steps 5+6 in one `try` so chunk-store failure cannot orphan pages; keep `build_index` + `record_chunks` adjacent.
- Test coverage: Unit tests cover `DocStore` round-trips (`tests/test_doc_store.py:199-230` restoration test) but no app-level `main.py` integration test.

**Streamlit rerun semantics + `st.rerun()` in upload loop:**
- Files: `main.py:45-56`, `main.py:115-244`
- Why fragile: Whole script reruns per interaction; correctness depends on session-state init order. `Clear All` wipes index + history without confirmation.
- Safe modification: Never touch session keys outside the init block without a guard; add confirmation for destructive actions.
- Test coverage: None for `main.py`.

**Error paths funnel to generic handlers:**
- Files: `main.py`, `local_llm.py:75-84`
- Why fragile: Embedding OOM/torch errors, Groq 401/429/500, and stream interrupts propagate as tracebacks mid-`st.write_stream`, leaving half-rendered bubbles.
- Safe modification: Wrap generation in `try/except`, append error to `chat_history`, offer retry.
- Test coverage: Only missing-key `ValueError`; no 401/429/500 or interrupt tests.

## Scaling Limits

**In-memory per-session index (unchanged):**
- Current capacity: ~1k vectors ≈ 52 ms/query pure Python; comfortable ceiling low-thousands of chunks + ~766 MB model RAM per session.
- Limit: Tens of thousands of chunks → multi-second scans; concurrent sessions multiply model RAM.
- Scaling path: NumPy/FAISS + disk persistence + per-hash dedup cache; Phase 1's `DocStore` covers metadata + chunks, not vectors.

**Groq Cloud quota (unchanged):**
- Current capacity: Single shared key, `max_tokens=1024`, history per request.
- Limit: 429s under concurrency; history inflates input tokens linearly.
- Scaling path: Per-user keys/quotas, history summarization, token-budget enforcement.

**Single-process Streamlit server (unchanged):**
- Current capacity: Demo-scale single user.
- Limit: No horizontal scaling; one giant PDF blocks all sessions.
- Scaling path: Background ingestion worker; per-user process limits.

## Dependencies at Risk

**Unpinned transitive stack (still open):**
- Risk: `requirements.txt` pins direct deps but `torch`/`transformers`/`tokenizers`/`huggingface-hub` float; no lockfile.
- Impact: Non-reproducible installs; surprise breakage.
- Migration plan: Lockfile (`pip-compile`/`uv.lock`) or explicit pins for `torch` + `transformers` + `numpy`; CPU-only wheel index docs.

**`groq==0.15.0` + `openai/gpt-oss-20b` (still open):**
- Risk: Pinned SDK may lag API; model ID is rename-sensitive. Server-side retirement = 404 on every question with no fallback.
- Impact: Total Q&A outage, cryptic error.
- Migration plan: `GROQ_MODEL` env var with default; 404 → "model unavailable" message.

**`langchain-text-splitters==0.3.6` for one function (low priority, unchanged):**
- Risk: Heavy tree for one `RecursiveCharacterTextSplitter` call; import-path churn risk.
- Impact: Install bloat; potential breakage.
- Migration plan: Vendor a small splitter if churn bites.

## Missing Critical Features

**No app-level tests for `main.py` (highest-value gap, still open):**
- Problem: 54 unit tests cover library modules, but `main.py` (upload/index/chat/rerun/session — where all 3 Criticals lived) has zero tests. The CR-01 regression test covers `DocStore` restoration, not the `main.py` dedup-hit branch itself.
- Blocks: Safe refactor of every Top Risk fix.

**No vector persistence / embedding cache read path (still open):**
- Problem: Documented in `README.md:228,236`; Phase 1 wrote metadata + chunk rows + cache files but vectors are never persisted and cache files never read.
- Blocks: Multi-document libraries, restart resilience without re-embed, Cloud sleep/wake.

**No observability (still open):**
- Problem: Only `print()` (`local_llm.py:17`, `local_embedding.py:22-24`, `pdf_reader.py:60`); no logging framework, error tracking, or latency metrics.
- Blocks: Production diagnosis, quota monitoring, perf tuning.

## Test Coverage Gaps

**Integration paths still without app-level coverage:**
- What's not tested: `main.py` dedup-hit-with-empty-index branch (store-level restoration IS tested in `tests/test_doc_store.py:199-230`, but the Streamlit branch is not); malformed-PDF-in-batch isolation at the `main.py` level; cache read-back (no read path exists).
- Files: `main.py:149-168`, `main.py:176-187`
- Risk: Unit-green / integration-broken can recur for future phases.
- Priority: High.

**Still entirely untested (unchanged priority):**
- What's not tested: `main.py` rerun/session logic; Groq failure modes (401/429/500, stream interrupts, model 404); `add_vector([])` dimension-0 lock (`vector_index.py:77-92`).
- Files: `main.py`, `local_llm.py:75-84`, `vector_index.py:77-92`
- Risk: NumPy migration, persistence, prompt rework can regress silently.
- Priority: High for `main.py` + failure modes; Medium for edge guards.

---

*Concerns audit: 2026-10-11*
