# Testing Patterns

**Analysis Date:** 2026-10-12

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt:2`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- Linter gate runs before tests in CI (see CI section)

**Assertion Library:**
- Plain `assert` + `pytest.raises(..., match=...)` + `pydantic.ValidationError` assertions. No `unittest.TestCase` classes; `unittest.mock.MagicMock` used for doubles. `numpy` used for deterministic vector construction in retrieval tests.

**Run Commands:**
```bash
pip install -r requirements.txt && pip install -r requirements-test.txt   # one-time setup (CI: .github/workflows/ci.yml)
python tests/data/corpus/generate_corpus.py                               # regenerate synthetic PDFs (CI step before pytest)
pytest tests/ -v                                                           # run full suite, 169 tests
pytest tests/test_summarizer.py -v                                         # run one file (10 tests)
pytest tests/test_citation_validator.py tests/test_main_ui.py -v           # Phase-5 QA + UI contracts (11 + 5 tests)
ruff check . && ruff format --check .                                      # lint gate (must pass before pytest in CI)
python scripts/benchmark_baseline.py                                       # baseline benchmark (not a test; writes .planning/research/BASELINE_BENCHMARK.json)
```

**Verified state (from disk):** `169 collected, 169 passed` (`pytest tests/ -q`); `ruff check .` → `All checks passed!`; `ruff format --check .` → `38 files already formatted`. Note: `05-03-SUMMARY.md:37` records `158/158` at plan-03 merge; the 11 review-fix regression tests added afterward bring the authoritative on-disk total to `169/169` per `05-REVIEW-FIX.md:52`.

## Test File Organization

**Location:**
- Separate `tests/` directory (not co-located): `tests/test_*.py` + `tests/conftest.py` + `tests/__init__.py` + `tests/data/corpus/`

**Naming:**
- `tests/test_<module>.py` mirrors root module name 1:1 (e.g. `hybrid_retriever.py` → `tests/test_hybrid_retriever.py`, `summarizer.py` → `tests/test_summarizer.py`, `citation_validator.py` → `tests/test_citation_validator.py`). Exception: `tests/test_main_ui.py` has no `main_ui.py` source module — it tests `main.py` UI contracts (serialization, drawer formatting, session purge). Test functions are `def test_<behavior>[(<aspect>)]() -> None` with a one-line docstring.

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                  # 5 shared fixtures (fake_env_groq_key, mock_groq_client,
│                                #   mock_sentence_transformer, sample_pdf_path, mock_llama_provider)
├── data/corpus/
│   ├── generate_corpus.py       # reportlab generator: 6 PDFs (see Corpus section)
│   ├── clean_digital.pdf
│   ├── dense_table.pdf
│   ├── chart_diagram.pdf
│   ├── multi_column.pdf
│   ├── scanned_sample.pdf
│   └── corrupt_invalid.pdf
├── test_citation_validator.py   # 11 tests — extraction, abstention, precision, empty, integration
├── test_doc_store.py            # 15 tests — SQLite WAL store, migrations, evidence + summary roundtrips
├── test_docling_reader.py       # 7 tests — docling fallback / mock-converter / fault isolation
├── test_hybrid_retriever.py     # 14 tests — CPU pinning, LanceDB persist, RRF, BM25, RETR-04, CR-03/WR-01/WR-05 regression
├── test_llama_cpp_provider.py   # 12 tests — httpx.MockTransport health/generate/stream/image
├── test_local_embedding.py      # 3 tests — init / build_index / get_context (mocked ST model)
├── test_local_llm.py            # 11 tests — AiModel auto-detect, fallback, streaming, self-healing, precomputed RetrievalResult
├── test_main_ui.py              # 5 tests — chat-turn schema, drawer cards, summary contract, provider attr, Clear-All purge
├── test_model_provider.py       # 12 tests — ProviderCapabilities/HealthStatus schema contract + ABC guard
├── test_models.py               # 20 tests — Chunk/Document/Page/EvidenceElement/BBox/EvidenceSnippet/RetrievalResult + cache_dir_for + tracer
├── test_ocr_fallback.py         # 8 tests — threshold gate, conditional OCR, page fault isolation
├── test_pdf_reader.py           # 9 tests — digital/table/chart/empty/corrupt/rename-stability
├── test_prompt_budget.py        # 10 tests — token heuristic, XML escaping (+case/whitespace), budget/truncation/injection
├── test_summarizer.py           # 10 tests — profiles, fast path, map-reduce, cache, None-guard, clamping, fabrication
├── test_upload_validation.py    # 8 tests — magic bytes/size/pages/hash/doc_id guards
├── test_vector_index.py         # 7 tests — metric math, guards, ranking, zero-magnitude
└── test_visual_analyzer.py      # 7 tests — detection/crop/VLM/provenance/degradation
                                 # TOTAL: 169 tests (per-file counts verified via --collect-only on disk)
```

## Suite Inventory (per-file)

| File | Count | What is covered | Key seams / doubles |
|------|-------|-----------------|---------------------|
| `tests/test_models.py` | 20 | `Chunk` legacy-key dump, frozen/hashable, `extra="forbid"` on all schemas, sha pattern rejects, JSON roundtrip, `BBox` defaults/extra-forbidden/invalid-coords, `Page`+`EvidenceElement` smoke, literal status validation, `doc_id` rejects (Document + EvidenceElement + EvidenceSnippet), `CONFIG_VERSION` + `cache_dir_for` (+ traversal reject), tracer chunk→store roundtrip (`tmp_path` + `sample_pdf_path`), backward-compat read, `EvidenceSnippet` schema/immutability (`test_evidence_snippet_schema_and_immutability`), `RetrievalResult` formatting + `source_labels` (`test_retrieval_result_formatting_and_source_labels`), `doc_id` validation + filename fallback (`test_evidence_snippet_doc_id_validation_and_filename_fallback`, WR-06/IN-01 regression) | Real `reportlab` corpus PDF for tracer; `tmp_path` SQLite |
| `tests/test_model_provider.py` | 12 | `ProviderCapabilities` valid/custom/empty-name/non-positive-window/immutability/extra-forbidden; `HealthStatus` valid/bad-literal/negative-latency/immutability; `BaseModelProvider()` direct instantiation raises `TypeError` | Pure Pydantic, no mocks |
| `tests/test_llama_cpp_provider.py` | 12 | `get_capabilities`; health `healthy`/`loading(503)`/`unreachable(ConnectError)`/`error(500)`; `generate_text` success + HTTP-error `RuntimeError`; `stream_text` multi-chunk SSE + error `RuntimeError`; `analyze_image` success + empty-bytes `ValueError` (+1 more image-path test) | `httpx.MockTransport(handler)` per test; `provider.close()` at end |
| `tests/test_local_llm.py` | 11 | `AiModel` with explicit `mock_llama_provider`; prompt assembly w/ `MagicMock` embedding; streaming yield; offline non-crash (no key, unreachable local); auto-detect healthy local; Groq fallback when local offline; Groq unconfigured health; dynamic self-healing; `close` propagation; Groq error encapsulation; **precomputed `retrieval_result` bypasses re-search** (`test_ai_model_with_precomputed_retrieval_result`, CR-02 regression) | `mock_llama_provider` fixture; `monkeypatch.setattr(LlamaCppProvider/GroqProvider, "check_health", ...)`; `monkeypatch.delenv("GROQ_API_KEY")` + `monkeypatch.setattr("streamlit.secrets", {})` |
| `tests/test_hybrid_retriever.py` | 14 | CPU pinning (`test_local_embedding_cpu_pinning`, RETR-01 — asserts `device == "cpu"` + constructor call args); anchored default path (`test_hybrid_retriever_anchored_default_path`, RETR-02); dense indexing + cosine search (`test_hybrid_retriever_dense_indexing_and_search`); disk persistence across re-instantiation (`test_hybrid_retriever_disk_persistence`, RETR-02); document deletion (`test_hybrid_retriever_document_deletion`); LanceDB-missing fallback (`test_hybrid_retriever_fallback_when_lancedb_missing` via `monkeypatch.setattr("hybrid_retriever.lancedb", None)`); RRF math + ordering (`test_rrf_scoring_math`, RETR-03 — asserts exact `1/62 + 1/61` score); keyword boost (`test_hybrid_retrieval_keyword_boost`); semantic boost (`test_hybrid_retrieval_semantic_boost`); shared `RetrievalResult` identity — `formatted_evidence()` + `source_labels()` (`test_retrieval_result_shared_identity`, RETR-04); empty-query/`k<=0` safety (`test_hybrid_retriever_empty_query_safe`); **filter-injection escaping** (`test_hybrid_retriever_filter_injection_escaping`, CR-03 — `doc_O'Reilly` + `' OR '1'='1` payloads); **fallback dedup** (`test_hybrid_retriever_fallback_deduplication`, WR-01); **lifecycle + setter** (`test_hybrid_retriever_lifecycle_and_setter`, WR-05/IN-02 — `with` block, `set_embedding_fn`, closed handles) | `tmp_path` `db_uri` per test (never real `data/lancedb/`); deterministic `_make_unit_vector(seed)` (`numpy` seeded `randn`, normalized); `monkeypatch` for `lancedb=None` legs; inline `mock_embed` topic-vector fn for semantic leg |
| `tests/test_summarizer.py` | 10 | `extract_page_references` parsing (`test_extract_page_references`); single-pass fast path (`test_summarize_document_single_pass`); all five profiles (`test_all_five_summary_profiles`); unknown profile `ValueError` (`test_unknown_profile_raises_error`); map-reduce with echo-pages mock asserting EXACT `[1, 2, 3, 4, 5]` union (`test_summarize_document_map_reduce`, WR-10); cache save→hit→`force_refresh` lifecycle (`test_summarize_document_caching_lifecycle`, `tmp_path` DocStore); **empty pages raise `ValueError`** (`test_summarize_empty_pages_raises_value_error`, WR-08); **clamped refs** (`test_extract_page_references_clamped`, WR-06); **no fabrication** (`test_no_page_citations_yields_empty_list_without_fabrication`, WR-01); **model-version invalidation** (`test_summarizer_cache_invalidates_on_model_version_change`, WR-02) | `MockSummarizerProvider` echo-pages double (parses `Pages {a} to {b}`, emits `(p. a)…(p. b)`); `tmp_path` DocStore; real `Page` models |
| `tests/test_citation_validator.py` | 11 | `extract_citations` parsing (`test_extract_citations`); `is_abstention` matrix (`test_is_abstention`); perfect precision (`test_validate_citations_perfect_precision`); hallucinated rank (`test_validate_citations_hallucinated_rank`); valid abstention (`test_validate_citations_valid_abstention`); abstention-with-citations invalid (`test_validate_citations_abstention_with_hallucinated_citations`, IN-02 message shape); **empty response invalid** (`test_validate_citations_empty_response`, CR-03 — `is_valid=False, precision=0.0`); **case-insensitive `[e1]`** (`test_extract_citations_case_insensitive`, IN-05); **benign prose guard** (`test_is_abstention_benign_prose_does_not_fire`, WR-07); ungrounded no-citation response (`test_validate_citations_ungrounded_response`); **`AiModel.validate_response` integration** (`test_ai_model_validate_response_integration`, WR-04 — explicit `RetrievalResult` + `last_verification_result` freshness) | `mock_llama_provider` fixture; real `RetrievalResult`/`EvidenceSnippet` models; no network |
| `tests/test_main_ui.py` | 5 | Chat-turn schema contract (`test_chat_turn_schema_contract`); evidence drawer card formatting (`test_evidence_drawer_card_formatting`); summary data contract + page formatting (`test_summary_data_contract_and_page_formatting`, `tmp_path`); **`AiModel.provider` attribute contract** (`test_ai_model_provider_attribute_contract`, Phase-5 CR-01 regression — guards the `._provider` typo); **Clear-All purges `summary_*` keys** (`test_clear_all_purges_summary_keys`, WR-05) | Pure contract/format asserts, no `st.AppTest`; `mock_llama_provider` for the attribute test |
| `tests/test_prompt_budget.py` | 10 | `estimate_tokens` heuristic (0/1/ceil); `sanitize_xml_boundary` escapes both tags; basic assembly (system+user, grounding directive present); empty context; short history preserved; oldest-first truncation; huge-context truncation marker; huge-prompt truncation marker; injection directive escaped inside context; **case/whitespace sanitization** (`test_sanitize_xml_boundary_case_and_whitespace`, WR-09 — `<DOCUMENT_CONTEXT>`, `<document_context >` variants) | Pure functions, no mocks |
| `tests/test_docling_reader.py` | 7 | Fallback when docling missing (`_has_docling=False` → `PdfReader`, real `clean_digital.pdf` asserts `"Fundamentals of Intelligence Systems"` + `chunk_id` prefix); mock-converter structured path (MockProv/MockTable/MockItem/MockDoc/MockConvRes, table `\|` intact, reading order); fault-isolation fallback on `convert` raise; empty-conversion fallback; (+3 extraction/record/slice asserts) | `MagicMock` converter; real corpus PDFs for fallback legs |
| `tests/test_ocr_fallback.py` | 8 | `should_ocr_page` thresholds; clean-page bypass (mocks never called); scanned page triggers OCR + `extraction=="ocr"` provenance; page-level fault isolation (renderer raises on p2 → p1 ok + p2 `failed`); no-OCR-available graceful keep; empty-image guard `("", 0.0)`; empty OCR result preserves existing chunks (WR-04); char offsets + monotonic IDs | `MagicMock` recognizer (`[[[box], text, score]], elapse` tuple shape) + `MagicMock` renderer; real `Page`/`Chunk` models |
| `tests/test_visual_analyzer.py` | 7 | Detection+cropping via mock detector/cropper; VLM analysis with `DEFAULT_VISION_PROMPT` + `source=="vlm:qwen3-vl-2b"`; graceful degradation when vision unsupported (`vision analysis unsupported` + `vlm:` source); crop-failure placeholder; empty-regions `[]`; kind fallback; bbox passthrough | `MockVisionProvider` / `MockTextOnlyProvider` (inline `BaseModelProvider` subclasses); `MagicMock` detector/cropper |
| `tests/test_doc_store.py` | 15 | Insert/get roundtrip; sha-unique semantics on reupload; page failure record; two-instance interleave (R1 Windows-lock check); `user_version` set; nullable JSON columns; restore chunks→embedding (`mock_sentence_transformer`); upsert updates size/time; full-column update on chunk conflict; evidence elements roundtrip; FK cascade deletion; summary save/get roundtrip; summary cascade deletion; summary upsert on same profile; **summary `model_version` invalidation** (`test_summary_get_with_model_version_invalidation`, WR-02). Note: `05-REVIEW-FIX.md:58` says "22 tests" but on-disk `--collect-only` reports 15 — disk count is authoritative | `tmp_path` SQLite per test (never repo-root DB); `mock_sentence_transformer` for restore leg |
| `tests/test_pdf_reader.py` | 9 | Digital extraction; chunk overlap (1000/200); `BytesIO` stream; empty/scanned yields safe empty; corrupt raises; dense-table content; chart/diagram content; page-failure isolation (`monkeypatch.setattr(page, "extract_text", broken)`); hash chunk-ID stability across rename | Real corpus PDFs; `monkeypatch` for fault injection |
| `tests/test_upload_validation.py` | 8 | `corrupt_invalid.pdf` rejected (`match="Not a valid PDF: missing %PDF header"`, WR07); valid accepts+hashes; rename yields same `doc_id`; oversize rejected (`match="File too large"`); over-page rejected via `StubReader` (`MAX_PAGES+1`); sha streaming stability; zero-page rejected via `ZeroPageReader`; `doc_id_for` invalid-sha rejected | `monkeypatch.setattr(pypdf, "PdfReader", StubReader)`; real `corrupt_invalid.pdf` |
| `tests/test_vector_index.py` | 7 | Init metric whitelist (`ValueError`); cosine math; euclidean math; `add_vector` guards (4 sequential `pytest.raises`: non-numeric vector ×2, non-dict doc, missing `content`, dim mismatch); empty-store `[]`; ranking order; zero-magnitude no-`ZeroDivisionError` | Pure stdlib math, no mocks |
| `tests/test_local_embedding.py` | 3 | Init (`mock_sentence_transformer`); `build_index` chunk count; `get_context` returns joined string | `mock_sentence_transformer` fixture (deterministic 384-d normalized float32) |

## Test Structure

**Suite Organization:**
```python
"""Unit tests for <Module> ... (RETR-0x)."""

import ...  # stdlib, then third-party, then local — same order as source
from unittest.mock import MagicMock
import numpy as np  # retrieval tests only

CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"  # only in corpus-backed files
CLEAN_PDF = CORPUS_DIR / "clean_digital.pdf"


def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:  # tests/test_hybrid_retriever.py:12-19
    """Generate a deterministic normalized float vector."""
    ...

def test_<behavior>[(<aspect>)]() -> None:
    """One-line contract statement."""
    # Arrange: real corpus path OR MagicMock double OR tmp_path DB
    # Act: single call into the unit under test
    # Assert: content + provenance + status/ID shape
```

**Patterns:**
- Single-behavior functions with docstrings; multi-case guard tests pack sequential `with pytest.raises(...)` blocks in one function instead of parametrization (`test_add_vector_guards` in `tests/test_vector_index.py`, `test_provider_capabilities_non_positive_window_rejected` in `tests/test_model_provider.py`).
- No `setUp/tearDown` classes, no class-based suites — flat functions only (inline-provider exceptions: `MockVisionProvider`/`MockTextOnlyProvider` classes inside `tests/test_visual_analyzer.py`, `MockSummarizerProvider` inside `tests/test_summarizer.py`).
- Teardown is explicit resource close where the source holds handles: `provider.close()` at the end of `LlamaCppProvider` tests; `with HybridRetriever(...)` context-manager leg in `test_hybrid_retriever_lifecycle_and_setter`; `tmp_path` auto-isolates SQLite/LanceDB; `monkeypatch` auto-undoes env/module patches.
- Echo-pages mock for map-reduce fidelity (WR-10 fix, `tests/test_summarizer.py:50-70`): the mock parses the batch page range out of each map prompt and echoes those exact pages, so the reduce test can assert the full `[1, 2, 3, 4, 5]` union is preserved. Canned identical citations per batch are forbidden.

## Mocking

**Framework:** `unittest.mock.MagicMock` + `pytest.monkeypatch` + `pytest.tmp_path` + `httpx.MockTransport` + local `Mock*Provider(BaseModelProvider)` subclasses. No `responses`, `respx`, `freezegun`, or snapshot libs.

**Patterns:**
```python
# HTTP (llama-server) — per-test MockTransport, never a real server:
def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={...})
provider = LlamaCppProvider(base_url="http://127.0.0.1:8080", transport=httpx.MockTransport(handler))

# Heavy deps — constructor-injected doubles (mirrors source's Optional-collaborator params):
engine = OcrEngine(recognizer=MagicMock(...), renderer=MagicMock(return_value=b"fake_png_image_bytes"))
analyzer = VisualAnalyzer(region_detector=MagicMock(...), cropper=MagicMock(return_value=b"fake_high_res_png_crop"))
reader = DoclingReader(CLEAN_PDF, converter=MagicMock(convert=MagicMock(return_value=MockConvRes())))
summarizer = Summarizer(provider=MockSummarizerProvider())  # echo-pages mock, never a live LLM

# LanceDB-missing leg — module-attribute patch, auto-reverted:
monkeypatch.setattr("hybrid_retriever.lancedb", None)  # or hybrid_retriever module attr (WR-01 leg)
retriever = HybridRetriever(db_uri=tmp_path / "fallback_db")
assert not retriever.is_persistent()

# Module singletons / env — monkeypatch, auto-reverted:
monkeypatch.setattr(LlamaCppProvider, "check_health", lambda self: healthy_status)
monkeypatch.delenv("GROQ_API_KEY", raising=False)
monkeypatch.setattr("streamlit.secrets", {}, raising=False)

# Embeddings — deterministic fixture (384-d, length-keyed signal, L2-normalized):
mock_sentence_transformer  # tests/conftest.py:51-81

# Retrieval vectors — seeded numpy unit vectors (no live model):
def _make_unit_vector(seed: int, dim: int = 384) -> list[float]: ...  # tests/test_hybrid_retriever.py:12-19
```

**What to Mock:**
- All network: `httpx` via `MockTransport`; Groq SDK via `mock_groq_client` (`tests/conftest.py:18-48`, canned `"This is a grounded answer."` token stream).
- All GPU/heavyweight: `SentenceTransformer` via `mock_sentence_transformer` (+ `MagicMock` class assert on `device="cpu"` in `test_local_embedding_cpu_pinning`); `RapidOCR`/`fitz` via recognizer/renderer doubles; `DocumentConverter` via `MagicMock`; VLM via `MockVisionProvider` / `mock_llama_provider` (`tests/conftest.py:91-161`); summarizer LLM via `MockSummarizerProvider` echo-pages double; LanceDB via `monkeypatch.setattr(..., None)` for the fallback leg (the LanceDB-present legs run against the real `lancedb` package into `tmp_path`).
- Environment: `GROQ_API_KEY` via `fake_env_groq_key` / `delenv`; `streamlit.secrets` via `setattr`; `pypdf.PdfReader` via `StubReader` for impossible shapes (over-page, zero-page).
- Filesystem: SQLite via `tmp_path` (one fresh `*.db` per test — never the repo-root store); LanceDB via `tmp_path / "<name>_db"` per test (never the real `data/lancedb/`).

**What NOT to Mock:**
- Pydantic validation (`ProviderCapabilities`, `HealthStatus`, `Chunk`, `Document`, `Page`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`) — always real, asserting `ValidationError` paths.
- Pure logic: `prompt_budget` token math/XML escaping/truncation, `vector_index` distance math, `upload_validation` hashing/magic-bytes, `should_ocr_page` gate, `compute_rrf` fusion math (asserts exact `round(1/62 + 1/61, 5)` in `test_rrf_scoring_math`), `extract_page_references`/`extract_citations` regex parsing.
- Real corpus PDFs for fallback/integration legs: `clean_digital.pdf` (fallback text `"Fundamentals of Intelligence Systems"`), `dense_table.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf` (rejection), `scanned_sample.pdf` (OCR path).

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def mock_sentence_transformer(monkeypatch): ...  # deterministic 384-d float32, length-keyed vec[0..1]
@pytest.fixture
def mock_groq_client(monkeypatch): ...           # canned 5-token stream via MockChunk/MockChoice/MockDelta
@pytest.fixture
def mock_llama_provider(): ...                   # healthy MockLlamaCppProvider (records stream_calls)
@pytest.fixture
def fake_env_groq_key(monkeypatch): ...          # GROQ_API_KEY=test-key-not-a-secret-mock-value
@pytest.fixture
def sample_pdf_path(): ...                       # tests/data/corpus/clean_digital.pdf
# pytest builtin: tmp_path (fresh SQLite/LanceDB per test), monkeypatch (auto-revert)
```

**Location:**
- Shared: `tests/conftest.py` (5 fixtures, header comment `Allows 100% offline unit testing without GPU allocation or API calls`).
- Local: inline `MockProv`/`MockTable`/`MockItem`/`MockDoc`/`MockConvRes` docling doubles (`tests/test_docling_reader.py`); `StubReader`/`ZeroPageReader` (`tests/test_upload_validation.py`); `MockVisionProvider`/`MockTextOnlyProvider` (`tests/test_visual_analyzer.py`); `MockSummarizerProvider` echo-pages double (`tests/test_summarizer.py:50-70`); `_make_unit_vector(seed)` + inline `mock_embed(text)` topic-vector fn (`tests/test_hybrid_retriever.py:12-19, 237-240`).

## Corpus

**Generator:** `tests/data/corpus/generate_corpus.py` (`reportlab`-based, `reportlab>=4.2.0` in `requirements-test.txt:3`). CI regenerates before pytest (`.github/workflows/ci.yml`). Six files:

| PDF | Purpose | Consumed by |
|-----|---------|-------------|
| `clean_digital.pdf` | Multi-page digital text w/ `"Fundamentals of Intelligence Systems"` marker | docling fallback, pdf_reader, models tracer, benchmark, `sample_pdf_path` |
| `dense_table.pdf` | Tabular content | pdf_reader table leg, docling table-order leg |
| `chart_diagram.pdf` | Vector/raster visuals | pdf_reader chart leg, visual analyzer manual path |
| `multi_column.pdf` | Complex reading order | docling order regression |
| `scanned_sample.pdf` | Image-only pages (low text) | OCR conditional path |
| `corrupt_invalid.pdf` | Non-`%PDF` bytes | upload-validation WR07 rejection, pdf_reader corrupt leg |

## Benchmark

**Script:** `scripts/benchmark_baseline.py` — NOT part of pytest. Measures pypdf extraction latency, chunk counts, CPU embedding time, in-memory linear-search latency, RSS deltas via `psutil>=6.1.0` (`requirements-test.txt:5`). Output: `.planning/research/BASELINE_BENCHMARK.json`. Run with `python scripts/benchmark_baseline.py` after generating the corpus. Ruff `E402` is waived for `scripts/*` (`pyproject.toml:9-10`) because the script inserts `REPO_ROOT` into `sys.path`.

## CI

**Pipeline:** `.github/workflows/ci.yml` — job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggers on `push`/`pull_request` to `main`:
1. `actions/checkout@v4` → 2. `actions/setup-python@v5` (`python-version: "3.11"`, `cache: "pip"`) → 3. `pip install -r requirements.txt` + `pip install -r requirements-test.txt` → 4. `ruff check .` + `ruff format --check .` (lint gate — tests do not run if this fails) → 5. `python tests/data/corpus/generate_corpus.py` → 6. `pytest tests/ -v`.
- Phase-05 fix report records the gate state at merge: `169 passed, ruff_check: 0 errors, ruff_format: clean (38 files)` (`.planning/phases/05-grounded-summarization-and-qa/05-REVIEW-FIX.md:50-67`), matching disk (`169 collected, 169 passed`; `38 files already formatted`).

## Coverage

**Requirements:** No percentage gate, no `coveragerc`, no `--cov` flag in CI. Effective bar is behavioral: every review finding ships with a regression test (CR/WR/IN IDs in `05-REVIEW-FIX.md`), and the fix report records full-suite green.

**View Coverage:**
```bash
# No coverage tooling configured; nearest equivalents:
pytest tests/ -v --tb=short          # per-test pass/fail with short tracebacks
pytest tests/ --collect-only -q      # per-file counts (authoritative inventory source)
ruff check . && ruff format --check .  # lint gate (CI step 4)
```

## Test Types

**Unit Tests:**
- Scope: all 169 tests are offline unit tests. Convention: one behavior per function, real models + mocked boundaries (see inventory table). Health probes, token math, validation guards, chunk-ID shapes, RRF math, `search_mode` derivation, page-reference clamping, citation precision/abstention matrices, summary cache lifecycle, and provenance tags are asserted directly.

**Integration Tests:**
- Corpus-backed legs (not a separate directory): docling→`PdfReader` fallback on real PDFs, OCR conditional path on `scanned_sample.pdf`, chunk→`DocStore`→embedding restore (`test_restore_chunks_to_embedding_from_doc_store`, `test_tracer_chunk_to_store_roundtrip`), `AiModel` auto-detect/fallback across both providers, `HybridRetriever` dense-index→search→delete→persistence roundtrips against real `lancedb` into `tmp_path`, `Summarizer`→`DocStore` cache roundtrips (`test_summarize_document_caching_lifecycle`, `test_summary_save_and_get_roundtrip`), `AiModel.validate_response` end-to-end against a real `RetrievalResult` (`test_ai_model_validate_response_integration`). All still offline (mocked HTTP/GPU, real files/SQLite-tmp/LanceDB-tmp).

**E2E Tests:**
- Not used. No Playwright/Selenium, no live `llama-server`, no Groq API calls, no Streamlit AppTest (`st.AppTest` absent). Browser/GPU paths are covered only by mocks + `main.py` manual verification.

## Common Patterns

**Async Testing:**
- Not applicable — the codebase is fully synchronous (generators + blocking `httpx.Client`, no `asyncio`). Streaming is tested by materializing the generator: `tokens = list(provider.stream_text(...))` then asserting joined content and call recording (`stream_calls` in `tests/conftest.py:141-150`).

**Error Testing:**
```python
with pytest.raises(ValidationError):                      # Pydantic contract (models, provider schemas, EvidenceSnippet doc_id)
    ProviderCapabilities(model_name="", context_window=0)
with pytest.raises(ValueError, match="..."):              # fail-fast guards (upload, bbox, image_bytes, metric, index_chunks mismatch)
    validate_pdf_bytes(raw, filename)
with pytest.raises(ValueError, match="Unknown summary profile"):  # summarizer profile gate
    summarizer.summarize_document(doc_id, sha, pages, profile="brief")
with pytest.raises(ValueError, match="No extractable text"):      # empty-document guard (WR-08)
    summarizer.summarize_document(doc_id, sha, pages=[])
with pytest.raises(RuntimeError, match="llama-server streaming failed"):  # wrapped httpx.HTTPError
    list(provider.stream_text("hi"))
with pytest.raises(TypeError):                            # ABC + DocStore + index_chunks type guards
    BaseModelProvider()
with pytest.raises(NotImplementedError):                  # unsupported capability made explicit
    GroqProvider(...).analyze_image(b"...", "...")
# Health-path anti-pattern to preserve: check_health() NEVER raises — assert the Status literal instead:
assert provider.check_health().status == "unreachable"
# Retrieval-path anti-pattern to preserve: empty/degenerate queries return typed empties, never raise:
assert retriever.search_hybrid("", k=5).snippets == []
assert retriever.search_dense(vec, k=0) == []
# Citation-path anti-patterns to preserve: empty responses and ungrounded claims are INVALID, never valid:
assert validate_citations("", rr).is_valid is False                    # CR-03
assert validate_citations("It is great.", rr).is_valid is False        # ungrounded
assert validate_citations("Abstain ... insufficient evidence ...", rr).is_valid is True  # QA-04
```

## Gaps

Per `05-REVIEW.md` (verdict `NEEDS FIXES`, 3 Critical + 10 Warnings + 5 Info) and `05-REVIEW-FIX.md` (all 18 findings resolved/documented, `169/169 passed`):

- **E2E / live-server coverage missing (noted, not planned):** no test boots a real `llama-server`, hits Groq, or drives `main.py` via `st.AppTest`. The suite deliberately stops at `httpx.MockTransport` + provider doubles. Phase 5 narrowed this slightly (`test_ai_model_provider_attribute_contract` guards the CR-01 `._provider` typo; `test_clear_all_purges_summary_keys` guards WR-05), but `test_main_ui.py` still asserts string formatting, never real Streamlit widgets — tab isolation, drawer rendering, and badge logic remain manual-only (WR-10, partially addressed). Priority: Medium.
- **Upload-loop path still thin:** Phase-5 CR-01 (AttributeError aborting every new-PDF ingest, invisible to the suite) was fixed by one line + an attribute-contract test, but no test exercises `main.py`'s upload loop end-to-end (`05-REVIEW.md:78`). A future ingestion outage of the same class would again hide behind green tests. Priority: Medium.
- **GPU/VRAM envelope unverified in tests:** 4 GB ceiling and GGUF quant behavior are manual artifacts, not CI assertions. `test_local_embedding_cpu_pinning` guards the CPU side (constructor called with `device="cpu"`), and map-reduce runs sequentially by code inspection (QUAL-01), but nothing asserts VRAM consumption or inference latency. `scripts/benchmark_baseline.py` numbers are manual artifacts (`.planning/research/BASELINE_BENCHMARK.json`), not CI assertions. Risk: perf regressions merge silently. Priority: Medium.
- **Real-OCR accuracy unasserted:** `tests/test_ocr_fallback.py` proves gating/provenance/isolation with mocked recognizers, never `RapidOCR` word accuracy on `scanned_sample.pdf`. Risk: low-text pages index poorly without a failing test. Priority: Low (CPU cost keeps it out of CI by design).
- **Real-VLM output unasserted:** `tests/test_visual_analyzer.py` proves `source="vlm:<model>"` separation and degradation branches with `MockVisionProvider`; no test checks Qwen3-VL description quality. Risk: hallucinated chart readings pass CI. Priority: Low (accepted — VIS-03 provenance tagging is the mitigation under test).
- **Real-LanceDB failure modes thin:** the LanceDB-present legs run against a working local `lancedb` into `tmp_path`; native Tantivy FTS availability, `merge_insert` vs delete-then-add version skew, and Windows file-lock contention on `data/lancedb/` have no dedicated tests — the BM25-from-table fallback (WR-02 leg) and `logger.warning` degradations are exercised only via mocks. Risk: production LanceDB upgrade changes behavior silently. Priority: Low-Medium.
- **Summary quality unasserted (new, Phase 5):** `tests/test_summarizer.py` proves routing, caching, clamping, and citation preservation via the echo-pages mock — never summary coherence, faithfulness, or profile distinctness against a real model. The echo mock asserts the union `[1, 2, 3, 4, 5]` survives, but a fluent-sounding hallucinated summary with intact `(p. X)` tags would pass. Priority: Low-Medium (accepted — LLM-as-judge is out of CI scope by design).
- **Abstention matcher still heuristic (known residual):** WR-07 tightened `CANONICAL_ABSTENTION_MARKERS` to full phrases + added the benign-prose negative test, but substring matching can still over/under-fire on paraphrased abstentions. Priority: Low.
- **Concurrency / Windows-lock coverage thin:** one interleave test (`test_two_instance_interleave_R1`, `tmp_path`) stands in for Streamlit rerun + multi-session SQLite contention; no equivalent multi-instance test exists for `HybridRetriever` fallback JSON persistence or concurrent summary upserts on the same `(sha256, profile)` row. Risk: `fallback_store.json` torn writes under rapid re-upload churn. Priority: Low.
- **No coverage gate:** percentage target is `Not enforced`; confidence rests on the 169-test behavioral inventory + lint gate. If a gate is ever added, start at the provider + ingestion + retrieval + summarization seams (`llama_cpp_provider.py`, `prompt_budget.py`, `ocr_fallback.py`, `visual_analyzer.py`, `hybrid_retriever.py`, `summarizer.py`, `citation_validator.py`) where the CR/WR fixes cluster.

---

*Testing analysis: 2026-10-12*
