"""Offline unit tests for conditional RapidOCR fallback and page-level fault isolation."""

from pathlib import Path
from unittest.mock import MagicMock

from models import Chunk, Page
from ocr_fallback import OcrEngine, apply_conditional_ocr, should_ocr_page


CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"
CLEAN_PDF = CORPUS_DIR / "clean_digital.pdf"
SCANNED_PDF = CORPUS_DIR / "scanned_sample.pdf"


def test_ocr_fallback_uses_modern_pymupdf_import():
    """Regression: use `import pymupdf` rather than the deprecated `fitz` alias (no startup warning)."""
    import pymupdf

    import ocr_fallback

    assert ocr_fallback.fitz is pymupdf


def test_should_ocr_page_thresholds():
    """Verify < 50 character threshold and status conditions."""
    # Under 50 chars -> triggers
    assert should_ocr_page("Short header text", status="ok", threshold=50) is True
    assert should_ocr_page("", status="ok", threshold=50) is True

    # 50 chars or more -> bypasses
    long_text = "A" * 50
    assert should_ocr_page(long_text, status="ok", threshold=50) is False
    assert should_ocr_page("B" * 150, status="ok", threshold=50) is False

    # Status empty or failed always triggers
    assert should_ocr_page(long_text, status="empty", threshold=50) is True
    assert should_ocr_page(long_text, status="failed", threshold=50) is True


def test_clean_digital_page_bypass():
    """Verify clean pages bypass OCR completely with zero recognizer invocations."""
    mock_recognizer = MagicMock()
    mock_renderer = MagicMock()
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(
            doc_id="doc_clean",
            page_num=1,
            status="ok",
            char_count=200,
            error=None,
            num_chunks=1,
        )
    ]
    chunks = [
        Chunk(
            content="This is a clean page with plenty of characters exceeding fifty total.",
            filename="clean_digital.pdf",
            page=1,
            chunk_id="testsha12345_p1_0000",
            doc_id="doc_clean",
            extraction="docling",
        )
    ]

    pdf_bytes = CLEAN_PDF.read_bytes()
    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=pdf_bytes,
        page_records=pages,
        existing_chunks=chunks,
        doc_id="doc_clean",
        sha12="testsha12345",
        filename="clean_digital.pdf",
        engine=engine,
        threshold=50,
    )

    # Recognizer and renderer should never have been invoked
    mock_recognizer.assert_not_called()
    mock_renderer.assert_not_called()

    assert len(updated_pages) == 1
    assert updated_pages[0].status == "ok"
    assert len(updated_chunks) == 1
    assert updated_chunks[0]["extraction"] == "docling"


def test_scanned_page_triggers_ocr_and_sets_provenance():
    """Verify empty/scanned pages trigger OCR and assign extraction='ocr'."""
    mock_recognizer = MagicMock()
    # Mock RapidOCR return format: list of [[box], text, score]
    mock_recognizer.return_value = (
        [
            [[[0, 0], [10, 0], [10, 10], [0, 10]], "Extracted Scanned Header", 0.98],
            [[[0, 20], [10, 20], [10, 30], [0, 30]], "Paragraph of scanned text data.", 0.95],
        ],
        0.05,
    )

    mock_renderer = MagicMock(return_value=b"fake_png_image_bytes")
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(
            doc_id="doc_scanned",
            page_num=1,
            status="empty",
            char_count=0,
            error=None,
            num_chunks=0,
        )
    ]
    existing_chunks: list[dict] = []

    pdf_bytes = SCANNED_PDF.read_bytes()
    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=pdf_bytes,
        page_records=pages,
        existing_chunks=existing_chunks,
        doc_id="doc_scanned",
        sha12="scanned12345",
        filename="scanned_sample.pdf",
        engine=engine,
        threshold=50,
    )

    # Renderer and recognizer should have been called once
    mock_renderer.assert_called_once_with(pdf_bytes, 1)
    mock_recognizer.assert_called_once_with(b"fake_png_image_bytes")

    assert len(updated_pages) == 1
    assert updated_pages[0].status == "ok"
    assert updated_pages[0].char_count > 0
    assert updated_pages[0].num_chunks >= 1

    assert len(updated_chunks) >= 1
    for chunk in updated_chunks:
        assert chunk["extraction"] == "ocr"
        assert chunk["doc_id"] == "doc_scanned"
        assert chunk["chunk_id"].startswith("scanned12345_p1_")


def test_page_level_fault_isolation():
    """Verify OCR failure on one page records status='failed' without aborting other pages."""

    def renderer_side_effect(pdf_bytes, page_num):
        if page_num == 2:
            raise RuntimeError("Corrupt font/rendering crash on page 2")
        return b"fake_png_bytes"

    mock_renderer = MagicMock(side_effect=renderer_side_effect)
    mock_recognizer = MagicMock(return_value=([[[[0, 0], [1, 0], [1, 1], [0, 1]], "Page 1 clean OCR text", 0.9]], 0.01))
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(
            doc_id="doc_multi",
            page_num=1,
            status="empty",
            char_count=0,
            error=None,
            num_chunks=0,
        ),
        Page(
            doc_id="doc_multi",
            page_num=2,
            status="empty",
            char_count=0,
            error=None,
            num_chunks=0,
        ),
    ]

    pdf_bytes = b"%PDF-1.4..."
    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=pdf_bytes,
        page_records=pages,
        existing_chunks=[],
        doc_id="doc_multi",
        sha12="multi1234567",
        filename="multi_page.pdf",
        engine=engine,
        threshold=50,
    )

    assert len(updated_pages) == 2
    # Page 1 succeeded
    assert updated_pages[0].page_num == 1
    assert updated_pages[0].status == "ok"
    # Page 2 failed gracefully
    assert updated_pages[1].page_num == 2
    assert updated_pages[1].status == "failed"
    assert "Corrupt font/rendering crash on page 2" in (updated_pages[1].error or "")

    # Only chunks from page 1 exist
    assert len(updated_chunks) >= 1
    assert all(c["page"] == 1 for c in updated_chunks)


def test_graceful_handling_when_no_ocr_available():
    """Verify apply_conditional_ocr handles unavailable OCR without crashing."""
    engine = OcrEngine(recognizer=None, renderer=None)
    pages = [
        Page(
            doc_id="doc_no_ocr",
            page_num=1,
            status="empty",
            char_count=0,
            error=None,
            num_chunks=0,
        )
    ]

    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=b"%PDF-1.4...",
        page_records=pages,
        existing_chunks=[],
        doc_id="doc_no_ocr",
        sha12="noocr1234567",
        filename="no_ocr.pdf",
        engine=engine,
    )

    assert len(updated_pages) == 1
    assert updated_pages[0].status == "empty"
    assert len(updated_chunks) == 0


def test_ocr_empty_image_guard():
    """Verify ocr_page_image handles empty bytes without invoking recognizer (WR-03)."""
    mock_recognizer = MagicMock()
    engine = OcrEngine(recognizer=mock_recognizer)

    text, score = engine.ocr_page_image(b"")
    assert text == ""
    assert score == 0.0
    mock_recognizer.assert_not_called()


def test_ocr_empty_result_preserves_existing_chunks():
    """Verify empty OCR result does not discard existing partial chunks (WR-04)."""
    mock_recognizer = MagicMock(return_value=([], 0.0))
    mock_renderer = MagicMock(return_value=b"fake_image_bytes")
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(
            doc_id="doc_partial",
            page_num=1,
            status="ok",
            char_count=20,
            error=None,
            num_chunks=1,
        )
    ]
    chunks = [
        Chunk(
            content="Partial line.",
            filename="partial.pdf",
            page=1,
            chunk_id="partial12345_p1_0000",
            doc_id="doc_partial",
            extraction="docling",
        )
    ]

    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=b"%PDF...",
        page_records=pages,
        existing_chunks=chunks,
        doc_id="doc_partial",
        sha12="partial12345",
        filename="partial.pdf",
        engine=engine,
        threshold=50,
    )

    # Should retain the existing chunk and page status
    assert len(updated_pages) == 1
    assert updated_pages[0].char_count == len("Partial line.")
    assert len(updated_chunks) == 1
    assert updated_chunks[0]["content"] == "Partial line."
    assert updated_chunks[0]["extraction"] == "docling"


def test_ocr_chunk_char_offsets_and_monotonic_ids():
    """Verify OCR chunks have populated character offsets and monotonic chunk IDs (IN-01, IN-02)."""
    line1 = "First OCR paragraph " + ("word " * 120)
    line2 = "Second OCR paragraph " + ("term " * 120)
    mock_recognizer = MagicMock(
        return_value=(
            [
                [[[0, 0], [1, 0], [1, 1], [0, 1]], line1, 0.95],
                [[[0, 10], [1, 10], [1, 11], [0, 11]], line2, 0.92],
            ],
            0.02,
        )
    )
    mock_renderer = MagicMock(return_value=b"fake_png_bytes")
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(
            doc_id="doc_monotonic",
            page_num=1,
            status="empty",
            char_count=0,
            error=None,
            num_chunks=0,
        )
    ]

    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=b"%PDF...",
        page_records=pages,
        existing_chunks=[],
        doc_id="doc_monotonic",
        sha12="monotonic123",
        filename="test.pdf",
        engine=engine,
        threshold=50,
    )

    assert len(updated_chunks) == 2
    # Verify monotonic IDs
    assert updated_chunks[0]["chunk_id"] == "monotonic123_p1_0000"
    assert updated_chunks[1]["chunk_id"] == "monotonic123_p1_0001"

    # Verify char offsets
    assert updated_chunks[0]["char_start"] == 0
    assert updated_chunks[0]["char_end"] > 0
    assert updated_chunks[1]["char_start"] is not None
    assert updated_chunks[1]["char_end"] is not None
    assert updated_chunks[1]["char_end"] > updated_chunks[1]["char_start"]


def test_multithreaded_batch_ocr_processing():
    """Verify concurrent thread-pool batch execution preserves page ordering across multi-page documents."""
    mock_recognizer = MagicMock(
        side_effect=lambda img: (
            [[[[0, 0], [1, 0], [1, 1], [0, 1]], f"Text from {img.decode()}", 0.95]],
            0.01,
        )
    )
    mock_renderer = MagicMock(side_effect=lambda pdf, page_num: f"page_{page_num}_img".encode())
    engine = OcrEngine(recognizer=mock_recognizer, renderer=mock_renderer)

    pages = [
        Page(doc_id="doc_batch", page_num=1, status="empty", char_count=0, num_chunks=0),
        Page(doc_id="doc_batch", page_num=2, status="empty", char_count=0, num_chunks=0),
        Page(doc_id="doc_batch", page_num=3, status="empty", char_count=0, num_chunks=0),
    ]

    pdf_bytes = b"%PDF-1.4..."
    updated_pages, updated_chunks = apply_conditional_ocr(
        pdf_bytes=pdf_bytes,
        page_records=pages,
        existing_chunks=[],
        doc_id="doc_batch",
        sha12="batch1234567",
        filename="batch.pdf",
        engine=engine,
        threshold=50,
    )

    assert len(updated_pages) == 3
    assert [p.page_num for p in updated_pages] == [1, 2, 3]
    assert all(p.status == "ok" for p in updated_pages)
    assert len(updated_chunks) == 3
    assert [c["page"] for c in updated_chunks] == [1, 2, 3]
    assert "Text from page_1_img" in updated_chunks[0]["content"]
    assert "Text from page_2_img" in updated_chunks[1]["content"]
    assert "Text from page_3_img" in updated_chunks[2]["content"]


def test_rapidocr_output_dataclass_handling():
    """Verify ocr_page_image correctly extracts text/scores from modern RapidOCROutput dataclasses."""
    from dataclasses import dataclass

    @dataclass
    class FakeRapidOCROutput:
        boxes: list | None
        txts: tuple[str, ...] | None
        scores: tuple[float, ...] | None

    output = FakeRapidOCROutput(
        boxes=None,
        txts=("Heading line 1", "Body text line 2"),
        scores=(0.98, 0.94),
    )
    mock_recognizer = MagicMock(return_value=output)
    engine = OcrEngine(recognizer=mock_recognizer)

    text, avg_score = engine.ocr_page_image(b"fake_image_bytes")
    assert text == "Heading line 1\nBody text line 2"
    assert round(avg_score, 2) == 0.96


def test_rapidocr_output_dataclass_empty_handling():
    """Verify ocr_page_image handles empty RapidOCROutput (None txts/scores) gracefully."""
    from dataclasses import dataclass

    @dataclass
    class FakeRapidOCROutput:
        boxes: list | None = None
        txts: tuple[str, ...] | None = None
        scores: tuple[float, ...] | None = None

    mock_recognizer = MagicMock(return_value=FakeRapidOCROutput())
    engine = OcrEngine(recognizer=mock_recognizer)

    text, avg_score = engine.ocr_page_image(b"fake_image_bytes")
    assert text == ""
    assert avg_score == 0.0


def test_rapidocr_non_iterable_unrecognized_output_does_not_crash():
    """Verify unexpected non-iterable object does not raise TypeError."""
    mock_recognizer = MagicMock(return_value=object())
    engine = OcrEngine(recognizer=mock_recognizer)

    text, avg_score = engine.ocr_page_image(b"fake_image_bytes")
    assert text == ""
    assert avg_score == 0.0
