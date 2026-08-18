"""
Unit and integration tests for Feature 9 Evaluation Pipeline Runner (eval/runner.py).
"""

from pathlib import Path
from unittest.mock import patch

from app.classification.models import ClassifierInputPayload

from eval.corpus_loader import DEFAULT_CORPUS_DIR, load_corpus, load_filing
from eval.models import (
    BenchmarkFiling,
    BenchmarkFilingMetadata,
    GroundTruthBbox,
    GroundTruthItem,
)
from eval.runner import (
    BenchmarkMockClassifierClient,
    get_default_classifier_client,
    run_benchmark_corpus,
    run_benchmark_filing,
)


def test_benchmark_mock_classifier_client() -> None:
    """Verifies that BenchmarkMockClassifierClient maps standard labels accurately."""
    client = BenchmarkMockClassifierClient()

    p1 = ClassifierInputPayload(label="Net income")
    r1 = client.classify(p1)
    assert r1.label == "Net Income"
    assert r1.confidence == 0.98

    p2 = ClassifierInputPayload(label="Stock-based compensation expense")
    r2 = client.classify(p2)
    assert r2.label == "Stock-based compensation"

    p3 = ClassifierInputPayload(label="Custom Unknown Item")
    r3 = client.classify(p3)
    assert r3.label == "Custom Unknown Item"


def test_get_default_classifier_client() -> None:
    with patch.dict("os.environ", {}, clear=True):
        client = get_default_classifier_client()
        assert isinstance(client, BenchmarkMockClassifierClient)


def test_run_benchmark_filing_success(tmp_path: Path) -> None:
    """AC-2, AC-10: Executes the full production pipeline end-to-end against a benchmark filing."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "acme_2023_10k")
    res = run_benchmark_filing(
        filing,
        corpus_dir=DEFAULT_CORPUS_DIR,
        output_dir=tmp_path,
    )

    assert res.success is True
    assert res.filing_id == "acme_2023_10k"
    assert res.company_name == "Acme Corporation"
    assert res.job_id != "uninitialized"
    assert res.page_count == 2
    assert res.nfr3_compliant is True

    # Granular runtimes verification (AC-10)
    assert res.runtimes.docling_time_seconds >= 0.0
    assert res.runtimes.coordinate_norm_time_seconds >= 0.0
    assert res.runtimes.assembly_and_scoring_time_seconds >= 0.0
    assert res.runtimes.extraction_time_seconds >= 0.0
    assert res.runtimes.classification_time_seconds >= 0.0
    assert res.runtimes.formula_time_seconds >= 0.0
    assert res.runtimes.generation_time_seconds >= 0.0
    assert res.runtimes.total_time_seconds > 0.0

    # Pipeline output verification
    assert len(res.scored_records) > 0
    assert len(res.classified_records) > 0
    assert res.extraction_summary is not None
    assert res.total_cells_generated > 0
    assert res.provenance_count > 0

    # Generated files verification in isolated dir (AC-9)
    assert (tmp_path / "models" / f"{res.job_id}_model.xlsx").is_file()
    assert (tmp_path / "jobs.json").is_file()


def test_run_benchmark_filing_test_isolation() -> None:
    """AC-9: Verifies that running in default isolation uses a temporary dir and does not mutate production stores."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "acme_2023_10k")
    res = run_benchmark_filing(filing, corpus_dir=DEFAULT_CORPUS_DIR)

    assert res.success is True
    assert res.isolated_data_dir is not None
    assert "footnote_eval_" in res.isolated_data_dir


def test_run_benchmark_filing_missing_pdf() -> None:
    """EC-4: Verifies descriptive failure result when PDF file is missing."""
    meta = BenchmarkFilingMetadata(
        filing_id="nonexistent_filing",
        company_name="Missing Co",
        ticker="MISS",
        fiscal_year=2023,
        pdf_filename="does_not_exist.pdf",
        page_count=1,
    )
    item = GroundTruthItem(
        value="100",
        label="Net income",
        normalized_label="Net Income",
        page=1,
        bbox=GroundTruthBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="does_not_exist.pdf",
    )
    filing = BenchmarkFiling(metadata=meta, ground_truth_items=[item])

    res = run_benchmark_filing(filing, corpus_dir=DEFAULT_CORPUS_DIR)
    assert res.success is False
    assert res.error_stage == "ingestion"
    assert "not found" in (res.error_detail or "")


def test_run_benchmark_filing_stage_error_isolation(tmp_path: Path) -> None:
    """EC-8: Captures stage-isolated failures cleanly without unhandled exception."""
    filing = load_filing(DEFAULT_CORPUS_DIR / "acme_2023_10k")

    with patch(
        "eval.runner.generate_workbook",
        side_effect=RuntimeError("Workbook generator crash"),
    ):
        res = run_benchmark_filing(
            filing,
            corpus_dir=DEFAULT_CORPUS_DIR,
            output_dir=tmp_path,
        )

    assert res.success is False
    assert res.error_stage == "excel_export"
    assert "Workbook generator crash" in (res.error_detail or "")


def test_run_benchmark_corpus_aggregates_metrics(tmp_path: Path) -> None:
    """AC-2, AC-10: Executes corpus subset and aggregates runtimes and success counts."""
    corpus = load_corpus(DEFAULT_CORPUS_DIR)
    subset = corpus[:2]

    res = run_benchmark_corpus(
        corpus=subset,
        corpus_dir=DEFAULT_CORPUS_DIR,
        output_base_dir=tmp_path,
    )

    assert res.total_filings == 2
    assert res.successful_filings == 2
    assert res.failed_filings == 0
    assert res.total_runtime_seconds > 0.0
    assert res.average_filing_runtime_seconds > 0.0
    assert res.all_nfr3_compliant is True
    assert len(res.filing_results) == 2
