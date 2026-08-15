"""
Data models for the Excel export stage (Feature 4).

Enforces CONSTITUTION §1.1, §1.3, §1.5, §2.3, §2.5:
- Fully typed Pydantic models for workbook metadata, cell mapping, and W3C Web Annotations.
- W3C Web Annotation standard schema with 0-1000 normalized bounding box coordinates.
"""

from typing import Literal

from pydantic import BaseModel, Field


class BoundingBoxCoordinates(BaseModel):
    """Normalized bounding box coordinates in 0-1000 coordinate space (plan §6.1 item 7)."""

    x0: float = Field(..., ge=0.0, le=1000.0)
    y0: float = Field(..., ge=0.0, le=1000.0)
    x1: float = Field(..., ge=0.0, le=1000.0)
    y1: float = Field(..., ge=0.0, le=1000.0)


class W3CRefinedBy(BaseModel):
    """Refined bounding box descriptor conforming to 0-1000 normalized space."""

    type: Literal["BoundingBox"] = "BoundingBox"
    coordinates: BoundingBoxCoordinates
    coordinate_space: Literal["0-1000"] = "0-1000"


class W3CSelector(BaseModel):
    """W3C Media Fragments selector for PDF page and coordinate targeting."""

    type: Literal["FragmentSelector"] = "FragmentSelector"
    conformsTo: Literal["http://www.w3.org/TR/media-frags/"] = "http://www.w3.org/TR/media-frags/"
    page: int = Field(..., ge=1, description="1-indexed source PDF page")
    value: str = Field(..., description="Media fragments selector string (e.g. xywh=...)")
    refinedBy: W3CRefinedBy


class W3CTarget(BaseModel):
    """W3C Web Annotation Target representing the source PDF document and fragment."""

    source: str = Field(..., description="Source filename (UTF-8, unmodified)")
    selector: W3CSelector | None = Field(default=None)


class W3CBody(BaseModel):
    """W3C Web Annotation Body containing the extracted and normalized textual description."""

    type: Literal["TextualBody"] = "TextualBody"
    value: str = Field(..., description="Extracted raw string or calculation representation")
    label: str = Field(..., description="Normalized taxonomy label")
    original_label: str | None = Field(default=None, description="Original structural label")
    purpose: Literal["describing"] = "describing"


class W3CAnnotationRecord(BaseModel):
    """
    Canonical W3C Web Annotation record for a generated workbook cell (plan §6.1 item 7, spec §4).
    """

    context: Literal["http://www.w3.org/ns/anno.jsonld"] = Field(
        default="http://www.w3.org/ns/anno.jsonld",
        alias="@context",
    )
    id: str = Field(..., description="Canonical URN identifying this annotation")
    type: Literal["Annotation"] = "Annotation"
    job_id: str = Field(..., description="Originating job UUID")
    sheet_name: str = Field(..., description="Space-free worksheet name")
    cell_coord: str = Field(..., description="Excel A1 coordinate (e.g. 'F2', 'C4')")
    node_id: str = Field(..., description="Associated FormulaNode ID")
    is_formula: bool = Field(default=False, description="True if cell is formula-driven")
    body: W3CBody
    target: W3CTarget


class CellReference(BaseModel):
    """
    Metadata representation of a generated cell within the Excel workbook.
    """

    sheet_name: str = Field(
        ...,
        description="Space-free worksheet name containing the cell",
    )
    row: int = Field(
        ...,
        ge=0,
        description="Zero-indexed row index in worksheet",
    )
    col: int = Field(
        ...,
        ge=0,
        description="Zero-indexed column index in worksheet",
    )
    coordinate: str = Field(
        ...,
        description="Excel A1-style cell reference (e.g. 'D2', 'C15')",
    )
    node_id: str | None = Field(
        default=None,
        description="Associated FormulaNode ID if linked to the formula tree",
    )
    formula: str | None = Field(
        default=None,
        description="Excel formula string if this cell is derived (starts with '=')",
    )
    is_formula: bool = Field(
        default=False,
        description="True if cell contains a dynamic Excel formula",
    )
    is_hardcode: bool = Field(
        default=False,
        description="True if cell is explicitly tagged as a manual hardcode",
    )
    source_node_id: str | None = Field(
        default=None,
        description="Originating FormulaInputNode ID for provenance tracking",
    )
    annotation_id: str | None = Field(
        default=None,
        description="Canonical W3C Web Annotation ID bound to this cell",
    )


class WorkbookGenerationResult(BaseModel):
    """
    Summary result of serializing a FormulaTree into an .xlsx workbook.
    """

    job_id: str = Field(
        ...,
        description="UUID of the job",
    )
    file_path: str = Field(
        ...,
        description="Absolute filesystem path to the generated .xlsx workbook",
    )
    target_metric: str = Field(
        ...,
        description="Target metric name (e.g. Adjusted EBITDA)",
    )
    sheet_names: list[str] = Field(
        default_factory=list,
        description="List of all created space-free sheet names",
    )
    total_cells_generated: int = Field(
        default=0,
        ge=0,
        description="Total number of populated data/formula cells in the workbook",
    )
    formula_cells_count: int = Field(
        default=0,
        ge=0,
        description="Total count of formula-driven cells",
    )
    source_cells_count: int = Field(
        default=0,
        ge=0,
        description="Total count of source input data cells",
    )
    cell_references: list[CellReference] = Field(
        default_factory=list,
        description="List of all cell references generated in the workbook",
    )
    provenance_records: list[W3CAnnotationRecord] = Field(
        default_factory=list,
        description="Canonical W3C Web Annotation records for all generated cells",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Diagnostic warnings (e.g. EC-2 unparseable values)",
    )
    is_success: bool = Field(
        default=True,
        description="True if generation and atomic disk serialization completed cleanly",
    )
    error_detail: str | None = Field(
        default=None,
        description="Error explanation if workbook generation failed",
    )


class ProvenanceQueryResponse(BaseModel):
    """API response for provenance records query (Feature 6 / Feature 8)."""

    job_id: str
    total_records: int
    records: list[W3CAnnotationRecord]
