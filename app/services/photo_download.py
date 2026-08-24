"""Download report photo URLs to temporary local files."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_PHOTOS = 3
TIMEOUT = httpx.Timeout(10.0, read=60.0)


def download_photo_urls(urls: list[str]) -> list[Path]:
    if not urls:
        raise ValueError("photoUrls is empty")

    temp_dir = Path(tempfile.mkdtemp(prefix="pawpawfind-query-"))
    saved: list[Path] = []

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        for index, url in enumerate(urls[:MAX_PHOTOS]):
            response = client.get(url)
            response.raise_for_status()
            suffix = Path(urlparse(url).path).suffix or ".jpg"
            path = temp_dir / f"photo_{index}{suffix}"
            path.write_bytes(response.content)
            saved.append(path)

    return saved


@contextmanager
def downloaded_photo_urls(urls: list[str]) -> Iterator[list[Path]]:
    paths = download_photo_urls(urls)
    temp_dirs = {path.parent for path in paths}
    try:
        yield paths
    finally:
        for temp_dir in temp_dirs:
            shutil.rmtree(temp_dir, ignore_errors=True)
