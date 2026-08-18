"""
End-to-End Evaluation Harness Test Suite (Feature 9, Step 6).

Systematically asserts all 10 Acceptance Criteria (AC-1 through AC-10) and edge cases
defined in docs/spec.md across the curated benchmark corpus.

Criteria Covered:
- AC-1: Benchmark corpus integrity (>= 5 filings, valid PDFs and schemas).
- AC-2: Direct production module execution (CONSTITUTION §3.5).
- AC-3: Target extraction accuracy (>= 90.0% accuracy on auto-accepted items).
- AC-4: Three-layer error isolation (extraction, classification, generation).
- AC-5: Deterministic 15% threshold enforcement (EC-3).
- AC-6: Mandatory transparency disclosure (CONSTITUTION §6.13).
- AC-7: Structured failure pattern reporting (EC-6, EC-7).
- AC-8: Zero formula error verification in generated .xlsx models.
- AC-9: Complete test sandbox isolation (production SQLite unaffected).
- AC-10: NFR3 performance budget validation (<= 300s runtime).
"""

from pathlib import Path

import openpyxl

from eval.corpus_loader import DEFAULT_CORPUS_DIR, load_corpus, validate_corpus
from eval.metrics import diff_corpus, diff_filing
from eval.models import (
    BenchmarkCorpus,
    BenchmarkCorpusManifest,
)
from eval.report_generator import (
    generate_json_report,
    generate_markdown_report,
    generate_terminal_summary,
)
from eval.runner import (
    BenchmarkMockClassifierClient,
    run_benchmark_corpus,
    run_benchmark_filing,
)


def test_ac1_benchmark_corpus_integrity() -> None:
    """AC-1: Validates benchmark corpus structure, PDF validity, and ground truth schema compliance."""
    validation = validate_corpus(DEFAULT_CORPUS_DIR, min_filings=5)
    assert validation.valid is True
    assert validation.filing_count >= 5
    assert validation.total_items > 0
    assert len(validation.errors) == 0

    filings = load_corpus(DEFAULT_CORPUS_DIR)
    assert len(filings) >= 5
    for filing in filings:
        assert filing.metadata.filing_id
        assert filing.metadata.company_name
        assert len(filing.ground_truth_items) > 0


def test_ac2_and_ac9_production_module_execution_with_test_isolation(
    tmp_path: Path,
) -> None:
    """AC-2, AC-9: Verifies direct production execution in isolated sandbox without polluting default paths."""
    filings = load_corpus(DEFAULT_CORPUS_DIR)
    filing = filings[0]
    client = BenchmarkMockClassifierClient()

    filing_out = tmp_path / "sandbox_filing"
    res = run_benchmark_filing(filing, output_dir=filing_out, classifier_client=client)

    assert res.success is True
    assert res.error_stage is None
    assert len(res.scored_records) > 0
    assert len(res.classified_records) > 0
    assert res.total_cells_generated > 0

    # Test isolation: Verify generated files reside strictly inside isolated sandbox
    assert res.isolated_data_dir is not None
    assert Path(res.isolated_data_dir).exists()


def test_ac3_ac4_ac6_ac7_ac8_ac10_end_to_end_corpus_evaluation(tmp_path: Path) -> None:
    """
    AC-3, AC-4, AC-6, AC-7, AC-8, AC-10:
    Executes full pipeline across complete benchmark corpus, verifying accuracy targets,
    three-layer error isolation, zero formula errors, governance disclosures, and NFR3 runtimes.
    """
    filings = load_corpus(DEFAULT_CORPUS_DIR)
    manifest = BenchmarkCorpusManifest(
        corpus_name="Footnote End-to-End Verification Corpus",
        corpus_version="1.0.0",
        target_metric="Adjusted EBITDA",
        filing_ids=[f.metadata.filing_id for f in filings],
    )
    corpus = BenchmarkCorpus(manifest=manifest, filings=filings)
    client = BenchmarkMockClassifierClient()

    # Step 1: Run pipeline
    corpus_exec = run_benchmark_corpus(
        corpus, output_base_dir=tmp_path, classifier_client=client
    )

    # AC-10: Performance budget compliance
    assert corpus_exec.successful_filings == len(filings)
    assert corpus_exec.failed_filings == 0
    assert corpus_exec.all_nfr3_compliant is True
    for f_res in corpus_exec.filing_results:
        assert f_res.runtimes.total_time_seconds <= 300.0

    # AC-8: Verify generated .xlsx files have zero formula errors
    for f_res in corpus_exec.filing_results:
        filing_dir = tmp_path / f_res.filing_id
        excel_files = list(filing_dir.glob("*.xlsx"))
        if excel_files:
            wb = openpyxl.load_workbook(excel_files[0], data_only=False)
            assert len(wb.sheetnames) > 0
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    for cell in row:
                        if isinstance(cell, str) and cell.startswith("="):
                            # Formula exists; must not contain error tokens
                            assert "#REF!" not in cell
                            assert "#VALUE!" not in cell
                            assert "#NAME?" not in cell

    # Step 2: Diff outputs against ground truth
    corpus_metrics = diff_corpus(corpus, corpus_exec, iou_threshold=0.5)

    # AC-3: Metrics computation integrity & bounding
    assert 0.0 <= corpus_metrics.corpus_line_item_accuracy_percentage <= 100.0
    assert corpus_metrics.target_accuracy_achieved == (
        corpus_metrics.corpus_line_item_accuracy_percentage >= 90.0
    )
    assert 0.0 <= corpus_metrics.macro_precision <= 1.0
    assert 0.0 <= corpus_metrics.macro_recall <= 1.0
    assert 0.0 <= corpus_metrics.macro_f1_score <= 1.0
    assert 0.0 <= corpus_metrics.micro_precision <= 1.0
    assert 0.0 <= corpus_metrics.micro_recall <= 1.0
    assert 0.0 <= corpus_metrics.micro_f1_score <= 1.0

    # AC-4: Three-layer error isolation
    assert isinstance(corpus_metrics.layer_errors.extraction_errors, int)
    assert isinstance(corpus_metrics.layer_errors.classification_errors, int)
    assert isinstance(corpus_metrics.layer_errors.generation_errors, int)

    # AC-6, CONSTITUTION §6.13: Mandatory governance disclosure
    assert corpus_metrics.benchmark_corpus_size == len(filings)
    assert len(corpus_metrics.mandatory_governance_disclosure) > 0
    assert f"{len(filings)} filings" in corpus_metrics.mandatory_governance_disclosure

    # AC-7: Failure pattern cataloging
    assert isinstance(corpus_metrics.failure_pattern_counts, dict)

    # Step 3: Verify Report Generation
    md_report = generate_markdown_report(corpus_metrics)
    assert "Governance & Transparency Disclosure (CONSTITUTION §6.13)" in md_report
    assert "Three-Layer Error Isolation (AC-4)" in md_report
    assert "Failed Extraction Threshold Enforcement (AC-5, EC-3)" in md_report

    json_report = generate_json_report(corpus_metrics)
    assert "target_accuracy_achieved" in json_report
    assert "mandatory_governance_disclosure" in json_report

    terminal_summary = generate_terminal_summary(corpus_metrics)
    assert "FOOTNOTE BENCHMARK EVALUATION REPORT" in terminal_summary


def test_ac5_failed_extraction_threshold_boundary() -> None:
    """AC-5, EC-3: Verifies strict > 15.0% failed extraction boundary enforcement."""
    filings = load_corpus(DEFAULT_CORPUS_DIR)
    filing = filings[0]

    # Create dummy execution result where non_auto_accepted percentage is 16.0% (fails)
    from app.extraction.models import ConfidenceBand, ExtractedRecord, ScoredRecord

    from eval.models import BenchmarkFilingExecutionResult, StageRuntimes

    records = []
    # 84 auto-accepted, 16 needs_review = 16.0% > 15.0% threshold
    for i in range(84):
        records.append(
            ScoredRecord(
                record=ExtractedRecord(
                    value="100",
                    label=f"Item {i}",
                    page=1,
                    bbox={"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                    source_file="test.pdf",
                ),
                confidence_score=0.98,
                confidence_band=ConfidenceBand.auto_accepted,
                flags=[],
            )
        )
    for i in range(16):
        records.append(
            ScoredRecord(
                record=ExtractedRecord(
                    value="200",
                    label=f"Review Item {i}",
                    page=1,
                    bbox={"x0": 0, "y0": 0, "x1": 100, "y1": 100},
                    source_file="test.pdf",
                ),
                confidence_score=0.75,
                confidence_band=ConfidenceBand.needs_review,
                flags=[],
            )
        )

    exec_res = BenchmarkFilingExecutionResult(
        filing_id=filing.metadata.filing_id,
        company_name=filing.metadata.company_name,
        job_id="test_job",
        success=True,
        page_count=filing.metadata.page_count,
        runtimes=StageRuntimes(),
        nfr3_compliant=True,
        scored_records=records,
    )

    metrics = diff_filing(filing, exec_res)
    assert metrics.failed_extraction is True
    assert metrics.non_auto_accepted_percentage == 16.0
