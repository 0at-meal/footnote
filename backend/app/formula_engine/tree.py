"""
Pure formula tree builder (Feature 4 Step 2).

Enforces CONSTITUTION §1.4:
- 100% pure function: no I/O, no clock, no random, no global mutable state.
- Strictly deterministic tree structure per target metric (Adjusted EBITDA).
- Resolves EC-1 (duplicate label aggregation), EC-4 (unsupported metric), EC-9 (degenerate single line item).
"""

import re
from collections import OrderedDict

from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputNode,
    FormulaNode,
    FormulaNodeType,
    FormulaTree,
)

SUPPORTED_TARGET_METRICS: set[str] = {"Adjusted EBITDA"}


def _slugify(text: str) -> str:
    """Creates a deterministic slug identifier from label text."""
    clean = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", clean)


def _collect_tree_nodes(
    node: FormulaNode,
    nodes_by_id: dict[str, FormulaNode],
    leaves: list[FormulaNode],
) -> None:
    """Recursively indexes all nodes by ID and collects all leaf nodes in tree traversal order."""
    nodes_by_id[node.node_id] = node
    if node.node_type == FormulaNodeType.leaf:
        leaves.append(node)
    for child in node.children:
        _collect_tree_nodes(child, nodes_by_id, leaves)


def build_formula_tree(
    input_batch: FormulaInputBatch,
    target_metric: str = "Adjusted EBITDA",
) -> FormulaTree:
    """
    Constructs a deterministic formula tree for the target metric from confirmed input nodes.

    Rules & Acceptance Criteria:
    - Pure function: identical input produces identical tree structure (AC-4, NFR1, CONSTITUTION §1.4).
    - Target metric validation: Phase 2 supports 'Adjusted EBITDA' (EC-4).
    - Zero confirmed records: surfaces explicit error (EC-5).
    - Duplicate normalized labels: aggregated under an intermediate aggregate node (EC-1).
    - Single item: valid degenerate formula tree (EC-9).
    - 100% of leaf nodes bind directly to their source FormulaInputNode (AC-5).
    """
    # 1. Validate target metric (EC-4)
    if target_metric not in SUPPORTED_TARGET_METRICS:
        return FormulaTree(
            target_metric=target_metric,
            is_valid=False,
            error_message=f"Unsupported target metric '{target_metric}'. Only 'Adjusted EBITDA' is supported in Phase 2 (EC-4).",
        )

    # 2. Validate input batch error or empty condition (EC-5)
    if input_batch.error_message:
        return FormulaTree(
            target_metric=target_metric,
            is_valid=False,
            error_message=input_batch.error_message,
        )

    if not input_batch.nodes:
        return FormulaTree(
            target_metric=target_metric,
            is_valid=False,
            error_message="No confirmed records available for formula generation.",
        )

    # 3. Deterministic sorting and grouping by normalized_label (NFR1, EC-1)
    sorted_nodes = sorted(input_batch.nodes, key=lambda n: (n.record_index, n.node_id))

    grouped_nodes: OrderedDict[str, list[FormulaInputNode]] = OrderedDict()
    for node in sorted_nodes:
        grouped_nodes.setdefault(node.normalized_label, []).append(node)

    root_children: list[FormulaNode] = []

    for label, group in grouped_nodes.items():
        if len(group) == 1:
            # Single occurrence: direct leaf node under root
            single_node = group[0]
            leaf_id = f"leaf_{single_node.record_index}_{_slugify(label)}"
            leaf_node = FormulaNode(
                node_id=leaf_id,
                label=single_node.normalized_label,
                node_type=FormulaNodeType.leaf,
                operator="+",
                source_node=single_node,
            )
            root_children.append(leaf_node)
        else:
            # Multiple occurrences of same label (EC-1): create distinct leaf nodes and aggregate
            leaf_children: list[FormulaNode] = []
            for item in group:
                leaf_id = f"leaf_{item.record_index}_{_slugify(label)}"
                leaf_node = FormulaNode(
                    node_id=leaf_id,
                    label=f"{item.normalized_label} (p. {item.page})",
                    node_type=FormulaNodeType.leaf,
                    operator="+",
                    source_node=item,
                )
                leaf_children.append(leaf_node)

            agg_id = f"agg_{_slugify(label)}"
            leaf_ids_expr = ", ".join(c.node_id for c in leaf_children)
            agg_node = FormulaNode(
                node_id=agg_id,
                label=f"Total {label}",
                node_type=FormulaNodeType.aggregate,
                operator="+",
                formula_expression=f"=SUM({leaf_ids_expr})",
                children=leaf_children,
            )
            root_children.append(agg_node)

    # 4. Construct calculated root node
    root_id = f"root_{_slugify(target_metric)}"
    operand_ids_expr = ", ".join(c.node_id for c in root_children)
    root_node = FormulaNode(
        node_id=root_id,
        label=target_metric,
        node_type=FormulaNodeType.calculated_root,
        operator="root",
        formula_expression=f"=SUM({operand_ids_expr})",
        children=root_children,
    )

    # 5. Index all nodes and flatten leaves
    nodes_by_id: dict[str, FormulaNode] = {}
    leaves: list[FormulaNode] = []
    _collect_tree_nodes(root_node, nodes_by_id, leaves)

    return FormulaTree(
        target_metric=target_metric,
        root=root_node,
        nodes_by_id=nodes_by_id,
        leaves=leaves,
        total_leaves=len(leaves),
        is_valid=True,
        error_message=None,
    )
