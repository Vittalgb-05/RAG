# ------------------------------------------------------------------
# Unit Tests for PdfReader
# Verifies text extraction, chunking overlap, BytesIO streams,
# error handling on corrupt input, and diverse corpus coverage
# ------------------------------------------------------------------

import io
from pathlib import Path
import pytest
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate
from pdf_reader import PdfReader


CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"


def test_pdf_reader_extract_text_digital():
    """Verify digital PDF extraction against 20-page clean corpus document."""
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    assert pdf_path.exists(), "Corpus file clean_digital.pdf must exist"

    reader = PdfReader(str(pdf_path))
    assert len(reader.reader.pages) == 20

    text = reader.extract_text()
    assert len(text) > 500
    assert "Section 1: Fundamentals of Intelligence Systems" in text
    assert "Section 20: Fundamentals of Intelligence Systems" in text


def test_pdf_reader_chunking_overlap():
    """
    Verify chunk generation, metadata fields, and chunk overlap preservation (WR-03).
    When text on a page exceeds chunk_size (1000 chars), consecutive chunks must share text.
    """
    # 1. Verify clean_digital.pdf chunk structure
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    reader = PdfReader(str(pdf_path))
    chunks = reader.get_paragraphs()

    assert len(chunks) >= 20, "Should generate at least one chunk per page"

    for chunk in chunks:
        assert "content" in chunk
        assert "filename" in chunk
        assert "page" in chunk
        assert "chunk_id" in chunk
        assert len(chunk["content"]) <= 1000, "Chunks must respect max size"
        assert 1 <= chunk["page"] <= 20

    # 2. Verify consecutive-chunk overlap on a single-page multi-chunk document
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf)
    styles = getSampleStyleSheet()
    long_text = " ".join([f"OverlapToken_{i}" for i in range(250)])
    doc.build([Paragraph(long_text, styles["Normal"])])
    buf.seek(0)

    multi_chunk_reader = PdfReader(buf, filename="overlap_doc.pdf")
    multi_chunks = multi_chunk_reader.get_paragraphs()
    assert len(multi_chunks) >= 2, "Long page should be split into multiple chunks"

    # Verify that consecutive chunks share overlapping tokens
    c0_words = set(multi_chunks[0]["content"].split())
    c1_words = set(multi_chunks[1]["content"].split())
    shared_words = c0_words.intersection(c1_words)
    assert len(shared_words) >= 3, "Consecutive chunks on the same page must preserve text overlap"


def test_pdf_reader_bytesio_stream():
    """Verify PdfReader accepts in-memory BytesIO streams."""
    pdf_path = CORPUS_DIR / "multi_column.pdf"
    with open(pdf_path, "rb") as f:
        stream = io.BytesIO(f.read())

    reader = PdfReader(stream, filename="in_memory_multi_column.pdf")
    assert reader.filename == "in_memory_multi_column.pdf"
    text = reader.extract_text()
    assert "Multi-Column Document" in text


def test_pdf_reader_empty_or_scanned_pdf():
    """
    Verify behavior on scanned/raster PDF.
    Pure pypdf extraction without OCR produces zero extractable text chunks.
    Documents the known limitation identified in CONCERNS.md #4.
    """
    pdf_path = CORPUS_DIR / "scanned_sample.pdf"
    reader = PdfReader(str(pdf_path))
    chunks = reader.get_paragraphs()

    # Scanned PDF with no text layer yields no chunks
    assert chunks == [], "Scanned PDF without text layer yields 0 chunks in baseline pypdf reader"


def test_pdf_reader_corrupt_pdf_rejects():
    """
    Verify that attempting to process a corrupt/invalid PDF raises an exception (WR-07, Risk 3).
    Ensures fail-fast behavior when reading malformed inputs.
    """
    pdf_path = CORPUS_DIR / "corrupt_invalid.pdf"
    assert pdf_path.exists(), "Corpus file corrupt_invalid.pdf must exist"

    with pytest.raises(Exception):
        reader = PdfReader(str(pdf_path))
        reader.extract_text()


def test_pdf_reader_dense_table():
    """
    Verify extraction on dense table corpus document (WR-07).
    Ensures table headers and numerical cell data are preserved in extracted text.
    """
    pdf_path = CORPUS_DIR / "dense_table.pdf"
    assert pdf_path.exists(), "Corpus file dense_table.pdf must exist"

    reader = PdfReader(str(pdf_path))
    text = reader.extract_text()
    assert "Quarterly Financial & Operational Metrics" in text
    assert "124.5" in text
    assert "68.2%" in text
    assert "630.9" in text


def test_pdf_reader_chart_diagram():
    """
    Verify extraction on chart/diagram corpus document (WR-07).
    Ensures text captions and workflow annotations are captured.
    """
    pdf_path = CORPUS_DIR / "chart_diagram.pdf"
    assert pdf_path.exists(), "Corpus file chart_diagram.pdf must exist"

    reader = PdfReader(str(pdf_path))
    text = reader.extract_text()
    assert "System Workflow Diagram" in text
    assert "Hybrid Search" in text
    assert "Local VLM" in text
