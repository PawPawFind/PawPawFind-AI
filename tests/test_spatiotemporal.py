import pytest

from app.reid.spatiotemporal import (
    address_location_similarity,
    address_units,
    location_similarity,
    spatiotemporal_similarity,
    time_similarity,
)


def test_address_location_similarity_rewards_shared_district() -> None:
    assert (
        address_location_similarity("서울특별시 마포구 연남동", "서울특별시 마포구 합정동") == 0.70
    )
    assert address_location_similarity("서울특별시 마포구", "제주특별자치도 제주시") == 0.10


def test_address_location_similarity_requires_matching_parent_for_same_dong() -> None:
    assert (
        address_location_similarity(
            "서울특별시 마포구 중앙동",
            "부산광역시 중구 중앙동",
        )
        == 0.10
    )
    assert (
        address_location_similarity(
            "서울특별시 마포구 중앙동",
            "서울특별시 마포구 중앙동",
        )
        == 0.90
    )


def test_address_location_similarity_parses_compact_korean_address() -> None:
    compact = "서울특별시마포구중앙동"
    assert address_units(compact) == ["서울특별시", "마포구", "중앙동"]
    assert address_location_similarity(compact, compact) == 0.90


def test_address_location_similarity_ignores_numeric_building_dong() -> None:
    query = "서울특별시 마포구 성산동 101동"
    candidate = "서울특별시 마포구 연남동 101동"
    assert "101동" not in address_units(query)
    assert address_location_similarity(query, candidate) == 0.70


def test_address_location_similarity_ignores_prefixed_building_dong() -> None:
    query = "서울특별시 마포구 성산동 제101동"
    candidate = "서울특별시 마포구 연남동 제101동"
    assert "제101동" not in address_units(query)
    assert address_location_similarity(query, candidate) == 0.70


def test_coordinate_location_score_decreases_with_distance() -> None:
    query = {"latitude": 37.5665, "longitude": 126.9780}
    nearby = location_similarity(query, {"latitude": 37.5700, "longitude": 126.9800})
    far = location_similarity(query, {"latitude": 33.4996, "longitude": 126.5312})

    assert nearby["method"] == "coordinates"
    assert far["method"] == "coordinates"
    assert nearby["score"] > far["score"]
    assert nearby["distance_km"] < far["distance_km"]


def test_time_similarity_penalizes_found_before_lost() -> None:
    correct = time_similarity(
        {"report_type": "LOST", "lost_at": "2026-08-01"},
        {"report_type": "FOUND", "found_at": "2026-08-03"},
    )
    impossible = time_similarity(
        {"report_type": "LOST", "lost_at": "2026-08-10"},
        {"report_type": "FOUND", "found_at": "2026-08-01"},
    )

    assert correct == {"score": 1.0, "elapsed_days": 2}
    assert impossible == {"score": 0.05, "elapsed_days": -9}


def test_spatiotemporal_combines_available_location_and_time() -> None:
    result = spatiotemporal_similarity(
        {
            "report_type": "LOST",
            "lost_at": "2026-08-01",
            "address": "서울특별시 마포구 연남동",
        },
        {
            "report_type": "FOUND",
            "found_at": "2026-08-02",
            "address": "서울특별시 마포구 합정동",
        },
    )

    assert result["location_method"] == "address_units"
    assert result["location_score"] == 0.70
    assert result["time_score"] == 1.0
    assert result["score"] == pytest.approx(0.805)
