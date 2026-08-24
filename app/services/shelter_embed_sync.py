"""Incremental shelter animal embedding sync (BE → embed → RDS)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
from app.schemas.gallery import AnimalEmbeddingBatchItem
from app.schemas.sync import AnimalForEmbeddingItem
from app.services.backend_client import fetch_animals_for_embedding, upsert_animal_embeddings
from app.services.embed_sync_state import (
    load_sync_state,
    save_sync_state,
    utc_now_iso,
)
from app.services.image_download import download_image_url, make_temp_dir


@dataclass
class AnimalEmbedSyncSummary:
    candidates: int
    prepared: int
    skipped: int
    upserted: int
    backend_skipped: int
    batches: int
    dry_run: bool


def _embed_animal_photo(*, image_path: Path, species: str) -> dict[str, object]:
    from app.reid.preprocess import image_feature_pack

    return image_feature_pack(image_path, species=species)


def animal_item_to_batch_items(
    item: AnimalForEmbeddingItem,
    *,
    model_version: str,
    preprocess_version: str,
    temp_dir: Path,
) -> list[AnimalEmbeddingBatchItem]:
    batch_items: list[AnimalEmbeddingBatchItem] = []
    for photo_index, image_url in enumerate(item.photo_urls):
        gallery_id = f"{item.species}:{item.desertion_no}:{photo_index}"
        local_path = download_image_url(
            image_url,
            temp_dir=temp_dir,
            filename=f"{item.desertion_no}_{photo_index}",
        )
        pack = _embed_animal_photo(image_path=local_path, species=item.species)
        batch_items.append(
            AnimalEmbeddingBatchItem(
                desertion_no=item.desertion_no,
                gallery_id=gallery_id,
                species=item.species,
                photo_index=photo_index,
                image_url=image_url,
                phash_full=str(pack["phash_full"]),
                phash_crop=str(pack["phash_crop"]),
                model_version=model_version,
                preprocess_version=preprocess_version,
                embedding_full=[float(v) for v in pack["embedding_full"].tolist()],
                embedding_crop=[float(v) for v in pack["embedding_crop"].tolist()],
                detection_confidence=float(pack["detection_confidence"]),
                blur_score=float(pack["blur"]),
            )
        )
    return batch_items


def sync_animal_embeddings(
    *,
    since: str | None = None,
    missing_only: bool = False,
    batch_size: int = 50,
    dry_run: bool = False,
    limit: int = 0,
    update_state: bool = True,
    state_path: Path | None = None,
) -> AnimalEmbedSyncSummary:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    state = load_sync_state(state_path)
    effective_since = since
    if effective_since is None and not missing_only:
        effective_since = state.animal_embed_synced_at

    response = fetch_animals_for_embedding(since=effective_since, missing_only=missing_only)
    candidates = response.items
    if limit > 0:
        candidates = candidates[:limit]

    if dry_run:
        photo_count = sum(len(item.photo_urls) for item in candidates)
        return AnimalEmbedSyncSummary(
            candidates=len(candidates),
            prepared=photo_count,
            skipped=0,
            upserted=0,
            backend_skipped=0,
            batches=0,
            dry_run=True,
        )

    temp_dir = make_temp_dir("pawpawfind-animal-sync-")
    prepared: list[AnimalEmbeddingBatchItem] = []
    skipped = 0
    for item in candidates:
        try:
            prepared.extend(
                animal_item_to_batch_items(
                    item,
                    model_version=MODEL_VERSION,
                    preprocess_version=PREPROCESS_VERSION,
                    temp_dir=temp_dir,
                )
            )
        except Exception:
            skipped += 1

    upserted = 0
    backend_skipped = 0
    batches = 0
    for start in range(0, len(prepared), batch_size):
        chunk = prepared[start : start + batch_size]
        result = upsert_animal_embeddings(chunk)
        upserted += result.upserted
        backend_skipped += result.skipped
        batches += 1

    if update_state and not dry_run:
        state.animal_embed_synced_at = utc_now_iso()
        save_sync_state(state, state_path)

    return AnimalEmbedSyncSummary(
        candidates=len(candidates),
        prepared=len(prepared),
        skipped=skipped,
        upserted=upserted,
        backend_skipped=backend_skipped,
        batches=batches,
        dry_run=False,
    )
