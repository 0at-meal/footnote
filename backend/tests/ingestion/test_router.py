"""
Integration tests for POST /upload/validate.

Uses FastAPI's TestClient (synchronous wrapper around the async app).
Each test verifies the HTTP contract — status codes, JSON shape, and
per-file result semantics — not the internal validation logic (that is
test_validation.py's job).
"""

import io

import pymupdf
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_minimal_pdf() -> bytes:
    """Real, parseable, unencrypted PDF — one blank page."""
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def pdf_upload(filename: str, content: bytes) -> tuple[str, tuple[str, io.BytesIO, str]]:
    """Helper: build a (field_name, (filename, stream, content_type)) tuple."""
    return ("files", (filename, io.BytesIO(content), "application/pdf"))


def file_upload(
    filename: str, content: bytes, content_type: str
) -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", (filename, io.BytesIO(content), content_type))


# ── Single-file cases ─────────────────────────────────────────────────────────


def test_root_endpoint_returns_ok() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_favicon_endpoint_returns_204() -> None:
    res = client.get("/favicon.ico")
    assert res.status_code == 204


def test_single_valid_pdf_returns_accepted() -> None:
    response = client.post(
        "/upload/validate",
        files=[pdf_upload("annual.pdf", make_minimal_pdf())],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["accepted"] is True
    assert results[0]["filename"] == "annual.pdf"
    assert results[0]["error_message"] is None


def test_single_non_pdf_returns_rejected_with_message() -> None:
    response = client.post(
        "/upload/validate",
        files=[file_upload("resume.docx", b"not a pdf", "application/msword")],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["accepted"] is False
    assert results[0]["filename"] == "resume.docx"
    assert results[0]["error_message"] is not None
    assert len(results[0]["error_message"]) > 0


def test_single_empty_file_returns_rejected() -> None:
    response = client.post(
        "/upload/validate",
        files=[pdf_upload("empty.pdf", b"")],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["accepted"] is False
    assert "empty" in results[0]["error_message"]


# ── Multi-file cases ──────────────────────────────────────────────────────────


def test_multi_file_mix_valid_and_invalid_independent_results() -> None:
    """Valid files are accepted; invalid files are rejected. Neither affects the other."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/validate",
        files=[
            pdf_upload("valid.pdf", pdf),
            file_upload("bad.txt", b"plain text", "text/plain"),
        ],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2

    by_name = {r["filename"]: r for r in results}
    assert by_name["valid.pdf"]["accepted"] is True
    assert by_name["bad.txt"]["accepted"] is False


def test_multi_file_all_invalid_returns_200_with_all_rejected() -> None:
    response = client.post(
        "/upload/validate",
        files=[
            file_upload("a.docx", b"doc content", "application/msword"),
            file_upload("b.png", b"\x89PNG", "image/png"),
        ],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert all(not r["accepted"] for r in results)
    # Each rejection has its own message
    assert all(r["error_message"] for r in results)


def test_multi_file_all_valid_all_accepted() -> None:
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/validate",
        files=[
            pdf_upload("report1.pdf", pdf),
            pdf_upload("report2.pdf", pdf),
            pdf_upload("report3.pdf", pdf),
        ],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 3
    assert all(r["accepted"] for r in results)


def test_same_filename_submitted_twice_creates_two_independent_results() -> None:
    """Spec EC-1: same filename in one session → two separate results."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/validate",
        files=[
            pdf_upload("annual.pdf", pdf),
            pdf_upload("annual.pdf", pdf),
        ],
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert all(r["accepted"] for r in results)


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_no_files_field_returns_422() -> None:
    """Required field missing → FastAPI returns 422 Unprocessable Entity."""
    response = client.post("/upload/validate")
    assert response.status_code == 422


def test_filename_empty_string_returns_422() -> None:
    """FastAPI's multipart parser rejects a part with an empty-string filename
    at the framework level (422). This is documented platform behaviour;
    the router's `upload.filename or '<unknown>'` guard handles None filenames
    from programmatic clients that omit the Content-Disposition filename param
    entirely, which is a different code path."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/validate",
        files=[("files", ("", io.BytesIO(pdf), "application/pdf"))],
    )
    assert response.status_code == 422


# ── Response shape ────────────────────────────────────────────────────────────


def test_response_always_contains_results_key() -> None:
    response = client.post(
        "/upload/validate",
        files=[pdf_upload("test.pdf", make_minimal_pdf())],
    )
    assert response.status_code == 200
    body = response.json()
    assert "results" in body
    assert isinstance(body["results"], list)


def test_each_result_has_required_fields() -> None:
    response = client.post(
        "/upload/validate",
        files=[pdf_upload("test.pdf", make_minimal_pdf())],
    )
    result = response.json()["results"][0]
    assert "filename" in result
    assert "accepted" in result
    assert "error_message" in result
    assert isinstance(result["accepted"], bool)
