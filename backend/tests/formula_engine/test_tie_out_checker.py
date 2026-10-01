"""
Unit tests for Tie-Out Check Engine and Checks Sheet (FN-012).
"""

from pathlib import Path

import openpyxl
from app.classification.models import StatementType
from app.excel_export.generator import generate_workbook
from app.formula_engine.models import FormulaInputBatch, FormulaInputNode
from app.formula_engine.tie_out_checker import (
    CheckResult,
    CheckStatus,
    apply_check_results_to_records,
    check_add_backs_sum,
    check_dna_cash_flow_match,
    check_net_income_match,
    check_period_consistency,
    check_sign_consistency,
    check_tax_and_interest_tie,
    run_tie_out_checks,
)
from app.formula_engine.tree import build_formula_tree


def _make_node(
    node_id: str,
    norm_label: str,
    val: str,
    statement_type: StatementType | None = None,
    idx: int = 0,
) -> FormulaInputNode:
    return FormulaInputNode(
        node_id=node_id,
        normalized_label=norm_label,
        value=val,
        label=norm_label,
        page=1,
        bbox={"x0": 10.0, "y0": 20.0, "x1": 50.0, "y1": 40.0},
        source_file="filing.pdf",
        record_index=idx,
        statement_type=statement_type,
    )


def test_check_add_backs_sum_pass() -> None:
    """FN-012: Check 1 passes when components precisely foot to reported total."""
    nodes = [
        _make_node("n1", "Net Income", "50,000", idx=0),
        _make_node("n2", "Income Tax Expense", "10,000", idx=1),
        _make_node("n3", "Interest Expense", "5,000", idx=2),
        _make_node("n4", "Depreciation & Amortization", "8,000", idx=3),
        _make_node("n5", "Stock-based compensation", "2,000", idx=4),
        _make_node("n6", "Adjusted EBITDA", "75,000", idx=5),
    ]

    res = check_add_backs_sum(nodes, target_metric="Adjusted EBITDA", tolerance=1.0)
    assert res.status == CheckStatus.PASS
    assert res.expected == 75000.0
    assert res.actual == 75000.0
    assert res.delta == 0.0
    assert res.failure_reason is None
    assert len(res.affected_item_ids) == 0


def test_check_add_backs_sum_fail_and_demotion() -> None:
    """FN-012 / I3: Check 1 fails when sum differs from target, identifying affected item IDs."""
    nodes = [
        _make_node("n1", "Net Income", "50,000", idx=0),
        _make_node("n2", "Income Tax Expense", "10,000", idx=1),
        _make_node("n3", "Adjusted EBITDA", "70,000", idx=2),  # Expected 60,000 != 70,000
    ]

    res = check_add_backs_sum(nodes, target_metric="Adjusted EBITDA", tolerance=1.0)
    assert res.status == CheckStatus.FAIL
    assert res.expected == 60000.0
    assert res.actual == 70000.0
    assert res.delta == 10000.0
    assert "delta: 10,000" in (res.failure_reason or "")
    assert len(res.affected_item_ids) == 3


def test_check_net_income_match_pass_and_fail() -> None:
    """FN-012: Check 2 verifies starting Net Income ties to Income Statement."""
    # Pass case
    nodes_pass = [
        _make_node("n1", "Net Income", "50,000", statement_type=None),
        _make_node("n2", "Net Income", "50,000", statement_type=StatementType.income_statement),
    ]
    res_pass = check_net_income_match(nodes_pass)
    assert res_pass.status == CheckStatus.PASS
    assert res_pass.delta == 0.0

    # Fail case
    nodes_fail = [
        _make_node("n1", "Net Income", "50,000", statement_type=None),
        _make_node("n2", "Net Income", "48,000", statement_type=StatementType.income_statement),
    ]
    res_fail = check_net_income_match(nodes_fail)
    assert res_fail.status == CheckStatus.FAIL
    assert res_fail.delta == 2000.0
    assert "does not tie" in (res_fail.failure_reason or "")


def test_check_dna_cash_flow_match() -> None:
    """FN-012: Check 3 verifies D&A add-back ties to Cash Flow Statement."""
    nodes = [
        _make_node("n1", "Depreciation & Amortization", "8,000", statement_type=None),
        _make_node("n2", "Depreciation & Amortization", "8,000", statement_type=StatementType.cash_flow),
    ]
    res = check_dna_cash_flow_match(nodes)
    assert res.status == CheckStatus.PASS
    assert res.delta == 0.0


def test_check_tax_and_interest_tie() -> None:
    """FN-012: Check 4 verifies taxes tie to Income Statement."""
    nodes = [
        _make_node("n1", "Income Tax Expense", "12,000", statement_type=None),
        _make_node("n2", "Income Tax Expense", "12,000", statement_type=StatementType.income_statement),
    ]
    res = check_tax_and_interest_tie(nodes)
    assert res.status == CheckStatus.PASS
    assert res.delta == 0.0


def test_check_sign_and_period_consistency() -> None:
    """FN-012: Checks 5 and 6 evaluate sign and reporting period consistency."""
    nodes = [
        _make_node("n1", "Net Income", "50,000"),
        _make_node("n2", "Stock-based compensation", "5,000"),
    ]
    res_sign = check_sign_consistency(nodes)
    assert res_sign.status == CheckStatus.PASS

    res_period = check_period_consistency(nodes)
    assert res_period.status == CheckStatus.PASS


def test_run_all_tie_out_checks_pure_function() -> None:
    """FN-012 / I2: Running checks is a deterministic pure function with consistent outputs."""
    nodes = [
        _make_node("n1", "Net Income", "50,000", idx=0),
        _make_node("n2", "Income Tax Expense", "10,000", idx=1),
        _make_node("n3", "Adjusted EBITDA", "60,000", idx=2),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=3,
        confirmed_count=3,
        excluded_count=0,
    )

    results1 = run_tie_out_checks(batch)
    results2 = run_tie_out_checks(batch)

    assert len(results1) == 6
    assert [r.status for r in results1] == [r.status for r in results2]
    assert [r.check_id for r in results1] == [r.check_id for r in results2]


def test_apply_check_failures_demotes_records() -> None:
    """FN-012 / I3: Failed checks demote affected items to needs-review."""
    class DummyRecord:
        def __init__(self, rec_id: str) -> None:
            self.record_id = rec_id
            self.confidence_band = "auto_accepted"
            self.flags: list[str] = []

    records = [DummyRecord("n1"), DummyRecord("n2")]
    failed_check = CheckResult(
        check_id="chk_test",
        name="Test Check",
        description="Failing check",
        status=CheckStatus.FAIL,
        affected_item_ids=["n1"],
        failure_reason="Footing error detected",
    )

    apply_check_results_to_records(records, [failed_check])
    assert records[0].confidence_band == "needs_review"
    assert any("TIE_OUT_FAILURE" in f for f in records[0].flags)
    assert records[1].confidence_band == "auto_accepted"


def test_generator_writes_checks_sheet_with_live_formulas(tmp_path: Path) -> None:
    """
    FN-012 Acceptance Criterion:
    Excel workbook generates with a Checks sheet containing live formulas.
    """
    nodes = [
        _make_node("n1", "Net Income", "50,000", idx=0),
        _make_node("n2", "Income Tax Expense", "10,000", idx=1),
        _make_node("n3", "Stock-based compensation", "5,000", idx=2),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=3,
        confirmed_count=3,
        excluded_count=0,
    )
    tree = build_formula_tree(batch)
    assert tree.is_valid is True

    result = generate_workbook(tree, job_id="test_checks_job", output_dir=tmp_path)
    assert result.is_success is True
    assert "Checks" in result.sheet_names

    # Inspect generated Excel with openpyxl
    wb = openpyxl.load_workbook(result.file_path, data_only=False)
    assert "Checks" in wb.sheetnames

    ws_checks = wb["Checks"]
    # Check Title
    assert "Model Tie-Out" in str(ws_checks["A1"].value)
    # Check headers
    assert ws_checks["A3"].value == "Check Name"
    assert ws_checks["F3"].value == "Status"
    # Live formula in F4
    f4_val = str(ws_checks["F4"].value)
    assert "IF" in f4_val and "PASS" in f4_val
    # Live summary formula in F7
    f7_val = str(ws_checks["F7"].value)
    assert "COUNTIF" in f7_val and "FAIL" in f7_val
    wb.close()
