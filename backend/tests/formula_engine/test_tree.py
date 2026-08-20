"""
Unit tests for Formula Engine tree construction (Feature 4 Step 2).

Tests formula tree construction, determinism, provenance binding, and edge cases:
- AC-1 / NFR1: Byte-identical / deterministic tree structure
- AC-4: Pure function idempotence and structural equality
- AC-5: Every non-hardcoded leaf node resolves to exactly one FormulaInputNode
- EC-1: Multiple confirmed records with same label aggregated cleanly
- EC-4: Unsupported target metric surfaces error
- EC-5: Zero confirmed records error
- EC-9: Single line item degenerate case
"""

import copy

from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputNode,
    FormulaNodeType,
    FormulaTree,
)
from app.formula_engine.tree import build_formula_tree


def _make_input_node(
    record_index: int,
    normalized_label: str,
    value: str = "100.0",
    page: int = 10,
    source_file: str = "filing.pdf",
    bbox: dict[str, float] | None = None,
) -> FormulaInputNode:
    if bbox is None:
        bbox = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0}
    return FormulaInputNode(
        node_id=f"node_{record_index}_{normalized_label}",
        normalized_label=normalized_label,
        value=value,
        label=f"Table Line / {normalized_label}",
        page=page,
        bbox=bbox,
        source_file=source_file,
        record_index=record_index,
        is_hardcode=False,
    )


def test_build_formula_tree_adjusted_ebitda_basic() -> None:
    """Verifies construction of an Adjusted EBITDA formula tree with distinct line items."""
    nodes = [
        _make_input_node(0, "Operating Income", value="500.0", page=12),
        _make_input_node(1, "Depreciation & Amortization", value="150.0", page=14),
        _make_input_node(2, "Stock-Based Compensation", value="50.0", page=28),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=3,
        confirmed_count=3,
        excluded_count=0,
    )

    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert isinstance(tree, FormulaTree)
    assert tree.is_valid is True
    assert tree.error_message is None
    assert tree.target_metric == "Adjusted EBITDA"
    assert tree.total_leaves == 3
    assert len(tree.leaves) == 3
    assert tree.root is not None
    assert tree.root.node_type == FormulaNodeType.calculated_root
    assert len(tree.root.children) == 3

    # Verify all children are direct leaf nodes
    labels = [c.label for c in tree.root.children]
    assert labels == [
        "Operating Income",
        "Depreciation & Amortization",
        "Stock-Based Compensation",
    ]


def test_build_formula_tree_duplicate_labels_aggregated() -> None:
    """Verifies that duplicate normalized labels are aggregated under an intermediate node (EC-1)."""
    nodes = [
        _make_input_node(0, "Operating Income", value="500.0", page=10),
        _make_input_node(1, "Stock-Based Compensation", value="30.0", page=25),
        _make_input_node(2, "Stock-Based Compensation", value="20.0", page=60),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=3,
        confirmed_count=3,
        excluded_count=0,
    )

    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert tree.is_valid is True
    assert tree.root is not None
    assert tree.total_leaves == 3  # All 3 underlying leaf nodes preserved
    assert (
        len(tree.root.children) == 2
    )  # Operating Income (leaf) + Stock-Based Compensation (aggregate)

    # First child is Operating Income leaf
    assert tree.root.children[0].node_type == FormulaNodeType.leaf
    assert tree.root.children[0].label == "Operating Income"

    # Second child is aggregated Stock-Based Compensation
    agg_node = tree.root.children[1]
    assert agg_node.node_type == FormulaNodeType.aggregate
    assert agg_node.label == "Total Stock-Based Compensation"
    assert len(agg_node.children) == 2
    assert agg_node.children[0].node_type == FormulaNodeType.leaf
    assert agg_node.children[1].node_type == FormulaNodeType.leaf
    assert "=SUM(" in (agg_node.formula_expression or "")


def test_build_formula_tree_single_line_item() -> None:
    """Verifies degenerate single line item case builds valid formula tree (EC-9)."""
    nodes = [_make_input_node(0, "EBITDA", value="1000.0", page=1)]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=1,
        confirmed_count=1,
        excluded_count=0,
    )

    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert tree.is_valid is True
    assert tree.root is not None
    assert tree.total_leaves == 1
    assert len(tree.root.children) == 1
    assert tree.root.children[0].node_type == FormulaNodeType.leaf


def test_build_formula_tree_unsupported_metric() -> None:
    """Verifies that non-Adjusted-EBITDA metrics surface explicit unsupported error (EC-4)."""
    batch = FormulaInputBatch(
        nodes=[_make_input_node(0, "Revenue", value="100.0")],
        total_records_received=1,
        confirmed_count=1,
        excluded_count=0,
    )

    tree = build_formula_tree(batch, target_metric="Free Cash Flow")

    assert tree.is_valid is False
    assert tree.root is None
    assert "Unsupported target metric 'Free Cash Flow'" in (tree.error_message or "")
    assert "EC-4" in (tree.error_message or "")


def test_build_formula_tree_empty_batch() -> None:
    """Verifies empty input batch produces invalid tree with error message (EC-5)."""
    batch = FormulaInputBatch(
        nodes=[],
        total_records_received=0,
        confirmed_count=0,
        excluded_count=0,
        error_message="No confirmed records available for formula generation.",
    )

    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert tree.is_valid is False
    assert tree.root is None
    assert (
        tree.error_message == "No confirmed records available for formula generation."
    )


def test_build_formula_tree_purity_and_determinism() -> None:
    """Verifies purity: identical inputs produce structurally identical trees (NFR1, AC-4, CONSTITUTION §1.4)."""
    nodes = [
        _make_input_node(0, "Operating Income", value="200.0"),
        _make_input_node(1, "Litigation Charges", value="40.0"),
        _make_input_node(2, "Litigation Charges", value="15.0"),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=3,
        confirmed_count=3,
        excluded_count=0,
    )
    batch_copy = copy.deepcopy(batch)

    tree1 = build_formula_tree(batch, target_metric="Adjusted EBITDA")
    tree2 = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert tree1 == tree2
    assert batch == batch_copy


def test_build_formula_tree_provenance_binding() -> None:
    """Verifies 100% of leaf nodes bind to exactly one FormulaInputNode with valid coordinates (AC-5)."""
    nodes = [
        _make_input_node(0, "Operating Income", page=5, source_file="doc_a.pdf"),
        _make_input_node(1, "Restructuring Charges", page=9, source_file="doc_b.pdf"),
    ]
    batch = FormulaInputBatch(
        nodes=nodes,
        total_records_received=2,
        confirmed_count=2,
        excluded_count=0,
    )

    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")

    assert len(tree.leaves) == 2
    for leaf in tree.leaves:
        assert leaf.source_node is not None
        assert leaf.source_node.source_file in ("doc_a.pdf", "doc_b.pdf")
        assert leaf.source_node.page in (5, 9)
        assert "x0" in leaf.source_node.bbox
        assert "y0" in leaf.source_node.bbox
        assert "x1" in leaf.source_node.bbox
        assert "y1" in leaf.source_node.bbox
