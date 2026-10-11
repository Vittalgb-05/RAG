# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
RAG/
├── main.py                 # Streamlit app — sole production entry point (329 lines)
├── models.py               # Pydantic v2 canonical schemas + cache path helper (131 lines)
├── doc_store.py            # SQLite metadata store (DocStore) (307 lines)
├── upload_validation.py    # PDF magic/size/page validation + SHA identity (113 lines)
├── pdf_reader.py           # pypdf extraction + chunking + Page records (149 lines)
├── local_embedding.py      # SentenceTransformer wrapper + retrieval facade (71 lines)
├── vector_index.py         # Pure-stdlib in-memory vector store (228 lines)
├── local_llm.py            # Groq client + streaming RAG generation (84 lines)
├── tests/                  # Pytest suite (7 modules + conftest + corpus)
│   ├── conftest.py         # Mock seams (Groq, SentenceTransformer, env) (88 lines)
│   ├── test_models.py      # Schema/serialization tests (297 lines)
│   ├── test_doc_store.py   # SQLite persistence tests (304 lines)
│   ├── test_upload_validation.py  # Validation tests (111 lines)
│   ├── test_pdf_reader.py  # Extraction/chunking tests (202 lines)
│   ├── test_vector_index.py       # Distance/index tests (109 lines)
│   ├── test_local_embedding.py    # Facade tests, mocked transformer (45 lines)
│   ├── test_local_llm.py          # Prompt/streaming tests, mocked Groq (83 lines)
│   └── data/corpus/        # Synthetic PDFs + generate_corpus.py (213 lines)
├── scripts/
│   └── benchmark_baseline.py  # Perf harness → BASELINE_BENCHMARK.json (174 lines)
├── data/                   # SQLite DB (gitignored, runtime-created — absent on fresh checkout)
│   └── documents.db        # DocStore database (WAL mode)
├── .cache/                 # Disk cache (runtime-created, safe to delete — absent on fresh checkout)
│   └── <sha256>/<config>/  # pages.json, chunks.json, manifest.json
├── .github/workflows/
│   └── ci.yml              # Ruff + corpus-gen + pytest on Python 3.11 (41 lines)
├── .devcontainer/
│   └── devcontainer.json   # Python 3.11 image + Streamlit auto-launch
├── .planning/              # GSD planning artefacts (codebase/, research/)
├── requirements.txt        # Pinned runtime deps (incl. pydantic, numpy)
├── requirements-test.txt   # pytest, reportlab, ruff, psutil
├── pyproject.toml          # Ruff config + pytest testpaths (20 lines)
└── README.md               # Setup/usage docs
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at root — one class per file, no packages, no `__init__.py`.
- Contains: `main.py`, `models.py`, `doc_store.py`, `upload_validation.py`, `pdf_reader.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`.
- Key files: `main.py` (orchestrator, 329 lines), `models.py` (contracts, 131 lines), `doc_store.py` (persistence, 307 lines).

**tests/:**
- Purpose: Full offline pytest suite — 100% offline via `conftest.py` mocks (no GPU, no API calls).
- Contains: 7 `test_*.py` modules, `conftest.py` (88 lines), `__init__.py` (1 line), `data/corpus/` with `generate_corpus.py` (213 lines) + 7 synthetic PDFs.
- Key files: `tests/conftest.py` (fake_env_groq_key, mock_groq_client, mock_sentence_transformer, sample_pdf_path), `tests/data/corpus/generate_corpus.py` (reportlab synthesiser).

**scripts/:**
- Purpose: One-off operational harnesses, not imported by the app.
- Contains: `scripts/benchmark_baseline.py` (174 lines — extraction/chunking/embed/scan timing + RSS profiling via `sys.path` repo-root bootstrap at `scripts/benchmark_baseline.py:16-17`).
- Key files: `scripts/benchmark_baseline.py` → writes `.planning/research/BASELINE_BENCHMARK.json`.

**data/ (gitignored, runtime-created — NOT present on fresh checkout):**
- Purpose: SQLite database directory auto-created by `DocStore.__init__` (`doc_store.py:73-74`).
- Contains at runtime: `documents.db` (+ WAL/SHM sidecars).
- Generated: Yes. Committed: No (`.gitignore` covers `data/`).

**.cache/ (runtime-created, safe to delete — NOT present on fresh checkout):**
- Purpose: Best-effort disk cache of derived artefacts per document + config version.
- Contains at runtime: `.cache/<64-hex-sha256>/chunker-1000-200-pypdf/{pages.json,chunks.json,manifest.json}`.
- Generated: Yes (`main.py:222-232`). Committed: No. Layout helper: `models.py:cache_dir_for` (17-30).

**.github/workflows/:**
- Purpose: CI pipeline.
- Contains: `ci.yml` (41 lines — pip install both requirements files → `ruff check` + `ruff format --check` → corpus generation → `pytest tests/ -v`).

**.planning/:**
- Purpose: GSD artefacts — `codebase/` maps (`ARCHITECTURE.md`, `STRUCTURE.md`, `STACK.md`, `CONVENTIONS.md`, `TESTING.md`, `INTEGRATIONS.md`, `CONCERNS.md`), `research/` baselines (`BASELINE_BENCHMARK.json`, `STACK.md`, `FEATURES.md`, `PITFALLS.md`, `SUMMARY.md`, `ARCHITECTURE.md`), plus milestone/phase dirs.
- Generated: Partially (benchmark output). Committed: Yes.

## Key File Locations

**Entry Points:**
- `main.py`: Sole production entry (`streamlit run main.py`, 329 lines; upload loop `main.py:114-263`, chat loop `main.py:273-329`).
- `scripts/benchmark_baseline.py`: Perf harness entry (`python scripts/benchmark_baseline.py`, `run_benchmark()` at line 28).
- `tests/data/corpus/generate_corpus.py`: Corpus synthesiser (213 lines; CI pre-test step).

**Configuration:**
- `pyproject.toml` (20 lines): Ruff (`line-length = 120`, `target-version = "py311"`, `E/F/W` rules, `E501/W291/W293` ignored, `scripts/*` gets `E402` ignore) + pytest (`testpaths = ["tests"]`, `filterwarnings` ignores).
- `requirements.txt`: Runtime pins (streamlit 1.42.0, pypdf 5.3.0, python-dotenv 1.0.1, langchain-text-splitters 0.3.6, groq 0.15.0, sentence-transformers 3.4.1, numpy range, pydantic 2.11.9).
- `requirements-test.txt`: pytest, reportlab, ruff, psutil.
- `.devcontainer/devcontainer.json`: Python 3.11 image, port 8501, post-attach Streamlit launch.
- `.github/workflows/ci.yml` (41 lines): CI job definition.
- `.gitignore`: Ignores `.env`, `.venv`, `data/`, caches, build artefacts.

**Core Logic:**
- `upload_validation.py` (113 lines): Upload gate + content identity (`validate_pdf_bytes` at 64-113, `sha256_bytes` at 19-33, `doc_id_for` at 36-48, `ValidatedUpload` at 51-62).
- `models.py` (131 lines): Canonical schemas + cache layout (`cache_dir_for` at 17-30, `BBox` at 33-51, `Chunk` at 54-72, `Page` at 75-87, `EvidenceElement` at 90-105, `Document` at 108-131).
- `doc_store.py` (307 lines): SQLite persistence (`DocStore` at 61-307; `SCHEMA_V1_DDL` at 16-54, `MIGRATIONS` at 56-58).
- `pdf_reader.py` (149 lines): Extraction + chunking (`extract_text` at 29-114, `get_paragraphs` at 124-131, `get_page_records` at 133-139).
- `local_embedding.py` (71 lines): Embedding facade (`build_index` at 41-58, `search` at 60-64, `get_context` at 66-71).
- `vector_index.py` (228 lines): In-memory k-NN store (`search` at 92-136, distance fns at 142-199, `__len__`/`__repr__` at 205-213, runnable example at 220-228).
- `local_llm.py` (84 lines): Grounded streaming generation (`__init__` at 13-34, `ask_a_question_from_pdf_stream` at 36-84).

**Testing:**
- `tests/conftest.py` (88 lines): Shared fixtures/mocks (`fake_env_groq_key`, `mock_groq_client` at 18-48, `mock_sentence_transformer`, `sample_pdf_path`).
- `tests/test_models.py` (297 lines), `tests/test_doc_store.py` (304 lines), `tests/test_pdf_reader.py` (202 lines), `tests/test_upload_validation.py` (111 lines), `tests/test_vector_index.py` (109 lines), `tests/test_local_embedding.py` (45 lines), `tests/test_local_llm.py` (83 lines).
- `tests/data/corpus/`: `clean_digital.pdf`, `dense_table.pdf`, `multi_column.pdf`, `chart_diagram.pdf`, `scanned_sample.pdf`, `corrupt_invalid.pdf` (+ table variant), `generate_corpus.py`.

## Per-File Reference

| File | Lines | Key classes / functions | Depends on | Used by |
|------|-------|-------------------------|------------|---------|
| `main.py` | 329 | `load_ai_model()` (`@st.cache_resource`, `main.py:65-73`); size pre-check (`main.py:124-132`); validation (`main.py:137-143`); dedup + restart restore (`main.py:145-168`); guarded extraction (`main.py:176-187`); page persist + progress (`main.py:189-193`); index build (`main.py:195-199`); chunk + doc persist (`main.py:201-219`); disk cache (`main.py:221-232`); session state (`main.py:234-243`); chat loop (`main.py:299-329`) | `doc_store.DocStore`, `local_embedding.LocalEmbedding`, `local_llm.AiModel`, `models.Chunk/Document/cache_dir_for`, `pdf_reader.PdfReader`, `upload_validation.MAX_FILE_MB/validate_pdf_bytes`, `sqlite3` | Streamlit runtime (entry) |
| `models.py` | 131 | `BBox` (33-51, frozen, coord validator), `Chunk` (54-72, frozen, legacy keys + `doc_id`/`extraction`/`embedding_model`), `Page` (75-87, `ok`/`empty`/`failed`), `EvidenceElement` (90-105), `Document` (108-131, `doc_` prefix validator); `CONFIG_VERSION` (14); `cache_dir_for(base, sha256)` (17-30, rejects non-64-hex) | `pydantic` only | `doc_store.py`, `pdf_reader.py`, `main.py`, tests |
| `doc_store.py` | 307 | `DocStore`: `__init__` (66-78), `_connect` context manager (80-96, WAL + 5 s timeout), `_apply_migrations` (98-111), `upsert_document` (113-148), `get_document` (150-168), `get_by_sha` (170-188), `list_documents` (190-200), `record_page` (202-233), `record_chunks` (235-283, batch `executemany`), `get_chunks_for_doc` (285-307, bbox rehydration); `SCHEMA_V1_DDL` (16-54), `MIGRATIONS` (56-58) | `sqlite3`, `pathlib`, `contextlib`, `collections.abc`, `models.BBox/Chunk/Document/Page` | `main.py:118-219`, tests |
| `upload_validation.py` | 113 | `validate_pdf_bytes` (64-113: magic → size → pypdf probe → page caps → hash), `sha256_bytes` (19-33, 1 MiB slices), `doc_id_for` (36-48, `doc_<sha16>`), `ValidatedUpload` (51-62, frozen); `MAX_FILE_MB=50` (15), `MAX_PAGES=500` (16) | `pypdf` (probe only), `hashlib`, `io`, `re`, `dataclasses` | `main.py:124-143`, tests |
| `pdf_reader.py` | 149 | `PdfReader`: `__init__` (12-26), `extract_text(doc_id, sha12)` (29-114, per-page try/except, `{prefix}_p{page}_{j:04d}` chunk IDs at 76), `extract_small_portion_of_the_pdf` (116-122), `get_paragraphs` (124-131), `get_page_records` (133-139) | `pypdf`, `langchain_text_splitters`, `re`, `models.Chunk/Page`, `pathlib` | `main.py:178-184`, `local_llm.py:44`, tests |
| `local_embedding.py` | 71 | `LocalEmbedding`: `__init__` (12-25), `_embed_one` (27-32), `get_embeddings` (34-39, L2-normalised), `build_index` (41-58, str-or-dict), `search` (60-64), `get_context` (66-71, `\n\n---\n\n` join) | `sentence_transformers`, `vector_index.VectorIndex` | `main.py:165-166,197-199,306`, `local_llm.py:46`, tests |
| `vector_index.py` | 228 | `VectorIndex`: `add_document` (39-63), `add_vector` (65-90, dim lock-in), `search` (92-136, linear scan + sort), `_euclidean_distance` (142-155), `_cosine_distance` (157-187, zero-vector + clamp guards), `_dot_product` (193-196), `_magnitude` (198-199), `__len__` (205-206), `__repr__` (208-213) | stdlib `math`, `typing` only | `local_embedding.py:25`, tests, benchmark |
| `local_llm.py` | 84 | `AiModel`: `__init__` (13-34, `openai/gpt-oss-20b`, secrets→env key), `ask_a_question_from_pdf_stream` (36-84: fallback build 43-47, contextualise 49-54, context k=10 at 56, system prompt 58-64, history splice 68-70, Groq stream 75-80, yield 82-84) | `groq.Groq` (guarded 6-9), `pdf_reader`, `local_embedding`, `streamlit`, `os` | `main.py:73,321`, tests |
| `scripts/benchmark_baseline.py` | 174 | `run_benchmark()` (28+), `get_current_rss_mb()` (23-25) | `pdf_reader`, `vector_index`, `sentence_transformers`, `psutil` | Manual / research only |
| `tests/conftest.py` | 88 | `fake_env_groq_key`, `mock_groq_client` (18-48), `mock_sentence_transformer`, `sample_pdf_path` | `pytest`, `numpy`, `unittest.mock` | All test modules |
| `tests/test_models.py` | 297 | Schema, legacy-key compat, immutability, `extra="forbid"`, serialisation, `doc_id`/`sha` validators | `models` | pytest |
| `tests/test_doc_store.py` | 304 | Roundtrip, WAL, migrations, `UNIQUE(sha256)`, page/chunk storage, rehydration tests | `doc_store`, `models` | pytest |
| `tests/test_upload_validation.py` | 111 | Magic-byte, size-cap, page-cap, hashing, `doc_id` tests | `upload_validation` | pytest |
| `tests/test_pdf_reader.py` | 202 | Extraction, chunking, fault isolation, hash chunk-ID tests | `pdf_reader`, corpus PDFs | pytest |
| `tests/test_vector_index.py` | 109 | Distance math, dimension locking, k-NN ordering tests | `vector_index` | pytest |
| `tests/test_local_embedding.py` | 45 | Batch embed, index build, search facade tests (mocked transformer) | `local_embedding` | pytest |
| `tests/test_local_llm.py` | 83 | Prompt assembly, streaming generator tests (mocked Groq) | `local_llm` | pytest |

## Dependency Graph

```text
main.py
 ├── upload_validation.py ──→ pypdf (probe only) + hashlib/io
 ├── models.py ──→ pydantic
 ├── doc_store.py ──→ sqlite3 + models.py (BBox/Chunk/Document/Page)
 ├── pdf_reader.py ──→ pypdf + langchain_text_splitters + models.py (Chunk/Page)
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
- Cache layout is content-addressed: `.cache/<sha256>/<CONFIG_VERSION>/` (`models.py:17-30`).

## Where to Add New Code

**New upload pipeline step (e.g. OCR fallback, NSFW scan):**
- Primary code: new root module (e.g. `ocr_fallback.py`) or extend `upload_validation.py` for cheap gate checks; wire into the 10-step loop in `main.py:124-247` between the pre-check (step 1) and extraction (step 5). Cheap rejections belong before `getvalue()` (see `main.py:124-132`); expensive work belongs after dedup (`main.py:145-168`).
- Persistence: add tables/columns via a new `MIGRATIONS` entry in `doc_store.py:56-58`, never inline DDL in `main.py`.
- Tests: `tests/test_<module>.py` mirroring the new module.

**New retrieval parameter (e.g. different k, metric):**
- Implementation: `local_embedding.py` (`search`/`get_context` defaults at 60-71) and/or `vector_index.py` (new distance fn + metric whitelist in `__init__` at 26-27).
- Call sites: `main.py:306` (sources pre-fetch) and `local_llm.py:56` (generation context) — keep both in sync (both currently `k=10`).

**New Pydantic schema:**
- Implementation: `models.py` alongside `BBox`/`Chunk`/`Page`/`EvidenceElement`/`Document`; bump `CONFIG_VERSION` (`models.py:14`) if chunking/extraction policy changes so `.cache/` segregates old artefacts.
- Storage: add table + CRUD in `doc_store.py`; add tests in `tests/test_models.py` + `tests/test_doc_store.py`.

**New component/module:**
- Implementation: new root-level `snake_case.py` with one public class, imported by name (`from x import Y`); no packages, no barrel files.

**Utilities:**
- Shared helpers: keep in the owning module (`sha256_bytes`/`doc_id_for` in `upload_validation.py`, `cache_dir_for` in `models.py`); no separate `utils/` directory exists — do not create one.

**Benchmarks:**
- Harness code: `scripts/` (see `scripts/benchmark_baseline.py:16-17` for the `sys.path` bootstrap + JSON report pattern).

## Special Directories

**data/ (absent on fresh checkout):**
- Purpose: Runtime SQLite database (`documents.db` + WAL/SHM sidecars), auto-created on first `DocStore(...)` construction.
- Generated: Yes (auto-created by `DocStore.__init__` at `doc_store.py:73-74`). Committed: No (`.gitignore`).

**.cache/ (absent on fresh checkout):**
- Purpose: Derived per-document artefacts (`pages.json`, `chunks.json`, `manifest.json` under `.cache/<sha256>/<CONFIG_VERSION>/`).
- Generated: Yes (`main.py:221-232`). Committed: No. Safe to delete — rebuilt on re-upload.

**tests/data/corpus/:**
- Purpose: Synthetic test PDFs generated by `generate_corpus.py` (reportlab); includes `clean_digital.pdf` (happy path), `corrupt_invalid.pdf` (negative path), plus `dense_table`, `multi_column`, `chart_diagram`, `scanned_sample` variants.
- Generated: Yes (CI regenerates before pytest via `.github/workflows/ci.yml:35-37`). Committed: PDFs present on disk but regenerable.

**.planning/:**
- Purpose: GSD maps (`codebase/`), research baselines (`research/BASELINE_BENCHMARK.json`, `STACK.md`, `FEATURES.md`, `PITFALLS.md`), milestone/phase dirs.
- Generated: Partially. Committed: Yes.

**application_screenshots/:**
- Purpose: UI screenshots for docs/demo.
- Generated: No. Committed: Yes.

---

*Structure analysis: 2026-10-11*
