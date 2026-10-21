"""Offline unit tests for DoclingReader and structured document parsing."""

import io
from pathlib import Path
from unittest.mock import MagicMock


from ingestion.docling_reader import DoclingReader


CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"
CLEAN_PDF = CORPUS_DIR / "clean_digital.pdf"
DENSE_TABLE_PDF = CORPUS_DIR / "dense_table.pdf"


def test_docling_reader_fallback_when_docling_missing():
    """Verify DoclingReader delegates transparently to PdfReader when docling is absent."""
    reader = DoclingReader(CLEAN_PDF)
    reader._has_docling = False

    text = reader.extract_text(doc_id="doc_test_fallback", sha12="test12345678")
    assert len(text) > 0
    assert "Fundamentals of Intelligence Systems" in text

    chunks = reader.get_paragraphs()
    assert len(chunks) > 0
    assert chunks[0]["doc_id"] == "doc_test_fallback"
    # Fallback to PdfReader produces chunks
    assert chunks[0]["chunk_id"].startswith("test12345678_p1_")

    records = reader.get_page_records()
    assert len(records) > 0
    assert records[0].status == "ok"


def test_docling_reader_with_mock_converter():
    """Verify DoclingReader correctly processes structured text & markdown tables using docling."""
    mock_converter = MagicMock()

    class MockProv:
        def __init__(self, page_no):
            self.page_no = page_no

    class MockTable:
        def __init__(self, md, page_no=1):
            self._md = md
            self.prov = [MockProv(page_no)]

        def export_to_markdown(self):
            return self._md

    class MockItem:
        def __init__(self, text, label="text", page_no=1):
            self.text = text
            self.label = label
            self.prov = [MockProv(page_no)]

    class MockDoc:
        def __init__(self):
            self.pages = [1, 2]
            self.tables = [
                MockTable(
                    "| Col A | Col B |\n|---|---|\n| Val 1 | Val 2 |",
                    page_no=1,
                )
            ]

        def iterate_items(self):
            return [
                (MockItem("Executive Summary", label="section_header", page_no=1), 1),
                (MockItem("This is the main body paragraph describing findings.", label="text", page_no=1), 2),
                (MockItem("Page two notes and addendum.", label="text", page_no=2), 1),
            ]

    class MockConvRes:
        def __init__(self):
            self.document = MockDoc()

    mock_converter.convert.return_value = MockConvRes()

    reader = DoclingReader(
        DENSE_TABLE_PDF,
        converter=mock_converter,
    )
    reader._has_docling = True

    text = reader.extract_text(doc_id="doc_mock_docling", sha12="abcdef123456")
    assert "Executive Summary" in text
    assert "| Col A | Col B |" in text

    chunks = reader.get_paragraphs()
    assert len(chunks) >= 3

    # Table chunk check
    table_chunks = [c for c in chunks if "| Col A |" in c["content"]]
    assert len(table_chunks) == 1
    table_c = table_chunks[0]
    assert table_c["extraction"] == "docling"
    assert table_c["doc_id"] == "doc_mock_docling"
    assert table_c["page"] == 1
    assert table_c["chunk_id"].startswith("abcdef123456_p1_")

    # Page records check
    page_records = reader.get_page_records()
    assert len(page_records) == 2
    assert page_records[0].page_num == 1
    assert page_records[0].status == "ok"
    assert page_records[0].num_chunks >= 2
    assert page_records[1].page_num == 2


def test_docling_reader_fault_isolation_fallback():
    """Verify unexpected converter exceptions fall back seamlessly to PdfReader."""
    mock_converter = MagicMock()
    mock_converter.convert.side_effect = RuntimeError("Docling native engine crashed")

    reader = DoclingReader(CLEAN_PDF, converter=mock_converter)
    reader._has_docling = True

    # Should not raise; should catch and invoke PdfReader fallback
    text = reader.extract_text(doc_id="doc_crash_fallback", sha12="crash1234567")
    assert len(text) > 0
    assert "Fundamentals of Intelligence Systems" in text

    chunks = reader.get_paragraphs()
    assert len(chunks) > 0
    assert chunks[0]["doc_id"] == "doc_crash_fallback"


def test_docling_reader_empty_conversion_fallback():
    """Verify empty document items trigger fallback to PdfReader."""
    mock_converter = MagicMock()

    class EmptyDoc:
        def __init__(self):
            self.pages = []
            self.tables = []

        def iterate_items(self):
            return []

    class EmptyConvRes:
        def __init__(self):
            self.document = EmptyDoc()

    mock_converter.convert.return_value = EmptyConvRes()

    reader = DoclingReader(CLEAN_PDF, converter=mock_converter)
    reader._has_docling = True

    text = reader.extract_text(doc_id="doc_empty_fallback", sha12="empty1234567")
    assert len(text) > 0
    assert "Fundamentals of Intelligence Systems" in text


def test_docling_reader_input_types():
    """Verify DoclingReader accepts bytes, BytesIO, and file path inputs."""
    raw_bytes = CLEAN_PDF.read_bytes()

    # Bytes input
    r1 = DoclingReader(raw_bytes, filename="clean_digital.pdf")
    assert r1.filename == "clean_digital.pdf"
    assert len(r1._raw_bytes) == len(raw_bytes)

    # BytesIO input
    r2 = DoclingReader(io.BytesIO(raw_bytes), filename="clean_digital.pdf")
    assert r2.filename == "clean_digital.pdf"
    assert len(r2._raw_bytes) == len(raw_bytes)


def test_docling_reader_sequential_reading_order():
    """Verify tables embedded within text maintain sequential reading order (CR-03)."""
    mock_converter = MagicMock()

    class MockProv:
        def __init__(self, page_no):
            self.page_no = page_no

    class MockItem:
        def __init__(self, text, label="text", md=None):
            self.text = text
            self.label = label
            self._md = md
            self.prov = [MockProv(1)]

        def export_to_markdown(self):
            if self._md:
                return self._md
            raise AttributeError("Not a table")

    class MockDoc:
        def __init__(self):
            self.pages = [1]
            self.tables = []

        def iterate_items(self):
            return [
                (MockItem("Section Header 1: Introduction", label="section_header"), 1),
                (
                    MockItem(
                        "| Header A | Header B |\n|---|---|\n| 10 | 20 |",
                        label="table",
                        md="| Header A | Header B |\n|---|---|\n| 10 | 20 |",
                    ),
                    2,
                ),
                (MockItem("Concluding remarks following the table.", label="text"), 1),
            ]

    class MockConvRes:
        def __init__(self):
            self.document = MockDoc()

    mock_converter.convert.return_value = MockConvRes()

    reader = DoclingReader(DENSE_TABLE_PDF, converter=mock_converter)
    reader._has_docling = True

    reader.extract_text(doc_id="doc_order_test", sha12="order1234567")
    chunks = reader.get_paragraphs()

    assert len(chunks) == 3
    # First chunk is Introduction header
    assert "Section Header 1: Introduction" in chunks[0]["content"]
    # Second chunk is Table
    assert "| Header A | Header B |" in chunks[1]["content"]
    # Third chunk is Concluding remarks
    assert "Concluding remarks following the table" in chunks[2]["content"]


def test_docling_reader_chunk_char_offsets():
    """Verify chunks have populated, valid character offset ranges (IN-02)."""
    mock_converter = MagicMock()

    class MockProv:
        def __init__(self, page_no):
            self.page_no = page_no

    class MockItem:
        def __init__(self, text):
            self.text = text
            self.label = "text"
            self.prov = [MockProv(1)]

    class MockDoc:
        def __init__(self):
            self.pages = [1]
            self.tables = []

        def iterate_items(self):
            return [
                (MockItem("First paragraph for offset check."), 1),
                (MockItem("Second paragraph for offset check."), 1),
            ]

    class MockConvRes:
        def __init__(self):
            self.document = MockDoc()

    mock_converter.convert.return_value = MockConvRes()

    reader = DoclingReader(DENSE_TABLE_PDF, converter=mock_converter)
    reader._has_docling = True

    full_text = reader.extract_text(doc_id="doc_offsets_test", sha12="offsets12345")
    chunks = reader.get_paragraphs()

    assert len(chunks) >= 1
    for c in chunks:
        assert c["char_start"] is not None
        assert c["char_end"] is not None
        assert c["char_end"] > c["char_start"]
        # Slice of full text matches chunk content
        assert full_text[c["char_start"] : c["char_end"]] == c["content"]


def test_export_table_markdown_with_doc_parameter():
    """Verify _export_table_markdown forwards doc when supported and falls back when not."""

    class ModernTable:
        def export_to_markdown(self, doc=None):
            return f"| Header |\n| Value ({getattr(doc, 'name', 'none')}) |"

    class LegacyTable:
        def export_to_markdown(self):
            return "| Header |\n| Value (legacy) |"

    class FakeDoc:
        name = "test_doc"

    doc = FakeDoc()
    modern_out = DoclingReader._export_table_markdown(ModernTable(), doc=doc)
    assert "Value (test_doc)" in modern_out

    legacy_out = DoclingReader._export_table_markdown(LegacyTable(), doc=doc)
    assert "Value (legacy)" in legacy_out
