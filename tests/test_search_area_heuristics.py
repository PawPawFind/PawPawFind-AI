from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.search_area import BehaviorProfile, BehaviorType, SearchAreaRequest
from app.search_area.heuristics import (
    ESTIMATED_CURRENT_TIME_ASSUMPTION,
    ESTIMATED_EVENT_HOUR_ASSUMPTION,
    calculate_elapsed_time,
    calculate_search_radius,
    classify_behavior,
)

SEOUL = ZoneInfo("Asia/Seoul")


def request(**overrides: object) -> SearchAreaRequest:
    payload: dict[str, object] = {
        "reportId": 1,
        "species": "강아지",
        "size": "중형",
        "eventDate": "2026-08-24",
        "eventHour": 12,
        "latitude": 37.5,
        "longitude": 127.0,
    }
    payload.update(overrides)
    return SearchAreaRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ({"escapeCause": "CHASE", "strangerResponse": "AVOID"}, BehaviorType.CHASE_DRIVEN),
        ({"noiseSensitivity": "HIGH", "strangerResponse": "APPROACH"}, BehaviorType.FEARFUL),
        ({"strangerResponse": "APPROACH"}, BehaviorType.HUMAN_SEEKING),
        ({}, BehaviorType.ALOOF),
    ],
)
def test_classifies_all_behavior_types(profile: dict[str, str], expected: BehaviorType) -> None:
    assert classify_behavior(BehaviorProfile.model_validate(profile)) is expected


def test_missing_hour_uses_seoul_noon_and_records_assumption() -> None:
    result = calculate_elapsed_time(
        request(eventHour=None), datetime(2026, 8, 24, 15, tzinfo=SEOUL)
    )

    assert result.hours == 3
    assert result.event_at.hour == 12
    assert result.assumptions == (ESTIMATED_EVENT_HOUR_ASSUMPTION,)


def test_missing_hour_on_current_morning_uses_current_seoul_time() -> None:
    current = datetime(2026, 8, 24, 9, 30, tzinfo=SEOUL)
    result = calculate_elapsed_time(request(eventHour=None), current)

    assert result.event_at == current
    assert result.hours == 0
    assert result.assumptions == (ESTIMATED_CURRENT_TIME_ASSUMPTION,)


def test_explicit_future_hour_on_current_day_is_rejected() -> None:
    with pytest.raises(ValueError, match="미래"):
        calculate_elapsed_time(request(eventHour=10), datetime(2026, 8, 24, 9, 30, tzinfo=SEOUL))


def test_elapsed_time_is_deterministic_with_injected_now() -> None:
    fixed_now = datetime(2026, 8, 25, 12, tzinfo=SEOUL)
    assert calculate_elapsed_time(request(), fixed_now).hours == 24
    assert calculate_elapsed_time(request(), fixed_now).hours == 24


def test_future_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="미래"):
        calculate_elapsed_time(request(eventDate="2026-08-26"), datetime(2026, 8, 25, tzinfo=SEOUL))


@pytest.mark.parametrize(("size", "radius"), [("소형", 500), ("중형", 1000), ("대형", 1500)])
def test_size_base_radius_at_24_hours(size: str, radius: int) -> None:
    assert calculate_search_radius(request(size=size), 24) == radius


@pytest.mark.parametrize(
    ("hours", "radius"),
    [(6, 600), (6.01, 1000), (24, 1000), (24.01, 1400), (72, 1400), (72.01, 1800)],
)
def test_elapsed_time_boundaries(hours: float, radius: int) -> None:
    assert calculate_search_radius(request(), hours) == radius


@pytest.mark.parametrize(
    ("profile", "radius"),
    [
        ({"activityLevel": "LOW"}, 800),
        ({"activityLevel": "MEDIUM"}, 1000),
        ({"activityLevel": "HIGH"}, 1250),
        ({"mobility": "LIMITED"}, 500),
        ({"escapeCause": "NOISE"}, 1100),
        ({"escapeCause": "CHASE"}, 1200),
    ],
)
def test_profile_multipliers(profile: dict[str, str], radius: int) -> None:
    assert calculate_search_radius(request(behaviorProfile=profile), 24) == radius


def test_radius_is_clamped_to_minimum_and_maximum() -> None:
    minimum = calculate_search_radius(
        request(size="소형", behaviorProfile={"activityLevel": "LOW", "mobility": "LIMITED"}), 1
    )
    maximum = calculate_search_radius(
        request(size="대형", behaviorProfile={"activityLevel": "HIGH", "escapeCause": "CHASE"}),
        100,
    )

    assert minimum == 300
    assert maximum == 3000
