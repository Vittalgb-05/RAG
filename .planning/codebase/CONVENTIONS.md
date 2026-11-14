---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# Coding Conventions

**Analysis Date:** 2026-11-14

## Scope

Two codebases in one repository:

- **Python backend** — `api/`, `core/`, `ingestion/`, `providers/`, `retrieval/`, `services/`, plus root CLI entry points `start.py` and `setup.py`.
- **TypeScript frontend** — `frontend/src/` (Next.js 15 App Router, React 19, static export).

There is no `ui/` Streamlit package and no `main.py` at the repo root. Older docs (`CLAUDE.md`, `docs/CODE_QUALITY_REPORT.md`, `docs/TEST_RESULTS.md`) still describe the pre-FastAPI Streamlit layout; use the paths below.

## Naming Patterns

**Files (Python):**
- Modules are `snake_case` and named after the single responsibility they own: `core/doc_store.py`, `core/citation_validator.py`, `retrieval/hybrid_retriever.py`, `api/streaming.py`.
- API routers are one file per resource under `api/routers/`: `chat.py`, `documents.py`, `jobs.py`, `search.py`, `settings.py`, `summaries.py`, `system.py`, `visualize.py`.
- API request/response models live under `api/schemas/` in a matching file (`api/schemas/documents.py`, `api/schemas/common.py`).
- Tests are `tests/test_<module_or_feature>.py` (e.g. `tests/test_hybrid_retriever.py`, `tests/test_openapi_contract.py`).

**Files (TypeScript/React):**
- Components: kebab-case file, PascalCase export — `frontend/src/components/chat/citation-pill.tsx` exports `CitationPill`.
- Hooks and query modules: `frontend/src/lib/api/queries.ts` exports `useHealth`, `useDocuments`, `useDeleteDocument`.
- Route pages: `frontend/src/app/(shell)/<route>/page.tsx` with a default-exported PascalCase component (`LibraryPage`, `ChatPage`).

**Classes and types:**
- `PascalCase` everywhere: `DocStore`, `HybridRetriever`, `AiModel`, `InferenceGate`, `ChatTurnService`, `IngestionService`, `AppContainer`.
- Abstract interfaces keep the `Base*` prefix (`BaseModelProvider` in `providers/model_provider.py`); callable contracts use `Protocol` (`CitationValidator` in `services/chat_turn.py`).
- Type aliases are `PascalCase`: `Emit = Callable[[str, dict[str, Any]], None]` (`api/streaming.py`), `GroundingStatus` (`api/schemas/common.py`).
- TSDoc/TS interfaces are `PascalCase`; props are `<Component>Props` (`CitationPillProps`, `GroundingBadgeProps`).

**Functions and methods:**
- `snake_case`, verb-first for actions: `validate_pdf_bytes`, `hydrate_startup_state`, `sse_from_worker`, `summarize_document`, `ingest_pdf`, `problem_from_exc`.
- Private module helpers are prefixed with a single underscore: `_is_sqlite_busy` (`core/doc_store.py`), `_format_sources` (`api/routers/chat.py`), `_build_report` (`services/chat_turn.py`).
- Test helper factories use `_make_*`, `_doc`, `_indexed_document`, `_snippet` (`tests/test_citation_validator.py`, `tests/test_audit_repairs.py`, `tests/test_chat_controller.py`).
- React hooks must start with `use` and live in `frontend/src/lib/api/queries.ts` or `frontend/src/lib/store/use-app-store.ts`.

**Variables:**
- Short names are accepted for local collaborators inside routers: `c` for `AppContainer`, `s` for `Settings`, `d` for a document row (`api/routers/documents.py`).
- Test functions name the behavior and condition: `test_sha_unique_violation_on_reupload`, `test_inference_gate_basic_acquire_release`, `test_local_only_ingestion_and_indexing_invariant`. Some append a ticket/audit id: `test_corrupt_invalid_rejected_WR07`, `test_two_instance_interleave_R1`.

**Constants:**
- `UPPER_SNAKE_CASE` for module constants: `DEFAULT_MAX_OUTPUT_TOKENS`, `WRITE_MAX_ATTEMPTS`, `SSE_HEADERS`, `SYSTEM_GROUNDING_TEMPLATE`, `MAX_PAGES`.
- Private constants get a leading underscore: `_WRITE_RETRY_BASE_DELAY`, `_DONE`, `_SECRET_ENV_VARS`.

## Code Style

**Formatting and linting:**
- Ruff is the only formatter/linter. Config in `pyproject.toml`:
  - `line-length = 120`, `target-version = "py311"`.
  - Lint select: `E`, `F`, `W`, `B`, `UP`, `SIM`; ignore `E501`, `W291`, `W293`.
  - Per-file ignores: `scripts/* = ["E402"]`, `start.py = ["UP036"]`.
  - Excludes `.planning`, `.cache`, `data`, `docs`, `*.md`.
- CI runs both `ruff check .` and `ruff format --check .` (`.github/workflows/ci.yml`). Run the same before committing:
  ```bash
  ruff check .
  ruff format --check .
  ruff format .
  ```
- Formatting is Ruff-format output: 4-space indent, double quotes, trailing commas, wrapped calls/argument lists. Very long string literals (prompt templates in `core/prompt_budget.py`) are intentionally left over 120 columns because `E501` is ignored.

**Typing:**
- Python 3.11+ syntax only. Use PEP 604 unions (`str | None`, `list[dict[str, Any]]`) and built-in generics — never `Optional[...]` / `List[...]`.
- Newer modules start with `from __future__ import annotations`: all of `api/`, `services/`, `core/redaction.py`, `setup.py`. Older modules (`core/models.py`, `core/doc_store.py`, `ingestion/upload_validation.py`) omit it; follow the file you are editing.
- Annotate every public function signature and dataclass field. Local variables are generally left unannotated unless the type is non-obvious.
- No mypy/pyright gate exists. Do not introduce type-checker-only constructs.

**Docstrings:**
- Production modules start with a `"""..."""` docstring stating purpose and invariants. Examples: `core/prompt_budget.py`, `services/chat_turn.py`, `api/streaming.py`. Most test modules do too (`tests/test_hybrid_retriever.py`), though a few older files (`tests/test_setup_checksums.py`) start directly with imports.
- Public functions/methods use Google-style `Args:` / `Returns:` / `Raises:` without repeating types (`providers/model_provider.py`, `core/prompt_budget.py`).
- Test functions carry a one-line behavioral docstring stating the invariant they pin (`tests/test_logging_setup.py`, `tests/test_citation_validator.py`).
- Use reStructuredText double-backtick references inside docstrings: `` ``document_context`` ``, `` ``[REDACTED]`` ``.

**Comments:**
- Comments explain *why* and invariants, not mechanics. Example: `core/doc_store.py` explains the smart-retry policy above the constants; `core/prompt_budget.py` explains why one output-token reservation replaced three divergent values.
- Pipeline stages are numbered inline in services: `# 1. Validation (5%)`, `# 2. ...` in `services/ingestion.py`.
- Suppressions are justified inline: `except Exception as exc:  # noqa: BLE001 - convert to a terminal SSE error event` (`api/streaming.py`).

## Import Organization

**Order (observed, not tool-enforced):**
1. `from __future__ import annotations` (when used).
2. Standard library (`asyncio`, `json`, `threading`, `pathlib`, `collections.abc`).
3. Third-party (`fastapi`, `pydantic`, `numpy`, `pytest`).
4. First-party absolute imports (`api.*`, `core.*`, `ingestion.*`, `providers.*`, `retrieval.*`, `services.*`), often alphabetized by module but not strictly.

```python
from __future__ import annotations
import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any
from fastapi import Request

from api.container import AppContainer
from api.errors import ApiError
from core.models import RetrievalResult
```

- Ruff's import-sorting (`I`) rules are **not** enabled. Sort imports sensibly by hand; do not rely on isort.
- Always use absolute first-party imports (`from core.models import Chunk`), including from tests. There are no relative imports in Python code.
- Import types only for annotations under `TYPE_CHECKING` to avoid cycles: `api/container.py` does this for `Settings`.
- Local (function-scope) imports are used deliberately for optional/lazy dependencies and test isolation: `tests/conftest.py` imports `providers.groq_provider` inside the fixture; `tests/test_audit_repairs.py` imports `retrieval.hybrid_retriever` inside the test.

**Frontend imports:**
- External packages first, then the `@/` alias (`@/lib/api/queries`, `@/components/motion/count-up`), then same-folder relative imports (`./client`, `./types`).
- `@/*` maps to `frontend/src/*` (`frontend/tsconfig.json`).

## Data Modeling

**Pydantic v2 (domain + API):**
- Domain models in `core/models.py` are frozen and closed:
  ```python
  class Chunk(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      content: str = Field(..., min_length=1, description="Extracted chunk text content.")
  ```
- Use `Literal[...]` for closed sets (`status: Literal["ok", "empty", "failed"]`, provider health states), `Field(..., ge=1, description=...)` for constraints, and `@model_validator(mode="after")` for cross-field invariants (`BBox.validate_coordinates`, `EvidenceElement.validate_doc_id`).
- Validation failures raise `ValueError` inside validators so callers can map them uniformly.
- API schemas are separate from domain models (`api/schemas/*.py`) and do **not** set `extra="forbid"`; they mirror wire formats with `snake_case` field names. Keep field names `snake_case` end to end — the frontend `types.ts` mirrors them unchanged.
- Every router declares `response_model=` and typed return annotations (`api/routers/documents.py`).

**Dataclasses:**
- Internal value objects use `@dataclass(frozen=True)`: `ChatTurnPreparation`, `ChatTurnResult` (`services/chat_turn.py`).
- Mutable runtime records use plain `@dataclass` with `field(default_factory=...)`: `Job`, `JobEvent` (`api/jobs.py`), `IngestionResult` (`services/ingestion.py`).

**Configuration:**
- Settings use `pydantic_settings.BaseSettings` with `SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")` (`api/config.py`). Add new settings there with a typed default and an inline comment when the value is operationally significant.

## Error Handling

**Python domain → API mapping:**
- Raise domain `ValueError` for invalid input/state (`ingestion/upload_validation.py`, Pydantic validators).
- Raise `ApiError(status_code, code, detail, title=None)` in routers/dependencies for explicit HTTP failures (`api/errors.py`, `api/deps.py`).
- Raise `PermissionError` for missing cloud consent; `TimeoutError` when `InferenceGate` cannot acquire; `RuntimeError` for unreachable providers; `VectorIndexError` for vector failures. `api/errors.py` maps all of these to RFC 9457 `application/problem+json` payloads with a `code` such as `consent_required`, `gpu_busy`, `provider_unreachable`, `index_unavailable`, `validation_failed`, `not_found`, `upload_too_large`, `too_many_pages`.
- Error payloads are built by `problem_payload` / `problem_response` and always pass detail through `core.redaction.redact_text`. Never put raw exception text or credentials into a response without that path.
- Global handlers are installed once by `install_error_handlers(app)` in `api/main.py`.

**Never:**
- Never catch `Exception` and return success. Broad handlers are allowed only around optional integrations (OCR, telemetry, cache cleanup), and must log context and preserve the failure signal (`docs/CODE_QUALITY_REPORT.md` records the vector-failure regressions this caused).
- Never use bare `except:` — there are none in `api/`, `core/`, `ingestion/`, `providers/`, `retrieval/`, `services/`.
- Never let a background thread exception escape an SSE generator; convert it to a terminal event through `on_error` (`api/streaming.py`).

**Streaming errors:**
- Emit `event: error` and terminate, e.g. `emit("error", on_error(exc))`; keepalive frames are `": keepalive\n\n"`.
- Background jobs must end in a terminal state (`completed` / `failed` / `cancelled`) with `error` populated rather than raising into the pool (`api/jobs.py`).

**Frontend errors:**
- `apiClient` parses RFC 9457 bodies into `ApiError` (`code`, `status`, `detail`, `requestId`) in `frontend/src/lib/api/client.ts`.
- UI handlers `try/catch` and surface `toast.error(err.message ...)`; aborting an SSE stream is a normal return, not an error (`frontend/src/lib/api/sse.ts`).

## Logging

- Module-level logger: `logger = logging.getLogger(__name__)` in `core/doc_store.py`, `api/main.py`, `api/jobs.py`, `services/ingestion.py`, `core/local_llm.py`.
- Use lazy `%s` formatting: `logger.info("[%s] [%s %d%%] %s", filename, stage, pct, msg or stage)` (`services/ingestion.py`).
- Logging setup lives in `core/logging_setup.py` (idempotent root config, rotating file under `data/logs/`, `RAG_LOG_LEVEL`/`RAG_LOG_DIR`) and `api/main.py:configure_logging` for the API process.
- Never use `print()` in library code. `print()` is reserved for CLI operator output in `start.py` and `setup.py`.
- Never log raw document text, prompts with secrets, or provider keys; route user-visible error text through `redact_text`.

## Function and Module Design

**Functions:**
- Prefer small, single-purpose helpers over long methods; services compose them (`services/chat_turn.py` splits `prepare` / `finalize` / regeneration).
- Inject collaborators through constructor/parameters rather than importing singletons inside functions: `IngestionService(doc_store=..., hybrid_retriever=..., local_embedding=..., cache_dir=...)`, `ChatTurnService(validator)`.
- Keyword-only configuration flags are used for option-heavy APIs: `configure_logging(..., *, enable_file=True, force=False)`.
- Return typed result objects rather than tuples or raw dicts (`IngestionResult`, `ChatTurnPreparation`, `HydrationReport`).
- Callback contracts are typed: `Callable[..., None]` for progress, `Protocol` for validators, `Emit` alias for SSE.

**Modules and packages:**
- One responsibility per module; module docstring names it and its invariants.
- Package `__init__.py` files are minimal (`core/__init__.py`, `providers/__init__.py`, `api/__init__.py` contain only a docstring, sometimes `__version__`). `services/__init__.py` is the exception: it re-exports the public service surface with `__all__`.
- Avoid module-level mutable state. The deliberate exceptions are process-wide singletons: `InferenceGate` class state (`core/local_llm.py`), `_ACTIVE_STOPS` in `api/routers/chat.py`, and the shared embedding cache in `retrieval/local_embedding.py`.
- Compose the application graph in one place: `AppContainer.build()` (`api/container.py`). Routers receive it via `get_container`; services never construct each other ad hoc.

## API Conventions

- One `APIRouter(tags=["<resource>"])` per file in `api/routers/`; all routers are mounted under `/api/v1` centrally in `api/main.py`.
- Every router depends on `require_client_header` (mounted as a router dependency), which requires `X-RAG-Client: web` on mutating requests and raises `ApiError(403, "missing_client_header")`.
- Mutating endpoints use meaningful status codes: uploads return `202 Accepted` with job handles (`api/routers/documents.py`), deletes return `{"deleted": true}`.
- Pagination/limits use FastAPI `Query(...)` with explicit bounds (`api/routers/chat.py`).
- SSE responses use `StreamingResponse` with `SSE_HEADERS` (`Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`).
- `openapi.json` at the repo root is a checked-in artifact. After changing routes/schemas, regenerate and verify:
  ```bash
  python -m api.export_openapi          # write
  python -m api.export_openapi --check  # CI gate
  ```

## Frontend Conventions

- App Router with a route group: `frontend/src/app/(shell)/{chat,library,summarizer,settings,diagnostics,constellation}/page.tsx`; shell chrome in `frontend/src/app/(shell)/layout.tsx`.
- `"use client"` is the first line of every file that uses hooks, browser APIs, or event handlers (all current pages/components).
- Pages are default exports named `<Area>Page`; reusable components are named exports in kebab-case files.
- Props are declared as a local `interface <Component>Props` immediately above the component.
- Data fetching goes exclusively through TanStack Query hooks in `frontend/src/lib/api/queries.ts`; use `queryKey: ["resource", id]` arrays and invalidate/set cache in `onSuccess`. Do not `fetch` directly in components except the centralized `apiClient`/`streamSSE` helpers.
- Global UI state uses Zustand in `frontend/src/lib/store/use-app-store.ts` with one setter per field.
- Styling: Tailwind v4 utilities, arbitrary color values from the palette in `frontend/src/styles/globals.css` (`#050507`, `#A78BFA`, `#22D3EE`, `#34D399`, `#FBBF24`, `#F87171`), and `cn(...)` from `frontend/src/lib/utils.ts` for conditional classes. No CSS modules, no styled-components.
- TypeScript is `strict: true`. Avoid `any` in new code; existing `catch (err: any)` handlers in pages are legacy.
- There is **no ESLint or Prettier config** in `frontend/` even though `package.json` defines `lint: next lint`. Style is enforced by convention: 2-space indent, double quotes, semicolons, trailing commas. `pnpm typecheck` (`tsc --noEmit`) is the enforced gate.

## Cross-Cutting Invariants

- **GPU serialization:** every path that runs LLM/VLM/summarizer inference must acquire `InferenceGate.hold(timeout=60.0)` (`core/local_llm.py`). Never call a provider directly from a router/component.
- **Privacy boundary:** local mode must not egress. Cloud adapters require explicit consent (`PermissionError` otherwise) and redact keys on the way out and back. `core/sanitizer.py` neutralizes links/embeds for local rendering.
- **Transactions:** routers and frontend code never write storage directly; ingestion goes through `IngestionService`, deletion/purge/reindex through `LifecycleService`, both using `DocStore` transactional helpers.
- **Untrusted documents:** text from PDFs is untrusted; prompts isolate it in `<document_context>`, `core/prompt_budget.sanitize_xml_boundary` escapes spoofed tags, and citation validation runs before display.

## Anti-Patterns To Avoid

- **Silent failure conversion:** wrapping vector/index writes in `except Exception` and reporting success. Propagate `VectorIndexError` so the API returns `503 index_unavailable` (`api/errors.py`).
- **Ad-hoc storage access from the edge:** calling `container.doc_store` mutation methods in a router instead of an orchestration service. Follow `api/routers/documents.py`, which delegates ingestion to `c.ingestion` and deletion/reindex to `c.lifecycle`.
- **Bypassing the inference gate:** calling `provider.generate_text`/`stream_text` outside `InferenceGate.hold(...)`.
- **Splitting the wire contract:** renaming API fields or changing response shapes without updating `api/schemas/`, `frontend/src/lib/api/types.ts`, and `openapi.json`.
- **Unredacted errors:** returning `str(exc)` directly from a router; always go through `ApiError`/`problem_response` or `problem_from_exc`.

---

*Convention analysis: 2026-11-14*
