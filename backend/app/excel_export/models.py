"""
Data models for the Excel export stage (Feature 4 Step 3).

Enforces CONSTITUTION §1.1, §1.3, §1.5, §2.3, §2.5:
- Fully typed Pydantic models for workbook metadata and cell mapping.
- Tracks formula vs. hardcode status per IB convention.
"""

from pydantic import BaseModel, Field


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
