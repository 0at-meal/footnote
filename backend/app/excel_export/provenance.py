"""
W3C Web Annotation provenance builder for Excel model cells (Feature 4 Step 4).

Enforces:
- plan §6.1 item 3, item 7: W3C Web Annotation Data Model in 0-1000 normalized coordinate space.
- spec.md §4: Canonical provenance records projected into cell comment and hyperlink.
- Pure functions: idempotent and deterministic.
"""

from app.excel_export.models import (
    BoundingBoxCoordinates,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
)
from app.formula_engine.models import FormulaNode


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

    if node.source_node is not None:
        src = node.source_node
        loc = getattr(src, "locator", None)
        if loc is not None and getattr(loc, "type", None) == "html":
            selector = W3CSelector(
                type="XPathSelector",
                conformsTo="http://www.w3.org/TR/DOM-XPath/",
                page=1,
                value=loc.element_path,
                refinedBy=None,
            )
            source_target = (
                loc.url
                if loc.url
                else f"https://www.sec.gov/edgar/data/{loc.accession}/{loc.document}"
            )
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
        coords = (
            target.selector.refinedBy.coordinates
            if target.selector.refinedBy
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
    base_url: str = "http://localhost:8000",
) -> str:
    """
    Constructs the canonical HTTP URI target for the cell's provenance hyperlink.
    """
    return f"{base_url}/models/{job_id}/provenance/{sheet_name}/{cell_coord}"


def format_source_deep_link(
    job_id: str,
    annotation: W3CAnnotationRecord | None = None,
    node: FormulaNode | None = None,
    base_url: str = "http://localhost:8000",
) -> str:
    """
    Constructs the deep link URL to the source document for label cell hyperlinks (FN-032).
    - For HTML sources: Public SEC link with fragment or element path.
    - For PDF sources: Hosted document viewer link with page anchor.
    """
    if node is not None and node.source_node is not None:
        src = node.source_node
        loc = getattr(src, "locator", None)
        if loc is not None and getattr(loc, "type", None) == "html":
            if getattr(loc, "url", None):
                return str(loc.url)
            accession = getattr(loc, "accession", "")
            document = getattr(loc, "document", "")
            if accession and document:
                clean_acc = accession.replace("-", "")
                return f"https://www.sec.gov/Archives/edgar/data/{clean_acc}/{document}"
        if loc is not None and getattr(loc, "type", None) == "pdf":
            page = getattr(loc, "page", 1)
            return f"{base_url}/api/review/{job_id}/source#page={page}"
        if src.page:
            return f"{base_url}/api/review/{job_id}/source#page={src.page}"

    if annotation is not None and annotation.target.selector is not None:
        target = annotation.target
        if target.selector.type == "XPathSelector":
            return target.source
        return f"{base_url}/api/review/{job_id}/source#page={target.selector.page}"

    return f"{base_url}/api/review/{job_id}"
