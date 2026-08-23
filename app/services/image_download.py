"""Download a remote image to a local temp path."""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(10.0, read=60.0)


def download_image_url(url: str, *, temp_dir: Path, filename: str) -> Path:
    suffix = Path(urlparse(url).path).suffix or ".jpg"
    path = temp_dir / f"{filename}{suffix}"
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def make_temp_dir(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
