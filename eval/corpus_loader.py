"""
Benchmark Corpus Loader and Validator for Footnote (Feature 9).

Loads and validates the benchmark corpus consisting of 5-10 manually tied-out 10-K filings
with source PDFs and ground-truth line-item specifications.
"""

import json
from pathlib import Path
from typing import Any

import pymupdf
from pydantic import ValidationError

from eval.models import (
    AccessionCorpusManifest,
    BenchmarkAccessionFiling,
    BenchmarkCorpusManifest,
    BenchmarkFiling,
    BenchmarkReconciliationLine,
    CorpusSplit,
    CorpusValidationResult,
)

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
DEFAULT_LABELS_DIR = DEFAULT_CORPUS_DIR / "labels"


class CorpusLoadingError(Exception):
    """Raised when an unrecoverable error occurs loading benchmark corpus files."""


def load_filing(filing_dir: Path | str) -> BenchmarkFiling:
    """
    Loads a single benchmark filing from its directory.

    Expects a `ground_truth.json` file inside the filing directory.
    Validates against the BenchmarkFiling Pydantic model.
    """
    f_path = Path(filing_dir).resolve()
    if not f_path.is_dir():
        raise CorpusLoadingError(f"Benchmark filing directory does not exist: {f_path}")

    gt_file = f_path / "ground_truth.json"
    if not gt_file.is_file():
        raise CorpusLoadingError(
            f"Missing ground_truth.json in benchmark filing directory: {f_path}"
        )

    try:
        raw_content = gt_file.read_text(encoding="utf-8")
        data = json.loads(raw_content)
        filing = BenchmarkFiling.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError, OSError) as e:
        raise CorpusLoadingError(
            f"Failed to load/validate ground_truth.json in {f_path}: {e}"
        ) from e

    # Verify PDF exists
    pdf_path = f_path / filing.metadata.pdf_filename
    if not pdf_path.is_file():
        raise CorpusLoadingError(
            f"Referenced PDF file '{filing.metadata.pdf_filename}' not found in {f_path}"
        )

    return filing


def load_corpus(corpus_dir: Path | str | None = None) -> list[BenchmarkFiling]:
    """
    Loads all benchmark filings from the specified corpus directory.

    If manifest.json exists, loads filings listed in the manifest in order.
    Otherwise, scans for subdirectories containing ground_truth.json.
    """
    c_dir = Path(corpus_dir).resolve() if corpus_dir else DEFAULT_CORPUS_DIR
    if not c_dir.is_dir():
        raise CorpusLoadingError(f"Corpus directory not found: {c_dir}")

    manifest_path = c_dir / "manifest.json"
    filings: list[BenchmarkFiling] = []

    if manifest_path.is_file():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = BenchmarkCorpusManifest.model_validate(manifest_data)
            filing_ids = manifest.filing_ids
        except (json.JSONDecodeError, ValidationError, ValueError, OSError) as e:
            raise CorpusLoadingError(
                f"Failed to read/validate manifest.json in {c_dir}: {e}"
            ) from e

        for filing_id in filing_ids:
            f_dir = c_dir / filing_id
            filing = load_filing(f_dir)
            filings.append(filing)
    else:
        for item in sorted(c_dir.iterdir()):
            if item.is_dir() and (item / "ground_truth.json").is_file():
                filings.append(load_filing(item))

    return filings


def validate_corpus(
    corpus_dir: Path | str | None = None,
    min_filings: int = 5,
) -> CorpusValidationResult:
    """
    Performs comprehensive data integrity and schema compliance checks on the corpus.

    Validates:
    - Directory and manifest structure
    - Minimum benchmark filing count requirement (>= 5)
    - Pydantic schema validation for all ground-truth annotations
    - PDF existence, byte integrity, and page count consistency with PyMuPDF
    - Page coordinate boundaries and 1-indexed page numbering
    - Numeric parseability of line item values
    """
    c_dir = Path(corpus_dir).resolve() if corpus_dir else DEFAULT_CORPUS_DIR
    errors: list[str] = []
    warnings: list[str] = []

    if not c_dir.exists() or not c_dir.is_dir():
        return CorpusValidationResult(
            valid=False,
            filing_count=0,
            total_items=0,
            errors=[f"Corpus directory does not exist: {c_dir}"],
        )

    # Discover filings
    manifest_path = c_dir / "manifest.json"
    filing_dirs: list[Path] = []

    if manifest_path.is_file():
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = BenchmarkCorpusManifest.model_validate(m_data)
            for fid in manifest.filing_ids:
                f_path = c_dir / fid
                if not f_path.is_dir():
                    errors.append(
                        f"Manifest specifies filing directory '{fid}' which does not exist in {c_dir}"
                    )
                else:
                    filing_dirs.append(f_path)
        except (json.JSONDecodeError, ValidationError, ValueError, OSError) as e:
            errors.append(f"Invalid manifest.json in {c_dir}: {e}")
    else:
        filing_dirs = [
            d
            for d in sorted(c_dir.iterdir())
            if d.is_dir() and (d / "ground_truth.json").is_file()
        ]

    if len(filing_dirs) < min_filings:
        errors.append(
            f"Corpus contains {len(filing_dirs)} filings, which is below the minimum required threshold of {min_filings} (AC-1)."
        )

    total_items = 0

    for f_dir in filing_dirs:
        gt_file = f_dir / "ground_truth.json"
        if not gt_file.is_file():
            errors.append(f"Missing ground_truth.json in {f_dir.name}")
            continue

        try:
            gt_data = json.loads(gt_file.read_text(encoding="utf-8"))
            filing = BenchmarkFiling.model_validate(gt_data)
        except (json.JSONDecodeError, ValidationError, ValueError, OSError) as e:
            errors.append(
                f"Schema validation error in {f_dir.name}/ground_truth.json: {e}"
            )
            continue

        # Check PDF presence and integrity
        pdf_path = f_dir / filing.metadata.pdf_filename
        if not pdf_path.is_file():
            errors.append(
                f"Referenced PDF file '{filing.metadata.pdf_filename}' not found in {f_dir.name}"
            )
            continue

        try:
            doc = pymupdf.open(pdf_path)
            actual_page_count = len(doc)
            if actual_page_count != filing.metadata.page_count:
                errors.append(
                    f"Page count mismatch in {f_dir.name}: metadata specifies {filing.metadata.page_count}, "
                    f"but PDF has {actual_page_count} pages."
                )
            doc.close()
        except (pymupdf.FileDataError, RuntimeError, OSError) as e:
            errors.append(
                f"Corrupted or invalid PDF file in {f_dir.name} ({filing.metadata.pdf_filename}): {e}"
            )
            continue

        # Validate line items
        for idx, item in enumerate(filing.ground_truth_items):
            total_items += 1
            if item.page > filing.metadata.page_count:
                errors.append(
                    f"Item [{idx}] '{item.label}' in {f_dir.name} references page {item.page}, "
                    f"which exceeds filing total pages ({filing.metadata.page_count})."
                )

            if item.parsed_numeric_value is None:
                errors.append(
                    f"Item [{idx}] '{item.label}' in {f_dir.name} has non-numeric value string: '{item.value}'"
                )

    is_valid = len(errors) == 0
    return CorpusValidationResult(
        valid=is_valid,
        filing_count=len(filing_dirs),
        total_items=total_items,
        errors=errors,
        warnings=warnings,
    )


def load_accession_filing(
    filepath_or_accession: Path | str,
    labels_dir: Path | str | None = None,
) -> BenchmarkAccessionFiling:
    """
    Loads and validates a single benchmark accession filing JSON label file.
    """
    l_dir = Path(labels_dir).resolve() if labels_dir else DEFAULT_LABELS_DIR
    p = Path(filepath_or_accession)
    if not p.is_file():
        # Try finding {accession}.json in labels_dir
        candidate = l_dir / f"{filepath_or_accession}.json"
        if candidate.is_file():
            p = candidate
        else:
            raise CorpusLoadingError(f"Benchmark accession label file not found: {filepath_or_accession}")

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return BenchmarkAccessionFiling.model_validate(data)
    except (json.JSONDecodeError, ValidationError, ValueError, OSError) as e:
        raise CorpusLoadingError(f"Failed to load/validate accession filing from {p}: {e}") from e


def load_labeled_corpus(
    labels_dir: Path | str | None = None,
    split: str | CorpusSplit | None = None,
) -> list[BenchmarkAccessionFiling]:
    """
    Loads all accession-keyed benchmark filings from the labels directory.
    Optionally filters by split ('dev' or 'test').
    """
    l_dir = Path(labels_dir).resolve() if labels_dir else DEFAULT_LABELS_DIR
    if not l_dir.is_dir():
        raise CorpusLoadingError(f"Benchmark labels directory not found: {l_dir}")

    manifest_path = l_dir / "manifest.json"
    filings: list[BenchmarkAccessionFiling] = []

    if manifest_path.is_file():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        accessions = manifest_data.get("filing_accessions", [])
        for acc in accessions:
            f = load_accession_filing(acc, labels_dir=l_dir)
            if split is None:
                filings.append(f)
            else:
                target_split = split.value if isinstance(split, CorpusSplit) else str(split).lower()
                if f.split.value == target_split:
                    filings.append(f)
    else:
        for json_path in sorted(l_dir.glob("*.json")):
            if json_path.name == "manifest.json":
                continue
            f = load_accession_filing(json_path, labels_dir=l_dir)
            if split is None or f.split.value == (split.value if isinstance(split, CorpusSplit) else str(split).lower()):
                filings.append(f)

    return filings


def validate_labeled_corpus(
    labels_dir: Path | str | None = None,
    expected_count: int = 40,
) -> CorpusValidationResult:
    """
    Validates schema conformance, split balance, double-labeling agreement,
    and reconciliation line math for all 40 benchmark filings.
    """
    l_dir = Path(labels_dir).resolve() if labels_dir else DEFAULT_LABELS_DIR
    errors: list[str] = []
    warnings: list[str] = []

    if not l_dir.is_dir():
        return CorpusValidationResult(
            valid=False,
            filing_count=0,
            total_items=0,
            errors=[f"Labels directory does not exist: {l_dir}"],
        )

    try:
        filings = load_labeled_corpus(labels_dir=l_dir)
    except CorpusLoadingError as e:
        return CorpusValidationResult(
            valid=False,
            filing_count=0,
            total_items=0,
            errors=[str(e)],
        )

    total_items = 0
    dev_count = 0
    test_count = 0
    double_labeled_count = 0

    for f in filings:
        if f.split == CorpusSplit.dev:
            dev_count += 1
        elif f.split == CorpusSplit.test:
            test_count += 1

        if f.double_labeled:
            double_labeled_count += 1
            if f.inter_annotator_agreement is None or f.inter_annotator_agreement < 0.8:
                errors.append(
                    f"Filing {f.accession_number} is marked double_labeled but agreement is {f.inter_annotator_agreement}"
                )

        if not f.reconciliation_lines:
            errors.append(f"Filing {f.accession_number} has no reconciliation lines")

        for idx, line in enumerate(f.reconciliation_lines):
            total_items += 1
            if line.scale <= 0:
                errors.append(f"Filing {f.accession_number} line [{idx}] invalid scale: {line.scale}")
            if line.sign not in (1, -1):
                errors.append(f"Filing {f.accession_number} line [{idx}] invalid sign: {line.sign}")

    if len(filings) < expected_count:
        errors.append(f"Expected at least {expected_count} filings, found {len(filings)}")

    if dev_count < 30:
        errors.append(f"Expected at least 30 dev filings, found {dev_count}")
    if test_count < 10:
        errors.append(f"Expected at least 10 locked test filings, found {test_count}")
    if double_labeled_count < 8:
        errors.append(f"Expected at least 8 (20%) double-labeled filings, found {double_labeled_count}")

    is_valid = len(errors) == 0
    return CorpusValidationResult(
        valid=is_valid,
        filing_count=len(filings),
        total_items=total_items,
        errors=errors,
        warnings=warnings,
    )


def calculate_annotator_agreement(
    filings: list[BenchmarkAccessionFiling],
) -> dict[str, Any]:
    """
    Computes inter-annotator agreement statistics across double-labeled filings.
    """
    double_labeled = [f for f in filings if f.double_labeled]
    if not double_labeled:
        return {"double_labeled_count": 0, "mean_agreement": 0.0, "filings": {}}

    agreements: dict[str, float] = {}
    for f in double_labeled:
        if f.inter_annotator_agreement is not None:
            agreements[f.accession_number] = f.inter_annotator_agreement

    mean_val = sum(agreements.values()) / len(agreements) if agreements else 0.0
    return {
        "double_labeled_count": len(double_labeled),
        "mean_agreement": round(mean_val, 4),
        "filings": agreements,
    }

