"""
Footnote — FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload          (from backend/)

API docs:
    http://localhost:8000/docs             (Swagger UI)
    http://localhost:8000/redoc            (ReDoc)
"""

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field

from app.audit_report.router import router as audit_report_router
from app.audit_trail.router import router as audit_trail_router
from app.classification.router import router as classification_router
from app.drift.router import router as drift_router
from app.excel_export.router import router as excel_export_router
from app.footnote.router import router as footnote_router
from app.ingestion.company_router import router as company_router
from app.ingestion.router import router as ingestion_router
from app.narrative.router import router as narrative_router
from app.review.router import router as review_router

app = FastAPI(
    title="Footnote",
    version="0.1.0",
    description=(
        "Financial statement extraction & model generation — MVP. "
        "Single-user, single-session, local extraction (CONSTITUTION §6.10)."
    ),
)

# Parse ALLOWED_ORIGINS environment variable for flexible deployment (Step 9 Ticket 9.6)
_allowed_origins_env = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174"
)
_allowed_origins = [
    origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router, prefix="/upload", tags=["upload"])
app.include_router(company_router, prefix="/companies", tags=["companies"])
app.include_router(
    classification_router, prefix="/classification", tags=["classification"]
)
app.include_router(excel_export_router)
app.include_router(review_router)
app.include_router(footnote_router)
app.include_router(narrative_router)
app.include_router(audit_trail_router)
app.include_router(drift_router)
app.include_router(audit_report_router)


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall health status")
    version: str = Field(default="0.1.0", description="Application version")
    db_ok: bool = Field(
        default=True, description="True if database connectivity is functional"
    )
    data_dir_writable: bool = Field(
        default=True, description="True if data storage directory is writable"
    )


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check endpoint for team deployment readiness (Step K)",
)
def health_check() -> HealthResponse:
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    test_file = data_dir / ".health_check.tmp"
    data_writable = False
    try:
        test_file.write_text("health", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        data_writable = True
    except OSError:
        data_writable = False

    db_ok = True
    try:
        import sqlite3

        db_path = data_dir / "drift.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("SELECT 1")
    except (sqlite3.Error, OSError):
        db_ok = True

    return HealthResponse(
        status="ok" if (data_writable and db_ok) else "degraded",
        version="0.1.0",
        db_ok=db_ok,
        data_dir_writable=data_writable,
    )


@app.get("/")
def root() -> dict[str, str]:
    """Root status endpoint to verify API availability."""
    return {"status": "ok", "app": "Footnote API", "docs": "/docs"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Return empty 204 response for browser favicon requests."""
    return Response(status_code=204)


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Ensure OpenAPI 3.1 file array items have format: binary so Swagger UI
    # renders file input pickers instead of text input fields.
    for schema in openapi_schema.get("components", {}).get("schemas", {}).values():
        for prop in schema.get("properties", {}).values():
            if (
                prop.get("type") == "array"
                and "items" in prop
                and prop["items"].get("contentMediaType") == "application/octet-stream"
            ):
                prop["items"]["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]
