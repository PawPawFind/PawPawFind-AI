"""Full V1 wire snapshots captured at ef43a3a before implementation changes."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.schemas.search_area import SearchAreaRequest
from app.search_area.environment import (
    EnvironmentData,
    EnvironmentFeature,
    EnvironmentKind,
    EnvironmentProviderError,
    StaticEnvironmentProvider,
)
from app.search_area.geo import GeoPoint, offset_point
from app.services.search_area import SearchAreaRecommendationService

NOW = datetime(2026, 10, 29, 12, tzinfo=ZoneInfo("Asia/Seoul"))
ORIGIN = GeoPoint(37.5665, 126.978)
GOLDEN = Path(__file__).parent / "fixtures" / "search_area_v1.json"
SCENARIOS = {
    "fearful_park": ({"noiseSensitivity": "HIGH"}, [(75, EnvironmentKind.GREEN_SPACE)]),
    "active_path": (
        {"activityLevel": "HIGH", "chaseTendency": "HIGH"},
        [(20, EnvironmentKind.FOOTPATH), (290, EnvironmentKind.GREEN_SPACE)],
    ),
    "road_barrier": (
        {"mobility": "LIMITED"},
        [(20, EnvironmentKind.MAJOR_ROAD), (80, EnvironmentKind.RAILWAY_BARRIER)],
    ),
    "sparse": ({"strangerResponse": "APPROACH"}, [(290, EnvironmentKind.BUILDING_RESIDENTIAL)]),
    "empty_static": ({}, []),
    "fallback": ({"noiseSensitivity": "HIGH"}, []),
}


def scenario(name):
    profile, features = SCENARIOS[name]
    request = SearchAreaRequest.model_validate(
        {
            "reportId": 1,
            "species": "강아지",
            "size": "중형",
            "eventDate": "2026-10-28",
            "eventHour": 12,
            "latitude": ORIGIN.latitude,
            "longitude": ORIGIN.longitude,
            "behaviorProfile": profile,
        }
    )
    data = EnvironmentData(
        "FIXED_TEST_DATA",
        tuple(
            EnvironmentFeature(offset_point(ORIGIN, north, 0), frozenset({kind}))
            for north, kind in features
        ),
    )
    return request, data


class FailedProvider:
    async def fetch(self, center, radius_meters):
        raise EnvironmentProviderError("fixed failure")


def v1_result(name):
    request, data = scenario(name)
    provider = FailedProvider() if name == "fallback" else StaticEnvironmentProvider(data)
    service = SearchAreaRecommendationService(provider, lambda: NOW)
    return asyncio.run(service.recommend(request)).model_dump(by_alias=True, mode="json")


@pytest.mark.parametrize("name", SCENARIOS)
def test_v1_wire_golden(name):
    assert v1_result(name) == json.loads(GOLDEN.read_text())[name]
