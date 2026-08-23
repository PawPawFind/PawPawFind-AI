"""Build in-memory gallery arrays from BE RDS export."""

from __future__ import annotations

from typing import Any

from app.schemas.gallery import GalleryAnimalItem, GalleryReportItem, GallerySearchResponse
from app.services.feature_mapper import CATEGORY_TO_FIELD


def features_to_gallery_metadata(features: list[Any]) -> dict[str, object]:
    metadata: dict[str, object] = {
        "sex": "",
        "colors": [],
        "patterns": [],
        "coat_length": "",
        "ear_shape": "",
        "tail_shape": "",
        "size": "",
        "distinctive_features": [],
        "description": "",
    }
    for feature in features:
        if hasattr(feature, "category"):
            category = str(feature.category).strip()
            keyword = str(feature.keyword).strip()
        else:
            category = str(feature.get("category", "")).strip()
            keyword = str(feature.get("keyword", "")).strip()
        field = CATEGORY_TO_FIELD.get(category)
        if field is None:
            values = metadata["distinctive_features"]
            assert isinstance(values, list)
            values.append(f"{category}:{keyword}")
            continue
        if field in {"colors", "patterns", "distinctive_features"}:
            values = metadata[field]
            assert isinstance(values, list)
            values.append(keyword)
        else:
            metadata[field] = keyword
    return metadata


def _append_item(
    *,
    gallery_ids: list[str],
    record_ids: list[str],
    species_values: list[str],
    embeddings_full: list[Any],
    embeddings_crop: list[Any],
    phashes_full: list[str],
    phashes_crop: list[str],
    detection_confidences: list[float],
    blurs: list[float],
    metadata: dict[str, dict[str, Any]],
    gallery_id: str,
    record_id: str,
    species: str,
    embedding_full: list[float],
    embedding_crop: list[float],
    phash_full: str | None,
    phash_crop: str | None,
    meta: dict[str, Any],
    detection_confidence: float | None = None,
    blur_score: float | None = None,
) -> None:
    import numpy as np

    gallery_ids.append(gallery_id)
    record_ids.append(record_id)
    species_values.append(species)
    embeddings_full.append(np.asarray(embedding_full, dtype="float32"))
    embeddings_crop.append(np.asarray(embedding_crop, dtype="float32"))
    phashes_full.append(phash_full or "")
    phashes_crop.append(phash_crop or "")
    detection_confidences.append(float(detection_confidence or 0.0))
    blurs.append(float(blur_score or 0.0))
    metadata[gallery_id] = meta


def animal_item_to_metadata(item: GalleryAnimalItem) -> dict[str, Any]:
    meta = dict(item.metadata)
    meta.setdefault("gallery_id", item.gallery_id)
    meta.setdefault("record_id", item.desertion_no)
    meta.setdefault("species", item.species)
    meta.setdefault("image_url", item.image_url)
    meta.setdefault("candidate_type", "SHELTER")
    meta.setdefault("candidate_report_id", None)
    return meta


def report_item_to_metadata(item: GalleryReportItem) -> dict[str, Any]:
    tag_metadata = features_to_gallery_metadata(item.features)
    return {
        "gallery_id": item.gallery_id,
        "record_id": str(item.report_id),
        "species": item.species,
        "image_url": item.image_url,
        "candidate_type": "REPORT",
        "candidate_report_id": item.report_id,
        **tag_metadata,
    }


def gallery_response_to_arrays(
    response: GallerySearchResponse,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    import numpy as np

    gallery_ids: list[str] = []
    record_ids: list[str] = []
    species_values: list[str] = []
    embeddings_full: list[Any] = []
    embeddings_crop: list[Any] = []
    phashes_full: list[str] = []
    phashes_crop: list[str] = []
    detection_confidences: list[float] = []
    blurs: list[float] = []
    metadata: dict[str, dict[str, Any]] = {}

    for item in response.animals:
        meta = animal_item_to_metadata(item)
        _append_item(
            gallery_ids=gallery_ids,
            record_ids=record_ids,
            species_values=species_values,
            embeddings_full=embeddings_full,
            embeddings_crop=embeddings_crop,
            phashes_full=phashes_full,
            phashes_crop=phashes_crop,
            detection_confidences=detection_confidences,
            blurs=blurs,
            metadata=metadata,
            gallery_id=item.gallery_id,
            record_id=item.desertion_no,
            species=item.species,
            embedding_full=item.embedding_full,
            embedding_crop=item.embedding_crop,
            phash_full=item.phash_full,
            phash_crop=item.phash_crop,
            meta=meta,
            detection_confidence=item.detection_confidence,
            blur_score=item.blur_score,
        )

    for item in response.reports:
        meta = report_item_to_metadata(item)
        _append_item(
            gallery_ids=gallery_ids,
            record_ids=record_ids,
            species_values=species_values,
            embeddings_full=embeddings_full,
            embeddings_crop=embeddings_crop,
            phashes_full=phashes_full,
            phashes_crop=phashes_crop,
            detection_confidences=detection_confidences,
            blurs=blurs,
            metadata=metadata,
            gallery_id=item.gallery_id,
            record_id=str(item.report_id),
            species=item.species,
            embedding_full=item.embedding_full,
            embedding_crop=item.embedding_crop,
            phash_full=item.phash_full,
            phash_crop=item.phash_crop,
            meta=meta,
        )

    count = len(gallery_ids)
    embed_dim = 0
    if count:
        embed_dim = int(embeddings_full[0].shape[0])

    gallery_data = {
        "gallery_ids": np.asarray(gallery_ids, dtype=str),
        "record_ids": np.asarray(record_ids, dtype=str),
        "species": np.asarray(species_values, dtype=str),
        "embeddings_full": (
            np.stack(embeddings_full).astype("float32")
            if count
            else np.zeros((0, embed_dim), dtype="float32")
        ),
        "embeddings_crop": (
            np.stack(embeddings_crop).astype("float32")
            if count
            else np.zeros((0, embed_dim), dtype="float32")
        ),
        "phashes_full": np.asarray(phashes_full, dtype=str),
        "phashes_crop": np.asarray(phashes_crop, dtype=str),
        "detection_confidences": np.asarray(detection_confidences, dtype="float32"),
        "blurs": np.asarray(blurs, dtype="float32"),
    }
    return gallery_data, metadata
