from dataclasses import replace

import pytest

from app.schemas.search_area import BehaviorProfile, BehaviorType
from app.search_area.config import SEARCH_AREA_CONFIG
from app.search_area.environment import EnvironmentData, EnvironmentFeature, EnvironmentKind
from app.search_area.geo import GridCell, distance_meters, offset_point
from app.search_area.scoring import rounded_contributions, score_grid, select_area_candidates
from app.search_area.scoring_v2 import proximity, score_grid_v2
from tests.test_search_area_golden import ORIGIN, SCENARIOS, scenario


def scored(
    kind, distance=0, behavior=BehaviorType.FEARFUL, profile=None, config=SEARCH_AREA_CONFIG
):
    data = EnvironmentData(
        "TEST", (EnvironmentFeature(offset_point(ORIGIN, distance, 0), frozenset({kind})),)
    )
    return score_grid_v2(
        [GridCell(0, 0, ORIGIN, 0)], 1000, behavior, profile or BehaviorProfile(), data, config
    )[0]


@pytest.mark.parametrize(
    "distance,expected", [(0, 1), (75, 0.75), (150, 0.5), (225, 0.25), (300, 0), (301, 0)]
)
def test_linear_decay(distance, expected):
    assert proximity(distance, 300) == expected


def test_invalid_radius():
    with pytest.raises(ValueError):
        proximity(0, 0)


@pytest.mark.parametrize(
    "behavior,kind,preference",
    [
        (BehaviorType.FEARFUL, EnvironmentKind.GREEN_SPACE, 1),
        (BehaviorType.CHASE_DRIVEN, EnvironmentKind.FOOTPATH, 1),
        (BehaviorType.HUMAN_SEEKING, EnvironmentKind.COMMERCIAL, 1),
        (BehaviorType.ALOOF, EnvironmentKind.GREEN_SPACE, 0.8),
    ],
)
def test_behavior_preferences_and_decay(behavior, kind, preference):
    assert scored(kind, 0, behavior).components.behavior_environment == preference
    assert scored(kind, 150, behavior).components.behavior_environment == pytest.approx(
        preference / 2
    )
    assert scored(kind, 300, behavior).components.behavior_environment == pytest.approx(
        0, abs=1e-10
    )
    assert scored(kind, 301, behavior).components.behavior_environment == 0


@pytest.mark.parametrize(
    "kind,preference",
    [
        (EnvironmentKind.FOOTPATH, 1),
        (EnvironmentKind.GREEN_SPACE, 0.7),
        (EnvironmentKind.WATER, 0.7),
        (EnvironmentKind.ROAD, 0.3),
    ],
)
def test_corridor_decay(kind, preference):
    assert scored(kind).components.corridor == preference
    assert scored(kind, 150).components.corridor == pytest.approx(preference / 2)


@pytest.mark.parametrize(
    "kind,penalty",
    [
        (EnvironmentKind.MAJOR_ROAD, 0.7),
        (EnvironmentKind.RAILWAY_BARRIER, 0.8),
        (EnvironmentKind.ROAD, 0.2),
    ],
)
def test_accessibility_penalty_decays(kind, penalty):
    assert scored(kind).components.accessibility == pytest.approx(1 - penalty)
    assert scored(kind, 150).components.accessibility == pytest.approx(1 - penalty / 2)
    assert scored(kind, 301).components.accessibility == 1


def test_multiple_features_max_preference_times_proximity_not_max_preference_first():
    data = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                offset_point(ORIGIN, 290, 0), frozenset({EnvironmentKind.GREEN_SPACE})
            ),
            EnvironmentFeature(ORIGIN, frozenset({EnvironmentKind.BUILDING_RESIDENTIAL})),
        ),
    )
    cell = GridCell(0, 0, ORIGIN, 0)
    item = score_grid_v2([cell], 1000, BehaviorType.FEARFUL, BehaviorProfile(), data)[0]
    assert item.components.behavior_environment == 0.8
    assert item.behavior_kind is EnvironmentKind.BUILDING_RESIDENTIAL
    duplicated = EnvironmentData("TEST", data.features * 2)
    assert (
        score_grid_v2([cell], 1000, BehaviorType.FEARFUL, BehaviorProfile(), duplicated)[0] == item
    )
    assert (
        score_grid_v2(
            [cell],
            1000,
            BehaviorType.FEARFUL,
            BehaviorProfile(),
            EnvironmentData("TEST", tuple(reversed(data.features))),
        )[0]
        == item
    )


def test_configurable_influence_radius():
    item = scored(
        EnvironmentKind.GREEN_SPACE,
        150,
        config=replace(SEARCH_AREA_CONFIG, environment_influence_meters=600),
    )
    assert item.components.behavior_environment == pytest.approx(0.75)


@pytest.mark.parametrize("name", [name for name in SCENARIOS if name != "fallback"])
def test_scenarios_range_distance_and_selection(name):
    from app.search_area.geo import generate_grid
    from app.search_area.heuristics import classify_behavior

    request, data = scenario(name)
    cells = generate_grid(ORIGIN, 1000)
    behavior = classify_behavior(request.behavior_profile)
    v1 = score_grid(cells, 1000, behavior, request.behavior_profile, data)
    v2 = score_grid_v2(cells, 1000, behavior, request.behavior_profile, data)
    assert [x.components.distance for x in v1] == [x.components.distance for x in v2]
    assert all(0 <= x.priority_score <= 100 for x in v2)
    selected = select_area_candidates(v2)
    assert 2 <= len(selected) <= 3
    assert selected == select_area_candidates(v2)
    assert [x.priority_score for x in selected] == sorted(
        (x.priority_score for x in selected), reverse=True
    )
    for i, a in enumerate(selected):
        assert sum(rounded_contributions(a).values()) == a.priority_score
        for b in selected[i + 1 :]:
            assert distance_meters(a.center, b.center) >= 0.6 * (a.radius_meters + b.radius_meters)


def test_sparse_environment_does_not_invent_positive_environment_contributions():
    cell = GridCell(0, 0, ORIGIN, 0)
    item = score_grid_v2(
        [cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), EnvironmentData("TEST", ())
    )[0]
    assert item.components.behavior_environment == 0
    assert item.components.corridor == 0
    assert item.behavior_kind is None
    assert item.corridor_kind is None


def test_event_context_retains_behavior_meaning_with_decay():
    for behavior, kind in [
        (BehaviorType.CHASE_DRIVEN, EnvironmentKind.FOOTPATH),
        (BehaviorType.HUMAN_SEEKING, EnvironmentKind.COMMERCIAL),
        (BehaviorType.ALOOF, EnvironmentKind.GREEN_SPACE),
    ]:
        assert (
            scored(kind, 0, behavior).components.event_context
            > scored(kind, 150, behavior).components.event_context
        )
    assert (
        scored(EnvironmentKind.MAJOR_ROAD, 0).components.event_context
        < scored(EnvironmentKind.MAJOR_ROAD, 150).components.event_context
    )
    profile = BehaviorProfile(mobility="LIMITED")
    assert (
        scored(EnvironmentKind.RAILWAY_BARRIER, 0, profile=profile).components.event_context
        < scored(EnvironmentKind.RAILWAY_BARRIER, 150, profile=profile).components.event_context
    )


def test_combined_penalties_clamp_and_duplicate_features_do_not_stack():
    data = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                ORIGIN,
                frozenset(
                    {
                        EnvironmentKind.MAJOR_ROAD,
                        EnvironmentKind.RAILWAY_BARRIER,
                        EnvironmentKind.ROAD,
                    }
                ),
            ),
        ),
    )
    cell = GridCell(0, 0, ORIGIN, 0)
    item = score_grid_v2([cell], 1000, BehaviorType.ALOOF, BehaviorProfile(), data)[0]
    assert item.components.accessibility == 0
    assert (
        score_grid_v2(
            [cell],
            1000,
            BehaviorType.ALOOF,
            BehaviorProfile(),
            EnvironmentData("TEST", data.features * 10),
        )[0]
        == item
    )


def test_empty_grid_and_invalid_config():
    assert (
        score_grid_v2([], 1000, BehaviorType.ALOOF, BehaviorProfile(), EnvironmentData("TEST", ()))
        == []
    )
    with pytest.raises(ValueError):
        scored(
            EnvironmentKind.FOOTPATH,
            config=replace(SEARCH_AREA_CONFIG, environment_influence_meters=0),
        )
