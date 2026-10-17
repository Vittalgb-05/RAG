<!-- refreshed: 2026-10-17 -->
# External Integrations

**Analysis Date:** 2026-10-17

## APIs & External Services

**Local Inference (no network egress):**
- llama-server (llama.cpp) — primary LLM/VLM backend, `Qwen3-VL 2B Q4_K_M` GGUF + `mmproj-f16` vision projector
  - SDK/Client: `httpx.Client` (`llama_cpp_provider.py:15,63-67`); endpoints `GET /health` (`llama_cpp_provider.py:81`) and `POST /v1/chat/completions` streaming + non-streaming (`llama_cpp_provider.py:170,219,285`)
  - Endpoint: `http://127.0.0.1:8080` default (`llama_cpp_provider.py:25`)
  - Auth: none — loopback only; SSRF guard rejects non-loopback hosts unless `allow_remote=True` (`llama_cpp_provider.py:40-57`)
  - Timeouts: connect 2s, read 60s (`llama_cpp_provider.py:66`)

**Cloud LLM/VLM (consent-gated, optional — disabled by default):**
- Groq — `groq/llama-3.3-70b-versatile` default via LiteLLM (`litellm_provider.py:23`) and `openai/gpt-oss-20b` via the native Groq client (`groq_provider.py:24`)
  - SDK/Client: `litellm` (`litellm_provider.py:19,217,269,331`) and `groq.Groq` (`groq_provider.py:13,52`)
  - Auth env var: `GROQ_API_KEY` (`litellm_provider.py:46`, `groq_provider.py:42,47`)
  - Context window declared: 131,072 (`litellm_provider.py:26`); vision not supported on the text path (`groq_provider.py:163-170`)
- OpenAI — `openai/gpt-4o-mini` (vision-capable) (`main.py:175`, `litellm_provider.py:32-33`)
  - SDK/Client: `litellm`
  - Auth env var: `OPENAI_API_KEY` (`litellm_provider.py:47`, `main.py:175`)
- Anthropic — `anthropic/claude-3-5-haiku-20241022` (vision-capable) (`main.py:176`, `litellm_provider.py:34-35`)
  - SDK/Client: `litellm`
  - Auth env var: `ANTHROPIC_API_KEY` (`litellm_provider.py:48`, `main.py:176`)
- Consent gate: every cloud call invokes `_assert_consent()` first, raising `PermissionError` without explicit user consent (`litellm_provider.py:126-132,195,244,296`). Cloud mode is toggled per session in the sidebar (`main.py:138-255`).
- Retries/timeouts: `timeout=30.0`, `num_retries=2` on all LiteLLM calls (`litellm_provider.py:103-104,211-212`).

**AI/ML Model Distribution:**
- Hugging Face Hub — model weight downloads
  - GGUF mirrors configured in `setup.py:44-63`: `bartowski/Qwen2-VL-2B-Instruct-GGUF` and `lmstudio-community/Qwen2-VL-2B-Instruct-GGUF` (base + mmproj), downloaded via `urllib.request` with mirror fallback (`setup.py:87-177`)
  - `sentence-transformers` downloads `all-MiniLM-L6-v2` from HF at first use (`local_embedding.py:35`); pre-cached in setup (`setup.py:180-195`)
  - RapidOCR ONNX weights pre-cached via `RapidOCR()` init (`setup.py:198-212`)
  - No HF token read in code; docs mention `HF_HUB_DISABLE_SYMLINKS_WARNING` (`docs/RUNBOOK.md:67-70`)

**System Tooling:**
- NVIDIA `nvidia-smi` — GPU VRAM telemetry via `subprocess.run` (`resource_telemetry.py:59-70`) and compute-app query (`resource_telemetry.py:110-117`); 2s timeout, 5s TTL cache, degrades to `None` on CPU-only/CI hosts

## Data Storage

**Databases:**
- SQLite (Python stdlib `sqlite3`) — document metadata, pages, chunks, evidence elements, cached summaries
  - Location: `data/documents.db` (default path passed from `main.py`; `doc_store.py:108-116`)
  - Schema: versioned migrations v1–v3 via `PRAGMA user_version` (`doc_store.py:96-154`); WAL mode + `busy_timeout=5000` + `foreign_keys=ON` per connection (`doc_store.py:131-135`)
  - Tables: `documents`, `pages`, `chunks`, `evidence_elements`, `document_summaries` (`doc_store.py:17-94`)
  - Client: `doc_store.py` `DocStore` class (no ORM)
  - Note: SQLite is metadata/cache only; BM25 lexical search is NOT SQLite FTS5 (see below)
- LanceDB — embedded on-disk vector + full-text index
  - Location: `data/lancedb/` (default `DEFAULT_DB_URI`, `hybrid_retriever.py:27`), benchmarks use `data/lancedb_bench/`
  - Client: `lancedb` + `pyarrow` (`hybrid_retriever.py:19-24`); single `chunks` table with `merge_insert` upsert (`hybrid_retriever.py:339-359`)
  - Full-text: `create_fts_index("content")` + `search(query_type="fts")` (`hybrid_retriever.py:430-438,518-532`)
  - Fallback: if LanceDB is unavailable, a pure-Python `VectorIndex` + `data/lancedb/fallback_store.json` is used, with pure-Python BM25 (`hybrid_retriever.py:104-124,440-503`)

**File Storage:**
- Local filesystem only — `models/` (GGUF weights), `data/`, `.cache/` (extraction artifacts keyed by SHA-256). No S3/object storage (`boto3` present only as a litellm transitive dep).

**Caching:**
- SQLite `document_summaries` table keyed `UNIQUE(sha256, profile)` with `model_version` invalidation (`doc_store.py:84,494-499`; `summarizer.py:332-337`)
- Process-level `SentenceTransformer` cache `_MODEL_CACHE` keyed `(model_name, device)` (`local_embedding.py:19,22-37`)
- GPU telemetry TTL cache (5.0s) to avoid `nvidia-smi` subprocess spam (`resource_telemetry.py:26-29,46-55`)
- No Redis/Memcached/external cache.

## Authentication & Identity

**Auth Provider:**
- None — no user accounts, login, OAuth, or identity provider. Single-user workstation model (`docs/RUNBOOK.md:242-244`).
- Inference authorization is limited to a **consent gate** for cloud egress (`litellm_provider.py:126-132`) plus per-session provider/key selection (`main.py:174-197`).
- API key storage: cloud API keys are held in `st.session_state.cloud_api_keys` (session memory only, never written to disk — `README.md:210`); or resolved from `.env`/`st.secrets` (`litellm_provider.py:39-79`).

## Monitoring & Observability

**Error Tracking:**
- None — no Sentry/Datadog/etc. Errors surface via Python `logging` (`litellm_provider.py:16`, `hybrid_retriever.py:16`, etc.) and Streamlit UI (`st.error`).

**Logs:**
- Standard-library `logging` with module loggers, plus `print()` diagnostics in setup/telemetry paths (`setup.py:66-75`, `doc_store.py:154`).
- Local resource telemetry: `resource_telemetry.py` tracks GPU VRAM, process RSS/VMS, and per-stage latency (`_LATENCY_HISTORY`, `LatencyTracker`, `track_stage`) with in-process history (max 200 samples/stage).

## CI/CD & Deployment

**Hosting:**
- Primary target: local single-user workstation (`127.0.0.1`); Streamlit UI + llama-server co-located (`docs/RUNBOOK.md:240-245`).
- No committed Dockerfile, `packages.txt`, `runtime.txt`, or Streamlit Cloud config. `README.md:216` documents the hosted-deployment caveat (remote host cannot reach loopback llama-server).

**CI Pipeline:**
- GitHub Actions `.github/workflows/ci.yml` — triggers on push/PR to `main`; on `ubuntu-latest`: checkout → setup Python 3.11 → install uv → `uv pip install -r requirements-lock.txt` + `requirements-test.txt` → `ruff check .` + `ruff format --check .` → generate synthetic corpus → `pytest tests/ -v`.
- No deployment job, no release workflow.

## Environment Configuration

**Required env vars:**
- `GROQ_API_KEY` — Groq cloud (optional; required only for Cloud Mode with Groq)
- `OPENAI_API_KEY` — OpenAI via LiteLLM (optional)
- `ANTHROPIC_API_KEY` — Anthropic via LiteLLM (optional)
- Local mode with llama-server requires **no** env vars.

**Secrets location:**
- `.env` in project root (gitignored, `.gitignore:1`; **absent from the working tree** — existence only).
- Streamlit secrets (`st.secrets`) checked before env vars (`litellm_provider.py:69-77`); no `.streamlit/secrets.toml` present.
- Cloud API keys never persisted — session memory only.

## Webhooks & Callbacks

**Incoming:**
- None — no webhook endpoints. The only inbound HTTP surface is the Streamlit UI (port 8501) and the external llama-server API (port 8080, consumed, not served by this app).

**Outgoing:**
- None — no webhook/callback registration. Outbound calls are limited to (a) loopback HTTP to llama-server, (b) consented LiteLLM cloud completions, and (c) one-time model weight downloads from Hugging Face during setup.

---

*Integration audit: 2026-10-17*
