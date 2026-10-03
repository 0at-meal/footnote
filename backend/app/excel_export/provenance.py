"""
W3C Web Annotation provenance builder for Excel model cells (Feature 4 Step 4).

Enforces:
- plan §6.1 item 3, item 7: W3C Web Annotation Data Model in 0-1000 normalized coordinate space.
- spec.md §4: Canonical provenance records projected into cell comment and hyperlink.
- Pure functions: idempotent and deterministic.
"""

from app.config import public_base_url
from app.excel_export.models import (
    BoundingBoxCoordinates,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
    W3CTextQuoteSelector,
)
from app.extraction.locator import is_sec_archives_url, sec_archives_url
from app.formula_engine.models import FormulaNode

# Re-exported for callers that build workbook links (AUD-018).
sec_document_url = sec_archives_url


def _html_document_url(loc: object, text: str | None = None) -> str | None:
    """
    sec.gov link for an HTML locator (D9): the stored URL when it is a CIK-qualified Archives
    URL, else one built from cik/accession/document, else None. Never a CIK-less guess.
    """
    stored = getattr(loc, "url", None)
    if is_sec_archives_url(stored):
        base = str(stored).split("#", 1)[0]
        return sec_archives_url(*_archives_parts(base), text=text) or base
    return sec_archives_url(
        getattr(loc, "cik", None), getattr(loc, "accession", None), getattr(loc, "document", None), text=text
    )


def _archives_parts(url: str) -> tuple[str, str, str]:
    cik, acc, document = url.removeprefix("https://www.sec.gov/Archives/edgar/data/").split("/", 2)
    return cik, acc, document


def _row_text(label: str | None) -> str | None:
    """The row label as printed in the filing (the extractor prefixes table title and period)."""
    if not label:
        return None
    return label.split(" > ")[-1].strip() or None


def build_w3c_annotation_for_node(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
    node: FormulaNode,
) -> W3CAnnotationRecord:
    """
    Constructs a canonical W3C Web Annotation record for a workbook cell (plan §6.1 item 7).
    """
    annotation_id = f"urn:footnote:provenance:{job_id}:{sheet_name}:{cell_coord}"

    record_locator = None
    if node.source_node is not None:
        src = node.source_node
        loc = getattr(src, "locator", None)
        record_locator = loc
        if loc is not None and getattr(loc, "type", None) == "html":
            selector = W3CSelector(
                type="XPathSelector",
                conformsTo="http://www.w3.org/TR/DOM-XPath/",
                page=1,
                value=loc.element_path,
                # The element is a table cell; the quote pins the value inside it (AUD-037).
                refinedBy=W3CTextQuoteSelector(exact=src.value.strip()) if src.value.strip() else None,
            )
            # No CIK and no valid stored URL: identify the document without inventing a link (AUD-018).
            source_target = _html_document_url(loc) or f"urn:footnote:sec:{loc.accession}:{loc.document}"
            target = W3CTarget(source=source_target, selector=selector)
        else:
            bbox = src.bbox
            coordinates = BoundingBoxCoordinates(
                x0=float(bbox.get("x0", 0.0)),
                y0=float(bbox.get("y0", 0.0)),
                x1=float(bbox.get("x1", 1000.0)),
                y1=float(bbox.get("y1", 1000.0)),
            )
            selector = W3CSelector(
                type="FragmentSelector",
                conformsTo="http://www.w3.org/TR/media-frags/",
                page=src.page,
                value=f"xywh=percent:{coordinates.x0},{coordinates.y0},{coordinates.x1},{coordinates.y1}",
                refinedBy=W3CRefinedBy(coordinates=coordinates),
            )
            target = W3CTarget(source=src.source_file, selector=selector)
        body = W3CBody(
            value=src.value,
            label=src.normalized_label,
            original_label=src.label,
        )
    else:
        # Aggregate or calculated root node
        target = W3CTarget(source="model_derived", selector=None)
        body = W3CBody(
            value=node.formula_expression or node.label,
            label=node.label,
            original_label=None,
        )

    return W3CAnnotationRecord(
        id=annotation_id,
        job_id=job_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
        node_id=node.node_id,
        is_formula=node.node_type != "leaf" or sheet_name == "Reconciliation",
        body=body,
        target=target,
        locator=record_locator,
    )


def format_cell_comment(annotation: W3CAnnotationRecord) -> str:
    """
    Creates human-readable projection of the W3C Web Annotation record for Excel cell comments (FN-032).
    Includes human-readable document reference and preserves W3C bounding box coordinates.
    """
    body = annotation.body
    target = annotation.target

    if target.selector is not None:
        if target.selector.type == "XPathSelector":
            return (
                f"EDGAR HTML · {target.source} · {body.label}\n"
                f"[Footnote Provenance - EDGAR HTML]\n"
                f"Label: {body.label}\n"
                f"Value: {body.value}\n"
                f"Source: {target.source}\n"
                f"Element: {target.selector.value}\n"
                f"ID: {annotation.id}"
            )
        refined = target.selector.refinedBy
        coords = (
            refined.coordinates
            if isinstance(refined, W3CRefinedBy)
            else BoundingBoxCoordinates(x0=0.0, y0=0.0, x1=0.0, y1=0.0)
        )
        return (
            f"{target.source} · p.{target.selector.page} · {body.label}\n"
            f"[Footnote Provenance]\n"
            f"Label: {body.label}\n"
            f"Value: {body.value}\n"
            f"Source: {target.source} (p. {target.selector.page})\n"
            f"BBox [0-1000]: [{coords.x0:.1f}, {coords.y0:.1f}, {coords.x1:.1f}, {coords.y1:.1f}]\n"
            f"ID: {annotation.id}"
        )

    return (
        f"[Footnote Provenance - Calculated]\n"
        f"Metric: {body.label}\n"
        f"Formula: {body.value}\n"
        f"ID: {annotation.id}"
    )


def format_cell_hyperlink_url(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
    base_url: str | None = None,
) -> str:
    """
    Constructs the canonical HTTP URI target for the cell's provenance hyperlink.
    """
    base_url = base_url or public_base_url()
    return f"{base_url}/models/{job_id}/provenance/{sheet_name}/{cell_coord}"


def format_source_deep_link(
    job_id: str,
    annotation: W3CAnnotationRecord | None = None,
    node: FormulaNode | None = None,
    base_url: str | None = None,
) -> str | None:
    """
    Deep link from a workbook label cell to its source document (FN-032, AUD-018, D9).
    - HTML sources: sec.gov Archives URL with the CIK and a text fragment for the row label;
      None when no valid URL can be built (the caller writes the label without a link, I3).
    - PDF sources: the API's PDF route `{base}/review/{job_id}/pdf#page=N` (a real route; the
      previous `/api/review/{job_id}/source` target returned 404).
    """
    base_url = base_url or public_base_url()
    pdf_url = f"{base_url}/review/{job_id}/pdf"
    if node is not None and node.source_node is not None:
        src = node.source_node
        loc = getattr(src, "locator", None)
        if loc is not None and getattr(loc, "type", None) == "html":
            return _html_document_url(loc, text=_row_text(src.label))
        if loc is not None and getattr(loc, "type", None) == "pdf":
            page = getattr(loc, "page", 1)
            return f"{pdf_url}#page={page}"
        if src.page:
            return f"{pdf_url}#page={src.page}"

    selector = annotation.target.selector if annotation is not None else None
    if annotation is not None and selector is not None:
        if selector.type == "XPathSelector":
            return annotation.target.source if is_sec_archives_url(annotation.target.source) else None
        return f"{pdf_url}#page={selector.page}"

    return pdf_url
