# External Integrations

**Analysis Date:** 2026-10-11

## APIs & External Services

**LLM Inference — Groq Cloud API:**
- Purpose: sole answer-generation backend; streams chat completions token-by-token into the Streamlit UI
  - Where used: `local_llm.py:6-9` (SDK import with `ImportError` guard), `local_llm.py:19` (model id), `local_llm.py:34` (client construction), `local_llm.py:75-80` (streaming call), `local_llm.py:82-84` (token yield loop); model-status label in `main.py:89`, caption in `main.py:266`; invoked per question in `main.py:321-326`
  - SDK/Client: `groq==0.15.0` package, `groq.Groq` class (`local_llm.py:7,34`)
  - Model: `openai/gpt-oss-20b` hardcoded as `self.model_name` (`local_llm.py:19`); asserted in tests (`tests/test_local_llm.py`)
  - Call shape: `self.groq_client.chat.completions.create(messages=messages, model=self.model_name, stream=True, max_tokens=1024)` (`local_llm.py:75-80`)
  - Prompt contract: system message grounded strictly to retrieved `Document Text` + `Conversation History`, with fallback `"The document does not contain information on this topic."` (`local_llm.py:58-64`); history appended verbatim then current prompt (`local_llm.py:66-72`)
  - Retrieval coupling: query contextualized as `f"{last_user_msg} {prompt}"`, top-k=10 chunks via `local_embedding.get_context(search_query, k=10)` (`local_llm.py:49-56`); sidebar source-preview search uses `k=10` separately (`main.py:306`)
  - Auth: `GROQ_API_KEY` (see Environment Configuration below)
  - Config required: valid Groq key with access to `openai/gpt-oss-20b`; without it `AiModel.__init__` raises `ValueError` (`local_llm.py:30-31`) and the whole Streamlit app fails at `load_ai_model()` (`main.py:65-73`, called at `main.py:88`)
  - Failure modes: missing `groq` package → `ImportError` with install hint (`local_llm.py:21-22`); invalid key / quota / model deprecation → exception surfaces inside `st.status` block (`main.py:87-89`); no retry, no fallback model, no offline mode
  - Test seam: `mock_groq_client` fixture patches `local_llm.Groq` with a `MagicMock` whose `chat.completions.create` yields 5 canned `delta.content` tokens (`tests/conftest.py:18-48`); no live Groq call is made in tests

**Embeddings — HuggingFace Hub (sentence-transformers):**
- Purpose: local semantic embedding model distribution; weights downloaded once, inference runs fully offline afterward
  - Where used: `local_embedding.py:7` (import), `local_embedding.py:22` (`SentenceTransformer(self.model_name)` construction), `local_embedding.py:39` (batched `model.encode` with `normalize_embeddings=True`); default model id `all-MiniLM-L6-v2` (`local_embedding.py:12`, surfaced in UI caption `main.py:266`); CPU-pinned in benchmark (`SentenceTransformer("all-MiniLM-L6-v2", device="cpu")`, `scripts/benchmark_baseline.py:70`)
  - SDK/Client: `sentence-transformers==3.4.1` (which pulls `transformers`, `huggingface-hub`, `torch`, `tokenizers` transitively); `numpy>=1.26.0,<3.0.0` backs vector math (`requirements.txt:7`)
  - Model: `all-MiniLM-L6-v2` — 384-dim, L2-normalised vectors (`local_embedding.py:1-5`); first run downloads from HuggingFace Hub to `~/.cache/huggingface/` (`README.md:199`)
  - Auth: none — no code path reads any HuggingFace token. Public MiniLM model needs no token; a token would only be needed for gated/private models or to avoid Hub rate limits
  - Config required: none for default usage; outbound HTTPS to `huggingface.co` / CDN on first run only; Windows devs may need Developer Mode for Hub symlink download (`README.md:176`)
  - Failure modes: no network on first run → model download fails and `LocalEmbedding()` raises; no vendored-model or offline-cache fallback in code
  - Test seam: `mock_sentence_transformer` fixture patches `local_embedding.SentenceTransformer` with a `MagicMock` returning deterministic 384-dim L2-normalised `float32` vectors derived from text length (`tests/conftest.py:51-81`); used by all 3 embedding tests (`tests/test_local_embedding.py`); no model download or GPU/CPU inference in tests

**Hosting — Streamlit Community Cloud:**
- Purpose: production hosting for the Streamlit UI
  - Where used: not in code — deployment target declared in `README.md:5` and live URL `https://rag1818.streamlit.app/` (`README.md:7`); cloud secrets path exercised in `local_llm.py:25-28`
  - SDK/Client: Streamlit server `1.42.0` (`requirements.txt:1`); devcontainer preview mirrors it on port 8501 (`.devcontainer/devcontainer.json:24-32`)
  - Config required: `GROQ_API_KEY` entered in the Cloud app's Secrets panel as TOML (`GROQ_API_KEY="gsk_..."`); repo must contain `requirements.txt` + `main.py` at root; no `.streamlit/config.toml` committed
  - Persistence caveat: `@st.cache_resource` (`main.py:65-73`) keeps one `AiModel` per server process; the vector index in `st.session_state` is per-browser-session and in-memory only, so dyno restarts wipe indexed vectors. SQLite (`data/documents.db`) and `.cache/` JSON survive only if the host provides a persistent volume — Community Cloud does not guarantee one, so re-upload may still be required after restarts
  - Notes: `numpy` range pin (`>=1.26.0,<3.0.0`) and `pydantic==2.11.9` must both install cleanly on the Cloud runner; both are pure-pip with wheels for Python 3.11

**CI — GitHub Actions:**
- Purpose: lint + format + test gate on `main` for pushes and pull requests
  - Where defined: `.github/workflows/ci.yml` (41 lines); job `test` on `ubuntu-latest` with Python 3.11 (`actions/setup-python@v5`, pip cache enabled, `.github/workflows/ci.yml:18-22`)
  - Steps: `actions/checkout@v4` → install `requirements.txt` + `requirements-test.txt` (`.github/workflows/ci.yml:24-28`) → `ruff check .` + `ruff format --check .` (`.github/workflows/ci.yml:30-33`) → `python tests/data/corpus/generate_corpus.py` (builds 6 synthetic PDFs so corpus assertions pass, `.github/workflows/ci.yml:35-37`) → `pytest tests/ -v` (`.github/workflows/ci.yml:39-41`)
  - External services used: `github.com` (checkout), `pypi.org` (pip installs for `pydantic`, `numpy`, `pytest`, `reportlab`, `ruff`, `psutil`), `huggingface.co` + CDN indirectly (only if a test path constructs a real `SentenceTransformer` — currently all embedding tests use the mock, so CI makes zero Hub calls by default)
  - Secrets required: none — the suite injects `GROQ_API_KEY=test-key-not-a-secret-mock-value` via the `fake_env_groq_key` fixture (`tests/conftest.py:12-15`) and never touches a real Groq key

## Data Storage

**Databases — SQLite local persistence:**
- Engine: CPython stdlib `sqlite3` — no server, no ORM, no extra pip package (`doc_store.py:12`)
  - Implementation: `DocStore` class (`doc_store.py:61-307`) with per-operation connection lifecycles (Windows file-lock + Streamlit-rerun safe)
  - Connection setup per operation: `sqlite3.connect(str(db_path), timeout=5.0)`, `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000` (`doc_store.py:89-96`)
  - Schema versioning: `MIGRATIONS: dict[int, list[str]] = {1: SCHEMA_V1_DDL}` applied against `PRAGMA user_version` (`doc_store.py:56-58,98-111`); v1 creates three tables:
    - `documents(doc_id PK, filename, sha256 UNIQUE, size_bytes, num_pages, status, upload_time, num_chunks)` (`doc_store.py:17-28`)
    - `pages(doc_id, page_num, status, char_count, error, num_chunks; PK(doc_id, page_num))` (`doc_store.py:29-39`)
    - `chunks(chunk_id PK, doc_id, filename, page, content, char_start, char_end, bbox_json NULL, extraction DEFAULT 'pypdf', embedding_model NULL)` (`doc_store.py:40-53`)
  - Write API: `upsert_document(doc)` (`doc_store.py:113-148`), `record_page(page)` (`doc_store.py:202-233`), `record_chunks(chunks)` single-transaction `executemany` (`doc_store.py:235-283`); read API: `get_document(doc_id)` (`doc_store.py:150-168`), `get_by_sha(sha256)` for dedup (`doc_store.py:170-188`), `list_documents()` ordered by `upload_time DESC` (`doc_store.py:190-200`), `get_chunks_for_doc(doc_id)` ordered by `page ASC, rowid ASC` with `bbox_json` → `BBox` rehydration (`doc_store.py:285-307`)
  - Type bridge: rows validated into Pydantic models via `Document.model_validate(dict(row))` / `Chunk.model_validate(...)` (`doc_store.py:168,188,200,306`); `bbox` serialized with `model_dump_json()` (`doc_store.py:265`)
  - DB file: `data/documents.db`, constructed as `DocStore(Path("data/documents.db"))` per upload batch (`main.py:118`); parent dirs auto-created (`doc_store.py:73-74`); `data/` is gitignored (`.gitignore:10`) and absent from a fresh checkout (verified — no `data/` directory exists until first upload)
  - Write flow in app: per-page `record_page` with progress bar (`main.py:189-193`) → `record_chunks` after embedding (`main.py:202-203`) → `upsert_document` with `sqlite3.IntegrityError` guard (`main.py:206-219`)
  - Dedup/restore flow: `get_by_sha` short-circuits re-indexing (`main.py:147`); on dedup hit after restart with empty session index, chunks are restored from `get_chunks_for_doc` and rebuilt into a fresh `LocalEmbedding` (`main.py:161-168`)
  - WAL sidecars (`documents.db-wal`, `documents.db-shm`) appear alongside the DB at runtime; never commit them
  - Test seam: `tests/test_doc_store.py` (9 tests) exercises the full API against `tmp_path` databases — zero production-DB coupling

**File Storage:**
- Disk cache layout (best-effort, STORE-03): `.cache/<sha256>/<CONFIG_VERSION>/` computed by `cache_dir_for(Path(".cache"), sha256)` (`models.py:17-30`, `CONFIG_VERSION = "chunker-1000-200-pypdf"` in `models.py:14`); three JSON artifacts per document written in `main.py:222-230` — `pages.json` (list of `Page.model_dump()`), `chunks.json` (chunk dicts), `manifest.json` (`Document.model_dump()`); wrapped in `try/except OSError` so cache failure only warns (`main.py:231-232`); `.cache/` is gitignored (`.gitignore:17`) and ephemeral (verified — absent from working tree until first upload)
- Uploaded PDF bytes: single in-memory read per file via `uploaded_file.getvalue()` (`main.py:135`); pre-buffer size gate via `uploaded_file.size` (`main.py:124-132`, cap `MAX_FILE_MB = 50` from `upload_validation.py:15`); passed as `io.BytesIO(raw_bytes)` to `PdfReader` (`main.py:178`) — never written to disk in the current flow
- Chunk IDs are content-hash prefixed: `{sha12}_p{page}_{idx:04d}` (`pdf_reader.py:76`), with `doc_id` threaded from validation (`main.py:181-182`)
- Generated test corpus on disk: 6 synthetic PDFs under `tests/data/corpus/` built by `tests/data/corpus/generate_corpus.py` (`clean_digital.pdf` 20 pages, `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf` raster-only, `chart_diagram.pdf`, `corrupt_invalid.pdf` invalid magic bytes)
- Benchmark report artifact: `.planning/research/BASELINE_BENCHMARK.json` written by `scripts/benchmark_baseline.py`
- No S3/GCS/Azure Blob integration

**Caching:**
- Streamlit server-side: `@st.cache_resource` memoizes `AiModel` for process lifetime (`main.py:65-73`)
- Streamlit session: `st.session_state` holds `doc_ids`, `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py:49-57`)
- SQLite dedup cache: `doc_store.get_by_sha()` short-circuits re-indexing of already-`indexed` documents across restarts (`main.py:147-168`)
- HuggingFace model cache: `~/.cache/huggingface/` (`README.md:199`)
- pip cache in CI via `actions/setup-python@v5` `cache: "pip"` (`.github/workflows/ci.yml:22`)
- No Redis/Memcached/CDN integration

## Authentication & Identity

**Auth Provider:**
- None — public app with no login, no user accounts, no per-user quotas
  - Implementation: anyone with the Cloud URL can upload PDFs and ask questions; `st.file_uploader` accepts any `*.pdf` (`main.py:106-112`) with server-side validation in `upload_validation.py` (`%PDF` magic bytes at `upload_validation.py:79-80`, 50 MB cap `MAX_FILE_MB`, 500-page cap `MAX_PAGES` at `upload_validation.py:15-16`, pypdf readability probe at `upload_validation.py:90-100`); `Clear All` button resets session (`main.py:98-104`)
  - Implication: `GROQ_API_KEY` is server-side only (never exposed to browser); but all visitors share the same key/quota with no throttling in code

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry/Rollbar/Datadog integration; CI surfaces failures as GitHub Actions job logs only

**Logs:**
- `print()` statements only: Groq init checks (`local_llm.py:17,33`), embedding load/ready (`local_embedding.py:21,23`), chunk indexing counts (`local_embedding.py:58`), PDF extraction stats (`pdf_reader.py:113`), upload validation (`upload_validation.py:106`), DocStore migrations (`doc_store.py:111`), benchmark stage/metrics prints (`scripts/benchmark_baseline.py:29-77`), corpus generator summary
- User-facing errors via `st.error` (oversize pre-check `main.py:129-131`, validation failures `main.py:142`, corrupt-PDF path `main.py:186`), `st.warning` (failed pages `main.py:193`, cache-write failure `main.py:232`), and `st.info`/`st.success` status widgets (`main.py:150,243,259-261`); no structured logging, no log levels, no log aggregation

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (`https://rag1818.streamlit.app/`, `README.md:7`); GitHub repo is the deploy source
- Devcontainers/Codespaces supported via `.devcontainer/devcontainer.json` (33 lines: Python 3.11 image, `ms-python.python` + `ms-python.vscode-pylance` extensions, auto `pip install -r requirements.txt` on update, auto `streamlit run` with CORS/XSRF disabled on attach at `.devcontainer/devcontainer.json:20-23`)

**CI Pipeline:**
- GitHub Actions workflow `.github/workflows/ci.yml` (41 lines): triggers on `push`/`pull_request` to `main`; single `test` job (Lint & Test Suite, Python 3.11, `ubuntu-latest`)
- Gate order: `ruff check .` + `ruff format --check .` (fail-fast lint/format) → corpus generation → `pytest tests/ -v` (54 tests across 7 files: `test_models.py` ×15, `test_pdf_reader.py` ×9, `test_doc_store.py` ×9, `test_upload_validation.py` ×8, `test_vector_index.py` ×7, `test_local_embedding.py` ×3, `test_local_llm.py` ×3)
- Dependency install: `pip install -r requirements.txt` (runtime incl. `pydantic==2.11.9`, `numpy>=1.26.0,<3.0.0`) + `pip install -r requirements-test.txt` (`pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0`)
- No CD step — Streamlit Cloud auto-deploys from `main` independently of CI status; no Docker build/push, no artifact upload

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — **required at app runtime**. Without it the app cannot start (raises `ValueError`, `local_llm.py:30-31`). In tests it is faked (`test-key-not-a-secret-mock-value` via `tests/conftest.py:15`) or deleted to assert the guard (`tests/test_local_llm.py`); CI needs no real key.

**Secrets location / resolution order:**
1. `st.secrets["GROQ_API_KEY"]` — Streamlit Cloud secrets panel / local `.streamlit/secrets.toml` (tried first, `local_llm.py:25-28`); `KeyError`/`FileNotFoundError` falls through silently
2. `os.environ.get("GROQ_API_KEY")` — local `.env` file via `load_dotenv()` (`main.py:72`) or shell-exported var (`local_llm.py:28`)
3. Neither present → `ValueError("GROQ_API_KEY is not set. Please add it to your Streamlit secrets or .env file.")` (`local_llm.py:31`)

**Local setup (from `README.md:181-186`):**
```toml
# .streamlit/secrets.toml  (Cloud + optional local alternative — file does NOT exist in repo)
GROQ_API_KEY = "gsk_your_groq_key_here"
```
```
# .env  (local dev — file does NOT exist in repo, gitignored via .gitignore:1)
GROQ_API_KEY=gsk_your_groq_key_here
```
- `.env` presence verified: absent from working tree (only `.gitignore` references it). `.streamlit/` directory verified: absent. `data/` and `.cache/` verified: absent until first upload. Secret *values* were never read and are not present in the repo.

**st.secrets vs .env — which to use when:**
- Local development → `.env` + `load_dotenv()` (`main.py:72`, `README.md:181`)
- Streamlit Community Cloud → Cloud Secrets panel (read via `st.secrets`, `local_llm.py:26`); `.env` is gitignored and never deployed, so committing keys is neither needed nor safe
- Tests/CI → `monkeypatch.setenv` fake key (`tests/conftest.py:12-15`); never a real secret

## Test Mocking Seams (offline boundaries)

All external network calls are severed in tests via `tests/conftest.py` (88 lines, 4 fixtures):

| Fixture | Patches | Yields | Consumed by |
|---|---|---|---|
| `fake_env_groq_key` | `os.environ[GROQ_API_KEY]` via `monkeypatch.setenv` (`tests/conftest.py:12-15`) | Fake key `test-key-not-a-secret-mock-value` | `tests/test_local_llm.py` |
| `mock_groq_client` | `local_llm.Groq` → `lambda api_key=None: mock_client` (`tests/conftest.py:47`) | `MagicMock` streaming 5 canned tokens `["This ", "is ", "a ", "grounded ", "answer."]` (`tests/conftest.py:38-43`) | `tests/test_local_llm.py` |
| `mock_sentence_transformer` | `local_embedding.SentenceTransformer` → `lambda model_name: mock_model` (`tests/conftest.py:80`) | Deterministic 384-dim normalised `float32` vectors (`tests/conftest.py:59-74`) | `tests/test_local_embedding.py` |
| `sample_pdf_path` | None (path helper) | `tests/data/corpus/clean_digital.pdf` path (`tests/conftest.py:84-88`) | Available for future tests |

- `test_vector_index.py`, `test_models.py`, `test_upload_validation.py` need no mocks: `VectorIndex` is pure stdlib, Pydantic validation is local, and upload validation runs against in-memory bytes (magic-byte/size/page-limit guards need no network).
- `test_doc_store.py` (9 tests) runs against `tmp_path` SQLite files — exercises WAL mode, migrations, upsert/get/dedup/chunk round-trip with zero production-DB coupling.
- `test_pdf_reader.py` (9 tests) runs against locally generated corpus PDFs (no network).
- Tests that bypass retrieval with `MagicMock().get_context` additionally isolate the Groq prompt-assembly layer from the embedding layer.
- Net effect: `pytest tests/ -v` runs 100% offline — zero Groq API calls, zero HuggingFace downloads, zero GPU allocation (per the header contract in `tests/conftest.py:1-4`).

## Webhooks & Callbacks

**Incoming:**
- None — no webhook endpoints, no REST routes; Streamlit's own websocket protocol (browser ↔ server on port 8501) is the only network ingress besides outbound API calls; GitHub Actions `push`/`pull_request` triggers (`.github/workflows/ci.yml:3-7`) are repo events, not app webhooks

**Outgoing:**
- `POST https://api.groq.com/openai/v1/chat/completions` (via `groq` SDK streaming, `local_llm.py:75-80`) — one call per user question (`main.py:321-326`), payload = system grounding prompt + up to last 10 history messages + current prompt (`local_llm.py:66-72`, history sliced at `main.py:319`), `max_tokens=1024`
- `GET https://huggingface.co/...` + CDN (via `huggingface-hub`, first-run model download only, `local_embedding.py:22`, `README.md:199`; CPU-pinned re-download path in `scripts/benchmark_baseline.py:70`)
- `pip install` egress in CI to `pypi.org` (`.github/workflows/ci.yml:24-28`); `actions/checkout`/`setup-python` egress to GitHub/Azure endpoints (`.github/workflows/ci.yml:15-22`)
- No other outbound calls — no analytics, no telemetry, no email/Slack/pager integrations

---

*Integration audit: 2026-10-11*
