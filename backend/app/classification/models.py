"""
Data models for the master financial taxonomy.
"""

from enum import Enum

from pydantic import BaseModel, Field


class StatementType(str, Enum):
    """
    Financial statement classification categories.
    """

    income_statement = "income_statement"
    balance_sheet = "balance_sheet"
    cash_flow = "cash_flow"
    non_gaap_bridge = "non_gaap_bridge"
    kpi = "kpi"


class TaxonomyItem(BaseModel):
    """
    A single canonical financial line item in the Master Financial Taxonomy.
    """

    canonical_name: str = Field(
        ..., min_length=1, description="Standardized GAAP/IFRS canonical line item name"
    )
    statement_type: StatementType = Field(
        ..., description="Financial statement type to which this line item belongs"
    )
    display_order: int = Field(
        default=0, description="Standard presentation order within the statement"
    )
    is_debit: bool = Field(
        default=False,
        description="True for debit normal balance (assets, expenses), False for credit (liabilities, equity, revenue)",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="List of recognized filing text aliases for deterministic matching",
    )


class MasterTaxonomy(BaseModel):
    """
    Structured Master Financial Taxonomy containing all canonical line items.
    """

    items: list[TaxonomyItem] = Field(
        default_factory=list,
        description="List of canonical taxonomy items",
    )


class TaxonomyStatus(str, Enum):
    """
    Taxonomy verification status for a classified label.
    """

    matched = "matched"
    """Candidate label matches an active seed taxonomy entry by exact string match."""

    fuzzy_matched = "fuzzy_matched"
    """Candidate label matches an active taxonomy entry by fuzzy token-set-ratio similarity (>= 0.85)."""

    pending_taxonomy_confirmation = "pending_taxonomy_confirmation"
    """Candidate label does not match taxonomy; queued for explicit human review."""


class TaxonomyCheckResult(BaseModel):
    """
    Result of evaluating a candidate label against the active taxonomy.
    """

    candidate_label: str = Field(
        ..., description="Candidate label returned by classifier"
    )
    status: TaxonomyStatus = Field(
        ...,
        description="Match status (matched, fuzzy_matched, or pending_taxonomy_confirmation)",
    )
    matched_entry: str | None = Field(
        default=None,
        description="Matched taxonomy entry if matched or fuzzy matched, otherwise None",
    )
    matched_item: TaxonomyItem | None = Field(
        default=None,
        description="Matched TaxonomyItem if matched against MasterTaxonomy",
    )
    is_matched: bool = Field(
        default=False,
        description="Convenience boolean indicating whether exact or fuzzy match was found",
    )
    similarity_score: float | None = Field(
        default=None,
        description="Fuzzy matching token-set similarity score if fuzzy matched",
    )

