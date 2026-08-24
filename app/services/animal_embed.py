"""Single shelter animal embed on sync (BE → AI → RDS)."""

from __future__ import annotations

from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
from app.schemas.embed import AnimalEmbedRequest, ReportPhotoEmbedResponse
from app.schemas.sync import AnimalForEmbeddingItem
from app.services.backend_client import upsert_animal_embeddings
from app.services.image_download import make_temp_dir
from app.services.shelter_embed_sync import animal_item_to_batch_items


def embed_animal(request: AnimalEmbedRequest) -> ReportPhotoEmbedResponse:
    photo_urls = [url.strip() for url in request.photo_urls if url and url.strip()]
    if not photo_urls:
        raise ValueError("photoUrls must not be empty")

    species = request.species.strip().lower()
    if species not in {"dog", "cat"}:
        raise ValueError("species must be dog or cat")

    item = AnimalForEmbeddingItem(
        desertionNo=request.desertion_no,
        species=species,
        photoUrls=photo_urls,
    )

    temp_dir = make_temp_dir("pawpawfind-animal-upload-")
    batch_items = animal_item_to_batch_items(
        item,
        model_version=MODEL_VERSION,
        preprocess_version=PREPROCESS_VERSION,
        temp_dir=temp_dir,
    )
    result = upsert_animal_embeddings(batch_items)
    return ReportPhotoEmbedResponse(upserted=result.upserted, skipped=result.skipped)
