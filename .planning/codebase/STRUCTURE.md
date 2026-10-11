# Codebase Structure

**Analysis Date:** 2026-10-11

## Directory Layout

```
RAG/
├── main.py                 # Streamlit entry point (sole runtime entry, 450 lines)
├── hybrid_retriever.py     # Persistent hybrid retrieval: LanceDB + BM25 + RRF (622 lines)
├── local_embedding.py      # CPU-pinned SentenceTransformer wrapper (116 lines)
├── vector_index.py         # Pure-stdlib in-memory vector store (228 lines)
├── local_llm.py            # AiModel RAG orchestrator + provider delegation (180 lines)
├── models.py               # Canonical Pydantic v2 contracts (204 lines)
├── model_provider.py       # BaseModelProvider ABC + HealthStatus/Capabilities (156 lines)
├── groq_provider.py        # Groq Cloud provider (170 lines)
├── llama_cpp_provider.py   # Local llama-server provider (268 lines)
├── prompt_budget.py        # Bounded context + XML injection defense (117 lines)
├── doc_store.py            # SQLite WAL metadata store (413 lines)
├── docling_reader.py       # Docling structured extraction + pypdf fallback (311 lines)
├── pdf_reader.py           # Legacy pypdf extraction + chunking (149 lines)
├── ocr_fallback.py         # Conditional RapidOCR for scanned pages (320 lines)
├── visual_analyzer.py      # Visual element detection + VLM analysis (264 lines)
├── upload_validation.py    # PDF header/size/page validation (113 lines)
├── tests/                  # pytest suite (14 test modules + data/corpus)
├── scripts/
│   └── benchmark_baseline.py  # Manual retrieval/generation benchmark
├── docs/
│   └── LOCAL_INFERENCE.md  # Local inference setup notes
├── data/                   # Runtime persistence (gitignored contents)
│   ├── documents.db*       # SQLite DocStore database (created at runtime)
│   └── lancedb/            # LanceDB tables or fallback_store.json
├── .cache/                 # Per-document disk cache (created at runtime)
├── application_screenshots/  # UI screenshots for docs
├── .devcontainer/          # Pinned Python 3.11 image + Streamlit auto-launch
├── .planning/              # GSD planning artifacts (incl. this codebase map)
├── requirements.txt        # Pinned runtime dependencies
├── requirements-test.txt   # Test-only dependencies
├── pyproject.toml          # Ruff (line-length 120) + pytest config
└── README.md               # Setup, run, and architecture documentation
```

## Directory Purposes

**Repo root (flat modular monolith):**
- Purpose: All application modules live at the root — one file per service, no packages, no `__init__.py`.
- Contains: `main.py`, `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`, `models.py`, providers, ingestion helpers, `requirements*.txt`, `pyproject.toml`.
- Key files: `main.py` (entry), `hybrid_retriever.py` (retrieval core), `models.py` (contracts).

**tests/:**
- Purpose: pytest suite mirroring each root module, plus a file corpus.
- Contains: `conftest.py`, `__init__.py`, `test_doc_store.py` (403 lines), `test_docling_reader.py` (274), `test_hybrid_retriever.py` (390), `test_llama_cpp_provider.py` (259), `test_local_embedding.py` (45), `test_local_llm.py` (226), `test_model_provider.py` (148), `test_models.py` (455), `test_ocr_fallback.py` (326), `test_pdf_reader.py` (202), `test_prompt_budget.py` (146), `test_upload_validation.py` (111), `test_vector_index.py` (109), `test_visual_analyzer.py` (369), `data/corpus/` (sample PDFs for ingestion tests).
- Key files: `tests/test_hybrid_retriever.py` (dense + BM25 + RRF + persistence coverage), `tests/conftest.py` (shared fixtures).

**scripts/:**
- Purpose: Manual/one-off tooling, excluded from strict lint (`pyproject.toml` per-file-ignores for `E402`).
- Contains: `scripts/benchmark_baseline.py`.
- Key files: `scripts/benchmark_baseline.py` — run manually, not part of the app or test suite.

**data/:**
- Purpose: Runtime persistence created on first run; contents are gitignored.
- Contains: `documents.db` (+ WAL/SHM sidecars) from `DocStore(Path("data/documents.db"))` (`main.py:155`); `lancedb/` LanceDB tables or `fallback_store.json` from `HybridRetriever` (`hybrid_retriever.py:27, 110`).
- Key files: None committed — directory structure only.

**.cache/:**
- Purpose: Best-effort per-document disk cache (`STORE-03`), written in `main.py:300-310`.
- Contains: `<sha256>/docling-1000-200-v1/{pages.json, chunks.json, manifest.json}` via `cache_dir_for` (`models.py:17-30`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Key files: None committed.

**docs/:**
- Purpose: Supplemental setup documentation.
- Contains: `docs/LOCAL_INFERENCE.md`.

**.planning/codebase/:**
- Purpose: GSD codebase maps consumed by plan/execute commands (this file, `ARCHITECTURE.md`, `STACK.md`, `CONVENTIONS.md`, etc.).

## Key File Locations

**Entry Points:**
- `main.py`: Sole runtime entry — `streamlit run main.py`.
- `scripts/benchmark_baseline.py`: Manual benchmark entry.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`) + pytest (`testpaths = ["tests"]`).
- `requirements.txt`: Runtime pins incl. `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `docling>=2.0.0`, `sentence-transformers==3.4.1`, `pydantic==2.11.9`.
- `requirements-test.txt`: Test-only deps.
- `.devcontainer/devcontainer.json`: Pinned Python 3.11 image, Streamlit auto-launch on port 8501.

**Core Logic:**
- `hybrid_retriever.py`: `compute_rrf` (lines 31-76), `HybridRetriever` (lines 79-622) — `index_chunks`, `search_dense`, `search_fts`, `_bm25_search_fallback`, `search_hybrid` → `RetrievalResult`, legacy `search`/`get_context` facades.
- `models.py`: `BBox` (33-51), `Chunk` (54-72), `Page` (75-87), `EvidenceElement` (90-112), `Document` (115-138), `EvidenceSnippet` (141-167), `RetrievalResult` + `formatted_evidence`/`source_labels` (170-204).
- `local_llm.py`: `AiModel._detect_provider` (48-69), `ask_a_question_from_pdf_stream` (101-180) — `retrieval_result`-first branch (121-122), in-LLM fallback retrieval (130-159), `assemble_grounded_messages` + `provider.stream_text` (163-180).
- `main.py`: Session-state init (53-62), `load_ai_model` (70-78), upload/index loop (151-331), chat + single shared retrieval (383-450).

**Testing:**
- `tests/test_hybrid_retriever.py`: CPU pinning, anchored default path, dense indexing/search, BM25, RRF, persistence/round-trip.
- `tests/test_local_llm.py`: Stream orchestration incl. `retrieval_result` precedence.
- `tests/test_models.py`: Contract validation for all Pydantic models.
- `tests/conftest.py`: Shared fixtures for the suite.

## Naming Conventions

**Files:**
- `snake_case.py`, one public class/service per file: `hybrid_retriever.py` → `HybridRetriever` + `compute_rrf`; `doc_store.py` → `DocStore`; `prompt_budget.py` → module functions. Exception: `main.py` (entry, no class) and `model_provider.py` (ABC + two schemas).

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `docs/`, `data/`, `.cache/`, `application_screenshots/`, `.devcontainer/`, `.planning/`.

**Tests:**
- Mirror pattern `test_<module>.py` → tests `tests/test_<module>.py` (e.g. `hybrid_retriever.py` → `tests/test_hybrid_retriever.py`).

## Where to Add New Code

**New retrieval behavior (ranking, fusion, search mode):**
- Primary code: `hybrid_retriever.py` — add methods alongside `search_dense`/`search_fts`/`search_hybrid`; pure ranking math goes in module-level functions next to `compute_rrf`.
- Contracts first: extend `EvidenceSnippet`/`RetrievalResult` in `models.py` before wiring consumers.
- Tests: `tests/test_hybrid_retriever.py`.

**New ingestion/extraction behavior:**
- Primary code: `docling_reader.py` (structured), `pdf_reader.py` (legacy), `ocr_fallback.py` (scanned pages), `visual_analyzer.py` (visual elements); validation in `upload_validation.py`.
- Wire-up: `main.py:222-264` extraction block; persistence via `doc_store.py`.
- Tests: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_upload_validation.py`.

**New inference provider or prompt behavior:**
- Primary code: new provider subclassing `BaseModelProvider` in `model_provider.py` next to `groq_provider.py`/`llama_cpp_provider.py`; prompt assembly in `prompt_budget.py`; delegation in `local_llm.py`.
- Tests: `tests/test_model_provider.py`, `tests/test_llama_cpp_provider.py`, `tests/test_local_llm.py`, `tests/test_prompt_budget.py`.

**New persisted metadata:**
- Primary code: `models.py` (Pydantic contract) → `doc_store.py` (table + migration in `MIGRATIONS`, record/get methods).
- Tests: `tests/test_doc_store.py`, `tests/test_models.py`.

**Utilities:**
- Shared helpers: root-level `snake_case.py` module + direct import (`from x import Y`) — no packages, no barrel files.

## Dependency Graph

```text
main.py
 ├── local_llm.py (AiModel)
 │    ├── model_provider.py (BaseModelProvider, HealthStatus, ProviderCapabilities)
 │    ├── groq_provider.py ──► model_provider.py
 │    ├── llama_cpp_provider.py ──► model_provider.py
 │    ├── prompt_budget.py (assemble_grounded_messages, standalone)
 │    ├── hybrid_retriever.py ──► models.py, vector_index.py
 │    │    ├── models.py (Chunk, BBox, EvidenceSnippet, RetrievalResult)
 │    │    └── vector_index.py (stdlib only: math, typing)
 │    ├── local_embedding.py ──► models.py, vector_index.py
 │    │    └── sentence-transformers (external, CPU-pinned)
 │    └── pdf_reader.py ──► pypdf, langchain-text-splitters (external)
 ├── hybrid_retriever.py (direct: dual-index writes + query)
 ├── local_embedding.py (direct: build_index + CR-01 restore)
 ├── docling_reader.py ──► models.py, pdf_reader.py (fallback)
 ├── doc_store.py ──► models.py (Chunk, Document, Page, EvidenceElement)
 ├── ocr_fallback.py
 ├── visual_analyzer.py ──► doc_store.py (record_evidence_elements)
 ├── upload_validation.py (standalone)
 └── models.py (no project imports — leaf contract module)

External-only leaves: prompt_budget.py, upload_validation.py, vector_index.py
```

**Import direction (must stay acyclic):** `main.py` → `local_llm.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py` → `prompt_budget.py`, `model_provider.py`; `docling_reader.py` → `pdf_reader.py`; everything persistence-shaped → `models.py`. `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py` import no project modules.

## Special Directories

**data/:**
- Purpose: Runtime SQLite + LanceDB persistence.
- Generated: Yes (created on first upload/index run).
- Committed: No (gitignored; only the directory placeholder exists in the repo).

**.cache/:**
- Purpose: Per-document `{pages,chunks,manifest}.json` cache keyed by SHA-256 + `CONFIG_VERSION`.
- Generated: Yes (best-effort write per upload).
- Committed: No.

**application_screenshots/:**
- Purpose: UI screenshots embedded in docs/README.
- Generated: No (manual captures).
- Committed: Yes.

**tests/data/corpus/:**
- Purpose: Sample PDFs exercised by ingestion/extraction tests.
- Generated: No (checked-in fixtures).
- Committed: Yes.

---

*Structure analysis: 2026-10-11*
