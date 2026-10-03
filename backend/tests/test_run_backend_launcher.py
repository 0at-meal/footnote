"""
D1 / AUD-003: tools/run_backend.py runs the backend with the project .venv interpreter and
reports Docling status; without a .venv it refuses with instructions.

CI installs requirements into the runner's Python and has no .venv, so there the launcher is
exercised in a temp copy of the repo layout whose `.venv/bin/python` is a shim to the test
interpreter (which has Docling installed).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LAUNCHER = ROOT / "tools" / "run_backend.py"


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "tools" / "run_backend.py"), "--check"],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _copy_launcher(root: Path) -> None:
    (root / "tools").mkdir(parents=True)
    shutil.copy(LAUNCHER, root / "tools" / "run_backend.py")


def test_launcher_check_uses_venv_interpreter_and_reports_docling(tmp_path: Path) -> None:
    if (ROOT / ".venv").exists():
        root = ROOT
    elif os.name == "posix":
        root = tmp_path
        _copy_launcher(root)
        shim = root / ".venv" / "bin" / "python"
        shim.parent.mkdir(parents=True)
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
    else:
        pytest.skip("no project .venv on this Windows machine and no shim support")

    result = _check(root)
    assert result.returncode == 0, result.stderr
    assert f"interpreter: {root / '.venv'}" in result.stdout
    assert "docling: ok" in result.stdout


def test_launcher_without_venv_refuses_with_instructions(tmp_path: Path) -> None:
    _copy_launcher(tmp_path)
    result = _check(tmp_path)
    assert result.returncode != 0
    assert "No project virtualenv found at .venv" in result.stderr
