# Footnote Evaluation Harness

> [!WARNING]
> **Status: FROZEN PENDING PILOT CLIENT CONFIRMATION**
>
> The evaluation harness is intentionally frozen on standby. The benchmark corpus (`eval/corpus/`) does not yet contain verified ground-truth financial statements or human-verified coordinate annotations.
>
> Do not extend or build further abstractions into this harness until a pilot client confirms the core extraction and spreading pipeline handles their primary use case end-to-end.
>
> Reference: `docs/business_alignment.md` §1.1 and `fixes.md` §13.

## Overview

The `eval/` package implements benchmarking and accuracy evaluation for Footnote's multi-stage extraction, confidence scoring, classification, and financial model compilation pipeline.

### Components

- `models.py`: Data contracts for benchmark metrics, stage reports, error classifications, and run configurations.
- `metrics.py`: Deterministic scoring algorithms (Cell Exact Match, Coordinate IoU, Taxonomy Alignment, Math Invariance).
- `corpus_loader.py`: File loader for SEC EDGAR 10-K/10-Q test filings and ground-truth manifests.
- `runner.py`: End-to-end test execution harness running jobs across the evaluation pipeline.
- `report_generator.py`: Generates Markdown and JSON accuracy reports into `eval/reports/`.
- `run_benchmark.py`: Command-line entry point for executing evaluation runs.
