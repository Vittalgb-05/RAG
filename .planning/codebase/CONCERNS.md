# Codebase Concerns

**Analysis Date:** 2026-10-20

Scope: full repository at commit `2c4e1d0` (working tree). Severity reflects impact on the project's two hard invariants: the 4 GB VRAM ceiling and "zero network egress in local mode", plus data-loss/privacy risk.

## Prior Concern Resolution Status

The `2c4e1d0` commit ("eliminate leaking code, refactor to chatbot-first UI, and resolve CONCERNS.md issues") and the preceding `2978dca` hardening commit are assessed below. Do not treat the commit message as proof of closure.

| Previously-flagged concern | Status | Evidence |
|---|---|---|
| Purge re-ingestion loop | **Partially closed — new loop introduced** | `uploader_key` is rotated on Clear/Purge (`main.py:70`, `ui/views.py:669`) but **not after a successful upload**. Combined with dedupe returning `success=True` (`ui/ingestion_service.py:97-108`), the post-upload `st.rerun()` (`ui/views.py:136-137`) re-runs with the same files still in the widget and reruns forever. See Known Bugs #1. |
| No startup hydration | **Largely closed, shallow** | `hydrate_startup_state()` restores SQLite docs and opens LanceDB (`ui/hydration.py:13-58`, called at `main.py:142`). It never verifies that each `indexed` SQLite doc actually has vectors, and does not hydrate `failed` docs. See Known Bugs #4. |
| Docker local-inference env mismatch | **Largely closed for Compose, open for standalone image** | `LLAMA_SERVER_URL`/`HOST`/`PORT` parsing and `host.docker.internal` allowlist in `llama_cpp_provider.py:44-73`; `docker-compose.yml:18-19` sets the host. A bare `docker run` (no Compose env) still defaults to `127.0.0.1:8080` *inside the container*, which cannot reach a host llama-server. |
| Python 3.13 OCR gap | **Partially closed, unverified** | Conditional pins in `requirements.txt:13-14` (`rapidocr` for ≥3.13) and RapidOCR v3 output handling in `ocr_fallback.py:154-197`. CI only tests Python 3.11 (`.github/workflows/ci.yml:12-18`); `docs/RUNBOOK.md:17` still states 3.11/3.12; `setup.py:722-729` classifies only 3.11/3.12. No 3.13 CI evidence. |
| Duplicate visual detection | **Closed (functionally)** | SHA-256 region cache in `visual_analyzer.py:64-66,145`. `IngestionService` still calls `detect_visual_regions()` and then `analyze_visual_elements()` (which detects again), but the second pass is cached (`ui/ingestion_service.py:160-172`). Extra call, no extra PyMuPDF work. |
| Unindexed LanceDB search | **Open** | Dedupe trusts SQLite status/chunk count only (`ui/ingestion_service.py:97-108`); hydration trusts `retriever.count_chunks() > 0` globally (`ui/hydration.py:47-56`). If `data/lancedb/` is deleted or a doc's vectors are missing, the UI still enables chat and retrieval silently returns nothing. |
| Ungated VLM inference | **Largely closed, with a data-quality leak** | `InferenceGate.hold(timeout=60.0)` wraps `analyze_image` (`visual_analyzer.py:272-281`). On timeout/failure the error string is written as the element content (`visual_analyzer.py:282-284`) and then **indexed as retrievable evidence** (`ui/ingestion_service.py:216-217,247-248`). |
| PyMuPDF AGPL licensing | **Disclosure closed, compliance risk open** | `docs/LICENSES.md` documents AGPL-3.0/commercial terms. PyMuPDF remains a hard runtime dependency (`requirements.txt:15`) and `README.md:247-249` still describes the project as MIT only. |
| Test gaps | **Partially closed** | ~285 test functions in 29 files, including concurrency, hydration, cloud privacy, and ingestion-empty-case tests. Still no end-to-end ingestion test, no coverage gate, no Python-version matrix, and no test for the upload rerun loop. See Test Coverage Gaps. |

---

## Tech Debt

**Legacy workspace aliases and duplicated routing:**
- Issue: `WORKSPACES` uses `"Chat"` but `ui/views.py:640` still sets `active_workspace = "Ask Documents"`, and `main.py:295-296,333` keeps backward-compatible aliases (`"Workspace"`, `"Ask Documents"`, `"Library"`).
- Files: `main.py:287-308,331-358`, `ui/views.py:638-641`
- Impact: Two sources of truth for navigation; future renames require touching three places.
- Fix approach: Introduce a single `Workspace` enum/constant module, have `render_library_view` set `"Chat"`, and drop alias branches once tests are updated.

**Dead code / unused parameters:**
- Issue: `safe_has_secret()` (`main.py:46-53`) and `MAX_CHAT_TURNS` (`main.py:43`) are unused; `render_chat_view(doc_store=...)` and `render_settings_view(ai_model=...)` accept parameters they never use (`ui/views.py:184-189,684-690`). `LocalEmbedding.store` (`local_embedding.py:72`) is constructed but the ingestion path uses `HybridRetriever` instead.
- Files: `main.py`, `ui/views.py`, `local_embedding.py`
- Impact: Misleads readers and static analysis; no runtime effect.
- Fix approach: Remove unused symbols/params or use them; delete the dead `VectorIndex` path in `LocalEmbedding` once legacy callers are gone.

**Promised library features are absent:**
- Issue: The docstring promises "retry, re-index" (`ui/views.py:594`) but the UI exposes only Chat/Delete plus a global purge.
- Files: `ui/views.py:590-676`
- Impact: A `failed` document can only be retried by deleting and re-uploading; there is no way to rebuild vectors after a LanceDB loss.
- Fix approach: Add per-document "Re-index" (re-run `IngestionService.ingest_pdf` with `force`) and "Retry" actions, or correct the docstring/UI copy.

**Doc/implementation drift:**
- Issue: `docs/RUNBOOK.md:17` excludes Python 3.13; `README.md` does not mention the AGPL disclosure or the mandatory local `llama-server`; `CLAUDE.md` still describes the old Groq-only/SQLite-less stack.
- Files: `docs/RUNBOOK.md`, `README.md`, `CLAUDE.md`, `docs/LICENSES.md`
- Impact: New contributors and operators follow stale setup instructions.
- Fix approach: Regenerate `CLAUDE.md` from the current map and align RUNBOOK/README with `requirements.txt`, Compose, and the licensing doc.

**Dual rendering fallbacks (`st.html` vs `st.markdown(unsafe_allow_html=True)`):**
- Issue: Every component has a runtime `hasattr(st, "html")` branch (`ui/components.py:63-66,80-83,107-110`; `main.py:267-270,321-324`; `ui/views.py:239-242,315-318,630-633,720-723,733-736`).
- Files: `ui/components.py`, `ui/views.py`, `main.py`
- Impact: Two rendering paths with different escaping semantics; the fallback is the path that caused the earlier "leaking HTML" bug.
- Fix approach: Pin Streamlit ≥ the version that guarantees `st.html`, then delete the fallback branches and always escape interpolated user data.

**No centralized logging configuration:**
- Issue: Modules emit `logger.info`/`logger.warning`, but nothing calls `logging.basicConfig`; several modules still use `print` for diagnostics (`doc_store.py:154`, `upload_validation.py:106`, `pdf_reader.py:131`).
- Files: `logging_setup.py`, `doc_store.py`, `upload_validation.py`, `pdf_reader.py`
- Impact: Ingestion diagnostics are usually dropped at the default `WARNING` level, while `print` lines leak filenames/doc IDs to stdout unredacted.
- Fix approach: Configure the root logger once in `main.py`/`start.py` from an env-controlled level, replace `print` with module loggers, and redact filenames at INFO if logs are shared.

**Unpinned runtime ranges vs. lockfile:**
- Issue: `requirements.txt` uses open ranges for the riskiest packages (`docling>=2.0.0`, `lancedb>=0.17.0`, `pymupdf>=1.24.0`, `litellm>=1.50.0`, `numpy>=1.26,<3`), while `requirements-lock.txt` pins specific versions (docling 2.138.0, lancedb 0.40.0, pymupdf 1.28.2, numpy 2.4.6, torch 2.14.1) that CI uses.
- Files: `requirements.txt`, `requirements-lock.txt`, `Dockerfile:30-31`, `.github/workflows/ci.yml:24-27`
- Impact: Docker builds and local installs can resolve different versions than CI; a future `docling`/`lancedb` minor can break the API at any time.
- Fix approach: Make the lockfile authoritative (`pip install -r requirements-lock.txt` in Docker and setup), or use `uv sync` with a checked-in `uv.lock` and a single install path.

---

## Known Bugs

**Infinite rerun / re-ingestion loop after a successful upload (P0):**
- Symptoms: After uploading one or more PDFs, the sidebar status flickers "Ready! Indexed 1 file(s)" indefinitely and the Streamlit script saturates a CPU core; the app never becomes idle.
- Files: `ui/views.py:72-137`, `ui/ingestion_service.py:97-108`, `main.py:70`
- Trigger: Upload any valid PDF, let ingestion finish. The uploader widget retains its files; `st.rerun()` re-executes the block; dedupe returns `success=True`; `new_docs_indexed` becomes 1 again; `st.rerun()` fires again.
- Workaround: Manually remove the file from the uploader (or use "Clear Session") after ingestion.
- Fix approach: Rotate `st.session_state.uploader_key` immediately after processing any upload (success or failure) before `st.rerun()`, and/or only count a document in `new_docs_indexed` when it was actually newly indexed, not when deduped. Add a regression test that calls the render function twice with the same fake uploader payload.

**Purge/Delete does not erase everything it claims to erase (privacy):**
- Symptoms: After "Purge All Data Now", previously retrieved document text and citations remain visible in the chat transcript, and full extracted page/chunk text remains on disk in `.cache/<sha256>/<CONFIG_VERSION>/pages.json` and `chunks.json`.
- Files: `ui/views.py:659-676` (purge leaves `chat_history`, `.cache`, `local_embedding`, and `selected_chat_doc` untouched), `ui/views.py:163-176` and `643-655` (single-doc delete leaves the cache dir and `summary_<doc_id>_*` session keys), `ui/ingestion_service.py:278-288` (cache writer)
- Trigger: Upload → chat → Purge All Data Now, then inspect the chat pane or `.cache/`.
- Fix approach: On purge, also clear `chat_history`, `selected_chat_doc`, `selected_summary_doc`, summary session keys, and remove `.cache/` (or all per-doc cache dirs). On single delete, remove `cache_dir_for(base, sha)` and the doc's summary keys. Make the purge copy accurately state what is removed.

**Deduped upload silently succeeds when vectors are missing:**
- Symptoms: Chat is enabled, retrieval returns zero snippets, and the model abstains or (older behavior) answers without evidence, even though the library shows the document as indexed with N chunks.
- Files: `ui/ingestion_service.py:97-108`, `ui/hydration.py:47-56`, `ui/views.py:372-390`
- Trigger: Delete `data/lancedb/` (or the fallback JSON) while `data/documents.db` survives, then re-upload the same PDF. SQLite says `indexed` / `num_chunks > 0`, so ingestion short-circuits.
- Fix approach: In the dedupe branch, verify `self.retriever.has_document(doc_id)` (and chunk count) before returning success; otherwise re-index from the SQLite chunks/cache. In hydration, filter `document_metadata` to docs present in the retriever, or expose a "vectors missing" state.

**Cloud consent "Cancel" can re-open the dialog indefinitely:**
- Symptoms: Toggling "Enable Cloud Inference" on, then pressing "Cancel (Keep 100% Local)", immediately shows the consent dialog again; the toggle remains on.
- Files: `ui/views.py:699-713`, `main.py:219-225`
- Cause: The toggle is keyed `settings_cloud_toggle` and its session value stays `True`; the cancel handler sets `cloud_mode=False` but not the widget key. On rerun `cloud_active != cloud_mode`, so the dialog is requested again.
- Fix approach: Key the toggle to a state variable that is reset in both consent branches, or use an `on_change` callback that sets `st.session_state.settings_cloud_toggle = False` on cancel. Add a Streamlit AppTest regression test.

**Visual evidence is attributed to the doc_id, not the filename:**
- Symptoms: Citation chips and evidence drawers for VLM-derived chunks show `doc_ab12…` instead of `report.pdf`.
- Files: `hybrid_retriever.py:389` (`"filename": el.doc_id`), `ui/views.py:305-333,419-440`
- Trigger: Upload a PDF with a figure, ask about it.
- Fix approach: Pass/store the original filename in `EvidenceElement` (or look it up from `DocStore` in `index_evidence_elements`) and index that as `filename`.

**Failed VLM analyses become searchable "evidence":**
- Symptoms: Answers cite "[Visual element: analysis failed: InferenceGate acquisition timed out…]" or "[Visual element: vision analysis unavailable]" as if it were document content.
- Files: `visual_analyzer.py:282-294`, `ui/ingestion_service.py:216-217,247-248`, `hybrid_retriever.py:383-400`
- Trigger: Start a long chat generation in another session (holds `InferenceGate` > 60 s) while uploading a PDF with figures, or run with a non-vision local model.
- Fix approach: Skip persistence/indexing of placeholder/error elements (filter on a `status`/`analysis_ok` field), and surface a per-document "N figures not analyzed" warning instead.

**Library "Chat" button writes a legacy workspace value:**
- Symptoms: Navigation works, but `st.session_state.active_workspace` is `"Ask Documents"` until the user next touches the radio.
- Files: `ui/views.py:638-641`, `main.py:331-339`
- Fix approach: Set `"Chat"` directly.

---

## Security Considerations

**No authentication and a network-exposed default in Docker (High):**
- Risk: Anyone who can reach port 8501 can upload documents, read all persisted documents, toggle cloud mode with their own key, and purge data. There is no login, session isolation by user, or CSRF-protected auth layer (Streamlit's XSRF token is not authentication).
- Files: `Dockerfile:47-53` (`--server.address=0.0.0.0`), `docker-compose.yml:7-8` (`ports: 8501:8501` published on all interfaces), `.streamlit/config.toml`
- Current mitigation: Local-only design assumption; XSRF protection enabled.
- Recommendations: Default Compose to `127.0.0.1:8501:8501`, document a reverse proxy with auth (or Streamlit OIDC) for any shared host, and refuse to bind `0.0.0.0` unless an explicit `--allow-network` flag is set.

**Docker build context includes secrets and multi-GB model weights (High):**
- Risk: `.dockerignore` omits `.env`, `models/`, `*.gguf`, `.planning/`, `tests/`, and `application_screenshots/`. A local `.env` present at build time (absent now) would be copied into an image layer by `COPY . .`; 2.2 GB of GGUF weights in `models/` would also be copied, bloating the image and potentially redistributing model weights.
- Files: `.dockerignore`, `Dockerfile:33-38`, `models/` (2.2 GB locally: `qwen3-vl-2b-instruct-q4_k_m.gguf`, `mmproj-f16.gguf`), `.gitignore:1,18-19`
- Current mitigation: `models/` and `.env` are gitignored, so they are not in git.
- Recommendations: Add `.env`, `.env.*`, `models/`, `*.gguf`, `*.onnx`, `.planning/`, `tests/`, `application_screenshots/`, `data/`, and `.cache/` to `.dockerignore`; consider a dedicated `models` build stage or a runtime download to a mounted volume.

**Delete/Purge leaves document text on disk (High privacy):**
- See Known Bugs #2. Extracted page/chunk text persists under `.cache/<sha>/<version>/` and in the chat transcript after the user is told data was erased.
- Files: `ui/views.py:659-676`, `ui/ingestion_service.py:277-288`
- Recommendations: Make purge the single source of truth for erasure, including cache and transcript; add a test asserting the cache directory and chat history are empty afterwards.

**Prompt injection can reach the system message (Medium):**
- Risk: Retrieved document text is interpolated into the **system** prompt (`prompt_budget.py:21-23,114`), which is the highest-trust position. The only structural defense is escaping `</document_context>` (`prompt_budget.py:26-40`), and output detection is a 13-phrase blocklist (`citation_validator.py:34-47,70-83`) that a paraphrase trivially bypasses. A malicious PDF can therefore steer answers or exfiltrate the system prompt through markdown links.
- Files: `prompt_budget.py`, `citation_validator.py`, `ui/sanitizer.py`
- Current mitigation: Explicit "treat as untrusted" instruction in the system prompt; XML boundary escaping; blocklist; citation-precision verification.
- Recommendations: Move untrusted context to the user message (or add a separate context role), delimit each snippet with non-guessable markers, strip/neutralize link syntax in local mode, and add a canary-based injection test rather than relying on phrase matching.

**Local-mode sanitizer does not block links or arbitrary HTML (Medium):**
- Risk: `sanitize_markdown_for_local` removes Markdown images, `<img>` tags, and `<script>` (`ui/sanitizer.py:19-49`) but leaves `[text](https://…)`, `<a href>`, `<iframe>`, CSS `url(...)`, and other browser-initiated requests. The test only asserts that the image URL is removed; the `[click](https://evil.com)` link in the same fixture is not asserted (`tests/test_ui_smoke.py:113-124`).
- Files: `ui/sanitizer.py`, `tests/test_ui_smoke.py`
- Current mitigation: External images/scripts are blocked; "zero egress" is true for automatic image loads only.
- Recommendations: Strip or rewrite all external link targets in local mode (`[text]` without href), strip `iframe`/`object`/`embed`/`style`, and update the test to assert the link target is gone.

**Cloud consent can be bypassed programmatically (Medium, latent):**
- Risk: `AiModel._detect_provider()` constructs a `GroqProvider` whenever `cloud_mode=True` and no `cloud_provider` was supplied (`local_llm.py:174-181`). `GroqProvider` has no consent gate (`groq_provider.py:18-52,128-161`), unlike `LiteLLMProvider._assert_consent()` (`litellm_provider.py:142-148`). Any caller using `AiModel(cloud_mode=True)` or `set_cloud_mode(True)` without a consented provider can transmit prompts without consent. UI paths currently pass a consented provider, so this is a latent footgun.
- Files: `local_llm.py`, `groq_provider.py`, `litellm_provider.py`
- Recommendations: Remove the silent Groq fallback from `_detect_provider`, or give `GroqProvider` the same `user_consented`/`_assert_consent` contract. Add a test that `AiModel(cloud_mode=True)` cannot perform a network generation without consent.

**Setup downloads and extracts archives without integrity or path checks (Medium):**
- Risk: `download_file_with_progress` verifies only minimum size, not a SHA-256 (`setup.py:103-193`); `download_and_extract_archive` calls `zipfile.extractall` / `tarfile.extractall` with no member-path validation (`setup.py:341-346`), enabling Zip Slip if a mirror or TLS endpoint is compromised. Model and llama-server binaries are then executed (`setup.py:427,482`).
- Files: `setup.py:103-193,308-357,359-493`
- Current mitigation: HTTPS from Hugging Face/GitHub; size floor.
- Recommendations: Pin SHA-256 digests per artifact, verify before extraction, use `zipfile` member checks (reject `..`/absolute paths) and `tarfile.extractall(..., filter="data")` on Python ≥3.12, and run the downloaded `llama-server --version` only after verification.

**Cloud API keys have uneven redaction (Low):**
- Risk: `LiteLLMProvider._scrub_credentials` redacts keys from errors (`litellm_provider.py:135-140`), but `GroqProvider` errors are surfaced unscrubbed (`groq_provider.py:125-126,160-161`), and `ui/views.py:453-454` displays the raw exception in the browser.
- Files: `groq_provider.py`, `ui/views.py`
- Recommendations: Centralize a `redact_secrets()` helper and apply it to every provider exception and `st.error` sink.

**First-run Hugging Face egress and no encryption at rest (Low):**
- Risk: `LocalEmbedding` instantiates `SentenceTransformer("all-MiniLM-L6-v2")` without `local_files_only` (`local_embedding.py:27-42,70`); on a fresh machine or container this performs network I/O before "local mode" is usable. SQLite and `.cache` store extracted document text unencrypted.
- Files: `local_embedding.py`, `doc_store.py`, `ui/ingestion_service.py`
- Recommendations: Set `HF_HUB_OFFLINE=1` after setup, document the first-run download explicitly, and consider SQLCipher or OS-level disk encryption guidance for shared laptops.

---

## Performance Bottlenecks

**Native FTS index is effectively never created; every query tokenizes the corpus (High):**
- Problem: `create_fts_index()` is called only in the legacy `merge_insert`-unavailable branch (`hybrid_retriever.py:353-366`). The normal "create new table" path (`hybrid_retriever.py:340-343`) and the `merge_insert` path (`hybrid_retriever.py:346-352`) never call it. After a restart, `_fallback_store` is empty in LanceDB mode (`hybrid_retriever.py:121-133` only loads the JSON when LanceDB is unavailable), so `_bm25_search_fallback` reads up to 10,000 rows from LanceDB and re-tokenizes them on every question (`hybrid_retriever.py:475-535`).
- Files: `hybrid_retriever.py`
- Cause: FTS creation omitted from the primary write path; no migration/backfill on open.
- Improvement path: Call `create_fts_index()` after table creation and after `merge_insert`; on `_init_table`, check for an FTS index and build one if absent. Cache tokenized BM25 stats or use LanceDB's native FTS (`search_fts` already attempts it at `hybrid_retriever.py:550-560`).

**Docling converter and RapidOCR engine are rebuilt per document (High):**
- Problem: `IngestionService` constructs `DoclingReader(...)` per file (`ui/ingestion_service.py:116-121`), and `DoclingReader` builds a fresh `DocumentConverter` with pipeline options on every call (`docling_reader.py:126-132`). `apply_conditional_ocr` builds `OcrEngine()` per call (`ocr_fallback.py:346`), and `OcrEngine.__init__` eagerly instantiates RapidOCR (`ocr_fallback.py:70-76`). Multi-file uploads therefore pay model-loading cost repeatedly.
- Files: `docling_reader.py`, `ocr_fallback.py`, `ui/ingestion_service.py`
- Cause: No process-level singleton for heavy extractors (contrast with the embedding model cache in `local_embedding.py:24-42`).
- Improvement path: Reuse one `DocumentConverter` and one `OcrEngine` per `IngestionService`/process, guarded by a lock; add lazy-init and a bounded LRU if memory is a concern.

**Synchronous ingestion blocks the script and can starve the GPU gate (Medium):**
- Problem: Docling, OCR, embeddings, and up to six VLM calls all run inline in the Streamlit script (`ui/ingestion_service.py:110-275`). `analyze_visual_elements` supports a `progress_callback` (`visual_analyzer.py:209,260-264`) but `IngestionService` never passes one, so the UI shows only "Analyzing N visual elements…". Each VLM call waits up to 60 s on `InferenceGate` (`visual_analyzer.py:277`); a long chat generation in another session can time out every figure.
- Files: `ui/ingestion_service.py:145-174`, `visual_analyzer.py:272-284`, `local_llm.py:298-311`
- Improvement path: Pass the progress callback through, reduce `max_regions` for large documents, and run ingestion in a background thread/queue with a job-status surface so the script does not block. Treat gate timeouts as retryable rather than writing failure text.

**OCR thread pool is serialized by a single lock (Medium):**
- Problem: `apply_conditional_ocr` submits up to 4 page jobs (`ocr_fallback.py:388-408`), but `OcrEngine.ocr_page_image` holds `self._ocr_lock` for the entire recognition call (`ocr_fallback.py:143-154`). Rendering may overlap; recognition does not. ONNX Runtime already manages intra-op threads.
- Files: `ocr_fallback.py:68,143-154,388-408`
- Improvement path: Remove the Python-level lock (RapidOCR instances are reusable per thread) or create a small recognizer pool; benchmark before adding concurrency, and keep a per-engine lock only if the backend is not thread-safe.

**Every rerun can double-probe llama-server (Medium):**
- Problem: `main.py:155,187` calls `check_health()` on every interaction. When unhealthy, `AiModel.check_health` creates a second provider and probes again (`local_llm.py:193-207`). With `httpx.Timeout(connect=2.0)` (`llama_cpp_provider.py:82`) that can add ~4 s to every click while the server is down; in Docker the host lookup can be slower.
- Files: `main.py:187-189`, `local_llm.py:187-207`, `llama_cpp_provider.py:89-141`
- Improvement path: Cache health for 3-5 s (like `resource_telemetry.get_gpu_memory_info`), reuse the existing provider for the second probe when its type matches, and use a shorter connect timeout for background probes.

**Document-filtered retrieval filters after candidate generation (Medium):**
- Problem: `search_hybrid` requests `candidate_pool` from the whole corpus, then drops non-matching docs (`hybrid_retriever.py:592-610`). With many documents and a single-doc filter, the surviving set can be much smaller than `k` even though relevant chunks exist.
- Files: `hybrid_retriever.py:566-679`
- Improvement path: Push the `doc_id` predicate into the LanceDB query (`table.search(...).where(...)`, escaping with `_escape_sql_literal`) and into the BM25 candidate selection; if post-filtering is kept, scale the pool by corpus size or retry with a larger pool when fewer than `k` survive.

**LanceDB score is computed with the wrong metric assumption (Medium):**
- Problem: `search_dense` calls `table.search(query_vector)` without `.metric("cosine")` and converts `_distance` as if it were cosine distance (`hybrid_retriever.py:438-447`). LanceDB's default is L2; for normalized vectors L2 = sqrt(2-2cos), so displayed scores are not cosine similarities (rank order is preserved, which is why retrieval still works).
- Files: `hybrid_retriever.py:425-463`
- Improvement path: Specify `.metric("cosine")` at query time and in table creation, or convert with `score = 1 - (dist**2)/2` for normalized vectors. Add a test asserting cosine-equivalent scores.

**Per-session duplicate vector state (Low-Medium):**
- Problem: `index_chunks` always appends every chunk/vector to the pure-Python `_fallback_store`, even when LanceDB is active (`hybrid_retriever.py:297-310`). Every Streamlit session creates its own `HybridRetriever` (`ui/hydration.py:47-56`), so RAM grows per open tab and the fallback JSON is only persisted in non-LanceDB mode.
- Files: `hybrid_retriever.py:113-119,297-310`, `ui/hydration.py`
- Improvement path: Keep the fallback store empty when `is_persistent()`, or load it lazily only on LanceDB failure; make the retriever a process-level cached resource with per-session query wrappers.

**Summarizer holds the GPU gate for the whole map-reduce (Medium):**
- Problem: `Summarizer.summarize_document` acquires `InferenceGate` around all map, consolidation, and reduce calls (`summarizer.py:388-395`). A long document can hold the gate for minutes; concurrent chat requests wait 60 s and then return the "System is busy" message (`local_llm.py:298-301`).
- Files: `summarizer.py:233-299,388-395`
- Improvement path: Acquire/release per provider call (map/reduce step) rather than around the whole pipeline, or add a queue with explicit progress and cancellation. Document the expected wait in the UI.

**SQLite lacks an index on `chunks.doc_id` (Medium):**
- Problem: Only primary keys and the summary indexes are declared (`doc_store.py:17-94`). `get_chunks_for_doc`, `delete_document`, and `purge_all` scan the chunks table by `doc_id` (`doc_store.py:340-362,587-619`); summarization calls `get_chunks_for_doc` for every uncached profile.
- Files: `doc_store.py`
- Improvement path: Add `CREATE INDEX idx_chunks_doc_id ON chunks(doc_id)` as schema v4, plus `pages(doc_id)` if needed; keep migrations additive.

**Raw PDF bytes are copied repeatedly (Low):**
- Problem: `UploadedFile.getvalue()` returns a full bytes copy (`ui/views.py:89`), then `DoclingReader` stores `_raw_bytes` (`docling_reader.py:51-69`), eagerly constructs a `PdfReader` over `io.BytesIO(self._raw_bytes)` (`docling_reader.py:73`), and `PdfReader` hashes the stream again (`pdf_reader.py:32-37`).
- Files: `ui/views.py`, `docling_reader.py`, `pdf_reader.py`
- Impact: Peak RSS for a 50 MB PDF can exceed several hundred MB during ingestion.
- Improvement path: Pass the bytes/hash through the pipeline rather than re-reading/hashing; construct the fallback reader lazily.

**Local llama-server stays resident in cloud mode (Low):**
- Problem: Switching to cloud only closes the HTTP client (`local_llm.py:164-166`); the `llama-server` process (started by `start.py` or Compose) keeps its VRAM allocated.
- Files: `local_llm.py:145-166`, `start.py:114-178`, `docker-compose.yml:30-55`
- Improvement path: Document that cloud mode does not free VRAM, or expose a "stop local engine" action in Settings that terminates the managed process.

---

## Fragile Areas

**`ui/views.py` (829 lines) — view logic and orchestration in one module:**
- Files: `ui/views.py` (sidebar ingestion loop, chat retrieval/streaming, summary cache, library CRUD, settings/privacy)
- Why fragile: The upload loop mixes widget state, DB writes, session mutation, reruns, and service construction (`ui/views.py:72-137`); chat mixes query contextualization, retrieval, prompt assembly, streaming, citation validation, and history mutation (`ui/views.py:350-465`). Any new feature touches a long, side-effect-heavy function.
- Safe modification: Extract upload orchestration into a testable function that takes an explicit file list and returns a result, and move chat turn construction into a `ChatService`. Add Streamlit AppTest coverage before moving code.
- Test coverage: Only data-shape tests (`tests/test_main_ui.py`); the actual render functions are not exercised.

**Dedupe ↔ hydration ↔ retriever consistency:**
- Files: `ui/ingestion_service.py:97-108`, `ui/hydration.py:30-56`, `hybrid_retriever.py:220-229`
- Why fragile: Three independent notions of "indexed" (SQLite status, SQLite chunk count, LanceDB `count_chunks`/`has_document`) can disagree. There is no reconciliation job.
- Safe modification: Always gate UI enablement and dedupe on `retriever.has_document(doc_id)` in addition to SQLite; add a repair routine that re-indexes docs present in SQLite but absent from the retriever.
- Test coverage: None for the mismatch scenario.

**`InferenceGate` is process-local and timeout-based:**
- Files: `local_llm.py:26-90`, `visual_analyzer.py:277`, `summarizer.py:389`
- Why fragile: It protects a single Streamlit server process only; multiple replicas/processes (Compose scaling, `streamlit` workers in the future) each have their own lock and can still collide in VRAM. Timeouts surface as user-visible "busy" messages or indexed error text.
- Safe modification: Keep the gate, but add a process-wide queue/backpressure signal and treat timeouts as retryable; if multi-process deployment is ever supported, move the lock to a cross-process primitive.
- Test coverage: Good unit coverage of the gate itself (`tests/test_concurrency_lock.py`), none across processes or with a real GPU.

**Streamlit session state as the source of truth:**
- Files: `main.py:45-89,109-129`, `ui/hydration.py`, `ui/views.py:100-119`
- Why fragile: Document metadata, retriever handles, cloud credentials, consent, and chat history live in a per-tab dict that is reset on restart; hydration is one-shot and gated by `_startup_hydrated`. A partial reset (`_reset_session_security_state`) can leave stale keys (`selected_chat_doc`, `_queued_prompt`, `settings_cloud_toggle`).
- Safe modification: Centralize every key in one initializer/`reset` function, and add a test that enumerates keys and asserts the reset result.
- Test coverage: Partial (`tests/test_ui_smoke.py`, `tests/test_main_ui.py` simulate logic but do not call the helpers that own the state in `main.py`, except `_reset_session_security_state`).

**Untrusted-PDF parsing in-process:**
- Files: `upload_validation.py:64-113`, `docling_reader.py:125-318`, `ocr_fallback.py:84-129`, `visual_analyzer.py:49-200`
- Why fragile: Caps exist (50 MB, 500 pages, 2048² pixels), but parsing/extraction has no timeout, memory cap, or subprocess isolation. A crafted PDF can still cause long CPU stalls or OOM through decompression or pathological layout.
- Safe modification: Run extraction in a worker subprocess with a wall-clock/memory limit; keep the existing size/page/pixel caps as the first line of defense.
- Test coverage: Only happy-path and empty-page cases; no malicious/fuzz corpus.

---

## Scaling Limits

**Vector store:**
- Current capacity: LanceDB on disk; linear scan fallback in `VectorIndex` (`vector_index.py`); `_bm25_search_fallback` reads at most 10,000 rows (`hybrid_retriever.py:484`).
- Limit: Fallback mode is O(N) per query and holds all vectors in RAM; native FTS is not built on the primary write path (see above). With no ANN index configuration, LanceDB still scans partitions but is far more scalable than the fallback.
- Scaling path: Guarantee LanceDB availability, create the FTS index on write, add an ANN index (IVF-PQ/HNSW) once the corpus exceeds ~100k chunks, and remove the per-session Python fallback copy.

**VRAM / context:**
- Current capacity: One active local model, 4,096-token context (`llama_cpp_provider.py:31,44-54`), 1,024 output tokens (`local_llm.py:308`), VLM at `-ngl 28` with an f16 mmproj (`start.py:127-149`, `docker-compose.yml:45-53`).
- Limit: A 2B Q4 model plus a 1.33 GB f16 projector plus 4K KV cache is close to the 4 GB ceiling; longer contexts or a second concurrent process will OOM.
- Scaling path: Quantize the mmproj, reduce `-ngl`/context, keep one server process, and expose the current budget in Settings (telemetry already reports VRAM: `resource_telemetry.py:33-97`).

**Ingestion throughput:**
- Current capacity: Sequential Docling → OCR (conditional) → embeddings (CPU) → up to 6 VLM calls per PDF, all inline.
- Limit: Large scanned documents (500 pages) can take many minutes and block the UI; multi-file uploads reload models per file.
- Scaling path: Reuse extractor singletons, batch embeddings, cap pages/regions by config, and move ingestion to a background job with progress/cancel.

**Session scaling:**
- Current capacity: Each browser session constructs its own `AiModel`, `HybridRetriever`, and `LocalEmbedding` wrapper; the SentenceTransformer weights are shared via `_MODEL_CACHE` (`local_embedding.py:24-42`).
- Limit: Memory and open LanceDB handles scale with concurrent tabs; `InferenceGate` serializes all inference anyway, so extra sessions add latency, not throughput.
- Scaling path: Cache the retriever/embedding as process-level resources (`@st.cache_resource`) with per-session query state, and document the single-user assumption.

---

## Dependencies at Risk

**PyMuPDF (AGPL-3.0 / commercial):**
- Risk: Copyleft/commercial obligations for network distribution; already disclosed but not resolved.
- Impact: Distributing the Docker image or hosting the app publicly may require an Artifex commercial license or a permissive renderer.
- Files: `requirements.txt:15`, `docs/LICENSES.md`, `ocr_fallback.py`, `visual_analyzer.py`
- Migration plan: Abstract rendering behind an interface and offer `pypdfium2` (Apache/BSD) as an alternative for rasterization/cropping; keep PyMuPDF as an opt-in extra.

**Unpinned `docling`, `lancedb`, `litellm`, `pymupdf`, `numpy`:**
- Risk: Breaking API/behavior changes on any fresh install; CI and Docker can diverge.
- Impact: Ingestion or retrieval APIs (`DoclingReader`, `merge_insert`, `search(query_type="fts")`) are version-sensitive.
- Files: `requirements.txt`, `requirements-lock.txt`, `Dockerfile`
- Migration plan: Install from the lockfile everywhere and add a scheduled dependency-update job that runs the test suite.

**`torch`/CUDA wheel drift (transitive via sentence-transformers):**
- Risk: `requirements.txt` does not pin torch; the lockfile pins `torch==2.14.1` with platform-specific CUDA variants. On Linux, default PyPI wheels pull large CUDA libraries; on a 4 GB laptop this is disk/RAM overhead and can conflict with the llama-server CUDA runtime.
- Files: `requirements.txt:10`, `requirements-lock.txt:541-549`, `Dockerfile`
- Migration plan: Pin a CPU-only torch wheel (`--index-url https://download.pytorch.org/whl/cpu`) for the embedding path and document the separate llama.cpp CUDA runtime.

**RapidOCR v3 vs. `rapidocr-onnxruntime` v1:**
- Risk: Two packages with different output shapes (`RapidOCROutput` vs tuple/list) and Python-version-conditional installation (`requirements.txt:13-14`); behavior on 3.13 is untested.
- Files: `requirements.txt`, `ocr_fallback.py:21-32,154-197`
- Migration plan: Standardize on one package per Python version, add a 3.13 CI leg, and keep the normalization branch covered by tests (already partly done in `tests/test_ocr_fallback.py:377-425`).

**`litellm` conditional pin for Python 3.14:**
- Risk: The lockfile selects different `litellm` versions for `<3.14` and `>=3.14` (`requirements-lock.txt:205-207`), indicating the project is tracking upstream churn; the cloud adapter relies on streaming/`num_retries` semantics.
- Files: `litellm_provider.py`, `requirements-lock.txt`
- Migration plan: Pin one tested version per Python minor and add a contract test for streaming and consent failures.

---

## Missing Critical Features

**Authentication / multi-user isolation:**
- Problem: No login or per-user document scoping; all sessions share `data/documents.db` and `data/lancedb/`.
- Blocks: Safe deployment on any shared machine, LAN, or container host. Also makes the "privacy-respecting" claim conditional on physical access control.

**Cache/transcript erasure as part of delete/purge:**
- Problem: Neither single-document delete nor "Purge All" removes `.cache/` directories or the chat transcript.
- Blocks: Honest "delete my data" behavior and GDPR-style erasure.

**Background ingestion with progress/cancel:**
- Problem: All processing is synchronous inside the Streamlit script; there is no job queue, cancel, or resume.
- Blocks: Large/scanned PDFs, batch uploads, and any responsiveness guarantee.

**Per-document re-index / vector repair:**
- Problem: No UI or service to rebuild vectors for a doc whose SQLite row exists but LanceDB chunks are missing.
- Blocks: Recovery from a corrupted/deleted LanceDB directory without re-uploading (and dedupe currently blocks the re-upload path).

**OCR confidence gating:**
- Problem: `OcrEngine.ocr_page_image` returns an average confidence (`ocr_fallback.py:131-197`), but callers discard it (`_score` at `ocr_fallback.py:230`); low-confidence OCR text is indexed and cited like ground truth.
- Blocks: Reliable evidence quality on noisy scans; no way to flag or exclude low-confidence pages.

**Visual/page preview in citations:**
- Problem: Citations show page numbers and bbox text but never render the source page or crop; `bbox` is displayed as coordinates in the evidence drawer (`ui/views.py:328-333`).
- Blocks: Verifiable visual citations for charts/figures, one of the project's stated goals.

**Cloud-mode VRAM release:**
- Problem: Switching to cloud does not stop the local llama-server, so VRAM stays allocated.
- Blocks: Reclaiming the 4 GB envelope when working in cloud mode or running another GPU workload.

---

## Test Coverage Gaps

**Ingestion pipeline end-to-end:**
- What's not tested: Successful `IngestionService.ingest_pdf` with Docling/OCR/VLM/LanceDB, dedupe behavior, cache writes, atomic failure rollback.
- Files: `ui/ingestion_service.py`; only `tests/test_main_ui.py:337-365` covers the zero-chunk failure.
- Risk: The most complex path (and the upload rerun loop) is unverified; model-loading and DB/vector consistency regressions ship silently.
- Priority: High.

**Upload loop / Streamlit view behavior:**
- What's not tested: `render_sidebar_documents`, `render_chat_view`, `render_library_view`, `render_settings_view` under a real `AppTest`; widget-key state transitions (uploader retention, consent cancel).
- Files: `ui/views.py`; `tests/test_main_ui.py` only simulates dictionaries.
- Risk: Infinite reruns and consent-dialog loops are invisible to the suite.
- Priority: High.

**Retriever/LanceDB consistency and FTS:**
- What's not tested: Missing vectors for an `indexed` SQLite doc; `has_document` after restart; FTS index existence/usage; `doc_id` filter starvation; cosine score correctness.
- Files: `hybrid_retriever.py`, `ui/hydration.py`; only one global-count hydration test (`tests/test_hydration.py:1-58`).
- Risk: Silent empty retrieval and misleading scores.
- Priority: High.

**Privacy/erasure:**
- What's not tested: Purge removes `.cache`, chat history, summary keys, and retriever rows; delete removes per-doc cache and summaries.
- Files: `ui/views.py`, `ui/ingestion_service.py`, `doc_store.py`
- Risk: Claimed erasure is incomplete; privacy regressions pass CI.
- Priority: High.

**CI matrix and coverage:**
- What's not tested: Python 3.12/3.13 (CI is 3.11 only, `.github/workflows/ci.yml:12-18`); Docker build; a real llama-server/VLM integration; Windows-specific paths.
- Files: `.github/workflows/ci.yml`, `pyproject.toml`
- Risk: The advertised 3.13 support and Docker instructions are unsubstantiated; platform bugs reach users.
- Priority: Medium-High.

**Security regression tests:**
- What's not tested: `.dockerignore` contents; archive extraction path traversal; sanitizer link stripping; cloud consent bypass via `AiModel(cloud_mode=True)`; secret redaction in provider errors.
- Files: `setup.py`, `ui/sanitizer.py`, `local_llm.py`, `groq_provider.py`, `.dockerignore`
- Risk: Security fixes can regress without a failing test.
- Priority: Medium.

**Coverage enforcement:**
- What's not tested: There is no `pytest-cov` dependency, coverage config, or threshold (`requirements-test.txt`, `pyproject.toml`). `~285` tests exist, but untested branches (dedupe, hydration mismatch, VLM failure indexing) are exactly the risky ones.
- Files: `requirements-test.txt`, `pyproject.toml`, `.github/workflows/ci.yml`
- Risk: Coverage can silently decay.
- Priority: Medium.

---

## Quick Priority Order

1. Fix the post-upload infinite rerun (rotate `uploader_key`, do not count dedupe as new) and the consent-cancel loop.
2. Make purge/delete erase `.cache/`, chat history, and stale session keys; update the danger-zone copy.
3. Gate dedupe/hydration on actual retriever presence, and add a vector-repair/re-index path.
4. Add `.env`, `models/`, `*.gguf` to `.dockerignore`; default Compose to loopback and document auth.
5. Fix FTS index creation and the LTS/LanceDB score metric; reuse Docling/RapidOCR singletons.
6. Do not index VLM failure placeholders; pass the original filename for visual evidence.
7. Add end-to-end ingestion, upload-loop, erasure, and retriever-consistency tests; add Python 3.12/3.13 CI legs.

---

*Concerns audit: 2026-10-20*
