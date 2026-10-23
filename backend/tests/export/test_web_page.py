"""The web app is served as a complete document by the API and the static export."""

from __future__ import annotations

from pathlib import Path

from app.export.web import web_page
from app.pipeline.cli import main


def test_web_page_wraps_the_fragment(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<title>X</title><p hidden>x</p>", encoding="utf-8"
    )
    page = web_page(tmp_path)
    assert page.startswith("<!doctype html>")
    assert (
        '<meta charset="utf-8">' in page and "[hidden]{display:none!important}" in page
    )
    assert "<body><title>X</title><p hidden>x</p></body>" in page


def test_static_export_writes_a_full_document(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert main(["--db", str(tmp_path / "empty.db"), "export", "--out", str(out)]) == 0
    page = (out / "index.html").read_text(encoding="utf-8")
    assert (
        page.startswith("<!doctype html>")
        and "[hidden]{display:none!important}" in page
    )
    assert (out / "snapshot.json").is_file()
