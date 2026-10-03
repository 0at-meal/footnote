"""FOOTNOTE_DATA_DIR redirects every repository away from backend/data (rule: never touch user data)."""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).parent.parent

PROBE = """
import json
from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository
from app.extraction.repository import ExtractionRepository
from app.excel_export.repository import ModelRepository
from app.config import DEFAULT_DATA_DIR
print(json.dumps({
  "config": str(DEFAULT_DATA_DIR),
  "jobs": str(JobRepository().data_dir),
  "review": str(ReviewRepository()._data_dir),
  "extraction": str(ExtractionRepository()._data_dir),
  "models": str(ModelRepository()._data_dir),
}))
"""


def test_footnote_data_dir_env_redirects_repositories(tmp_path: Path) -> None:
    env = dict(os.environ, FOOTNOTE_DATA_DIR=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    out = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip().splitlines()[-1]
    dirs = json.loads(out)
    for name, value in dirs.items():
        assert Path(value).resolve() == tmp_path.resolve(), (name, value)
