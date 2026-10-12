# Codebase Structure

**Analysis Date:** 2026-10-12

## Directory Layout

```
RAG/
├── main.py                   # Streamlit entry point: tabs (chat + summarizer), upload/index, QA + validation, telemetry widget, chat bounding (664 lines)
├── local_llm.py              # AiModel RAG orchestrator + InferenceGate single-active-LLM lock + validate_response façade (319 lines)
├── resource_telemetry.py     # GPU/RAM telemetry + LatencyTracker + snapshot aggregation (211 lines)
├── summarizer.py             # Hierarchical 5-profile map-reduce summarization service, gate-held generation (420 lines)
├── citation_validator.py     # Post-generation [En] citation + abstention validator (181 lines)
├── hybrid_retriever.py       # Sole persistent hybrid index: LanceDB + BM25 + RRF (626 lines)
├── local_embedding.py        # CPU-pinned SentenceTransformer wrapper, embed-fn provider for retriever (116 lines)
├── vector_index.py           # Pure-stdlib in-memory vector store, retriever fallback mirror (228 lines)
├── models.py                 # Canonical Pydantic v2 contracts incl. SummaryResult (235 lines)
├── doc_store.py              # SQLite WAL store incl. document_summaries v3 + count_* for widget (610 lines)
├── model_provider.py         # BaseModelProvider ABC + HealthStatus/Capabilities (156 lines)
├── groq_provider.py          # Groq Cloud provider (170 lines)
├── llama_cpp_provider.py     # Local llama-server provider (268 lines)
├── prompt_budget.py          # Bounded grounded context + bound_chat_history turn cap + XML defense (152 lines)
├── docling_reader.py         # Docling structured extraction + pypdf fallback (311 lines)
├── pdf_reader.py             # Legacy pypdf extraction + chunking (149 lines)
├── ocr_fallback.py           # Conditional RapidOCR for scanned pages (320 lines)
├── visual_analyzer.py        # Visual element detection + VLM analysis (264 lines)
├── upload_validation.py      # PDF header/size/page validation (113 lines)
├── tests/                    # pytest suite (21 test modules + data/corpus)
│   ├── test_concurrency_lock.py    # InferenceGate acquire/release/hold/timeout/generation/summarizer (225 lines)
│   ├── test_resource_telemetry.py  # nvidia-smi parse, psutil fallback, LatencyTracker, snapshot (165 lines)
│   ├── test_cache_invalidation.py  # bound_chat_history cap, count_*, summary version invalidation (218 lines)
│   ├── test_summarizer.py          # Map-reduce, profiles, cache, page-refs (342 lines)
│   ├── test_citation_validator.py  # Precision, abstention, empty, AiModel wiring (161 lines)
│   ├── test_main_ui.py             # Chat-turn + summary-display contracts (156 lines)
│   ├── test_doc_store.py           # DocStore incl. summary roundtrip/version/cascade (582 lines)
│   ├── test_local_llm.py           # Stream orchestration incl. retrieval_result + validate_response (226 lines)
│   └── ...                         # Per-module mirrors (see below)
├── scripts/
│   ├── profile_resources.py   # 6-stage VRAM/latency/cache/concurrency profiler → RESOURCE_PROFILE.json (342 lines)
│   └── benchmark_baseline.py  # Manual retrieval/generation benchmark (174 lines)
├── docs/
│   └── LOCAL_INFERENCE.md    # Local inference setup notes
├── data/                     # Runtime persistence (gitignored contents)
│   ├── documents.db*         # SQLite DocStore database (created at runtime)
│   └── lancedb/              # LanceDB tables or fallback_store.json
├── .cache/                   # Per-document disk cache Tier 2 (created at runtime)
├── .planning/research/       # Profiler output RESOURCE_PROFILE.json (generated)
├── application_screenshots/  # UI screenshots for docs
├── .devcontainer/            # Pinned Python 3.11 image + Streamlit auto-launch
├── .planning/                # GSD planning artifacts (incl. this codebase map)
├── requirements.txt          # Pinned runtime dependencies
├── requirements-test.txt     # Test-only dependencies
├── pyproject.toml            # Ruff (line-length 120) + pytest config
└── README.md                 # Setup, run, and architecture documentation
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at the root — one file per service, no packages, no `__init__.py`.
- Contains: `main.py`, `local_llm.py` (incl. `InferenceGate`), `resource_telemetry.py`, `summarizer.py`, `citation_validator.py`, `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`, `models.py`, providers, ingestion helpers, `requirements*.txt`, `pyproject.toml`.
- Key files: `main.py` (entry + tab wiring + telemetry widget + `MAX_CHAT_TURNS`), `local_llm.py` (`InferenceGate` + `AiModel`), `resource_telemetry.py` (probes + tracker), `models.py` (contracts).

**tests/:**
- Purpose: pytest suite mirroring each root module, plus concurrency/telemetry/cache-invalidation suites, a file corpus, and UI-contract tests.
- Contains: `conftest.py`, `__init__.py`, `test_concurrency_lock.py` (225), `test_resource_telemetry.py` (165), `test_cache_invalidation.py` (218), `test_summarizer.py` (342), `test_citation_validator.py` (161), `test_main_ui.py` (156), `test_doc_store.py` (582), `test_docling_reader.py` (274), `test_hybrid_retriever.py` (390), `test_llama_cpp_provider.py` (259), `test_local_embedding.py` (45), `test_local_llm.py` (226), `test_model_provider.py` (148), `test_models.py` (455), `test_ocr_fallback.py` (326), `test_pdf_reader.py` (202), `test_prompt_budget.py` (160), `test_upload_validation.py` (111), `test_vector_index.py` (109), `test_visual_analyzer.py` (369), `data/corpus/` (sample PDFs + `generate_corpus.py`).
- Key files: `tests/test_concurrency_lock.py` (gate acquire/release/reentrant-hold/stray-release/timeout-contention/`hold`-timeout/`generate_text`-holds-gate/stream-busy-yield/summarizer-holds-gate with `MockProvider` + `gate_was_locked` probes), `tests/test_resource_telemetry.py` (mocked `subprocess.run` nvidia-smi parse, empty/malformed → `None`, `FileNotFoundError` → `None`, psutil RSS/VMS, `LatencyTracker` success/error/`to_dict`, `track_stage`/`record_stage_latency` history cap, `get_system_telemetry_snapshot` aggregation), `tests/test_cache_invalidation.py` (`bound_chat_history` 50-turn cap + orphan-assistant prune + empty passthrough, `count_documents`/`count_summaries` zero→N, summary cache hit + `model_version`-mismatch invalidation), `tests/test_summarizer.py` (fast-path vs map-reduce dispatch, profile templates, `extract_page_references`, DocStore cache hit/version-mismatch/force-refresh with `MockSummarizerProvider` counting `generate_calls`), `tests/test_citation_validator.py` (perfect precision, hallucinated rank, valid abstention, abstention-with-citations, empty response, ungrounded response, `AiModel.validate_response` delegation + fallback-to-last-result), `tests/test_main_ui.py` (chat-turn `{role, content, sources, verification, snippets}` schema, summary-display `cached`/`page_references` contract), `tests/conftest.py` (shared fixtures).

**scripts/:**
- Purpose: Manual/one-off tooling, excluded from strict lint (`pyproject.toml` per-file-ignores for `E402`).
- Contains: `scripts/profile_resources.py`, `scripts/benchmark_baseline.py`.
- Key files: `scripts/profile_resources.py` — `BenchmarkProvider` (deterministic `BaseModelProvider` with `call_count`, 20ms `generate_text`, 5-token `stream_text`), `run_resource_profile()` 6-stage audit (baseline RSS/VRAM → ingestion ms/page per corpus PDF → CPU embedding ms/chunk → LanceDB index + cold/warm `search_hybrid` → cold vs warm summary with `<50ms` cache-SLA assert → `InferenceGate` hold-cycle check → projected-peak VRAM budget vs 3800 MB) writing `.planning/research/RESOURCE_PROFILE.json`; run via `python scripts/profile_resources.py`, not part of the app or test suite.

**data/:**
- Purpose: Runtime persistence created on first run; contents are gitignored.
- Contains: `documents.db` (+ WAL/SHM sidecars) from `DocStore(Path("data/documents.db"))` (`main.py:86`); `lancedb/` LanceDB tables or `fallback_store.json` from `HybridRetriever` (`hybrid_retriever.py:27, 110`).
- Key files: None committed — directory structure only. `document_summaries` rows live inside `documents.db` (schema v3).

**.cache/:**
- Purpose: Best-effort per-document disk cache Tier 2 (`STORE-03`), written in `main.py:311-321`.
- Contains: `<sha256>/docling-1000-200-v1/{pages.json, chunks.json, manifest.json}` via `cache_dir_for` (`models.py`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Key files: None committed.

**.planning/research/:**
- Purpose: Generated profiler artifact destination.
- Contains: `RESOURCE_PROFILE.json` written by `scripts/profile_resources.py:329-331` (timestamp, target GPU, projected peak/headroom, hardware live RSS/GPU, ingestion/embeddings/retrieval/summarization/concurrency sections).
- Key files: None committed (generated on profiler runs).

**docs/:**
- Purpose: Supplemental setup documentation.
- Contains: `docs/LOCAL_INFERENCE.md`.

**.planning/codebase/:**
- Purpose: GSD codebase maps consumed by plan/execute commands (this file, `ARCHITECTURE.md`, `STACK.md`, `CONVENTIONS.md`, etc.).

## Key File Locations

**Entry Points:**
- `main.py`: Sole runtime entry — `streamlit run main.py`. Session-state init `main.py:58-67`; `load_ai_model` `main.py:75-83`; tab root at `main.py:402` (`st.tabs`); chat loop `main.py:404-576`; summary loop `main.py:579-664`.
- `scripts/profile_resources.py:341-342`: Profiler entry (`run_resource_profile()` under `if __name__ == "__main__"`).
- `scripts/benchmark_baseline.py`: Manual benchmark entry.

**Concurrency (single-active-LLM):**
- `local_llm.py:26-90`: `InferenceGate` — `_lock: RLock` + `_active_threads`/`_state_lock`, `acquire(timeout=60.0)`, `release()`, `is_locked()`, `hold(timeout)` context manager (raises `TimeoutError`).
- `local_llm.py:258-271`: Stream path — `acquire(60s)` → busy-yield on failure → `yield from provider.stream_text` → `finally: release()`.
- `local_llm.py:273-299`: `AiModel.generate_text(..., timeout=60.0)` — `with InferenceGate.hold(...)`.
- `summarizer.py:387-394`: Map-reduce dispatch inside `with InferenceGate.hold(timeout=120.0)`.

**Telemetry (probes → widget → artifact):**
- `resource_telemetry.py:26-71`: `get_gpu_memory_info` (nvidia-smi CSV parse, `None` on failure); `resource_telemetry.py:74-96`: `get_process_memory_info` (psutil RSS/VMS, zeros fallback); `resource_telemetry.py:99-181`: `LatencyTracker`/`track_stage`/`record_stage_latency`/`get_latency_history`/`clear_latency_history` (`MAX_STAGE_HISTORY=200`); `resource_telemetry.py:184-211`: `get_system_telemetry_snapshot`.
- `main.py:357-386`: Sidebar `📊 System Telemetry & VRAM` expander widget (`st.metric` + `st.progress` + tiered captions + RSS + `count_documents`/`count_summaries`).
- `scripts/profile_resources.py:94-342`: 6-stage offline profiler → `.planning/research/RESOURCE_PROFILE.json`.

**Retrieval (sole index):**
- `hybrid_retriever.py`: `compute_rrf` (lines 31-76), `HybridRetriever` (lines 79-626) — `index_chunks` (upsert dedup + LanceDB/`fallback_store.json` mirror), `search_dense`, `search_fts`, `_bm25_search_fallback`, `search_hybrid` → `RetrievalResult`, legacy `search`/`get_context` facades, `delete_document`, `count_chunks`/`has_document`.
- `local_embedding.py:45-50`: `_embed_one` — the shared embedding fn injected as `HybridRetriever(embedding_fn=...)` (`main.py:283-286`, `main.py:217-219`).
- `main.py:278-288`: Sole-index build (CPU `get_embeddings` batch → `index_chunks`); `main.py:495-499`: sole-index query (`search_hybrid(k=5)`); `main.py:212-225`: CR-01 restore path.

**Chat bounding (turn cap + token budget):**
- `main.py:38`: `MAX_CHAT_TURNS = 50`; `main.py:389-395`: `append_chat_turn` (append → `bound_chat_history`); `main.py:481`: `history_to_pass = chat_history[:-1][-10:]`.
- `prompt_budget.py:57-129`: `assemble_grounded_messages` (input budget `max_context - 1024`, prompt/context clamp, oldest-first history retention); `prompt_budget.py:131-152`: `bound_chat_history(history, max_turns=50)` (tail-slice + orphan-assistant prune).

**Multi-tier cache (invalidation points):**
- Tier 1 session: `main.py:622` (`summary_{doc_id}_{profile}` write), `main.py:643` (read), `main.py:151-153` (Clear All purge).
- Tier 2 disk: `main.py:311-321` (`.cache/<sha>/<CONFIG_VERSION>/*.json` best-effort write).
- Tier 3 SQLite: `doc_store.py:425-463` (`save_summary` upsert on `ON CONFLICT(sha256, profile)`), `doc_store.py:465-514` (`get_summary` with `model_version` invalidation → `None`), `doc_store.py:516-573` (`list/delete_summaries_for_doc`), `summarizer.py:331-336` (cache check + `force_refresh` bypass).
- Tier 4 vectors: `hybrid_retriever.py:110-187` (`_load/_save_fallback_store`, `close()` flush), `doc_store.py:590-610` (`count_documents`/`count_summaries` for widget).

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`) + pytest (`testpaths = ["tests"]`).
- `requirements.txt`: Runtime pins incl. `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `docling>=2.0.0`, `sentence-transformers==3.4.1`, `pydantic==2.11.9`, `psutil` (telemetry).
- `requirements-test.txt`: Test-only deps.
- `.devcontainer/devcontainer.json`: Pinned Python 3.11 image, Streamlit auto-launch on port 8501.

**Core Logic:**
- `local_llm.py`: `InferenceGate` (26-90), `AiModel._detect_provider` (131-152), `ask_a_question_from_pdf_stream` (184-271) — `retrieval_result`-first branch (204-205), in-LLM fallback retrieval (206-242), gate-held stream (258-271); `generate_text` (273-299); `validate_response` (301-319).
- `summarizer.py`: `PROFILE_SYSTEM_INSTRUCTIONS` (five profiles), `MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`, `extract_page_references`, `Summarizer` (301-420) — `summarize_document` (cache → resolve pages → gate-held fast/map-reduce → refs → save).
- `citation_validator.py`: `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `CitationVerificationResult`, `extract_citations`, `is_abstention`, `validate_citations` (empty → invalid; abstention; 0-citation → invalid; ≥95% precision).
- `models.py`: `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`, `EvidenceSnippet`, `RetrievalResult` + `formatted_evidence`/`source_labels`, `SummaryProfile`/`VALID_SUMMARY_PROFILES`, `SummaryResult` + `validate_ids`.
- `main.py`: Session-state init (58-67), `load_ai_model` (75-83), Clear All incl. `summary_*` purge (142-154), upload/index loop (164-353), telemetry widget (357-386), `append_chat_turn` (389-395), `tab_chat` + single shared retrieval (492-511) + `validate_response` + badges/drawer (523-576), `tab_summary` selectbox/radio/force-refresh/generate/display (579-664).

**Testing:**
- `tests/test_concurrency_lock.py`: Gate unit tests — unlocked baseline, reentrant `hold`, stray-release safety, cross-thread contention (holder thread + 0.05s acquire → `False`), `hold`-timeout `TimeoutError`, `generate_text`-holds-gate probe, stream-busy-yield on forced `acquire=False`, summarizer-holds-gate probe; autouse fixture drains the gate before/after each test.
- `tests/test_resource_telemetry.py`: Probe tests — mocked nvidia-smi success parse (4096/1024/3072 → 25.0%), empty/malformed → `None`, `FileNotFoundError`/`SubprocessError` → `None`, multi-line first-line parsing; psutil RSS/VMS + `ImportError` → zeros; `LatencyTracker` success/error/`to_dict`, `track_stage`, `record_stage_latency`, `MAX_STAGE_HISTORY` cap, `get_system_telemetry_snapshot` shape; autouse `clear_latency_history` fixture.
- `tests/test_cache_invalidation.py`: `bound_chat_history` 50-turn bound + `MAX_CHAT_TURNS == 50` assert + orphan-assistant prune + empty passthrough; `count_documents`/`count_summaries` zero→2 roundtrips; Tier-3 hit returns `cached=True` with zero provider calls; `model_version` mismatch → `None` → regenerate.
- `tests/test_summarizer.py`: `MockSummarizerProvider` (records `generate_calls`, deterministic text); fast-path vs map-reduce dispatch, all-five-profile templates, `extract_page_references` clamping, cache-hit zero-call, `force_refresh`, model-version mismatch regeneration.
- `tests/test_citation_validator.py`: Fixture `RetrievalResult` with ranked snippets; perfect/hallucinated/abstention/abstention-with-citations/empty/ungrounded cases; `AiModel.validate_response` explicit-arg + fallback-to-`last_retrieval_result` integration.
- `tests/test_main_ui.py`: No Streamlit runtime — pure contract tests on the `{role, content, sources, verification, snippets}` chat-turn dict and the `SummaryResult.model_dump()` display dict (`cached`, `page_references`, `model_version`).
- `tests/test_hybrid_retriever.py`: CPU pinning, anchored default path, dense indexing/search, BM25, RRF, persistence/round-trip.
- `tests/test_local_llm.py`: Stream orchestration incl. `retrieval_result` precedence and `validate_response`.
- `tests/test_models.py`: Contract validation for all Pydantic models incl. `SummaryResult`.
- `tests/conftest.py`: Shared fixtures for the suite.

## Naming Conventions

**Files:**
- `snake_case.py`, one public class/service per file: `local_llm.py` → `AiModel` + `InferenceGate`; `resource_telemetry.py` → `get_gpu_memory_info`/`get_process_memory_info`/`LatencyTracker`/`track_stage`/`get_system_telemetry_snapshot` + `_LATENCY_HISTORY`/`MAX_STAGE_HISTORY`; `summarizer.py` → `Summarizer` + `extract_page_references` + `PROFILE_SYSTEM_INSTRUCTIONS`/`MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`; `citation_validator.py` → `CitationVerificationResult` + `validate_citations`/`extract_citations`/`is_abstention`; `hybrid_retriever.py` → `HybridRetriever` + `compute_rrf`; `doc_store.py` → `DocStore`; `prompt_budget.py` → module functions incl. `bound_chat_history`. Exceptions: `main.py` (entry, no class), `model_provider.py` (ABC + two schemas), `scripts/profile_resources.py` (`BenchmarkProvider` + `run_resource_profile`).

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `docs/`, `data/`, `.cache/`, `application_screenshots/`, `.devcontainer/`, `.planning/`, `.planning/research/` (profiler artifact dir).

**Tests:**
- Mirror pattern `test_<module>.py` → tests `tests/test_<module>.py` (e.g. `resource_telemetry.py` → `tests/test_resource_telemetry.py`, `local_llm.py` → `tests/test_local_llm.py` + `tests/test_concurrency_lock.py` for the gate facet, `prompt_budget.py` + `doc_store.py` counts → `tests/test_cache_invalidation.py`). New cross-cutting suites are named by concern (`test_concurrency_lock.py`, `test_resource_telemetry.py`, `test_cache_invalidation.py`), not by module. UI contracts that span modules live in `tests/test_main_ui.py` (no `main_ui.py` source module — it tests `main.py` tab display shapes).

## Where to Add New Code

**New single-active-LLM / concurrency behavior:**
- Primary code: `local_llm.py:26-90` (`InferenceGate`) — new gate API goes here as `@classmethod`; new timeout policy = call-site arg (`60.0` stream, `60.0` generate, `120.0` summarizer). Never add a second lock — extend this one.
- Call sites: gate-held generation in `local_llm.py:258-271` / `local_llm.py:293` / `summarizer.py:388`; keep the stream-yields-retry-notice vs non-stream-raises-`TimeoutError` asymmetry.
- Tests: `tests/test_concurrency_lock.py` (gate unit + generation/summarizer hold probes with the autouse drain fixture).

**New telemetry probe or widget row:**
- Primary code: `resource_telemetry.py` — new probe returns a plain dict or `None` (never raises; `logger.debug` on failure, matching `get_gpu_memory_info`/`get_process_memory_info`); new aggregation goes in `get_system_telemetry_snapshot`.
- UI: wire reads in `main.py:357-386` (branch on `None`, never try/except in the widget).
- Offline: extend the matching stage in `scripts/profile_resources.py:94-342` and the `profile_data` dict written to `.planning/research/RESOURCE_PROFILE.json`.
- Tests: `tests/test_resource_telemetry.py` (mock `subprocess.run`/`psutil`, assert `None`/zeros fallbacks).

**New multi-tier cache behavior (tiers, keys, invalidation):**
- Primary code: Tier 1 session keys in `main.py` (new `summary_*`-style keys must be added to the Clear All purge at `main.py:151-153`); Tier 3 predicates in `doc_store.py:get_summary` (read-time invalidation, never key-part); Tier 3 writes in `doc_store.py:save_summary` (`ON CONFLICT` upsert); bypass flags thread through `summarizer.py:summarize_document(force_refresh=...)`.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- Widget counts: new `count_*` methods next to `count_documents`/`count_summaries` (`doc_store.py:590-610`) if the telemetry widget must surface the new tier.
- Tests: `tests/test_cache_invalidation.py` (cap/counts/hit/invalidation), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New chat-memory / bounding behavior:**
- Primary code: `prompt_budget.py:131-152` (`bound_chat_history`) — turn-cap changes here; `main.py:38` (`MAX_CHAT_TURNS`) stays the single call-site constant; per-request token policy in `prompt_budget.py:57-129`; retrieval window width at `main.py:481`.
- Rule: every `chat_history` mutation goes through `append_chat_turn` (`main.py:389-395`) — never `st.session_state.chat_history.append` directly.
- Tests: `tests/test_cache_invalidation.py` (turn-cap contract), `tests/test_prompt_budget.py` (token budgeting).

**New summarization behavior (profiles, budgets, stages):**
- Primary code: `summarizer.py` — new profile = entry in `PROFILE_SYSTEM_INSTRUCTIONS` + `models.py:VALID_SUMMARY_PROFILES`; new token budget = module constant next to `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS`; new pipeline stage = private method next to `_bundle_pages`/`_summarize_map_reduce`; keep all generation inside the existing `InferenceGate.hold(timeout=120.0)` block.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- UI: wire controls in `main.py:579-664` (`profile_map`, radio, cache-key `summary_{doc_id}_{profile}`); session keys must be added to the Clear All purge (`main.py:151-153`).
- Tests: `tests/test_summarizer.py` (service), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New QA grounding / citation behavior:**
- Primary code: `citation_validator.py` — new citation syntax = `CITATION_REGEX`; new abstention phrasing = `CANONICAL_ABSTENTION_MARKERS`; new verdict fields = `CitationVerificationResult`; threshold change = `validate_citations` `0.95` comparison.
- Prompt rules: `prompt_budget.py:SYSTEM_GROUNDING_TEMPLATE` (the `[En]` rules + abstention sentence must stay in sync with the validator or precision will collapse).
- Facade: `local_llm.py:validate_response` stays the only caller path — `main.py` must call it, never `validate_citations` directly.
- Tests: `tests/test_citation_validator.py`.

**New retrieval behavior (ranking, fusion, search mode):**
- Primary code: `hybrid_retriever.py` — add methods alongside `search_dense`/`search_fts`/`search_hybrid`; pure ranking math goes in module-level functions next to `compute_rrf`. The retriever stays the sole index — do not add a second index object to session state.
- Embedding fn: `local_embedding.py:_embed_one` stays the injected CPU function; session state keeps exactly one `HybridRetriever` + one `LocalEmbedding` (embed-fn holder).
- Contracts first: extend `EvidenceSnippet`/`RetrievalResult` in `models.py` before wiring consumers.
- Tests: `tests/test_hybrid_retriever.py`.

**New ingestion/extraction behavior:**
- Primary code: `docling_reader.py` (structured), `pdf_reader.py` (legacy), `ocr_fallback.py` (scanned pages), `visual_analyzer.py` (visual elements); validation in `upload_validation.py`.
- Wire-up: `main.py:230-288` extraction + sole-index build block; persistence via `doc_store.py`.
- Tests: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_upload_validation.py`.

**New inference provider or prompt behavior:**
- Primary code: new provider subclassing `BaseModelProvider` in `model_provider.py` next to `groq_provider.py`/`llama_cpp_provider.py`; prompt assembly in `prompt_budget.py`; delegation in `local_llm.py`. `Summarizer` consumes only `provider.generate_text` + `provider.get_capabilities` — keep new providers compatible with both streaming and non-streaming paths. All new token-producing paths must execute under `InferenceGate`.
- Tests: `tests/test_model_provider.py`, `tests/test_llama_cpp_provider.py`, `tests/test_local_llm.py`, `tests/test_prompt_budget.py`, `tests/test_concurrency_lock.py` (gate-hold probe for the new path).

**New persisted metadata:**
- Primary code: `models.py` (Pydantic contract) → `doc_store.py` (table + migration in `MIGRATIONS`, record/get methods + `count_*` if widget-visible).
- Tests: `tests/test_doc_store.py`, `tests/test_models.py`, `tests/test_cache_invalidation.py` (if cache-tier).

**Utilities:**
- Shared helpers: root-level `snake_case.py` module + direct import (`from x import Y`) — no packages, no barrel files. `resource_telemetry.py` is the exemplar: stdlib + optional-dependency probes with never-raise fallbacks and no project imports.

## Dependency Graph

```text
main.py
 ├── local_llm.py (AiModel + InferenceGate)
 │    ├── model_provider.py (BaseModelProvider, HealthStatus, ProviderCapabilities)
 │    ├── groq_provider.py ──► model_provider.py
 │    ├── llama_cpp_provider.py ──► model_provider.py
 │    ├── prompt_budget.py (assemble_grounded_messages, bound_chat_history, standalone)
 │    ├── citation_validator.py ──► models.py (RetrievalResult, type-only bound)
 │    ├── hybrid_retriever.py ──► models.py, vector_index.py
 │    │    ├── models.py (Chunk, BBox, EvidenceSnippet, RetrievalResult, SummaryResult)
 │    │    └── vector_index.py (stdlib only: math, typing)
 │    ├── local_embedding.py ──► models.py, vector_index.py
 │    │    └── sentence-transformers (external, CPU-pinned)
 │    └── pdf_reader.py ──► pypdf, langchain-text-splitters (external)
 ├── summarizer.py ──► local_llm.py (InferenceGate only), model_provider.py, models.py, prompt_budget.py, doc_store.py
 ├── hybrid_retriever.py (direct: sole-index writes + query)
 ├── local_embedding.py (direct: embed-fn holder + CR-01 re-embed)
 ├── resource_telemetry.py (stdlib + nvidia-smi subprocess + optional psutil; no project imports)
 ├── docling_reader.py ──► models.py, pdf_reader.py (fallback)
 ├── doc_store.py ──► models.py (Chunk, Document, Page, EvidenceElement, SummaryResult)
 ├── ocr_fallback.py
 ├── visual_analyzer.py ──► doc_store.py (record_evidence_elements)
 ├── upload_validation.py (standalone)
 ├── scripts/profile_resources.py ──► doc_store.py, hybrid_retriever.py, local_embedding.py,
 │                                      local_llm.py (InferenceGate), model_provider.py, models.py,
 │                                      pdf_reader.py, resource_telemetry.py, summarizer.py
 └── models.py (no project imports — leaf contract module)

External-only leaves: prompt_budget.py, upload_validation.py, vector_index.py, resource_telemetry.py
```

**Import direction (must stay acyclic):** `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `local_llm.py` (gate-only import; `local_llm.py` never imports `summarizer.py`); `summarizer.py` → `doc_store.py`, `models.py`; `docling_reader.py` → `pdf_reader.py`; `scripts/profile_resources.py` → everything except `main.py`; everything persistence-shaped → `models.py`. `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py`, `resource_telemetry.py` import no project modules; `citation_validator.py` imports only `models.py`.

## Special Directories

**data/:**
- Purpose: Runtime SQLite + LanceDB persistence (incl. `document_summaries` rows in `documents.db`, `fallback_store.json` under `data/lancedb/` without LanceDB).
- Generated: Yes (created on first upload/index/summarize run).
- Committed: No (gitignored; only the directory placeholder exists in the repo).

**.cache/:**
- Purpose: Tier-2 per-document `{pages,chunks,manifest}.json` cache keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes (best-effort write per upload).
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
- Purpose: Sample PDFs exercised by ingestion/extraction tests AND the resource profiler (`clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`, plus `generate_corpus.py`).
- Generated: No (checked-in fixtures).
- Committed: Yes.

---

*Structure analysis: 2026-10-12*
