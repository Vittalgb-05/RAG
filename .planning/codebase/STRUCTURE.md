# Codebase Structure

**Analysis Date:** 2026-10-12

## Directory Layout

```
RAG/
├── main.py                   # Streamlit entry point: Privacy & Provider Mode block + tabs (chat + summarizer), upload/index, mode-aware QA + validation, telemetry widget + pipeline banner, chat bounding (854 lines)
├── local_llm.py              # AiModel mode-switched orchestrator (cloud_mode/set_cloud_mode/_detect_provider, no silent fallback) + InferenceGate single-active-LLM lock + validate_response façade (346 lines)
├── litellm_provider.py       # Consented multi-cloud adapter (groq/openai/anthropic via litellm, _assert_consent PermissionError gate, per-prefix windows/keys) (346 lines)
├── llama_cpp_provider.py     # Local llama-server client with SEC-01 loopback SSRF guard (scheme normalise + ipaddress.is_loopback + allow_remote opt-in) (292 lines)
├── resource_telemetry.py     # GPU/RAM telemetry + 5.0s TTL GPU cache (TEL-01, double-checked _SAMPLING_LOCK) + LatencyTracker + snapshot aggregation (245 lines)
├── summarizer.py             # Hierarchical 5-profile map-reduce summarization service, gate-held generation (420 lines)
├── citation_validator.py     # Post-generation [En] citation + abstention validator (181 lines)
├── hybrid_retriever.py       # Sole persistent hybrid index (always local): LanceDB + BM25 + RRF (626 lines)
├── local_embedding.py        # CPU-pinned SentenceTransformer wrapper (always local), embed-fn provider for retriever (116 lines)
├── vector_index.py           # Pure-stdlib in-memory vector store, retriever fallback mirror (228 lines)
├── models.py                 # Canonical Pydantic v2 contracts incl. SummaryResult (235 lines)
├── doc_store.py              # SQLite WAL store incl. document_summaries v3 + count_* for widget (610 lines)
├── model_provider.py         # BaseModelProvider ABC + HealthStatus/Capabilities incl. is_local egress flag (156 lines)
├── groq_provider.py          # Groq Cloud provider, legacy cloud path when cloud_mode=True w/o explicit cloud_provider (170 lines)
├── prompt_budget.py          # Bounded grounded context + bound_chat_history turn cap + XML defense (152 lines)
├── docling_reader.py         # Docling structured extraction + pypdf fallback, always local (311 lines)
├── pdf_reader.py             # Legacy pypdf extraction + chunking, always local (149 lines)
├── ocr_fallback.py           # Conditional RapidOCR for scanned pages, always local (320 lines)
├── visual_analyzer.py        # Visual element detection + VLM analysis, rejects non-local providers (271 lines)
├── upload_validation.py      # PDF header/size/page validation (113 lines)
├── docs/
│   ├── RUNBOOK.md            # Operational runbook: lockfile install, llama-server launch (--host 127.0.0.1), ingestion/telemetry/cloud procedures, 4-issue troubleshooting (202 lines)
│   ├── LOCAL_INFERENCE.md    # 4 GB VRAM budget table (~3,260 MB peak), model download, server flags, health check (148 lines)
│   └── EVALUATION.md         # Release acceptance record: 217 cases, 100% pass, 50.6s, ruff clean (138 lines)
├── tests/                    # pytest suite (22 test modules + conftest + data/corpus)
│   ├── test_cloud_privacy.py       # Local-only default, consent state-transition workflow, socket-guarded ingestion invariant, turn locality schema, provider switching matrix, visual-analyzer cloud rejection, set_cloud_mode idempotency, per-provider key lookup (251 lines)
│   ├── test_litellm_provider.py    # Consent gate blocks, consent-grant flow, health/key-missing, capabilities, generation/stream/vision, key resolution (252 lines)
│   ├── test_llama_cpp_provider.py  # Streaming/health/capabilities + SEC-01 loopback tests (rejected non-loopback, allow_remote opt-in, accepted 127.0.0.0/8 + localhost + ::1 + scheme-less) (292 lines)
│   ├── test_concurrency_lock.py    # InferenceGate acquire/release/hold/timeout/generation/summarizer (225 lines)
│   ├── test_resource_telemetry.py  # nvidia-smi parse, TEL-01 TTL caching + force_refresh, psutil fallback, LatencyTracker, snapshot (190 lines)
│   ├── test_cache_invalidation.py  # bound_chat_history cap, count_*, summary version invalidation (218 lines)
│   ├── test_summarizer.py          # Map-reduce, profiles, cache, page-refs (342 lines)
│   ├── test_citation_validator.py  # Precision, abstention, empty, AiModel wiring (161 lines)
│   ├── test_main_ui.py             # Chat-turn + summary-display contracts (195 lines)
│   ├── test_doc_store.py           # DocStore incl. summary roundtrip/version/cascade (582 lines)
│   ├── test_local_llm.py           # Stream orchestration incl. retrieval_result + validate_response (248 lines)
│   ├── test_models.py              # Contract validation incl. SummaryResult (455 lines)
│   ├── test_hybrid_retriever.py    # CPU pinning, anchored path, dense/BM25/RRF, persistence round-trip (390 lines)
│   ├── test_docling_reader.py      # Structured extraction + fallback (274 lines)
│   ├── test_ocr_fallback.py        # Conditional OCR paths (326 lines)
│   ├── test_visual_analyzer.py     # Detection + local-only VLM gating (369 lines)
│   ├── test_local_embedding.py     # Embedding wrapper (45 lines)
│   ├── test_model_provider.py      # ABC + capabilities contracts (148 lines)
│   ├── test_pdf_reader.py          # Extraction + chunking (202 lines)
│   ├── test_prompt_budget.py       # Token budgeting + history bounding (160 lines)
│   ├── test_upload_validation.py   # Header/size/page checks (111 lines)
│   ├── test_vector_index.py        # Vector store ops (109 lines)
│   ├── conftest.py                 # Shared fixtures (165 lines)
│   ├── __init__.py                 # Test package marker
│   └── data/corpus/                # Sample PDFs + generate_corpus.py for ingestion tests + profiler
├── scripts/
│   ├── profile_resources.py  # 6-stage VRAM/latency/cache/concurrency profiler → RESOURCE_PROFILE.json (342 lines)
│   └── benchmark_baseline.py # Manual retrieval/generation benchmark (174 lines)
├── data/                     # Runtime persistence (gitignored contents; documents.db + lancedb/ present)
├── .github/workflows/
│   └── ci.yml                # CI: setup-python 3.11 → pip install → ruff check + format --check → generate corpus → pytest
├── .devcontainer/            # Pinned Python 3.11 image + Streamlit auto-launch on port 8501
├── application_screenshots/  # UI screenshots for docs
├── .planning/                # GSD planning artifacts (incl. this codebase map + research/ profiler output)
├── requirements.txt          # Dev-friendly manifest: 17 lines, mixed == / >= (streamlit==1.42.0 … litellm>=1.50.0)
├── requirements-lock.txt     # Deterministic production lockfile: 27 lines, all == (streamlit==1.65.0 … litellm==1.105.0); installed by docs/RUNBOOK.md
├── requirements-test.txt     # Test-only dependencies (5 lines)
├── pyproject.toml            # Ruff (line-length 120, select E/F/W) + pytest (testpaths=tests) config (20 lines)
├── LICENSE                   # MIT License, RAG Assistant Contributors 2026 (21 lines)
├── README.md                 # Setup, run, and architecture documentation
├── CLAUDE.md                 # GSD project context (stack / conventions / architecture excerpts)
└── .gitignore                # .env, .venv, data/, .cache/, model weights
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at the root — one file per service, no packages, no `__init__.py`.
- Contains: `main.py`, `local_llm.py` (incl. `InferenceGate`), `litellm_provider.py`, `llama_cpp_provider.py` (incl. SEC-01 loopback guard), `resource_telemetry.py` (incl. TEL-01 TTL cache), `summarizer.py`, `citation_validator.py`, `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`, `models.py`, providers, ingestion helpers, `requirements*.txt`, `pyproject.toml`, `LICENSE`.
- Key files: `main.py` (entry + Privacy & Provider Mode block + tab wiring + telemetry widget + pipeline banner + `MAX_CHAT_TURNS`), `local_llm.py` (`set_cloud_mode` + `_detect_provider` + `InferenceGate` + `AiModel`), `litellm_provider.py` (`LiteLLMProvider` + `_assert_consent` + `_resolve_api_key_for_model`), `llama_cpp_provider.py` (loopback validation + `allow_remote` opt-in), `resource_telemetry.py` (`_GPU_CACHE_TTL_SECONDS` + `_SAMPLING_LOCK` + `clear_gpu_cache`), `models.py` (contracts).

**docs/:**
- Purpose: Operator- and release-facing documentation: install/launch/operate/troubleshoot, VRAM budgeting, and acceptance metrics. This is the runbook layer referenced by ARCHITECTURE.md.
- Contains: `docs/RUNBOOK.md` (202), `docs/LOCAL_INFERENCE.md` (148), `docs/EVALUATION.md` (138).
- Key files: `docs/RUNBOOK.md` — venv + `pip install -r requirements-lock.txt` + Windows symlink tip; `llama-server` launch (`-m …q4_k_m.gguf --mmproj … -c 4096 -ngl 28 --host 127.0.0.1 --port 8080`) with per-flag breakdown (`--host 127.0.0.1` bound for SSRF security); `curl http://127.0.0.1:8080/health` check; ingestion limits (50 MB / 500 pages / `%PDF` magic); 5.0s telemetry TTL note; cloud-consent activation steps; 4-issue troubleshooting (unreachable server, CUDA OOM with `-ngl`/`-c` reduction, missing optional-deps graceful degrade, stale `.cache/` purge). `docs/LOCAL_INFERENCE.md` — VRAM table (Q4_K_M ~1,450 + mmproj ~450 + KV ~510 + CUDA ~350 + DWM ~500 = ~3,260 MB peak vs 4,096 MB ceiling), model download, server flags. `docs/EVALUATION.md` — release metrics (217 cases, 100% pass, 50.6s, 23 suites, ruff clean).

**tests/:**
- Purpose: pytest suite mirroring each root module, plus concurrency/telemetry/cache-invalidation/cloud-privacy suites, a file corpus, and UI-contract tests. 22 `test_*.py` modules on disk (see tree for per-file lines); `docs/EVALUATION.md` records the release tally (217 cases, 100% pass).
- Contains: `conftest.py` (165), `__init__.py`, 22 `test_*.py` modules, `data/corpus/` (sample PDFs + `generate_corpus.py`).
- Key files: `tests/test_cloud_privacy.py` (default-session-local-only assert; `local → unconsented-blocked → consented-active → revoked` workflow incl. `set_cloud_mode(True, cloud_provider)` / `set_cloud_mode(False)`; socket-`create_connection`-guarded embed+index+search invariant; `is_cloud`/`model_name` turn-schema contract; groq/openai/anthropic capability matrix 131072/128000/200000 + vision flags; `VisualAnalyzer`-rejects-cloud direct + `main.py`-filter (`local_vlm_provider is None`) checks; `set_cloud_mode` idempotency WR-02; per-provider `cloud_api_keys` lookup WR-01 incl. legacy-key pollution guard), `tests/test_litellm_provider.py` (unconsented `generate_text`/`stream_text`/`analyze_image` → `PermissionError "Cloud transmission blocked"`; `set_consent(True)` grant flow with mocked `litellm.completion`; missing-key `unreachable` health; capabilities per prefix; generation/stream/vision success + error wrapping; 4-tier key resolution), `tests/test_llama_cpp_provider.py` (provider streaming/health/capabilities + SEC-01: `test_endpoint_loopback_validation_rejected`, `test_endpoint_loopback_validation_allowed_with_flag`, `test_endpoint_loopback_accepted_addresses` covering `127.0.0.1`/`127.0.1.1`/`127.0.0.2`/`localhost`/`::1`/scheme-less), `tests/test_concurrency_lock.py` (gate unit + generation/summarizer hold probes with the autouse drain fixture), `tests/test_resource_telemetry.py` (mocked `subprocess.run` nvidia-smi parse, empty/malformed → `None`, `FileNotFoundError` → `None`, TEL-01 TTL-caching + `force_refresh` bypass assertions, psutil RSS/VMS, `LatencyTracker` success/error/`to_dict`, `track_stage`/`record_stage_latency` history cap, `get_system_telemetry_snapshot` shape; autouse `clear_latency_history` fixture), `tests/test_cache_invalidation.py` (`bound_chat_history` 50-turn cap + orphan-assistant prune + empty passthrough, `count_documents`/`count_summaries` zero→N, summary cache hit + `model_version`-mismatch invalidation — note cloud/local switches change `model_version` so they invalidate Tier-3 rows), `tests/test_summarizer.py` (fast-path vs map-reduce dispatch, all-five-profile templates, `extract_page_references`, DocStore cache hit/version-mismatch/force-refresh with `MockSummarizerProvider` counting `generate_calls`), `tests/test_citation_validator.py` (perfect precision, hallucinated rank, valid/abstention/empty/ungrounded cases, `AiModel.validate_response` explicit-arg + fallback integration), `tests/test_main_ui.py` (chat-turn dict + `SummaryResult.model_dump()` display contracts: `cached`, `page_references`, `model_version`).

**scripts/:**
- Purpose: Manual/one-off tooling, excluded from strict lint (`pyproject.toml` per-file-ignores for `E402`).
- Contains: `scripts/profile_resources.py`, `scripts/benchmark_baseline.py`.
- Key files: `scripts/profile_resources.py` — `BenchmarkProvider` (deterministic `BaseModelProvider` with `call_count`, 20ms `generate_text`, 5-token `stream_text`), `run_resource_profile()` 6-stage audit (baseline RSS/VRAM → ingestion ms/page per corpus PDF → CPU embedding ms/chunk → LanceDB index + cold/warm `search_hybrid` → cold vs warm summary with `<50ms` cache-SLA assert → `InferenceGate` hold-cycle check → projected-peak VRAM budget vs 3800 MB) writing `.planning/research/RESOURCE_PROFILE.json`; run via `python scripts/profile_resources.py`, not part of the app or test suite.

**data/:**
- Purpose: Runtime persistence created on first run; contents are gitignored; always local (never egresses in either mode).
- Contains: `documents.db` (+ WAL/SHM sidecars) from `DocStore(Path("data/documents.db"))` (`main.py:95-96`); `lancedb/` LanceDB tables or `fallback_store.json` from `HybridRetriever` (`hybrid_retriever.py:27, 110`). Both currently present on disk from local runs.
- Key files: None committed — runtime state only. `document_summaries` rows live inside `documents.db` (schema v3).

**.cache/ (absent until first upload):**
- Purpose: Best-effort per-document disk cache Tier 2 (`STORE-03`), written in the upload persist block. Not present on disk at analysis time — created on first upload.
- Contains (when created): `<sha256>/docling-1000-200-v1/{pages.json, chunks,manifest}.json` via `cache_dir_for` (`models.py`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Key files: None committed.

**.planning/research/:**
- Purpose: Generated profiler artifact destination.
- Contains: `RESOURCE_PROFILE.json` written by `scripts/profile_resources.py:329-331` (timestamp, target GPU, projected peak/headroom, hardware live RSS/GPU, ingestion/embeddings/retrieval/summarization/concurrency sections).
- Key files: None committed (generated on profiler runs).

**.planning/codebase/:**
- Purpose: GSD codebase maps consumed by plan/execute commands (this file, `ARCHITECTURE.md`, `STACK.md`, `CONVENTIONS.md`, etc.).

**.github/workflows/:**
- Purpose: CI pipeline.
- Contains: `ci.yml` — checkout → setup-Python 3.11 with pip cache → `pip install -r requirements.txt` + `pip install -r requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v`. nvidia-smi absent on CI → telemetry `None` path exercised, never a failure; LiteLLM tests mock `litellm.completion` (no network/keys needed).

**application_screenshots/:**
- Purpose: UI screenshots embedded in docs/README.
- Generated: No (manual captures).
- Committed: Yes.

**tests/data/corpus/:**
- Purpose: Sample PDFs exercised by ingestion/extraction tests AND the resource profiler (`clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`, plus `generate_corpus.py` which CI regenerates).
- Generated: Regenerated in CI via `generate_corpus.py`; fixtures present on disk.
- Committed: Yes.

## Key File Locations

**Entry Points:**
- `main.py`: Sole runtime entry — `streamlit run main.py` (per `docs/RUNBOOK.md:127-138`). Session-state init incl. cloud keys `main.py:60-76`; `load_ai_model` `main.py:84-92`; Privacy & Provider Mode block `main.py:108-245`; tab root at `main.py:556` (`st.tabs`); chat loop `main.py:558-749`; summary loop `main.py:752+`.
- `scripts/profile_resources.py:341-342`: Profiler entry (`run_resource_profile()` under `if __name__ == "__main__"`).
- `scripts/benchmark_baseline.py`: Manual benchmark entry.
- `docs/RUNBOOK.md`: Operator entry — install → launch → operate → troubleshoot sequence.
- `docs/LOCAL_INFERENCE.md`: VRAM-budget + model-acquisition reference.
- `docs/EVALUATION.md`: Release acceptance record.

**Privacy & Provider Mode (cloud/local switch + consent + egress UI):**
- `main.py:67-73`: Cloud session keys — `cloud_mode`, `cloud_mode_toggle`, `user_consented`, `cloud_provider`, `cloud_model`, `cloud_api_keys` (per-provider dict), `cloud_api_key` (legacy).
- `main.py:111-145`: Consent dialog — `_render_consent_dialog_content` (external-transmission warning + stays-local list + consent/cancel buttons) + `show_consent_dialog` (`@st.dialog("Cloud Inference & Data Privacy Consent")` with plain-render fallback).
- `main.py:147-160`: Toggle state machine — `st.toggle("Enable Cloud Inference", key="cloud_mode_toggle")`; ON-without-consent → dialog; OFF-while-active → triple-flag reset + `st.rerun()`.
- `main.py:162-208`: `CLOUD_PROVIDER_OPTIONS` (groq/openai/anthropic → label/model-id/env-var) + selectbox + memory-only session API key `st.text_input` + `☁️ Cloud Mode Active` / `🔒 Local Mode Active` captions + `Revoke Consent (Switch to Local)` triple-flag reset.
- `main.py:219-245`: Provider sync — cached `LiteLLMProvider(cloud_model, active_key, user_consented=True)` per `(model, key)` + `ai_model.set_cloud_mode(True, ...)`; else-branch closes/clears cached provider + `ai_model.set_cloud_mode(False)`.
- `main.py:251-279`: Model health badge — `🟢 Inference: Local ({model})` vs `☁️ Inference: Cloud ({model})` vs `⏳ Loading` vs `⚠️ Offline` (offline remedy in `docs/RUNBOOK.md:173-178`).
- `main.py:537-540`: Pipeline banner — `🔒 100% Offline Local Pipeline` vs `☁️ Cloud Inference · {model} (Embeddings & LanceDB 100% Local)`.
- `main.py:576-582` + `main.py:686-690`: Egress badges — replay (`is_cloud`/`model_name` per turn) and live (`caps.is_local`/`caps.model_name`) `☁️ ... with user consent.` vs `🔒 ... (zero network egress).`
- `main.py:596-618` + `main.py:703-724`: Evidence chips + `🔍 Cited Evidence & Source Context` drawer (mode-identical).
- `main.py:726-748`: Turn persistence — `is_cloud: not caps.is_local` + `model_name: caps.model_name` on both success and interruption turns.

**Provider selection (explicit, no silent fallback) + loopback guard:**
- `local_llm.py:103-126`: `AiModel.__init__(provider=None, cloud_mode=False, cloud_provider=None)` — explicit provider wins, else `_detect_provider()`; default is strictly local.
- `local_llm.py:139-160`: `set_cloud_mode(enabled, cloud_provider=None)` — WR-02 idempotent fast path, flag set, optional provider store, `close()`, re-detect, `model_name` refresh.
- `local_llm.py:162-179`: `_detect_provider()` — `cloud_mode=True` → injected `cloud_provider` or health-checked `GroqProvider`; `cloud_mode=False` → unconditional `LlamaCppProvider()`. No cross-boundary health fallback.
- `local_llm.py:181-201`: `check_health()` — same-mode re-probe only.
- `llama_cpp_provider.py:23-67`: Loopback guard — scheme normalisation (`llama_cpp_provider.py:40`), `localhost`-literal or `ipaddress.is_loopback` check (`llama_cpp_provider.py:44-51`), `ValueError("Restricted endpoint: ...")` unless `allow_remote=True` (`llama_cpp_provider.py:53-57`); `httpx.Client` timeouts `connect=2.0/read=60.0/write=10.0/pool=5.0` (`llama_cpp_provider.py:63-67`).
- `litellm_provider.py:23`: `DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"`; `litellm_provider.py:25-36`: `KNOWN_CONTEXT_WINDOWS` (groq 131072 / openai 128000 / anthropic 200000) + `VISION_SUPPORTED_PREFIXES`.
- `litellm_provider.py:39-85`: `_resolve_api_key_for_model` — per-prefix resolution: session `cloud_api_keys` dict → legacy `cloud_api_key` → `st.secrets[ENV_VAR]` → `os.environ[ENV_VAR]`.
- `litellm_provider.py:88-98`: `_detect_image_mime_type` (magic-byte sniff JPEG/PNG/GIF/WEBP).
- `litellm_provider.py:128-138`: `set_consent` / `_assert_consent` (`PermissionError` gate on all transmitting methods).
- `litellm_provider.py:140-181`: `check_health` (missing-install / missing-key `unreachable`) + `get_capabilities` (`is_local=False`).
- `litellm_provider.py:183-342`: `generate_text` / `stream_text` / `analyze_image` (consent-first, `litellm.completion` with `timeout=30.0`/`num_retries=2`, `RuntimeError`-wrapped failures) + no-op `close`.
- `model_provider.py:15-41`: `ProviderCapabilities` — `is_local` is the egress discriminator consumed by every badge/banner/filter.

**Concurrency (single-active-LLM):**
- `local_llm.py:26-90`: `InferenceGate` — `_lock: RLock` + `_active_threads`/`_state_lock`, `acquire(timeout=60.0)`, `release()`, `is_locked()`, `hold(timeout)` context manager (raises `TimeoutError`).
- `local_llm.py:285-298`: Stream path — `acquire(60s)` → busy-yield on failure → `yield from provider.stream_text` → `finally: release()`.
- `local_llm.py:300-326`: `AiModel.generate_text(..., timeout=60.0)` — `with InferenceGate.hold(...)`.
- `summarizer.py:387-394`: Map-reduce dispatch inside `with InferenceGate.hold(timeout=120.0)`.

**Telemetry (TTL-cached probes → widget → artifact):**
- `resource_telemetry.py:25-30`: TTL state — `_GPU_CACHE_TTL_SECONDS = 5.0`, `_LAST_GPU_INFO`, `_LAST_GPU_SAMPLE_TIME`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`.
- `resource_telemetry.py:33-95`: `get_gpu_memory_info(force_refresh=False)` — TTL fast path + double-checked sampling + nvidia-smi CSV parse + `None` fallbacks; `resource_telemetry.py:211`: `clear_gpu_cache()` reset hook.
- `resource_telemetry.py:99-211`: `LatencyTracker`/`track_stage`/`record_stage_latency`/`get_latency_history`/`clear_latency_history` (`MAX_STAGE_HISTORY=200`) + `get_process_memory_info` + `get_system_telemetry_snapshot`.
- `main.py:508-535`: Sidebar `📊 System Telemetry & VRAM` expander widget (`st.metric` + `st.progress` + tiered captions + RSS + `count_documents`/`count_summaries`).
- `scripts/profile_resources.py:94-342`: 6-stage offline profiler → `.planning/research/RESOURCE_PROFILE.json`.
- `docs/RUNBOOK.md:157-161`: Operator-facing TTL note (5.0s cache avoids process-spawn latency).

**Retrieval (sole index, always local):**
- `hybrid_retriever.py`: `compute_rrf` (lines 31-76), `HybridRetriever` (lines 79-626) — `index_chunks` (upsert dedup + LanceDB/`fallback_store.json` mirror), `search_dense`, `search_fts`, `_bm25_search_fallback`, `search_hybrid` → `RetrievalResult`, legacy `search`/`get_context` facades, `delete_document`, `count_chunks`/`has_document`.
- `local_embedding.py:45-50`: `_embed_one` — the shared embedding fn injected as `HybridRetriever(embedding_fn=...)` (`main.py:434-437`).
- `main.py:431-439`: Sole-index build (CPU `get_embeddings` batch → `index_chunks`); `main.py:656-660`: sole-index query (`search_hybrid(k=5)`); CR-01 restore path (re-embed persisted chunks → fresh retriever).

**Ingestion-stays-local invariant (wiring + guards + tests):**
- Wiring: extraction/OCR/embed/index/persist blocks use only `docling_reader.py` / `pdf_reader.py` / `ocr_fallback.py` / `local_embedding.py` / `hybrid_retriever.py` / `doc_store.py` — none imports a network client.
- VLM filter: `main.py:404-417` builds `local_vlm_provider` (active provider iff `get_capabilities().is_local`, else `None`) and passes it to `VisualAnalyzer.analyze_visual_elements`; `visual_analyzer.py` additionally rejects non-local providers on direct pass.
- Tests: `tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` (socket-guarded embed/index/search) + `::test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` (direct + filtered paths).

**Chat bounding (turn cap + token budget):**
- `main.py:38`: `MAX_CHAT_TURNS = 50`; `main.py:543-549`: `append_chat_turn` (append → `bound_chat_history`); `main.py:642`: `history_to_pass = chat_history[:-1][-10:]`.
- `prompt_budget.py:57-129`: `assemble_grounded_messages` (input budget `max_context - 1024`, prompt/context clamp, oldest-first history retention); `prompt_budget.py:131-152`: `bound_chat_history(history, max_turns=50)` (tail-slice + orphan-assistant prune).

**Multi-tier cache (invalidation points + TTL tier):**
- Tier 1 session: summary-tab `summary_{doc_id}_{profile}` write/read; Clear All purge of every `summary_*` key.
- Tier 2 disk: upload persist block (`.cache/<sha>/<CONFIG_VERSION>/*.json` best-effort write; `.cache/` absent on disk until first upload).
- Tier 3 SQLite: `doc_store.py:425-463` (`save_summary` upsert on `ON CONFLICT(sha256, profile)`), `doc_store.py:465-514` (`get_summary` with `model_version` invalidation → `None`), `doc_store.py:516-573` (`list/delete_summaries_for_doc`), `summarizer.py:331-336` (cache check + `force_refresh` bypass). Provider switches change `model_version`, invalidating Tier-3 rows.
- Tier 4 vectors: `hybrid_retriever.py:110-187` (`_load/_save_fallback_store`, `close()` flush), `doc_store.py:590-610` (`count_documents`/`count_summaries` for widget).
- Time-based tier: `resource_telemetry.py:25-60` (5.0s GPU TTL, `force_refresh` bypass, `clear_gpu_cache` reset).

**Configuration + lockfile strategy:**
- `pyproject.toml` (20 lines): Ruff (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`, ignore `E501/W291/W293`, `scripts/*` ignores `E402`) + pytest (`testpaths = ["tests"]`, `python_files = ["test_*.py"]`, warnings filters).
- `requirements.txt` (17 lines): Dev-friendly manifest — exact pins for core (`streamlit==1.42.0`, `pypdf==5.3.0`, `sentence-transformers==3.4.1`, `pydantic==2.11.9`, `httpx==0.28.1`, `psutil==6.1.1`) + floor ranges for optional/heavy (`docling>=2.0.0`, `rapidocr-onnxruntime>=1.3.0`, `pymupdf>=1.24.0`, `lancedb>=0.17.0`, `litellm>=1.50.0`).
- `requirements-lock.txt` (27 lines): Deterministic production lockfile (header-marked, all `==`: `streamlit==1.65.0`, `litellm==1.105.0`, `sentence-transformers==5.2.3`, `pypdf==6.12.1`, `lancedb` transitive via `pyarrow==23.0.1`, `ruff==0.15.12`, `pytest==9.0.3`). Installed by `docs/RUNBOOK.md:45-49`. Regenerate (not hand-edit) when `requirements.txt` changes.
- `requirements-test.txt` (5 lines): Test-only deps.
- `.devcontainer/devcontainer.json`: Pinned Python 3.11 image, Streamlit auto-launch on port 8501.
- `LICENSE` (21 lines): MIT, RAG Assistant Contributors 2026.
- Secrets (existence only, never contents): `.env` (gitignored, `load_dotenv()` in `load_ai_model`) + Streamlit secrets for `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` + memory-only `st.session_state.cloud_api_keys`.

**Core Logic:**
- `local_llm.py`: `InferenceGate` (26-90), `AiModel.__init__` (103-126), `set_cloud_mode` (139-160), `_detect_provider` (162-179), `ask_a_question_from_pdf_stream` (211-298) — `retrieval_result`-first branch, in-LLM fallback retrieval, gate-held stream; `generate_text` (300-326); `validate_response` (328-346).
- `llama_cpp_provider.py`: Loopback guard (40-57), `httpx.Client` build (59-67), `close`, `check_health` (unreachable + launch hint), `get_capabilities` (`is_local=True`), `generate_text`/`stream_text`/`analyze_image`.
- `litellm_provider.py`: `DEFAULT_CLOUD_MODEL`/`KNOWN_CONTEXT_WINDOWS`/`VISION_SUPPORTED_PREFIXES` (23-36), `_resolve_api_key_for_model` (39-85), `_detect_image_mime_type` (88-98), `LiteLLMProvider` (101-346) — `__init__`/`set_consent`/`_assert_consent`/`check_health`/`get_capabilities`/`generate_text`/`stream_text`/`analyze_image`/`close`.
- `summarizer.py`: `PROFILE_SYSTEM_INSTRUCTIONS` (five profiles), `MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`, `extract_page_references`, `Summarizer` (301-420) — `summarize_document` (cache → resolve pages → gate-held fast/map-reduce → refs → save).
- `citation_validator.py`: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations` (empty → invalid; abstention; 0-citation → invalid; ≥95% precision).
- `models.py`: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult` + `formatted_evidence`/`source_labels`, `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` + `validate_ids`.
- `main.py`: Session-state init incl. cloud keys (60-76), `load_ai_model` (84-92), Privacy & Provider Mode block (108-245), health badge (247-279), upload/index loop (283+), telemetry widget (508-535), pipeline banner (537-540), `append_chat_turn` (543-549), `tab_chat` + single shared retrieval (653-672) + `validate_response` + egress/verification badges + drawer (684-749), `tab_summary` selectbox/radio/force-refresh/generate/display (752+).

**Testing:**
- `tests/test_cloud_privacy.py` (251): Privacy/state-machine suite — local-only default; full transition workflow (`AiModel(cloud_mode=False)` → unconsented `PermissionError` → `set_cloud_mode(True, consented_cloud)` → `set_cloud_mode(False)`); socket-guarded ingestion/index/search invariant; `is_cloud`/`model_name` turn contract; 3-provider capability matrix; visual-analyzer cloud rejection (direct + `main.py`-filter paths); `set_cloud_mode` idempotency (WR-02); per-provider key lookup (WR-01).
- `tests/test_litellm_provider.py` (252): Provider unit suite — consent gate on all three transmitting methods; grant flow with mocked `litellm.completion`; key-missing `unreachable` health; capabilities; success + `RuntimeError` wrapping; key-resolution precedence.
- `tests/test_llama_cpp_provider.py` (292): Local provider suite — streaming/health/capabilities + SEC-01 loopback tests (rejected non-loopback, `allow_remote` opt-in, accepted loopback variants).
- `tests/test_concurrency_lock.py` (225): Gate unit tests — unlocked baseline, reentrant `hold`, stray-release safety, cross-thread contention (holder thread + 0.05s acquire → `False`), `hold`-timeout `TimeoutError`, `generate_text`-holds-gate probe, stream-busy-yield on forced `acquire=False`, summarizer-holds-gate probe; autouse fixture drains the gate before/after each test.
- `tests/test_resource_telemetry.py` (190): Probe tests — mocked nvidia-smi success parse (4096/1024/3072 → 25.0%), empty/malformed → `None`, `FileNotFoundError`/`SubprocessError` → `None`, TEL-01 TTL-caching + `force_refresh` bypass, multi-line first-line parsing; psutil RSS/VMS + `ImportError` → zeros; `LatencyTracker` success/error/`to_dict`, `track_stage`, `record_stage_latency`, `MAX_STAGE_HISTORY` cap, `get_system_telemetry_snapshot` shape; autouse `clear_latency_history` fixture.
- `tests/test_cache_invalidation.py` (218): `bound_chat_history` 50-turn bound + `MAX_CHAT_TURNS == 50` assert + orphan-assistant prune + empty passthrough; `count_documents`/`count_summaries` zero→2 roundtrips; Tier-3 hit returns `cached=True` with zero provider calls; `model_version` mismatch → `None` → regenerate.
- `tests/test_summarizer.py` (342): `MockSummarizerProvider` (records `generate_calls`, deterministic text); fast-path vs map-reduce dispatch, all-five-profile templates, `extract_page_references` clamping, cache-hit zero-call, `force_refresh`, model-version mismatch regeneration.
- `tests/test_citation_validator.py` (161): Fixture `RetrievalResult` with ranked snippets; perfect/hallucinated/abstention/abstention-with-citations/empty/ungrounded cases; `AiModel.validate_response` explicit-arg + fallback-to-`last_retrieval_result` integration.
- `tests/test_main_ui.py` (195): No Streamlit runtime — pure contract tests on the `{role, content, sources, verification, snippets}` chat-turn dict and the `SummaryResult.model_dump()` display dict (`cached`, `page_references`, `model_version`).
- `tests/test_hybrid_retriever.py` (390): CPU pinning, anchored default path, dense indexing/search, BM25, RRF, persistence/round-trip.
- `tests/test_local_llm.py` (248): Stream orchestration incl. `retrieval_result` precedence and `validate_response`.
- `tests/test_models.py` (455): Contract validation for all Pydantic models incl. `SummaryResult`.
- `tests/test_doc_store.py` (582): DocStore incl. summary roundtrip/version/cascade.
- `tests/conftest.py` (165): Shared fixtures for the suite.

## Naming Conventions

**Files:**
- `snake_case.py`, one public class/service per file: `local_llm.py` → `AiModel` + `InferenceGate`; `litellm_provider.py` → `LiteLLMProvider` + `DEFAULT_CLOUD_MODEL`/`KNOWN_CONTEXT_WINDOWS`/`VISION_SUPPORTED_PREFIXES` + `_resolve_api_key_for_model`/`_detect_image_mime_type`; `llama_cpp_provider.py` → `LlamaCppProvider` (+ `allow_remote` guard flag); `resource_telemetry.py` → `get_gpu_memory_info`/`get_process_memory_info`/`clear_gpu_cache`/`LatencyTracker`/`track_stage`/`get_system_telemetry_snapshot` + `_GPU_CACHE_TTL_SECONDS`/`_GPU_CACHE_LOCK`/`_SAMPLING_LOCK`/`_LATENCY_HISTORY`/`MAX_STAGE_HISTORY`; `summarizer.py` → `Summarizer` + `extract_page_references` + `PROFILE_SYSTEM_INSTRUCTIONS`/`MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`; `citation_validator.py` → `CitationVerificationResult` + `validate_citations`/`extract_citations`/`is_abstention`; `hybrid_retriever.py` → `HybridRetriever` + `compute_rrf`; `doc_store.py` → `DocStore`; `prompt_budget.py` → module functions incl. `bound_chat_history`. Exceptions: `main.py` (entry, no class), `model_provider.py` (ABC + two schemas), `scripts/profile_resources.py` (`BenchmarkProvider` + `run_resource_profile`); `docs/*.md` are `UPPERCASE.md` runbook documents.

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `docs/`, `data/`, `.cache/` (created on first upload), `application_screenshots/`, `.devcontainer/`, `.github/workflows/`, `.planning/`, `.planning/research/` (profiler artifact dir).

**Tests:**
- Mirror pattern `test_<module>.py` → tests `tests/test_<module>.py` (e.g. `litellm_provider.py` → `tests/test_litellm_provider.py`, `resource_telemetry.py` → `tests/test_resource_telemetry.py`, `llama_cpp_provider.py` → `tests/test_llama_cpp_provider.py` incl. the SEC-01 facet, `local_llm.py` → `tests/test_local_llm.py` + `tests/test_concurrency_lock.py` for the gate facet, `prompt_budget.py` + `doc_store.py` counts → `tests/test_cache_invalidation.py`). New cross-cutting suites are named by concern (`test_concurrency_lock.py`, `test_resource_telemetry.py`, `test_cache_invalidation.py`, `test_cloud_privacy.py`), not by module. UI contracts that span modules live in `tests/test_main_ui.py` (no `main_ui.py` source module — it tests `main.py` tab display shapes).

## Where to Add New Code

**New cloud/local mode or consent behavior:**
- Primary code: flags in `main.py:67-73`; transitions in `main.py:108-245` (toggle/dialog/select/keys/revoke/sync). New cloud model = entry in `CLOUD_PROVIDER_OPTIONS` (`main.py:162-166`) + its env-var name; new consent copy = `_render_consent_dialog_content` (`main.py:111-135`).
- Routing: `local_llm.py:139-179` (`set_cloud_mode` + `_detect_provider`) — new routing inputs must flow through `set_cloud_mode` args, never by mutating `ai_model.provider` directly; keep the no-silent-fallback rule (local unhealth must NOT auto-select cloud).
- Enforcement: `litellm_provider.py:128-138` (`set_consent`/`_assert_consent`) — every new transmitting method must call `_assert_consent()` first; new API-key sources go in `_resolve_api_key_for_model` preserving the session-dict → legacy → secrets → env precedence (WR-01).
- Turn contract: new per-turn locality metadata goes next to `is_cloud`/`model_name` (`main.py:726-748`) and must be rendered in BOTH the live badge (`main.py:686-690`) and the replay badge (`main.py:576-582`).
- Tests: `tests/test_cloud_privacy.py` (state machine, invariants, turn schema, key lookup) + `tests/test_litellm_provider.py` (gate + provider behavior).

**New egress-transparency UI (badges, chips, banners):**
- Primary code: banner `main.py:537-540`, live badge `main.py:686-690`, replay badge `main.py:576-582`, chips/drawer `main.py:596-618` + `main.py:703-724`. All locality branches key off `caps.is_local` (live) or persisted `is_cloud` (replay) — never off `AiModel.cloud_mode` directly.
- Rule: any new cloud caption must name the model, cite consent, and carry the stays-local qualifier (`Embeddings & LanceDB 100% Local`); any new local caption must state `zero network egress`.
- Tests: `tests/test_cloud_privacy.py::test_chat_turn_metadata_records_locality_and_cloud_egress` (turn schema), `tests/test_main_ui.py` (display contracts).

**New single-active-LLM / concurrency behavior:**
- Primary code: `local_llm.py:26-90` (`InferenceGate`) — new gate API goes here as `@classmethod`; new timeout policy = call-site arg (`60.0` stream, `60.0` generate, `120.0` summarizer). Never add a second lock — extend this one.
- Call sites: gate-held generation in `local_llm.py:285-298` / `local_llm.py:320` / `summarizer.py:388`; keep the stream-yields-retry-notice vs non-stream-raises-`TimeoutError` asymmetry. Gate usage is mode-independent — new providers need no gate changes.
- Tests: `tests/test_concurrency_lock.py` (gate unit + generation/summarizer hold probes with the autouse drain fixture).

**New local-endpoint / SSRF-guard behavior:**
- Primary code: `llama_cpp_provider.py:40-57` — new accepted host shapes go in the `is_loopback` predicate (keep `localhost`-literal + `ipaddress.is_loopback`; do not regress to a literal set); new bypass reasons go through the existing `allow_remote` flag, never a second flag. The server bind stays `--host 127.0.0.1` (runbook + `docs/LOCAL_INFERENCE.md` flags must stay in sync with the default `base_url`).
- Tests: `tests/test_llama_cpp_provider.py:262-292` (rejected / allowed-with-flag / accepted-variants — extend the accepted-variants list for any new loopback shape).

**New telemetry probe or widget row:**
- Primary code: `resource_telemetry.py` — new probe returns a plain dict or `None` (never raises; `logger.debug` on failure, matching `get_gpu_memory_info`/`get_process_memory_info`); decide TTL vs live: slow-subprocess probes reuse the `_GPU_CACHE_TTL_SECONDS`/`_SAMPLING_LOCK` double-checked shape with their own cache vars + a `clear_*` hook; cheap in-process probes stay live like `get_process_memory_info`. New aggregation goes in `get_system_telemetry_snapshot`.
- UI: wire reads in `main.py:508-535` (branch on `None`, never try/except in the widget); document any new cache window in `docs/RUNBOOK.md:157-161` next to the existing TTL note.
- Offline: extend the matching stage in `scripts/profile_resources.py:94-342` and the `profile_data` dict written to `.planning/research/RESOURCE_PROFILE.json`.
- Tests: `tests/test_resource_telemetry.py` (mock `subprocess.run`/`psutil`, assert `None`/zeros fallbacks; for TTL probes mirror the TEL-01 caching + `force_refresh` assertions).

**New multi-tier cache behavior (tiers, keys, invalidation):**
- Primary code: Tier 1 session keys in `main.py` (new `summary_*`-style keys must be added to the Clear All purge); Tier 3 predicates in `doc_store.py:get_summary` (read-time invalidation, never key-part); Tier 3 writes in `doc_store.py:save_summary` (`ON CONFLICT` upsert); bypass flags thread through `summarizer.py:summarize_document(force_refresh=...)`. Remember provider switches change `model_version`, so new cache consumers must decide whether cross-model rows are valid.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- Widget counts: new `count_*` methods next to `count_documents`/`count_summaries` (`doc_store.py:590-610`) if the telemetry widget must surface the new tier.
- Tests: `tests/test_cache_invalidation.py` (cap/counts/hit/invalidation), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New chat-memory / bounding behavior:**
- Primary code: `prompt_budget.py:131-152` (`bound_chat_history`) — turn-cap changes here; `main.py:38` (`MAX_CHAT_TURNS`) stays the single call-site constant; per-request token policy in `prompt_budget.py:57-129`; retrieval window width at `main.py:642`.
- Rule: every `chat_history` mutation goes through `append_chat_turn` (`main.py:543-549`) — never `st.session_state.chat_history.append` directly. New turn fields (like `is_cloud`/`model_name`) must be set on both success and interruption appends.
- Tests: `tests/test_cache_invalidation.py` (turn-cap contract), `tests/test_prompt_budget.py` (token budgeting).

**New summarization behavior (profiles, budgets, stages):**
- Primary code: `summarizer.py` — new profile = entry in `PROFILE_SYSTEM_INSTRUCTIONS` + `models.py:VALID_SUMMARY_PROFILES`; new token budget = module constant next to `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS`; new pipeline stage = private method next to `_bundle_pages`/`_summarize_map_reduce`; keep all generation inside the existing `InferenceGate.hold(timeout=120.0)` block.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- UI: wire controls in the summary tab (`main.py:752+`) (`profile_map`, radio, cache-key `summary_{doc_id}_{profile}`); session keys must be added to the Clear All purge.
- Tests: `tests/test_summarizer.py` (service), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New QA grounding / citation behavior:**
- Primary code: `citation_validator.py` — new citation syntax = `CITATION_REGEX`; new abstention phrasing = `CANONICAL_ABSTENTION_MARKERS`; new verdict fields = `CitationVerificationResult`; threshold change = `validate_citations` `0.95` comparison.
- Prompt rules: `prompt_budget.py:SYSTEM_GROUNDING_TEMPLATE` (the `[En]` rules + abstention sentence must stay in sync with the validator or precision will collapse).
- Facade: `local_llm.py:validate_response` stays the only caller path — `main.py` must call it, never `validate_citations` directly.
- Tests: `tests/test_citation_validator.py`.

**New retrieval behavior (ranking, fusion, search mode):**
- Primary code: `hybrid_retriever.py` — add methods alongside `search_dense`/`search_fts`/`search_hybrid`; pure ranking math goes in module-level functions next to `compute_rrf`. The retriever stays the sole index — do not add a second index object to session state. Retrieval stays local regardless of inference mode.
- Embedding fn: `local_embedding.py:_embed_one` stays the injected CPU function; session state keeps exactly one `HybridRetriever` + one `LocalEmbedding` (embed-fn holder).
- Contracts first: extend `EvidenceSnippet`/`RetrievalResult` in `models.py` before wiring consumers.
- Tests: `tests/test_hybrid_retriever.py` + the socket-guarded invariant in `tests/test_cloud_privacy.py` (new retrieval code must pass it).

**New ingestion/extraction behavior:**
- Primary code: `docling_reader.py` (structured), `pdf_reader.py` (legacy), `ocr_fallback.py` (scanned pages), `visual_analyzer.py` (visual elements); validation in `upload_validation.py`. New ingestion code must import no network clients (the socket-guarded test enforces this).
- Wire-up: `main.py` extraction + `local_vlm_provider` filter (`main.py:404-417`) + sole-index build block (`main.py:431-439`); persistence via `doc_store.py`. New VLM-affecting code must preserve the `is_local`-only filter AND the analyzer's internal cloud rejection.
- Tests: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_upload_validation.py`, `tests/test_cloud_privacy.py` (invariant + cloud-vision rejection).

**New inference provider or prompt behavior:**
- Primary code: new provider subclassing `BaseModelProvider` in `model_provider.py` next to `groq_provider.py`/`llama_cpp_provider.py`/`litellm_provider.py` (copy the `LiteLLMProvider` consent-gate shape if the provider transmits off-device; copy the `LlamaCppProvider` loopback-guard shape if it speaks HTTP to a local server); prompt assembly in `prompt_budget.py`; delegation in `local_llm.py`. `Summarizer` consumes only `provider.generate_text` + `provider.get_capabilities` — keep new providers compatible with both streaming and non-streaming paths. All new token-producing paths must execute under `InferenceGate`. Wire new cloud providers through `CLOUD_PROVIDER_OPTIONS` + `set_cloud_mode`, never by direct `ai_model.provider` assignment.
- Tests: `tests/test_model_provider.py`, `tests/test_llama_cpp_provider.py`, `tests/test_litellm_provider.py` (or a new `test_<provider>.py` mirror), `tests/test_local_llm.py`, `tests/test_prompt_budget.py`, `tests/test_concurrency_lock.py` (gate-hold probe for the new path), `tests/test_cloud_privacy.py` (switching matrix + invariant).

**New persisted metadata:**
- Primary code: `models.py` (Pydantic contract) → `doc_store.py` (table + migration in `MIGRATIONS`, record/get methods + `count_*` if widget-visible).
- Tests: `tests/test_doc_store.py`, `tests/test_models.py`, `tests/test_cache_invalidation.py` (if cache-tier).

**New runbook / ops documentation:**
- Primary code: `docs/RUNBOOK.md` (procedures + troubleshooting), `docs/LOCAL_INFERENCE.md` (VRAM/model/server reference), `docs/EVALUATION.md` (release metrics). Keep launch flags (`-c 4096 -ngl 28 --host 127.0.0.1 --port 8080`), ingestion limits (50 MB / 500 pages / `%PDF`), telemetry TTL (5.0s), and the lockfile install command in sync with code defaults (`llama_cpp_provider.py:25-27`, `upload_validation.py`, `resource_telemetry.py:26`, `requirements-lock.txt`).

**New dependencies (lockfile rule):**
- Primary code: add the import + pin in `requirements.txt` (exact `==` for core, floor `>=` for optional/heavy) + freeze the resolved version in `requirements-lock.txt` (all `==`, never hand-bump without a reinstall-freeze). Test-only deps go in `requirements-test.txt`. The runbook installs from the lockfile, CI installs from `requirements.txt` + `requirements-test.txt` — both paths must stay green.

**Utilities:**
- Shared helpers: root-level `snake_case.py` module + direct import (`from x import Y`) — no packages, no barrel files. `resource_telemetry.py` is the exemplar: stdlib + optional-dependency probes with never-raise fallbacks and no project imports.

## Dependency Graph

```text
main.py
 ├── local_llm.py (AiModel incl. set_cloud_mode/_detect_provider + InferenceGate)
 │    ├── model_provider.py (BaseModelProvider, HealthStatus, ProviderCapabilities incl. is_local)
 │    ├── groq_provider.py ──► model_provider.py
 │    ├── llama_cpp_provider.py ──► model_provider.py (+ SEC-01 loopback guard; httpx localhost-only)
 │    ├── litellm_provider.py ──► model_provider.py (+ optional litellm, guarded None)
 │    ├── prompt_budget.py (assemble_grounded_messages, bound_chat_history, standalone)
 │    ├── citation_validator.py ──► models.py (RetrievalResult, type-only bound)
 │    ├── hybrid_retriever.py ──► models.py, vector_index.py
 │    │    ├── models.py (Chunk, BBox, EvidenceSnippet, RetrievalResult, SummaryResult)
 │    │    └── vector_index.py (stdlib only: math, typing)
 │    ├── local_embedding.py ──► models.py, vector_index.py
 │    │    └── sentence-transformers (external, CPU-pinned)
 │    └── pdf_reader.py ──► pypdf, langchain-text-splitters (external)
 ├── litellm_provider.py (direct: cached consented cloud client construction)
 ├── summarizer.py ──► local_llm.py (InferenceGate only), model_provider.py, models.py, prompt_budget.py, doc_store.py
 ├── hybrid_retriever.py (direct: sole-index writes + query, always local)
 ├── local_embedding.py (direct: embed-fn holder + CR-01 re-embed, always local)
 ├── resource_telemetry.py (stdlib + nvidia-smi subprocess TTL-cached + optional psutil; no project imports)
 ├── docling_reader.py ──► models.py, pdf_reader.py (fallback)
 ├── doc_store.py ──► models.py (Chunk, Document, Page, EvidenceElement, SummaryResult)
 ├── ocr_fallback.py
 ├── visual_analyzer.py ──► doc_store.py (record_evidence_elements); receives ONLY local-or-None provider from main.py
 ├── upload_validation.py (standalone)
 ├── scripts/profile_resources.py ──► doc_store.py, hybrid_retriever.py, local_embedding.py,
 │                                      local_llm.py (InferenceGate), model_provider.py, models.py,
 │                                      pdf_reader.py, resource_telemetry.py, summarizer.py
 └── models.py (no project imports — leaf contract module)

External-only leaves: prompt_budget.py, upload_validation.py, vector_index.py, resource_telemetry.py
Network-capable modules (egress only via consented cloud path): litellm_provider.py, groq_provider.py
Loopback-HTTP-only module (SEC-01 guarded): llama_cpp_provider.py (127.0.0.0/8, localhost, ::1 unless allow_remote=True)
Strictly offline modules (socket-guarded by tests): hybrid_retriever.py, local_embedding.py, vector_index.py, docling_reader.py, pdf_reader.py, ocr_fallback.py, doc_store.py, models.py
Docs (no imports): docs/RUNBOOK.md, docs/LOCAL_INFERENCE.md, docs/EVALUATION.md
```

**Import direction (must stay acyclic):** `main.py` → `local_llm.py` / `summarizer.py` / `litellm_provider.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `litellm_provider.py` → `model_provider.py` only; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py` (gate-only import; `local_llm.py` never imports `summarizer.py` or `litellm_provider.py`); `summarizer.py` → `doc_store.py`, `models.py`; `docling_reader.py` → `pdf_reader.py`; `scripts/profile_resources.py` → everything except `main.py`; everything persistence-shaped → `models.py`. `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` import no project modules; `citation_validator.py` imports only `models.py`.

## Special Directories

**data/:**
- Purpose: Runtime SQLite + LanceDB persistence (incl. `document_summaries` rows in `documents.db`, `fallback_store.json` under `data/lancedb/` without LanceDB); always on-device. `documents.db` + `lancedb/` present on disk from local runs.
- Generated: Yes (created on first upload/index/summarize run).
- Committed: No (gitignored; runtime state only).

**.cache/ (absent until first upload):**
- Purpose: Tier-2 per-document `{pages,chunks,manifest}.json` cache keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes (best-effort write per upload; not present on disk at analysis time).
- Committed: No.

**.planning/research/:**
- Purpose: Profiler artifact output (`RESOURCE_PROFILE.json` from `scripts/profile_resources.py`).
- Generated: Yes (created on profiler runs).
- Committed: No (research artifact, not app state).

**application_screenshots/:**
- Purpose: UI screenshots embedded in docs/README.
- Generated: No (manual captures).
- Committed: Yes.

**tests/data/corpus/:**
- Purpose: Sample PDFs exercised by ingestion/extraction tests AND the resource profiler (`clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`, plus `generate_corpus.py` regenerated in CI).
- Generated: Regenerated in CI via `generate_corpus.py`.
- Committed: Yes.

**.github/workflows/:**
- Purpose: CI pipeline (`ci.yml`).
- Generated: No.
- Committed: Yes.

**docs/:**
- Purpose: Runbooks + VRAM reference + release acceptance record (`RUNBOOK.md`, `LOCAL_INFERENCE.md`, `EVALUATION.md`).
- Generated: No (hand-maintained; must stay in sync with code defaults per the runbook rule above).
- Committed: Yes.

---

*Structure analysis: 2026-10-12*
