"""Offline unit tests for VisualAnalyzer, high-fidelity cropping, and VLM provenance isolation."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from doc_store import DocStore
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities
from models import BBox, Chunk, Document, EvidenceElement
from visual_analyzer import DEFAULT_VISION_PROMPT, VisualAnalyzer


CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"
CHART_PDF = CORPUS_DIR / "chart_diagram.pdf"
DENSE_TABLE_PDF = CORPUS_DIR / "dense_table.pdf"


class MockVisionProvider(BaseModelProvider):
    """Mock local provider with vision support for offline tests."""

    def __init__(self, model_name: str = "qwen3-vl-2b"):
        self._model_name = model_name
        self.analyze_calls: list[dict] = []

    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="Mock vision ready.", latency_ms=1.0)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            model_name=self._model_name,
            context_window=4096,
            supports_vision=True,
            is_local=True,
            supports_streaming=True,
        )

    def generate_text(
        self, prompt: str, system_prompt: str | None = None, max_tokens: int = 1024, temperature: float = 0.2
    ) -> str:
        return "Mock text response."

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ):
        yield "Mock text stream."

    def analyze_image(self, image_bytes: bytes, prompt: str, max_tokens: int = 512) -> str:
        self.analyze_calls.append({"image_len": len(image_bytes), "prompt": prompt})
        return "Architecture flowchart showing Ingestion, Hybrid Search, and Local VLM processing stages."


class MockTextOnlyProvider(BaseModelProvider):
    """Mock provider without vision support (e.g. Groq Cloud text fallback)."""

    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="Mock text provider.", latency_ms=1.0)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            model_name="llama-3.3-70b-versatile",
            context_window=8192,
            supports_vision=False,
            is_local=False,
            supports_streaming=True,
        )

    def generate_text(
        self, prompt: str, system_prompt: str | None = None, max_tokens: int = 1024, temperature: float = 0.2
    ) -> str:
        return "Text only."

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ):
        yield "Text only."

    def analyze_image(self, image_bytes: bytes, prompt: str, max_tokens: int = 512) -> str:
        raise NotImplementedError("Vision not supported by this model.")


def test_visual_element_detection_and_cropping():
    """Verify visual elements are detected and cropped to high-resolution PNG bytes."""
    mock_detector = MagicMock(
        return_value=[
            {
                "page": 1,
                "kind": "chart",
                "bbox": BBox(x0=72.0, y0=592.0, x1=532.0, y1=652.0),
            }
        ]
    )
    mock_cropper = MagicMock(return_value=b"fake_high_res_png_crop")

    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=mock_cropper)
    pdf_bytes = CHART_PDF.read_bytes()

    regions = analyzer.detect_visual_regions(pdf_bytes)
    assert len(regions) == 1
    assert regions[0]["kind"] == "chart"
    assert regions[0]["page"] == 1

    crop = analyzer.crop_visual_element(pdf_bytes, 1, regions[0]["bbox"])
    assert crop == b"fake_high_res_png_crop"
    mock_cropper.assert_called_once()


def test_vlm_analysis_with_targeted_prompt():
    """Verify VLM is queried with targeted prompt and produces EvidenceElement with provenance."""
    mock_detector = MagicMock(
        return_value=[
            {
                "page": 1,
                "kind": "chart",
                "bbox": BBox(x0=72.0, y0=592.0, x1=532.0, y1=652.0),
            }
        ]
    )
    mock_cropper = MagicMock(return_value=b"valid_png_crop_bytes")
    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=mock_cropper)

    provider = MockVisionProvider(model_name="qwen3-vl-2b")
    pdf_bytes = CHART_PDF.read_bytes()

    elements = analyzer.analyze_visual_elements(
        pdf_bytes=pdf_bytes,
        doc_id="doc_chart123",
        provider=provider,
    )

    assert len(elements) == 1
    elem = elements[0]
    assert elem.doc_id == "doc_chart123"
    assert elem.page == 1
    assert elem.kind == "chart"
    assert "Architecture flowchart" in elem.content
    assert elem.source == "vlm:qwen3-vl-2b"
    assert elem.model_version == "qwen3-vl-2b"
    assert elem.bbox is not None

    # Verify provider was called with the targeted vision prompt
    assert len(provider.analyze_calls) == 1
    assert provider.analyze_calls[0]["prompt"] == DEFAULT_VISION_PROMPT


def test_graceful_degradation_when_vision_unsupported():
    """Verify non-vision providers gracefully record placeholder without crashing."""
    mock_detector = MagicMock(
        return_value=[
            {
                "page": 1,
                "kind": "chart",
                "bbox": BBox(x0=50.0, y0=50.0, x1=200.0, y1=200.0),
            }
        ]
    )
    mock_cropper = MagicMock(return_value=b"fake_crop")
    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=mock_cropper)

    provider = MockTextOnlyProvider()
    pdf_bytes = CHART_PDF.read_bytes()

    elements = analyzer.analyze_visual_elements(
        pdf_bytes=pdf_bytes,
        doc_id="doc_textonly",
        provider=provider,
    )

    assert len(elements) == 1
    elem = elements[0]
    assert "vision analysis unsupported" in elem.content
    assert elem.source == "vlm:llama-3.3-70b-versatile"


def test_provenance_separation_from_ground_truth_tables(tmp_path):
    """Verify visual descriptions do not overwrite or contaminate ground truth table data (VIS-03)."""
    db_file = tmp_path / "provenance.db"
    store = DocStore(db_file)

    doc_id = "doc_dual_evidence"
    store.upsert_document(
        Document(
            doc_id=doc_id,
            filename="dense_table.pdf",
            sha256="d" * 64,
            size_bytes=1024,
            num_pages=1,
            status="indexed",
            upload_time="2026-10-11T10:00:00Z",
            num_chunks=1,
        )
    )

    # 1. Ground truth table extracted from Docling
    table_chunk = Chunk(
        content="| Metric | Q1 | Q2 |\n|---|---|---|\n| Revenue | $124.5M | $142.1M |",
        filename="dense_table.pdf",
        page=1,
        chunk_id="chunk_table_0001",
        doc_id=doc_id,
        extraction="docling",
    )
    store.record_chunks([table_chunk])

    # 2. VLM visual description of a diagram
    visual_element = EvidenceElement(
        element_id="elem_diagram_0001",
        doc_id=doc_id,
        page=1,
        kind="chart",
        content="System architecture showing flow from ingestion to vector index.",
        bbox=BBox(x0=72.0, y0=100.0, x1=400.0, y1=300.0),
        source="vlm:qwen3-vl-2b",
        model_version="qwen3-vl-2b",
    )
    store.record_evidence_elements([visual_element])

    # Verify Chunk store retains exact table markdown and extraction="docling"
    stored_chunks = store.get_chunks_for_doc(doc_id)
    assert len(stored_chunks) == 1
    assert stored_chunks[0].extraction == "docling"
    assert "$124.5M" in stored_chunks[0].content

    # Verify EvidenceElement store retains separate VLM provenance
    stored_evidence = store.get_evidence_for_doc(doc_id)
    assert len(stored_evidence) == 1
    assert stored_evidence[0].source == "vlm:qwen3-vl-2b"
    assert stored_evidence[0].kind == "chart"

    # Sources are strictly disjoint
    assert stored_chunks[0].extraction != stored_evidence[0].source


def test_vlm_analysis_error_isolation():
    """Verify exception in analyze_image is caught and recorded without aborting document."""
    mock_detector = MagicMock(
        return_value=[
            {
                "page": 1,
                "kind": "chart",
                "bbox": BBox(x0=10.0, y0=10.0, x1=100.0, y1=100.0),
            }
        ]
    )
    mock_cropper = MagicMock(return_value=b"crop_bytes")
    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=mock_cropper)

    failing_provider = MockVisionProvider()
    failing_provider.analyze_image = MagicMock(side_effect=RuntimeError("VLM GPU inference timeout"))

    elements = analyzer.analyze_visual_elements(
        pdf_bytes=b"%PDF...",
        doc_id="doc_fail",
        provider=failing_provider,
    )

    assert len(elements) == 1
    assert "analysis failed" in elements[0].content
    assert "VLM GPU inference timeout" in elements[0].content


def test_crop_visual_element_out_of_bounds_and_inverted_coords(monkeypatch):
    """Verify crop_visual_element rejects inverted or non-intersecting boxes (WR-02)."""
    analyzer = VisualAnalyzer()
    pdf_bytes = CHART_PDF.read_bytes()

    # Inverted coordinates: BBox Pydantic model rejects them
    with pytest.raises(ValueError):
        BBox(x0=200.0, y0=300.0, x1=100.0, y1=200.0)

    # Inverted coordinates bypassing validation (e.g. model_construct): crop_visual_element rejects them
    inverted_bbox = BBox.model_construct(x0=200.0, y0=300.0, x1=100.0, y1=200.0)
    with pytest.raises(ValueError, match="Invalid bounding box coordinates"):
        analyzer.crop_visual_element(pdf_bytes, page_num=1, bbox=inverted_bbox)

    # Provide offline PyMuPDF mock if fitz is not installed
    class FakeRect:
        def __init__(self, x0, y0, x1, y1):
            self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

        def intersect(self, other):
            ix0 = max(self.x0, other.x0)
            iy0 = max(self.y0, other.y0)
            ix1 = min(self.x1, other.x1)
            iy1 = min(self.y1, other.y1)
            if ix1 <= ix0 or iy1 <= iy0:
                return FakeRect(0, 0, 0, 0)
            return FakeRect(ix0, iy0, ix1, iy1)

        @property
        def is_empty(self):
            return self.x1 <= self.x0 or self.y1 <= self.y0

        @property
        def width(self):
            return max(0.0, self.x1 - self.x0)

        @property
        def height(self):
            return max(0.0, self.y1 - self.y0)

    class FakePage:
        rect = FakeRect(0, 0, 612, 792)

    class FakeDoc:
        def __len__(self):
            return 1

        def load_page(self, idx):
            return FakePage()

        def close(self):
            pass

    class FakeFitz:
        Rect = FakeRect

        @staticmethod
        def open(stream=None, filetype=None):
            return FakeDoc()

    monkeypatch.setattr("visual_analyzer.fitz", FakeFitz)

    # Non-intersecting bounding box (completely outside page boundaries)
    out_of_bounds_bbox = BBox(x0=5000.0, y0=5000.0, x1=6000.0, y1=6000.0)
    with pytest.raises(ValueError, match="Bounding box does not intersect page boundaries"):
        analyzer.crop_visual_element(pdf_bytes, page_num=1, bbox=out_of_bounds_bbox)


def test_crop_failure_description_attribution():
    """Verify cropping failure is accurately attributed rather than claiming model lacks vision (WR-01)."""
    mock_detector = MagicMock(
        return_value=[
            {
                "page": 1,
                "kind": "chart",
                "bbox": BBox(x0=10.0, y0=10.0, x1=50.0, y1=50.0),
            }
        ]
    )

    # Cropper fails
    def failing_cropper(pdf_bytes, page_num, bbox):
        raise RuntimeError("Pixmap allocation failure")

    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=failing_cropper)
    provider = MockVisionProvider()  # Provider DOES support vision

    elements = analyzer.analyze_visual_elements(
        pdf_bytes=b"%PDF...",
        doc_id="doc_crop_fail",
        provider=provider,
    )

    assert len(elements) == 1
    # Must NOT claim model does not support vision
    assert "vision analysis unsupported" not in elements[0].content
    # Must correctly attribute to cropping failure
    assert "cropping failed, image unavailable" in elements[0].content


def test_max_regions_cap_enforced():
    """Verify analyze_visual_elements respects max_regions parameter to prevent resource exhaustion."""
    mock_detector = MagicMock(
        return_value=[{"page": 1, "kind": "chart", "bbox": BBox(x0=10.0, y0=10.0, x1=50.0, y1=50.0)} for _ in range(50)]
    )
    analyzer = VisualAnalyzer(region_detector=mock_detector, cropper=lambda *args: b"mock_png")
    elements = analyzer.analyze_visual_elements(
        pdf_bytes=b"%PDF...",
        doc_id="doc_cap",
        max_regions=5,
    )
    assert len(elements) == 5
