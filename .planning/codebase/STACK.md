# Technology Stack

**Analysis Date:** 2026-10-11

## Languages

**Primary:**
- Python 3.11+ — all application code (`main.py`, `local_llm.py`, `model_provider.py`, `groq_provider.py`, `llama_cpp_provider.py`, `prompt_budget.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `doc_store.py`, `models.py`, `upload_validation.py`, `scripts/benchmark_baseline.py`, `tests/`)

**Secondary:**
- JSON — `.devcontainer/devcontainer.json`, disk cache payloads `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json` written by `main.py:279-287`
- Markdown — docs only (`README.md`, `docs/LOCAL_INFERENCE.md`, `CLAUDE.md`)
- SQL (SQLite DDL inline in Python) — `doc_store.py:16-75` (`SCHEMA_V1_DDL`, `SCHEMA_V2_DDL`, `MIGRATIONS`)
- No JavaScript/TypeScript/CSS — UI is 100% Streamlit Python

## Runtime

**Environment:**
- CPython 3.11 locally via `streamlit run main.py` (`main.py:1-13`, `.devcontainer/devcontainer.json:22`)
- Devcontainer / Codespaces: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm` (`.devcontainer/devcontainer.json:4`), auto-opens `README.md` + `main.py`, serves Streamlit on port 8501 with CORS/XSRF disabled (`.devcontainer/devcontainer.json:22-32`)
- CI: GitHub Actions `ubuntu-latest` with `actions/setup-python@v5` pinned to `"3.11"` with pip cache (`.github/workflows/ci.yml:9-21`)
- Target inference host: Windows 11 + NVIDIA RTX 3050 Laptop GPU (4 GB VRAM); VRAM budget ~3,260 MB peak documented in `docs/LOCAL_INFERENCE.md:7-18`
- External inference server (not Python): `llama-server` (llama.cpp CUDA build) on `http://127.0.0.1:8080` — see INTEGRATIONS.md

**Package Manager:**
- pip
- Runtime deps: `requirements.txt` (13 entries, mix of `==` pins and `>=` floors — see table below)
- Test/benchmark deps: `requirements-test.txt` (4 entries)
- Lockfile: absent (no `requirements.lock`, `poetry.lock`, `Pipfile.lock`, `uv.lock`)
- Virtual env convention: `.venv` (gitignored via `.gitignore:2`)

## Frameworks

**Core:**
- Streamlit `==1.42.0` — entire UI layer: `st.set_page_config` (`main.py:38-43`), sidebar (`main.py:83-323`), `st.file_uploader` (`main.py:138-144`), `st.chat_input` / `st.chat_message` (`main.py:343-410`), `st.status` (`main.py:90`, `main.py:148`), `st.cache_resource` (`main.py:68-76`), `st.write_stream` (`main.py:394`), caption `Powered by Groq + MiniLM-L6-v2` (`main.py:323`)
- Pydantic `==2.11.9` — canonical data models and provider schemas (`models.py:33-138`, `model_provider.py:15-62`)
- httpx `>=0.28.0` — HTTP client for the local llama-server provider with explicit timeouts (`llama_cpp_provider.py:13,39-43`); also the offline test seam via `httpx.MockTransport` (`tests/test_llama_cpp_provider.py`)
- sentence-transformers `==3.4.1` — local CPU embedding wrapper (`local_embedding.py:7,22`); default model `all-MiniLM-L6-v2` (`local_embedding.py:12`), 384-dim L2-normalised float32 vectors (`local_embedding.py:1-5,39`)

**Ingestion / multimodal:**
- docling `>=2.0.0` — structured layout + markdown table extraction via `DocumentConverter` with `PdfPipelineOptions(do_ocr=False, do_table_structure=True)` (`docling_reader.py:23-31,103-109`); guarded `try/except ImportError → None` with `PdfReader` fallback (`docling_reader.py:22-31,95-100,288-293`)
- rapidocr-onnxruntime `>=1.3.0` — CPU-only OCR via ONNX Runtime `CPUExecutionProvider` (`ocr_fallback.py:18-21,63-69`); guarded import, lazy init, `recognizer`/`renderer` constructor injection for offline tests (`ocr_fallback.py:49-61`)
- pymupdf `>=1.24.0` (`import fitz`) — PDF raster rendering at 150 DPI for OCR (`ocr_fallback.py:96-108`) and visual region detection + 2x-zoom PNG crops (`visual_analyzer.py:64-183`); guarded `try/except ImportError → None` in both modules (`ocr_fallback.py:23-26`, `visual_analyzer.py:17-20`)
- pillow `>=10.2.0` — image codec floor supporting PNG bytes produced/consumed by the PyMuPDF ↔ RapidOCR ↔ VLM paths (`ocr_fallback.py`, `visual_analyzer.py`, `llama_cpp_provider.py:216-268`); no direct `PIL` import in app code, required transitively
- pypdf `==5.3.0` — baseline text extraction (`pdf_reader.py:3,16`), validation page-count probe (`upload_validation.py:12,91`), `DoclingReader` fallback reader (`docling_reader.py:72`)
- langchain-text-splitters `==0.3.6` — chunking only via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)` (`pdf_reader.py:35-39`, `docling_reader.py:172-176`, `ocr_fallback.py:188-192`); no chains/agents

**Inference:**
- groq `==0.15.0` — optional cloud fallback client `groq.Groq` (`groq_provider.py:12-15,52`); guarded import (`groq_provider.py:12-15`); default model `openai/gpt-oss-20b`, context window 8192 (`groq_provider.py:24-25`)
- llama.cpp `llama-server` (EXTERNAL binary, not a pip package) — serves `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB) + `mmproj-f16.gguf` (~450 MB) with `-c 4096 -ngl 28 --port 8080 --host 127.0.0.1` (`docs/LOCAL_INFERENCE.md:52-60`, `llama_cpp_provider.py:79-82`); OpenAI-compatible `GET /health` + `POST /v1/chat/completions` (stream + non-stream, SSE `data: [DONE]`), vision via `image_url` base64 data URI (`llama_cpp_provider.py:49-268`)
- No NumPy / FAISS / scikit-learn as pinned runtime deps — `vector_index.py:11-12` is pure stdlib (`math`, `typing`); `numpy>=1.26.0,<3.0.0` is a direct floor in `requirements.txt:7` used by tests/benchmark (`tests/conftest.py:8`, `scripts/benchmark_baseline.py:100`); `torch`, `transformers`, `huggingface-hub`, `tokenizers` arrive transitively via sentence-transformers

**Testing:**
- pytest `>=8.3.0` — runner; config `[tool.pytest.ini_options]` in `pyproject.toml:13-19` (`testpaths=["tests"]`, `python_files=["test_*.py"]`)
- reportlab `>=4.2.0` — synthetic 6-PDF corpus generation (`tests/data/corpus/generate_corpus.py:6-18`: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`)
- psutil `>=6.1.0` — RSS/CPU profiling in `scripts/benchmark_baseline.py:13,23-25`
- numpy (runtime floor) — deterministic 384-dim mock embeddings in `tests/conftest.py:59-74` and random-vector scan benchmark in `scripts/benchmark_baseline.py:100-114`

**Build/Dev:**
- ruff `>=0.9.0` — linter + formatter; config in `pyproject.toml:1-10` (`line-length=120`, `target-version="py311"`, `select=["E","F","W"]`, `ignore=["E501","W291","W293"]`, `scripts/*` ignores `E402`)
- No bundler, no compile step, no `setup.py`/`setup.cfg`

## Key Dependencies

**Critical (verified pin per line of `requirements.txt`):**
| Package | Pin | Where used | Why it matters |
|---|---|---|---|
| `streamlit` | `==1.42.0` (`requirements.txt:1`) | `main.py:23`, `groq_provider.py:40` | App runtime; UI does not run without it |
| `pypdf` | `==5.3.0` (`requirements.txt:2`) | `pdf_reader.py:3`, `upload_validation.py:12`, `docling_reader.py:72` | Baseline extraction + validation probe + Docling fallback |
| `python-dotenv` | `==1.0.1` (`requirements.txt:3`) | `main.py:22,75` | Loads `.env` inside cached `load_ai_model()` before provider detection |
| `langchain-text-splitters` | `==0.3.6` (`requirements.txt:4`) | `pdf_reader.py:5`, `docling_reader.py:15`, `ocr_fallback.py:12` | Sole langchain component — 1000/200 chunking in all three extraction paths |
| `groq` | `==0.15.0` (`requirements.txt:5`) | `groq_provider.py:12-15,117-161` | Cloud fallback inference; guarded import with `check_health` unreachable state when missing |
| `sentence-transformers` | `==3.4.1` (`requirements.txt:6`) | `local_embedding.py:7,22,39` | Embedding inference; triggers HuggingFace download on first run |
| `numpy` | `>=1.26.0,<3.0.0` (`requirements.txt:7`) | `tests/conftest.py:8`, `scripts/benchmark_baseline.py:100` | Mock embeddings + benchmark vector synthesis |
| `pydantic` | `==2.11.9` (`requirements.txt:8`) | `models.py:11`, `model_provider.py:12` | Every canonical schema (`Chunk`, `Page`, `Document`, `BBox`, `EvidenceElement`, `ProviderCapabilities`, `HealthStatus`) |
| `httpx` | `>=0.28.0` (`requirements.txt:9`) | `llama_cpp_provider.py:13,39-43` | Local provider transport (`Client` + `.stream()` SSE); `MockTransport` seam in tests |
| `docling` | `>=2.0.0` (`requirements.txt:10`) | `docling_reader.py:23-31,103-115` | Primary extraction path (layout + tables); CPU-only, `do_ocr=False` |
| `rapidocr-onnxruntime` | `>=1.3.0` (`requirements.txt:11`) | `ocr_fallback.py:18-21,124-159` | Conditional scanned-page OCR (threshold 50 chars, 150 DPI render) |
| `pymupdf` | `>=1.24.0` (`requirements.txt:12`) | `ocr_fallback.py:96-108`, `visual_analyzer.py:64-183` | Page rasterisation, image/drawing region detection, 2x PNG crops |
| `pillow` | `>=10.2.0` (`requirements.txt:13`) | transitive image codec for the PNG paths above | Required for raster/crop/OCR image handling |

**Infrastructure:**
- `torch`, `transformers`, `huggingface-hub`, `tokenizers` — transitive via sentence-transformers (not pinned); model weights cached in `~/.cache/huggingface/`
- stdlib `sqlite3` only for persistence — no DB driver (`doc_store.py:12`); no FAISS/LanceDB/Redis
- stdlib `hashlib`, `re`, `io`, `json`, `math`, `base64`, `logging`, `pathlib` across `upload_validation.py`, `prompt_budget.py`, `vector_index.py`, `llama_cpp_provider.py`, `main.py`

## Configuration

**Environment:**
- `GROQ_API_KEY` resolved `st.secrets["GROQ_API_KEY"]` → `os.environ["GROQ_API_KEY"]` (`groq_provider.py:37-49`); absence yields `unreachable` `HealthStatus`, never an exception (`groq_provider.py:70-74`)
- `.env` is gitignored (`.gitignore:1`); `load_dotenv()` runs inside `load_ai_model()` (`main.py:75`)
- Local llama-server endpoint default `http://127.0.0.1:8080`, model `qwen3-vl-2b`, context 4096 (`llama_cpp_provider.py:21-26`); `AiModel._detect_provider` probes local → Groq → local-with-diagnostics (`local_llm.py:46-67`)
- Locked deployment caps: `MAX_FILE_MB = 50`, `MAX_PAGES = 500` (`upload_validation.py:15-16`); OCR trigger `threshold = 50` chars (`ocr_fallback.py:29-43`); OCR render `dpi = 150` (`ocr_fallback.py:77-82`); visual crop `zoom = 2.0` (`visual_analyzer.py:138-144`)
- Chunking policy constant: `CONFIG_VERSION = "docling-1000-200-v1"` (`models.py:14`); cache path `cache_dir_for(base, sha256) → base/sha256/CONFIG_VERSION` with strict 64-hex validation (`models.py:17-30`)
- Prompt budget defaults: `max_context_tokens=4096`, `max_output_tokens=1024`, heuristic `estimate_tokens = ceil(len/4)` (`prompt_budget.py:34-53`); system template `SYSTEM_GROUNDING_TEMPLATE` with `<document_context>` isolation (`prompt_budget.py:11-17`)

**Build:**
- No build step — interpreted Python. `pyproject.toml` holds only `[tool.ruff]` + `[tool.pytest.ini_options]` (`pyproject.toml:1-20`)
- `.devcontainer/devcontainer.json:20` pip-installs `requirements.txt` + streamlit, then auto-launches Streamlit on port 8501
- `.github/workflows/ci.yml:24-41` installs `requirements.txt` + `requirements-test.txt`, runs `ruff check .`, `ruff format --check .`, generates the corpus (`python tests/data/corpus/generate_corpus.py`), then `pytest tests/ -v`

## Platform Requirements

**Development:**
- Python 3.11+, pip, virtualenv (`.venv`); Windows users may need Developer Mode / admin terminal for HuggingFace symlink-based model download
- NVIDIA driver 550.x+ / CUDA 12.x + llama.cpp CUDA build for local inference; `models/qwen3-vl-2b-instruct-q4_k_m.gguf` + `models/mmproj-f16.gguf` downloads from HuggingFace GGUF repos (`docs/LOCAL_INFERENCE.md:22-44`)
- `reportlab` (via `requirements-test.txt`) needed locally to generate `tests/data/corpus/*.pdf` before running `tests/` (CI does this in a dedicated step, `.github/workflows/ci.yml:35-37`)
- `docling>=2.0.0` pulls a heavy transitive tree (torch/transformers); first `DocumentConverter` construction downloads layout/table models — allow disk + warm-up time

**Production:**
- Primary intended deployment: local Windows workstation inside the 4 GB VRAM ceiling (`docs/LOCAL_INFERENCE.md:7-18`); zero network egress when the local provider is healthy (`llama_cpp_provider.py:1-6`, `model_provider.py:33-37` `is_local=True`)
- Streamlit Community Cloud is the hosted fallback with `GROQ_API_KEY` in the Cloud secrets panel; in-memory `VectorIndex` only, SQLite at `data/documents.db` and `.cache/` are best-effort/ephemeral there
- `data/` (`.gitignore:10`) and `.cache/` (`.gitignore:17`) are gitignored runtime state, never committed

## Entry Points

| Entry | Command | File |
|---|---|---|
| Streamlit app (sole entry point) | `streamlit run main.py` | `main.py:1-410` |
| Devcontainer auto-start | `streamlit run main.py --server.enableCORS false --server.enableXsrfProtection false` | `.devcontainer/devcontainer.json:21-23` |
| Benchmark | `python scripts/benchmark_baseline.py` (writes `.planning/research/BASELINE_BENCHMARK.json`) | `scripts/benchmark_baseline.py:173-174` |
| Corpus generation | `python tests/data/corpus/generate_corpus.py` | `tests/data/corpus/generate_corpus.py` |
| No CLI / module entry | No `if __name__ == "__main__"` in app modules (only `scripts/benchmark_baseline.py:173`) | Not applicable |

- `main.py` — Streamlit front-end, session state, upload → validate → dedup → Docling → OCR → visual → index → chat → stream orchestration
- `local_llm.py` — `AiModel`: provider auto-detection + `ask_a_question_from_pdf_stream` generator with `assemble_grounded_messages` budgeting
- `model_provider.py` — `BaseModelProvider` ABC (`generate_text`/`stream_text`/`analyze_image`/`check_health`/`get_capabilities`) + frozen `ProviderCapabilities` / `HealthStatus` schemas
- `llama_cpp_provider.py` / `groq_provider.py` — local / cloud `BaseModelProvider` implementations
- `prompt_budget.py` — pure-function token budgeting + `<document_context>` injection defense (no dependencies beyond `math`)
- `local_embedding.py` — `LocalEmbedding`: sentence-transformers wrapper + batch `build_index`
- `vector_index.py` — `VectorIndex`: pure-stdlib in-memory cosine/Euclidean store
- `pdf_reader.py` / `docling_reader.py` / `ocr_fallback.py` / `visual_analyzer.py` — four-stage ingestion: baseline → structured → scanned-text recovery → visual evidence
- `doc_store.py` — `DocStore`: SQLite metadata + chunk + evidence persistence with v1/v2 migrations
- `models.py` — canonical Pydantic v2 schemas + `CONFIG_VERSION` + `cache_dir_for`
- `upload_validation.py` — `%PDF` magic-byte / size / page-count gate + `doc_<sha16>` identity

---

*Stack analysis: 2026-10-11*
