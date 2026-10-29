"""Prepare once, score twice. No I/O or clock reads inside either algorithm run."""

from collections.abc import Callable
from datetime import datetime

from app.schemas.search_area import (
    AlgorithmSearchAreas,
    BehaviorType,
    ExplainedSearchArea,
    RankChange,
    SearchAreaCenter,
    SearchAreaCompareResponse,
    SearchAreaComparison,
    SearchAreaRequest,
)
from app.search_area.config import SEARCH_AREA_CONFIG
from app.search_area.environment import EnvironmentProvider, EnvironmentProviderError
from app.search_area.explanations import explain_candidate
from app.search_area.geo import GeoPoint, distance_meters, generate_grid
from app.search_area.heuristics import (
    SEOUL_TIMEZONE,
    calculate_elapsed_time,
    calculate_search_radius,
    classify_behavior,
)
from app.search_area.scoring import (
    AreaCandidate,
    rounded_contributions,
    score_grid,
    select_area_candidates,
)
from app.search_area.scoring_v2 import score_grid_v2
from app.services.search_area import FALLBACK_ASSUMPTION, _fallback_response, _reason, _reason_codes

LIMITED_COMPARISON = (
    "환경 데이터를 사용할 수 없어 환경 기반 비교가 제한됩니다. V2 개선 효과를 평가할 수 없습니다."
)


async def compare_search_areas(
    request: SearchAreaRequest,
    provider: EnvironmentProvider,
    now_provider: Callable[[], datetime],
) -> SearchAreaCompareResponse:
    now = now_provider().astimezone(SEOUL_TIMEZONE)
    behavior = classify_behavior(request.behavior_profile)
    elapsed = calculate_elapsed_time(request, now)
    radius = calculate_search_radius(request, elapsed.hours)
    origin = GeoPoint(request.latitude, request.longitude)
    assumptions = list(elapsed.assumptions)
    try:
        environment = await provider.fetch(origin, radius)
    except EnvironmentProviderError:
        assumptions.extend([FALLBACK_ASSUMPTION, LIMITED_COMPARISON])
        fallback = _fallback_response(request, behavior, radius, assumptions)
        results = [
            AlgorithmSearchAreas(
                algorithm_version=version,
                behavior_type=behavior,
                estimated_radius_meters=radius,
                environment_source=fallback.environment_source,
                fallback_used=True,
                assumptions=assumptions,
                areas=[
                    ExplainedSearchArea(**area.model_dump(), score_breakdown=None)
                    for area in fallback.areas
                ],
            )
            for version in ("HEURISTIC_V1", "HEURISTIC_V2")
        ]
    else:
        cells = generate_grid(origin, radius)
        results = []
        for version, scorer in (("HEURISTIC_V1", score_grid), ("HEURISTIC_V2", score_grid_v2)):
            candidates = select_area_candidates(
                scorer(cells, radius, behavior, request.behavior_profile, environment)
            )
            if len(candidates) < SEARCH_AREA_CONFIG.min_areas:
                # Preserve the existing candidate-failure fallback policy, without re-fetching.
                fallback = _fallback_response(
                    request, behavior, radius, assumptions + [FALLBACK_ASSUMPTION]
                )
                results.append(
                    AlgorithmSearchAreas(
                        algorithm_version=version,
                        behavior_type=behavior,
                        estimated_radius_meters=radius,
                        environment_source="UNAVAILABLE",
                        fallback_used=True,
                        assumptions=fallback.assumptions,
                        areas=[
                            ExplainedSearchArea(**area.model_dump(), score_breakdown=None)
                            for area in fallback.areas
                        ],
                    )
                )
            else:
                results.append(
                    AlgorithmSearchAreas(
                        algorithm_version=version,
                        behavior_type=behavior,
                        estimated_radius_meters=radius,
                        environment_source=environment.source,
                        fallback_used=False,
                        assumptions=assumptions,
                        areas=[
                            _explained_area(candidate, rank, behavior, version == "HEURISTIC_V2")
                            for rank, candidate in enumerate(candidates, 1)
                        ],
                    )
                )
    baseline, improved = results
    return SearchAreaCompareResponse(
        report_id=request.report_id,
        compared_at=now,
        baseline=baseline,
        improved=improved,
        comparison=compare_results(baseline, improved),
    )


def _explained_area(
    candidate: AreaCandidate, rank: int, behavior: BehaviorType, improved: bool
) -> ExplainedSearchArea:
    codes, reason = (
        explain_candidate(candidate, behavior)
        if improved
        else (_reason_codes(behavior, candidate.kinds), _reason(behavior, candidate.kinds))
    )
    return ExplainedSearchArea(
        rank=rank,
        center=SearchAreaCenter(
            latitude=round(candidate.center.latitude, 6),
            longitude=round(candidate.center.longitude, 6),
        ),
        radius_meters=candidate.radius_meters,
        priority_score=candidate.priority_score,
        score_breakdown=rounded_contributions(candidate),
        reason_codes=codes,
        reason=reason,
    )


def compare_results(
    before: AlgorithmSearchAreas, after: AlgorithmSearchAreas
) -> SearchAreaComparison:
    before_by_rank = {area.rank: area for area in before.areas}
    after_by_rank = {area.rank: area for area in after.areas}
    changes = []
    for rank in sorted(before_by_rank.keys() | after_by_rank.keys()):
        old, new = before_by_rank.get(rank), after_by_rank.get(rank)
        shift = None
        if old and new:
            shift = round(
                distance_meters(
                    GeoPoint(old.center.latitude, old.center.longitude),
                    GeoPoint(new.center.latitude, new.center.longitude),
                ),
                3,
            )
        changes.append(
            RankChange(
                rank=rank,
                status="BOTH" if old and new else "ADDED" if new else "REMOVED",
                before_center=old.center if old else None,
                after_center=new.center if new else None,
                center_shift_meters=shift,
                before_radius_meters=old.radius_meters if old else None,
                after_radius_meters=new.radius_meters if new else None,
                before_priority_score=old.priority_score if old else None,
                after_priority_score=new.priority_score if new else None,
                score_delta=new.priority_score - old.priority_score if old and new else None,
                added_reason_codes=[
                    code for code in new.reason_codes if not old or code not in old.reason_codes
                ]
                if new
                else [],
                removed_reason_codes=[
                    code for code in old.reason_codes if not new or code not in new.reason_codes
                ]
                if old
                else [],
            )
        )
    fallback = before.fallback_used or after.fallback_used
    shifts = [
        change.center_shift_meters for change in changes if change.center_shift_meters is not None
    ]
    deltas = [change.score_delta for change in changes if change.score_delta is not None]
    summary = (
        LIMITED_COMPARISON
        if fallback
        else (
            f"추천 영역 {len(before.areas)}개 → {len(after.areas)}개. "
            f"동일 순위 중심 이동 최대 {max(shifts, default=0):.1f}m, "
            f"점수 변화 {min(deltas, default=0):+d}~{max(deltas, default=0):+d}점. "
            "동일 순위 비교는 동일 물리 영역의 추적이 아니며 "
            "점수 차이는 정확도 차이를 뜻하지 않습니다."
        )
    )
    return SearchAreaComparison(
        fallback_used=fallback,
        summary=summary,
        area_count_before=len(before.areas),
        area_count_after=len(after.areas),
        rank_changes=changes,
    )
