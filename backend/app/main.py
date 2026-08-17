"""
Footnote — FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload          (from backend/)

API docs:
    http://localhost:8000/docs             (Swagger UI)
    http://localhost:8000/redoc            (ReDoc)
"""

from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.audit_report.router import router as audit_report_router
from app.audit_trail.router import router as audit_trail_router
from app.classification.router import router as classification_router
from app.drift.router import router as drift_router
from app.excel_export.router import router as excel_export_router
from app.ingestion.router import router as ingestion_router
from app.review.router import router as review_router

app = FastAPI(
    title="Footnote",
    version="0.1.0",
    description=(
        "Financial statement extraction & model generation — MVP. "
        "Single-user, single-session, local extraction (CONSTITUTION §6.10)."
    ),
)

# Allow the Vite dev server to call the backend without browser CORS errors.
# MVP is single-user/local (CONSTITUTION §6.10); this is not a security boundary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion_router, prefix="/upload", tags=["upload"])
app.include_router(classification_router, prefix="/classification", tags=["classification"])
app.include_router(excel_export_router)
app.include_router(review_router)
app.include_router(audit_trail_router)
app.include_router(drift_router)
app.include_router(audit_report_router)


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
            if prop.get("type") == "array" and "items" in prop and prop["items"].get("contentMediaType") == "application/octet-stream":
                prop["items"]["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]
