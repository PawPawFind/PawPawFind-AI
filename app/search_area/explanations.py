"""V2 explanations use actual weighted cell contributions and winning features."""

from app.schemas.search_area import BehaviorType
from app.search_area.environment import EnvironmentKind
from app.search_area.scoring import AreaCandidate, candidate_contributions

ENVIRONMENT_LABELS = {
    EnvironmentKind.GREEN_SPACE: "녹지",
    EnvironmentKind.FOOTPATH: "보행로",
    EnvironmentKind.WATER: "수변",
    EnvironmentKind.ROAD: "일반 도로",
    EnvironmentKind.COMMERCIAL: "상업 시설",
    EnvironmentKind.BUILDING_RESIDENTIAL: "주거 건물",
}
BEHAVIOR_LABELS = {
    BehaviorType.FEARFUL: "두려움 관련 행동 특성",
    BehaviorType.CHASE_DRIVEN: "추격 성향",
    BehaviorType.HUMAN_SEEKING: "사람에게 접근하는 행동 특성",
    BehaviorType.ALOOF: "독립적으로 이동하는 행동 특성",
}


def explain_candidate(candidate: AreaCandidate, behavior: BehaviorType) -> tuple[list[str], str]:
    parts = candidate_contributions(candidate)
    evidence: list[tuple[float, str, str]] = []
    if parts["distance"] > 0:
        evidence.append(
            (
                parts["distance"],
                "DISTANCE_FROM_LAST_SEEN",
                "실종 위치와의 거리가 우선점수에 반영되었습니다.",
            )
        )
    for component, field, prefix, description in (
        ("behavior_environment", "behavior_kind", "BEHAVIOR_NEAR_", "행동·환경 적합도"),
        ("corridor", "corridor_kind", "CORRIDOR_NEAR_", "이동 통로 관련 점수"),
    ):
        # Winning kinds only: an incidental union of nearby kinds is not evidence.
        by_kind: dict[EnvironmentKind, float] = {}
        for cell in candidate.cells:
            kind = getattr(cell, field)
            if kind is not None:
                by_kind[kind] = by_kind.get(kind, 0.0) + getattr(cell.components, component)
        if by_kind and parts[component] > 0:
            kind = min(by_kind, key=lambda kind: (-by_kind[kind], kind.value))
            evidence.append(
                (
                    parts[component],
                    prefix + kind.value,
                    f"{BEHAVIOR_LABELS[behavior]}을 고려한 {description}에 "
                    f"구성 격자와 {ENVIRONMENT_LABELS[kind]} 대표점의 "
                    "가까운 거리가 반영되었습니다.",
                )
            )
    if parts["accessibility"] > 0 and candidate.kinds.intersection(
        {EnvironmentKind.MAJOR_ROAD, EnvironmentKind.RAILWAY_BARRIER, EnvironmentKind.ROAD}
    ):
        evidence.append(
            (
                parts["accessibility"],
                "BARRIER_DISTANCE_CONSIDERED",
                "도로·장벽 대표점과의 거리에 따른 감점을 반영했습니다. "
                "실제 통과 가능 여부를 판단한 결과는 아닙니다.",
            )
        )
    chosen = sorted(evidence, key=lambda item: -item[0])[:3]
    codes = [code for _, code, _ in chosen]
    sentences = [sentence for _, _, sentence in chosen]
    if len(chosen) < 2:
        codes.append("LIMITED_ENVIRONMENT_EVIDENCE")
        sentences.append("주변 환경에 관한 추천 근거가 제한적입니다.")
    return codes, " ".join(sentences) + " 우선 수색을 위한 참고 정보입니다."
