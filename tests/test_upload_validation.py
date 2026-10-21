# ------------------------------------------------------------------
# Unit Tests for Upload Validation (upload_validation.py)
# Verifies %PDF header validation, size limits, page count caps,
# streaming SHA-256 calculation, and filename-independent doc_id.
# ------------------------------------------------------------------

import hashlib
from pathlib import Path
import pytest
from ingestion.upload_validation import MAX_FILE_MB, MAX_PAGES, doc_id_for, sha256_bytes, validate_pdf_bytes


CORPUS_DIR = Path(__file__).resolve().parent / "data" / "corpus"


def test_corrupt_invalid_rejected_WR07():
    """Verify that a corrupt or non-PDF file is rejected at magic-byte check (WR-07)."""
    corrupt_path = CORPUS_DIR / "corrupt_invalid.pdf"
    with open(corrupt_path, "rb") as f:
        raw_bytes = f.read()

    with pytest.raises(ValueError, match="Not a valid PDF: missing %PDF header"):
        validate_pdf_bytes(raw_bytes, "corrupt_invalid.pdf")


def test_valid_pdf_accepts_and_hashes():
    """Verify clean digital PDF validates successfully with correct metadata."""
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    with open(pdf_path, "rb") as f:
        raw_bytes = f.read()

    result = validate_pdf_bytes(raw_bytes, "clean_digital.pdf")
    assert result.filename == "clean_digital.pdf"
    assert len(result.sha256) == 64
    assert result.doc_id == f"doc_{result.sha256[:16]}"
    assert result.num_pages == 20
    assert result.size_bytes == len(raw_bytes)


def test_rename_yields_same_doc_id():
    """Verify that renaming a file yields identical sha256 and doc_id (INGEST-02)."""
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    with open(pdf_path, "rb") as f:
        raw_bytes = f.read()

    upload_a = validate_pdf_bytes(raw_bytes, "original_name.pdf")
    upload_b = validate_pdf_bytes(raw_bytes, "renamed_copy.pdf")

    assert upload_a.filename != upload_b.filename
    assert upload_a.sha256 == upload_b.sha256
    assert upload_a.doc_id == upload_b.doc_id


def test_oversize_rejected():
    """Verify that payloads exceeding MAX_FILE_MB are rejected before parsing."""
    oversize_bytes = b"%PDF-" + b"0" * (MAX_FILE_MB * 1024 * 1024 + 1024)
    with pytest.raises(ValueError, match="File too large"):
        validate_pdf_bytes(oversize_bytes, "too_large.pdf")


def test_over_page_rejected(monkeypatch):
    """Verify that documents exceeding MAX_PAGES are rejected."""
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    with open(pdf_path, "rb") as f:
        raw_bytes = f.read()

    class StubReader:
        def __init__(self, stream):
            self.pages = [None] * (MAX_PAGES + 1)

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", StubReader)

    with pytest.raises(ValueError, match=f"Too many pages \\({MAX_PAGES + 1} > {MAX_PAGES}\\)"):
        validate_pdf_bytes(raw_bytes, "page_heavy.pdf")


def test_sha256_streaming_stable():
    """Verify streaming sha256_bytes matches hashlib directly."""
    sample_data = b"%PDF-1.4 " + b"Arbitrary binary content " * 1000
    expected_hex = hashlib.sha256(sample_data).hexdigest()
    assert sha256_bytes(sample_data) == expected_hex
    assert doc_id_for(expected_hex) == f"doc_{expected_hex[:16]}"


def test_zero_page_pdf_rejected(monkeypatch):
    """Verify that a PDF reporting zero pages is rejected (WR-03)."""
    pdf_path = CORPUS_DIR / "clean_digital.pdf"
    with open(pdf_path, "rb") as f:
        raw_bytes = f.read()

    class ZeroPageReader:
        def __init__(self, stream):
            self.pages = []

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", ZeroPageReader)

    with pytest.raises(ValueError, match="contains no pages"):
        validate_pdf_bytes(raw_bytes, "empty_pages.pdf")


def test_doc_id_for_invalid_sha_rejected():
    """Verify doc_id_for rejects invalid or non-hex sha256 arguments (WR-05)."""
    with pytest.raises(ValueError, match="Invalid sha256"):
        doc_id_for("short_hash")

    with pytest.raises(ValueError, match="Invalid sha256"):
        doc_id_for("G" * 64)


def test_preflight_estimates_scanned_ratio(monkeypatch):
    """Pre-flight estimates a scanned ratio from cheap pypdf text extraction."""

    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class ScannedReader:
        def __init__(self, stream):
            self.pages = [FakePage("") for _ in range(3)]

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", ScannedReader)

    result = validate_pdf_bytes(b"%PDF-1.4 fake", "scan.pdf")
    assert result.estimated_scanned_ratio == 1.0
    assert "appear scanned" in result.preflight_note
    assert "OCR" in result.preflight_note


def test_preflight_reports_digital_pages(monkeypatch):
    """Pre-flight reports digital text without rejecting or OCR'ing the upload."""

    class FakePage:
        def extract_text(self) -> str:
            return "A" * 80

    class DigitalReader:
        def __init__(self, stream):
            self.pages = [FakePage() for _ in range(2)]

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", DigitalReader)

    result = validate_pdf_bytes(b"%PDF-1.4 fake", "digital.pdf")
    assert result.estimated_scanned_ratio == 0.0
    assert "digital text" in result.preflight_note


def test_preflight_failure_does_not_reject_upload(monkeypatch):
    """A page whose text extraction fails is counted as low-text, not fatal."""

    class BrokenPage:
        def extract_text(self) -> str:
            raise RuntimeError("damaged content stream")

    class BrokenReader:
        def __init__(self, stream):
            self.pages = [BrokenPage(), BrokenPage()]

    import pypdf

    monkeypatch.setattr(pypdf, "PdfReader", BrokenReader)

    result = validate_pdf_bytes(b"%PDF-1.4 fake", "broken_text.pdf")
    assert result.estimated_scanned_ratio == 1.0
    assert result.doc_id.startswith("doc_")


def test_preflight_caps_are_unchanged():
    """The 50 MB and 500 page hard caps remain in force."""
    assert MAX_FILE_MB == 50
    assert MAX_PAGES == 500
