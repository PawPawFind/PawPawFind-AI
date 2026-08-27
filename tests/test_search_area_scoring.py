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
    parse_overpass_response,
)
from app.search_area.geo import GeoPoint, GridCell, distance_meters, generate_grid, offset_point
from app.search_area.scoring import (
    AreaCandidate,
    EnvironmentSpatialIndex,
    ScoreComponents,
    ScoredCell,
    cluster_scored_cells,
    remove_overlapping_candidates,
    score_grid,
    select_area_candidates,
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


def test_spatial_index_includes_feature_on_influence_boundary() -> None:
    boundary = offset_point(ORIGIN, 300, 0)
    data = environment(EnvironmentKind.GREEN_SPACE, boundary)
    index = EnvironmentSpatialIndex(data, ORIGIN, bucket_size_meters=300)

    assert index.nearby(ORIGIN, 300) == data.features


def test_spatial_index_preserves_brute_force_scores_and_nearby_kinds() -> None:
    cells = generate_grid(ORIGIN, 400)
    data = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                offset_point(ORIGIN, 300, 0), frozenset({EnvironmentKind.GREEN_SPACE})
            ),
            EnvironmentFeature(
                offset_point(ORIGIN, -250, 200), frozenset({EnvironmentKind.FOOTPATH})
            ),
            EnvironmentFeature(
                offset_point(ORIGIN, 1000, 1000), frozenset({EnvironmentKind.MAJOR_ROAD})
            ),
        ),
    )
    optimized = score_grid(cells, 400, BehaviorType.FEARFUL, BehaviorProfile(), data)
    expected = []
    for cell in cells:
        nearby = tuple(
            feature
            for feature in data.features
            if distance_meters(cell.center, feature.point) <= 300
        )
        expected.append(
            score_grid(
                [cell],
                400,
                BehaviorType.FEARFUL,
                BehaviorProfile(),
                EnvironmentData("TEST", nearby),
            )[0]
        )

    assert [item.priority_score for item in optimized] == [item.priority_score for item in expected]
    assert [item.nearby_kinds for item in optimized] == [item.nearby_kinds for item in expected]


def test_spatial_index_handles_empty_and_small_environment_data() -> None:
    cell = GridCell(0, 0, ORIGIN, 0)
    empty = score_grid(
        [cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), EnvironmentData("TEST", ())
    )
    small = score_grid(
        [cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), environment(EnvironmentKind.ROAD)
    )

    assert len(empty) == 1
    assert small[0].nearby_kinds == {EnvironmentKind.ROAD}


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


def test_non_blocking_barrier_does_not_receive_accessibility_penalty() -> None:
    cell = GridCell(0, 0, ORIGIN, 0)
    gate_environment = parse_overpass_response(
        {
            "elements": [
                {
                    "lat": ORIGIN.latitude,
                    "lon": ORIGIN.longitude,
                    "tags": {"barrier": "gate"},
                }
            ]
        }
    )
    score = score_grid([cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), gate_environment)[0]

    assert score.components.accessibility == 1.0


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


def scored_cell(row: int, column: int, score: float) -> ScoredCell:
    components = ScoreComponents(1, 1, 1, 1, 1)
    return ScoredCell(
        GridCell(
            row,
            column,
            offset_point(ORIGIN, row * 200, column * 200),
            (row**2 + column**2) ** 0.5 * 200,
        ),
        score,
        components,
        frozenset({EnvironmentKind.GREEN_SPACE}) if column == 0 else frozenset(),
    )


def test_continuous_score_cluster_is_split_into_two_distinct_representatives() -> None:
    scored = [scored_cell(0, 0, 90), scored_cell(0, 1, 89), scored_cell(0, 2, 88)]

    selected = select_area_candidates(scored)

    assert len(selected) == 2
    assert selected[0] is not selected[1]
    assert selected[0].center != selected[1].center
    assert selected[0].kinds != selected[1].kinds
    assert [item.priority_score for item in selected] == [90, 89]


@pytest.mark.parametrize("count", [2, 3, 4])
def test_separate_valid_clusters_return_top_candidates_up_to_three(count: int) -> None:
    scored = [scored_cell(index * 5, 0, 90 - index) for index in range(count)]

    selected = select_area_candidates(scored)

    assert len(selected) == min(count, 3)
    assert [item.priority_score for item in selected] == list(range(90, 90 - min(count, 3), -1))


def test_candidate_selection_is_deterministic() -> None:
    scored = [scored_cell(0, 0, 90), scored_cell(0, 1, 89), scored_cell(0, 2, 88)]

    assert select_area_candidates(scored) == select_area_candidates(scored)


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
    assert 2 <= len(response.areas) <= 3
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
    assert len(response.areas) == 2
    assert response.areas[0].center.latitude == ORIGIN.latitude
    assert response.areas[0].center == response.areas[1].center
    assert response.areas[0].radius_meters < response.areas[1].radius_meters
    assert response.areas[0].priority_score > response.areas[1].priority_score
    assert response.areas[0].reason_codes == ["ENVIRONMENT_FALLBACK", "LAST_SEEN_LOCATION"]
    assert response.areas[1].reason_codes == [
        "ENVIRONMENT_FALLBACK",
        "EXPANDED_SEARCH_RADIUS",
    ]
    assert "환경 데이터를 사용할 수 없어" in response.areas[1].reason
    assert "확장 수색" in response.areas[1].reason
    assert all(150 <= area.radius_meters <= 500 for area in response.areas)
