"""
Evaluation Harness for Footnote (Feature 9).

Public API exports:
- Corpus Loading: load_corpus, load_filing, validate_corpus
- Pipeline Runner: run_benchmark_corpus, run_benchmark_filing, BenchmarkMockClassifierClient, get_default_classifier_client
- Diffing & Metrics: diff_corpus, diff_filing, calculate_bbox_iou, are_values_equivalent, classify_failure_pattern
- Report Generation: generate_json_report, generate_markdown_report, generate_terminal_summary, save_reports
- CLI Orchestrator: run_benchmark, main
"""

from eval.corpus_loader import load_corpus, load_filing, validate_corpus
from eval.metrics import (
    are_values_equivalent,
    calculate_bbox_iou,
    classify_failure_pattern,
    diff_corpus,
    diff_filing,
)
from eval.models import (
    BenchmarkCorpus,
    BenchmarkCorpusExecutionResult,
    BenchmarkCorpusManifest,
    BenchmarkFiling,
    BenchmarkFilingExecutionResult,
    BenchmarkFilingMetadata,
    CorpusAccuracyMetrics,
    CorpusValidationResult,
    FailurePattern,
    FilingAccuracyMetrics,
    GroundTruthBbox,
    GroundTruthItem,
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
from eval.run_benchmark import main, parse_args, run_benchmark
from eval.runner import (
    BenchmarkMockClassifierClient,
    get_default_classifier_client,
    run_benchmark_corpus,
    run_benchmark_filing,
)

__all__ = [
    "BenchmarkCorpus",
    "BenchmarkCorpusExecutionResult",
    "BenchmarkCorpusManifest",
    "BenchmarkFiling",
    "BenchmarkFilingExecutionResult",
    "BenchmarkFilingMetadata",
    "BenchmarkMockClassifierClient",
    "CorpusAccuracyMetrics",
    "CorpusValidationResult",
    "FailurePattern",
    "FilingAccuracyMetrics",
    "GroundTruthBbox",
    "GroundTruthItem",
    "ItemMatchStatus",
    "LayerMetricsSummary",
    "LineItemDiff",
    "StageRuntimes",
    "are_values_equivalent",
    "calculate_bbox_iou",
    "classify_failure_pattern",
    "diff_corpus",
    "diff_filing",
    "generate_json_report",
    "generate_markdown_report",
    "generate_terminal_summary",
    "get_default_classifier_client",
    "load_corpus",
    "load_filing",
    "main",
    "parse_args",
    "run_benchmark",
    "run_benchmark_corpus",
    "run_benchmark_filing",
    "save_reports",
    "validate_corpus",
]
