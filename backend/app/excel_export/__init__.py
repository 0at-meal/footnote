"""
Excel Export Package (Feature 4).

Deterministic generation of formatted .xlsx financial workbooks with real Excel formulas.
"""

from app.excel_export.generator import generate_workbook
from app.excel_export.models import CellReference, WorkbookGenerationResult

__all__ = [
    "CellReference",
    "WorkbookGenerationResult",
    "generate_workbook",
]
