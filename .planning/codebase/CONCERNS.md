# Codebase Concerns

**Analysis Date:** 2026-10-19

## Verified Recent Context

- `ocr_fallback.py:30` and `visual_analyzer.py:18` both use `import pymupdf as fitz`; no legacy `import fitz` / `from fitz` remains anywhere in the Python source. The `fitz` deprecation symptom is resolved.
- `logging_setup.py` exists and `main.py:39,51` installs `suppress_torch_classes_scan_warning()` at import. The filter targets only logger `streamlit.watcher.local_sources_watcher` and only records whose message contains `torch.classes` (`logging_setup.py:16-46`).
- `tools/llama-server/llama-server.exe` **is present and runnable**: `--version` returns `0.7.0-dev (build 11718, commit 547208dca)`. It is not on `PATH`, and nothing is listening on `http://127.0.0.1:8080` (`curl /health` fails). The "Inference: Offline" state is therefore an environment/process state, not a missing binary or code defect.
- `models/mmproj-f16.gguf` (1.33 GB) and `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (986 MB) are present. `models/` and `*.gguf` are ignored in both the committed and working-tree `.gitignore`, and `git ls-files` contains no GGUF/weight files.

## Tech Debt

**`main.py` is a 973-line module with import-time side effects (High):**
- Pages, session-state initialization, `DocStore` construction, sidebar rendering, upload ingestion, chat handling, and summary rendering all execute at module scope (`main.py:101-973`).
- The upload pipeline is a ~220-line inline loop (`main.py:389-614`) mixing validation, extraction, OCR, VLM analysis, SQLite writes, LanceDB indexing, cache writes, and Streamlit widget state.
- Impact: high regression risk (see Known Bugs), near-impossible to unit test as a unit, and any import of `main` requires a Streamlit runtime/mocks.
- Fix approach: extract an `IngestionService` (validate → extract → OCR → visuals → persist → index) and a `ChatService`, leaving `main.py` as thin UI wiring. Add an integration test that drives the service with the corpus PDFs.

**Duplicate cloud-provider implementations (Medium):**
- `litellm_provider.py` is the consented production path used by `main.py:291-295`; `groq_provider.py` is a second, legacy cloud client selected as a fallback by `AiModel._detect_provider` (`local_llm.py:174-181`).
- `GroqProvider` has no consent gate (contrast `litellm_provider.py:142-148`) and wraps errors without credential scrubbing (`groq_provider.py:125-126,160-161`).
- Fix approach: remove `GroqProvider` from the runtime decision path or make it delegate to `LiteLLMProvider(user_consented=...)`; keep one cloud adapter.

**Dead/deprecated paths retained (Low):**
- `ask_a_question_from_pdf_stream(pdf_path=...)` explicitly raises after a deprecation warning (`local_llm.py:240-250`); `main.py:799` always passes `pdf_path=""`.
- `HybridRetriever.search()` / `get_context()` emit `DeprecationWarning` (`hybrid_retriever.py:641-659`); `LocalEmbedding.search_hybrid()` is also deprecated (`local_embedding.py:113-140`), yet `main.py:779-789` still routes through those legacy methods when the retriever is absent.
- Fix approach: delete the legacy branches and require a `RetrievalResult`, or keep one documented compatibility shim with tests.

**Duplicated storage of every vector (Medium):**
- `HybridRetriever.index_chunks` always writes to the in-memory `VectorIndex` fallback (`hybrid_retriever.py:297-311`) and then to LanceDB (`hybrid_retriever.py:312-364`). Vectors therefore live twice per session even when LanceDB is healthy.
- Fix approach: populate the fallback only when LanceDB is unavailable, or keep only chunk metadata in memory for BM25.

**Logging is inconsistent (Low):**
- `print()` remains in production paths: `pdf_reader.py:131`, `upload_validation.py:106`, `doc_store.py:154`. Most newer modules use `logging.getLogger(__name__)`.
- Fix approach: standardize on `logger.info/warning`; configure handlers once at startup.

**Silent exception swallowing (Medium):**
- `main.py:72-94` closes providers inside `try/except Exception: pass`; `main.py:546-549` and `549-555` swallow integrity/evidence failures; `ocr_fallback.py:250-254` and `visual_analyzer.py:250-254` swallow progress-callback errors; `setup.py:32-41` and `57-63` swallow console reconfiguration errors.
- Impact: failed cleanup or persistence looks successful to the user (e.g., evidence elements silently not recorded) while the UI reports success.
- Fix approach: log at `warning` with context; surface non-fatal persistence failures as UI warnings; reserve bare `pass` for genuinely optional telemetry.

**Packaging/setup is dual-mode and fragile (Low):**
- `setup.py` mixes setuptools metadata, custom commands, a full CLI, downloaders, and archive extraction. `setup(**setup_kwargs)` is inside `if __name__ == "__main__"` (`setup.py:808-820`), so any tooling that imports `setup.py` without executing it as `__main__` registers nothing.
- Classifiers list Python 3.11/3.12 only (`setup.py:723-725`) while `start.py:49-54`, `requirements.txt:11`, and the debug notes discuss 3.13.
- Fix approach: move metadata to `pyproject.toml`, keep a tiny packaging shim, and put operational setup in a `scripts/` or console entry point.

**Requirements drift across install paths (High):**
- `requirements.txt` leaves `docling`, `lancedb`, `litellm`, `pymupdf`, `pillow`, `pyarrow`, and `rapidocr-onnxruntime` floating (`requirements.txt:8-18`).
- `requirements-lock.txt` is a universal lock compiled for Python 3.11 (`requirements-lock.txt:1-3`) and is used by CI (`.github/workflows/ci.yml:27-29`).
- `Dockerfile:20-22` installs `requirements.txt`, **not** the lockfile it copies, so Docker builds are not reproducible.
- `setup.py run_full_setup` installs `requirements.txt` unless `--lockfile` is passed (`setup.py:496-533,549-555`).
- Fix approach: make the lockfile the single install source for Docker, CI, and setup; add an automated `pip-compile` refresh check.

## Known Bugs

**"Purge All Data" and "Clear Session" immediately re-ingest retained uploads (High):**
- Both buttons clear `doc_ids`/`indexed_files` (`main.py:66-94`) but do not clear the `st.file_uploader` widget (`main.py:381-387`). Streamlit re-renders the same files on the next rerun, so the upload loop (`main.py:389`) validates and re-indexes them right after the user asked to purge/clear.
- `Purge All Data` can therefore re-populate `data/documents.db`, `data/lancedb`, and `.cache/` in the same interaction sequence (`main.py:355-379`).
- Fix approach: add a `clear_uploads` counter to the uploader `key` (e.g., `key=f"uploader_{st.session_state.upload_epoch}"`) and increment it in `_reset_session_security_state`; or refuse ingestion when a `purge_in_progress` flag is set.

**Persisted documents are not hydrated on startup (High):**
- On a fresh process/session, `hybrid_retriever` and `local_embedding` are `None` (`main.py:120-121`), and nothing constructs a retriever from `data/lancedb` or reads `DocStore` documents at startup. `edit_document`/list APIs exist (`doc_store.py:233-243`) but are only used for the telemetry count (`main.py:633`).
- Result: after restarting the app, the sidebar says "Upload a PDF to get started" (`main.py:624-625`) and the chat input is disabled (`main.py:748-751`) even though the index and metadata are on disk. Only re-uploading the same file triggers the dedup restore path (`main.py:437-451`).
- Fix approach: on first run, open `HybridRetriever()`, set an embedding function, and hydrate `document_metadata` from `doc_store.list_documents()`; enable chat when the persistent retriever has chunks.

**Docker local-inference path cannot connect (High):**
- `docker-compose.yml:19-20` exports `LLAMA_SERVER_HOST=host.docker.internal` and `LLAMA_SERVER_PORT=8080`, but no Python module reads those variables. `LlamaCppProvider` defaults to `http://127.0.0.1:8080` (`llama_cpp_provider.py:26-33`) and `AiModel._detect_provider` constructs it with defaults (`local_llm.py:183-185`).
- Even if the env vars were read, `host.docker.internal` is not loopback and would be rejected by the SSRF guard unless `allow_remote=True` (`llama_cpp_provider.py:43-60`).
- Result: the `app` container reports Inference Offline even when the optional `llama-server` compose service is healthy; only cloud mode works in Docker.
- Fix approach: read `LLAMA_SERVER_HOST`/`PORT` (and an explicit `LLAMA_SERVER_ALLOW_REMOTE` opt-in) in `LlamaCppProvider`, or document/ship the app and server in one container.

**OCR is silently unavailable on Python 3.13 installs via `requirements.txt` (High for this machine):**
- `requirements.txt:11` installs `rapidocr-onnxruntime` only when `python_version < "3.13"`. No `rapidocr` requirement covers 3.13+, although `ocr_fallback.py:21-27` supports the newer package and `setup.py:216-234` tries it.
- `requirements-lock.txt` happens to pin both `rapidocr==3.10.0` and `rapidocr-onnxruntime==1.4.4`, so CI (lock-based) is fine; `python setup.py`/`Dockerfile` (requirements-based) are not.
- Consequence on a 3.13 local install: `RapidOCR = None` (`ocr_fallback.py:27`), `should_ocr_page` still selects scanned pages, `ocr_page_image` returns `("", 0.0)` (`ocr_fallback.py:143-144`), and the document is marked indexed with zero chunks and a success toast (`main.py:564-604`). Chat then abstains.
- Fix approach: add `rapidocr>=3.0.0; python_version >= "3.13"` to `requirements.txt`, or pin a single compatible package; add an ingestion test that asserts nonzero chunks for `tests/data/corpus/scanned_sample.pdf` on 3.13.

**Visual region detection runs twice per document (High performance/cost):**
- `main.py:495` calls `visual_analyzer.detect_visual_regions(raw_bytes)` to decide whether to show progress; `VisualAnalyzer.analyze_visual_elements` calls `self.detect_visual_regions(pdf_bytes)` again at `visual_analyzer.py:218`.
- Each call re-opens the PDF and iterates all pages with `get_images()` and `get_drawings()` (`visual_analyzer.py:63-136`), doubling PDF parse cost on every upload.
- Fix approach: pass the precomputed `detected_regions` into `analyze_visual_elements` (new optional parameter) or have it return regions alongside elements.

**LanceDB dense scores are not cosine similarity (Medium):**
- The table is created without a distance metric (`hybrid_retriever.py:340-343`), so LanceDB uses its default L2 distance. `search_dense` converts results as `score = 1.0 - _distance` (`hybrid_retriever.py:410-415`), while the fallback path uses cosine distance (`vector_index.py:157-187`).
- Ranking remains monotonic for L2-normalized MiniLM vectors, but the score shown in the evidence drawer (`main.py:728,834`) is not a cosine score and is inconsistent between LanceDB and fallback.
- Fix approach: create the table/index with `metric="cosine"` (or convert L2 to cosine explicitly: `cos = 1 - d²/2` for unit vectors) and document the score meaning.

**Cached summaries can be shown for the wrong model version (Medium):**
- `Summarizer.summarize_document` passes `model_version` to `DocStore.get_summary` (`summarizer.py:330-337`), but the UI read path calls `doc_store.get_summary(selected_sha, selected_profile)` without it (`main.py:952-956`).
- After switching local ↔ cloud models, the summary tab can display a cached summary produced by a different model.
- Fix approach: compute `f"{provider_caps.model_name}:{CONFIG_VERSION}"` in `main.py` and pass it to `get_summary`, or always route reads through `Summarizer`.

**`failed_doc_ids` survives Clear Session (Low):**
- `_reset_session_security_state` resets `doc_ids`, `indexed_files`, `document_metadata`, index, chat, summaries, and cloud state (`main.py:66-94`) but not `st.session_state.failed_doc_ids` (initialized at `main.py:117`).
- A document that failed once stays blocked (`main.py:454-456`) even after the user clears the session; the message tells them to remove/re-upload, but the content hash is unchanged, so it remains blocked.
- Fix approach: clear `failed_doc_ids` in `_reset_session_security_state`; add an explicit retry action.

**Summary tab's filename fallback cannot resolve metadata (Low):**
- The main branch keys `document_metadata` by `doc_id` (`main.py:595-602`), but the `else` branch looks up `document_metadata.get(selected_file)` with a filename (`main.py:893-897`), which returns `{}`. That branch only runs when `document_metadata` is empty, so it typically yields an empty `selected_doc_id`/`selected_sha`.
- Fix approach: key metadata consistently or derive `doc_id` from `DocStore.get_by_sha`/filename lookup.

**LanceDB write failures silently lose chunks on restart (Medium):**
- `index_chunks` logs an error if LanceDB persistence fails (`hybrid_retriever.py:363-364`) but does not persist the fallback store in that branch. `close()` persists the fallback only when LanceDB is inactive (`hybrid_retriever.py:156-161`).
- The UI still reports the document as indexed; after restart, the chunks are gone from LanceDB and were never written to `fallback_store.json`.
- Fix approach: on LanceDB write failure, mark the document/index degraded, persist the fallback, and surface a warning; never report success without a durable write.

## Security Considerations

**Untrusted PDF parsing is not sandboxed (High):**
- `validate_pdf_bytes` checks `%PDF-` magic bytes, 50 MB size, 1–500 pages, and pypdf readability (`upload_validation.py:64-113`). After that, the same bytes are parsed by pypdf, Docling, PyMuPDF, and RapidOCR in-process.
- Risks: decompression bombs, malformed-page crashes in native parsers, and future parser CVEs. `pypdf.PdfReader` is constructed before the page cap, so `len(reader.pages)` itself parses attacker-controlled structures (`upload_validation.py:90-94`).
- Current mitigation: page-level try/except in `pdf_reader.py:116-127`, `ocr_fallback.py:294-307`, and `docling_reader.py:309-314`; per-file isolation in `main.py:529-532`.
- Recommendations: run parsing in a worker process with memory/CPU limits; validate page dimensions and embedded-image counts before rendering; keep parser versions pinned and patched.

**Full-page OCR rendering has no pixel cap (Medium):**
- `OcrEngine.render_page_image` renders a page at up to 300 DPI with no dimension check (`ocr_fallback.py:100-121`). A PDF with a huge MediaBox can allocate a very large RGBA pixmap.
- `VisualAnalyzer.crop_visual_element` does cap estimated pixels at 2048×2048 (`visual_analyzer.py:179-184`), but the full-page path in `ocr_fallback.py` does not.
- Fix approach: clamp rendered width/height to a maximum pixel budget (e.g., 4096×4096) and reject oversized page boxes before `get_pixmap`.

**Rendered document content can trigger browser-side egress (Medium privacy):**
- Retrieved chunks, model output, filenames, and source labels are rendered with `st.markdown` (`main.py:695,730,836`, history replay `main.py:693-739`). Streamlit's Markdown renderer permits images/links; a PDF containing `![x](https://attacker.example/pixel)` or a model echoing such a link causes the user's browser to fetch it.
- This contradicts the "zero external network egress" caption (`main.py:659,811`) for the local mode.
- Fix approach: sanitize/escape Markdown in untrusted content (render as plain text or code blocks), strip image/link syntax, or set a strict CSP in the deployed UI; document that the caption covers server-side egress only.

**`setup.py` archive extraction lacks traversal and integrity checks (Medium supply chain):**
- `download_and_extract_archive` calls `zipfile.extractall(dest_dir)` and `tarfile.extractall(dest_dir)` without member-path validation (`setup.py:340-349`). A malicious/mirrored archive with `../` members or symlinks can write outside `tools/llama-server`.
- Downloads verify only a minimum byte size (`setup.py:103-193`, `MODEL_REGISTRY` at `setup.py:59-78`); there are no SHA-256/signature checks for GGUF weights, the llama.cpp archive, or the CUDA runtime archive. URLs are hardcoded to GitHub/Hugging Face mirrors (`setup.py:64-77,288-290`).
- Fix approach: use `zipfile` member validation / `tarfile` `filter="data"` (Python 3.12+) or extract to a temp dir after validating names; publish and verify checksums; pin release assets.

**Cloud fallback has no consent gate outside `LiteLLMProvider` (Medium defense-in-depth):**
- `AiModel._detect_provider` returns `cloud_provider` when set, otherwise constructs `GroqProvider()` if `cloud_mode=True` and Groq is healthy (`local_llm.py:174-181`). `GroqProvider` has no `user_consented` check (`groq_provider.py:18-52,99-161`).
- `main.py` always passes a consented `LiteLLMProvider` (`main.py:291-300`), so the UI path is gated, but any programmatic caller of `AiModel(cloud_mode=True)` can transmit document text with only an env key.
- Fix approach: require an explicit `BaseModelProvider` with `is_local=False` and a consent flag; remove the implicit `GroqProvider` construction.

**API key handling is memory-only but duplicated (Low):**
- Session keys live in `st.session_state.cloud_api_keys` and are compared/cached raw in `_cached_cloud_key` (`main.py:255-298`). They are not persisted to disk; `.env` is absent in this working tree (not read).
- `LiteLLMProvider` scrubs its own key from error strings (`litellm_provider.py:135-140,237-239,294-296`). `GroqProvider` does not scrub (`groq_provider.py:125-126,160-161`).
- Fix approach: store only a hash/identifier for cache comparison, and centralize credential scrubbing in a shared helper used by every provider.

**SSRF guard is adequate for the app but bypassable by design (Low):**
- `LlamaCppProvider.__init__` rejects non-loopback hosts unless `allow_remote=True` (`llama_cpp_provider.py:43-60`); `httpx.Client` does not follow redirects by default (`llama_cpp_provider.py:66-70`), and DNS names other than `localhost` are rejected.
- Gaps: `allow_remote=True` is an unconditional bypass; `base_url` is not user-configurable through the UI, but any library consumer can pass it; `start.py --llama-host` probes an arbitrary host with `urllib` (`start.py:82-100,214-251`) — CLI-controlled, not untrusted input.
- Note: the same loopback rule blocks the legitimate `host.docker.internal` deployment (see Known Bugs), so the guard and Docker compose are in conflict.
- Fix approach: keep loopback default, add an explicit allowlist/config for container hostnames, and log rejected endpoints.

**Prompt-injection defenses are heuristic (Medium):**
- `<document_context>` tags are escaped (`prompt_budget.py:26-40`) and the system prompt instructs the model to treat context as data (`prompt_budget.py:13-23`), but document text is not otherwise sanitized.
- Output-side detection matches a fixed phrase list (`citation_validator.py:34-47,70-83`); paraphrased or encoded injections bypass it, and legitimate security documents that quote those phrases are flagged as `injection_detected` and rejected (`citation_validator.py:150-163`).
- Citation scoring validates only that `[En]` tags are in range; it does not check whether the cited sentence is actually supported by the snippet (`citation_validator.py:204-219`). A single valid citation yields 100% precision even if most claims are uncited.
- Fix approach: keep the heuristic as a warning rather than a hard rejection, add entailment/claim-coverage checks, and distinguish "model echoed a directive" from "document contains a directive".

**Container runs as root with an unpinned base and broad port binding (Low/Medium):**
- `Dockerfile` has no `USER`, uses `python:3.11-slim-bookworm` without a digest, and the CMD binds `0.0.0.0:8501` (`Dockerfile:2,52-54`). There is no authentication in front of the Streamlit UI.
- `docker-compose.yml:8-10` publishes `8501` to the host; anyone who can reach it can upload documents, query them, and enable cloud mode.
- Fix approach: run as a non-root user, pin image digests, bind to `127.0.0.1` by default, and document that the UI is single-user/trusted-network only.

**Purge does not erase data at rest (Medium privacy):**
- `DocStore.purge_all` issues `DELETE` statements (`doc_store.py:597-607`) but does not `VACUUM`, enable `PRAGMA secure_delete`, truncate the WAL, or delete `data/documents.db`. Extracted text can remain in free pages/WAL.
- `main.py:355-379` removes LanceDB tables and `.cache/` but leaves the SQLite file and any `-wal`/`-shm` files.
- Fix approach: `VACUUM` after purge, delete/recreate the DB file and WAL, and document that secure erasure on SSDs is best-effort.

**First-run downloads contradict the zero-egress claim (Low):**
- `sentence-transformers` downloads `all-MiniLM-L6-v2`, Docling downloads layout/table models, and RapidOCR downloads ONNX weights on first initialization (`local_embedding.py:38-41`, `setup.py:196-234`). `LlamaCppProvider` itself makes no outbound calls, but ingestion is not fully offline until those caches are warm.
- Fix approach: ship/pre-cache weights in the installer and add a runtime network kill-switch/offline mode for users who require strict egress guarantees.

## Performance Bottlenecks

**Synchronous ingestion blocks the UI (High):**
- Docling conversion, conditional OCR, embeddings, and up to 20 sequential VLM calls all run inside one `st.status` block on the Streamlit script thread (`main.py:391-614`). A scanned or figure-heavy PDF can block the session for minutes with only text updates.
- There is no background job, queue, cancellation, or resume; a browser refresh loses progress and restarts (`main.py:389-608`).

**Every rerun re-validates retained uploads (Medium):**
- While `st.file_uploader` still holds files, each rerun calls `uploaded_file.getvalue()` and `validate_pdf_bytes` (full SHA-256 + pypdf parse) before the dedup check (`main.py:394-421`). Large PDFs pay this cost on every interaction.
- The dedup branch then emits an "Already indexed" info line per file (`main.py:423-452`), adding UI noise.

**LanceDB search is unindexed and FTS is never initialized (High):**
- `create_fts_index()` is defined (`hybrid_retriever.py:433-441`) but has **no production call site**; no `create_index()` (vector ANN) call exists anywhere. `search_fts` therefore falls back to `_bm25_search_fallback` (`hybrid_retriever.py:505-532`), which tokenizes every stored document and recomputes document frequencies on every query (`hybrid_retriever.py:443-503`).
- Dense search is a full table scan (`limit(k)` without an index). Query cost grows linearly with chunk count.
- Fix approach: create the FTS index after the first table creation and call `table.create_index(metric="cosine")`; rebuild lazily when row count changes; measure with `scripts/benchmark_baseline.py`.

**OCR thread pool is serialized by a lock (Medium):**
- `apply_conditional_ocr` uses up to 4 workers (`ocr_fallback.py:380-400`), but `OcrEngine.ocr_page_image` wraps the recognizer call in `self._ocr_lock` (`ocr_fallback.py:135-146`). Recognition is therefore serial; only page rendering overlaps.
- Fix approach: use a process pool or instantiate one RapidOCR session per worker (with a bounded pool), or explicitly document that the pool only parallelizes rendering.

**Visual analysis bypasses the VRAM gate (High):**
- `InferenceGate` serializes chat streaming and summarization (`local_llm.py:298-311`, `summarizer.py:389`), but `VisualAnalyzer.analyze_visual_elements` calls `provider.analyze_image` directly without acquiring it (`visual_analyzer.py:262-270`).
- Two sessions (or an upload plus a chat request) can run VLM analysis and token generation against the same llama-server simultaneously, exceeding the 4 GB budget.
- Fix approach: wrap each `analyze_image` call (or the whole visual batch) in `InferenceGate.hold(...)`; also gate at the llama-server level if multiple processes are possible.

**Sequential VLM work per upload (Medium):**
- Up to 20 regions are detected and analyzed one-by-one (`visual_analyzer.py:198,244-293`), each a full HTTP round trip with base64-encoded crops (`llama_cpp_provider.py:250-302`). No batching, caching, or per-region timeout.
- Fix approach: cache descriptions by `(doc_id, page, bbox)` in `DocStore`, batch where the server supports it, and make `max_regions` configurable.

**Per-page SQLite connection/commit during ingestion (Medium):**
- `main.py:557-561` calls `doc_store.record_page(page)` per page; `record_page` opens a new connection and commits (`doc_store.py:245-276`). A 500-page PDF performs 500 connections/commits, plus chunk/evidence batches.
- Fix approach: add `record_pages(list[Page])` using one connection/transaction; batch WAL commits.

**Vector memory is duplicated per session (High at scale):**
- Every `HybridRetriever` owns a `VectorIndex` fallback containing all chunk vectors (`hybrid_retriever.py:113-119,297-311`). The embedding model is shared process-wide (`local_embedding.py:23-42`), but vectors and chat state are per session.
- With S sessions and N chunks, memory is roughly `S × N × 384 × 4 bytes` for fallback vectors (plus LanceDB). 10 sessions × 20k chunks ≈ 300 MB just for duplicate vectors.
- Fix approach: keep only chunk metadata per session (or a shared read-only fallback) and let LanceDB own vectors.

**Startup imports are heavy (Medium):**
- `main.py:33-46` imports Docling, LiteLLM, sentence-transformers, and the full ingestion stack at module load. `pytest --collect-only` took ~67 s for 267 tests, largely import time.
- Fix approach: lazy-import Docling/LiteLLM inside the ingestion/cloud paths; add import-time regression checks.

**Health probing on every rerun (Low):**
- `main.py:310` calls `ai_model.check_health()` on each interaction. When offline, `check_health` constructs a new `LlamaCppProvider`, probes, and closes it (`local_llm.py:187-207`), creating/closing an `httpx.Client` per rerun.
- Fix approach: cache health for a short TTL and reuse the provider instance.

**BM25/JSON fallback growth (Medium):**
- `_save_fallback_store` rewrites the entire JSON file (`hybrid_retriever.py:169-192`), and `_load_fallback_store` loads it on every session (`hybrid_retriever.py:135-148`). Memory and startup time scale with the whole corpus.
- Fix approach: use SQLite/LanceDB for the fallback, or append-only records with an index.

**Token estimation is crude (Medium):**
- `estimate_tokens` uses `ceil(len(text) / 4)` (`prompt_budget.py:43-54`). Tables, OCR output, code, and non-English text tokenize worse than 4 chars/token, so a prompt that appears within budget can still overflow the 4,096-token server context and fail generation.
- Fix approach: use the model tokenizer when available, or apply a conservative factor and a hard post-estimate check.

## Fragile Areas

**`main.py` ingestion state machine:**
- Files: `main.py:389-614`.
- Why fragile: ordering dependencies between `doc_store.upsert_document`, `record_evidence_elements`, `record_page`, `record_chunks`, LanceDB indexing, and session-state mutation. The FK-inversion and infinite-rerun bugs documented in `.planning/debug/upload-loop-rapidocr-and-crawl.md` came from exactly this coupling.
- Safe modification: keep the invariant "parent document row before child rows; session state only after durable writes"; add a service-level integration test.
- Test coverage: no end-to-end ingestion test; `tests/test_main_ui.py` covers only data contracts.

**HybridRetriever dual-write consistency:**
- Files: `hybrid_retriever.py:256-368`.
- Why fragile: LanceDB and the in-memory fallback can diverge (write failures, dedup branches, multi-session writes). `search_fts` may read LanceDB while `_bm25_search_fallback` reads the fallback, producing different candidate sets.
- Safe modification: make one store authoritative per instance; add a consistency check/test that indexes, restarts, and compares `count_chunks`/search results.
- Test coverage: strong unit coverage (`tests/test_hybrid_retriever.py`), but no multi-session or crash-recovery test.

**Docling fallback hides extraction quality loss:**
- Files: `docling_reader.py:116-121,204-212,309-314`.
- Why fragile: any Docling failure silently falls back to pypdf, losing tables/reading order; the UI still reports success. A model/version change can alter output without a visible error.
- Safe modification: surface a per-document `extraction="pypdf_fallback"` warning in the UI/metadata; test with a table-heavy PDF and assert markdown-table chunks.
- Test coverage: `tests/test_docling_reader.py` mocks the converter; no real Docling CI test.

**RapidOCR output-shape branching:**
- Files: `ocr_fallback.py:146-189`.
- Why fragile: supports `RapidOCROutput`, `(result, elapse)` tuples, and raw lists across v1/v3 APIs. The `RapidOCROutput` failure documented in `.planning/debug/upload-loop-rapidocr-and-crawl.md` is a recent example.
- Safe modification: pin one RapidOCR major version per Python range and add a contract test for each supported return shape.

**Health/setup command drift:**
- Files: `llama_cpp_provider.py:104-121`, `start.py:102-110`, `docs/RUNBOOK.md:95-112`.
- Why fragile: setup commands hardcode `--port 8080`, the `models/qwen3-vl-2b-instruct-q4_k_m.gguf` name, and `-ngl 28`; `start.py`/provider base URLs can disagree with the actual server.
- Safe modification: centralize model filenames/ports in one config module and build both the health message and launcher command from it.

**`InferenceGate` is process-local:**
- Files: `local_llm.py:26-90`.
- Why fragile: the `RLock` protects threads in one Python process only. Multiple Streamlit server processes, a separate summarizer process, or direct llama-server clients are not coordinated. Streamlit generator cancellation is handled by `finally` (`local_llm.py:303-311`), but a hung provider call holds the gate for up to the stream duration.
- Safe modification: also serialize at the server (single llama-server slot) or add a cross-process lock/file lease; add a timeout around provider streams.

**Multi-session shared persistence:**
- Files: `hybrid_retriever.py:119,169-192`, `doc_store.py:122-139`.
- Why fragile: SQLite uses WAL and per-operation connections (good), but the JSON fallback is written non-atomically and without locking; multiple sessions can overwrite each other. LanceDB table handles are created per session with no write coordination.
- Safe modification: treat SQLite as the metadata source of truth, avoid JSON fallback writes under concurrency, and document single-user deployment.

**Region-detection heuristics:**
- Files: `visual_analyzer.py:92-130`.
- Why fragile: any cluster of ≥2 drawings with ≥40×40 pt area becomes a "chart"; page borders/full-page backgrounds are excluded by a 95% area rule, but decorative rules/logos can still pass. Results are capped at 20 with only an info log (`visual_analyzer.py:221-227`), silently dropping later figures.
- Safe modification: expose detected/skipped counts in the UI, make `max_regions` configurable, and add a fixture with mixed decorative and real figures.

**`citation_validator` phrase lists:**
- Files: `citation_validator.py:18-47`.
- Why fragile: abstention and injection detection are substring lists; wording changes in prompts/models silently change validation outcomes, and legitimate quotes can be misclassified.
- Safe modification: keep lists in one config, add regression fixtures for each phrase, and treat detection as advisory where appropriate.

## Scaling Limits

**4 GB VRAM envelope:**
- `models/qwen3-vl-2b-instruct-q4_k_m.gguf` is 986 MB and `mmproj-f16.gguf` is 1.33 GB on disk; README claims ~3.45 GB peak VRAM with ~646 MB headroom (`README.md:18`). KV cache at 4,096 context plus CUDA/runtime overhead leaves little room for concurrency.
- Limit: a second concurrent generation/vision request can exhaust VRAM. The only guard is process-local `InferenceGate`, which visual analysis bypasses (see above).
- Scaling path: enforce a single inference slot at llama-server, lower `-ngl`/context, or queue requests.

**Per-session in-memory index:**
- Each session duplicates all vectors in the fallback store (see Performance). The embedding model is shared, but the vector store, chat history (up to 50 turns, `main.py:53,664-670`), summaries, and ingestion buffers are not.
- Limit: a handful of concurrent sessions with large corpora will exhaust host RAM before VRAM.
- Scaling path: single shared retriever backed by LanceDB; move chat/history to a bounded store.

**Ingestion caps:**
- 50 MB / 500 pages (`upload_validation.py:15-16`), 20 visual regions (`visual_analyzer.py:198`), OCR threshold 50 chars (`ocr_fallback.py:35-49`), 4 OCR workers (`ocr_fallback.py:382`), visual crop 2048² pixels (`visual_analyzer.py:180`).
- Limit: a 500-page scanned PDF can require hundreds of OCR renders, thousands of chunks, and many minutes of CPU; the script thread is blocked throughout.
- Scaling path: background queue with progress persistence, page-range batching, and incremental indexing.

**Retrieval cost:**
- Linear dense scan + Python BM25 over all chunks (`hybrid_retriever.py:393-532`), with `candidate_pool = max(k*2, 10)` (`hybrid_retriever.py:558`).
- Limit: query latency grows with corpus size; at tens of thousands of chunks, BM25 tokenization alone dominates.
- Scaling path: LanceDB ANN + FTS indexes, precomputed token counts/DF, or a dedicated search service.

**Single-node persistence:**
- `data/documents.db` and `data/lancedb` are local files; `Dockerfile` mounts them via compose. No replication, backup, or migration tooling.
- Limit: one host; corruption/loss requires re-ingestion.
- Scaling path: document backup/restore, add a schema/config migration path, and make `purge`/re-index operations idempotent.

## Dependencies at Risk

**`docling>=2.0.0` (High):**
- Core ingestion dependency, unpinned in `requirements.txt:9`; lock resolves `docling==2.138.0` plus `docling-ibm-models`, `docling-parse`, `torch`, `torchvision` (`requirements-lock.txt:83-93,541-549`).
- Risk: frequent API/output changes; heavy transitive CUDA/CPU stack; model downloads on first use.
- Mitigation: pin in `requirements.txt`, add a real-Docling CI fixture, and isolate the converter behind `DoclingReader`.

**`litellm>=1.50.0` (High):**
- Unpinned (`requirements.txt:18`); imported eagerly by `main.py:36` through `litellm_provider.py:21-26`. The lock resolves different versions by Python (`requirements-lock.txt:205-207`).
- Risk: large dependency/attack surface, frequent releases, provider-pricing/telemetry behavior changes, and startup latency.
- Mitigation: lazy-import only when cloud mode is enabled, pin, and keep the `LiteLLMProvider` adapter thin.

**`lancedb>=0.17.0` (Medium):**
- Unpinned (`requirements.txt:14`); lock resolves `lancedb==0.40.0` (`requirements-lock.txt:193`). Code probes for `merge_insert`, `create_fts_index`, and `table_names` (`hybrid_retriever.py:200,346-352,437-438`).
- Risk: API drift and Windows file-lock behavior; no ANN/FTS index is created, so upgrades can change search semantics.
- Mitigation: pin, add an upgrade test that indexes/searches on Windows, and create indexes explicitly.

**`pymupdf>=1.24.0` licensing (Medium/High legal):**
- The project declares MIT (`LICENSE:1`, `setup.py:726`), but PyMuPDF is AGPL-3.0 (or commercial). It is a required dependency (`requirements.txt:13`) used by OCR rendering and visual analysis.
- Risk: distributing the app under MIT without complying with AGPL is a license conflict.
- Mitigation: obtain a commercial PyMuPDF license, relicense the project, or replace it with a permissively licensed renderer.

**RapidOCR split packages / Python markers (Medium):**
- `rapidocr-onnxruntime` is restricted to `<3.13` (`requirements.txt:11`); the code also imports `rapidocr` (`ocr_fallback.py:21-27`). The lock pins both (`requirements-lock.txt:444,446`).
- Risk: OCR silently disabled on 3.13 installs from `requirements.txt` (see Known Bugs); output-shape differences across versions.
- Mitigation: declare one compatible package per Python range, pin, and test both install paths.

**`torch` / `sentence-transformers` (Medium):**
- Pulled transitively; lock pins `torch==2.14.1`/`torchvision==0.29.1` (`requirements-lock.txt:541-549`). Embeddings are CPU-pinned (`local_embedding.py:27-42,55-70`).
- Risk: multi-GB installs, CUDA/CPU wheel mismatches, Windows symlink requirements for the Hugging Face cache, and long startup/import times.
- Mitigation: document the CPU-only wheel, pre-cache the model, and keep the embedding backend behind `LocalEmbedding`.

**`streamlit==1.42.0` (Low):**
- Pinned (`requirements.txt:1`); code branches on `st.dialog` availability (`main.py:201-209`).
- Risk: older release; `st.markdown`/widget behavior and watcher internals are version-specific (`logging_setup.py:13`).
- Mitigation: pin and add a UI smoke test on upgrade.

**`groq==0.15.0` / cloud models (Low):**
- Pinned (`requirements.txt:5`); default cloud models include `groq/llama-3.3-70b-versatile`, `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022` (`main.py:226-230`). Model IDs can be retired.
- Mitigation: make model IDs configurable, add a health check that validates the model, and keep `LiteLLMProvider` provider-agnostic.

**Unverified remote artifacts (Medium):**
- GGUF weights, llama.cpp archives, and the CUDA runtime are fetched from GitHub/Hugging Face with only a size check (`setup.py:59-78,103-193,288-290,308-356`). Release tag `b11718` is hardcoded (`setup.py:288`) and may disappear.
- Mitigation: checksum/signature verification and a local artifact mirror.

**Base images / container image (Low):**
- `python:3.11-slim-bookworm` is unpinned (`Dockerfile:2`); `ghcr.io/ggml-org/llama.cpp:server-cuda` has no tag/digest (`docker-compose.yml:39`).
- Mitigation: pin digests and add a Docker build CI job.

## Missing Critical Features

**Document lifecycle UI:**
- `DocStore.delete_document` and `HybridRetriever.delete_document` exist (`doc_store.py:575-595`, `hybrid_retriever.py:374-391`) but no UI exposes single-document delete, retry, or re-index. Only "Clear Session" and "Purge All Data" exist (`main.py:349-379`).
- Blocks: correcting a bad extraction or removing one sensitive document without wiping everything.

**Reliable retry/resume for failed ingestion:**
- `failed_doc_ids` blocks retries (`main.py:454-456`), and there is no job queue, progress persistence, or cancel button. A refresh during a long upload restarts from scratch.
- Blocks: large/scanned documents and flaky VLM/OCR environments.

**Startup recovery of persisted state:**
- No hydration of `DocStore`/LanceDB into session state (see Known Bugs). Persistence exists but is not usable until re-upload.
- Blocks: the core "local-first, restartable" workflow.

**Cloud-mode multimodal parity:**
- `VisualAnalyzer` explicitly rejects non-local providers (`visual_analyzer.py:229-241`) even though `LiteLLMProvider` supports vision for GPT-4o/Claude (`litellm_provider.py:175-191,298-355`). In cloud mode, figures get placeholder descriptions (`visual_analyzer.py:278-280`) and scanned pages still depend on local OCR.
- Blocks: cloud-mode users with image-heavy or scanned documents.

**Encrypted/password-protected PDFs:**
- `validate_pdf_bytes` reports "Unreadable PDF" when pypdf cannot open an encrypted file (`upload_validation.py:90-94`); there is no password prompt or decrypt path.
- Blocks: common enterprise documents.

**Config/model migration:**
- `CONFIG_VERSION` (`models.py:14`) and summary `model_version` exist, but there is no migration/rebuild workflow when chunking, extraction, or embedding models change. Old chunks remain until a manual purge.
- Blocks: safe upgrades without silently mixing incompatible indexes.

**Multi-user/auth isolation:**
- No authentication; `data/` is shared across sessions, and the Docker UI binds `0.0.0.0` (`Dockerfile:52-54`). Session state isolates chat/keys only, not documents.
- Blocks: deployment beyond a single trusted user.

**Export and evidence packaging:**
- Summaries, citations, and evidence snippets are rendered in Streamlit only; no JSON/Markdown/PDF export. `SummaryResult` and `RetrievalResult` are already serializable (`models.py:171-235`), so this is mostly a UI gap.

**Strict offline mode:**
- There is no runtime network kill-switch or egress audit; the "100% offline" claim is enforced by default provider selection and tests that monkeypatch sockets (`tests/test_cloud_privacy.py:55-104`), not by the running app.
- Blocks: environments with strict data-loss-prevention requirements.

**At-rest protection/retention:**
- Extracted text, chunks, and summaries are stored unencrypted in SQLite/LanceDB (`data/`), with no retention policy or secure erase (see Security). `.gitignore` correctly excludes `data/`, but local disk exposure remains.

## Test Coverage Gaps

**Suite size and gating:**
- 267 tests are collected (`pytest tests/ --collect-only`), with dedicated tests for most modules (providers, retriever, DocStore, OCR, Docling, summarizer, telemetry, launcher). There is **no** `pytest-cov` dependency, no coverage threshold, and no coverage job in `.github/workflows/ci.yml`.
- Risk: regressions in untested UI/ingestion paths ship silently.

**Ingestion loop (`main.py`):**
- What's not tested: the full upload → validate → Docling → OCR → VLM → SQLite → LanceDB → rerun flow, including FK ordering, `new_pdf_uploaded`, `failed_doc_ids`, dedup restore, and purge/clear behavior.
- Files: `main.py:389-614`; existing coverage is contract-level only (`tests/test_main_ui.py`).
- Risk: high — the infinite-rerun and FK failures documented in `.planning/debug/upload-loop-rapidocr-and-crawl.md` were found manually, not by tests.
- Priority: High.

**Docker and compose:**
- What's not tested: image build, `pip install -e .`, healthcheck, model mounting, and app→llama-server connectivity (`Dockerfile`, `docker-compose.yml`).
- Risk: the current compose local-inference path is broken (see Known Bugs) and no CI job would catch it.
- Priority: High.

**Windows and Python 3.13:**
- CI runs `ubuntu-latest` with Python 3.11 only (`.github/workflows/ci.yml:10-16`), despite Windows being the primary platform and the local environment being 3.13 (per `.planning/debug/launch-warnings-and-inference.md`). Windows file locks, cp1252 console handling, Hugging Face symlinks, and the 3.13 RapidOCR gap are untested.
- Files: `.github/workflows/ci.yml`, `start.py:21-36`, `setup.py:31-41`, `requirements.txt:11`.
- Priority: High for release confidence.

**Real-parser paths:**
- Docling, RapidOCR, PyMuPDF rendering, and llama-server are mostly mocked:
  - `tests/test_docling_reader.py` uses `MagicMock` converters (`tests/test_docling_reader.py:36-260`).
  - `tests/test_visual_analyzer.py` uses fake detectors/croppers and a `FakeFitz` (`tests/test_visual_analyzer.py:94-377`).
  - Provider tests use `httpx.MockTransport`/mocks; no live llama-server test.
- Risk: API/output-shape changes in native libraries are not caught until runtime.
- Priority: Medium (add a small opt-in integration suite).

**Setup/download integrity:**
- What's not tested: `download_and_extract_archive` path traversal/symlink members, checksum verification, mirror fallback, undersized-file handling, and `MODEL_REGISTRY` URL/name consistency.
- Files: `setup.py:103-193,308-356`; `tests/test_setup_llama.py` covers orchestration with mocks only.
- Risk: supply-chain and extraction issues ship untested.
- Priority: Medium.

**Concurrency and multi-session behavior:**
- `tests/test_concurrency_lock.py` covers `InferenceGate` in one process; no test covers two `HybridRetriever` instances writing the same LanceDB table, concurrent JSON fallback writes, or VLM analysis overlapping chat streaming.
- Risk: VRAM/RAM exhaustion and index corruption under real multi-session use.
- Priority: Medium.

**Startup hydration and persistence recovery:**
- No tests exist because the feature is absent: reopening the app with existing `data/` does not restore retrievers/metadata (see Known Bugs).
- Priority: High once implemented.

**Security/rendering regressions:**
- No test asserts that untrusted Markdown (image/link syntax) is neutralized before `st.markdown`, or that API keys never appear in logs/errors for `GroqProvider`.
- Files: `main.py:693-739`, `groq_provider.py:125-126`.
- Priority: Medium.

**Performance regressions:**
- `scripts/benchmark_baseline.py`, `scripts/benchmark_multimodal.py`, and `scripts/profile_resources.py` exist but are not run in CI; there are no latency/VRAM budgets asserted.
- Priority: Medium.

**Tracked binary corpus:**
- `tests/data/corpus/*.pdf` are committed binaries regenerated by `tests/data/corpus/generate_corpus.py` in CI (`.github/workflows/ci.yml:31-33`). ReportLab version changes can produce different bytes, making the working tree dirty and making "golden" assertions brittle.
- Fix approach: generate corpus into a temp directory in tests, or assert on extracted content rather than committed bytes.

---

*Concerns audit: 2026-10-19*
