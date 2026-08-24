from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.schemas.search_area import (
    BehaviorProfile,
    BehaviorType,
    EscapeCause,
    SearchAreaRequest,
)
from app.search_area.config import SEARCH_AREA_CONFIG, SearchAreaHeuristicConfig

SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")
ESTIMATED_EVENT_HOUR_ASSUMPTION = "실종 시간이 없어 Asia/Seoul 정오(12시)로 추정했습니다."
ESTIMATED_CURRENT_TIME_ASSUMPTION = (
    "실종 시간이 없고 당일 정오 이전이어서 현재 Asia/Seoul 시각으로 추정했습니다."
)


@dataclass(frozen=True)
class ElapsedTime:
    event_at: datetime
    hours: float
    assumptions: tuple[str, ...]


def classify_behavior(profile: BehaviorProfile) -> BehaviorType:
    if profile.escape_cause is EscapeCause.CHASE or profile.chase_tendency.value == "HIGH":
        return BehaviorType.CHASE_DRIVEN
    if (
        profile.escape_cause is EscapeCause.NOISE
        or profile.noise_sensitivity.value == "HIGH"
        or profile.stranger_response.value == "AVOID"
    ):
        return BehaviorType.FEARFUL
    if profile.stranger_response.value == "APPROACH":
        return BehaviorType.HUMAN_SEEKING
    return BehaviorType.ALOOF


def calculate_elapsed_time(request: SearchAreaRequest, now: datetime) -> ElapsedTime:
    current = now.astimezone(SEOUL_TIMEZONE)
    estimated_hour = request.event_hour is None
    if estimated_hour and request.event_date == current.date() and current.hour < 12:
        event_at = current
        assumptions = (ESTIMATED_CURRENT_TIME_ASSUMPTION,)
    else:
        event_hour = 12 if estimated_hour else request.event_hour
        assert event_hour is not None
        event_at = datetime.combine(request.event_date, time(hour=event_hour), SEOUL_TIMEZONE)
        assumptions = (ESTIMATED_EVENT_HOUR_ASSUMPTION,) if estimated_hour else ()
    elapsed_hours = (current - event_at).total_seconds() / 3600
    if elapsed_hours < 0:
        raise ValueError("eventDate와 eventHour는 현재 시각보다 미래일 수 없습니다.")
    return ElapsedTime(event_at=event_at, hours=elapsed_hours, assumptions=assumptions)


def calculate_search_radius(
    request: SearchAreaRequest,
    elapsed_hours: float,
    config: SearchAreaHeuristicConfig = SEARCH_AREA_CONFIG,
) -> int:
    if elapsed_hours < 0:
        raise ValueError("경과 시간은 음수일 수 없습니다.")
    base_radius = dict(config.base_radius_by_size)[request.size]
    time_multiplier = next(
        multiplier
        for maximum_hours, multiplier in config.elapsed_time_multipliers
        if elapsed_hours <= maximum_hours
    )
    profile = request.behavior_profile
    multiplier = time_multiplier * dict(config.activity_multipliers)[profile.activity_level.value]
    if profile.mobility.value == "LIMITED":
        multiplier *= config.limited_mobility_multiplier
    if profile.escape_cause is EscapeCause.NOISE:
        multiplier *= config.noise_escape_multiplier
    elif profile.escape_cause is EscapeCause.CHASE:
        multiplier *= config.chase_escape_multiplier
    radius = round(base_radius * multiplier)
    return max(config.min_search_radius_meters, min(config.max_search_radius_meters, radius))
