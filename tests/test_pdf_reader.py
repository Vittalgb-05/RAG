# ------------------------------------------------------------------
# Unit Tests for PdfReader
# Verifies text extraction, chunking, BytesIO streams, and scanned PDF limits
# ------------------------------------------------------------------

import io
from pathlib import Path
import pytest
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
    """Verify chunk generation and metadata fields."""
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
