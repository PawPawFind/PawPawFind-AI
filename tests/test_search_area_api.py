from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.search_area import get_search_area_service
from app.main import app
from app.search_area.environment import (
    EnvironmentData,
    EnvironmentFeature,
    EnvironmentKind,
    StaticEnvironmentProvider,
)
from app.search_area.geo import GeoPoint
from app.services.search_area import SearchAreaRecommendationService

client = TestClient(app)
SEOUL = ZoneInfo("Asia/Seoul")


def request_payload() -> dict[str, object]:
    return {
        "reportId": 1,
        "species": "강아지",
        "size": "중형",
        "eventDate": "2026-08-24",
        "eventHour": 13,
        "latitude": 37.5665,
        "longitude": 126.978,
        "happenPlace": "서울특별시 마포구",
        "description": "산책 중 큰 소리에 놀라 도망감",
        "behaviorProfile": {
            "activityLevel": "HIGH",
            "strangerResponse": "AVOID",
            "noiseSensitivity": "HIGH",
            "chaseTendency": "LOW",
            "mobility": "NORMAL",
            "escapeCause": "NOISE",
        },
    }


@pytest.fixture(autouse=True)
def _fixed_search_area_service() -> None:
    data = EnvironmentData(
        source="FIXED_TEST_DATA",
        features=(
            EnvironmentFeature(
                GeoPoint(37.568, 126.976),
                frozenset({EnvironmentKind.GREEN_SPACE, EnvironmentKind.FOOTPATH}),
            ),
        ),
    )
    app.dependency_overrides[get_search_area_service] = lambda: SearchAreaRecommendationService(
        StaticEnvironmentProvider(data),
        now_provider=lambda: datetime(2026, 8, 25, 13, tzinfo=SEOUL),
    )
    yield
    app.dependency_overrides.pop(get_search_area_service, None)


def test_post_search_areas_returns_camel_case_contract() -> None:
    response = client.post("/search-areas", json=request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["reportId"] == 1
    assert body["algorithmVersion"] == "HEURISTIC_V1"
    assert body["behaviorType"] == "FEARFUL"
    assert body["estimatedRadiusMeters"] == 1375
    assert body["environmentSource"] == "FIXED_TEST_DATA"
    assert body["fallbackUsed"] is False
    assert 1 <= len(body["areas"]) <= 3
    assert body["areas"][0]["rank"] == 1
    assert "priorityScore" in body["areas"][0]
    assert "radiusMeters" in body["areas"][0]
    assert "reasonCodes" in body["areas"][0]


@pytest.mark.parametrize(
    "update",
    [
        {"species": "고양이"},
        {"size": "초대형"},
        {"eventHour": 25},
        {"latitude": 100},
    ],
)
def test_post_search_areas_returns_422_for_invalid_contract(update: dict[str, object]) -> None:
    payload = request_payload()
    payload.update(update)
    assert client.post("/search-areas", json=payload).status_code == 422


def test_post_search_areas_returns_422_for_future_event() -> None:
    payload = request_payload()
    payload["eventDate"] = "2026-08-26"
    response = client.post("/search-areas", json=payload)

    assert response.status_code == 422
    assert "미래" in response.json()["detail"]


def test_openapi_exposes_search_area_endpoint() -> None:
    schema = client.get("/openapi.json").json()
    assert "post" in schema["paths"]["/search-areas"]
