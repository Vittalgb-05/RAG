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

    # 4. Content hashing
    sha = sha256_bytes(raw)
    doc_id = doc_id_for(sha)

    print(f"[UploadValidation] Validated {filename} ({doc_id}, {num_pages} pages, {size_bytes} bytes)")
    return ValidatedUpload(
        doc_id=doc_id,
        filename=filename,
        sha256=sha,
        size_bytes=size_bytes,
        num_pages=num_pages,
    )
