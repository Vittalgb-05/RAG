# Coding Conventions

**Analysis Date:** 2026-10-12

## Naming Patterns

**Files:**
- Flat `snake_case.py` modules at repo root, one class/concern per file: `main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`, `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `litellm_provider.py`, `prompt_budget.py`, `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `doc_store.py`, `models.py`, `upload_validation.py`, `hybrid_retriever.py`, `summarizer.py`, `citation_validator.py`, `resource_telemetry.py`.
- Test files mirror module names: `tests/test_<module>.py` (e.g. `tests/test_llama_cpp_provider.py` mirrors `llama_cpp_provider.py`, `tests/test_cloud_privacy.py` covers the Phase-7 privacy layer across `local_llm.py` + `litellm_provider.py` + `main.py` + `visual_analyzer.py`). Shared fixtures live in `tests/conftest.py`. Synthetic corpus generator lives at `tests/data/corpus/generate_corpus.py`. Benchmark/profiling harnesses live in `scripts/`: `scripts/benchmark_baseline.py`, `scripts/profile_resources.py`. UI-contract tests live in `tests/test_main_ui.py` (no `main_ui.py` source module — it tests helpers/contracts consumed by `main.py`).
- Profiling/benchmark scripts prepend repo root to `sys.path` instead of using relative imports (`scripts/benchmark_baseline.py`, `scripts/profile_resources.py`).

**Functions:**
- `snake_case` throughout. Examples: `ask_a_question_from_pdf_stream` (`local_llm.py`), `build_index` / `get_embeddings` / `get_context` (`local_embedding.py`), `add_document` / `add_vector` / `search` (`vector_index.py`), `extract_text` / `get_paragraphs` (`pdf_reader.py`), `load_ai_model` (`main.py`), `generate_text` / `stream_text` / `analyze_image` / `check_health` / `get_capabilities` (all `BaseModelProvider` implementations: `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `litellm_provider.py`), `set_consent` / `set_cloud_mode` (`litellm_provider.py`, `local_llm.py`), `_resolve_api_key_for_model` / `_detect_image_mime_type` (`litellm_provider.py`).
- Phase-8 additions: `get_gpu_memory_info(force_refresh=False)` / `clear_gpu_cache()` (`resource_telemetry.py:33,210`), `LlamaCppProvider.__init__(..., allow_remote=False)` (`llama_cpp_provider.py:29`), `_render_consent_dialog_content` / `show_consent_dialog` (`main.py:111-147`).
- Private helpers use a single leading underscore: `_embed_one` (`local_embedding.py`), `_cosine_distance` / `_euclidean_distance` / `_dot_product` / `_magnitude` (`vector_index.py`), `_detect_provider` (`local_llm.py`), `_resolve_api_key_for_model` / `_detect_image_mime_type` / `_require_consent` (`litellm_provider.py`).

**Variables:**
- `snake_case` locals and attributes: `indexed_files`, `document_metadata`, `local_embedding`, `chat_history` (`main.py`), `page_chunks`, `pages_text`, `filename` (`pdf_reader.py`), `cloud_mode`, `user_consented`, `cloud_provider`, `active_cloud_provider`, `local_vlm_provider` (`main.py`, `local_llm.py`, `litellm_provider.py`), `stream_calls` (mock providers in `tests/conftest.py`).
- Private state uses a single leading underscore: `_vector_dim`, `_distance_metric`, `_embedding_fn` (`vector_index.py`), `_healthy`, `_tokens` (mocks in `tests/conftest.py`).
- Telemetry cache state is module-level underscore-prefixed: `_GPU_CACHE_TTL_SECONDS`, `_GPU_CACHE_LOCK`, `_SAMPLING_LOCK`, `_LAST_GPU_SAMPLE_TIME`, `_LAST_GPU_SAMPLE` (`resource_telemetry.py:26-31`). Tests reset it via `clear_gpu_cache()` — never by touching the globals directly (`tests/test_resource_telemetry.py:27,30`).
- Pydantic model fields are `snake_case` with explicit `Field(...)` metadata: `chunk_id`, `doc_id`, `page`, `supports_vision`, `is_local`, `context_window` (`models.py`, `model_provider.py`).

**Types:**
- `PascalCase`, one public class per module: `AiModel` (`local_llm.py`), `LocalEmbedding` (`local_embedding.py`), `VectorIndex` (`vector_index.py`), `PdfReader` (`pdf_reader.py`), `LiteLLMProvider` (`litellm_provider.py`), `LlamaCppProvider` (`llama_cpp_provider.py`), `GroqProvider` (`groq_provider.py`), `VisualAnalyzer` (`visual_analyzer.py`), `HybridRetriever` (`hybrid_retriever.py`), `DocStore` (`doc_store.py`), `InferenceGate` (`local_llm.py`).
- Pydantic v2 schemas in `models.py` (`Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`, `EvidenceSnippet`, `SummaryResult`, `RetrievalResult`) and `model_provider.py` (`BaseModelProvider`, `HealthStatus`, `ProviderCapabilities`): all use `ConfigDict(frozen=True, extra="forbid")` unless mutation is required. New schemas must follow this frozen/forbid default.
- Module-level `UPPER_CASE` constants for policy tables and defaults: `DEFAULT_CLOUD_MODEL`, `KNOWN_CONTEXT_WINDOWS`, `VISION_SUPPORTED_PREFIXES` (`litellm_provider.py`), `CONFIG_VERSION` (`models.py`), `_GPU_CACHE_TTL_SECONDS = 5.0` (`resource_telemetry.py:26`). Retrieval/UI tunables that are call-site literals (not policy) stay inline: `chunk_size=1000, chunk_overlap=200` (`pdf_reader.py`), `k=10` call sites (`main.py`), `max_tokens=1024` (`local_llm.py`, provider `generate_text` signatures).
- Modern `X | None` union syntax (target `py311` per `pyproject.toml:3`), builtin generics (`list[dict]`, `dict[str, str]`, `list[tuple[dict, float]]`). `typing` imports (`List`, `Dict`, `Optional`) survive only in legacy `vector_index.py`; new code must use builtin generics.

## Code Style

**Formatting:**
- Ruff formatter is canonical. Config in `pyproject.toml:1-10`: `line-length = 120`, `target-version = "py311"`.
- Verify with `ruff format --check .` (46 files, clean per `08-REVIEW-FIX.md`). CI enforces it (`.github/workflows/ci.yml:30-33`).
- 4-space indentation. Double quotes for code strings; `"""..."""` docstrings everywhere (see Docstrings below).

**Linting:**
- Ruff linter. Config in `pyproject.toml:5-10`: `select = ["E", "F", "W"]`, `ignore = ["E501", "W291", "W293"]` (line length enforced by formatter, not `E501`).
- Per-file ignores: `"scripts/*" = ["E402"]` (`pyproject.toml:9-10`) — `scripts/` intentionally imports after `sys.path` manipulation.
- Verify with `ruff check .` (0 errors). CI runs `ruff check .` before tests (`.github/workflows/ci.yml:30-33`).

## Import Organization

**Order:**
1. Stdlib block (`os`, `re`, `base64`, `logging`, `sqlite3`, `pathlib`, `datetime`, `collections.abc`, `ipaddress`, `threading`, `subprocess`, `urllib.parse`)
2. Third-party block (`streamlit`, `pydantic`, `litellm`, `sentence_transformers`, `pypdf`, `langchain_text_splitters`)
3. Local block (`from model_provider import ...`, `from litellm_provider import ...`)

- Exemplars: `main.py:14-35` (stdlib, blank line, third-party, blank line, local), `litellm_provider.py:1-20` (`base64`, `collections.abc`, `logging`, `os`, `typing`, then `model_provider`), `models.py:1-15`, `vector_index.py:11-12` (stdlib-only: `math`, `typing`), `llama_cpp_provider.py` (stdlib `ipaddress` + `urllib.parse` for loopback validation), `resource_telemetry.py` (stdlib `threading` + `subprocess` for TTL cache).
- No path aliases. All imports are top-level absolute (`from vector_index import VectorIndex` in `local_embedding.py:8`).

**Optional-dependency pattern (must-follow):**
- Guarded top-level import → `None` sentinel → explicit error at use site. Copy this shape for any new optional third-party import:
  ```python
  try:
      import litellm
  except ImportError:
      litellm = None  # type: ignore[assignment]
  ```
  (`litellm_provider.py`, same shape as the `groq` guard in `local_llm.py`/`groq_provider.py`). Use-site checks raise `RuntimeError("LiteLLM is not installed.")` (`litellm_provider.py:203,252,306`) or `ImportError` with install hint.
- `check_health()` must handle the `None` library gracefully and report `unreachable`, never raise (`litellm_provider.py`, covered by `test_check_health_when_litellm_missing` in `tests/test_litellm_provider.py:80-89`).

## Error Handling

**Fail-fast validation (must-follow):**
- `TypeError` for wrong types, `ValueError` for bad values, before mutating state. Guard inventory to mirror: metric whitelist and dimension lock-in (`vector_index.py`), non-dict document / missing `content` key (`vector_index.py`), `sha256` hex-digest validation (`models.py:cache_dir_for`), empty `image_bytes` → `ValueError("image_bytes cannot be empty.")` (`litellm_provider.py:304`), non-string vectors and `k <= 0` (`vector_index.py`).
- Empty-store behaviour: `search()` returns `[]` instead of raising when nothing is indexed (`vector_index.py`).

**Loopback endpoint validation (Phase-8 SEC-01, must-follow):**
- `LlamaCppProvider.__init__` normalises scheme before parsing (`base_url if "://" in base_url else f"http://{base_url}"`), then accepts `host == "localhost"` or `ipaddress.ip_address(host).is_loopback` (`llama_cpp_provider.py:39-56`, per `08-REVIEW-FIX.md` WR-01). Non-loopback raises `ValueError("Restricted endpoint ... Specify a loopback URL or pass allow_remote=True.")` unless `allow_remote=True` is explicitly passed.
- New network-endpoint constructors must follow this shape: scheme normalisation + `ipaddress.is_loopback` + explicit opt-out flag. Never hardcode a literal host set. Covered by `test_endpoint_loopback_validation_rejected`, `test_endpoint_loopback_validation_allowed_with_flag`, `test_endpoint_loopback_accepted_addresses` (`tests/test_llama_cpp_provider.py:262-295`), including `127.0.1.1`/`127.0.0.2`/scheme-less cases.

**Consent gate (Phase-7, must-follow):**
- Cloud transmission without explicit user consent raises `PermissionError("Cloud transmission blocked ...")` before any network call. Enforcement point is `_require_consent()` inside `LiteLLMProvider.generate_text` / `stream_text` / `analyze_image` (`litellm_provider.py:135`), with `set_consent(bool)` as the only grant/revoke path. Covered by `test_consent_gate_blocks_generation_by_default` (`tests/test_litellm_provider.py:26-37`) and `test_consent_state_transition_workflow` (`tests/test_cloud_privacy.py:22-52`). New cloud-touching entry points must call `_require_consent()` first.

**Exception wrapping (must-follow):**
- Provider SDK errors are wrapped in `RuntimeError` naming the provider and model, chained with `from err`: `"Cloud provider generation error ({model})"` / `"Cloud provider streaming error ({model})"` / `"Cloud provider vision error ({model})"` (`litellm_provider.py:228,284,342`), `"Groq API error: ..."` (`groq_provider.py:126,161`), `"llama-server generation failed: ..."` (`llama_cpp_provider.py:151`). Never let raw SDK exceptions reach `main.py`. Covered by `test_exception_wrapping_into_runtime_error` (`tests/test_litellm_provider.py:220-235`).

**Capability rejection:**
- `NotImplementedError` when a provider structurally cannot serve a request: non-vision cloud model receiving `analyze_image` (`litellm_provider.py:310`, `groq_provider.py:170`), including the `VisualAnalyzer` defense-in-depth guard that forces `supports_vision = False` for non-local providers (`visual_analyzer.py`, per `07-REVIEW-FIX.md` CR-01).

**UI-level isolation:**
- Per-file `try/except Exception as e` around `PdfReader` + `get_paragraphs()`, reporting via `st.error(f"... (Error: {e})")` then `continue` so one bad PDF never aborts the batch (`main.py`). New per-document processing must use this isolate-and-continue shape, never a bare `except:`.
- `paragraphs[-1]["page"] if paragraphs else 0` guards empty PDFs; `if chat_history:` / `if last_user_msgs:` guards history contextualisation; zero-magnitude vectors return `0.0`/`1.0` instead of dividing by zero. Preserve these guards when touching the same code.
- Missing API key in `check_health()` returns `HealthStatus(status="unreachable", message="Missing API key ...")` — never raises, never touches network (`litellm_provider.py`, covered by `tests/test_litellm_provider.py:58-77`).

## Logging

**Framework:** `logging` with module-level `logger = logging.getLogger(__name__)` in all service modules (`litellm_provider.py:14`, `citation_validator.py:14`, `docling_reader.py:20`, `hybrid_retriever.py:16`). Lazy `%s` argument style, never f-strings: `logger.info("LanceDB persistent retriever connected at %s", self.db_uri)` (`hybrid_retriever.py:117`), `logger.warning("Failed to initialize LanceDB at %s: %s. ...", ...)` (`hybrid_retriever.py:119`).

**Rules:**
- `logger.info` for lifecycle (model ready, index built, fallback engaged), `logger.warning` for degraded-but-continuing paths (fallback stores, skipped providers), `logger.error` for persistence failures, `logger.debug` for vendor-SDK notices (`hybrid_retriever.py:415,432,507`).
- Residual `print()` calls survive only in `doc_store.py:154` (migration notice) and `pdf_reader.py:113` (extraction summary); `scripts/` may print freely (CLI harnesses). Do not add new `print()` to service modules — use `logger`.
- User-facing feedback goes through Streamlit, never `print`/`logger`: `st.error` / `st.warning` / `st.info` / `st.success` / `st.status` / `st.toast` (`main.py:112,251-279,312-504,618-738`). Rule: `logger` for developer diagnostics, `st.*` for anything the user should see.

## Comments

**When to Comment:**
- Explain *why Streamlit behaves unusually*, not what the code does. Exemplar: why the whole script reruns and why session state is the only persistence (`main.py`), why `set_cloud_mode` needs an idempotence guard to avoid connection-pool churn on every rerun (`local_llm.py:140-155`, `main.py:210-240`, per `07-REVIEW.md` WR-02).
- Privacy-invariant comments at every egress boundary: what stays on-device vs what is transmitted upon consent (`main.py` privacy dialog, `litellm_provider.py` consent gate, `visual_analyzer.py` local-only guard per `07-REVIEW-FIX.md` CR-01). Phase-8 consent copy must name OCR text and visual summaries explicitly (`main.py:111-123`, per `08-01-SUMMARY.md` PRIV-01).
- Algorithm notes where the math is non-obvious: L2-normalisation rationale (`local_embedding.py`), zero-vector guard (`vector_index.py`), float-drift clamp (`vector_index.py`), image magic-byte sniffing (`litellm_provider.py:_detect_image_mime_type`), TTL + double-checked sampling rationale (`resource_telemetry.py:26-60`, per `08-REVIEW-FIX.md` IN-01).
- Security rationale at SSRF boundaries: why loopback-only is the default and what `allow_remote=True` opts into (`llama_cpp_provider.py:38-56`, per `08-REVIEW.md` WR-01).

**Docstrings:**
- Every module has a top-of-file `"""..."""` summary stating inputs/outputs and requirement tags where applicable (e.g. `litellm_provider.py:1-7` cites `INF-04, UI-04`; `tests/test_cloud_privacy.py:1` cites `UI-04, INF-03, INF-04`). New modules must include one.
- Public methods carry Google-style `Args:`/`Returns:` docstrings (`models.py:cache_dir_for`, `vector_index.py`, `local_embedding.py`). Provider interface methods document consent, bounds, and error contracts (`model_provider.py`, `litellm_provider.py`). Phase-8 security/telemetry methods document `allow_remote`, `force_refresh`, and TTL semantics (`llama_cpp_provider.py:29-38`, `resource_telemetry.py:33-44`).

**JSDoc/TSDoc:**
- Not applicable (Python codebase).

## Function Design

**Size:** Small single-purpose methods (5–25 lines). Largest functions are UI layout blocks in `main.py` (sidebar, chat handler) — these are sequential Streamlit layouts, not logic to extract, unless adding genuinely new UI sections.

**Parameters:** Keyword-friendly with sane defaults: `prompt: str = "tell me what is this pdf about", local_embedding=None, chat_history=None` (`local_llm.py`); `k: int = 3` (retrieval methods); `model_name: str = "groq/llama-3.3-70b-versatile"` / `timeout=25.0` / `num_retries=3` / `temperature: float = 0.2` (`litellm_provider.py`); `max_tokens: int = 1024`. Cloud calls must be bounded: new generation paths must accept and forward `timeout`/`num_retries` and clamp `temperature` to `2.0` (covered by `test_generate_text_clamps_temperature_and_passes_bounded_params` in `tests/test_litellm_provider.py:112-145`).
- Telemetry sampling uses `force_refresh: bool = False` to bypass the 5.0s TTL cache for diagnostic paths (`resource_telemetry.py:33`); benchmarks pass `force_refresh=True` while Streamlit reruns rely on the cached default. New telemetry readers must accept and honour `force_refresh`.
- Network constructors use explicit opt-out flags defaulting to the safe posture: `allow_remote: bool = False` (`llama_cpp_provider.py:29`). New endpoint-accepting constructors must default to loopback-only the same way.

**Return Values:** Data methods return plain containers or Pydantic models: `list[dict]` chunks with `content`/`filename`/`page`/`chunk_id` keys (`pdf_reader.py`), `list[tuple[dict, float]]` of `(document, distance)` sorted ascending (`vector_index.py`), `HealthStatus` / `ProviderCapabilities` from `check_health()` / `get_capabilities()` (all providers).

**Streaming:** Generation is a token generator (`yield` fragments in `LiteLLMProvider.stream_text`, `LlamaCppProvider.stream_text`, `AiModel.ask_a_question_from_pdf_stream`) consumed by `st.write_stream`, which returns the full string (`main.py`). New LLM entry points must yield strings (not return a completed string) to preserve streaming. `None`-content deltas must be skipped, not yielded (covered by `test_stream_text_yields_deltas` in `tests/test_litellm_provider.py:148-168`).

**TTL caching with double-checked locking (Phase-8 TEL-01, must-follow):**
- `get_gpu_memory_info` checks the TTL under `_GPU_CACHE_LOCK`, samples `nvidia-smi` only inside `_SAMPLING_LOCK`, then re-checks the timestamp under `_GPU_CACHE_LOCK` before spawning (`resource_telemetry.py:46-60`, per `08-REVIEW-FIX.md` IN-01). Tests reset state via `clear_gpu_cache()` at test start (`tests/test_resource_telemetry.py:27,30`), never by mutating module globals. New subprocess-backed telemetry readers must copy this two-lock shape, not a single-lock check-then-sample.

**Idempotence on rerun paths:** `AiModel.set_cloud_mode` returns early as a no-op when mode and provider instance are unchanged (`local_llm.py:140-155`, per `07-REVIEW.md` WR-02); `main.py` caches `active_cloud_provider` / `_cached_cloud_model` / `_cached_cloud_key` and only constructs a new provider when model or key changes. Covered by `test_ai_model_set_cloud_mode_idempotent_preserves_connections` (`tests/test_cloud_privacy.py:206-221`). Any new per-rerun mutator must be idempotent the same way.

**Dual-type flexibility:** Where the codebase already does it — `PdfReader.__init__(self, file_or_path, filename=None)` accepts path/bytes/file-object (`pdf_reader.py`); `VectorIndex.search(query: Any, ...)` accepts string or precomputed vector (`vector_index.py`); `LocalEmbedding.build_index(chunks: list)` accepts `list[str]` or `list[dict]` (`local_embedding.py`). Extend with the same accept-both-types + normalise-early shape.

## Module Design

**Exports:** Single public class per module, imported by name — no `__all__`, no factories, no re-exports. Wire new cross-module dependencies the same way (`from x import Y` at top level). All providers implement `BaseModelProvider` (`model_provider.py`) and are interchangeable via `AiModel(provider=...)` / `AiModel.set_cloud_mode(...)` injection.

**Pydantic schemas:** New data crossing module boundaries must be a Pydantic v2 model in `models.py` (frozen/forbid default), with `model_dump()` at the persistence/serialization boundary and `Chunk(...)`/`Document(...)` constructors accepting legacy dicts for backward compatibility (covered by `tests/test_models.py`, 20 tests).

**Barrel Files:** None and not wanted: the flat layout means a new module is just a new root-level file plus an import where used.

## Streamlit Idioms (must-follow)

- `st.set_page_config(...)` is the very first Streamlit call (`main.py`) — never insert a Streamlit call above it.
- Initialise all `st.session_state` keys via the key/default loop (`main.py:60-80`); add new keys there, never lazily mid-layout. Phase-7 keys: `cloud_mode: bool = False`, `user_consented: bool = False`, `cloud_provider`, `cloud_model`, `cloud_api_keys: dict[str, str]` (per-provider, keyed `groq`/`openai`/`anthropic`), `cloud_mode_toggle`, `active_cloud_provider`. Legacy `cloud_api_key: str = ""` survives only as a cleared fallback (`main.py:73,315-316`, per `08-01-SUMMARY.md` PRIV-02 — new code must read `cloud_api_keys`, never the legacy key).
- Heavy singletons go behind `@st.cache_resource` (`main.py:load_ai_model`); per-`load_dotenv()`-before-read ordering inside the cached function matters because provider constructors read env/secrets.
- Every `st.toggle` must carry an explicit `key=` (e.g. `key="cloud_mode_toggle"`) and consent-cancel paths must explicitly reset `st.session_state.cloud_mode_toggle = False` (`main.py:120-155,195-200`, per `07-REVIEW.md` WR-03).
- Consent dialog uses `@st.dialog("Cloud Inference & Data Privacy Consent")` (`main.py:141-147`); disclosure copy must enumerate transmitted classes — query prompts, retrieved excerpts, extracted text/tables, OCR-processed text, visual figure descriptions and image summaries (`main.py:111-123`, per `08-01-SUMMARY.md` PRIV-01). Dismissal/cancel must leave the app in local mode with the toggle synced OFF.
- Egress transparency: sidebar status badge (`🟢 Inference: Local` vs `☁️ Inference: Cloud`), pipeline locality footer, and per-chat-turn disclosure chips (`☁️ Generated via external cloud provider ... with user consent` vs `🔒 Generated locally on-device`) driven by `is_cloud` + `model_name` turn metadata (`main.py:618,724`, `tests/test_cloud_privacy.py:105-129`).
- Render pattern: `with st.sidebar:` layout, `st.status` for staged work with `.update(label=..., state="complete", expanded=False)` on completion, `st.chat_message` + `st.markdown` for history replay, `st.chat_input(..., disabled=(...))` for gated input, `response_stream → st.write_stream(response_stream) → append to history`.
- State mutation ends with `st.rerun()` after batch updates (`main.py`).
- Ingestion visual analysis must only ever receive a local provider: filter `active_provider` to `local_vlm_provider = prov if (prov and prov.get_capabilities().is_local) else None` before calling `VisualAnalyzer.analyze_visual_elements` (`main.py:410-420`, per `07-REVIEW-FIX.md` CR-01). Never pass the raw active provider at ingestion time.
- "Clear All" must reset cloud posture as well as documents: close `active_cloud_provider`, null `_cached_cloud_model`/`_cached_cloud_key`, set `cloud_mode = False`, `cloud_mode_toggle = False`, `user_consented = False`, cleanse `cloud_api_keys` to empty strings (and legacy `cloud_api_key`), then `st.rerun()` (`main.py:288-320`, per `08-REVIEW-FIX.md` WR-02). Covered by `test_clear_all_resets_cloud_posture_and_credentials` (`tests/test_main_ui.py:159-185`).

## Config Patterns (must-follow)

- Precedence for secrets: explicit arg → `st.session_state.cloud_api_keys[provider]` → legacy `st.session_state.cloud_api_key` → `st.secrets[VAR]` → `os.environ[VAR]` (`litellm_provider.py:_resolve_api_key_for_model`, `local_llm.py`). Per-provider env map: `groq → GROQ_API_KEY`, `openai → OPENAI_API_KEY`, `anthropic → ANTHROPIC_API_KEY`. Covered by `test_per_provider_api_key_lookup` (`tests/test_cloud_privacy.py:224-251`). Never introduce a new shared single-string key — always extend the `cloud_api_keys` dict. `main.py` no longer writes the legacy key on entry (PRIV-02); it only clears it in "Clear All".
- Never commit secrets: `.env` is gitignored; existence only is noted, contents are never read or quoted. Tests use `"mock-key"` / `"test-key"` / `"sk-test"` literals, never real credentials.
- New required-config checks must raise with "what + where to set it" message shape (naming both `st.secrets` and env locations).

## Dependency Patterns (must-follow)

- Dev/CI float file: `requirements.txt` (17 lines; `httpx==0.28.1` and `psutil==6.1.1` pinned per `08-01-SUMMARY.md` QUAL-02; unpinned ranges survive for `docling`, `rapidocr-onnxruntime`, `pymupdf`, `pillow`, `lancedb`, `pyarrow`, `litellm`, `numpy`). CI installs `requirements.txt` + `requirements-test.txt` (`pytest>=8.3.0`, `reportlab>=4.2.0`, `ruff>=0.9.0`, `psutil>=6.1.0`).
- Deterministic deploy lockfile: `requirements-lock.txt` (27 pinned `==` entries with header comment; generated per `08-01-SUMMARY.md` QUAL-02). Production/runbook installs use the lockfile (`README.md:131`, `docs/RUNBOOK.md:48`); CI still installs the float files and is verified in sync with the lockfile strategy (per `08-01-SUMMARY.md` §5 and `08-REVIEW-FIX.md` §2). When adding a runtime dependency, pin it in `requirements.txt` and regenerate the lockfile — never hand-edit lockfile versions.
- `LICENSE` (MIT) exists at repo root; `README.md` badges/links reference it (per `08-REVIEW-FIX.md` WR-03). Do not remove it.

---

*Convention analysis: 2026-10-12*
