"""
Unit and integration tests for Evaluation Report Generator (eval/report_generator.py).

Enforces:
- CONSTITUTION §6.13: Mandatory governance disclosures embedded in Markdown, JSON, and Terminal outputs.
- AC-3: Extraction accuracy percentage reporting.
- AC-4: Three-layer architectural error breakdown isolation.
- AC-5 / EC-3: Failed extraction threshold callout rendering.
- AC-7: Failure pattern categorization reporting.
"""

import json
from pathlib import Path

from eval.models import (
    CorpusAccuracyMetrics,
    FailurePattern,
    FilingAccuracyMetrics,
    ItemMatchStatus,
    LayerMetricsSummary,
    LineItemDiff,
    StageRuntimes,
)
from eval.report_generator import (
    generate_json_report,
    generate_markdown_report,
    generate_terminal_summary,
    save_reports,
)


def _create_mock_corpus_metrics() -> CorpusAccuracyMetrics:
    """Helper to generate mock CorpusAccuracyMetrics with realistic filing metrics."""
    filing1 = FilingAccuracyMetrics(
        filing_id="acme_2023_10k",
        company_name="Acme Corporation",
        total_ground_truth_items=5,
        extracted_items_count=5,
        true_positives=5,
        false_positives=0,
        false_negatives=0,
        precision=1.0,
        recall=1.0,
        f1_score=1.0,
        line_item_accuracy_percentage=100.0,
        target_accuracy_achieved=True,
        failed_extraction=False,
        non_auto_accepted_count=0,
        non_auto_accepted_percentage=0.0,
        layer_errors=LayerMetricsSummary(
            extraction_errors=0, classification_errors=0, generation_errors=0
        ),
        failure_patterns=[FailurePattern.none],
        line_item_diffs=[
            LineItemDiff(
                ground_truth_label="Net income",
                ground_truth_normalized_label="Net Income",
                ground_truth_value="50000",
                extracted_label="Net income",
                extracted_normalized_label="Net Income",
                extracted_value="50,000",
                page=1,
                iou=0.92,
                status=ItemMatchStatus.exact_match,
                failure_pattern=FailurePattern.none,
                is_optional=False,
            )
        ],
        runtimes=StageRuntimes(total_time_seconds=12.5),
        nfr3_compliant=True,
    )

    filing2 = FilingAccuracyMetrics(
        filing_id="beta_2023_10k",
        company_name="Beta Technologies",
        total_ground_truth_items=5,
        extracted_items_count=4,
        true_positives=3,
        false_positives=1,
        false_negatives=2,
        precision=0.75,
        recall=0.60,
        f1_score=0.6667,
        line_item_accuracy_percentage=60.0,
        target_accuracy_achieved=False,
        failed_extraction=True,
        non_auto_accepted_count=2,
        non_auto_accepted_percentage=50.0,
        layer_errors=LayerMetricsSummary(
            extraction_errors=2, classification_errors=1, generation_errors=0
        ),
        failure_patterns=[
            FailurePattern.sign_mismatch,
            FailurePattern.multi_column_bleed,
        ],
        line_item_diffs=[
            LineItemDiff(
                ground_truth_label="Stock-based compensation",
                ground_truth_normalized_label="Stock-Based Compensation",
                ground_truth_value="4200",
                extracted_label="Stock-based comp",
                extracted_normalized_label="Stock-Based Compensation",
                extracted_value="-4200",
                page=2,
                iou=0.85,
                status=ItemMatchStatus.value_mismatch,
                failure_pattern=FailurePattern.sign_mismatch,
                is_optional=False,
            )
        ],
        runtimes=StageRuntimes(total_time_seconds=18.0),
        nfr3_compliant=True,
    )

    return CorpusAccuracyMetrics(
        corpus_name="Test Corpus",
        total_filings=2,
        successful_filings=1,
        failed_extraction_filings_count=1,
        total_ground_truth_items=10,
        total_extracted_items=9,
        total_true_positives=8,
        total_false_positives=1,
        total_false_negatives=2,
        macro_precision=0.875,
        macro_recall=0.80,
        macro_f1_score=0.8333,
        micro_precision=0.8889,
        micro_recall=0.80,
        micro_f1_score=0.8421,
        corpus_line_item_accuracy_percentage=80.0,
        target_accuracy_achieved=False,
        layer_errors=LayerMetricsSummary(
            extraction_errors=2, classification_errors=1, generation_errors=0
        ),
        failure_pattern_counts={
            FailurePattern.sign_mismatch.value: 1,
            FailurePattern.multi_column_bleed.value: 1,
        },
        filing_metrics=[filing1, filing2],
        benchmark_corpus_size=2,
        total_manual_review_items=2,
        manual_review_percentage=22.22,
        mandatory_governance_disclosure=(
            "Evaluation conducted on benchmark corpus of 2 filings (10 total ground-truth items). "
            "2 items (22.22%) required human review or manual correction."
        ),
    )


def test_generate_json_report_valid_and_deserializable() -> None:
    """Verifies that JSON output is valid and can be deserialized back into CorpusAccuracyMetrics."""
    metrics = _create_mock_corpus_metrics()
    json_str = generate_json_report(metrics)

    parsed = json.loads(json_str)
    assert parsed["corpus_name"] == "Test Corpus"
    assert parsed["total_filings"] == 2
    assert parsed["corpus_line_item_accuracy_percentage"] == 80.0
    assert (
        "Evaluation conducted on benchmark corpus of 2 filings"
        in parsed["mandatory_governance_disclosure"]
    )

    roundtrip = CorpusAccuracyMetrics.model_validate_json(json_str)
    assert roundtrip.corpus_name == metrics.corpus_name
    assert roundtrip.benchmark_corpus_size == metrics.benchmark_corpus_size
    assert roundtrip.layer_errors.extraction_errors == 2


def test_generate_markdown_report_mandatory_disclosure() -> None:
    """AC-6, CONSTITUTION §6.13: Verifies presence of governance disclosure callout."""
    metrics = _create_mock_corpus_metrics()
    md = generate_markdown_report(metrics)

    assert "# Evaluation Report: Test Corpus" in md
    assert "> [!IMPORTANT]" in md
    assert "Governance & Transparency Disclosure (CONSTITUTION §6.13)" in md
    assert "Evaluation conducted on benchmark corpus of 2 filings" in md


def test_generate_markdown_report_three_layer_error_isolation() -> None:
    """AC-4: Verifies separate three-layer error categorization."""
    metrics = _create_mock_corpus_metrics()
    md = generate_markdown_report(metrics)

    assert "## 2. Three-Layer Error Isolation (AC-4)" in md
    assert "| **Extraction Layer** | 2 |" in md
    assert "| **Classification Layer** | 1 |" in md
    assert "| **Generation Layer** | 0 |" in md


def test_generate_markdown_report_failed_extraction_callout() -> None:
    """AC-5, EC-3: Verifies explicit failed extraction threshold section."""
    metrics = _create_mock_corpus_metrics()
    md = generate_markdown_report(metrics)

    assert "## 3. Failed Extraction Threshold Enforcement (AC-5, EC-3)" in md
    assert "1 filing(s)" in md
    assert "`beta_2023_10k`" in md
    assert "50.0%" in md
    assert "❌ Failed Extraction" in md


def test_generate_markdown_report_failure_patterns_table() -> None:
    """AC-7: Verifies structural failure patterns breakdown table."""
    metrics = _create_mock_corpus_metrics()
    md = generate_markdown_report(metrics)

    assert "## 4. Failure Pattern Classification (AC-7)" in md
    assert "`sign_mismatch`" in md
    assert "`multi_column_bleed`" in md


def test_generate_markdown_report_diff_details_flag() -> None:
    """Verifies that include_diff_details toggle controls line-item diff rendering."""
    metrics = _create_mock_corpus_metrics()
    md_with_diffs = generate_markdown_report(metrics, include_diff_details=True)
    md_without_diffs = generate_markdown_report(metrics, include_diff_details=False)

    assert "## 6. Granular Line-Item Diffs" in md_with_diffs
    assert "Stock-based comp" in md_with_diffs
    assert "## 6. Granular Line-Item Diffs" not in md_without_diffs


def test_generate_terminal_summary() -> None:
    """Verifies terminal summary output contains key metrics and governance disclosure."""
    metrics = _create_mock_corpus_metrics()
    summary = generate_terminal_summary(metrics)

    assert "FOOTNOTE BENCHMARK EVALUATION REPORT: TEST CORPUS" in summary
    assert "Line-Item Accuracy:          80.00% (Target: >= 90.0%)" in summary
    assert "THREE-LAYER ERROR ISOLATION (AC-4):" in summary
    assert "Extraction Errors:        2" in summary
    assert "MANDATORY GOVERNANCE DISCLOSURE (CONSTITUTION §6.13):" in summary


def test_save_reports_writes_files(tmp_path: Path) -> None:
    """Verifies saving JSON and Markdown report files to disk."""
    metrics = _create_mock_corpus_metrics()
    json_path, md_path = save_reports(
        metrics, tmp_path, base_filename="benchmark_report"
    )

    assert json_path.exists()
    assert md_path.exists()
    assert json_path.stat().st_size > 0
    assert md_path.stat().st_size > 0

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert json_data["corpus_name"] == "Test Corpus"

    md_text = md_path.read_text(encoding="utf-8")
    assert "# Evaluation Report: Test Corpus" in md_text
