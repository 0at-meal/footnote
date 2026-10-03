"""tools/run_backend.py always resolves the project virtualenv interpreter (D1)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_launcher_check_uses_venv_interpreter_and_reports_docling() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "run_backend.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert ".venv" in result.stdout
    assert "docling: ok" in result.stdout
