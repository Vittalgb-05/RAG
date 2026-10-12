# External Integrations

**Analysis Date:** 2026-10-12

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
- Groq Cloud — chat completions via the `groq` Python SDK (`groq==0.15.0`, guarded `try/except ImportError → Groq=None` in `groq_provider.py:12-15`)
  - SDK/Client: `groq.Groq(api_key)` (`groq_provider.py:50-52`); `chat.completions.create` non-stream (`groq_provider.py:116-126`) and stream yielding `chunk.choices[0].delta.content` (`groq_provider.py:148-161`)
  - Model: `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-25`)
  - Auth: `GROQ_API_KEY` with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); missing key/package yields `unreachable` `HealthStatus`, never raises (`groq_provider.py:59-83`)
  - Selection: used only when the local server is unhealthy; chosen in `AiModel._detect_provider` (local → Groq → local-with-diagnostics) and re-probed on every unhealthy `check_health()` (`local_llm.py:46-89`)
  - Capabilities: `supports_vision=False, is_local=False, supports_streaming=True` (`groq_provider.py:85-97`)
  - Vision: not supported — `analyze_image` raises `NotImplementedError` (`groq_provider.py:163-170`); visual evidence degrades to `[Visual element: vision analysis unsupported by active model]` (`visual_analyzer.py:246-249`)

**Model hosting:**
- HuggingFace Hub (embedding weights) — `sentence-transformers` downloads `all-MiniLM-L6-v2` on first run, cached in `~/.cache/huggingface/` (`local_embedding.py:40`); instantiated CPU-pinned `SentenceTransformer(model_name, device="cpu")` (`local_embedding.py:24,40`); no token required for the public model
- HuggingFace Hub (GGUF weights) — `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB) + `mmproj-f16.gguf` (~450 MB) downloaded manually into local `models/` (`docs/LOCAL_INFERENCE.md:31-44`); consumed by the external `llama-server` process, never imported in Python
- Docling model zoo — first `DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(...)})` construction (`docling_reader.py:103-109`) downloads layout/table-structure weights on CPU; converter is lazily built inside `extract_text()` and injectable via `DoclingReader(converter=...)` for tests (`docling_reader.py:37-71`)

## Data Storage

**Databases:**
- SQLite via stdlib `sqlite3` (`doc_store.py:12,103-588`)
  - Connection: file path `data/documents.db`, passed to `DocStore(...)` in the `main.py:150` upload loop; parent dirs auto-created (`doc_store.py:115-116`); `data/` is gitignored (`.gitignore:10`)
  - Tables v1 (`SCHEMA_V1_DDL`, `doc_store.py:17-55`): `documents` (PK `doc_id`, UNIQUE `sha256`), `pages` (PK `doc_id,page_num`), `chunks` (PK `chunk_id`)
  - Tables v2 (`SCHEMA_V2_DDL`, `doc_store.py:57-71`): `evidence_elements` (PK `element_id`, FK `doc_id → documents` with `ON DELETE CASCADE`)
  - Tables v3 — Phase 5 summaries (`SCHEMA_V3_DDL`, `doc_store.py:73-94`): `document_summaries` (PK `summary_id`, UNIQUE `(sha256, profile)`, FK `doc_id → documents` with `ON DELETE CASCADE`; columns `summary_id/doc_id/sha256/profile/summary_text/page_references_json/created_at/model_version`) plus indexes `idx_summaries_sha256` and `idx_summaries_doc_id`
  - Mode: WAL + `busy_timeout=5000` + `foreign_keys=ON` (`doc_store.py:131-135`); schema versioned via `PRAGMA user_version` with `MIGRATIONS = {1: V1, 2: V2, 3: V3}` dict (`doc_store.py:96-100,141-154`)
  - Lifecycle: per-operation connection opened/closed inside `_connect()` context manager — Windows-lock and Streamlit-rerun safe (`doc_store.py:122-139`)
  - Writes: `upsert_document` / `record_page` / `record_chunks` (single-transaction `executemany`) / `record_evidence_elements` / `save_summary` (upsert on `(sha256, profile)`, `doc_store.py:425-463`) (`doc_store.py:156-423`); reads: `get_by_sha` (dedup), `get_chunks_for_doc` (CR-01 index restore after restart + summarizer page reconstruction fallback), `get_evidence_for_doc`, `get_summary(sha256, profile, model_version)` (returns `SummaryResult(cached=True)` or `None` on miss/version-mismatch, `doc_store.py:465-514`), `list_summaries_for_doc`, `delete_summaries_for_doc` (`doc_store.py:188-573`); `bbox` round-trips as `bbox_json` (`doc_store.py:308,344-349`); `page_references` round-trips as `page_references_json` with tolerant `json.loads` fallback to `[]` (`doc_store.py:435,501-503,539-541`)
  - Phase-5 access pattern: `Summarizer.summarize_document` checks `doc_store.get_summary(sha256, profile, model_version)` before generation and calls `doc_store.save_summary(result)` after (`summarizer.py:330-335,414-416`); `force_refresh=True` bypasses the read path; `main.py:586-588` constructs `Summarizer(provider=ai_model.provider, doc_store=doc_store)` per summary request
- LanceDB embedded store via `lancedb>=0.17.0` + `pyarrow>=14.0.0` (`hybrid_retriever.py:18-24`, `requirements.txt:14-15`)
  - Connection: local filesystem directory `DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"` (repo-root anchored, never CWD-relative) opened with `lancedb.connect(str(db_uri))` (`hybrid_retriever.py:27,96,115`); parent dirs auto-created (`hybrid_retriever.py:114,167`); `data/` is gitignored (`.gitignore:10`); verified anchored-absolute in `tests/test_hybrid_retriever.py:37-43`
  - Table `chunks`: one persistent table holding `chunk_id` (merge key) / `doc_id` / `filename` / `page` / `content` / `vector` (384-dim `float` list) / `extraction` / `char_start` / `char_end` / `bbox_json` (`hybrid_retriever.py:296-309`); reopened on restart via `db.table_names()` → `open_table("chunks")` (`hybrid_retriever.py:189-200`); row count via `len(table)` (`hybrid_retriever.py:206-213`)
  - Writes: `index_chunks(chunks, embeddings)` normalises `Chunk | dict` → dicts, computes missing embeddings via `embedding_fn`, dedups fallback by `chunk_id`, then `create_table("chunks", mode="create")` on first write or `merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(records)` (delete-then-`add` fallback when `merge_insert` is absent) (`hybrid_retriever.py:226-340`); `add_vector(vector, doc)` compatibility shim (`hybrid_retriever.py:342-344`); `delete_document(doc_id)` removes fallback rows in reverse index order plus `table.delete("doc_id = '...'")` (`hybrid_retriever.py:346-363`)
  - Reads: `search_dense(query_vector, k)` → `table.search(vec).limit(k)` → `score = max(0.0, 1.0 - _distance)` (`hybrid_retriever.py:365-403`); `has_document(doc_id)` → `table.search().where("doc_id = '...'").limit(1)` (`hybrid_retriever.py:215-224`); `count_chunks()` (`hybrid_retriever.py:206-213`); all filter literals single-quote-escaped (`doc_id.replace("'", "''")`, `cid.replace("'", "''")`) per `tests/test_hybrid_retriever.py:306-341`
  - Persistence verified across re-instantiation in `tests/test_hybrid_retriever.py:98-124` (write → close → reopen → identical chunks + cosine scores); deletion isolation in `tests/test_hybrid_retriever.py:127-151`
  - Fallback when LanceDB missing/unhealthy: in-memory `VectorIndex(distance_metric="cosine")` (`hybrid_retriever.py:105-108`) + disk JSON `db_uri / "fallback_store.json"` (`hybrid_retriever.py:110,126-141,162-187`) loaded on init, flushed on `close()` / non-LanceDB `index_chunks` / `delete_document`; lifecycle `close()` + `__enter__`/`__exit__` (`hybrid_retriever.py:149-160`); dynamic `set_embedding_fn(fn)` re-wires both retriever and fallback store (`hybrid_retriever.py:143-147`); covered in `tests/test_hybrid_retriever.py:154-171,344-390`
  - Wiring: `main.py` owns one `HybridRetriever` in `st.session_state.hybrid_retriever` (`main.py:58`), constructs it with `embedding_fn=local_embedding._embed_one` on upload (`main.py:205-206`) and on restart restore (`main.py:272-273`), indexes via `index_chunks(chunk_dicts, embeddings.tolist())` (`main.py:212,277`), closes on Clear All (`main.py:137-139`), and prefers it as `active_retriever = hybrid_retriever or local_embedding` for chat (`main.py:407`); `AiModel.ask_a_question_from_pdf_stream` dispatches `isinstance(local_embedding, HybridRetriever) → search_hybrid(query, k=10)` (`local_llm.py:105,142-144`)

**In-process services (no network, no new pip deps — Phase 5, verified 2026-10-12):**
- `Summarizer` (`summarizer.py:152-418`): hierarchical multi-profile summarization over canonical `Page` models; fast path (`total_tokens <= 2500` → `_summarize_single_pass`, `summarizer.py:387-389`) vs map-reduce (`_bundle_pages(max_tokens=2000)` → per-batch `MAP_PROMPT_TEMPLATE` → optional two-half consolidation when `combined > 2500 tokens and > 3 batches` → `REDUCE_PROMPT_TEMPLATE`, `summarizer.py:232-298`); page refs extracted via `extract_page_references(text, max_page)` and clamped to document max (`summarizer.py:135-149,395-396`); result `SummaryResult(summary_id=summ_<hex16>, cached=False)` then persisted (`summarizer.py:401-416`)
- `citation_validator.py` (`citation_validator.py:52-181`): `extract_citations` (unique sorted `[En]` ranks via `CITATION_REGEX`), `is_abstention` (12 `CANONICAL_ABSTENTION_MARKERS`), `validate_citations(response_text, retrieval_result)` — empty → invalid; abstention without citations → valid (`precision=1.0`); abstention with citations → invalid; zero-citation non-abstention → invalid ungrounded; otherwise `precision = valid/total`, `is_valid = precision >= 0.95` (`citation_validator.py:96-181`); consumed by `AiModel.validate_response` storing `last_retrieval_result`/`last_verification_result` (`local_llm.py:44-45,171,192-210`)

**Embedding pipeline (CPU-only, zero VRAM):**
- `LocalEmbedding(model_name="all-MiniLM-L6-v2", device="cpu")` → `SentenceTransformer(model_name, device="cpu")` (`local_embedding.py:20-40`); batch `get_embeddings` with `normalize_embeddings=True` L2 normalisation (`local_embedding.py:52-57`); `_embed_one(text)` single-string helper wired as both `VectorIndex` and `HybridRetriever` query embedder (`local_embedding.py:45-50`, `main.py:206,273`); CPU pinning asserted in `tests/test_hybrid_retriever.py:22-33` (`SentenceTransformer` called once with `("all-MiniLM-L6-v2", device="cpu")`)
- Index handoff: `LocalEmbedding.get_embeddings(texts)` → numpy array → `.tolist()` → `HybridRetriever.index_chunks(chunk_dicts, embeddings)` (`main.py:212,277`); `build_index` remains the legacy in-memory path (`local_embedding.py:59-76`)

**Full-text / hybrid retrieval (BM25 + RRF):**
- Pure function `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` — `RRF(d) = Σ 1/(k_rrf + rank)` over dense + FTS rank lists, returns `(chunk_id, rrf_score, final_rank, dense_rank|None, fts_rank|None)` sorted by descending composite score (`hybrid_retriever.py:31-76`, `DEFAULT_RRF_K = 60` at `hybrid_retriever.py:28`); math verified in `tests/test_hybrid_retriever.py:174-194` (doc_b > doc_a > doc_d > doc_c)
- `create_fts_index()` → `table.create_fts_index("content", replace=True)` when supported (`hybrid_retriever.py:405-413`); `search_fts(query, k)` → `table.search(query, query_type="fts").limit(k)` with `_score` passthrough, degrading to `_bm25_search_fallback` on any exception or empty result (`hybrid_retriever.py:478-505`)
- `_bm25_search_fallback(query, k)` (`hybrid_retriever.py:415-476`): tokenises `re.findall(r"\w+")`, drops 1-char tokens, k1=1.5 / b=0.75, single-pass `df_map` (O(N·|Q|)), reads fallback docs or up-to-10000 LanceDB rows when fallback is empty; keyword boost verified `RTX-3050-Ti → chk_exact_rtx` (`tests/test_hybrid_retriever.py:197-229`), semantic path verified `company profits → chk_fiscal` (`tests/test_hybrid_retriever.py:232-264`)
- `search_hybrid(query, k, k_rrf)` (`hybrid_retriever.py:507-612`): candidate pool `max(k*2, 10)` per arm → dense via `embedding_fn` + `search_dense` → FTS via `search_fts` → `compute_rrf` fuse → top-k `EvidenceSnippet(chunk_id/score/rank/dense_rank/fts_rank/...)` in canonical `RetrievalResult(query, snippets, total_candidates, search_mode)` where `search_mode ∈ {hybrid,dense,fts,fallback}`; empty query / `k<=0` returns empty `RetrievalResult` (`tests/test_hybrid_retriever.py:295-303`); shared identity (prompt `formatted_evidence()` `[E1] (file, p. N)` ≡ UI `source_labels()` chips) verified in `tests/test_hybrid_retriever.py:267-292`
- Legacy facades preserved: `HybridRetriever.search(question, k) → list[(doc_dict, score)]` and `get_context(question, k) → formatted_evidence()` (`hybrid_retriever.py:614-622`); `LocalEmbedding.search_hybrid` remains dense-only (`search_mode="dense"`, `local_embedding.py:84-109`)

**File Storage:**
- Local filesystem only
  - LanceDB files under `data/lancedb/` (live `fallback_store.json` observed; full `*.lance` tables materialise once `index_chunks` runs with `lancedb` installed); gitignored (`.gitignore:10`)
  - Deterministic JSON cache under `.cache/<sha256>/<CONFIG_VERSION>/{pages.json,chunks.json,manifest.json}` written best-effort in `main.py:278-289`; path computed by `cache_dir_for` with strict 64-hex validation (`models.py:17-30`); `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`); `.cache/` is gitignored (`.gitignore:17`)
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
- In-process Streamlit cache: `@st.cache_resource(show_spinner=False)` memoizes one `AiModel` (and its active provider) per server process (`main.py:68-76`); `Summarizer` is constructed per request from the cached `ai_model.provider` so summaries always use the active backend (`main.py:586`)
- SQLite summary cache: `document_summaries` keyed UNIQUE `(sha256, profile)` with `model_version` invalidation (`doc_store.py:73-94,465-514`); second request for the same document+profile returns `cached=True` without any LLM call (`summarizer.py:330-335`)
- Per-session persistent retriever: `HybridRetriever` in `st.session_state` backed by `data/lancedb/` on disk, surviving server restarts (`main.py:58,205-212,272-277`); legacy per-session in-memory `VectorIndex` inside `LocalEmbedding` remains as the degraded path (`main.py:57,254-256`); dedup-hit-after-restart restores both `DocStore.get_chunks_for_doc` and `HybridRetriever.index_chunks` (`main.py:193-200,272-277`)
- No Redis / external cache

## Authentication & Identity

**Auth Provider:**
- None. No user accounts or sessions. The only credential is the optional `GROQ_API_KEY`, resolved with precedence `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); absence yields an `unreachable` `HealthStatus`, not an error.

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry/OpenTelemetry).

**Logs:**
- `logging` module (`getLogger(__name__)`) in the Phase 3–5 modules: `logger.info` for Docling fallback paths (`docling_reader.py:96,184,281`), LanceDB connect/open-table/index lifecycle (`hybrid_retriever.py:117,139,198,315`), summarizer fast-path/map-reduce routing and cache hits (`summarizer.py:334,388,391,416`); `logger.warning` for conversion/crop failures (`docling_reader.py:289`, `ocr_fallback.py:68,128`, `visual_analyzer.py:60,228`), LanceDB init/search/persistence degradation (`hybrid_retriever.py:119,141,187,200,390,402,503,540`); `logger.error` for page-level OCR faults and VLM failures (`ocr_fallback.py:307`, `visual_analyzer.py:133,238`) plus LanceDB persist/delete faults (`hybrid_retriever.py:336,361`); `logger.debug` for FTS-index notices and BM25 table-read fallback (`hybrid_retriever.py:413,430`)
- Module-prefixed `print()` for developer diagnostics in legacy modules: `[LocalEmbedding]` (`local_embedding.py:21,23,58`), `[DocStore]` migrations (`doc_store.py:129`), `[UploadValidation]` (`upload_validation.py:106`), pypdf success line (`pdf_reader.py:113`)
- User-facing feedback via Streamlit (`st.status`, `st.error`, `st.warning`, `st.info`, `st.success`, `st.progress`) — never `print` (`main.py:90-121,148-310,351-410`); summarizer tab surfaces `st.info` when no document is indexed (`main.py:542`) and streams summary progress inline (`main.py:538-622`)
- Provider health surfaced through the `HealthStatus` schema rendered in the sidebar (`main.py:93-121`); VLM provenance kept separate as `EvidenceElement(source="vlm:<model_name>")` so visual approximations never contaminate ground-truth tables (`visual_analyzer.py:240-262`); retrieval provenance carried per-snippet (`dense_rank`/`fts_rank`/`search_mode`) from `HybridRetriever.search_hybrid` through `RetrievalResult` into prompts and citations (`hybrid_retriever.py:590-611`, `models.py:141-200`); citation precision diagnostics carried in `CitationVerificationResult(message, precision, valid/hallucinated_citations)` (`citation_validator.py:35-49`, `local_llm.py:192-210`)

## CI/CD & Deployment

**Hosting:**
- Primary: local Windows workstation (RTX 3050, 4 GB VRAM ceiling) — zero-egress local inference (`docs/LOCAL_INFERENCE.md`, `llama_cpp_provider.py:1-6`); embeddings (`sentence-transformers` CPU) and retrieval (LanceDB disk / BM25) add zero VRAM load by construction; summarizer map-reduce runs sequentially for the same reason (`summarizer.py:232-244`)
- Fallback: Streamlit Community Cloud with `GROQ_API_KEY` in the Cloud secrets panel; ephemeral disk (LanceDB + SQLite + `.cache/` best-effort only)
- Devcontainer/Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` with Streamlit on port 8501 (`.devcontainer/devcontainer.json`)

**CI Pipeline:**
- GitHub Actions — `.github/workflows/ci.yml` (sole workflow)
  - Triggers: push / pull_request on `main` (`.github/workflows/ci.yml:3-7`)
  - Job `test` on `ubuntu-latest`: checkout (`actions/checkout@v4`) → setup Python `"3.11"` with pip cache (`actions/setup-python@v5`) → `pip install -r requirements.txt` (15 lines, unchanged by Phase 5) + `pip install -r requirements-test.txt` → `ruff check .` + `ruff format --check .` → `python tests/data/corpus/generate_corpus.py` → `pytest tests/ -v` (`.github/workflows/ci.yml:9-41`); suite now includes `tests/test_summarizer.py` + `tests/test_citation_validator.py` alongside the 14-file pre-existing set
  - No deploy job, no artifact upload, no coverage gate
- Benchmark (manual): `python scripts/benchmark_baseline.py` measures pypdf extraction latency, 1000/200 chunking, CPU `SentenceTransformer("all-MiniLM-L6-v2", device="cpu")` load + batch encode latency, `VectorIndex` linear-scan latency over 100/500/1000 vectors, and RSS via `psutil`; writes `.planning/research/BASELINE_BENCHMARK.json` (`scripts/benchmark_baseline.py:1-174`)

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — optional; only needed for the cloud fallback path (`groq_provider.py:37-49`); no other env var is read in app code

**Secrets location:**
- Local: `.env` in project root (gitignored, `.gitignore:1`) loaded via `python-dotenv` inside `load_ai_model()` (`main.py:75`)
- Cloud: Streamlit secrets (`st.secrets["GROQ_API_KEY"]`, `groq_provider.py:40-44`)
- No `.streamlit/secrets.toml` is committed; never quote secret values in docs or code

**Local runtime state (gitignored, existence-only):**
- `.env` — API key (`main.py:75`)
- `data/documents.db` — SQLite store including `document_summaries` (`.gitignore:10`, `main.py:150`)
- `data/lancedb/` — LanceDB tables + `fallback_store.json` (`hybrid_retriever.py:27,110`; `.gitignore:10`; observed live `data/lancedb/fallback_store.json`)
- `.cache/<sha256>/<CONFIG_VERSION>/` — extraction cache (`.gitignore:17`, `main.py:278-289`)
- `models/` — local GGUF weights (downloaded per `docs/LOCAL_INFERENCE.md:31-44`, served by external `llama-server`)
- `~/.cache/huggingface/` — sentence-transformers + Docling model downloads (outside repo)

## Test Mock Seams (offline — no GPU, no network, no API keys)

- `httpx.MockTransport(handler)` injected as `LlamaCppProvider(transport=...)` — covers `GET /health` (200/503/error/connect-fail) and `POST /v1/chat/completions` (JSON + SSE `data: [DONE]`) (`tests/test_llama_cpp_provider.py`, `llama_cpp_provider.py:26,34,39-43`)
- `MagicMock` Groq client (`mock_groq_client`, `tests/conftest.py:18-48`) yielding canned `delta.content` tokens `["This ", "is ", "a ", "grounded ", "answer."]`; `fake_env_groq_key` sets a dummy `GROQ_API_KEY` (`tests/conftest.py:11-16`)
- `MagicMock` SentenceTransformer (`mock_sentence_transformer`, `tests/conftest.py:51-81`) returning deterministic 384-dim L2-normalised `numpy.float32` vectors; CPU-pinning asserted via `MagicMock` class replacement in `tests/test_hybrid_retriever.py:22-33`
- `MockLlamaCppProvider(BaseModelProvider)` healthy/unhealthy double recording `stream_calls` (`tests/conftest.py:91-161`)
- `MockSummarizerProvider(BaseModelProvider)` recording `generate_calls` and returning deterministic citation-bearing summaries (`tests/test_summarizer.py:16-50`); `CitationFreeProvider` variant covers citation-less output (`tests/test_summarizer.py:288`); `tmp_path`-isolated `DocStore` covers cache lifecycle + `model_version` invalidation (`tests/test_summarizer.py:198-341`)
- Citation fixtures: `tests/test_citation_validator.py` covers perfect precision, hallucinated rank, valid abstention, abstention-with-citations, empty response, and ungrounded response (`tests/test_citation_validator.py:54-140`)
- `tmp_path`-isolated `HybridRetriever(db_uri=tmp_path / ...)` per test (no shared `data/lancedb/` mutation) plus `monkeypatch.setattr("hybrid_retriever.lancedb", None)` / `monkeypatch.setattr(hybrid_retriever, "lancedb", None)` for fallback-path tests (`tests/test_hybrid_retriever.py:46-390`); deterministic `_make_unit_vector(seed, dim=384)` numpy helper (`tests/test_hybrid_retriever.py:12-19`)
- Constructor injection seams (no network/install required): `DoclingReader(converter=...)` (`docling_reader.py:37-71`), `OcrEngine(recognizer=..., renderer=...)` (`ocr_fallback.py:49-61`), `VisualAnalyzer(region_detector=..., cropper=...)` (`visual_analyzer.py:33-45`); `FakeFitz` module double via `monkeypatch.setattr("visual_analyzer.fitz", FakeFitz)` (`tests/test_visual_analyzer.py:286-332`)
- Corpus fixtures: `sample_pdf_path` → `tests/data/corpus/clean_digital.pdf` (`tests/conftest.py:84-88`); full 16-file suite `tests/test_*.py` (citation_validator, doc_store, docling_reader, hybrid_retriever, llama_cpp_provider, local_embedding, local_llm, main_ui, model_provider, models, ocr_fallback, pdf_reader, prompt_budget, summarizer, upload_validation, vector_index, visual_analyzer)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (Groq fallback is a direct SDK call, not a webhook; llama-server is localhost REST, not external; LanceDB is an embedded in-process library, not a network service; summarizer/citation_validator are in-process pure-Python services with no network surface)

---

*Integration audit: 2026-10-12*
