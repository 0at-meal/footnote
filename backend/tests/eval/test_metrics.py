"""
Unit and integration tests for Feature 9 Evaluation Multi-Layer Diffing & Metrics (eval/metrics.py).

Enforces:
- CONSTITUTION §1.4: Pure mathematical and semantic evaluation without I/O side effects.
- CONSTITUTION §3.5: Direct model and layer error verification (AC-4).
- CONSTITUTION §6.13: Mandatory governance disclosures embedded in all corpus reports.
- AC-3: >= 90% Line-item extraction accuracy target threshold.
- AC-5 / EC-3: Strict > 15.0% non-auto-accepted confidence threshold for failed extractions.
- AC-7: Failure pattern categorization.
- EC-1: Optional ground-truth items handling.
- EC-2: Accounting parentheses and currency equivalence.
- EC-6: 2D Bounding box IoU calculation.
"""

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.extraction.models import ConfidenceBand, ExtractedRecord, ScoredRecord

from eval.metrics import (
    are_values_equivalent,
    calculate_bbox_iou,
    classify_failure_pattern,
    diff_corpus,
    diff_filing,
    parse_numeric_value,
)
from eval.models import (
    BenchmarkCorpus,
    BenchmarkCorpusExecutionResult,
    BenchmarkCorpusManifest,
    BenchmarkFiling,
    BenchmarkFilingExecutionResult,
    BenchmarkFilingMetadata,
    FailurePattern,
    GroundTruthBbox,
    GroundTruthItem,
    ItemMatchStatus,
    StageRuntimes,
)


def test_calculate_bbox_iou_identical_boxes() -> None:
    """EC-6: Bounding box IoU of identical boxes is exactly 1.0."""
    b1 = GroundTruthBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0)
    b2 = GroundTruthBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0)
    iou = calculate_bbox_iou(b1, b2)
    assert iou == 1.0


def test_calculate_bbox_iou_disjoint_boxes() -> None:
    """EC-6: Disjoint non-overlapping bounding boxes have IoU of 0.0."""
    b1 = GroundTruthBbox(x0=10.0, y0=10.0, x1=50.0, y1=50.0)
    b2 = GroundTruthBbox(x0=60.0, y0=60.0, x1=100.0, y1=100.0)
    iou = calculate_bbox_iou(b1, b2)
    assert iou == 0.0


def test_calculate_bbox_iou_partial_overlap() -> None:
    """EC-6: Partial overlap computes exact intersection-over-union ratio."""
    # Box A: [0, 0, 10, 10] -> Area = 100
    # Box B: [5, 0, 15, 10] -> Area = 100
    # Inter: [5, 0, 10, 10] -> Area = 50
    # Union: 100 + 100 - 50 = 150
    # IoU: 50 / 150 = 0.3333
    b1 = GroundTruthBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0)
    b2 = GroundTruthBbox(x0=5.0, y0=0.0, x1=15.0, y1=10.0)
    iou = calculate_bbox_iou(b1, b2)
    assert iou == 0.3333


def test_calculate_bbox_iou_none_handling() -> None:
    """EC-6: Returns 0.0 when second box is None."""
    b1 = GroundTruthBbox(x0=10.0, y0=10.0, x1=50.0, y1=50.0)
    assert calculate_bbox_iou(b1, None) == 0.0


def test_parse_numeric_value_variants() -> None:
    """EC-2: Parses accounting parentheses negatives, dollar signs, commas, percentages."""
    assert parse_numeric_value("(1,234.50)") == -1234.50
    assert parse_numeric_value("$50,000") == 50000.0
    assert parse_numeric_value("-100.0") == -100.0
    assert parse_numeric_value("100%") == 100.0
    assert parse_numeric_value("  ( 500 ) ") == -500.0
    assert parse_numeric_value("invalid_text") is None
    assert parse_numeric_value(None) is None


def test_are_values_equivalent_accounting_parens() -> None:
    """EC-2: Evaluates '(1,234)' and '-1234' as semantically equivalent."""
    assert are_values_equivalent("(1,234)", "-1234") is True
    assert are_values_equivalent("$50,000.00", "50000") is True
    assert are_values_equivalent("(50.00)", "50.00") is False
    assert are_values_equivalent("100", "200") is False
    assert are_values_equivalent(None, None) is True
    assert are_values_equivalent("Net income", "net income") is True


def test_classify_failure_pattern() -> None:
    """AC-7: Classifies structural layout errors accurately."""
    gt = GroundTruthItem(
        value="100",
        label="Net income",
        normalized_label="Net Income",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=10.0, x1=50.0, y1=50.0),
        source_file="f.pdf",
    )

    # Sign mismatch
    p1 = classify_failure_pattern(
        gt, "-100", "Net income", ItemMatchStatus.value_mismatch
    )
    assert p1 == FailurePattern.sign_mismatch

    # Multi-column bleed
    p2 = classify_failure_pattern(
        gt, "100 200 300", "Net income", ItemMatchStatus.value_mismatch
    )
    assert p2 == FailurePattern.multi_column_bleed

    # Merged cell misalignment
    p3 = classify_failure_pattern(
        gt, "100", "Net income", ItemMatchStatus.localization_error
    )
    assert p3 == FailurePattern.merged_cell_misalignment

    # Unrecognized taxonomy label
    p4 = classify_failure_pattern(
        gt, "100", "Net income", ItemMatchStatus.classification_mismatch
    )
    assert p4 == FailurePattern.unrecognized_label

    # Missing item
    p5 = classify_failure_pattern(gt, None, None, ItemMatchStatus.missed_item)
    assert p5 == FailurePattern.missing_item


def _create_mock_filing_and_exec_result(
    confidence_scores: list[float] | None = None,
    val_mismatch: bool = False,
    class_mismatch: bool = False,
    optional_item: bool = False,
) -> tuple[BenchmarkFiling, BenchmarkFilingExecutionResult]:
    """Helper to generate mock filing and execution result pairs."""
    meta = BenchmarkFilingMetadata(
        filing_id="acme_2023_10k",
        company_name="Acme Corporation",
        ticker="ACME",
        fiscal_year=2023,
        pdf_filename="acme.pdf",
        page_count=2,
    )
    items = [
        GroundTruthItem(
            value="50000",
            label="Net income",
            normalized_label="Net Income",
            page=1,
            bbox=GroundTruthBbox(x0=100.0, y0=100.0, x1=300.0, y1=150.0),
            source_file="acme.pdf",
        ),
        GroundTruthItem(
            value="12000",
            label="Interest expense",
            normalized_label="Interest Expense",
            page=1,
            bbox=GroundTruthBbox(x0=100.0, y0=160.0, x1=300.0, y1=210.0),
            source_file="acme.pdf",
            is_optional=optional_item,
        ),
    ]
    filing = BenchmarkFiling(metadata=meta, ground_truth_items=items)

    scores = confidence_scores or [0.98, 0.96]
    rec1 = ExtractedRecord(
        label="Net income",
        value="50,000" if not val_mismatch else "99,999",
        page=1,
        bbox={"x0": 100.0, "y0": 100.0, "x1": 300.0, "y1": 150.0},
        source_file="acme.pdf",
    )
    rec2 = ExtractedRecord(
        label="Interest expense",
        value="12,000",
        page=1,
        bbox={"x0": 100.0, "y0": 160.0, "x1": 300.0, "y1": 210.0},
        source_file="acme.pdf",
    )

    sr1 = ScoredRecord(
        record=rec1,
        confidence_score=scores[0],
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
    )
    sr2 = ScoredRecord(
        record=rec2,
        confidence_score=scores[1],
        confidence_band=(
            ConfidenceBand.auto_accepted
            if scores[1] >= 0.95
            else ConfidenceBand.needs_review
        ),
        flags=[],
    )

    cr1 = ClassifiedRecord(
        record=sr1,
        normalized_label="Net Income" if not class_mismatch else "Wrong Label",
        taxonomy_status=(
            TaxonomyStatus.matched
            if not class_mismatch
            else TaxonomyStatus.pending_taxonomy_confirmation
        ),
        classifier_confidence=0.99,
        is_confirmed=not class_mismatch,
    )
    cr2 = ClassifiedRecord(
        record=sr2,
        normalized_label="Interest Expense",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.99,
        is_confirmed=True,
    )

    exec_res = BenchmarkFilingExecutionResult(
        filing_id="acme_2023_10k",
        company_name="Acme Corporation",
        job_id="test-job-123",
        success=True,
        page_count=2,
        runtimes=StageRuntimes(total_time_seconds=12.5),
        nfr3_compliant=True,
        scored_records=[sr1, sr2],
        classified_records=[cr1, cr2],
        total_cells_generated=10,
        provenance_count=10,
    )
    return filing, exec_res


def test_diff_filing_perfect_match() -> None:
    """AC-3, AC-4: Evaluates clean 100% precision, recall, and accuracy matching."""
    filing, exec_res = _create_mock_filing_and_exec_result()
    metrics = diff_filing(filing, exec_res)

    assert metrics.true_positives == 2
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0
    assert metrics.line_item_accuracy_percentage == 100.0
    assert metrics.target_accuracy_achieved is True
    assert metrics.failed_extraction is False
    assert metrics.layer_errors.extraction_errors == 0
    assert metrics.layer_errors.classification_errors == 0
    assert metrics.layer_errors.generation_errors == 0


def test_diff_filing_optional_ground_truth_item() -> None:
    """EC-1: Non-reporting of an optional item does not penalize recall."""
    filing, exec_res = _create_mock_filing_and_exec_result(optional_item=True)
    # Remove second record from execution output
    exec_res.scored_records = [exec_res.scored_records[0]]
    exec_res.classified_records = [exec_res.classified_records[0]]

    metrics = diff_filing(filing, exec_res)

    # 1 non-optional item extracted correctly
    assert metrics.true_positives == 1
    assert metrics.false_negatives == 0
    assert metrics.recall == 1.0
    assert metrics.line_item_accuracy_percentage == 100.0
    assert metrics.target_accuracy_achieved is True


def test_diff_filing_failed_extraction_threshold_boundary() -> None:
    """AC-5, EC-3: Filing with > 15% non-auto-accepted items is marked failed_extraction."""
    # 1 item auto-accept (score 0.98), 1 item needs review (score 0.80) -> 50% non-auto-accepted
    filing, exec_res = _create_mock_filing_and_exec_result(
        confidence_scores=[0.98, 0.80]
    )
    metrics = diff_filing(filing, exec_res)

    assert metrics.non_auto_accepted_count == 1
    assert metrics.non_auto_accepted_percentage == 50.0
    assert metrics.failed_extraction is True


def test_diff_filing_under_threshold_passes() -> None:
    """AC-5, EC-7: Filing with <= 15% non-auto-accepted items passes."""
    filing, exec_res = _create_mock_filing_and_exec_result(
        confidence_scores=[0.98, 0.96]
    )
    metrics = diff_filing(filing, exec_res)

    assert metrics.non_auto_accepted_count == 0
    assert metrics.non_auto_accepted_percentage == 0.0
    assert metrics.failed_extraction is False


def test_diff_filing_three_layer_error_isolation() -> None:
    """AC-4: Strictly isolates extraction, classification, and generation errors."""
    filing, exec_res = _create_mock_filing_and_exec_result(
        val_mismatch=True, class_mismatch=True
    )
    # Set generation to 0 cells
    exec_res.total_cells_generated = 0

    metrics = diff_filing(filing, exec_res)

    assert metrics.layer_errors.extraction_errors >= 1
    assert metrics.layer_errors.generation_errors >= 1
    assert metrics.target_accuracy_achieved is False


def test_diff_corpus_aggregates_and_embeds_mandatory_disclosure() -> None:
    """AC-3, AC-6, CONSTITUTION §6.13: Computes corpus aggregates and embeds mandatory disclosure."""
    filing1, exec_res1 = _create_mock_filing_and_exec_result()

    manifest = BenchmarkCorpusManifest(
        corpus_name="test_corpus",
        corpus_version="1.0.0",
        filing_ids=["acme_2023_10k"],
    )
    corpus = BenchmarkCorpus(manifest=manifest, filings=[filing1])
    corpus_exec = BenchmarkCorpusExecutionResult(
        corpus_name="test_corpus",
        total_filings=1,
        successful_filings=1,
        failed_filings=0,
        total_runtime_seconds=12.5,
        average_filing_runtime_seconds=12.5,
        all_nfr3_compliant=True,
        filing_results=[exec_res1],
    )

    corpus_metrics = diff_corpus(corpus, corpus_exec)

    assert corpus_metrics.corpus_name == "test_corpus"
    assert corpus_metrics.total_filings == 1
    assert corpus_metrics.total_ground_truth_items == 2
    assert corpus_metrics.total_true_positives == 2
    assert corpus_metrics.corpus_line_item_accuracy_percentage == 100.0
    assert corpus_metrics.target_accuracy_achieved is True
    assert corpus_metrics.benchmark_corpus_size == 1

    # Verify CONSTITUTION §6.13 mandatory disclosure formatting
    assert (
        "Evaluation conducted on benchmark corpus of 1 filings (2 total ground-truth items)"
        in (corpus_metrics.mandatory_governance_disclosure)
    )
    assert "0 items (0.00%) required human review or manual correction" in (
        corpus_metrics.mandatory_governance_disclosure
    )


def test_diff_filing_failed_pipeline_execution() -> None:
    """AC-4: Complete pipeline failure results in zero accuracy and failed extraction status."""
    filing, exec_res = _create_mock_filing_and_exec_result()
    exec_res.success = False
    exec_res.error_stage = "extraction"
    exec_res.error_detail = "PDF corrupted"
    exec_res.scored_records = []
    exec_res.classified_records = []

    metrics = diff_filing(filing, exec_res)

    assert metrics.true_positives == 0
    assert metrics.false_negatives == 2
    assert metrics.line_item_accuracy_percentage == 0.0
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.f1_score == 0.0
    assert metrics.failed_extraction is True
    assert metrics.target_accuracy_achieved is False
    assert metrics.layer_errors.generation_errors >= 1


def test_diff_filing_spurious_extractions() -> None:
    """AC-4: Spurious extractions not matching ground truth are flagged and lower precision."""
    filing, exec_res = _create_mock_filing_and_exec_result()
    # Add a third spurious record
    spurious_rec = ExtractedRecord(
        label="Random Unrelated Note",
        value="999",
        page=1,
        bbox={"x0": 500.0, "y0": 500.0, "x1": 600.0, "y1": 550.0},
        source_file="acme.pdf",
    )
    spurious_sr = ScoredRecord(
        record=spurious_rec,
        confidence_score=0.97,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
    )
    spurious_cr = ClassifiedRecord(
        record=spurious_sr,
        normalized_label="Other non-operating income",
        taxonomy_status=TaxonomyStatus.matched,
        classifier_confidence=0.90,
        is_confirmed=True,
    )
    exec_res.scored_records.append(spurious_sr)
    exec_res.classified_records.append(spurious_cr)

    metrics = diff_filing(filing, exec_res)

    assert metrics.true_positives == 2
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 0
    assert metrics.precision == 0.6667  # 2 / (2 + 1)
    assert metrics.recall == 1.0  # 2 / (2 + 0)
    assert metrics.layer_errors.extraction_errors >= 1
    assert any(
        d.status == ItemMatchStatus.spurious_item for d in metrics.line_item_diffs
    )
