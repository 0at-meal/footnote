"""
Footnote — FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload          (from backend/)

API docs:
    http://localhost:8000/docs             (Swagger UI)
    http://localhost:8000/redoc            (ReDoc)
"""

from fastapi import FastAPI

from app.ingestion.router import router as ingestion_router

app = FastAPI(
    title="Footnote",
    version="0.1.0",
    description=(
        "Financial statement extraction & model generation — MVP. "
        "Single-user, single-session, local extraction (CONSTITUTION §6.10)."
    ),
)

app.include_router(ingestion_router, prefix="/upload", tags=["upload"])
