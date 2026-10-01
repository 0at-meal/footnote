"""
Unit and integration tests for CI Regression Gates and Eval Runner (FN-011).
"""

from pathlib import Path

from app.classification.models import ClassifierInputPayload

from eval.metrics import compute_eval_gate_metrics, evaluate_gates
from eval.models import (
    EvalGateMetrics,
    FailurePattern,
    ItemMatchStatus,
    LineItemDiff,
)
from eval.record_replay import RecordReplayClassifierClient


def test_record_replay_classifier_offline_mode() -> None:
    """FN-011: RecordReplay client executes deterministically without live network calls."""
    client = RecordReplayClassifierClient(mode="replay")
    payload = ClassifierInputPayload(label="Stock-based compensation expense")
    res = client.classify(payload)

    assert res.label == "Stock-based compensation"
    assert res.confidence >= 0.90


def test_compute_eval_gate_metrics_accurate_split() -> None:
    """FN-011: Computes auto-accepted vs flagged separation and calibration buckets."""
    diffs = [
        LineItemDiff(
            ground_truth_label="Net income",
            extracted_label="Net income",
            ground_truth_value="50,000",
            extracted_value="50,000",
            status=ItemMatchStatus.exact_match,
            iou=0.9,
            ground_truth_normalized_label="Net Income",
            extracted_normalized_label="Net Income",
        ),
        LineItemDiff(
            ground_truth_label="Taxes",
            extracted_label="Taxes",
            ground_truth_value="10,000",
            extracted_value="10,000",
            status=ItemMatchStatus.exact_match,
            iou=0.85,
            ground_truth_normalized_label="Income Tax Expense",
            extracted_normalized_label="Income Tax Expense",
        ),
        LineItemDiff(
            ground_truth_label="Restructuring",
            extracted_label="Restructuring",
            ground_truth_value="5,000",
            extracted_value="4,500",
            status=ItemMatchStatus.value_mismatch,
            failure_pattern=FailurePattern.multi_column_bleed,
            ground_truth_normalized_label="Restructuring Charges",
            extracted_normalized_label="Restructuring Charges",
        ),
    ]

    metrics = compute_eval_gate_metrics(diffs)
    assert metrics.auto_accepted_count == 2
    assert metrics.flagged_count == 1
    assert metrics.auto_accepted_exact_match_rate == 1.0
    assert metrics.sign_accuracy == 1.0
    assert metrics.scale_accuracy == 1.0
    assert len(metrics.calibration) == 4
    assert metrics.calibration[0].bucket_name == "0.9-1.0"
    assert metrics.calibration[0].accuracy == 1.0


def test_evaluate_gates_success(tmp_path: Path) -> None:
    """FN-011: Evaluates passing metrics against gates configuration."""
    gates_file = tmp_path / "gates.yaml"
    gates_file.write_text(
        """
gates:
  min_auto_accepted_exact_match: 0.95
  min_recall: 0.90
  min_precision: 0.85
  min_sign_accuracy: 0.95
  min_scale_accuracy: 0.95
  min_total_tie_out_rate: 0.90
tolerance: 0.02
cost_budget_per_filing_usd: 0.05
latency_budget_per_filing_seconds: 30.0
""",
        encoding="utf-8",
    )

    passing_metrics = EvalGateMetrics(
        line_item_recall=0.96,
        line_item_precision=0.92,
        value_exact_match_rate=0.95,
        auto_accepted_exact_match_rate=0.98,
        sign_accuracy=0.99,
        scale_accuracy=0.99,
        total_tie_out_rate=0.95,
        category_accuracy=0.90,
        locator_accuracy=0.88,
        estimated_cost_usd=0.01,
        mean_latency_seconds=5.2,
    )

    result = evaluate_gates(passing_metrics, gates_path=gates_file)
    assert result.passed is True
    assert len(result.failures) == 0


def test_evaluate_gates_regression_failure(tmp_path: Path) -> None:
    """FN-011: Fails PR / CI when metrics regress beyond tolerance threshold."""
    gates_file = tmp_path / "gates.yaml"
    gates_file.write_text(
        """
gates:
  min_auto_accepted_exact_match: 0.98
  min_recall: 0.90
tolerance: 0.01
cost_budget_per_filing_usd: 0.05
latency_budget_per_filing_seconds: 30.0
""",
        encoding="utf-8",
    )

    # Degraded metrics: recall 80% (well below 90% floor)
    regressed_metrics = EvalGateMetrics(
        line_item_recall=0.80,
        line_item_precision=0.85,
        auto_accepted_exact_match_rate=0.92,
        estimated_cost_usd=0.01,
        mean_latency_seconds=5.0,
    )

    result = evaluate_gates(regressed_metrics, gates_path=gates_file)
    assert result.passed is False
    assert any("min_recall" in f for f in result.failures)
    assert any("min_auto_accepted_exact_match" in f for f in result.failures)


def test_ci_fails_on_deliberately_broken_extractor(tmp_path: Path) -> None:
    """
    FN-011 Acceptance Criterion:
    CI runner detects deliberately broken extractor and triggers regression gate failure.
    """
    gates_file = tmp_path / "gates.yaml"
    gates_file.write_text(
        """
gates:
  min_auto_accepted_exact_match: 0.98
  min_recall: 0.90
tolerance: 0.02
""",
        encoding="utf-8",
    )

    # Simulate deliberately broken extractor output: all missed items or wrong amounts
    broken_diffs = [
        LineItemDiff(
            ground_truth_label=f"Item {i}",
            extracted_label=None,
            ground_truth_value="1000",
            extracted_value=None,
            status=ItemMatchStatus.missed_item,
            failure_pattern=FailurePattern.missing_item,
        )
        for i in range(10)
    ]

    broken_metrics = compute_eval_gate_metrics(broken_diffs)
    assert broken_metrics.line_item_recall == 0.0

    result = evaluate_gates(broken_metrics, gates_path=gates_file)
    assert result.passed is False
    assert any("min_recall" in f for f in result.failures)
