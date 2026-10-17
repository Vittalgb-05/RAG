# Codebase Concerns

**Analysis Date:** 2026-10-17

## Tech Debt

**Duplicated cloud-posture reset logic in `main.py`:**
- Issue: The "Clear Session" and "Purge All Data" button handlers each repeat an identical ~15-line block that closes `active_cloud_provider`, nulls `_cached_cloud_model`/`_cached_cloud_key`, resets `cloud_mode`/`cloud_mode_toggle`/`user_consented`, and clears `cloud_api_keys`.
- Files: `main.py:296-324` (Clear Session), `main.py:326-373` (Purge All Data), `main.py:307-309` / `main.py:356-358` (duplicated `summary_*` key sweep)
- Impact: Any security-sensitive reset change must be applied twice; divergence risks leaving API keys or consent flags live in one path.
- Fix approach: Extract a single `_reset_session_security_state()` helper and call it from both handlers.

**Stale process-singleton / `@st.cache_resource` documentation:**
- Issue: `AiModel` docstring claims it "acts as a process singleton" when loaded via `@st.cache_resource`, but the app now builds a per-session instance in `st.session_state` and `@st.cache_resource` is not used anywhere in the repo.
- Files: `local_llm.py:96-101`, `main.py:91-105` (`get_session_ai_model`)
- Impact: Misleads future maintainers about cross-session state, exactly the contamination class the session-scoped refactor fixed (P1 audit).
- Fix approach: Update the docstring to describe session-scoped instantiation; grep for other `cache_resource` references.

**Unpinned heavyweight dependencies in `requirements.txt`:**
- Issue: `requirements.txt` uses open ranges (`docling>=2.0.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`, `pyarrow>=14.0.0`, `pymupdf>=1.24.0`, `rapidocr-onnxruntime>=1.3.0`, `pillow>=10.2.0`, `numpy>=1.26.0,<3.0.0`) while CI installs from the fully pinned `requirements-lock.txt`. Docs (`README.md`, `docs/RUNBOOK.md`) instruct users to install from `requirements.txt`.
- Files: `requirements.txt:1-17`, `requirements-lock.txt`, `.github/workflows/ci.yml`
- Impact: Local dev installs and CI installs can resolve different versions; reproducibility gap between documented and tested paths.
- Fix approach: Either pin `requirements.txt` or make docs direct local installs to `requirements-lock.txt`.

**`setup.py` doubles as installer CLI and package definition:**
- Issue: A 486-line `setup.py` performs the functions of an install/setup tool (pip install, GGUF download, cache warm-up, custom `download_models` command) while also declaring the package via `setup(**setup_kwargs)`. It registers a top-level `py_modules` entry named `setup` and a console script `rag-setup=setup:main_cli`.
- Files: `setup.py:44-63`, `setup.py:349-372`, `setup.py:396-449`
- Impact: `pip install -e .` triggers the legacy `setup.py` path (deprecated by PEP 517) and installs a top-level module named `setup`, which can shadow/unsettle tooling; mixing packaging with a downloader makes both harder to test.
- Fix approach: Move runtime CLI logic to a `scripts/` module (e.g. `scripts/install.py`) and keep `setup.py` (or migrate to `pyproject.toml`) packaging-only.

**Inline imports scattered through logic:**
- Issue: Imports appear inside functions rather than the top-level block (`import io` in the upload loop, `import shutil` in the purge handler, `import json`/`import math`/`import re` inside `HybridRetriever` methods).
- Files: `main.py:131`, `main.py:343`, `hybrid_retriever.py:131`, `hybrid_retriever.py:165`, `hybrid_retriever.py:317`, `hybrid_retriever.py:442-443`
- Impact: If a module is uninstalled/renamed the failure surfaces only at runtime on the specific branch; harder static analysis.
- Fix approach: Hoist to top-level imports per the repo import convention.

**Legacy facades retained alongside the canonical API:**
- Issue: `LocalEmbedding.build_index`, `LocalEmbedding.search_hybrid`, `HybridRetriever.search`/`get_context`, `VectorIndex` and the `pdf_reader` legacy methods survive only for backward compatibility; `VectorIndex` is now used solely as `HybridRetriever`'s fallback store.
- Files: `local_embedding.py:83-140`, `hybrid_retriever.py:641-649`, `vector_index.py`, `pdf_reader.py:116-139`
- Impact: Two retrieval code paths must be kept correct; the `search_hybrid` name on the dense-only `LocalEmbedding` path is misleading.
- Fix approach: Mark deprecated paths with warnings and delete once no caller remains (only `docling_reader` fallback and tests reference them).

**Documentation drift from reality:**
- Issue: `docs/EVALUATION.md` reports 217 tests / 23 suites and lists test files that do not exist (`test_audit_fixes.py`, `test_benchmark_metrics.py`, `test_citation_verifier.py`, `test_docling_parser.py`, `test_lancedb_index.py`). `README.md` claims 226 tests; the actual suite is 233 passing across 24 files. `docs/RUNBOOK.md:187` says the OCR trigger threshold is "30 characters" but the code uses 50.
- Files: `docs/EVALUATION.md:10-40`, `README.md:10,106,225`, `docs/RUNBOOK.md:187`, `ocr_fallback.py:31,294`
- Impact: The stated quality/coverage metrics cannot be trusted for release gating.
- Fix approach: Regenerate the evaluation report from `pytest --collect-only` output and reconcile all numeric claims.

## Known Bugs

**Unguarded `st.secrets` access can crash the cloud-mode sidebar:**
- Symptoms: When Cloud Mode is toggled and no provider key is present in the environment, rendering evaluates `env_var_name in st.secrets`; if `.streamlit/secrets.toml` does not exist Streamlit raises on secrets access, surfacing an uncaught exception page.
- Files: `main.py:199` (unwrapped), contrast with `litellm_provider.py:70-76` and `groq_provider.py:38-44` which wrap `st.secrets` in `try/except`.
- Trigger: Enable Cloud Mode in a deployment with no secrets file and no env var set.
- Workaround: Set the provider env var so the `or` short-circuits before touching `st.secrets`.
- Fix: Wrap the membership test in `try/except (KeyError, FileNotFoundError, AttributeError)` and default to `False`.

**`document_metadata` keyed by filename collides across distinct documents:**
- Symptoms: Two different PDFs sharing a filename overwrite each other's metadata entry (`pages`, `chunks`, `doc_id`), even though dedup is content-hash based.
- Files: `main.py:421-429` and `main.py:550-556` (dict keyed on `filename`), `main.py:570-575` (iteration), `main.py:839-845` (summary lookup by filename → `doc_id`)
- Trigger: Upload `report.pdf` twice with different contents in one session.
- Workaround: Rename one file.
- Fix: Key `document_metadata` by `doc_id` (or `sha256`) and derive filename for display only.

**Model identity mismatch between installer, provider, and docs:**
- Symptoms: `setup.py` names/describes the download as "Qwen2-VL 2B" and fetches `Qwen2-VL-2B-Instruct-Q4_K_M.gguf`, saving it as `models/qwen3-vl-2b-instruct-q4_k_m.gguf`; the provider default is `model_name="qwen3-vl-2b"` and the health-check hint references `qwen3-vl-2b-instruct-q4_k_m.gguf`; `docs/RUNBOOK.md` refers to Qwen3-VL 2B throughout.
- Files: `setup.py:44-63`, `llama_cpp_provider.py:26,104-106`, `docs/RUNBOOK.md:89-140`
- Trigger: Run setup, then compare the loaded model against documentation claims.
- Impact: Users may run a different model revision than documented, invalidating benchmark/quality claims.
- Fix: Reconcile on a single model identity across `setup.py`, `llama_cpp_provider.py`, and `docs/`.

**Latent non-hash `doc_id` / filename-prefixed chunk IDs:**
- Symptoms: `extract_text()` called without `doc_id`/`sha12` (e.g. via auto-invoking `get_paragraphs()`/`get_page_records()` on a fresh reader) falls back to `doc_{filename}` and filename-prefixed `chunk_id`s, which are not content-stable and can collide.
- Files: `docling_reader.py:92-93,297-305`, `pdf_reader.py:41-42,129-139`
- Trigger: Any future caller invoking the reader without explicit `doc_id`/`sha12`.
- Impact: Broken dedup and chunk-ID collisions (silent upsert overwrites in `doc_store.record_chunks`).
- Fix: Make `doc_id`/`sha12` required, or derive them from the content hash inside the reader.

## Security Considerations

**Model weights directory is not gitignored (2.2 GB at risk of commit):**
- Risk: `models/` is absent from `.gitignore`; `git status` reports `?? models/` and `git add -n models/` stages `models/mmproj-f16.gguf` and `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (~2.2 GB total). A `git add .` / `git add -A` would embed hundreds of MB–GB binaries into history with no easy removal.
- Files: `.gitignore:1-18` (no `models/` entry), `.git/info/exclude` (only `/.freebuff/`), `models/` (contains live `*.tmp` download artifact)
- Current mitigation: None — nowhere ignores `models/`.
- Recommendations: Add `models/` (and `*.gguf`, `*.tmp`) to `.gitignore` immediately; verify no GGUF blob is already tracked (`git ls-files models/`).

**No authentication on the Streamlit UI:**
- Risk: `start.py` exposes a settable `--host` bind address with no auth, and the app permits document upload, indexing, cloud-mode toggling, and API-key entry. Binding to `0.0.0.0` (or a LAN IP) exposes the whole pipeline to anyone who can reach the port.
- Files: `start.py:112-113,80-90`, `main.py:375-381` (uploader), `main.py:158-218` (cloud toggle + key input)
- Current mitigation: Documentation-only guidance that this is a single-user workstation tool (`docs/RUNBOOK.md:240-245`); default host is `localhost`.
- Recommendations: Add an optional password/auth gate, refuse non-loopback binds by default, and warn in-product when a non-loopback address is configured.

**LiteLLM telemetry not disabled (privacy/egress leak):**
- Risk: `litellm` is imported and used without disabling its anonymous usage telemetry (`litellm.telemetry`) or setting `LITELLM_TELEMETRY=False`. For a project whose core promise is "zero external network egress during local operation," this is a silent egress vector once cloud mode is enabled (and potentially at import).
- Files: `litellm_provider.py:18-21`, `main.py:238-242` (provider construction), `docs/RUNBOOK.md:240-245` (privacy claims)
- Current mitigation: Cloud path is gated behind explicit consent (`litellm_provider.py:126-132`); local-only mode never constructs the provider.
- Recommendations: Set `litellm.telemetry = False` at import and pin/disable telemetry explicitly; document the provider's egress footprint.

**Partial prompt-injection defense (input side):**
- Risk: `sanitize_xml_boundary` only escapes `</?document_context>` tags, and `detect_adversarial_injection` is a fixed substring list applied exclusively to the model *output*. Untrusted PDF text (or OCR output) can therefore carry instructions that are neither neutralized at ingestion nor detected unless echoed verbatim in the response.
- Files: `prompt_budget.py:26-40`, `citation_validator.py:70-83`, `summarizer.py:111,131,220` (prompt instructions to ignore embedded directives), `hybrid_retriever.py` (no content sanitization at index time)
- Current mitigation: System prompt instructs the model to treat `<document_context>` as untrusted data; output-side directive echo detection exists.
- Recommendations: Sanitize/strip control directives at ingestion, and broaden detection to more than the 14 hard-coded phrases.

**Session API keys surfaced through the widgets layer:**
- Risk: Per-provider keys live in `st.session_state.cloud_api_keys` and are re-passed as the `value` of a `type="password"` `st.text_input` on every rerun; LiteLLM error paths (`litellm_provider.py:220-222,276-278`) log the raised exception text, which may include key-adjacent provider errors.
- Files: `main.py:75,202-212`, `litellm_provider.py:214-222,266-278`
- Current mitigation: Keys are memory-only (not persisted) and cleared on Clear Session / Purge / Revoke Consent.
- Recommendations: Use widget keys without echoing the stored value, and scrub key material from logged/raised messages.

**Unvalidated DDL/identifier interpolation in LanceDB filters:**
- Risk: LanceDB `where`/`delete` clauses are built by string interpolation (`f"doc_id = '{safe_doc_id}'"`, `chunk_id IN (...)`), with only single-quote doubling as the escape. `doc_id`/`chunk_id` are currently content-hash-derived, so practical exposure is low, but the pattern is injection-prone if identifiers ever become user-influenced.
- Files: `hybrid_retriever.py:219-220,353-356,382-383`
- Current mitigation: Values are generated from SHA-256 digests in the current flow.
- Recommendations: Use parameterized LanceDB filters where available; centralize identifier escaping.

## Performance Bottlenecks

**Synchronous VLM visual analysis inside the ingestion loop:**
- Problem: Upload handling calls `VisualAnalyzer.analyze_visual_elements(...)` inline, which detects up to 20 regions and issues a separate `analyze_image` VLM call per region on the 4 GB GPU.
- Files: `main.py:475-490`, `visual_analyzer.py:192-287` (`max_regions=20`), `ocr_fallback.py:356-376`
- Cause: GPU inference is serialized through the request path and competes with the LLM for the VRAM ceiling.
- Improvement path: Defer/cap visual analysis, batch clauses, or run it lazily per page; expose the region cap to the UI.

**No ANN vector index in LanceDB; brute-force dense search:**
- Problem: Only `create_fts_index` is ever called; no `create_index`/IVF/PQ index is built. Dense search scans the table, and the pure-Python fallback is an O(N) linear scan.
- Files: `hybrid_retriever.py:390-428`, `hybrid_retriever.py:430-438` (FTS only), `vector_index.py:131-136` (linear scan)
- Cause: Default brute-force semantics with no index maintenance.
- Improvement path: Build a LanceDB vector index when chunk count crosses a threshold; re-index on ingest.

**BM25 fallback loads up to 10,000 rows and tokenizes per query:**
- Problem: `_bm25_search_fallback` may pull 10,000 rows from LanceDB into Python and re-tokenize them on every FTS query when the fallback store is empty, before scoring.
- Files: `hybrid_retriever.py:440-503` (`limit(10000)`, per-query tokenization loop)
- Cause: No cached tokenized corpus; recomputation on each call.
- Improvement path: Cache token counts/DF statistics keyed by index generation, or rely on LanceDB FTS exclusively.

**`DocStore` re-instantiated at module scope on every rerun:**
- Problem: `doc_store = DocStore(DOC_STORE_PATH)` executes on every Streamlit script rerun, opening a SQLite connection and re-running `_apply_migrations` (a `PRAGMA user_version` read) each interaction.
- Files: `main.py:88`, `doc_store.py:108-154`
- Cause: No caching of the store object.
- Impact: Minor latency and needless connection churn on every UI event.
- Improvement path: Cache the store once (module-level singleton guarded by a lock, or `@st.cache_resource`).

**Global inference gate serializes all generation:**
- Problem: `InferenceGate` allows exactly one active inference op; a multi-batch summarization holds it for up to 120 s, during which a chat request blocks for up to 60 s and then yields a "System is busy" placeholder.
- Files: `local_llm.py:26-90`, `summarizer.py:388-395` (`hold(timeout=120.0)`), `main.py:750-757`
- Cause: Deliberate VRAM-safety single-flight design.
- Improvement path: Expose queue status in the UI and align the chat gate timeout with expected summarization duration.

**CPU-pinned, full-batch embedding of every chunk at once:**
- Problem: `LocalEmbedding.get_embeddings` encodes the entire chunk list in one `SentenceTransformer.encode` call, and embeddings are pinned to CPU to preserve VRAM.
- Files: `local_embedding.py:22-37,76-81`, `main.py:511-512`
- Cause: Single batch for a 500-page PDF (thousands of chunks) is CPU-bound and RAM-spiky.
- Improvement path: Encode in bounded sub-batches with progress reporting.

## Fragile Areas

**OcrEngine shared across a thread pool:**
- Files: `ocr_fallback.py:344-376`
- Why fragile: The same `OcrEngine`/RapidOCR recognizer instance is submitted to up to 4 worker threads; ONNX Runtime session thread-safety is not guaranteed, and `page_results[i]` indexing assumes every page produced an entry (a worker crash path could leave gaps).
- Safe modification: Create one recognizer per worker or guard inference with a lock; add tests exercising >1 OCR page concurrently.
- Test coverage: `tests/test_ocr_fallback.py` exists but exercises the single-page path (`ocr_tasks == 1`) more heavily than the thread-pool branch.

**Version-sensitive Docling introspection with silent fallbacks:**
- Files: `docling_reader.py:102-293` (multiple `except Exception: pass` around `iterate_items`/`tables`/`prov`), `docling_reader.py:288-293` (whole-conversion catch → PdfReader)
- Why fragile: Docling's internal item/table APIs are unstable across major versions; failures degrade silently to lower-quality pypdf extraction with no user-visible signal.
- Safe modification: Pin Docling tighter, log at `warning` on every fallback path, and surface a UI banner when fallback occurs.
- Test coverage: `tests/test_docling_reader.py` uses a mocked converter, so real Docling API drift is not caught.

**Manual cloud-provider cache keying in `main.py`:**
- Files: `main.py:229-255`
- Why fragile: Correctness depends on three hand-maintained session attributes (`active_cloud_provider`, `_cached_cloud_model`, `_cached_cloud_key`) staying in sync with `AiModel`'s internal `provider`; the early-return identity checks in `set_cloud_mode` (`local_llm.py:152-157`) are load-bearing.
- Safe modification: Encapsulate provider lifecycle in a dedicated helper with explicit invalidation.
- Test coverage: `tests/test_cloud_privacy.py` covers consent and routing, but not the model/key-change recreation branch.

**Streaming retries can duplicate tokens:**
- Files: `litellm_provider.py:256-278` (`stream=True`, `num_retries=2`)
- Why fragile: A retry after partial stream consumption may re-emit earlier tokens, producing duplicated output.
- Safe modification: Disable retries for streaming or track emitted-token offsets.
- Test coverage: `tests/test_litellm_provider.py` exercises success/error paths, not mid-stream retry.

**Provider layer depends on the Streamlit runtime:**
- Files: `litellm_provider.py:52-76` (imports `streamlit`, reads `session_state`/`secrets`), `groq_provider.py:38-44`
- Why fragile: A pure provider module reaching into UI session state couples layers and makes headless/CLI use and unit isolation harder; `st.secrets` access can raise when no secrets file exists.
- Safe modification: Inject resolved keys/consent from the caller and keep providers UI-agnostic.
- Test coverage: Improvement mocks around `st`, so real Streamlit secret behavior is not exercised.

## Scaling Limits

**Single-inference, single-process design:**
- Current capacity: One LLM/VLM operation at a time within the 4 GB VRAM envelope; `InferenceGate` timeout 60 s (chat) / 120 s (summary).
- Limit: Concurrent users or a long summarization block all inference; beyond one request at a time the UI degrades to busy placeholders.
- Scaling path: Queue with per-session fair scheduling; offload inference to a dedicated local service.

**In-memory/session-scoped index with brute-force search:**
- Current capacity: Index lives in `st.session_state`; a new browser session starts empty and relies on `DocStore` restore (`main.py:430-444`).
- Limit: Dense search latency grows linearly with total chunks (no ANN); index is lost on process restart unless fallback `close()` ran.
- Scaling path: Enable LanceDB ANN indexing and treat LanceDB as the single source of retrieval truth.

## Dependencies at Risk

**`litellm` (unpinned `>=1.50.0`):**
- Risk: Fast-moving dependency with frequent breaking changes and default telemetry; heavy transitive footprint.
- Impact: Cloud-mode breakage on upgrade; unintended egress.
- Migration plan: Pin in `requirements.txt` (lockfile already pins), disable telemetry, or replace with per-provider SDKs.

**Ranged scientific/document deps without a single enforced source of truth:**
- Risk: `docling`, `rapidocr-onnxruntime`, `pymupdf`, `lancedb`, `pyarrow`, `pillow`, `numpy` are ranged in `requirements.txt`; only `requirements-lock.txt` pins them, and docs point at the ranged file.
- Impact: Divergent local environments vs. CI.
- Migration plan: Make `requirements-lock.txt` the documented install source, or pin `requirements.txt`.

**Interpreter version mismatch:**
- Risk: The active local interpreter is Python 3.13.5 while the project and CI target Python 3.11; `docling`/`rapidocr-onnxruntime`/`pymupdf` wheels may lag 3.13 support.
- Impact: Runtime import/behavior differences between dev and CI.
- Migration plan: Pin a 3.11 virtualenv (`.venv`) via `start.py`/setup guidance and assert the version at launch (partially done in `start.py:29-34`).

## Missing Critical Features

**No per-document deletion from the UI:**
- Problem: `DocStore.delete_document` (`doc_store.py:575-595`) and `HybridRetriever.delete_document` (`hybrid_retriever.py:371-388`) exist but are never called from `main.py`; the only removal paths are full "Clear Session" and "Purge All Data".
- Blocks: Removing a single unwanted or sensitive document without nuking the whole store.

**No authentication/authorization layer:**
- Problem: There is no login, token, or access control anywhere in the UI or launcher.
- Blocks: Safe network-exposed or multi-user deployment despite API-key and cloud-consent features.

**Fallback vector store persistence is not crash-safe:**
- Problem: The in-memory `VectorIndex` fallback is only flushed to `fallback_store.json` on `HybridRetriever.close()` or explicit save (`hybrid_retriever.py:149-187,362-363`); an abrupt process kill loses it.
- Blocks: Reliable persistence when LanceDB is unavailable and the process dies uncleanly.

**PDF-only ingestion:**
- Problem: The uploader is restricted to `type=["pdf"]` (`main.py:377`) and validation requires the `%PDF-` magic header (`upload_validation.py:79`).
- Blocks: Ingesting images, Office documents, or HTML despite the multimodal visual stack.

## Test Coverage Gaps

**`groq_provider.py` has no dedicated test module:**
- What's not tested: `GroqProvider.generate_text` / `stream_text` / `check_health` / `get_capabilities` behavior and the `NotImplementedError` image path.
- Files: `groq_provider.py:18-170`; `tests/conftest.py:23` provides a `mock_groq_client` fixture but no `tests/test_groq_provider.py` exists.
- Risk: The legacy cloud-fallback provider can regress unnoticed.
- Priority: Medium

**`setup.py` installation/model-download logic untested:**
- What's not tested: Mirror failover, min-size verification, atomic temp→destination move, and cache warm-up.
- Files: `setup.py:87-264`, `setup.py:306-346`
- Risk: Users fail setup with no regression signal.
- Priority: Medium

**`start.py` launcher untested:**
- What's not tested: Python version gate, directory provisioning, llama-server probe (200/503/absent), and Streamlit subprocess argument construction.
- Files: `start.py:29-128`
- Risk: Silent launcher regressions on the documented happy path.
- Priority: Low

**End-to-end ingestion→OCR→visual→retrieval→answer chain untested:**
- What's not tested: The full `main.py` upload loop combined with `apply_conditional_ocr` thread-pool branch, `VisualAnalyzer` VLM calls, LanceDB indexing, and hybrid retrieval as one integration.
- Files: `main.py:383-567`; closest existing test `tests/test_main_ui.py` is mock-level.
- Risk: Integration wiring (index/embedding/FTS creation) breaks while unit tests stay green — note that no test asserts `create_fts_index` is invoked after ingestion.
- Priority: High

**Evaluation report does not match the suite:**
- What's not tested/verified: `docs/EVALUATION.md` references test modules that do not exist and reports 217 tests / 23 suites vs. the actual 233 tests / 24 files.
- Files: `docs/EVALUATION.md:10-40`, `README.md:10,106,225`
- Risk: The published quality gate is unverifiable and could mask a dropped suite.
- Priority: Medium

---

*Concerns audit: 2026-10-17*  
*Concerns resolved: 2026-10-18 (Session: fix-all-concerns-and-keras3)*
- Resolved Keras 3 runtime crash via top-level PyTorch backend enforcement in `main.py` and `start.py`.
- Deduplicated session security reset in `main.py` via `_reset_session_security_state()`.
- Guarded `st.secrets` access in `main.py` and `litellm_provider.py`.
- Keyed `document_metadata` by `doc_id` in `main.py` to prevent filename collisions.
- Derived content-hash `doc_<sha16>` when doc_id is omitted in readers.
- Hoisted inline imports and added `DeprecationWarning` to legacy facades in `hybrid_retriever.py` and `local_embedding.py`.
- Disabled LiteLLM telemetry and set `num_retries=0` in `stream_text`.
- Scrubbed API credentials from error messages and logs in `litellm_provider.py`.
- Escaped SQL literals in LanceDB queries and added `models/`, `*.gguf`, `*.tmp`, `*.onnx` to `.gitignore`.
- Added thread safety lock to `OcrEngine.ocr_page_image`.
- Added `tests/test_groq_provider.py` and `tests/test_start_launcher.py`.
- Reconciled documentation claims in `docs/EVALUATION.md`, `README.md`, and `docs/RUNBOOK.md` (248 tests / 24 test suites).
