"""
Data models for the layout-aware extraction pipeline (Feature 2).

Scope (Step 1):
    DoclingBbox  ← Docling-native bounding box coordinates (points).
    DoclingItem  ← Intermediate representation of a parsed table cell/value.

Note:
    ExtractedRecord (the frozen 5-field schema per spec.md) will be introduced in Step 3.
"""

from pydantic import BaseModel


class DoclingBbox(BaseModel):
    """
    Docling-native bounding box coordinates (in PDF points, page-relative).

    Coordinates are relative to the top-left or bottom-left depending on Docling's
    coordinate space prior to PyMuPDF 0-1000 normalization (Feature 2 Step 2).
    """

    x0: float
    y0: float
    x1: float
    y1: float


class DoclingItem(BaseModel):
    """
    Raw output of the Docling structural parse for a single value / table cell.

    This is an intermediate representation produced by Step 1 before coordinate
    normalization (Step 2) and record assembly (Step 3).
    """

    value: str
    """Literal text string of the cell contents (unmodified, EC-5 parentheses preserved)."""

    label: str
    """Hierarchical structural label path (e.g. 'Operating Expenses / Stock-based compensation')."""

    page: int
    """1-indexed page number where the item appears in the source PDF."""

    bbox: DoclingBbox
    """Docling-native bounding box prior to PyMuPDF normalization."""

    source_file: str
    """Original filename string as uploaded (UTF-8, stored as-is — EC-8 contract)."""


class NormalizedBbox(BaseModel):
    """
    W3C Web Annotation-style bounding box, normalized to 0-1000 coordinate space.

    Coordinates are clamped to [0.0, 1000.0] and rounded to 2 decimal places.
    """

    x0: float
    y0: float
    x1: float
    y1: float


class NormalizedItem(BaseModel):
    """
    Intermediate representation of an extracted item after PyMuPDF coordinate normalization (Step 2).
    """

    value: str
    label: str
    page: int
    bbox: NormalizedBbox
    source_file: str


class ExtractedRecord(BaseModel):
    """
    Canonical 5-field frozen schema for an extracted line item (spec.md FR2, AC-3).

    Field names (value, label, page, bbox, source_file) are frozen for the project lifetime
    (CONSTITUTION §2.3, NFR7).
    """

    value: str
    """Raw text string as extracted from the document (unmodified)."""

    label: str
    """Raw structural label path from document structure."""

    page: int
    """1-indexed page number in the source PDF."""

    bbox: dict[str, float]
    """W3C Web Annotation-style bounding box in 0-1000 space: {x0, y0, x1, y1}."""

    source_file: str
    """Original filename string as uploaded (UTF-8, unmodified)."""
