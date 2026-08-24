"""
Unit tests for multi-statement formula tree builders (Phase B).

Validates:
- Income statement tree DAG structure, sign conventions, and missing node handling
- EBITDA bridge tree EBIT cross-reference and add-back aggregation
- Free cash flow tree OCF and CapEx sign conventions
- Net debt tree debt (+) vs cash (-) conventions
- Comprehensive model tree building all statement trees from a mixed batch
- Zero-hallucination guarantee: every leaf is strictly bound to a confirmed input node
"""

import pytest
from app.classification.models import StatementType
from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputNode,
    FormulaNodeType,
)
from app.formula_engine.tree import (
    build_comprehensive_model_tree,
    build_ebitda_bridge_tree,
    build_free_cash_flow_tree,
    build_income_statement_tree,
    build_net_debt_tree,
)


def _make_node(
    label: str,
    value: str = "100",
    record_index: int = 0,
    statement_type: StatementType | None = None,
) -> FormulaInputNode:
    return FormulaInputNode(
        node_id=f"node_{record_index}_{label}",
        normalized_label=label,
        value=value,
        label=label,
        page=1,
        bbox={"x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 50.0},
        source_file="filing.pdf",
        record_index=record_index,
        statement_type=statement_type,
    )


def test_build_income_statement_tree_structure_and_signs() -> None:
    nodes = [
        _make_node("Revenue", value="1000", record_index=0, statement_type=StatementType.income_statement),
        _make_node("Cost of Revenue", value="400", record_index=1, statement_type=StatementType.income_statement),
        _make_node("Research & Development", value="150", record_index=2, statement_type=StatementType.income_statement),
        _make_node("Sales & Marketing", value="100", record_index=3, statement_type=StatementType.income_statement),
        _make_node("Operating Income", value="350", record_index=4, statement_type=StatementType.income_statement),
        _make_node("Provision for Income Taxes", value="50", record_index=5, statement_type=StatementType.income_statement),
        _make_node("Net Income", value="300", record_index=6, statement_type=StatementType.income_statement),
    ]

    tree = build_income_statement_tree(nodes)
    assert tree.is_valid is True
    assert tree.total_leaves == 7

    # Check sign conventions
    nodes_by_label = {leaf.source_node.normalized_label: leaf for leaf in tree.leaves if leaf.source_node}
    assert nodes_by_label["Revenue"].operator == "+"
    assert nodes_by_label["Cost of Revenue"].operator == "-"
    assert nodes_by_label["Research & Development"].operator == "-"
    assert nodes_by_label["Sales & Marketing"].operator == "-"
    assert nodes_by_label["Provision for Income Taxes"].operator == "-"
    assert nodes_by_label["Net Income"].operator == "+"


def test_build_income_statement_tree_empty() -> None:
    tree = build_income_statement_tree([])
    assert tree.is_valid is True
    assert tree.total_leaves == 0


def test_build_ebitda_bridge_tree_cross_reference_and_addbacks() -> None:
    nodes = [
        _make_node("Stock-Based Compensation", value="50", record_index=1, statement_type=StatementType.non_gaap_bridge),
        _make_node("Restructuring Charges", value="20", record_index=2, statement_type=StatementType.non_gaap_bridge),
    ]

    tree = build_ebitda_bridge_tree(nodes)
    assert tree.is_valid is True
    assert tree.root is not None
    assert tree.root.node_type == FormulaNodeType.calculated_root
    assert "=SUM(" in tree.root.formula_expression

    # Check EBIT cross-reference node
    cross_refs = [n for n in tree.nodes_by_id.values() if n.node_type == FormulaNodeType.cross_reference]
    assert len(cross_refs) == 1
    assert cross_refs[0].cross_reference_sheet == "Income_Statement"
    assert cross_refs[0].cross_reference_target == "Operating Income"


def test_build_free_cash_flow_tree_structure() -> None:
    nodes = [
        _make_node("Cash Provided by Operating Activities", value="500", record_index=0, statement_type=StatementType.cash_flow),
        _make_node("Capital Expenditures", value="120", record_index=1, statement_type=StatementType.cash_flow),
        _make_node("Dividends Paid", value="80", record_index=2, statement_type=StatementType.cash_flow),
    ]

    tree = build_free_cash_flow_tree(nodes)
    assert tree.is_valid is True
    assert tree.total_leaves == 3

    nodes_by_label = {leaf.source_node.normalized_label: leaf for leaf in tree.leaves if leaf.source_node}
    assert nodes_by_label["Cash Provided by Operating Activities"].operator == "+"
    assert nodes_by_label["Capital Expenditures"].operator == "-"
    assert nodes_by_label["Dividends Paid"].operator == "-"


def test_build_net_debt_tree_structure() -> None:
    nodes = [
        _make_node("Cash and Cash Equivalents", value="200", record_index=0, statement_type=StatementType.balance_sheet),
        _make_node("Short-Term Investments", value="300", record_index=1, statement_type=StatementType.balance_sheet),
        _make_node("Short-Term Debt", value="100", record_index=2, statement_type=StatementType.balance_sheet),
        _make_node("Long-Term Debt", value="800", record_index=3, statement_type=StatementType.balance_sheet),
    ]

    tree = build_net_debt_tree(nodes)
    assert tree.is_valid is True
    assert tree.total_leaves == 4

    nodes_by_label = {leaf.source_node.normalized_label: leaf for leaf in tree.leaves if leaf.source_node}
    assert nodes_by_label["Short-Term Debt"].operator == "+"
    assert nodes_by_label["Long-Term Debt"].operator == "+"
    assert nodes_by_label["Cash and Cash Equivalents"].operator == "-"
    assert nodes_by_label["Short-Term Investments"].operator == "-"


def test_build_comprehensive_model_tree_mixed_batch() -> None:
    nodes = [
        # Income statement
        _make_node("Revenue", value="1000", record_index=0, statement_type=StatementType.income_statement),
        _make_node("Net Income", value="200", record_index=1, statement_type=StatementType.income_statement),
        # Bridge
        _make_node("Stock-Based Compensation", value="30", record_index=2, statement_type=StatementType.non_gaap_bridge),
        # Cash Flow
        _make_node("Cash Provided by Operating Activities", value="400", record_index=3, statement_type=StatementType.cash_flow),
        _make_node("Capital Expenditures", value="80", record_index=4, statement_type=StatementType.cash_flow),
        # Balance Sheet
        _make_node("Cash and Cash Equivalents", value="150", record_index=5, statement_type=StatementType.balance_sheet),
        _make_node("Long-Term Debt", value="500", record_index=6, statement_type=StatementType.balance_sheet),
    ]

    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=len(nodes),
        confirmed_count=len(nodes),
        excluded_count=0,
    )

    comp_tree = build_comprehensive_model_tree(batch)
    assert comp_tree.is_valid is True
    assert len(comp_tree.statement_trees) == 4

    assert comp_tree.income_statement_tree is not None
    assert comp_tree.income_statement_tree.total_leaves == 2

    assert comp_tree.ebitda_bridge_tree is not None
    assert comp_tree.ebitda_bridge_tree.total_leaves >= 1

    assert comp_tree.cash_flow_tree is not None
    assert comp_tree.cash_flow_tree.total_leaves == 2

    assert comp_tree.balance_sheet_tree is not None
    assert comp_tree.balance_sheet_tree.total_leaves == 2

    # Zero hallucination check: all leaf nodes (except cross-reference) must bind to source_node
    for st in comp_tree.statement_trees:
        for leaf in st.tree.leaves:
            if leaf.node_type == FormulaNodeType.leaf:
                assert leaf.source_node is not None
                assert leaf.source_node.value is not None
                assert leaf.source_node.source_file == "filing.pdf"
