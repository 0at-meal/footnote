"""
API Router for Audit Trail Lookup (Feature 6 Step 1).

Exposes:
- GET /audit-trail/{job_id}/cell/{sheet_name}/{cell_coord} (FR8, AC-1, AC-2)
- GET /audit-trail/{job_id}/provenance/{provenance_id:path} (FR8, AC-7)
- GET /audit-trail/{job_id}/record (FR8, query param provenance_id)
"""

from fastapi import APIRouter, Query

from app.audit_trail.models import SourceChainResponse
from app.audit_trail.resolver import AuditTrailResolver

router = APIRouter(prefix="/audit-trail", tags=["audit-trail"])
_resolver = AuditTrailResolver()


def get_audit_trail_resolver() -> AuditTrailResolver:
    """Returns the active AuditTrailResolver instance."""
    return _resolver


def set_audit_trail_resolver(resolver: AuditTrailResolver) -> None:
    """Sets the active AuditTrailResolver instance (used for testing / dependency injection)."""
    global _resolver
    _resolver = resolver


@router.get(
    "/{job_id}/cell/{sheet_name}/{cell_coord}",
    response_model=SourceChainResponse,
    summary="Resolve full source chain by workbook cell reference",
)
def resolve_cell_source_chain(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
) -> SourceChainResponse:
    """
    Given a job UUID, sheet name, and cell coordinate, resolves the complete source chain
    down to exact PDF pages, bounding boxes, and live review status (FR8, AC-1, AC-2).
    """
    return _resolver.resolve_by_cell(
        job_id=job_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
    )


@router.get(
    "/{job_id}/record",
    response_model=SourceChainResponse,
    summary="Resolve full source chain by provenance record ID query parameter",
)
def resolve_record_source_chain_query(
    job_id: str,
    provenance_id: str = Query(..., description="Canonical W3C Web Annotation URN ID"),
) -> SourceChainResponse:
    """
    Resolves full source chain by W3C Web Annotation ID via query parameter (AC-7).
    """
    return _resolver.resolve_by_provenance_id(
        job_id=job_id,
        provenance_id=provenance_id,
    )


@router.get(
    "/{job_id}/provenance/{provenance_id:path}",
    response_model=SourceChainResponse,
    summary="Resolve full source chain by path-based provenance record ID",
)
def resolve_record_source_chain_path(
    job_id: str,
    provenance_id: str,
) -> SourceChainResponse:
    """
    Resolves full source chain by W3C Web Annotation ID via path parameter (AC-7).
    """
    return _resolver.resolve_by_provenance_id(
        job_id=job_id,
        provenance_id=provenance_id,
    )
