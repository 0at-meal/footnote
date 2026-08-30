"""
FastAPI router for Narrative Intelligence & MD&A Diffing (Feature 10, Step G).

Endpoints:
    GET  /narrative/{job_id}/sections   ← Retrieve extracted narrative sections
    POST /narrative/{company_id}/diff   ← Compute word-level delta diff between two filings
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.ingestion.repository import JobRepository
from app.narrative.differ import (
    diff_narrative_sections,
    diff_risk_factors,
)
from app.narrative.extractor import extract_risk_factors
from app.narrative.models import (
    NarrativeDiff,
    NarrativeDiffRequest,
    NarrativeSection,
    RiskFactorRedline,
    RiskFactorRedlineRequest,
)
from app.narrative.repository import NarrativeRepository

router = APIRouter(prefix="/narrative", tags=["narrative"])

_default_job_repo = JobRepository()
_default_narrative_repo = NarrativeRepository()


def get_job_repository() -> JobRepository:
    return _default_job_repo


def get_narrative_repository() -> NarrativeRepository:
    return _default_narrative_repo


@router.get(
    "/{job_id}/sections",
    response_model=list[NarrativeSection],
    summary="Get extracted narrative sections (MD&A, Risk Factors) for a job",
)
def get_narrative_sections(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    narrative_repo: Annotated[NarrativeRepository, Depends(get_narrative_repository)],
) -> list[NarrativeSection]:
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    return narrative_repo.get_sections(job_id)


@router.post(
    "/{company_id}/diff",
    response_model=NarrativeDiff,
    summary="Compute word-level diff between MD&A or Risk narrative sections across consecutive filings",
)
def compute_narrative_diff(
    company_id: str,
    payload: NarrativeDiffRequest,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    narrative_repo: Annotated[NarrativeRepository, Depends(get_narrative_repository)],
) -> NarrativeDiff:
    earlier_job = job_repo.get_job(payload.earlier_job_id)
    if earlier_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Earlier job '{payload.earlier_job_id}' not found",
        )

    later_job = job_repo.get_job(payload.later_job_id)
    if later_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Later job '{payload.later_job_id}' not found",
        )

    # Check cached diff
    cached = narrative_repo.get_diff(
        company_id=company_id,
        earlier_job=payload.earlier_job_id,
        later_job=payload.later_job_id,
        item_no=payload.item_number,
    )
    if cached is not None:
        return cached

    earlier_sections = narrative_repo.get_sections(payload.earlier_job_id)
    later_sections = narrative_repo.get_sections(payload.later_job_id)

    target_item = payload.item_number.lower().replace(" ", "")

    earlier_match = next(
        (
            s
            for s in earlier_sections
            if s.item_number.lower().replace(" ", "") == target_item
        ),
        None,
    )
    later_match = next(
        (
            s
            for s in later_sections
            if s.item_number.lower().replace(" ", "") == target_item
        ),
        None,
    )

    if earlier_match is None:
        earlier_match = NarrativeSection(
            job_id=payload.earlier_job_id,
            item_number=payload.item_number,
            title=f"{payload.item_number} (Not found in prior filing)",
            text="",
            page_start=1,
            page_end=1,
        )

    if later_match is None:
        later_match = NarrativeSection(
            job_id=payload.later_job_id,
            item_number=payload.item_number,
            title=f"{payload.item_number} (Not found in current filing)",
            text="",
            page_start=1,
            page_end=1,
        )

    diff = diff_narrative_sections(
        earlier=earlier_match,
        later=later_match,
        company_id=company_id,
    )
    narrative_repo.save_diff(diff)
    return diff


@router.post(
    "/{company_id}/risk-redline",
    response_model=RiskFactorRedline,
    summary="Compute risk factor changes, additions, and deletions between consecutive filings",
)
def compute_risk_redline(
    company_id: str,
    payload: RiskFactorRedlineRequest,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    narrative_repo: Annotated[NarrativeRepository, Depends(get_narrative_repository)],
) -> RiskFactorRedline:
    earlier_job = job_repo.get_job(payload.earlier_job_id)
    if earlier_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Earlier job '{payload.earlier_job_id}' not found",
        )

    later_job = job_repo.get_job(payload.later_job_id)
    if later_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Later job '{payload.later_job_id}' not found",
        )

    # Check cached redline
    cached = narrative_repo.get_risk_redline(
        company_id=company_id,
        earlier_job=payload.earlier_job_id,
        later_job=payload.later_job_id,
    )
    if cached is not None:
        return cached

    earlier_sections = narrative_repo.get_sections(payload.earlier_job_id)
    later_sections = narrative_repo.get_sections(payload.later_job_id)

    earlier_risk_sec = next(
        (
            s
            for s in earlier_sections
            if s.item_number.lower().replace(" ", "") == "item1a"
        ),
        None,
    )
    later_risk_sec = next(
        (
            s
            for s in later_sections
            if s.item_number.lower().replace(" ", "") == "item1a"
        ),
        None,
    )

    earlier_risks = (
        extract_risk_factors(earlier_risk_sec.text)
        if earlier_risk_sec is not None
        else []
    )
    later_risks = (
        extract_risk_factors(later_risk_sec.text) if later_risk_sec is not None else []
    )

    redline = diff_risk_factors(
        earlier_risks=earlier_risks,
        later_risks=later_risks,
        company_id=company_id,
        earlier_job_id=payload.earlier_job_id,
        later_job_id=payload.later_job_id,
    )
    narrative_repo.save_risk_redline(redline)
    return redline
