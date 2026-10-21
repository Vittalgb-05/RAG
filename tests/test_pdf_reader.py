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
from ingestion.pdf_reader import PdfReader


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


def test_page_failure_isolated(monkeypatch):
    """
    Verify that an extraction failure on page 2 does not abort remaining 19 pages (INGEST-05).
    Verifies that get_page_records() tracks the failed page with error message.
    """
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    reader = PdfReader(str(pdf_path))

    # Monkeypatch page index 1 (page 2) to raise an error
    def mock_broken_extract():
        raise RuntimeError("Corrupted font streams on page 2")

    monkeypatch.setattr(reader.reader.pages[1], "extract_text", mock_broken_extract)

    chunks = reader.get_paragraphs()
    records = reader.get_page_records()

    # Total 20 pages: 19 succeeded, 1 failed
    assert len(records) == 20
    assert records[1].page_num == 2
    assert records[1].status == "failed"
    assert "Corrupted font streams" in (records[1].error or "")

    # Pages 1 and 3 are ok
    assert records[0].status == "ok"
    assert records[2].status == "ok"

    # Chunks from other pages still processed
    assert len(chunks) >= 19
    chunk_pages = {c["page"] for c in chunks}
    assert 2 not in chunk_pages
    assert 1 in chunk_pages
    assert 3 in chunk_pages


def test_hash_chunk_ids_stable_across_rename():
    """
    Verify chunk_id stability across renames when sha12 prefix is provided (INGEST-02).
    Without sha12, preserves legacy filename-based prefix.
    """
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    reader_a = PdfReader(str(pdf_path), filename="doc_alpha.pdf")
    reader_b = PdfReader(str(pdf_path), filename="doc_beta_renamed.pdf")

    # With sha12: chunk IDs are identical
    sha12 = "123456abcdef"
    reader_a.extract_text(doc_id="doc_1", sha12=sha12)
    reader_b.extract_text(doc_id="doc_1", sha12=sha12)

    chunks_a = reader_a.get_paragraphs()
    chunks_b = reader_b.get_paragraphs()

    ids_a = [c["chunk_id"] for c in chunks_a]
    ids_b = [c["chunk_id"] for c in chunks_b]
    assert ids_a == ids_b
    assert ids_a[0].startswith("123456abcdef_p1_")

    # Without sha12: legacy filename prefix is preserved
    reader_legacy = PdfReader(str(pdf_path), filename="legacy.pdf")
    reader_legacy.extract_text()
    legacy_chunks = reader_legacy.get_paragraphs()
    assert legacy_chunks[0]["chunk_id"].startswith("legacy.pdf_p1_")
