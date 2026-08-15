"""
Excel Export Package (Feature 4).

Deterministic generation of formatted .xlsx financial workbooks with real Excel formulas and W3C provenance.
"""

from app.excel_export.generator import generate_workbook
from app.excel_export.models import (
    CellReference,
    ProvenanceQueryResponse,
    W3CAnnotationRecord,
    WorkbookGenerationResult,
)
from app.excel_export.provenance import (
    build_w3c_annotation_for_node,
    format_cell_comment,
    format_cell_hyperlink_url,
)
from app.excel_export.repository import ModelRepository
from app.excel_export.router import (
    get_model_repository,
    set_model_repository,
)
from app.excel_export.router import (
    router as excel_export_router,
)

__all__ = [
    "CellReference",
    "ModelRepository",
    "ProvenanceQueryResponse",
    "W3CAnnotationRecord",
    "WorkbookGenerationResult",
    "build_w3c_annotation_for_node",
    "excel_export_router",
    "format_cell_comment",
    "format_cell_hyperlink_url",
    "generate_workbook",
    "get_model_repository",
    "set_model_repository",
]
