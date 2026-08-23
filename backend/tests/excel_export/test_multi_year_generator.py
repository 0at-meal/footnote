"""
Unit tests for app.excel_export.multi_year_generator.generate_multi_year_workbook.

Tests verify:
- Multi-year layout with FY column ordering
- Correct line item row alignment across years
- Absent items in a given year are left blank (not zero)
- Accurate =SUM(col_start:col_end) formula generation
- W3C Web Annotation provenance records and cell comments
- Error handling on empty or invalid trees
"""

from pathlib import Path

from app.excel_export.multi_year_generator import generate_multi_year_workbook
from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputNode,
    FormulaNode,
    FormulaNodeType,
    FormulaTree,
)
from app.ingestion.models import CompanyRecord, JobRecord, JobStatus


def _make_input_node(
    node_id: str, label: str, value: str, page: int = 1
) -> FormulaInputNode:
    return FormulaInputNode(
        node_id=node_id,
        label=label,
        normalized_label=label,
        value=value,
        page=page,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 500.0, "y1": 250.0},
        source_file=f"filing_page_{page}.pdf",
        record_index=0,
    )


def _make_tree(
    target_metric: str, leaves_data: list[tuple[str, str, str]]
) -> FormulaTree:
    """Builds a valid FormulaTree from a list of (node_id, label, value)."""
    leaves: list[FormulaNode] = []
    for node_id, label, value in leaves_data:
        src = _make_input_node(node_id, label, value)
        leaves.append(
            FormulaNode(
                node_id=node_id,
                label=label,
                node_type=FormulaNodeType.leaf,
                source_node=src,
                children=[],
            )
        )

    root = FormulaNode(
        node_id=f"root-{target_metric}",
        label=target_metric,
        node_type=FormulaNodeType.calculated_root,
        children=leaves,
    )

    batch = FormulaInputBatch(
        nodes=[leaf.source_node for leaf in leaves if leaf.source_node is not None],
        total_records_received=len(leaves),
        confirmed_count=len(leaves),
        excluded_count=0,
    )

    return FormulaTree(
        root=root,
        leaves=leaves,
        target_metric=target_metric,
        batch=batch,
        is_valid=True,
    )


def test_generate_multi_year_workbook_with_three_years(tmp_path: Path) -> None:
    """AC: 3 FormulaTree inputs produce single xlsx with 3 year columns, correct formulas and provenance."""
    company = CompanyRecord(
        company_id="comp-123",
        name="Acme Corporation",
        ticker="ACME",
        created_at="2026-08-23T12:00:00Z",
        job_ids=["job-2021", "job-2022", "job-2023"],
    )

    # Year 2021 has: Stock-based Comp ($100), Restructuring ($50)
    tree_2021 = _make_tree(
        "Adjusted EBITDA",
        [
            ("n1-2021", "Stock-based Compensation", "100.00"),
            ("n2-2021", "Restructuring Charges", "50.00"),
        ],
    )
    job_2021 = JobRecord(
        job_id="job-2021",
        filename="acme_2021.pdf",
        file_size_bytes=1000,
        status=JobStatus.done,
        target_metric="Adjusted EBITDA",
        submitted_at="2026-01-01T00:00:00Z",
        filing_year=2021,
        company_id=company.company_id,
    )

    # Year 2022 has: Stock-based Comp ($120), Legal Settlement ($30) [Restructuring absent!]
    tree_2022 = _make_tree(
        "Adjusted EBITDA",
        [
            ("n1-2022", "Stock-based Compensation", "120.00"),
            ("n3-2022", "Legal Settlement", "30.00"),
        ],
    )
    job_2022 = JobRecord(
        job_id="job-2022",
        filename="acme_2022.pdf",
        file_size_bytes=1100,
        status=JobStatus.done,
        target_metric="Adjusted EBITDA",
        submitted_at="2026-01-02T00:00:00Z",
        filing_year=2022,
        company_id=company.company_id,
    )

    # Year 2023 has: Stock-based Comp ($140), Restructuring ($60), Legal Settlement ($40)
    tree_2023 = _make_tree(
        "Adjusted EBITDA",
        [
            ("n1-2023", "Stock-based Compensation", "140.00"),
            ("n2-2023", "Restructuring Charges", "60.00"),
            ("n3-2023", "Legal Settlement", "40.00"),
        ],
    )
    job_2023 = JobRecord(
        job_id="job-2023",
        filename="acme_2023.pdf",
        file_size_bytes=1200,
        status=JobStatus.done,
        target_metric="Adjusted EBITDA",
        submitted_at="2026-01-03T00:00:00Z",
        filing_year=2023,
        company_id=company.company_id,
    )

    jobs = [(job_2021, tree_2021), (job_2022, tree_2022), (job_2023, tree_2023)]

    result = generate_multi_year_workbook(company, jobs, output_dir=tmp_path)

    assert result.is_success is True
    assert Path(result.file_path).exists()
    assert result.sheet_names == ["Multi_Year_Model"]

    # 3 unique line items: Stock-based Comp, Restructuring, Legal Settlement
    # Total rows = 3 data rows (rows 3, 4, 5 in Excel, 1-indexed) + total row (row 6)
    # Total formula cells: 3 (one per year column: B6, C6, D6)
    assert result.formula_cells_count == 3
    # Total value cells: 2 in 2021 + 2 in 2022 + 3 in 2023 = 7 value cells
    assert result.source_cells_count == 7
    assert result.total_cells_generated == 10

    # Verify formula strings in cell references
    formulas = {c.coordinate: c.formula for c in result.cell_references if c.is_formula}
    assert formulas["B6"] == "=SUM(B3:B5)"
    assert formulas["C6"] == "=SUM(C3:C5)"
    assert formulas["D6"] == "=SUM(D3:D5)"

    # Verify provenance records generated for all 7 value cells
    assert len(result.provenance_records) == 7
    for record in result.provenance_records:
        assert record.sheet_name == "Multi_Year_Model"
        assert record.body.value is not None


def test_generate_multi_year_workbook_empty_or_invalid_jobs(tmp_path: Path) -> None:
    """Empty or invalid jobs list returns is_success=False."""
    company = CompanyRecord(
        company_id="comp-empty",
        name="Empty Corp",
        created_at="2026-08-23T12:00:00Z",
    )

    result = generate_multi_year_workbook(company, [], output_dir=tmp_path)
    assert result.is_success is False
    assert result.total_cells_generated == 0
    assert "No valid jobs" in (result.error_detail or "")


def test_generate_multi_year_workbook_without_ticker_and_without_filing_year(
    tmp_path: Path,
) -> None:
    """Company without ticker and job without filing_year falls back cleanly."""
    company = CompanyRecord(
        company_id="comp-no-ticker",
        name="Private Equity Portfolio Co",
        ticker=None,
        created_at="2026-08-23T12:00:00Z",
    )

    tree_1 = _make_tree(
        "EBITDA",
        [("n1", "Management Fees", "25.50")],
    )
    job_1 = JobRecord(
        job_id="job-not-dated",
        filename="custom_filing.pdf",
        file_size_bytes=500,
        status=JobStatus.done,
        target_metric="EBITDA",
        submitted_at="2026-01-01T00:00:00Z",
        filing_year=None,
        company_id=company.company_id,
    )

    result = generate_multi_year_workbook(
        company, [(job_1, tree_1)], output_dir=tmp_path
    )
    assert result.is_success is True
    assert result.total_cells_generated == 2  # 1 value cell + 1 total formula cell
    formulas = {c.coordinate: c.formula for c in result.cell_references if c.is_formula}
    assert formulas["B4"] == "=SUM(B3:B3)"


def test_generate_multi_year_workbook_with_two_years(tmp_path: Path) -> None:
    """Generate multi-year workbook with exactly 2 years."""
    company = CompanyRecord(
        company_id="comp-2yr",
        name="Dunder Mifflin",
        ticker="DMI",
        created_at="2026-08-23T12:00:00Z",
        job_ids=["job-2022", "job-2023"],
    )

    tree_2022 = _make_tree(
        "Adjusted EBITDA",
        [
            ("n1", "Paper Sales Margin", "500.00"),
            ("n2", "Branch Overhead", "200.00"),
        ],
    )
    job_2022 = JobRecord(
        job_id="job-2022",
        filename="dunder_2022.pdf",
        file_size_bytes=1000,
        status=JobStatus.done,
        target_metric="Adjusted EBITDA",
        submitted_at="2026-01-01T00:00:00Z",
        filing_year=2022,
        company_id=company.company_id,
    )

    tree_2023 = _make_tree(
        "Adjusted EBITDA",
        [
            ("n1", "Paper Sales Margin", "600.00"),
            ("n2", "Branch Overhead", "220.00"),
        ],
    )
    job_2023 = JobRecord(
        job_id="job-2023",
        filename="dunder_2023.pdf",
        file_size_bytes=1100,
        status=JobStatus.done,
        target_metric="Adjusted EBITDA",
        submitted_at="2026-01-02T00:00:00Z",
        filing_year=2023,
        company_id=company.company_id,
    )

    result = generate_multi_year_workbook(
        company, [(job_2022, tree_2022), (job_2023, tree_2023)], output_dir=tmp_path
    )
    assert result.is_success is True
    assert result.formula_cells_count == 2
    assert result.source_cells_count == 4
    assert result.total_cells_generated == 6

    formulas = {c.coordinate: c.formula for c in result.cell_references if c.is_formula}
    assert formulas["B5"] == "=SUM(B3:B4)"
    assert formulas["C5"] == "=SUM(C3:C4)"
