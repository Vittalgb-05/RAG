# Technology Stack

**Analysis Date:** 2026-10-12

## Languages

**Primary:**
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `model_provider.py`, `groq_provider.py`, `litellm_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`, `local_embedding.py`, `vector_index.py`, `hybrid_retriever.py`, `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `doc_store.py`, `models.py`, `upload_validation.py`, `summarizer.py`, `citation_validator.py`, `resource_telemetry.py`, `scripts/benchmark_baseline.py`, `scripts/profile_resources.py`, `tests/`)

**Secondary:**
- JSON — `.devcontainer/devcontainer.json`, disk cache payloads `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json` written by `main.py:278-289`, LanceDB fallback payload `data/lancedb/fallback_store.json` written by `hybrid_retriever.py:162-187`, summary `page_references_json` serialised via `json.dumps` in `doc_store.py:435`
- Markdown — docs only (`README.md`, `docs/LOCAL_INFERENCE.md`, `CLAUDE.md`); generated summary text itself is Markdown with `##`/`###` profile templates (`summarizer.py:30-104`)
- SQL (SQLite DDL inline in Python) — `doc_store.py:17-94` (`SCHEMA_V1_DDL`, `SCHEMA_V2_DDL`, `SCHEMA_V3_DDL`, `MIGRATIONS`)
- SQL (LanceDB filter strings inline in Python) — `doc_id = '...'` / `chunk_id IN (...)` predicates in `hybrid_retriever.py:220,331,358`
- No JavaScript/TypeScript/CSS — UI is 100% Streamlit Python

## Runtime

**Environment:**
- CPython 3.11 locally via `streamlit run main.py` (`main.py:1-13`, `.devcontainer/devcontainer.json:22`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py`, serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:22-32`)
- CI: GitHub Actions `ubuntu-latest` with `actions/setup-python@v5` pinned to `"3.11"` with pip cache (`.github/workflows/ci.yml:9-22`)
- Target inference host: Windows 11 + NVIDIA RTX 3050 Laptop GPU (4 GB VRAM); VRAM budget ~3,260 MB peak documented in `docs/LOCAL_INFERENCE.md:7-18`
- External inference server (not Python): `llama-server` (llama.cpp CUDA build) on `http://127.0.0.1:8080` — see INTEGRATIONS.md

**Package Manager:**
- pip
- Runtime deps: `requirements.txt` (17 entries, mix of `==` pins and `>=` floors — see table below; **verified 2026-10-12: Phase 7 adds `litellm>=1.50.0` (`requirements.txt:17`)**; Phase 6 added `psutil>=6.1.0` (`requirements.txt:16`))
- Test/benchmark deps: `requirements-test.txt` (4 entries: `pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0` — psutil now duplicated as runtime + test dep)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`)

## Frameworks

**Core:**
- Streamlit `==1.42.0` — entire UI layer: `st.set_page_config` (`main.py:38-43`), sidebar (`main.py:83-323`), `st.file_uploader` (`main.py:302-308`), `st.chat_input` / `st.chat_message`, `st.tabs`, `st.status`, `st.cache_resource` (`main.py:84-92`), `st.write_stream`; privacy controls `st.toggle("Enable Cloud Inference")` + `st.dialog` consent + `st.selectbox("Cloud Provider")` + `st.text_input(type="password")` (`main.py:108-210`); session state holds `hybrid_retriever` alongside `local_embedding` (`main.py:58`)
- Pydantic `==2.11.9` — canonical data models and provider schemas (`models.py:33-138`); `Chunk` (`models.py:54`), `EvidenceSnippet` (`models.py:141`), `RetrievalResult` with `search_mode: Literal["hybrid","dense","fts","fallback"]` (`models.py:170-180`); Phase 5 adds `SummaryResult` + `SummaryProfile` (`models.py:208-235`) and `CitationVerificationResult` frozen schema (`citation_validator.py:35-49`)
- httpx `>=0.28.0` — HTTP client for the local llama-server provider with explicit timeouts (`llama_cpp_provider.py:13,39-43`); also the offline test seam via `httpx.MockTransport` (`tests/test_llama_cpp_provider.py`)
- sentence-transformers `==3.4.1` — local CPU-pinned embedding wrapper (`local_embedding.py:7,40`); default model `all-MiniLM-L6-v2` (`local_embedding.py:22`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,57`); device pinned `device="cpu"` (`local_embedding.py:24,40`) to preserve 100% GPU VRAM for VLM inference (RETR-01)

**Phase 7 — LiteLLM multi-provider cloud adapter (one new runtime dep, verified 2026-10-12):**
- `litellm_provider.py` (346 lines) — `LiteLLMProvider(BaseModelProvider)` unified cloud adapter routing `litellm.completion` to Groq / OpenAI / Anthropic (`litellm_provider.py:101-346`); guarded `try/except ImportError → litellm = None` with `unreachable` `HealthStatus` + `RuntimeError("LiteLLM is not installed.")` at use sites (`litellm_provider.py:18-21,140-150,202-203,251-252,305-306`); consent gate `_assert_consent()` raising `PermissionError("Cloud transmission blocked... (INF-04, UI-04)")` at the top of `generate_text` / `stream_text` / `analyze_image` (`litellm_provider.py:132-138,201,250,302`); bounded calls `timeout=30.0` + `num_retries=2` defaults passed as `litellm.completion(timeout=..., num_retries=...)` (`litellm_provider.py:104-111,212-221,263-273,327-335`); temperature clamped `0.0–2.0` (`litellm_provider.py:205,254`); vision via base64 data-URI `image_url` payload gated on `VISION_SUPPORTED_PREFIXES` (`openai/gpt-4o*`, `anthropic/claude-3*`) else `NotImplementedError` (`litellm_provider.py:31-36,308-312,314-324`); `close()` is a stateless no-op (`litellm_provider.py:344-346`)
- Model routing: `DEFAULT_CLOUD_MODEL = "groq/llama-3.3-70b-versatile"` (`litellm_provider.py:23`); `KNOWN_CONTEXT_WINDOWS = {groq: 131072, openai: 128000, anthropic: 200000}` (`litellm_provider.py:25-29`); `get_capabilities()` derives `context_window` by provider prefix (fallback 128000), `supports_vision` by prefix match, `is_local=False`, `supports_streaming=True` (`litellm_provider.py:165-181`)
- Key resolution: `_resolve_api_key_for_model(model_name, explicit_key)` — explicit arg → `st.session_state.cloud_api_keys[prefix]` dict → legacy `st.session_state.cloud_api_key` → `st.secrets[VAR]` → `os.environ[VAR]`, with `{"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}` map (`litellm_provider.py:39-85`)
- Wiring: `main.py:29` imports `LiteLLMProvider`; sidebar constructs per model/key change as `LiteLLMProvider(model_name=cloud_model, api_key=active_key or None, user_consented=True)` and caches in `st.session_state.active_cloud_provider` (`main.py:219-237`); `AiModel.set_cloud_mode(True, cloud_provider=...)` routes all generation through it (`main.py:237`, `local_llm.py:139-160`); `AiModel._detect_provider` returns the injected cloud provider when `cloud_mode=True`, else legacy `GroqProvider` healthy-check fallback, else local `LlamaCppProvider` (`local_llm.py:162-179`)
- UI consent state: `user_consented=False`, `cloud_mode=False`, `cloud_provider="groq"`, `cloud_model="groq/llama-3.3-70b-versatile"`, `cloud_api_keys={"groq": "", "openai": "", "anthropic": ""}` + legacy `cloud_api_key=""` all initialised in the session-state loop (`main.py:67-73`)

**Phase 5 — summarization & citation validation (zero new third-party deps, verified 2026-10-12):**
- `summarizer.py` (418 lines) — `Summarizer(provider: BaseModelProvider, doc_store)` with `summarize_document` / `_summarize_single_pass` / `_summarize_map_reduce` / `_bundle_pages` / `_format_page_batch` (`summarizer.py:152-418`); imports stdlib only (`datetime`, `logging`, `re`, `typing`, `uuid` in `summarizer.py:10-14`) plus internal `model_provider`, `models`, `prompt_budget` (`summarizer.py:16-18`); no new pip package
- `citation_validator.py` (181 lines) — pure functions `extract_citations` / `is_abstention` / `validate_citations` plus frozen `CitationVerificationResult` (`citation_validator.py:35-181`); imports stdlib only (`logging`, `re` in `citation_validator.py:9-10`) plus `pydantic` (`citation_validator.py:11`, already pinned `==2.11.9`) and internal `models.RetrievalResult` (`citation_validator.py:12`); no new pip package
- Wiring: `main.py` imports `Summarizer`, instantiates per summary request as `Summarizer(provider=ai_model.provider, doc_store=doc_store)`; `local_llm.py:9` imports `CitationVerificationResult, validate_citations`, exposed via `AiModel.validate_response` (`local_llm.py:328-346`)

**Retrieval / storage (Phase 4):**
- lancedb `>=0.17.0` — serverless embedded on-disk vector + columnar store backing `HybridRetriever` (`hybrid_retriever.py:20,115`); table `chunks` with schema `chunk_id/doc_id/filename/page/content/vector/extraction/char_start/char_end/bbox_json` (`hybrid_retriever.py:296-309`); `create_table(mode="create")` on first index, `merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all()` upsert or delete-then-`add` fallback (`hybrid_retriever.py:311-334`); dense search via `table.search(query_vector).limit(k)` with cosine `score = 1.0 - _distance` (`hybrid_retriever.py:380-388`); FTS via `table.search(query, query_type="fts")` with `create_fts_index("content")` (`hybrid_retriever.py:405-413,493`); optional-import guard `try/except ImportError → lancedb = None` with `VectorIndex` + JSON fallback (`hybrid_retriever.py:18-24,100-124`)
- pyarrow `>=14.0.0` — columnar/transit dependency of LanceDB (`hybrid_retriever.py:21`, `requirements.txt:15`); `import pyarrow as pa` guarded alongside `lancedb`
- stdlib `math` + `re` — pure-Python BM25 fallback in `HybridRetriever._bm25_search_fallback` (k1=1.5, b=0.75, `idf = log((N-df+0.5)/(df+0.5)+1)`, single-pass precomputed `df_map` → O(N·|Q|)) (`hybrid_retriever.py:415-476`); module-level `compute_rrf(dense_ranks, fts_ranks, k_rrf=60)` implementing `RRF(d) = Σ 1/(k_rrf + rank)` (`hybrid_retriever.py:31-76`)

**Ingestion / multimodal:**
- docling `>=2.0.0` — structured layout + markdown table extraction via `DocumentConverter` with `PdfPipelineOptions(do_ocr=False, do_table_structure=True)` (`docling_reader.py:23-31,103-109`); guarded `try/except ImportError → None` with `PdfReader` fallback (`docling_reader.py:22-31,95-100,288-293`)
- rapidocr-onnxruntime `>=1.3.0` — CPU-only OCR via ONNX Runtime `CPUExecutionProvider` (`ocr_fallback.py:18-21,63-69`); guarded import, lazy init, `recognizer`/`renderer` constructor injection for offline tests (`ocr_fallback.py:49-61`)
- pymupdf `>=1.24.0` (`import fitz`) — PDF raster rendering at 150 DPI for OCR (`ocr_fallback.py:96-108`) and visual region detection + 2x-zoom PNG crops (`visual_analyzer.py:64-183`); guarded `try/except ImportError → None` in both modules (`ocr_fallback.py:23-26`, `visual_analyzer.py:17-20`)
- pillow `>=10.2.0` — image codec floor supporting PNG bytes produced/consumed by the PyMuPDF ↔ RapidOCR ↔ VLM paths (`ocr_fallback.py`, `visual_analyzer.py`, `llama_cpp_provider.py:216-268`); no direct `PIL` import in app code, required transitively
- pypdf `==5.3.0` — baseline text extraction (`pdf_reader.py:3,16`), validation page-count probe (`upload_validation.py:12,91`), `DoclingReader` fallback reader (`docling_reader.py:72`)
- langchain-text-splitters `==0.3.6` — chunking only via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:35-39`, `docling_reader.py:172-176`, `ocr_fallback.py:188-192`); no chains/agents

**Inference:**
- litellm `>=1.50.0` — unified multi-provider cloud client `litellm.completion` (`litellm_provider.py:19,223,275,337`); guarded import (`litellm_provider.py:18-21`); routes `groq/llama-3.3-70b-versatile` (131072 ctx), `openai/gpt-4o-mini` (128000 ctx, vision), `anthropic/claude-3-5-haiku-20241022` (200000 ctx, vision)
- groq `==0.15.0` — legacy cloud fallback client `groq.Groq` (`groq_provider.py:12-15,52`); guarded import (`groq_provider.py:12-15`); default model `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-25`); retained as the `AiModel._detect_provider` fallback when `cloud_mode=True` without an injected `LiteLLMProvider` (`local_llm.py:169-175`)
- llama.cpp `llama-server` (EXTERNAL binary, not a pip package) — serves `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB) + `mmproj-f16.gguf` (~450 MB) with `-c 4096 -ngl 28 --port 8080 --host 127.0.0.1` (`docs/LOCAL_INFERENCE.md:52-60`, `llama_cpp_provider.py:79-82`); OpenAI-compatible `GET /health` + `POST /v1/chat/completions` (stream + non-stream, SSE `data: [DONE]`), vision via `image_url` base64 data URI (`llama_cpp_provider.py:49-268`)
- No FAISS / scikit-learn as pinned runtime deps — `vector_index.py:11-12` is pure stdlib (`math`, `typing`); `numpy>=1.26.0,<3.0.0` is a direct floor in `requirements.txt:7` used by tests/benchmark and `HybridRetriever` call sites (`tests/conftest.py:8`, `tests/test_hybrid_retriever.py:5`, `scripts/benchmark_baseline.py:100`, `main.py` for `embeddings.tolist()`); `torch`, `transformers`, `huggingface-hub`, `tokenizers` arrive transitively via sentence-transformers

**Testing:**
- pytest `>=8.3.0` — runner; config `[tool.pytest.ini_options]` in `pyproject.toml:13-19` (`testpaths=["tests"]`, `python_files=["test_*.py"]`); Phase-7 suites add `tests/test_litellm_provider.py` (252 lines: consent-gate default-block, `set_consent` grant, health missing-key/healthy/missing-lib, 3-model capability matrix, bounded-params clamp + timeout/retry passthrough, SSE delta streaming, vision support/rejection + JPEG/WebP MIME sniffing, `RuntimeError` wrapping, `AiModel` cloud-toggle) and `tests/test_cloud_privacy.py` (251 lines: default local-only, consent transition workflow, socket-guarded zero-egress ingestion/indexing, chat-turn `is_cloud`/`model_name` metadata, provider-switching matrix, `VisualAnalyzer` cloud-vision rejection, `set_cloud_mode` idempotency, per-provider key lookup); Phase-5 suites add `tests/test_summarizer.py` and `tests/test_citation_validator.py`; Phase 6 adds `tests/test_resource_telemetry.py` (165 lines) plus `test_sidebar_telemetry_contracts` in `tests/test_cache_invalidation.py:208-218`
- reportlab `>=4.2.0` — synthetic 6-PDF corpus generation (`tests/data/corpus/generate_corpus.py:6-18`: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`)
- psutil `>=6.1.0` — PROMOTED to runtime dep in Phase 6 (`requirements.txt:16`); still also in `requirements-test.txt:5`. Runtime use: `resource_telemetry.py:83-96` (`psutil.Process().memory_info()` → `rss_mb`/`vms_mb`, zero-fallback on `ImportError`/any error); legacy benchmark use: `scripts/benchmark_baseline.py:13,23-25`
- numpy (runtime floor) — deterministic 384-dim mock embeddings `_make_unit_vector(seed)` in `tests/test_hybrid_retriever.py:12-19` and in `tests/conftest.py:59-74`, plus random-vector scan benchmark in `scripts/benchmark_baseline.py:100-114`

**Observability / telemetry (Phase 6 — QUAL-01):**
- `resource_telemetry.py` (211 lines, stdlib + optional `psutil`, NO new pip package beyond the `psutil` runtime promotion) — `get_gpu_memory_info()` queries `nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader,nounits` via `subprocess.run(timeout=2.0)` with first-line parse → `{total_mb, used_mb, free_mb, utilization_pct}` or `None` on `FileNotFoundError`/`SubprocessError`/`ValueError`/`IndexError` (`resource_telemetry.py:26-71`); `get_process_memory_info()` wraps `psutil.Process().memory_info()` → `{rss_mb, vms_mb}` with zero-fallback (`resource_telemetry.py:74-96`); `LatencyTracker(stage_name, record_history=True)` context manager measuring `time.perf_counter()` → `elapsed_ms` + `success`/`error`, recording into thread-safe `_LATENCY_HISTORY` (`threading.Lock`, `MAX_STAGE_HISTORY=200`, `resource_telemetry.py:20-23,99-152`); `track_stage()` generator shim (`resource_telemetry.py:155-160`); `record_stage_latency` / `get_latency_history` / `clear_latency_history` registry API (`resource_telemetry.py:163-181`); `get_system_telemetry_snapshot()` → `{timestamp, gpu, process, stages: {count, avg_ms, min_ms, max_ms}}` (`resource_telemetry.py:184-211`)
- `nvidia-smi` (EXTERNAL binary, not pip) — invoked only via `resource_telemetry.get_gpu_memory_info`; 2 s timeout; `None` return drives CPU-only UI captions and the 487.0 MB DWM-baseline fallback in `scripts/profile_resources.py:268`
- UI wiring: `main.py:33` imports `get_gpu_memory_info, get_process_memory_info`; sidebar expander `📊 System Telemetry & VRAM` renders `st.metric` + `st.progress` + 🟢/🟡/🔴 thresholds at 3500/3800 MB, `CPU-only Mode` caption when `None`, plus RSS + doc/summary counts

**Build/Dev:**
- ruff `>=0.9.0` — linter + formatter; config in `pyproject.toml:1-10` (`line-length=120`, `target-version="py311"`, `select=["E","F","W"]`, `ignore=["E501","W291","W293"]`, `scripts/*` ignores `E402`)
- No bundler, no compile step, no `setup.py`/`setup.cfg`

## Key Dependencies

**Critical (verified pin per line of `requirements.txt`, re-verified 2026-10-12 — 17 lines; Phase 7 adds `litellm`):**
| Package | Pin | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` (`requirements.txt:1`) | `main.py:23`, `groq_provider.py:40` | App runtime; UI does not run without it |
| `pypdf` | `==5.3.0` (`requirements.txt:2`) | `pdf_reader.py:3`, `upload_validation.py:12`, `docling_reader.py:72` | Baseline extraction + validation probe + Docling fallback |
| `python-dotenv` | `==1.0.1` (`requirements.txt:3`) | `main.py`, `load_ai_model()` | Loads `.env` inside cached `load_ai_model()` before provider detection |
| `langchain-text-splitters` | `==0.3.6` (`requirements.txt:4`) | `pdf_reader.py:5`, `docling_reader.py:15`, `ocr_fallback.py:12` | Sole langchain component — 1000/200 chunking in all three extraction paths |
| `groq` | `==0.15.0` (`requirements.txt:5`) | `groq_provider.py:12-15,117-161` | Legacy cloud fallback inference; guarded import with `check_health` unreachable state when missing |
| `sentence-transformers` | `==3.4.1` (`requirements.txt:6`) | `local_embedding.py:7,22,40` | Embedding inference (CPU-pinned); triggers HuggingFace download on first run |
| `numpy` | `>=1.26.0,<3.0.0` (`requirements.txt:7`) | `tests/conftest.py:8`, `tests/test_hybrid_retriever.py:5`, `scripts/benchmark_baseline.py:100`, `main.py` | Mock embeddings + benchmark vector synthesis + `.tolist()` handoff into `HybridRetriever.index_chunks` |
| `pydantic` | `==2.11.9` (`requirements.txt:8`) | `models.py:11`, `model_provider.py:12`, `citation_validator.py:11` | Every canonical schema (`Chunk`, `Page`, `Document`, `BBox`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`, `ProviderCapabilities`, `HealthStatus`) |
| `httpx` | `>=0.28.0` (`requirements.txt:9`) | `llama_cpp_provider.py:13,39-43` | Local provider transport (`Client` + `.stream()` SSE); `MockTransport` seam in tests |
| `docling` | `>=2.0.0` (`requirements.txt:10`) | `docling_reader.py:23-31,103-115` | Primary extraction path (layout + tables); CPU-only, `do_ocr=False` |
| `rapidocr-onnxruntime` | `>=1.3.0` (`requirements.txt:11`) | `ocr_fallback.py:18-21,124-159` | Conditional scanned-page OCR (threshold 50 chars, 150 DPI render) |
| `pymupdf` | `>=1.24.0` (`requirements.txt:12`) | `ocr_fallback.py:96-108`, `visual_analyzer.py:64-183` | Page rasterisation, image/drawing region detection, 2x PNG crops |
| `pillow` | `>=10.2.0` (`requirements.txt:13`) | transitive image codec for the PNG paths above | Required for raster/crop/OCR image handling |
| `lancedb` | `>=0.17.0` (`requirements.txt:14`) | `hybrid_retriever.py:20,115,196-200,311-334,380,493` | Persistent on-disk vector + FTS store; optional import with `VectorIndex` fallback |
| `pyarrow` | `>=14.0.0` (`requirements.txt:15`) | `hybrid_retriever.py:21` (guarded `import pyarrow as pa`), transitive LanceDB columnar layer | Required by LanceDB; no direct app-code API use beyond the guarded import |
| `psutil` | `>=6.1.0` (`requirements.txt:16`, Phase 6 promotion; also `requirements-test.txt:5`) | `resource_telemetry.py:83-96`, `scripts/profile_resources.py:118,259`, `scripts/benchmark_baseline.py:13,23-25` | Runtime process-memory telemetry with zero-fallback when missing; CI-safe (`None`/zeros, never raises) |
| `litellm` | `>=1.50.0` (`requirements.txt:17`, Phase 7 addition) | `litellm_provider.py:18-21,223,275,337` (`import litellm`, `litellm.completion` × 3 call sites: `generate_text`, `stream_text`, `analyze_image`) | Unified multi-provider cloud gateway (Groq/OpenAI/Anthropic); guarded import — absence yields `unreachable` health + `RuntimeError` at use sites, never an import crash |

**Infrastructure:**
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — transitive via sentence-transformers (not pinned); model weights cached in `~/.cache/huggingface/`
- stdlib `sqlite3` only for metadata persistence — no DB driver (`doc_store.py:12`); vector persistence is LanceDB embedded files under `data/lancedb/` (no server, no driver); no Redis
- stdlib `subprocess` + `threading` + `time` + `datetime` for telemetry — `subprocess.run(["nvidia-smi", ...], timeout=2.0)` (`resource_telemetry.py:39-45`), `threading.Lock` guarding `_LATENCY_HISTORY` (`resource_telemetry.py:22`), `time.perf_counter()` for stage latency (`resource_telemetry.py:119,130`), `datetime.now(timezone.utc).isoformat()` for snapshot timestamps (`resource_telemetry.py:207`)
- stdlib `hashlib`, `re`, `io`, `json`, `math`, `base64`, `logging`, `pathlib`, `uuid`, `datetime` across `upload_validation.py`, `prompt_budget.py`, `vector_index.py`, `hybrid_retriever.py`, `llama_cpp_provider.py`, `litellm_provider.py` (`base64` for vision data-URI, `litellm_provider.py:8,315`), `summarizer.py`, `citation_validator.py`, `main.py`

## Configuration

**Environment:**
- `GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — per-provider keys resolved by `_resolve_api_key_for_model` with precedence explicit-arg → `st.session_state.cloud_api_keys[prefix]` → legacy `st.session_state.cloud_api_key` → `st.secrets[VAR]` → `os.environ[VAR]` (`litellm_provider.py:39-85`); legacy `GroqProvider` resolves `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); absence yields `unreachable` `HealthStatus`, never an exception (`groq_provider.py:70-74`, `litellm_provider.py:152-158`)
- `.env` is gitignored (`.gitignore:1`); `load_dotenv()` runs inside `load_ai_model()` (`main.py:91`)
- Local llama-server endpoint default `http://127.0.0.1:8080`, model `qwen3-vl-2b`, context 4096 (`llama_cpp_provider.py:21-26`); `AiModel._detect_provider` routes cloud-mode → injected `LiteLLMProvider` → healthy `GroqProvider` → local `LlamaCppProvider` (`local_llm.py:162-179`)
- Cloud-mode defaults: `timeout=30.0`, `num_retries=2` (`litellm_provider.py:109-110`); UI `CLOUD_PROVIDER_OPTIONS` maps `groq → groq/llama-3.3-70b-versatile`, `openai → openai/gpt-4o-mini`, `anthropic → anthropic/claude-3-5-haiku-20241022` with env-var labels (`main.py:162-166`)
- Retrieval defaults: `DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"` (`hybrid_retriever.py:27`), `DEFAULT_RRF_K = 60` (`hybrid_retriever.py:28`), dense `score = max(0.0, 1.0 - dist)` (`hybrid_retriever.py:386,398`), hybrid candidate pool `max(k*2, 10)` (`hybrid_retriever.py:531`), fallback JSON `db_uri / "fallback_store.json"` (`hybrid_retriever.py:110`)
- Embedding defaults: `model_name="all-MiniLM-L6-v2"`, `device="cpu"`, `distance_metric="cosine"`, `vector_dim=384` (`local_embedding.py:22-24`, `hybrid_retriever.py:86`)
- Locked deployment caps: `MAX_FILE_MB = 50`, `MAX_PAGES = 500` (`upload_validation.py:15-16`); OCR trigger `threshold = 50` chars (`ocr_fallback.py:29-43`); OCR render `dpi = 150` (`ocr_fallback.py:77-82`); visual crop `zoom = 2.0` (`visual_analyzer.py:138-144`)
- Summarizer budgets (Phase 5): `FAST_PATH_TOKEN_LIMIT = 2500`, `MAX_BATCH_TOKENS = 2000` (`summarizer.py:27-28`); single-pass `max_tokens=1500`, map `max_tokens=800`, reduce `max_tokens=1500`, all `temperature=0.2` (`summarizer.py:225-298`); citation regex `re.compile(r"\[E(\d+)\]", re.IGNORECASE)` (`citation_validator.py:16`) and page-ref regex `r"\b(?:p\.|page)\s*(\d+)\b"` (`summarizer.py:147`); precision gate `>= 0.95` (`citation_validator.py:163`)
- Summary profiles: `VALID_SUMMARY_PROFILES = ("overview", "detailed", "study_notes", "tables_figures", "findings")` (`models.py:209`); templates `PROFILE_SYSTEM_INSTRUCTIONS` / `MAP_PROMPT_TEMPLATE` / `REDUCE_PROMPT_TEMPLATE` (`summarizer.py:30-132`)
- Telemetry / QUAL-01 budgets (Phase 6): VRAM health thresholds `vram_used < 3500 → 🟢 Healthy`, `<= 3800 → 🟡 Headroom Limited`, `> 3800 → 🔴 High`; profiling budget `vram_target_mb = 3800.0` vs 4096 ceiling, projected peak = DWM overhead + 1450 (Qwen3-VL 2B Q4_K_M) + 450 (mmproj-f16) + 510 (4K FP16 KV cache) + 350 (CUDA scratch) (`scripts/profile_resources.py:270-287`); DWM fallback `487.0 MB` in headless/CI where `nvidia-smi` is absent (`scripts/profile_resources.py:268`); SQLite cache SLA `warm < 50.0 ms` asserted (`scripts/profile_resources.py:247`); latency history cap `MAX_STAGE_HISTORY = 200` (`resource_telemetry.py:23`)
- Chunking policy constant: `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`); cache path `cache_dir_for(base, sha256) → base/sha256/CONFIG_VERSION` with strict 64-hex validation (`models.py:17-30`)
- Prompt budget defaults: `max_context_tokens=4096`, `max_output_tokens=1024`, heuristic `estimate_tokens = ceil(len/4)` (`prompt_budget.py:34-53`); system template `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`prompt_budget.py:11-17`)

**Build:**
- No build step — interpreted Python. `pyproject.toml` holds only `[tool.ruff]` + `[tool.pytest.ini_options]` (`pyproject.toml:1-20`)
- `.devcontainer/devcontainer.json:20` pip-installs `requirements.txt` + streamlit, then auto-launches Streamlit on port 8501
- `.github/workflows/ci.yml:24-41` installs `requirements.txt` (17 lines post-Phase-7) + `requirements-test.txt`, runs `ruff check .`, `ruff format --check .`, generates the corpus (`python tests/data/corpus/generate_corpus.py`), then `pytest tests/ -v`

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download
- NVIDIA driver 550.x+ / CUDA 12.x + llama.cpp CUDA build for local inference; `models/qwen3-vl-2b-instruct-q4_k_m.gguf` + `models/mmproj-f16.gguf` downloads from HuggingFace GGUF repos (`docs/LOCAL_INFERENCE.md:22-44`)
- `reportlab` (via `requirements-test.txt`) needed locally to generate `tests/data/corpus/*.pdf` before running `tests/` (CI does this in a dedicated step, `.github/workflows/ci.yml:35-37`)
- `docling>=2.0.0` pulls a heavy transitive tree (torch/transformers); first `DocumentConverter` construction downloads layout/table models — allow disk + warm-up time
- `lancedb>=0.17.0` + `pyarrow>=14.0.0` install cleanly on CI `ubuntu-latest`; on Windows, LanceDB files land under `data/lancedb/` (gitignored via `.gitignore:10`); absence degrades to disk-backed `fallback_store.json`, never a crash
- `litellm>=1.50.0` pulls its own transitive tree (openai/anthropic SDK shims, tiktoken, httpx); absence is tolerated — `LiteLLMProvider.check_health` returns `unreachable` and generation raises `RuntimeError`, never an import crash (`litellm_provider.py:18-21,140-150`)

**Production:**
- Primary intended deployment: local Windows workstation inside the 4 GB VRAM ceiling (`docs/LOCAL_INFERENCE.md:7-18`); zero network egress when the local provider is healthy and `cloud_mode=False` (`llama_cpp_provider.py:1-6`, `model_provider.py:33-37` `is_local=True`, `local_llm.py:164-179`); embeddings and LanceDB run on CPU/disk, never VRAM; summarizer map-reduce executes sequentially to respect single-active-LLM VRAM constraint (`summarizer.py:232-244`); ingestion-time `VisualAnalyzer` strictly rejects cloud providers even in cloud mode (`tests/test_cloud_privacy.py:151-203`)
- Streamlit Community Cloud is the hosted fallback with per-provider keys in the Cloud secrets panel (`GROQ_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`); LanceDB at `data/lancedb/` and SQLite at `data/documents.db` and `.cache/` are best-effort/ephemeral there (fallback JSON persists only if disk persists)
- `data/` (`.gitignore:10`) and `.cache/` (`.gitignore:17`) are gitignored runtime state, never committed

## Entry Points

| Entry | Command | File |
|---|---|---|
| Streamlit app (sole entry point) | `streamlit run main.py` | `main.py:1-837` |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:21-23` |
| Benchmark | `python scripts/benchmark_baseline.py` (writes `.planning/research/BASELINE_BENCHMARK.json`; CPU-pinned `SentenceTransformer(..., device="cpu")` at line 70) | `scripts/benchmark_baseline.py:173-174` |
| Resource profile (QUAL-01) | `python scripts/profile_resources.py` (writes `.planning/research/RESOURCE_PROFILE.json`; 6 stages: baseline → ingestion → CPU embeddings → LanceDB hybrid retrieval cold/warm → summarizer cold/warm cache SLA → InferenceGate check → VRAM headroom audit; `BenchmarkProvider` mock, `tempfile` DocStore/LanceDB, `shutil.rmtree` cleanup) | `scripts/profile_resources.py:94-342` |
| Corpus generation | `python tests/data/corpus/generate_corpus.py` | `tests/data/corpus/generate_corpus.py` |
| No CLI / module entry | No `if __name__ == "__main__"` in app modules (only `scripts/benchmark_baseline.py:173`, `scripts/profile_resources.py:341`) | Not applicable |

- `main.py` — Streamlit front-end, session state (privacy keys at `main.py:67-73`, `hybrid_retriever`, `local_embedding`), consent dialog + provider switcher + ephemeral key inputs (`main.py:108-245`), upload → validate → dedup → Docling → OCR → visual → embed → `HybridRetriever.index_chunks` → hybrid chat + summarizer tab → stream orchestration
- `local_llm.py` — `AiModel`: provider auto-detection + `cloud_mode`/`cloud_provider` routing (`local_llm.py:103-179`), `set_cloud_mode` idempotent toggle (`local_llm.py:139-160`), `ask_a_question_from_pdf_stream(pdf_path, prompt, local_embedding: LocalEmbedding | HybridRetriever | None, chat_history, retrieval_result)` with `HybridRetriever.search_hybrid(search_query, k=10)` dispatch (`local_llm.py:211-298`) and `assemble_grounded_messages` budgeting; plus `validate_response(response_text, retrieval_result)` → `validate_citations` (`local_llm.py:328-346`)
- `litellm_provider.py` — `LiteLLMProvider`: consented multi-provider cloud adapter (`generate_text` / `stream_text` / `analyze_image` / `check_health` / `get_capabilities` / `set_consent` / `close`) plus module functions `_resolve_api_key_for_model` and `_detect_image_mime_type` (`litellm_provider.py:39-98`)
- `summarizer.py` — `Summarizer`: `summarize_document(doc_id, sha256, pages, chunks, profile, force_refresh)` with SQLite cache check/save via `DocStore.get_summary`/`save_summary` (`summarizer.py:300-418`); page reconstruction from `Chunk` dicts/models or `doc_store.get_chunks_for_doc` (`summarizer.py:338-377`); result `SummaryResult(summary_id=summ_<hex16>, page_references, model_version, cached)` (`summarizer.py:401-411`)
- `citation_validator.py` — `validate_citations(response_text, retrieval_result)` enforcing >=95% precision + abstention rules, `extract_citations`, `is_abstention`, `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS` (`citation_validator.py:16-181`)
- `model_provider.py` — `BaseModelProvider` ABC (`generate_text`/`stream_text`/`analyze_image`/`check_health`/`get_capabilities`) + frozen `ProviderCapabilities` / `HealthStatus` schemas
- `llama_cpp_provider.py` / `groq_provider.py` / `litellm_provider.py` — local / legacy-cloud / multi-cloud `BaseModelProvider` implementations
- `prompt_budget.py` — pure-function token budgeting + `<document_context>` injection defense (no dependencies beyond `math`); reused by `summarizer.py` via `estimate_tokens` + `sanitize_xml_boundary` (`summarizer.py:18,181,200,290`)
- `local_embedding.py` — `LocalEmbedding`: CPU-pinned sentence-transformers wrapper + batch `build_index` + `search`/`search_hybrid`/`get_context` facades (dense-only `RetrievalResult(search_mode="dense")`, `local_embedding.py:84-109`)
- `hybrid_retriever.py` — `HybridRetriever`: persistent LanceDB vector + BM25/FTS hybrid retrieval with RRF; `compute_rrf` pure function; `index_chunks` / `add_vector` / `search_dense` / `search_fts` / `search_hybrid` / legacy `search`+`get_context` facades; `has_document` / `delete_document` / `count_chunks` / `is_persistent` / `set_embedding_fn` / `close` + context-manager protocol
- `vector_index.py` — `VectorIndex`: pure-stdlib in-memory cosine/Euclidean store; now also the `HybridRetriever._fallback_store` backend (`hybrid_retriever.py:105-108`)
- `pdf_reader.py` / `docling_reader.py` / `ocr_fallback.py` / `visual_analyzer.py` — four-stage ingestion: baseline → structured → scanned-text recovery → visual evidence
- `doc_store.py` — `DocStore`: SQLite metadata + chunk + evidence + summary persistence with v1/v2/v3 migrations (v3 adds `document_summaries`, `doc_store.py:73-94`)
- `models.py` — canonical Pydantic v2 schemas + `CONFIG_VERSION` + `cache_dir_for`; `EvidenceSnippet`/`RetrievalResult.formatted_evidence()`/`source_labels()` shared by generation prompts and UI citations; Phase 5 adds `SummaryProfile`/`VALID_SUMMARY_PROFILES`/`SummaryResult` (`models.py:208-235`)
- `upload_validation.py` — `%PDF` magic-byte / size / page-count gate + `doc_<sha16>` identity
- `resource_telemetry.py` — `get_gpu_memory_info` / `get_process_memory_info` / `LatencyTracker` / `track_stage` / `record_stage_latency` / `get_latency_history` / `clear_latency_history` / `get_system_telemetry_snapshot`; zero third-party surface beyond optional `psutil`; consumed by sidebar telemetry expander and `scripts/profile_resources.py:28-32` (6-stage benchmark)

---

*Stack analysis: 2026-10-12*
