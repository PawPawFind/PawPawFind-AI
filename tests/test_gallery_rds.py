from __future__ import annotations

from app.reid.gallery_rds import gallery_response_to_arrays
from app.schemas.gallery import (
    GalleryAnimalItem,
    GalleryReportItem,
    GallerySearchResponse,
    MatchFeatureDto,
)


def test_gallery_response_to_arrays_merges_shelter_and_report() -> None:
    response = GallerySearchResponse(
        modelVersion="avito-dinov2-small-v1.1",
        preprocessVersion="v8-yolo11n-full-crop",
        animals=[
            GalleryAnimalItem(
                galleryId="dog:111:0",
                desertionNo="111",
                species="dog",
                imageUrl="https://example.com/shelter.jpg",
                phashFull="aaa",
                phashCrop="bbb",
                embeddingFull=[1.0, 0.0],
                embeddingCrop=[0.0, 1.0],
                metadata={"kindCd": "mix", "candidate_type": "SHELTER"},
            )
        ],
        reports=[
            GalleryReportItem(
                galleryId="report:42:7",
                reportId=42,
                reportPhotoId=7,
                species="dog",
                imageUrl="https://example.com/report.jpg",
                phashFull="ccc",
                phashCrop="ddd",
                embeddingFull=[0.5, 0.5],
                embeddingCrop=[0.4, 0.6],
                features=[MatchFeatureDto(category="털길이", keyword="장모")],
                reportType="FOUND",
                eventDate="2026-08-02",
                latitude=37.57,
                longitude=126.98,
                happenPlace="서울특별시 마포구",
            )
        ],
    )

    gallery_data, metadata = gallery_response_to_arrays(response)

    assert gallery_data["gallery_ids"].tolist() == ["dog:111:0", "report:42:7"]
    assert gallery_data["record_ids"].tolist() == ["111", "42"]
    assert gallery_data["species"].tolist() == ["dog", "dog"]
    assert gallery_data["embeddings_full"].shape == (2, 2)
    assert metadata["dog:111:0"]["candidate_type"] == "SHELTER"
    assert metadata["report:42:7"]["candidate_type"] == "REPORT"
    assert metadata["report:42:7"]["candidate_report_id"] == 42
    assert metadata["report:42:7"]["coat_length"] == "장모"
    assert metadata["report:42:7"]["eventDate"] == "2026-08-02"
    assert metadata["report:42:7"]["latitude"] == 37.57


def test_gallery_response_empty_arrays() -> None:
    response = GallerySearchResponse(
        modelVersion="avito-dinov2-small-v1.1",
        preprocessVersion="v8-yolo11n-full-crop",
        animals=[],
        reports=[],
    )
    gallery_data, metadata = gallery_response_to_arrays(response)
    assert len(gallery_data["gallery_ids"]) == 0
    assert gallery_data["embeddings_full"].shape == (0, 0)
    assert metadata == {}
