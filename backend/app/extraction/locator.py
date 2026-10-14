"""
Locator Union Schema.

Defines the discriminated union of provenance locators:
- PdfLocator: targeting page number, normalized 0-1000 bounding box, and source filename.
- HtmlLocator: targeting SEC EDGAR accession number, document/exhibit, DOM element path (XPath/CSS),
  optional character range, and direct SEC URL.

Enforces:
- Exact provenance locator preserved across all operations.
- Deterministic, backward-compatible deserialization and serialization.
"""

import re
from typing import Annotated, Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, model_validator

# https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{document}
_SEC_ARCHIVES_URL = re.compile(
    r"^https://www\.sec\.gov/Archives/edgar/data/[1-9]\d*/\d{18}/[^/#?]+$"
)


def sec_archives_url(
    cik: str | int | None,
    accession: str | None,
    document: str | None,
    text: str | None = None,
) -> str | None:
    """
    EDGAR Archives URL for a filing document, or None when it cannot be built.

    The CIK is required: CIK-less Archives URLs return 404 or redirect. `text`
    adds a text fragment (`#:~:text=`) so the browser scrolls to that text.
    """
    if cik is None or not accession or not document:
        return None
    try:
        cik_int = int(str(cik).strip())
    except ValueError:
        return None
    acc = accession.replace("-", "").strip()
    if cik_int <= 0 or not re.fullmatch(r"\d{18}", acc):
        return None
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{quote(document)}"
    if text and text.strip():
        # `&`, `,` and `-` are text-fragment syntax and must be percent-encoded; quote() keeps `-`.
        url += "#:~:text=" + quote(text.strip(), safe="").replace("-", "%2D")
    return url


def require_provenance(data: Any) -> Any:
    """
    `mode="before"` check for record models: no silent failure, provenance required.

    A record must carry provenance: a locator, or all of page, bbox and source_file (the legacy
    fields). Missing values are never padded with page 1, a whole-page box, or "unknown.pdf".
    """
    if not isinstance(data, dict) or data.get("locator") is not None:
        return data
    missing = [
        key
        for key in ("page", "bbox", "source_file")
        if data.get(key) is None or data.get(key) == ""
    ]
    if missing:
        raise ValueError(
            "record has no provenance: give a locator, or page, bbox and source_file "
            f"(missing: {', '.join(missing)})"
        )
    return data


def is_sec_archives_url(url: str | None) -> bool:
    """True for a CIK-qualified EDGAR Archives document URL (fragment ignored)."""
    return bool(url) and bool(_SEC_ARCHIVES_URL.match(str(url).split("#", 1)[0]))


class PdfLocator(BaseModel):
    """
    Provenance locator for PDF document targets.
    """

    type: Literal["pdf"] = "pdf"
    page: int = Field(..., ge=1, description="1-indexed source PDF page")
    bbox: dict[str, float] = Field(
        ...,
        description="Bounding box in 0-1000 normalized coordinates: {x0, y0, x1, y1}",
    )
    source_file: str = Field(
        ...,
        min_length=1,
        description="Source PDF filename",
    )


class HtmlLocator(BaseModel):
    """
    Provenance locator for SEC EDGAR HTML and iXBRL document targets.
    """

    type: Literal["html"] = "html"
    cik: str | None = Field(
        default=None,
        description="SEC Central Index Key of the filer; required to build a valid Archives URL",
    )
    accession: str = Field(
        ...,
        min_length=1,
        description="SEC EDGAR accession number (e.g. '0000320193-23-000106')",
    )
    document: str = Field(
        ...,
        min_length=1,
        description="Filing document or exhibit filename (e.g. 'aapl-20230930.htm')",
    )
    element_path: str = Field(
        ...,
        min_length=1,
        description="DOM element XPath or CSS path (e.g. '/html/body/table[2]/tr[4]/td[2]')",
    )
    char_range: tuple[int, int] | list[int] | None = Field(
        default=None,
        description="Character range [start, end] within the target element",
    )
    url: str | None = Field(
        default=None,
        description="Full SEC EDGAR URL to the document",
    )
    source_file: str | None = Field(
        default=None,
        description="Convenience filename alias for backward compatibility",
    )

    @model_validator(mode="before")
    @classmethod
    def _ensure_source_file(cls, data: Any) -> Any:
        if (
            isinstance(data, dict)
            and not data.get("source_file")
            and data.get("document")
        ):
            data["source_file"] = data["document"]
        return data


Locator = Annotated[PdfLocator | HtmlLocator, Field(discriminator="type")]


def deserialize_locator(data: dict[str, Any] | Locator | None) -> Locator | None:
    """
    Deserializes raw JSON or dictionary into the appropriate Locator variant.
    Supports legacy dicts without 'type' by inspecting presence of 'accession' or 'page'.
    Raises ValueError for payloads that match neither variant (never guesses).
    """
    if data is None:
        return None
    if isinstance(data, (PdfLocator, HtmlLocator)):
        return data
    if not isinstance(data, dict):
        return None

    locator_type = data.get("type")
    if locator_type == "html" or "accession" in data:
        return HtmlLocator.model_validate(data)
    elif locator_type == "pdf" or "page" in data or "bbox" in data:
        return PdfLocator.model_validate(data)

    raise ValueError(
        "Unrecognized locator payload: expected 'type', 'accession', or 'page'/'bbox' keys"
    )
