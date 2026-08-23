from __future__ import annotations

from pydantic import BaseModel, Field


class AnimalEmbedRequest(BaseModel):
    desertion_no: str = Field(alias="desertionNo")
    species: str
    photo_urls: list[str] = Field(alias="photoUrls")

    model_config = {"populate_by_name": True}


class ReportPhotoEmbedRequest(BaseModel):
    report_photo_id: int = Field(alias="reportPhotoId")
    report_id: int = Field(alias="reportId")
    photo_url: str = Field(alias="photoUrl")
    species: str

    model_config = {"populate_by_name": True}


class ReportPhotoEmbedResponse(BaseModel):
    upserted: int
    skipped: int
