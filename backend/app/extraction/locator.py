"""
Locator Union Schema (FN-023).

Defines the discriminated union of provenance locators:
- PdfLocator: targeting page number, normalized 0-1000 bounding box, and source filename.
- HtmlLocator: targeting SEC EDGAR accession number, document/exhibit, DOM element path (XPath/CSS),
  optional character range, and direct SEC URL.

Enforces Invariants:
- I4: Exact provenance locator preserved across all operations.
- Deterministic, backward-compatible deserialization and serialization.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class PdfLocator(BaseModel):
    """
    Provenance locator for PDF document targets (Feature 2 / Feature 4).
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

    @model_validator(mode="before")
    @classmethod
    def _coerce_bbox(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("bbox") is not None and not isinstance(data.get("bbox"), dict):
            raw_bbox = data["bbox"]
            data["bbox"] = {
                "x0": float(getattr(raw_bbox, "x0", 0.0)),
                "y0": float(getattr(raw_bbox, "y0", 0.0)),
                "x1": float(getattr(raw_bbox, "x1", 1000.0)),
                "y1": float(getattr(raw_bbox, "y1", 1000.0)),
            }
        return data


class HtmlLocator(BaseModel):
    """
    Provenance locator for SEC EDGAR HTML and iXBRL document targets (FN-023, FN-021).
    """

    type: Literal["html"] = "html"
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
        if isinstance(data, dict) and not data.get("source_file") and data.get("document"):
            data["source_file"] = data["document"]
        return data


Locator = Annotated[PdfLocator | HtmlLocator, Field(discriminator="type")]


def locator_from_legacy(
    page: int,
    bbox: dict[str, float] | Any,
    source_file: str,
) -> PdfLocator:
    """Creates a canonical PdfLocator from legacy five-field components."""
    if isinstance(bbox, dict):
        normalized_bbox = {
            "x0": float(bbox.get("x0", 0.0)),
            "y0": float(bbox.get("y0", 0.0)),
            "x1": float(bbox.get("x1", 1000.0)),
            "y1": float(bbox.get("y1", 1000.0)),
        }
    elif bbox is not None:
        normalized_bbox = {
            "x0": float(getattr(bbox, "x0", 0.0)),
            "y0": float(getattr(bbox, "y0", 0.0)),
            "x1": float(getattr(bbox, "x1", 1000.0)),
            "y1": float(getattr(bbox, "y1", 1000.0)),
        }
    else:
        normalized_bbox = {"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0}

    return PdfLocator(
        type="pdf",
        page=max(1, page),
        bbox=normalized_bbox,
        source_file=source_file or "unknown.pdf",
    )


def deserialize_locator(data: dict[str, Any] | Locator | None) -> Locator | None:
    """
    Deserializes raw JSON or dictionary into the appropriate Locator variant.
    Supports legacy dicts without 'type' by inspecting presence of 'accession' or 'page'.
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

    # Fallback to pdf locator
    return locator_from_legacy(
        page=int(data.get("page", 1)),
        bbox=data.get("bbox", {}),
        source_file=str(data.get("source_file", "unknown.pdf")),
    )
