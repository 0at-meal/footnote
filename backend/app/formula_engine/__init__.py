"""
Formula Engine Package (Feature 4).

Pure, deterministic formula graph construction and validation (CONSTITUTION ? 1.4).
"""

from app.formula_engine.models import (
    ComprehensiveModelTree,
    FormulaInputBatch,
    FormulaInputError,
    FormulaInputNode,
    FormulaNode,
    FormulaNodeType,
    FormulaTree,
    StatementTree,
)
from app.formula_engine.reader import (
    read_formula_inputs,
    read_formula_inputs_from_review,
)
from app.formula_engine.tree import (
    build_comprehensive_model_tree,
    build_ebitda_bridge_tree,
    build_formula_tree,
    build_free_cash_flow_tree,
    build_income_statement_tree,
    build_net_debt_tree,
)

__all__ = [
    "ComprehensiveModelTree",
    "FormulaInputBatch",
    "FormulaInputError",
    "FormulaInputNode",
    "FormulaNode",
    "FormulaNodeType",
    "FormulaTree",
    "StatementTree",
    "build_comprehensive_model_tree",
    "build_ebitda_bridge_tree",
    "build_formula_tree",
    "build_free_cash_flow_tree",
    "build_income_statement_tree",
    "build_net_debt_tree",
    "read_formula_inputs",
    "read_formula_inputs_from_review",
]
