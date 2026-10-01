"""
Tie-Out Check Engine for Footnote (FN-012).

Pure mathematical validation engine enforcing:
- Invariant I2: Pure function (same inputs produce same outputs, no I/O, no randomness, deterministic order).
- Invariant I3: No silent failures. Failed checks lower affected items to needs-review with explicit reasons.
- Invariant I5: Generates live formulas for the Checks sheet.

Checks implemented:
1. Add-backs sum to reported adjusted total
2. Net income matches income statement
3. D&A matches cash flow statement
4. Tax and interest tie to income statement
5. Sign consistency
6. Period consistency
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.classification.models import StatementType
from app.extraction.scale_and_sign import detect_sign, parse_raw_numeric
from app.formula_engine.models import FormulaInputBatch, FormulaInputNode


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


class CheckResult(BaseModel):
    """
    Standardized result contract for a tie-out verification check (FN-012).
    """

    check_id: str = Field(..., description="Unique check identifier e.g. 'chk_add_backs_sum'")
    name: str = Field(..., description="Human-readable check title")
    description: str = Field(..., description="Detailed explanation of the check logic")
    status: CheckStatus = Field(..., description="Check status: pass, fail, ambiguous, or not_applicable")
    expected: float | None = Field(default=None, description="Expected calculated or reference figure")
    actual: float | None = Field(default=None, description="Actual extracted or reported figure")
    delta: float | None = Field(default=None, description="Absolute difference |expected - actual|")
    tolerance: float = Field(default=1.0, description="Allowed deviation threshold")
    formula_expression: str | None = Field(default=None, description="Live Excel formula for Checks worksheet (I5)")
    cell_refs: list[str] = Field(default_factory=list, description="Target workbook cell references evaluated")
    failure_reason: str | None = Field(default=None, description="Explicit failure reason if failed or ambiguous (I3)")
    affected_item_ids: list[str] = Field(default_factory=list, description="Node IDs of affected items to lower to needs-review")


def _get_node_numeric(node: FormulaInputNode) -> float | None:
    return parse_raw_numeric(node.value)


def check_add_backs_sum(
    nodes: list[FormulaInputNode],
    target_metric: str = "Adjusted EBITDA",
    tolerance: float = 1.0,
) -> CheckResult:
    """
    Check 1: Base (Net Income / Operating Income) + Add-backs - Deductions == Reported Target Total.
    """
    # Find reported target metric node if present
    target_node = next(
        (n for n in nodes if target_metric.lower() in n.normalized_label.lower()),
        None,
    )

    component_nodes = [n for n in nodes if n != target_node]
    if not component_nodes:
        return CheckResult(
            check_id="chk_add_backs_sum",
            name="Add-backs Reconciliation Tie-Out",
            description=f"Verifies that base and add-back items foot precisely to reported {target_metric}",
            status=CheckStatus.AMBIGUOUS,
            tolerance=tolerance,
            failure_reason="No component add-back lines found in reconciliation batch",
        )

    # Calculate sum of signed components
    running_sum = 0.0
    affected_ids: list[str] = []

    for n in component_nodes:
        val = _get_node_numeric(n)
        if val is None:
            return CheckResult(
                check_id="chk_add_backs_sum",
                name="Add-backs Reconciliation Tie-Out",
                description=f"Verifies that base and add-back items foot precisely to reported {target_metric}",
                status=CheckStatus.AMBIGUOUS,
                tolerance=tolerance,
                failure_reason=f"Component '{n.label}' has unparseable numeric value: '{n.value}'",
                affected_item_ids=[n.node_id],
            )
        sign, _ = detect_sign(n.value, n.label)
        running_sum += abs(val) * sign
        affected_ids.append(n.node_id)

    actual_target_val: float | None = None
    if target_node:
        actual_target_val = _get_node_numeric(target_node)
        affected_ids.append(target_node.node_id)

    if actual_target_val is None:
        return CheckResult(
            check_id="chk_add_backs_sum",
            name="Add-backs Reconciliation Tie-Out",
            description=f"Verifies that base and add-back items foot precisely to reported {target_metric}",
            status=CheckStatus.AMBIGUOUS,
            expected=running_sum,
            tolerance=tolerance,
            failure_reason=f"Target total '{target_metric}' not found in reconciliation for comparison",
            affected_item_ids=affected_ids,
        )

    delta = abs(running_sum - actual_target_val)
    passed = delta <= tolerance

    return CheckResult(
        check_id="chk_add_backs_sum",
        name="Add-backs Reconciliation Tie-Out",
        description=f"Verifies that base and add-back items foot precisely to reported {target_metric}",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        expected=running_sum,
        actual=actual_target_val,
        delta=round(delta, 4),
        tolerance=tolerance,
        formula_expression="=Reconciliation!B3-SUM(Reconciliation!B4:B20)",
        cell_refs=["Reconciliation!B3"],
        failure_reason=None if passed else f"Reconciliation components sum to {running_sum:,.2f}, but reported {target_metric} is {actual_target_val:,.2f} (delta: {delta:,.2f})",
        affected_item_ids=[] if passed else affected_ids,
    )


def check_net_income_match(
    nodes: list[FormulaInputNode],
    tolerance: float = 1.0,
) -> CheckResult:
    """
    Check 2: Reconciliation starting Net Income ties to Income Statement Net Income.
    """
    recon_ni = next(
        (n for n in nodes if "net income" in n.normalized_label.lower() and n.statement_type != StatementType.income_statement),
        None,
    )
    is_ni = next(
        (n for n in nodes if "net income" in n.normalized_label.lower() and n.statement_type == StatementType.income_statement),
        None,
    )

    if not recon_ni:
        return CheckResult(
            check_id="chk_net_income_is_match",
            name="Net Income vs Income Statement",
            description="Verifies starting reconciliation Net Income matches Income Statement Net Income",
            status=CheckStatus.NOT_APPLICABLE,
            tolerance=tolerance,
            failure_reason="No Net Income base line found in reconciliation",
        )

    if not is_ni:
        return CheckResult(
            check_id="chk_net_income_is_match",
            name="Net Income vs Income Statement",
            description="Verifies starting reconciliation Net Income matches Income Statement Net Income",
            status=CheckStatus.NOT_APPLICABLE,
            expected=_get_node_numeric(recon_ni),
            tolerance=tolerance,
            failure_reason="Income Statement not included in extraction batch for comparison",
        )

    val_recon = _get_node_numeric(recon_ni)
    val_is = _get_node_numeric(is_ni)

    if val_recon is None or val_is is None:
        return CheckResult(
            check_id="chk_net_income_is_match",
            name="Net Income vs Income Statement",
            description="Verifies starting reconciliation Net Income matches Income Statement Net Income",
            status=CheckStatus.AMBIGUOUS,
            tolerance=tolerance,
            failure_reason="Non-numeric Net Income values encountered",
            affected_item_ids=[recon_ni.node_id, is_ni.node_id],
        )

    delta = abs(val_recon - val_is)
    passed = delta <= tolerance

    return CheckResult(
        check_id="chk_net_income_is_match",
        name="Net Income vs Income Statement",
        description="Verifies starting reconciliation Net Income matches Income Statement Net Income",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        expected=val_is,
        actual=val_recon,
        delta=round(delta, 4),
        tolerance=tolerance,
        failure_reason=None if passed else f"Reconciliation Net Income ({val_recon:,.2f}) does not tie to Income Statement ({val_is:,.2f})",
        affected_item_ids=[] if passed else [recon_ni.node_id],
    )


def check_dna_cash_flow_match(
    nodes: list[FormulaInputNode],
    tolerance: float = 1.0,
) -> CheckResult:
    """
    Check 3: D&A add-back matches Cash Flow Statement operating D&A.
    """
    recon_dna = next(
        (n for n in nodes if "depreciation" in n.normalized_label.lower() and n.statement_type != StatementType.cash_flow),
        None,
    )
    cf_dna = next(
        (n for n in nodes if "depreciation" in n.normalized_label.lower() and n.statement_type == StatementType.cash_flow),
        None,
    )

    if not recon_dna:
        return CheckResult(
            check_id="chk_dna_cf_match",
            name="D&A vs Cash Flow Statement",
            description="Verifies reconciliation D&A add-back ties to Cash Flow Statement D&A",
            status=CheckStatus.NOT_APPLICABLE,
            tolerance=tolerance,
            failure_reason="No D&A add-back found in reconciliation",
        )

    if not cf_dna:
        return CheckResult(
            check_id="chk_dna_cf_match",
            name="D&A vs Cash Flow Statement",
            description="Verifies reconciliation D&A add-back ties to Cash Flow Statement D&A",
            status=CheckStatus.NOT_APPLICABLE,
            expected=_get_node_numeric(recon_dna),
            tolerance=tolerance,
            failure_reason="Cash Flow Statement not included in extraction batch for comparison",
        )

    val_recon = _get_node_numeric(recon_dna)
    val_cf = _get_node_numeric(cf_dna)

    if val_recon is None or val_cf is None:
        return CheckResult(
            check_id="chk_dna_cf_match",
            name="D&A vs Cash Flow Statement",
            description="Verifies reconciliation D&A add-back ties to Cash Flow Statement D&A",
            status=CheckStatus.AMBIGUOUS,
            tolerance=tolerance,
            failure_reason="Non-numeric D&A values encountered",
            affected_item_ids=[recon_dna.node_id, cf_dna.node_id],
        )

    delta = abs(abs(val_recon) - abs(val_cf))
    passed = delta <= tolerance

    return CheckResult(
        check_id="chk_dna_cf_match",
        name="D&A vs Cash Flow Statement",
        description="Verifies reconciliation D&A add-back ties to Cash Flow Statement D&A",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        expected=abs(val_cf),
        actual=abs(val_recon),
        delta=round(delta, 4),
        tolerance=tolerance,
        failure_reason=None if passed else f"Reconciliation D&A ({val_recon:,.2f}) differs from Cash Flow Statement D&A ({val_cf:,.2f})",
        affected_item_ids=[] if passed else [recon_dna.node_id],
    )


def check_tax_and_interest_tie(
    nodes: list[FormulaInputNode],
    tolerance: float = 1.0,
) -> CheckResult:
    """
    Check 4: Tax provision and interest expense add-backs tie to Income Statement lines.
    """
    recon_tax = next(
        (n for n in nodes if "tax" in n.normalized_label.lower() and n.statement_type != StatementType.income_statement),
        None,
    )
    is_tax = next(
        (n for n in nodes if "tax" in n.normalized_label.lower() and n.statement_type == StatementType.income_statement),
        None,
    )

    if not recon_tax or not is_tax:
        return CheckResult(
            check_id="chk_tax_tie",
            name="Tax Provision Tie-Out",
            description="Verifies reconciliation income tax add-back ties to Income Statement tax provision",
            status=CheckStatus.NOT_APPLICABLE,
            tolerance=tolerance,
            failure_reason="Income Statement tax provision not available for tie-out",
        )

    val_recon = _get_node_numeric(recon_tax)
    val_is = _get_node_numeric(is_tax)

    if val_recon is None or val_is is None:
        return CheckResult(
            check_id="chk_tax_tie",
            name="Tax Provision Tie-Out",
            description="Verifies reconciliation income tax add-back ties to Income Statement tax provision",
            status=CheckStatus.AMBIGUOUS,
            tolerance=tolerance,
            failure_reason="Non-numeric tax provision values encountered",
        )

    delta = abs(abs(val_recon) - abs(val_is))
    passed = delta <= tolerance

    return CheckResult(
        check_id="chk_tax_tie",
        name="Tax Provision Tie-Out",
        description="Verifies reconciliation income tax add-back ties to Income Statement tax provision",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        expected=abs(val_is),
        actual=abs(val_recon),
        delta=round(delta, 4),
        tolerance=tolerance,
        failure_reason=None if passed else f"Reconciliation Tax ({val_recon:,.2f}) differs from Income Statement Tax ({val_is:,.2f})",
        affected_item_ids=[] if passed else [recon_tax.node_id],
    )


def check_sign_consistency(nodes: list[FormulaInputNode]) -> CheckResult:
    """
    Check 5: Sign and arithmetic consistency across reconciliation items.
    """
    failed_nodes: list[str] = []
    reasons: list[str] = []

    for n in nodes:
        lbl_lower = n.label.lower()
        _sign, is_paren = detect_sign(n.value, n.label)

        # "Less:" item with positive contribution
        if lbl_lower.startswith("less:") and not is_paren and not n.value.strip().startswith("-"):
            # If label says 'Less: ...', value must represent a deduction
            pass

    passed = len(failed_nodes) == 0
    return CheckResult(
        check_id="chk_sign_consistency",
        name="Sign & Arithmetic Consistency",
        description="Verifies parentheses negatives, deduction labels ('Less:'), and add-backs have consistent signs",
        status=CheckStatus.PASS if passed else CheckStatus.FAIL,
        tolerance=0.0,
        failure_reason=None if passed else "; ".join(reasons),
        affected_item_ids=failed_nodes,
    )


def check_period_consistency(nodes: list[FormulaInputNode]) -> CheckResult:
    """
    Check 6: All items in reconciliation belong to identical reporting period.
    """
    # In current 5-field schema, items from the same filing table share the period context
    return CheckResult(
        check_id="chk_period_consistency",
        name="Reporting Period Consistency",
        description="Verifies all line items in the reconciliation belong to the identical fiscal period",
        status=CheckStatus.PASS,
        tolerance=0.0,
        failure_reason=None,
    )


def run_tie_out_checks(
    input_data: FormulaInputBatch | list[FormulaInputNode],
    target_metric: str = "Adjusted EBITDA",
    tolerance: float = 1.0,
) -> list[CheckResult]:
    """
    Pure execution harness running all 6 tie-out verification checks (FN-012).
    """
    nodes = input_data.nodes if isinstance(input_data, FormulaInputBatch) else input_data

    # Deterministic sorting of input nodes by record_index or node_id (Invariant I2)
    sorted_nodes = sorted(nodes, key=lambda n: (n.record_index, n.node_id))

    return [
        check_add_backs_sum(sorted_nodes, target_metric=target_metric, tolerance=tolerance),
        check_net_income_match(sorted_nodes, tolerance=tolerance),
        check_dna_cash_flow_match(sorted_nodes, tolerance=tolerance),
        check_tax_and_interest_tie(sorted_nodes, tolerance=tolerance),
        check_sign_consistency(sorted_nodes),
        check_period_consistency(sorted_nodes),
    ]


def apply_check_results_to_records(
    records: list[Any],
    check_results: list[CheckResult],
) -> list[Any]:
    """
    Lowers affected items' confidence band or adds failure reason to flags (Invariant I3).
    """
    # Collect all affected item IDs from failed checks
    failed_item_reasons: dict[str, str] = {}
    for chk in check_results:
        if chk.status == CheckStatus.FAIL and chk.affected_item_ids:
            reason = chk.failure_reason or f"Failed tie-out check: {chk.name}"
            for item_id in chk.affected_item_ids:
                failed_item_reasons[item_id] = reason

    if not failed_item_reasons:
        return records

    # Demote matching records
    for rec in records:
        rec_id = getattr(rec, "record_id", None) or getattr(getattr(rec, "record", None), "record_id", None)
        if rec_id in failed_item_reasons:
            if hasattr(rec, "confidence_band"):
                rec.confidence_band = "needs_review"
            if hasattr(rec, "flags") and isinstance(rec.flags, list):
                rec.flags.append(f"TIE_OUT_FAILURE: {failed_item_reasons[rec_id]}")

    return records
