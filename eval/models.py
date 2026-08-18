"""
Data models for the Footnote Evaluation Harness (Feature 9).

Provides Pydantic models for benchmark corpus specifications, ground-truth annotations,
filing metadata, and corpus validation results.

Frozen schema fields (value, label, page, bbox, source_file) are preserved per CONSTITUTION §2.3.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class GroundTruthBbox(BaseModel):
    """
    W3C Web Annotation-style bounding box in normalized 0-1000 coordinate space.
    """

    x0: float = Field(
        ..., ge=0.0, le=1000.0, description="Left coordinate in 0-1000 space"
    )
    y0: float = Field(
        ..., ge=0.0, le=1000.0, description="Top coordinate in 0-1000 space"
    )
    x1: float = Field(
        ..., ge=0.0, le=1000.0, description="Right coordinate in 0-1000 space"
    )
    y1: float = Field(
        ..., ge=0.0, le=1000.0, description="Bottom coordinate in 0-1000 space"
    )

    @model_validator(mode="after")
    def validate_coordinates(self) -> "GroundTruthBbox":
        if self.x0 >= self.x1:
            raise ValueError(
                f"Invalid x coordinates: x0 ({self.x0}) must be strictly less than x1 ({self.x1})"
            )
        if self.y0 >= self.y1:
            raise ValueError(
                f"Invalid y coordinates: y0 ({self.y0}) must be strictly less than y1 ({self.y1})"
            )
        return self

    def to_dict(self) -> dict[str, float]:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


class GroundTruthItem(BaseModel):
    """
    Schema-validated ground-truth specification for an expected line item.
    """

    value: str = Field(
        ..., description="Raw expected numeric/text string representation"
    )
    label: str = Field(..., description="Raw structural label in source document")
    normalized_label: str = Field(..., description="Target standardized taxonomy label")
    page: int = Field(..., ge=1, description="1-indexed page number in the source PDF")
    bbox: GroundTruthBbox = Field(
        ..., description="Normalized bounding box coordinates"
    )
    source_file: str = Field(..., description="PDF source filename")
    is_optional: bool = Field(
        default=False, description="Whether this line item is optional per EC-1"
    )
    section: str | None = Field(
        default=None, description="Document section or footnote description"
    )

    @field_validator("value")
    @classmethod
    def validate_value_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ground-truth item 'value' cannot be empty")
        return v.strip()

    @field_validator("label")
    @classmethod
    def validate_label_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ground-truth item 'label' cannot be empty")
        return v.strip()

    @field_validator("normalized_label")
    @classmethod
    def validate_normalized_label_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Ground-truth item 'normalized_label' cannot be empty")
        return v.strip()

    @property
    def parsed_numeric_value(self) -> float | None:
        """
        Parses raw string representation into float for semantic numeric comparisons (EC-2).
        Handles negative values in parentheses e.g. '(1,234)' -> -1234.0, commas, and dollar signs.
        """
        val_str = self.value.strip()
        is_negative = False
        if val_str.startswith("(") and val_str.endswith(")"):
            is_negative = True
            val_str = val_str[1:-1].strip()
        val_str = val_str.replace("$", "").replace(",", "").strip()
        try:
            parsed = float(val_str)
            return -parsed if is_negative else parsed
        except ValueError:
            return None


class BenchmarkFilingMetadata(BaseModel):
    """
    Metadata for a curated benchmark filing.
    """

    filing_id: str = Field(..., description="Unique benchmark filing identifier")
    company_name: str = Field(..., description="Entity/Company name")
    ticker: str = Field(..., description="Stock ticker symbol")
    fiscal_year: int = Field(..., ge=1900, le=2100, description="Fiscal year")
    filing_type: str = Field(default="10-K", description="Filing type (e.g. 10-K)")
    pdf_filename: str = Field(
        ..., description="Name of the PDF file in the filing folder"
    )
    page_count: int = Field(..., ge=1, description="Total number of pages in the PDF")
    target_metric: str = Field(
        default="Adjusted EBITDA", description="Target metric for evaluation"
    )
    description: str | None = Field(
        default=None, description="Filing context notes or characteristics"
    )


class BenchmarkFiling(BaseModel):
    """
    Complete benchmark filing record containing metadata and ground truth items.
    """

    metadata: BenchmarkFilingMetadata
    ground_truth_items: list[GroundTruthItem]
    expected_reconciliation_total: float | None = Field(
        default=None,
        description="Expected final calculated metric value for the filing",
    )

    @field_validator("ground_truth_items")
    @classmethod
    def validate_items_non_empty(
        cls, v: list[GroundTruthItem]
    ) -> list[GroundTruthItem]:
        if not v:
            raise ValueError(
                "A benchmark filing must contain at least one ground-truth line item"
            )
        return v


class BenchmarkCorpusManifest(BaseModel):
    """
    Manifest file listing all benchmark filings in the corpus.
    """

    corpus_name: str = Field(
        default="Footnote Benchmark Corpus", description="Name of benchmark corpus"
    )
    corpus_version: str = Field(default="1.0.0", description="Corpus version")
    target_metric: str = Field(
        default="Adjusted EBITDA", description="Target evaluation metric"
    )
    filing_ids: list[str] = Field(
        ..., min_length=1, description="List of benchmark filing folder IDs"
    )


class BenchmarkCorpus(BaseModel):
    """
    Complete benchmark corpus specification comprising manifest and loaded filings.
    """

    manifest: BenchmarkCorpusManifest = Field(
        default_factory=lambda: BenchmarkCorpusManifest(filing_ids=[])
    )
    filings: list[BenchmarkFiling] = Field(default_factory=list)


class CorpusValidationResult(BaseModel):
    """
    Result summary of validating the benchmark corpus.
    """

    valid: bool
    filing_count: int
    total_items: int
    errors: list[str] = []
    warnings: list[str] = []


class StageRuntimes(BaseModel):
    """
    Granular runtime measurements in seconds for each pipeline stage.
    """

    docling_time_seconds: float = Field(default=0.0, ge=0.0)
    coordinate_norm_time_seconds: float = Field(default=0.0, ge=0.0)
    assembly_and_scoring_time_seconds: float = Field(default=0.0, ge=0.0)
    extraction_time_seconds: float = Field(default=0.0, ge=0.0)
    classification_time_seconds: float = Field(default=0.0, ge=0.0)
    formula_time_seconds: float = Field(default=0.0, ge=0.0)
    generation_time_seconds: float = Field(default=0.0, ge=0.0)
    total_time_seconds: float = Field(default=0.0, ge=0.0)


class BenchmarkFilingExecutionResult(BaseModel):
    """
    Complete execution result for a single benchmark filing run through the production pipeline.
    """

    filing_id: str
    company_name: str
    job_id: str
    success: bool
    error_stage: str | None = None
    error_detail: str | None = None
    page_count: int
    runtimes: StageRuntimes
    nfr3_compliant: bool = Field(
        ...,
        description="True if total_time_seconds <= 300.0s (5-minute budget per NFR3)",
    )
    scored_records: list[Any] = Field(default_factory=list)
    classified_records: list[Any] = Field(default_factory=list)
    extraction_summary: Any | None = None
    total_cells_generated: int = 0
    provenance_count: int = 0
    isolated_data_dir: str | None = None


class BenchmarkCorpusExecutionResult(BaseModel):
    """
    Aggregate execution metrics across all filings in the benchmark corpus.
    """

    corpus_name: str
    total_filings: int
    successful_filings: int
    failed_filings: int
    total_runtime_seconds: float
    average_filing_runtime_seconds: float
    all_nfr3_compliant: bool
    filing_results: list[BenchmarkFilingExecutionResult]


class FailurePattern(str, Enum):
    """
    Structural failure pattern taxonomy for layout and extraction anomalies (AC-7).
    """

    multi_column_bleed = "multi_column_bleed"
    merged_cell_misalignment = "merged_cell_misalignment"
    footnote_severance = "footnote_severance"
    sign_mismatch = "sign_mismatch"
    missing_item = "missing_item"
    spurious_item = "spurious_item"
    unrecognized_label = "unrecognized_label"
    none = "none"


class ItemMatchStatus(str, Enum):
    """
    Status of aligning an extracted line item against ground truth.
    """

    exact_match = "exact_match"
    value_mismatch = "value_mismatch"
    classification_mismatch = "classification_mismatch"
    localization_error = "localization_error"
    missed_item = "missed_item"
    spurious_item = "spurious_item"


class LineItemDiff(BaseModel):
    """
    Detailed comparison between a ground-truth line item and the extracted pipeline output.
    """

    ground_truth_label: str | None = None
    ground_truth_normalized_label: str | None = None
    ground_truth_value: str | None = None
    extracted_label: str | None = None
    extracted_normalized_label: str | None = None
    extracted_value: str | None = None
    page: int = 1
    iou: float = Field(default=0.0, ge=0.0, le=1.0)
    status: ItemMatchStatus
    failure_pattern: FailurePattern = FailurePattern.none
    is_optional: bool = False
    detail: str | None = None


class LayerMetricsSummary(BaseModel):
    """
    Isolated error counts per architectural pipeline layer (AC-4).
    """

    extraction_errors: int = Field(default=0, ge=0)
    classification_errors: int = Field(default=0, ge=0)
    generation_errors: int = Field(default=0, ge=0)


class FilingAccuracyMetrics(BaseModel):
    """
    Structured evaluation and accuracy metrics for a single benchmark filing (AC-3, AC-4, AC-5).
    """

    filing_id: str
    company_name: str
    total_ground_truth_items: int
    extracted_items_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1_score: float = Field(ge=0.0, le=1.0)
    line_item_accuracy_percentage: float = Field(ge=0.0, le=100.0)
    target_accuracy_achieved: bool = Field(
        ..., description="True if line_item_accuracy_percentage >= 90.0% (AC-3)"
    )
    failed_extraction: bool = Field(
        ...,
        description="True if non-auto-accepted items exceed 15.0% threshold (AC-5, EC-3)",
    )
    non_auto_accepted_count: int = Field(default=0, ge=0)
    non_auto_accepted_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    layer_errors: LayerMetricsSummary = Field(default_factory=LayerMetricsSummary)
    failure_patterns: list[FailurePattern] = Field(default_factory=list)
    line_item_diffs: list[LineItemDiff] = Field(default_factory=list)
    runtimes: StageRuntimes = Field(default_factory=StageRuntimes)
    nfr3_compliant: bool = True


class CorpusAccuracyMetrics(BaseModel):
    """
    Corpus-wide aggregate evaluation metrics with mandatory CONSTITUTION §6.13 governance disclosure.
    """

    corpus_name: str
    total_filings: int
    successful_filings: int
    failed_extraction_filings_count: int
    total_ground_truth_items: int
    total_extracted_items: int
    total_true_positives: int
    total_false_positives: int
    total_false_negatives: int
    macro_precision: float = Field(ge=0.0, le=1.0)
    macro_recall: float = Field(ge=0.0, le=1.0)
    macro_f1_score: float = Field(ge=0.0, le=1.0)
    micro_precision: float = Field(ge=0.0, le=1.0)
    micro_recall: float = Field(ge=0.0, le=1.0)
    micro_f1_score: float = Field(ge=0.0, le=1.0)
    corpus_line_item_accuracy_percentage: float = Field(ge=0.0, le=100.0)
    target_accuracy_achieved: bool = Field(
        ...,
        description="True if corpus_line_item_accuracy_percentage >= 90.0% (AC-3)",
    )
    layer_errors: LayerMetricsSummary = Field(default_factory=LayerMetricsSummary)
    failure_pattern_counts: dict[str, int] = Field(default_factory=dict)
    filing_metrics: list[FilingAccuracyMetrics] = Field(default_factory=list)
    benchmark_corpus_size: int = Field(
        ...,
        description="Mandatory disclosure: count of filings in benchmark corpus (CONSTITUTION §6.13)",
    )
    total_manual_review_items: int = Field(
        default=0,
        ge=0,
        description="Mandatory disclosure: total items requiring human review or manual correction (CONSTITUTION §6.13)",
    )
    manual_review_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Mandatory disclosure: percentage of items requiring human review (CONSTITUTION §6.13)",
    )
    mandatory_governance_disclosure: str = Field(
        ...,
        description="Explicit formatted statement of corpus size and human review count per CONSTITUTION §6.13",
    )
