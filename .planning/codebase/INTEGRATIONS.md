# External Integrations

**Analysis Date:** 2026-10-10

## APIs & External Services

**LLM Inference — Groq Cloud API:**
- Purpose: sole answer-generation backend; streams chat completions token-by-token into the Streamlit UI
  - Where used: `local_llm.py:7-9` (SDK import with `ImportError` guard), `local_llm.py:18` (model id), `local_llm.py:32-33` (client construction), `local_llm.py:73-78` (streaming call), `local_llm.py:80-82` (token yield loop); status/UI labels in `main.py:90`, `main.py:98`, `main.py:175`; invoked per question in `main.py:233-238`
  - SDK/Client: `groq==0.15.0` package, `groq.Groq` class (`local_llm.py:7,33`)
  - Model: `openai/gpt-oss-20b` hardcoded as `self.model_name` (`local_llm.py:18`)
  - Call shape: `self.groq_client.chat.completions.create(messages=messages, model=self.model_name, stream=True, max_tokens=1024)` (`local_llm.py:73-78`)
  - Prompt contract: system message grounded strictly to retrieved `Document Text` + `Conversation History`, with fallback `"The document does not contain information on this topic."` (`local_llm.py:56-62`); history appended verbatim then current prompt (`local_llm.py:64-70`)
  - Retrieval coupling: query contextualized as `f"{last_user_msg} {prompt}"`, top-k=10 chunks via `local_embedding.get_context(search_query, k=10)` (`local_llm.py:48-54`); sidebar source-preview search uses `k=10` separately (`main.py:216`)
  - Auth: `GROQ_API_KEY` (see Environment Configuration below)
  - Config required: valid Groq key with access to `openai/gpt-oss-20b`; without it `AiModel.__init__` raises `ValueError` (`local_llm.py:29-30`) and the whole Streamlit app fails at `load_ai_model()` (`main.py:97`)
  - Failure modes: missing `groq` package → `ImportError` with install hint (`local_llm.py:20-21`); invalid key / quota / model deprecation → exception surfaces inside `st.status` block (`main.py:96-98`); no retry, no fallback model, no offline mode

**Embeddings — HuggingFace Hub (sentence-transformers):**
- Purpose: local semantic embedding model distribution; weights downloaded once, inference runs fully offline afterward
  - Where used: `local_embedding.py:7` (import), `local_embedding.py:23` (`SentenceTransformer(self.model_name)` construction), `local_embedding.py:40` (batched `model.encode` with `normalize_embeddings=True`); default model id `all-MiniLM-L6-v2` (`local_embedding.py:13`, surfaced in UI caption `main.py:175`)
  - SDK/Client: `sentence-transformers==3.4.1` (which pulls `transformers`, `huggingface-hub`, `torch`, `tokenizers` transitively)
  - Model: `all-MiniLM-L6-v2` — 384-dim, L2-normalised vectors (`local_embedding.py:1-5`); first run downloads from HuggingFace Hub to `~/.cache/huggingface/` (`README.md:199`)
  - Auth: `HF_TOKEN` referenced only in a code comment (`main.py:66` — "make HF_TOKEN available before AiModel.__init__ reads it"); **no code path reads `HF_TOKEN`** — `grep` over `*.py` shows zero `os.environ.get("HF_TOKEN")` / `st.secrets["HF_TOKEN"]` calls. Public MiniLM model needs no token; a token would only be needed for gated/private models or to avoid Hub rate limits
  - Config required: none for default usage; outbound HTTPS to `huggingface.co` / CDN on first run only; Windows devs may need Developer Mode for Hub symlink download (`README.md:176`)
  - Failure modes: no network on first run → model download fails and `LocalEmbedding()` raises; no vendored-model or offline-cache fallback in code

**Hosting — Streamlit Community Cloud:**
- Purpose: production hosting for the Streamlit UI
  - Where used: not in code — deployment target declared in `README.md:5` and live URL `https://rag1818.streamlit.app/` (`README.md:7`); cloud secrets path exercised in `local_llm.py:24-27`
  - SDK/Client: Streamlit server `1.42.0` (`requirements.txt:1`); devcontainer preview mirrors it on port 8501 (`.devcontainer/devcontainer.json:24-32`)
  - Config required: `GROQ_API_KEY` entered in the Cloud app's Secrets panel as TOML (`GROQ_API_KEY="gsk_..."`); repo must contain `requirements.txt` + `main.py` at root (already the layout per `README.md:138-147`); no `.streamlit/config.toml` committed
  - Notes: `@st.cache_resource` (`main.py:59-67`) keeps one `AiModel` per server process; `st.session_state` index is per-browser-session and in-memory only, so dyno restarts / reboots wipe all indexed documents (documented limitation, `README.md:228`)

## Data Storage

**Databases:**
- None — no Postgres/SQLite/ORM/vector-DB integration anywhere; `grep` for `sqlalchemy|psycopg|sqlite|pinecone|weaviate|qdrant|chroma|faiss|pgvector` across `*.py` returns zero hits

**File Storage:**
- Ephemeral local temp files only for the legacy path: `save_uploaded_pdf()` writes upload bytes to `tempfile.NamedTemporaryFile(delete=False)` (`main.py:70-81`); current upload flow actually bypasses disk and passes `io.BytesIO` directly to `PdfReader` (`main.py:131-135`), so the helper is dead-ish code kept for path-based callers (`local_llm.py:41-45` fallback when `local_embedding is None`)
- No S3/GCS/Azure Blob integration; uploaded PDFs live in browser memory + `st.session_state`, never persisted

**Caching:**
- Streamlit server-side: `@st.cache_resource` memoizes `AiModel` for process lifetime (`main.py:59-67`)
- Streamlit session: `st.session_state` holds `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py:45-52`)
- HuggingFace model cache: `~/.cache/huggingface/` (`README.md:199`)
- No Redis/Memcached/CDN integration

## Authentication & Identity

**Auth Provider:**
- None — public app with no login, no user accounts, no per-user quotas
  - Implementation: anyone with the Cloud URL can upload PDFs and ask questions; `st.file_uploader` accepts any `*.pdf` (`main.py:114-120`); `Clear All` button resets session (`main.py:107-112`)
  - Implication: `GROQ_API_KEY` is server-side only (never exposed to browser); but all visitors share the same key/quota with no throttling in code

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry/Rollbar/Datadog integration

**Logs:**
- `print()` statements only: Groq init checks (`local_llm.py:16,32`), embedding load/ready (`local_embedding.py:22,24`), chunk indexing counts (`local_embedding.py:59`), PDF extraction stats (`pdf_reader.py:60`)
- User-facing errors via `st.error` (corrupt-PDF guard, `main.py:138`) and `st.info`/`st.success` status widgets (`main.py:164-172`); no structured logging, no log levels, no log aggregation

## CI/CD & Deployment

**Hosting:**
- Streamlit Community Cloud (`https://rag1818.streamlit.app/`, `README.md:7`); GitHub repo `Vittalgb-05/RAG` is the deploy source (`README.md:163-165`)
- Devcontainers/Codespaces supported via `.devcontainer/devcontainer.json` (Python 3.11 image, auto `pip install -r requirements.txt`, auto `streamlit run` on attach)

**CI Pipeline:**
- None — no `.github/workflows/`, no `Jenkinsfile`, no `azure-pipelines.yml`, no test suite to gate on

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — **required**. Without it the app cannot start (raises `ValueError`, `local_llm.py:29-30`).
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

## Webhooks & Callbacks

**Incoming:**
- None — no webhook endpoints, no REST routes, no `st.experimental` API handlers; Streamlit's own websocket protocol (browser ↔ server on port 8501) is the only network ingress besides outbound API calls

**Outgoing:**
- `POST https://api.groq.com/openai/v1/chat/completions` (via `groq` SDK streaming, `local_llm.py:73-78`) — one call per user question (`main.py:233-238`), payload = system grounding prompt + up to last 10 history messages + current prompt (`local_llm.py:64-70`), `max_tokens=1024`
- `GET https://huggingface.co/...` + CDN (via `huggingface-hub`, first-run model download only, `local_embedding.py:23`, `README.md:199`)
- No other outbound calls — no analytics, no telemetry, no email/Slack/pager integrations

---

*Integration audit: 2026-10-10*
