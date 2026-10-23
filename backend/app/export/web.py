"""
The web app as a complete HTML document.

``web/index.html`` is a page fragment (title, styles, markup, script). The API
and the static export both serve it inside the same document skeleton, so the
page gets a doctype, charset, viewport and the ``[hidden]`` rule it relies on
wherever it is hosted.
"""

from __future__ import annotations

from pathlib import Path

from app.config import REPO_ROOT

WEB_DIR = REPO_ROOT / "web"

_SKELETON = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    "<style>:root{padding-top:env(safe-area-inset-top,0px);"
    "padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}"
    "[hidden]{display:none!important}</style></head><body>{page}</body></html>"
)


def web_page(web_dir: Path = WEB_DIR) -> str:
    """``web/index.html`` wrapped in the document skeleton."""
    fragment = (web_dir / "index.html").read_text(encoding="utf-8")
    return _SKELETON.replace("{page}", fragment)
