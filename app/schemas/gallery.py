from __future__ import annotations

from pydantic import BaseModel, Field


class MatchFeatureDto(BaseModel):
    category: str
    keyword: str


class GalleryAnimalItem(BaseModel):
    gallery_id: str = Field(alias="galleryId")
    desertion_no: str = Field(alias="desertionNo")
    species: str
    image_url: str = Field(alias="imageUrl")
    phash_full: str | None = Field(default=None, alias="phashFull")
    phash_crop: str | None = Field(default=None, alias="phashCrop")
    embedding_full: list[float] = Field(alias="embeddingFull")
    embedding_crop: list[float] = Field(alias="embeddingCrop")
    detection_confidence: float | None = Field(default=None, alias="detectionConfidence")
    blur_score: float | None = Field(default=None, alias="blurScore")
    metadata: dict[str, object] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class GalleryReportItem(BaseModel):
    gallery_id: str = Field(alias="galleryId")
    report_id: int = Field(alias="reportId")
    report_photo_id: int = Field(alias="reportPhotoId")
    species: str
    image_url: str = Field(alias="imageUrl")
    phash_full: str | None = Field(default=None, alias="phashFull")
    phash_crop: str | None = Field(default=None, alias="phashCrop")
    embedding_full: list[float] = Field(alias="embeddingFull")
    embedding_crop: list[float] = Field(alias="embeddingCrop")
    features: list[MatchFeatureDto] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class GallerySearchResponse(BaseModel):
    model_version: str = Field(alias="modelVersion")
    preprocess_version: str = Field(alias="preprocessVersion")
    animals: list[GalleryAnimalItem] = Field(default_factory=list)
    reports: list[GalleryReportItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class AnimalEmbeddingBatchItem(BaseModel):
    desertion_no: str = Field(alias="desertionNo")
    gallery_id: str = Field(alias="galleryId")
    species: str
    photo_index: int = Field(default=0, alias="photoIndex")
    image_url: str = Field(alias="imageUrl")
    phash_full: str | None = Field(default=None, alias="phashFull")
    phash_crop: str | None = Field(default=None, alias="phashCrop")
    model_version: str = Field(alias="modelVersion")
    preprocess_version: str = Field(alias="preprocessVersion")
    embedding_full: list[float] = Field(alias="embeddingFull")
    embedding_crop: list[float] = Field(alias="embeddingCrop")
    detection_confidence: float | None = Field(default=None, alias="detectionConfidence")
    blur_score: float | None = Field(default=None, alias="blurScore")

    model_config = {"populate_by_name": True}


class ReportEmbeddingBatchItem(BaseModel):
    report_photo_id: int = Field(alias="reportPhotoId")
    report_id: int = Field(alias="reportId")
    phash_full: str | None = Field(default=None, alias="phashFull")
    phash_crop: str | None = Field(default=None, alias="phashCrop")
    model_version: str = Field(alias="modelVersion")
    preprocess_version: str = Field(alias="preprocessVersion")
    embedding_full: list[float] = Field(alias="embeddingFull")
    embedding_crop: list[float] = Field(alias="embeddingCrop")

    model_config = {"populate_by_name": True}


class EmbeddingBatchResponse(BaseModel):
    upserted: int
    skipped: int
