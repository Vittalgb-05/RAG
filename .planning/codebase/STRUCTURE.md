# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
RAG/
├── main.py                 # Streamlit app — sole production entry point
├── models.py               # Pydantic v2 canonical schemas + cache path helper
├── doc_store.py            # SQLite metadata store (DocStore)
├── upload_validation.py    # PDF magic/size/page validation + SHA identity
├── pdf_reader.py           # pypdf extraction + chunking + Page records
├── local_embedding.py      # SentenceTransformer wrapper + retrieval facade
├── vector_index.py         # Pure-stdlib in-memory vector store
├── local_llm.py            # Groq client + streaming RAG generation
├── tests/                  # Pytest suite (7 modules + conftest + corpus)
│   ├── conftest.py         # Mock seams (Groq, SentenceTransformer, env)
│   ├── test_models.py      # Schema/serialization tests (230 lines)
│   ├── test_doc_store.py   # SQLite persistence tests (173 lines)
│   ├── test_upload_validation.py  # Validation tests (84 lines)
│   ├── test_pdf_reader.py  # Extraction/chunking tests (202 lines)
│   ├── test_vector_index.py
│   ├── test_local_embedding.py
│   ├── test_local_llm.py
│   └── data/corpus/        # Synthetic PDFs + generate_corpus.py
├── scripts/
│   └── benchmark_baseline.py  # Perf harness → BASELINE_BENCHMARK.json
├── data/                   # SQLite DB (gitignored, runtime-created)
│   └── documents.db        # DocStore database (WAL mode)
├── .cache/                 # Disk cache (runtime-created, safe to delete)
│   └── <sha256>/<config>/  # pages.json, chunks.json, manifest.json
├── .github/workflows/
│   └── ci.yml              # Ruff + corpus-gen + pytest on Python 3.11
├── .devcontainer/
│   └── devcontainer.json   # Python 3.11 image + Streamlit auto-launch
├── .planning/              # GSD planning artefacts (codebase/, research/)
├── requirements.txt        # Pinned runtime deps (incl. pydantic, numpy)
├── requirements-test.txt   # pytest, reportlab, ruff, psutil
├── pyproject.toml          # Ruff config + pytest testpaths
└── README.md               # Setup/usage docs
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at root — one class per file, no packages, no `__init__.py`.
- Contains: `main.py`, `models.py`, `doc_store.py`, `upload_validation.py`, `pdf_reader.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`.
- Key files: `main.py` (orchestrator), `models.py` (contracts), `doc_store.py` (persistence).

**tests/:**
- Purpose: Full offline pytest suite — 100% offline via `conftest.py` mocks (no GPU, no API calls).
- Contains: 7 `test_*.py` modules, `conftest.py`, `__init__.py`, `data/corpus/` with `generate_corpus.py` + 6 synthetic PDFs.
- Key files: `tests/conftest.py` (mock_groq_client, mock_sentence_transformer, fake_env_groq_key, sample_pdf_path), `tests/data/corpus/generate_corpus.py` (reportlab synthesiser).

**scripts/:**
- Purpose: One-off operational harnesses, not imported by the app.
- Contains: `scripts/benchmark_baseline.py` (174 lines — extraction/chunking/embed/scan timing + RSS profiling).
- Key files: `scripts/benchmark_baseline.py` → writes `.planning/research/BASELINE_BENCHMARK.json`.

**data/ (gitignored, runtime-created):**
- Purpose: SQLite database directory auto-created by `DocStore.__init__` (`doc_store.py:73-74`).
- Contains: `documents.db` (+ WAL/SHM sidecars at runtime).
- Generated: Yes. Committed: No (`.gitignore:10`).

**.cache/ (runtime-created, safe to delete):**
- Purpose: Best-effort disk cache of derived artefacts per document + config version.
- Contains: `.cache/<64-hex-sha256>/chunker-1000-200-pypdf/{pages.json,chunks.json,manifest.json}`.
- Generated: Yes (`main.py:191-201`). Committed: No. Layout helper: `models.py:cache_dir_for` (15-26).

**.github/workflows/:**
- Purpose: CI pipeline.
- Contains: `ci.yml` (41 lines — pip install both requirements files → `ruff check` + `ruff format --check` → corpus generation → `pytest tests/ -v`).

**.planning/:**
- Purpose: GSD artefacts — `codebase/` maps, `research/` baselines (`BASELINE_BENCHMARK.json`, `STACK.md`, `FEATURES.md`, `PITFALLS.md`, `SUMMARY.md`, `ARCHITECTURE.md`).
- Generated: Partially (benchmark output). Committed: Yes.

## Key File Locations

**Entry Points:**
- `main.py`: Sole production entry (`streamlit run main.py`, 297 lines).
- `scripts/benchmark_baseline.py`: Perf harness entry (`python scripts/benchmark_baseline.py`).
- `tests/data/corpus/generate_corpus.py`: Corpus synthesiser (CI pre-test step).

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`, `E/F/W` rules) + pytest (`testpaths = ["tests"]`) config.
- `requirements.txt`: Runtime pins (streamlit 1.42.0, pypdf 5.3.0, python-dotenv 1.0.1, langchain-text-splitters 0.3.6, groq 0.15.0, sentence-transformers 3.4.1, numpy range, pydantic 2.11.9).
- `requirements-test.txt`: pytest, reportlab, ruff, psutil.
- `.devcontainer/devcontainer.json`: Python 3.11 image, port 8501, post-attach Streamlit launch.
- `.github/workflows/ci.yml`: CI job definition.
- `.gitignore`: Ignores `.env`, `.venv`, `data/`, caches, build artefacts.

**Core Logic:**
- `upload_validation.py` (107 lines): Upload gate + content identity.
- `models.py` (111 lines): Canonical schemas + cache layout.
- `doc_store.py` (294 lines): SQLite persistence.
- `pdf_reader.py` (145 lines): Extraction + chunking.
- `local_embedding.py` (71 lines): Embedding facade.
- `vector_index.py` (228 lines): In-memory k-NN store.
- `local_llm.py` (84 lines): Grounded streaming generation.

**Testing:**
- `tests/conftest.py` (88 lines): Shared fixtures/mocks.
- `tests/test_models.py` (230 lines), `tests/test_doc_store.py` (173 lines), `tests/test_pdf_reader.py` (202 lines), `tests/test_upload_validation.py` (84 lines), plus `test_vector_index.py`, `test_local_embedding.py`, `test_local_llm.py`.
- `tests/data/corpus/`: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf`, `generate_corpus.py`.

## Per-File Reference

| File | Lines | Key classes / functions | Depends on | Used by |
|------|-------|-------------------------|------------|---------|
| `main.py` | 297 | `load_ai_model()` (`@st.cache_resource`); 8-step upload loop (`main.py:119-216`); chat loop (`main.py:267-297`) | `doc_store.DocStore`, `local_embedding.LocalEmbedding`, `local_llm.AiModel`, `models.Document/cache_dir_for`, `pdf_reader.PdfReader`, `upload_validation.validate_pdf_bytes` | Streamlit runtime (entry) |
| `models.py` | 111 | `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document`; `CONFIG_VERSION`; `cache_dir_for(base, sha256)` | `pydantic` only | `doc_store.py`, `pdf_reader.py`, `main.py`, tests |
| `doc_store.py` | 294 | `DocStore`: `__init__`, `_connect`, `_apply_migrations`, `upsert_document`, `get_document`, `get_by_sha`, `list_documents`, `record_page`, `record_chunks`, `get_chunks_for_doc`; `SCHEMA_V1_DDL`, `MIGRATIONS` | `sqlite3`, `pathlib`, `models` | `main.py:117-188`, tests |
| `upload_validation.py` | 107 | `validate_pdf_bytes`, `sha256_bytes`, `doc_id_for`, `ValidatedUpload`; `MAX_FILE_MB=50`, `MAX_PAGES=500` | `pypdf`, `hashlib`, `io` | `main.py:127`, tests |
| `pdf_reader.py` | 145 | `PdfReader`: `__init__`, `extract_text(doc_id, sha12)`, `extract_small_portion_of_the_pdf`, `get_paragraphs`, `get_page_records` | `pypdf`, `langchain_text_splitters`, `re`, `models.Chunk/Page` | `main.py:157-162`, `local_llm.py:44`, tests |
| `local_embedding.py` | 71 | `LocalEmbedding`: `__init__`, `_embed_one`, `get_embeddings`, `build_index`, `search`, `get_context` | `sentence_transformers`, `vector_index.VectorIndex` | `main.py:172-174,274`, `local_llm.py:46`, tests |
| `vector_index.py` | 228 | `VectorIndex`: `add_document`, `add_vector`, `search`, `_cosine_distance`, `_euclidean_distance`, `_dot_product`, `_magnitude`, `__len__`, `__repr__` | stdlib `math`, `typing` only | `local_embedding.py:25`, tests, benchmark |
| `local_llm.py` | 84 | `AiModel`: `__init__`, `ask_a_question_from_pdf_stream` | `groq.Groq` (guarded), `pdf_reader`, `local_embedding`, `streamlit`, `os` | `main.py:87,289`, tests |
| `scripts/benchmark_baseline.py` | 174 | `run_benchmark()`, `get_current_rss_mb()` | `pdf_reader`, `vector_index`, `sentence_transformers`, `psutil`, `numpy` | Manual / research only |
| `tests/conftest.py` | 88 | `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`, `sample_pdf_path` | `pytest`, `numpy`, `unittest.mock` | All test modules |
| `tests/test_models.py` | 230 | Schema, legacy-key compat, immutability, `extra="forbid"`, serialisation tests | `models` | pytest |
| `tests/test_doc_store.py` | 173 | Roundtrip, WAL, migrations, `UNIQUE(sha256)`, page/chunk storage tests | `doc_store`, `models` | pytest |
| `tests/test_upload_validation.py` | 84 | Magic-byte, size-cap, page-cap, hashing, `doc_id` tests | `upload_validation` | pytest |
| `tests/test_pdf_reader.py` | 202 | Extraction, chunking, fault isolation, hash chunk-ID tests | `pdf_reader`, corpus PDFs | pytest |
| `tests/test_vector_index.py` | — | Distance math, dimension locking, k-NN ordering tests | `vector_index` | pytest |
| `tests/test_local_embedding.py` | — | Batch embed, index build, search facade tests (mocked transformer) | `local_embedding` | pytest |
| `tests/test_local_llm.py` | — | Prompt assembly, streaming generator tests (mocked Groq) | `local_llm` | pytest |

## Dependency Graph

```text
main.py
 ├── upload_validation.py ──→ pypdf (probe only)
 ├── models.py ──→ pydantic
 ├── doc_store.py ──→ sqlite3 + models.py
 ├── pdf_reader.py ──→ pypdf + langchain_text_splitters + models.py
 ├── local_embedding.py ──→ sentence_transformers + vector_index.py (stdlib only)
 └── local_llm.py ──→ groq + pdf_reader.py + local_embedding.py

tests/ ──→ every module above, via conftest.py mocks (no live model/API)
scripts/benchmark_baseline.py ──→ pdf_reader.py + vector_index.py (+ live transformer)
```

Direction is strictly one-way — no cycles: `vector_index.py` and `models.py` and `upload_validation.py` have zero project imports; `pdf_reader.py` imports only `models.py`; `local_embedding.py` imports only `vector_index.py`; `local_llm.py` imports `pdf_reader.py` + `local_embedding.py`; `doc_store.py` imports only `models.py`; only `main.py` fans out to all of them.

## Naming Conventions

**Files:**
- Flat `snake_case.py` at root, one class per file: `models.py`, `doc_store.py`, `upload_validation.py`, `pdf_reader.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`; `main.py` is the Streamlit entry exception.
- Tests mirror modules: `test_<module>.py` in `tests/` (e.g. `test_doc_store.py` ↔ `doc_store.py`).

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `data/`, `.cache/`, `.planning/`, `.github/`, `.devcontainer/`, `application_screenshots/`.
- Cache layout is content-addressed: `.cache/<sha256>/<CONFIG_VERSION>/` (`models.py:15-26`).

## Where to Add New Code

**New upload pipeline step (e.g. OCR fallback, NSFW scan):**
- Primary code: new root module (e.g. `ocr_fallback.py`) or extend `upload_validation.py` for cheap gate checks; wire into the 8-step loop in `main.py:119-216` between validation (step 2) and extraction (step 4).
- Persistence: add tables/columns via a new `MIGRATIONS` entry in `doc_store.py:54-56`, never inline DDL in `main.py`.
- Tests: `tests/test_<module>.py` mirroring the new module.

**New retrieval parameter (e.g. different k, metric):**
- Implementation: `local_embedding.py` (`search`/`get_context` defaults) and/or `vector_index.py` (new distance fn + metric whitelist in `__init__`).
- Call sites: `main.py:274` (sources pre-fetch) and `local_llm.py:56` (generation context) — keep both in sync.

**New Pydantic schema:**
- Implementation: `models.py` alongside `BBox`/`Chunk`/`Page`/`EvidenceElement`/`Document`; bump `CONFIG_VERSION` (`models.py:12`) if chunking/extraction policy changes so `.cache/` segregates old artefacts.
- Storage: add table + CRUD in `doc_store.py`; add tests in `tests/test_models.py` + `tests/test_doc_store.py`.

**New component/module:**
- Implementation: new root-level `snake_case.py` with one public class, imported by name (`from x import Y`); no packages, no barrel files.

**Utilities:**
- Shared helpers: keep in the owning module (`sha256_bytes`/`doc_id_for` in `upload_validation.py`, `cache_dir_for` in `models.py`); no separate `utils/` directory exists — do not create one.

**Benchmarks:**
- Harness code: `scripts/` (see `scripts/benchmark_baseline.py` for the `sys.path` bootstrap + JSON report pattern).

## Special Directories

**data/:**
- Purpose: Runtime SQLite database (`documents.db` + WAL/SHM sidecars).
- Generated: Yes (auto-created by `DocStore.__init__`). Committed: No (`.gitignore:10`).

**.cache/:**
- Purpose: Derived per-document artefacts (`pages.json`, `chunks.json`, `manifest.json`).
- Generated: Yes. Committed: No. Safe to delete — rebuilt on re-upload.

**tests/data/corpus/:**
- Purpose: Synthetic test PDFs generated by `generate_corpus.py` (reportlab); includes `clean_digital.pdf` (happy path), `corrupt_invalid.pdf` (negative path), plus `dense_table`, `multi_column`, `chart_diagram`, `scanned_sample` variants.
- Generated: Yes (CI regenerates before pytest). Committed: PDFs present on disk but regenerable.

**.planning/:**
- Purpose: GSD maps (`codebase/`), research baselines (`research/BASELINE_BENCHMARK.json`, `STACK.md`, `FEATURES.md`, `PITFALLS.md`).
- Generated: Partially. Committed: Yes.

**application_screenshots/:**
- Purpose: UI screenshots for docs/demo.
- Generated: No. Committed: Yes.

---

*Structure analysis: 2026-10-11*
