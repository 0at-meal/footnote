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
    """Candidate matches a taxonomy canonical name or alias (exact, cleaned, or canonicalized)."""

    fuzzy_matched = "fuzzy_matched"
    """Fuzzy token-set-ratio suggestion (>= 0.85); requires human confirmation, is_matched stays False."""

    pending_taxonomy_confirmation = "pending_taxonomy_confirmation"
    """Candidate label does not match taxonomy; queued for explicit human review."""


class TaxonomyCheckResult(BaseModel):
    """
    Result of evaluating a candidate label against the active taxonomy.
    """

    candidate_label: str = Field(
        ..., description="Candidate line-item label being checked"
    )
    status: TaxonomyStatus = Field(
        ...,
        description="Match status (matched, fuzzy_matched, or pending_taxonomy_confirmation)",
    )
    matched_entry: str | None = Field(
        default=None,
        description="Matched entry, or the suggested entry for a fuzzy match; otherwise None",
    )
    matched_item: TaxonomyItem | None = Field(
        default=None,
        description="Matched TaxonomyItem if matched against MasterTaxonomy",
    )
    is_matched: bool = Field(
        default=False,
        description="True only for an exact, alias, or canonicalized match; fuzzy suggestions stay False",
    )
    similarity_score: float | None = Field(
        default=None,
        description="Fuzzy matching token-set similarity score if fuzzy matched",
    )
