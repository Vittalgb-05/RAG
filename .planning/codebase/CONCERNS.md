<!-- refreshed: 2026-10-22 -->
# Codebase Concerns

**Analysis Date:** 2026-10-22
**Scope:** Full repository at the on-disk working-tree state.
**Core value under assessment:** Fast, evidence-grounded PDF summarization and QA with page-level citations, local-only operation, and a strict 4 GB VRAM ceiling.

**Verification snapshot (2026-10-22):**

- `python -m pytest -q` -> `392 passed in 49.02s`
- `ruff check .` -> passed
- `ruff format --check .` -> `76 files already formatted`
- No live `llama-server` or GPU inference run was performed; `docs/TEST_RESULTS.md:17-18` still marks that path `UNTESTED`.

Severity reflects impact on grounded answers, privacy/local-only guarantees, or the 4 GB runtime envelope.

## Repair Verification (2026-10-22)

The previously reported high-priority defects were checked against current source, not against the prior report.

| Prior claim | Status | Current evidence |
|---|---|---|
| Downloads lacked checksum pinning | **Fixed** | Every `MODEL_REGISTRY` entry and every llama archive path has a pinned SHA-256; `download_file_with_progress()` verifies before install and deletes bad bytes; `RAG_REQUIRE_CHECKSUMS` fails closed. Covered by `tests/test_setup_checksums.py`. |
| Streaming download could report success on a short read | **Fixed** | `setup.py:521-618` enforces `Content-Length` and post-write SHA-256; tests cover mismatch, and wrong existing files are replaced. |
| Write-only extraction cache with unbounded growth | **Fixed in code** | No production module persists `pages.json` / `chunks.json`; `ui/ingestion_service.py` no longer writes `.cache`, and runtime trees are empty. Stale UI/docs still claim cache persistence (see Documentation drift). |
| `print()` used throughout library modules | **Fixed** | Active prints remain only in operator CLIs (`setup.py`, `start.py`) and comments. Library modules use `logging.getLogger(__name__)`. |
| Deprecated `HybridRetriever.add_vector()` shim wrote empty vectors | **Fixed** | Only `retrieval/vector_index.py::VectorIndex.add_vector()` remains. `retrieval/retriever.py` is gone. |
| `LocalEmbedding` deprecated facades silently ran another vector store | **Open** | `retrieval/local_embedding.py:114,152` still exposes `search_hybrid()` / `get_context()` and `core/local_llm.py:113` still falls back to them. |
| Ruff did not enable bugbear/pyupgrade/Sim rules | **Fixed (partial)** | `pyproject.toml` selects `E`, `F`, `I`, `UP`, `B`, `SIM`, `RUF`; `BLE001` is not selected. |
| Fallback mirror merge broke after lazy load | **Fixed** | `retrieval/hybrid_retriever.py:312-347` merges with the on-disk mirror instead of writing a one-document file. Correctness is fixed; cost remains O(N) (see Performance). |
| Whole-document extraction used a fixed 10,000-character cutoff | **Fixed** | `retrieval/hybrid_retriever.py:623-637` filters in SQL before ordering/limits; `tests/test_whole_document_extraction.py` covers long documents. |
| Visual evidence was dropped before summarization | **Fixed** | `_build_summary_sources()` in `core/summarizer.py` merges `[E#]` elements into pages. |
| Scoped retrievals could emit no truncation warning | **Fixed** | `core/local_llm.py:351-356` and `ui/views.py:750-770` surface context truncation; intent-scoped queries now still produce an indicator when chunks were clipped. |
| Summary session keys omitted the model version | **Fixed** | `ui/views.py:39-41` uses `summary_<doc>_<profile>_<model_version>`; `model_version` is stored and filtered at `core/doc_store.py:704-751`. |
| JPEG visual bytes were passed to llama.cpp as `image/png` | **Fixed** | `providers/llama_cpp_provider.py:281-302` sniffs JPEG/PNG and sets the matching MIME. |
| Library logging was unconfigured | **Fixed** | `core/logging_setup.py` configures UTF-8 rotating logs; `main.py` initializes it. |

The deferred items below were re-checked and remain open. The largest residual risks are the inconsistent token budgets, silent extraction/OCR caps, unauthenticated network mode, plaintext-at-rest data, and incomplete end-to-end verification.

## Tech Debt

**Monolithic installer and packaging (`setup.py`):**
- Issue: `setup.py` is 930 lines mixing setuptools metadata, model registry/download verification, archive extraction, llama-server installation, dependency installation, environment diagnostics, shell profile mutation, and a custom CLI (`setup.py:686-930`).
- Impact: every installer change is high-blast-radius; download, extraction, venv, and packaging concerns are coupled. `setup_kwargs` includes `py_modules=["setup"]` at `setup.py:814`, so the installer is also installed as an importable module; `find_packages()` can include `tests` because `tests/__init__.py` exists.
- Fix approach: split into `installer/models.py`, `installer/llama_server.py`, `installer/deps.py`, `installer/__main__.py`, leaving a thin shim in `setup.py`; exclude `tests` explicitly from packaging; add focused failure-path tests.

**Two retrieval/facade layers (`retrieval/local_embedding.py`, `retrieval/vector_index.py`, `retrieval/hybrid_retriever.py`):**
- Issue: `LocalEmbedding` retains deprecated `search_hybrid()` / `get_context()` facades and an unused `db_uri` constructor argument (`retrieval/local_embedding.py:60-172`). The live path is `HybridRetriever` plus `VectorIndex`; `core/local_llm.py:113` still has a legacy fallback branch.
- Impact: readers and future agents can follow the wrong retrieval implementation; the deprecated objects are in-memory and do not share LanceDB persistence semantics.
- Fix approach: move callers to `HybridRetriever`, remove the facades and `db_uri`, then delete the `tests/test_hybrid_retriever.py`-level facade tests. Do this after confirming no external users.

**Broad exception handling and suppressed linting (`pyproject.toml`, ingestion modules):**
- Issue: 93 `except Exception` sites remain. `BLE001` is not selected by Ruff. Some paths silently pass instead of logging: `ingestion/docling_reader.py:140`, `ingestion/docling_reader.py:224`, `ingestion/pdf_reader.py:41`.
- Impact: conversion, indexing, and UI failures can degrade to empty content without an operator-visible cause; future broad catches compile cleanly.
- Fix approach: enable `BLE001` with a narrow, documented per-file ignore list; replace silent passes with `logger.warning(..., exc_info=True)`; convert recoverable ingestion failures into explicit warnings returned by `IngestionService`.

**Stale extraction-cache controls and documentation (`ui/views.py`, `ui/lifecycle_service.py`, `README.md`):**
- Issue: production extraction caching was removed, but Settings still offers “Clear Disk Cache (.cache/)” (`ui/views.py:1268-1278`), lifecycle still deletes legacy cache directories, and architecture docs still describe `.cache/<sha256>/<version>` as a live cache.
- Impact: UI controls promise a cache that no longer exists; documentation misstates startup behavior. Legacy empty directories may remain until cleanup.
- Fix approach: remove the control or relabel it “Remove legacy cache directories”; update `README.md`, `ARCHITECTURE.md`, and `docs/EVALUATION.md` to state that extraction is recomputed.

**Dependency and CI reproducibility (`requirements.txt`, `requirements-lock.txt`, `Dockerfile`, `.github/workflows/ci.yml`):**
- Issue: `requirements.txt` uses loose lower bounds, the lock is compiled for Python 3.11 only, and `Dockerfile` installs the loose file rather than the lock. CI runs only Ubuntu with Python 3.11. Primary Windows behavior is not exercised.
- Impact: Docker and developer environments can resolve different versions from CI; a clean install may behave differently from a tested install.
- Fix approach: install `requirements-lock.txt` in Docker, add a Windows CI job and a Python 3.12 job if supported, and refresh the lock deliberately.

**Model naming mismatch (`setup.py`, `core/model_identity.py`, `start.py`):**
- Issue: Setup downloads a Qwen2-VL checkpoint renamed to `models/qwen3-vl-2b-instruct-q4_k_m.gguf`; `core/model_identity.py` accepts both architectures, and `start.py` verifies GGUF metadata to catch mislabeled files.
- Impact: the identity guard prevents a silent wrong-model launch, but filenames, UI labels, and docs imply Qwen3-VL. Operators may fetch a different Qwen3 checkpoint that passes the architecture check but differs from the tested model.
- Fix approach: rename the artifact to match the actual checkpoint, or pin a true Qwen3-VL checkpoint and update registry, docs, and tests together.

**UI composition is concentrated in `ui/views.py`:**
- Issue: one 1,277-line module owns helper state, chat, summarizer, library, and settings rendering.
- Impact: hard to test in isolation and easy to create session-state coupling across workspaces.
- Fix approach: split by workspace into `ui/views/chat.py`, `ui/views/summarizer.py`, `ui/views/library.py`, `ui/views/settings.py`; keep shared helpers in `ui/state.py`.

**Deprecation warnings are globally hidden (`pyproject.toml`):**
- Issue: pytest filters `DeprecationWarning`, so facade and dependency deprecations are invisible.
- Impact: removals become breaking surprises rather than gradual migrations.
- Fix approach: narrow the filter to known third-party warnings; fix project deprecations before suppressing them.

## Known Bugs

### [High · open] Token budgets disagree and can exceed the configured context window

`core/prompt_budget.py:73-74` defaults to reserving `max_output_tokens=1536`. `core/local_llm.py:317-322` calls `assemble_grounded_messages()` without overriding that value, but `core/local_llm.py:339` then asks the provider for `max_tokens=2048`. Separately, `core/query_intent.py:109` computes the whole-document char budget assuming only `1024` output tokens; `core/local_llm.py:296` and `ui/views.py:714` use that default.

Effect: input selection and generation reservation are based on three different output budgets (1024, 1536, 2048). With the configured `4096` context, prompt assembly plus generation can request roughly 4,600 tokens. llama.cpp will truncate or reject depending on server flags, so the “no silent truncation” guarantee is incomplete.

The summarizer has the same class of bug: `core/summarizer.py:24-31` documents 1,500 output tokens for map/reduce, `FAST_PATH_TOKEN_LIMIT=2000`, but `core/summarizer.py:407` and `core/summarizer.py:461` both request `max_tokens=2500`. A single-pass summary can reach ~4,500 tokens; a 2,500-token reduce output leaves no room for its 2,500-token consolidation prompt.

Fix approach: define one `MAX_OUTPUT_TOKENS` per model profile, pass it to `assemble_grounded_messages()`, `whole_document_char_budget()`, and every provider call, and assert `estimated_input + max_output_tokens <= context_window`. Add unit tests that exercise the maximum-evidence path, not only the small fixtures.

### [High · open] Whole-document questions silently stop at 500 chunks

`retrieval/hybrid_retriever.py:641` calls `fetch_document_chunks(..., limit=500)`. `core/query_intent.py:227` uses that method for whole-document retrieval. A 500-page document with normal chunk sizes commonly produces more than 500 chunks, so later pages are omitted before ranking.

There is no warning or truncation flag for this cap, and no test uses more than 500 chunks. Answers over long reports can therefore be confidently incomplete while the citation validator still reports full validity for the sampled pages.

Fix approach: remove the fixed cap or paginate until all chunks are collected; derive the budget from `num_chunks`; return a `truncated`/`omitted_chunks` field through `RetrievalResult` and surface it in the chat evidence panel. Add a regression test with >500 chunks where the answer must cite the tail.

### [Medium · open] Full setup exits successfully after failed downloads or installs

`setup.py:686-739` calls `download_all_models()` and `setup_llama_server()` without checking either return value, suppresses `pip install -e .` failures, and then prints “Setup Complete!” and returns `0`. `download_all_models()` also ignores the return values of `precache_embedding_model()` and `precache_ocr_model()` (`setup.py:400-401`).

Effect: a first-run installer can tell the user it succeeded while models, llama-server, or the package are missing. The failure appears later as a launcher error.

Fix approach: aggregate per-step booleans, return non-zero if any required step failed, report optional failures distinctly, and add tests that monkeypatch each failure path.

### [Medium · open] OCR and visual-analysis caps silently drop evidence

`ingestion/ocr_fallback.py:34-35` caps OCR at `MAX_OCR_PAGES_PER_DOC=200` and `MAX_OCR_SECONDS_PER_DOC=300`. `ui/ingestion_service.py` limits visual analysis to `max_regions=6` (the analyzer default is 20). Pages/regions beyond the caps are logged but not represented in `IngestionResult`.

Impact: a 500-page scanned document can be indexed as successfully parsed while 300 pages remain un-OCR’d; diagrams after the first six are invisible to retrieval. Chat answers may omit evidence with no user-visible “partial extraction” state. `IngestionResult.fallback_used` exists but is not rendered, and there is no separate OCR/visual degradation flag.

Fix approach: add structured warnings (`pages_ocr_skipped`, `visual_regions_skipped`, `time_budget_exceeded`) to `IngestionResult`, render them in the Library and document detail views, and avoid marking a document “fully indexed” when critical pages were skipped.

### [Medium · open] Vector repair does not restore visual evidence

`ui/hydration.py:135-144` repairs missing vectors using only `doc_store.get_chunks_for_doc()`. `ui/ingestion_service.py:115-127` performs the same text-only repair during deduplication. `ui/lifecycle_service.py:187-195` shows the intended full path: re-index text chunks and `evidence_elements` together.

Impact: after LanceDB loss or a partial write, visual evidence can exist in SQLite but never be re-embedded, so chart/figure questions regress until a user manually reindexes the document. Hydration then marks the document healthy because text vectors retrieve successfully.

Fix approach: centralize repair in one function that loads chunks and evidence for a document, embeds both, and verifies both retrieval pools. Add a test that deletes the vector index, hydrates, and asserts a visual-evidence query succeeds.

### [Medium-High · open] Grounding validation proves rank existence, not evidential support

`core/citation_validator.py:107-124` treats a citation as valid when its `[E#]` rank exists in the result set. Lexical `support_precision` is calculated but only used as a diagnostic/warning (`ui/views.py:100-105`, `:750-770`); responses with unsupported citations are displayed with a verification caption rather than withheld.

Worse, `auto_attribute_citations()` (`core/citation_validator.py:456-510`) can append a citation to an uncited sentence when lexical overlap is at least `0.18`. The appended rank then passes `is_valid()`. This creates an appearance of grounding that the model did not produce.

Impact: the stated “>=95% citation precision” target can be reported while sentences are only loosely related to the cited evidence. This is the most direct risk to the product’s core evidence claim.

Fix approach: separate `citation_exists` from `evidence_supports_claim`; require a minimum semantic/lexical support score derived from the cited element, not the whole result set. Mark auto-attributed citations distinctly in the UI and never count them toward the precision target without review. Add tests with plausible-but-unsupported sentences.

### [Medium · open] Prompt-injection detection is a phrase blocklist that can reject legitimate documents

`core/citation_validator.py:303-353` detects injection via a list of phrases such as “ignore previous instructions” and “system prompt:”. The validator marks the response invalid, and the UI withdraws it (`ui/views.py:764-770`).

Impact: a security report, policy document, or AI research paper quoting those phrases can trigger a blanket failure, including when the user asks about prompt injection itself. Conversely, paraphrased attacks are not detected. The design provides false assurance in both directions.

Fix approach: treat detection as a warning/quarantine channel rather than a hard response failure; scope detection to instruction-like structure and document provenance; add benign adversarial-text fixtures and a user override that preserves citations.

### [Low-Medium · open] Extraction degradation and skipped visual regions are not surfaced

`ingestion/docling_reader.py:140` catches Docling failure during the probe and falls back to `pypdf`; `ui/ingestion_service.py:99-102` sets `fallback_used=True`, but the UI never displays it. Visual failures are often only logged (`ui/ingestion_service.py:167-178`).

Impact: users cannot distinguish “the document contains no table” from “table extraction failed” or “the visual region was skipped”. This undermines trust in answers about complex layouts.

Fix approach: render `fallback_used`, OCR counts, visual counts, and conversion method in the Library detail and chat source drawer; include them in the document manifest.

### [Low · open] The fallback vector mirror is a read-modify-write JSON file without locking

`retrieval/hybrid_retriever.py:277-286` writes atomically via a temp file, but `:312-347` merges by reading the current mirror and rewriting it. Concurrent uploads from two Streamlit sessions can interleave, and the last writer can drop the other document’s vectors. A multi-process deployment makes this more likely.

Impact: fallback recovery can silently lose documents even though SQLite has them. The primary LanceDB index may still be correct, so the loss is only discovered when fallback is used.

Fix approach: serialize mirror mutations with a file lock or a small SQLite table; derive the mirror from LanceDB instead of maintaining a second write path; add a concurrency test.

## Security Considerations

### [High if network-exposed · open] No authentication or authorization

No login, token, session identity, or access-control layer exists in `main.py`, `ui/`, or `.streamlit/config.toml`. Any client that can reach Streamlit can upload, read, summarize, re-index, and delete all documents.

Current mitigation: `.streamlit/config.toml:15` binds to loopback, `start.py:22` warns when a non-loopback host is configured, and `docker-compose.yml` publishes on `127.0.0.1`. These are deployment conventions, not application controls.

Recommendation: keep loopback binding mandatory unless an explicit auth proxy is configured; document the threat model; add optional password/session auth before any LAN or reverse-proxy deployment.

### [High · open] Document content and metadata are unencrypted at rest

`data/documents.db` stores full chunk text and page text; `data/lancedb/` stores embeddings and FTS content; `data/logs/` can contain filenames and exception text. There is no encryption layer, key management, or secure-deletion guarantee beyond filesystem deletion/VACUUM.

Impact: any local process or user with file access can read the entire document corpus; backups and disk snapshots inherit plaintext.

Recommendation: document at-rest assumptions in the privacy model; offer optional OS keyring/SQLCipher or encrypted-volume guidance; ensure logs never include chunk bodies or API keys.

### [Medium · open] Mutable container images and unpinned base image

`docker-compose.yml:8` uses `ghcr.io/ggml-org/llama.cpp:server-cuda` (mutable tag), and `Dockerfile:2` uses `python:3.11-slim-bookworm` without a digest. A rebuild can change llama-server flags, CUDA compatibility, or Python dependency resolution.

Impact: reproducible deployments and model compatibility are not guaranteed; a tag update can break `start.py` health checks.

Recommendation: pin both images by digest, document the llama.cpp build/version, and add a scheduled image-update job with smoke tests.

### [Medium · open] First-run model downloads create non-obvious network egress

`ingestion/docling_reader.py:189-194` constructs `DocumentConverter`, which can download Docling/Hugging Face artifacts on first use. `setup.py:339-401` pre-caches the embedding and OCR models but not Docling, and ignores both pre-cache return values. `RAG_REQUIRE_CHECKSUMS` covers GGUF/llama archives, not these HF/RapidOCR downloads.

Impact: the README’s “zero egress” claim holds only after all model caches are warm; a clean install can contact external hosts during ingestion with no checksum/fail-closed policy. A failed precache is not reported by the installer.

Recommendation: pre-cache every model family in setup, verify cache completeness before launch, honor `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE`, and fail with a clear offline-setup message. Add an opt-in network audit test.

### [Medium · open] Regex sanitizer is the only defense for rendered document text

`ui/sanitizer.py:14-21` uses regular expressions to strip tags and neutralize links; it is not an HTML parser/allowlist renderer. Chat rendering relies on Streamlit escaping any remaining HTML, which limits current impact, but future `unsafe_allow_html` use would expose bypasses. Cloud mode with `allow_external=True` intentionally permits external links/images, which can leak browser requests.

Impact: crafted PDF text could affect layout, hide content, or cause egress if sanitization assumptions change. The code is fragile because safety depends on call-site behavior.

Recommendation: render untrusted text with an explicit allowlist sanitizer or keep HTML disabled at every call site; add fuzz/property tests for malformed tags, Markdown link variants, and mixed encodings; make external navigation a per-click user action.

### [Medium · open] API-key redaction is exact-string replacement

`providers/litellm_provider.py:50-74` and `providers/groq_provider.py:50-68` scrub the configured key from error strings via `replace()`. Variants (URL-encoded, partially masked, wrapped by provider formatting, or logged before scrubbing) are not covered.

Impact: a provider error could leak credentials into logs or UI error text.

Recommendation: centralize redaction, redact recognized key prefixes and Authorization headers, never include raw provider exceptions in user-visible output, and add tests with realistic provider error payloads.

### [Medium · open] Document text is treated as untrusted for prompting but not for resource use

`core/prompt_budget.py` isolates context in XML tags and the system prompt says evidence is untrusted, but there is no defense against extremely repetitive text, pathological tables, or adversarial layouts beyond file/page limits.

Impact: prompt injection is partially mitigated, while CPU/memory denial-of-service and citation flooding remain possible within the 50 MB / 500 page limits.

Recommendation: cap chunks per page and total evidence elements, limit table cell sizes, and add decompression/zip-bomb checks for any future Office formats. Treat the 50 MB/page limits as the outer bound, not the only bound.

## Performance Bottlenecks

**Fallback mirror rewrites all vectors on every mutation:**
- Problem: `retrieval/hybrid_retriever.py:277-286` serializes the full document/vector set, and `:312-347` reads and rewrites the entire JSON for each upsert.
- Cause: a single JSON file is used as a durable mirror of LanceDB.
- Impact: upload/delete time grows linearly with corpus size; 384-dimensional vectors make the file large. Each write also duplicates embedding data already in LanceDB.
- Improvement path: store the mirror in SQLite with per-document rows, append incrementally, or rebuild it from LanceDB on demand; delete the mirror once fallback recovery is reliable.

**BM25 fallback loads every chunk into Python:**
- Problem: `retrieval/hybrid_retriever.py:830-852` fetches all rows with BM25 scores and groups them by document.
- Cause: document-level candidate selection is implemented by scanning the whole table.
- Impact: memory and latency grow with corpus size; a large library can stall chat retrieval.
- Improvement path: maintain a document-level BM25 table or aggregate at write time; cap candidate documents before loading chunks; benchmark at 10k+ chunks.

**Hydration performs synchronous re-embedding:**
- Problem: `ui/hydration.py:135-144` calls `local_embedding.get_embeddings()` and `retriever.index_chunks()` in the startup path, showing progress but blocking the session.
- Cause: missing vectors are repaired inline on first load.
- Impact: a large library or partial index loss can make startup feel hung, especially on CPU. There is no background job or resumable queue.
- Improvement path: run repair in a background worker with persisted job state; bound repair per startup; show a “repair in progress” state and allow chat on already-indexed documents.

**OCR is CPU-heavy and time-capped rather than adaptive:**
- Problem: `ingestion/ocr_fallback.py:368-435` processes up to 200 pages/300 seconds with RapidOCR on CPU.
- Cause: no page-level difficulty estimate beyond the low-character trigger; no concurrency budget or cancellation.
- Impact: a scanned PDF can consume minutes before the user sees a partial result, and later pages are silently skipped.
- Improvement path: estimate OCR cost from page raster size/text density, prioritize pages with retrieval value, expose a cancel action, and report skipped pages.

**Inference is serialized with a 60-second wait and no cancellation:**
- Problem: `InferenceGate.acquire(timeout=60.0)` in `core/local_llm.py:328-332` serializes all LLM/VLM/summarizer work; `stream_text` has no user stop control.
- Cause: one model must fit in 4 GB VRAM, so concurrency is intentionally excluded.
- Impact: a long summary or visual pass blocks chat; a stuck generation holds the gate until the HTTP stream ends. The UI has no cancel-generation path.
- Improvement path: add cooperative cancellation (close the httpx stream, release the gate), enforce a per-request deadline, and queue requests with visible positions rather than a generic busy message.

## Fragile Areas

**Ingestion degradation matrix (`ui/ingestion_service.py`, `ingestion/*`):**
- Why fragile: Docling fallback, OCR skip, visual extraction failure, and embedding failure are handled in separate branches with different logging and different effects on `IngestionResult`. Some failures leave a document “indexed” with partial content.
- Safe modification: add a single `IngestionDiagnostics` object that every stage populates; make “indexed” depend on required stages only; test each failure combination.
- Coverage gaps: no test asserts UI visibility of fallback/OCR/visual warnings.

**Retrieval consistency across SQLite, LanceDB, and JSON mirror (`core/doc_store.py`, `retrieval/hybrid_retriever.py`, `ui/*`):**
- Why fragile: deletion and repair must touch three stores plus session state. `ui/lifecycle_service.py` is the only place that handles all of them correctly; hydration and dedup repair are narrower.
- Safe modification: route all mutations through a single repository/service that owns the transaction boundary; add integrity checks that compare counts and hashes across stores.
- Coverage gaps: no test for concurrent uploads, partial delete failure, or mirror/SQLite divergence.

**Grounding and citation pipeline (`core/citation_validator.py`, `core/local_llm.py`, `ui/views.py`):**
- Why fragile: validity, support precision, auto-attribution, injection filtering, and UI warnings are separate knobs. Changing one can make a response “valid” while support remains low, or make a legitimate document unanswerable.
- Safe modification: define a single `GroundingReport` with explicit fields (`citation_exists`, `support_score`, `auto_attributed`, `injection_suspected`); make UI policy a pure function of that report; test the combinations.
- Coverage gaps: no end-to-end test with a plausible unsupported sentence; injection tests cover obvious phrases only.

**Setup/installer (`setup.py`, `start.py`):**
- Why fragile: network downloads, archive extraction, venv creation, shell profile edits, model identity verification, and process launch are tightly coupled. Most functions return booleans that callers ignore.
- Safe modification: aggregate exit status, isolate side effects, and add a dry-run mode; never report success without verifying required artifacts.
- Coverage gaps: checksum tests are strong; failure propagation, extraction rollback, and launcher process cleanup are untested.

**Streamlit UI/session state (`main.py`, `ui/views.py`, `ui/components.py`):**
- Why fragile: 1,277-line views module, many `st.session_state` keys, widget-key rotation for uploads, and cache-resource singletons. Behavior depends on rerun order.
- Safe modification: centralize state keys and transitions; keep render functions free of service construction; add Streamlit `AppTest` coverage for upload -> index -> chat and delete -> purge.
- Coverage gaps: `tests/test_ui_smoke.py` and `tests/test_main_ui.py` exercise helpers/contracts, not full view rendering.

**Regex sanitizer (`ui/sanitizer.py`):**
- Why fragile: safety depends on every caller keeping HTML escaping enabled and on regexes covering all Markdown/HTML forms. A new rendering path or an `unsafe_allow_html=True` call changes the threat model.
- Safe modification: make the sanitizer return a typed “safe text” object, disallow raw HTML centrally, and add a lint/check for unsafe render calls.
- Coverage gaps: no fuzz corpus for nested/malformed HTML and no explicit test for external image egress.

## Scaling Limits

| Resource | Current limit / behavior | Where it breaks |
|---|---|---|
| Upload size | 50 MB (`ingestion/upload_validation.py:18`) | Large scanned PDFs rejected; no streaming upload |
| Page count | 500 pages (`ingestion/upload_validation.py:19`) | 500-page reports must be split |
| OCR | 200 pages / 300 seconds (`ingestion/ocr_fallback.py:34-35`) | Later scanned pages silently skipped |
| Visual analysis | 6 regions per document in UI (`ui/ingestion_service.py`) | Diagram-heavy documents lose evidence |
| Whole-document retrieval | 500 chunks (`retrieval/hybrid_retriever.py:641`) | Long documents omit tail content |
| Context | 4,096 tokens | Budget arithmetic can exceed it; map/reduce outputs too large |
| Inference concurrency | One process-wide gate | Multi-process/Docker replica deployment breaks the invariant |
| Fallback mirror | Full JSON rewrite per mutation | Slows and grows with corpus; no file lock |
| BM25 fallback | Full-table row load per query | Latency/memory spike on large libraries |

**Scaling path:** define explicit per-document budgets (chunks, OCR pages, visual regions), move repair/indexing to background jobs, replace the JSON mirror with a row store, and publish a tested multi-process story or explicitly enforce single-process deployment.

## Dependencies at Risk

**`ghcr.io/ggml-org/llama.cpp:server-cuda` (mutable tag):**
- Risk: image contents and CLI behavior can change without a repo change.
- Impact: `start.py` flags, `/health`, chat template handling, and GPU offload may break.
- Migration plan: pin by digest, record the llama.cpp build number, and run a container smoke test before updating.

**`python:3.11-slim-bookworm` (unpinned base):**
- Risk: base OS packages and Python patch level drift.
- Impact: native wheel availability and ONNX/CUDA compatibility can change.
- Migration plan: pin by digest; rebuild on a schedule with the lockfile.

**`requirements.txt` vs `requirements-lock.txt`:**
- Risk: Docker resolves loose lower bounds while CI uses the lock.
- Impact: an image can ship untested dependency versions.
- Migration plan: install the lock in Docker and CI; regenerate the lock for each supported Python version.

**Hugging Face / RapidOCR model artifacts:**
- Risk: runtime download availability, licensing changes, and no checksum pinning for these caches.
- Impact: offline installs fail at first ingestion; model versions can drift.
- Migration plan: vendor or pre-cache all artifacts in setup, record revisions, verify cache integrity, and fail closed in offline mode.

**Optional cloud adapters (`litellm`, `groq`):**
- Risk: SDK/API changes, key handling, and provider-specific errors.
- Impact: optional cloud fallback can fail or leak error text; local mode must remain untouched.
- Migration plan: pin versions, wrap provider calls behind a strict error boundary, and test consent/key-scrubbing paths.

**`pillow` is declared but unused in first-party code:**
- Risk: unnecessary native dependency and CVE surface in lockfiles/images.
- Impact: larger image and more upgrade work.
- Migration plan: remove after confirming no transitive or test requirement depends on it.

## Missing Critical Features

**Authentication and access control:**
- Problem: none exists; loopback is the only boundary.
- Blocks: safe LAN, multi-user, or reverse-proxy deployment.

**Encryption at rest and secure deletion:**
- Problem: SQLite, LanceDB, and logs are plaintext; deletion is logical/VACUUM-based.
- Blocks: compliance-sensitive use and shared-machine privacy guarantees.

**End-to-end UI and live inference verification:**
- Problem: no Streamlit `AppTest`, no live llama-server/GPU smoke test, no automated check of citation behavior under real generation.
- Blocks: confidence that the tested unit graph matches the shipped app.

**Background indexing/repair and cancellation:**
- Problem: ingestion/hydration repair blocks the session; generation cannot be stopped.
- Blocks: responsive UX on large libraries and long documents.

**Health auto-recovery and readiness:**
- Problem: provider health is checked, but there is no supervised restart of llama-server, no queue drain on recovery, and no readiness gate for first-run model downloads.
- Blocks: unattended local operation.

**CI coverage for the primary platform:**
- Problem: CI is Ubuntu/Python 3.11 only; Windows is the primary host.
- Blocks: catching path, multiprocessing, and DLL/CUDA issues before release.

## Test Coverage Gaps

**Streamlit views and session transitions:**
- What is not tested: `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view`, upload widget rotation, delete/purge rerun paths.
- Files: `ui/views.py`, `main.py`, `tests/test_ui_smoke.py`, `tests/test_main_ui.py`.
- Risk: state-key and rerun regressions ship unnoticed.
- Priority: High.

**Token-budget invariants:**
- What is not tested: `estimated_prompt_tokens + max_output_tokens <= context_window` for maximum evidence, every intent, and every summary profile.
- Files: `core/prompt_budget.py`, `core/query_intent.py`, `core/local_llm.py`, `core/summarizer.py`.
- Risk: silent truncation or provider rejection at the 4K boundary.
- Priority: High.

**Whole-document retrieval beyond 500 chunks:**
- What is not tested: tail content retrieval and truncation signaling on long documents.
- Files: `retrieval/hybrid_retriever.py`, `core/query_intent.py`, `tests/test_whole_document_extraction.py`.
- Risk: incomplete answers with valid-looking citations.
- Priority: High.

**Citation support vs citation existence:**
- What is not tested: plausible-but-unsupported sentences, auto-attributed citations counted as valid, cross-page evidence mismatch.
- Files: `core/citation_validator.py`, `tests/test_citation_validator.py`, `tests/test_citation_and_result.py`.
- Risk: the primary evidence guarantee is overstated.
- Priority: High.

**Ingestion degradation and caps:**
- What is not tested: OCR page cap, OCR time cap, visual-region cap, Docling fallback visibility, partial-index status.
- Files: `ingestion/ocr_fallback.py`, `ingestion/docling_reader.py`, `ui/ingestion_service.py`, `tests/test_ocr_fallback.py`.
- Risk: users trust incomplete documents.
- Priority: High.

**Installer failure propagation:**
- What is not tested: `run_full_setup()` return code when model/server/package steps fail; ignored pre-cache results.
- Files: `setup.py`, `tests/test_setup_checksums.py`, `tests/test_start_launcher.py`.
- Risk: false “Setup Complete!” and confusing first-run failures.
- Priority: Medium.

**Live provider behavior:**
- What is not tested: real llama-server SSE, multimodal image payloads, stop/cancel, 4 GB OOM handling, health recovery.
- Files: `providers/llama_cpp_provider.py`, `core/local_llm.py`, `start.py`.
- Risk: production-only failures in the core inference path.
- Priority: High for release, not necessarily unit CI.

**Sanitizer adversarial corpus:**
- What is not tested: fuzzed/malformed HTML, nested Markdown links, external image egress, future `unsafe_allow_html` paths.
- Files: `ui/sanitizer.py`, `tests/test_sanitizer.py`.
- Risk: local-only/privacy regression if rendering assumptions change.
- Priority: Medium.

**Concurrency and multi-store consistency:**
- What is not tested: simultaneous uploads, mirror JSON races, partial delete failures, hydration while ingesting.
- Files: `retrieval/hybrid_retriever.py`, `core/doc_store.py`, `ui/lifecycle_service.py`, `ui/ingestion_service.py`.
- Risk: silent data loss or stale vectors.
- Priority: Medium.

---

*Concerns audit: 2026-10-22*
