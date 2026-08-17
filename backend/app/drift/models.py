"""
Data models for Cross-Year Drift Detection (Feature 7).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic boundaries), §2.3 (frozen fields).
"""

from pydantic import BaseModel, Field


class MetricDefinitionNode(BaseModel):
    """
    Represents a specific metric component definition in the historical drift graph.
    """

    node_id: str = Field(..., description="Unique identifier for this definition node")
    entity: str = Field(..., description="Entity identifier (e.g. company ticker/name)")
    target_metric: str = Field(..., description="Target metric name (e.g. 'Adjusted EBITDA')")
    filing_year: int = Field(..., description="Filing year associated with this definition")
    component_labels: list[str] = Field(
        default_factory=list,
        description="Sorted list of normalized component labels that define this metric",
    )
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")


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
    prior_node_id: str = Field(
        ...,
        description="Reference to the prior-year graph node compared against",
    )
    created_at: str = Field(..., description="ISO 8601 UTC timestamp of flag generation")


class DriftFlagsResponse(BaseModel):
    """
    API response model for GET /drift/jobs/{job_id}/flags (spec AC-8, EC-10).
    """

    job_id: str = Field(..., description="Job identifier")
    entity: str | None = Field(default=None, description="Entity identifier if known")
    target_metric: str | None = Field(default=None, description="Target metric name if known")
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
