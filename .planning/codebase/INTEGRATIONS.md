# External Integrations

**Analysis Date:** 2026-10-11

## APIs & External Services

**LLM Inference — Groq Cloud API:**
- Purpose: sole answer-generation backend; streams chat completions token-by-token into the Streamlit UI
  - Where used: `local_llm.py:7-9` (SDK import with `ImportError` guard), `local_llm.py:18` (model id), `local_llm.py:32-33` (client construction), `local_llm.py:73-78` (streaming call), `local_llm.py:80-82` (token yield loop); status/UI labels in `main.py:90`, `main.py:98`, `main.py:175`; invoked per question in `main.py:233-238`
  - SDK/Client: `groq==0.15.0` package, `groq.Groq` class (`local_llm.py:7,33`)
  - Model: `openai/gpt-oss-20b` hardcoded as `self.model_name` (`local_llm.py:18`); asserted in tests (`tests/test_local_llm.py:24,48`)
  - Call shape: `self.groq_client.chat.completions.create(messages=messages, model=self.model_name, stream=True, max_tokens=1024)` (`local_llm.py:73-78`)
  - Prompt contract: system message grounded strictly to retrieved `Document Text` + `Conversation History`, with fallback `"The document does not contain information on this topic."` (`local_llm.py:56-62`); history appended verbatim then current prompt (`local_llm.py:64-70`)
  - Retrieval coupling: query contextualized as `f"{last_user_msg} {prompt}"`, top-k=10 chunks via `local_embedding.get_context(search_query, k=10)` (`local_llm.py:48-54`); sidebar source-preview search uses `k=10` separately (`main.py:216`)
  - Auth: `GROQ_API_KEY` (see Environment Configuration below)
  - Config required: valid Groq key with access to `openai/gpt-oss-20b`; without it `AiModel.__init__` raises `ValueError` (`local_llm.py:29-30`) and the whole Streamlit app fails at `load_ai_model()` (`main.py:97`)
  - Failure modes: missing `groq` package → `ImportError` with install hint (`local_llm.py:20-21`); invalid key / quota / model deprecation → exception surfaces inside `st.status` block (`main.py:96-98`); no retry, no fallback model, no offline mode
  - Test seam: `mock_groq_client` fixture patches `local_llm.Groq` with a `MagicMock` whose `chat.completions.create` yields 5 canned `delta.content` tokens (`tests/conftest.py:19-48`); prompt-assembly test asserts model/stream/system-message/history wiring (`tests/test_local_llm.py:21-62`); streaming test asserts exact token passthrough (`tests/test_local_llm.py:65-80`); no live Groq call is made in tests

**Embeddings — HuggingFace Hub (sentence-transformers):**
- Purpose: local semantic embedding model distribution; weights downloaded once, inference runs fully offline afterward
  - Where used: `local_embedding.py:7` (import), `local_embedding.py:23` (`SentenceTransformer(self.model_name)` construction), `local_embedding.py:40` (batched `model.encode` with `normalize_embeddings=True`); default model id `all-MiniLM-L6-v2` (`local_embedding.py:13`, surfaced in UI caption `main.py:175`); CPU-pinned in benchmark (`SentenceTransformer("all-MiniLM-L6-v2", device="cpu")`, `scripts/benchmark_baseline.py:70`)
  - SDK/Client: `sentence-transformers==3.4.1` (which pulls `transformers`, `huggingface-hub`, `torch`, `tokenizers` transitively)
  - Model: `all-MiniLM-L6-v2` — 384-dim, L2-normalised vectors (`local_embedding.py:1-5`); first run downloads from HuggingFace Hub to `~/.cache/huggingface/` (`README.md:199`)
  - Auth: `HF_TOKEN` referenced only in a code comment (`main.py:66` — "make HF_TOKEN available before AiModel.__init__ reads it"); **no code path reads `HF_TOKEN`** — `grep` over `*.py` shows zero `os.environ.get("HF_TOKEN")` / `st.secrets["HF_TOKEN"]` calls. Public MiniLM model needs no token; a token would only be needed for gated/private models or to avoid Hub rate limits
  - Config required: none for default usage; outbound HTTPS to `huggingface.co` / CDN on first run only; Windows devs may need Developer Mode for Hub symlink download (`README.md:176`)
  - Failure modes: no network on first run → model download fails and `LocalEmbedding()` raises; no vendored-model or offline-cache fallback in code
  - Test seam: `mock_sentence_transformer` fixture patches `local_embedding.SentenceTransformer` with a `MagicMock` returning deterministic 384-dim L2-normalised `float32` vectors derived from text length (`tests/conftest.py:51-81`); used by all 3 embedding tests (`tests/test_local_embedding.py:10,17,31`); no model download or GPU/CPU inference in tests

**Hosting — Streamlit Community Cloud:**
- Purpose: production hosting for the Streamlit UI
  - Where used: not in code — deployment target declared in `README.md:5` and live URL `https://rag1818.streamlit.app/` (`README.md:7`); cloud secrets path exercised in `local_llm.py:24-27`
  - SDK/Client: Streamlit server `1.42.0` (`requirements.txt:1`); devcontainer preview mirrors it on port 8501 (`.devcontainer/devcontainer.json:24-32`)
  - Config required: `GROQ_API_KEY` entered in the Cloud app's Secrets panel as TOML (`GROQ_API_KEY="gsk_..."`); repo must contain `requirements.txt` + `main.py` at root (already the layout per `README.md:138-147`); no `.streamlit/config.toml` committed
  - Notes: `@st.cache_resource` (`main.py:59-67`) keeps one `AiModel` per server process; `st.session_state` index is per-browser-session and in-memory only, so dyno restarts / reboots wipe all indexed documents (documented limitation, `README.md:228`)

**CI — GitHub Actions:**
- Purpose: lint + test gate on `main` for pushes and pull requests
  - Where defined: `.github/workflows/ci.yml` (40 lines); job `test` on `ubuntu-latest` with Python 3.11 (`actions/setup-python@v5`, pip cache enabled)
  - Steps: `actions/checkout@v4` → install `requirements.txt` + `pytest pytest-mock reportlab ruff psutil` → `ruff check .` → `python tests/data/corpus/generate_corpus.py` (builds 6 synthetic PDFs so `tests/test_pdf_reader.py` corpus assertions pass) → `pytest tests/ -v`
  - External services used: `github.com` (checkout), `pypi.org` (pip installs), `huggingface.co` + CDN indirectly (only if a test path constructs a real `SentenceTransformer` — currently all embedding tests use the mock, so CI makes zero Hub calls by default)
  - Secrets required: none — the suite injects `GROQ_API_KEY=gsk_mock_test_key_...` via the `fake_env_groq_key` fixture (`tests/conftest.py:13-16`) and never touches a real Groq key

## Data Storage

**Databases:**
- None — no Postgres/SQLite/ORM/vector-DB integration anywhere; `grep` for `sqlalchemy|psycopg|sqlite|pinecone|weaviate|qdrant|chroma|faiss|pgvector` across `*.py` returns zero hits

**File Storage:**
- Ephemeral local temp files only for the legacy path: `save_uploaded_pdf()` writes upload bytes to `tempfile.NamedTemporaryFile(delete=False)` (`main.py:70-81`); current upload flow actually bypasses disk and passes `io.BytesIO` directly to `PdfReader` (`main.py:131-135`), so the helper is dead-ish code kept for path-based callers (`local_llm.py:41-45` fallback when `local_embedding is None`)
- Generated test corpus on disk (gitignored or generated at CI time): 6 synthetic PDFs under `tests/data/corpus/` built by `tests/data/corpus/generate_corpus.py:187-207` (`clean_digital.pdf` 20 pages, `multi_column.pdf`, `dense_table.pdf`, `scanned_sample.pdf` raster-only, `chart_diagram.pdf`, `corrupt_invalid.pdf` invalid magic bytes)
- Benchmark report artifact: `.planning/research/BASELINE_BENCHMARK.json` written by `scripts/benchmark_baseline.py:161-164` (extraction/chunking/embedding/scan latencies + RSS memory profile)
- No S3/GCS/Azure Blob integration; uploaded PDFs live in browser memory + `st.session_state`, never persisted

**Caching:**
- Streamlit server-side: `@st.cache_resource` memoizes `AiModel` for process lifetime (`main.py:59-67`)
- Streamlit session: `st.session_state` holds `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py:45-52`)
- HuggingFace model cache: `~/.cache/huggingface/` (`README.md:199`)
- pip cache in CI via `actions/setup-python@v5` `cache: "pip"` (`.github/workflows/ci.yml:21`)
- No Redis/Memcached/CDN integration

## Authentication & Identity

**Auth Provider:**
- None — public app with no login, no user accounts, no per-user quotas
  - Implementation: anyone with the Cloud URL can upload PDFs and ask questions; `st.file_uploader` accepts any `*.pdf` (`main.py:114-120`); `Clear All` button resets session (`main.py:107-112`)
  - Implication: `GROQ_API_KEY` is server-side only (never exposed to browser); but all visitors share the same key/quota with no throttling in code

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry/Rollbar/Datadog integration; CI surfaces failures as GitHub Actions job logs only

**Logs:**
- `print()` statements only: Groq init checks (`local_llm.py:16,32`), embedding load/ready (`local_embedding.py:22,24`), chunk indexing counts (`local_embedding.py:59`), PDF extraction stats (`pdf_reader.py:60`), benchmark stage/metrics prints (`scripts/benchmark_baseline.py:29-39,51-54,61-62,74-75,92,123,126,166-167`), corpus generator summary (`tests/data/corpus/generate_corpus.py:212-214`)
- User-facing errors via `st.error` (corrupt-PDF guard, `main.py:138`) and `st.info`/`st.success` status widgets (`main.py:164-172`); no structured logging, no log levels, no log aggregation

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (`https://rag1818.streamlit.app/`, `README.md:7`); GitHub repo `Vittalgb-05/RAG` is the deploy source (`README.md:163-165`)
- Devcontainers/Codespaces supported via `.devcontainer/devcontainer.json` (Python 3.11 image, auto `pip install -r requirements.txt`, auto `streamlit run` on attach)

**CI Pipeline:**
- GitHub Actions workflow `.github/workflows/ci.yml`: triggers on `push`/`pull_request` to `main`; single `test` job (Lint & Test Suite, Python 3.11, `ubuntu-latest`)
- Gate order: `ruff check .` (fail-fast lint) → corpus generation → `pytest tests/ -v` (17 tests across `test_vector_index.py` ×7, `test_pdf_reader.py` ×4, `test_local_embedding.py` ×3, `test_local_llm.py` ×3)
- No CD step — Streamlit Cloud auto-deploys from `main` independently of CI status; no Docker build/push, no artifact upload

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — **required at app runtime**. Without it the app cannot start (raises `ValueError`, `local_llm.py:29-30`). In tests it is faked (`gsk_mock_test_key_1234567890abcdef` via `tests/conftest.py:16`) or deleted to assert the guard (`tests/test_local_llm.py:16`); CI needs no real key.
- `HF_TOKEN` — **not required** despite the comment in `main.py:66`. No code reads it; only relevant if switching to a gated HuggingFace embedding model.

**Secrets location / resolution order:**
1. `st.secrets["GROQ_API_KEY"]` — Streamlit Cloud secrets panel / local `.streamlit/secrets.toml` (tried first, `local_llm.py:24-27`); `KeyError`/`FileNotFoundError` falls through silently
2. `os.environ.get("GROQ_API_KEY")` — local `.env` file via `load_dotenv()` (`main.py:66`) or shell-exported var (`local_llm.py:27`)
3. Neither present → `ValueError("GROQ_API_KEY is not set. Please add it to your Streamlit secrets or .env file.")` (`local_llm.py:30`)

**Local setup (from `README.md:178-187`):**
```toml
# .streamlit/secrets.toml  (Cloud + optional local alternative — file does NOT exist in repo)
GROQ_API_KEY = "gsk_your_groq_key_here"
```
```
# .env  (local dev — file does NOT exist in repo, gitignored via .gitignore:1)
GROQ_API_KEY=gsk_your_groq_keyhere
```
- `.env` presence verified: absent from working tree (only `.gitignore` references it). `.streamlit/` directory verified: absent. Secret *values* were never read and are not present in the repo.

**st.secrets vs .env — which to use when:**
- Local development → `.env` + `load_dotenv()` (`main.py:66`, `README.md:178-182`)
- Streamlit Community Cloud → Cloud Secrets panel (read via `st.secrets`, `local_llm.py:25`, `README.md:222`); `.env` is gitignored and never deployed, so committing keys is neither needed nor safe
- Tests/CI → `monkeypatch.setenv` fake key (`tests/conftest.py:13-16`); never a real secret

## Test Mocking Seams (offline boundaries)

All external network calls are severed in tests via `tests/conftest.py` (88 lines, 4 fixtures):

| Fixture | Patches | Yields | Consumed by |
|---|---|---|---|
| `fake_env_groq_key` | `os.environ[GROQ_API_KEY]` via `monkeypatch.setenv` (`tests/conftest.py:13-16`) | Fake key `gsk_mock_test_key_1234567890abcdef` | `tests/test_local_llm.py:21,65` |
| `mock_groq_client` | `local_llm.Groq` → `lambda api_key=None: mock_client` (`tests/conftest.py:46-47`) | `MagicMock` streaming 5 canned tokens `["This ", "is ", "a ", "grounded ", "answer."]` (`tests/conftest.py:39-44`) | `tests/test_local_llm.py:21,65` |
| `mock_sentence_transformer` | `local_embedding.SentenceTransformer` → `lambda model_name: mock_model` (`tests/conftest.py:79-80`) | Deterministic 384-dim normalised `float32` vectors (`tests/conftest.py:59-75`) | `tests/test_local_embedding.py:10,17,31` |
| `sample_pdf_path` | None (path helper) | `tests/data/corpus/clean_digital.pdf` path (`tests/conftest.py:84-88`) | Available for future tests (currently unused; `test_pdf_reader.py` uses its own `CORPUS_DIR` constant) |

- `test_vector_index.py` and `test_pdf_reader.py` need no mocks: `VectorIndex` is pure stdlib, and `PdfReader` tests run against locally generated corpus PDFs (no network).
- Tests that bypass retrieval with `MagicMock().get_context` (`tests/test_local_llm.py:26-27,69-70`) additionally isolate the Groq prompt-assembly layer from the embedding layer.
- Net effect: `pytest tests/ -v` runs 100% offline — zero Groq API calls, zero HuggingFace downloads, zero GPU allocation (per the header contract in `tests/conftest.py:1-4`).

## Webhooks & Callbacks

**Incoming:**
- None — no webhook endpoints, no REST routes, no `st.experimental` API handlers; Streamlit's own websocket protocol (browser ↔ server on port 8501) is the only network ingress besides outbound API calls; GitHub Actions `push`/`pull_request` triggers (`.github/workflows/ci.yml:3-7`) are repo events, not app webhooks

**Outgoing:**
- `POST https://api.groq.com/openai/v1/chat/completions` (via `groq` SDK streaming, `local_llm.py:73-78`) — one call per user question (`main.py:233-238`), payload = system grounding prompt + up to last 10 history messages + current prompt (`local_llm.py:64-70`), `max_tokens=1024`
- `GET https://huggingface.co/...` + CDN (via `huggingface-hub`, first-run model download only, `local_embedding.py:23`, `README.md:199`; CPU-pinned re-download path in `scripts/benchmark_baseline.py:70`)
- `pip install` egress in CI to `pypi.org` (`.github/workflows/ci.yml:26-28`); `actions/checkout`/`setup-python` egress to GitHub/Azure endpoints (`.github/workflows/ci.yml:15-21`)
- No other outbound calls — no analytics, no telemetry, no email/Slack/pager integrations

---

*Integration audit: 2026-10-11*
