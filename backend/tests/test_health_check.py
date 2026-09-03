"""
Unit tests for health check endpoint (Step 11).
"""

import sqlite3
from unittest.mock import patch

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check_success() -> None:
    """Verify health check returns status ok under normal circumstances."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("ok", "degraded")
    assert "db_ok" in data
    assert "data_dir_writable" in data


def test_health_check_db_failure() -> None:
    """Verify health check returns db_ok=False and degraded status when database fails."""
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("Mocked DB failure")):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["db_ok"] is False
        assert data["status"] == "degraded"
