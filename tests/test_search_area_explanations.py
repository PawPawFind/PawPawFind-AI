import pytest

from app.schemas.search_area import BehaviorProfile, BehaviorType
from app.search_area.environment import EnvironmentData, EnvironmentFeature, EnvironmentKind
from app.search_area.explanations import explain_candidate
from app.search_area.geo import GridCell, offset_point
from app.search_area.scoring import AreaCandidate, rounded_contributions
from app.search_area.scoring_v2 import score_grid_v2
from tests.test_search_area_compare import compare
from tests.test_search_area_golden import ORIGIN, SCENARIOS


def candidate(data, behavior=BehaviorType.FEARFUL, distance=0):
    cell = score_grid_v2(
        [GridCell(0, 0, ORIGIN, distance)], 1000, behavior, BehaviorProfile(), data
    )[0]
    return AreaCandidate(ORIGIN, 150, round(cell.priority_score), cell.nearby_kinds, (cell,))


def test_real_winner_explained_instead_of_incidental_green_space():
    data = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                offset_point(ORIGIN, 290, 0), frozenset({EnvironmentKind.GREEN_SPACE})
            ),
            EnvironmentFeature(ORIGIN, frozenset({EnvironmentKind.BUILDING_RESIDENTIAL})),
        ),
    )
    item = candidate(data)
    codes, text = explain_candidate(item, BehaviorType.FEARFUL)
    assert "BEHAVIOR_NEAR_BUILDING_RESIDENTIAL" in codes
    assert "BEHAVIOR_NEAR_GREEN_SPACE" not in codes
    assert "주거 건물" in text
    assert "두려움" in text
    assert "참고 정보" in text


def test_larger_actual_contribution_is_explained_first():
    data = EnvironmentData(
        "TEST",
        (
            EnvironmentFeature(
                ORIGIN, frozenset({EnvironmentKind.GREEN_SPACE, EnvironmentKind.FOOTPATH})
            ),
        ),
    )
    item = candidate(data, distance=950)
    codes, text = explain_candidate(item, BehaviorType.FEARFUL)
    assert codes[:2] == ["BEHAVIOR_NEAR_GREEN_SPACE", "CORRIDOR_NEAR_FOOTPATH"]
    assert codes[2] == "DISTANCE_FROM_LAST_SEEN"
    assert text.index("녹지") < text.index("보행로") < text.index("실종 위치")
    assert len(codes) == 3
    assert rounded_contributions(item)["distance"] < rounded_contributions(item)["corridor"]


def test_empty_environment_explanation_is_conservative():
    item = candidate(EnvironmentData("TEST", ()))
    codes, text = explain_candidate(item, BehaviorType.FEARFUL)
    assert codes == ["DISTANCE_FROM_LAST_SEEN", "LIMITED_ENVIRONMENT_EVIDENCE"]
    assert "제한적" in text
    assert not any(word in text for word in ["녹지", "보행로", "주거 건물", "통행량", "교통량"])


@pytest.mark.parametrize("name", SCENARIOS)
def test_v2_reason_codes_match_scored_evidence_and_do_not_claim_unmeasured_facts(name):
    response = compare(name)
    for area in response.improved.areas:
        codes, text = area.reason_codes, area.reason
        assert "LOW_TRAFFIC" not in codes
        assert not any(
            phrase in text
            for phrase in [
                "발견 확률이 높",
                "실제 이동한 경로",
                "안전한 지역",
                "반드시",
                "교통량이 적",
                "차량 통행량이 낮",
            ]
        )
        if response.improved.fallback_used:
            assert area.score_breakdown is None
            continue
        assert 2 <= len(codes) <= 3
        assert "참고 정보" in text
        parts = area.score_breakdown
        for code in codes:
            if code.startswith("BEHAVIOR_NEAR_"):
                assert parts.behavior_environment > 0
            if code.startswith("CORRIDOR_NEAR_"):
                assert parts.corridor > 0
            if code == "DISTANCE_FROM_LAST_SEEN":
                assert parts.distance > 0


def test_accessibility_reason_describes_penalty_not_impassability_or_traffic():
    data = EnvironmentData(
        "TEST", (EnvironmentFeature(ORIGIN, frozenset({EnvironmentKind.MAJOR_ROAD})),)
    )
    codes, text = explain_candidate(candidate(data), BehaviorType.FEARFUL)
    assert "BARRIER_DISTANCE_CONSIDERED" in codes
    assert "감점" in text
    assert "실제 통과 가능 여부를 판단한 결과는 아닙니다" in text
    assert "교통량" not in text
