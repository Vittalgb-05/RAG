# Codebase Structure

**Analysis Date:** 2026-10-12

## Directory Layout

```
RAG/
├── main.py                   # Streamlit entry point: tabs (chat + summarizer), upload/index, QA + validation (622 lines)
├── summarizer.py             # Hierarchical 5-profile map-reduce summarization service (418 lines)
├── citation_validator.py     # Post-generation [En] citation + abstention validator (181 lines)
├── local_llm.py              # AiModel RAG orchestrator + validate_response façade (210 lines)
├── hybrid_retriever.py       # Persistent hybrid retrieval: LanceDB + BM25 + RRF (622 lines)
├── local_embedding.py        # CPU-pinned SentenceTransformer wrapper (116 lines)
├── vector_index.py           # Pure-stdlib in-memory vector store (228 lines)
├── models.py                 # Canonical Pydantic v2 contracts incl. SummaryResult (235 lines)
├── doc_store.py              # SQLite WAL store incl. document_summaries v3 (588 lines)
├── model_provider.py         # BaseModelProvider ABC + HealthStatus/Capabilities (156 lines)
├── groq_provider.py          # Groq Cloud provider (170 lines)
├── llama_cpp_provider.py     # Local llama-server provider (268 lines)
├── prompt_budget.py          # Bounded grounded context + XML injection defense (125 lines)
├── docling_reader.py         # Docling structured extraction + pypdf fallback (311 lines)
├── pdf_reader.py             # Legacy pypdf extraction + chunking (149 lines)
├── ocr_fallback.py           # Conditional RapidOCR for scanned pages (320 lines)
├── visual_analyzer.py        # Visual element detection + VLM analysis (264 lines)
├── upload_validation.py      # PDF header/size/page validation (113 lines)
├── tests/                    # pytest suite (17 test modules + data/corpus)
│   ├── test_summarizer.py          # Map-reduce, profiles, cache, page-refs (342 lines)
│   ├── test_citation_validator.py  # Precision, abstention, empty, AiModel wiring (161 lines)
│   ├── test_main_ui.py             # Chat-turn + summary-display contracts (156 lines)
│   ├── test_doc_store.py           # DocStore incl. summary roundtrip/version/cascade
│   ├── test_local_llm.py           # Stream orchestration incl. retrieval_result + validate_response
│   └── ...                         # Per-module mirrors (see below)
├── scripts/
│   └── benchmark_baseline.py  # Manual retrieval/generation benchmark
├── docs/
│   └── LOCAL_INFERENCE.md    # Local inference setup notes
├── data/                     # Runtime persistence (gitignored contents)
│   ├── documents.db*         # SQLite DocStore database (created at runtime)
│   └── lancedb/              # LanceDB tables or fallback_store.json
├── .cache/                   # Per-document disk cache (created at runtime)
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
- Contains: `main.py`, `summarizer.py`, `citation_validator.py`, `hybrid_retriever.py`, `local_embedding.py`, `vector_index.py`, `local_llm.py`, `models.py`, providers, ingestion helpers, `requirements*.txt`, `pyproject.toml`.
- Key files: `main.py` (entry + tab wiring), `summarizer.py` (summarization core), `citation_validator.py` (grounding gate), `models.py` (contracts).

**tests/:**
- Purpose: pytest suite mirroring each root module, plus a file corpus and UI-contract tests.
- Contains: `conftest.py`, `__init__.py`, `test_summarizer.py` (342), `test_citation_validator.py` (161), `test_main_ui.py` (156), `test_doc_store.py`, `test_docling_reader.py` (274), `test_hybrid_retriever.py` (390), `test_llama_cpp_provider.py` (259), `test_local_embedding.py` (45), `test_local_llm.py` (226), `test_model_provider.py` (148), `test_models.py` (455), `test_ocr_fallback.py` (326), `test_pdf_reader.py` (202), `test_prompt_budget.py` (146), `test_upload_validation.py` (111), `test_vector_index.py` (109), `test_visual_analyzer.py` (369), `data/corpus/` (sample PDFs for ingestion tests).
- Key files: `tests/test_summarizer.py` (fast-path vs map-reduce dispatch, profile templates, `extract_page_references`, DocStore cache hit/version-mismatch/force-refresh with `MockSummarizerProvider` counting `generate_calls`), `tests/test_citation_validator.py` (perfect precision, hallucinated rank, valid abstention, abstention-with-citations, empty response, ungrounded response, `AiModel.validate_response` delegation + fallback-to-last-result), `tests/test_main_ui.py` (chat-turn `{role, content, sources, verification, snippets}` schema, summary-display `cached`/`page_references` contract), `tests/test_doc_store.py` (summary save/get roundtrip, `delete_document` cascade to `document_summaries`, `model_version` invalidation), `tests/conftest.py` (shared fixtures).

**scripts/:**
- Purpose: Manual/one-off tooling, excluded from strict lint (`pyproject.toml` per-file-ignores for `E402`).
- Contains: `scripts/benchmark_baseline.py`.
- Key files: `scripts/benchmark_baseline.py` — run manually, not part of the app or test suite.

**data/:**
- Purpose: Runtime persistence created on first run; contents are gitignored.
- Contains: `documents.db` (+ WAL/SHM sidecars) from `DocStore(Path("data/documents.db"))` (`main.py:83`); `lancedb/` LanceDB tables or `fallback_store.json` from `HybridRetriever` (`hybrid_retriever.py:27, 110`).
- Key files: None committed — directory structure only. `document_summaries` rows live inside `documents.db` (schema v3).

**.cache/:**
- Purpose: Best-effort per-document disk cache (`STORE-03`), written in `main.py:308-318`.
- Contains: `<sha256>/docling-1000-200-v1/{pages.json, chunks.json, manifest.json}` via `cache_dir_for` (`models.py:17-30`, `CONFIG_VERSION = "docling-1000-200-v1"`).
- Key files: None committed.

**docs/:**
- Purpose: Supplemental setup documentation.
- Contains: `docs/LOCAL_INFERENCE.md`.

**.planning/codebase/:**
- Purpose: GSD codebase maps consumed by plan/execute commands (this file, `ARCHITECTURE.md`, `STACK.md`, `CONVENTIONS.md`, etc.).

## Key File Locations

**Entry Points:**
- `main.py`: Sole runtime entry — `streamlit run main.py`. Tab root at `main.py:360` (`st.tabs`); chat loop `main.py:362-534`; summary loop `main.py:537-622`.
- `scripts/benchmark_baseline.py`: Manual benchmark entry.

**Configuration:**
- `pyproject.toml`: Ruff (`line-length = 120`, `target-version = "py311"`, `select = ["E","F","W"]`) + pytest (`testpaths = ["tests"]`).
- `requirements.txt`: Runtime pins incl. `lancedb>=0.17.0`, `pyarrow>=14.0.0`, `docling>=2.0.0`, `sentence-transformers==3.4.1`, `pydantic==2.11.9`.
- `requirements-test.txt`: Test-only deps.
- `.devcontainer/devcontainer.json`: Pinned Python 3.11 image, Streamlit auto-launch on port 8501.

**Core Logic:**
- `summarizer.py`: `PROFILE_SYSTEM_INSTRUCTIONS` (lines 30-104, five profiles), `MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE` (106-132), `extract_page_references` (135-149), `Summarizer` (152-418) — `_bundle_pages`, `_format_page_batch`, `_summarize_single_pass`, `_summarize_map_reduce`, `summarize_document` (cache → resolve pages → fast/map-reduce → refs → save).
- `citation_validator.py`: `CITATION_REGEX` (line 16), `CANONICAL_ABSTENTION_MARKERS` (18-32), `CitationVerificationResult` (35-49), `extract_citations` (52-65), `is_abstention` (68-78), `validate_citations` (81-181, empty → invalid; abstention; 0-citation → invalid; ≥95% precision).
- `local_llm.py`: `AiModel._detect_provider` (58-79), `ask_a_question_from_pdf_stream` (111-190) — `retrieval_result`-first branch (131-132), in-LLM fallback retrieval (140-169), `assemble_grounded_messages` + `provider.stream_text` (173-190); `validate_response` (192-210).
- `models.py`: `BBox` (33-51), `Chunk` (54-72), `Page` (75-88), `EvidenceElement` (91-113), `Document` (116-139), `EvidenceSnippet` (142-168), `RetrievalResult` + `formatted_evidence`/`source_labels` (171-205), `SummaryProfile`/`VALID_SUMMARY_PROFILES` (208-209), `SummaryResult` + `validate_ids` (212-235).
- `doc_store.py`: `SCHEMA_V3_DDL` `document_summaries` (73-94), `MIGRATIONS = {1,2,3}` (96-100), `save_summary` (425-463), `get_summary` with `model_version` invalidation (465-514), `list_summaries_for_doc` (516-555), `delete_summaries_for_doc` (557-573), `delete_document` cascade (575-588).
- `main.py`: Session-state init (54-63), `load_ai_model` (71-79), Clear All incl. `summary_*` purge (137-149), upload/index loop (159-340), `tab_chat` + single shared retrieval (450-469) + `validate_response` + badges/drawer (483-534), `tab_summary` selectbox/radio/force-refresh/generate/display (537-622).
- `hybrid_retriever.py`: `compute_rrf` (lines 31-76), `HybridRetriever` (lines 79-622) — `index_chunks`, `search_dense`, `search_fts`, `_bm25_search_fallback`, `search_hybrid` → `RetrievalResult`, legacy `search`/`get_context` facades.

**Testing:**
- `tests/test_summarizer.py`: `MockSummarizerProvider` (records `generate_calls`, deterministic text); fast-path vs map-reduce dispatch, all-five-profile templates, `extract_page_references` clamping, cache-hit zero-call, `force_refresh`, model-version mismatch regeneration.
- `tests/test_citation_validator.py`: Fixture `RetrievalResult` with ranked snippets; perfect/hallucinated/abstention/abstention-with-citations/empty/ungrounded cases; `AiModel.validate_response` explicit-arg + fallback-to-`last_retrieval_result` integration.
- `tests/test_main_ui.py`: No Streamlit runtime — pure contract tests on the `{role, content, sources, verification, snippets}` chat-turn dict and the `SummaryResult.model_dump()` display dict (`cached`, `page_references`, `model_version`).
- `tests/test_hybrid_retriever.py`: CPU pinning, anchored default path, dense indexing/search, BM25, RRF, persistence/round-trip.
- `tests/test_local_llm.py`: Stream orchestration incl. `retrieval_result` precedence and `validate_response`.
- `tests/test_models.py`: Contract validation for all Pydantic models incl. `SummaryResult`.
- `tests/conftest.py`: Shared fixtures for the suite.

## Naming Conventions

**Files:**
- `snake_case.py`, one public class/service per file: `summarizer.py` → `Summarizer` + `extract_page_references` + `PROFILE_SYSTEM_INSTRUCTIONS`/`MAP_PROMPT_TEMPLATE`/`REDUCE_PROMPT_TEMPLATE`; `citation_validator.py` → `CitationVerificationResult` + `validate_citations`/`extract_citations`/`is_abstention`; `hybrid_retriever.py` → `HybridRetriever` + `compute_rrf`; `doc_store.py` → `DocStore`; `prompt_budget.py` → module functions. Exception: `main.py` (entry, no class) and `model_provider.py` (ABC + two schemas).

**Directories:**
- Lowercase flat names: `tests/`, `scripts/`, `docs/`, `data/`, `.cache/`, `application_screenshots/`, `.devcontainer/`, `.planning/`.

**Tests:**
- Mirror pattern `test_<module>.py` → tests `tests/test_<module>.py` (e.g. `summarizer.py` → `tests/test_summarizer.py`, `citation_validator.py` → `tests/test_citation_validator.py`). UI contracts that span modules live in `tests/test_main_ui.py` (no `main_ui.py` source module — it tests `main.py` tab display shapes).

## Where to Add New Code

**New summarization behavior (profiles, budgets, stages):**
- Primary code: `summarizer.py` — new profile = entry in `PROFILE_SYSTEM_INSTRUCTIONS` + `models.py:VALID_SUMMARY_PROFILES`; new token budget = module constant next to `FAST_PATH_TOKEN_LIMIT`/`MAX_BATCH_TOKENS`; new pipeline stage = private method next to `_bundle_pages`/`_summarize_map_reduce`.
- Contracts first: extend `SummaryResult` in `models.py` before persisting new fields; add columns via a new `SCHEMA_V4_DDL` + `MIGRATIONS[4]` entry in `doc_store.py`.
- UI: wire controls in `main.py:537-622` (`profile_map`, radio, cache-key `summary_{doc_id}_{profile}`); session keys must be added to the Clear All purge (`main.py:146-148`).
- Tests: `tests/test_summarizer.py` (service), `tests/test_doc_store.py` (persistence), `tests/test_main_ui.py` (display contract).

**New QA grounding / citation behavior:**
- Primary code: `citation_validator.py` — new citation syntax = `CITATION_REGEX`; new abstention phrasing = `CANONICAL_ABSTENTION_MARKERS`; new verdict fields = `CitationVerificationResult`; threshold change = `validate_citations` `0.95` comparison.
- Prompt rules: `prompt_budget.py:SYSTEM_GROUNDING_TEMPLATE` (the `[En]` rules + abstention sentence must stay in sync with the validator or precision will collapse).
- Facade: `local_llm.py:validate_response` stays the only caller path — `main.py` must call it, never `validate_citations` directly.
- Tests: `tests/test_citation_validator.py`.

**New retrieval behavior (ranking, fusion, search mode):**
- Primary code: `hybrid_retriever.py` — add methods alongside `search_dense`/`search_fts`/`search_hybrid`; pure ranking math goes in module-level functions next to `compute_rrf`.
- Contracts first: extend `EvidenceSnippet`/`RetrievalResult` in `models.py` before wiring consumers.
- Tests: `tests/test_hybrid_retriever.py`.

**New ingestion/extraction behavior:**
- Primary code: `docling_reader.py` (structured), `pdf_reader.py` (legacy), `ocr_fallback.py` (scanned pages), `visual_analyzer.py` (visual elements); validation in `upload_validation.py`.
- Wire-up: `main.py:230-266` extraction block; persistence via `doc_store.py`.
- Tests: `tests/test_docling_reader.py`, `tests/test_ocr_fallback.py`, `tests/test_visual_analyzer.py`, `tests/test_upload_validation.py`.

**New inference provider or prompt behavior:**
- Primary code: new provider subclassing `BaseModelProvider` in `model_provider.py` next to `groq_provider.py`/`llama_cpp_provider.py`; prompt assembly in `prompt_budget.py`; delegation in `local_llm.py`. `Summarizer` consumes only `provider.generate_text` + `provider.get_capabilities` — keep new providers compatible with both streaming and non-streaming paths.
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
 │    ├── citation_validator.py ──► models.py (RetrievalResult, type-only bound)
 │    ├── hybrid_retriever.py ──► models.py, vector_index.py
 │    │    ├── models.py (Chunk, BBox, EvidenceSnippet, RetrievalResult, SummaryResult)
 │    │    └── vector_index.py (stdlib only: math, typing)
 │    ├── local_embedding.py ──► models.py, vector_index.py
 │    │    └── sentence-transformers (external, CPU-pinned)
 │    └── pdf_reader.py ──► pypdf, langchain-text-splitters (external)
 ├── summarizer.py ──► model_provider.py, models.py (Page, SummaryResult), prompt_budget.py, doc_store.py
 ├── hybrid_retriever.py (direct: dual-index writes + query)
 ├── local_embedding.py (direct: build_index + CR-01 restore)
 ├── docling_reader.py ──► models.py, pdf_reader.py (fallback)
 ├── doc_store.py ──► models.py (Chunk, Document, Page, EvidenceElement, SummaryResult)
 ├── ocr_fallback.py
 ├── visual_analyzer.py ──► doc_store.py (record_evidence_elements)
 ├── upload_validation.py (standalone)
 └── models.py (no project imports — leaf contract module)

External-only leaves: prompt_budget.py, upload_validation.py, vector_index.py
```

**Import direction (must stay acyclic):** `main.py` → `local_llm.py` / `summarizer.py` → `hybrid_retriever.py` → `local_embedding.py` → `vector_index.py`; `local_llm.py`/`summarizer.py` → `prompt_budget.py`, `model_provider.py`; `local_llm.py` → `citation_validator.py`; `summarizer.py` → `doc_store.py`, `models.py`; `docling_reader.py` → `pdf_reader.py`; everything persistence-shaped → `models.py`. `models.py`, `vector_index.py`, `prompt_budget.py`, `upload_validation.py` import no project modules; `citation_validator.py` imports only `models.py`.

## Special Directories

**data/:**
- Purpose: Runtime SQLite + LanceDB persistence (incl. `document_summaries` rows in `documents.db`).
- Generated: Yes (created on first upload/index/summarize run).
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

*Structure analysis: 2026-10-12*
