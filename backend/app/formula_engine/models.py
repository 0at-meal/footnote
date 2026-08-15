"""
Data models for the formula engine (Feature 4).

Enforces CONSTITUTION §1.1, §1.3, §1.4, §2.3:
- Fully typed Pydantic models for pipeline stage boundary.
- Pure in-memory representations (no I/O, no random, no clock).
- Preserves frozen schema field names (value, label, page, bbox, source_file).
"""

from enum import Enum

from pydantic import BaseModel, Field


class FormulaInputNode(BaseModel):
    """
    Authoritative in-memory input node representing a single confirmed line item.

    Each node binds the confirmed normalized taxonomy label to its raw extracted value
    and W3C Web Annotation provenance fields (0-1000 normalized space).
    """

    node_id: str = Field(
        ...,
        description="Unique deterministic node identifier within the formula input set",
    )
    normalized_label: str = Field(
        ...,
        min_length=1,
        description="Confirmed standardized taxonomy label from Feature 3",
    )
    value: str = Field(
        ...,
        description="Raw extracted numeric or text string from source document (unmodified)",
    )
    label: str = Field(
        ...,
        description="Original structural label from Feature 2 extraction",
    )
    page: int = Field(
        ...,
        ge=1,
        description="1-indexed page number in the source PDF",
    )
    bbox: dict[str, float] = Field(
        ...,
        description="W3C Web Annotation bounding box in 0-1000 space: {x0, y0, x1, y1}",
    )
    source_file: str = Field(
        ...,
        min_length=1,
        description="Original filename string as uploaded (UTF-8, unmodified)",
    )
    record_index: int = Field(
        ...,
        ge=0,
        description="Zero-based index of originating extraction record in the job batch",
    )
    is_hardcode: bool = Field(
        default=False,
        description="Explicit flag for manual hardcode overrides per NFR2",
    )


class FormulaInputError(BaseModel):
    """
    Error record indicating a validation or provenance failure during formula input extraction.
    """

    record_index: int = Field(
        ...,
        ge=0,
        description="Zero-based index of the affected record in the input batch",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Explanation of the validation or provenance failure",
    )
    label: str | None = Field(
        default=None,
        description="Structural or normalized label if available",
    )
    source_file: str | None = Field(
        default=None,
        description="Source file name if available",
    )


class FormulaInputBatch(BaseModel):
    """
    Container for the batch of valid formula input nodes and any encountered errors.
    """

    nodes: list[FormulaInputNode] = Field(
        default_factory=list,
        description="List of valid confirmed formula input nodes",
    )
    errors: list[FormulaInputError] = Field(
        default_factory=list,
        description="List of validation/provenance errors surfaced during filtering",
    )
    total_records_received: int = Field(
        ...,
        ge=0,
        description="Total count of ClassifiedRecord objects provided to the reader",
    )
    confirmed_count: int = Field(
        ...,
        ge=0,
        description="Count of records with confirmed normalized labels",
    )
    excluded_count: int = Field(
        ...,
        ge=0,
        description="Count of records excluded (pending confirmation, manual required, or errors)",
    )
    error_message: str | None = Field(
        default=None,
        description="Top-level error message if batch cannot proceed to tree generation (e.g. EC-5)",
    )


class FormulaNodeType(str, Enum):
    """
    Classification of nodes within the formula expression tree.
    """

    leaf = "leaf"
    """Leaf node binding directly to a single extracted source item with full provenance."""

    aggregate = "aggregate"
    """Intermediate node aggregating multiple occurrences of the same normalized label (EC-1)."""

    calculated_root = "calculated_root"
    """Root target metric formula node (e.g. Adjusted EBITDA)."""


class FormulaNode(BaseModel):
    """
    Node within the hierarchical formula tree expression graph.
    """

    node_id: str = Field(
        ...,
        description="Deterministic unique identifier for this tree node",
    )
    label: str = Field(
        ...,
        description="Display label or metric name",
    )
    node_type: FormulaNodeType = Field(
        ...,
        description="Type of formula node (leaf, aggregate, or calculated_root)",
    )
    operator: str = Field(
        default="+",
        description="Arithmetic operator with respect to parent (+, -, or root)",
    )
    formula_expression: str | None = Field(
        default=None,
        description="Symbolic or Excel formula representation for calculated nodes",
    )
    source_node: FormulaInputNode | None = Field(
        default=None,
        description="Reference to originating confirmed input node (leaf nodes only)",
    )
    children: list["FormulaNode"] = Field(
        default_factory=list,
        description="Child operand nodes contributing to this formula node",
    )


class FormulaTree(BaseModel):
    """
    Complete in-memory formula tree for a target metric (FR5, FR6).
    """

    target_metric: str = Field(
        ...,
        description="Target metric name (e.g. Adjusted EBITDA)",
    )
    root: FormulaNode | None = Field(
        default=None,
        description="Root formula node representing the reconciled target metric",
    )
    nodes_by_id: dict[str, FormulaNode] = Field(
        default_factory=dict,
        description="Lookup mapping of all nodes by node_id",
    )
    leaves: list[FormulaNode] = Field(
        default_factory=list,
        description="Flattened list of all leaf nodes in deterministic order",
    )
    total_leaves: int = Field(
        default=0,
        description="Count of active leaf nodes in the tree",
    )
    is_valid: bool = Field(
        default=True,
        description="True if formula tree is structurally valid and ready for export",
    )
    error_message: str | None = Field(
        default=None,
        description="Error description if tree construction failed (e.g. EC-4, EC-5)",
    )
