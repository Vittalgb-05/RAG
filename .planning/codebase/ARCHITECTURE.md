<!-- refreshed: 2026-10-11 -->
# Architecture

**Analysis Date:** 2026-10-11

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                     Streamlit UI  (`main.py`)                         │
│  sidebar: health badge · upload · indexed-docs   main: chat + stream  │
└───────┬───────────────────────┬───────────────────────┬──────────────┘
        │ upload bytes          │ query                 │ render tokens
        ▼                       ▼                       │
┌────────────────────┐  ┌────────────────────┐          │
│ upload_validation  │  │  local_llm.AiModel │          │
│  %PDF · size ·     │  │  provider select · │          │
│  pages · sha256    │  │  prompt budgeting  │          │
└───────┬────────────┘  └─────┬───────┬──────┘          │
        │                     │       │                 │
        ▼                     ▼       ▼                 │
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐│
│ DoclingReader    │ │local_embedding│ │ BaseModelProvider││
│  primary (+ pypdf│ │  (MiniLM CPU) │ │  ── LlamaCpp_   ││
│  fallback)       │ │  + VectorIndex│ │     provider    ││
└───────┬──────────┘ └──────┬───────┘ │  ── GroqProvider││
        │                   │         └────────┬─────────┘│
        ▼                   ▼                  ▼          │
┌──────────────────┐        │         ┌──────────────────┐│
│ conditional OCR  │        │         │ prompt_budget    ││
│ OcrEngine+Rapid  │        │         │ bounded messages ││
│ OCR (CPU, 150dpi)│        │         └──────────────────┘│
└───────┬──────────┘        │                             │
        ▼                   ▼                             │
┌──────────────────┐ ┌────────────────────────┐  ┌──────────────────┐
│ VisualAnalyzer   │ │  models.py (Pydantic)  │  │ llama-server /   │──┘
│  fitz detect ·   │ │  Document·Page·Chunk·  │  │ Groq Cloud       │
│  2x crop · VLM   │ │  BBox·EvidenceElement  │  └──────────────────┘
└───────┬──────────┘ └──────────┬─────────────┘
        │                       ▼
        │            ┌────────────────────────────┐  ┌───────────────────────┐
        └───────────►│  doc_store.DocStore        │  │  VectorIndex (in-RAM) │
                     │  SQLite WAL · documents /  │  │  cosine linear scan   │
                     │  pages / chunks / evidence │  └───────────────────────┘
                     └──────────────┬─────────────┘
                                    ▼
                     ┌────────────────────────────┐
                     │  .cache/<sha>/<ver>/      │
                     │  pages·chunks·manifest.json│
                     └────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit App | Page config, session state, sidebar health/upload/dedup orchestration, chat replay, streaming render, source display, Clear All | `main.py` |
| AiModel | Provider auto-detection + re-probe, retrieval orchestration, grounded prompt assembly, token-stream generator | `local_llm.py` |
| BaseModelProvider | Abstract inference contract (`generate_text`, `stream_text`, `analyze_image`, `check_health`, `get_capabilities`) + `ProviderCapabilities`/`HealthStatus` frozen schemas | `model_provider.py` |
| LlamaCppProvider | Local llama-server HTTP client — `GET /health`, OpenAI-compatible `POST /v1/chat/completions`, SSE streaming, base64 `analyze_image`, connection lifecycle | `llama_cpp_provider.py` |
| GroqProvider | Cloud Groq implementation; `st.secrets` → env API-key resolution; no vision (`analyze_image` raises) | `groq_provider.py` |
| prompt_budget | Bounded token budgeting, `<document_context>` injection isolation, oldest-first history truncation | `prompt_budget.py` |
| DoclingReader | Primary structured extraction (reading order, headings, markdown tables, CPU `do_ocr=False`); graceful `PdfReader` fallback | `docling_reader.py` |
| PdfReader | pypdf fallback extraction, whitespace cleanup, per-page fault isolation, canonical `Chunk`/`Page` construction | `pdf_reader.py` |
| OcrEngine / conditional OCR | Page-selective RapidOCR (threshold <50 chars or empty/failed), 150 DPI PyMuPDF render, page-isolated faults | `ocr_fallback.py` |
| VisualAnalyzer | Raster + vector-diagram region detection, 2x PNG crops, `provider.analyze_image` VLM descriptions, `EvidenceElement` provenance (`vlm:<model>`) | `visual_analyzer.py` |
| LocalEmbedding | SentenceTransformer wrapper (CPU, `all-MiniLM-L6-v2`, 384-dim L2-normalised), batch embed + build index, search/get_context facade | `local_embedding.py` |
| VectorIndex | Pure-stdlib in-memory vector store; cosine/Euclidean; dimension locking; linear-scan k-NN | `vector_index.py` |
| DocStore | SQLite (WAL) persistence of documents, pages, chunks, evidence elements; versioned migrations; dedup lookup; chunk replay | `doc_store.py` |
| models | Canonical Pydantic v2 schemas (`Document`, `Page`, `Chunk`, `BBox`, `EvidenceElement`) + `CONFIG_VERSION` + `cache_dir_for` | `models.py` |
| upload_validation | `%PDF` magic bytes, size/page caps (50 MB / 500 pages), streaming SHA-256, stable `doc_id` (`doc_<sha16>`) | `upload_validation.py` |
| Baseline benchmark | Offline latency/memory measurement harness (extraction, chunking, CPU embedding, linear scan, RSS) | `scripts/benchmark_baseline.py` |

## Pattern Overview

**Overall:** Layered modular monolith with a provider abstraction and a UI-orchestrated pipeline.

**Key Characteristics:**
- `main.py` owns both loops (ingestion and query); domain modules are stateless helpers except for cached/singleton objects held in session state or `st.cache_resource`.
- Fully local retrieval (embeddings + vector scan on CPU), pluggable generation — local llama-server (Qwen3-VL 2B GGUF) preferred, Groq Cloud as configured fallback (`local_llm.py:46-67`).
- Multi-stage ingestion: validate → Docling primary (pypdf fallback) → conditional OCR → visual analysis → persist (SQLite + `.cache`) → embed.
- Generator-based streaming decouples token production (`BaseModelProvider.stream_text`) from rendering (`st.write_stream`).
- Strict one-way dependencies; no circular imports.
- Every canonical entity is a frozen/validated Pydantic model, and legacy dict keys (`content`, `filename`, `page`, `chunk_id`) are preserved so `VectorIndex` (stdlib, dict-based) keeps working unchanged.

## Layers

**UI / Orchestration:**
- Purpose: file upload, dedup, index-status display, health badge, conversational chat, streamed rendering.
- Location: `main.py`
- Contains: `st.set_page_config` (`main.py:38-43`), session-state init (`main.py:52-60`), `load_ai_model()` cache (`main.py:68-76`), sidebar health block (`main.py:90-121`), upload loop (`main.py:146-310`), chat loop (`main.py:330-410`).
- Depends on: `doc_store`, `docling_reader`, `local_embedding`, `local_llm`, `models`, `ocr_fallback`, `upload_validation`, `visual_analyzer`.
- Used by: end user via browser at `http://localhost:8501`; devcontainer `postAttachCommand`.

**Provider / Inference:**
- Purpose: interchangeable LLM/VLM backends behind one contract; health + capability introspection; grounded streaming generation.
- Location: `model_provider.py`, `llama_cpp_provider.py`, `groq_provider.py`, `local_llm.py`, `prompt_budget.py`
- Contains: `BaseModelProvider` (`model_provider.py:64-156`), `ProviderCapabilities` (`model_provider.py:15-41`), `HealthStatus` (`model_provider.py:44-61`), `LlamaCppProvider` (`llama_cpp_provider.py:18-268`), `GroqProvider` (`groq_provider.py:18-170`), `AiModel` (`local_llm.py:17-153`), `assemble_grounded_messages` (`prompt_budget.py:48-117`).
- Depends on: `httpx` (local), `groq` (optional cloud), `pydantic`.
- Used by: `main.py` health badge (`main.py:90-121`), chat path (`main.py:388-393`), visual pipeline (`main.py:231-240` via `active_provider`).

**Ingestion (validate → extract → OCR → visual):**
- Purpose: bytes-in, validated metadata + page-tagged text chunks + visual evidence out.
- Location: `upload_validation.py`, `docling_reader.py`, `pdf_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`, `models.py`
- Contains: `validate_pdf_bytes` (`upload_validation.py:64-113`), `DoclingReader.extract_text/get_paragraphs/get_page_records` (`docling_reader.py:78-311`), `PdfReader.extract_text/get_paragraphs/get_page_records` (`pdf_reader.py:29-139`), `apply_conditional_ocr` (`ocr_fallback.py:162-320`), `should_ocr_page` (`ocr_fallback.py:29-43`), `OcrEngine` (`ocr_fallback.py:46-159`), `VisualAnalyzer.detect_visual_regions/crop_visual_element/analyze_visual_elements` (`visual_analyzer.py:47-264`).
- Depends on: `pypdf`, `docling` (optional), `rapidocr-onnxruntime` (optional), `PyMuPDF/fitz` (optional), `langchain_text_splitters`, `re`, `hashlib`.
- Used by: `main.py:166-250`.

**Persistence:**
- Purpose: durable document/page/chunk/evidence metadata across restarts + best-effort JSON disk cache.
- Location: `doc_store.py` + `data/documents.db` + `.cache/<sha256>/<CONFIG_VERSION>/`
- Contains: `DocStore` (`doc_store.py:78-413`) — `_connect` (`doc_store.py:97-114`), `_apply_migrations` (`doc_store.py:116-129`), `upsert_document` (`doc_store.py:131-166`), `get_by_sha` (`doc_store.py:188-206`), `record_page` (`doc_store.py:220-251`), `record_chunks` (`doc_store.py:253-301`), `get_chunks_for_doc` (`doc_store.py:303-325`), `record_evidence_elements` (`doc_store.py:327-371`), `get_evidence_for_doc` (`doc_store.py:373-398`); schema v1 (documents/pages/chunks) + v2 (evidence_elements) (`doc_store.py:16-75`); `cache_dir_for` (`models.py:17-30`), `CONFIG_VERSION="docling-1000-200-v1"` (`models.py:14`).
- Depends on: stdlib `sqlite3` (WAL + busy-timeout + per-operation connections), `models`.
- Used by: `main.py` upload loop (`main.py:150-289`).

**Retrieval:**
- Purpose: semantic embedding and nearest-neighbour lookup.
- Location: `local_embedding.py`, `vector_index.py`
- Contains: `LocalEmbedding` (`local_embedding.py:11-71`) — `_embed_one` (`local_embedding.py:27-32`), `get_embeddings` (`local_embedding.py:34-39`), `build_index` (`local_embedding.py:41-58`), `search` (`local_embedding.py:60-64`), `get_context` (`local_embedding.py:66-71`); `VectorIndex` (`vector_index.py:15-213`) — `add_document` (`vector_index.py:39-63`), `add_vector` (`vector_index.py:65-90`), `search` (`vector_index.py:92-136`) + `_cosine_distance`/`_euclidean_distance` (`vector_index.py:157-155`/`142-155`).
- Depends on: `sentence_transformers` (embedding layer only); `vector_index` uses stdlib `math` only.
- Used by: `main.py:254-256,372` and `local_llm.py:134`.

## Data Flow

### Primary Request Path — Ingestion (PDF upload → indexed + persisted)

1. `st.file_uploader` returns files; client size pre-check against `MAX_FILE_MB` (`main.py:152-164`)
2. Single `raw_bytes = uploaded_file.getvalue()` per file (`main.py:167`); `validate_pdf_bytes(raw_bytes, filename)` → `%PDF` header, size/page caps, SHA-256, stable `doc_id` (`main.py:170-175`, `upload_validation.py:64-113`)
3. Dedup: `DocStore(Path("data/documents.db"))` + `get_by_sha(validated.sha256)` + session `doc_ids` guard (`main.py:150,178-200`); on dedup hit after restart, chunks restored from SQLite into a fresh `LocalEmbedding` (`main.py:194-200`)
4. Primary extraction: `DoclingReader(io.BytesIO(raw_bytes), filename).extract_text(doc_id, sha12)` → `get_paragraphs()` + `get_page_records()` (`main.py:211-218`, `docling_reader.py:78-293`); Docling runs CPU-only (`do_ocr=False`, `do_table_structure=True`, `docling_reader.py:103-109`), groups items by page in reading order, keeps markdown tables intact (≤2000 chars), splits prose at 1000/200; any missing-docling or conversion failure degrades to `PdfReader` (`docling_reader.py:95-100,183-191,288-293`)
5. Conditional OCR: `apply_conditional_ocr(pdf_bytes, page_records, paragraphs, doc_id, sha12, filename)` (`main.py:221-228`, `ocr_fallback.py:162-320`) — pages with <50 chars or `empty`/`failed` status are rendered at 150 DPI via PyMuPDF (`ocr_fallback.py:77-110`) and OCR'd on CPU via RapidOCR (`ocr_fallback.py:112-159`); clean pages bypass OCR untouched; OCR text re-chunked (1000/200) with `extraction="ocr"`; per-page faults isolated to `failed` records
6. Visual analysis: `VisualAnalyzer().analyze_visual_elements(pdf_bytes, doc_id, provider=active_provider)` (`main.py:231-240`, `visual_analyzer.py:185-264`) — `detect_visual_regions` finds raster images (≥30px) + vector-diagram clusters (≥2 drawings, ≥40pt, <95% page area) (`visual_analyzer.py:47-136`); each region cropped at 2x zoom PNG (`visual_analyzer.py:138-183`); `provider.analyze_image` produces a description tagged `source="vlm:<model_name>"` so VLM approximations never overwrite ground-truth table text; results persisted via `doc_store.record_evidence_elements` (`main.py:240`)
7. Page records persisted with per-page progress bar; `failed` pages warned but do not abort (`main.py:246-250`)
8. `LocalEmbedding.build_index(paragraphs)` appends embeddings into the unified `VectorIndex` (`main.py:254-256`, `local_embedding.py:41-58`)
9. `DocStore.record_chunks(chunk_models)` + `upsert_document(doc_model)` (`main.py:259-276`); best-effort JSON disk cache `pages.json`/`chunks.json`/`manifest.json` under `.cache/<sha256>/<CONFIG_VERSION>/` (`main.py:279-289`, `models.py:17-30`); `sqlite3.IntegrityError` on duplicate handled as info (`main.py:274-276`)
10. Session state updated (`doc_ids`, `indexed_files`, `document_metadata`); any genuinely new PDF clears `chat_history` and calls `st.rerun()` (`main.py:291-304`)

### Secondary Flow — Query (question → streamed grounded answer)

1. User submits via `st.chat_input` (disabled unless an index exists and provider health is `healthy`) (`main.py:351-360`); offline placeholder names both recovery paths (`main.py:352-356`)
2. Sources pre-fetched for display: `local_embedding.search(prompt, k=10)` filenames collected into a set (`main.py:372-376`)
3. `AiModel.ask_a_question_from_pdf_stream(pdf_path="", prompt, local_embedding, chat_history[-10:])` (`main.py:385-393`, signature `local_llm.py:99-105`)
4. Retrieval contextualized with the last user question (`last_user_msg + " " + prompt`) for follow-ups, then `local_embedding.get_context(search_query, k=10)` (`local_llm.py:123-134`)
5. `assemble_grounded_messages(prompt, context_text, history, max_context_tokens=caps.context_window)` builds `[system(with context), ...retained history, user]` (`local_llm.py:136-146`, `prompt_budget.py:48-117`): input budget = `context_window − 1024` reserved output; prompt truncated first, then context (`[... truncated ...]`), then oldest-first history dropped; all untrusted text passed through `sanitize_xml_boundary` and wrapped in `<document_context>` with an ignore-instructions directive (`prompt_budget.py:11-31`)
6. `provider.stream_text(bounded_prompt, system_prompt, history_turns, max_tokens=1024)` yields tokens — local SSE parse (`llama_cpp_provider.py:155-214`) or Groq stream (`groq_provider.py:128-161`) (`local_llm.py:148-152`)
7. `st.write_stream` renders incrementally and returns the full string appended to `chat_history` with sources (`main.py:394-401`); generation exceptions caught and recorded as an interrupted-assistant turn (`main.py:402-410`)

### Tertiary Flow — Standalone `AiModel` fallback

- If `local_embedding is None` and `pdf_path` is set, `AiModel` builds a `PdfReader` + `LocalEmbedding` inline (`local_llm.py:117-121`). `main.py` never hits this path (always passes an embedding and `pdf_path=""`).

### Health-Status Wiring (`main.py:88-121` + provider layers)

1. `load_ai_model()` constructs `AiModel()` once per server process via `@st.cache_resource` (`main.py:68-76`); constructor probes local `llama-server` first, then Groq if a key exists, else keeps a diagnostic local instance (`local_llm.py:46-67`)
2. Every sidebar render calls `ai_model.check_health()` (`main.py:93`), which re-probes and hot-swaps providers when unhealthy → healthy transitions occur (e.g. llama-server started after boot) (`local_llm.py:69-89`)
3. Badge states: `healthy` + `is_local` → 🟢 Local (`main.py:95-101`); `healthy` + cloud → 🔵 Groq Cloud (`main.py:102-107`); `loading` (llama-server HTTP 503 while loading weights into VRAM) → ⏳ running + info (`main.py:108-114`, `llama_cpp_provider.py:66-71`); otherwise ⚠️ Offline + warning with the provider's actionable message (`main.py:115-121`)
4. Health gates the chat: `is_healthy = health.status == "healthy"` drives the input placeholder, the `disabled=` flag, and a pre-generation error branch (`main.py:351-364`); `st.session_state.ai_model` also exposes the instance so the visual stage can reuse the exact active provider (`main.py:92,232-233`)
5. Provider probes: local `GET /health` with 2 s timeout → healthy/loading/unreachable(with start command)/error (`llama_cpp_provider.py:49-94`, latency in `latency_ms`); Groq checks package presence → key presence → client init (`groq_provider.py:59-83`)
6. Capability display: `get_capabilities()` feeds both the badge (`model_name`, `is_local`) and the token budget (`context_window` → `prompt_budget`, `local_llm.py:136-142`); footer caption shows the active model (`main.py:323`)

**State Management:**
- `st.session_state` (per browser session): `doc_ids: set`, `indexed_files: set`, `document_metadata: dict`, `local_embedding: LocalEmbedding | None`, `chat_history: list` — initialized in `main.py:52-60`; `Clear All` resets all five and reruns (`main.py:130-136`).
- `st.cache_resource` (per server process): the single `AiModel` instance (`main.py:68-76`); also mirrored to `st.session_state.ai_model` (`main.py:92`) for visual-stage reuse.
- `LocalEmbedding`/`VectorIndex` are **not** cached across sessions — each browser session loads its own SentenceTransformer copy.
- Durable state: SQLite at `data/documents.db` (documents/pages/chunks/evidence_elements) + `.cache/<sha256>/<CONFIG_VERSION>/` JSON snapshots.

## Key Abstractions

**Chunk (canonical retrieval unit):**
- Purpose: text plus provenance threaded through every layer.
- Examples: `pdf_reader.py:77-85` / `docling_reader.py:228-266` (construction), `models.py:54-73` (schema), `doc_store.py:253-301` (persistence), `ocr_fallback.py:280-292` (OCR variant).
- Pattern: frozen Pydantic model with legacy-compatible keys (`content`, `filename`, `page`, `chunk_id`) plus `doc_id`, `char_start/end`, `bbox`, `extraction` (`pypdf`/`docling`/`ocr`), `embedding_model`; `model_dump()` feeds `VectorIndex` unchanged.

**Page (extraction ledger):**
- Purpose: per-page status/metrics so one bad page never aborts a document.
- Examples: `docling_reader.py:196-278`, `pdf_reader.py:48-109`, `ocr_fallback.py:204-318` (OCR re-status), `doc_store.py:220-251` (persistence), `main.py:246-250` (progress + warnings).
- Pattern: `Page(doc_id, page_num, status ∈ {ok, empty, failed}, char_count, error, num_chunks)` (`models.py:75-87`).

**ModelProvider:**
- Purpose: swap inference backends without touching orchestration; share one instance between chat generation and visual analysis.
- Examples: `model_provider.py:64-156` (contract), `groq_provider.py:18-170`, `llama_cpp_provider.py:18-268`.
- Pattern: ABC + `ProviderCapabilities`/`HealthStatus` frozen schemas (`model_provider.py:15-61`); `AiModel` selects at construction (`local_llm.py:46-67`), re-probes on `check_health` (`local_llm.py:69-89`), and delegates `stream_text` (`local_llm.py:148-152`); context-managed `close()` per provider.

**Grounded prompt budget:**
- Purpose: guarantee the 4K context ceiling and neutralize prompt injection from documents.
- Examples: `prompt_budget.py:48-117`, asserted in `tests/test_prompt_budget.py`.
- Pattern: chars/4 heuristic token estimate (`prompt_budget.py:34-45`) → reserve 1024 output → truncate prompt, then context with `[... truncated ...]`, then drop oldest history first → wrap untrusted context in `<document_context>` with an explicit ignore-instructions directive (`SYSTEM_GROUNDING_TEMPLATE`, `prompt_budget.py:11-17`); `sanitize_xml_boundary` escapes spoofed tags (`prompt_budget.py:20-31`).

**EvidenceElement (visual provenance):**
- Purpose: keep VLM visual approximations strictly separated from ground-truth text/table extractions.
- Examples: `visual_analyzer.py:185-264` (production), `models.py:90-112` (schema), `doc_store.py:56-75,327-398` (v2 table + accessors).
- Pattern: `EvidenceElement(element_id=elem_<doc>_p<page>_<kind>_<idx>, kind ∈ {text, table, chart, image}, source="vlm:<model>", model_version)`; `main.py:240` persists them without touching chunk tables.

**Unified multi-document index:**
- Purpose: one `LocalEmbedding`/`VectorIndex` pair spans all uploaded PDFs; per-document attribution via chunk `filename`/`doc_id`.
- Examples: `main.py:254-256,372`, `local_embedding.py:41-58`.
- Pattern: append-only in-memory growth; full reset only via Clear All; durable chunks replayable from `DocStore` (`main.py:194-200`).

## Entry Points

**Streamlit app:**
- Location: `main.py`
- Triggers: `streamlit run main.py` (local), devcontainer `postAttachCommand`, Streamlit Community Cloud
- Responsibilities: `st.set_page_config` must be the first Streamlit call (`main.py:38-43`); session-state init (`main.py:52-60`); cached `AiModel` (`main.py:68-76`); sidebar health + upload loop (`main.py:83-323`); chat loop (`main.py:330-410`).

**Benchmark harness:**
- Location: `scripts/benchmark_baseline.py`
- Triggers: `python scripts/benchmark_baseline.py`
- Responsibilities: measure extraction, chunking, CPU embedding, and linear-scan latencies plus RSS; write `.planning/research/BASELINE_BENCHMARK.json`.

**Test corpus generator:**
- Location: `tests/data/corpus/generate_corpus.py`
- Triggers: `python tests/data/corpus/generate_corpus.py` (also a CI step)
- Responsibilities: emit 6 synthetic PDFs (clean digital, multi-column, dense table, scanned, chart, corrupt).

## Architectural Constraints

- **Threading:** Single-threaded Streamlit script model — `main.py` reruns top-to-bottom on every interaction; long work (model load, Docling conversion, OCR, embedding) blocks the script and is masked with `st.status`/`st.progress` (`main.py:90,148,206`). Streaming is incremental rendering, not background work.
- **Global state:** One process-wide `AiModel` via `@st.cache_resource` (`main.py:68-76`); per-session `LocalEmbedding` + `SentenceTransformer` + `VectorIndex` in `st.session_state`. `DocStore` opens/closes a connection per operation, so multiple sessions can interleave safely (`doc_store.py:97-114`; asserted by `tests/test_doc_store.py` interleave test).
- **Circular imports:** None. Direction is one-way: `main.py` → `local_llm.py` → `{groq_provider, llama_cpp_provider, prompt_budget, local_embedding, pdf_reader}` → `{model_provider, vector_index, models}`; `docling_reader.py` → `pdf_reader.py` (fallback only); `ocr_fallback.py`/`visual_analyzer.py` → `models.py` only.
- **In-memory vectors:** `VectorIndex` never touches disk; vectors are lost on server restart and must be re-embedded (chunks + pages + evidence survive in SQLite and `.cache`).
- **VRAM ceiling:** exactly one GGUF model in VRAM; context bounded to 4096 (`llama_cpp_provider.py:21-27`, `prompt_budget.py:48-68`); embeddings + Docling + RapidOCR pinned to CPU.
- **No network egress locally:** only the optional Groq provider makes outbound calls; llama-server is bound to `127.0.0.1` (`llama_cpp_provider.py:21-43`).

## Anti-Patterns

### Double retrieval per question

**What happens:** `main.py:372` calls `local_embedding.search(prompt, k=10)` to display sources, then `local_llm.py:134` calls `local_embedding.get_context(search_query, k=10)`, which embeds and scans again.
**Why it's wrong:** Duplicate embedding + full linear scan on every question; source display can also diverge from the query used for grounding (raw prompt vs history-contextualized prompt).
**Do this instead:** Have `AiModel` return or expose the retrieved chunks once and let the UI render those, rather than re-querying independently.

### Dead fallback parameters (`pdf_path`)

**What happens:** `ask_a_question_from_pdf_stream` accepts `pdf_path` and builds an inline `PdfReader` + `LocalEmbedding` when no index is supplied (`local_llm.py:117-121`), but `main.py` always passes `pdf_path=""` and an existing index (`main.py:388-393`).
**Why it's wrong:** Unused branch that lazily constructs ingestion concerns inside the inference layer.
**Do this instead:** Keep retrieval wiring in `main.py`; either remove the branch or cover it with an explicit dedicated entry point.

### Hand-rolled dispatch instead of the provider contract

**What happens:** `AiModel._detect_provider` constructs concrete `LlamaCppProvider`/`GroqProvider` and probes them directly (`local_llm.py:46-67`); the visual stage reaches into `current_model._provider`, a private attribute (`main.py:233`).
**Why it's wrong:** Provider selection logic is embedded in the orchestrator rather than configurable, so adding a backend requires editing `AiModel`; private-attribute access couples the UI to `AiModel` internals.
**Do this instead:** Route selection through a factory/config so `BaseModelProvider` implementations stay pluggable, and expose the active provider via a public accessor.

## Error Handling

**Strategy:** Fail fast at boundaries with typed schemas; isolate and continue for per-page/per-file work; surface actionable health instead of crashing.

**Patterns:**
- Per-page fault isolation in `PdfReader.extract_text` and `DoclingReader.extract_text` — a failing page records a `failed` `Page` and the loop continues (`pdf_reader.py:98-109`; `docling_reader.py:288-293` fallback); OCR faults collapse to `failed` page records without touching sibling pages (`ocr_fallback.py:306-318`); visual crop/VLM failures degrade to placeholder `EvidenceElement` content (`visual_analyzer.py:225-249`).
- Upload validation raises `ValueError` with user-actionable text (`upload_validation.py:64-113`), caught in the UI and reported via `st.error` before `continue` (`main.py:171-175`).
- Constructor validation: `VectorIndex` raises `ValueError`/`TypeError` on bad metric, missing `content`, dimension mismatch, `k <= 0` (`vector_index.py:26-27,50-59,76-87,121-125`); `DocStore` raises `TypeError` on wrong model types (`doc_store.py:138-139,178-179,227-228`); `BBox`/`Document` validators reject bad coordinates and non-`doc_` ids (`models.py:47-51,109-138`).
- Providers never raise on missing config — they return an `unreachable`/`error` `HealthStatus` (`groq_provider.py:59-83`, `llama_cpp_provider.py:49-94`), and `AiModel` starts degraded rather than failing (`local_llm.py:46-67`).
- Chat streaming errors are caught in the UI and recorded as interrupted-assistant turns (`main.py:402-410`); visual/OCR errors never propagate to the chat path.

## Cross-Cutting Concerns

**Logging:** `print()` with a `[Module]` prefix for developer diagnostics (`[LocalEmbedding]`, `[DocStore]`, `[UploadValidation]`); `logging` (`logger.info/warning/error`) inside `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py`; Streamlit widgets for anything user-visible.
**Validation:** Pydantic v2 everywhere (`models.py`, `model_provider.py`) with `extra="forbid"` and `frozen=True` where immutability matters; ad-hoc guards in `VectorIndex`; magic-byte/size/page validation at the upload boundary.
**Authentication:** Not applicable — single-user local app; only the optional `GROQ_API_KEY`.
**Configuration:** `MAX_FILE_MB`/`MAX_PAGES` (`upload_validation.py:15-16`), `CONFIG_VERSION` (`models.py:14`), OCR threshold 50 / DPI 150 (`ocr_fallback.py:29,81`), visual zoom 2.0 (`visual_analyzer.py:143`), and provider defaults are module-level literals; context window flows from `ProviderCapabilities.context_window` into `prompt_budget`.

## Test / Benchmark / CI

- **Runner:** `pytest` (`pyproject.toml:13-20` — `testpaths=["tests"]`, `python_files=["test_*.py"]`); offline by design via `tests/conftest.py` seams (`mock_sentence_transformer`, `mock_llama_provider`, `mock_groq_client`, `fake_env_groq_key`, `sample_pdf_path`).
- **Coverage:** 13 test modules, one per root module (`test_doc_store`, `test_docling_reader`, `test_llama_cpp_provider`, `test_local_embedding`, `test_local_llm`, `test_model_provider`, `test_models`, `test_ocr_fallback`, `test_pdf_reader`, `test_prompt_budget`, `test_upload_validation`, `test_vector_index`, `test_visual_analyzer`); corpus fixtures generated by `tests/data/corpus/generate_corpus.py` (6 PDFs: clean, multi-column, dense table, scanned, chart, corrupt).
- **Benchmark:** `python scripts/benchmark_baseline.py` measures pypdf extraction, chunking, CPU embedding batches, `VectorIndex` linear scans (100/500/1000 vectors), and RSS via `psutil`; JSON report to `.planning/research/BASELINE_BENCHMARK.json`.
- **CI:** `.github/workflows/ci.yml` — Python 3.11, install `requirements.txt` + `requirements-test.txt`, `ruff check .` + `ruff format --check .`, regenerate corpus, `pytest tests/ -v`.

---

*Architecture analysis: 2026-10-11*
