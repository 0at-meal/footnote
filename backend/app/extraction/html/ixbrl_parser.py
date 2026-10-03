"""
Inline XBRL (iXBRL) Parser for SEC Filings (FN-021).

Extracts authoritative GAAP facts from inline XBRL tags (e.g. us-gaap:NetIncomeLoss)
for cross-checks and validation against non-GAAP figures.
"""

import logging
import re

from bs4 import BeautifulSoup, Tag

from app.extraction.html.models import IxbrlFact

logger = logging.getLogger(__name__)

_US_GAAP_NAME = re.compile(r"^us-gaap:", re.IGNORECASE)


def _attr(tag: Tag, *names: str) -> str | None:
    """First non-empty attribute value as a string (bs4 may return a list for multi-valued attrs)."""
    for name in names:
        value = tag.get(name)
        if isinstance(value, list):
            value = " ".join(value)
        if value:
            return str(value)
    return None


def _has_us_gaap_name(tag: Tag) -> bool:
    return bool(_US_GAAP_NAME.match(_attr(tag, "name") or ""))


def parse_ixbrl_facts(soup: BeautifulSoup) -> list[IxbrlFact]:
    """
    Parses authoritative GAAP facts from iXBRL elements in an SEC EDGAR HTML filing.

    Looks for tags like <ix:nonfraction> or elements with ix concepts.
    """
    facts: list[IxbrlFact] = []

    # 1. Map contexts to dates
    # <xbrli:context id="c-1"> ... <xbrli:endDate>2024-09-30</xbrli:endDate> ...
    context_dates: dict[str, str] = {}
    for ctx in soup.find_all(re.compile(r"^(?:xbrli:)?context$", re.IGNORECASE)):
        ctx_id = _attr(ctx, "id")
        if not ctx_id:
            continue
        # Find period
        end_date = ctx.find(re.compile(r"^(?:xbrli:)?enddate$", re.IGNORECASE))
        if end_date and end_date.get_text(strip=True):
            context_dates[ctx_id] = end_date.get_text(strip=True)
            continue
        instant = ctx.find(re.compile(r"^(?:xbrli:)?instant$", re.IGNORECASE))
        if instant and instant.get_text(strip=True):
            context_dates[ctx_id] = instant.get_text(strip=True)
            continue

    # 2. Find all <ix:nonfraction> tags
    # Also support tag names without namespace prefix if stripped by parser
    ix_tags = soup.find_all(re.compile(r"^(?:ix:)?nonfraction$", re.IGNORECASE))
    if not ix_tags:
        # Check elements having 'name' attribute starting with us-gaap:
        ix_tags = soup.find_all(_has_us_gaap_name)

    for tag in ix_tags:
        concept = _attr(tag, "name", "concept")
        if not concept:
            continue

        raw_text = tag.get_text(strip=True)
        if not raw_text:
            continue

        # Parse scale and sign
        scale_val = 0
        try:
            scale_str = _attr(tag, "scale")
            if scale_str is not None:
                scale_val = int(scale_str)
        except (ValueError, TypeError):
            scale_val = 0

        sign_mult = -1 if (_attr(tag, "sign") or "").strip() == "-" else 1

        # Clean number
        clean_num_str = raw_text.replace(",", "").replace("$", "").strip()
        # Handle parentheses
        if clean_num_str.startswith("(") and clean_num_str.endswith(")"):
            clean_num_str = clean_num_str[1:-1].strip()
            sign_mult = -1

        try:
            base_val = float(clean_num_str)
        except ValueError:
            continue

        final_val = base_val * (10 ** scale_val) * sign_mult

        ctx_ref = _attr(tag, "contextref", "contextRef") or ""
        period_str = context_dates.get(ctx_ref, ctx_ref)

        unit = _attr(tag, "unitref", "unitRef") or "USD"
        decimals = _attr(tag, "decimals")

        facts.append(
            IxbrlFact(
                concept=concept,
                value=final_val,
                context_period=period_str,
                scale=scale_val,
                sign=sign_mult,
                unit=unit,
                decimals=decimals,
            )
        )

    return facts
