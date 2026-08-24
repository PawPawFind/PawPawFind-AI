from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal[
    "NO_GALLERY",
    "NEAR_DUPLICATE_CANDIDATE",
    "RANKED_CANDIDATES_NEED_HUMAN_REVIEW",
]
CandidateType = Literal["SHELTER", "REPORT"]
Species = Literal["강아지", "고양이"]


class MatchFeature(BaseModel):
    category: str
    keyword: str


class MatchRequest(BaseModel):
    report_id: int = Field(alias="reportId")
    species: Species
    photo_urls: list[str] = Field(default_factory=list, alias="photoUrls")
    features: list[MatchFeature] = Field(default_factory=list)
    report_type: str | None = Field(default=None, alias="reportType")
    event_date: str | None = Field(default=None, alias="eventDate")
    latitude: float | None = None
    longitude: float | None = None
    happen_place: str | None = Field(default=None, alias="happenPlace")
    description: str | None = None

    model_config = {"populate_by_name": True}


class MatchResultItem(BaseModel):
    rank: int = Field(ge=1, le=20)
    candidate_type: CandidateType = Field(alias="candidateType")
    desertion_no: str | None = Field(default=None, alias="desertionNo")
    candidate_report_id: int | None = Field(default=None, alias="candidateReportId")
    visual_score: float = Field(alias="visualScore")
    ranking_score: float | None = Field(default=None, alias="rankingScore")
    tag_score: float | None = Field(default=None, alias="tagScore")
    text_score: float | None = Field(default=None, alias="textScore")
    location_score: float | None = Field(default=None, alias="locationScore")
    time_score: float | None = Field(default=None, alias="timeScore")
    spatiotemporal_score: float | None = Field(default=None, alias="spatiotemporalScore")
    distance_km: float | None = Field(default=None, alias="distanceKm")
    elapsed_days: int | None = Field(default=None, alias="elapsedDays")
    location_method: str | None = Field(default=None, alias="locationMethod")
    phash_distance: int | None = Field(default=None, alias="phashDistance")
    near_duplicate: bool | None = Field(default=None, alias="nearDuplicate")
    matched_tags: dict[str, str] | None = Field(default=None, alias="matchedTags")
    conflicting_tags: dict[str, str] | None = Field(default=None, alias="conflictingTags")
    gallery_id: str | None = Field(default=None, alias="galleryId")
    image_url: str | None = Field(default=None, alias="imageUrl")

    model_config = {"populate_by_name": True}


class MatchResponse(BaseModel):
    report_id: int = Field(alias="reportId")
    model_version: str = Field(alias="modelVersion")
    rerank_version: str | None = Field(default=None, alias="rerankVersion")
    decision: Decision
    results: list[MatchResultItem]

    model_config = {"populate_by_name": True}
