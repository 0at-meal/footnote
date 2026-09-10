"""
Unit tests for Master Financial Taxonomy management, alias matching, and pre-classification (Feature 3).

Validates:
- MasterTaxonomy validation from seed taxonomy.json
- TaxonomyRepository loading and persistence of MasterTaxonomy
- match_master_taxonomy exact canonical and alias matching
- get_items_by_statement filtering
- pre_classify_records deterministic classification bypassing Groq
- Unmatched records returned for Groq dispatch
"""

from pathlib import Path

from app.classification.dispatcher import pre_classify_records
from app.classification.models import (
    MasterTaxonomy,
    StatementType,
    TaxonomyItem,
    TaxonomyStatus,
)
from app.classification.taxonomy import (
    SEED_MASTER_TAXONOMY,
    TaxonomyRepository,
    check_label_against_taxonomy,
    match_master_taxonomy,
)
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)


def _make_dummy_scored_record(
    label: str,
    value: str = "100",
    confidence_band: ConfidenceBand = ConfidenceBand.auto_accepted,
    status: str = "ok",
    table_name: str | None = "Income Statement",
) -> ScoredRecord:
    er = ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 50.0},
        source_file="filing.pdf",
    )
    return ScoredRecord(
        record=er,
        confidence_band=confidence_band,
        confidence_score=0.95,
        status=status,
        flags=[],
        table_name=table_name,
        is_reconciliation_candidate=True,
    )


def test_master_taxonomy_loads_from_seed_json() -> None:
    repo = TaxonomyRepository()
    master = repo.load_taxonomy()
    assert isinstance(master, MasterTaxonomy)
    assert len(master.items) >= 50
    canonical_names = [item.canonical_name for item in master.items]
    assert "Revenue" in canonical_names
    assert "Cost of Revenue" in canonical_names
    assert "Net Income" in canonical_names
    assert "Stock-Based Compensation" in canonical_names


def test_match_master_taxonomy_canonical_and_aliases() -> None:
    master = SEED_MASTER_TAXONOMY

    # 1. Exact canonical name match
    res_rev = match_master_taxonomy("Revenue", master)
    assert res_rev is not None
    assert res_rev.canonical_name == "Revenue"
    assert res_rev.statement_type == StatementType.income_statement

    # 2. Alias match: "Cost of sales" -> "Cost of Revenue"
    res_cogs = match_master_taxonomy("Cost of sales", master)
    assert res_cogs is not None
    assert res_cogs.canonical_name == "Cost of Revenue"

    # 3. Canonicalized alias match with casing / punctuation
    res_sbc = match_master_taxonomy("stock based compensation expense", master)
    assert res_sbc is not None
    assert res_sbc.canonical_name == "Stock-Based Compensation"

    # 4. Leaf match (after /)
    res_leaf = match_master_taxonomy(
        "Operating activities / Depreciation of property and equipment", master
    )
    assert res_leaf is not None
    assert "Depreciation" in res_leaf.canonical_name

    # 5. Miss: unknown label
    res_unknown = match_master_taxonomy("zzz_totally_unknown_line_item_123", master)
    assert res_unknown is None


def test_get_items_by_statement() -> None:
    repo = TaxonomyRepository()
    is_items = repo.get_items_by_statement(StatementType.income_statement)
    assert len(is_items) >= 10
    assert all(
        item.statement_type == StatementType.income_statement for item in is_items
    )

    cf_items = repo.get_items_by_statement(StatementType.cash_flow)
    assert len(cf_items) >= 5
    assert all(item.statement_type == StatementType.cash_flow for item in cf_items)


def test_taxonomy_repository_save_and_reload(tmp_path: Path) -> None:
    repo = TaxonomyRepository(data_dir=tmp_path)
    custom_master = MasterTaxonomy(
        items=[
            TaxonomyItem(
                canonical_name="Custom Metric",
                statement_type=StatementType.kpi,
                display_order=10,
                is_debit=False,
                aliases=["Custom Alias"],
            )
        ]
    )
    saved_path = repo.save_taxonomy(custom_master)
    assert saved_path.exists()

    reloaded = repo.load_taxonomy()
    assert len(reloaded.items) == 1
    assert reloaded.items[0].canonical_name == "Custom Metric"
    assert reloaded.items[0].statement_type == StatementType.kpi


def test_pre_classify_records_deterministic_and_unmatched() -> None:
    master = SEED_MASTER_TAXONOMY

    rec_revenue = _make_dummy_scored_record("Total revenues")
    rec_cogs = _make_dummy_scored_record("Cost of sales")
    rec_unknown = _make_dummy_scored_record("Novel Patent Settlement Reserve")
    rec_error = _make_dummy_scored_record("Revenue", status="extraction_error")

    records = [rec_revenue, rec_cogs, rec_unknown, rec_error]

    pre_classified, unmatched = pre_classify_records(records, master)

    # 2 records matched deterministically (Revenue and Cost of sales)
    assert len(pre_classified) == 2
    assert pre_classified[0].normalized_label == "Revenue"
    assert pre_classified[0].statement_type == StatementType.income_statement
    assert pre_classified[0].is_confirmed is True
    assert pre_classified[0].classifier_confidence == 1.0

    assert pre_classified[1].normalized_label == "Cost of Revenue"
    assert pre_classified[1].statement_type == StatementType.income_statement
    assert pre_classified[1].is_confirmed is True

    # 2 records unmatched (unknown item and extraction_error item)
    assert len(unmatched) == 2
    assert unmatched[0].record.label == "Novel Patent Settlement Reserve"
    assert unmatched[1].record.label == "Revenue"


def test_check_label_against_taxonomy_master() -> None:
    master = SEED_MASTER_TAXONOMY
    result = check_label_against_taxonomy("Cost of goods sold", master)
    assert result.status == TaxonomyStatus.matched
    assert result.is_matched is True
    assert result.matched_entry == "Cost of Revenue"
    assert result.matched_item is not None
    assert result.matched_item.statement_type == StatementType.income_statement

    unknown_result = check_label_against_taxonomy("Random Unknown Item", master)
    assert unknown_result.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert unknown_result.is_matched is False


def test_fuzzy_alias_matching_token_set_ratio() -> None:
    """
    Ticket C-3: Fuzzy alias matching matches similar labels with token-set-ratio >= 0.85
    and produces TaxonomyStatus.fuzzy_matched without blocking matching.
    """
    master = SEED_MASTER_TAXONOMY
    # "Derivative fair value adjustment" vs alias "Derivative fair value adjustments"
    result = check_label_against_taxonomy("Derivative fair value adjustment", master)
    assert result.is_matched is True
    assert result.status in (TaxonomyStatus.matched, TaxonomyStatus.fuzzy_matched)
    assert result.matched_entry == "Change in FV of Derivatives"


def test_expanded_taxonomy_coverage() -> None:
    """
    Ticket C-1: Seed taxonomy contains 60+ items covering non-GAAP and key financial categories.
    """
    master = SEED_MASTER_TAXONOMY
    assert len(master.items) >= 60

    canonical_names = {item.canonical_name for item in master.items}
    required_categories = [
        "Change in FV of Derivatives",
        "Non-cash Lease Expense",
        "Earn-out Payments",
        "IPO-related Costs",
        "Spin-off Costs",
        "COVID Costs",
        "Contingent Consideration",
        "Stock-Based Compensation",
        "Restructuring Charges",
        "Litigation Charges",
        "Interest Expense",
        "Provision for Income Taxes",
    ]
    for cat in required_categories:
        assert cat in canonical_names, f"Missing required category: {cat}"


def test_clean_raw_label_parentheticals_and_dates() -> None:
    """Verifies that clean_raw_label removes parentheticals, dates, footnotes, and bracketed text."""
    from app.classification.taxonomy import clean_raw_label

    assert clean_raw_label("Cost of revenues (exclusive of depreciation)") == "Cost of revenues"
    assert clean_raw_label("Operating income (loss)") == "Operating income"
    assert clean_raw_label("Research and development / 2024") == "Research and development"
    assert clean_raw_label("Restructuring and other charges (Note 4)") == "Restructuring and other charges"
    assert clean_raw_label("Stock-based compensation expense (1)") == "Stock-based compensation expense"
    assert clean_raw_label("[a] Net cash provided by (used in) operating activities") == "Net cash provided by operating activities"


def test_match_master_taxonomy_with_parentheticals_and_headers() -> None:
    """Verifies that match_master_taxonomy matches items with parentheticals, footnote marks, or column dates."""
    from app.classification.taxonomy import match_master_taxonomy

    # Parenthetical exclusion
    item1 = match_master_taxonomy("Cost of revenues (exclusive of depreciation)")
    assert item1 is not None
    assert item1.canonical_name == "Cost of Revenue"

    # Parenthetical (loss)
    item2 = match_master_taxonomy("Operating income (loss)")
    assert item2 is not None
    assert item2.canonical_name == "Operating Income"

    # Year header suffix in table cell
    item3 = match_master_taxonomy("Research and development / 2024")
    assert item3 is not None
    assert item3.canonical_name == "Research & Development"

    # Footnote marker
    item4 = match_master_taxonomy("Stock-based compensation expense (1)")
    assert item4 is not None
    assert item4.canonical_name == "Stock-Based Compensation"

    # Note reference
    item5 = match_master_taxonomy("Restructuring and other charges (Note 14)")
    assert item5 is not None
    assert item5.canonical_name == "Restructuring Charges"
