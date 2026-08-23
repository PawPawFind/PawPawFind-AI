from __future__ import annotations

from pydantic import BaseModel, Field


class AnimalForEmbeddingItem(BaseModel):
    desertion_no: str = Field(alias="desertionNo")
    species: str
    photo_urls: list[str] = Field(alias="photoUrls")
    kind_cd: str | None = Field(default=None, alias="kindCd")
    kind_nm: str | None = Field(default=None, alias="kindNm")
    color_cd: str | None = Field(default=None, alias="colorCd")
    sex_cd: str | None = Field(default=None, alias="sexCd")
    care_nm: str | None = Field(default=None, alias="careNm")
    care_tel: str | None = Field(default=None, alias="careTel")
    care_addr: str | None = Field(default=None, alias="careAddr")
    special_mark: str | None = Field(default=None, alias="specialMark")
    updated_at: str | None = Field(default=None, alias="updatedAt")

    model_config = {"populate_by_name": True}


class AnimalForEmbeddingResponse(BaseModel):
    items: list[AnimalForEmbeddingItem] = Field(default_factory=list)


class ReportPhotoForEmbeddingItem(BaseModel):
    report_photo_id: int = Field(alias="reportPhotoId")
    report_id: int = Field(alias="reportId")
    species: str
    photo_url: str = Field(alias="photoUrl")

    model_config = {"populate_by_name": True}


class ReportPhotoForEmbeddingResponse(BaseModel):
    items: list[ReportPhotoForEmbeddingItem] = Field(default_factory=list)
