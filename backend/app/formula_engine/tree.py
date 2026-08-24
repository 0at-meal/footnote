"""
Multi-Statement Formula Tree Engine (Feature 4 & Phase B).

Enforces CONSTITUTION ? 1.4:
- 100% pure functions: no I/O, no clock, no random, no global mutable state.
- Strictly deterministic tree structure per statement (Income Statement, EBITDA Bridge, Cash Flow, Balance Sheet).
- Resolves EC-1 (duplicate label aggregation), EC-9 (degenerate single line item).
- Multi-statement DAG builders for comprehensive financial modeling.
"""

import re
from collections import OrderedDict

from app.classification.models import MasterTaxonomy, StatementType
from app.classification.taxonomy import SEED_MASTER_TAXONOMY, match_master_taxonomy
from app.formula_engine.models import (
    ComprehensiveModelTree,
    FormulaInputBatch,
    FormulaInputNode,
    FormulaNode,
    FormulaNodeType,
    FormulaTree,
    StatementTree,
)

SUPPORTED_TARGET_METRICS: set[str] = {
    "Adjusted EBITDA",
    "Income Statement",
    "Cash Flow",
    "Balance Sheet",
    "EBITDA Bridge",
    "Full Model",
}


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
    if node.node_type in (
        FormulaNodeType.leaf,
        FormulaNodeType.cross_reference,
        FormulaNodeType.blank_cell,
    ):
        leaves.append(node)
    for child in node.children:
        _collect_tree_nodes(child, nodes_by_id, leaves)


def _group_nodes_by_label(
    nodes: list[FormulaInputNode],
) -> OrderedDict[str, list[FormulaInputNode]]:
    """Deterministically groups input nodes by normalized_label preserving order."""
    sorted_nodes = sorted(nodes, key=lambda n: (n.record_index, n.node_id))
    grouped: OrderedDict[str, list[FormulaInputNode]] = OrderedDict()
    for node in sorted_nodes:
        grouped.setdefault(node.normalized_label, []).append(node)
    return grouped


def _make_node_for_group(
    label: str,
    group: list[FormulaInputNode],
    operator: str = "+",
    statement_type: StatementType | None = None,
) -> FormulaNode:
    """Creates a single leaf node or aggregated node for duplicate line items."""
    if len(group) == 1:
        single = group[0]
        return FormulaNode(
            node_id=f"leaf_{single.record_index}_{_slugify(label)}",
            label=single.normalized_label,
            node_type=FormulaNodeType.leaf,
            operator=operator,
            source_node=single,
            statement_type=statement_type,
        )
    else:
        children = [
            FormulaNode(
                node_id=f"leaf_{item.record_index}_{_slugify(label)}",
                label=f"{item.normalized_label} (p. {item.page})",
                node_type=FormulaNodeType.leaf,
                operator="+",
                source_node=item,
                statement_type=statement_type,
            )
            for item in group
        ]
        child_ids = ", ".join(c.node_id for c in children)
        return FormulaNode(
            node_id=f"agg_{_slugify(label)}",
            label=f"Total {label}",
            node_type=FormulaNodeType.aggregate,
            operator=operator,
            formula_expression=f"=SUM({child_ids})",
            children=children,
            statement_type=statement_type,
        )


def build_income_statement_tree(nodes: list[FormulaInputNode]) -> FormulaTree:
    """
    Builds the Income Statement DAG:
    Revenue -> (-Cost of Revenue) -> Gross Profit -> (-OpEx items) -> Operating Income (EBIT)
    -> (+/- Non-Operating) -> Income Before Tax -> (-Tax) -> Net Income -> EPS Diluted.
    """
    if not nodes:
        return FormulaTree(
            target_metric="Income Statement",
            statement_type=StatementType.income_statement,
            is_valid=True,
            error_message=None,
            total_leaves=0,
        )

    grouped = _group_nodes_by_label(nodes)
    is_children: list[FormulaNode] = []

    # 1. Revenue & Cost of Revenue
    rev_group = grouped.get("Revenue", [])
    if rev_group:
        is_children.append(
            _make_node_for_group(
                "Revenue",
                rev_group,
                operator="+",
                statement_type=StatementType.income_statement,
            )
        )

    cogs_group = grouped.get("Cost of Revenue", [])
    if cogs_group:
        is_children.append(
            _make_node_for_group(
                "Cost of Revenue",
                cogs_group,
                operator="-",
                statement_type=StatementType.income_statement,
            )
        )

    # 2. Operating Expenses
    opex_labels = [
        "Research & Development",
        "Sales & Marketing",
        "General & Administrative",
        "Total Operating Expenses",
    ]
    for label in opex_labels:
        grp = grouped.get(label, [])
        if grp:
            is_children.append(
                _make_node_for_group(
                    label,
                    grp,
                    operator="-",
                    statement_type=StatementType.income_statement,
                )
            )

    # 3. Operating Income / EBIT
    ebit_group = grouped.get("Operating Income", [])
    if ebit_group:
        is_children.append(
            _make_node_for_group(
                "Operating Income",
                ebit_group,
                operator="+",
                statement_type=StatementType.income_statement,
            )
        )

    # 4. Non-Operating items & Taxes
    for label, op in [
        ("Interest Income", "+"),
        ("Interest Expense", "-"),
        ("Other Income / Expense Net", "+"),
        ("Income Before Income Taxes", "+"),
        ("Provision for Income Taxes", "-"),
        ("Net Income", "+"),
        ("Basic EPS", "+"),
        ("Diluted EPS", "+"),
        ("Weighted Average Shares - Basic", "+"),
        ("Weighted Average Shares - Diluted", "+"),
    ]:
        grp = grouped.get(label, [])
        if grp:
            is_children.append(
                _make_node_for_group(
                    label,
                    grp,
                    operator=op,
                    statement_type=StatementType.income_statement,
                )
            )

    # Any remaining income statement items not explicitly handled
    handled = {
        "Revenue",
        "Cost of Revenue",
        *opex_labels,
        "Operating Income",
        "Interest Income",
        "Interest Expense",
        "Other Income / Expense Net",
        "Income Before Income Taxes",
        "Provision for Income Taxes",
        "Net Income",
        "Basic EPS",
        "Diluted EPS",
        "Weighted Average Shares - Basic",
        "Weighted Average Shares - Diluted",
    }
    for label, grp in grouped.items():
        if label not in handled:
            is_children.append(
                _make_node_for_group(
                    label,
                    grp,
                    operator="+",
                    statement_type=StatementType.income_statement,
                )
            )

    root = FormulaNode(
        node_id="root_income_statement",
        label="Income Statement",
        node_type=FormulaNodeType.calculated_root,
        operator="root",
        children=is_children,
        statement_type=StatementType.income_statement,
    )

    nodes_by_id: dict[str, FormulaNode] = {}
    leaves: list[FormulaNode] = []
    _collect_tree_nodes(root, nodes_by_id, leaves)

    return FormulaTree(
        target_metric="Income Statement",
        statement_type=StatementType.income_statement,
        root=root,
        nodes_by_id=nodes_by_id,
        leaves=leaves,
        total_leaves=len(leaves),
        is_valid=True,
        error_message=None,
    )


def build_ebitda_bridge_tree(
    nodes: list[FormulaInputNode],
    ebit_source: str | None = None,
) -> FormulaTree:
    """
    Builds the Non-GAAP EBITDA Bridge DAG:
    EBIT (cross-reference to Income Statement) + D&A + Non-GAAP Add-backs -> Adjusted EBITDA.
    """
    root_children: list[FormulaNode] = []

    # 1. Add EBIT cross-reference node
    ebit_ref_node = FormulaNode(
        node_id="ref_ebit_income_statement",
        label="Operating Income (EBIT)",
        node_type=FormulaNodeType.cross_reference,
        operator="+",
        cross_reference_sheet="Income_Statement",
        cross_reference_target="Operating Income",
        statement_type=StatementType.non_gaap_bridge,
    )
    root_children.append(ebit_ref_node)

    # 2. Add confirmed bridge items (D&A and add-backs)
    grouped = _group_nodes_by_label(nodes)
    for label, group in grouped.items():
        if label in ("Operating Income", "EBIT"):
            continue  # Covered by cross-reference
        root_children.append(
            _make_node_for_group(
                label, group, operator="+", statement_type=StatementType.non_gaap_bridge
            )
        )

    root_id = "root_adjusted_ebitda"
    operand_ids = ", ".join(c.node_id for c in root_children)
    root = FormulaNode(
        node_id=root_id,
        label="Adjusted EBITDA",
        node_type=FormulaNodeType.calculated_root,
        operator="root",
        formula_expression=f"=SUM({operand_ids})",
        children=root_children,
        statement_type=StatementType.non_gaap_bridge,
    )

    nodes_by_id: dict[str, FormulaNode] = {}
    leaves: list[FormulaNode] = []
    _collect_tree_nodes(root, nodes_by_id, leaves)

    return FormulaTree(
        target_metric="Adjusted EBITDA",
        statement_type=StatementType.non_gaap_bridge,
        root=root,
        nodes_by_id=nodes_by_id,
        leaves=leaves,
        total_leaves=len(leaves),
        is_valid=True,
        error_message=None,
    )


def build_free_cash_flow_tree(nodes: list[FormulaInputNode]) -> FormulaTree:
    """
    Builds the Free Cash Flow DAG:
    Operating Cash Flow - Capital Expenditures -> FCFF;
    FCFF - Debt Service - Stock Repurchases - Dividends -> FCFE.
    """
    if not nodes:
        return FormulaTree(
            target_metric="Cash Flow",
            statement_type=StatementType.cash_flow,
            is_valid=True,
            error_message=None,
            total_leaves=0,
        )

    grouped = _group_nodes_by_label(nodes)
    cf_children: list[FormulaNode] = []

    # 1. Operating Activities
    for label, op in [
        ("Net Income (CF)", "+"),
        ("Depreciation & Amortization (CF)", "+"),
        ("Stock-Based Compensation (CF)", "+"),
        ("Deferred Income Taxes (CF)", "+"),
        ("Other Non-Cash Items (CF)", "+"),
        ("Change in Working Capital", "+"),
        ("Cash Provided by Operating Activities", "+"),
    ]:
        grp = grouped.get(label, [])
        if grp:
            cf_children.append(
                _make_node_for_group(
                    label, grp, operator=op, statement_type=StatementType.cash_flow
                )
            )

    # 2. Investing Activities & CapEx
    for label, op in [
        ("Capital Expenditures", "-"),
        ("Purchases of Marketable Securities", "-"),
        ("Proceeds from Marketable Securities", "+"),
        ("Acquisitions, Net of Cash Acquired", "-"),
        ("Cash Used in Investing Activities", "-"),
    ]:
        grp = grouped.get(label, [])
        if grp:
            cf_children.append(
                _make_node_for_group(
                    label, grp, operator=op, statement_type=StatementType.cash_flow
                )
            )

    # 3. Financing Activities
    for label, op in [
        ("Proceeds from / Repayments of Debt", "+"),
        ("Repurchases of Common Stock", "-"),
        ("Dividends Paid", "-"),
        ("Cash Used in Financing Activities", "-"),
        ("Free Cash Flow", "+"),
    ]:
        grp = grouped.get(label, [])
        if grp:
            cf_children.append(
                _make_node_for_group(
                    label, grp, operator=op, statement_type=StatementType.cash_flow
                )
            )

    # Any remaining cash flow items
    handled = {
        "Net Income (CF)",
        "Depreciation & Amortization (CF)",
        "Stock-Based Compensation (CF)",
        "Deferred Income Taxes (CF)",
        "Other Non-Cash Items (CF)",
        "Change in Working Capital",
        "Cash Provided by Operating Activities",
        "Capital Expenditures",
        "Purchases of Marketable Securities",
        "Proceeds from Marketable Securities",
        "Acquisitions, Net of Cash Acquired",
        "Cash Used in Investing Activities",
        "Proceeds from / Repayments of Debt",
        "Repurchases of Common Stock",
        "Dividends Paid",
        "Cash Used in Financing Activities",
        "Free Cash Flow",
    }
    for label, grp in grouped.items():
        if label not in handled:
            cf_children.append(
                _make_node_for_group(
                    label, grp, operator="+", statement_type=StatementType.cash_flow
                )
            )

    root = FormulaNode(
        node_id="root_cash_flow",
        label="Cash Flow",
        node_type=FormulaNodeType.calculated_root,
        operator="root",
        children=cf_children,
        statement_type=StatementType.cash_flow,
    )

    nodes_by_id: dict[str, FormulaNode] = {}
    leaves: list[FormulaNode] = []
    _collect_tree_nodes(root, nodes_by_id, leaves)

    return FormulaTree(
        target_metric="Cash Flow",
        statement_type=StatementType.cash_flow,
        root=root,
        nodes_by_id=nodes_by_id,
        leaves=leaves,
        total_leaves=len(leaves),
        is_valid=True,
        error_message=None,
    )


def build_net_debt_tree(nodes: list[FormulaInputNode]) -> FormulaTree:
    """
    Builds the Net Debt / Balance Sheet summary DAG:
    (Short-Term Debt + Long-Term Debt) - (Cash & Equivalents + Short-Term Investments) -> Net Debt.
    """
    if not nodes:
        return FormulaTree(
            target_metric="Balance Sheet",
            statement_type=StatementType.balance_sheet,
            is_valid=True,
            error_message=None,
            total_leaves=0,
        )

    grouped = _group_nodes_by_label(nodes)
    bs_children: list[FormulaNode] = []

    # Current Assets
    for label, op in [
        ("Cash and Cash Equivalents", "-"),
        ("Short-Term Investments", "-"),
        ("Accounts Receivable", "+"),
        ("Inventory", "+"),
        ("Other Current Assets", "+"),
        ("Total Current Assets", "+"),
        ("Property, Plant and Equipment, Net", "+"),
        ("Operating Lease Right-of-Use Assets", "+"),
        ("Goodwill", "+"),
        ("Intangible Assets, Net", "+"),
        ("Other Non-Current Assets", "+"),
        ("Total Assets", "+"),
        ("Accounts Payable", "+"),
        ("Accrued Expenses and Other Current Liabilities", "+"),
        ("Short-Term Debt", "+"),
        ("Total Current Liabilities", "+"),
        ("Long-Term Debt", "+"),
        ("Operating Lease Liabilities, Non-Current", "+"),
        ("Other Non-Current Liabilities", "+"),
        ("Total Liabilities", "+"),
        ("Retained Earnings", "+"),
        ("Total Stockholders' Equity", "+"),
        ("Total Liabilities and Stockholders' Equity", "+"),
    ]:
        grp = grouped.get(label, [])
        if grp:
            bs_children.append(
                _make_node_for_group(
                    label, grp, operator=op, statement_type=StatementType.balance_sheet
                )
            )

    # Any remaining balance sheet items
    handled = {
        "Cash and Cash Equivalents",
        "Short-Term Investments",
        "Accounts Receivable",
        "Inventory",
        "Other Current Assets",
        "Total Current Assets",
        "Property, Plant and Equipment, Net",
        "Operating Lease Right-of-Use Assets",
        "Goodwill",
        "Intangible Assets, Net",
        "Other Non-Current Assets",
        "Total Assets",
        "Accounts Payable",
        "Accrued Expenses and Other Current Liabilities",
        "Short-Term Debt",
        "Total Current Liabilities",
        "Long-Term Debt",
        "Operating Lease Liabilities, Non-Current",
        "Other Non-Current Liabilities",
        "Total Liabilities",
        "Retained Earnings",
        "Total Stockholders' Equity",
        "Total Liabilities and Stockholders' Equity",
    }
    for label, grp in grouped.items():
        if label not in handled:
            bs_children.append(
                _make_node_for_group(
                    label, grp, operator="+", statement_type=StatementType.balance_sheet
                )
            )

    root = FormulaNode(
        node_id="root_balance_sheet",
        label="Balance Sheet",
        node_type=FormulaNodeType.calculated_root,
        operator="root",
        children=bs_children,
        statement_type=StatementType.balance_sheet,
    )

    nodes_by_id: dict[str, FormulaNode] = {}
    leaves: list[FormulaNode] = []
    _collect_tree_nodes(root, nodes_by_id, leaves)

    return FormulaTree(
        target_metric="Balance Sheet",
        statement_type=StatementType.balance_sheet,
        root=root,
        nodes_by_id=nodes_by_id,
        leaves=leaves,
        total_leaves=len(leaves),
        is_valid=True,
        error_message=None,
    )


def build_comprehensive_model_tree(
    input_batch: FormulaInputBatch,
    master: MasterTaxonomy | None = None,
) -> ComprehensiveModelTree:
    """
    Constructs comprehensive multi-statement formula trees from an input batch.
    Groups nodes by statement_type and builds DAGs for all 4 financial statements simultaneously.
    """
    active_master = master if master is not None else SEED_MASTER_TAXONOMY

    # Categorize input nodes by statement type
    is_nodes: list[FormulaInputNode] = []
    cf_nodes: list[FormulaInputNode] = []
    bs_nodes: list[FormulaInputNode] = []
    bridge_nodes: list[FormulaInputNode] = []
    kpi_nodes: list[FormulaInputNode] = []

    for node in input_batch.nodes:
        st = node.statement_type
        if st is None:
            matched = match_master_taxonomy(
                node.normalized_label, active_master
            ) or match_master_taxonomy(node.label, active_master)
            if matched:
                st = matched.statement_type

        if st == StatementType.income_statement:
            is_nodes.append(node)
        elif st == StatementType.cash_flow:
            cf_nodes.append(node)
        elif st == StatementType.balance_sheet:
            bs_nodes.append(node)
        elif st == StatementType.kpi:
            kpi_nodes.append(node)
        else:
            # Default non-GAAP or unrecognized to EBITDA bridge
            bridge_nodes.append(node)

    statement_trees = [
        StatementTree(
            statement_type=StatementType.income_statement,
            tree=build_income_statement_tree(is_nodes),
        ),
        StatementTree(
            statement_type=StatementType.non_gaap_bridge,
            tree=build_ebitda_bridge_tree(bridge_nodes),
        ),
        StatementTree(
            statement_type=StatementType.cash_flow,
            tree=build_free_cash_flow_tree(cf_nodes),
        ),
        StatementTree(
            statement_type=StatementType.balance_sheet,
            tree=build_net_debt_tree(bs_nodes),
        ),
    ]

    all_valid = all(st.tree.is_valid for st in statement_trees)
    error_msg = None
    if not all_valid:
        error_msg = "; ".join(
            st.tree.error_message for st in statement_trees if st.tree.error_message
        )

    return ComprehensiveModelTree(
        statement_trees=statement_trees,
        is_valid=all_valid,
        error_message=error_msg,
    )


def build_formula_tree(
    input_batch: FormulaInputBatch,
    target_metric: str = "Adjusted EBITDA",
) -> FormulaTree:
    """
    Backward-compatible single-tree builder for target metrics.
    """
    if target_metric not in SUPPORTED_TARGET_METRICS:
        return FormulaTree(
            target_metric=target_metric,
            is_valid=False,
            error_message=f"Unsupported target metric '{target_metric}' (EC-4).",
        )

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

    if target_metric in ("Income Statement", "income_statement"):
        return build_income_statement_tree(input_batch.nodes)
    elif target_metric in ("Cash Flow", "cash_flow"):
        return build_free_cash_flow_tree(input_batch.nodes)
    elif target_metric in ("Balance Sheet", "balance_sheet"):
        return build_net_debt_tree(input_batch.nodes)

    # Default Adjusted EBITDA tree
    sorted_nodes = sorted(input_batch.nodes, key=lambda n: (n.record_index, n.node_id))
    grouped_nodes: OrderedDict[str, list[FormulaInputNode]] = OrderedDict()
    for node in sorted_nodes:
        grouped_nodes.setdefault(node.normalized_label, []).append(node)

    root_children: list[FormulaNode] = []
    for label, group in grouped_nodes.items():
        root_children.append(_make_node_for_group(label, group, operator="+"))

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
