# Phase 3: Multimodal Ingestion & Conditional OCR — Research

**Researched:** 2026-10-11
**Domain:** Structured document parsing (Docling), conditional CPU OCR (RapidOCR), visual-element detection + cropping (PyMuPDF), and local VLM figure description on a 4 GB VRAM budget
**Confidence:** MEDIUM-HIGH (APIs verified against current library docs and the existing codebase; integration shapes verified by direct reads. Library versions are candidates to pin at execution time.)

> **Inline-execution deviation.** This phase was planned with `gsd-plan-phase` running all four roles (researcher, planner, checker) in a single context because this runtime has no subagent dispatch. The workflow's `plan-phase.md` normally forbids role collapse; the developer explicitly authorized the deviation for this run. Consequences: the plan-checker gate is a self-review, not an independent context, and the researcher here did **not** spawn `gsd-phase-researcher`. Treat the artifacts accordingly.

---

## Summary

Phase 3 replaces the single-modality, pypdf-only ingestion path with a multimodal pipeline that satisfies **INGEST-03**, **INGEST-04**, **VIS-01**, **VIS-02**, and **VIS-03**:

1. **Structured layout + tables (INGEST-03):** introduce Docling (`DocumentConverter`) to recover reading order, heading hierarchy, and tables as Markdown, emitting canonical `Chunk`/`Page` records.
2. **Conditional OCR (INGEST-04):** detect pages whose extractable text is below the 50-character threshold and invoke RapidOCR (ONNX Runtime, CPU) **only** on those pages, leaving clean digital pages untouched.
3. **Visual element analysis (VIS-01/02/03):** detect chart/diagram/table/image regions with PyMuPDF, crop them to high-fidelity PNGs, describe them with the local VLM via `BaseModelProvider.analyze_image`, and store descriptions as `EvidenceElement` artifacts carrying explicit model/version provenance so VLM approximations never masquerade as ground-truth table text.

The existing data model already reserves the needed slots: `models.py` defines `BBox`, `EvidenceElement`, `Chunk.extraction`, and `Page.status` (`ok`/`empty`/`failed`). The provider layer already exposes `analyze_image` (`model_provider.py:107`, implemented in `llama_cpp_provider.py:220`). Phase 3 is therefore mostly **wiring new extractors into existing contracts**, not new schema design.

---

## 1. Current-State Analysis (verified by direct code reads)

### 1.1 Ingestion today is pypdf-only (`pdf_reader.py`)
- `PdfReader.extract_text` iterates `self.reader.pages`, calls `page.extract_text()`, whitespace-normalizes with `re.sub(r" +", " ", ...)`, then splits with `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`.
- Chunks are constructed as `Chunk(..., extraction="pypdf")`; `char_start`/`char_end` are **never** populated (`CONCERNS.md` "Chunk character offsets never populated").
- Empty pages are recorded as `Page(status="empty", char_count=0)`; failures as `Page(status="failed", error=...)`. This is the exact signal INGEST-04 can branch on — **no new page-state enum is required**.
- Image-only pages yield zero chunks; `tests/test_pdf_reader.py::test_pdf_reader_empty_or_scanned_pdf` asserts `chunks == []` for `scanned_sample.pdf`. Phase 3 must change that outcome for scanned pages without breaking the pypdf baseline for clean pages.

### 1.2 Canonical model already has the multimodal slots (`models.py`)
- `BBox` (frozen, `extra="forbid"`, validated coordinates) — `models.py:33`.
- `EvidenceElement` (`element_id`, `doc_id`, `page`, `kind` ∈ {text,table,chart,image}, `content`, `bbox`, `source`) — `models.py:90`. **`source` is the provenance hook VIS-03 needs.**
- `Chunk.extraction` (default `"pypdf"`) — designed for values like `"docling"` / `"ocr"`.
- `CONFIG_VERSION = "chunker-1000-200-pypdf"` (`models.py:14`) keys the disk cache; the extraction backend change must bump this so stale caches are not reused.

### 1.3 Orchestration and persistence (`main.py`, `doc_store.py`)
- Upload loop: validate → dedup (`DocStore.get_by_sha`) → `PdfReader(...)` → `record_page` per page → `LocalEmbedding.build_index` → `record_chunks` + `upsert_document` → best-effort JSON cache.
- `DocStore` already stores chunks with `bbox_json` and `extraction` columns, and pages with `status`/`char_count`/`error`/`num_chunks`. **There is no table for `EvidenceElement` yet** — Phase 3 must decide: add a migration (`MIGRATIONS[2]`) or serialize evidence into the disk cache only. Adding a table is the durable choice (Phase 4 retrieval will want figures indexed).
- Migrations are additive and version-gated via `PRAGMA user_version` (`doc_store.py:98-110`), so a v2 migration is low-risk.

### 1.4 Inference layer is ready to describe figures
- `BaseModelProvider.analyze_image(image_bytes, prompt, max_tokens=512) -> str` (`model_provider.py:107`).
- `LlamaCppProvider.analyze_image` builds an OpenAI-compatible vision payload with a base64 JPEG data URL and POSTs `/v1/chat/completions` (`llama_cpp_provider.py:220-268`). It is **already implemented and unit-tested offline** but has **no production caller** (`CONCERNS.md` "Vision analysis not wired into ingestion"). Phase 3 supplies that caller.
- `GroqProvider.analyze_image` raises `NotImplementedError` (`groq_provider.py:151`), so visual description must degrade gracefully when the active provider is cloud.

### 1.5 VRAM / CPU constraints (from PROJECT.md + `docs/LOCAL_INFERENCE.md`)
- 4 GB VRAM ceiling; exactly one GGUF model resident. Qwen3-VL 2B Q4_K_M + mmproj + 4K KV ≈ 3.26 GB.
- Embeddings are already CPU-pinned. Docling and RapidOCR must likewise run **CPU-only** and be sequenced so they never compete with the VLM for VRAM. RapidOCR via ONNX Runtime uses CPU execution providers; Docling layout/table models should be forced to CPU.

---

## 2. Docling Integration (INGEST-03)

### 2.1 Verified API shape
```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions

opts = PdfPipelineOptions()
opts.do_ocr = False              # we own OCR (INGEST-04) — avoid double OCR + CPU cost
opts.do_table_structure = True   # table structure model

converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
)
result = converter.convert(DocumentStream(name=filename, stream=io.BytesIO(raw)))  # in-memory
doc = result.document                       # DoclingDocument
markdown = doc.export_to_markdown()          # structured Markdown incl. tables
```
- `DocumentConverter.convert` accepts a `Path`, URL, `DocumentStream`, or `HttpSource`; returns a `ConversionResult` whose `.document` is a `DoclingDocument` when successful.
- In-memory `DocumentStream(name=..., stream=BytesIO)` preserves the app's "no disk IO for uploads" property.
- `export_to_markdown()` yields tables as Markdown tables — the cleanest bridge to the requirement "markdown tables".
- Docling exposes a document object model with element kinds and page provenance, so heading hierarchy can be reconstructed rather than regex-guessed.

### 2.2 Integration design
- New module `docling_reader.py` owning a lazily-initialized, process-wide `DocumentConverter` (converter init loads models; construct once, reuse — mirrors the `@st.cache_resource` pattern used for `AiModel`).
- Emit canonical records:
  - `Page` records derived from Docling's page provenance + char counts (status `ok`/`empty`, `num_chunks`).
  - `Chunk` records with `extraction="docling"` and, where Docling exposes offsets, populated `char_start`/`char_end`.
  - `EvidenceElement(kind="table", source="docling")` for each detected table, `content` = Markdown table.
- Keep `PdfReader` (pypdf) as the fallback when Docling fails or is unavailable — this preserves the existing per-page fault-isolation behavior and keeps the app usable if the heavy dependency is missing (optional-import pattern already used for `groq`).

### 2.3 Performance target
- Success criterion 1: "20 pages < 5 seconds without unnecessary OCR". Docling's table-structure model is the dominant cost. Mitigations: CPU-only, `do_ocr=False`, reuse the converter instance, and gate OCR out. **Measure** with the existing `scripts/benchmark_baseline.py` pattern; treat the 5 s target as a measured goal, not an assertion (CI hardware differs from the RTX 3050 host).

---

## 3. Conditional RapidOCR (INGEST-04)

### 3.1 Candidate dependency
- `rapidocr-onnxruntime` (latest 1.4.4; deps: `onnxruntime`, `opencv-python`, `pillow`, `numpy`). Chosen over PaddleOCR for CPU-only, pip-installable, offline operation. A newer consolidated `rapidocr` package also exists; pin whichever is validated at execution.
- Engine construction downloads/loads ONNX detection+recognition models; construct **once** and reuse (module-level lazy singleton) — per-page re-instantiation would blow the 5 s budget.

### 3.2 Conditional trigger
- After a page's primary extraction, compute extractable text length. If `char_count < 50` **or** status is `empty`, run OCR on that page's rendered image.
- Render the page to a NumPy array via PyMuPDF/Pillow, then:
```python
from rapidocr_onnxruntime import RapidOCR
engine = RapidOCR()
ocr_result, _elapse = engine(img)     # ocr_result: list[[box, text, score]] | None
text = "\n".join(item[1] for item in ocr_result) if ocr_result else ""
```
- Chunks produced from OCR text get `extraction="ocr"` so provenance survives into retrieval and citations.

### 3.3 Fault isolation
- OCR must never abort the document: wrap the OCR call per page in `try/except Exception`, record `Page(status="failed", error=...)` on error, and continue — the same isolate-and-continue contract as `pdf_reader.py:109-122` and the per-file guard in `main.py`.
- Bypass is a first-class requirement: clean digital pages must **not** invoke the engine (verified by asserting the engine is not called for pages above threshold).

---

## 4. Visual Element Detection, Cropping, and VLM Description (VIS-01/02/03)

### 4.1 Detection + cropping with PyMuPDF
- Prefer `import pymupdf` (the modern import path; `import fitz` is legacy).
- Text/layout blocks + bboxes: `page.get_text("dict")["blocks"]` → block `type` (0 text, 1 image) and `bbox`.
- Embedded raster images: `page.get_images(full=True)` + `page.get_image_rects(xref)` → placement rectangles.
- Vector diagrams (the `chart_diagram.pdf` corpus case has no raster images — it is drawn with vector primitives): detect via `page.get_drawings()` density, or fall back to region heuristics. **This is the trickiest detection case and is called out explicitly.**
- High-fidelity crop: `pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=rect)` then `pix.tobytes("png")`; `zoom≥2` for legible figures.
- **Licensing note (raise to developer):** PyMuPDF is **AGPL-3.0**. The requirement text says "PyMuPDF/Pillow", so honor it, but `pypdfium2` is (a) permissively licensed and (b) already pulled in by Docling — a license-clean alternative worth a developer decision before locking the dependency.

### 4.2 VLM description (VIS-02)
- Call the active provider: `ai_model.provider.analyze_image(image_bytes=png, prompt=<targeted prompt>, max_tokens=512)`.
- Prompt should be targeted per element kind, e.g. "Describe this chart: axis labels, series, and key values." / "Transcribe this diagram's boxes and arrows."
- Must degrade gracefully when `provider.get_capabilities().supports_vision is False` (e.g. Groq fallback): skip description, keep the crop, tag `source` accordingly. Never fail the document because vision is unavailable.

### 4.3 Provenance separation (VIS-03)
- Each description becomes an `EvidenceElement(kind="chart"|"diagram"|"image", source=f"vlm:{model_name}")` where `source` encodes model provenance; also record the model/version explicitly so a stronger model's output can be distinguished later.
- **Ground-truth separation is the requirement:** VLM descriptions must never overwrite or merge into Docling table `content`. Tables remain `source="docling"`; VLM text lives in its own tagged elements. Retrieval (Phase 4) can then weight/flag derived visual text separately.

---

## 5. Data Model & Persistence Changes

- Bump `CONFIG_VERSION` (e.g. `"docling-rapidocr-pymupdf-v1"`) so `.cache/<sha>/<version>/` invalidates old pypdf-only caches.
- Add `DocStore` migration `MIGRATIONS[2]`:
  - `evidence_elements(element_id PRIMARY KEY, doc_id, page, kind, content, bbox_json, source, model_version)`.
  - Optionally `ALTER TABLE chunks` if new columns are needed (prefer none — `extraction` covers it).
- `Document.num_chunks` already exists; add nothing schema-breaking.

## 6. Testing Strategy (offline-first)

Reuse the existing synthetic corpus (`tests/data/corpus/generate_corpus.py`):
| Corpus file | Exercises |
|---|---|
| `clean_digital.pdf` (20 pages) | Docling structured extraction + the "no OCR" bypass path + the <5 s timing target |
| `dense_table.pdf` | Markdown table extraction + `EvidenceElement(kind="table", source="docling")` |
| `multi_column.pdf` | Reading-order recovery |
| `scanned_sample.pdf` | Conditional OCR trigger (0 chars → OCR path) |
| `chart_diagram.pdf` | Visual-element detection (vector diagram, no raster) + VLM description |
| `corrupt_invalid.pdf` | Fault isolation unchanged |

- **Mock the VLM**: `provider.analyze_image` via the existing `mock_llama_provider` fixture (`tests/conftest.py:92`) — no GPU.
- **Mock OCR determinism**: monkeypatch a fake `RapidOCR` engine returning canned `[[box, text, score]]`, and assert it is *not called* for clean pages.
- **Docling**: run for real on the small corpus PDFs (offline, CPU) OR mock the converter if CI time is a problem; decide at execution. Prefer at least one real conversion test to catch API drift.
- **Timing**: keep the 5 s/20-page target as a measured benchmark (script), **not** a hard CI assertion — CI runners are slower than the target host and a hard threshold would be flaky.

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Docling is a heavy dependency (large transitive tree, model downloads on first use) | Long installs, first-run latency, CI cost | Pin version; lazy-import so the app still runs pypdf-only if absent; document model pre-fetch in a runbook (mirror `docs/LOCAL_INFERENCE.md`) |
| PyMuPDF AGPL license | Licensing exposure if redistributed | Flag to developer; `pypdfium2` alternative (already a Docling dep) |
| OCR correctness varies on raster scans | Low-quality text entering the index | Tag `extraction="ocr"`; keep confidence from RapidOCR; never let OCR text masquerade as digital text |
| Vector-diagram detection (no raster images) | Charts missed entirely | Combine `get_images` + `get_drawings` density + layout-block heuristics; cover with `chart_diagram.pdf` |
| VLM hallucination contaminating tables | Wrong answers attributed to ground truth | VIS-03 provenance separation; tables stay `source="docling"` |
| VRAM contention (Docling/OCR vs VLM) | Thrashing, >4 GB | CPU-only for Docling/RapidOCR/PyMuPDF; sequence OCR → VLM so only one GPU consumer is active |
| Breaking the pypdf baseline | Regressions on clean digital docs | Keep `PdfReader` as fallback; existing pypdf tests remain green |

## 8. Codebase Map Alignment

- **ARCHITECTURE.md:** new extractors are ingestion-layer modules alongside `pdf_reader.py`; the VLM description step reuses the inference layer via the provider contract (no new coupling to `AiModel` internals). Dependencies stay one-way.
- **CONVENTIONS.md:** flat root modules one class per file; module docstring; Pydantic `frozen=True, extra="forbid"`; `try/except ImportError → None` for optional heavy deps (docling, rapidocr, pymupdf); module-prefixed `print()` diagnostics; per-page isolate-and-continue; Google-style docstrings on public methods.
- **CONCERNS.md:** directly resolves "Vision analysis not wired into ingestion" (`analyze_image` gains a caller) and "OCR / visual ingestion for scanned documents" (missing critical feature). Also addresses "Chunk character offsets never populated" opportunistically via Docling offsets.
- **INTEGRATIONS.md:** adds no external network services; all new processing is local/CPU. New local dependencies only (docling, rapidocr-onnxruntime, pymupdf, pillow).
- **TESTING.md:** extends the offline suite with mocked VLM/OCR transports; keeps zero GPU/network requirement in CI.
- **STACK.md / STRUCTURE.md:** adds root modules `docling_reader.py`, `ocr_fallback.py`, `visual_analyzer.py` (+ tests) and the new pinned dependencies.
