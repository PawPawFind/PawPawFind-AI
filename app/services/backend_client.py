from __future__ import annotations

import os

import httpx

from app.schemas.gallery import (
    AnimalEmbeddingBatchItem,
    EmbeddingBatchResponse,
    GallerySearchResponse,
    ReportEmbeddingBatchItem,
)
from app.schemas.sync import AnimalForEmbeddingResponse, ReportPhotoForEmbeddingResponse


def backend_base_url() -> str:
    return os.environ.get("PAWPAWFIND_BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def fetch_gallery_for_search(
    *,
    species_ko: str,
    model_version: str,
    preprocess_version: str,
    exclude_report_id: int | None = None,
    include_animals: bool = True,
    include_reports: bool = True,
    timeout: float = 120.0,
) -> GallerySearchResponse:
    params: dict[str, str | int | bool] = {
        "species": species_ko,
        "modelVersion": model_version,
        "preprocessVersion": preprocess_version,
        "includeAnimals": include_animals,
        "includeReports": include_reports,
    }
    if exclude_report_id is not None:
        params["excludeReportId"] = exclude_report_id

    with httpx.Client(base_url=backend_base_url(), timeout=timeout) as client:
        response = client.get("/api/internal/gallery/for-search", params=params)
        response.raise_for_status()
        return GallerySearchResponse.model_validate(response.json())


def upsert_animal_embeddings(
    items: list[AnimalEmbeddingBatchItem],
    *,
    timeout: float = 120.0,
) -> EmbeddingBatchResponse:
    payload = {"items": [item.model_dump(by_alias=True) for item in items]}
    with httpx.Client(base_url=backend_base_url(), timeout=timeout) as client:
        response = client.post("/api/internal/animal-embeddings/batch", json=payload)
        response.raise_for_status()
        return EmbeddingBatchResponse.model_validate(response.json())


def upsert_report_embeddings(
    items: list[ReportEmbeddingBatchItem],
    *,
    timeout: float = 120.0,
) -> EmbeddingBatchResponse:
    payload = {"items": [item.model_dump(by_alias=True) for item in items]}
    with httpx.Client(base_url=backend_base_url(), timeout=timeout) as client:
        response = client.post("/api/internal/report-embeddings/batch", json=payload)
        response.raise_for_status()
        return EmbeddingBatchResponse.model_validate(response.json())


def fetch_animals_for_embedding(
    *,
    since: str | None = None,
    missing_only: bool = False,
    timeout: float = 120.0,
) -> AnimalForEmbeddingResponse:
    params: dict[str, str | bool] = {"missingOnly": missing_only}
    if since:
        params["since"] = since
    with httpx.Client(base_url=backend_base_url(), timeout=timeout) as client:
        response = client.get("/api/internal/animals/for-embedding", params=params)
        response.raise_for_status()
        return AnimalForEmbeddingResponse.model_validate(response.json())


def fetch_report_photos_for_embedding(
    *,
    missing_only: bool = True,
    timeout: float = 120.0,
) -> ReportPhotoForEmbeddingResponse:
    params = {"missingOnly": missing_only}
    with httpx.Client(base_url=backend_base_url(), timeout=timeout) as client:
        response = client.get("/api/internal/report-photos/for-embedding", params=params)
        response.raise_for_status()
        return ReportPhotoForEmbeddingResponse.model_validate(response.json())
