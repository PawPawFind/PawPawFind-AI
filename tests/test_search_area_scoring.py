from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.search_area import BehaviorProfile, BehaviorType, SearchAreaRequest
from app.search_area.environment import (
    EnvironmentData,
    EnvironmentFeature,
    EnvironmentKind,
    EnvironmentProviderError,
    StaticEnvironmentProvider,
)
from app.search_area.geo import GeoPoint, GridCell, generate_grid, offset_point
from app.search_area.scoring import (
    AreaCandidate,
    ScoreComponents,
    ScoredCell,
    cluster_scored_cells,
    remove_overlapping_candidates,
    score_grid,
)
from app.services.search_area import SearchAreaRecommendationService

SEOUL = ZoneInfo("Asia/Seoul")
ORIGIN = GeoPoint(37.5665, 126.978)


def environment(kind: EnvironmentKind, point: GeoPoint = ORIGIN) -> EnvironmentData:
    return EnvironmentData(
        source="FIXED_TEST_DATA",
        features=(EnvironmentFeature(point, frozenset({kind})),),
    )


def test_behavior_environment_changes_score_and_scores_are_normalized() -> None:
    cell = generate_grid(ORIGIN, 300)[0]
    fearful = score_grid(
        [cell],
        300,
        BehaviorType.FEARFUL,
        BehaviorProfile(),
        environment(EnvironmentKind.GREEN_SPACE),
    )[0]
    human = score_grid(
        [cell],
        300,
        BehaviorType.HUMAN_SEEKING,
        BehaviorProfile(),
        environment(EnvironmentKind.GREEN_SPACE),
    )[0]

    assert fearful.priority_score > human.priority_score
    assert 0 <= fearful.priority_score <= 100
    assert all(0 <= value <= 1 for value in vars(fearful.components).values())


def test_major_road_and_railway_reduce_accessibility() -> None:
    cell = GridCell(0, 0, ORIGIN, 0)
    safe = score_grid(
        [cell],
        1000,
        BehaviorType.ALOOF,
        BehaviorProfile(),
        environment(EnvironmentKind.GREEN_SPACE),
    )[0]
    barriers = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                ORIGIN,
                frozenset({EnvironmentKind.MAJOR_ROAD, EnvironmentKind.RAILWAY_BARRIER}),
            ),
        ),
    )
    blocked = score_grid([cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), barriers)[0]
    assert blocked.components.accessibility < safe.components.accessibility


def test_adjacent_high_scoring_cells_are_clustered() -> None:
    components = ScoreComponents(1, 1, 1, 1, 1)
    scored = [
        ScoredCell(GridCell(0, 0, ORIGIN, 0), 90, components, frozenset()),
        ScoredCell(GridCell(0, 1, offset_point(ORIGIN, 0, 200), 200), 80, components, frozenset()),
        ScoredCell(
            GridCell(5, 5, offset_point(ORIGIN, 1000, 1000), 1414), 85, components, frozenset()
        ),
    ]
    clusters = cluster_scored_cells(scored)

    assert len(clusters) == 2
    assert all(150 <= item.radius_meters <= 500 for item in clusters)


def test_overlapping_lower_ranked_candidates_are_removed_and_limited() -> None:
    candidates = [
        AreaCandidate(ORIGIN, 300, 90, frozenset()),
        AreaCandidate(offset_point(ORIGIN, 0, 100), 300, 80, frozenset()),
        AreaCandidate(offset_point(ORIGIN, 0, 1000), 200, 70, frozenset()),
        AreaCandidate(offset_point(ORIGIN, 1000, 0), 200, 60, frozenset()),
        AreaCandidate(offset_point(ORIGIN, -1000, 0), 200, 50, frozenset()),
    ]
    selected = remove_overlapping_candidates(candidates)

    assert [item.priority_score for item in selected] == [90, 70, 60]


class FailingProvider:
    async def fetch(self, center: GeoPoint, radius_meters: int) -> EnvironmentData:
        raise EnvironmentProviderError("failed")


def request() -> SearchAreaRequest:
    return SearchAreaRequest.model_validate(
        {
            "reportId": 1,
            "species": "강아지",
            "size": "중형",
            "eventDate": "2026-08-24",
            "eventHour": 13,
            "latitude": ORIGIN.latitude,
            "longitude": ORIGIN.longitude,
            "behaviorProfile": {"noiseSensitivity": "HIGH"},
        }
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_service_uses_injected_provider_and_returns_ranked_areas() -> None:
    provider = StaticEnvironmentProvider(environment(EnvironmentKind.GREEN_SPACE))
    service = SearchAreaRecommendationService(
        provider, now_provider=lambda: datetime(2026, 8, 25, 13, tzinfo=SEOUL)
    )
    response = await service.recommend(request())

    assert response.fallback_used is False
    assert response.environment_source == "FIXED_TEST_DATA"
    assert 1 <= len(response.areas) <= 3
    assert [area.rank for area in response.areas] == list(range(1, len(response.areas) + 1))
    assert [area.priority_score for area in response.areas] == sorted(
        (area.priority_score for area in response.areas), reverse=True
    )


@pytest.mark.anyio
async def test_service_returns_last_seen_fallback_without_network() -> None:
    service = SearchAreaRecommendationService(
        FailingProvider(), now_provider=lambda: datetime(2026, 8, 25, 13, tzinfo=SEOUL)
    )
    response = await service.recommend(request())

    assert response.fallback_used is True
    assert response.environment_source == "UNAVAILABLE"
    assert len(response.areas) == 1
    assert response.areas[0].center.latitude == ORIGIN.latitude
    assert response.areas[0].reason_codes == ["ENVIRONMENT_FALLBACK", "LAST_SEEN_LOCATION"]
