"""
Tests for the P0-03 release saver. Content and identifiers are synthetic
fixtures (zero CIKs); nothing here is a real filing.
"""

from pathlib import Path

import pytest
from tools.gold.fetch_releases import (
    save_release,
    selected_releases,
    sha256_hex,
    verify,
)

REL = {
    "ticker": "FIXT",
    "cik": "0000000000",
    "accession": "0000000000-26-000001",
    "filed": "2026-05-01",
    "exhibit": "ex991.htm",
    "url": "https://example.com/ex991.htm",
}


def test_save_and_verify_roundtrip(tmp_path: Path) -> None:
    content = b"<html>synthetic release</html>"
    entry = save_release(tmp_path, REL, content)
    assert entry.sha256 == sha256_hex(content)
    assert entry.bytes == len(content)
    manifest = {"releases": [entry.__dict__]}
    assert verify(tmp_path, manifest) == []


def test_saved_gzip_is_deterministic(tmp_path: Path) -> None:
    content = b"<html>same bytes</html>"
    save_release(tmp_path / "a", REL, content)
    save_release(tmp_path / "b", REL, content)
    rel_path = "0000000000-26-000001/ex991.htm.gz"
    assert (tmp_path / "a" / rel_path).read_bytes() == (
        tmp_path / "b" / rel_path
    ).read_bytes()


def test_verify_detects_tampering_and_missing(tmp_path: Path) -> None:
    entry = save_release(tmp_path, REL, b"<html>original</html>")
    manifest = {"releases": [entry.__dict__]}
    save_release(tmp_path, REL, b"<html>edited</html>")
    assert any("sha256 mismatch" in p for p in verify(tmp_path, manifest))
    (tmp_path / entry.path).unlink()
    assert verify(tmp_path, manifest) == [f"missing: {entry.path}"]


def test_selected_releases_requires_approval() -> None:
    issuers = {"approved_by": None, "selected": []}
    with pytest.raises(ValueError, match="not approved"):
        selected_releases(issuers)


def test_selected_releases_flattens() -> None:
    issuers = {
        "approved_by": "owner",
        "selected": [
            {
                "ticker": "FIXT",
                "cik": "0000000000",
                "releases": [
                    {k: v for k, v in REL.items() if k not in ("ticker", "cik")}
                ],
            }
        ],
    }
    out = selected_releases(issuers)
    assert out == [REL]
