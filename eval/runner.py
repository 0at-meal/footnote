"""
Benchmark Pipeline Execution Runner for Footnote (Feature 9, Step 2).

Imports and executes live production pipeline modules end-to-end against benchmark filings
in isolated execution sandboxes (CONSTITUTION §3.5, AC-2, AC-9).
Instruments granular stopwatch timers per stage to measure NFR3 performance budget compliance (AC-10).
"""

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import ClassVar

from app.classification.client import GroqClassifierClient
from app.classification.decision_log import (
    DecisionLogRepository,
    build_log_entries,
)
from app.classification.dispatcher import dispatch_records_to_classifier
from app.classification.models import (
    ClassifierInputPayload,
    ClassifierRawResponse,
)
from app.classification.normalizer import normalize_records
from app.classification.repository import ClassificationRepository
from app.classification.taxonomy import TaxonomyRepository
from app.excel_export.generator import generate_workbook
from app.excel_export.repository import ModelRepository
from app.extraction.assembler import assemble_records
from app.extraction.confidence import score_records
from app.extraction.coordinate_normalizer import (
    count_image_only_pages,
    normalize_coordinates,
)
from app.extraction.docling_parser import parse_pdf
from app.extraction.flagger import create_extraction_summary
from app.extraction.repository import ExtractionRepository
from app.formula_engine.reader import read_formula_inputs
from app.formula_engine.tree import build_formula_tree
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository

from eval.corpus_loader import DEFAULT_CORPUS_DIR, load_corpus
from eval.models import (
    BenchmarkCorpusExecutionResult,
    BenchmarkFiling,
    BenchmarkFilingExecutionResult,
    StageRuntimes,
)

logger = logging.getLogger(__name__)

# NFR3: 200-page 10-K must complete in under 5 minutes (300.0 seconds)
NFR3_MAX_RUNTIME_SECONDS = 300.0


class BenchmarkMockClassifierClient(GroqClassifierClient):
    """
    Deterministic offline classifier client for benchmark evaluations (NFR5).
    Maps common raw labels to standardized taxonomy entries without external API calls.
    """

    MOCK_TAXONOMY_MAP: ClassVar[dict[str, str]] = {
        "net income": "Net Income",
        "net loss": "Net Income",
        "interest expense": "Interest Expense",
        "interest expense, net": "Interest Expense",
        "provision for income taxes": "Income Tax Expense",
        "provision for taxes": "Income Tax Expense",
        "income tax benefit": "Income Tax Expense",
        "depreciation and amortization": "Depreciation & Amortization",
        "depreciation & amortization": "Depreciation & Amortization",
        "stock-based compensation": "Stock-based compensation",
        "stock-based compensation expense": "Stock-based compensation",
        "share-based compensation": "Stock-based compensation",
        "r&d stock-based compensation": "Stock-based compensation",
        "sg&a stock-based compensation": "Stock-based compensation",
        "operating income": "Operating Income",
        "restructuring": "Restructuring Charges",
        "restructuring and facility exit costs": "Restructuring Charges",
        "restructuring charges": "Restructuring Charges",
        "litigation": "Litigation settlement",
        "litigation settlement": "Litigation settlement",
        "litigation settlement expense": "Litigation settlement",
        "operating lease cost adjustment": "Lease adjustments",
        "lease adjustments": "Lease adjustments",
        "transaction & acquisition costs": "M&A transaction costs",
        "acquisition-related expenses": "M&A transaction costs",
        "gain on disposal of assets": "Other non-operating income",
        "adjusted ebitda": "Adjusted EBITDA",
    }

    def __init__(self) -> None:
        super().__init__(api_key="mock_benchmark_key")

    def classify(self, payload: ClassifierInputPayload) -> ClassifierRawResponse:
        clean_label = payload.label.strip().lower()
        matched_label = None
        for key, val in self.MOCK_TAXONOMY_MAP.items():
            if key in clean_label:
                matched_label = val
                break
        if not matched_label:
            matched_label = payload.label.strip()

        return ClassifierRawResponse(label=matched_label, confidence=0.98)


def get_default_classifier_client() -> GroqClassifierClient:
    """Returns a live GroqClassifierClient if API key is present, else BenchmarkMockClassifierClient."""
    if os.environ.get("GROQ_API_KEY"):
        return GroqClassifierClient()
    return BenchmarkMockClassifierClient()


def run_benchmark_filing(
    filing: BenchmarkFiling,
    corpus_dir: Path | str | None = None,
    output_dir: Path | None = None,
    classifier_client: GroqClassifierClient | None = None,
) -> BenchmarkFilingExecutionResult:
    """
    Executes the full production pipeline end-to-end against a single benchmark filing.

    Runs inside an isolated directory to avoid mutating production stores (AC-9).
    Instruments granular timing per stage (AC-10).
    Captures stage-isolated failures without aborting corpus execution (EC-8).
    """
    c_dir = Path(corpus_dir).resolve() if corpus_dir else DEFAULT_CORPUS_DIR
    pdf_source_path = c_dir / filing.metadata.filing_id / filing.metadata.pdf_filename

    if not pdf_source_path.is_file():
        return BenchmarkFilingExecutionResult(
            filing_id=filing.metadata.filing_id,
            company_name=filing.metadata.company_name,
            job_id="uninitialized",
            success=False,
            error_stage="ingestion",
            error_detail=f"Source PDF not found at {pdf_source_path}",
            page_count=filing.metadata.page_count,
            runtimes=StageRuntimes(),
            nfr3_compliant=True,
        )

    # Use specified output_dir or create a temporary directory for isolation (AC-9)
    temp_dir_ctx = None
    if output_dir is None:
        temp_dir_ctx = tempfile.TemporaryDirectory(prefix="footnote_eval_")
        target_data_dir = Path(temp_dir_ctx.name)
    else:
        target_data_dir = Path(output_dir).resolve()
        target_data_dir.mkdir(parents=True, exist_ok=True)

    runtimes = StageRuntimes()
    start_total_time = time.perf_counter()
    current_stage = "ingestion"

    try:
        # Step 0: Ingestion into isolated repo
        repo = JobRepository(data_dir=target_data_dir)
        pdf_bytes = pdf_source_path.read_bytes()
        job_record = repo.save_job(
            filename=filing.metadata.pdf_filename,
            content=pdf_bytes,
            target_metric=filing.metadata.target_metric,
        )
        job_id = job_record.job_id
        repo.update_job_status(job_id, JobStatus.extracting)

        extraction_repo = ExtractionRepository(data_dir=target_data_dir)
        classification_repo = ClassificationRepository(data_dir=target_data_dir)
        taxonomy_repo = TaxonomyRepository(data_dir=target_data_dir)
        decision_log_repo = DecisionLogRepository(data_dir=target_data_dir)
        model_repo = ModelRepository(data_dir=target_data_dir)

        # Seed isolated taxonomy with benchmark base entries
        active_tax = taxonomy_repo.load_taxonomy()
        for base_entry in [
            "Net Income",
            "Interest Expense",
            "Income Tax Expense",
            "Depreciation & Amortization",
            "Stock-based compensation",
            "Stock-Based Compensation",
            "Operating Income",
            "Restructuring Charges",
            "Litigation settlement",
            "Litigation Charges",
            "Lease adjustments",
            "Lease Adjustments",
            "M&A transaction costs",
            "Acquisition-Related Expenses",
            "Other non-operating income",
            "Gain/Loss on Divestitures",
            "Adjusted EBITDA",
        ]:
            if base_entry not in active_tax:
                active_tax.append(base_entry)
        taxonomy_repo.save_taxonomy(active_tax)

        isolated_pdf_path = repo.get_pdf_path(job_id)

        # Stage 1: Docling structural parse
        current_stage = "extraction"
        docling_t0 = time.perf_counter()
        docling_items = parse_pdf(isolated_pdf_path, job_record.filename)
        docling_t1 = time.perf_counter()
        runtimes.docling_time_seconds = round(docling_t1 - docling_t0, 4)
        extraction_repo.save_docling_items(job_id, docling_items)

        # Stage 2: PyMuPDF 0-1000 coordinate normalization
        coord_t0 = time.perf_counter()
        normalized_items = normalize_coordinates(isolated_pdf_path, docling_items)
        coord_t1 = time.perf_counter()
        runtimes.coordinate_norm_time_seconds = round(coord_t1 - coord_t0, 4)
        extraction_repo.save_normalized_items(job_id, normalized_items)

        # Stage 3: Assembler & Stage 4: Confidence Scoring & Stage 5: Extraction Summary
        score_t0 = time.perf_counter()
        extracted_records = assemble_records(normalized_items)
        extraction_repo.save_extracted_records(job_id, extracted_records)

        scored_records = score_records(extracted_records, normalized_items)
        extraction_repo.save_scored_records(job_id, scored_records)

        image_only_pages = count_image_only_pages(isolated_pdf_path)
        extraction_summary = create_extraction_summary(
            scored_records, image_only_page_count=image_only_pages
        )
        extraction_repo.save_extraction_summary(job_id, extraction_summary)
        score_t1 = time.perf_counter()
        runtimes.assembly_and_scoring_time_seconds = round(score_t1 - score_t0, 4)
        runtimes.extraction_time_seconds = round(
            runtimes.docling_time_seconds
            + runtimes.coordinate_norm_time_seconds
            + runtimes.assembly_and_scoring_time_seconds,
            4,
        )

        # Stage 6: Classification & Taxonomy Normalization
        current_stage = "classification"
        classif_t0 = time.perf_counter()
        client = classifier_client or get_default_classifier_client()
        active_taxonomy = taxonomy_repo.load_taxonomy()

        batch_result = dispatch_records_to_classifier(scored_records, client)
        classified_records = normalize_records(
            scored_records, batch_result, active_taxonomy
        )
        classification_repo.save_classified_records(job_id, classified_records)

        log_entries = build_log_entries(job_id, batch_result, active_taxonomy)
        decision_log_repo.log_batch_calls(job_id, log_entries)
        classif_t1 = time.perf_counter()
        runtimes.classification_time_seconds = round(classif_t1 - classif_t0, 4)

        # Stage 7: Formula Engine
        current_stage = "formula_engine"
        formula_t0 = time.perf_counter()
        formula_inputs = read_formula_inputs(classified_records)
        target_metric = filing.metadata.target_metric or "Adjusted EBITDA"
        formula_tree = build_formula_tree(formula_inputs, target_metric=target_metric)
        formula_t1 = time.perf_counter()
        runtimes.formula_time_seconds = round(formula_t1 - formula_t0, 4)

        # Stage 8: Excel Export & Provenance Tagging
        current_stage = "excel_export"
        gen_t0 = time.perf_counter()
        generation_result = generate_workbook(
            formula_tree,
            job_id=job_id,
            output_dir=target_data_dir,
        )
        provenance_count = 0
        if generation_result.is_success and generation_result.provenance_records:
            model_repo.save_provenance_records(
                job_id, generation_result.provenance_records
            )
            provenance_count = len(generation_result.provenance_records)
        gen_t1 = time.perf_counter()
        runtimes.generation_time_seconds = round(gen_t1 - gen_t0, 4)

        repo.update_job_status(job_id, JobStatus.done)

        total_runtime = round(time.perf_counter() - start_total_time, 4)
        runtimes.total_time_seconds = total_runtime
        nfr3_compliant = total_runtime <= NFR3_MAX_RUNTIME_SECONDS

        return BenchmarkFilingExecutionResult(
            filing_id=filing.metadata.filing_id,
            company_name=filing.metadata.company_name,
            job_id=job_id,
            success=True,
            page_count=filing.metadata.page_count,
            runtimes=runtimes,
            nfr3_compliant=nfr3_compliant,
            scored_records=scored_records,
            classified_records=classified_records,
            extraction_summary=extraction_summary,
            total_cells_generated=generation_result.total_cells_generated,
            provenance_count=provenance_count,
            isolated_data_dir=str(target_data_dir),
        )

    except Exception as exc:  # noqa: BLE001
        total_runtime = round(time.perf_counter() - start_total_time, 4)
        runtimes.total_time_seconds = total_runtime
        logger.error(
            "Benchmark execution failed for filing %s in stage %s: %s",
            filing.metadata.filing_id,
            current_stage,
            exc,
        )
        return BenchmarkFilingExecutionResult(
            filing_id=filing.metadata.filing_id,
            company_name=filing.metadata.company_name,
            job_id=job_id if "job_id" in locals() else "uninitialized",
            success=False,
            error_stage=current_stage,
            error_detail=str(exc),
            page_count=filing.metadata.page_count,
            runtimes=runtimes,
            nfr3_compliant=total_runtime <= NFR3_MAX_RUNTIME_SECONDS,
            isolated_data_dir=str(target_data_dir),
        )


def _infer_error_stage(runtimes: StageRuntimes) -> str:
    """Infers the failing stage based on completed runtime markers."""
    if runtimes.docling_time_seconds == 0.0:
        return "extraction"
    if runtimes.coordinate_norm_time_seconds == 0.0:
        return "extraction"
    if runtimes.assembly_and_scoring_time_seconds == 0.0:
        return "extraction"
    if runtimes.classification_time_seconds == 0.0:
        return "classification"
    if runtimes.formula_time_seconds == 0.0:
        return "formula_engine"
    if runtimes.generation_time_seconds == 0.0:
        return "excel_export"
    return "unknown"


def run_benchmark_corpus(
    corpus: list[BenchmarkFiling] | None = None,
    corpus_dir: Path | str | None = None,
    output_base_dir: Path | None = None,
    classifier_client: GroqClassifierClient | None = None,
) -> BenchmarkCorpusExecutionResult:
    """
    Executes the full pipeline against all filings in the benchmark corpus.
    """
    filings = corpus if corpus is not None else load_corpus(corpus_dir)
    results: list[BenchmarkFilingExecutionResult] = []
    total_runtime = 0.0

    for idx, filing in enumerate(filings):
        filing_out_dir = (
            output_base_dir / filing.metadata.filing_id if output_base_dir else None
        )
        res = run_benchmark_filing(
            filing,
            corpus_dir=corpus_dir,
            output_dir=filing_out_dir,
            classifier_client=classifier_client,
        )
        results.append(res)
        total_runtime += res.runtimes.total_time_seconds

    successful_count = sum(1 for r in results if r.success)
    failed_count = len(results) - successful_count
    avg_runtime = round(total_runtime / len(results), 4) if results else 0.0
    all_nfr3 = all(r.nfr3_compliant for r in results)

    return BenchmarkCorpusExecutionResult(
        corpus_name="Footnote Benchmark Corpus",
        total_filings=len(results),
        successful_filings=successful_count,
        failed_filings=failed_count,
        total_runtime_seconds=round(total_runtime, 4),
        average_filing_runtime_seconds=avg_runtime,
        all_nfr3_compliant=all_nfr3,
        filing_results=results,
    )
