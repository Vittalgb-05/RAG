"""
Server-side PDF upload validation and streaming SHA-256 content hashing.

Enforces %PDF magic-byte validation, maximum file size caps, page count thresholds,
and produces deterministic doc_id identifiers based on document content hash.
"""

from dataclasses import dataclass
import hashlib
import io
import re
import pypdf

# Locked configuration constants (RESEARCH-locked ASSUMED caps)
MAX_FILE_MB: int = 50
MAX_PAGES: int = 500

# Cheap pre-flight estimate: sample a handful of pages only.  This is advisory
# (never rejects an upload) and deliberately does not trigger Docling/OCR.
PREFLIGHT_SAMPLE_PAGES: int = 5
PREFLIGHT_LOW_TEXT_CHARS: int = 50


def estimate_scanned_ratio(reader: "pypdf.PdfReader", sample_limit: int = PREFLIGHT_SAMPLE_PAGES) -> float:
    """Estimate the fraction of sampled pages that are likely scanned.

    Uses ``pypdf`` text extraction only (no rasterization, OCR, or model loads),
    so it is safe to run as a pre-flight diagnostic before ingestion.

    Args:
        reader: Already-open pypdf reader.
        sample_limit: Maximum number of pages to sample.

    Returns:
        Ratio in ``[0.0, 1.0]``, or 0.0 when no page could be sampled.
    """
    try:
        page_count = len(reader.pages)
    except Exception:
        return 0.0

    sampled = min(max(0, int(sample_limit)), page_count)
    if sampled <= 0:
        return 0.0

    low_text_pages = 0
    for index in range(sampled):
        try:
            text = reader.pages[index].extract_text() or ""
        except Exception:
            text = ""
        if len(text.strip()) < PREFLIGHT_LOW_TEXT_CHARS:
            low_text_pages += 1

    return low_text_pages / sampled


def _preflight_note(ratio: float) -> str:
    """Build a human-readable pre-flight diagnostic for the scanned-page ratio."""
    if ratio <= 0.0:
        return "Preflight: sampled pages contain digital text."
    if ratio >= 0.8:
        return (
            f"Preflight: ~{ratio:.0%} of sampled pages appear scanned; OCR fallback will run "
            "and is bounded by per-document page/time budgets."
        )
    return f"Preflight: ~{ratio:.0%} of sampled pages may require OCR fallback."


def sha256_bytes(raw: bytes) -> str:
    """
    Compute SHA-256 hex digest using 1 MiB slices to maintain flat memory usage.

    Args:
        raw: Full binary file content.

    Returns:
        str: 64-character lowercase hexadecimal digest.
    """
    hasher = hashlib.sha256()
    slice_size = 1024 * 1024
    for offset in range(0, len(raw), slice_size):
        hasher.update(raw[offset : offset + slice_size])
    return hasher.hexdigest()


def doc_id_for(sha: str) -> str:
    """
    Generate stable document identifier from SHA-256 digest.

    Args:
        sha: 64-character SHA-256 digest.

    Returns:
        str: Stable identifier in 'doc_<sha16>' format.
    """
    if not isinstance(sha, str) or not re.match(r"^[0-9a-f]{64}$", sha):
        raise ValueError(f"Invalid sha256 digest: {sha!r}")
    return f"doc_{sha[:16]}"


@dataclass(frozen=True)
class ValidatedUpload:
    """
    Validated PDF upload metadata.
    """

    doc_id: str
    filename: str
    sha256: str
    size_bytes: int
    num_pages: int
    estimated_scanned_ratio: float = 0.0
    preflight_note: str = ""


def validate_pdf_bytes(raw: bytes, filename: str) -> ValidatedUpload:
    """
    Validate raw uploaded bytes for %PDF magic header, size limits, and page count.

    Args:
        raw: Raw bytes of the uploaded file.
        filename: Original file name.

    Returns:
        ValidatedUpload: Validated upload metadata with stable doc_id.

    Raises:
        ValueError: If validation fails with user-actionable error explanation.
    """
    # 1. Magic bytes check
    if not raw.startswith(b"%PDF-"):
        raise ValueError(f"Not a valid PDF: missing %PDF header — {filename}.")

    # 2. Size limit check
    size_bytes = len(raw)
    max_bytes = MAX_FILE_MB * 1024 * 1024
    if size_bytes > max_bytes:
        mb = size_bytes / (1024 * 1024)
        raise ValueError(f"File too large ({mb:.1f} MB > {MAX_FILE_MB} MB) — {filename}.")

    # 3. Page count & structural readability probe
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        num_pages = len(reader.pages)
    except Exception as err:
        raise ValueError(f"Unreadable PDF ({err}) — {filename}.") from err

    if num_pages < 1:
        raise ValueError(f"PDF contains no pages — {filename}.")

    if num_pages > MAX_PAGES:
        raise ValueError(f"Too many pages ({num_pages} > {MAX_PAGES}) — {filename}.")

    # 4. Cheap scanned-page pre-flight (advisory only; never rejects the upload).
    scanned_ratio = estimate_scanned_ratio(reader)
    preflight_note = _preflight_note(scanned_ratio)

    # 5. Content hashing
    sha = sha256_bytes(raw)
    doc_id = doc_id_for(sha)

    print(f"[UploadValidation] Validated {filename} ({doc_id}, {num_pages} pages, {size_bytes} bytes)")
    print(f"[UploadValidation] {preflight_note}")
    return ValidatedUpload(
        doc_id=doc_id,
        filename=filename,
        sha256=sha,
        size_bytes=size_bytes,
        num_pages=num_pages,
        estimated_scanned_ratio=scanned_ratio,
        preflight_note=preflight_note,
    )
