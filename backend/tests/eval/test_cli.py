"""
Unit and integration tests for Benchmark CLI Runner (eval/run_benchmark.py).

Enforces:
- AC-1: Loading benchmark corpus and single-filing filtering.
- AC-2: Production module execution via CLI orchestrator.
- AC-5: Strict threshold evaluation flags.
- CONSTITUTION §6.13: Mandatory governance disclosures embedded in CLI output and saved reports.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from eval.models import CorpusAccuracyMetrics
from eval.run_benchmark import main, parse_args, run_benchmark


def test_cli_parse_args_defaults() -> None:
    """Verifies default CLI argument values."""
    args = parse_args([])
    assert args.filing_id is None
    assert args.mock_classifier is False
    assert args.iou_threshold == 0.5
    assert args.strict is False
    assert args.no_diff_details is False
    assert args.quiet is False
    assert args.report_name == "evaluation_report"


def test_cli_parse_args_custom_flags() -> None:
    """Verifies custom CLI arguments are correctly parsed."""
    args = parse_args(
        [
            "--corpus-dir",
            "./custom_corpus",
            "--filing-id",
            "acme_2023_10k",
            "--output-dir",
            "./custom_reports",
            "--report-name",
            "ci_report",
            "--mock-classifier",
            "--iou-threshold",
            "0.7",
            "--no-diff-details",
            "--strict",
            "--quiet",
        ]
    )

    assert str(args.corpus_dir) == "custom_corpus"
    assert args.filing_id == "acme_2023_10k"
    assert str(args.output_dir) == "custom_reports"
    assert args.report_name == "ci_report"
    assert args.mock_classifier is True
    assert args.iou_threshold == 0.7
    assert args.no_diff_details is True
    assert args.strict is True
    assert args.quiet is True


def test_cli_missing_corpus_raises() -> None:
    """Verifies that non-existent corpus directory raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        run_benchmark(corpus_dir="./non_existent_directory_12345")


def test_cli_invalid_filing_id_raises() -> None:
    """Verifies that non-existent filing ID raises KeyError."""
    corpus_dir = (
        Path(__file__).resolve().parent.parent.parent.parent / "eval" / "corpus"
    )
    with pytest.raises(KeyError):
        run_benchmark(corpus_dir=corpus_dir, filing_id="invalid_unknown_company_id")


def test_cli_main_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verifies --help exits with 0 and prints usage."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Footnote Benchmark Evaluation Harness" in captured.out


def test_cli_main_single_filing_mock_execution(tmp_path: Path) -> None:
    """AC-1, AC-2, AC-6: Tests complete CLI execution for a single benchmark filing in mock mode."""
    corpus_dir = (
        Path(__file__).resolve().parent.parent.parent.parent / "eval" / "corpus"
    )

    exit_code = main(
        [
            "--corpus-dir",
            str(corpus_dir),
            "--filing-id",
            "acme_2023_10k",
            "--output-dir",
            str(tmp_path),
            "--report-name",
            "test_run",
            "--mock-classifier",
            "--quiet",
        ]
    )

    assert exit_code == 0

    json_file = tmp_path / "test_run.json"
    md_file = tmp_path / "test_run.md"

    assert json_file.exists()
    assert md_file.exists()
    assert json_file.stat().st_size > 0
    assert md_file.stat().st_size > 0

    # Verify report content
    json_text = json_file.read_text(encoding="utf-8")
    md_text = md_file.read_text(encoding="utf-8")

    assert "acme_2023_10k" in json_text
    assert "Evaluation Report" in md_text
    assert "CONSTITUTION §6.13" in md_text


def test_cli_strict_mode_failure_on_low_accuracy(tmp_path: Path) -> None:
    """AC-5: Tests that strict mode returns exit code 1 when accuracy criteria fail."""
    corpus_dir = (
        Path(__file__).resolve().parent.parent.parent.parent / "eval" / "corpus"
    )

    # We mock diff_corpus to simulate a failed accuracy threshold (< 90%)
    with patch("eval.run_benchmark.diff_corpus") as mock_diff:
        mock_diff.return_value = CorpusAccuracyMetrics(
            corpus_name="Mock Corpus",
            total_filings=1,
            successful_filings=1,
            failed_extraction_filings_count=0,
            total_ground_truth_items=5,
            total_extracted_items=5,
            total_true_positives=3,
            total_false_positives=2,
            total_false_negatives=2,
            macro_precision=0.6,
            macro_recall=0.6,
            macro_f1_score=0.6,
            micro_precision=0.6,
            micro_recall=0.6,
            micro_f1_score=0.6,
            corpus_line_item_accuracy_percentage=60.0,
            target_accuracy_achieved=False,  # Fails target accuracy
            benchmark_corpus_size=1,
            mandatory_governance_disclosure="Evaluation conducted on benchmark corpus of 1 filings.",
        )

        exit_code = main(
            [
                "--corpus-dir",
                str(corpus_dir),
                "--filing-id",
                "acme_2023_10k",
                "--output-dir",
                str(tmp_path),
                "--mock-classifier",
                "--strict",
                "--quiet",
            ]
        )

        assert exit_code == 1
