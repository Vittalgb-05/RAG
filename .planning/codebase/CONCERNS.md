# Codebase Concerns

**Analysis Date:** 2026-10-10

## Top 5 Risks (Ordered by Severity)

### 1. Unhandled Groq API / startup failures crash the whole app
- Files: `local_llm.py:23-33`, `local_llm.py:73-81`, `main.py:96-98`
- Risk: **High.** `AiModel.__init__` raises `ValueError`/`ImportError` when `GROQ_API_KEY` is missing, and the streaming call `groq_client.chat.completions.create(...)` has zero `try/except` (rate limits, network outage, invalid key, revoked key, model deprecation of `openai/gpt-oss-20b`). Both execute inside a `st.status` block with no error boundary, so one failure shows a raw traceback and kills the session for every user.
- Fix approach: Wrap `load_ai_model()` and the `ask_a_question_from_pdf_stream` call site (`main.py:233-239`) in `try/except` with `st.error` + `st.stop()`; add retry with backoff for transient Groq errors; validate the key at startup with a clear message.

### 2. No persistence + per-session embedding model = data loss and memory blowup
- Files: `main.py:45-52`, `main.py:141-156`, `local_embedding.py:13-26`, `vector_index.py:30-34`
- Risk: **High.** `VectorIndex` is pure in-memory (`self.vectors`, `self.documents` lists) with no save/load; every server restart or browser session reset forces full re-embedding. Worse, each Streamlit session constructs its own `LocalEmbedding()` → its own `SentenceTransformer("all-MiniLM-L6-v2")` (~80 MB + torch runtime) on first upload instead of sharing one via `@st.cache_resource`. N concurrent users = N model copies in RAM.
- Fix approach: Cache the `SentenceTransformer` with `@st.cache_resource`; keep only the lightweight `VectorIndex` in `st.session_state`; add optional disk serialization (`vectors` + `documents` to `.npz`/JSON keyed by file hash) so re-uploads hit cache.

### 3. Unbounded file upload path enables memory-exhaustion DoS
- Files: `main.py:114-132`, `pdf_reader.py:38-56`
- Risk: **High.** `st.file_uploader(type=["pdf"])` is client-side extension filtering only — no server-side magic-byte check, no size cap, no page/chunk cap. `uploaded_file.getvalue()` loads the entire file into RAM, then copies it again into `io.BytesIO`, then `build_index` embeds all chunks in one batch (`local_embedding.py:56`). A single 500 MB / 10k-page PDF can OOM the Streamlit process for all users. `README.md:228-230` already admits the linear-scan limit.
- Fix approach: Enforce `maxUploadSize` in `.streamlit/config.toml`, reject non-PDF magic bytes (`%PDF`), cap pages/chunks per file, embed in mini-batches with a progress bar, and refuse empty-text PDFs early.

### 4. Filename-keyed dedup causes silent wrong-index behavior
- Files: `main.py:126-156`
- Risk: **Medium-High.** Dedup key is `uploaded_file.name` only. Uploading a *different* file with the same name is silently skipped (stale index); removing a file from the uploader widget does not remove its vectors (no removal path — only nuclear `Clear All`); `chat_history` is wiped without warning on every new upload (`main.py:154-156`). Empty-text PDFs (scanned images) produce zero chunks yet are still marked indexed, enabling chat against an empty index.
- Fix approach: Key on content hash (e.g. SHA-256 of bytes) instead of name; implement per-file removal; confirm before clearing chat; block chat when total chunks == 0 with an "unreadable PDF, OCR needed" message.

### 5. Prompt assembly can overflow context and is injection-prone; displayed sources can lie
- Files: `local_llm.py:47-70`, `main.py:216-227`
- Risk: **Medium-High.** Retrieval uses hardcoded `k=10` chunks of ~1000 chars each (~10k chars) plus up to 10 history messages plus the system prompt, with no token counting or truncation before sending to Groq (`max_tokens=1024` caps output only). Long docs/history risk truncated context or API errors. Separately, `main.py` computes displayed "Sources used" from `search(prompt, k=10)` while generation uses `get_context(f"{last_user_msg} {prompt}", k=10)` — different queries, so the cited sources may not match the context the answer was grounded in. The "answer only from document" instruction (`local_llm.py:56-58`) is trivially overridable by user prompt injection (no delimiter/sanitization).
- Fix approach: Single retrieval call shared by both display and generation; add token-budget truncation (newest history first); wrap document text in explicit delimiters and add an injection-resistant system prompt.

## Tech Debt

**In-memory index, no persistence:**
- Issue: `VectorIndex` (`vector_index.py:30-34`) has no `save`/`load`; `README.md:228` documents this as a known limitation. Re-upload = full re-embed from scratch every run.
- Files: `vector_index.py`, `local_embedding.py:42-59`, `README.md:228`
- Impact: Slow restarts, wasted embedding compute, no cross-session reuse.
- Fix approach: Add `VectorIndex.save(path)` / `load(path)` (pickle or JSON + numpy); key cache entries by file content hash.

**Linear brute-force scan in pure Python:**
- Issue: `VectorIndex.search` (`vector_index.py:137-144`) computes cosine/euclidean distance against *every* stored vector with Python-level loops (`_dot_product`, `_magnitude`). O(n·d) per query with high constant factor (384-dim floats, no NumPy/FAISS).
- Files: `vector_index.py:137-144`, `vector_index.py:201-207`
- Impact: Noticeable latency past a few thousand chunks; acknowledged in `README.md:229`. Query-time embedding (`_embed_one` → full transformer forward pass) dominates small indexes, scan dominates large ones.
- Fix approach: Short term — vectorize with NumPy; long term — ANN (HNSW via `hnswlib`/`faiss`) per `README.md:237`.

**Hardcoded retrieval/generation knobs, no token budgeting:**
- Issue: `k=10` hardcoded at two call sites, `chunk_size=1000`/`chunk_overlap=200` hardcoded, `max_tokens=1024` hardcoded, history window `[-10:]` hardcoded. No shared config, no token counting.
- Files: `main.py:216`, `main.py:231`, `local_llm.py:54`, `local_llm.py:77`, `pdf_reader.py:31-35`
- Impact: Context-window overflow on long docs; tuning requires editing 4 files; behavior drift between display path and generation path.
- Fix approach: Centralize into a config dataclass/module (chunk size, overlap, k, max_tokens, history window); add a token-budget function that truncates oldest context first.

**Dead code — `save_uploaded_pdf` never called, leaks temp files if revived:**
- Issue: `main.py:70-81` defines `save_uploaded_pdf` using `tempfile.NamedTemporaryFile(delete=False)` with no cleanup, but the upload path (`main.py:131-135`) uses `io.BytesIO` directly. The function is dead; if anyone calls it, temp files accumulate in the OS temp dir forever.
- Files: `main.py:70-81`
- Impact: Confusion for future maintainers; latent disk-fill bug.
- Fix approach: Delete the function; if disk-backed parsing is ever needed, use a context manager with guaranteed `os.unlink`.

**Fragile fallback path in `AiModel`:**
- Issue: When `local_embedding is None`, `ask_a_question_from_pdf_stream` rebuilds the index from `pdf_path` (`local_llm.py:41-45`) — but the sole caller passes `pdf_path=""` (`main.py:234`). Invoking the fallback would make `pypdf.PdfReader("")` raise. The parameter is misleading dead weight.
- Files: `local_llm.py:36-45`, `main.py:233-238`
- Impact: Any future caller relying on the `pdf_path` path gets a cryptic crash.
- Fix approach: Remove `pdf_path` param; require `local_embedding` explicitly (raise a clear error if `None`).

**Duplicate model/docstring drift:**
- Issue: `README.md` says "Llama 3" in several places while code uses `openai/gpt-oss-20b` (`local_llm.py:18`); docstring in `main.py:1-12` claims "fully local LLM — no cloud required" while generation is Groq Cloud. `README.md:53` claims "PDF ingestion directly from memory (no disk IO)" which is currently true but contradicts the dead `save_uploaded_pdf` helper.
- Files: `main.py:1-12`, `local_llm.py:18`, `README.md:5-20`
- Impact: Misleading onboarding; wrong mental model for offline expectations.
- Fix approach: Update docstrings/README to state Groq Cloud generation + local embedding consistently.

## Known Bugs

**Same-name files collide; removed files linger in the index:**
- Symptoms: Upload `report.pdf`, then a different `report.pdf` → second file silently ignored. Uncheck/remove a file from the uploader → its chunks remain searchable and cited.
- Files: `main.py:126-156`
- Trigger: Any filename reuse; any uploader deselection.
- Workaround: Click `Clear All` (wipes everything, including chat).

**Empty/scanned PDFs enable chat against an empty index:**
- Symptoms: Image-only PDF yields zero chunks; app still marks it indexed (`chunks: 0`) and enables chat; `get_context` returns `""`, so the LLM answers from nothing while sources UI shows nothing.
- Files: `main.py:144-152`, `local_embedding.py:42-47`, `pdf_reader.py:38-56`
- Trigger: Upload any scanned PDF with no embedded text layer.
- Workaround: None — needs an explicit "no extractable text" error and OCR guidance.

**Page count metadata wrong for multi-chunk docs:**
- Symptoms: Sidebar shows `pages` as `paragraphs[-1]["page"]` (`main.py:150`) — the page of the *last chunk*, which is correct only if every page produced ≥1 chunk. Pages whose `extract_text()` returned `None`/empty (scanned pages, `pdf_reader.py:40-41` skip) are invisible, so the count under-reports without warning.
- Files: `main.py:148-152`, `pdf_reader.py:38-45`
- Trigger: PDFs with a mix of text and image-only pages.
- Workaround: None.

**Sources badge may not match generation context:**
- Symptoms: "Sources used" line lists files from `search(prompt)` while the answer was grounded in `get_context(last_msg + prompt)` — can cite files that were not used, or omit files that were.
- Files: `main.py:216-227`, `local_llm.py:47-54`
- Trigger: Any follow-up question where history contextualization changes ranking.
- Workaround: None — needs a single shared retrieval call.

## Security Considerations

**API key handling (acceptable but brittle):**
- Risk: `GROQ_API_KEY` read from `st.secrets` then `os.environ` (`local_llm.py:23-27`); `load_dotenv()` is called inside the cached `load_ai_model()` (`main.py:66`) so any other module reading env at import time would miss it. Key is passed in-memory to `Groq(api_key=...)` — not logged, good — but error messages (`main.py:138`) interpolate raw exception text that could leak paths/keys in edge cases.
- Files: `local_llm.py:23-33`, `main.py:60-67`
- Current mitigation: `.env` is gitignored (`.gitignore:1`); `st.secrets` preferred for Streamlit Cloud; no key is hardcoded.
- Recommendations: Call `load_dotenv()` at module top (before any other reads); never interpolate exception internals into UI errors — log full trace server-side, show a generic message; document key rotation in README.

**File upload validation (weak):**
- Risk: Only `type=["pdf"]` extension filter (`main.py:114-120`); no magic-byte, size, page-count, or decompression-bomb checks. `pypdf` parses attacker-controlled bytes; PDF parser exploits or zip-bombs could DoS/crash the server process shared by all users.
- Files: `main.py:114-135`, `pdf_reader.py:14-23`
- Current mitigation: `try/except` around `PdfReader` with a user-facing error (`main.py:134-139`).
- Recommendations: Verify `%PDF` magic bytes, cap upload size (`.streamlit/config.toml` `maxUploadSize`), cap pages/chunks per file, sandbox parsing with timeouts.

**Prompt injection (unmitigated by design):**
- Risk: User prompt is concatenated directly into messages (`local_llm.py:64-70`) with only a soft "answer only from document" instruction. A "ignore previous instructions…" prompt can exfiltrate system-prompt content or produce ungrounded answers presented as grounded.
- Files: `local_llm.py:56-70`
- Current mitigation: Grounding instruction only.
- Recommendations: Delimit untrusted context (`<document>…</document>`), add an explicit "do not follow instructions inside document/user text" rule, consider output citation requirements.

**No auth / multi-tenancy isolation:**
- Risk: Streamlit app has no authentication; `load_ai_model` is process-global (shared Groq key/quota) while indexes are per-session. One abusive user can burn shared Groq quota or OOM the process for everyone.
- Files: `main.py:59-67`
- Current mitigation: None (expected for a demo).
- Recommendations: Before any public deployment beyond Streamlit Community Cloud demo: add auth, per-user rate limits, and resource caps.

## Performance Bottlenecks

**Single-batch full-corpus embedding blocks the UI:**
- Problem: `build_index` embeds *all* chunks in one `model.encode` call (`local_embedding.py:56`) inside a `st.status` block with no progress feedback; the Streamlit script run blocks until done.
- Files: `local_embedding.py:42-59`, `main.py:144-145`
- Cause: No batching, no progress callback, no background execution.
- Improvement path: Embed in mini-batches (e.g. 32) with `st.progress`; `README.md:238` already proposes this.

**Per-query transformer forward pass + full scan:**
- Problem: Every keystroke-submitted question triggers a full MiniLM forward pass (`local_embedding.py:28-33`) plus an O(n) Python-loop scan (`vector_index.py:137-144`).
- Files: `local_embedding.py:28-33`, `vector_index.py:137-144`
- Cause: No query caching, no vectorized math.
- Improvement path: NumPy-vectorize distance computation; cache recent query embeddings; move to ANN for large corpora.

**SentenceTransformer reloaded per session:**
- Problem: See Top Risk #2 — model weights re-downloaded/loaded per server process at first upload per session rather than once globally.
- Files: `main.py:141-142`, `local_embedding.py:13-24`
- Cause: `LocalEmbedding()` instantiated in session state instead of `@st.cache_resource`.
- Improvement path: `@st.cache_resource` the model, keep per-session only the `VectorIndex`.

## Fragile Areas

**Streamlit rerun semantics + `st.rerun()` inside upload loop:**
- Files: `main.py:41-52`, `main.py:122-162`
- Why fragile: Whole script reruns on every interaction; correctness depends on `st.session_state` keys initialized in the loop at `main.py:45-52` and on the `st.rerun()` at `main.py:156` after indexing. Misordering (e.g. touching `chat_history` before init) silently resets state. `Clear All` (`main.py:107-112`) wipes index + history without confirmation.
- Safe modification: Never read/write `st.session_state` keys outside the init block without a guard; keep all state mutations (index add, history clear) in one place; add confirmation for destructive actions.
- Test coverage: None — no tests exist in the repo.

**Temp-file helper (dead but dangerous):**
- Files: `main.py:70-81`
- Why fragile: `delete=False` + no `os.unlink` = disk leak; `suffix=f"_{uploaded_file.name}"` embeds user-controlled filenames into temp paths (path-traversal-ish / odd characters on Windows).
- Safe modification: Delete it; use `io.BytesIO` path exclusively (already the live path).
- Test coverage: None.

**PDF text extraction edge cases:**
- Files: `pdf_reader.py:26-61`
- Why fragile: `page.extract_text()` returning `None`/whitespace-only pages are silently dropped with no per-page accounting; `re.sub(r' +', ' ', ...)` doesn't normalize tabs/newlines; encrypted PDFs raise from `pypdf.PdfReader` with only the generic `main.py:138` error; no OCR fallback.
- Safe modification: Count skipped pages and surface "N pages had no extractable text" warning; handle `pypdf.errors.PdfReadError` explicitly; strip empty chunks (`p.strip()` can yield `""` entries that still get embedded).
- Test coverage: None.

**Error paths all funnel to generic handlers:**
- Files: `main.py:134-139`, `main.py:233-239`, `local_llm.py:73-81`
- Why fragile: Only the PDF-parse step has a `try/except`; embedding failures (OOM, torch errors), Groq failures (401/429/500), and stream-interrupt errors propagate as unhandled tracebacks mid-`st.write_stream`, leaving a half-rendered assistant bubble and a chat history entry that is never saved.
- Safe modification: Wrap generation in `try/except`, append an error message to `chat_history` on failure, and offer retry.
- Test coverage: None.

## Scaling Limits

**In-memory per-session index:**
- Current capacity: Comfortable to low-thousands of chunks (each 384-dim float list + dict metadata in Python objects ≈ KBs per chunk + model RAM).
- Limit: Tens of thousands of chunks → multi-second pure-Python scans per question; hundreds of MBs of session RAM; concurrent sessions multiply model RAM.
- Scaling path: NumPy/FAISS backend + disk persistence + per-hash dedup cache (`README.md:236-237`).

**Groq Cloud quota:**
- Current capacity: Single shared key, `max_tokens=1024` per answer, 10 history messages per request.
- Limit: Rate limits (429) under concurrent users; growing history inflates input tokens linearly.
- Scaling path: Per-user keys/quotas, history summarization instead of raw last-10, token-budget enforcement.

**Single-process Streamlit server:**
- Current capacity: Demo-scale (one user at a time on Streamlit Community Cloud).
- Limit: No horizontal scaling, no job queue; one giant PDF blocks all sessions.
- Scaling path: Move ingestion to a background worker / async pipeline; deploy with process-per-user limits.

## Dependencies at Risk

**Unpinned transitive stack + missing `torch`:**
- Risk: `requirements.txt` pins 6 direct deps (`streamlit==1.42.0`, `pypdf==5.3.0`, `python-dotenv==1.0.1`, `langchain-text-splitters==0.3.6`, `groq==0.15.0`, `sentence-transformers==3.4.1`) but the heavy transitive deps (`torch`, `transformers`, `tokenizers`, `huggingface-hub`) float. Fresh installs can pull breaking majors; `torch` CPU/CUDA wheel size (~800 MB–2 GB) also breaks Streamlit Cloud-style deploys unpredictably. No lockfile.
- Impact: Non-reproducible installs; surprise breakage on rebuild.
- Migration plan: Add a lockfile (`pip-compile`/`uv.lock`) or pin `torch` + `transformers` explicitly; document the CPU-only wheel index.

**`groq==0.15.0` + model string `openai/gpt-oss-20b`:**
- Risk: Pinned SDK may lag the API; the model ID looks like a placeholder/rename-sensitive value (README still says "Llama 3"). A server-side model retirement turns every question into a 404 with no fallback.
- Impact: Total Q&A outage with a cryptic error.
- Migration plan: Make model name an env var (`GROQ_MODEL`) with a sane default; handle 404 by surfacing "model unavailable, contact admin".

**`langchain-text-splitters==0.3.6` for one function:**
- Risk: Pulling the LangChain dependency tree for a single `RecursiveCharacterTextSplitter` call is heavyweight for what it does; version bumps in LangChain have historically broken import paths.
- Impact: Install bloat; potential import breakage.
- Migration plan: Low priority — consider vendoring a small splitter or switching to `sentence-transformers`-native chunking if LangChain churn bites.

## Missing Critical Features

**No tests whatsoever:**
- Problem: Zero test files, zero test config, zero CI in the repo. `VectorIndex` (pure logic, easily unit-testable) has only commented-out example usage (`vector_index.py:227-236`).
- Blocks: Safe refactoring of any item above (scan optimization, persistence, rerun-logic changes).

**No persistence / caching of embeddings:**
- Problem: Documented in `README.md:228` and `README.md:236` as future work. Every session re-pays full embedding cost.
- Blocks: Multi-document libraries, restart resilience, Streamlit Cloud sleep/wake cycles.

**No observability:**
- Problem: Only `print()` statements (`local_llm.py:16`, `local_embedding.py:22-24`, `pdf_reader.py:60`); no logging framework, no error tracking, no usage/latency metrics.
- Blocks: Diagnosing production failures, quota monitoring, performance tuning.

## Test Coverage Gaps

**Everything — no test suite exists:**
- What's not tested: `VectorIndex` distances/validation, chunking metadata, rerun/session logic, Groq streaming, error paths. Highest-value first target: `vector_index.py` (cosine/euclidean correctness, dim-mismatch errors, `k` edge cases, empty-index behavior).
- Files: `vector_index.py`, `pdf_reader.py`, `local_embedding.py`, `local_llm.py`, `main.py`
- Risk: Any change (NumPy migration, persistence, prompt rework) can regress silently.
- Priority: High.

---

*Concerns audit: 2026-10-10*
