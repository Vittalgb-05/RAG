<!-- refreshed: 2026-10-12 -->
# Architecture

**Analysis Date:** 2026-10-12

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│              Streamlit UI / Orchestrator                     │
│  `main.py` (854) — tab_chat (grounded QA) + tab_summary     │
│  (summarizer) + sidebar upload + telemetry widget +          │
│  Privacy & Provider Mode block (cloud toggle, consent       │
│  dialog, provider select, session API keys, revoke)         │
├──────────────────┬──────────────────┬───────────────────────┤
│  Ingestion       │  Hybrid Retrieval│  Inference (gated +    │
│  (ALWAYS LOCAL)  │  (ALWAYS LOCAL)  │  mode-switched)        │
│  `docling_reader │  `hybrid_        │  `local_llm.py`        │
│  .py`            │  retriever.py`   │  (InferenceGate +      │
│  `pdf_reader.py` │  (sole index)    │  AiModel incl.         │
│  `ocr_fallback   │  `local_         │  set_cloud_mode /      │
│  .py`            │  embedding.py`   │  _detect_provider)     │
│  `visual_        │  (embed-fn only) │  `model_provider.py`   │
│  analyzer.py`    │  `vector_index   │  `llama_cpp_provider   │
│  (local-VLM      │  .py` (mirror)   │  .py` (local default,  │
│  only)           │                  │  loopback-guarded)     │
│                  │                  │  `groq_provider.py`    │
│                  │                  │  (legacy cloud)        │
│                  │                  │  `litellm_provider.py` │
│                  │                  │  (consented cloud)     │
│                  │                  │  `prompt_budget.py`    │
│                  │                  │  `summarizer.py`       │
│                  │                  │  `citation_validator   │
│                  │                  │  .py`                 │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│  Persistence + Telemetry Layer (ALWAYS LOCAL)                │
│  `doc_store.py` (SQLite `data/documents.db`: documents,     │
│   pages, chunks, evidence_elements, document_summaries v3)   │
│  `hybrid_retriever.py` (LanceDB `data/lancedb`)             │
│  `resource_telemetry.py` (5.0s-TTL GPU cache, psutil,       │
│   LatencyTracker) + `scripts/profile_resources.py`          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Canonical Contracts + Operations                           │
│  `models.py` — Chunk / Page / Document / EvidenceSnippet /  │
│  RetrievalResult / BBox / EvidenceElement / SummaryResult /  │
│  SummaryProfile + VALID_SUMMARY_PROFILES                     │
│  `docs/RUNBOOK.md` + `docs/LOCAL_INFERENCE.md` +            │
│  `docs/EVALUATION.md` — install / launch / troubleshoot /   │
│  VRAM budget / release metrics                               │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session-state init (incl. `cloud_mode`/`cloud_mode_toggle`/`user_consented`/`cloud_provider`/`cloud_model`/`cloud_api_keys`/`cloud_api_key`), `st.tabs` wiring (`tab_chat` / `tab_summary`), Privacy & Provider Mode sidebar block, consent dialog, provider select + session keys, revoke-consent reset, cloud-provider caching + `set_cloud_mode` wiring, telemetry expander widget, pipeline banner, chat replay with egress + verification badges/drawer, `MAX_CHAT_TURNS` bounding via `append_chat_turn`, single shared `RetrievalResult` fetch, streaming render | `main.py` |
| InferenceGate | Process-level reentrant lock (`threading.RLock` + counter) guaranteeing max one active GPU inference op; `acquire`/`release`/`is_locked`/`hold` (timeout → `TimeoutError`); guards QA streaming and summarization map/reduce | `local_llm.py:26-90` |
| AiModel | Explicit mode-switched orchestration: `cloud_mode` flag + optional consented `cloud_provider`, `set_cloud_mode(enabled, cloud_provider)` dynamic toggle (idempotent no-op fast path, WR-02), `_detect_provider` explicit selection with NO silent fallback, health re-probing, RAG orchestration, `retrieval_result`-first prompt assembly via `assemble_grounded_messages`, InferenceGate-guarded `ask_a_question_from_pdf_stream` + `generate_text`, `validate_response` citation-validation façade | `local_llm.py:93-346` |
| LiteLLMProvider (consented cloud) | Unified cloud adapter over `litellm.completion` for `groq/*`, `openai/*`, `anthropic/*` (`DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"`); programmatic `_assert_consent` gate raising `PermissionError` on every `generate_text`/`stream_text`/`analyze_image` without `user_consented=True`; `set_consent`, per-prefix context windows (groq 131072 / openai 128000 / anthropic 200000), `is_local=False`, vision allowlist, `timeout=30.0`/`num_retries=2`, 4-tier API-key resolution | `litellm_provider.py:101-346` |
| GroqProvider (legacy cloud) | Cloud fallback used only when `cloud_mode=True` without an explicit `cloud_provider` and its health check passes; `is_local=False` | `groq_provider.py` |
| LlamaCppProvider (local default, loopback-guarded) | Local llama-server client (`http://127.0.0.1:8080`, `qwen3-vl-2b`, context 4096); constructor validates `base_url` host is loopback (`localhost` literal or `ipaddress.ip_address(host).is_loopback`, scheme normalised when `://` is absent) and raises `ValueError("Restricted endpoint: ...")` for non-loopback hosts unless `allow_remote=True` is explicitly passed; `is_local=True` | `llama_cpp_provider.py:23-67` |
| Consent Dialog + Cloud-Mode Sidebar | `st.toggle("Enable Cloud Inference")` (`cloud_mode_toggle` widget key) → `show_consent_dialog()` (`@st.dialog`, fallback plain render) with `_render_consent_dialog_content` (external-transmission warning + stays-local list + `I Consent & Enable Cloud` / `Cancel (Keep 100% Local)` buttons); provider selectbox over `CLOUD_PROVIDER_OPTIONS` (groq/openai/anthropic → model id + env var); per-provider `st.text_input` session API key (memory-only); `Revoke Consent (Switch to Local)` reset; cached `LiteLLMProvider(user_consented=True)` construction + `ai_model.set_cloud_mode(True/False)` sync every rerun | `main.py:108-245` |
| Egress Transparency (badges/chips/banner) | Pipeline banner under telemetry (`🔒 100% Offline Local Pipeline` vs `☁️ Cloud Inference · {model}` with `(Embeddings & LanceDB 100% Local)` suffix); per-turn egress badge on live stream and on replay (`☁️ Generated via external cloud provider ({model}) with user consent.` vs `🔒 Generated locally on-device (zero network egress).`); `is_cloud` + `model_name` persisted per assistant turn; `[En] filename (p. N)` source chips + `🔍 Cited Evidence & Source Context` expander | `main.py:537-540`, `main.py:576-618`, `main.py:686-749` |
| Resource Telemetry (TTL-cached) | `get_gpu_memory_info(force_refresh=False)` (nvidia-smi CSV parse → `total/used/free_mb` + `utilization_pct`, `None` on headless/CI; 5.0s monotonic TTL via `_GPU_CACHE_TTL_SECONDS` + `_GPU_CACHE_LOCK` fast path + `_SAMPLING_LOCK` double-checked sampling so concurrent reruns spawn at most one subprocess; `clear_gpu_cache()` test/ops hook), `get_process_memory_info` (psutil RSS/VMS MB, zeros fallback), `LatencyTracker`/`track_stage`/`record_stage_latency` (thread-safe `defaultdict`, `MAX_STAGE_HISTORY=200`), `get_system_telemetry_snapshot` (timestamp + gpu + process + per-stage count/avg/min/max) | `resource_telemetry.py:25-245` |
| Telemetry Widget | Sidebar `📊 System Telemetry & VRAM` expander: `st.metric` GPU VRAM + progress bar + 3-tier health caption (🟢 <3.5GB / 🟡 3.5–3.8GB / 🔴 >3.8GB, else CPU-only caption), process RSS caption, persistent-cache counts via `count_documents`/`count_summaries`; per-rerun reads are served from the 5.0s TTL cache, not fresh subprocess spawns | `main.py:508-535` |
| Resource Profiler | Offline 6-stage benchmark harness (ingestion → CPU embeddings → LanceDB retrieval cold/warm → summary cache SLA → InferenceGate check → VRAM budget audit) writing `.planning/research/RESOURCE_PROFILE.json` with projected-peak VRAM vs 3800 MB target | `scripts/profile_resources.py:94-342` |
| HybridRetriever (sole index, always local) | Persistent hybrid retrieval: LanceDB dense vectors + FTS index, pure-Python BM25 fallback, RRF fusion (`compute_rrf`), `search_hybrid` → canonical `RetrievalResult`; in-memory `VectorIndex` mirror with `chunk_id` upsert dedup; disk-backed `fallback_store.json` when LanceDB missing; never performs network egress | `hybrid_retriever.py:79-626` |
| LocalEmbedding (embed-fn provider, always local) | CPU-pinned `SentenceTransformer` wrapper; `_embed_one` is the shared query/index embedding function injected into `HybridRetriever`; `build_index`/`search`/`search_hybrid`/`get_context` retained as fallback dense path | `local_embedding.py:19-116` |
| VectorIndex | Pure-stdlib in-memory vector store; `add_vector`/`add_document`/`search` (linear-scan k-NN, cosine + Euclidean, dimension locking); serves as `HybridRetriever` fallback mirror (`hybrid_retriever.py:104-108`) | `vector_index.py` |
| Canonical Models | Pydantic v2 contracts: `Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult` (`formatted_evidence`, `source_labels`), `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` | `models.py` |
| DocStore | SQLite WAL metadata store (`documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` v3; migrations v1–v3); SHA-256 dedup, chunk restore, `save_summary`/`get_summary` (model-version invalidation)/`list_summaries_for_doc`/`delete_summaries_for_doc`/`delete_document` cascade, `count_documents`/`count_summaries` for telemetry widget | `doc_store.py` |
| Summarizer | Hierarchical multi-profile summarization: profile dispatch, fast-path vs map-reduce selection, `InferenceGate.hold(timeout=120.0)`-guarded generation, `(p. X)` citation preservation, `SummaryResult` construction, 4-tier cache check/save (`force_refresh` bypass); runs against whichever provider `AiModel` currently routes to | `summarizer.py:301-420` |
| CitationValidator | Post-generation grounding gate: `extract_citations` (`[En]`), `is_abstention`, `validate_citations` → frozen `CitationVerificationResult` (≥95% precision, empty-response invalid, abstention-with-citations invalid) | `citation_validator.py` |
| Chat Bounding | `MAX_CHAT_TURNS = 50` + `append_chat_turn` (append → `bound_chat_history`) + `bound_chat_history` (tail-slice to 50, strip leading orphan assistant turns) + token-level oldest-first truncation inside `assemble_grounded_messages` | `main.py:38,543-549`, `prompt_budget.py:57-152` |
| Providers | `BaseModelProvider` ABC + `HealthStatus`/`ProviderCapabilities` (`is_local` is the egress discriminator); `LlamaCppProvider` (local default, loopback-guarded), `GroqProvider` (legacy cloud), `LiteLLMProvider` (consented multi-cloud) | `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `litellm_provider.py` |
| DoclingReader | Structured extraction via Docling `DocumentConverter` (CPU-only, `do_ocr=False`, `do_table_structure=True`); graceful degrade to `PdfReader` (pypdf); local-only | `docling_reader.py` |
| PdfReader | Legacy pypdf text extraction + `RecursiveCharacterTextSplitter` chunking (1000/200) with `{content, filename, page, chunk_id}` metadata; local-only | `pdf_reader.py` |
| Conditional OCR | RapidOCR fallback for low-text/scanned pages; local-only | `ocr_fallback.py` |
| VisualAnalyzer | Visual element detection, cropping, VLM analysis with defense-in-depth cloud rejection (refuses non-local providers); results recorded via `DocStore.record_evidence_elements`; ingestion call site passes a `local_vlm_provider` that is `None` whenever the active provider is not local | `visual_analyzer.py`, `main.py:402-417` |
| Upload Validation | Server-side `%PDF` header / size / page-limit checks, SHA-256 + `doc_id` derivation | `upload_validation.py` |
| Prompt Budget | Bounded context assembly: `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`[E1]` citation rules + abstention sentence), `sanitize_xml_boundary`, `estimate_tokens`, oldest-first history truncation, `bound_chat_history` turn cap | `prompt_budget.py` |
| Runbooks + Evaluation Docs | `docs/RUNBOOK.md` (install via lockfile, llama-server launch flags, ingestion/telemetry/cloud runbooks, 4-issue troubleshooting), `docs/LOCAL_INFERENCE.md` (VRAM budget table ~3,260 MB peak, model download, server flags, health check), `docs/EVALUATION.md` (release test metrics: 217 cases, 100% pass, ruff clean) | `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md` |

## Pattern Overview

**Overall:** UI-orchestrated modular monolith with explicit local/cloud mode switching, consent-gated cloud egress, SSRF-hardened local endpoint, persistent hybrid retrieval, single-active-LLM concurrency gating, TTL-cached resource telemetry, multi-tier cache invalidation, and bounded chat memory.

**Key Characteristics:**
- Ingestion-stays-local invariant — extraction (Docling/pypdf/OCR), CPU embeddings, LanceDB/SQLite/`.cache` persistence, and visual analysis NEVER touch the network in either mode; only generation (`provider.stream_text` / `provider.generate_text`) may egress, and only through a consented cloud provider while `cloud_mode=True`.
- Explicit provider selection, no silent fallback — `_detect_provider` (`local_llm.py:162-179`) routes purely on `cloud_mode`: `False` → fresh `LlamaCppProvider` unconditionally (no health-probe fallback to cloud); `True` → explicit `cloud_provider` if supplied, else a health-checked `GroqProvider`. Local unhealth never auto-escalates to cloud.
- SSRF-hardened local endpoint — `LlamaCppProvider.__init__` (`llama_cpp_provider.py:40-57`) normalises scheme (`base_url if "://" in base_url else f"http://{base_url}"`), accepts `localhost` literally or any `ipaddress.is_loopback` address (covers the full `127.0.0.0/8` block and `::1`), and raises `ValueError("Restricted endpoint: ... is not a local loopback address. ...")` for anything else unless `allow_remote=True` is explicitly passed. The server itself binds `--host 127.0.0.1` (`docs/RUNBOOK.md:95,106,115`). Covered in `tests/test_llama_cpp_provider.py:262-292` (rejected non-loopback, `allow_remote` opt-in, accepted loopback variants incl. `127.0.1.1`/`127.0.0.2`/scheme-less).
- Cloud-mode state machine — `local → dialog → consented cloud → revocation`: default `cloud_mode=False, user_consented=False` (100% local); toggling ON opens the consent dialog (consent → both flags `True`; cancel → both `False`); consented cloud persists across reruns via session flags + cached `LiteLLMProvider`; toggle-OFF, `Revoke Consent`, or unconsented-state detection resets both flags `False`, closes/drops the cloud provider, and calls `set_cloud_mode(False)`.
- Programmatic consent enforcement — `LiteLLMProvider._assert_consent` raises `PermissionError("Cloud transmission blocked: ... (INF-04, UI-04).")` at the top of every transmitting method (`generate_text`, `stream_text`, `analyze_image`), independent of the UI; `user_consented=False` is the constructor default.
- Egress transparency everywhere — pipeline banner (`main.py:537-540`), per-turn live + replay badges (`☁️` vs `🔒`), `is_cloud`/`model_name` persisted per assistant turn, `[En]` source chips + evidence drawer; cloud captions always name the model and cite consent, and always carry the `(Embeddings & LanceDB 100% Local)` qualifier on the banner.
- Single-active-LLM invariant — every token-producing call (QA stream, `generate_text`, summarizer map/reduce) executes while holding `InferenceGate`; concurrent inference either waits (up to timeout) or yields a busy-retry notice instead of colliding in 4 GB VRAM.
- HybridRetriever-as-sole-index — one `search_hybrid(k=5)` call in `main.py` spans all uploaded documents; `LocalEmbedding` is retained only as the CPU embedding-function provider (`_embed_one`) injected into the retriever, plus a dormant dense-only fallback path.
- One-retrieval-per-question: `main.py` fetches a single shared `RetrievalResult` and passes the identical object to prompt assembly, generation, validation, and UI citations (RETR-04).
- Generator-based streaming — `ask_a_question_from_pdf_stream` yields `str` fragments; `st.write_stream` renders incrementally and returns the full string for post-hoc validation.
- Validate-after-stream: citations are checked on the completed string via `AiModel.validate_response` → `validate_citations`; the `CitationVerificationResult` is persisted alongside the turn in `chat_history` and re-rendered on replay.
- TTL-throttled telemetry: `get_gpu_memory_info` caches the last probe for 5.0s (`_GPU_CACHE_TTL_SECONDS`, `resource_telemetry.py:26-30`) with double-checked locking (`_SAMPLING_LOCK`, `resource_telemetry.py:50-55`), so per-rerun widget reads cost zero subprocess spawns inside the window; `force_refresh=True` bypasses for profiler/ops use.
- Multi-tier cache invalidation: Tier 1 session (`summary_{doc_id}_{profile}` dicts, purged by Clear All) → Tier 2 disk `.cache/<sha>/<CONFIG_VERSION>/*.json` (best-effort extraction cache) → Tier 3 SQLite `document_summaries` keyed `(sha256, profile)` with read-time `model_version` invalidation + `force_refresh` bypass → Tier 4 LanceDB/`fallback_store.json` vector persistence; telemetry counts surface Tier 3 size.
- Bounded chat memory at two levels: turn-count cap (`MAX_CHAT_TURNS=50` via `bound_chat_history`) and token-budget truncation (oldest-first inside `assemble_grounded_messages` against `context_window - 1024` reserved).
- Graceful degradation everywhere: Docling → pypdf, LanceDB → JSON-backed `VectorIndex`, nvidia-smi/psutil → `None`/zeros in CI. NOTE: local LLM health degradation does NOT fall back to cloud — the failure surfaces as an offline notice.
- Deterministic deployment: fluid `requirements.txt` (17 lines, mixed `==`/`>=` ranges for dev flexibility) vs frozen `requirements-lock.txt` (27 lines, all `==` pins incl. `litellm==1.105.0`, `streamlit==1.65.0`); the runbook installs from the lockfile (`docs/RUNBOOK.md:45-49`).

## Layers

**Presentation / Orchestration (incl. Privacy & Provider Mode):**
- Purpose: File upload, provider-mode + consent UX, index-status display, tabbed chat + summarizer UX, streamed answer rendering with egress/verification badges and evidence drawers, live VRAM/RAM/cache telemetry.
- Location: `main.py`
- Contains: `st.set_page_config` (`main.py:44-49`), session-state init loop incl. cloud keys (`main.py:60-76`), `load_ai_model` (`@st.cache_resource`, `main.py:84-92`), Privacy & Provider Mode block (`main.py:108-245`), sidebar upload/index loop (`main.py:283+`), telemetry expander (`main.py:508-535`), pipeline banner (`main.py:537-540`), `append_chat_turn` bounding helper (`main.py:543-549`), `st.tabs(["💬 Ask Your Document", "📑 Document Summarizer"])` (`main.py:556`), chat tab (`main.py:558-749`), summary tab (`main.py:752+`).
- Depends on: `local_llm.py:AiModel` (+ `set_cloud_mode`), `litellm_provider.py:LiteLLMProvider`, `local_embedding.py:LocalEmbedding`, `hybrid_retriever.py:HybridRetriever`, `docling_reader.py:DoclingReader`, `doc_store.py:DocStore`, `summarizer.py:Summarizer`, `resource_telemetry.py:get_gpu_memory_info/get_process_memory_info`, `prompt_budget.py:bound_chat_history`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`.
- Used by: End user via browser at `http://localhost:8501`; dev container post-attach command.

**Ingestion / Extraction (always local, mode-independent):**
- Purpose: Bytes-in, canonical `Chunk`/`Page` records out, with per-page fault isolation and zero network egress in both modes.
- Location: `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`
- Contains: `DoclingReader.extract_text/get_paragraphs/get_page_records`, `PdfReader.extract_text/get_paragraphs`, `apply_conditional_ocr`, `VisualAnalyzer.analyze_visual_elements` (rejects non-local providers), `validate_pdf_bytes`.
- Depends on: `docling`, `pypdf`, `langchain_text_splitters.RecursiveCharacterTextSplitter`, `models.py:Chunk/Page`.
- Used by: `main.py` upload path (extraction + OCR + visual analysis with `local_vlm_provider` filter at `main.py:404-417`) and `local_llm.py:234-238` (on-the-fly fallback path).

**Retrieval (HybridRetriever as sole index, always local):**
- Purpose: Semantic + keyword lookup fused into ranked, provenance-carrying evidence through a single index object; no network in either mode.
- Location: `hybrid_retriever.py`, `local_embedding.py` (embed-fn only), `vector_index.py` (mirror)
- Contains: `HybridRetriever.index_chunks/search_dense/search_fts/search_hybrid`, `compute_rrf`, `_bm25_search_fallback`, `LocalEmbedding._embed_one/get_embeddings`, `VectorIndex.add_vector/add_document/search` plus `_cosine_distance/_euclidean_distance`.
- Depends on: `sentence_transformers.SentenceTransformer` (embedding only), optional `lancedb` + `pyarrow`; fallback store is stdlib-only.
- Used by: `main.py:431-439` (build: `LocalEmbedding.get_embeddings` batch → `HybridRetriever.index_chunks` with `chunk_id` upsert dedup), `main.py:656-660` (query: `active_retriever.search_hybrid(search_query, k=5)`), CR-01 restore path (re-embed persisted chunks → fresh `HybridRetriever`), `local_llm.py` (in-LLM fallback retrieval).

**Inference / Generation (InferenceGate-guarded, mode-switched, loopback-hardened local path):**
- Purpose: Grounded answer synthesis with conversational memory, bounded context, explicit local/cloud routing, SSRF-safe local transport, and single-active-LLM concurrency safety.
- Location: `local_llm.py:26-90` (gate), `local_llm.py:103-210` (`__init__`/`set_cloud_mode`/`_detect_provider`/`check_health`), `local_llm.py:211-326` (stream + non-stream paths), `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py:23-67` (loopback guard), `litellm_provider.py`, `prompt_budget.py`
- Contains: `InferenceGate.acquire/release/is_locked/hold`, `AiModel.set_cloud_mode` (idempotent toggle + provider swap + `close()` + re-detect), `AiModel._detect_provider` (cloud_mode branch → explicit/cloud-health-checked provider; local branch → `LlamaCppProvider`), `AiModel.ask_a_question_from_pdf_stream/generate_text/validate_response`, `LiteLLMProvider._assert_consent/set_consent/check_health/get_capabilities/generate_text/stream_text/analyze_image`, `BaseModelProvider.stream_text/generate_text`, `assemble_grounded_messages`, `bound_chat_history`.
- Depends on: `HybridRetriever` / `LocalEmbedding` (retrieval input), `models.py:RetrievalResult` (context input), `citation_validator.py:validate_citations` (post-check), `litellm` package (cloud path only), `httpx` (loopback localhost HTTP only, unless `allow_remote=True`).
- Used by: `main.py:677-683` (chat stream), `summarizer.py:388-394` (summary map/reduce via gate-held `provider.generate_text`).

**Summarization:**
- Purpose: Bounded, VRAM-safe, profile-shaped document synthesis with `(p. X)` citations and multi-tier caching; generation egress follows the active mode (local vs consented cloud).
- Location: `summarizer.py:301-420`
- Contains: `Summarizer.summarize_document` (profile whitelist → Tier-3 cache check → page resolve/enrich → `InferenceGate.hold(timeout=120.0)` fast/map-reduce → `extract_page_references` → `save_summary`), `_bundle_pages`, `_format_page_batch`, `_summarize_single_pass`, `_summarize_map_reduce`, `extract_page_references`, `PROFILE_SYSTEM_INSTRUCTIONS`, `MAP_PROMPT_TEMPLATE` / `REDUCE_PROMPT_TEMPLATE`, `FAST_PATH_TOKEN_LIMIT = 2500` / `MAX_BATCH_TOKENS = 2000`.
- Depends on: `local_llm.py:InferenceGate`, `model_provider.py:BaseModelProvider` (`generate_text`, `get_capabilities`), `models.py:Page/SummaryResult/VALID_SUMMARY_PROFILES`, `prompt_budget.py:estimate_tokens/sanitize_xml_boundary`, `doc_store.py:DocStore` (Tier-3 cache backend).
- Used by: summary tab generation (`main.py:752+`).

**Citation Validation:**
- Purpose: Deterministic post-generation grounding gate independent of any LLM or mode.
- Location: `citation_validator.py:52-181`
- Contains: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations`.
- Depends on: `models.py:RetrievalResult` (snippet-count bound only), stdlib `re`, Pydantic v2.
- Used by: `local_llm.py:328-346` (`AiModel.validate_response`), exercised in `main.py:693`.

**Persistence + Telemetry (always local, TTL-throttled probes):**
- Purpose: Survive restarts (document metadata, chunk text, vectors, evidence elements, summaries, disk cache) and expose live resource pressure (VRAM/RAM/latency) without per-rerun subprocess cost; never egresses.
- Location: `doc_store.py`, `hybrid_retriever.py:_save_fallback_store/_load_fallback_store`, `resource_telemetry.py:25-60` (TTL cache), `resource_telemetry.py:99-211` (latency registry + snapshot + `clear_gpu_cache`), `.cache/`, `scripts/profile_resources.py`
- Contains: `DocStore.upsert_document/record_page/record_chunks/record_evidence_elements/get_chunks_for_doc/save_summary/get_summary/list_summaries_for_doc/delete_summaries_for_doc/delete_document/count_documents/count_summaries`, `SCHEMA_V3_DDL` `document_summaries` table (`doc_store.py:73-94`, `UNIQUE(sha256, profile)`, FK `doc_id → documents(doc_id) ON DELETE CASCADE`), `MIGRATIONS = {1,2,3}` (`doc_store.py:96-100`), LanceDB `chunks` table, `fallback_store.json`, `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`, `_GPU_CACHE_TTL_SECONDS=5.0` + `_GPU_CACHE_LOCK` + `_SAMPLING_LOCK` + `get_gpu_memory_info(force_refresh)` + `clear_gpu_cache`, `get_process_memory_info/get_system_telemetry_snapshot`.
- Depends on: stdlib `sqlite3` (WAL mode), optional `lancedb`, `nvidia-smi` subprocess (TTL-throttled), optional `psutil`.
- Used by: `DOC_STORE_PATH` open (`main.py:95-96`), upload persist block, CR-01 restore after restart, telemetry widget reads (`main.py:510-535`, served from TTL cache), summary cache read, `summarizer.py:332-336,415-418` (summary cache check/save).

**Operations / Runbooks:**
- Purpose: Reproducible install, local-server launch, ingestion/telemetry/cloud procedures, troubleshooting, VRAM budget, and release acceptance metrics — the human-executable counterpart to the architecture.
- Location: `docs/RUNBOOK.md` (202), `docs/LOCAL_INFERENCE.md` (148), `docs/EVALUATION.md` (138)
- Contains: venv setup + `pip install -r requirements-lock.txt` (deterministic pins) + Windows symlink tip (`RUNBOOK.md:23-54`); `llama-server` launch (`-m …q4_k_m.gguf --mmproj … -c 4096 -ngl 28 --host 127.0.0.1 --port 8080`) with per-flag breakdown and `curl http://127.0.0.1:8080/health` check (`RUNBOOK.md:84-124`); ingestion limits (50 MB / 500 pages / `%PDF` magic) and pipeline order (`RUNBOOK.md:144-155`); telemetry TTL note (`RUNBOOK.md:157-161`); cloud-consent activation steps (`RUNBOOK.md:163-167`); 4-issue troubleshooting (unreachable server, CUDA OOM with `-ngl`/`-c` reduction, missing optional deps graceful-degrade, stale `.cache/` purge) (`RUNBOOK.md:171-202`); VRAM allocation table totalling ~3,260 MB peak vs 4,096 MB ceiling (`LOCAL_INFERENCE.md:7-19`); release metrics table (217 cases, 100% pass, 50.6s, ruff clean) (`EVALUATION.md:8-20`).
- Depends on: Nothing in code — documents reference `llama_cpp_provider.py` defaults, `resource_telemetry.py` TTL, and `upload_validation.py` limits.
- Used by: Operators and release verification; GSD planning reads these as ground truth for launch/limits/budgets.

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted, always local)

1. Upload + validate (sidebar upload block, `main.py:310+`) — single `getvalue()` read per file; `MAX_FILE_MB` pre-check; `validate_pdf_bytes` (`upload_validation.py`) yields `doc_id`/`sha256`/`num_pages`. Limits documented in `docs/RUNBOOK.md:144-150` (50 MB / 500 pages / `%PDF` magic).
2. Dedup via `DocStore.get_by_sha` — session `doc_ids` set + SQLite `status == "indexed"` check; CR-01 path restores chunks from `DocStore.get_chunks_for_doc` into fresh `LocalEmbedding` + `HybridRetriever` (re-embed via `get_embeddings`, `index_chunks`) when the session index is empty after restart.
3. Extraction — `DoclingReader.extract_text` → `get_paragraphs`/`get_page_records`; `apply_conditional_ocr` patches scanned pages; `VisualAnalyzer.analyze_visual_elements` runs with the `local_vlm_provider` filter (`main.py:404-417`: passes the active provider ONLY when `get_capabilities().is_local`, else `None`, and the analyzer itself rejects cloud providers) and records elements; per-page `record_page` with `st.progress`; failed pages warn and continue. No branch transmits bytes off-device.
4. Sole-index build (`main.py:431-439`) — `LocalEmbedding.get_embeddings([p["content"] ...])` batch on CPU, then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` which writes BOTH the persistent LanceDB table (or `fallback_store.json`) and the in-memory `VectorIndex` mirror with `chunk_id` upsert dedup (`hybrid_retriever.py:269-282`). `LocalEmbedding.build_index`/`store` is NOT written on this path — the embedding object serves only as the `_embed_one` function provider. All stores are on-disk/in-process.
5. Persist — `Chunk.model_validate` → `record_chunks`; `Document` → `upsert_document`; best-effort `.cache/<sha>/docling-1000-200-v1/*.json` write; session-state update + `st.rerun()`.

### Cloud-Mode State Machine (local → dialog → consented cloud → revocation)

1. Default local (`main.py:67-73`) — session keys initialise to `cloud_mode=False`, `cloud_mode_toggle=False`, `user_consented=False`, `cloud_provider="groq"`, `cloud_model="groq/llama-3.3-70b-versatile"`, `cloud_api_keys={"groq":"","openai":"","anthropic":""}`; `AiModel()` constructs with `cloud_mode=False` so `_detect_provider` returns a local `LlamaCppProvider` with zero egress.
2. Toggle ON → consent dialog (`main.py:147-155`) — `st.toggle("Enable Cloud Inference", key="cloud_mode_toggle")`; when the widget value is `True` while `user_consented` is still `False`, `show_consent_dialog()` renders (`@st.dialog("Cloud Inference & Data Privacy Consent")` when available, else inline). The dialog warns that query prompts + retrieved excerpts will egress, enumerates what stays on-device (PDF bytes, extracted text/OCR, MiniLM embeddings, LanceDB + SQLite), and offers `I Consent & Enable Cloud` (sets `user_consented=True`, `cloud_mode=True`, `cloud_mode_toggle=True` + `st.rerun()`) vs `Cancel (Keep 100% Local)` (all three `False` + `st.rerun()`).
3. Consented cloud active (`main.py:168-237`) — sidebar shows `☁️ Cloud Mode Active (Egress permitted with user consent)`; provider selectbox over `CLOUD_PROVIDER_OPTIONS`; per-provider session API key `st.text_input(type="password")` kept in `st.session_state.cloud_api_keys` (memory only); a cached `LiteLLMProvider(model_name=cloud_model, api_key=active_key or None, user_consented=True)` is built once per `(model, key)` pair and bound via `ai_model.set_cloud_mode(True, cloud_provider=cached_prov)`, which closes the old provider and re-runs `_detect_provider` to return the cloud provider.
4. Provider-level consent gate (`litellm_provider.py:128-138,183-201,230-250,286-302`) — even if the UI wiring is bypassed, `generate_text`/`stream_text`/`analyze_image` each call `_assert_consent()` first and raise `PermissionError("Cloud transmission blocked: ... (INF-04, UI-04).")` when `user_consented` is `False` (the constructor default). `set_consent(bool)` flips the flag post-construction.
5. Revocation (three equivalent paths, all converge) — (a) toggle OFF → all three flags `False` + `st.rerun()`; (b) `Revoke Consent (Switch to Local)` button → all three flags `False` + `st.rerun()`; (c) `AiModel.set_cloud_mode(False)` (`local_llm.py:139-160`, idempotent WR-02 fast path) → `cloud_mode=False`, `close()` old provider, `_detect_provider()` returns a fresh local `LlamaCppProvider`. The UI else-branch additionally `close()`s and clears the cached cloud provider so no consented client lingers in session state, then shows `🔒 Local Mode Active (100% on-device, zero network egress)`.

### Provider Selection — `_detect_provider` (explicit, no silent fallback)

1. Contract (`local_llm.py:162-179`) — selection is a pure function of `(cloud_mode, cloud_provider)`; there is no health-triggered cross-boundary fallback.
2. `cloud_mode=True` branch (`local_llm.py:169-175`) — return the injected `cloud_provider` when present; otherwise construct `GroqProvider()`, return it iff `check_health().status == "healthy"`, else `close()` it and fall through. No local construction happens on this branch.
3. `cloud_mode=False` branch (`local_llm.py:177-179`) — unconditionally `return LlamaCppProvider()` without probing cloud health or credentials. A dead local server therefore surfaces as an offline/unhealthy status in the sidebar badge (`main.py:251-279`), never as an automatic cloud escalation.
4. `check_health` re-probe (`local_llm.py:181-201`) stays within the same mode — it re-runs `_detect_provider()` (same `cloud_mode`) and swaps only when the same-mode re-probe is healthy.
5. Idempotent switching (`local_llm.py:139-160`) — `set_cloud_mode` returns early when `(mode, provider)` are unchanged (local+local, or cloud+identical provider object), avoiding `close()`/re-detection churn (WR-02); otherwise it sets the flag, stores an injected `cloud_provider`, `close()`s the old provider, and re-detects + refreshes `model_name`.

### Local Endpoint Guard — loopback SSRF protection (SEC-01)

1. Guard location (`llama_cpp_provider.py:40-57`) — every `LlamaCppProvider` construction (default `http://127.0.0.1:8080`, plus any injected `base_url`) passes scheme normalisation → `urlparse` hostname extraction → `localhost`-literal or `ipaddress.is_loopback` check → `ValueError` unless `allow_remote=True`.
2. Accepted by default: `127.0.0.1`, any `127.0.0.0/8` address (`127.0.1.1`, `127.0.0.2`), `localhost`, `::1`, scheme-less `127.0.0.1:8080` (normalised to `http://` before parsing). Rejected by default: any non-loopback hostname/IP (public IPs, LAN hosts, DNS names that are not `localhost`).
3. Opt-in escape hatch: `allow_remote=True` permits remote hosts for explicitly configured remote-server deployments; no production or UI path passes it today — all `_detect_provider` constructions use the loopback default.
4. Server-side complement: `llama-server` binds `--host 127.0.0.1` (`docs/RUNBOOK.md:95,106,115`, `docs/LOCAL_INFERENCE.md` flags), so even a misconfigured client cannot reach an externally bound server that does not exist.
5. Tests: `tests/test_llama_cpp_provider.py:262-292` — rejected non-loopback, allowed-with-flag, accepted loopback variants.

### Egress Transparency (badges / chips / banner)

1. Pipeline banner (`main.py:537-540`) — `caps.is_local` (`ProviderCapabilities.is_local`, `model_provider.py:32-37`) selects `🔒 100% Offline Local Pipeline · Qwen3-VL ({model}) + MiniLM-L6-v2 + LanceDB` vs `☁️ Cloud Inference · {model} (Embeddings & LanceDB 100% Local)`; the cloud variant always carries the stays-local qualifier.
2. Live per-answer badge (`main.py:686-690`) — immediately after `st.write_stream`, `caps.is_local` selects `🔒 Generated locally on-device (zero network egress).` vs `☁️ Generated via external cloud provider ({caps.model_name}) with user consent.`
3. Replay badges (`main.py:576-582`) — persisted `is_cloud`/`model_name` per assistant turn re-render the same two captions on every rerun; `is_cloud is False` → local caption, truthy → cloud caption naming the stored model.
4. Turn persistence (`main.py:726-748`) — every assistant turn stores `is_cloud: not caps.is_local` + `model_name: caps.model_name` alongside `sources`/`verification`/`snippets` (both success and interruption paths), so replay never re-derives locality from the CURRENT mode.
5. Evidence chips + drawer (`main.py:596-618` replay, `main.py:703-724` live) — `**Sources:** [E{rank}] {filename} (p. {page}), ...` caption plus `🔍 Cited Evidence & Source Context` expander iterating `snippets_data` with `[E{rank}] filename (p. N, score)` headers, quoted content, and optional `📐 Region` bbox caption. Provenance rendering is identical in both modes.
6. Model badge (`main.py:251-265`) — `st.status` label shows `🟢 Inference: Local ({model})` vs `☁️ Inference: Cloud ({model})`, so the active egress posture is visible before any question is asked.

### InferenceGate Single-Active-LLM Flow (concurrency control)

1. Gate primitive (`local_llm.py:26-90`) — class-level `threading.RLock` (`_lock`) + `_active_threads` counter under `_state_lock`. `acquire(timeout)` blocks on the RLock then increments; `release()` releases and decrements (swallows stray `RuntimeError`); `is_locked()` reads the counter; `hold(timeout)` context manager raises `TimeoutError("InferenceGate acquisition timed out after ...")` on failure and always releases.
2. QA streaming path (`local_llm.py:285-298`) — after prompt assembly, `ask_a_question_from_pdf_stream` calls `InferenceGate.acquire(timeout=60.0)`; on failure it yields `"⚠️ System is busy processing another inference request. Please retry in a moment."` and returns WITHOUT calling the provider; on success it `yield from provider.stream_text(...)` inside `try/finally: InferenceGate.release()`. The provider here is whichever `_detect_provider` selected — gate semantics are mode-independent.
3. Non-streaming path (`local_llm.py:300-326`) — `AiModel.generate_text(..., timeout=60.0)` wraps `provider.generate_text` in `with InferenceGate.hold(timeout=timeout)`, so contention raises `TimeoutError` to the caller.
4. Summarization path (`summarizer.py:387-394`) — `summarize_document` wraps the entire fast-path-or-map-reduce generation block in `with InferenceGate.hold(timeout=120.0)` (longer timeout for multi-call map-reduce); every `provider.generate_text` inside map/consolidate/reduce therefore executes under the same single-active-LLM lock, strictly sequentially.
5. Reentrancy note — because the underlying lock is an RLock, nested `hold` on the SAME thread re-enters (covered in `tests/test_concurrency_lock.py`); cross-thread contention blocks to timeout. The busy-yield (stream) vs raise (non-stream) asymmetry is intentional: interactive chat degrades to a retry notice, programmatic callers get an exception.

### Telemetry Pipeline (TTL-cached probes → sidebar widget → profiler artifact)

1. TTL cache (`resource_telemetry.py:25-30`) — `_GPU_CACHE_TTL_SECONDS = 5.0`, `_LAST_GPU_INFO`, `_LAST_GPU_SAMPLE_TIME` (monotonic), `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`.
2. GPU probe (`resource_telemetry.py:33-95`) — `get_gpu_memory_info(force_refresh=False)`: fast path returns the cached dict copy when `(now - _LAST_GPU_SAMPLE_TIME) < TTL`; on expiry, takes `_SAMPLING_LOCK` and double-checks the timestamp before spawning `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits` (`timeout=2.0`), parses the first line into `{total_mb, used_mb, free_mb, utilization_pct}`; returns `None` on `FileNotFoundError`/`SubprocessError`/`ValueError`/`IndexError` (headless/CI) with a `logger.debug`. Concurrent reruns inside one TTL window therefore spawn zero subprocesses; concurrent expiry spawns exactly one.
3. Process probe (`resource_telemetry.py`) — `get_process_memory_info` reads `psutil.Process().memory_info()` into `{rss_mb, vms_mb}`; returns zeros on missing `psutil` or any error.
4. Latency registry (`resource_telemetry.py:99-181`) — `LatencyTracker(stage_name)` context manager times with `perf_counter`, records `elapsed_ms`/`success`/`error` into thread-safe `_LATENCY_HISTORY` capped at `MAX_STAGE_HISTORY=200`; `track_stage`/`record_stage_latency` are convenience wrappers; `get_latency_history`/`clear_latency_history` copy/clear under `_LATENCY_LOCK`; `get_system_telemetry_snapshot` aggregates per-stage `{count, avg_ms, min_ms, max_ms}` with an ISO timestamp. `clear_gpu_cache()` (`resource_telemetry.py:211`) resets the TTL state for tests/ops.
5. Live widget (`main.py:508-535`) — sidebar `with st.expander("📊 System Telemetry & VRAM")` calls both probes + `doc_store.count_documents()`/`count_summaries()` every rerun; GPU reads hit the TTL cache, so chat keystrokes no longer fork `nvidia-smi` per rerun. GPU present → `st.metric("GPU VRAM", ...)` + `st.progress(used/total)` + tiered caption (🟢 `<3500` / 🟡 `3500–3800` / 🔴 `>3800`); GPU absent → `ℹ️ CPU-only Mode` caption; always shows `Process RAM (RSS)` caption and `Persistent Cache: {docs} docs · {sums} summaries` caption.
6. Offline profiler (`scripts/profile_resources.py:94-342`) — `run_resource_profile()` executes 6 stages against `tests/data/corpus/` and writes `.planning/research/RESOURCE_PROFILE.json`.
7. Tests: `tests/test_resource_telemetry.py:49-70` — TTL caching (second call within window returns cached copy without re-spawning subprocess), `force_refresh` bypass, subprocess fallbacks.

### Multi-Tier Cache Invalidation

1. Tier 1 — session (`main.py` summary tab + Clear All) — `st.session_state[f"summary_{doc_id}_{profile}"] = summary_obj.model_dump()` on generate; read-first on display; Clear All deletes every `summary_*` key plus resets `doc_ids`/`indexed_files`/`document_metadata`/`local_embedding`/`hybrid_retriever`/`chat_history` and closes the retriever.
2. Tier 2 — disk extraction cache (`models.py`, upload persist block) — best-effort `.cache/<sha256>/docling-1000-200-v1/{pages,chunks,manifest}.json` write per upload (`STORE-03`); `OSError` → `st.warning`, never fatal; keyed by SHA-256 + `CONFIG_VERSION`, so chunking/config changes naturally miss.
3. Tier 3 — SQLite summary cache (`summarizer.py:331-336`, `doc_store.py:425-514`) — `summarize_document` returns `DocStore.get_summary(sha256, profile, model_version=provider.model_name)` immediately on hit (zero provider calls, zero gate acquisition) unless `force_refresh=True`; key is `(sha256, profile)` (`UNIQUE` in `doc_store.py:84`); `model_version` is a read-time invalidation predicate (`doc_store.py:494-499` returns `None` on mismatch → regenerate + `ON CONFLICT(sha256, profile) DO UPDATE` upsert in `save_summary`); `list_summaries_for_doc`/`delete_summaries_for_doc` scope by `doc_id`; `delete_document` cascades via FK.
4. Tier 4 — vector persistence (`hybrid_retriever.py:110-124,149-187`) — LanceDB `chunks` table when available (upsert via `merge_insert` on `chunk_id`); otherwise `fallback_store.json` under `data/lancedb/` rewritten on `close()` and reloaded in `_load_fallback_store`; `delete_document(doc_id)` evicts from both mirror and table.
5. Telemetry GPU TTL as a fifth, time-based tier — `resource_telemetry.py:25-60` (5.0s monotonic window, double-checked sampling, `force_refresh` bypass, `clear_gpu_cache` reset); covered in `tests/test_resource_telemetry.py:49-70`.

### Grounded QA Flow (question → gated stream → validated citations → badges/drawer)

1. Bounded history + contextualized query (`main.py:641-651`) — new user turn appended via `append_chat_turn` (turn-cap enforced immediately); `history_to_pass = chat_history[:-1][-10:]`; `search_query = last_user_msg + " " + prompt` so follow-ups retrieve correctly.
2. Single shared retrieval (`main.py:653-672`, always local) — `active_retriever = hybrid_retriever or local_embedding`; if it exposes `search_hybrid`, one call `search_hybrid(search_query, k=5)` returns the canonical `RetrievalResult`; `sources = retrieval_res.source_labels()` plus `snippets_data = [s.model_dump() for s in retrieval_res.snippets]`. Legacy `search(k=10)` branch only applies to retrievers without `search_hybrid`.
3. Hybrid fusion inside `HybridRetriever.search_hybrid` (`hybrid_retriever.py:511-616`) — embed query via CPU embedding fn → `search_dense` (LanceDB vector search, `candidate_pool = max(k*2, 10)`) + `search_fts` (LanceDB FTS → pure-Python BM25 fallback) → `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` → top-k mapped to `EvidenceSnippet` items (with `rank`, `dense_rank`, `fts_rank`, `score=RRF`, `bbox` rehydrated from `bbox_json`) → frozen `RetrievalResult(query, snippets, total_candidates, search_mode)`.
4. Shared-identity gated generation (`main.py:677-683` → `local_llm.py:231-298`) — the same `retrieval_result` object is passed to `ask_a_question_from_pdf_stream(..., retrieval_result=retrieval_res)`; the LLM uses `retrieval_result.formatted_evidence()` (`[E1] (file, p. N)` blocks) directly under `InferenceGate.acquire(60s)`; the in-LLM fallback (`local_llm.py:234-269`) only runs when no pre-computed result is supplied. Generation egresses ONLY when the active provider is a consented cloud provider; the local path speaks loopback HTTP guarded by the SEC-01 constructor check.
5. Bounded grounded prompt + stream (`local_llm.py:273-298`) — `assemble_grounded_messages` wraps context in `<document_context>` with the `[E1]`/`[E2]` citation rules and abstention sentence (`prompt_budget.py:13-23`), XML sanitization and token budgeting against the provider's `context_window` (local 4K default vs cloud 128K–200K per `KNOWN_CONTEXT_WINDOWS`); `provider.stream_text(...)` yields tokens; `st.write_stream` renders and returns the full string (`main.py:684`).
6. Citation validation (`main.py:693` → `local_llm.py:328-346` → `citation_validator.py`) — `ai_model.validate_response(full_response, retrieval_res)` resolves the active result (explicit arg wins, else `last_retrieval_result`), runs `validate_citations`: empty text → `is_valid=False, precision=0.0`; abstention text + zero citations → `is_valid=True, precision=1.0, abstention_detected=True`; abstention + citations → invalid; otherwise precision = `valid_ranks / total_claimed` with `is_valid = precision >= 0.95` against `len(retrieval_result.snippets)` as the rank bound.
7. Badge + drawer render (`main.py:686-736`, replay `main.py:572-618`) — egress badge first (`☁️` vs `🔒`), then abstention (`ℹ️ Explicit abstention`) / valid (`✅ Verified Grounding (P% citation precision)`) / invalid (`⚠️ Unverified Citations (P%)`). Evidence chips `[E{rank}] filename (p. N)` plus `🔍 Cited Evidence & Source Context` expander iterate `snippets_data`. The turn is appended via `append_chat_turn` (re-bounding to 50, persisting `is_cloud` + `model_name`); the exception path records an interruption note with `verification: None`.

### Summarization Flow (profile → gated map-reduce → cache → summary tab)

1. Tab wiring + selection (summary tab, `main.py:752+`) — `tab_summary` shows selectbox over `sorted(indexed_files)`, resolves `doc_id`/`sha256` from `document_metadata` with `doc_store.get_document` fallback, radio over the five `profile_map` keys, `Generate Summary` button (disabled when inference unhealthy) + `Force re-generate` checkbox. Per-doc/profile session key `summary_{doc_id}_{profile}`.
2. Tier-3 cache check (`summarizer.py:331-336`) — `summarize_document(doc_id, sha256, profile, force_refresh)` validates `profile ∈ VALID_SUMMARY_PROFILES`, reads `provider.get_capabilities().model_name` as `model_version`, and returns `DocStore.get_summary(sha256, profile, model_version=model_version)` immediately on hit (zero provider calls, zero gate acquisition). A model switch (local ↔ cloud) therefore invalidates cached summaries via `model_version` mismatch.
3. Page resolution (`summarizer.py:338-378`) — if `pages is None`, reconstructs `Page` records from `chunks` arg or `doc_store.get_chunks_for_doc(doc_id)` grouped by page; if caller-supplied `Page` records lack `page_text`, enriches from stored chunks. Filters to pages with non-blank `page_text`; raises `ValueError` when none is extractable.
4. Fast path vs map-reduce under gate (`summarizer.py:385-394`) — `total_tokens = Σ estimate_tokens(page_text)`; `≤ FAST_PATH_TOKEN_LIMIT (2500)` → `_summarize_single_pass`; above → `_summarize_map_reduce`; the dispatch executes inside `with InferenceGate.hold(timeout=120.0)`.
5. Map stage — `_bundle_pages(pages, MAX_BATCH_TOKENS=2000)` packs sequential pages by `estimate_tokens`; each batch is rendered as `--- Page N ---` sections with `sanitize_xml_boundary` and sent through `MAP_PROMPT_TEMPLATE` (page-range + `(p. X)` citation mandate) with `max_tokens=800, temperature=0.2`. Executes strictly sequential to respect the single-active-LLM constraint.
6. Consolidation + reduce — intermediates joined with `\n\n---\n\n`; if combined tokens exceed `FAST_PATH_TOKEN_LIMIT` and there are >3 intermediates, two half-consolidation `generate_text` calls (`max_tokens=1000`) precede the final `REDUCE_PROMPT_TEMPLATE` synthesis under the profile system prompt (`max_tokens=1500, temperature=0.2`).
7. Reference extraction + persist (`summarizer.py:396-418`) — `extract_page_references(summary_text, max_page=...)` parses `(p. N)`/`(Page N)` via regex, dedups, sorts, clamps; builds `SummaryResult(summary_id=summ_*, ..., cached=False)`; `doc_store.save_summary(result)` upserts on `ON CONFLICT(sha256, profile)`.
8. Display — prefers the session value, falls back to `doc_store.get_summary(selected_sha, selected_profile)` without model-version pin; cached rows show `⚡ Loaded from persistent SQLite cache (DocStore v3)`, fresh ones `✨ Generated fresh with {model_version}`; summary markdown renders verbatim, then `📄 Referenced Source Pages` expander lists `Page N` chips + `created_at`.

**State Management:**
- `st.session_state` (per-browser-session, survives full-script reruns): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict` (filename → `doc_id`/`sha256`/`upload_time`/`pages`/`chunks`), `local_embedding: LocalEmbedding | None` (CPU embed-fn holder), `hybrid_retriever: HybridRetriever | None` (sole retrieval index), `chat_history: list` of `{role, content, sources, verification, snippets, is_cloud, model_name}` capped at `MAX_CHAT_TURNS=50` — initialised in `main.py:60-76`; cloud keys `cloud_mode` / `cloud_mode_toggle` / `user_consented` / `cloud_provider` / `cloud_model` / `cloud_api_keys` / `cloud_api_key` (`main.py:67-73`); cached cloud client `active_cloud_provider` + `_cached_cloud_model` / `_cached_cloud_key` (`main.py:221-235`); plus dynamic `summary_{doc_id}_{profile}` keys. `Clear All` closes the retriever, resets index/chat keys, deletes every `summary_*` key, calls `st.rerun()` (cloud flags are NOT cleared by Clear All — revocation is the separate `Revoke Consent` path).
- `st.cache_resource` (per-server-process singleton): `load_ai_model()` (`main.py:84-92`) constructs `AiModel` once; every rerun/session reuses it, and `set_cloud_mode(True/False)` mutates the shared instance's routing per the current session's flags. The embedding model is NOT cached — `LocalEmbedding`/`SentenceTransformer` lives in session state, so each browser session loads its own copy.
- `AiModel` routing state: `cloud_mode: bool` + `cloud_provider: BaseModelProvider | None` + `provider: BaseModelProvider` (the resolved active provider) + `model_name` (`local_llm.py:117-126`); transient grounding state `last_retrieval_result` (set on every `ask_a_question_from_pdf_stream`, `local_llm.py:271`) and `last_verification_result` (set on every `validate_response`, `local_llm.py:345`). Process-singleton caveat documented in `local_llm.py:93-101` — always pass an explicit `retrieval_result` to `validate_response` to avoid cross-session contamination.
- `LiteLLMProvider` consent state: `user_consented: bool` (constructor default `False`, flipped via `set_consent`) + resolved `api_key` + `model_name`/`timeout`/`num_retries` (`litellm_provider.py:104-126`); stateless otherwise (`close()` is a no-op).
- `LlamaCppProvider` endpoint state: `base_url` (loopback-validated at construction) + `allow_remote` flag (`llama_cpp_provider.py:59-62`); `httpx.Client` with `connect=2.0/read=60.0/write=10.0/pool=5.0` timeouts (`llama_cpp_provider.py:63-67`).
- `InferenceGate` class state (`local_llm.py:34-36`): `_lock: RLock` + `_active_threads: int` under `_state_lock` — the only cross-session mutable concurrency state besides the telemetry TTL cache; every other store (`VectorIndex` vectors/documents, `HybridRetriever` handles, `Summarizer` refs) is instance-scoped.
- Telemetry TTL state (process-shared, lock-protected): `_LAST_GPU_INFO` + `_LAST_GPU_SAMPLE_TIME` under `_GPU_CACHE_LOCK`/`_SAMPLING_LOCK` (`resource_telemetry.py:26-30`); reset via `clear_gpu_cache()`.
- On-disk state: SQLite `data/documents.db` (DocStore incl. `document_summaries`), LanceDB `data/lancedb/` (or `fallback_store.json` there without LanceDB), `.cache/<sha256>/docling-1000-200-v1/`.

## Key Abstractions

**Chunk (unit of retrieval):**
- Purpose: Text plus provenance metadata threaded through every layer.
- Examples: produced in `docling_reader.py` / `pdf_reader.py`, validated as `models.py:Chunk`, stored in LanceDB rows (`hybrid_retriever.py:298-311`) and mirrored in `vector_index.py`, restored from `doc_store.py`.
- Pattern: Frozen Pydantic model — `content`, `filename`, `page`, `chunk_id`, `doc_id` required; `char_start`/`char_end`/`bbox`/`extraction`/`embedding_model` optional. `Chunk.chunk_id` is the LanceDB upsert key.

**RetrievalResult + EvidenceSnippet (shared prompt/UI/validation contract, RETR-04):**
- Purpose: Single immutable container consumed identically by LLM prompt assembly, UI citation rendering, and citation validation — eliminates double retrieval and prompt/citation/validation drift. Built entirely on the local path in both modes.
- Examples: constructed in `hybrid_retriever.py:611-616` and `local_embedding.py:104-109`; consumed in `local_llm.py` (`formatted_evidence`), `main.py:660` (`source_labels`), `main.py:670-672` (`model_dump` snippets), `citation_validator.py` (rank bound).
- Pattern: Frozen Pydantic models. `EvidenceSnippet` carries `content/doc_id/filename/page/chunk_id/score/rank/dense_rank/fts_rank/extraction/char_start/char_end/bbox` (`models.py`). `RetrievalResult` carries `query/snippets/total_candidates/search_mode ∈ {hybrid, dense, fts, fallback}` with `formatted_evidence()` (`[E1] (name, p. N)` blocks) and `source_labels()` (deduped `filename (p. N)` chips).

**Cloud-mode triple (session flags + AiModel routing + provider consent):**
- Purpose: Separate the three layers of the egress decision so UI state, routing state, and transmission enforcement can each be reasoned about and tested independently.
- Examples: flags in `main.py:67-73` + toggle/dialog/select/revoke in `main.py:108-245`; routing in `local_llm.py:139-179` (`set_cloud_mode`, `_detect_provider`); enforcement in `litellm_provider.py:128-138` (`set_consent`, `_assert_consent`); covered in `tests/test_cloud_privacy.py` (state-transition workflow, idempotent switching, key lookup) and `tests/test_litellm_provider.py` (consent gate, grant flow).
- Pattern: UI owns `cloud_mode`/`user_consented` booleans; `AiModel` owns `cloud_mode` + provider pointer and NEVER transmits itself; `LiteLLMProvider` owns `user_consented` and refuses to transmit without it. All three must agree for egress; any layer can veto (dialog cancel, `set_cloud_mode(False)`, missing consent).

**Loopback-guarded endpoint (SSRF boundary, SEC-01):**
- Purpose: Make the local inference transport incapable of becoming an SSRF primitive even if a future caller passes an attacker-influenced `base_url`.
- Examples: guard in `llama_cpp_provider.py:40-57`; server bind `--host 127.0.0.1` in `docs/RUNBOOK.md:95,106,115`; tests in `tests/test_llama_cpp_provider.py:262-292`.
- Pattern: Constructor-time validation with explicit opt-in (`allow_remote=True`) — deny-by-default, not audit-after-the-fact. Remote deployments must pass the flag deliberately, which keeps the egress exception visible at the call site.

**InferenceGate (single-active-LLM lock):**
- Purpose: Enforce the 4 GB VRAM invariant (only one LLM/VLM resident operation at a time) across QA streaming, direct generation, and summarization without a central scheduler. Mode-independent.
- Examples: acquired in `local_llm.py:285` (stream), held in `local_llm.py:320` (`generate_text`), held in `summarizer.py:388` (map-reduce, 120s timeout); verified in `tests/test_concurrency_lock.py` and `scripts/profile_resources.py:249-256`.
- Pattern: Class-level `threading.RLock` + counter with `acquire(timeout)/release/is_locked/hold(timeout)` API; stream path degrades to a busy-retry yield, non-stream paths raise `TimeoutError`.

**TTL-cached telemetry snapshot (VRAM/RAM/latency contract, TEL-01):**
- Purpose: One call capturing everything the widget and profiler need without importing Streamlit and without forking `nvidia-smi` per rerun.
- Examples: produced in `resource_telemetry.py` (`get_gpu_memory_info` TTL path `resource_telemetry.py:45-55`, `get_system_telemetry_snapshot`), consumed live in `main.py:510-535`, aggregated to JSON in `scripts/profile_resources.py:289-331`, documented in `docs/RUNBOOK.md:157-161`.
- Pattern: Plain dict `{timestamp, gpu: {...}|None, process: {rss_mb, vms_mb}, stages: {stage: {count, avg_ms, min_ms, max_ms}}}`; `LatencyTracker` is both the measurement instrument and the registry writer; the GPU slice is TTL-cached (5.0s, `force_refresh` bypass) while latency/process slices stay live.

**CitationVerificationResult (grounding verdict):**
- Purpose: Deterministic, LLM-independent verdict rendered as badges and persisted per turn.
- Examples: produced in `citation_validator.py`, stored via `local_llm.py:344-345` (`last_verification_result`), persisted in `chat_history` (`main.py:726-736`), rendered in `main.py` badges/drawers.
- Pattern: Frozen Pydantic model — `is_valid`, `precision ∈ [0,1]`, `total_citations`, `valid_citations`/`hallucinated_citations` tags, `cited_ranks`, `abstention_detected`, `message`. Threshold `precision >= 0.95`.

**SummaryResult + SummaryProfile (cached synthesis contract):**
- Purpose: Profile-shaped markdown plus machine-readable page references and cache identity.
- Examples: produced in `summarizer.py:403-413`, persisted via `doc_store.py:425-463`, read in `summarizer.py:332-336` and the summary tab, rendered with cache/fresh captions.
- Pattern: `SummaryProfile = Literal["overview","detailed","study_notes","tables_figures","findings"]`, `VALID_SUMMARY_PROFILES` tuple (`models.py`); `SummaryResult` carries `summary_id (summ_*)`, `doc_id (doc_*)`, `sha256`, `profile`, `summary_text`, `page_references: list[int]`, `created_at`, `model_version`, `cached`. SQLite row mirrors every field with `page_references_json` (`doc_store.py:73-94`).

**Unified sole retrieval index:**
- Purpose: One `search_hybrid` call spans all uploaded documents; exactly one object owns ranking state.
- Examples: `main.py:431-439` (incremental `index_chunks` per file into the session `HybridRetriever`), chat header chunk aggregation (`main.py:564`), `main.py:656` (`active_retriever = hybrid or local` with hybrid preferred).
- Pattern: Append-only growth with `chunk_id` upsert dedup (`hybrid_retriever.py:269-282`); no per-document isolation; deletion only via `delete_document(doc_id)` or full Clear All reset. Summarization is the exception: it scopes to one `doc_id` via DocStore chunk lookup, never via the retriever.

**RRF fusion:**
- Purpose: Combine dense semantic ranking and BM25 keyword ranking without score calibration.
- Examples: `hybrid_retriever.py:31-76` (`compute_rrf`, `DEFAULT_RRF_K = 60`), wired in `hybrid_retriever.py:580`.
- Pattern: `RRF(d) = Σ 1/(k_rrf + rank_m(d))`; returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score; `search_mode` records which modalities contributed (`hybrid_retriever.py:571-578`).

**Token-stream generator (gate-held, provider-agnostic):**
- Purpose: Decouple token production (local or consented cloud provider) from rendering (Streamlit) while holding VRAM exclusivity for the whole stream duration.
- Examples: `local_llm.py:211-298` (producer holds `InferenceGate` from before first token until generator exhaustion), `main.py:677-684` (consumer via `st.write_stream`).
- Pattern: Generator yielding `str` fragments; gate is released in the generator's `finally`, so early abandonment still unlocks. Summarization uses the non-streaming sibling `provider.generate_text` under `hold` instead.

**Map-reduce page bundling:**
- Purpose: Fit arbitrarily long documents into a bounded context window without parallel LLM residency.
- Examples: `summarizer.py` (`_bundle_pages`, `_summarize_map_reduce`).
- Pattern: Greedy sequential packing by `estimate_tokens` against `MAX_BATCH_TOKENS`; map → optional half-consolidation → reduce, every stage carrying `(p. X)` forward, all inside one `InferenceGate.hold`. Cloud models get larger windows via `KNOWN_CONTEXT_WINDOWS`, but the bundling budgets stay fixed.

**Bounded chat history (turn cap + token budget):**
- Purpose: Cap unbounded session memory growth and keep every prompt inside the provider context window.
- Examples: `main.py:38` (`MAX_CHAT_TURNS = 50`), `main.py:543-549` (`append_chat_turn`), `prompt_budget.py:131-152` (`bound_chat_history`), `prompt_budget.py:105-122` (oldest-first token truncation), `main.py:642` (`history_to_pass = chat_history[:-1][-10:]` retrieval window).
- Pattern: Hard tail-slice to 50 turns with orphan-assistant pruning on every append; soft token truncation per request; narrow 10-turn window actually sent for history-contextualized retrieval.

## Entry Points

**Streamlit app (sole runtime entry):**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local, per `docs/RUNBOOK.md:127-138`); dev container `postAttachCommand` in `.devcontainer/devcontainer.json`; Streamlit Community Cloud.
- Responsibilities: Everything user-facing — `st.set_page_config` first (`main.py:44-49`); session-state init incl. cloud keys; cached model load; Privacy & Provider Mode block; sidebar upload/index loop; telemetry widget + pipeline banner; `st.tabs` chat + summarizer loops.

**Privacy & Provider Mode block (consent-gated egress switch):**
- Location: `main.py:108-245`
- Triggers: Rendering the sidebar on every rerun; `st.toggle("Enable Cloud Inference")` flip; `I Consent & Enable Cloud` / `Cancel (Keep 100% Local)` / `Revoke Consent (Switch to Local)` clicks; provider selectbox / session-key edits.
- Responsibilities: Owns the `local → dialog → consented cloud → revocation` transitions, the `CLOUD_PROVIDER_OPTIONS` selectbox, memory-only session API keys, the cached `LiteLLMProvider` lifecycle, and the per-rerun `ai_model.set_cloud_mode(True/False)` sync.

**Chat tab (grounded QA, mode-aware badges):**
- Location: `main.py:558-749` (`with tab_chat:`)
- Triggers: Selecting `💬 Ask Your Document`; submitting `st.chat_input` (`main.py:627-630`, disabled until an index exists and inference is healthy).
- Responsibilities: History replay with egress + verification badges/drawer, single shared `search_hybrid(k=5)` (always local), gate-held `ask_a_question_from_pdf_stream` + `st.write_stream`, `validate_response`, live badge/drawer, `append_chat_turn` persisting `is_cloud`/`model_name` (bounded).

**Summary tab (grounded summarization):**
- Location: `main.py:752+` (`with tab_summary:`)
- Triggers: Selecting `📑 Document Summarizer`; pressing `Generate Summary`.
- Responsibilities: Document selectbox, 5-profile radio, force-refresh flag, gate-held `Summarizer(provider=ai_model.provider, doc_store=doc_store).summarize_document(...)` under `st.status`, 4-tier cache display with page-reference expander.

**On-the-fly Q&A fallback (legacy, not exercised by UI):**
- Location: `local_llm.py:234-238`
- Triggers: Calling `ask_a_question_from_pdf_stream(pdf_path, prompt)` with `local_embedding=None` and no `retrieval_result`.
- Responsibilities: Self-contained RAG — builds `PdfReader` → `LocalEmbedding` inline, then retrieval + generation. `main.py` always passes an existing retriever and `pdf_path=""`, so this path is dormant in production.

**Benchmark + profiler scripts:**
- Location: `scripts/benchmark_baseline.py` (174), `scripts/profile_resources.py:94-342`
- Triggers: Manual invocation (`python scripts/profile_resources.py`).
- Responsibilities: Baseline retrieval/generation benchmarking; 6-stage VRAM/latency/cache/concurrency audit writing `.planning/research/RESOURCE_PROFILE.json` (see STRUCTURE.md).

**Runbooks (operator entry points):**
- Location: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`, `docs/EVALUATION.md`
- Triggers: Fresh install, server launch, incident triage, release sign-off.
- Responsibilities: `RUNBOOK.md` is the install→launch→operate→troubleshoot sequence; `LOCAL_INFERENCE.md` is the VRAM-budget + model-acquisition reference for the 4 GB envelope; `EVALUATION.md` is the release acceptance record (test counts, pass rate, lint status).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom per interaction; long work (model load, extraction, embedding, summarization) blocks and is masked with `st.status` spinners. Token streaming is incremental rendering, not background threading. Map-reduce is deliberately sequential (no `asyncio`/threads). Cross-thread primitives are exactly two: `InferenceGate` (`threading.RLock` + counter, `local_llm.py:34-36`) and the telemetry locks (`_LATENCY_LOCK`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`, `resource_telemetry.py:22-30`).
- **Single-active-LLM invariant:** At most one gate-held inference op at a time (QA stream 60s timeout, `generate_text` 60s, summarizer 120s). Stream contention yields a retry notice; non-stream contention raises `TimeoutError`. RLock reentrancy means same-thread nesting does not deadlock — cross-thread nesting blocks.
- **Ingestion-stays-local invariant:** Extraction, OCR, CPU embeddings, LanceDB/SQLite/`.cache` writes, and visual analysis perform zero network egress in BOTH modes. Enforced structurally (none of `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `local_embedding.py`, `hybrid_retriever.py`, `doc_store.py` imports any network client), at the call site (`main.py:404-417` `local_vlm_provider` filter passes a provider to `VisualAnalyzer` ONLY when `is_local`), inside the analyzer (rejects non-local providers even on direct pass), and by test (`tests/test_cloud_privacy.py::test_local_only_ingestion_and_indexing_invariant` fails the suite on any `socket.create_connection` during embed/index/search; `test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode` asserts `analyze_image` is never invoked with a cloud provider).
- **Loopback-only local transport (SEC-01):** `LlamaCppProvider` refuses non-loopback `base_url` unless `allow_remote=True` (`llama_cpp_provider.py:53-57`); the only `httpx` client in the local path therefore cannot be redirected at internal or external hosts by accident. `allow_remote` is never set in production wiring — remote-server deployments must opt in explicitly at the construction call site.
- **No silent fallback across the egress boundary:** `_detect_provider` never routes local→cloud on health failure and never routes cloud→local silently either — mode changes happen ONLY through `set_cloud_mode` (UI toggle/dialog/revoke path). A dead local server surfaces as `⚠️ Inference: Offline (setup required)` (`main.py:273-279`); a missing cloud key surfaces as `unreachable` from `LiteLLMProvider.check_health` (`litellm_provider.py:140-163`).
- **Consent-before-transmission:** No document-derived string reaches `litellm.completion` unless `LiteLLMProvider.user_consented` is `True` at call time; the default is `False` and the UI can only set the provider-level flag to `True` through the consented branch (`user_consented=True` at construction, `main.py:228-232`). Revocation destroys the cached provider object.
- **VRAM envelope:** Embeddings pinned to CPU (`device="cpu"` in `local_embedding.py`); only one LLM/VLM active at a time via `InferenceGate`; local 4K context default with 1024 reserved output tokens (`prompt_budget.py:57-77`); cloud windows are larger (128K–200K via `KNOWN_CONTEXT_WINDOWS`) but summarizer budgets (`FAST_PATH_TOKEN_LIMIT=2500`, `MAX_BATCH_TOKENS=2000`, map `800` / reduce `1500` / consolidate `1000` token caps) keep every provider call bounded; telemetry widget enforces operational awareness with 3.5/3.8 GB alert tiers (`main.py:525-530`); full allocation table (~3,260 MB peak vs 4,096 MB ceiling) in `docs/LOCAL_INFERENCE.md:7-19`.
- **Global state:** `st.cache_resource`-cached `AiModel` + active provider shared across sessions (`main.py:84-92`); per-session `LocalEmbedding` + `SentenceTransformer` + `HybridRetriever` + `VectorIndex` mirror + cloud flags/keys/cached cloud provider in `st.session_state`. `AiModel.last_retrieval_result` / `last_verification_result` are process-shared transient state — pass explicit `retrieval_result` per call (`local_llm.py:93-101`). `AiModel.cloud_mode`/`cloud_provider` on the shared instance reflects the LAST session that synced — per-turn `is_cloud`/`model_name` persistence is what keeps replay truthful. `InferenceGate._lock/_active_threads` is process-shared concurrency state (`local_llm.py:34-36`); the telemetry TTL cache (`_LAST_GPU_INFO`/`_LAST_GPU_SAMPLE_TIME`) is process-shared read-mostly state resettable via `clear_gpu_cache()`.
- **Secrets handling:** Session API keys live ONLY in `st.session_state.cloud_api_keys` (memory, never written to disk); `_resolve_api_key_for_model` (`litellm_provider.py:39-85`) resolves per-provider-prefix in order session-state dict → legacy `cloud_api_key` → `st.secrets[ENV_VAR]` → `os.environ[ENV_VAR]` (`GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). `.env` is gitignored; existence only is noted, contents never quoted.
- **Deterministic dependencies:** `requirements.txt` (17 lines, mixed `==`/`>=`) is the dev-friendly manifest; `requirements-lock.txt` (27 lines, all `==`, header-marked deterministic production lockfile) is the deploy manifest installed by the runbook (`docs/RUNBOOK.md:45-49`); `requirements-test.txt` (5 lines) holds test-only deps. Never add a runtime import without pinning it in `requirements.txt` AND freezing it in `requirements-lock.txt`.
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `main.py` → `litellm_provider.py` → `model_provider.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py` (gate-only import; `local_llm.py` never imports `summarizer.py`); `docling_reader.py` → `pdf_reader.py`; `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` have no project imports. `citation_validator.py` imports only `models.py`. `litellm_provider.py` imports only `model_provider.py` (+ optional `litellm`, guarded `None` fallback). `docs/*.md` import nothing.
- **Persistence quadruplicity:** Every indexed chunk exists in up to four places — session `HybridRetriever` mirror, LanceDB table or `fallback_store.json`, SQLite `chunks` table, `.cache/*.json`. The four are kept in sync only by the paired write in the upload block + persist block + CR-01 restore; direct writes to one store bypass the others.
- **Summary cache identity:** Key is `(sha256, profile)` (`UNIQUE` in `doc_store.py:84`); `model_version` is a read-time invalidation predicate, not part of the key (`doc_store.py:494-499`). Same bytes under a new filename re-point `doc_id` on upsert; `list_summaries_for_doc` on the old id then misses. `force_refresh=True` bypasses the read but still overwrites the row on save. Switching providers (local ↔ cloud) changes `model_version`, so summaries regenerate rather than serve cross-model stale rows.
- **Chat memory bounds:** Hard cap `MAX_CHAT_TURNS=50` turns in session state (`main.py:38`, `prompt_budget.py:131-152`); 10-turn window sent for retrieval contextualization (`main.py:642`); token-budget truncation per request (`prompt_budget.py:105-122`). Growing past 50 user+assistant turns evicts oldest-first; leading orphan assistant turns are pruned so history never starts mid-exchange.
- **Linear-scan fallback:** Without LanceDB, `VectorIndex.search` is O(n) per query; BM25 fallback is O(N·|Q|) with precomputed document frequencies (`hybrid_retriever.py:453-456`).

## Anti-Patterns

### Dual-write ingestion still split across two statements in the UI layer

**What happens:** The upload block calls `LocalEmbedding.get_embeddings` then `HybridRetriever.index_chunks(paragraphs, embeddings=...)` as two separate statements (`main.py:438-439`), and the mirror write into `VectorIndex` happens implicitly inside `index_chunks` (`hybrid_retriever.py:269-282`).
**Why it's wrong:** A failure between the embedding call and the index call, or any future path that calls one without the other, leaves the embed-fn holder and the sole index inconsistent; readers must know the mirror exists to reason about `count_chunks`.
**Do this instead:** Encapsulate the embed-then-index pair behind a single façade (e.g. `HybridRetriever.index_texts(chunks)` that embeds via its own `embedding_fn` internally), so callers cannot partially index. Reference the existing `embedding_fn` injection (`main.py:434-437`) as the consolidation point.

### Dormant `pdf_path` / on-the-fly indexing parameter

**What happens:** `ask_a_question_from_pdf_stream(pdf_path="", ...)` still accepts a path and can build a throwaway `PdfReader` + `LocalEmbedding` (`local_llm.py:234-238`); `main.py:677-683` always passes `pdf_path=""` with a live retriever.
**Why it's wrong:** Dead surface area that suggests an indexing path the UI never uses; risks confusion about which index answers a question.
**Do this instead:** Keep the parameter for backward compatibility (tests in `tests/test_local_llm.py` cover it) but treat `retrieval_result`/`local_embedding` as the canonical inputs — which is already the documented precedence in `local_llm.py:211-232`.

### Mode flags live on a process-shared AiModel while consent lives per-session

**What happens:** `AiModel.cloud_mode`/`cloud_provider` mutate the `@st.cache_resource` singleton (`main.py:237,245`), but `cloud_mode`/`user_consented`/API keys live in per-session `st.session_state`.
**Why it's wrong:** In multi-user deployments the last session to sync wins the process-wide routing, so one user's cloud opt-in can steer another session's generation path.
**Do this instead:** Keep the current single-user behavior, but treat per-turn `is_cloud`/`model_name` persistence (`main.py:726-748`) as the source of truth for replay, and never infer a past turn's locality from the current `AiModel.cloud_mode`. Any multi-user work must scope provider resolution per session instead of mutating the shared singleton.

## Error Handling

**Strategy:** Validate at boundaries, isolate per-file/per-page failures, degrade gracefully across backends, invalidate rather than serve stale, gate cloud transmission on explicit consent, refuse non-loopback local endpoints at construction, never hold the gate on failure paths.

**Patterns:**
- SSRF denial is a constructor `ValueError`, not a runtime surprise — non-loopback `base_url` without `allow_remote=True` fails fast in `LlamaCppProvider.__init__` (`llama_cpp_provider.py:53-57`) before any `httpx.Client` is built, so no socket ever opens to the rejected host.
- Consent denial is an exception, not a silent local fallback — unconsented `LiteLLMProvider.generate_text/stream_text/analyze_image` raises `PermissionError("Cloud transmission blocked: ...")` (`litellm_provider.py:132-138`); the chat `try/except` renders it as `Inference streaming failed: ...` with an interruption turn (`main.py:737-749`) rather than quietly answering locally and misattributing locality.
- Gate-safe failure — the stream path releases `InferenceGate` in a `finally` (`local_llm.py:297-298`) so provider exceptions never wedge the lock; contention itself yields a retry string instead of raising, keeping the chat loop alive. `hold()` users (`generate_text`, summarizer) get `TimeoutError`, which the summary tab catches as `st.error` without touching chat.
- Telemetry never raises — `get_gpu_memory_info` returns `None` and `get_process_memory_info` returns zeros on any probe failure (`resource_telemetry.py`); the widget branches on `None` instead of try/except (`main.py:515-535`). Stale-but-fast beats fresh-but-blocking: inside the 5.0s TTL the widget renders the cached snapshot rather than failing or forking.
- Per-file upload guard — `try/except` around validation, `DoclingReader` extraction, OCR, and visual analysis in the sidebar upload block shows `st.error` and `continue`s, so one corrupt PDF never aborts the batch; per-page `status == "failed"` records warn individually.
- Summary tab guard — `try/except` around `summarizer.summarize_document` inside `st.status` flips the status to `error` and shows `st.error(f"Summarization error: ...")` without touching other tabs; empty-text documents raise `ValueError` from the service layer (`summarizer.py:382-383`); unknown profiles raise `ValueError` before any provider call or gate acquisition (`summarizer.py:323-326`).
- Constructor validation raises — `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0`; `HybridRetriever.index_chunks` raises on chunk/embedding mismatch or missing embedding source (`hybrid_retriever.py:252-266`); `LiteLLMProvider.analyze_image` raises `ValueError` on empty bytes and `NotImplementedError` on non-vision models (`litellm_provider.py:302-312`); Pydantic models reject bad `doc_id`/`sha256`/coordinates/summary ids; `DocStore.save_summary` requires a `SummaryResult` instance (`doc_store.py:432-433`).
- Health-as-data — `check_health` never raises for expected outages: missing `litellm` install → `unreachable` with install hint; missing per-provider key → `unreachable` naming the `*_API_KEY` var (`litellm_provider.py:140-163`); unreachable `llama-server` → `unreachable` with the launch command (`llama_cpp_provider.py`); the sidebar renders `⚠️ Inference: Offline` + the message instead of try/except (`main.py:273-279`). The runbook mirrors each outage with a remedy (`docs/RUNBOOK.md:171-202`).
- Validation-as-data — `validate_citations` never raises on bad input: empty responses, ungrounded claims, hallucinated ranks, and abstention-with-citations all return a populated `CitationVerificationResult` with `is_valid=False`; the chat exception path records `verification: None` explicitly rather than fabricating a pass (`main.py:739-749`).

## Cross-Cutting Concerns

**Logging:** `logging.getLogger(__name__)` per module (`local_llm.py`, `litellm_provider.py` logs generation/streaming/vision failures with model name, `resource_telemetry.py` `logger.debug` for probe unavailability so CI/headless stays quiet); developer lifecycle `print(f"[LocalEmbedding] ...")` in embedding/reader modules; user-facing feedback exclusively via Streamlit (`st.error` / `st.info` / `st.success` / `st.status` / `st.write` / `st.caption` badges). Rule: `print()`/`logger` for diagnostics, `st.*` for anything the user sees.

**Validation:** Boundary validation at every layer — `validate_pdf_bytes` (header/size/pages) at upload; `LlamaCppProvider` loopback guard at local-provider construction; Pydantic contracts (`models.py`) at persistence; `VectorIndex` type/dimension guards; `LiteLLMProvider` consent + empty-bytes + vision-capability guards; `CitationValidator` post-generation grounding gate; `model_version` read-time cache invalidation.

**Authentication:** No user auth. Provider credentials are per-cloud-API keys resolved per call by `_resolve_api_key_for_model` (`litellm_provider.py:39-85`): session-state `cloud_api_keys` dict (memory-only) → legacy `cloud_api_key` → `st.secrets` → `os.environ`. Missing keys degrade to `unreachable` health, never to silent local substitution or to transmitting without a key. Dependency installation needs no auth beyond public PyPI (lockfile strategy in `docs/RUNBOOK.md:45-49`).

---

*Architecture analysis: 2026-10-12*
