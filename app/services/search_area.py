from collections.abc import Callable
from datetime import datetime

from app.schemas.search_area import (
    BehaviorType,
    RecommendedSearchArea,
    SearchAreaCenter,
    SearchAreaRequest,
    SearchAreaResponse,
)
from app.search_area.config import SEARCH_AREA_CONFIG
from app.search_area.environment import (
    EnvironmentKind,
    EnvironmentProvider,
    EnvironmentProviderError,
)
from app.search_area.geo import GeoPoint, generate_grid
from app.search_area.heuristics import (
    SEOUL_TIMEZONE,
    calculate_elapsed_time,
    calculate_search_radius,
    classify_behavior,
)
from app.search_area.scoring import score_grid, select_area_candidates

FALLBACK_ASSUMPTION = "주변 환경 데이터를 사용할 수 없어 마지막 목격 위치를 중심으로 추천했습니다."


class SearchAreaRecommendationService:
    def __init__(
        self,
        environment_provider: EnvironmentProvider,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.environment_provider = environment_provider
        self.now_provider = now_provider or (lambda: datetime.now(SEOUL_TIMEZONE))

    async def recommend(self, request: SearchAreaRequest) -> SearchAreaResponse:
        behavior_type = classify_behavior(request.behavior_profile)
        elapsed = calculate_elapsed_time(request, self.now_provider())
        search_radius = calculate_search_radius(request, elapsed.hours)
        origin = GeoPoint(request.latitude, request.longitude)
        assumptions = list(elapsed.assumptions)
        try:
            environment = await self.environment_provider.fetch(origin, search_radius)
            scored = score_grid(
                generate_grid(origin, search_radius),
                search_radius,
                behavior_type,
                request.behavior_profile,
                environment,
            )
            candidates = select_area_candidates(scored)
            if len(candidates) < SEARCH_AREA_CONFIG.min_areas:
                raise EnvironmentProviderError("유효한 추천 영역이 없습니다.")
        except EnvironmentProviderError:
            assumptions.append(FALLBACK_ASSUMPTION)
            return _fallback_response(request, behavior_type, search_radius, assumptions)
        areas = [
            RecommendedSearchArea(
                rank=index,
                center=SearchAreaCenter(
                    latitude=round(candidate.center.latitude, 6),
                    longitude=round(candidate.center.longitude, 6),
                ),
                radiusMeters=candidate.radius_meters,
                priorityScore=candidate.priority_score,
                reasonCodes=_reason_codes(behavior_type, candidate.kinds),
                reason=_reason(behavior_type, candidate.kinds),
            )
            for index, candidate in enumerate(candidates, start=1)
        ]
        return SearchAreaResponse(
            reportId=request.report_id,
            algorithmVersion=SEARCH_AREA_CONFIG.algorithm_version,
            behaviorType=behavior_type,
            estimatedRadiusMeters=search_radius,
            environmentSource=environment.source,
            fallbackUsed=False,
            assumptions=assumptions,
            areas=areas,
        )


def _fallback_response(
    request: SearchAreaRequest,
    behavior_type: BehaviorType,
    search_radius: int,
    assumptions: list[str],
) -> SearchAreaResponse:
    core_radius = min(
        SEARCH_AREA_CONFIG.max_area_radius_meters - 100,
        max(SEARCH_AREA_CONFIG.min_area_radius_meters, round(search_radius / 4)),
    )
    expanded_radius = min(
        SEARCH_AREA_CONFIG.max_area_radius_meters,
        max(core_radius + 100, round(search_radius / 3)),
    )
    return SearchAreaResponse(
        reportId=request.report_id,
        algorithmVersion=SEARCH_AREA_CONFIG.algorithm_version,
        behaviorType=behavior_type,
        estimatedRadiusMeters=search_radius,
        environmentSource="UNAVAILABLE",
        fallbackUsed=True,
        assumptions=assumptions,
        areas=[
            RecommendedSearchArea(
                rank=1,
                center=SearchAreaCenter(
                    latitude=request.latitude,
                    longitude=request.longitude,
                ),
                radiusMeters=core_radius,
                priorityScore=50,
                reasonCodes=["ENVIRONMENT_FALLBACK", "LAST_SEEN_LOCATION"],
                reason=(
                    "환경 데이터를 사용할 수 없어 마지막 목격 위치 주변을 "
                    "우선 수색 영역으로 제안합니다."
                ),
            ),
            RecommendedSearchArea(
                rank=2,
                center=SearchAreaCenter(
                    latitude=request.latitude,
                    longitude=request.longitude,
                ),
                radiusMeters=expanded_radius,
                priorityScore=40,
                reasonCodes=["ENVIRONMENT_FALLBACK", "EXPANDED_SEARCH_RADIUS"],
                reason=(
                    "환경 데이터를 사용할 수 없어 마지막 목격 위치 주변으로 "
                    "범위를 넓힌 확장 수색 영역입니다."
                ),
            ),
        ],
    )


def _reason_codes(behavior_type: BehaviorType, kinds: frozenset[EnvironmentKind]) -> list[str]:
    codes = [
        {
            BehaviorType.FEARFUL: "FEARFUL_HIDE",
            BehaviorType.CHASE_DRIVEN: "CHASE_ROUTE",
            BehaviorType.HUMAN_SEEKING: "HUMAN_CONTACT",
            BehaviorType.ALOOF: "ALOOF_ROAMING",
        }[behavior_type]
    ]
    for kind, code in (
        (EnvironmentKind.GREEN_SPACE, "GREEN_SPACE"),
        (EnvironmentKind.FOOTPATH, "WALKING_CORRIDOR"),
        (EnvironmentKind.WATER, "WATERSIDE_CORRIDOR"),
        (EnvironmentKind.BUILDING_RESIDENTIAL, "RESIDENTIAL_SHELTER"),
    ):
        if kind in kinds:
            codes.append(code)
    if EnvironmentKind.MAJOR_ROAD not in kinds and EnvironmentKind.RAILWAY_BARRIER not in kinds:
        codes.append("LOW_TRAFFIC")
    return codes


def _reason(behavior_type: BehaviorType, kinds: frozenset[EnvironmentKind]) -> str:
    behavior_text = {
        BehaviorType.FEARFUL: "두려움이 강한 행동 특성",
        BehaviorType.CHASE_DRIVEN: "추격 성향과 이동 경로",
        BehaviorType.HUMAN_SEEKING: "사람에게 접근하는 행동 특성",
        BehaviorType.ALOOF: "독립적으로 이동하는 행동 특성",
    }[behavior_type]
    environment_text = "주변 환경과 접근성"
    if EnvironmentKind.GREEN_SPACE in kinds:
        environment_text = "주변 녹지와 이동 가능 경로"
    elif EnvironmentKind.FOOTPATH in kinds:
        environment_text = "보행로와 연결된 이동 경로"
    elif EnvironmentKind.BUILDING_RESIDENTIAL in kinds:
        environment_text = "주거지 주변 은신 가능 공간"
    return f"{behavior_text} 및 {environment_text}을 고려한 우선 수색 영역입니다."
