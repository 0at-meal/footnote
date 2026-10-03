#!/usr/bin/env python
"""
Start the Footnote backend with the project virtualenv's interpreter (decision D1).

Works when launched by *any* Python (system or venv): it locates `.venv` and runs uvicorn
with that interpreter, so Docling is always the parser that is used. The audit found the
server had been started with a system Python that lacked Docling, which silently degraded
extraction (AUD-003).

Usage:
    python tools/run_backend.py            # uvicorn app.main:app --reload
    python tools/run_backend.py --check    # report interpreter + Docling status, exit 1 if missing
    python tools/run_backend.py --port 8001 --host 127.0.0.1   # extra args go to uvicorn
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def venv_python() -> Path:
    for candidate in (
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return candidate
    sys.exit(
        "No project virtualenv found at .venv. Create it with:\n"
        "  python -m venv .venv\n"
        "  .venv/Scripts/python.exe -m pip install -r requirements.txt   (Windows)\n"
        "  .venv/bin/python -m pip install -r requirements.txt           (macOS/Linux)"
    )


def docling_status(python: Path) -> tuple[bool, str]:
    probe = subprocess.run(
        [str(python), "-c", "import docling.document_converter"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0:
        return True, "ok"
    last = (probe.stderr.strip().splitlines() or ["unknown error"])[-1]
    return False, last


def main(argv: list[str]) -> int:
    python = venv_python()
    available, detail = docling_status(python)
    if "--check" in argv:
        print(f"interpreter: {python}")
        print(f"docling: {detail}")
        return 0 if available else 1
    if not available and os.environ.get("ALLOW_PYMUPDF_FALLBACK", "").strip() != "1":
        print(
            f"Docling is not importable in {python}: {detail}\n"
            "Install requirements into .venv, or set ALLOW_PYMUPDF_FALLBACK=1 for degraded mode.",
            file=sys.stderr,
        )
        return 1
    uvicorn_args = argv or ["--reload"]
    return subprocess.call(
        [str(python), "-m", "uvicorn", "app.main:app", *uvicorn_args],
        cwd=ROOT / "backend",
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
