"""
Footnote — FastAPI application entry point.

Run locally:
    uvicorn app.main:app --reload          (from backend/)

API docs:
    http://localhost:8000/docs             (Swagger UI)
    http://localhost:8000/redoc            (ReDoc)
"""

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

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
            if prop.get("type") == "array" and "items" in prop:
                if prop["items"].get("contentMediaType") == "application/octet-stream":
                    prop["items"]["format"] = "binary"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]

