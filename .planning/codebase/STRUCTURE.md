---
last_mapped_commit: 6acbd27a48dddbd1b122277663ebab42d9f83f7e
last_mapped_at: 2026-11-14
---
# Codebase Structure

**Analysis Date:** 2026-11-14

## Directory Layout

```text
RAG/
├── api/                      # FastAPI application: app factory, routers, schemas, SSE bridge, jobs, errors
│   ├── routers/              # One module per resource; all mounted under /api/v1
│   ├── schemas/              # Pydantic request/response models, one module per resource
│   ├── main.py               # create_app(), lifespan, middleware, router registration
│   ├── container.py          # AppContainer composition root (singletons)
│   ├── deps.py               # get_container(), require_client_header()
│   ├── errors.py             # RFC 9457 problem+json mapping
│   ├── streaming.py          # worker-thread → asyncio → SSE bridge
│   ├── jobs.py               # Single-worker JobManager
│   ├── cloud_state.py        # Consent, in-memory keys, provider swap, egress ledger
│   ├── config.py             # pydantic-settings (RAG_ prefix)
│   └── export_openapi.py     # `python -m api.export_openapi [--check]`
├── services/                 # Orchestration: chat turns, ingestion, lifecycle, hydration
├── core/                     # Domain logic: models, SQLite store, LLM facade/gate, summarizer, citations
├── retrieval/                # Hybrid retriever, embeddings, pure-Python vector index
├── ingestion/                # PDF validation, Docling/pypdf readers, OCR, visual analysis
├── providers/                # BaseModelProvider ABC + llama.cpp / LiteLLM / Groq adapters
├── frontend/                 # Next.js 15 static-export UI (pnpm workspace)
│   └── src/
│       ├── app/              # App Router: root layout, redirect page, (shell) route group
│       ├── components/       # shell/, chat/, motion/ presentational components
│       ├── lib/              # api/ (client, sse, queries, types, mocks), store/ (zustand)
│       └── styles/           # globals.css (Tailwind v4)
├── tests/                    # pytest suite (43 test modules) + synthetic corpus
│   └── data/corpus/          # Generated + committed PDF fixtures and generator
├── scripts/                  # Offline benchmarks, resource profiling, icon generation
├── docs/                     # Runbook, evaluation, dependency audit, traceability (partly stale)
├── assets/                   # Brand mark and monochrome SVG icons (legacy Streamlit-era assets)
├── data/                     # Runtime state (gitignored): documents.db, lancedb/, .cache/, logs/
├── application_screenshots/  # README/demo images
├── .github/workflows/ci.yml  # Backend lint/openapi/tests + frontend typecheck/build
├── .devcontainer/            # Dev container definition
├── start.py                  # One-command launcher (preflight + optional llama-server + uvicorn)
├── setup.py                  # Packaging + dependency/model provisioning CLI
├── pyproject.toml            # Ruff + pytest configuration
├── requirements.txt          # Runtime deps
├── requirements-lock.txt     # uv-compiled lockfile (Python 3.11)
├── requirements-test.txt     # Test-only deps
├── openapi.json             # Committed OpenAPI export (CI drift check)
├── Dockerfile                # Multi-stage: Next build → Python runtime, exposes 8000
├── docker-compose.yml        # app + optional CUDA llama-server profile
└── .env.example              # Documented environment names (no secrets)
```

## Directory Purposes

**`api/`:**
- Purpose: HTTP transport and composition.
- Contains: App factory, settings, dependency providers, error mapping, SSE bridge, job manager, cloud state, routers, schemas.
- Key files: `api/main.py`, `api/container.py`, `api/routers/chat.py`, `api/routers/documents.py`, `api/streaming.py`, `api/jobs.py`, `api/errors.py`.

**`api/routers/`:**
- Purpose: One router per resource, thin handlers that delegate to container services.
- Contains: `system.py` (health/telemetry/diagnostics/logs), `settings.py` (settings + cloud + privacy ledger), `documents.py` (upload/list/detail/page image/reindex/delete/purge), `jobs.py` (list/detail/events/cancel), `chat.py` (sessions + SSE message stream + stop), `summaries.py` (cached/generate/export/delete), `search.py` (hybrid search + X-Ray), `visualize.py` (constellation + query trace).
- Key files: `api/routers/chat.py` and `api/routers/documents.py` hold most orchestration logic.

**`api/schemas/`:**
- Purpose: Wire contracts, kept separate from domain models so HTTP shapes can evolve independently.
- Contains: `common.py` (Scope, Source, Grounding, Problem), `chat.py`, `documents.py`, `jobs.py`, `search.py`, `settings.py`, `summaries.py`, `system.py`, `visualize.py`.
- Key files: `api/schemas/common.py` is imported by several routers.

**`services/`:**
- Purpose: Multi-resource workflows that must not live in routers.
- Contains: `chat_turn.py` (scope → retrieval → verification → result), `ingestion.py` (staged pipeline), `lifecycle.py` (delete/purge/reindex across tiers), `hydration.py` (startup repair + tombstones).
- Key files: `services/chat_turn.py`, `services/ingestion.py`.

**`core/`:**
- Purpose: Domain rules and persistence independent of HTTP.
- Contains: `models.py` (canonical Pydantic schemas), `doc_store.py` (SQLite), `local_llm.py` (AiModel + InferenceGate), `summarizer.py`, `citation_validator.py`, `prompt_budget.py`, `query_intent.py`, `sanitizer.py`, `redaction.py`, `resource_telemetry.py`, `runtime_info.py`, `model_identity.py`, `logging_setup.py`, `limits.py`.
- Key files: `core/models.py`, `core/local_llm.py`, `core/doc_store.py`.

**`retrieval/`:**
- Purpose: Query-time evidence retrieval and indexing.
- Contains: `hybrid_retriever.py` (LanceDB dense + BM25 FTS + RRF, document fetch, embedding export), `local_embedding.py` (MiniLM wrapper + process cache), `vector_index.py` (stdlib fallback).
- Key files: `retrieval/hybrid_retriever.py:169` (`HybridRetriever`).

**`ingestion/`:**
- Purpose: PDF-to-structured-evidence primitives.
- Contains: `upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`.
- Key files: `ingestion/upload_validation.py:118` (`validate_pdf_bytes`), `ingestion/visual_analyzer.py:41` (`VisualAnalyzer`).

**`providers/`:**
- Purpose: Inference adapters behind a single ABC.
- Contains: `model_provider.py` (ABC + capability/health models), `llama_cpp_provider.py`, `litellm_provider.py`, `groq_provider.py`.
- Key files: `providers/model_provider.py:64`, `providers/llama_cpp_provider.py:68`.

**`frontend/src/app/`:**
- Purpose: Next.js App Router pages (static export).
- Contains: `layout.tsx` (QueryClient + global overlays), `page.tsx` (redirect to `/chat`), `(shell)/layout.tsx` (sidebar + topbar + aurora background), and route pages `chat`, `library`, `summarizer`, `constellation`, `settings`, `diagnostics`.
- Key files: `frontend/src/app/(shell)/chat/page.tsx` (largest surface, SSE streaming), `frontend/src/app/(shell)/library/page.tsx`, `frontend/src/app/(shell)/summarizer/page.tsx`.

**`frontend/src/components/`:**
- Purpose: Presentational and interaction components grouped by surface.
- Contains: `shell/` (sidebar, topbar, command palette, jobs tray, aurora background), `chat/` (message bubble, citation pill, evidence drawer, evidence lens modal, grounding badge, grounding heatmap, retrieval X-Ray drawer), `motion/` (blur text, count up, magnet, shiny text, spotlight card).
- Key files: `frontend/src/components/shell/sidebar.tsx` (nav registry), `frontend/src/components/chat/message-bubble.tsx`.

**`frontend/src/lib/`:**
- Purpose: Non-visual client infrastructure.
- Contains: `api/client.ts` (fetch wrapper + `ApiError`), `api/sse.ts` (POST/fetch SSE parser), `api/queries.ts` (TanStack Query hooks), `api/types.ts` (hand-maintained TS mirrors of API schemas), `api/mocks.ts` (mock mode), `store/use-app-store.ts` (zustand), `utils.ts` (`cn`).
- Key files: `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/queries.ts`, `frontend/src/lib/api/sse.ts`.

**`tests/`:**
- Purpose: Offline pytest suite with GPU/network seams mocked.
- Contains: 43 `test_*.py` modules covering API contracts, streaming bridge, chat controller, retrieval, ingestion readers, providers, setup/launcher, redaction, openapi, cloud privacy.
- Key files: `tests/conftest.py` (fixtures: mock Groq client, mock SentenceTransformer, env keys), `tests/test_chat_api_sse.py`, `tests/test_openapi_contract.py`.

**`tests/data/corpus/`:**
- Purpose: Deterministic PDF fixtures for extraction/OCR tests.
- Contains: `generate_corpus.py` (reportlab generator) and generated PDFs (`clean_digital.pdf`, `scanned_sample.pdf`, `dense_table.pdf`, `chart_diagram.pdf`, `multi_column.pdf`, `corrupt_invalid.pdf`).
- Key files: `tests/data/corpus/generate_corpus.py` (run in CI before pytest).

**`scripts/`:**
- Purpose: Offline evaluation and dev utilities, not imported by the app.
- Contains: `benchmark_baseline.py`, `benchmark_multimodal.py`, `profile_resources.py`, `generate_icons.py`.
- Key files: `scripts/profile_resources.py`.

**`data/`:**
- Purpose: Runtime persistence root (gitignored).
- Contains: `documents.db` (SQLite), `lancedb/` (vector + FTS), `.cache/<sha256>/<CONFIG_VERSION>/`, `logs/rag.log`, optional `originals/<sha256>.pdf`.
- Key files: paths are computed from `Settings.data_dir` (`api/config.py:20`) and `core/models.py:cache_dir_for`.

**`docs/`:**
- Purpose: Operational and audit documentation.
- Contains: runbook, evaluation, dependency audit, code-quality report, endpoint integration matrix, requirements traceability, local inference tuning, repair log, test results.
- Key files: `docs/RUNBOOK.md`, `docs/LOCAL_INFERENCE.md`. Note: several docs still describe the removed Streamlit UI.

## Key File Locations

**Entry Points:**
- `api/main.py`: FastAPI app factory, lifespan, router mounting, static frontend mount.
- `api/main.py:90`: `run()` used by the `rag-api` console script.
- `start.py:354`: `launch_server()` — preflight + uvicorn launch.
- `setup.py:1257`: console scripts (`rag-api`).
- `frontend/src/app/page.tsx`: client redirect to `/chat`.

**Configuration:**
- `api/config.py`: all runtime settings (`RAG_*` env vars).
- `pyproject.toml`: Ruff (line length 120, py311) and pytest config.
- `frontend/next.config.mjs`: `output: "export"`, unoptimized images, trailing slashes.
- `frontend/tsconfig.json`: `@/*` path alias to `src/*`.
- `Dockerfile`, `docker-compose.yml`: container build and runtime topology.
- `.github/workflows/ci.yml`: lint, OpenAPI drift check, corpus generation, pytest, frontend typecheck/build.

**Core Logic:**
- `services/chat_turn.py`: retrieval scope, evidence preparation, citation verification/regeneration/abstention.
- `services/ingestion.py`: staged PDF ingestion transaction.
- `core/local_llm.py`: provider routing, prompt assembly, `InferenceGate`.
- `core/citation_validator.py`: `[E#]` precision and claim-support rules.
- `core/doc_store.py`: SQLite schema and all persistence methods.
- `retrieval/hybrid_retriever.py`: dense+lexical retrieval and indexing.
- `api/streaming.py`: the only correct way to stream generation to a client.

**Testing:**
- `tests/conftest.py`: shared offline fixtures.
- `tests/test_chat_api_sse.py`: end-to-end SSE behavior with a stubbed container.
- `tests/test_openapi_contract.py`: route/contract coverage.
- `tests/data/corpus/generate_corpus.py`: fixture generation.

## Naming Conventions

**Files (Python):**
- Modules: `snake_case.py`; one concern per module (`chat_turn.py`, `hybrid_retriever.py`).
- Routers mirror resources: `api/routers/<resource>.py`.
- Schemas mirror routers: `api/schemas/<resource>.py`.
- Tests: `tests/test_<module_or_feature>.py` (e.g., `test_cloud_state.py`, `test_chat_api_sse.py`).

**Files (Frontend):**
- Components: kebab-case files exporting PascalCase components (`message-bubble.tsx` → `MessageBubble`).
- Route pages: lowercase directory + `page.tsx` (`app/(shell)/library/page.tsx`).
- Client modules: lowercase (`client.ts`, `sse.ts`, `queries.ts`, `types.ts`).
- Store hooks: `use-<thing>.ts` exporting `use<Thing>` (`use-app-store.ts` → `useAppStore`).

**Directories:**
- Python packages are responsibility-based, not layer-suffix-based: `core/`, `retrieval/`, `ingestion/`, `providers/`, `services/`, `api/`.
- Frontend groups by surface: `components/shell`, `components/chat`, `components/motion`; infrastructure under `lib/api`, `lib/store`.

**Classes / Functions:**
- Classes: `PascalCase` (`ChatTurnService`, `HybridRetriever`, `InferenceGate`, `DocStore`).
- Functions/methods: `snake_case`, verb-first (`ingest_pdf`, `delete_document`, `purge_all`, `reindex_document`, `hydrate_startup_state`).
- Router handlers: verb + resource (`list_documents`, `upload_documents`, `stream_message`, `stop_generation`).
- React components: `PascalCase`; hooks: `useXxx`.
- Constants: `UPPER_SNAKE_CASE` (`MAX_FILE_MB`, `DEFAULT_MAX_OUTPUT_TOKENS`, `SSE_HEADERS`).

**Identifiers in data:**
- Documents: `doc_<sha16>` (`ingestion/upload_validation.py:88`).
- Chat messages: `msg_<hex16>`; summaries: `summ_*`; requests: `req_<hex16>`.
- Citation tokens: `[E1]`, `[E2]` matching `EvidenceSnippet.rank`.

## Where to Add New Code

**New API endpoint:**
- Request/response models: `api/schemas/<resource>.py` (reuse `api/schemas/common.py`).
- Handler: add to the existing router in `api/routers/<resource>.py`; use `c: AppContainer = Depends(get_container)` and raise `ApiError` for failures.
- New resource: create `api/routers/<resource>.py` and register it in the tuple in `api/main.py:74`.
- Regenerate the contract: `python -m api.export_openapi` and commit `openapi.json` (CI checks drift).
- Tests: `tests/test_<resource>_api.py` using `TestClient(app)` and dependency overrides like `tests/test_chat_api_sse.py`.

**New orchestration workflow:**
- Implementation: new module in `services/`, constructed in `AppContainer.build()` (`api/container.py:45`) and exposed as a dataclass field.
- Keep it framework-free (no FastAPI imports); accept collaborators via the constructor.
- Long-running work: submit through `JobManager.submit(kind, fn)` and report via `JobHandle.progress` (`api/jobs.py:86`).

**New ingestion/extraction capability:**
- Primitive: `ingestion/<capability>.py` returning `Page`/`Chunk`/`EvidenceElement` from `core/models.py`.
- Wire it into the staged sequence in `services/ingestion.py` with a `_report(stage, pct)` call.
- Update `services/lifecycle.py:reindex_document` if the capability affects stored vectors.

**New inference provider:**
- Implement `BaseModelProvider` (`providers/model_provider.py:64`): `generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`.
- Register selection in `core/local_llm.py` (`_detect_provider`, `swap_provider`) and, for cloud, in `api/cloud_state.py` plus the provider literal in `api/schemas/settings.py`.
- Tests: `tests/test_<provider>_provider.py` with mocked HTTP/SDK clients.

**New retrieval behavior:**
- Extend `HybridRetriever.search_hybrid` / `fetch_document_chunks` rather than adding a parallel search path (see `retrieval/hybrid_retriever.py:959`, `641`).
- Keep the return type `RetrievalResult` and populate `explanation` if the UI must show it.

**New frontend page:**
- Page: `frontend/src/app/(shell)/<name>/page.tsx` (`"use client"`).
- Navigation: add an entry to `NAV_ITEMS` in `frontend/src/components/shell/sidebar.tsx:21`.
- Data: add hooks to `frontend/src/lib/api/queries.ts` and types to `frontend/src/lib/api/types.ts`.
- New backend-driven component: place it under `frontend/src/components/chat/` or `components/shell/` depending on scope.

**Shared helper:**
- Python: `core/` for domain-agnostic helpers (e.g., `redaction.py`, `limits.py`), not in routers.
- Frontend: `frontend/src/lib/utils.ts` for generic helpers; `lib/api/` for transport concerns.

**Tests for a bug fix:**
- Add a focused module matching the touched area (`tests/test_<area>.py`) and follow the offline fixture style in `tests/conftest.py`.

## Special Directories

**`data/`:**
- Purpose: SQLite DB, LanceDB index, extraction cache, logs, optional originals.
- Generated: Yes (at runtime).
- Committed: No (`.gitignore` excludes `data/`).

**`frontend/node_modules/`, `frontend/.next/`, `frontend/out/`:**
- Purpose: Dependencies, dev build cache, static export consumed by FastAPI.
- Generated: Yes.
- Committed: No (`node_modules/`, `.next/`, `out/` are ignored).

**`__pycache__/`, `.pytest_cache/`:**
- Purpose: Python/pytest caches.
- Generated: Yes.
- Committed: No.

**`tests/data/corpus/`:**
- Purpose: Deterministic PDF fixtures.
- Generated: Yes, by `generate_corpus.py`, but the PDFs are present in the repo and regenerated in CI.
- Committed: Yes.

**`assets/`:**
- Purpose: Brand mark and monochrome SVG icon set.
- Generated: Partly (`scripts/generate_icons.py`).
- Committed: Yes. Note: current UI uses `lucide-react`; `assets/icons` is a legacy Streamlit-era set.

**`application_screenshots/`:**
- Purpose: Demo images referenced by README.
- Generated: No.
- Committed: Yes.

**`.planning/`:**
- Purpose: GSD planning artifacts (project, roadmap, phases, debug notes).
- Generated: Yes, by GSD workflows.
- Committed: Yes (GSD-managed).

---

*Structure analysis: 2026-11-14*
