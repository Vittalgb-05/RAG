# Endpoint & Integration Matrix

**Date:** 2026-10-21
**Rule:** The application exposes no document-processing HTTP API. All inference is outbound to a provider (local loopback by default) and all persistence is embedded (SQLite, LanceDB, filesystem). The only inbound listener is the Streamlit UI.

## Inbound

| Interface | Direction | Default address | Auth | Code | Verification |
|---|---|---|---|---|---|
| Streamlit UI | Browser → app | `http://localhost:8501` | None (single-user, bind locally) | `main.py`, `start.py` | Import/smoke tests; live browser **UNTESTED** |
| Streamlit health | Browser → app | `/_stcore/health` (Streamlit built-in) | None | Streamlit runtime | Not audited; framework-owned |

There are **no** FastAPI/Flask routes, no upload endpoint, and no citation API. Uploads are handled in-process by Streamlit.

## Outbound providers

| Interface | Direction | Address / transport | Auth & consent | Code | Automated evidence | Live status |
|---|---|---|---|---|---|---|
| llama-server health | App → local | `GET http://127.0.0.1:8080/health` | Loopback-only enforcement (`localhost`, `127.0.0.1`, `::1`, `host.docker.internal`, `llama-server`) | `providers/llama_cpp_provider.py::check_health` | `test_llama_cpp_provider` (503/ready/refused cases) | **UNTESTED** — connection timeout |
| llama-server chat (blocking) | App → local | `POST http://127.0.0.1:8080/v1/chat/completions` | Loopback + `InferenceGate` | `LlamaCppProvider.generate_text` | Mock transport tests | **UNTESTED** |
| llama-server chat (stream) | App → local | `POST /v1/chat/completions` with SSE | Loopback + gate | `LlamaCppProvider.stream_text` | Mock SSE tests | **UNTESTED** |
| llama-server vision | App → local | `POST /v1/chat/completions` with `image_url` data URI | Loopback + gate | `LlamaCppProvider.analyze_image` | Mock payload tests | **UNTESTED** |
| llama-server models | App/manual → local | `GET /v1/models` | Loopback | manual diagnostics | None | **UNTESTED** — timeout |
| LiteLLM (Groq/OpenAI/Anthropic) | App → internet | Provider SDK HTTPS | API key from env + `user_consented=True` required; errors scrubbed | `providers/litellm_provider.py` | `test_litellm_provider`, `test_cloud_privacy` | **NOT RUN** (no egress/keys by design) |
| Groq direct | App → internet | Groq SDK HTTPS | `GROQ_API_KEY` + `user_consented=True`; cannot be auto-constructed by `AiModel` | `providers/groq_provider.py` | `test_groq_provider`, `test_audit_repairs` consent test | **NOT RUN** |
| Hugging Face model download | Setup → internet | HTTPS GET (explicit CLI) | None | `setup.py` | `test_setup_llama` (safe extraction/magic) | **NOT RUN** this audit |
| llama.cpp release download | Setup → internet | GitHub/HTTPS (explicit CLI) | None | `setup.py` | `test_setup_llama` | **NOT RUN** |

## Embedded persistence

| Interface | Direction | Location | Consistency model | Code | Evidence |
|---|---|---|---|---|---|
| SQLite metadata | App → disk | `data/documents.db` (WAL) | ACID; single transaction per ingestion | `core/doc_store.py` | `test_doc_store`, `test_audit_repairs` |
| LanceDB vectors + FTS | App → disk | `data/lancedb/` | Best-effort table ops with durable JSON fallback; failures raise | `retrieval/hybrid_retriever.py` | `test_hybrid_retriever`, `test_audit_repairs` |
| Legacy LanceDB migration | App → disk | legacy `retrieval/data/lancedb/` → `data/lancedb/` | Non-destructive copy when target has no `*.lance` | `retrieval/hybrid_retriever.py` | `test_audit_repairs::test_legacy...` |
| Extraction cache | App → disk | `.cache/<sha256>/<config-version>/` | Per-document files; purge removes and recreates | `core/models.py`, `ui/ingestion_service.py`, `ui/lifecycle_service.py` | `test_cache_invalidation`, `test_audit_repairs` |

## Local process integration

| Interface | Direction | Address | Code | Evidence |
|---|---|---|---|---|
| llama-server process launch | `start.py` → OS | `127.0.0.1:8080`, `-ngl 28`, `-c 4096` | `start.py`, `providers/llama_cpp_provider.py` | `test_start_launcher` (11) |
| Artifact identity check | launcher → GGUF files | local paths | `core/model_identity.py` | passes on installed Qwen2-VL pair |
| GPU serialization | any inference caller → `InferenceGate` | in-process | `core/local_llm.py::InferenceGate` | `test_concurrency_lock` (8) |
| Hardware telemetry | app → `nvidia-smi`/psutil | local subprocess/OS | `core/resource_telemetry.py` | `test_resource_telemetry` (14) |

## Manual verification commands for UNTESTED rows

```powershell
# 1. Local server readiness
curl.exe http://127.0.0.1:8080/health
curl.exe http://127.0.0.1:8080/v1/models

# 2. Blocking generation
curl.exe -X POST http://127.0.0.1:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"qwen2-vl-2b\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK\"}],\"max_tokens\":16}'

# 3. Streaming generation (expect SSE data: frames)
curl.exe -N -X POST http://127.0.0.1:8080/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{\"model\":\"qwen2-vl-2b\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Count to 3\"}]}'

# 4. App-level flow
python start.py --start-llama
# then ingest tests/data/corpus/*.pdf, ask a grounded question, restart, re-query
```

## Security notes

- The local provider rejects non-loopback base URLs; this is SSRF/egress control, not authentication.
- Cloud mode cannot be entered without an explicitly consented provider; `AiModel(cloud_mode=True)` alone raises `PermissionError`.
- API keys are read from environment/session state and scrubbed from surfaced errors.
- Setup downloads are explicit operator actions, not background telemetry.
