"""
Detector for 8-K Item 2.02 and EX-99.1 Exhibits (FN-022).
"""

import re

from app.ingestion.edgar.models import FilingRef
from app.ingestion.exhibit_99.models import EarningsReleaseMetadata, ExhibitFormat

ITEM_2_02_PATTERN = re.compile(
    r"\b(item\s+2\.02|results\s+of\s+operations\s+and\s+financial\s+condition)\b",
    re.IGNORECASE,
)

GUIDANCE_PATTERN = re.compile(
    r"\b(guidance|outlook|forward-looking|future\s+outlook|full\s+year\s+\d{4}\s+outlook|financial\s+outlook)\b",
    re.IGNORECASE,
)


def is_item_2_02_text(text: str) -> bool:
    """Checks if text contains SEC Form 8-K Item 2.02 reference."""
    return bool(ITEM_2_02_PATTERN.search(text))


def classify_exhibit_format(filename: str) -> ExhibitFormat:
    """Classifies exhibit file format by extension."""
    lower = filename.lower()
    if lower.endswith((".htm", ".html")):
        return ExhibitFormat.HTML
    if lower.endswith(".pdf"):
        return ExhibitFormat.PDF
    if lower.endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        return ExhibitFormat.IMAGE
    return ExhibitFormat.UNSUPPORTED


def detect_earnings_release_exhibit(
    filing: FilingRef,
    raw_8k_content: str | None = None,
) -> EarningsReleaseMetadata | None:
    """
    Evaluates an 8-K filing to discover Item 2.02 earnings releases and EX-99.1 exhibits.
    """
    if filing.form != "8-K" and not filing.form.startswith("8-K"):
        return None

    has_item_202 = False
    if raw_8k_content and is_item_2_02_text(raw_8k_content):
        has_item_202 = True

    # Search for EX-99.1 in exhibits
    ex99 = next(
        (e for e in filing.exhibits if e.exhibit_number in ("EX-99.1", "EX-99")),
        None,
    )

    if not ex99:
        # Search for any exhibit with 99 in filename
        ex99 = next(
            (e for e in filing.exhibits if "ex99" in e.filename.lower() or "ex-99" in e.filename.lower()),
            None,
        )

    if not ex99 and not has_item_202:
        return None

    filename = ex99.filename if ex99 else None
    fmt = classify_exhibit_format(filename) if filename else ExhibitFormat.HTML
    url = ex99.url if ex99 else None

    return EarningsReleaseMetadata(
        accession=filing.accession,
        filing_date=filing.filed_at,
        period=filing.period,
        has_item_2_02=has_item_202,
        exhibit_number="EX-99.1",
        exhibit_filename=filename,
        exhibit_url=url,
        format=fmt,
    )


def is_guidance_text(text: str) -> bool:
    """Determines whether a table title or row indicates forward-looking / guidance reconciliations."""
    return bool(GUIDANCE_PATTERN.search(text))
