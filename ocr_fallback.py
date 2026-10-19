"""Conditional RapidOCR fallback for scanned or low-text PDF pages.

Selectively executes CPU-based RapidOCR on pages where primary extraction yields
fewer than 50 characters or empty status, bypassing clean digital pages to preserve
sub-5-second throughput. Isolates OCR failures strictly at the page level.
"""

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import threading
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from models import Chunk, Page

logger = logging.getLogger(__name__)

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    try:
        from rapidocr import RapidOCR
    except ImportError:
        RapidOCR = None  # type: ignore[assignment, misc]

try:
    import pymupdf as fitz  # Modern import; the legacy `fitz` alias is deprecated in PyMuPDF >= 1.24
except ImportError:
    fitz = None  # type: ignore[assignment]


def should_ocr_page(text: str = "", status: str = "ok", threshold: int = 50) -> bool:
    """Determine whether a page requires OCR fallback.

    Args:
        text: Extracted text content of the page.
        status: Canonical status of the page ('ok', 'empty', 'failed').
        threshold: Minimum character count below which OCR is triggered.

    Returns:
        True if page is empty, failed, or text length is below threshold.
    """
    if status in ("empty", "failed"):
        return True
    eff_threshold = max(0, int(threshold))
    return len(text.strip()) < eff_threshold


class OcrEngine:
    """CPU-only OCR engine wrapping RapidOCR and PDF raster rendering."""

    def __init__(
        self,
        recognizer: Any = None,
        renderer: Any = None,
    ) -> None:
        """Initialize OcrEngine.

        Args:
            recognizer: Optional pre-configured RapidOCR instance or mock.
            renderer: Optional callable `(pdf_bytes: bytes, page_num: int) -> bytes`.
        """
        self._recognizer = recognizer
        self._renderer = renderer
        self._ocr_lock = threading.Lock()

        if self._recognizer is None and RapidOCR is not None:
            # RapidOCR runs on CPU by default via ONNX Runtime CPUExecutionProvider
            try:
                self._recognizer = RapidOCR()
            except Exception as e:
                logger.warning("Failed to initialize RapidOCR: %s", e)
                self._recognizer = None

    def is_available(self) -> bool:
        """Check if OCR recognizer and page rendering are available."""
        has_renderer = self._renderer is not None or fitz is not None
        has_recognizer = self._recognizer is not None or RapidOCR is not None
        return bool(has_renderer and has_recognizer)

    def render_page_image(
        self,
        pdf_bytes: bytes,
        page_num: int,
        dpi: int = 150,
    ) -> bytes | None:
        """Render a single PDF page into PNG image bytes.

        Args:
            pdf_bytes: Raw binary content of the PDF.
            page_num: 1-indexed page number.
            dpi: Rendering resolution (default 150 DPI for balanced speed/accuracy).

        Returns:
            PNG image bytes or None if rendering fails/unavailable.
        """
        if self._renderer is not None:
            return self._renderer(pdf_bytes, page_num)

        if fitz is not None:
            eff_dpi = min(300, max(72, int(dpi)))
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                try:
                    if page_num < 1 or page_num > len(doc):
                        return None
                    page = doc.load_page(page_num - 1)
                    zoom = eff_dpi / 72.0
                    matrix = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=matrix)
                    return pix.tobytes("png")
                finally:
                    doc.close()
            except Exception as e:
                logger.warning("Rendering page %d via fitz failed: %s", page_num, e)
                return None

        return None

    def ocr_page_image(self, image_data: bytes | Any) -> tuple[str, float]:
        """Run OCR on image bytes or array.

        Args:
            image_data: PNG bytes or numpy array.

        Returns:
            Tuple of (extracted_text, average_confidence).
        """
        if not image_data:
            return "", 0.0

        with self._ocr_lock:
            if self._recognizer is None and RapidOCR is not None:
                try:
                    self._recognizer = RapidOCR()
                except Exception as e:
                    logger.warning("Lazy RapidOCR initialization failed: %s", e)
                    return "", 0.0

            if self._recognizer is None:
                return "", 0.0

            res = self._recognizer(image_data)
            # RapidOCR v3+ returns RapidOCROutput dataclass (with .txts and .scores)
            # Older versions or wrappers return tuple (result, elapse) or raw result list.
            target = res[0] if isinstance(res, tuple) and len(res) > 0 else res

            # Handle RapidOCROutput or objects with .txts attribute
            if hasattr(target, "txts"):
                raw_txts = getattr(target, "txts", None) or ()
                raw_scores = getattr(target, "scores", None) or ()
                lines = [str(t).strip() for t in raw_txts if str(t).strip()]
                scores: list[float] = []
                for s in raw_scores:
                    try:
                        scores.append(float(s))
                    except (ValueError, TypeError):
                        pass
                full_text = "\n".join(lines)
                avg_score = sum(scores) / len(scores) if scores else 0.0
                return full_text, avg_score

            # Guard against non-iterable target
            if not isinstance(target, (list, tuple)):
                return "", 0.0

            lines: list[str] = []
            scores: list[float] = []
            for item in target:
                # Format: [[box_points], text, score]
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    text_line = str(item[1]).strip()
                    if text_line:
                        lines.append(text_line)
                    try:
                        scores.append(float(item[2]))
                    except (ValueError, TypeError):
                        pass
                elif isinstance(item, (list, tuple)) and len(item) == 2:
                    text_line = str(item[0]).strip()
                    if text_line:
                        lines.append(text_line)

            full_text = "\n".join(lines)
            avg_score = sum(scores) / len(scores) if scores else 0.0
            return full_text, avg_score


def _process_page_ocr(
    page: Page,
    pdf_bytes: bytes,
    curr_chunks: list[dict[str, Any]],
    doc_id: str,
    sha12: str,
    filename: str,
    engine: OcrEngine,
    text_splitter: RecursiveCharacterTextSplitter,
) -> tuple[Page, list[dict[str, Any]]]:
    """Execute OCR and text chunking on a single page with fault isolation."""
    page_num = page.page_num
    curr_text = "\n".join(c.get("content", "") for c in curr_chunks).strip()

    try:
        image_bytes = engine.render_page_image(pdf_bytes, page_num)
        if not image_bytes:
            # Unable to render page image (e.g. missing fitz/renderer)
            return (
                Page(
                    doc_id=doc_id,
                    page_num=page_num,
                    status="empty" if not curr_chunks else page.status,
                    char_count=len(curr_text),
                    error=None,
                    num_chunks=len(curr_chunks),
                ),
                curr_chunks,
            )

        ocr_text, _score = engine.ocr_page_image(image_bytes)
        ocr_text_clean = ocr_text.strip()

        if not ocr_text_clean:
            # OCR yielded no text; preserve existing partial chunks if present (WR-04)
            if curr_chunks:
                return (
                    Page(
                        doc_id=doc_id,
                        page_num=page_num,
                        status=page.status if page.status != "empty" else "ok",
                        char_count=len(curr_text),
                        error=None,
                        num_chunks=len(curr_chunks),
                    ),
                    curr_chunks,
                )
            else:
                return (
                    Page(
                        doc_id=doc_id,
                        page_num=page_num,
                        status="empty",
                        char_count=0,
                        error=None,
                        num_chunks=0,
                    ),
                    [],
                )

        # Split OCR text into canonical chunks
        sub_chunks = text_splitter.split_text(ocr_text_clean)
        page_new_chunks: list[dict[str, Any]] = []
        chunk_idx = 0
        current_offset = 0

        for sc in sub_chunks:
            content = sc.strip()
            if not content:
                continue
            sc_start = ocr_text_clean.find(content, current_offset)
            if sc_start == -1:
                sc_start = current_offset
            sc_end = sc_start + len(content)
            current_offset = sc_end

            chunk_id = f"{sha12}_p{page_num}_{chunk_idx:04d}"
            chunk_model = Chunk(
                content=content,
                filename=filename,
                page=page_num,
                chunk_id=chunk_id,
                doc_id=doc_id,
                char_start=sc_start,
                char_end=sc_end,
                extraction="ocr",
            )
            page_new_chunks.append(chunk_model.model_dump())
            chunk_idx += 1

        return (
            Page(
                doc_id=doc_id,
                page_num=page_num,
                status="ok" if page_new_chunks else "empty",
                char_count=len(ocr_text_clean),
                error=None,
                num_chunks=len(page_new_chunks),
            ),
            page_new_chunks,
        )

    except Exception as err:
        logger.error("Page %d OCR processing failed: %s", page_num, err)
        # Isolate fault to this page: do not crash document ingestion
        return (
            Page(
                doc_id=doc_id,
                page_num=page_num,
                status="failed",
                char_count=0,
                error=str(err),
                num_chunks=0,
            ),
            [],
        )


def apply_conditional_ocr(
    pdf_bytes: bytes,
    page_records: list[Page],
    existing_chunks: list[dict[str, Any] | Chunk],
    doc_id: str,
    sha12: str,
    filename: str = "document.pdf",
    engine: OcrEngine | None = None,
    threshold: int = 50,
) -> tuple[list[Page], list[dict[str, Any]]]:
    """Conditionally run OCR on low-text pages while preserving clean pages.

    Supports concurrent thread-pool batch execution across multi-core CPUs
    when multiple pages require OCR, while preserving exact page order and fault isolation.

    Args:
        pdf_bytes: Raw PDF document bytes.
        page_records: Extracted Page records from primary extraction.
        existing_chunks: Chunks extracted from primary pass.
        doc_id: Canonical document ID.
        sha12: Stable 12-char SHA prefix for chunk IDs.
        filename: Document filename.
        engine: Optional pre-configured OcrEngine.
        threshold: Character count threshold for triggering OCR.

    Returns:
        Updated tuple of (page_records, chunk_dicts).
    """
    active_engine = engine or OcrEngine()
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )

    # Index existing chunks by page number
    page_chunks_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for c in existing_chunks:
        c_dict = c.model_dump() if isinstance(c, Chunk) else dict(c)
        p_num = c_dict.get("page", 1)
        page_chunks_map[p_num].append(c_dict)

    page_results: dict[int, tuple[Page, list[dict[str, Any]]]] = {}
    ocr_tasks: list[tuple[int, Page, list[dict[str, Any]]]] = []

    for idx, page in enumerate(page_records):
        page_num = page.page_num
        curr_chunks = page_chunks_map.get(page_num, [])
        curr_text = "\n".join(c.get("content", "") for c in curr_chunks).strip()

        # Check conditional threshold
        if not should_ocr_page(curr_text, status=page.status, threshold=threshold):
            # Bypass OCR completely: retain clean digital page output
            page_results[idx] = (page, curr_chunks)
        else:
            ocr_tasks.append((idx, page, curr_chunks))

    # Execute OCR on candidate pages
    if len(ocr_tasks) == 1:
        idx, page, curr_chunks = ocr_tasks[0]
        page_results[idx] = _process_page_ocr(
            page=page,
            pdf_bytes=pdf_bytes,
            curr_chunks=curr_chunks,
            doc_id=doc_id,
            sha12=sha12,
            filename=filename,
            engine=active_engine,
            text_splitter=text_splitter,
        )
    elif len(ocr_tasks) > 1:
        # Batch OCR inference across multiple worker threads on multi-core CPUs (CONCERNS.md Performance Bottleneck 1)
        max_workers = min(4, os.cpu_count() or 1, len(ocr_tasks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _process_page_ocr,
                    page=p,
                    pdf_bytes=pdf_bytes,
                    curr_chunks=c,
                    doc_id=doc_id,
                    sha12=sha12,
                    filename=filename,
                    engine=active_engine,
                    text_splitter=text_splitter,
                ): i
                for (i, p, c) in ocr_tasks
            }
            for future in future_to_idx:
                i = future_to_idx[future]
                page_results[i] = future.result()

    updated_pages: list[Page] = []
    final_chunks: list[dict[str, Any]] = []
    for i in range(len(page_records)):
        p, c_list = page_results[i]
        updated_pages.append(p)
        final_chunks.extend(c_list)

    return updated_pages, final_chunks
