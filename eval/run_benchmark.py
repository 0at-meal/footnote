#!/usr/bin/env python3
"""
Footnote Benchmark Evaluation CLI Runner (Feature 9).

Executes the complete production pipeline against the curated 10-K benchmark corpus,
evaluates three-layer discrepancies (extraction, classification, generation),
enforces the >15% failed extraction confidence threshold, and exports structured
evaluation reports with mandatory CONSTITUTION §6.13 governance disclosures.

Usage:
    python -m eval.run_benchmark [OPTIONS]
    python eval/run_benchmark.py [OPTIONS]

Examples:
    # Run full corpus in mock mode for fast local verification
    python -m eval.run_benchmark --mock-classifier

    # Run single filing with custom output directory
    python -m eval.run_benchmark --filing-id acme_2023_10k --output-dir ./reports

    # Strict CI/CD mode (fails if accuracy < 90% or failed extractions > 0)
    python -m eval.run_benchmark --strict --mock-classifier
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

# Ensure repository root and backend directory are in sys.path
_repo_root = Path(__file__).resolve().parent.parent
_backend_dir = _repo_root / "backend"
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.classification.client import GroqClassifierClient

from eval.corpus_loader import load_corpus, validate_corpus
from eval.metrics import diff_corpus
from eval.models import (
    BenchmarkCorpus,
    BenchmarkCorpusManifest,
    CorpusAccuracyMetrics,
)
from eval.report_generator import (
    generate_terminal_summary,
    save_reports,
)
from eval.runner import (
    BenchmarkMockClassifierClient,
    get_default_classifier_client,
    run_benchmark_corpus,
)


def configure_logging(quiet: bool = False) -> None:
    """Configures evaluation logging output format."""
    level = logging.WARNING if quiet else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses command-line arguments for the benchmark runner."""
    parser = argparse.ArgumentParser(
        prog="footnote-benchmark",
        description="Footnote Benchmark Evaluation Harness (Feature 9)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    default_corpus_dir = _repo_root / "eval" / "corpus"
    default_output_dir = _repo_root / "eval" / "reports"

    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=default_corpus_dir,
        help="Path to curated benchmark corpus directory containing manifest.json",
    )
    parser.add_argument(
        "--filing-id",
        type=str,
        default=None,
        help="Optional specific filing ID to evaluate (e.g. 'acme_2023_10k')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=default_output_dir,
        help="Directory where evaluation reports (.json and .md) will be saved",
    )
    parser.add_argument(
        "--report-name",
        type=str,
        default="evaluation_report",
        help="Base filename for generated reports",
    )
    parser.add_argument(
        "--mock-classifier",
        action="store_true",
        default=False,
        help="Use deterministic mock classifier client instead of live LLM API",
    )
    parser.add_argument(
        "--iou-threshold",
        type=float,
        default=0.5,
        help="Bounding box 2D IoU threshold for localization matching (0.0 - 1.0)",
    )
    parser.add_argument(
        "--no-diff-details",
        action="store_true",
        default=False,
        help="Omit granular line-item diff tables in Markdown report",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Enforce strict exit code 1 if accuracy < 90.0%% or failed extractions > 0",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress informational console logs during execution",
    )

    return parser.parse_args(args)


def run_benchmark(
    corpus_dir: Path | str,
    filing_id: str | None = None,
    output_dir: Path | str = "./eval/reports",
    report_name: str = "evaluation_report",
    use_mock_classifier: bool = False,
    iou_threshold: float = 0.5,
    include_diff_details: bool = True,
    strict: bool = False,
    quiet: bool = False,
) -> tuple[CorpusAccuracyMetrics, int]:
    """
    Core programmatic entry point to run benchmark evaluations.

    Returns:
        Tuple of (CorpusAccuracyMetrics, exit_code).
    """
    configure_logging(quiet)
    logger = logging.getLogger("eval.runner")

    corpus_path = Path(corpus_dir).resolve()
    out_path = Path(output_dir).resolve()

    if not corpus_path.exists():
        logger.error(f"Corpus directory not found at: {corpus_path}")
        raise FileNotFoundError(f"Corpus directory does not exist: {corpus_path}")

    # Validate corpus integrity
    validation_res = validate_corpus(corpus_path)
    if not validation_res.valid:
        logger.error(f"Corpus integrity validation failed: {validation_res.errors}")
        raise ValueError(f"Invalid benchmark corpus: {validation_res.errors}")

    # Load filings
    all_filings = load_corpus(corpus_path)

    # Filter to single filing if requested
    if filing_id:
        matching_filings = [f for f in all_filings if f.metadata.filing_id == filing_id]
        if not matching_filings:
            logger.error(f"Requested filing ID '{filing_id}' not found in corpus.")
            raise KeyError(f"Filing ID '{filing_id}' not found in corpus.")
        filings = matching_filings
        corpus_name = f"Footnote Benchmark (Single: {filing_id})"
    else:
        filings = all_filings
        corpus_name = "Footnote Benchmark Corpus"

    manifest = BenchmarkCorpusManifest(
        corpus_name=corpus_name,
        corpus_version="1.0.0",
        target_metric="Adjusted EBITDA",
        filing_ids=[f.metadata.filing_id for f in filings],
    )
    corpus = BenchmarkCorpus(manifest=manifest, filings=filings)

    logger.info(
        f"Initiating benchmark evaluation for corpus '{corpus.manifest.corpus_name}' "
        f"({len(corpus.filings)} filings, metric: '{corpus.manifest.target_metric}')"
    )

    # Initialize classifier client
    classifier_client: GroqClassifierClient
    if (
        use_mock_classifier
        or os.getenv("FOOTNOTE_EVAL_MOCK_CLASSIFIER", "false").lower() == "true"
    ):
        logger.info(
            "Using BenchmarkMockClassifierClient for deterministic classification."
        )
        classifier_client = BenchmarkMockClassifierClient()
    else:
        logger.info("Using default live classifier client.")
        classifier_client = get_default_classifier_client()

    # Execute pipeline
    corpus_exec = run_benchmark_corpus(corpus, classifier_client=classifier_client)

    # Compute multi-layer diffs and metrics
    corpus_metrics = diff_corpus(corpus, corpus_exec, iou_threshold=iou_threshold)

    # Print terminal summary
    terminal_output = generate_terminal_summary(corpus_metrics)
    print("\n" + terminal_output + "\n")

    # Save reports
    json_path, md_path = save_reports(
        corpus_metrics,
        output_dir=out_path,
        base_filename=report_name,
        include_diff_details=include_diff_details,
    )
    logger.info(f"JSON evaluation report saved to: {json_path}")
    logger.info(f"Markdown evaluation report saved to: {md_path}")

    # Determine exit code
    exit_code = 0
    if corpus_exec.failed_filings > 0:
        logger.warning(
            f"Pipeline execution encountered {corpus_exec.failed_filings} failed filing(s)."
        )
        exit_code = 1
    elif strict:
        if not corpus_metrics.target_accuracy_achieved:
            logger.error(
                f"Strict mode failure: Line-item accuracy ({corpus_metrics.corpus_line_item_accuracy_percentage:.2f}%) "
                f"did not achieve target threshold (>= 90.0%)."
            )
            exit_code = 1
        elif corpus_metrics.failed_extraction_filings_count > 0:
            logger.error(
                f"Strict mode failure: {corpus_metrics.failed_extraction_filings_count} filing(s) exceeded the >15.0% "
                f"failed extraction threshold."
            )
            exit_code = 1

    return corpus_metrics, exit_code


def main(args: Sequence[str] | None = None) -> int:
    """CLI entry point function."""
    parsed = parse_args(args)
    try:
        _, exit_code = run_benchmark(
            corpus_dir=parsed.corpus_dir,
            filing_id=parsed.filing_id,
            output_dir=parsed.output_dir,
            report_name=parsed.report_name,
            use_mock_classifier=parsed.mock_classifier,
            iou_threshold=parsed.iou_threshold,
            include_diff_details=not parsed.no_diff_details,
            strict=parsed.strict,
            quiet=parsed.quiet,
        )
        return exit_code
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"Error during benchmark execution: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
