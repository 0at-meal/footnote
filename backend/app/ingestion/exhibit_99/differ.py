"""
Bridge Differ and Deduplication Engine for 8-K EX-99.1 vs 10-Q/10-K (FN-022).

Enforces:
- 'Latest filed wins' deduplication precedence: 10-Q supersedes 8-K earnings release.
- Dual provenance: preserves both release locator and periodic filing locator.
- Line-item diffing with discrepancy detection.
- Segregation of forward-looking (guidance) items.
"""

import logging
import re

from app.extraction.models import ExtractedRecord
from app.ingestion.exhibit_99.models import (
    BridgeDiffReport,
    CanonicalBridgeResult,
    DiffItem,
)

logger = logging.getLogger(__name__)


def _normalize_metric_key(label: str) -> str:
    """Normalizes label text for matching between 8-K release and 10-Q."""
    # Take the last component of a hierarchical label if ' > ' is present
    parts = label.split(" > ")
    leaf = parts[-1].strip().lower()
    # Remove footnote markers like (1), *, [a]
    cleaned = re.sub(r"\s*(?:\([a-z0-9]\)|\[[a-z0-9]\]|\*+)\s*$", "", leaf)
    # Remove non-alphanumeric chars
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    return cleaned


def _extract_numeric_float(value_str: str) -> float | None:
    """Extracts a numeric float from an ExtractedRecord string value."""
    s = value_str.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = f"-{s[1:-1].strip()}"
    try:
        return float(s)
    except ValueError:
        return None


def diff_bridges(
    release_records: list[ExtractedRecord],
    filing_records: list[ExtractedRecord],
    cik: str = "",
    period: str = "",
    release_accession: str = "",
    filing_accession: str = "",
) -> BridgeDiffReport:
    """
    Diffs non-GAAP reconciliation line items between 8-K earnings release and 10-Q/10-K.
    """
    # Group by normalized metric key
    release_map: dict[str, ExtractedRecord] = {}
    for r in release_records:
        k = _normalize_metric_key(r.label)
        if k:
            release_map[k] = r

    filing_map: dict[str, ExtractedRecord] = {}
    for f in filing_records:
        k = _normalize_metric_key(f.label)
        if k:
            filing_map[k] = f

    all_keys = set(release_map.keys()) | set(filing_map.keys())
    diff_items: list[DiffItem] = []
    has_discrepancies = False

    for k in sorted(all_keys):
        rel_rec = release_map.get(k)
        fil_rec = filing_map.get(k)

        metric_name = fil_rec.label if fil_rec else (rel_rec.label if rel_rec else k)
        rel_val = _extract_numeric_float(rel_rec.value) if rel_rec else None
        fil_val = _extract_numeric_float(fil_rec.value) if fil_rec else None

        rel_loc = rel_rec.locator if rel_rec else None
        fil_loc = fil_rec.locator if fil_rec else None

        if rel_rec is not None and fil_rec is not None:
            # Both present
            if rel_val is not None and fil_val is not None:
                diff = fil_val - rel_val
                is_match = abs(diff) < 1e-4
                if not is_match:
                    has_discrepancies = True
                    status = "discrepancy"
                    notes = f"8-K value was {rel_val}, adjusted in 10-Q to {fil_val} (diff: {diff:+.2f})"
                else:
                    status = "match"
                    notes = "Values identical between 8-K release and 10-Q filing"
            else:
                diff = None
                is_match = rel_rec.value.strip() == fil_rec.value.strip()
                status = "match" if is_match else "discrepancy"
                notes = ""

            diff_items.append(
                DiffItem(
                    metric_name=metric_name,
                    period=period,
                    release_value=rel_val,
                    filing_value=fil_val,
                    difference=diff,
                    is_match=is_match,
                    status=status,
                    notes=notes,
                    release_locator=rel_loc,
                    filing_locator=fil_loc,
                )
            )
        elif rel_rec is not None:
            # Only in 8-K
            diff_items.append(
                DiffItem(
                    metric_name=metric_name,
                    period=period,
                    release_value=rel_val,
                    filing_value=None,
                    difference=None,
                    is_match=False,
                    status="release_only",
                    notes="Furnished in 8-K release but omitted from 10-Q filing",
                    release_locator=rel_loc,
                    filing_locator=None,
                )
            )
        else:
            # Only in 10-Q
            assert fil_rec is not None
            diff_items.append(
                DiffItem(
                    metric_name=metric_name,
                    period=period,
                    release_value=None,
                    filing_value=fil_val,
                    difference=None,
                    is_match=False,
                    status="filing_only",
                    notes="Disclosed in 10-Q filing but absent from initial 8-K release",
                    release_locator=None,
                    filing_locator=fil_loc,
                )
            )

    summary = (
        f"Diff completed for CIK {cik} ({period}): {len(diff_items)} items checked, "
        f"{sum(1 for i in diff_items if i.status == 'discrepancy')} discrepancies found."
    )

    return BridgeDiffReport(
        cik=cik,
        period=period,
        release_accession=release_accession,
        filing_accession=filing_accession,
        items=diff_items,
        has_discrepancies=has_discrepancies,
        summary=summary,
    )


def merge_dedupe_bridges(
    release_records: list[ExtractedRecord],
    filing_records: list[ExtractedRecord],
    cik: str = "",
    period: str = "",
    release_accession: str = "",
    filing_accession: str = "",
) -> CanonicalBridgeResult:
    """
    Merges 8-K and 10-Q bridge records adhering to 'latest filed wins' precedence.
    Also segregates guidance items and keeps diff report with dual provenance.
    """
    diff_report = diff_bridges(
        release_records=release_records,
        filing_records=filing_records,
        cik=cik,
        period=period,
        release_accession=release_accession,
        filing_accession=filing_accession,
    )

    # 1. Separate guidance records (from release or filing)
    canonical: list[ExtractedRecord] = []
    guidance: list[ExtractedRecord] = []

    for r in filing_records:
        if "guidance" in r.label.lower() or "outlook" in r.label.lower():
            guidance.append(r)
        else:
            canonical.append(r)

    # If filing records are empty (e.g. 10-Q not yet filed, only 8-K available),
    # 8-K records populate canonical bridge
    if not canonical:
        for r in release_records:
            if "guidance" in r.label.lower() or "outlook" in r.label.lower():
                guidance.append(r)
            else:
                canonical.append(r)
    else:
        # Also collect any unique guidance items from 8-K release
        filing_keys = {_normalize_metric_key(c.label) for c in canonical + guidance}
        for r in release_records:
            if "guidance" in r.label.lower() or "outlook" in r.label.lower():
                k = _normalize_metric_key(r.label)
                if k not in filing_keys:
                    guidance.append(r)

    return CanonicalBridgeResult(
        canonical_records=canonical,
        guidance_records=guidance,
        diff_report=diff_report,
    )
