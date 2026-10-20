# Coding Conventions

**Analysis Date:** 2026-10-20

## Naming Patterns

**Files:**
- Root-level modules are flat `snake_case.py`, one primary class or cohesive concern per file: `citation_validator.py`, `doc_store.py`, `docling_reader.py`, `hybrid_retriever.py`, `local_llm.py`, `logging_setup.py`, `prompt_budget.py`, `resource_telemetry.py`, `summarizer.py`, `vector_index.py`.
- Entry points and CLI tooling are short verb/role names at repo root: `main.py` (Streamlit entry), `start.py` (launcher), `setup.py` (installer/packaging), `models.py` (Pydantic schemas).
- The UI layer is the only package: `ui/__init__.py`, `ui/theme.py`, `ui/components.py`, `ui/views.py`, `ui/ingestion_service.py`, `ui/hydration.py`, `ui/sanitizer.py`. Every module is a role-named `snake_case.py`; no nested subpackages.
- Scripts live in `scripts/` with intent names: `benchmark_baseline.py`, `benchmark_multimodal.py`, `generate_icons.py`, `profile_resources.py`.
- Tests are `tests/test_<module>.py`, one file per source module (`tests/test_hybrid_retriever.py` ↔ `hybrid_retriever.py`). Cross-cutting suites add a domain name: `tests/test_cloud_privacy.py`, `tests/test_concurrency_lock.py`, `tests/test_cache_invalidation.py`, `tests/test_main_ui.py`, `tests/test_ui_smoke.py`.
- Test fixture assets live under `tests/data/corpus/` with a generator named `generate_corpus.py` (not collected by pytest, since collection requires `test_*.py`).

**Classes:**
- `PascalCase`, noun-first, one public class per module: `DocStore` (`doc_store.py:108`), `HybridRetriever` (`hybrid_retriever.py`), `LocalEmbedding` (`local_embedding.py`), `PdfReader` (`pdf_reader.py`), `DoclingReader` (`docling_reader.py`), `AiModel` (`local_llm.py`), `IngestionService` (`ui/ingestion_service.py:38`), `TorchClassesScanLogFilter` (`logging_setup.py:16`).
- Provider implementations end in `Provider` and subclass `BaseModelProvider`: `GroqProvider` (`groq_provider.py`), `LlamaCppProvider` (`llama_cpp_provider.py`), `LiteLLMProvider` (`litellm_provider.py`).
- Pydantic schemas are bare domain nouns (`BBox`, `Chunk`, `Page`, `Document`, `RetrievalResult`, `EvidenceSnippet` in `models.py`) and result/verification records end in `Result`: `SummaryResult`, `CitationVerificationResult`, `IngestionResult`.
- Result containers use `@dataclass`: `IngestionResult` (`ui/ingestion_service.py:23`) and the frozen `ValidatedUpload` record (`upload_validation.py:50-51`).

**Functions and methods:**
- `snake_case`, verb-first for actions: `ingest_pdf`, `index_chunks`, `search_hybrid`, `compute_rrf`, `validate_citations`, `sanitize_markdown_for_local`, `hydrate_startup_state`, `inject_custom_theme`, `suppress_torch_classes_scan_warning`.
- UI renderers all start with `render_` and return either `None` (they draw) or `str` (they return markup): `render_sidebar_documents`, `render_chat_view`, `render_summarizer_view`, `render_library_view`, `render_settings_view` (`ui/views.py:49,184,473,590,684`); `render_status_pill`, `render_citation_chip`, `render_stat_card`, `render_empty_state` (`ui/components.py`).
- Private helpers and state use a single leading underscore: `_report` (`ui/ingestion_service.py:72`), `_reset_session_security_state` (`main.py:56`), `_connect`, `_apply_migrations` (`doc_store.py:123,141`), `_escape_sql_literal` (`hybrid_retriever.py:35`), `_embed_one` (`local_embedding.py`), `_fallback_store`, `_db`, `_table` (`hybrid_retriever.py`).
- Test helpers use a leading underscore and are module-local: `_make_unit_vector` (`tests/test_hybrid_retriever.py:14`).

**Variables and attributes:**
- `snake_case` locals and attributes; no Hungarian prefixes. UI cache keys are deliberately string-prefixed: `_cached_cloud_model`, `_cached_cloud_key`, `_startup_hydrated` in `st.session_state`.
- `UPPER_CASE` module constants: `CONFIG_VERSION`, `SCHEMA_V1_DDL`, `SCHEMA_V2_DDL`, `DEFAULT_DB_URI`, `DEFAULT_RRF_K`, `MAX_CHAT_TURNS`, `CITATION_REGEX`, `CANONICAL_ABSTENTION_MARKERS`, `WATCHER_LOGGER_NAME` (`logging_setup.py:13`), theme tokens `COLOR_BG`, `COLOR_PRIMARY`, `THEME_CSS` (`ui/theme.py:6-17`).
- Newer modules type private caches explicitly, e.g. `_MODEL_CACHE: dict[tuple[str, str], SentenceTransformer]` (`local_embedding.py:24`) and `_ICON_CACHE: dict[str, str]` (`ui/components.py:11`).

**Types:**
- Pydantic v2 models with `model_config = ConfigDict(frozen=True, extra="forbid")` for value objects (`BBox`, `Chunk`, `ProviderCapabilities`) and `extra="forbid"` alone for mutable records (`Page`, `Document`).
- `Literal[...]` for closed enums (`status`, provider type) rather than free strings.
- Field validation belongs on the model (`Field(..., ge=1)`, `model_validator(mode="after")`), not in call sites.

## Code Style

**Formatting:**
- Formatter: `ruff format` (CI gate `ruff format --check .` in `.github/workflows/ci.yml`). Current baseline is clean: 65 files already formatted.
- Config lives in `pyproject.toml:1-17`: `line-length = 120`, `target-version = "py311"`, excludes `.planning`, `.cache`, `data`, `docs`, `*.md`.
- Style is effectively PEP 8 with 4-space indentation, double-quoted strings, two blank lines between top-level definitions. `ruff format` normalizes quote style; hand-written code already uses double quotes.
- Long f-strings and inline HTML are allowed to run to 120 columns (e.g. `ui/components.py:59-61`, `ui/theme.py`), and E501 is ignored, so lines may exceed 120 when splitting would hurt readability.

**Linting:**
- Tool: `ruff` (pinned `>=0.9.0` in `requirements-test.txt:4`; local run verified with 0.15.12).
- Rule selection: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` (`pyproject.toml:12-14`). This is pycodestyle + pyflakes only — no `I` import sorting, no `B` bugbear, no `UP` pyupgrade, no `ANN` annotations, no `D` docstring rules.
- Per-file ignore: `scripts/*` may use `E402` (module-level import not at top) because scripts inject `sys.path` before importing project modules (`pyproject.toml:16-17`, `scripts/benchmark_multimodal.py:10-23`).
- No mypy/pyright, no pre-commit hooks found.
- Run gate locally with `ruff check .` and `ruff format --check .`; both pass today.

## Import Organization

**Order (match this exactly):**
1. Module docstring.
2. Environment guards that must execute before heavy imports — `os.environ.setdefault("USE_TF", "0")`, `USE_TORCH`, `TF_ENABLE_ONEDNN_OPTS` (`main.py:15-18`, `start.py:31-33`, `local_embedding.py:10-12`).
3. Standard library: `logging`, `os`, `datetime`, `pathlib`, `typing`/`collections.abc`.
4. Third-party: `streamlit`, `pydantic`, `numpy`, `httpx`, `dotenv`.
5. Blank line, then local absolute imports (`from models import ...`, `from ui.views import ...`).

**Path aliases:**
- None configured. All imports are absolute top-level module names resolved from the repo root (flat layout) or the `ui` package.
- `from __future__ import annotations` is used only in the two CLI/packaging entry points `setup.py:14` and `start.py:10`; library and UI modules rely on native `X | Y` syntax (Python 3.11).
- Optional third-party dependencies are imported at module top in `try/except ImportError` and set to `None`, then guarded at use sites: `lancedb`/`pyarrow` (`hybrid_retriever.py:25-31`), `docling` (`docling_reader.py:27`), `groq` (`groq_provider.py:14`), `litellm` (`litellm_provider.py:25`), RapidOCR (`ocr_fallback.py:23-31`).
- Deferred imports inside functions are reserved for optional/fallback paths to avoid import cost or cycles: `from pdf_reader import PdfReader` inside the Docling failure branch (`ui/ingestion_service.py:126`), and `from main import _reset_session_security_state` inside a test (`tests/test_ui_smoke.py:109`).

## Error Handling

**Patterns:**
- **Fail fast at boundaries.** Public constructors and validators raise `ValueError` for bad values and `TypeError` for bad types before mutating state: `DocStore.__init__`, `HybridRetriever`, `cache_dir_for` (`models.py:22-23`), `validate_pdf_bytes` (`upload_validation.py`).
- **Typed, actionable exceptions.** Missing credentials raise `ValueError` with remediation; cloud use without consent raises `PermissionError("Cloud transmission blocked...")` (`litellm_provider.py`, covered in `tests/test_cloud_privacy.py:34`); provider transport failures are wrapped in `RuntimeError` with provider/model context (`tests/test_llama_cpp_provider.py:128`, `tests/test_litellm_provider.py:231`).
- **Stage-isolated degradation in orchestration.** `IngestionService.ingest_pdf` wraps each stage (validation, extraction, OCR, visual analysis, SQLite write, LanceDB indexing, cache write) in its own `try/except`, logs a `warning`, and either continues with partial results or returns an `IngestionResult(success=False, error=...)` (`ui/ingestion_service.py:79-289`). Never let one optional stage abort the whole ingestion.
- **Nested fallback chains.** Docling failure falls back to `PdfReader`; LanceDB absence/failure falls back to `VectorIndex` plus a JSON store (`hybrid_retriever.py:126-148`, `tests/test_hybrid_retriever.py:156`). Fallback paths log at `warning`/`info` and remain functional, not silent.
- **Guard-only `except Exception: pass`** is acceptable solely for teardown/cleanup of optional resources: closing providers or reverting status (`main.py:63-67,77-81`, `ui/ingestion_service.py:252-266`). Do not use bare `except:` anywhere.
- **Optional dependency guard shape:** `try: import x / except ImportError: x = None  # type: ignore[assignment]`, then raise `ImportError` with an install hint or degrade at the use site (`hybrid_retriever.py:25-31`, `groq_provider.py:14`).
- **Empty is not an error.** Retrieval returns empty lists/result objects rather than raising on an empty store; `search_hybrid` is covered by `tests/test_hybrid_retriever.py:297`.
- **Tests assert exception types and message fragments** with `pytest.raises(..., match="...")`; new error paths should expose a stable message substring.

## Logging

**Framework:** stdlib `logging`. No third-party logger, no structlog.

**Patterns:**
- Every service module declares a module-level logger immediately after imports: `logger = logging.getLogger(__name__)` (`citation_validator.py:14`, `hybrid_retriever.py:20`, `local_llm.py:23`, `local_embedding.py:21`, `main.py:38`, `ui/views.py:30`, `ui/ingestion_service.py:20`, `ui/hydration.py:10`, `visual_analyzer.py:16`). The exception is `doc_store.py`, which uses `print` for migration notices only.
- Use lazy `%s` formatting, never f-strings in log calls: `logger.info("LanceDB persistent retriever connected at %s", self.db_uri)` (`hybrid_retriever.py:126`), `logger.warning("OCR processing warning: %s", ocr_err)` (`ui/ingestion_service.py:156`).
- Level discipline: `info` for lifecycle/state transitions, `warning` for recoverable degradation and fallbacks, `error` for failed persistence/generation, `debug` for noisy library notices (e.g. LanceDB FTS index creation, `hybrid_retriever.py:471-487`).
- User-facing feedback uses Streamlit primitives (`st.status`, `st.warning`, `st.error`, `st.success`, `st.info`) or the `progress_callback` passed into `IngestionService`; never `print()` from UI/library code. `print()` is confined to human-run CLIs (`setup.py`, `start.py`, `scripts/*`, `tests/data/corpus/generate_corpus.py`) and two legacy spots: `pdf_reader.py:131` and `doc_store.py:154`.
- `logging_setup.py` demonstrates the preferred targeted suppression: a `logging.Filter` subclass (`TorchClassesScanLogFilter`, `logging_setup.py:16-28`) installed idempotently by a named installer (`suppress_torch_classes_scan_warning`, `logging_setup.py:31-47`) instead of raising global logger levels. Filters are used because Streamlit's `get_logger` resets levels on import. Reuse this shape for any "quiet one benign third-party message" need.
- Scripts that own the process configure logging once at entry: `logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")` (`scripts/benchmark_multimodal.py:29`, `scripts/profile_resources.py`).

## Docstrings and Comments

**Module docstrings:**
- Required on every module. They state purpose plus the invariants/requirement IDs the module enforces: capability tags such as `(RETR-01, RETR-02)`, `(QUAL-01)`, `(INF-03)`, `(UI-04)`, `(P0-Audit)` appear in `hybrid_retriever.py:1-6`, `local_llm.py`, `citation_validator.py:1-7`, `ui/sanitizer.py:1-5`, `main.py:1-9`, `ui/ingestion_service.py:1`.
- Older test modules use a `# ---` banner block instead of a docstring (`tests/conftest.py:1-4`, `tests/test_models.py:1-5`); newer test modules use a one-line docstring (all `tests/test_*.py` touched recently, e.g. `tests/test_main_ui.py:1`). Prefer the docstring form for new files.

**Function/method docstrings:**
- Public APIs use Google-style `Args:` / `Returns:` blocks: `compute_rrf` (`hybrid_retriever.py:38-59`), `TorchClassesScanLogFilter` installer (`logging_setup.py:34-43`), `IngestionService.ingest_pdf` (`ui/ingestion_service.py:60-70`), `sanitize_markdown_for_local` (`ui/sanitizer.py:19-29`), `get_svg_icon` (`ui/components.py:14-24`).
- Trivial one-liners may use a single imperative sentence: `"""Render an evidence citation chip with page reference."""` (`ui/components.py:114`), `"""Reset session security state, in-memory models, and cleanse credentials (WR-02)."""` (`main.py:57`).
- Private helpers get a terse docstring only when non-obvious: `_escape_sql_literal` (`hybrid_retriever.py:35`).

**Comments:**
- Comments explain *why*, not *what*: the `InferenceGate` VRAM rationale (`local_llm.py:29-33`), the filter-vs-setLevel rationale (`logging_setup.py:18-22`), the `torch.classes` watcher workaround (`main.py:40`), the stage numbering in `ingest_pdf` (`# 1. Validation` … `# 9. Disk cache write`, `ui/ingestion_service.py:77-277`).
- Reference audit IDs in comments/docstrings when a guard exists for a specific defect: `(P0-1)`, `(P0-2)`, `(P1-5)`, `(WR-01)`, `(CR-01)`, `(CONCERNS P1 audit)` (`ui/ingestion_service.py:176`, `tests/test_ui_smoke.py:108-122`).
- Section banners are the agreed visual separator. In `ui/views.py` and `main.py` use the 69-character `# ====` / `# ----` banner with a numbered title and surrounding blank lines (`ui/views.py:44-46,179-181,468-470,585-587,679-681`; `main.py:91-93,105-107`).
- Keep the commented-out usage examples at the bottom of pure-logic modules (`pdf_reader.py:166-167`) — update them when the API changes.

## Type Hints

**Patterns:**
- Modern PEP 604/PEP 585 syntax only: `str | None`, `list[Chunk]`, `dict[str, Any]`, `tuple[str, ...]`, no `Optional`/`List`/`Dict`.
- Public methods on core services annotate all parameters and returns, including `-> None`: `DocStore` methods (`doc_store.py:156-638`), `HybridRetriever` methods, `compute_rrf(...) -> list[tuple[str, float, int, int | None, int | None]]` (`hybrid_retriever.py:42-48`).
- Callable and generator types come from `collections.abc`: `Callable[[str], None]` (`ui/ingestion_service.py:58`), `Generator[...]` (`doc_store.py:123`, `local_llm.py:8`), never `typing.Callable`.
- UI renderers may omit hints on `st`-driven helpers, but `ui/ingestion_service.py`, `ui/hydration.py`, `ui/components.py` and `ui/sanitizer.py` are fully annotated. New code in `ui/` must annotate parameters and returns.
- Tests are inconsistent by file: newer suites annotate `def test_...(tmp_path, monkeypatch) -> None` (`tests/test_sanitizer.py`, `tests/test_cloud_privacy.py`); older suites omit the return annotation (`tests/test_models.py`, `tests/test_hybrid_retriever.py`). Match the file you are editing; annotate `-> None` for new test files.
- `# type: ignore[...]` is used narrowly and always names the code (`# type: ignore[assignment]` in `hybrid_retriever.py:29`, `# type: ignore[method-assign]` in `tests/test_logging_setup.py:59`).

## UI Package Conventions (chatbot-first refactor)

**Layering:** `ui/theme.py` → `ui/components.py` → `ui/views.py`; services (`ui/ingestion_service.py`, `ui/hydration.py`) do not import Streamlit rendering, only `st.session_state` where hydration demands it. `main.py` is the only module that calls `st.set_page_config`.

- **Theme:** design tokens are module constants (`COLOR_*`), CSS is one `THEME_CSS` f-string with doubled braces, and the single entry point is `inject_custom_theme()` (`ui/theme.py:186-188`). Never hardcode a new hex color in a view — add a token or reuse an existing one. Color values also appear in `ui/components.py` SVG calls (`#B9A3FF`, `#70D9C2`, `#FF7B72`); reuse those exact values.
- **Components:** pure functions that return HTML strings; caller decides where to render. All interpolated user/document text must pass through `html.escape` (`ui/components.py:72,76-77,91,98-99,116`). SVG icons are local files loaded from `assets/icons/` and cached in `_ICON_CACHE`; never reference a CDN (enforced by `tests/test_ui_smoke.py:38-61`).
- **Streamlit version compatibility:** optional APIs are feature-detected with `hasattr(st, "html")` and fall back to `st.markdown(..., unsafe_allow_html=True)` (`ui/components.py:63-66,80-83,107-110`). Follow this pattern for any newer Streamlit API.
- **Views:** each view is one `render_<view>_view(...)` function with a numbered section banner; it receives services (`DocStore`, `AiModel`, cache dir) as parameters rather than constructing them internally. Session-scoped objects are passed as `st.session_state.get("hybrid_retriever")` into `IngestionService` and written back after ingestion (`ui/views.py:84-118`).
- **Services:** `IngestionService` is constructor-injected (`doc_store`, optional `hybrid_retriever`, `local_embedding`, `cache_dir`) with lazy defaults; it returns a dataclass result instead of raising for expected failures, and accepts `progress_callback: Callable[[str], None]` for UI progress. Follow this shape for new orchestration services.
- **HTML sanitization:** all model-authored or document-authored Markdown displayed in local mode goes through `sanitize_display_markdown` / `sanitize_markdown_for_local` (`ui/sanitizer.py`); external images/scripts are replaced, not escaped. Preserve the `allow_external` flag semantics (only `True` after cloud consent).
- **Hydration:** `hydrate_startup_state` is idempotent via `st.session_state._startup_hydrated` and swallows/records non-fatal failures with `logger.warning` (`ui/hydration.py:19-28,47-58`). Add new startup state behind the same one-shot guard rather than in an ad-hoc `main.py` block.

## Config and Secret Conventions

- Precedence is explicit: Streamlit secrets first (`st.secrets["GROQ_API_KEY"]` guarded by `safe_has_secret`, `main.py:46-53`), then environment / `.env` loaded via `load_dotenv()`. Missing keys raise `ValueError` naming both locations.
- `.env` is gitignored (`.gitignore:1`); `data/`, `models/`, `tools/`, `.cache/`, `.planning/` are gitignored. Never commit model weights, LanceDB data, or vendored binaries.
- Cloud mode requires an explicit boolean consent (`user_consented`) and raises `PermissionError` otherwise; privacy invariants are regression-tested (`tests/test_cloud_privacy.py`, `tests/test_litellm_provider.py:30-36`). Any new network-capable path must carry the same gate.

## Vendored Runtime: `tools/llama-server`

- `tools/llama-server/` contains prebuilt Windows x64 `llama.cpp` binaries and CUDA 12 DLLs (`llama-server.exe`, `llama-cli.exe`, `ggml-cuda.dll`, `cublas64_12.dll`, etc.).
- It is not source code and is entirely gitignored via `tools/` (`.gitignore` last line). Do not edit, format, or lint these files, and do not write Python that imports from this directory.
- Launch/integration belongs in `llama_cpp_provider.py` (HTTP client) and `start.py` / `setup.py` (process acquisition and health verification), with the server URL configured rather than hardcoded into views.

## Function Design

**Size:** Small single-purpose functions; view renderers are the deliberate exception and should stay as sequential layout blocks (`render_chat_view` and `render_library_view` in `ui/views.py` run 100–200 lines of streamed layout calls).

**Parameters:**
- Keyword-friendly with sane defaults: `max_tokens: int = 1024`, `temperature: float = 0.2`, `k: int = 10`, `k_rrf: int = DEFAULT_RRF_K`, `allow_external: bool = False`.
- Dependency injection over global lookups for testability: pass `transport=` to `LlamaCppProvider`, `provider=` to `AiModel`, `embedding_fn=` to `HybridRetriever`, `doc_store=` to `IngestionService`.

**Return values:**
- Data methods return plain containers or Pydantic models: `list[Chunk]`, `list[tuple[dict, float]]`, `RetrievalResult`, `IngestionResult`.
- Generators for streaming: `stream_text` and `ask_a_question_from_pdf_stream` `yield` string fragments; never return a fully buffered string.
- No `None`-on-error sentinel for failures that callers must handle — raise with context, or return an explicit result object with `success: bool, error: str | None`.

## Module Design

- **Exports:** `ui/__init__.py` re-exports exactly one function (`sanitize_markdown_for_local`) with `__all__` (`ui/__init__.py:3-5`). Root modules export their class implicitly; do not add barrel re-exports at the repo root.
- **Singletons:** process-level caches are module-private dicts with explicit get/clear functions (`_MODEL_CACHE` / `get_shared_sentence_transformer` / `clear_shared_model_cache`, `local_embedding.py:24-45`; `_ICON_CACHE`, `ui/components.py:11`). Tests must call the clear function in `finally` (`tests/test_hybrid_retriever.py:22-35`).
- **Context managers:** resource-owning classes implement `__enter__`/`__exit__` plus `close()` (`HybridRetriever`); SQLite uses a `@contextmanager` connection factory (`doc_store.py:122-140`).

## Documented Test/Lint Gates

- `.github/workflows/ci.yml` is the canonical gate: Python 3.11, `uv pip install -r requirements-lock.txt -r requirements-test.txt`, `ruff check .`, `ruff format --check .`, `python tests/data/corpus/generate_corpus.py`, `pytest tests/ -v`.
- README documents the same commands but its test count (248) is stale; the live suite collects 289 tests. Do not copy counts into docs without re-running collection.

---

*Convention analysis: 2026-10-20*
