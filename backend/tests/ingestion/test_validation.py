"""
Unit tests for app.ingestion.validation.validate_pdf_bytes.

Tests are written against the plan, not the implementation, to catch
wrong assumptions rather than just confirm what the code already does.

Each test targets exactly one rejection path or one boundary condition.
The size-boundary tests patch MAX_FILE_SIZE_BYTES to a small value so
no test ever allocates 100 MB of memory.
"""

from unittest.mock import patch

import pymupdf
import pytest

from app.ingestion.validation import (
    MAX_FILE_SIZE_BYTES,
    PDF_MAGIC,
    validate_pdf_bytes,
)

# ── Shared fixtures ───────────────────────────────────────────────────────────

# A syntactically corrupt stream that starts with %PDF so it passes the magic
# check but fails the PyMuPDF structural parse.
CORRUPT_PDF: bytes = b"%PDF-1.4\n%%This is deliberately not a valid PDF object"

# A non-PDF stream (PNG magic bytes) used for magic-byte rejection tests.
NON_PDF: bytes = b"\x89PNG\r\n\x1a\nThis is a PNG file"


def make_minimal_pdf() -> bytes:
    """Create a real, valid, minimal PDF using pymupdf. One blank page."""
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def make_encrypted_pdf() -> bytes:
    """Create a real AES-256 encrypted PDF. Requires a password to read."""
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes(  # type: ignore[no-any-return]
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="ownerpass",
    )


# ── Check 1: Zero-byte ────────────────────────────────────────────────────────


def test_zero_byte_file_is_rejected() -> None:
    result = validate_pdf_bytes("empty.pdf", b"")
    assert not result.accepted
    assert result.filename == "empty.pdf"
    assert result.error_message is not None
    assert "empty" in result.error_message


# ── Check 2: Size ceiling ─────────────────────────────────────────────────────

# The limit is patched to 100 bytes so tests avoid allocating 100 MB.
_SMALL_LIMIT = 100


def test_file_one_byte_over_limit_is_rejected() -> None:
    # 101 bytes: non-%PDF content so it can't accidentally pass further checks
    oversized = b"x" * (_SMALL_LIMIT + 1)
    with patch("app.ingestion.validation.MAX_FILE_SIZE_BYTES", _SMALL_LIMIT):
        result = validate_pdf_bytes("big.pdf", oversized)
    assert not result.accepted
    assert result.error_message is not None
    assert "exceeds" in result.error_message


def test_file_exactly_at_limit_passes_size_check() -> None:
    """Content at exactly the limit passes the size check.
    It then fails at the magic-bytes check (content is not %PDF),
    proving the boundary is inclusive (<=, not <)."""
    at_limit = b"x" * _SMALL_LIMIT
    with patch("app.ingestion.validation.MAX_FILE_SIZE_BYTES", _SMALL_LIMIT):
        result = validate_pdf_bytes("at_limit.pdf", at_limit)
    # Fails at magic bytes, NOT size — proving size check passed.
    assert result.error_message is not None
    assert "only PDF is accepted" in result.error_message


def test_rejection_message_states_actual_size_and_limit() -> None:
    oversized = b"x" * (_SMALL_LIMIT + 50)
    with patch("app.ingestion.validation.MAX_FILE_SIZE_BYTES", _SMALL_LIMIT):
        result = validate_pdf_bytes("huge.pdf", oversized)
    assert result.error_message is not None
    # Message must describe the situation (spec AC-3 requires actual size + limit).
    # We check for structural keywords rather than exact byte values so the
    # test is independent of the mocked limit's MB representation.
    assert "exceeds" in result.error_message
    assert "MB" in result.error_message


def test_rejection_message_states_actual_size_with_small_mock_limit() -> None:
    """With a mocked 1 KB limit, the error message reflects that limit."""
    limit = 1024
    oversized = b"x" * (limit + 1)
    with patch("app.ingestion.validation.MAX_FILE_SIZE_BYTES", limit):
        result = validate_pdf_bytes("big.pdf", oversized)
    assert result.error_message is not None
    assert "exceeds" in result.error_message


# ── Check 3: Magic bytes ──────────────────────────────────────────────────────


def test_non_pdf_magic_bytes_rejected() -> None:
    result = validate_pdf_bytes("image.png", NON_PDF)
    assert not result.accepted
    assert result.error_message is not None
    assert "only PDF is accepted" in result.error_message


def test_plain_text_file_rejected_by_magic() -> None:
    result = validate_pdf_bytes("notes.txt", b"This is plain text, not a PDF.")
    assert not result.accepted
    assert result.error_message is not None
    assert "only PDF is accepted" in result.error_message


def test_empty_prefix_not_confused_with_pdf() -> None:
    """A file whose first 4 bytes are spaces (not %PDF) is rejected."""
    result = validate_pdf_bytes("spaces.pdf", b"    " + b"rest of content")
    assert not result.accepted
    assert result.error_message is not None
    assert "only PDF is accepted" in result.error_message


# ── Check 4: Structural parse (corrupt / truncated) ───────────────────────────


def test_corrupt_pdf_stream_rejected() -> None:
    """Starts with %PDF but fails pymupdf structural parse."""
    result = validate_pdf_bytes("corrupt.pdf", CORRUPT_PDF)
    assert not result.accepted
    assert result.error_message is not None
    assert "corrupted or truncated" in result.error_message


def test_truncated_pdf_rejected() -> None:
    """A valid PDF header with the body cut off mid-stream."""
    truncated = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog"  # no endobj, no xref
    result = validate_pdf_bytes("truncated.pdf", truncated)
    assert not result.accepted
    assert result.error_message is not None
    assert "corrupted or truncated" in result.error_message


# ── Check 5: Password protection ─────────────────────────────────────────────


def test_password_protected_pdf_rejected() -> None:
    """A real AES-256 encrypted PDF is rejected with the specific message."""
    encrypted = make_encrypted_pdf()
    result = validate_pdf_bytes("protected.pdf", encrypted)
    assert not result.accepted
    assert result.filename == "protected.pdf"
    assert result.error_message is not None
    # Exact message wording is spec-mandated (spec EC-3)
    assert "encrypted" in result.error_message
    assert "password" in result.error_message


# ── Happy path ────────────────────────────────────────────────────────────────


def test_valid_minimal_pdf_accepted() -> None:
    content = make_minimal_pdf()
    result = validate_pdf_bytes("annual_report.pdf", content)
    assert result.accepted
    assert result.filename == "annual_report.pdf"
    assert result.error_message is None


def test_accepted_result_has_no_error_message() -> None:
    """error_message must be None (not empty string) on acceptance."""
    content = make_minimal_pdf()
    result = validate_pdf_bytes("report.pdf", content)
    assert result.error_message is None


# ── Filename attribution ──────────────────────────────────────────────────────


def test_filename_preserved_in_rejection() -> None:
    """The returned filename must match what was passed in."""
    result = validate_pdf_bytes("résumé.pdf", b"")
    assert result.filename == "résumé.pdf"


def test_filename_preserved_in_acceptance() -> None:
    content = make_minimal_pdf()
    result = validate_pdf_bytes("Annual Report FY2024.pdf", content)
    assert result.filename == "Annual Report FY2024.pdf"
