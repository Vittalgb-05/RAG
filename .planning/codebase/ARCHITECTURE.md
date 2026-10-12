<!-- refreshed: 2026-10-13 -->
# Architecture

**Analysis Date:** 2026-10-13

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              Streamlit UI / Orchestrator                     │
│  `main.py` (920) — tab_chat (grounded QA) + tab_summary     │
│  (summarizer) + sidebar upload + telemetry widget +          │
│  Privacy & Provider Mode block (cloud toggle, consent       │
│  dialog, provider select, session API keys, revoke) +       │
│  Clear Session (memory-only) vs Purge All Data (persistent) │
│  + session-scoped AiModel (`get_session_ai_model`) +        │
│  anchored paths (`APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR`)    │
├──────────────────┬──────────────────┬───────────────────────┤
│  Ingestion       │  Hybrid Retrieval│  Inference (gated +    │
│  (ALWAYS LOCAL)  │  (ALWAYS LOCAL)  │  mode-switched)        │
│  `docling_reader │  `hybrid_        │  `local_llm.py`        │
│  .py`            │  retriever.py`   │  (InferenceGate +      │
│  `pdf_reader.py` │  (sole index +   │  AiModel incl.         │
│  `ocr_fallback   │  `purge_all`)    │  set_cloud_mode /      │
│  .py` (DPI       │  `local_         │  _detect_provider +    │
│  clamped 72–300)│  embedding.py`   │  `last_truncation_     │
│  `visual_        │  (shared model   │  warning`)             │
│  analyzer.py`    │  cache, embed-fn │  `model_provider.py`   │
│  (local-VLM      │  only)           │  `llama_cpp_provider   │
│  only, zoom ≤3.0 │  `vector_index   │  .py` (local default,  │
│  + 2048² px cap  │  .py` (mirror)   │  loopback-guarded)     │
│  + max 20        │                  │  `groq_provider.py`    │
│  regions)        │                  │  (legacy cloud)        │
│                  │                  │  `litellm_provider.py` │
│                  │                  │  (consented cloud)     │
│                  │                  │  `prompt_budget.py`    │
│                  │                  │  (truncation_meta)     │
│                  │                  │  `summarizer.py`       │
│                  │                  │  `citation_validator   │
│                  │                  │  .py`                 │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence + Telemetry Layer (ALWAYS LOCAL)                │
│  `doc_store.py` (SQLite `data/documents.db`: documents,     │
│   pages, chunks, evidence_elements, document_summaries v3    │
│   + `delete_document` hardened + `purge_all`)                │
│  `hybrid_retriever.py` (LanceDB `data/lancedb` +            │
│   `purge_all`: drop `chunks` table + reset mirror +         │
│   unlink `fallback_store.json`)                             │
│  `resource_telemetry.py` (5.0s-TTL GPU cache, psutil,       │
│   LatencyTracker) + `scripts/profile_resources.py` (live    │
│   VRAM audit: 3450 MB peak / 646 MB headroom)               │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Canonical Contracts + Operations + Benchmarks              │
│  `models.py` — Chunk / Page / Document / EvidenceSnippet /  │
│  RetrievalResult / BBox / EvidenceElement / SummaryResult /  │
│  SummaryProfile + VALID_SUMMARY_PROFILES                     │
│  `docs/RUNBOOK.md` + `docs/LOCAL_INFERENCE.md` +            │
│  `docs/EVALUATION.md` — install (lockfile) / launch /       │
│  troubleshoot / VRAM budget / release metrics                │
│  `scripts/benchmark_multimodal.py` →                        │
│  `.planning/research/MULTIMODAL_BENCHMARK.json` (5 cases,   │
│   100% factual/visual/abstention/citation)                   │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session-state init (incl. `cloud_mode`/`cloud_mode_toggle`/`user_consented`/`cloud_provider`/`cloud_model`/`cloud_api_keys`/`cloud_api_key`/`ai_model`), `st.tabs` wiring (`tab_chat` / `tab_summary`), Privacy & Provider Mode sidebar block, consent dialog, provider select + session keys, revoke-consent reset, session-scoped `get_session_ai_model` + `set_cloud_mode` wiring, Clear Session (memory-only) vs Purge All Data (persistent) buttons, anchored `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR`, telemetry expander widget, pipeline banner, chat replay with egress + verification badges/drawer, truncation caption, `MAX_CHAT_TURNS` bounding via `append_chat_turn`, single shared `RetrievalResult` fetch, streaming render | `main.py` |
| Session-Scoped AiModel | `get_session_ai_model()` lazily constructs one `AiModel` per browser session in `st.session_state.ai_model` (`load_dotenv()` on first creation); `load_ai_model` retained as a backwards-compatibility alias. Guarantees consent, model selection, and cloud-mode routing stay isolated per session instead of mutating a process-shared `@st.cache_resource` singleton | `main.py:92-106` |
| Purge Controls (Clear vs Purge) | `Clear Session` button resets in-memory state only (doc ids, index handles, chat, `summary_*` keys, cloud posture + credential cleanse, retriever `close()`) and reruns; `Purge All Data` additionally calls `doc_store.purge_all()`, `hybrid_retriever.purge_all()` (+ `close()` or a temp-retriever purge when no session retriever exists), `shutil.rmtree(CACHE_DIR)`, closes the cached cloud provider, resets cloud flags/keys, and shows a `st.toast` confirmation before rerun | `main.py:297-378` |
| InferenceGate | Process-level reentrant lock (`threading.RLock` + counter) guaranteeing max one active GPU inference op; `acquire`/`release`/`is_locked`/`hold` (timeout → `TimeoutError`); guards QA streaming and summarization map/reduce | `local_llm.py:26-90` |
| AiModel | Explicit mode-switched orchestration: `cloud_mode` flag + optional consented `cloud_provider`, `set_cloud_mode(enabled, cloud_provider)` dynamic toggle (idempotent no-op fast path, WR-02), `_detect_provider` explicit selection with NO silent fallback, health re-probing, RAG orchestration, `retrieval_result`-first prompt assembly via `assemble_grounded_messages` (with `truncation_meta` into `last_truncation_warning`), InferenceGate-guarded `ask_a_question_from_pdf_stream` + `generate_text`, `validate_response` citation-validation façade | `local_llm.py:93-346` |
| Truncation Transparency | `assemble_grounded_messages(..., truncation_meta)` resets and sets `prompt_truncated` / `context_truncated` / `history_truncated` flags when prompt/context/history budgets clamp; `AiModel` threads its `last_truncation_warning` dict through; the chat tab renders a `ℹ️ Retrieved evidence context was truncated…` caption when `context_truncated` is set | `prompt_budget.py`, `local_llm.py`, `main.py:804-807` |
| LiteLLMProvider (consented cloud) | Unified cloud adapter over `litellm.completion` for `groq/*`, `openai/*`, `anthropic/*` (`DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"`); programmatic `_assert_consent` gate raising `PermissionError` on every `generate_text`/`stream_text`/`analyze_image` without `user_consented=True`; `set_consent`, per-prefix context windows (groq 131072 / openai 128000 / anthropic 200000), `is_local=False`, vision allowlist, `timeout=30.0`/`num_retries=2`, 4-tier API-key resolution | `litellm_provider.py:101-346` |
| GroqProvider (legacy cloud) | Cloud fallback used only when `cloud_mode=True` without an explicit `cloud_provider` and its health check passes; `is_local=False` | `groq_provider.py` |
| LlamaCppProvider (local default, loopback-guarded) | Local llama-server client (`http://127.0.0.1:8080`, `qwen3-vl-2b`, context 4096); constructor validates `base_url` host is loopback (`localhost` literal or `ipaddress.ip_address(host).is_loopback`, scheme normalised when `://` is absent) and raises `ValueError("Restricted endpoint: ...")` for non-loopback hosts unless `allow_remote=True` is explicitly passed; `is_local=True` | `llama_cpp_provider.py:23-67` |
| Consent Dialog + Cloud-Mode Sidebar | `st.toggle("Enable Cloud Inference")` (`cloud_mode_toggle` widget key) → `show_consent_dialog()` (`@st.dialog`, fallback plain render) with `_render_consent_dialog_content` (external-transmission warning + stays-local list + `I Consent & Enable Cloud` / `Cancel (Keep 100% Local)` buttons); provider selectbox over `CLOUD_PROVIDER_OPTIONS` (groq/openai/anthropic → model id + env var); per-provider `st.text_input` session API key (memory-only); `Revoke Consent (Switch to Local)` reset; cached `LiteLLMProvider(user_consented=True)` construction + `ai_model.set_cloud_mode(True/False)` sync every rerun | `main.py:121-245` |
| Egress Transparency (badges/chips/banner) | Pipeline banner under telemetry (`🔒 100% Offline Local Pipeline` vs `☁️ Cloud Inference · {model}` with `(Embeddings & LanceDB 100% Local)` suffix); per-turn egress badge on live stream and on replay (`☁️ Generated via external cloud provider ({model}) with user consent.` vs `🔒 Generated locally on-device (zero network egress).`); `is_cloud` + `model_name` persisted per assistant turn; `[En] filename (p. N)` source chips + `🔍 Cited Evidence & Source Context` expander | `main.py`, `prompt_budget.py` |
| Resource Telemetry (TTL-cached) | `get_gpu_memory_info(force_refresh=False)` (nvidia-smi CSV parse → `total/used/free_mb` + `utilization_pct`, `None` on headless/CI; 5.0s monotonic TTL via `_GPU_CACHE_TTL_SECONDS` + `_GPU_CACHE_LOCK` fast path + `_SAMPLING_LOCK` double-checked sampling so concurrent reruns spawn at most one subprocess; `clear_gpu_cache()` test/ops hook), `get_process_memory_info` (psutil RSS/VMS MB, zeros fallback), `LatencyTracker`/`track_stage`/`record_stage_latency` (thread-safe `defaultdict`, `MAX_STAGE_HISTORY=200`), `get_system_telemetry_snapshot` (timestamp + gpu + process + per-stage count/avg/min/max) | `resource_telemetry.py:25-245` |
| Telemetry Widget | Sidebar `📊 System Telemetry & VRAM` expander: `st.metric` GPU VRAM + progress bar + 3-tier health caption (🟢 <3.5GB / 🟡 3.5–3.8GB / 🔴 >3.8GB, else CPU-only caption), process RSS caption, persistent-cache counts via `count_documents`/`count_summaries`; per-rerun reads are served from the 5.0s TTL cache, not fresh subprocess spawns | `main.py` |
| Resource Profiler (live VRAM audit) | Offline 6-stage benchmark harness (baseline RSS/live VRAM → ingestion ms/page → CPU embeddings ms/chunk → LanceDB index + cold/warm `search_hybrid` → cold vs warm summary with `<50ms` cache-SLA assert → `InferenceGate` hold-cycle check → projected-peak VRAM budget) writing `.planning/research/RESOURCE_PROFILE.json`. Live audit values (RTX 3050, audit commit): 4096 MB total, 690 MB live used (DWM baseline), 639→720 MB RSS (+81), projected peak **3450 MB** vs 3800 MB target → **646 MB headroom, QUAL-01 compliant**. Headless/CI falls back to a 487 MB empirical DWM baseline | `scripts/profile_resources.py:94-342` |
| Multimodal Benchmark Harness | Offline accuracy/grounding suite (`DeterministicBenchmarkProvider` with keyword-shaped canned answers; `--live` flag swaps in a health-checked resident `LlamaCppProvider` with deterministic fallback): 5 `BENCHMARK_CASES` (2 table lookups on `dense_table.pdf`, 1 visual diagram-steps on `chart_diagram.pdf`, 1 text claim on `clean_digital.pdf`, 1 abstention probe), indexes 3 corpus PDFs into an isolated `data/lancedb_bench` retriever, streams each answer through `AiModel.ask_a_question_from_pdf_stream`, validates via `validate_citations`, checks keyword accuracy + abstention match, writes `.planning/research/MULTIMODAL_BENCHMARK.json` (100% factual / 100% visual / 100% abstention / 100% citation precision, 0.087s avg latency), then `purge_all()` + `close()` cleanup | `scripts/benchmark_multimodal.py` (292) |
| HybridRetriever (sole index, always local) | Persistent hybrid retrieval: LanceDB dense vectors + FTS index, pure-Python BM25 fallback, RRF fusion (`compute_rrf`), `search_hybrid` → canonical `RetrievalResult`; in-memory `VectorIndex` mirror with `chunk_id` upsert dedup; disk-backed `fallback_store.json` when LanceDB missing; `db_uri` defaults to anchored `<repo_root>/data/lancedb`; `purge_all()` drops the LanceDB `chunks` table, resets the fallback mirror to a fresh `VectorIndex`, and unlinks `fallback_store.json` (all failure paths warn-and-continue); never performs network egress | `hybrid_retriever.py` |
| LocalEmbedding (shared model cache, always local) | Process-level `_MODEL_CACHE` keyed `(model_name, device)` via `get_shared_sentence_transformer` (lazy init, `clear_shared_model_cache` for tests/reclamation); `LocalEmbedding` instances share one CPU-pinned `SentenceTransformer` across sessions; `_embed_one` is the shared query/index embedding function injected into `HybridRetriever`; `build_index`/`search`/`search_hybrid`/`get_context` retained as fallback dense path | `local_embedding.py:18-140` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search` (linear-scan k-NN, cosine + Euclidean, dimension locking); serves as `HybridRetriever` fallback mirror | `vector_index.py` |
| Canonical Models | Pydantic v2 contracts: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult` (`formatted_evidence`, `source_labels`), `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` | `models.py` |
| DocStore | SQLite WAL metadata store (`documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` v3; migrations v1–v3); SHA-256 dedup, chunk restore, `save_summary`/`get_summary` (model-version invalidation)/`list_summaries_for_doc`/`delete_summaries_for_doc`/`delete_document` (explicit per-table cascade incl. summaries + `TypeError` on non-string `doc_id`)/`purge_all` (wipes all five tables)/`count_documents`/`count_summaries` for telemetry widget | `doc_store.py` |
| Summarizer | Hierarchical multi-profile summarization: profile dispatch, fast-path vs map-reduce selection, `InferenceGate.hold(timeout=120.0)`-guarded generation, `(p. X)` citation preservation, `SummaryResult` construction, 4-tier cache check/save (`force_refresh` bypass); runs against whichever provider `AiModel` currently routes to | `summarizer.py:301-420` |
| CitationValidator | Post-generation grounding gate: `extract_citations` (`[En]`), `is_abstention`, `validate_citations` → frozen `CitationVerificationResult` (≥95% precision, empty-response invalid, abstention-with-citations invalid) | `citation_validator.py` |
| Chat Bounding | `MAX_CHAT_TURNS = 50` + `append_chat_turn` (append → `bound_chat_history`) + `bound_chat_history` (tail-slice to 50, strip leading orphan assistant turns) + token-level oldest-first truncation inside `assemble_grounded_messages` (flagged via `truncation_meta`) | `main.py`, `prompt_budget.py:57-152` |
| Providers | `BaseModelProvider` ABC + `HealthStatus`/`ProviderCapabilities` (`is_local` is the egress discriminator); `LlamaCppProvider` (local default, loopback-guarded), `GroqProvider` (legacy cloud), `LiteLLMProvider` (consented multi-cloud) | `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `litellm_provider.py` |
| DoclingReader | Structured extraction via Docling `DocumentConverter` (CPU-only, `do_ocr=False`, `do_table_structure=True`); graceful degrade to `PdfReader` (pypdf); local-only | `docling_reader.py` |
| PdfReader | Legacy pypdf text extraction + `RecursiveCharacterTextSplitter` chunking (1000/200) with `{content, filename, page, chunk_id}` metadata; local-only | `pdf_reader.py` |
| Conditional OCR (DPI-clamped) | RapidOCR fallback for low-text/scanned pages with effective DPI clamped to `min(300, max(72, dpi))` to bound raster memory; local-only | `ocr_fallback.py` |
| VisualAnalyzer (budget-capped) | Visual element detection, cropping, VLM analysis with defense-in-depth cloud rejection (refuses non-local providers); raster zoom clamped to `min(3.0, max(0.5, zoom))` with a strict 2048×2048 pixel-budget downscale; `analyze_visual_elements(..., max_regions=20)` caps regions to preserve inference budget; results recorded via `DocStore.record_evidence_elements`; ingestion call site passes a `local_vlm_provider` that is `None` whenever the active provider is not local | `visual_analyzer.py`, `main.py` |
| Upload Validation | Server-side `%PDF` header / size / page-limit checks, SHA-256 + `doc_id` derivation | `upload_validation.py` |
| Prompt Budget | Bounded context assembly: `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`[E1]` citation rules + abstention sentence), `sanitize_xml_boundary`, `estimate_tokens`, oldest-first history truncation, `bound_chat_history` turn cap, `truncation_meta` reporting | `prompt_budget.py` |
| Runbooks + Evaluation Docs | `docs/RUNBOOK.md` (install via lockfile, llama-server launch flags, ingestion/telemetry/cloud/purge runbooks, troubleshooting), `docs/LOCAL_INFERENCE.md` (live VRAM budget: 3450 MB peak / 646 MB headroom, model download, server flags, health check), `docs/EVALUATION.md` (release test metrics) | `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md` |

## Pattern Overview

**Overall:** UI-orchestrated modular monolith with session-scoped inference routing, explicit local/cloud mode switching, consent-gated cloud egress, SSRF-hardened local endpoint, persistent hybrid retrieval with full purge, single-active-LLM concurrency gating, shared CPU embedding cache, TTL-cached resource telemetry, multi-tier cache invalidation, truncation transparency, raster-budget clamps, and offline benchmark harnesses.

**Key Characteristics:**
- Session-scoped inference — `get_session_ai_model()` (`main.py:92-106`) keeps one `AiModel` per browser session in `st.session_state.ai_model`; consent, model selection, and cloud-mode routing never leak across sessions. `load_ai_model` remains only as an alias.
- Anchored storage paths — `APP_DIR` / `DOC_STORE_PATH` / `CACHE_DIR` (`main.py:86-89`) and `DEFAULT_DB_URI` (`hybrid_retriever.py`) resolve all persistent state (SQLite, LanceDB, `.cache/`) from the repo root, so launch working directory can never redirect or orphan the stores.
- Clear-vs-purge duality — `Clear Session` resets memory only; `Purge All Data` wipes every persistent tier (SQLite `purge_all`, LanceDB `purge_all`, `.cache/` rmtree) plus session state plus cloud posture, confirmed by toast.
- Ingestion-stays-local invariant — extraction (Docling/pypdf/OCR), CPU embeddings, LanceDB/SQLite/`.cache` persistence, and visual analysis NEVER touch the network in either mode; only generation (`provider.stream_text` / `provider.generate_text`) may egress, and only through a consented cloud provider while `cloud_mode=True`.
- Explicit provider selection, no silent fallback — `_detect_provider` (`local_llm.py`) routes purely on `cloud_mode`: `False` → fresh `LlamaCppProvider` unconditionally (no health-probe fallback to cloud); `True` → explicit `cloud_provider` if supplied, else a health-checked `GroqProvider`. Local unhealth never auto-escalates to cloud.
- SSRF-hardened local endpoint — `LlamaCppProvider.__init__` (`llama_cpp_provider.py:40-57`) normalises scheme, accepts `localhost` literally or any `ipaddress.is_loopback` address, and raises `ValueError("Restricted endpoint: ...")` for anything else unless `allow_remote=True` is explicitly passed. The server itself binds `--host 127.0.0.1` (`docs/RUNBOOK.md`). Covered in `tests/test_llama_cpp_provider.py:262-292`.
- Cloud-mode state machine — `local → dialog → consented cloud → revocation`: default `cloud_mode=False, user_consented=False` (100% local); toggling ON opens the consent dialog; consented cloud persists per session via session flags + cached `LiteLLMProvider`; toggle-OFF, `Revoke Consent`, `Clear Session`, or `Purge All Data` resets all three flags `False`, closes/drops the cloud provider, and calls `set_cloud_mode(False)`.
- Programmatic consent enforcement — `LiteLLMProvider._assert_consent` raises `PermissionError("Cloud transmission blocked: ... (INF-04, UI-04).")` at the top of every transmitting method, independent of the UI; `user_consented=False` is the constructor default.
- Egress transparency everywhere — pipeline banner, per-turn live + replay badges (`☁️` vs `🔒`), `is_cloud`/`model_name` persisted per assistant turn, `[En]` source chips + evidence drawer; cloud captions always name the model and cite consent, and always carry the `(Embeddings & LanceDB 100% Local)` qualifier on the banner.
- Truncation transparency — every token-budget clamp in `assemble_grounded_messages` records into `truncation_meta`; `AiModel.last_truncation_warning` surfaces it and the chat UI captions context truncation, so silently dropped evidence is always disclosed.
- Single-active-LLM invariant — every token-producing call (QA stream, `generate_text`, summarizer map/reduce) executes while holding `InferenceGate`; concurrent inference either waits (up to timeout) or yields a busy-retry notice instead of colliding in 4 GB VRAM.
- Shared CPU embedding model — one process-level `SentenceTransformer` (`_MODEL_CACHE` in `local_embedding.py:18-42`) serves all sessions; per-session `LocalEmbedding` objects are thin holders sharing the same weights, eliminating duplicate ~90 MB loads.
- Raster-budget clamps — OCR DPI pinned to 72–300 (`ocr_fallback.py`), visual zoom to 0.5–3.0 with a 2048×2048 pixel cap and `max_regions=20` (`visual_analyzer.py`), bounding worst-case raster/VLM memory per page.
- HybridRetriever-as-sole-index — one `search_hybrid(k=5)` call spans all uploaded documents; `LocalEmbedding` is retained only as the CPU embedding-function provider (`_embed_one`) injected into the retriever, plus a dormant dense-only fallback path.
- One-retrieval-per-question: the UI fetches a single shared `RetrievalResult` and passes the identical object to prompt assembly, generation, validation, and UI citations (RETR-04).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `str` fragments; `st.write_stream` renders incrementally and returns the full string for post-hoc validation.
- Validate-after-stream: citations are checked on the completed string via `AiModel.validate_response` → `validate_citations`; the `CitationVerificationResult` is persisted alongside the turn in `chat_history` and re-rendered on replay.
- TTL-throttled telemetry: `get_gpu_memory_info` caches the last probe for 5.0s with double-checked locking, so per-rerun widget reads cost zero subprocess spawns inside the window; `force_refresh=True` bypasses for profiler/ops use.
- Live-measured VRAM compliance: the profiler seeds its projection from a live `nvidia-smi` sample (690 MB DWM baseline on the RTX 3050) instead of a hardcoded estimate, yielding a measured 3450 MB peak / 646 MB headroom (`.planning/research/RESOURCE_PROFILE.json`).
- Multi-tier cache invalidation: Tier 1 session (`summary_{doc_id}_{profile}` dicts, purged by Clear Session AND Purge All) → Tier 2 disk `.cache/<sha>/<CONFIG_VERSION>/*.json` (best-effort extraction cache, deleted only by Purge All) → Tier 3 SQLite `document_summaries` keyed `(sha256, profile)` with read-time `model_version` invalidation + `force_refresh` bypass (deleted only by Purge All) → Tier 4 LanceDB/`fallback_store.json` vector persistence (dropped/unlinked only by Purge All); telemetry counts surface Tier 3 size.
- Bounded chat memory at two levels: turn-count cap (`MAX_CHAT_TURNS=50` via `bound_chat_history`) and token-budget truncation (oldest-first inside `assemble_grounded_messages` against `context_window - 1024` reserved, now flag-reported).
- Graceful degradation everywhere: Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, nvidia-smi/psutil → `None`/zeros in CI. NOTE: local LLM health degradation does NOT fall back to cloud — the failure surfaces as an offline notice.
- Deterministic deployment: fluid `requirements.txt` for dev flexibility vs frozen `requirements-lock.txt` (uv-synced, ~600 lines, all `==` pins); CI installs from the lockfile and the runbook installs from the lockfile (`docs/RUNBOOK.md`).

## Layers

**Presentation / Orchestration (incl. Privacy & Provider Mode + purge controls):**
- Purpose: File upload, provider-mode + consent UX, session-vs-persistent reset UX, index-status display, tabbed chat + summarizer UX, streamed answer rendering with egress/verification badges and evidence drawers, live VRAM/RAM/cache telemetry.
- Location: `main.py`
- Contains: `st.set_page_config` (first Streamlit call), session-state init loop incl. cloud keys + `ai_model`, `get_session_ai_model` / `load_ai_model` alias (`main.py:92-106`), anchored paths `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR` (`main.py:86-89`), Privacy & Provider Mode block, sidebar upload/index loop (`Clear Session` + `Purge All Data`), telemetry expander, pipeline banner, `append_chat_turn` bounding helper, `st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])`, chat tab, summary tab, truncation caption.
- Depends on: `local_llm.py:AiModel` (+ `set_cloud_mode`), `litellm_provider.py:LiteLLMProvider`, `local_embedding.py:LocalEmbedding`, `hybrid_retriever.py:HybridRetriever`, `docling_reader.py:DoclingReader`, `doc_store.py:DocStore`, `summarizer.py:Summarizer`, `resource_telemetry.py:get_gpu_memory_info/get_process_memory_info`, `prompt_budget.py:bound_chat_history`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion / Extraction (always local, mode-independent, budget-clamped):**
- Purpose: Bytes-in, canonical `Chunk`/`Page` records out, with per-page fault isolation, raster-memory clamps, and zero network egress in both modes.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader.extract_text/get_paragraphs/get_page_records`, `PdfReader.extract_text/get_paragraphs`, `apply_conditional_ocr` (DPI clamped 72–300), `VisualAnalyzer.analyze_visual_elements` (zoom ≤3.0, 2048² px cap, `max_regions=20`, rejects non-local providers), `validate_pdf_bytes`.
- Depends on: `docling`, `pypdf`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `models.py:Chunk/Page`.
- Used by: `main.py` upload path (extraction + OCR + visual analysis with `local_vlm_provider` filter) and `local_llm.py` (on-the-fly fallback path).

**Retrieval (HybridRetriever as sole index, always local):**
- Purpose: Semantic + keyword lookup fused into ranked, provenance-carrying evidence through a single index object; no network in either mode.
- Location: `hybrid_retriever.py`, `local_embedding.py` (shared model + embed-fn only), `vector_index.py` (mirror)
- Contains: `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid/delete_document/purge_all`, `compute_rrf`, `_bm25_search_fallback`, `get_shared_sentence_transformer/clear_shared_model_cache`, `LocalEmbedding._embed_one/get_embeddings`, `VectorIndex.add_vector/add_document/search` plus `_cosine_distance/_euclidean_distance`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding only, process-shared), optional `lancedb` + `pyarrow`; fallback store is stdlib-only.
- Used by: `main.py` (build: CPU `get_embeddings` batch → `index_chunks` with `chunk_id` upsert dedup; query: `search_hybrid(search_query, k=5)`), CR-01 restore path (re-embed persisted chunks → fresh `HybridRetriever`), `local_llm.py` (in-LLM fallback retrieval), `scripts/benchmark_multimodal.py` (isolated `data/lancedb_bench` index + `purge_all` cleanup).

**Inference / Generation (InferenceGate-guarded, mode-switched, loopback-hardened local path):**
- Purpose: Grounded answer synthesis with conversational memory, bounded context, truncation reporting, explicit local/cloud routing, SSRF-safe local transport, and single-active-LLM concurrency safety.
- Location: `local_llm.py:26-90` (gate), `local_llm.py` (`__init__`/`set_cloud_mode`/`_detect_provider`/`check_health` + `last_truncation_warning`), `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py:23-67` (loopback guard), `litellm_provider.py`, `prompt_budget.py` (`assemble_grounded_messages` + `truncation_meta`)
- Contains: `InferenceGate.acquire/release/is_locked/hold`, `AiModel.set_cloud_mode` (idempotent toggle + provider swap + `close()` + re-detect), `AiModel._detect_provider` (cloud_mode branch → explicit/cloud-health-checked provider; local branch → `LlamaCppProvider`), `AiModel.ask_a_question_from_pdf_stream/generate_text/validate_response`, `LiteLLMProvider._assert_consent/set_consent/check_health/get_capabilities/generate_text/stream_text/analyze_image`, `BaseModelProvider.stream_text/generate_text`, `assemble_grounded_messages`, `bound_chat_history`.
- Depends on: `HybridRetriever` / `LocalEmbedding` (retrieval input), `models.py:RetrievalResult` (context input), `citation_validator.py:validate_citations` (post-check), `litellm` package (cloud path only), `httpx` (loopback localhost HTTP only, unless `allow_remote=True`).
- Used by: `main.py` (chat stream), `summarizer.py` (summary map/reduce via gate-held `provider.generate_text`).

**Summarization:**
- Purpose: Bounded, VRAM-safe, profile-shaped document synthesis with `(p. X)` citations and multi-tier caching; generation egress follows the active mode (local vs consented cloud).
- Location: `summarizer.py:301-420`
- Contains: `Summarizer.summarize_document` (profile whitelist → Tier-3 cache check → page resolve/enrich → `InferenceGate.hold(timeout=120.0)` fast/map-reduce → `extract_page_references` → `save_summary`), `_bundle_pages`, `_format_page_batch`, `_summarize_single_pass`, `_summarize_map_reduce`, `extract_page_references`, `PROFILE_SYSTEM_INSTRUCTIONS`, `MAP_PROMPT_TEMPLATE` / `REDUCE_PROMPT_TEMPLATE`, `FAST_PATH_TOKEN_LIMIT = 2500` / `MAX_BATCH_TOKENS = 2000`.
- Depends on: `local_llm.py:InferenceGate`, `model_provider.py:BaseModelProvider` (`generate_text`, `get_capabilities`), `models.py:Page/SummaryResult/VALID_SUMMARY_PROFILES`, `prompt_budget.py:estimate_tokens/sanitize_xml_boundary`, `doc_store.py:DocStore` (Tier-3 cache backend).
- Used by: summary tab generation (`main.py` summary loop).

**Citation Validation:**
- Purpose: Deterministic post-generation grounding gate independent of any LLM or mode.
- Location: `citation_validator.py:52-181`
- Contains: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations`.
- Depends on: `models.py:RetrievalResult` (snippet-count bound only), stdlib `re`, Pydantic v2.
- Used by: `local_llm.py` (`AiModel.validate_response`), exercised in `main.py` chat flow and `scripts/benchmark_multimodal.py:199`.

**Persistence + Telemetry (always local, TTL-throttled probes, full purge):**
- Purpose: Survive restarts (document metadata, chunk text, vectors, evidence elements, summaries, disk cache), wipe completely on demand (purge), and expose live resource pressure (VRAM/RAM/latency) without per-rerun subprocess cost; never egresses.
- Location: `doc_store.py` (+ `purge_all`), `hybrid_retriever.py:purge_all/_save_fallback_store/_load_fallback_store`, `resource_telemetry.py:25-60` (TTL cache), `resource_telemetry.py` (latency registry + snapshot + `clear_gpu_cache`), `.cache/`, `scripts/profile_resources.py`, `main.py:329-378` (purge wiring)
- Contains: `DocStore.upsert_document/record_page/record_chunks/record_evidence_elements/get_chunks_for_doc/save_summary/get_summary/list_summaries_for_doc/delete_summaries_for_doc/delete_document/count_documents/count_summaries/purge_all`, `SCHEMA_V3_DDL` `document_summaries` table (`UNIQUE(sha256, profile)`, FK `doc_id → documents(doc_id) ON DELETE CASCADE`), `MIGRATIONS = {1,2,3}`, LanceDB `chunks` table, `fallback_store.json`, `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`, `_GPU_CACHE_TTL_SECONDS=5.0` + `_GPU_CACHE_LOCK` + `_SAMPLING_LOCK` + `get_gpu_memory_info(force_refresh)` + `clear_gpu_cache`, `get_process_memory_info/get_system_telemetry_snapshot`.
- Depends on: stdlib `sqlite3` (WAL mode), optional `lancedb`, `nvidia-smi` subprocess (TTL-throttled), optional `psutil`.
- Used by: `DOC_STORE_PATH` open (`main.py:86-89`), upload persist block, CR-01 restore after restart, telemetry widget reads (served from TTL cache), summary cache read, `summarizer.py` (summary cache check/save), purge buttons.

**Benchmarks (offline, deterministic + live-capable):**
- Purpose: Prove grounding quality and VRAM safety with repeatable artifacts, without touching production stores.
- Location: `scripts/benchmark_multimodal.py` (292), `scripts/profile_resources.py:94-342` (342), `scripts/benchmark_baseline.py` (174)
- Contains: `DeterministicBenchmarkProvider` + `BENCHMARK_CASES` (5) + `run_benchmark(live_model)` (`benchmark_multimodal.py:88-292`); `BenchmarkProvider` + `run_resource_profile()` 6-stage audit (`profile_resources.py:39-342`).
- Depends on: `citation_validator.py`, `hybrid_retriever.py` (isolated `data/lancedb_bench`), `local_embedding.py`, `local_llm.py:AiModel` (+ `InferenceGate`), `model_provider.py`, `models.py`, `pdf_reader.py`, `resource_telemetry.py`, `doc_store.py`, `summarizer.py`. Never imports `main.py`.
- Used by: Operators/CI via `python scripts/benchmark_multimodal.py [--live]` and `python scripts/profile_resources.py`; outputs `.planning/research/MULTIMODAL_BENCHMARK.json` and `.planning/research/RESOURCE_PROFILE.json`.

**Operations / Runbooks:**
- Purpose: Reproducible install, local-server launch, ingestion/telemetry/cloud/purge procedures, troubleshooting, VRAM budget, and release acceptance metrics — the human-executable counterpart to the architecture.
- Location: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`
- Contains: venv setup + `pip install -r requirements-lock.txt` (deterministic uv-synced pins) + Windows symlink tip; `llama-server` launch (`-m …q4_k_m.gguf --mmproj … -c 4096 -ngl 28 --host 127.0.0.1 --port 8080`) with per-flag breakdown and `curl http://127.0.0.1:8080/health` check; ingestion limits (50 MB / 500 pages / `%PDF` magic); telemetry TTL note; cloud-consent activation steps; purge procedure (Clear Session vs Purge All Data); troubleshooting (unreachable server, CUDA OOM with `-ngl`/`-c` reduction, missing optional deps graceful-degrade, stale `.cache/` purge); live VRAM budget (3450 MB peak / 646 MB headroom on RTX 3050); release metrics record.
- Depends on: Nothing in code — documents reference `llama_cpp_provider.py` defaults, `resource_telemetry.py` TTL, `upload_validation.py` limits, and the lockfile.
- Used by: Operators and release verification; GSD planning reads these as ground truth for launch/limits/budgets.

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted, always local)

1. Upload + validate (sidebar upload block, `main.py`) — single `getvalue()` read per file; `MAX_FILE_MB` pre-check; `validate_pdf_bytes` (`upload_validation.py`) yields `doc_id`/`sha256`/`num_pages`. Limits documented in `docs/RUNBOOK.md` (50 MB / 500 pages / `%PDF` magic).
2. Dedup via `DocStore.get_by_sha` — session `doc_ids` set + SQLite `status == "indexed"` check; CR-01 path restores chunks from `DocStore.get_chunks_for_doc` into fresh `LocalEmbedding` + `HybridRetriever` (re-embed via `get_embeddings`, `index_chunks`) when the session index is empty after restart.
3. Extraction — `DoclingReader.extract_text` → `get_paragraphs`/`get_page_records`; `apply_conditional_ocr` patches scanned pages (DPI clamped 72–300, `ocr_fallback.py`); `VisualAnalyzer.analyze_visual_elements` runs with the `local_vlm_provider` filter (passes the active provider ONLY when `get_capabilities().is_local`, else `None`, and the analyzer itself rejects cloud providers), capped at `max_regions=20` with zoom ≤3.0 and a 2048×2048 pixel budget, and records elements; per-page `record_page` with `st.progress`; failed pages warn and continue. No branch transmits bytes off-device.
4. Sole-index build (`main.py`) — `LocalEmbedding.get_embeddings([p["content"] ...])` batch on the process-shared CPU model, then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` which writes BOTH the persistent LanceDB table (or `fallback_store.json`) and the in-memory `VectorIndex` mirror with `chunk_id` upsert dedup. `LocalEmbedding.build_index`/`store` is NOT written on this path — the embedding object serves only as the `_embed_one` function provider. All stores are on-disk/in-process under anchored paths.
5. Persist — `Chunk.model_validate` → `record_chunks`; `Document` → `upsert_document`; best-effort `.cache/<sha>/docling-1000-200-v1/*.json` write; session-state update + `st.rerun()`.

### Persistent Purge Flow (Purge All Data vs Clear Session)

1. Two-button contract (`main.py:297-378`) — `Clear Session` resets memory only (doc ids, index handles with retriever `close()`, chat, `summary_*` keys, cloud posture + credential cleanse) and reruns; `Purge All Data` additionally destroys every persistent tier before the same session reset, then toasts and reruns.
2. SQLite wipe (`doc_store.py:purge_all`) — single transaction deleting `chunks`, `pages`, `evidence_elements`, `document_summaries`, then `documents`; committed atomically. `delete_document(doc_id)` is the surgical sibling: explicit per-table deletes (chunks/pages/evidence/summaries/documents) with a `TypeError` guard on non-string `doc_id` (`doc_store.py`).
3. Vector wipe (`hybrid_retriever.py:purge_all`) — with LanceDB: drop the `chunks` table (warn-and-continue on error) and null the handle; always: replace `_fallback_store` with a fresh `VectorIndex` and unlink `fallback_store.json` (`missing_ok=True`, `OSError` warn-and-continue). The purge button calls `purge_all()` + `close()` on the session retriever, or builds a temp `HybridRetriever()` (anchored default URI) purely to purge + close when no session retriever exists.
4. Disk-cache wipe (`main.py:345-351`) — `shutil.rmtree(CACHE_DIR, ignore_errors=True)` under `CACHE_DIR.exists()`, failures logged via `logger.warning`, never fatal.
5. Session + cloud reset (shared with Clear Session) — reset `doc_ids`/`indexed_files`/`document_metadata`/`local_embedding`/`hybrid_retriever`/`chat_history`, delete every `summary_*` key, `close()` the cached cloud provider, clear `_cached_cloud_model/_key`, reset `cloud_mode`/`cloud_mode_toggle`/`user_consented`/`cloud_api_keys`/legacy key.
6. Tests: `tests/test_doc_store.py::test_purge_all_empties_all_tables` + `test_delete_document_cascades_all_tables` (incl. summaries), `tests/test_hybrid_retriever.py::test_hybrid_retriever_purge_all` (mirror empty + fallback file unlinked), `tests/test_cache_invalidation.py::test_tier_1_session_purge` (Tier-1 key purge shape).

### Cloud-Mode State Machine (local → dialog → consented cloud → revocation)

1. Default local — session keys initialise to `cloud_mode=False`, `cloud_mode_toggle=False`, `user_consented=False`, `cloud_provider="groq"`, `cloud_model="groq/llama-3.3-70b-versatile"`, `cloud_api_keys={"groq":"","openai":"","anthropic":""}`; `get_session_ai_model()` constructs `AiModel()` with `cloud_mode=False` so `_detect_provider` returns a local `LlamaCppProvider` with zero egress. Each browser session gets its own `AiModel`.
2. Toggle ON → consent dialog — `st.toggle("Enable Cloud Inference", key="cloud_mode_toggle")`; when the widget value is `True` while `user_consented` is still `False`, `show_consent_dialog()` renders (`@st.dialog("Cloud Inference & Data Privacy Consent")` when available, else inline). The dialog warns that query prompts + retrieved excerpts will egress, enumerates what stays on-device (PDF bytes, extracted text/OCR, MiniLM embeddings, LanceDB + SQLite), and offers `I Consent & Enable Cloud` (sets `user_consented=True`, `cloud_mode=True`, `cloud_mode_toggle=True` + `st.rerun()`) vs `Cancel (Keep 100% Local)` (all three `False` + `st.rerun()`).
3. Consented cloud active — sidebar shows `☁️ Cloud Mode Active (Egress permitted with user consent)`; provider selectbox over `CLOUD_PROVIDER_OPTIONS`; per-provider session API key `st.text_input(type="password")` kept in `st.session_state.cloud_api_keys` (memory only); a cached `LiteLLMProvider(model_name=cloud_model, api_key=active_key or None, user_consented=True)` is built once per `(model, key)` pair and bound via `ai_model.set_cloud_mode(True, cloud_provider=cached_prov)` on the SESSION's `AiModel`, which closes the old provider and re-runs `_detect_provider`.
4. Provider-level consent gate (`litellm_provider.py`) — even if the UI wiring is bypassed, `generate_text`/`stream_text`/`analyze_image` each call `_assert_consent()` first and raise `PermissionError("Cloud transmission blocked: ... (INF-04, UI-04).")` when `user_consented` is `False` (the constructor default). `set_consent(bool)` flips the flag post-construction.
5. Revocation (four equivalent paths, all converge) — (a) toggle OFF → all three flags `False` + `st.rerun()`; (b) `Revoke Consent (Switch to Local)` button → all three flags `False` + `st.rerun()`; (c) `Clear Session` → same reset plus session-state wipe; (d) `Purge All Data` → same plus persistent wipe. `AiModel.set_cloud_mode(False)` (idempotent WR-02 fast path) sets `cloud_mode=False`, `close()`s the old provider, and `_detect_provider()` returns a fresh local `LlamaCppProvider`. The UI else-branch additionally `close()`s and clears the cached cloud provider so no consented client lingers in session state.

### Provider Selection — `_detect_provider` (explicit, no silent fallback)

1. Contract (`local_llm.py`) — selection is a pure function of `(cloud_mode, cloud_provider)`; there is no health-triggered cross-boundary fallback.
2. `cloud_mode=True` branch — return the injected `cloud_provider` when present; otherwise construct `GroqProvider()`, return it iff `check_health().status == "healthy"`, else `close()` it and fall through. No local construction happens on this branch.
3. `cloud_mode=False` branch — unconditionally `return LlamaCppProvider()` without probing cloud health or credentials. A dead local server therefore surfaces as an offline/unhealthy status in the sidebar badge, never as an automatic cloud escalation.
4. `check_health` re-probe stays within the same mode — it re-runs `_detect_provider()` (same `cloud_mode`) and swaps only when the same-mode re-probe is healthy.
5. Idempotent switching — `set_cloud_mode` returns early when `(mode, provider)` are unchanged (local+local, or cloud+identical provider object), avoiding `close()`/re-detection churn (WR-02); otherwise it sets the flag, stores an injected `cloud_provider`, `close()`s the old provider, and re-detects + refreshes `model_name`.

### Local Endpoint Guard — loopback SSRF protection (SEC-01)

1. Guard location (`llama_cpp_provider.py:40-57`) — every `LlamaCppProvider` construction (default `http://127.0.0.1:8080`, plus any injected `base_url`) passes scheme normalisation → `urlparse` hostname extraction → `localhost`-literal or `ipaddress.is_loopback` check → `ValueError` unless `allow_remote=True`.
2. Accepted by default: `127.0.0.1`, any `127.0.0.0/8` address (`127.0.1.1`, `127.0.0.2`), `localhost`, `::1`, scheme-less `127.0.0.1:8080` (normalised to `http://` before parsing). Rejected by default: any non-loopback hostname/IP (public IPs, LAN hosts, DNS names that are not `localhost`).
3. Opt-in escape hatch: `allow_remote=True` permits remote hosts for explicitly configured remote-server deployments; no production or UI path passes it today — all `_detect_provider` constructions use the loopback default.
4. Server-side complement: `llama-server` binds `--host 127.0.0.1` (`docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md` flags), so even a misconfigured client cannot reach an externally bound server that does not exist.
5. Tests: `tests/test_llama_cpp_provider.py:262-292` — rejected non-loopback, allowed-with-flag, accepted loopback variants.

### Egress Transparency (badges / chips / banner)

1. Pipeline banner (`main.py`) — `caps.is_local` (`ProviderCapabilities.is_local`, `model_provider.py`) selects `🔒 100% Offline Local Pipeline · Qwen3-VL ({model}) + MiniLM-L6-v2 + LanceDB` vs `☁️ Cloud Inference · {model} (Embeddings & LanceDB 100% Local)`; the cloud variant always carries the stays-local qualifier.
2. Live per-answer badge (`main.py`) — immediately after `st.write_stream`, `caps.is_local` selects `🔒 Generated locally on-device (zero network egress).` vs `☁️ Generated via external cloud provider ({caps.model_name}) with user consent.`
3. Replay badges (`main.py`) — persisted `is_cloud`/`model_name` per assistant turn re-render the same two captions on every rerun; `is_cloud is False` → local caption, truthy → cloud caption naming the stored model.
4. Turn persistence (`main.py`) — every assistant turn stores `is_cloud: not caps.is_local` + `model_name: caps.model_name` alongside `sources`/`verification`/`snippets` (both success and interruption paths), so replay never re-derives locality from the CURRENT mode or session.
5. Evidence chips + drawer (`main.py`) — `**Sources:** [E{rank}] {filename} (p. {page}), ...` caption plus `🔍 Cited Evidence & Source Context` expander iterating `snippets_data` with `[E{rank}] filename (p. N, score)` headers, quoted content, and optional `📐 Region` bbox caption. Provenance rendering is identical in both modes.
6. Model badge (`main.py`) — `st.status` label shows `🟢 Inference: Local ({model})` vs `☁️ Inference: Cloud ({model})`, so the active egress posture is visible before any question is asked.
7. Truncation caption (`main.py:804-807`) — when `ai_model.last_truncation_warning["context_truncated"]` is set, a `ℹ️ Retrieved evidence context was truncated to fit the active model's token context budget.` caption renders under the evidence drawer.

### InferenceGate Single-Active-LLM Flow (concurrency control)

1. Gate primitive (`local_llm.py:26-90`) — class-level `threading.RLock` (`_lock`) + `_active_threads` counter under `_state_lock`. `acquire(timeout)` blocks on the RLock then increments; `release()` releases and decrements (swallows stray `RuntimeError`); `is_locked()` reads the counter; `hold(timeout)` context manager raises `TimeoutError("InferenceGate acquisition timed out after ...")` on failure and always releases.
2. QA streaming path (`local_llm.py`) — after prompt assembly, `ask_a_question_from_pdf_stream` calls `InferenceGate.acquire(timeout=60.0)`; on failure it yields `"⚠️ System is busy processing another inference request. Please retry in a moment."` and returns WITHOUT calling the provider; on success it `yield from provider.stream_text(...)` inside `try/finally: InferenceGate.release()`. The provider here is whichever `_detect_provider` selected — gate semantics are mode-independent.
3. Non-streaming path (`local_llm.py`) — `AiModel.generate_text(..., timeout=60.0)` wraps `provider.generate_text` in `with InferenceGate.hold(timeout=timeout)`, so contention raises `TimeoutError` to the caller.
4. Summarization path (`summarizer.py`) — `summarize_document` wraps the entire fast-path-or-map-reduce generation block in `with InferenceGate.hold(timeout=120.0)` (longer timeout for multi-call map-reduce); every `provider.generate_text` inside map/consolidate/reduce therefore executes under the same single-active-LLM lock, strictly sequentially.
5. Reentrancy note — because the underlying lock is an RLock, nested `hold` on the SAME thread re-enters (covered in `tests/test_concurrency_lock.py`); cross-thread contention blocks to timeout. The busy-yield (stream) vs raise (non-stream) asymmetry is intentional: interactive chat degrades to a retry notice, programmatic callers get an exception.

### Telemetry Pipeline (TTL-cached probes → sidebar widget → profiler artifact)

1. TTL cache (`resource_telemetry.py:25-30`) — `_GPU_CACHE_TTL_SECONDS = 5.0`, `_LAST_GPU_INFO`, `_LAST_GPU_SAMPLE_TIME` (monotonic), `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`.
2. GPU probe (`resource_telemetry.py:33-95`) — `get_gpu_memory_info(force_refresh=False)`: fast path returns the cached dict copy when `(now - _LAST_GPU_SAMPLE_TIME) < TTL`; on expiry, takes `_SAMPLING_LOCK` and double-checks the timestamp before spawning `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits` (`timeout=2.0`), parses the first line into `{total_mb, used_mb, free_mb, utilization_pct}`; returns `None` on `FileNotFoundError`/`SubprocessError`/`ValueError`/`IndexError` (headless/CI) with a `logger.debug`. Concurrent reruns inside one TTL window therefore spawn zero subprocesses; concurrent expiry spawns exactly one.
3. Process probe (`resource_telemetry.py`) — `get_process_memory_info` reads `psutil.Process().memory_info()` into `{rss_mb, vms_mb}`; returns zeros on missing `psutil` or any error.
4. Latency registry (`resource_telemetry.py`) — `LatencyTracker(stage_name)` context manager times with `perf_counter`, records `elapsed_ms`/`success`/`error` into thread-safe `_LATENCY_HISTORY` capped at `MAX_STAGE_HISTORY=200`; `track_stage`/`record_stage_latency` are convenience wrappers; `get_latency_history`/`clear_latency_history` copy/clear under `_LATENCY_LOCK`; `get_system_telemetry_snapshot` aggregates per-stage `{count, avg_ms, min_ms, max_ms}` with an ISO timestamp. `clear_gpu_cache()` resets the TTL state for tests/ops.
5. Live widget (`main.py`) — sidebar `with st.expander("📊 System Telemetry & VRAM")` calls both probes + `doc_store.count_documents()`/`count_summaries()` every rerun; GPU reads hit the TTL cache, so chat keystrokes no longer fork `nvidia-smi` per rerun. GPU present → `st.metric("GPU VRAM", ...)` + `st.progress(used/total)` + tiered caption (🟢 `<3500` / 🟡 `3500–3800` / 🔴 `>3800`); GPU absent → `ℹ️ CPU-only Mode` caption; always shows `Process RAM (RSS)` caption and `Persistent Cache: {docs} docs · {sums} summaries` caption.
6. Offline profiler with live VRAM seed (`scripts/profile_resources.py:94-342`) — `run_resource_profile()` executes 6 stages against `tests/data/corpus/` and writes `.planning/research/RESOURCE_PROFILE.json`. Stage 6 seeds the projection from the LIVE `get_gpu_memory_info()` sample (`initial_gpu_mem["used_mb"]` = 690 MB DWM baseline on the RTX 3050; 487 MB empirical fallback only when `nvidia-smi` is absent) plus fixed model weights 1450 + mmproj 450 + KV-4K 510 + CUDA scratch 350 → projected peak **3450.0 MB** vs 3800 MB target → **646.0 MB headroom** (`compliant_with_qual_01: true`). Measured latencies: ~3–7 ms/page ingestion, ~27 ms/chunk CPU embeddings, ~16–17 ms hybrid queries, 28.7 ms cold / 3.1 ms warm summary (cache SLA met).
7. Tests: `tests/test_resource_telemetry.py:49-70` — TTL caching (second call within window returns cached copy without re-spawning subprocess), `force_refresh` bypass, subprocess fallbacks.

### Multimodal Benchmark Harness (accuracy + grounding audit)

1. Provider selection (`scripts/benchmark_multimodal.py:132-158`) — default `DeterministicBenchmarkProvider` (keyword-shaped canned answers per query class, `is_local=True`, vision-capable); `--live` flag swaps in a health-checked resident `LlamaCppProvider`, falling back to deterministic with a warning when the server is unreachable. `is_live_server` is recorded in the artifact.
2. Isolated indexing (`scripts/benchmark_multimodal.py:159-176`) — `LocalEmbedding()` + `HybridRetriever(db_uri=<repo>/data/lancedb_bench)`; `purge_all()` before indexing; `dense_table.pdf` + `chart_diagram.pdf` + `clean_digital.pdf` chunked via `PdfReader`, embedded, tagged `filename`/`doc_id`, indexed with per-file chunk counts logged.
3. Case execution (`scripts/benchmark_multimodal.py:181-236`) — 5 `BENCHMARK_CASES`: `table_q1_lookup` (Q1 revenue $124.5M + 68.2% margin), `table_fy_total` (FY $630.9M + $203.8k compute), `visual_diagram_steps` (Ingestion → Hybrid Search → Local VLM), `digital_claim_lookup` (10 ms latency claim), `absent_abstention_check` (turnover/CEO bonus → must abstain). Each case: `search_hybrid(query, k=3)` → stream through `AiModel.ask_a_question_from_pdf_stream` → `validate_citations` → keyword-accuracy + abstention-match check → `PASS`/`FAIL (reason)` verdict with latency, precision, hallucinated ranks.
4. Aggregation + artifact (`scripts/benchmark_multimodal.py:238-287`) — `factual_accuracy_pct` (table+text keyword hits), `visual_accuracy_pct`, `abstention_quality_pct`, `citation_precision_pct` (mean precision ×100), `average_latency_seconds`; written to `.planning/research/MULTIMODAL_BENCHMARK.json`. Recorded result: **100.0 / 100.0 / 100.0 / 100.0**, 0.087s avg latency, 5/5 PASS. Cleanup: `retriever.purge_all()` + `close()` so the temp `lancedb_bench` store never leaks into production.
5. Entry: `python scripts/benchmark_multimodal.py [--live]` (`benchmark_multimodal.py:290-292`).

### Multi-Tier Cache Invalidation

1. Tier 1 — session (`main.py` summary tab + Clear Session + Purge All) — `st.session_state[f"summary_{doc_id}_{profile}"] = summary_obj.model_dump()` on generate; read-first on display; both reset buttons delete every `summary_*` key plus reset `doc_ids`/`indexed_files`/`document_metadata`/`local_embedding`/`hybrid_retriever`/`chat_history`.
2. Tier 2 — disk extraction cache (upload persist block) — best-effort `.cache/<sha256>/docling-1000-200-v1/{pages,chunks,manifest}.json` write per upload (`STORE-03`); `OSError` → `st.warning`, never fatal; keyed by SHA-256 + `CONFIG_VERSION`, so chunking/config changes naturally miss. Wiped ONLY by Purge All Data (`shutil.rmtree(CACHE_DIR)`).
3. Tier 3 — SQLite summary cache (`summarizer.py`, `doc_store.py`) — `summarize_document` returns `DocStore.get_summary(sha256, profile, model_version=provider.model_name)` immediately on hit (zero provider calls, zero gate acquisition) unless `force_refresh=True`; key is `(sha256, profile)` (`UNIQUE` in `doc_store.py`); `model_version` is a read-time invalidation predicate (returns `None` on mismatch → regenerate + `ON CONFLICT(sha256, profile) DO UPDATE` upsert in `save_summary`); `list_summaries_for_doc`/`delete_summaries_for_doc` scope by `doc_id`; `delete_document` cascades via FK + explicit deletes. Wiped ONLY by Purge All Data (`purge_all`).
4. Tier 4 — vector persistence (`hybrid_retriever.py`) — LanceDB `chunks` table when available (upsert via `merge_insert` on `chunk_id`); otherwise `fallback_store.json` under `data/lancedb/` rewritten on `close()` and reloaded in `_load_fallback_store`; `delete_document(doc_id)` evicts from both mirror and table; `purge_all()` drops/unlinks both. Untouched by Clear Session (which only `close()`s the handle).
5. Telemetry GPU TTL as a fifth, time-based tier — `resource_telemetry.py:25-60` (5.0s monotonic window, double-checked sampling, `force_refresh` bypass, `clear_gpu_cache` reset); covered in `tests/test_resource_telemetry.py:49-70`.
6. Shared embedding weights as a sixth, process-lifetime tier — `_MODEL_CACHE` in `local_embedding.py:18-42` (keyed `(model_name, device)`, cleared only via `clear_shared_model_cache()`); survives both reset buttons by design.

### Grounded QA Flow (question → gated stream → validated citations → badges/drawer)

1. Bounded history + contextualized query (`main.py`) — new user turn appended via `append_chat_turn` (turn-cap enforced immediately); `history_to_pass = chat_history[:-1][-10:]`; `search_query = last_user_msg + " " + prompt` so follow-ups retrieve correctly. The SESSION's `AiModel` (`get_session_ai_model()`) owns routing.
2. Single shared retrieval (`main.py`, always local) — `active_retriever = hybrid_retriever or local_embedding`; if it exposes `search_hybrid`, one call `search_hybrid(search_query, k=5)` returns the canonical `RetrievalResult`; `sources = retrieval_res.source_labels()` plus `snippets_data = [s.model_dump() for s in retrieval_res.snippets]`. Legacy `search(k=10)` branch only applies to retrievers without `search_hybrid`.
3. Hybrid fusion inside `HybridRetriever.search_hybrid` (`hybrid_retriever.py`) — embed query via shared CPU embedding fn → `search_dense` (LanceDB vector search, `candidate_pool = max(k*2, 10)`) + `search_fts` (LanceDB FTS → pure-Python BM25 fallback) → `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k mapped to `EvidenceSnippet` items (with `rank`, `dense_rank`, `fts_rank`, `score=RRF`, `bbox` rehydrated from `bbox_json`) → frozen `RetrievalResult(query, snippets, total_candidates, search_mode)`.
4. Shared-identity gated generation (`main.py` → `local_llm.py`) — the same `retrieval_result` object is passed to `ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_res)`; the LLM uses `retrieval_result.formatted_evidence()` (`[E1] (file, p. N)` blocks) directly under `InferenceGate.acquire(60s)`; the in-LLM fallback only runs when no pre-computed result is supplied. Generation egresses ONLY when the session's active provider is a consented cloud provider; the local path speaks loopback HTTP guarded by the SEC-01 constructor check.
5. Bounded grounded prompt + stream (`local_llm.py` + `prompt_budget.py`) — `assemble_grounded_messages` wraps context in `<document_context>` with the `[E1]`/`[E2]` citation rules and abstention sentence, XML sanitization and token budgeting against the provider's `context_window` (local 4K default vs cloud 128K–200K per `KNOWN_CONTEXT_WINDOWS`), recording every clamp into `truncation_meta` (= `ai_model.last_truncation_warning`); `provider.stream_text(...)` yields tokens; `st.write_stream` renders and returns the full string.
6. Citation validation (`main.py` → `local_llm.py` → `citation_validator.py`) — `ai_model.validate_response(full_response, retrieval_res)` resolves the active result (explicit arg wins, else `last_retrieval_result`), runs `validate_citations`: empty text → `is_valid=False, precision=0.0`; abstention text + zero citations → `is_valid=True, precision=1.0, abstention_detected=True`; abstention + citations → invalid; otherwise precision = `valid_ranks / total_claimed` with `is_valid = precision >= 0.95` against `len(retrieval_result.snippets)` as the rank bound.
7. Badge + drawer + truncation render (`main.py`, replay + live) — egress badge first (`☁️` vs `🔒`), then abstention (`ℹ️ Explicit abstention`) / valid (`✅ Verified Grounding (P% citation precision)`) / invalid (`⚠️ Unverified Citations (P%)`). Evidence chips `[E{rank}] filename (p. N)` plus `🔍 Cited Evidence & Source Context` expander iterate `snippets_data`. Context-truncation caption when flagged. The turn is appended via `append_chat_turn` (re-bounding to 50, persisting `is_cloud` + `model_name`); the exception path records an interruption note with `verification: None`.

### Summarization Flow (profile → gated map-reduce → cache → summary tab)

1. Tab wiring + selection (summary tab, `main.py`) — `tab_summary` shows selectbox over `sorted(indexed_files)`, resolves `doc_id`/`sha256` from `document_metadata` with `doc_store.get_document` fallback, radio over the five `profile_map` keys, `Generate Summary` button (disabled when inference unhealthy) + `Force re-generate` checkbox. Per-doc/profile session key `summary_{doc_id}_{profile}`.
2. Tier-3 cache check (`summarizer.py`) — `summarize_document(doc_id, sha256, profile, force_refresh)` validates `profile ∈ VALID_SUMMARY_PROFILES`, reads `provider.get_capabilities().model_name` as `model_version`, and returns `DocStore.get_summary(sha256, profile, model_version=model_version)` immediately on hit (zero provider calls, zero gate acquisition). A model switch (local ↔ cloud) therefore invalidates cached summaries via `model_version` mismatch.
3. Page resolution (`summarizer.py`) — if `pages is None`, reconstructs `Page` records from `chunks` arg or `doc_store.get_chunks_for_doc(doc_id)` grouped by page; if caller-supplied `Page` records lack `page_text`, enriches from stored chunks. Filters to pages with non-blank `page_text`; raises `ValueError` when none is extractable.
4. Fast path vs map-reduce under gate (`summarizer.py`) — `total_tokens = Σ estimate_tokens(page_text)`; `≤ FAST_PATH_TOKEN_LIMIT (2500)` → `_summarize_single_pass`; above → `_summarize_map_reduce`; the dispatch executes inside `with InferenceGate.hold(timeout=120.0)`.
5. Map stage — `_bundle_pages(pages, MAX_BATCH_TOKENS=2000)` packs sequential pages by `estimate_tokens`; each batch is rendered as `--- Page N ---` sections with `sanitize_xml_boundary` and sent through `MAP_PROMPT_TEMPLATE` (page-range + `(p. X)` citation mandate) with `max_tokens=800, temperature=0.2`. Executes strictly sequential to respect the single-active-LLM constraint.
6. Consolidation + reduce — intermediates joined with `\n\n---\n\n`; if combined tokens exceed `FAST_PATH_TOKEN_LIMIT` and there are >3 intermediates, two half-consolidation `generate_text` calls (`max_tokens=1000`) precede the final `REDUCE_PROMPT_TEMPLATE` synthesis under the profile system prompt (`max_tokens=1500, temperature=0.2`).
7. Reference extraction + persist (`summarizer.py`) — `extract_page_references(summary_text, max_page=...)` parses `(p. N)`/`(Page N)` via regex, dedups, sorts, clamps; builds `SummaryResult(summary_id=summ_*, ..., cached=False)`; `doc_store.save_summary(result)` upserts on `ON CONFLICT(sha256, profile)`.
8. Display — prefers the session value, falls back to `doc_store.get_summary(selected_sha, selected_profile)` without model-version pin; cached rows show `⚡ Loaded from persistent SQLite cache (DocStore v3)`, fresh ones `✨ Generated fresh with {model_version}`; summary markdown renders verbatim, then `📄 Referenced Source Pages` expander lists `Page N` chips + `created_at`.

**State Management:**
- `st.session_state` (per-browser-session, survives full-script reruns): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict` (filename → `doc_id`/`sha256`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None` (thin holder over the process-shared model), `hybrid_retriever: HybridRetriever | None` (sole retrieval index), `ai_model: AiModel` (session-scoped inference router + consent mirror, created by `get_session_ai_model`), `chat_history: list` of `{role, content, sources, verification, snippets, is_cloud, model_name}` capped at `MAX_CHAT_TURNS=50` — initialised in the `main.py` key/default loop; cloud keys `cloud_mode` / `cloud_mode_toggle` / `user_consented` / `cloud_provider` / `cloud_model` / `cloud_api_keys` / `cloud_api_key`; cached cloud client `active_cloud_provider` + `_cached_cloud_model` / `_cached_cloud_key`; plus dynamic `summary_{doc_id}_{profile}` keys. `Clear Session` closes the retriever, resets index/chat keys, deletes every `summary_*` key, revokes cloud posture, and calls `st.rerun()`; `Purge All Data` does all of that PLUS the persistent wipe.
- No `st.cache_resource` singletons for inference — the audit commit replaced the process-shared `load_ai_model()` singleton with per-session `get_session_ai_model()` (`main.py:92-106`), so `AiModel.cloud_mode`/`cloud_provider` on one session can never steer another session's generation. (`load_ai_model` remains as an alias for backwards compatibility.)
- Process-shared state (intentional, minimal): the `_MODEL_CACHE` SentenceTransformer weights (`local_embedding.py:18-42`, shared read-only after init, resettable via `clear_shared_model_cache()`); `InferenceGate._lock/_active_threads` (`local_llm.py`); the telemetry TTL cache (`_LAST_GPU_INFO`/`_LAST_GPU_SAMPLE_TIME`, resettable via `clear_gpu_cache()`).
- `AiModel` routing state: `cloud_mode: bool` + `cloud_provider: BaseModelProvider | None` + `provider: BaseModelProvider` (the resolved active provider) + `model_name`; transient grounding state `last_retrieval_result` (set on every `ask_a_question_from_pdf_stream`) and `last_verification_result` (set on every `validate_response`) plus `last_truncation_warning` (`{"prompt_truncated","context_truncated","history_truncated"}`, rewritten per call via `truncation_meta`). Always pass an explicit `retrieval_result` to `validate_response` — the `last_*` fields are session-local now, but explicit args remain the documented precedence.
- `LiteLLMProvider` consent state: `user_consented: bool` (constructor default `False`, flipped via `set_consent`) + resolved `api_key` + `model_name`/`timeout`/`num_retries` (`litellm_provider.py`); stateless otherwise (`close()` is a no-op).
- `LlamaCppProvider` endpoint state: `base_url` (loopback-validated at construction) + `allow_remote` flag; `httpx.Client` with `connect=2.0/read=60.0/write=10.0/pool=5.0` timeouts.
- On-disk state (all under anchored paths): SQLite `data/documents.db` (DocStore incl. `document_summaries`), LanceDB `data/lancedb/` (or `fallback_store.json` there without LanceDB), `.cache/<sha256>/docling-1000-200-v1/`.

## Key Abstractions

**Chunk (unit of retrieval):**
- Purpose: Text plus provenance metadata threaded through every layer.
- Examples: produced in `docling_reader.py` / `pdf_reader.py`, validated as `models.py:Chunk`, stored in LanceDB rows and mirrored in `vector_index.py`, restored from `doc_store.py`.
- Pattern: Frozen Pydantic model — `content`, `filename`, `page`, `chunk_id`, `doc_id` required; `char_start`/`char_end`/`bbox`/`extraction`/`embedding_model` optional. `Chunk.chunk_id` is the LanceDB upsert key.

**RetrievalResult + EvidenceSnippet (shared prompt/UI/validation contract, RETR-04):**
- Purpose: Single immutable container consumed identically by LLM prompt assembly, UI citation rendering, and citation validation — eliminates double retrieval and prompt/citation/validation drift. Built entirely on the local path in both modes.
- Examples: constructed in `hybrid_retriever.py` and `local_embedding.py`; consumed in `local_llm.py` (`formatted_evidence`), `main.py` (`source_labels`, `model_dump` snippets), `citation_validator.py` (rank bound), `scripts/benchmark_multimodal.py:190-199`.
- Pattern: Frozen Pydantic models. `EvidenceSnippet` carries `content/doc_id/filename/page/chunk_id/score/rank/dense_rank/fts_rank/extraction/char_start/char_end/bbox` (`models.py`). `RetrievalResult` carries `query/snippets/total_candidates/search_mode ∈ {hybrid, dense, fts, fallback}` with `formatted_evidence()` (`[E1] (name, p. N)` blocks) and `source_labels()` (deduped `filename (p. N)` chips).

**Cloud-mode triple (session flags + session AiModel routing + provider consent):**
- Purpose: Separate the three layers of the egress decision so UI state, routing state, and transmission enforcement can each be reasoned about and tested independently — all three now scoped to the session.
- Examples: flags + toggle/dialog/select/revoke in `main.py`; routing in `local_llm.py` (`set_cloud_mode`, `_detect_provider`) on the session's `AiModel`; enforcement in `litellm_provider.py` (`set_consent`, `_assert_consent`); covered in `tests/test_cloud_privacy.py` and `tests/test_litellm_provider.py`.
- Pattern: UI owns `cloud_mode`/`user_consented` booleans; the session `AiModel` owns `cloud_mode` + provider pointer and NEVER transmits itself; `LiteLLMProvider` owns `user_consented` and refuses to transmit without it. All three must agree for egress; any layer can veto.

**Session-scoped AiModel (P1 audit fix):**
- Purpose: Eliminate cross-session routing contamination — one user's cloud opt-in must never steer another session's generation.
- Examples: `get_session_ai_model()` (`main.py:92-106`); per-turn `is_cloud`/`model_name` persistence remains the replay source of truth.
- Pattern: Lazy per-session construction in `st.session_state.ai_model`; never `@st.cache_resource` for inference routing. New routing inputs must flow through `set_cloud_mode` args on the session instance, never by mutating a shared singleton (there is none anymore).

**Shared SentenceTransformer (P1 audit fix):**
- Purpose: Load the ~90 MB MiniLM weights once per server process instead of once per browser session.
- Examples: `get_shared_sentence_transformer` / `clear_shared_model_cache` / `_MODEL_CACHE` (`local_embedding.py:18-42`); covered in `tests/test_local_embedding.py`.
- Pattern: Module-level dict keyed `(model_name, device)`; `LocalEmbedding.__init__` is a thin holder. New embedding model ids automatically get their own cache slot; tests clear via `clear_shared_model_cache()`.

**Truncation-meta reporting:**
- Purpose: Make token-budget clamps observable instead of silent — dropped evidence is always disclosed in the UI.
- Examples: `truncation_meta` param (`prompt_budget.py`), `AiModel.last_truncation_warning` (`local_llm.py`), caption (`main.py:804-807`); covered in `tests/test_prompt_budget.py`.
- Pattern: Caller-owned dict, callee-reset per call (`False/False/False` then set on clamp). New budget clamps must set their flag; new consumers read `ai_model.last_truncation_warning`.

**Anchored storage paths (P1 audit fix):**
- Purpose: Make persistent-store locations independent of the process working directory.
- Examples: `APP_DIR`/`DOC_STORE_PATH`/`CACHE_DIR` (`main.py:86-89`), `DEFAULT_DB_URI` (`hybrid_retriever.py`), `REPO_ROOT` constants in both `scripts/*.py`.
- Pattern: `Path(__file__).resolve().parent`-anchored constants at module top; every open/connect/rmtree goes through them. New persistent files must add an anchored constant, never a bare relative path.

**Purge duality (Clear Session vs Purge All Data):**
- Purpose: Separate "forget this browser session" from "destroy all persistent evidence" so operators cannot wipe the database by accident and users are never stuck with stale persistent rows.
- Examples: `main.py:297-378`, `doc_store.py:purge_all`, `hybrid_retriever.py:purge_all`; covered in `tests/test_doc_store.py`, `tests/test_hybrid_retriever.py`, `tests/test_cache_invalidation.py`, `tests/test_main_ui.py`.
- Pattern: Memory reset is a strict subset of purge (purge = persistent wipe + memory reset + cloud revocation + toast). New persistent tiers must be added to the Purge All handler AND get a `purge_*`/`delete_*` method with a test.

**Loopback-guarded endpoint (SSRF boundary, SEC-01):**
- Purpose: Make the local inference transport incapable of becoming an SSRF primitive even if a future caller passes an attacker-influenced `base_url`.
- Examples: guard in `llama_cpp_provider.py:40-57`; server bind `--host 127.0.0.1` in `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`; tests in `tests/test_llama_cpp_provider.py:262-292`.
- Pattern: Constructor-time validation with explicit opt-in (`allow_remote=True`) — deny-by-default, not audit-after-the-fact.

**InferenceGate (single-active-LLM lock):**
- Purpose: Enforce the 4 GB VRAM invariant (only one LLM/VLM resident operation at a time) across QA streaming, direct generation, and summarization without a central scheduler. Mode-independent.
- Examples: acquired in stream path, held in `generate_text`, held in `summarizer.py` (120s timeout); verified in `tests/test_concurrency_lock.py` and `scripts/profile_resources.py`.
- Pattern: Class-level `threading.RLock` + counter with `acquire(timeout)/release/is_locked/hold(timeout)` API; stream path degrades to a busy-retry yield, non-stream paths raise `TimeoutError`.

**TTL-cached telemetry snapshot (VRAM/RAM/latency contract, TEL-01):**
- Purpose: One call capturing everything the widget and profiler need without importing Streamlit and without forking `nvidia-smi` per rerun.
- Examples: produced in `resource_telemetry.py`, consumed live in `main.py` widget, aggregated to JSON in `scripts/profile_resources.py:289-331`, documented in `docs/RUNBOOK.md`.
- Pattern: Plain dict `{timestamp, gpu: {...}|None, process: {rss_mb, vms_mb}, stages: {stage: {count, avg_ms, min_ms, max_ms}}}`; `LatencyTracker` is both the measurement instrument and the registry writer; the GPU slice is TTL-cached (5.0s, `force_refresh` bypass) while latency/process slices stay live.

**Live-seeded VRAM projection (QUAL-01):**
- Purpose: Ground the 4 GB compliance claim in a measured `nvidia-smi` sample instead of a hardcoded desktop-overhead guess.
- Examples: `scripts/profile_resources.py:267-287` (live `used_mb` as DWM baseline, 487 MB fallback only headless); `.planning/research/RESOURCE_PROFILE.json` (`projected_peak_vram_mb: 3450.0`, `vram_headroom_mb: 646.0`, `compliant_with_qual_01: true`, live `hardware_live` block).
- Pattern: `projected = live_used + 1450 (Q4_K_M) + 450 (mmproj) + 510 (KV-4K) + 350 (CUDA scratch)`; assert `≤ 3800`. Re-run the profiler on hardware changes; the JSON is the compliance artifact.

**CitationVerificationResult (grounding verdict):**
- Purpose: Deterministic, LLM-independent verdict rendered as badges and persisted per turn.
- Examples: produced in `citation_validator.py`, stored via `local_llm.py` (`last_verification_result`), persisted in `chat_history` (`main.py`), rendered in badges/drawers, audited per-case in `MULTIMODAL_BENCHMARK.json`.
- Pattern: Frozen Pydantic model — `is_valid`, `precision ∈ [0,1]`, `total_citations`, `valid_citations`/`hallucinated_citations` tags, `cited_ranks`, `abstention_detected`, `message`. Threshold `precision >= 0.95`.

**SummaryResult + SummaryProfile (cached synthesis contract):**
- Purpose: Profile-shaped markdown plus machine-readable page references and cache identity.
- Examples: produced in `summarizer.py`, persisted via `doc_store.py`, read in `summarizer.py` and the summary tab, rendered with cache/fresh captions.
- Pattern: `SummaryProfile = Literal["overview","detailed","study_notes","tables_figures","findings"]`, `VALID_SUMMARY_PROFILES` tuple (`models.py`); `SummaryResult` carries `summary_id (summ_*)`, `doc_id (doc_*)`, `sha256`, `profile`, `summary_text`, `page_references: list[int]`, `created_at`, `model_version`, `cached`. SQLite row mirrors every field with `page_references_json`.

**Unified sole retrieval index:**
- Purpose: One `search_hybrid` call spans all uploaded documents; exactly one object owns ranking state.
- Examples: `main.py` (incremental `index_chunks` per file into the session `HybridRetriever`), chat header chunk aggregation, `active_retriever = hybrid or local` with hybrid preferred.
- Pattern: Append-only growth with `chunk_id` upsert dedup; no per-document isolation; deletion only via `delete_document(doc_id)` or `purge_all`. Summarization is the exception: it scopes to one `doc_id` via DocStore chunk lookup, never via the retriever.

**RRF fusion:**
- Purpose: Combine dense semantic ranking and BM25 keyword ranking without score calibration.
- Examples: `hybrid_retriever.py` (`compute_rrf`, `DEFAULT_RRF_K = 60`).
- Pattern: `RRF(d) = Σ 1/(k_rrf + rank_m(d))`; returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score; `search_mode` records which modalities contributed.

**Token-stream generator (gate-held, provider-agnostic):**
- Purpose: Decouple token production (local or consented cloud provider) from rendering (Streamlit) while holding VRAM exclusivity for the whole stream duration.
- Examples: `local_llm.py` (producer holds `InferenceGate` from before first token until generator exhaustion), `main.py` (consumer via `st.write_stream`).
- Pattern: Generator yielding `str` fragments; gate is released in the generator's `finally`, so early abandonment still unlocks. Summarization uses the non-streaming sibling `provider.generate_text` under `hold` instead.

**Map-reduce page bundling:**
- Purpose: Fit arbitrarily long documents into a bounded context window without parallel LLM residency.
- Examples: `summarizer.py` (`_bundle_pages`, `_summarize_map_reduce`).
- Pattern: Greedy sequential packing by `estimate_tokens` against `MAX_BATCH_TOKENS`; map → optional half-consolidation → reduce, every stage carrying `(p. X)` forward, all inside one `InferenceGate.hold`. Cloud models get larger windows via `KNOWN_CONTEXT_WINDOWS`, but the bundling budgets stay fixed.

**Bounded chat history (turn cap + token budget + reporting):**
- Purpose: Cap unbounded session memory growth and keep every prompt inside the provider context window — with disclosure when clamping fires.
- Examples: `main.py` (`MAX_CHAT_TURNS = 50`), `append_chat_turn`, `prompt_budget.py` (`bound_chat_history`, oldest-first token truncation + `truncation_meta`), `main.py` (`history_to_pass = chat_history[:-1][-10:]` retrieval window, truncation caption).
- Pattern: Hard tail-slice to 50 turns with orphan-assistant pruning on every append; soft token truncation per request (flag-reported); narrow 10-turn window actually sent for history-contextualized retrieval.

**Raster-budget clamps:**
- Purpose: Bound worst-case per-page raster memory in the always-local ingestion path.
- Examples: `eff_dpi = min(300, max(72, int(dpi)))` (`ocr_fallback.py`), `zoom_clamped = min(3.0, max(0.5, float(zoom)))` + 2048×2048 pixel-budget downscale + `max_regions=20` (`visual_analyzer.py`); covered in `tests/test_visual_analyzer.py`.
- Pattern: Clamp-then-derive — clamp the resolution scalar first, then derive pixel buffers from the clamped value. New raster allocations must go through the same clamp shape.

## Entry Points

**Streamlit app (sole runtime entry):**
- Location: `main.py` (920 lines)
- Triggers: `streamlit run main.py` (local, per `docs/RUNBOOK.md`); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` first; session-state init incl. cloud keys + `ai_model`; session-scoped model load; anchored path constants; Privacy & Provider Mode block; sidebar upload/index loop with Clear Session + Purge All Data; telemetry widget + pipeline banner; `st.tabs` chat + summarizer loops.

**Privacy & Provider Mode block (consent-gated egress switch):**
- Location: `main.py:121-245`
- Triggers: Rendering the sidebar on every rerun; `st.toggle("Enable Cloud Inference")` flip; `I Consent & Enable Cloud` / `Cancel (Keep 100% Local)` / `Revoke Consent (Switch to Local)` clicks; provider selectbox / session-key edits.
- Responsibilities: Owns the `local → dialog → consented cloud → revocation` transitions, the `CLOUD_PROVIDER_OPTIONS` selectbox, memory-only session API keys, the cached `LiteLLMProvider` lifecycle, and the per-rerun `ai_model.set_cloud_mode(True/False)` sync on the session instance.

**Purge controls (persistent-data lifecycle):**
- Location: `main.py:297-378` (`col_clear` / `col_purge`)
- Triggers: `Clear Session` click (memory-only reset) vs `Purge All Data` click (persistent wipe + reset + toast).
- Responsibilities: Owns the clear-vs-purge contract; calls `doc_store.purge_all()`, session/temp `HybridRetriever.purge_all()` + `close()`, `CACHE_DIR` rmtree, cloud revocation, `st.rerun()`.

**Chat tab (grounded QA, mode-aware badges):**
- Location: `main.py` (`with tab_chat:`)
- Triggers: Selecting `💬 Ask Your Document`; submitting `st.chat_input` (disabled until an index exists and inference is healthy).
- Responsibilities: History replay with egress + verification badges/drawer, single shared `search_hybrid(k=5)` (always local), gate-held `ask_a_question_from_pdf_stream` + `st.write_stream`, `validate_response`, live badge/drawer + truncation caption, `append_chat_turn` persisting `is_cloud`/`model_name` (bounded).

**Summary tab (grounded summarization):**
- Location: `main.py` (`with tab_summary:`)
- Triggers: Selecting `📑 Document Summarizer`; pressing `Generate Summary`.
- Responsibilities: Document selectbox, 5-profile radio, force-refresh flag, gate-held `Summarizer(provider=ai_model.provider, doc_store=doc_store).summarize_document(...)` under `st.status`, 4-tier cache display with page-reference expander.

**On-the-fly Q&A fallback (legacy, not exercised by UI):**
- Location: `local_llm.py`
- Triggers: Calling `ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None` and no `retrieval_result`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then retrieval + generation. `main.py` always passes an existing retriever and `pdf_path=""`, so this path is dormant in production.

**Multimodal benchmark harness:**
- Location: `scripts/benchmark_multimodal.py:290-292` (`run_benchmark(live_model)` under `if __name__ == "__main__"`, `--live` flag)
- Triggers: Manual/CI invocation (`python scripts/benchmark_multimodal.py [--live]`).
- Responsibilities: 5-case accuracy/grounding audit over corpus PDFs through `AiModel` + isolated LanceDB-bench retriever + `validate_citations`; writes `.planning/research/MULTIMODAL_BENCHMARK.json`.

**Resource profiler:**
- Location: `scripts/profile_resources.py:341-342` (`run_resource_profile()` under `if __name__ == "__main__"`)
- Triggers: Manual invocation (`python scripts/profile_resources.py`).
- Responsibilities: 6-stage VRAM/latency/cache/concurrency audit with live `nvidia-smi` seed; writes `.planning/research/RESOURCE_PROFILE.json`.

**Baseline benchmark (manual):**
- Location: `scripts/benchmark_baseline.py` (174)
- Triggers: Manual invocation.
- Responsibilities: Manual retrieval/generation benchmark (predecessor to the two JSON-producing harnesses above).

**Runbooks (operator entry points):**
- Location: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`
- Triggers: Fresh install, server launch, incident triage, release sign-off.
- Responsibilities: `RUNBOOK.md` is the install→launch→operate→troubleshoot sequence (incl. purge procedure); `LOCAL_INFERENCE.md` is the live-measured VRAM-budget + model-acquisition reference for the 4 GB envelope; `EVALUATION.md` is the release acceptance record.

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom per interaction; long work (model load, extraction, embedding, summarization) blocks and is masked with `st.status` spinners. Token streaming is incremental rendering, not background threading. Map-reduce is deliberately sequential (no `asyncio`/threads). Cross-thread primitives are exactly three: `InferenceGate` (`threading.RLock` + counter, `local_llm.py`), the telemetry locks (`_LATENCY_LOCK`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`, `resource_telemetry.py`), and the GIL-guarded lazy `_MODEL_CACHE` fill (`local_embedding.py`).
- **Single-active-LLM invariant:** At most one gate-held inference op at a time (QA stream 60s timeout, `generate_text` 60s, summarizer 120s). Stream contention yields a retry notice; non-stream contention raises `TimeoutError`. RLock reentrancy means same-thread nesting does not deadlock — cross-thread nesting blocks.
- **Ingestion-stays-local invariant:** Extraction, OCR, CPU embeddings, LanceDB/SQLite/`.cache` writes, and visual analysis perform zero network egress in BOTH modes. Enforced structurally (none of `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `local_embedding.py`, `hybrid_retriever.py`, `doc_store.py` imports any network client), at the call site (`main.py` `local_vlm_provider` filter passes a provider to `VisualAnalyzer` ONLY when `is_local`), inside the analyzer (rejects non-local providers even on direct pass), and by test (`tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` fails the suite on any `socket.create_connection` during embed/index/search; `test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` asserts `analyze_image` is never invoked with a cloud provider).
- **Loopback-only local transport (SEC-01):** `LlamaCppProvider` refuses non-loopback `base_url` unless `allow_remote=True` (`llama_cpp_provider.py:53-57`); the only `httpx` client in the local path therefore cannot be redirected at internal or external hosts by accident. `allow_remote` is never set in production wiring — remote-server deployments must opt in explicitly at the construction call site.
- **No silent fallback across the egress boundary:** `_detect_provider` never routes local→cloud on health failure and never routes cloud→local silently either — mode changes happen ONLY through `set_cloud_mode` (UI toggle/dialog/revoke/clear/purge path on the session instance). A dead local server surfaces as `⚠️ Inference: Offline (setup required)`; a missing cloud key surfaces as `unreachable` from `LiteLLMProvider.check_health`.
- **Consent-before-transmission:** No document-derived string reaches `litellm.completion` unless `LiteLLMProvider.user_consented` is `True` at call time; the default is `False` and the UI can only set the provider-level flag to `True` through the consented branch. Revocation (toggle-off / revoke / clear / purge) destroys the cached provider object.
- **Session isolation (P1 audit):** `AiModel`, cloud flags, API keys, and the cached cloud provider all live in `st.session_state` — no inference routing state is process-shared anymore. The only intentional process-shared state is read-mostly weights (`_MODEL_CACHE`), the concurrency lock, and the telemetry TTL cache.
- **VRAM envelope (live-measured):** Embeddings pinned to CPU (`device="cpu"`); only one LLM/VLM active at a time via `InferenceGate`; local 4K context default with 1024 reserved output tokens; cloud windows are larger (128K–200K) but summarizer budgets (`FAST_PATH_TOKEN_LIMIT=2500`, `MAX_BATCH_TOKENS=2000`, map `800` / reduce `1500` / consolidate `1000`) keep every provider call bounded; OCR DPI ≤300, visual zoom ≤3.0 with 2048² px cap and ≤20 regions bound ingestion-side raster/VLM memory; telemetry widget enforces operational awareness with 3.5/3.8 GB alert tiers; measured allocation (RTX 3050 live audit): 690 DWM + 1450 weights + 450 mmproj + 510 KV-4K + 350 CUDA = **3450 MB peak, 646 MB headroom, QUAL-01 compliant** (`.planning/research/RESOURCE_PROFILE.json`, `docs/LOCAL_INFERENCE.md`).
- **Global state:** Per-session `AiModel` + `LocalEmbedding` holder + `HybridRetriever` + `VectorIndex` mirror + cloud flags/keys/cached cloud provider in `st.session_state`. Process-shared: `_MODEL_CACHE` weights, `InferenceGate._lock/_active_threads`, telemetry TTL cache (`_LAST_GPU_INFO`/`_LAST_GPU_SAMPLE_TIME`, resettable via `clear_gpu_cache()`). Per-turn `is_cloud`/`model_name` persistence is what keeps replay truthful.
- **Secrets handling:** Session API keys live ONLY in `st.session_state.cloud_api_keys` (memory, never written to disk; wiped by Clear Session AND Purge All); `_resolve_api_key_for_model` (`litellm_provider.py:39-85`) resolves per-provider-prefix in order session-state dict → legacy `cloud_api_key` → `st.secrets[ENV_VAR]` → `os.environ[ENV_VAR]` (`GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). `.env` is gitignored; existence only is noted, contents never quoted.
- **Deterministic dependencies:** `requirements.txt` is the dev-friendly manifest; `requirements-lock.txt` is the uv-synced deterministic production lockfile (all `==`, installed by the runbook AND by CI per the audit fix); `requirements-test.txt` holds test-only deps. Never add a runtime import without pinning it in `requirements.txt` AND freezing it in `requirements-lock.txt`.
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `main.py` → `litellm_provider.py` → `model_provider.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py` (gate-only import; `local_llm.py` never imports `summarizer.py`); `docling_reader.py` → `pdf_reader.py`; `scripts/*.py` → everything except `main.py`; `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` have no project imports. `citation_validator.py` imports only `models.py`. `litellm_provider.py` imports only `model_provider.py` (+ optional `litellm`, guarded `None` fallback). `docs/*.md` import nothing.
- **Persistence sextuplicity:** Every indexed chunk exists in up to four places — session `HybridRetriever` mirror, LanceDB table or `fallback_store.json`, SQLite `chunks` table, `.cache/*.json` — plus the shared embedding weights and Tier-3 summaries alongside. The four chunk copies are kept in sync only by the paired write in the upload block + persist block + CR-01 restore; direct writes to one store bypass the others. Purge All is the only operation that empties all of them at once.
- **Summary cache identity:** Key is `(sha256, profile)` (`UNIQUE` in `doc_store.py`); `model_version` is a read-time invalidation predicate, not part of the key. Same bytes under a new filename re-point `doc_id` on upsert; `list_summaries_for_doc` on the old id then misses. `force_refresh=True` bypasses the read but still overwrites the row on save. Switching providers (local ↔ cloud) changes `model_version`, so summaries regenerate rather than serve cross-model stale rows.
- **Chat memory bounds:** Hard cap `MAX_CHAT_TURNS=50` turns in session state; 10-turn window sent for retrieval contextualization; token-budget truncation per request (flag-reported via `truncation_meta`). Growing past 50 user+assistant turns evicts oldest-first; leading orphan assistant turns are pruned so history never starts mid-exchange.
- **Linear-scan fallback:** Without LanceDB, `VectorIndex.search` is O(n) per query; BM25 fallback is O(N·|Q|) with precomputed document frequencies.
- **Anchored-path rule:** Every persistent file (SQLite, LanceDB, fallback JSON, `.cache/`, benchmark artifacts) resolves from a `Path(__file__)`-anchored constant. No bare relative persistent paths.

## Anti-Patterns

### Dual-write ingestion still split across two statements in the UI layer

**What happens:** The upload block calls `LocalEmbedding.get_embeddings` then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` as two separate statements (`main.py`), and the mirror write into `VectorIndex` happens implicitly inside `index_chunks`.
**Why it's wrong:** A failure between the embedding call and the index call, or any future path that calls one without the other, leaves the embed-fn holder and the sole index inconsistent; readers must know the mirror exists to reason about `count_chunks`.
**Do this instead:** Encapsulate the embed-then-index pair behind a single façade (e.g. `HybridRetriever.index_texts(chunks)` that embeds via its own `embedding_fn` internally), so callers cannot partially index. Reference the existing `embedding_fn` injection as the consolidation point.

### Dormant `pdf_path` / on-the-fly indexing parameter

**What happens:** `ask_a_question_from_pdf_stream(pdf_path="", ...)` still accepts a path and can build a throwaway `PdfReader` + `LocalEmbedding` (`local_llm.py`); `main.py` always passes `pdf_path=""` with a live retriever.
**Why it's wrong:** Dead surface area that suggests an indexing path the UI never uses; risks confusion about which index answers a question.
**Do this instead:** Keep the parameter for backward compatibility (tests in `tests/test_local_llm.py` cover it) but treat `retrieval_result`/`local_embedding` as the canonical inputs — which is already the documented precedence in `local_llm.py`.

## Error Handling

**Strategy:** Validate at boundaries, isolate per-file/per-page failures, degrade gracefully across backends, invalidate rather than serve stale, gate cloud transmission on explicit consent, refuse non-loopback local endpoints at construction, clamp raster budgets before allocating, never hold the gate on failure paths, and never let purge fail loudly.

**Patterns:**
- SSRF denial is a constructor `ValueError`, not a runtime surprise — non-loopback `base_url` without `allow_remote=True` fails fast in `LlamaCppProvider.__init__` before any `httpx.Client` is built, so no socket ever opens to the rejected host.
- Consent denial is an exception, not a silent local fallback — unconsented `LiteLLMProvider.generate_text/stream_text/analyze_image` raises `PermissionError("Cloud transmission blocked: ...")`; the chat `try/except` renders it as `Inference streaming failed: ...` with an interruption turn rather than quietly answering locally and misattributing locality.
- Purge never raises — `HybridRetriever.purge_all` wraps the LanceDB `drop_table` in try/except-warn and the `fallback_store.json` unlink in `OSError`-warn (`missing_ok=True`); `main.py` wraps `shutil.rmtree(CACHE_DIR)` in try/except-logged-warning; `DocStore.purge_all` runs in one committed transaction; cloud-provider `close()` is guarded per-call. A purge that partially fails still resets session state and reruns.
- Strict deletion guards — `DocStore.delete_document` raises `TypeError` on non-string `doc_id` and explicitly deletes chunks/pages/evidence/summaries before the document row, so no orphan summaries survive a document delete.
- Gate-safe failure — the stream path releases `InferenceGate` in a `finally` so provider exceptions never wedge the lock; contention itself yields a retry string instead of raising, keeping the chat loop alive. `hold()` users (`generate_text`, summarizer) get `TimeoutError`, which the summary tab catches as `st.error` without touching chat.
- Budget clamps fail-safe by construction — DPI/zoom/region/pixel caps (`ocr_fallback.py`, `visual_analyzer.py`) clamp scalar inputs before any buffer allocation, so oversized pages degrade to lower-resolution crops rather than raising or OOMing.
- Telemetry never raises — `get_gpu_memory_info` returns `None` and `get_process_memory_info` returns zeros on any probe failure; the widget branches on `None` instead of try/except. Stale-but-fast beats fresh-but-blocking: inside the 5.0s TTL the widget renders the cached snapshot rather than failing or forking.
- Per-file upload guard — `try/except` around validation, `DoclingReader` extraction, OCR, and visual analysis in the sidebar upload block shows `st.error` and `continue`s, so one corrupt PDF never aborts the batch; per-page `status == "failed"` records warn individually.
- Summary tab guard — `try/except` around `summarizer.summarize_document` inside `st.status` flips the status to `error` and shows `st.error(f"Summarization error: ...")` without touching other tabs; empty-text documents raise `ValueError` from the service layer; unknown profiles raise `ValueError` before any provider call or gate acquisition.
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0`; `HybridRetriever.index_chunks` raises on chunk/embedding mismatch or missing embedding source; `LiteLLMProvider.analyze_image` raises `ValueError` on empty bytes and `NotImplementedError` on non-vision models; Pydantic models reject bad `doc_id`/`sha256`/coordinates/summary ids; `DocStore.save_summary` requires a `SummaryResult` instance.
- Health-as-data — `check_health` never raises for expected outages: missing `litellm` install → `unreachable` with install hint; missing per-provider key → `unreachable` naming the `*_API_KEY` var; unreachable `llama-server` → `unreachable` with the launch command; the sidebar renders `⚠️ Inference: Offline` + the message instead of try/except. The runbook mirrors each outage with a remedy (`docs/RUNBOOK.md`).
- Validation-as-data — `validate_citations` never raises on bad input: empty responses, ungrounded claims, hallucinated ranks, and abstention-with-citations all return a populated `CitationVerificationResult` with `is_valid=False`; the chat exception path records `verification: None` explicitly rather than fabricating a pass; the benchmark harness records per-case `citation_precision` + `hallucinated_citations` without aborting the suite on a FAIL.

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` per module (`local_llm.py`, `litellm_provider.py` logs generation/streaming/vision failures with model name, `resource_telemetry.py` `logger.debug` for probe unavailability so CI/headless stays quiet, `main.py:logger` for `CACHE_DIR` removal failures, `hybrid_retriever.py` for purge drop/unlink outcomes, `local_embedding.py` for shared-model load, `visual_analyzer.py` for region capping); developer lifecycle `print` in embedding/reader/benchmark/profiler modules; user-facing feedback exclusively via Streamlit (`st.error` / `st.info` / `st.success` / `st.status` / `st.write` / `st.caption` badges + `st.toast` for purge). Rule: `print()`/`logger` for diagnostics, `st.*` for anything the user sees.

**Validation:** Boundary validation at every layer — `validate_pdf_bytes` (header/size/pages) at upload; `LlamaCppProvider` loopback guard at local-provider construction; `TypeError` on `delete_document` misuse; Pydantic contracts (`models.py`) at persistence; `VectorIndex` type/dimension guards; `LiteLLMProvider` consent + empty-bytes + vision-capability guards; raster clamps (DPI/zoom/pixels/regions) before allocation; `CitationValidator` post-generation grounding gate; `model_version` read-time cache invalidation; `truncation_meta` disclosure of budget clamps.

**Authentication:** No user auth. Provider credentials are per-cloud-API keys resolved per call by `_resolve_api_key_for_model` (`litellm_provider.py:39-85`): session-state `cloud_api_keys` dict (memory-only, wiped by Clear Session AND Purge All) → legacy `cloud_api_key` → `st.secrets` → `os.environ`. Missing keys degrade to `unreachable` health, never to silent local substitution or to transmitting without a key. Dependency installation needs no auth beyond public PyPI (lockfile strategy in `docs/RUNBOOK.md`).

---

*Architecture analysis: 2026-10-13*
