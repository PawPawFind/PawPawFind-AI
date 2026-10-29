from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ActivityLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class StrangerResponse(StrEnum):
    APPROACH = "APPROACH"
    NEUTRAL = "NEUTRAL"
    AVOID = "AVOID"
    UNKNOWN = "UNKNOWN"


class NoiseSensitivity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class ChaseTendency(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class Mobility(StrEnum):
    NORMAL = "NORMAL"
    LIMITED = "LIMITED"
    UNKNOWN = "UNKNOWN"


class EscapeCause(StrEnum):
    DOOR_OPEN = "DOOR_OPEN"
    NOISE = "NOISE"
    CHASE = "CHASE"
    UNKNOWN = "UNKNOWN"


class BehaviorType(StrEnum):
    HUMAN_SEEKING = "HUMAN_SEEKING"
    FEARFUL = "FEARFUL"
    CHASE_DRIVEN = "CHASE_DRIVEN"
    ALOOF = "ALOOF"


class BehaviorProfile(BaseModel):
    activity_level: ActivityLevel = Field(default=ActivityLevel.UNKNOWN, alias="activityLevel")
    stranger_response: StrangerResponse = Field(
        default=StrangerResponse.UNKNOWN, alias="strangerResponse"
    )
    noise_sensitivity: NoiseSensitivity = Field(
        default=NoiseSensitivity.UNKNOWN, alias="noiseSensitivity"
    )
    chase_tendency: ChaseTendency = Field(default=ChaseTendency.UNKNOWN, alias="chaseTendency")
    mobility: Mobility = Mobility.UNKNOWN
    escape_cause: EscapeCause = Field(default=EscapeCause.UNKNOWN, alias="escapeCause")

    model_config = {"populate_by_name": True}


class SearchAreaRequest(BaseModel):
    report_id: int = Field(alias="reportId", ge=1)
    species: Literal["강아지"]
    size: Literal["소형", "중형", "대형"]
    event_date: date = Field(alias="eventDate")
    event_hour: int | None = Field(default=None, alias="eventHour", ge=0, le=23)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    happen_place: str | None = Field(default=None, alias="happenPlace")
    description: str | None = None
    behavior_profile: BehaviorProfile = Field(
        default_factory=BehaviorProfile, alias="behaviorProfile"
    )

    model_config = {"populate_by_name": True}

    @field_validator("behavior_profile", mode="before")
    @classmethod
    def default_null_behavior_profile(cls, value: object) -> object:
        return {} if value is None else value


class SearchAreaCenter(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RecommendedSearchArea(BaseModel):
    rank: int = Field(ge=1)
    center: SearchAreaCenter
    radius_meters: int = Field(alias="radiusMeters", ge=150, le=500)
    priority_score: int = Field(alias="priorityScore", ge=0, le=100)
    reason_codes: list[str] = Field(alias="reasonCodes")
    reason: str

    model_config = {"populate_by_name": True}


class SearchAreaResponse(BaseModel):
    report_id: int = Field(alias="reportId", ge=1)
    algorithm_version: Literal["HEURISTIC_V1"] = Field(alias="algorithmVersion")
    behavior_type: BehaviorType = Field(alias="behaviorType")
    estimated_radius_meters: int = Field(alias="estimatedRadiusMeters", ge=300, le=3000)
    environment_source: str = Field(alias="environmentSource")
    fallback_used: bool = Field(alias="fallbackUsed")
    assumptions: list[str]
    areas: list[RecommendedSearchArea]

    model_config = {"populate_by_name": True}


class ScoreBreakdown(BaseModel):
    distance: int = Field(ge=0, le=30)
    behavior_environment: int = Field(alias="behaviorEnvironment", ge=0, le=30)
    corridor: int = Field(ge=0, le=20)
    accessibility: int = Field(ge=0, le=10)
    event_context: int = Field(alias="eventContext", ge=0, le=10)

    model_config = {"populate_by_name": True}


class ExplainedSearchArea(RecommendedSearchArea):
    score_breakdown: ScoreBreakdown | None = Field(alias="scoreBreakdown")


class AlgorithmSearchAreas(BaseModel):
    algorithm_version: Literal["HEURISTIC_V1", "HEURISTIC_V2"] = Field(alias="algorithmVersion")
    behavior_type: BehaviorType = Field(alias="behaviorType")
    estimated_radius_meters: int = Field(alias="estimatedRadiusMeters", ge=300, le=3000)
    environment_source: str = Field(alias="environmentSource")
    fallback_used: bool = Field(alias="fallbackUsed")
    assumptions: list[str]
    areas: list[ExplainedSearchArea]

    model_config = {"populate_by_name": True}


class RankChange(BaseModel):
    """Same rank comparison; this does not match or track physical regions."""

    rank: int = Field(ge=1)
    status: Literal["BOTH", "ADDED", "REMOVED"]
    before_center: SearchAreaCenter | None = Field(alias="beforeCenter")
    after_center: SearchAreaCenter | None = Field(alias="afterCenter")
    center_shift_meters: float | None = Field(alias="centerShiftMeters", ge=0)
    before_radius_meters: int | None = Field(alias="beforeRadiusMeters")
    after_radius_meters: int | None = Field(alias="afterRadiusMeters")
    before_priority_score: int | None = Field(alias="beforePriorityScore")
    after_priority_score: int | None = Field(alias="afterPriorityScore")
    score_delta: int | None = Field(alias="scoreDelta")
    added_reason_codes: list[str] = Field(alias="addedReasonCodes")
    removed_reason_codes: list[str] = Field(alias="removedReasonCodes")

    model_config = {"populate_by_name": True}


class SearchAreaComparison(BaseModel):
    fallback_used: bool = Field(alias="fallbackUsed")
    summary: str
    area_count_before: int = Field(alias="areaCountBefore")
    area_count_after: int = Field(alias="areaCountAfter")
    rank_changes: list[RankChange] = Field(alias="rankChanges")

    model_config = {"populate_by_name": True}


class SearchAreaCompareResponse(BaseModel):
    report_id: int = Field(alias="reportId", ge=1)
    compared_at: datetime = Field(alias="comparedAt")
    baseline: AlgorithmSearchAreas
    improved: AlgorithmSearchAreas
    comparison: SearchAreaComparison

    model_config = {"populate_by_name": True}
