"""Visual element detection, high-fidelity cropping, and VLM analysis.

Identifies visual elements (charts, diagrams, flowcharts, figures, visual tables)
using PyMuPDF raster and vector drawing inspection, renders 2x zoom PNG crops,
queries the active BaseModelProvider via analyze_image, and produces canonical
EvidenceElement records with isolated model provenance (VIS-01, VIS-02, VIS-03).
"""

import hashlib
import logging
from typing import Any

from providers.model_provider import BaseModelProvider
from core.models import BBox, EvidenceElement

logger = logging.getLogger(__name__)

try:
    import pymupdf as fitz  # Modern import; the legacy `fitz` alias is deprecated in PyMuPDF >= 1.24
except ImportError:
    fitz = None  # type: ignore[assignment]


DEFAULT_VISION_PROMPT = (
    "Describe this visual element in detail. Identify if it is a chart, diagram, "
    "flowchart, or illustration. Summarize its primary message, structure, "
    "key labels, and data points."
)


class VisualAnalyzer:
    """Detects visual elements, extracts 2x crops, and runs VLM analysis."""

    def __init__(
        self,
        region_detector: Any = None,
        cropper: Any = None,
    ) -> None:
        """Initialize VisualAnalyzer.

        Args:
            region_detector: Optional callable `(pdf_bytes: bytes) -> list[dict]` for mocking.
            cropper: Optional callable `(pdf_bytes: bytes, page_num: int, bbox: BBox) -> bytes` for mocking.
        """
        self._region_detector = region_detector
        self._cropper = cropper
        self._region_cache: dict[str, list[dict[str, Any]]] = {}

    def detect_visual_regions(self, pdf_bytes: bytes) -> list[dict[str, Any]]:
        """Detect bounding boxes for raster images and vector diagrams.

        Args:
            pdf_bytes: Raw binary content of the PDF.

        Returns:
            List of dicts with keys: 'page' (int), 'kind' (str), 'bbox' (BBox).
        """
        if self._region_detector is not None:
            return self._region_detector(pdf_bytes)

        if not pdf_bytes:
            return []

        pdf_sha = hashlib.sha256(pdf_bytes).hexdigest()
        if pdf_sha in self._region_cache:
            return list(self._region_cache[pdf_sha])

        if fitz is None:
            logger.warning("PyMuPDF (fitz) is not installed; visual region detection skipped.")
            return []

        regions: list[dict[str, Any]] = []
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                for page_idx in range(len(doc)):
                    page = doc.load_page(page_idx)
                    page_num = page_idx + 1
                    page_rect = page.rect

                    # 1. Detect embedded raster images
                    image_list = page.get_images()
                    for img_info in image_list:
                        xref = img_info[0]
                        rects = page.get_image_rects(xref)
                        for r in rects:
                            if r.width >= 30 and r.height >= 30:
                                regions.append(
                                    {
                                        "page": page_num,
                                        "kind": "image",
                                        "bbox": BBox(
                                            x0=float(max(0, r.x0)),
                                            y0=float(max(0, r.y0)),
                                            x1=float(min(page_rect.width, r.x1)),
                                            y1=float(min(page_rect.height, r.y1)),
                                        ),
                                    }
                                )

                    # 2. Detect vector diagrams (drawings)
                    drawings = page.get_drawings()
                    if drawings:
                        diagram_rect = None
                        drawing_count = 0
                        for draw in drawings:
                            r = draw.get("rect")
                            if not r:
                                continue
                            # Exclude full page borders/backgrounds (>95% area)
                            if r.width >= page_rect.width * 0.95 and r.height >= page_rect.height * 0.95:
                                continue
                            drawing_count += 1
                            if diagram_rect is None:
                                diagram_rect = fitz.Rect(r)
                            else:
                                diagram_rect = diagram_rect | fitz.Rect(r)

                        # If drawing cluster is substantial (>2 drawings and area > 1000 pt^2)
                        if (
                            diagram_rect is not None
                            and drawing_count >= 2
                            and diagram_rect.is_valid
                            and diagram_rect.width >= 40
                            and diagram_rect.height >= 40
                        ):
                            pad = 10.0
                            x0 = float(max(0.0, diagram_rect.x0 - pad))
                            y0 = float(max(0.0, diagram_rect.y0 - pad))
                            x1 = float(min(page_rect.width, diagram_rect.x1 + pad))
                            y1 = float(min(page_rect.height, diagram_rect.y1 + pad))
                            if x1 > x0 and y1 > y0:
                                regions.append(
                                    {
                                        "page": page_num,
                                        "kind": "chart",
                                        "bbox": BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                                    }
                                )
            finally:
                doc.close()
        except Exception as e:
            logger.error("Visual region detection error: %s", e)

        self._region_cache[pdf_sha] = list(regions)
        return regions

    def crop_visual_element(
        self,
        pdf_bytes: bytes,
        page_num: int,
        bbox: BBox,
        zoom: float = 2.0,
    ) -> bytes:
        """Render a high-resolution PNG image crop of a visual element.

        Args:
            pdf_bytes: Raw binary content of the PDF.
            page_num: 1-indexed page number.
            bbox: Bounding box coordinates on the page.
            zoom: Resolution scale factor (default 2.0x for crisp VLM input).

        Returns:
            PNG image bytes.
        """
        if bbox.x1 <= bbox.x0 or bbox.y1 <= bbox.y0:
            raise ValueError(
                f"Invalid bounding box coordinates: x0={bbox.x0}, x1={bbox.x1}, y0={bbox.y0}, y1={bbox.y1}"
            )

        if self._cropper is not None:
            return self._cropper(pdf_bytes, page_num, bbox)

        if fitz is None:
            raise RuntimeError("PyMuPDF (fitz) is not available for visual cropping.")

        zoom_clamped = min(3.0, max(0.5, float(zoom)))

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if page_num < 1 or page_num > len(doc):
                raise ValueError(f"Invalid page_num {page_num} for document with {len(doc)} pages.")
            page = doc.load_page(page_num - 1)
            clip_rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
            clip_rect = clip_rect.intersect(page.rect)
            if clip_rect.is_empty or clip_rect.width <= 0 or clip_rect.height <= 0:
                raise ValueError("Bounding box does not intersect page boundaries.")

            # Strict pixel budget clamp (max 2048x2048 area) to avoid runaway raster memory allocations
            max_crop_pixels = 2048 * 2048
            est_pixels = (clip_rect.width * zoom_clamped) * (clip_rect.height * zoom_clamped)
            if est_pixels > max_crop_pixels:
                scale = (max_crop_pixels / est_pixels) ** 0.5
                zoom_clamped = max(0.5, zoom_clamped * scale)

            mat = fitz.Matrix(zoom_clamped, zoom_clamped)
            pix = page.get_pixmap(matrix=mat, clip=clip_rect)
            return pix.tobytes("png")
        finally:
            doc.close()

    def analyze_visual_elements(
        self,
        pdf_bytes: bytes,
        doc_id: str,
        provider: BaseModelProvider | None = None,
        prompt: str = DEFAULT_VISION_PROMPT,
        max_regions: int = 20,
        progress_callback: Any = None,
    ) -> list[EvidenceElement]:
        """Detect, crop, and generate VLM descriptions for visual elements.

        Preserves provenance separation by tagging descriptions with
        source="vlm:<model_name>", ensuring ungrounded visual approximations
        never overwrite or contaminate ground-truth table extractions (VIS-03).

        Args:
            pdf_bytes: Raw PDF bytes.
            doc_id: Canonical document identifier.
            provider: Optional BaseModelProvider instance (e.g. Qwen2-VL 2B or Groq fallback).
            prompt: Targeted vision query prompt.
            max_regions: Maximum visual regions to analyze to preserve memory/time budgets (default 20).
            progress_callback: Optional callable (current, total, label) -> None for UI progress updates.

        Returns:
            List of EvidenceElement models representing visual artifacts.
        """
        regions = self.detect_visual_regions(pdf_bytes)
        if not regions:
            return []
        if len(regions) > max_regions:
            logger.info(
                "Capping visual elements from %d to %d to preserve inference budget",
                len(regions),
                max_regions,
            )
            regions = regions[:max_regions]

        supports_vision = False
        model_name = "unknown"
        if provider is not None:
            caps = provider.get_capabilities()
            model_name = caps.model_name
            if caps.is_local:
                supports_vision = caps.supports_vision
            else:
                supports_vision = False
                logger.warning(
                    "Non-local provider (%s) rejected for visual element analysis to enforce local-only ingestion invariant (INF-03).",
                    caps.model_name,
                )

        elements: list[EvidenceElement] = []
        for idx, reg in enumerate(regions):
            page_num = reg["page"]
            kind = reg["kind"]
            bbox = reg["bbox"]
            element_id = f"elem_{doc_id}_p{page_num}_{kind}_{idx:02d}"

            if progress_callback is not None:
                try:
                    progress_callback(idx + 1, len(regions), f"{kind} (page {page_num})")
                except Exception:
                    pass

            try:
                crop_bytes = self.crop_visual_element(pdf_bytes, page_num, bbox)
            except Exception as e:
                logger.warning("Failed to crop visual element %s: %s", element_id, e)
                crop_bytes = b""

            if supports_vision and provider is not None and crop_bytes:
                try:
                    # Concurrency gate: serialize visual inference with GPU chat & summarization
                    from core.local_llm import InferenceGate

                    with InferenceGate.hold(timeout=60.0):
                        description = provider.analyze_image(
                            image_bytes=crop_bytes,
                            prompt=prompt,
                        )
                except Exception as err:
                    logger.error("VLM image analysis failed for %s: %s", element_id, err)
                    description = f"[Visual element: analysis failed: {err}]"
                source = f"vlm:{model_name}"
                version = model_name
            elif not crop_bytes:
                description = "[Visual element: cropping failed, image unavailable]"
                source = f"vlm:{model_name}" if provider is not None else "vlm:none"
                version = model_name
            else:
                description = "[Visual element: vision analysis unsupported by active model]"
                source = f"vlm:{model_name}" if provider is not None else "vlm:none"
                version = model_name

            elements.append(
                EvidenceElement(
                    element_id=element_id,
                    doc_id=doc_id,
                    page=page_num,
                    kind=kind if kind in ("text", "table", "chart", "image") else "chart",
                    content=description,
                    bbox=bbox,
                    source=source,
                    model_version=version,
                )
            )

        return elements
