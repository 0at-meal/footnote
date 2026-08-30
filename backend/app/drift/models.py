"""
Data models for Cross-Year Drift Detection (Feature 7).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic boundaries), §2.3 (frozen fields).
"""

from enum import Enum

from pydantic import BaseModel, Field


class DriftChangeType(str, Enum):
    """
    Classification of drift change.
    """

    added = "added"
    removed = "removed"
    modified = "modified"
    relabeled = "relabeled"


class DriftEdgeType(str, Enum):
    """
    Type of directed transition edge in the historical drift graph.
    """

    redefinition = "redefinition"
    continuation = "continuation"


class RelabeledComponent(BaseModel):
    """
    Component whose label shifted cosmetically but substance remains identical (Step J).
    """

    old_label: str = Field(..., description="Prior period component label")
    new_label: str = Field(..., description="Current period component label")
    similarity_score: float = Field(
        ..., description="Token / fuzzy similarity score (0.0 - 1.0)"
    )
    is_confirmed: bool = Field(
        default=False, description="True if confirmed by analyst"
    )
    justification: str | None = Field(
        default=None, description="Analyst rationale or confirmation note"
    )


class MetricDefinitionNode(BaseModel):
    """
    Represents a specific metric component definition in the historical drift graph.
    """

    node_id: str = Field(..., description="Unique identifier for this definition node")
    entity: str = Field(..., description="Entity identifier (e.g. company ticker/name)")
    target_metric: str = Field(
        ..., description="Target metric name (e.g. 'Adjusted EBITDA')"
    )
    filing_year: int = Field(
        ..., description="Filing year associated with this definition"
    )
    component_labels: list[str] = Field(
        default_factory=list,
        description="Sorted list of normalized component labels that define this metric",
    )
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")


class DriftEdge(BaseModel):
    """
    Represents a directed link between metric definition states in the drift graph (spec §3).
    """

    edge_id: str = Field(..., description="Unique identifier for this drift graph edge")
    from_node_id: str = Field(..., description="Originating prior definition node ID")
    to_node_id: str = Field(..., description="Target definition node ID")
    entity: str = Field(..., description="Entity identifier")
    target_metric: str = Field(..., description="Target metric name")
    filing_year: int = Field(..., description="Filing year of the transition")
    edge_type: DriftEdgeType = Field(
        ..., description="Whether definition changed or continued"
    )
    added_labels: list[str] = Field(
        default_factory=list,
        description="Component labels added in this transition",
    )
    removed_labels: list[str] = Field(
        default_factory=list,
        description="Component labels removed in this transition",
    )
    relabeled_labels: list[RelabeledComponent] = Field(
        default_factory=list,
        description="Component labels relabeled in this transition",
    )
    created_at: str = Field(..., description="ISO 8601 UTC timestamp of edge creation")


class DriftComparisonResult(BaseModel):
    """
    Result of comparing a current filing's normalized labels against a prior-year graph entry.
    """

    entity: str = Field(..., description="Entity identifier")
    target_metric: str = Field(..., description="Target financial metric")
    filing_year: int = Field(..., description="Current filing year")
    is_baseline: bool = Field(
        ...,
        description="True if no prior graph node exists (baseline initialization year)",
    )
    added_labels: list[str] = Field(
        default_factory=list,
        description="Normalized labels present in current filing but absent in prior entry",
    )
    removed_labels: list[str] = Field(
        default_factory=list,
        description="Normalized labels present in prior entry but absent in current filing",
    )
    unchanged_labels: list[str] = Field(
        default_factory=list,
        description="Normalized labels present in both current filing and prior entry",
    )
    relabeled_components: list[RelabeledComponent] = Field(
        default_factory=list,
        description="Components detected as cosmetic relabeling (similarity >= 0.80)",
    )
    current_labels: list[str] = Field(
        default_factory=list,
        description="All normalized labels from confirmed locked items in the current filing",
    )
    prior_node_id: str | None = Field(
        default=None,
        description="Node ID of the prior-year definition entry compared against, if any",
    )
    has_discrepancy: bool = Field(
        ...,
        description="True if there are any added or removed component labels",
    )


class DriftFlag(BaseModel):
    """
    Structured discrepancy record created when a metric redefinition is detected (spec §2, AC-2, AC-4).
    """

    flag_id: str = Field(..., description="Unique drift flag identifier (UUIDv4)")
    job_id: str = Field(..., description="Job identifier of the current filing")
    entity: str = Field(..., description="Entity identifier")
    target_metric: str = Field(..., description="Target metric name")
    filing_year: int = Field(..., description="Filing year of the current filing")
    added_labels: list[str] = Field(
        default_factory=list,
        description="List of component labels added in this filing",
    )
    removed_labels: list[str] = Field(
        default_factory=list,
        description="List of component labels removed in this filing",
    )
    relabeled_components: list[RelabeledComponent] = Field(
        default_factory=list,
        description="List of cosmetic relabelings detected in this filing",
    )
    prior_node_id: str = Field(
        ...,
        description="Reference to the prior-year graph node compared against",
    )
    created_at: str = Field(
        ..., description="ISO 8601 UTC timestamp of flag generation"
    )


class DriftFlagsResponse(BaseModel):
    """
    API response model for GET /drift/jobs/{job_id}/flags (spec AC-8, EC-10).
    """

    job_id: str = Field(..., description="Job identifier")
    entity: str | None = Field(default=None, description="Entity identifier if known")
    target_metric: str | None = Field(
        default=None, description="Target metric name if known"
    )
    filing_year: int | None = Field(default=None, description="Filing year if known")
    is_baseline: bool = Field(
        default=False,
        description="True if the filing was a baseline year with no prior definition",
    )
    flags: list[DriftFlag] = Field(
        default_factory=list,
        description="List of active drift flags for this job",
    )
    total_flags: int = Field(..., description="Count of drift flags returned")


class DriftGraphExport(BaseModel):
    """
    Export representation of the entire drift graph or a subtree (spec §3, §4).
    """

    nodes: list[MetricDefinitionNode] = Field(default_factory=list)
    edges: list[DriftEdge] = Field(default_factory=list)
    total_nodes: int = Field(default=0)
    total_edges: int = Field(default=0)


class MetricHistoryResponse(BaseModel):
    """
    Response model for historical evolution of a target metric definition for an entity (spec §3).
    """

    entity: str
    target_metric: str
    definitions: list[MetricDefinitionNode] = Field(default_factory=list)
    edges: list[DriftEdge] = Field(default_factory=list)
    total_definitions: int = Field(default=0)


class DriftEvaluationRequest(BaseModel):
    """
    Optional payload for POST /drift/jobs/{job_id}/evaluate.
    """

    entity: str | None = Field(
        default=None, description="Optional entity identifier override"
    )
    filing_year: int | None = Field(
        default=None, description="Optional filing year override"
    )


class DriftEvaluationResponse(BaseModel):
    """
    Response model for POST /drift/jobs/{job_id}/evaluate.
    """

    job_id: str
    status: str = Field(..., description="'evaluated' or 'skipped_no_locked_records'")
    entity: str | None = None
    target_metric: str | None = None
    filing_year: int | None = None
    is_baseline: bool = False
    has_discrepancy: bool = False
    flag: DriftFlag | None = None
    active_definition_node: MetricDefinitionNode | None = None


class MarkRelabeledRequest(BaseModel):
    """
    Payload for POST /drift/{job_id}/mark-relabeled (Step J).
    """

    old_standard_label: str = Field(..., description="Prior period label")
    new_standard_label: str = Field(..., description="Current period label")
    justification: str | None = Field(default=None, description="Analyst justification")
