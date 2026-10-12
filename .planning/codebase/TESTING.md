# Testing Patterns

**Analysis Date:** 2026-10-12

## Test Framework

**Runner:**
- pytest `>=8.3.0` (`requirements-test.txt:2`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml:13-20` — `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `python_functions = ["test_*"]`, `filterwarnings = ["ignore::UserWarning", "ignore::DeprecationWarning"]`
- Linter gate runs before tests in CI (see CI section)

**Assertion Library:**
- Plain `assert` + `pytest.raises(..., match=...)` + `pydantic.ValidationError` assertions. No `unittest.TestCase` classes; `unittest.mock.MagicMock`/`patch` used for doubles. `numpy` used for deterministic vector construction in retrieval tests. `threading.Event`/`Thread` used for gate-contention choreography.

**Run Commands:**
```bash
pip install -r requirements.txt && pip install -r requirements-test.txt   # one-time setup (CI: .github/workflows/ci.yml)
python tests/data/corpus/generate_corpus.py                               # regenerate synthetic PDFs (CI step before pytest)
pytest tests/ -v                                                           # run full suite, 193 tests
pytest tests/test_summarizer.py -v                                         # run one file (10 tests)
pytest tests/test_citation_validator.py tests/test_main_ui.py -v           # Phase-5 QA + UI contracts (11 + 5 tests)
pytest tests/test_resource_telemetry.py tests/test_concurrency_lock.py tests/test_cache_invalidation.py -v  # Phase-6 suites (10 + 8 + 6 tests)
ruff check . && ruff format --check .                                      # lint gate (must pass before pytest in CI)
python scripts/benchmark_baseline.py                                       # baseline benchmark (not a test; writes .planning/research/BASELINE_BENCHMARK.json)
python scripts/profile_resources.py                                        # Phase-6 profiler (not a test; writes .planning/research/RESOURCE_PROFILE.json)
```

**Verified state (from disk):** `193 passed in 23.90s` (`pytest tests/ -q`); per-file `--collect-only` counts sum to 193 (see inventory); `ruff check .` → `All checks passed!`; `ruff format --check .` → `43 files already formatted`. Note: `06-02-SUMMARY.md:47` records `192/192` at plan-02 merge; the review-fix regression test `test_unauthorized_release_does_not_corrupt_active_counter` (CR-01/IN-01) brings the authoritative on-disk total to `193/193` per `06-REVIEW-FIX.md:40`.

## Test File Organization

**Location:**
- Separate `tests/` directory (not co-located): `tests/test_*.py` + `tests/conftest.py` + `tests/__init__.py` + `tests/data/corpus/`

**Naming:**
- `tests/test_<module>.py` mirrors root module name 1:1 (e.g. `hybrid_retriever.py` → `tests/test_hybrid_retriever.py`, `summarizer.py` → `tests/test_summarizer.py`, `citation_validator.py` → `tests/test_citation_validator.py`, `resource_telemetry.py` → `tests/test_resource_telemetry.py`). Exceptions: `tests/test_main_ui.py` has no `main_ui.py` source module — it tests `main.py` UI contracts; `tests/test_concurrency_lock.py` covers `InferenceGate` in `local_llm.py` (+ guarded `generate_text`/`summarize_document` legs); `tests/test_cache_invalidation.py` covers `bound_chat_history` (`prompt_budget.py`) + `DocStore.count_*` + tiered invalidation + telemetry contracts. Test functions are `def test_<behavior>[(<aspect>)]() -> None` with a one-line docstring.

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
├── test_cache_invalidation.py   # 6 tests — bound_chat_history, count_*, tier-1/3/4, telemetry contracts
├── test_citation_validator.py   # 11 tests — extraction, abstention, precision, empty, integration
├── test_concurrency_lock.py     # 8 tests — InferenceGate acquire/release/reentrancy/rogue-release/blocking/timeout/guards
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
├── test_resource_telemetry.py   # 10 tests — nvidia-smi parse/degrade, psutil live/fallback, LatencyTracker, snapshot
├── test_summarizer.py           # 10 tests — profiles, fast path, map-reduce, cache, None-guard, clamping, fabrication
├── test_upload_validation.py    # 8 tests — magic bytes/size/pages/hash/doc_id guards
├── test_vector_index.py         # 7 tests — metric math, guards, ranking, zero-magnitude
└── test_visual_analyzer.py      # 7 tests — detection/crop/VLM/provenance/degradation
                                 # TOTAL: 193 tests (per-file counts verified via --collect-only on disk)
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
| `tests/test_resource_telemetry.py` | 10 | `nvidia-smi` success parse (`test_get_gpu_memory_info_success` — `"4096, 1024, 3072"` → 25.0% util); empty/malformed → `None` (`test_get_gpu_memory_info_empty_or_malformed`); `FileNotFoundError`/`CalledProcessError`/`TimeoutExpired` → `None` (`test_get_gpu_memory_info_subprocess_failures`); live `psutil` RSS/VMS keys (`test_get_process_memory_info_live`); `psutil.Process` raise → zero-dict (`test_get_process_memory_info_fallback_on_error`); `LatencyTracker` success timing + `to_dict` + history write (`test_latency_tracker_success`, loose `>= 15.0` ms bound); exception capture (`test_latency_tracker_exception` — `success=False`, `error` str, history still written); `track_stage` convenience (`test_track_stage_context_manager`); manual record/get/clear (`test_record_and_get_latency_history`); snapshot aggregation `count`/`avg`/`min`/`max` (`test_get_system_telemetry_snapshot` — 100+200 → avg 150.0) | `patch("subprocess.run", ...)` + `patch("psutil.Process", ...)`; autouse `reset_latencies` fixture (`clear_latency_history` before+after each test); real `time.sleep` for timing legs only |
| `tests/test_concurrency_lock.py` | 8 | Basic acquire/release (`test_inference_gate_basic_acquire_release`); same-thread reentrancy (`test_inference_gate_reentrancy_in_same_thread`); **rogue-release safety** (`test_unauthorized_release_does_not_corrupt_active_counter`, Phase-6 CR-01/IN-01 — foreign-thread `release()` must not unlock the gate); parallel-thread blocking with 0.05 s timeout (`test_inference_gate_blocks_parallel_threads`); `hold()` `TimeoutError` (`test_inference_gate_hold_raises_timeout_error`, `match="InferenceGate acquisition timed out"`); `AiModel.generate_text` spy-guard (`test_ai_model_generate_text_guarded` — `gate_was_locked == [True]` + post-call release); streaming busy-warning token (`test_ai_model_streaming_busy_yields_warning` — `acquire → False` patch yields 1 busy token); summarizer gate spy-guard (`test_summarizer_guarded_by_inference_gate`) | `DummyProvider` (`BaseModelProvider` subclass, `tests/test_concurrency_lock.py:13-58`); autouse `ensure_gate_released` fixture (drains gate before+after each test); `threading.Event`/`Thread.join(timeout=...)` choreography; `monkeypatch.setattr(InferenceGate, "acquire", ...)` for busy leg |
| `tests/test_cache_invalidation.py` | 6 | `bound_chat_history` capacity + orphan-assistant pruning + empty (`test_chat_history_bounding_drops_oldest_turns`, Phase-6 WR-02/WR-03 — tests the real `prompt_budget.bound_chat_history`, asserts `MAX_CHAT_TURNS == 50`, first turn is `user`, 75-turn history pruned to ≤ 50); `DocStore.count_documents/count_summaries` (`test_doc_store_count_helpers`); Tier-1 session purge incl. `summary_*` keys (`test_tier_1_session_purge`); Tier-3 SQLite version invalidation — hit on match, `None` on `model_version` mismatch (`test_tier_3_sqlite_summary_version_invalidation`); Tier-4 LanceDB deletion sync via `contains_document` alias (`test_tier_4_lancedb_document_deletion_sync`); sidebar telemetry key contracts (`test_sidebar_telemetry_contracts` — `used_mb`/`total_mb`/`utilization_pct` when GPU present, `rss_mb >= 0.0` always) | Real `prompt_budget.bound_chat_history` (WR-03 fidelity fix — no inline slice); `tempfile.TemporaryDirectory()` SQLite/LanceDB per test; real `get_gpu_memory_info`/`get_process_memory_info` (graceful-degradation asserts, no mocks) |
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
"""Unit tests for <Module> ... (RETR-0x / QUAL-01)."""

import ...  # stdlib, then third-party, then local — same order as source
from unittest.mock import MagicMock, patch
import threading
import time
import numpy as np  # retrieval tests only

CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"  # only in corpus-backed files
CLEAN_PDF = CORPUS_DIR / "clean_digital.pdf"


@pytest.fixture(autouse=True)
def reset_latencies(): ...       # tests/test_resource_telemetry.py:22-27 — clear_latency_history before+after
@pytest.fixture(autouse=True)
def ensure_gate_released(): ...  # tests/test_concurrency_lock.py:61-68 — drain InferenceGate before+after

def _make_unit_vector(seed: int, dim: int = 384) -> list[float]:  # tests/test_hybrid_retriever.py:12-19
    """Generate a deterministic normalized float vector."""
    ...

def test_<behavior>[(<aspect>)]() -> None:
    """One-line contract statement."""
    # Arrange: real corpus path OR MagicMock double OR tmp_path DB OR patch(subprocess/psutil)
    # Act: single call into the unit under test
    # Assert: content + provenance + status/ID shape
```

**Patterns:**
- Single-behavior functions with docstrings; multi-case guard tests pack sequential `with pytest.raises(...)` blocks in one function instead of parametrization (`test_add_vector_guards` in `tests/test_vector_index.py`, `test_provider_capabilities_non_positive_window_rejected` in `tests/test_model_provider.py`, `test_get_gpu_memory_info_empty_or_malformed` / `test_get_gpu_memory_info_subprocess_failures` in `tests/test_resource_telemetry.py`).
- No `setUp/tearDown` classes, no class-based suites — flat functions only (inline-provider exceptions: `MockVisionProvider`/`MockTextOnlyProvider` classes inside `tests/test_visual_analyzer.py`, `MockSummarizerProvider` inside `tests/test_summarizer.py`, `DummyProvider` inside `tests/test_concurrency_lock.py:13-58`).
- Global-state hygiene is fixture-enforced: `reset_latencies` (telemetry) and `ensure_gate_released` (gate) are both `autouse` and both clean before AND after each test. Any new test touching `_LATENCY_HISTORY` or `InferenceGate` MUST rely on these fixtures, never manual cleanup.
- Teardown is explicit resource close where the source holds handles: `provider.close()` at the end of `LlamaCppProvider` tests; `with HybridRetriever(...)` context-manager leg in `test_hybrid_retriever_lifecycle_and_setter`; `tmp_path`/`TemporaryDirectory` auto-isolates SQLite/LanceDB; `monkeypatch`/`patch` auto-undoes env/module patches; `Thread.join(timeout=...)` + `Event.set()` choreography in gate-blocking tests (`tests/test_concurrency_lock.py:114-165`).
- Echo-pages mock for map-reduce fidelity (WR-10 fix, `tests/test_summarizer.py:50-70`): the mock parses the batch page range out of each map prompt and echoes those exact pages, so the reduce test can assert the full `[1, 2, 3, 4, 5]` union is preserved. Canned identical citations per batch are forbidden.
- Spy-generate pattern for gate guards (Phase 6): wrap `provider.generate_text` to capture `InferenceGate.is_locked()` at call time, assert `gate_was_locked == [True]`, then assert post-call release (`tests/test_concurrency_lock.py:168-225`). Busy-path pattern: patch `InferenceGate.acquire → False` and assert the single busy-warning token.

## Mocking

**Framework:** `unittest.mock.MagicMock` + `unittest.mock.patch` + `pytest.monkeypatch` + `pytest.tmp_path` + `httpx.MockTransport` + local `Mock*Provider(BaseModelProvider)` subclasses. No `responses`, `respx`, `freezegun`, or snapshot libs.

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

# nvidia-smi / psutil — patch the boundary, assert graceful degradation:
with patch("subprocess.run", return_value=mock_res): ...           # canned "4096, 1024, 3072\n"
with patch("subprocess.run", side_effect=FileNotFoundError): ...   # → None
with patch("psutil.Process", side_effect=RuntimeError(...)): ...   # → zero-dict

# Gate contention — patch acquire or choreograph real threads:
monkeypatch.setattr(InferenceGate, "acquire", MagicMock(return_value=False))  # busy leg
t1_started = threading.Event(); t1_finish = threading.Event()                 # blocking leg

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

# Latencies — canned values, never wall-clock (except loose lower bounds):
record_stage_latency("map_stage", 100.0)  # tests/test_resource_telemetry.py:150-165
```

**What to Mock:**
- All network: `httpx` via `MockTransport`; Groq SDK via `mock_groq_client` (`tests/conftest.py:18-48`, canned `"This is a grounded answer."` token stream).
- All GPU/heavyweight: `SentenceTransformer` via `mock_sentence_transformer` (+ `MagicMock` class assert on `device="cpu"` in `test_local_embedding_cpu_pinning`); `RapidOCR`/`fitz` via recognizer/renderer doubles; `DocumentConverter` via `MagicMock`; VLM via `MockVisionProvider` / `mock_llama_provider` (`tests/conftest.py:91-161`); summarizer LLM via `MockSummarizerProvider` echo-pages double; gate legs via `DummyProvider` (`tests/test_concurrency_lock.py`); profiler LLM via `BenchmarkProvider` (`scripts/profile_resources.py`, never in pytest); LanceDB via `monkeypatch.setattr(..., None)` for the fallback leg (the LanceDB-present legs run against the real `lancedb` package into `tmp_path`).
- OS/hardware boundaries: `nvidia-smi` via `patch("subprocess.run", ...)`; `psutil.Process` via `patch(...)` for the error leg (the live leg calls the real `psutil` and asserts `>= 0.0`).
- Environment: `GROQ_API_KEY` via `fake_env_groq_key` / `delenv`; `streamlit.secrets` via `setattr`; `pypdf.PdfReader` via `StubReader` for impossible shapes (over-page, zero-page).
- Filesystem: SQLite via `tmp_path`/`TemporaryDirectory` (one fresh `*.db` per test — never the repo-root store); LanceDB via `tmp_path / "<name>_db"` per test (never the real `data/lancedb/`).

**What NOT to Mock:**
- Pydantic validation (`ProviderCapabilities`, `HealthStatus`, `Chunk`, `Document`, `Page`, `EvidenceElement`, `EvidenceSnippet`, `RetrievalResult`, `SummaryResult`, `CitationVerificationResult`) — always real, asserting `ValidationError` paths.
- Pure logic: `prompt_budget` token math/XML escaping/truncation/`bound_chat_history` (WR-03 fidelity fix — `tests/test_cache_invalidation.py` imports the real function), `vector_index` distance math, `upload_validation` hashing/magic-bytes, `should_ocr_page` gate, `compute_rrf` fusion math (asserts exact `round(1/62 + 1/61, 5)` in `test_rrf_scoring_math`), `extract_page_references`/`extract_citations` regex parsing, `LatencyTracker` arithmetic + snapshot aggregation (canned `record_stage_latency` values assert exact `avg 150.0`).
- Real corpus PDFs for fallback/integration legs: `clean_digital.pdf` (fallback text `"Fundamentals of Intelligence Systems"`), `dense_table.pdf`, `chart_diagram.pdf`, `corrupt_invalid.pdf` (rejection), `scanned_sample.pdf` (OCR path).
- Gate state machine internals: blocking/timeout/reentrancy/rogue-release tests drive the REAL `InferenceGate` with real threads — only the busy leg patches `acquire`.

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
@pytest.fixture(autouse=True)
def reset_latencies(): ...                        # tests/test_resource_telemetry.py:22-27 — latency isolation
@pytest.fixture(autouse=True)
def ensure_gate_released(): ...                   # tests/test_concurrency_lock.py:61-68 — gate isolation
# pytest builtin: tmp_path (fresh SQLite/LanceDB per test), monkeypatch (auto-revert)
```

**Location:**
- Shared: `tests/conftest.py` (5 fixtures, header comment `Allows 100% offline unit testing without GPU allocation or API calls`).
- Local: inline `MockProv`/`MockTable`/`MockItem`/`MockDoc`/`MockConvRes` docling doubles (`tests/test_docling_reader.py`); `StubReader`/`ZeroPageReader` (`tests/test_upload_validation.py`); `MockVisionProvider`/`MockTextOnlyProvider` (`tests/test_visual_analyzer.py`); `MockSummarizerProvider` echo-pages double (`tests/test_summarizer.py:50-70`); `DummyProvider` (`tests/test_concurrency_lock.py:13-58`); `_make_unit_vector(seed)` + inline `mock_embed(text)` topic-vector fn (`tests/test_hybrid_retriever.py:12-19, 237-240`); `reset_latencies` (`tests/test_resource_telemetry.py:22-27`); `ensure_gate_released` (`tests/test_concurrency_lock.py:61-68`).

## Corpus

**Generator:** `tests/data/corpus/generate_corpus.py` (`reportlab`-based, `reportlab>=4.2.0` in `requirements-test.txt:3`). CI regenerates before pytest (`.github/workflows/ci.yml:35-37`). Six files:

| PDF | Purpose | Consumed by |
|-----|---------|-------------|
| `clean_digital.pdf` | Multi-page digital text w/ `"Fundamentals of Intelligence Systems"` marker | docling fallback, pdf_reader, models tracer, benchmark, profiler stages 1–2, `sample_pdf_path` |
| `dense_table.pdf` | Tabular content | pdf_reader table leg, docling table-order leg, profiler ingestion leg |
| `chart_diagram.pdf` | Vector/raster visuals | pdf_reader chart leg, visual analyzer manual path |
| `multi_column.pdf` | Complex reading order | docling order regression, profiler ingestion leg |
| `scanned_sample.pdf` | Image-only pages (low text) | OCR conditional path |
| `corrupt_invalid.pdf` | Non-`%PDF` bytes | upload-validation WR07 rejection, pdf_reader corrupt leg |

## Benchmark + Profiling Harnesses

**Baseline script:** `scripts/benchmark_baseline.py` — NOT part of pytest. Measures pypdf extraction latency, chunk counts, CPU embedding time, in-memory linear-search latency, RSS deltas via `psutil>=6.1.0` (`requirements-test.txt:5`). Output: `.planning/research/BASELINE_BENCHMARK.json` (present on disk). Run with `python scripts/benchmark_baseline.py` after generating the corpus. Ruff `E402` is waived for `scripts/*` (`pyproject.toml:9-10`) because scripts insert `REPO_ROOT` into `sys.path`.

**Profiler harness (Phase 6 QUAL-01):** `scripts/profile_resources.py` (`run_resource_profile()`, `if __name__ == "__main__"` entry at `:341-342`) — NOT part of pytest. Six sequential stages against `tempfile.mkdtemp(prefix="rag_benchmark_")` (always removed in `finally`, `:337-338`):
1. Hardware baseline — `get_process_memory_info()` + `get_gpu_memory_info()` (`:117-127`).
2. Ingestion latency — `PdfReader` + `get_paragraphs()` per corpus file under `LatencyTracker(f"extract_{file_name}")`, records pages/chars/chunks/ms-per-page (`:129-160`).
3. CPU embeddings — `LocalEmbedding()._embed_one` over 10 chunks under `LatencyTracker("cpu_embeddings_10_chunks")` (`:161-173`).
4. Hybrid retrieval — `HybridRetriever(db_uri=<tmp>/lancedb)` index + 1 cold + 2 warm `search_hybrid` queries under per-stage trackers (`:175-194`).
5. Summary cache SLA — `DocStore` + `Summarizer(BenchmarkProvider)` cold vs warm `summarize_document`, asserts `warm.cached is True` and `warm_ms < 50.0` (`:196-247`).
6. Gate safety + VRAM audit — `InferenceGate.hold` acquire/release cycle, then projected-peak VRAM math (DWM overhead + 1450.0 weights + 450.0 mmproj + 510.0 KV-cache + 350.0 CUDA scratch vs 3800.0 MB target, headroom vs 4096 MB) with the `487.0` MB empirical Win11 DWM fallback in headless/CI (IN-02 documented at `:268-269`) (`:249-287`).
- Output: `.planning/research/RESOURCE_PROFILE.json` (present on disk) with `timestamp`, `target_gpu`, `projected_peak_vram_mb`, `vram_headroom_mb`, `compliant_with_qual_01`, `hardware_live`, `ingestion`, `embeddings`, `retrieval`, `summarization` (`cache_sla_met`), `concurrency_lock` (`:289-327`). Per `06-REVIEW-FIX.md:46`: peak projected 3,445 MB (≤ 3,800 target) and warm summary cache hit 5.4 ms (< 50 ms SLA).
- Doubles: `BenchmarkProvider(BaseModelProvider)` with 20 ms `generate_text` sleep + canned `(p. 1)`/`(p. 2)` summary (`scripts/profile_resources.py:39-91`); dummy `[[0.05 * (i % 10)]] * 384` index vectors (`:180`). Never import `BenchmarkProvider` in pytest — it lives in the harness only.

## CI

**Pipeline:** `.github/workflows/ci.yml` — job `Lint & Test Suite (Python 3.11)` on `ubuntu-latest`, triggers on `push`/`pull_request` to `main`:
1. `actions/checkout@v4` → 2. `actions/setup-python@v5` (`python-version: "3.11"`, `cache: "pip"`) → 3. `pip install -r requirements.txt` + `pip install -r requirements-test.txt` → 4. `ruff check .` + `ruff format --check .` (lint gate — tests do not run if this fails) → 5. `python tests/data/corpus/generate_corpus.py` → 6. `pytest tests/ -v`.
- Phase-06 fix report records the gate state at merge: `193 passed, ruff_check: 0 errors, ruff_format: clean (43 files)` (`.planning/phases/06-performance-optimization-and-resource-profiling/06-REVIEW-FIX.md:40-51`), matching disk (`193 passed`; `43 files already formatted`).
- Note: CI runs on `ubuntu-latest` (no NVIDIA GPU) — `get_gpu_memory_info()` returns `None` there by design, so `test_sidebar_telemetry_contracts` guards the GPU asserts behind `if gpu is not None`, and the profiler falls back to the `487.0` MB DWM estimate. Gate-blocking tests use short timeouts (0.05 s) so they stay fast on shared runners.

## Coverage

**Requirements:** No percentage gate, no `coveragerc`, no `--cov` flag in CI. Effective bar is behavioral: every review finding ships with a regression test (CR/WR/IN IDs in `05-REVIEW-FIX.md` and `06-REVIEW-FIX.md`), and the fix reports record full-suite green.

**View Coverage:**
```bash
# No coverage tooling configured; nearest equivalents:
pytest tests/ -v --tb=short          # per-test pass/fail with short tracebacks
pytest tests/ --collect-only -q      # per-file counts (authoritative inventory source)
ruff check . && ruff format --check .  # lint gate (CI step 4)
python scripts/profile_resources.py  # QUAL-01 profiler (writes .planning/research/RESOURCE_PROFILE.json)
```

## Test Types

**Unit Tests:**
- Scope: all 193 tests are offline unit tests. Convention: one behavior per function, real models + mocked boundaries (see inventory table). Health probes, token math, validation guards, chunk-ID shapes, RRF math, `search_mode` derivation, page-reference clamping, citation precision/abstention matrices, summary cache lifecycle, gate acquire/release/reentrancy/timeout/rogue-release, telemetry parse/degrade/timing/aggregation, `bound_chat_history` capacity + orphan pruning, count helpers, and provenance tags are asserted directly.

**Integration Tests:**
- Corpus-backed legs (not a separate directory): docling→`PdfReader` fallback on real PDFs, OCR conditional path on `scanned_sample.pdf`, chunk→`DocStore`→embedding restore (`test_restore_chunks_to_embedding_from_doc_store`, `test_tracer_chunk_to_store_roundtrip`), `AiModel` auto-detect/fallback across both providers, `HybridRetriever` dense-index→search→delete→persistence roundtrips against real `lancedb` into `tmp_path`, `Summarizer`→`DocStore` cache roundtrips (`test_summarize_document_caching_lifecycle`, `test_summary_save_and_get_roundtrip`), `AiModel.validate_response` end-to-end against a real `RetrievalResult` (`test_ai_model_validate_response_integration`), gate-guarded `AiModel.generate_text`/`Summarizer.summarize_document` spy tests against the real `InferenceGate` (`test_ai_model_generate_text_guarded`, `test_summarizer_guarded_by_inference_gate`), Tier-3/Tier-4 invalidation roundtrips against real `DocStore`/`HybridRetriever` into `TemporaryDirectory` (`test_tier_3_sqlite_summary_version_invalidation`, `test_tier_4_lancedb_document_deletion_sync`). All still offline (mocked HTTP/GPU, real files/SQLite-tmp/LanceDB-tmp, real threads for gate legs).

**E2E Tests:**
- Not used. No Playwright/Selenium, no live `llama-server`, no Groq API calls, no Streamlit AppTest (`st.AppTest` absent). Browser/GPU paths are covered only by mocks + `main.py` manual verification + the offline profiler harness.

## Common Patterns

**Async Testing:**
- Not applicable — the codebase is fully synchronous (generators + blocking `httpx.Client`, no `asyncio`). Streaming is tested by materializing the generator: `tokens = list(provider.stream_text(...))` then asserting joined content and call recording (`stream_calls` in `tests/conftest.py:141-150`). Gate-blocking concurrency is tested with real `threading.Thread` + `Event` choreography, not async primitives.

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
with pytest.raises(ValueError, match="Intentional failure"):  # LatencyTracker still records on failure
    with LatencyTracker("failing_stage"):
        raise ValueError("Intentional failure")
with pytest.raises(TimeoutError, match="InferenceGate acquisition timed out"):  # gate contention
    with InferenceGate.hold(timeout=0.05):
        pass
# Health-path anti-pattern to preserve: check_health() NEVER raises — assert the Status literal instead:
assert provider.check_health().status == "unreachable"
# Retrieval-path anti-pattern to preserve: empty/degenerate queries return typed empties, never raise:
assert retriever.search_hybrid("", k=5).snippets == []
assert retriever.search_dense(vec, k=0) == []
# Telemetry anti-patterns to preserve: absent hardware returns None/zeros, never raises:
assert get_gpu_memory_info() is None                     # FileNotFoundError / CalledProcessError / TimeoutExpired
assert get_process_memory_info() == {"rss_mb": 0.0, "vms_mb": 0.0}  # psutil failure
assert bound_chat_history([], max_turns=50) == []        # empty history
# Citation-path anti-patterns to preserve: empty responses and ungrounded claims are INVALID, never valid:
assert validate_citations("", rr).is_valid is False                    # CR-03
assert validate_citations("It is great.", rr).is_valid is False        # ungrounded
assert validate_citations("Abstain ... insufficient evidence ...", rr).is_valid is True  # QA-04
```

## Gaps

Per `06-REVIEW.md` (verdict `NEEDS FIXES`, 1 Critical + 3 Warnings + 2 Info) and `06-REVIEW-FIX.md` (all 6 findings resolved/documented, `193/193 passed`):

- **All Phase-6 review findings closed:** CR-01 (gate release order → release-before-decrement + `test_unauthorized_release_does_not_corrupt_active_counter`), WR-01 (`_LATENCY_LOCK` + `MAX_STAGE_HISTORY=200` on every access), WR-02 (`bound_chat_history` + leading-assistant prune in `assemble_grounded_messages`), WR-03 (cache-invalidation test now exercises the real `bound_chat_history`), IN-01 (rogue-release test), IN-02 (DWM `487.0` MB fallback documented at `scripts/profile_resources.py:268-269`). No open Phase-6 defects remain per `06-REVIEW-FIX.md:5`.
- **E2E / live-server coverage missing (noted, not planned):** no test boots a real `llama-server`, hits Groq, or drives `main.py` via `st.AppTest`. The suite deliberately stops at `httpx.MockTransport` + provider doubles. Phase 5 narrowed this slightly (`test_ai_model_provider_attribute_contract` guards the CR-01 `._provider` typo; `test_clear_all_purges_summary_keys` guards WR-05), and Phase 6 added contract-level telemetry asserts (`test_sidebar_telemetry_contracts`), but `test_main_ui.py` still asserts string formatting, never real Streamlit widgets — tab isolation, drawer rendering, telemetry-widget badge thresholds (🟢/🟡/🔴 at 3500/3800 MB in `main.py:374-379`), and badge logic remain manual-only. Priority: Medium.
- **Upload-loop path still thin:** Phase-5 CR-01 (AttributeError aborting every new-PDF ingest, invisible to the suite) was fixed by one line + an attribute-contract test, but no test exercises `main.py`'s upload loop end-to-end (`05-REVIEW.md:78`). Phase 6 touched the same loop (dual-index removal, `contains_document` alias) with only Tier-4 deletion-sync coverage at the retriever level. A future ingestion outage of the same class would again hide behind green tests. Priority: Medium.
- **GPU/VRAM envelope asserted only by projection, not measurement:** the 4 GB ceiling is verified by `scripts/profile_resources.py` arithmetic (projected 3,445 MB ≤ 3,800 MB target) and the suite guards the CPU side (`test_local_embedding_cpu_pinning`) plus gate serialization (`tests/test_concurrency_lock.py`), but nothing measures real VRAM under load — `nvidia-smi` legs assert parsing/degradation with mocks, never live GPU counters, and the profiler is a manual artifact (`.planning/research/RESOURCE_PROFILE.json`), not a CI assertion. Risk: VRAM regressions merge silently. Priority: Medium.
- **Gate coverage is single-process only:** `InferenceGate` is a `threading.RLock` — contention tests prove intra-process serialization, but Streamlit multi-worker deployments (multiple server processes) would each hold an independent gate, silently violating the single-active-LLM invariant. No cross-process lock (file lock, socket guard) exists or is tested. Priority: Low-Medium (accepted for single-user laptop scope).
- **Latency-history bound is per-stage, not global:** `MAX_STAGE_HISTORY=200` caps each stage list, but a proliferation of distinct stage names (e.g. per-file `extract_{filename}` trackers in the profiler) grows the dict without a global cap. Long-running servers accumulating many unique stage keys could still leak slowly. Priority: Low.
- **Real-OCR accuracy unasserted:** `tests/test_ocr_fallback.py` proves gating/provenance/isolation with mocked recognizers, never `RapidOCR` word accuracy on `scanned_sample.pdf`. Risk: low-text pages index poorly without a failing test. Priority: Low (CPU cost keeps it out of CI by design).
- **Real-VLM output unasserted:** `tests/test_visual_analyzer.py` proves `source="vlm:<model>"` separation and degradation branches with `MockVisionProvider`; no test checks Qwen3-VL description quality. Risk: hallucinated chart readings pass CI. Priority: Low (accepted — VIS-03 provenance tagging is the mitigation under test).
- **Real-LanceDB failure modes thin:** the LanceDB-present legs run against a working local `lancedb` into `tmp_path`; native Tantivy FTS availability, `merge_insert` vs delete-then-add version skew, and Windows file-lock contention on `data/lancedb/` have no dedicated tests — the BM25-from-table fallback (WR-02 leg) and `logger.warning` degradations are exercised only via mocks. Risk: production LanceDB upgrade changes behavior silently. Priority: Low-Medium.
- **Summary quality unasserted (Phase 5, still open):** `tests/test_summarizer.py` proves routing, caching, clamping, and citation preservation via the echo-pages mock — never summary coherence, faithfulness, or profile distinctness against a real model. The echo mock asserts the union `[1, 2, 3, 4, 5]` survives, but a fluent-sounding hallucinated summary with intact `(p. X)` tags would pass. Priority: Low-Medium (accepted — LLM-as-judge is out of CI scope by design).
- **Abstention matcher still heuristic (known residual):** WR-07 tightened `CANONICAL_ABSTENTION_MARKERS` to full phrases + added the benign-prose negative test, but substring matching can still over/under-fire on paraphrased abstentions. Priority: Low.
- **Concurrency / Windows-lock coverage improved but partial:** Phase 6 added real-thread gate tests (blocking, timeout, rogue-release) plus `test_two_instance_interleave_R1` (`tmp_path`) for SQLite; still no multi-instance test for `HybridRetriever` fallback JSON persistence or concurrent summary upserts on the same `(sha256, profile)` row. Risk: `fallback_store.json` torn writes under rapid re-upload churn. Priority: Low.
- **No coverage gate:** percentage target is `Not enforced`; confidence rests on the 193-test behavioral inventory + lint gate. If a gate is ever added, start at the provider + ingestion + retrieval + summarization + concurrency/telemetry seams (`llama_cpp_provider.py`, `prompt_budget.py`, `ocr_fallback.py`, `visual_analyzer.py`, `hybrid_retriever.py`, `summarizer.py`, `citation_validator.py`, `local_llm.py`, `resource_telemetry.py`) where the CR/WR fixes cluster.

---

*Testing analysis: 2026-10-12*
