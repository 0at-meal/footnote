"""
Server-side PDF validation for the ingestion pipeline.

Scope: byte-level checks only — size, magic bytes, structural integrity,
and password protection. This module never reads financial content from
the file; that is Feature 2 (extraction). It never creates job records;
that is Feature 1, Step 3.

No exception is swallowed here: pymupdf.FileDataError is caught and
re-surfaced as a rejected FileValidationResult, not dropped silently
(CONSTITUTION §1.9).
"""

import pymupdf

from app.ingestion.models import FileValidationResult

# Hard ceiling per file. Spec AC-3 requires a "concrete byte limit";
# 100 MB is the documented default. Change only here — tests patch this
# constant rather than duplicating the magic number.
MAX_FILE_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB

# All valid PDFs begin with this byte sequence (ISO 32000-1 §7.5.2).
PDF_MAGIC: bytes = b"%PDF"


def validate_pdf_bytes(filename: str, content: bytes) -> FileValidationResult:
    """
    Validate raw file bytes server-side before a job record is created.

    Checks are ordered fast → slow so that cheap byte comparisons gate
    the expensive pymupdf parse:

    1. Zero-byte content  — cannot hold a valid PDF (spec EC-2).
    2. Size ceiling       — must not exceed MAX_FILE_SIZE_BYTES (spec AC-3).
    3. PDF magic bytes    — first 4 bytes must be b'%PDF' (spec AC-2).
    4. Structural parse   — pymupdf.open() must succeed without error
                            (spec AC-4: catches corrupted / truncated files
                            and files that were renamed to .pdf but are not).
    5. Password check     — doc.needs_pass must be False (spec EC-3).

    A file that passes all five checks is accepted. Any failed check
    returns a descriptive, user-visible error_message. No check result
    is ever silently discarded (spec AC-9, CONSTITUTION §1.9).

    Args:
        filename: The original filename as supplied by the uploader.
                  Used only for attribution in the returned result.
        content:  Raw bytes of the uploaded file.

    Returns:
        FileValidationResult with accepted=True, or accepted=False and a
        human-readable error_message naming the specific rejection reason.
    """
    # ── 1. Zero-byte ─────────────────────────────────────────────────────
    if len(content) == 0:
        return FileValidationResult(
            filename=filename,
            accepted=False,
            error_message="file is empty — cannot contain valid PDF content",
        )

    # ── 2. Size ceiling ──────────────────────────────────────────────────
    if len(content) > MAX_FILE_SIZE_BYTES:
        actual_mb: float = len(content) / (1024 * 1024)
        limit_mb: float = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        return FileValidationResult(
            filename=filename,
            accepted=False,
            error_message=(
                f"file size {actual_mb:.1f} MB exceeds the {limit_mb:.0f} MB limit"
            ),
        )

    # ── 3. Magic bytes ───────────────────────────────────────────────────
    if content[:4] != PDF_MAGIC:
        return FileValidationResult(
            filename=filename,
            accepted=False,
            error_message="unsupported file type — only PDF is accepted",
        )

    # ── 4 & 5. Structural parse + password check ─────────────────────────
    # pymupdf.FileDataError covers: corrupted body, truncated uploads,
    # and renamed non-PDFs that share the %PDF header with a real PDF
    # (extremely rare; caught defensively).
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                return FileValidationResult(
                    filename=filename,
                    accepted=False,
                    error_message="file is encrypted / password-protected",
                )
    except pymupdf.FileDataError:
        return FileValidationResult(
            filename=filename,
            accepted=False,
            error_message=(
                "file cannot be parsed as a valid PDF"
                " — it may be corrupted or truncated"
            ),
        )

    return FileValidationResult(filename=filename, accepted=True)
