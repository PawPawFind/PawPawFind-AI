from pathlib import Path

import httpx
import pytest

from app.services import photo_download


def test_download_failure_removes_temporary_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    temp_dir = tmp_path / "failed-download"

    def fake_mkdtemp(*, prefix: str) -> str:
        assert prefix == "pawpawfind-query-"
        temp_dir.mkdir()
        return str(temp_dir)

    def fail_get(self: httpx.Client, url: str) -> httpx.Response:
        del self, url
        raise httpx.ConnectError("download failed")

    monkeypatch.setattr(photo_download.tempfile, "mkdtemp", fake_mkdtemp)
    monkeypatch.setattr(httpx.Client, "get", fail_get)

    with pytest.raises(httpx.ConnectError):
        photo_download.download_photo_urls(["https://example.com/pet.jpg"])

    assert not temp_dir.exists()
