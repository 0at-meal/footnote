"""
AUD-033 (mypy-found runtime bugs in drift/router.py):
- list_jobs(company_id=...) raised TypeError -> 500 for any job assigned to a company.
- item.extracted_value does not exist on ReviewItem -> AttributeError for an empty value.

Value parsing/semantics of QoE are AUD-021 (batch 8); this only checks the route works.
"""

from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.main import app
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient


def _item(item_id: str, value: str) -> ReviewItem:
    return ReviewItem.model_validate(
        {
            "id": item_id,
            "value": value,
            "label": "Stock-based compensation",
            "page": 1,
            "bbox": {"x0": 1.0, "y0": 1.0, "x1": 2.0, "y1": 2.0},
            "source_file": "synthetic.pdf",
            "confidence_band": "auto_accepted",
            "confidence_score": 0.99,
            "status": ReviewStatus.locked,
        }
    )


def test_qoe_route_works_for_jobs_assigned_to_a_company() -> None:
    with TestClient(app) as client:
        repo = JobRepository()
        prior = repo.save_job("prior.pdf", b"%PDF-1.4", "Adjusted EBITDA", company_id="co-1")
        current = repo.save_job("current.pdf", b"%PDF-1.4", "Adjusted EBITDA", company_id="co-1")
        repo.update_job_status(prior.job_id, JobStatus.done)
        repo.update_job_status(current.job_id, JobStatus.done)
        reviews = ReviewRepository()
        reviews.save_review_items(prior.job_id, [_item("p1", "50")])
        reviews.save_review_items(current.job_id, [_item("c1", "60"), _item("c2", "")])

        response = client.get(f"/drift/jobs/{current.job_id}/qoe")

    assert response.status_code == 200, response.text
