"""Incremental report photo embedding sync (BE → embed → RDS)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
from app.schemas.gallery import ReportEmbeddingBatchItem
from app.schemas.sync import ReportPhotoForEmbeddingItem
from app.services.backend_client import fetch_report_photos_for_embedding, upsert_report_embeddings
from app.services.embed_sync_state import load_sync_state, save_sync_state, utc_now_iso
from app.services.image_download import download_image_url, make_temp_dir


@dataclass
class ReportEmbedSyncSummary:
    candidates: int
    prepared: int
    skipped: int
    upserted: int
    backend_skipped: int
    batches: int
    dry_run: bool


def _embed_report_photo(*, image_path: Path, species: str) -> dict[str, object]:
    from app.reid.preprocess import image_feature_pack

    return image_feature_pack(image_path, species=species)


def report_item_to_batch_item(
    item: ReportPhotoForEmbeddingItem,
    *,
    model_version: str,
    preprocess_version: str,
    temp_dir: Path,
) -> ReportEmbeddingBatchItem:
    local_path = download_image_url(
        item.photo_url,
        temp_dir=temp_dir,
        filename=f"report_{item.report_id}_{item.report_photo_id}",
    )
    pack = _embed_report_photo(image_path=local_path, species=item.species)
    return ReportEmbeddingBatchItem(
        report_photo_id=item.report_photo_id,
        report_id=item.report_id,
        phash_full=str(pack["phash_full"]),
        phash_crop=str(pack["phash_crop"]),
        model_version=model_version,
        preprocess_version=preprocess_version,
        embedding_full=[float(v) for v in pack["embedding_full"].tolist()],
        embedding_crop=[float(v) for v in pack["embedding_crop"].tolist()],
    )


def sync_report_embeddings(
    *,
    missing_only: bool = True,
    batch_size: int = 50,
    dry_run: bool = False,
    limit: int = 0,
    update_state: bool = True,
    state_path: Path | None = None,
) -> ReportEmbedSyncSummary:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    response = fetch_report_photos_for_embedding(missing_only=missing_only)
    candidates = response.items
    if limit > 0:
        candidates = candidates[:limit]

    if dry_run:
        return ReportEmbedSyncSummary(
            candidates=len(candidates),
            prepared=len(candidates),
            skipped=0,
            upserted=0,
            backend_skipped=0,
            batches=0,
            dry_run=True,
        )

    temp_dir = make_temp_dir("pawpawfind-report-sync-")
    prepared: list[ReportEmbeddingBatchItem] = []
    skipped = 0
    for item in candidates:
        try:
            prepared.append(
                report_item_to_batch_item(
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
        result = upsert_report_embeddings(chunk)
        upserted += result.upserted
        backend_skipped += result.skipped
        batches += 1

    if update_state and not dry_run:
        state = load_sync_state(state_path)
        state.report_embed_synced_at = utc_now_iso()
        save_sync_state(state, state_path)

    return ReportEmbedSyncSummary(
        candidates=len(candidates),
        prepared=len(prepared),
        skipped=skipped,
        upserted=upserted,
        backend_skipped=backend_skipped,
        batches=batches,
        dry_run=False,
    )
