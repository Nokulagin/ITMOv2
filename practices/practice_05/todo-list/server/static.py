"""Serve the page from static/: GET / and GET /static/{name}.

The UI owns the files in static/; this module only reads them.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
INDEX_NAME = "index.html"
STATIC_PREFIX = "/static/"

# Text types carry an explicit charset (contract, section 10).
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def content_type_for(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in CONTENT_TYPES:
        return CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def is_safe_name(name: str) -> bool:
    """A file name only: no folders, no parent references, not empty."""
    if not name or name in (".", ".."):
        return False
    if "/" in name or "\\" in name or ".." in name:
        return False
    return True


def read_static(url_path: str, static_dir: Path = STATIC_DIR) -> Optional[Tuple[bytes, str]]:
    """Return (body, content type) for a page path, or None when it must be 404."""
    url_path = unquote(url_path)
    if url_path == "/":
        name = INDEX_NAME
    elif url_path.startswith(STATIC_PREFIX):
        name = url_path[len(STATIC_PREFIX):]
    else:
        return None
    if not is_safe_name(name):
        return None

    base = Path(static_dir).resolve()
    candidate = (base / name).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate.read_bytes(), content_type_for(name)
