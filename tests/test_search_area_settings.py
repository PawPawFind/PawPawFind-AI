import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.api.search_area import get_search_area_service
from app.main import app
from app.search_area.environment import OverpassEnvironmentProvider
from app.search_area.settings import load_search_area_settings


def test_settings_keep_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OVERPASS_TIMEOUT_SECONDS", raising=False)
    assert load_search_area_settings().overpass_timeout_seconds == 10.0


def test_settings_accept_positive_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERPASS_TIMEOUT_SECONDS", "2.5")
    assert load_search_area_settings().overpass_timeout_seconds == 2.5


def test_validated_timeout_is_passed_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERPASS_TIMEOUT_SECONDS", "2.5")
    with TestClient(app):
        request = Request({"type": "http", "app": app})
        service = get_search_area_service(request)

    assert isinstance(service.environment_provider, OverpassEnvironmentProvider)
    assert service.environment_provider.timeout_seconds == 2.5


@pytest.mark.parametrize("value", ["invalid", "0", "-1"])
def test_settings_reject_invalid_timeout(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OVERPASS_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="OVERPASS_TIMEOUT_SECONDS"):
        load_search_area_settings()


def test_application_startup_rejects_invalid_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERPASS_TIMEOUT_SECONDS", "invalid")
    with pytest.raises(ValueError, match="OVERPASS_TIMEOUT_SECONDS"):
        with TestClient(app):
            pass
