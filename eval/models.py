"""
Data models for the Footnote Evaluation Harness (Feature 9).

Provides Pydantic models for benchmark corpus specifications, ground-truth annotations,
filing metadata, and corpus validation results.

Frozen schema fields (value, label, page, bbox, source_file) are preserved per CONSTITUTION §2.3.
"""

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


class CorpusValidationResult(BaseModel):
    """
    Result summary of validating the benchmark corpus.
    """

    valid: bool
    filing_count: int
    total_items: int
    errors: list[str] = []
    warnings: list[str] = []
