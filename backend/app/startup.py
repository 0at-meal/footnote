"""
Startup checks (D1): the server refuses to start without Docling unless degraded mode is enabled.
"""

from dataclasses import dataclass

from app.config import pymupdf_fallback_allowed
from app.extraction import docling_parser


@dataclass(frozen=True)
class ParserStatus:
    docling_available: bool
    parser_mode: str
    """'docling' or 'pymupdf_fallback' (degraded)."""
    degraded_reason: str | None


class ParserDependencyError(RuntimeError):
    """Raised at startup when Docling is missing and degraded mode is not enabled."""


def parser_status() -> ParserStatus:
    import_error = docling_parser.DOCLING_IMPORT_ERROR
    if import_error is None:
        return ParserStatus(docling_available=True, parser_mode="docling", degraded_reason=None)
    return ParserStatus(
        docling_available=False,
        parser_mode="pymupdf_fallback",
        degraded_reason=(
            f"Docling is not installed in this Python interpreter ({import_error}). "
            "PDF extraction uses the PyMuPDF fallback: labels lose column headers and "
            "many more items are flagged for review."
        ),
    )


def check_parser_dependencies() -> ParserStatus:
    status = parser_status()
    if not status.docling_available and not pymupdf_fallback_allowed():
        raise ParserDependencyError(
            "Refusing to start: Docling is not importable "
            f"({docling_parser.DOCLING_IMPORT_ERROR}). This usually means the server was "
            "started with a Python interpreter other than the project virtualenv. "
            "Start it with `python tools/run_backend.py` (uses .venv), or set "
            "ALLOW_PYMUPDF_FALLBACK=1 to run in degraded PyMuPDF mode."
        )
    return status
