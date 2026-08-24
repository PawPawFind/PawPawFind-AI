import pytest
from pydantic import ValidationError

from app.schemas.search_area import (
    ActivityLevel,
    BehaviorProfile,
    BehaviorType,
    SearchAreaCenter,
    SearchAreaRequest,
    SearchAreaResponse,
)
from app.search_area.config import SEARCH_AREA_CONFIG


def valid_payload() -> dict[str, object]:
    return {
        "reportId": 1,
        "species": "강아지",
        "size": "중형",
        "eventDate": "2026-08-24",
        "eventHour": 13,
        "latitude": 37.5665,
        "longitude": 126.978,
        "behaviorProfile": {"activityLevel": "HIGH"},
    }


def test_request_parses_camel_case_and_serializes_aliases() -> None:
    request = SearchAreaRequest.model_validate(valid_payload())

    assert request.report_id == 1
    assert request.event_date.isoformat() == "2026-08-24"
    assert request.behavior_profile.activity_level is ActivityLevel.HIGH
    dumped = request.model_dump(by_alias=True, mode="json")
    assert dumped["reportId"] == 1
    assert dumped["behaviorProfile"]["activityLevel"] == "HIGH"


def test_behavior_profile_defaults_every_value_to_unknown() -> None:
    profile = BehaviorProfile()

    assert set(profile.model_dump(mode="json").values()) == {"UNKNOWN"}
    request = SearchAreaRequest.model_validate({**valid_payload(), "behaviorProfile": None})
    assert request.behavior_profile == profile


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("reportId", 0),
        ("species", "고양이"),
        ("size", "초대형"),
        ("eventHour", 24),
        ("latitude", 91),
        ("longitude", -181),
    ],
)
def test_request_rejects_invalid_values(field: str, value: object) -> None:
    payload = valid_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        SearchAreaRequest.model_validate(payload)


def test_response_serializes_camel_case() -> None:
    response = SearchAreaResponse(
        reportId=1,
        algorithmVersion="HEURISTIC_V1",
        behaviorType=BehaviorType.FEARFUL,
        estimatedRadiusMeters=1000,
        environmentSource="FALLBACK",
        fallbackUsed=True,
        assumptions=[],
        areas=[],
    )

    body = response.model_dump(by_alias=True, mode="json")
    assert body["algorithmVersion"] == "HEURISTIC_V1"
    assert body["estimatedRadiusMeters"] == 1000
    assert SearchAreaCenter(latitude=37.5, longitude=127.0).latitude == 37.5


def test_heuristic_configuration_is_centralized_and_consistent() -> None:
    assert dict(SEARCH_AREA_CONFIG.base_radius_by_size) == {
        "소형": 500,
        "중형": 1000,
        "대형": 1500,
    }
    assert sum(dict(SEARCH_AREA_CONFIG.score_weights).values()) == pytest.approx(1.0)
