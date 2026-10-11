# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
RAG/
├── main.py                      # Streamlit entry point + UI orchestration (health, upload, chat)
├── local_llm.py                 # AiModel orchestrator (provider select, retrieval, stream)
├── model_provider.py            # BaseModelProvider ABC + ProviderCapabilities/HealthStatus
├── groq_provider.py             # Groq Cloud provider implementation
├── llama_cpp_provider.py        # Local llama-server HTTP provider implementation
├── prompt_budget.py             # Token budgeting + <document_context> injection isolation
├── docling_reader.py            # Primary structured extraction (Docling, pypdf fallback)
├── pdf_reader.py                # pypdf extraction + langchain chunking (fallback path)
├── ocr_fallback.py              # Conditional RapidOCR for scanned/low-text pages
├── visual_analyzer.py           # Visual region detect + 2x crop + VLM EvidenceElements
├── local_embedding.py           # SentenceTransformer wrapper + index facade
├── vector_index.py              # Pure-stdlib in-memory vector store
├── doc_store.py                 # SQLite (WAL) document/page/chunk/evidence persistence
├── models.py                    # Canonical Pydantic schemas + CONFIG_VERSION + cache helper
├── upload_validation.py         # %PDF/size/pages validation + SHA-256 doc_id
├── requirements.txt             # Pinned runtime dependencies (13 entries)
├── requirements-test.txt        # Test/benchmark deps (pytest, reportlab, ruff, psutil)
├── pyproject.toml               # ruff + pytest configuration only
├── README.md                    # User-facing docs
├── CLAUDE.md                    # Agent instructions with embedded codebase-map snapshots
├── scripts/
│   └── benchmark_baseline.py    # Offline latency/memory benchmark harness
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures + offline mocking seams
│   ├── test_doc_store.py        # DocStore CRUD, migrations, interleave
│   ├── test_docling_reader.py   # Docling extraction, table handling, fallback
│   ├── test_llama_cpp_provider.py # Local provider health/stream/vision (MockTransport)
│   ├── test_local_embedding.py  # Embedding facade (mocked SentenceTransformer)
│   ├── test_local_llm.py        # AiModel detection, grounding, streaming
│   ├── test_model_provider.py   # Provider contract + schema validation
│   ├── test_models.py           # Pydantic schemas, validators, cache paths
│   ├── test_ocr_fallback.py     # Threshold gating, page isolation, chunking
│   ├── test_pdf_reader.py       # pypdf extraction, fault isolation
│   ├── test_prompt_budget.py    # Budget caps, truncation, injection defense
│   ├── test_upload_validation.py# Magic bytes, size/page caps, hashing
│   ├── test_vector_index.py     # Add/search, metrics, dimension guards
│   ├── test_visual_analyzer.py  # Region detect, crop, VLM provenance
│   └── data/corpus/
│       ├── generate_corpus.py   # reportlab generator for 6 synthetic PDFs
│       ├── clean_digital.pdf    # 20-page digital baseline (generated)
│       ├── multi_column.pdf     # Multi-column layout (generated)
│       ├── dense_table.pdf      # Dense tables (generated)
│       ├── scanned_sample.pdf   # Scanned/image-only (generated)
│       ├── chart_diagram.pdf    # Charts and diagrams (generated)
│       └── corrupt_invalid.pdf  # Corrupt fixture (generated)
├── docs/
│   └── LOCAL_INFERENCE.md       # Qwen3-VL/llama-server runbook (4 GB VRAM)
├── data/
│   └── documents.db             # Runtime SQLite store (generated, gitignored)
├── .cache/
│   └── <sha256>/<ver>/         # Per-doc pages/chunks/manifest JSON (generated, gitignored)
├── application_screenshots/     # README images
├── .github/workflows/ci.yml     # Lint + corpus-gen + pytest CI
├── .devcontainer/               # Python 3.11 devcontainer + Streamlit auto-launch
└── .planning/                   # GSD planning artifacts (codebase maps, phases, research)
```

## Directory Purposes

**Repository root (`/`):**
- Purpose: Flat module layout — one public class per file, no packages.
- Contains: all 15 importable modules plus config files.
- Key files: `main.py` (entry), `local_llm.py` (orchestrator), `models.py` (schemas), `doc_store.py` (persistence), `docling_reader.py` (primary extraction).

**`scripts/`:**
- Purpose: Out-of-band developer tooling.
- Contains: `benchmark_baseline.py` (adds repo root to `sys.path`, measures extraction/chunk/embed/scan latency and RSS via `psutil`, writes `.planning/research/BASELINE_BENCHMARK.json`).
- Key files: `scripts/benchmark_baseline.py` (174 lines).

**`tests/`:**
- Purpose: pytest suite mirroring root modules 1:1 (13 test modules for 15 root modules; `main.py` and `scripts/` have no dedicated test).
- Contains: `conftest.py` fixtures (`fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider`), plus one `test_<module>.py` per domain module.
- Key files: `tests/conftest.py` (161 lines), `tests/test_local_llm.py`, `tests/test_llama_cpp_provider.py`.

**`tests/data/corpus/`:**
- Purpose: Synthetic PDF fixtures covering document archetypes.
- Contains: `generate_corpus.py` (reportlab) producing `clean_digital.pdf` (20 pages), `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf`.
- Generated: Yes. Committed: generated PDFs are gitignored; only the generator is tracked; CI regenerates before tests.

**`docs/`:**
- Purpose: Operational runbooks.
- Contains: `docs/LOCAL_INFERENCE.md` — model download, `llama-server` launch flags, VRAM budget, health probe, troubleshooting.

**`.planning/`:**
- Purpose: GSD workflow artifacts.
- Contains: `codebase/` (these maps), `phases/`, `research/` (incl. `BASELINE_BENCHMARK.json`), `PROJECT.md`, `ROADMAP.md`, `REQUIREMENTS.md`, `STATE.md`, `config.json`.

**`.github/workflows/`:**
- Purpose: CI.
- Contains: `ci.yml` (41 lines) — setup Python 3.11, install both requirement files, `ruff check` + `ruff format --check`, corpus generation, `pytest tests/ -v`.

**`.devcontainer/`:**
- Purpose: Reproducible dev environment.
- Contains: `devcontainer.json` — Python 3.11 image, pip install hook, Streamlit launch on port 8501.

## Key File Locations

**Entry Points:**
- `main.py`: Streamlit app (`streamlit run main.py`) — must keep `st.set_page_config` as the first Streamlit call (`main.py:38-43`).
- `scripts/benchmark_baseline.py`: `python scripts/benchmark_baseline.py`.
- `tests/data/corpus/generate_corpus.py`: `python tests/data/corpus/generate_corpus.py`.

**Configuration:**
- `pyproject.toml`: `[tool.ruff]` (line-length 120, target `py311`, select E/F/W, ignore E501/W291/W293) and `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `python_files=["test_*.py"]`).
- `requirements.txt` (13 pins: `streamlit`, `pypdf`, `python-dotenv`, `langchain-text-splitters`, `groq`, `sentence-transformers`, `numpy`, `pydantic`, `httpx`, `docling`, `rapidocr-onnxruntime`, `pymupdf`, `pillow`) / `requirements-test.txt` (`pytest`, `reportlab`, `ruff`, `psutil`).
- `.devcontainer/devcontainer.json`: dev environment + auto-launch command.
- `.github/workflows/ci.yml`: lint/test pipeline.
- `.env`: local `GROQ_API_KEY` (gitignored, not committed); Streamlit Cloud uses `st.secrets["GROQ_API_KEY"]`.

**Core Logic:**
- `main.py`: UI + ingestion/query orchestration (410 lines).
- `local_llm.py`: `AiModel` — provider selection, retrieval, prompt assembly, streaming (153 lines).
- `model_provider.py`: provider contract + capability/health schemas (156 lines).
- `llama_cpp_provider.py` / `groq_provider.py`: concrete backends (268 / 170 lines).
- `prompt_budget.py`: context budgeting + injection isolation (117 lines).
- `docling_reader.py` (311 lines) / `pdf_reader.py` (149 lines): extraction.
- `ocr_fallback.py` (320 lines) / `visual_analyzer.py` (264 lines): enrichment stages.
- `models.py` (138 lines): canonical schemas + `cache_dir_for`.
- `doc_store.py` (413 lines): SQLite persistence.
- `upload_validation.py` (113 lines): ingestion front end.
- `local_embedding.py` (71 lines) / `vector_index.py` (228 lines): retrieval.

**Testing:**
- `tests/conftest.py`: fixtures and mocking seams for fully offline runs.
- `tests/test_*.py`: 13 unit-test modules (see per-file table below).

## Per-File Module Table

| File | Lines | Key classes / functions | Depends on | Tested by |
|------|-------|-------------------------|------------|-----------|
| `main.py` | 410 | `load_ai_model()` (`:68-76`); sidebar health badge (`:90-121`); upload loop (`:146-310`); chat loop (`:330-410`) | `doc_store`, `docling_reader`, `local_embedding`, `local_llm`, `models`, `ocr_fallback`, `upload_validation`, `visual_analyzer`, `streamlit`, `dotenv` | None (no UI test) |
| `local_llm.py` | 153 | `AiModel` (`:17`): `__init__` (`:20`), `_detect_provider` (`:46`), `check_health` (`:69`), `get_capabilities` (`:91`), `ask_a_question_from_pdf_stream` (`:99`) | `groq_provider`, `llama_cpp_provider`, `local_embedding`, `model_provider`, `pdf_reader`, `prompt_budget` | `tests/test_local_llm.py` |
| `model_provider.py` | 156 | `ProviderCapabilities` (`:15`), `HealthStatus` (`:44`), `BaseModelProvider` (`:64`): `generate_text` (`:78`), `stream_text` (`:99`), `analyze_image` (`:122`), `check_health` (`:141`), `get_capabilities` (`:150`) | `pydantic`, stdlib `abc` | `tests/test_model_provider.py` |
| `llama_cpp_provider.py` | 268 | `LlamaCppProvider` (`:18`): `check_health` (`:49`, `GET /health`), `get_capabilities` (`:96`), `generate_text` (`:110`), `stream_text` (`:155`, SSE), `analyze_image` (`:216`, base64) | `model_provider`, `httpx` | `tests/test_llama_cpp_provider.py` |
| `groq_provider.py` | 170 | `GroqProvider` (`:18`): `check_health` (`:59`), `get_capabilities` (`:85`), `generate_text` (`:99`), `stream_text` (`:128`), `analyze_image` (`:163`, raises) | `model_provider`, `groq` (optional), `streamlit` (secrets) | covered via `tests/conftest.py::mock_groq_client` |
| `prompt_budget.py` | 117 | `SYSTEM_GROUNDING_TEMPLATE` (`:11`), `sanitize_xml_boundary` (`:20`), `estimate_tokens` (`:34`), `assemble_grounded_messages` (`:48`) | stdlib `math` only | `tests/test_prompt_budget.py` |
| `docling_reader.py` | 311 | `DoclingReader` (`:34`): `__init__` (`:37`), `extract_text` (`:78`), `get_paragraphs` (`:295`), `get_page_records` (`:301`), `extract_small_portion_of_the_pdf` (`:307`) | `docling` (optional), `pdf_reader` (fallback), `models`, `langchain_text_splitters` | `tests/test_docling_reader.py` |
| `pdf_reader.py` | 149 | `PdfReader` (`:10`): `extract_text` (`:29`), `extract_small_portion_of_the_pdf` (`:116`), `get_paragraphs` (`:124`), `get_page_records` (`:133`) | `pypdf`, `models`, `langchain_text_splitters` | `tests/test_pdf_reader.py` |
| `ocr_fallback.py` | 320 | `should_ocr_page` (`:29`), `OcrEngine` (`:46`): `is_available` (`:71`), `render_page_image` (`:77`), `ocr_page_image` (`:112`); `apply_conditional_ocr` (`:162`) | `rapidocr_onnxruntime` + `fitz` (optional), `models`, `langchain_text_splitters` | `tests/test_ocr_fallback.py` |
| `visual_analyzer.py` | 264 | `VisualAnalyzer` (`:30`): `detect_visual_regions` (`:47`), `crop_visual_element` (`:138`), `analyze_visual_elements` (`:185`); `DEFAULT_VISION_PROMPT` (`:23`) | `model_provider`, `models`, `fitz` (optional) | `tests/test_visual_analyzer.py` |
| `local_embedding.py` | 71 | `LocalEmbedding` (`:11`): `_embed_one` (`:27`), `get_embeddings` (`:34`), `build_index` (`:41`), `search` (`:60`), `get_context` (`:66`) | `sentence_transformers`, `vector_index` | `tests/test_local_embedding.py` |
| `vector_index.py` | 228 | `VectorIndex` (`:15`): `add_document` (`:39`), `add_vector` (`:65`), `search` (`:92`), `_euclidean_distance` (`:142`), `_cosine_distance` (`:157`), `_dot_product` (`:193`), `_magnitude` (`:198`) | stdlib `math`, `typing` only | `tests/test_vector_index.py` |
| `doc_store.py` | 413 | `DocStore` (`:78`): `_connect` (`:97`), `_apply_migrations` (`:116`), `upsert_document` (`:131`), `get_document` (`:168`), `get_by_sha` (`:188`), `list_documents` (`:208`), `record_page` (`:220`), `record_chunks` (`:253`), `get_chunks_for_doc` (`:303`), `record_evidence_elements` (`:327`), `get_evidence_for_doc` (`:373`), `delete_document` (`:400`); `SCHEMA_V1_DDL` (`:16`), `SCHEMA_V2_DDL` (`:56`), `MIGRATIONS` (`:72`) | stdlib `sqlite3`, `models` | `tests/test_doc_store.py` |
| `models.py` | 138 | `CONFIG_VERSION` (`:14`), `cache_dir_for` (`:17`), `BBox` (`:33`), `Chunk` (`:54`), `Page` (`:75`), `EvidenceElement` (`:90`), `Document` (`:115`) | `pydantic` | `tests/test_models.py` |
| `upload_validation.py` | 113 | `MAX_FILE_MB`/`MAX_PAGES` (`:15-16`), `sha256_bytes` (`:19`), `doc_id_for` (`:36`), `ValidatedUpload` (`:52`), `validate_pdf_bytes` (`:64`) | `pypdf`, stdlib `hashlib` | `tests/test_upload_validation.py` |
| `scripts/benchmark_baseline.py` | 174 | `run_benchmark()` (`:28`), `get_current_rss_mb()` (`:23`) | `pdf_reader`, `vector_index`, `sentence_transformers`, `psutil`, `numpy` | None (harness, not suite) |
| `tests/conftest.py` | 161 | `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path`, `mock_llama_provider` | `pytest`, `numpy`, `local_embedding`, `model_provider` | — (fixtures) |
| `tests/data/corpus/generate_corpus.py` | — | corpus generator (reportlab) | `reportlab` | — (fixture factory) |

## Dependency Graph

```text
main.py
 ├── doc_store.py ──→ models.py ──→ pydantic
 ├── docling_reader.py ──→ docling (optional)
 │                      ──→ pdf_reader.py ──→ pypdf + langchain_text_splitters ──→ models.py
 │                      ──→ models.py
 ├── ocr_fallback.py ──→ rapidocr-onnxruntime (optional) + fitz/PyMuPDF (optional)
 │                    ──→ models.py + langchain_text_splitters
 ├── visual_analyzer.py ──→ fitz/PyMuPDF (optional)
 │                       ──→ model_provider.py ──→ pydantic
 │                       ──→ models.py
 ├── local_embedding.py ──→ sentence-transformers
 │                       ──→ vector_index.py (stdlib only)
 ├── local_llm.py ──→ groq_provider.py ──→ groq (optional) + model_provider.py
 │                 ──→ llama_cpp_provider.py ──→ httpx + model_provider.py
 │                 ──→ prompt_budget.py (stdlib only)
 │                 ──→ local_embedding.py / pdf_reader.py (fallback path)
 ├── upload_validation.py ──→ pypdf + hashlib
 └── streamlit + dotenv (UI/runtime only)

No cycles. Optional heavy deps (docling, rapidocr, fitz, groq) are all
guarded try/except imports with graceful degradation.
```

## Naming Conventions

**Files:**
- Root modules: flat `snake_case.py`, one public class per file, no packages/`__init__.py` (except `tests/__init__.py`).
- Providers: `*_provider.py` subclassing `BaseModelProvider` (`groq_provider.py`, `llama_cpp_provider.py`).
- Pipeline stages: noun-named modules (`docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `upload_validation.py`, `doc_store.py`).
- Tests: `test_<module>.py` mirroring the module under test (`tests/test_doc_store.py`, `tests/test_vector_index.py`).
- Docs: `UPPER_SNAKE.md` for planning maps (`ARCHITECTURE.md`), `TitleCase.md` for runbooks (`docs/LOCAL_INFERENCE.md`).

**Directories:**
- Lowercase, singular-purpose (`scripts/`, `tests/`, `docs/`, `data/`); planning dirs under `.planning/` are hyphenated lowercase (`phases/`, `codebase/`, `research/`).

## Where to Add New Code

**New inference backend:**
- Implementation: new root module `x_provider.py` subclassing `BaseModelProvider` (`model_provider.py:64`), returning `ProviderCapabilities`/`HealthStatus`; add `close()` if it holds connections.
- Wiring: extend `AiModel._detect_provider` (`local_llm.py:46-67`) or inject via `AiModel(provider=...)`; expose via a public accessor rather than `model._provider`.
- Tests: `tests/test_x_provider.py` mocking HTTP with `httpx.MockTransport` (see `tests/test_llama_cpp_provider.py`); add a `mock_x_provider` fixture in `tests/conftest.py` if the UI needs it.

**New canonical model:**
- Implementation: add to `models.py` with `ConfigDict(frozen=True, extra="forbid")` and Pydantic validators; keep legacy dict-key compatibility in `model_dump()`; bump `CONFIG_VERSION` (`models.py:14`) if chunking/extraction policy changes.
- Tests: `tests/test_models.py`; add a migration in `doc_store.py::MIGRATIONS` if the model needs a new table.

**New ingestion/extraction stage:**
- Implementation: new root module (e.g. `table_extract.py`) operating on `(pdf_bytes, page_records, chunks)` and returning updated records, following the `apply_conditional_ocr` signature shape (`ocr_fallback.py:162-171`); wire between OCR and visual steps in `main.py:221-240`; record `Page` status through `doc_store.record_page`.
- Tests: `tests/test_<stage>.py` with injected fakes (see `OcrEngine(recognizer=..., renderer=...)` and `VisualAnalyzer(region_detector=..., cropper=...)` seams); add corpus archetypes in `tests/data/corpus/generate_corpus.py`.

**New visual capability:**
- Implementation: extend `visual_analyzer.py` (new `kind` in `EvidenceElement.kind` literal in `models.py:100` + detector branch in `detect_visual_regions`); keep `source="vlm:<model>"` provenance separation.
- Tests: `tests/test_visual_analyzer.py`.

**New prompt-budget policy:**
- Implementation: extend `prompt_budget.py` (`assemble_grounded_messages`); token window always comes from `ProviderCapabilities.context_window`, never a literal.
- Tests: `tests/test_prompt_budget.py`.

**New UI section:**
- Implementation: `main.py` — add session-state keys to the init loop (`main.py:52-60`), render inside `with st.sidebar:` or the main area, end batch updates with `st.rerun()`; reuse `st.session_state.ai_model` for the active provider instead of re-constructing one.

**Shared helpers:**
- Prefer extending the owning module; there is no generic `utils.py`. Pure helpers live next to their domain (`models.cache_dir_for`, `upload_validation.sha256_bytes`).

## Special Directories

**`data/`:**
- Purpose: `documents.db` SQLite database at runtime (WAL mode).
- Generated: Yes. Committed: No.

**`.cache/`:**
- Purpose: per-document JSON cache (`pages.json`, `chunks.json`, `manifest.json`) keyed by `<sha256>/<CONFIG_VERSION>` via `cache_dir_for` (`models.py:17-30`).
- Generated: Yes. Committed: No.

**`tests/__pycache__`, `.pytest_cache`, `.ruff_cache`, `__pycache__/`:**
- Generated: Yes. Committed: No.

**`tests/data/corpus/*.pdf`:**
- Generated by `generate_corpus.py`. Committed: No — CI regenerates before running tests.

---

*Structure analysis: 2026-10-11*
