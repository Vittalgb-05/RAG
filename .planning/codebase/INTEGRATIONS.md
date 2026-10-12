# External Integrations

**Analysis Date:** 2026-10-12

## Cloud Inference via LiteLLM (Phase 7 — INF-04, UI-04; consent-gated, only egress path)

**Unified multi-provider gateway (`litellm_provider.py`, `litellm>=1.50.0` at `requirements.txt:17`):**
- Client: `litellm.completion(**{model, messages, max_tokens, temperature, timeout, num_retries[, api_key][, stream]})` — three call sites: non-stream `generate_text` (`litellm_provider.py:212-225`), SSE stream `stream_text` yielding `chunk.choices[0].delta.content` (`litellm_provider.py:263-281`), vision `analyze_image` with base64 data-URI `image_url` payload (`litellm_provider.py:327-339`)
- SDK import: guarded `try/except ImportError → litellm = None` (`litellm_provider.py:18-21`); absence → `check_health` returns `unreachable` "LiteLLM library is not installed" (`litellm_provider.py:146-150`), generation/stream/vision raise `RuntimeError("LiteLLM is not installed.")` (`litellm_provider.py:202-203,251-252,305-306`); all downstream exceptions wrapped as `RuntimeError("Cloud provider {generation|streaming|vision} error (...)")` with `logger.error` (`litellm_provider.py:226-228,282-284,340-342`)
- Provider matrix (selected in sidebar `CLOUD_PROVIDER_OPTIONS`, `main.py:162-166`):
  - Groq `groq/llama-3.3-70b-versatile` — ctx 131072 (`KNOWN_CONTEXT_WINDOWS["groq"]`, `litellm_provider.py:26`), `supports_vision=False`, env `GROQ_API_KEY`
  - OpenAI `openai/gpt-4o-mini` — ctx 128000, `supports_vision=True` (prefix `openai/gpt-4o*`), env `OPENAI_API_KEY`
  - Anthropic `anthropic/claude-3-5-haiku-20241022` — ctx 200000, `supports_vision=True` (prefix `anthropic/claude-3*`), env `ANTHROPIC_API_KEY`
  - Capabilities derived in `get_capabilities()` (`litellm_provider.py:165-181`): context by provider prefix (fallback 128000), vision by `VISION_SUPPORTED_PREFIXES` (`litellm_provider.py:31-36`), always `is_local=False, supports_streaming=True`
  - Defaults: `DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"` (`litellm_provider.py:23`); `timeout=30.0`, `num_retries=2` (`litellm_provider.py:109-110`); temperature clamped `0.0–2.0` (`litellm_provider.py:205,254`)
  - Vision MIME sniffing `_detect_image_mime_type` on magic bytes → `image/jpeg` / `image/png` / `image/gif` / `image/webp` (default `image/png`) (`litellm_provider.py:88-98`); non-vision model `analyze_image` raises `NotImplementedError("Vision analysis is not supported...")` (`litellm_provider.py:308-312`); empty bytes raise `ValueError` (`litellm_provider.py:303-304`)
- Auth: per-provider env vars `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`; resolution order in `_resolve_api_key_for_model(model_name, explicit_key)` (`litellm_provider.py:39-85`): (1) explicit constructor arg, (2) `st.session_state.cloud_api_keys[provider_prefix]` dict, (3) legacy `st.session_state.cloud_api_key`, (4) `st.secrets[VAR]`, (5) `os.environ[VAR]`; missing key → `check_health` returns `unreachable` "Missing API key for {model}. Please set {PREFIX}_API_KEY." with zero network calls (`litellm_provider.py:152-158`)

**Consent-gated egress (programmatic + UI double gate):**
- Programmatic gate: `LiteLLMProvider(user_consented=False)` by default (`litellm_provider.py:108`); `_assert_consent()` raises `PermissionError("Cloud transmission blocked: explicit user consent is required ... (INF-04, UI-04).")` at the top of `generate_text` / `stream_text` / `analyze_image` before any network use (`litellm_provider.py:132-138,201,250,302`); `set_consent(bool)` flips state (`litellm_provider.py:128-130`)
- UI gate (`main.py:67-73,108-245`): session defaults `cloud_mode=False`, `user_consented=False`; `st.toggle("Enable Cloud Inference")` (`main.py:147-152`) opens `st.dialog("Cloud Inference & Data Privacy Consent")` warning that queries + retrieved excerpts leave the device while PDFs/embeddings/LanceDB/SQLite stay local (`main.py:111-135`); "I Consent & Enable Cloud" sets `user_consented=True, cloud_mode=True`, "Cancel" keeps 100% local (`main.py:125-135`); un-toggling or "Revoke Consent (Switch to Local)" clears both flags and closes/drops `active_cloud_provider` (`main.py:156-160,204-208,239-245`)
- Routing: `AiModel(cloud_mode, cloud_provider)` + idempotent `set_cloud_mode(enabled, cloud_provider)` (no-op when mode+provider unchanged, WR-02, `local_llm.py:139-160`); `_detect_provider` returns injected `LiteLLMProvider` when `cloud_mode=True`, else legacy healthy `GroqProvider`, else local `LlamaCppProvider` (`local_llm.py:162-179`); sidebar rebuilds `LiteLLMProvider(model_name=cloud_model, api_key=active_key or None, user_consented=True)` only when model/key changes, else reuses `st.session_state.active_cloud_provider` (`main.py:219-237`)
- Transparency: `☁️ Cloud Mode Active (Egress permitted with user consent)` vs `🔒 Local Mode Active (100% on-device, zero network egress)` captions (`main.py:169,210`); per-answer `☁️ *Generated via external cloud provider ({model}) with user consent.*` captions; chat-turn dicts carry `is_cloud` + `model_name` (`tests/test_cloud_privacy.py:105-129`)
- Ingestion invariant: `VisualAnalyzer.analyze_visual_elements` rejects any `is_local=False` provider (defense-in-depth `is_local` check) so crops are never sent to cloud even in cloud mode; verified in `tests/test_cloud_privacy.py:151-203`

**Ephemeral key handling (memory-only, never persisted):**
- Session inputs: `st.text_input("Session API Key (Optional if set in env)", type="password")` per selected provider, placeholder `Configured via {VAR}` when env/secrets already has it (`main.py:191-198`); value stored only in `st.session_state.cloud_api_keys[prefix]` (+ legacy `cloud_api_key` mirror) (`main.py:199-202`); help text states "Kept in memory only."
- Lifetime: keys live in Streamlit session state (per-browser-session RAM); `Clear All` does not explicitly wipe them (only doc/chat/summary keys, `main.py:288-300`) — closing the tab ends the session; nothing is written to `data/`, `.cache/`, SQLite, LanceDB, logs, or git (`.env` gitignored, `.gitignore:1`; no `.streamlit/secrets.toml` committed)
- Precedence note: session-state key beats `st.secrets`/env (WR-01 per-provider isolation — one provider's key never leaks into another; `tests/test_cloud_privacy.py:224-251` asserts groq/openai/anthropic resolve independently despite a polluted legacy key); explicit constructor `api_key` beats everything (`litellm_provider.py:41-42`)
- Secrets locations: local `.env` via `load_dotenv()` in `load_ai_model()` (`main.py:91`); Streamlit Cloud secrets panel (`GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`); never quote values in docs/code

## System Telemetry & Profiling (Phase 6 — QUAL-01, local-only, no network)

**GPU VRAM via `nvidia-smi` (external binary, not pip):**
- Client: `resource_telemetry.get_gpu_memory_info()` (`resource_telemetry.py:26-71`) shells `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits` via `subprocess.run(capture_output=True, text=True, check=True, timeout=2.0)` (`resource_telemetry.py:34-45`), parses the first CSV line → `{total_mb, used_mb, free_mb, utilization_pct = round(used/total*100, 1)}` (`resource_telemetry.py:50-65`)
- Auth: none (local driver query)
- Degradation: returns `None` on `FileNotFoundError` (binary absent — CI/CPU-only), `SubprocessError` (non-zero exit, timeout), or `ValueError`/`IndexError` (empty/malformed stdout); unexpected exceptions also → `None` via `logger.debug`, never raised (`resource_telemetry.py:66-71`)
- Consumers: sidebar expander `📊 System Telemetry & VRAM` — `st.metric("GPU VRAM", "{used:.0f} / {total:.0f} MB", "{pct:.1f}% used")` + `st.progress(used/total)` + 🟢 `< 3500` / 🟡 `3.5–3.8 GB` / 🔴 `> 3.8 GB` captions, else `ℹ️ CPU-only Mode` caption; `get_system_telemetry_snapshot()["gpu"]` (`resource_telemetry.py:184-211`); `scripts/profile_resources.py:119,260` baseline/final sampling with `487.0 MB` Windows-11-DWM fallback when `None` (`scripts/profile_resources.py:268`)
- Contract test: `tests/test_resource_telemetry.py:30-73` (success parse `4096, 1024, 3072 → 25.0%`; empty/malformed → `None`; `FileNotFoundError`/`CalledProcessError`/`TimeoutExpired` → `None`) + `test_sidebar_telemetry_contracts` in `tests/test_cache_invalidation.py:208-218`

**Process memory via `psutil>=6.1.0` (Phase 6 runtime promotion, `requirements.txt:16`; also `requirements-test.txt:5`):**
- Client: `resource_telemetry.get_process_memory_info()` (`resource_telemetry.py:74-96`) — function-level `import psutil`, `psutil.Process().memory_info()` → `{rss_mb: round(rss/1MiB, 2), vms_mb: round(vms/1MiB, 2)}`; `ImportError` or any error → `{"rss_mb": 0.0, "vms_mb": 0.0}` via `logger.debug` (`resource_telemetry.py:91-96`)
- Auth: none (local process query)
- Consumers: sidebar `**Process RAM (RSS):** {rss:.1f} MB` caption; `get_system_telemetry_snapshot()["process"]` (`resource_telemetry.py:191`); `scripts/profile_resources.py:118,259` initial/final RSS + growth delta; legacy `scripts/benchmark_baseline.py:13,23-25` RSS + `cpu_count`/`virtual_memory` hardware block (`scripts/benchmark_baseline.py:136-137`)
- Contract test: `tests/test_resource_telemetry.py:76-90` (live `rss_mb >= 0.0`/`vms_mb >= 0.0`; `psutil.Process` raising → zeros)

**Stage-latency harness (in-process, stdlib-only — `time` + `threading`, no network):**
- API: `LatencyTracker(stage_name, record_history=True)` context manager (`time.perf_counter()` → `elapsed_ms`, `success`/`error`, thread-safe append to `_LATENCY_HISTORY` capped at `MAX_STAGE_HISTORY=200` via `_LATENCY_LOCK`) (`resource_telemetry.py:20-23,99-152`); `track_stage(name)` generator shim (`resource_telemetry.py:155-160`); `record_stage_latency` / `get_latency_history` (copy) / `clear_latency_history` registry (`resource_telemetry.py:163-181`); `get_system_telemetry_snapshot()` → `{timestamp (UTC ISO), gpu, process, stages: {count, avg_ms, min_ms, max_ms}}` (`resource_telemetry.py:184-211`)
- Profiling harness: `scripts/profile_resources.py` (342 lines, `python scripts/profile_resources.py` → `.planning/research/RESOURCE_PROFILE.json`, `scripts/profile_resources.py:329-331`) runs 6 stages — [Baseline] RSS + VRAM, [1] per-PDF `extract_<file>` ingestion (`PdfReader.get_paragraphs`, ms/page), [2] `cpu_embeddings_10_chunks` (`LocalEmbedding._embed_one` × 10), [3] `lancedb_indexing` + `cold_query`/`warm_query_*` (`HybridRetriever.index_chunks`/`search_hybrid k=5`), [4] `cold_summarization` + `warm_summarization_cache_hit` (`Summarizer` + `tempfile` `DocStore`, asserts `cached` flip + `warm < 50.0 ms` SLA), [5] `inference_gate_concurrency` (`InferenceGate.hold`), [6] RSS growth + projected-peak VRAM audit (`dwm + 1450 + 450 + 510 + 350` vs `3800.0` target, `scripts/profile_resources.py:94-335`); deterministic `BenchmarkProvider(BaseModelProvider)` mock (4096 ctx, vision+streaming flags, 20 ms `generate_text`, 5-token `stream_text`) avoids GPU/network (`scripts/profile_resources.py:39-91`); `tempfile.mkdtemp` DocStore/LanceDB cleaned via `shutil.rmtree` (`scripts/profile_resources.py:112,337-338`); `sys.path.insert(0, REPO_ROOT)` bootstrap (`scripts/profile_resources.py:18-19`, covered by `scripts/* → E402` Ruff waiver)
- Tests: `tests/test_resource_telemetry.py:93-165` (`LatencyTracker` ≥15 ms success + history write, exception capture, `track_stage` shim, manual record/clear, snapshot `count/avg/min/max`)

## APIs & External Services

**Local inference (primary, zero network egress):**
- llama-server (llama.cpp) — OpenAI-compatible chat completions + health probe serving Qwen3-VL 2B Q4_K_M GGUF + `mmproj-f16` projector
  - SDK/Client: `httpx.Client(base_url, timeout=connect 2.0 / read 60.0 / write 10.0 / pool 5.0)` over REST (`llama_cpp_provider.py:39-43`)
  - Endpoints: `GET /health` → `healthy` (200) / `loading` (503) / `error` / `unreachable` (ConnectError → setup command in message) (`llama_cpp_provider.py:49-94`); `POST /v1/chat/completions` non-stream (`generate_text`, `llama_cpp_provider.py:110-153`) and SSE stream (`stream_text`, parses `data: ` lines until `[DONE]`, skips `:` keep-alives, `llama_cpp_provider.py:155-214`); vision via `image_url` base64 data-URI payload (`analyze_image`, `llama_cpp_provider.py:216-268`)
  - Defaults: `base_url="http://127.0.0.1:8080"`, `model_name="qwen3-vl-2b"`, `context_window=4096` (`llama_cpp_provider.py:21-26`)
  - Server launch (external binary, not pip): `llama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf --mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port 8080 --host 127.0.0.1` (`docs/LOCAL_INFERENCE.md:52-60`; health message reproduces the command at `llama_cpp_provider.py:79-82`)
  - Auth: none — bound to `127.0.0.1` only (`docs/LOCAL_INFERENCE.md:66-68`)
  - Capabilities: `supports_vision=True, is_local=True, supports_streaming=True` (`llama_cpp_provider.py:96-108`)
  - Phase-5 reuse: `Summarizer` calls the same provider via `provider.generate_text(prompt, system_prompt, max_tokens, temperature=0.2)` for single-pass (1500 tokens), map (800), consolidate (1000), and reduce (1500) steps (`summarizer.py:225-298`); sequential execution preserves the single-active-LLM 4 GB VRAM envelope (`summarizer.py:232-244`)

**Cloud inference (optional fallback, only egress path):**
- LiteLLM multi-provider (Phase 7, preferred) — see top section: `LiteLLMProvider` via `litellm>=1.50.0` serving Groq / OpenAI / Anthropic behind the consent gate (`litellm_provider.py`); selected through `AiModel.set_cloud_mode(True, cloud_provider)` (`local_llm.py:139-160`); `is_local=False` on all models so `VisualAnalyzer` and locality chips treat every LiteLLM route as cloud
- Groq Cloud direct SDK (legacy fallback) — chat completions via the `groq` Python SDK (`groq==0.15.0`, guarded `try/except ImportError → Groq=None` in `groq_provider.py:12-15`)
  - SDK/Client: `groq.Groq(api_key)` (`groq_provider.py:50-52`); `chat.completions.create` non-stream (`groq_provider.py:116-126`) and stream yielding `chunk.choices[0].delta.content` (`groq_provider.py:148-161`)
  - Model: `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-25`)
  - Auth: `GROQ_API_KEY` with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); missing key/package yields `unreachable` `HealthStatus`, never raises (`groq_provider.py:59-83`)
  - Selection: used only when `cloud_mode=True` without an injected `LiteLLMProvider` and the key is healthy; chosen in `AiModel._detect_provider` (injected cloud → Groq → local-with-diagnostics) and re-probed on every unhealthy `check_health()` (`local_llm.py:162-201`)
  - Capabilities: `supports_vision=False, is_local=False, supports_streaming=True` (`groq_provider.py:85-97`)
  - Vision: not supported — `analyze_image` raises `NotImplementedError` (`groq_provider.py:163-170`); visual evidence degrades to `[Visual element: vision analysis unsupported by active model]` (`visual_analyzer.py:246-249`)

**Model hosting:**
- HuggingFace Hub (embedding weights) — `sentence-transformers` downloads `all-MiniLM-L6-v2` on first run, cached in `~/.cache/huggingface/` (`local_embedding.py:40`); instantiated CPU-pinned `SentenceTransformer(model_name, device="cpu")` (`local_embedding.py:24,40`); no token required for the public model
- HuggingFace Hub (GGUF weights) — `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB) + `mmproj-f16.gguf` (~450 MB) downloaded manually into local `models/` (`docs/LOCAL_INFERENCE.md:31-44`); consumed by the external `llama-server` process, never imported in Python
- Docling model zoo — first `DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(...)})` construction (`docling_reader.py:103-109`) downloads layout/table-structure weights on CPU; converter is lazily built inside `extract_text()` and injectable via `DoclingReader(converter=...)` for tests (`docling_reader.py:37-71`)

## Data Storage

**Databases:**
- SQLite via stdlib `sqlite3` (`doc_store.py:12,103-588`)
  - Connection: file path `data/documents.db`, passed to `DocStore(...)` in the upload loop; parent dirs auto-created (`doc_store.py:115-116`); `data/` is gitignored (`.gitignore:10`)
  - Tables v1 (`SCHEMA_V1_DDL`, `doc_store.py:17-55`): `documents` (PK `doc_id`, UNIQUE `sha256`), `pages` (PK `doc_id,page_num`), `chunks` (PK `chunk_id`)
  - Tables v2 (`SCHEMA_V2_DDL`, `doc_store.py:57-71`): `evidence_elements` (PK `element_id`, FK `doc_id → documents` with `ON DELETE CASCADE`)
  - Tables v3 — Phase 5 summaries (`SCHEMA_V3_DDL`, `doc_store.py:73-94`): `document_summaries` (PK `summary_id`, UNIQUE `(sha256, profile)`, FK `doc_id → documents` with `ON DELETE CASCADE`; columns `summary_id/doc_id/sha256/profile/summary_text/page_references_json/created_at/model_version`) plus indexes `idx_summaries_sha256` and `idx_summaries_doc_id`
  - Mode: WAL + `busy_timeout=5000` + `foreign_keys=ON` (`doc_store.py:131-135`); schema versioned via `PRAGMA user_version` with `MIGRATIONS = {1: V1, 2: V2, 3: V3}` dict (`doc_store.py:96-100,141-154`)
  - Lifecycle: per-operation connection opened/closed inside `_connect()` context manager — Windows-lock and Streamlit-rerun safe (`doc_store.py:122-139`)
  - Writes: `upsert_document` / `record_page` / `record_chunks` (single-transaction `executemany`) / `record_evidence_elements` / `save_summary` (upsert on `(sha256, profile)`, `doc_store.py:425-463`) (`doc_store.py:156-423`); reads: `get_by_sha` (dedup), `get_chunks_for_doc` (CR-01 index restore after restart + summarizer page reconstruction fallback), `get_evidence_for_doc`, `get_summary(sha256, profile, model_version)` (returns `SummaryResult(cached=True)` or `None` on miss/version-mismatch, `doc_store.py:465-514`), `list_summaries_for_doc`, `delete_summaries_for_doc` (`doc_store.py:188-573`); `bbox` round-trips as `bbox_json` (`doc_store.py:308,344-349`); `page_references` round-trips as `page_references_json` with tolerant `json.loads` fallback to `[]` (`doc_store.py:435,501-503,539-541`)
  - Phase-5 access pattern: `Summarizer.summarize_document` checks `doc_store.get_summary(sha256, profile, model_version)` before generation and calls `doc_store.save_summary(result)` after (`summarizer.py:330-335,414-416`); `force_refresh=True` bypasses the read path
- LanceDB embedded store via `lancedb>=0.17.0` + `pyarrow>=14.0.0` (`hybrid_retriever.py:18-24`, `requirements.txt:14-15`)
  - Connection: local filesystem directory `DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"` (repo-root anchored, never CWD-relative) opened with `lancedb.connect(str(db_uri))` (`hybrid_retriever.py:27,96,115`); parent dirs auto-created (`hybrid_retriever.py:114,167`); `data/` is gitignored (`.gitignore:10`); verified anchored-absolute in `tests/test_hybrid_retriever.py:37-43`
  - Table `chunks`: one persistent table holding `chunk_id` (merge key) / `doc_id` / `filename` / `page` / `content` / `vector` (384-dim `float` list) / `extraction` / `char_start` / `char_end` / `bbox_json` (`hybrid_retriever.py:296-309`); reopened on restart via `db.table_names()` → `open_table("chunks")` (`hybrid_retriever.py:189-200`); row count via `len(table)` (`hybrid_retriever.py:206-213`)
  - Writes: `index_chunks(chunks, embeddings)` normalises `Chunk | dict` → dicts, computes missing embeddings via `embedding_fn`, dedups fallback by `chunk_id`, then `create_table("chunks", mode="create")` on first write or `merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(records)` (delete-then-`add` fallback when `merge_insert` is absent) (`hybrid_retriever.py:226-340`); `add_vector(vector, doc)` compatibility shim (`hybrid_retriever.py:342-344`); `delete_document(doc_id)` removes fallback rows in reverse index order plus `table.delete("doc_id = '...'")` (`hybrid_retriever.py:346-363`)
  - Reads: `search_dense(query_vector, k)` → `table.search(vec).limit(k)` → `score = max(0.0, 1.0 - _distance)` (`hybrid_retriever.py:365-403`); `has_document(doc_id)` → `table.search().where("doc_id = '...'").limit(1)` (`hybrid_retriever.py:215-224`); `count_chunks()` (`hybrid_retriever.py:206-213`); all filter literals single-quote-escaped (`doc_id.replace("'", "''")`, `cid.replace("'", "''")`) per `tests/test_hybrid_retriever.py:306-341`
  - Persistence verified across re-instantiation in `tests/test_hybrid_retriever.py:98-124` (write → close → reopen → identical chunks + cosine scores); deletion isolation in `tests/test_hybrid_retriever.py:127-151`
  - Fallback when LanceDB missing/unhealthy: in-memory `VectorIndex(distance_metric="cosine")` (`hybrid_retriever.py:105-108`) + disk JSON `db_uri / "fallback_store.json"` (`hybrid_retriever.py:110,126-141,162-187`) loaded on init, flushed on `close()` / non-LanceDB `index_chunks` / `delete_document`; lifecycle `close()` + `__enter__`/`__exit__` (`hybrid_retriever.py:149-160`); dynamic `set_embedding_fn(fn)` re-wires both retriever and fallback store (`hybrid_retriever.py:143-147`); covered in `tests/test_hybrid_retriever.py:154-171,344-390`
  - Wiring: `main.py` owns one `HybridRetriever` in `st.session_state.hybrid_retriever`, constructs it with `embedding_fn=local_embedding._embed_one` on upload and on restart restore, indexes via `index_chunks(chunk_dicts, embeddings.tolist())`, closes on Clear All, and prefers it as `active_retriever = hybrid_retriever or local_embedding` for chat; `AiModel.ask_a_question_from_pdf_stream` dispatches `isinstance(local_embedding, HybridRetriever) → search_hybrid(query, k=10)` (`local_llm.py:251-254`)

**In-process services (no network, no new pip deps — Phase 5, verified 2026-10-12):**
- `Summarizer` (`summarizer.py:152-418`): hierarchical multi-profile summarization over canonical `Page` models; fast path (`total_tokens <= 2500` → `_summarize_single_pass`, `summarizer.py:387-389`) vs map-reduce (`_bundle_pages(max_tokens=2000)` → per-batch `MAP_PROMPT_TEMPLATE` → optional two-half consolidation when `combined > 2500 tokens and > 3 batches` → `REDUCE_PROMPT_TEMPLATE`, `summarizer.py:232-298`); page refs extracted via `extract_page_references(text, max_page)` and clamped to document max (`summarizer.py:135-149,395-396`); result `SummaryResult(summary_id=summ_<hex16>, cached=False)` then persisted (`summarizer.py:401-416`)
- `citation_validator.py` (`citation_validator.py:52-181`): `extract_citations` (unique sorted `[En]` ranks via `CITATION_REGEX`), `is_abstention` (12 `CANONICAL_ABSTENTION_MARKERS`), `validate_citations(response_text, retrieval_result)` — empty → invalid; abstention without citations → valid (`precision=1.0`); abstention with citations → invalid; zero-citation non-abstention → invalid ungrounded; otherwise `precision = valid/total`, `is_valid = precision >= 0.95` (`citation_validator.py:96-181`); consumed by `AiModel.validate_response` storing `last_retrieval_result`/`last_verification_result` (`local_llm.py:125-126,271,328-346`)

**Embedding pipeline (CPU-only, zero VRAM):**
- `LocalEmbedding(model_name="all-MiniLM-L6-v2", device="cpu")` → `SentenceTransformer(model_name, device="cpu")` (`local_embedding.py:20-40`); batch `get_embeddings` with `normalize_embeddings=True` L2 normalisation (`local_embedding.py:52-57`); `_embed_one(text)` single-string helper wired as both `VectorIndex` and `HybridRetriever` query embedder (`local_embedding.py:45-50`); CPU pinning asserted in `tests/test_hybrid_retriever.py:22-33` (`SentenceTransformer` called once with `("all-MiniLM-L6-v2", device="cpu")`)
- Index handoff: `LocalEmbedding.get_embeddings(texts)` → numpy array → `.tolist()` → `HybridRetriever.index_chunks(chunk_dicts, embeddings)`; `build_index` remains the legacy in-memory path (`local_embedding.py:59-76`)

**Full-text / hybrid retrieval (BM25 + RRF):**
- Pure function `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` — `RRF(d) = Σ 1/(k_rrf + rank)` over dense + FTS rank lists, returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score (`hybrid_retriever.py:31-76`, `DEFAULT_RRF_K = 60` at `hybrid_retriever.py:28`); math verified in `tests/test_hybrid_retriever.py:174-194` (doc_b > doc_a > doc_d > doc_c)
- `create_fts_index()` → `table.create_fts_index("content", replace=True)` when supported (`hybrid_retriever.py:405-413`); `search_fts(query, k)` → `table.search(query, query_type="fts").limit(k)` with `_score` passthrough, degrading to `_bm25_search_fallback` on any exception or empty result (`hybrid_retriever.py:478-505`)
- `_bm25_search_fallback(query, k)` (`hybrid_retriever.py:415-476`): tokenises `re.findall(r"\w+")`, drops 1-char tokens, k1=1.5 / b=0.75, single-pass `df_map` (O(N·|Q|)), reads fallback docs or up-to-10000 LanceDB rows when fallback is empty; keyword boost verified `RTX-3050-Ti → chk_exact_rtx` (`tests/test_hybrid_retriever.py:197-229`), semantic path verified `company profits → chk_fiscal` (`tests/test_hybrid_retriever.py:232-264`)
- `search_hybrid(query, k, k_rrf)` (`hybrid_retriever.py:507-612`): candidate pool `max(k*2, 10)` per arm → dense via `embedding_fn` + `search_dense` → FTS via `search_fts` → `compute_rrf` fuse → top-k `EvidenceSnippet(chunk_id/score/rank/dense_rank/fts_rank/...)` in canonical `RetrievalResult(query, snippets, total_candidates, search_mode)` where `search_mode ∈ {hybrid,dense,fts,fallback}`; empty query / `k<=0` returns empty `RetrievalResult` (`tests/test_hybrid_retriever.py:295-303`); shared identity (prompt `formatted_evidence()` `[E1] (file, p. N)` ≡ UI `source_labels()` chips) verified in `tests/test_hybrid_retriever.py:267-292`
- Legacy facades preserved: `HybridRetriever.search(question, k) → list[(doc_dict, score)]` and `get_context(question, k) → formatted_evidence()` (`hybrid_retriever.py:614-622`); `LocalEmbedding.search_hybrid` remains dense-only (`search_mode="dense"`, `local_embedding.py:84-109`)

**File Storage:**
- Local filesystem only
  - LanceDB files under `data/lancedb/` (live `fallback_store.json` observed; full `*.lance` tables materialise once `index_chunks` runs with `lancedb` installed); gitignored (`.gitignore:10`)
  - Deterministic JSON cache under `.cache/<sha256>/<CONFIG_VERSION>/{pages.json,chunks.json,manifest.json}` written best-effort; path computed by `cache_dir_for` with strict 64-hex validation (`models.py:17-30`); `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`); `.cache/` is gitignored (`.gitignore:17`)
  - SQLite file `data/documents.db` (see above; now includes `document_summaries` table from v3 migration)
  - Local GGUF weights in `models/` (external to pip; see local-inference section)
  - Synthetic test PDFs `tests/data/corpus/*.pdf` (6 files: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`) generated by `tests/data/corpus/generate_corpus.py` (reportlab)

**Ingestion backends (local libraries, no network):**
- Docling `>=2.0.0` (`docling_reader.py`): `DocumentConverter` + `DocumentStream(name, BytesIO)` (`docling_reader.py:111-115`); CPU-only pipeline `do_ocr=False, do_table_structure=True` (`docling_reader.py:104-106`); reading-order grouping by `item.prov[0].page_no`, markdown tables via `export_to_markdown()` preserved intact as single chunks when `startswith("|")` and ≤2000 chars, prose split 1000/200 (`docling_reader.py:118-267`); chunk `extraction="docling"` (`docling_reader.py:228-266`); any missing package / empty result / exception degrades to `PdfReader` fallback (`docling_reader.py:95-100,183-191,288-293`)
- RapidOCR / ONNX Runtime `>=1.3.0` (`ocr_fallback.py`): `RapidOCR()` CPU default (`ocr_fallback.py:63-69`); trigger `should_ocr_page(text, status, threshold=50)` — `empty`/`failed` status or <50 chars (`ocr_fallback.py:29-43`); page render via PyMuPDF at 150 DPI (`ocr_fallback.py:77-110`); `ocr_page_image` parses `[[box], text, score]` tuples → `(full_text, avg_conf)` (`ocr_fallback.py:112-159`); `apply_conditional_ocr` preserves clean pages untouched, isolates per-page faults to `status="failed"` without aborting the document, tags new chunks `extraction="ocr"` (`ocr_fallback.py:162-320`)
- PyMuPDF `>=1.24.0` (`import fitz`): OCR renderer `fitz.open(stream, filetype="pdf") → page.get_pixmap(Matrix(zoom,zoom)).tobytes("png")` (`ocr_fallback.py:96-108`); visual detection of raster images (`get_images` + `get_image_rects`, ≥30×30 pt, `kind="image"`) and vector diagrams (`get_drawings` cluster ≥2 drawings, ≥40×40 pt, 95%-area background exclusion, 10 pt padding, `kind="chart"`) (`visual_analyzer.py:64-136`); 2x-zoom PNG crops clipped to page rect (`crop_visual_element`, `visual_analyzer.py:138-183`); both modules guard `fitz is None` (OCR unavailable / regions `[]` / crop raises `RuntimeError`) (`ocr_fallback.py:23-26,72-75`, `visual_analyzer.py:17-20,59-61,164-165`)
- pypdf `==5.3.0`: baseline `PdfReader` extraction with per-page `try/except` → `ok`/`empty`/`failed` `Page` records and `extraction="pypdf"` chunks (`pdf_reader.py:29-114`); validation probe in `upload_validation.py:89-94`
- pyarrow `>=14.0.0`: LanceDB columnar/file-format layer (`hybrid_retriever.py:21`); no direct app-code API surface — indirect via `lancedb.connect` / `create_table` / `merge_insert` / `search`

**Caching:**
- In-process Streamlit cache: `@st.cache_resource(show_spinner=False)` memoizes one `AiModel` (and its active provider) per server process (`main.py:84-92`); cloud provider instance is session-scoped (`st.session_state.active_cloud_provider`, `main.py:233-235`) so per-provider keys never cross sessions; `Summarizer` is constructed per request from the cached `ai_model.provider` so summaries always use the active backend
- SQLite summary cache: `document_summaries` keyed UNIQUE `(sha256, profile)` with `model_version` invalidation (`doc_store.py:73-94,465-514`); second request for the same document+profile returns `cached=True` without any LLM call (`summarizer.py:330-335`)
- Per-session persistent retriever: `HybridRetriever` in `st.session_state` backed by `data/lancedb/` on disk, surviving server restarts; legacy per-session in-memory `VectorIndex` inside `LocalEmbedding` remains as the degraded path; dedup-hit-after-restart restores both `DocStore.get_chunks_for_doc` and `HybridRetriever.index_chunks`
- No Redis / external cache

## Authentication & Identity

**Auth Provider:**
- None. No user accounts or sessions. Credentials are per-provider cloud API keys only:
  - `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` resolved with precedence explicit-arg → `st.session_state.cloud_api_keys[prefix]` → legacy `cloud_api_key` → `st.secrets[VAR]` → `os.environ[VAR]` (`litellm_provider.py:39-85`); legacy `GroqProvider` resolves `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); absence yields `unreachable` `HealthStatus`, never an error
- Ephemeral handling: sidebar `type="password"` inputs held in `st.session_state.cloud_api_keys` RAM only (`main.py:191-202`); never written to disk, SQLite, LanceDB, logs, or git

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/OpenTelemetry).

**Logs:**
- `logging` module (`getLogger(__name__)`) in the Phase 3–7 modules: `logger.info` for Docling fallback paths (`docling_reader.py:96,184,281`), LanceDB connect/open-table/index lifecycle (`hybrid_retriever.py:117,139,198,315`), summarizer fast-path/map-reduce routing and cache hits (`summarizer.py:334,388,391,416`); `logger.warning` for conversion/crop failures (`docling_reader.py:289`, `ocr_fallback.py:68,128`, `visual_analyzer.py:60,228`), LanceDB init/search/persistence degradation (`hybrid_retriever.py:119,141,187,200,390,402,503,540`); `logger.error` for page-level OCR faults and VLM failures (`ocr_fallback.py:307`, `visual_analyzer.py:133,238`), LanceDB persist/delete faults (`hybrid_retriever.py:336,361`), and LiteLLM generation/streaming/vision failures with model name (`litellm_provider.py:227,283,341`); `logger.debug` for FTS-index notices and BM25 table-read fallback (`hybrid_retriever.py:413,430`) plus telemetry unavailability (`resource_telemetry.py:67,70,92,95` — nvidia-smi absent/failing, psutil missing/erroring; debug-only so CI/headless stays quiet)
- Module-prefixed `print()` for developer diagnostics in legacy modules: `[LocalEmbedding]` (`local_embedding.py:21,23,58`), `[DocStore]` migrations (`doc_store.py:129`), `[UploadValidation]` (`upload_validation.py:106`), pypdf success line (`pdf_reader.py:113`)
- User-facing feedback via Streamlit (`st.status`, `st.error`, `st.warning`, `st.info`, `st.success`, `st.progress`) — never `print`; summarizer tab surfaces `st.info` when no document is indexed and streams summary progress inline; telemetry rendered via sidebar `st.expander("📊 System Telemetry & VRAM")` with `st.metric` + `st.progress` + threshold captions
- Provider health surfaced through the `HealthStatus` schema rendered in the sidebar (`main.py:247-279`); VLM provenance kept separate as `EvidenceElement(source="vlm:<model_name>")` so visual approximations never contaminate ground-truth tables (`visual_analyzer.py:240-262`); retrieval provenance carried per-snippet (`dense_rank`/`fts_rank`/`search_mode`) from `HybridRetriever.search_hybrid` through `RetrievalResult` into prompts and citations (`hybrid_retriever.py:590-611`, `models.py:141-200`); citation precision diagnostics carried in `CitationVerificationResult(message, precision, valid/hallucinated_citations)` (`citation_validator.py:35-49`, `local_llm.py:328-346`); cloud answers carry `is_cloud` + `model_name` in chat history for egress chips (`tests/test_cloud_privacy.py:105-129`)

## CI/CD & Deployment

**Hosting:**
- Primary: local Windows workstation (RTX 3050, 4 GB VRAM ceiling) — zero-egress local inference (`docs/LOCAL_INFERENCE.md`, `llama_cpp_provider.py:1-6`); embeddings (`sentence-transformers` CPU) and retrieval (LanceDB disk / BM25) add zero VRAM load by construction; summarizer map-reduce runs sequentially for the same reason (`summarizer.py:232-244`)
- Fallback: Streamlit Community Cloud with per-provider keys in the Cloud secrets panel (`GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`); ephemeral disk (LanceDB + SQLite + `.cache/` best-effort only)
- Devcontainer/Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` with Streamlit on port 8501 (`.devcontainer/devcontainer.json`)

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml` (sole workflow)
  - Triggers: push / pull_request on `main` (`.github/workflows/ci.yml:3-7`)
  - Job `test` on `ubuntu-latest`: checkout (`actions/checkout@v4`) → setup Python `"3.11"` with pip cache (`actions/setup-python@v5`) → `pip install -r requirements.txt` (17 lines post-Phase-7, incl. `litellm>=1.50.0` + `psutil>=6.1.0`) + `pip install -r requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v` (`.github/workflows/ci.yml:9-41`); suite now includes `tests/test_litellm_provider.py` + `tests/test_cloud_privacy.py` alongside `tests/test_summarizer.py` + `tests/test_citation_validator.py` and Phase-6 `tests/test_resource_telemetry.py` (nvidia-smi absent on CI → `None` path exercised, never a failure; LiteLLM tests mock `litellm.completion` — no network/keys needed)
  - No deploy job, no artifact upload, no coverage gate
- Benchmarks (manual): `python scripts/benchmark_baseline.py` measures pypdf extraction latency, 1000/200 chunking, CPU `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` load + batch encode latency, `VectorIndex` linear-scan latency over 100/500/1000 vectors, and RSS via `psutil`; writes `.planning/research/BASELINE_BENCHMARK.json` (`scripts/benchmark_baseline.py:1-174`); `python scripts/profile_resources.py` runs the Phase-6 QUAL-01 resource profile (ingestion → CPU embeddings → LanceDB hybrid cold/warm → summarizer cold/warm `< 50 ms` SLA → InferenceGate → 4 GB VRAM headroom audit) and writes `.planning/research/RESOURCE_PROFILE.json` (`scripts/profile_resources.py:1-342`)

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — all optional; each needed only for its LiteLLM provider route (`litellm_provider.py:39-85`); `GROQ_API_KEY` alone suffices for the legacy `GroqProvider` fallback (`groq_provider.py:37-49`); no other env var is read in app code

**Secrets location:**
- Local: `.env` in project root (gitignored, `.gitignore:1`) loaded via `python-dotenv` inside `load_ai_model()` (`main.py:91`)
- Session-ephemeral: `st.session_state.cloud_api_keys` dict + legacy `cloud_api_key` (`main.py:72-73,199-202`) — RAM only, populated from `type="password"` inputs, never persisted
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY" | "OPENAI_API_KEY" | "ANTHROPIC_API_KEY"]`, `litellm_provider.py:76-82`, `groq_provider.py:40-44`)
- No `.streamlit/secrets.toml` is committed; never quote secret values in docs or code

**Local runtime state (gitignored, existence-only):**
- `.env` — API keys (`main.py:91`)
- `data/documents.db` — SQLite store including `document_summaries` (`.gitignore:10`)
- `data/lancedb/` — LanceDB tables + `fallback_store.json` (`hybrid_retriever.py:27,110`; `.gitignore:10`)
- `.planning/research/RESOURCE_PROFILE.json` — Phase-6 profiling-harness output (`scripts/profile_resources.py:329-331`; gitignored or planning-ignored research artifact, regenerated per run)
- `.cache/<sha256>/<CONFIG_VERSION>/` — extraction cache (`.gitignore:17`)
- `models/` — local GGUF weights (downloaded per `docs/LOCAL_INFERENCE.md:31-44`, served by external `llama-server`)
- `~/.cache/huggingface/` — sentence-transformers + Docling model downloads (outside repo)

## Test Mock Seams (offline — no GPU, no network, no API keys)

- LiteLLM seams (no network/keys): `monkeypatch.setattr(litellm, "completion", ...)` with `MockCompletionResponse` / SSE `MockDelta` iterables (`tests/test_litellm_provider.py:48-55,112-168,195-217`); `monkeypatch.setattr(litellm_provider, "litellm", None)` for missing-library health (`tests/test_litellm_provider.py:80-90`); `monkeypatch.delenv("GROQ_API_KEY"/"OPENAI_API_KEY"/"ANTHROPIC_API_KEY")` + `monkeypatch.setattr("streamlit.secrets", {})` for missing-key health (`tests/test_litellm_provider.py:58-68`); `FakeSessionState(dict)` with per-provider `cloud_api_keys` + polluted legacy key for WR-01 isolation (`tests/test_cloud_privacy.py:224-251`); `socket.create_connection` guard raising `ConnectionRefusedError` proves zero-egress ingestion/indexing (`tests/test_cloud_privacy.py:61-64`); `VisualAnalyzer(region_detector=..., cropper=...)` + monkeypatched `analyze_image` spy proves cloud vision is never called (`tests/test_cloud_privacy.py:151-203`)
- `httpx.MockTransport(handler)` injected as `LlamaCppProvider(transport=...)` — covers `GET /health` (200/503/error/connect-fail) and `POST /v1/chat/completions` (JSON + SSE `data: [DONE]`) (`tests/test_llama_cpp_provider.py`, `llama_cpp_provider.py:26,34,39-43`)
- `MagicMock` Groq client (`mock_groq_client`, `tests/conftest.py:18-48`) yielding canned `delta.content` tokens `["This ", "is ", "a ", "grounded ", "answer."]`; `fake_env_groq_key` sets a dummy `GROQ_API_KEY` (`tests/conftest.py:11-16`)
- `MagicMock` SentenceTransformer (`mock_sentence_transformer`, `tests/conftest.py:51-81`) returning deterministic 384-dim L2-normalised `numpy.float32` vectors; CPU-pinning asserted via `MagicMock` class replacement in `tests/test_hybrid_retriever.py:22-33`
- `MockLlamaCppProvider(BaseModelProvider)` healthy/unhealthy double recording `stream_calls` (`tests/conftest.py:91-161`)
- `MockSummarizerProvider(BaseModelProvider)` recording `generate_calls` and returning deterministic citation-bearing summaries (`tests/test_summarizer.py:16-50`); `CitationFreeProvider` variant covers citation-less output (`tests/test_summarizer.py:288`); `tmp_path`-isolated `DocStore` covers cache lifecycle + `model_version` invalidation (`tests/test_summarizer.py:198-341`)
- Citation fixtures: `tests/test_citation_validator.py` covers perfect precision, hallucinated rank, valid abstention, abstention-with-citations, empty response, and ungrounded response (`tests/test_citation_validator.py:54-140`)
- `tmp_path`-isolated `HybridRetriever(db_uri=tmp_path / ...)` per test (no shared `data/lancedb/` mutation) plus `monkeypatch.setattr("hybrid_retriever.lancedb", None)` / `monkeypatch.setattr(hybrid_retriever, "lancedb", None)` for fallback-path tests (`tests/test_hybrid_retriever.py:46-390`); deterministic `_make_unit_vector(seed, dim=384)` numpy helper (`tests/test_hybrid_retriever.py:12-19`)
- Constructor injection seams (no network/install required): `DoclingReader(converter=...)` (`docling_reader.py:37-71`), `OcrEngine(recognizer=..., renderer=...)` (`ocr_fallback.py:49-61`), `VisualAnalyzer(region_detector=..., cropper=...)` (`visual_analyzer.py:33-45`); `FakeFitz` module double via `monkeypatch.setattr("visual_analyzer.fitz", FakeFitz)` (`tests/test_visual_analyzer.py:286-332`)
- Corpus fixtures: `sample_pdf_path` → `tests/data/corpus/clean_digital.pdf` (`tests/conftest.py:84-88`); full 19-file suite `tests/test_*.py` (citation_validator, cache_invalidation incl. `test_sidebar_telemetry_contracts`, cloud_privacy, doc_store, docling_reader, hybrid_retriever, litellm_provider, llama_cpp_provider, local_embedding, local_llm, main_ui, model_provider, models, ocr_fallback, pdf_reader, prompt_budget, resource_telemetry, summarizer, upload_validation, vector_index, visual_analyzer, concurrency_lock)
- Telemetry seams (no GPU required): `patch("subprocess.run", ...)` with `MagicMock(stdout=...)` for nvidia-smi success/empty/malformed plus `side_effect=FileNotFoundError/CalledProcessError/TimeoutExpired` for degradation (`tests/test_resource_telemetry.py:30-73`); `patch("psutil.Process", side_effect=RuntimeError)` for RSS fallback (`tests/test_resource_telemetry.py:86-90`); `autouse reset_latencies` fixture clearing `_LATENCY_HISTORY` before/after each test (`tests/test_resource_telemetry.py:22-27`)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (LiteLLM/Groq cloud calls are direct SDK calls, not webhooks; llama-server is localhost REST, not external; LanceDB is an embedded in-process library, not a network service; summarizer/citation_validator are in-process pure-Python services with no network surface)

---

*Integration audit: 2026-10-12*
