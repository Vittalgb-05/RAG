# Codebase Structure

**Analysis Date:** 2026-10-13

## Directory Layout

```
RAG/
├── main.py                   # Streamlit entry point (920 lines): session-scoped AiModel + anchored paths + tabs (chat + summarizer) + Clear Session vs Purge All Data + Privacy & Provider Mode + telemetry widget + truncation caption
├── local_llm.py              # AiModel mode-switched orchestrator (set_cloud_mode/_detect_provider, no silent fallback, last_truncation_warning) + InferenceGate single-active-LLM lock
├── litellm_provider.py       # Consented multi-cloud adapter (groq/openai/anthropic via litellm, _assert_consent PermissionError gate, per-prefix windows/keys)
├── llama_cpp_provider.py     # Local llama-server client with SEC-01 loopback SSRF guard (scheme normalise + ipaddress.is_loopback + allow_remote opt-in)
├── resource_telemetry.py     # GPU/RAM telemetry + 5.0s TTL GPU cache (TEL-01, double-checked _SAMPLING_LOCK) + LatencyTracker + snapshot aggregation (245 lines)
├── summarizer.py             # Hierarchical 5-profile map-reduce summarization service, gate-held generation (420 lines)
├── citation_validator.py     # Post-generation [En] citation + abstention validator (181 lines)
├── hybrid_retriever.py       # Sole persistent hybrid index (always local): LanceDB + BM25 + RRF + delete_document + purge_all + anchored DEFAULT_DB_URI (649 lines)
├── local_embedding.py        # Process-shared SentenceTransformer cache (always local) + embed-fn provider for retriever (140 lines)
├── vector_index.py           # Pure-stdlib in-memory vector store, retriever fallback mirror (228 lines)
├── models.py                 # Canonical Pydantic v2 contracts incl. SummaryResult (235 lines)
├── doc_store.py              # SQLite WAL store incl. document_summaries v3 + hardened delete_document + purge_all + count_* for widget
├── model_provider.py         # BaseModelProvider ABC + HealthStatus/Capabilities incl. is_local egress flag (156 lines)
├── groq_provider.py          # Groq Cloud provider, legacy cloud path when cloud_mode=True w/o explicit cloud_provider (170 lines)
├── prompt_budget.py          # Bounded grounded context + truncation_meta reporting + bound_chat_history turn cap + XML defense
├── docling_reader.py         # Docling structured extraction + pypdf fallback, always local (311 lines)
├── pdf_reader.py             # Legacy pypdf extraction + chunking, always local (149 lines)
├── ocr_fallback.py           # Conditional RapidOCR for scanned pages, DPI clamped 72–300, always local (320 lines)
├── visual_analyzer.py        # Visual element detection + VLM analysis, rejects non-local providers, zoom ≤3.0 + 2048² px cap + max_regions=20
├── upload_validation.py      # PDF header/size/page validation (113 lines)
├── docs/
│   ├── RUNBOOK.md            # Operational runbook: lockfile install, llama-server launch (--host 127.0.0.1), ingestion/telemetry/cloud/purge procedures, troubleshooting
│   ├── LOCAL_INFERENCE.md    # Live-measured VRAM budget (3450 MB peak / 646 MB headroom on RTX 3050), model download, server flags, health check
│   └── EVALUATION.md         # Release acceptance record (test metrics, pass rate, ruff clean)
├── tests/                    # pytest suite (22 test modules + conftest + data/corpus)
│   ├── test_cloud_privacy.py       # Local-only default, consent state-transition workflow, socket-guarded ingestion invariant, turn locality schema, provider switching matrix, visual-analyzer cloud rejection, set_cloud_mode idempotency, per-provider key lookup
│   ├── test_litellm_provider.py    # Consent gate blocks, consent-grant flow, health/key-missing, capabilities, generation/stream/vision, key resolution
│   ├── test_llama_cpp_provider.py  # Streaming/health/capabilities + SEC-01 loopback tests (rejected non-loopback, allow_remote opt-in, accepted 127.0.0.0/8 + localhost + ::1 + scheme-less)
│   ├── test_concurrency_lock.py    # InferenceGate acquire/release/hold/timeout/generation/summarizer
│   ├── test_resource_telemetry.py  # nvidia-smi parse, TEL-01 TTL caching + force_refresh, psutil fallback, LatencyTracker, snapshot
│   ├── test_cache_invalidation.py  # bound_chat_history cap, Tier-1 session purge, count_*, summary version invalidation
│   ├── test_summarizer.py          # Map-reduce, profiles, cache, force_refresh, page-refs
│   ├── test_citation_validator.py  # Precision, abstention, empty, AiModel wiring
│   ├── test_main_ui.py             # Chat-turn + summary-display contracts + purge-reset + truncation-warning contracts
│   ├── test_doc_store.py           # DocStore incl. summary roundtrip/version/cascade + purge_all + delete-cascade incl. summaries
│   ├── test_local_llm.py           # Stream orchestration incl. retrieval_result + validate_response + truncation_meta
│   ├── test_local_embedding.py     # Shared model cache (identity + clear) + embedding wrapper
│   ├── test_models.py              # Contract validation incl. SummaryResult
│   ├── test_hybrid_retriever.py    # CPU pinning, anchored path, dense/BM25/RRF, persistence round-trip + purge_all (mirror empty + file unlinked)
│   ├── test_docling_reader.py      # Structured extraction + fallback
│   ├── test_ocr_fallback.py        # Conditional OCR paths
│   ├── test_visual_analyzer.py     # Detection + local-only VLM gating + zoom/pixel/region caps
│   ├── test_model_provider.py      # ABC + capabilities contracts
│   ├── test_pdf_reader.py          # Extraction + chunking
│   ├── test_prompt_budget.py       # Token budgeting + history bounding + truncation_meta flags
│   ├── test_upload_validation.py   # Header/size/page checks
│   ├── test_vector_index.py        # Vector store ops
│   ├── conftest.py                 # Shared fixtures
│   ├── __init__.py                 # Test package marker
│   └── data/corpus/                # Sample PDFs + generate_corpus.py for ingestion tests + profiler + multimodal benchmark
├── scripts/
│   ├── profile_resources.py  # 6-stage VRAM/latency/cache/concurrency profiler (live nvidia-smi seed) → RESOURCE_PROFILE.json (342 lines)
│   ├── benchmark_multimodal.py # 5-case accuracy/grounding harness (deterministic + --live) → MULTIMODAL_BENCHMARK.json (292 lines)
│   └── benchmark_baseline.py # Manual retrieval/generation benchmark (174 lines)
├── data/                     # Runtime persistence (gitignored contents; documents.db + lancedb/ present)
├── .github/workflows/
│   └── ci.yml                # CI: setup-python 3.11 → install from requirements-lock.txt (audit fix) → ruff check + format --check → generate corpus → pytest
├── .devcontainer/            # Pinned Python 3.11 image + Streamlit auto-launch on port 8501
├── application_screenshots/  # UI screenshots for docs
├── .planning/                # GSD planning artifacts
│   ├── codebase/             # This map (ARCHITECTURE.md, STRUCTURE.md, STACK.md, CONVENTIONS.md, TESTING.md, INTEGRATIONS.md, CONCERNS.md)
│   ├── research/             # RESOURCE_PROFILE.json (live 3450/646 audit) + MULTIMODAL_BENCHMARK.json (5/5 PASS) + BASELINE_BENCHMARK.json + research notes
│   ├── debug/                # reliability-performance-audit.md (P0/P1 audit findings driving the 619814a fix commit)
│   └── phases/               # 00–08 phase plans/summaries/reviews (00 baseline … 08 release hardening)
├── requirements.txt          # Dev-friendly manifest: mixed == / >= pins
├── requirements-lock.txt     # Deterministic production lockfile: uv-synced, all == (~600 lines incl. litellm, streamlit, lancedb transitive); installed by docs/RUNBOOK.md AND CI
├── requirements-test.txt     # Test-only dependencies
├── pyproject.toml            # Ruff (line-length 120, select E/F/W) + pytest (testpaths=tests) config
├── LICENSE                   # MIT License, RAG Assistant Contributors 2026
├── README.md                 # Setup, run, and architecture documentation (incl. audit-fix notes)
├── CLAUDE.md                 # GSD project context (stack / conventions / architecture excerpts)
└── .gitignore                # .env, .venv, data/, .cache/, model weights
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at the root — one file per service, no packages, no `__init__.py`.
- Contains: `main.py`, `local_llm.py` (incl. `InferenceGate`), `litellm_provider.py`, `llama_cpp_provider.py` (incl. SEC-01 loopback guard), `resource_telemetry.py` (incl. TEL-01 TTL cache), `summarizer.py`, `citation_validator.py`, `hybrid_retriever.py` (incl. `purge_all` + anchored `DEFAULT_DB_URI`), `local_embedding.py` (incl. `_MODEL_CACHE` + `get_shared_sentence_transformer` + `clear_shared_model_cache`), `vector_index.py`, `models.py`, providers, ingestion helpers (with raster clamps), `requirements*.txt`, `pyproject.toml`, `LICENSE`.
- Key files: `main.py` (entry + `get_session_ai_model` + anchored `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR` + Clear Session vs Purge All Data + Privacy & Provider Mode block + tab wiring + telemetry widget + pipeline banner + truncation caption + `MAX_CHAT_TURNS`), `local_llm.py` (`set_cloud_mode` + `_detect_provider` + `InferenceGate` + `AiModel` + `last_truncation_warning`), `litellm_provider.py` (`LiteLLMProvider` + `_assert_consent` + `_resolve_api_key_for_model`), `llama_cpp_provider.py` (loopback validation + `allow_remote` opt-in), `resource_telemetry.py` (`_GPU_CACHE_TTL_SECONDS` + `_SAMPLING_LOCK` + `clear_gpu_cache`), `models.py` (contracts), `doc_store.py` (`purge_all` + hardened `delete_document`), `prompt_budget.py` (`truncation_meta`).

**docs/:**
- Purpose: Operator- and release-facing documentation: install/launch/operate/troubleshoot, live VRAM budgeting, purge procedure, and acceptance metrics. This is the runbook layer referenced by ARCHITECTURE.md.
- Contains: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`.
- Key files: `docs/RUNBOOK.md` — venv + `pip install -r requirements-lock.txt` + Windows symlink tip; `llama-server` launch (`-m …q4_k_m.gguf --mmproj … -c 4096 -ngl 28 --host 127.0.0.1 --port 8080`) with per-flag breakdown (`--host 127.0.0.1` bound for SSRF security); `curl http://127.0.0.1:8080/health` check; ingestion limits (50 MB / 500 pages / `%PDF` magic); 5.0s telemetry TTL note; cloud-consent activation steps; Clear Session vs Purge All Data procedure; troubleshooting (unreachable server, CUDA OOM with `-ngl`/`-c` reduction, missing optional-deps graceful degrade, stale `.cache/` purge). `docs/LOCAL_INFERENCE.md` — live-measured VRAM table (690 DWM live + 1450 weights + 450 mmproj + 510 KV-4K + 350 CUDA = 3450 MB peak vs 4,096 MB ceiling, 646 MB headroom), model download, server flags. `docs/EVALUATION.md` — release metrics record.

**tests/:**
- Purpose: pytest suite mirroring each root module, plus concurrency/telemetry/cache-invalidation/cloud-privacy suites, a file corpus, and UI-contract tests. 22 `test_*.py` modules on disk (see tree for per-file scope); `docs/EVALUATION.md` records the release tally.
- Contains: `conftest.py`, `__init__.py`, 22 `test_*.py` modules, `data/corpus/` (sample PDFs + `generate_corpus.py`).
- Key files: `tests/test_cloud_privacy.py` (default-session-local-only assert; `local → unconsented-blocked → consented-active → revoked` workflow; socket-`create_connection`-guarded embed+index+search invariant; `is_cloud`/`model_name` turn-schema contract; groq/openai/anthropic capability matrix; `VisualAnalyzer`-rejects-cloud direct + `main.py`-filter checks; `set_cloud_mode` idempotency WR-02; per-provider `cloud_api_keys` lookup WR-01), `tests/test_litellm_provider.py` (unconsented methods → `PermissionError "Cloud transmission blocked"`; `set_consent(True)` grant flow with mocked `litellm.completion`; missing-key `unreachable` health; capabilities; 4-tier key resolution), `tests/test_llama_cpp_provider.py` (streaming/health/capabilities + SEC-01: rejected non-loopback, `allow_remote` opt-in, accepted loopback variants), `tests/test_concurrency_lock.py` (gate unit + generation/summarizer hold probes with autouse drain fixture), `tests/test_resource_telemetry.py` (mocked nvidia-smi parse, TEL-01 TTL-caching + `force_refresh` bypass, psutil fallback, `LatencyTracker`, snapshot), `tests/test_cache_invalidation.py` (turn-cap, Tier-1 session purge, `count_*`, Tier-3 hit + `model_version` invalidation), `tests/test_summarizer.py` (dispatch, profiles, cache, `force_refresh`, page-refs), `tests/test_citation_validator.py` (precision/abstention/empty/AiModel wiring), `tests/test_main_ui.py` (chat-turn + summary-display contracts + purge-reset + truncation-warning contracts), `tests/test_hybrid_retriever.py` (CPU pinning, anchored path, dense/BM25/RRF, persistence round-trip, `purge_all` mirror-empty + file-unlinked), `tests/test_doc_store.py` (CRUD + summary roundtrip/version/cascade + `purge_all` empties all tables + delete-cascade incl. summaries), `tests/test_local_embedding.py` (shared-cache identity + `clear_shared_model_cache` + wrapper), `tests/test_prompt_budget.py` (token budgeting + history bounding + `truncation_meta` flags), `tests/test_visual_analyzer.py` (detection + local-only gating + zoom/pixel/region caps), `tests/conftest.py` (shared fixtures).

**scripts/:**
- Purpose: Offline/manual tooling, excluded from strict lint (`pyproject.toml` per-file-ignores for `E402`); never imported by the app.
- Contains: `scripts/profile_resources.py`, `scripts/benchmark_multimodal.py`, `scripts/benchmark_baseline.py`.
- Key files: `scripts/profile_resources.py` — `BenchmarkProvider` (deterministic `BaseModelProvider` with `call_count`, 20ms `generate_text`, 5-token `stream_text`), `run_resource_profile()` 6-stage audit (live-seeded baseline RSS/VRAM → ingestion ms/page → CPU embedding ms/chunk → LanceDB index + cold/warm `search_hybrid` → cold vs warm summary with `<50ms` cache-SLA assert → `InferenceGate` hold-cycle check → projected-peak VRAM budget 3450 vs 3800 MB) writing `.planning/research/RESOURCE_PROFILE.json`; run via `python scripts/profile_resources.py`. `scripts/benchmark_multimodal.py` — `DeterministicBenchmarkProvider` (keyword-shaped canned answers per query class) + 5 `BENCHMARK_CASES` (table×2 / visual / text / abstention) + `run_benchmark(live_model=False)` (isolated `data/lancedb_bench` index → per-case `search_hybrid(k=3)` + `AiModel` stream + `validate_citations` + keyword/abstention checks → aggregate metrics → `.planning/research/MULTIMODAL_BENCHMARK.json` → `purge_all()` + `close()` cleanup); `--live` flag swaps in a health-checked resident `LlamaCppProvider` with deterministic fallback; run via `python scripts/benchmark_multimodal.py [--live]`. `scripts/benchmark_baseline.py` — manual predecessor benchmark (174 lines).

**data/:**
- Purpose: Runtime persistence created on first run; contents are gitignored; always local (never egresses in either mode); locations anchored (`DOC_STORE_PATH`, `DEFAULT_DB_URI`).
- Contains: `documents.db` (+ WAL/SHM sidecars) from `DocStore(DOC_STORE_PATH)` (`main.py:86-89`); `lancedb/` LanceDB tables or `fallback_store.json` from `HybridRetriever`; `lancedb_bench/` only transiently during benchmark runs (purged + closed on completion).
- Key files: None committed — runtime state only. `document_summaries` rows live inside `documents.db` (schema v3). Fully wiped by Purge All Data; untouched by Clear Session.

**.cache/ (absent until first upload):**
- Purpose: Best-effort per-document disk cache Tier 2 (`STORE-03`), written in the upload persist block; anchored as `CACHE_DIR` (`main.py:86-89`).
- Contains (when created): `<sha256>/docling-1000-200-v1/{pages.json, chunks,manifest}.json` via `cache_dir_for` (`models.py`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Key files: None committed. Wiped ONLY by Purge All Data (`shutil.rmtree(CACHE_DIR)`).

**.planning/research/:**
- Purpose: Generated benchmark/profiler artifact destination + research notes.
- Contains: `RESOURCE_PROFILE.json` (live audit: 3450.0 peak / 646.0 headroom / `compliant_with_qual_01: true` / `hardware_live` block, written by `scripts/profile_resources.py`), `MULTIMODAL_BENCHMARK.json` (100.0 factual / 100.0 visual / 100.0 abstention / 100.0 citation precision, 0.087s avg, 5/5 PASS, written by `scripts/benchmark_multimodal.py`), `BASELINE_BENCHMARK.json`, `STACK.md` / `ARCHITECTURE.md` / `FEATURES.md` / `PITFALLS.md` / `SUMMARY.md` research notes.
- Key files: None committed as source — generated on harness runs (committed as audit evidence by the fix commit).

**.planning/debug/:**
- Purpose: Audit findings driving hardening work.
- Contains: `reliability-performance-audit.md` (P0/P1 findings: lockfile sync, live VRAM profiling, multimodal benchmark, persistent purge, shared embeddings, session-scoped consent — closed by audit commit `619814a`).

**.planning/codebase/:**
- Purpose: GSD codebase maps consumed by plan/execute commands (this file, `ARCHITECTURE.md`, `STACK.md`, `CONVENTIONS.md`, `TESTING.md`, `INTEGRATIONS.md`, `CONCERNS.md`).

**.planning/phases/:**
- Purpose: Phase lifecycle artifacts (00 baseline … 08 release hardening): `*-PLAN.md`, `*-SUMMARY.md`, `*-REVIEW.md`, `*-REVIEW-FIX.md`, `*-VERIFICATION.md`, `RESEARCH.md`.

**.github/workflows/:**
- Purpose: CI pipeline.
- Contains: `ci.yml` — checkout → setup-Python 3.11 with pip cache → install from `requirements-lock.txt` (audit fix P0-1: deterministic, uv-synced) + test deps → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`. nvidia-smi absent on CI → telemetry `None` path exercised, never a failure; LiteLLM/multimodal tests mock providers (no network/keys needed).

**application_screenshots/:**
- Purpose: UI screenshots embedded in docs/README.
- Generated: No (manual captures).
- Committed: Yes.

**tests/data/corpus/:**
- Purpose: Sample PDFs exercised by ingestion/extraction tests AND both harnesses (`clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`, plus `generate_corpus.py` which CI regenerates).
- Generated: Regenerated in CI via `generate_corpus.py`; fixtures present on disk.
- Committed: Yes.

## Key File Locations

**Entry Points:**
- `main.py` (920 lines): Sole runtime entry — `streamlit run main.py` (per `docs/RUNBOOK.md`). Anchored paths `main.py:86-89`; session-scoped `get_session_ai_model` + alias `main.py:92-106`; Privacy & Provider Mode block; Clear Session vs Purge All Data `main.py:297-378`; tab root (`st.tabs`); chat loop; summary loop; truncation caption.
- `scripts/benchmark_multimodal.py:290-292`: Multimodal harness entry (`run_benchmark(live_model)` under `if __name__ == "__main__"`, `--live` flag).
- `scripts/profile_resources.py:341-342`: Profiler entry (`run_resource_profile()` under `if __name__ == "__main__"`).
- `scripts/benchmark_baseline.py`: Manual benchmark entry.
- `docs/RUNBOOK.md`: Operator entry — install → launch → operate (incl. purge) → troubleshoot sequence.
- `docs/LOCAL_INFERENCE.md`: Live VRAM-budget + model-acquisition reference.
- `docs/EVALUATION.md`: Release acceptance record.

**Session-scoped inference + anchored paths (P1 audit):**
- `main.py:86-89`: `APP_DIR` / `DOC_STORE_PATH` / `CACHE_DIR` anchored constants + module-level `doc_store`.
- `main.py:92-106`: `get_session_ai_model()` (per-session lazy `AiModel` in `st.session_state.ai_model`) + `load_ai_model` backwards-compatibility alias.
- `local_llm.py`: `last_truncation_warning` dict (`prompt_truncated`/`context_truncated`/`history_truncated`) threaded as `truncation_meta` into `assemble_grounded_messages`.
- `local_embedding.py:18-42`: `_MODEL_CACHE` + `get_shared_sentence_transformer(model_name, device)` + `clear_shared_model_cache()`; `LocalEmbedding.__init__` uses the shared model.

**Persistent purge (P1 audit):**
- `main.py:297-327`: `Clear Session` — memory-only reset (doc ids, index handles + `close()`, chat, `summary_*` keys, cloud posture + credential cleanse) + `st.rerun()`.
- `main.py:329-378`: `Purge All Data` — `doc_store.purge_all()` + session/temp `HybridRetriever.purge_all()` + `close()` + `shutil.rmtree(CACHE_DIR)` + same session/cloud reset + `st.toast(...)` + `st.rerun()`.
- `doc_store.py`: `delete_document` (explicit per-table cascade incl. summaries + `TypeError` guard) + `purge_all` (single-transaction wipe of all five tables).
- `hybrid_retriever.py`: `purge_all` (drop LanceDB `chunks` table warn-and-continue + fresh fallback `VectorIndex` + unlink `fallback_store.json` warn-and-continue) + `delete_document(doc_id)` eviction + anchored `DEFAULT_DB_URI`.

**Privacy & Provider Mode (cloud/local switch + consent + egress UI):**
- Session keys incl. `ai_model` + cloud keys (`cloud_mode`, `cloud_mode_toggle`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys` dict, legacy `cloud_api_key`).
- Consent dialog — `_render_consent_dialog_content` (external-transmission warning + stays-local list + consent/cancel buttons) + `show_consent_dialog` (`@st.dialog("Cloud Inference & Data Privacy Consent")` with plain-render fallback).
- Toggle state machine — `st.toggle("Enable Cloud Inference", key="cloud_mode_toggle")`; ON-without-consent → dialog; OFF-while-active → triple-flag reset + `st.rerun()`.
- `CLOUD_PROVIDER_OPTIONS` (groq/openai/anthropic → label/model-id/env-var) + selectbox + memory-only session API key `st.text_input` + `☁️ Cloud Mode Active` / `🔒 Local Mode Active` captions + `Revoke Consent (Switch to Local)` triple-flag reset.
- Provider sync — cached `LiteLLMProvider(cloud_model, active_key, user_consented=True)` per `(model, key)` + `ai_model.set_cloud_mode(True, ...)` on the session instance; else-branch closes/clears cached provider + `ai_model.set_cloud_mode(False)`.
- Model health badge — `🟢 Inference: Local ({model})` vs `☁️ Inference: Cloud ({model})` vs `⏳ Loading` vs `⚠️ Offline`.
- Pipeline banner — `🔒 100% Offline Local Pipeline` vs `☁️ Cloud Inference · {model} (Embeddings & LanceDB 100% Local)`.
- Egress badges — replay (`is_cloud`/`model_name` per turn) and live (`caps.is_local`/`caps.model_name`) `☁️ ... with user consent.` vs `🔒 ... (zero network egress).`
- Evidence chips + `🔍 Cited Evidence & Source Context` drawer (mode-identical) + truncation caption (`ℹ️ Retrieved evidence context was truncated…` when `context_truncated`).
- Turn persistence — `is_cloud: not caps.is_local` + `model_name: caps.model_name` on both success and interruption turns.

**Provider selection (explicit, no silent fallback) + loopback guard:**
- `local_llm.py`: `AiModel.__init__(provider=None, cloud_mode=False, cloud_provider=None)` — explicit provider wins, else `_detect_provider()`; default is strictly local.
- `local_llm.py`: `set_cloud_mode(enabled, cloud_provider=None)` — WR-02 idempotent fast path, flag set, optional provider store, `close()`, re-detect, `model_name` refresh.
- `local_llm.py`: `_detect_provider()` — `cloud_mode=True` → injected `cloud_provider` or health-checked `GroqProvider`; `cloud_mode=False` → unconditional `LlamaCppProvider()`. No cross-boundary health fallback.
- `local_llm.py`: `check_health()` — same-mode re-probe only.
- `llama_cpp_provider.py:23-67`: Loopback guard — scheme normalisation, `localhost`-literal or `ipaddress.is_loopback` check, `ValueError("Restricted endpoint: ...")` unless `allow_remote=True`; `httpx.Client` timeouts `connect=2.0/read=60.0/write=10.0/pool=5.0`.
- `litellm_provider.py`: `DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"`; `KNOWN_CONTEXT_WINDOWS` (groq 131072 / openai 128000 / anthropic 200000) + `VISION_SUPPORTED_PREFIXES`.
- `litellm_provider.py`: `_resolve_api_key_for_model` — per-prefix resolution: session `cloud_api_keys` dict → legacy `cloud_api_key` → `st.secrets[ENV_VAR]` → `os.environ[ENV_VAR]`.
- `litellm_provider.py`: `_detect_image_mime_type` (magic-byte sniff JPEG/PNG/GIF/WEBP).
- `litellm_provider.py`: `set_consent` / `_assert_consent` (`PermissionError` gate on all transmitting methods).
- `litellm_provider.py`: `check_health` (missing-install / missing-key `unreachable`) + `get_capabilities` (`is_local=False`).
- `litellm_provider.py`: `generate_text` / `stream_text` / `analyze_image` (consent-first, `litellm.completion` with `timeout=30.0`/`num_retries=2`, `RuntimeError`-wrapped failures) + no-op `close`.
- `model_provider.py`: `ProviderCapabilities` — `is_local` is the egress discriminator consumed by every badge/banner/filter.

**Concurrency (single-active-LLM):**
- `local_llm.py:26-90`: `InferenceGate` — `_lock: RLock` + `_active_threads`/`_state_lock`, `acquire(timeout=60.0)`, `release()`, `is_locked()`, `hold(timeout)` context manager (raises `TimeoutError`).
- Stream path — `acquire(60s)` → busy-yield on failure → `yield from provider.stream_text` → `finally: release()`.
- `local_llm.py`: `AiModel.generate_text(..., timeout=60.0)` — `with InferenceGate.hold(...)`.
- `summarizer.py`: Map-reduce dispatch inside `with InferenceGate.hold(timeout=120.0)`.

**Telemetry (TTL-cached probes → widget → live-seeded profiler artifact):**
- `resource_telemetry.py:25-30`: TTL state — `_GPU_CACHE_TTL_SECONDS = 5.0`, `_LAST_GPU_INFO`, `_LAST_GPU_SAMPLE_TIME`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`.
- `resource_telemetry.py:33-95`: `get_gpu_memory_info(force_refresh=False)` — TTL fast path + double-checked sampling + nvidia-smi CSV parse + `None` fallbacks; `clear_gpu_cache()` reset hook.
- `resource_telemetry.py`: `LatencyTracker`/`track_stage`/`record_stage_latency`/`get_latency_history`/`clear_latency_history` (`MAX_STAGE_HISTORY=200`) + `get_process_memory_info` + `get_system_telemetry_snapshot`.
- `main.py`: Sidebar `📊 System Telemetry & VRAM` expander widget (`st.metric` + `st.progress` + tiered captions + RSS + `count_documents`/`count_summaries`).
- `scripts/profile_resources.py:94-342`: 6-stage offline profiler with live VRAM seed → `.planning/research/RESOURCE_PROFILE.json` (3450.0 peak / 646.0 headroom / compliant / `hardware_live` block).
- `docs/RUNBOOK.md`: Operator-facing TTL note (5.0s cache avoids process-spawn latency).

**Multimodal benchmark harness (P0 audit):**
- `scripts/benchmark_multimodal.py:33-86`: `DeterministicBenchmarkProvider` (`BaseModelProvider`, keyword-shaped canned answers per query class, `is_local=True`, vision-capable `analyze_image`).
- `scripts/benchmark_multimodal.py:88-129`: `BENCHMARK_CASES` (5: `table_q1_lookup` / `table_fy_total` / `visual_diagram_steps` / `digital_claim_lookup` / `absent_abstention_check` with pdf/query/keywords/abstention flags).
- `scripts/benchmark_multimodal.py:132-287`: `run_benchmark(live_model=False)` — corpus ensure → provider select (live-health-checked `LlamaCppProvider` iff `--live` and healthy, else deterministic) → isolated `data/lancedb_bench` index + `purge_all()` → per-case `search_hybrid(k=3)` + `AiModel` stream + `validate_citations` + keyword/abstention verdicts → aggregate metrics → `.planning/research/MULTIMODAL_BENCHMARK.json` → `purge_all()` + `close()` cleanup.
- `.planning/research/MULTIMODAL_BENCHMARK.json` (74 lines): 100.0 factual / 100.0 visual / 100.0 abstention / 100.0 citation precision, 0.087s avg latency, 5/5 PASS.

**Retrieval (sole index, always local):**
- `hybrid_retriever.py`: `compute_rrf`, `HybridRetriever` — `index_chunks` (upsert dedup + LanceDB/`fallback_store.json` mirror), `search_dense`, `search_fts`, `_bm25_search_fallback`, `search_hybrid` → `RetrievalResult`, `delete_document`, `purge_all`, legacy `search`/`get_context` facades, `count_chunks`/`has_document`.
- `local_embedding.py`: `_MODEL_CACHE` + `get_shared_sentence_transformer` + `clear_shared_model_cache`; `_embed_one` — the shared embedding fn injected as `HybridRetriever(embedding_fn=...)`.
- `main.py`: Sole-index build (CPU `get_embeddings` batch → `index_chunks`); sole-index query (`search_hybrid(k=5)`); CR-01 restore path (re-embed persisted chunks → fresh retriever).

**Ingestion-stays-local invariant (wiring + guards + tests + clamps):**
- Wiring: extraction/OCR/embed/index/persist blocks use only `docling_reader.py` / `pdf_reader.py` / `ocr_fallback.py` / `local_embedding.py` / `hybrid_retriever.py` / `doc_store.py` — none imports a network client.
- VLM filter: `main.py` builds `local_vlm_provider` (active provider iff `get_capabilities().is_local`, else `None`) and passes it to `VisualAnalyzer.analyze_visual_elements`; `visual_analyzer.py` additionally rejects non-local providers on direct pass.
- Raster clamps: `eff_dpi = min(300, max(72, int(dpi)))` (`ocr_fallback.py`); `zoom_clamped = min(3.0, max(0.5, float(zoom)))` + 2048×2048 pixel-budget downscale + `max_regions=20` (`visual_analyzer.py`).
- Tests: `tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` (socket-guarded embed/index/search) + `::test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` (direct + filtered paths).

**Chat bounding (turn cap + token budget + truncation flags):**
- `main.py`: `MAX_CHAT_TURNS = 50`; `append_chat_turn` (append → `bound_chat_history`); `history_to_pass = chat_history[:-1][-10:]`.
- `prompt_budget.py`: `assemble_grounded_messages` (input budget `max_context - 1024`, prompt/context clamp, oldest-first history retention, `truncation_meta` flags); `bound_chat_history(history, max_turns=50)` (tail-slice + orphan-assistant prune).
- `local_llm.py`: `last_truncation_warning` threaded from `assemble_grounded_messages`; `main.py:804-807` renders the context-truncation caption.

**Multi-tier cache (invalidation points + TTL tier + shared-weights tier):**
- Tier 1 session: summary-tab `summary_{doc_id}_{profile}` write/read; Clear Session AND Purge All purge every `summary_*` key.
- Tier 2 disk: upload persist block (`.cache/<sha>/<CONFIG_VERSION>/*.json` best-effort write; anchored `CACHE_DIR`); wiped ONLY by Purge All.
- Tier 3 SQLite: `doc_store.py` (`save_summary` upsert on `ON CONFLICT(sha256, profile)`), (`get_summary` with `model_version` invalidation → `None`), (`list/delete_summaries_for_doc`), (`summarizer.py` cache check + `force_refresh` bypass). Provider switches change `model_version`, invalidating Tier-3 rows. Wiped ONLY by Purge All (`purge_all`).
- Tier 4 vectors: `hybrid_retriever.py` (`_load/_save_fallback_store`, `close()` flush, `purge_all` drop/unlink), `doc_store.py` (`count_documents`/`count_summaries` for widget). Untouched by Clear Session.
- Time-based tier: `resource_telemetry.py` (5.0s GPU TTL, `force_refresh` bypass, `clear_gpu_cache` reset).
- Process-lifetime tier: `local_embedding.py:_MODEL_CACHE` (survives both resets by design; `clear_shared_model_cache()` for tests/reclamation).

**Configuration + lockfile strategy (P0 audit):**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`, `scripts/*` ignores `E402`) + pytest (`testpaths = ["tests"]`, `python_files = ["test_*.py"]`, warnings filters).
- `requirements.txt`: Dev-friendly manifest — exact pins for core + floor ranges for optional/heavy.
- `requirements-lock.txt`: Deterministic production lockfile, uv-synced (all `==`, ~600 lines). Installed by `docs/RUNBOOK.md` AND by CI (audit fix P0-1). Regenerate (not hand-edit) when `requirements.txt` changes.
- `requirements-test.txt`: Test-only deps.
- `.devcontainer/devcontainer.json`: Pinned Python 3.11 image, Streamlit auto-launch on port 8501.
- `LICENSE`: MIT, RAG Assistant Contributors 2026.
- Secrets (existence only, never contents): `.env` (gitignored, `load_dotenv()` in `get_session_ai_model`) + Streamlit secrets for `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` + memory-only `st.session_state.cloud_api_keys` (wiped by both resets).

**Core Logic:**
- `local_llm.py`: `InferenceGate` (26-90), `AiModel.__init__` (provider/`cloud_mode`/`cloud_provider`/`model_name` + `last_retrieval_result`/`last_verification_result`/`last_truncation_warning`), `set_cloud_mode` (idempotent), `_detect_provider` (explicit, no silent fallback), `ask_a_question_from_pdf_stream` (`retrieval_result`-first branch, in-LLM fallback retrieval, gate-held stream, `truncation_meta` threading); `generate_text`; `validate_response`.
- `llama_cpp_provider.py`: Loopback guard (40-57), `httpx.Client` build, `close`, `check_health` (unreachable + launch hint), `get_capabilities` (`is_local=True`), `generate_text`/`stream_text`/`analyze_image`.
- `litellm_provider.py`: `DEFAULT_CLOUD_MODEL`/`KNOWN_CONTEXT_WINDOWS`/`VISION_SUPPORTED_PREFIXES`, `_resolve_api_key_for_model`, `_detect_image_mime_type`, `LiteLLMProvider` — `__init__`/`set_consent`/`_assert_consent`/`check_health`/`get_capabilities`/`generate_text`/`stream_text`/`analyze_image`/`close`.
- `summarizer.py`: `PROFILE_SYSTEM_INSTRUCTIONS` (five profiles), `MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`, `extract_page_references`, `Summarizer` (301-420) — `summarize_document` (cache → resolve pages → gate-held fast/map-reduce → refs → save).
- `citation_validator.py`: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations` (empty → invalid; abstention; 0-citation → invalid; ≥95% precision).
- `prompt_budget.py`: `SYSTEM_GROUNDING_TEMPLATE`, `sanitize_xml_boundary`, `estimate_tokens`, `assemble_grounded_messages` (+ `truncation_meta`), `bound_chat_history`.
- `models.py`: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult` + `formatted_evidence`/`source_labels`, `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` + `validate_ids`.
- `main.py`: Anchored paths (86-89), session-scoped `get_session_ai_model` (92-106), Privacy & Provider Mode block, health badge, Clear Session vs Purge All Data (297-378), upload/index loop, telemetry widget, pipeline banner, `append_chat_turn`, `tab_chat` + single shared retrieval + `validate_response` + egress/verification badges + drawer + truncation caption, `tab_summary` selectbox/radio/force-refresh/generate/display.
- `doc_store.py`: `SCHEMA_V3_DDL` + `MIGRATIONS`, `upsert_document`/`get_by_sha`/`get_document`, `record_page`/`record_chunks`/`get_chunks_for_doc`, `record_evidence_elements`, `save_summary`/`get_summary` (model-version predicate)/`list/delete_summaries_for_doc`, `delete_document` (explicit cascade + `TypeError` guard), `purge_all`, `count_documents`/`count_summaries`.
- `hybrid_retriever.py` (649 lines): `DEFAULT_DB_URI` anchored default, `compute_rrf`, `HybridRetriever` (`__init__`/`_init_table`/`_load/_save_fallback_store`/`index_chunks`/`search_dense`/`search_fts`/`_bm25_search_fallback`/`search_hybrid`/`delete_document`/`purge_all`/`close`/`count_chunks`/`has_document`).
- `local_embedding.py` (140 lines): `_MODEL_CACHE` + `get_shared_sentence_transformer` + `clear_shared_model_cache` + `LocalEmbedding` (`__init__`/`_embed_one`/`get_embeddings`/`build_index`/`search`/`search_hybrid`/`get_context`).

**Testing:**
- `tests/test_cloud_privacy.py`: Privacy/state-machine suite — local-only default; full transition workflow; socket-guarded ingestion/index/search invariant; `is_cloud`/`model_name` turn contract; 3-provider capability matrix; visual-analyzer cloud rejection (direct + `main.py`-filter paths); `set_cloud_mode` idempotency (WR-02); per-provider key lookup (WR-01).
- `tests/test_litellm_provider.py`: Provider unit suite — consent gate on all three transmitting methods; grant flow with mocked `litellm.completion`; key-missing `unreachable` health; capabilities; success + `RuntimeError` wrapping; key-resolution precedence.
- `tests/test_llama_cpp_provider.py`: Local provider suite — streaming/health/capabilities + SEC-01 loopback tests (rejected non-loopback, `allow_remote` opt-in, accepted loopback variants).
- `tests/test_concurrency_lock.py`: Gate unit tests — unlocked baseline, reentrant `hold`, stray-release safety, cross-thread contention, `hold`-timeout `TimeoutError`, `generate_text`-holds-gate probe, stream-busy-yield on forced `acquire=False`, summarizer-holds-gate probe; autouse fixture drains the gate before/after each test.
- `tests/test_resource_telemetry.py`: Probe tests — mocked nvidia-smi success parse, empty/malformed → `None`, `FileNotFoundError`/`SubprocessError` → `None`, TEL-01 TTL-caching + `force_refresh` bypass assertions, multi-line first-line parsing; psutil RSS/VMS + `ImportError` → zeros; `LatencyTracker` success/error/`to_dict`, `track_stage`, `record_stage_latency`, `MAX_STAGE_HISTORY` cap, `get_system_telemetry_snapshot` shape; autouse `clear_latency_history` fixture.
- `tests/test_cache_invalidation.py`: `bound_chat_history` 50-turn bound + `MAX_CHAT_TURNS == 50` assert + orphan-assistant prune + empty passthrough; Tier-1 session purge; `count_documents`/`count_summaries` zero→N; Tier-3 hit returns `cached=True` with zero provider calls; `model_version` mismatch → `None` → regenerate.
- `tests/test_summarizer.py`: `MockSummarizerProvider` (records `generate_calls`, deterministic text); fast-path vs map-reduce dispatch, all-five-profile templates, `extract_page_references` clamping, cache-hit zero-call, `force_refresh`, model-version mismatch regeneration.
- `tests/test_citation_validator.py`: Fixture `RetrievalResult` with ranked snippets; perfect/hallucinated/abstention/abstention-with-citations/empty/ungrounded cases; `AiModel.validate_response` explicit-arg + fallback-to-`last_retrieval_result` integration.
- `tests/test_main_ui.py`: No Streamlit runtime — pure contract tests on the `{role, content, sources, verification, snippets}` chat-turn dict, the `SummaryResult.model_dump()` display dict (`cached`, `page_references`, `model_version`), purge-reset key contract, and truncation-warning caption contract.
- `tests/test_hybrid_retriever.py`: CPU pinning, anchored default path, dense indexing/search, BM25, RRF, persistence/round-trip, `delete_document` (incl. SQL-injection-shaped ids), `purge_all` (mirror empty + fallback file unlinked).
- `tests/test_local_llm.py`: Stream orchestration incl. `retrieval_result` precedence, `validate_response`, `truncation_meta` threading.
- `tests/test_local_embedding.py`: Shared-cache identity (same object across instances), `clear_shared_model_cache`, embedding wrapper behavior.
- `tests/test_prompt_budget.py`: Token budgeting, history bounding, `truncation_meta` flag assertions (prompt/context/history).
- `tests/test_visual_analyzer.py`: Detection + local-only VLM gating + zoom/pixel-budget/region-cap behavior.
- `tests/test_models.py`: Contract validation for all Pydantic models incl. `SummaryResult`.
- `tests/test_doc_store.py`: DocStore incl. summary roundtrip/version/cascade + `purge_all` empties all tables.
- `tests/conftest.py`: Shared fixtures for the suite.

## Naming Conventions

**Files:**
- `snake_case.py`, one public class/service per file: `local_llm.py` → `AiModel` + `InferenceGate`; `litellm_provider.py` → `LiteLLMProvider` + `DEFAULT_CLOUD_MODEL`/`KNOWN_CONTEXT_WINDOWS`/`VISION_SUPPORTED_PREFIXES` + `_resolve_api_key_for_model`/`_detect_image_mime_type`; `llama_cpp_provider.py` → `LlamaCppProvider` (+ `allow_remote` guard flag); `resource_telemetry.py` → `get_gpu_memory_info`/`get_process_memory_info`/`clear_gpu_cache`/`LatencyTracker`/`track_stage`/`get_system_telemetry_snapshot` + `_GPU_CACHE_TTL_SECONDS`/`_GPU_CACHE_LOCK`/`_SAMPLING_LOCK`/`_LATENCY_HISTORY`/`MAX_STAGE_HISTORY`; `summarizer.py` → `Summarizer` + `extract_page_references` + `PROFILE_SYSTEM_INSTRUCTIONS`/`MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`; `citation_validator.py` → `CitationVerificationResult` + `validate_citations`/`extract_citations`/`is_abstention`; `hybrid_retriever.py` → `HybridRetriever` + `compute_rrf` + `DEFAULT_DB_URI`; `local_embedding.py` → `LocalEmbedding` + `get_shared_sentence_transformer`/`clear_shared_model_cache` + `_MODEL_CACHE`; `doc_store.py` → `DocStore` (+ `purge_all`); `prompt_budget.py` → module functions incl. `bound_chat_history` + `truncation_meta` param. Exceptions: `main.py` (entry, no class; `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR` + `get_session_ai_model`/`load_ai_model`), `model_provider.py` (ABC + two schemas), `scripts/profile_resources.py` (`BenchmarkProvider` + `run_resource_profile`), `scripts/benchmark_multimodal.py` (`DeterministicBenchmarkProvider` + `BENCHMARK_CASES` + `run_benchmark`); `docs/*.md` are `UPPERCASE.md` runbook documents; `.planning/research/*.json` are `UPPERCASE.json` harness artifacts.

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `docs/`, `data/`, `.cache/` (created on first upload; anchored `CACHE_DIR`), `application_screenshots/`, `.devcontainer/`, `.github/workflows/`, `.planning/`, `.planning/research/` (harness artifact dir), `.planning/debug/` (audit findings), `.planning/phases/` (phase lifecycle), `.planning/codebase/` (this map).

**Tests:**
- Mirror pattern `test_<module>.py` → tests `tests/test_<module>.py` (e.g. `litellm_provider.py` → `tests/test_litellm_provider.py`, `resource_telemetry.py` → `tests/test_resource_telemetry.py`, `llama_cpp_provider.py` → `tests/test_llama_cpp_provider.py` incl. the SEC-01 facet, `local_llm.py` → `tests/test_local_llm.py` + `tests/test_concurrency_lock.py` for the gate facet, `prompt_budget.py` + `doc_store.py` counts → `tests/test_cache_invalidation.py`, purge methods → `tests/test_doc_store.py` + `tests/test_hybrid_retriever.py` + `tests/test_cache_invalidation.py` + `tests/test_main_ui.py`). New cross-cutting suites are named by concern (`test_concurrency_lock.py`, `test_resource_telemetry.py`, `test_cache_invalidation.py`, `test_cloud_privacy.py`), not by module. UI contracts that span modules live in `tests/test_main_ui.py` (no `main_ui.py` source module — it tests `main.py` tab display shapes). New audit facets extend the mirror file (`test_local_embedding.py` shared cache, `test_prompt_budget.py` truncation flags, `test_visual_analyzer.py` raster caps).

## Where to Add New Code

**New cloud/local mode or consent behavior:**
- Primary code: session flags in `main.py` (incl. `ai_model`); transitions in the Privacy & Provider Mode block (toggle/dialog/select/keys/revoke/sync). New cloud model = entry in `CLOUD_PROVIDER_OPTIONS` + its env-var name; new consent copy = `_render_consent_dialog_content`.
- Routing: `local_llm.py` (`set_cloud_mode` + `_detect_provider`) — new routing inputs must flow through `set_cloud_mode` args on the SESSION instance from `get_session_ai_model()`, never by mutating a shared singleton (none exists); keep the no-silent-fallback rule (local unhealth must NOT auto-select cloud).
- Enforcement: `litellm_provider.py` (`set_consent`/`_assert_consent`) — every new transmitting method must call `_assert_consent()` first; new API-key sources go in `_resolve_api_key_for_model` preserving the session-dict → legacy → secrets → env precedence (WR-01).
- Turn contract: new per-turn locality metadata goes next to `is_cloud`/`model_name` and must be rendered in BOTH the live badge and the replay badge.
- Session rule (P1): new per-user state goes in `st.session_state`, never in module globals or `@st.cache_resource`. Process-shared state is limited to weights/locks/TTL caches.
- Tests: `tests/test_cloud_privacy.py` (state machine, invariants, turn schema, key lookup) + `tests/test_litellm_provider.py` (gate + provider behavior).

**New egress-transparency UI (badges, chips, banners, truncation):**
- Primary code: pipeline banner, live badge, replay badge, chips/drawer, truncation caption (`main.py:804-807`). All locality branches key off `caps.is_local` (live) or persisted `is_cloud` (replay) — never off `AiModel.cloud_mode` directly.
- Rule: any new cloud caption must name the model, cite consent, and carry the stays-local qualifier (`Embeddings & LanceDB 100% Local`); any new local caption must state `zero network egress`. Any new token-budget clamp must set its `truncation_meta` flag AND render a caption like the context-truncation one.
- Tests: `tests/test_cloud_privacy.py::test_chat_turn_metadata_records_locality_and_cloud_egress` (turn schema), `tests/test_main_ui.py` (display + truncation contracts).

**New single-active-LLM / concurrency behavior:**
- Primary code: `local_llm.py` (`InferenceGate`) — new gate API goes here as `@classmethod`; new timeout policy = call-site arg (`60.0` stream, `60.0` generate, `120.0` summarizer). Never add a second lock — extend this one.
- Call sites: gate-held generation in stream / `generate_text` / `summarizer.py`; keep the stream-yields-retry-notice vs non-stream-raises-`TimeoutError` asymmetry. Gate usage is mode-independent — new providers need no gate changes.
- Tests: `tests/test_concurrency_lock.py` (gate unit + generation/summarizer hold probes with the autouse drain fixture).

**New local-endpoint / SSRF-guard behavior:**
- Primary code: `llama_cpp_provider.py` — new accepted host shapes go in the `is_loopback` predicate (keep `localhost`-literal + `ipaddress.is_loopback`; do not regress to a literal set); new bypass reasons go through the existing `allow_remote` flag, never a second flag. The server bind stays `--host 127.0.0.1` (runbook + `docs/LOCAL_INFERENCE.md` flags must stay in sync with the default `base_url`).
- Tests: `tests/test_llama_cpp_provider.py:262-292` (rejected / allowed-with-flag / accepted-variants — extend the accepted-variants list for any new loopback shape).

**New telemetry probe or widget row:**
- Primary code: `resource_telemetry.py` — new probe returns a plain dict or `None` (never raises; `logger.debug` on failure, matching `get_gpu_memory_info`/`get_process_memory_info`); decide TTL vs live: slow-subprocess probes reuse the `_GPU_CACHE_TTL_SECONDS`/`_SAMPLING_LOCK` double-checked shape with their own cache vars + a `clear_*` hook; cheap in-process probes stay live like `get_process_memory_info`. New aggregation goes in `get_system_telemetry_snapshot`.
- UI: wire reads in the sidebar telemetry expander (branch on `None`, never try/except in the widget); document any new cache window in `docs/RUNBOOK.md` next to the existing TTL note.
- Offline: extend the matching stage in `scripts/profile_resources.py` and the `profile_data` dict written to `.planning/research/RESOURCE_PROFILE.json`.
- Tests: `tests/test_resource_telemetry.py` (mock `subprocess.run`/`psutil`, assert `None`/zeros fallbacks; for TTL probes mirror the TEL-01 caching + `force_refresh` assertions).

**New multi-tier cache behavior (tiers, keys, invalidation, purge):**
- Primary code: Tier 1 session keys in `main.py` (new `summary_*`-style keys must be added to BOTH the Clear Session and Purge All purges); Tier 3 predicates in `doc_store.py:get_summary` (read-time invalidation, never key-part); Tier 3 writes in `doc_store.py:save_summary` (`ON CONFLICT` upsert); bypass flags thread through `summarizer.py:summarize_document(force_refresh=...)`. Remember provider switches change `model_version`, so new cache consumers must decide whether cross-model rows are valid.
- Purge rule: every NEW persistent tier must add its wipe to the Purge All Data handler (`main.py:329-378`) plus a `purge_*`/`delete_*` method on its store with warn-and-continue failure semantics — never raise out of purge.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- Widget counts: new `count_*` methods next to `count_documents`/`count_summaries` if the telemetry widget must surface the new tier.
- Path rule: new persistent files get an anchored constant (`APP_DIR`- or `REPO_ROOT`-relative), never a bare relative path.
- Tests: `tests/test_cache_invalidation.py` (cap/counts/hit/invalidation/purge), `tests/test_doc_store.py` (persistence + `purge_all`), `tests/test_main_ui.py` (display + purge contract).

**New benchmark / harness behavior:**
- Primary code: new harness = new `scripts/benchmark_*.py` following the `benchmark_multimodal.py` shape (`DeterministicBenchmarkProvider` + `*_CASES` list + `run_*()` writing `.planning/research/<NAME>.json` + isolated store + `purge_all()`/`close()` cleanup + `if __name__ == "__main__"` entry). Isolated LanceDB dirs (`data/lancedb_<name>`) must never collide with production `data/lancedb`.
- Live mode: copy the `--live` swap-in shape (health-checked `LlamaCppProvider`, deterministic fallback with warning, `is_live_server` recorded in the artifact).
- Tests: harnesses are operator tools, not pytest suites — but any new assertion helper they share with tests belongs in the tested module, not in `scripts/`.

**New chat-memory / bounding behavior:**
- Primary code: `prompt_budget.py:bound_chat_history` — turn-cap changes here; `main.py` (`MAX_CHAT_TURNS`) stays the single call-site constant; per-request token policy in `assemble_grounded_messages` (set the matching `truncation_meta` flag on any new clamp); retrieval window width at the `history_to_pass` slice.
- Rule: every `chat_history` mutation goes through `append_chat_turn` — never `st.session_state.chat_history.append` directly. New turn fields (like `is_cloud`/`model_name`) must be set on both success and interruption appends.
- Tests: `tests/test_cache_invalidation.py` (turn-cap contract), `tests/test_prompt_budget.py` (token budgeting + truncation flags).

**New summarization behavior (profiles, budgets, stages):**
- Primary code: `summarizer.py` — new profile = entry in `PROFILE_SYSTEM_INSTRUCTIONS` + `models.py:VALID_SUMMARY_PROFILES`; new token budget = module constant next to `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS`; new pipeline stage = private method next to `_bundle_pages`/`_summarize_map_reduce`; keep all generation inside the existing `InferenceGate.hold(timeout=120.0)` block.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- UI: wire controls in the summary tab (`profile_map`, radio, cache-key `summary_{doc_id}_{profile}`); session keys must be added to BOTH resets.
- Tests: `tests/test_summarizer.py` (service), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New QA grounding / citation behavior:**
- Primary code: `citation_validator.py` — new citation syntax = `CITATION_REGEX`; new abstention phrasing = `CANONICAL_ABSTENTION_MARKERS`; new verdict fields = `CitationVerificationResult`; threshold change = `validate_citations` `0.95` comparison.
- Prompt rules: `prompt_budget.py:SYSTEM_GROUNDING_TEMPLATE` (the `[En]` rules + abstention sentence must stay in sync with the validator or precision will collapse).
- Facade: `local_llm.py:validate_response` stays the only caller path — `main.py` must call it, never `validate_citations` directly. The benchmark harness calls `validate_citations` directly only because it audits precision per case outside the chat loop.
- Tests: `tests/test_citation_validator.py`.

**New retrieval behavior (ranking, fusion, search mode, deletion):**
- Primary code: `hybrid_retriever.py` — add methods alongside `search_dense`/`search_fts`/`search_hybrid`; pure ranking math goes in module-level functions next to `compute_rrf`. The retriever stays the sole index — do not add a second index object to session state. Retrieval stays local regardless of inference mode. New eviction paths must mirror `delete_document`/`purge_all` (update BOTH the LanceDB table and the fallback mirror + file).
- Embedding fn: `get_shared_sentence_transformer` + `LocalEmbedding._embed_one` stays the injected CPU function; session state keeps exactly one `HybridRetriever` + one `LocalEmbedding` (embed-fn holder). New model ids get their own `_MODEL_CACHE` slot automatically.
- Contracts first: extend `EvidenceSnippet`/`RetrievalResult` in `models.py` before wiring consumers.
- Tests: `tests/test_hybrid_retriever.py` + the socket-guarded invariant in `tests/test_cloud_privacy.py` (new retrieval code must pass it) + purge/delete tests for new eviction paths.

**New ingestion/extraction behavior (incl. raster budgets):**
- Primary code: `docling_reader.py` (structured), `pdf_reader.py` (legacy), `ocr_fallback.py` (scanned pages, DPI clamp), `visual_analyzer.py` (visual elements, zoom/pixel/region caps); validation in `upload_validation.py`. New ingestion code must import no network clients (the socket-guarded test enforces this).
- Wire-up: `main.py` extraction + `local_vlm_provider` filter + sole-index build block; persistence via `doc_store.py` under anchored paths. New VLM-affecting code must preserve the `is_local`-only filter AND the analyzer's internal cloud rejection.
- Budget rule: new raster allocations (render scale, crop buffers, region lists) must clamp inputs BEFORE allocating, following the DPI/zoom/pixel/`max_regions` shapes — never allocate-then-check.
- Tests: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_upload_validation.py`, `tests/test_cloud_privacy.py` (invariant + cloud-vision rejection).

**New inference provider or prompt behavior:**
- Primary code: new provider subclassing `BaseModelProvider` in `model_provider.py` next to `groq_provider.py`/`llama_cpp_provider.py`/`litellm_provider.py` (copy the `LiteLLMProvider` consent-gate shape if the provider transmits off-device; copy the `LlamaCppProvider` loopback-guard shape if it speaks HTTP to a local server); prompt assembly in `prompt_budget.py` (set `truncation_meta` on new clamps); delegation in `local_llm.py`. `Summarizer` consumes only `provider.generate_text` + `provider.get_capabilities` — keep new providers compatible with both streaming and non-streaming paths. All new token-producing paths must execute under `InferenceGate`. Wire new cloud providers through `CLOUD_PROVIDER_OPTIONS` + `set_cloud_mode` on the session instance, never by direct `ai_model.provider` assignment.
- Tests: `tests/test_model_provider.py`, `tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py` (or a new `test_<provider>.py` mirror), `tests/test_local_llm.py`, `tests/test_prompt_budget.py`, `tests/test_concurrency_lock.py` (gate-hold probe for the new path), `tests/test_cloud_privacy.py` (switching matrix + invariant).

**New persisted metadata:**
- Primary code: `models.py` (Pydantic contract) → `doc_store.py` (table + migration in `MIGRATIONS`, record/get methods + `count_*` if widget-visible + coverage in `delete_document`/`purge_all`).
- Tests: `tests/test_doc_store.py`, `tests/test_models.py`, `tests/test_cache_invalidation.py` (if cache-tier), `tests/test_main_ui.py` (if purge-visible).

**New runbook / ops documentation:**
- Primary code: `docs/RUNBOOK.md` (procedures incl. purge + troubleshooting), `docs/LOCAL_INFERENCE.md` (live VRAM/model/server reference), `docs/EVALUATION.md` (release metrics). Keep launch flags (`-c 4096 -ngl 28 --host 127.0.0.1 --port 8080`), ingestion limits (50 MB / 500 pages / `%PDF`), telemetry TTL (5.0s), live VRAM numbers (3450 peak / 646 headroom), and the lockfile install command in sync with code defaults (`llama_cpp_provider.py`, `upload_validation.py`, `resource_telemetry.py`, `requirements-lock.txt`, `.planning/research/RESOURCE_PROFILE.json`).

**New dependencies (lockfile rule, P0 audit):**
- Primary code: add the import + pin in `requirements.txt` (exact `==` for core, floor `>=` for optional/heavy) + freeze the resolved version in `requirements-lock.txt` via uv (all `==`, never hand-bump without a reinstall-freeze). Test-only deps go in `requirements-test.txt`. The runbook installs from the lockfile AND CI installs from the lockfile — both paths must stay green.

**Utilities:**
- Shared helpers: root-level `snake_case.py` module + direct import (`from x import Y`) — no packages, no barrel files. `resource_telemetry.py` is the exemplar: stdlib + optional-dependency probes with never-raise fallbacks and no project imports.

## Dependency Graph

```text
main.py (920: session-scoped AiModel + anchored paths + purge controls)
 ├── local_llm.py (AiModel incl. set_cloud_mode/_detect_provider/last_truncation_warning + InferenceGate)
 │    ├── model_provider.py (BaseModelProvider, HealthStatus, ProviderCapabilities incl. is_local)
 │    ├── groq_provider.py ──► model_provider.py
 │    ├── llama_cpp_provider.py ──► model_provider.py (+ SEC-01 loopback guard; httpx localhost-only)
 │    ├── litellm_provider.py ──► model_provider.py (+ optional litellm, guarded None)
 │    ├── prompt_budget.py (assemble_grounded_messages + truncation_meta, bound_chat_history, standalone)
 │    ├── citation_validator.py ──► models.py (RetrievalResult, type-only bound)
 │    ├── hybrid_retriever.py ──► models.py, vector_index.py
 │    │    ├── models.py (Chunk, BBox, EvidenceSnippet, RetrievalResult, SummaryResult)
 │    │    └── vector_index.py (stdlib only: math, typing)
 │    ├── local_embedding.py ──► models.py, vector_index.py (+ _MODEL_CACHE process-shared)
 │    │    └── sentence-transformers (external, CPU-pinned, shared across sessions)
 │    └── pdf_reader.py ──► pypdf, langchain-text-splitters (external)
 ├── litellm_provider.py (direct: cached consented cloud client construction per session)
 ├── summarizer.py ──► local_llm.py (InferenceGate only), model_provider.py, models.py, prompt_budget.py, doc_store.py
 ├── hybrid_retriever.py (direct: sole-index writes + query + delete_document + purge_all, always local)
 ├── local_embedding.py (direct: shared-model holder + CR-01 re-embed, always local)
 ├── resource_telemetry.py (stdlib + nvidia-smi subprocess TTL-cached + optional psutil; no project imports)
 ├── docling_reader.py ──► models.py, pdf_reader.py (fallback)
 ├── doc_store.py ──► models.py (Chunk, Document, Page, EvidenceElement, SummaryResult)
 ├── ocr_fallback.py (DPI clamp; standalone)
 ├── visual_analyzer.py ──► doc_store.py (record_evidence_elements); receives ONLY local-or-None provider from main.py
 ├── upload_validation.py (standalone)
 ├── scripts/profile_resources.py ──► doc_store.py, hybrid_retriever.py, local_embedding.py,
 │                                      local_llm.py (InferenceGate), model_provider.py, models.py,
 │                                      pdf_reader.py, resource_telemetry.py, summarizer.py
 ├── scripts/benchmark_multimodal.py ──► citation_validator.py, hybrid_retriever.py,
 │                                         llama_cpp_provider.py (--live), local_embedding.py,
 │                                         local_llm.py (AiModel), model_provider.py, models.py,
 │                                         pdf_reader.py
 └── models.py (no project imports — leaf contract module)

External-only leaves: prompt_budget.py, upload_validation.py, vector_index.py, resource_telemetry.py
Network-capable modules (egress only via consented cloud path): litellm_provider.py, groq_provider.py
Loopback-HTTP-only module (SEC-01 guarded): llama_cpp_provider.py (127.0.0.0/8, localhost, ::1 unless allow_remote=True)
Strictly offline modules (socket-guarded by tests): hybrid_retriever.py, local_embedding.py, vector_index.py, docling_reader.py, pdf_reader.py, ocr_fallback.py, doc_store.py, models.py
Benchmark scripts (offline, isolated stores, never import main.py): scripts/profile_resources.py, scripts/benchmark_multimodal.py
Docs (no imports): docs/RUNBOOK.md, docs/LOCAL_INFERENCE.md, docs/EVALUATION.md
Harness artifacts (generated JSON, committed as audit evidence): .planning/research/RESOURCE_PROFILE.json, .planning/research/MULTIMODAL_BENCHMARK.json
```

**Import direction (must stay acyclic):** `main.py` → `local_llm.py` / `summarizer.py` / `litellm_provider.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `main.py` → `litellm_provider.py` → `model_provider.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `litellm_provider.py` → `model_provider.py` only; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py` (gate-only import; `local_llm.py` never imports `summarizer.py` or `litellm_provider.py`); `summarizer.py` → `doc_store.py`, `models.py`; `docling_reader.py` → `pdf_reader.py`; `scripts/profile_resources.py` + `scripts/benchmark_multimodal.py` → everything except `main.py`; everything persistence-shaped → `models.py`. `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` import no project modules; `citation_validator.py` imports only `models.py`. Session state flows one way: `main.py` owns `st.session_state.ai_model`; no module besides `main.py` touches session state.

## Special Directories

**data/:**
- Purpose: Runtime SQLite + LanceDB persistence (incl. `document_summaries` rows in `documents.db`, `fallback_store.json` under `data/lancedb/` without LanceDB); always on-device; anchored via `DOC_STORE_PATH` / `DEFAULT_DB_URI`. `documents.db` + `lancedb/` present on disk from local runs. `lancedb_bench/` exists only transiently during multimodal benchmark runs (purged + closed on completion).
- Generated: Yes (created on first upload/index/summarize/benchmark run).
- Committed: No (gitignored; runtime state only).

**.cache/ (absent until first upload; anchored CACHE_DIR):**
- Purpose: Tier-2 per-document `{pages,chunks,manifest}.json` cache keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes (best-effort write per upload; not present on disk at analysis time).
- Committed: No.

**.planning/research/:**
- Purpose: Harness artifact output (`RESOURCE_PROFILE.json` from `scripts/profile_resources.py` — live 3450/646 audit; `MULTIMODAL_BENCHMARK.json` from `scripts/benchmark_multimodal.py` — 5/5 PASS) plus research notes (`STACK.md`, `ARCHITECTURE.md`, `FEATURES.md`, `PITFALLS.md`, `SUMMARY.md`, `BASELINE_BENCHMARK.json`).
- Generated: Yes (created on harness runs; committed as audit evidence by fix commit `619814a`).
- Committed: Yes (artifacts).

**.planning/debug/:**
- Purpose: Audit findings (`reliability-performance-audit.md` — P0/P1 issues closed by `619814a`).
- Generated: No (hand-written audit record).
- Committed: Yes.

**.planning/phases/ (00–08):**
- Purpose: Phase lifecycle (`*-PLAN.md`, `*-SUMMARY.md`, `*-REVIEW.md`, `*-REVIEW-FIX.md`, `*-VERIFICATION.md`, `RESEARCH.md`).
- Generated: No (GSD workflow artifacts).
- Committed: Yes.

---

*Structure analysis: 2026-10-13*
