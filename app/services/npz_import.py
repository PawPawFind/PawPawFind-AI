"""Import Colab gallery npz cache into BE animal_embeddings (RDS)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
from app.schemas.gallery import AnimalEmbeddingBatchItem
from app.services.backend_client import upsert_animal_embeddings


@dataclass
class NpzImportSummary:
    total_rows: int
    prepared: int
    skipped: int
    upserted: int
    backend_skipped: int
    batches: int
    dry_run: bool


def resolve_features_dir(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if root.is_file() and root.suffix == ".npz":
        return root.parent
    if (root / "gallery_features.npz").exists():
        return root
    if (root / "features" / "gallery_features.npz").exists():
        return root / "features"
    raise FileNotFoundError(
        f"Could not find gallery_features.npz under {root}. "
        "Pass --features-dir to the folder that contains gallery_features.npz."
    )


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_npz_gallery(
    features_dir: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    import numpy as np

    feature_file = features_dir / "gallery_features.npz"
    meta_file = features_dir / "gallery_meta.json"
    manifest_file = features_dir / "manifest.json"
    if not feature_file.exists():
        raise FileNotFoundError(f"Missing {feature_file}")
    if not meta_file.exists():
        raise FileNotFoundError(f"Missing {meta_file}")

    arrays = np.load(feature_file, allow_pickle=False)
    gallery_data = {key: arrays[key] for key in arrays.files}
    metadata = _load_json(meta_file, {})
    manifest = _load_json(manifest_file, {})
    return gallery_data, metadata, manifest


def _parse_photo_index(gallery_id: str, meta: dict[str, Any]) -> int:
    if meta.get("photo_index") is not None:
        return int(meta["photo_index"])
    parts = gallery_id.split(":")
    if len(parts) >= 3 and parts[-1].isdigit():
        return int(parts[-1])
    return 0


def _vector_to_list(vector: Any) -> list[float]:
    return [float(value) for value in vector.tolist()]


def animal_batch_item_from_row(
    index: int,
    gallery_data: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    *,
    model_version: str,
    preprocess_version: str,
) -> AnimalEmbeddingBatchItem | None:
    gallery_id = str(gallery_data["gallery_ids"][index])
    record_id = str(gallery_data["record_ids"][index])
    species = str(gallery_data["species"][index])
    meta = metadata.get(gallery_id, {})

    image_url = str(meta.get("image_url") or meta.get("imageUrl") or "").strip()
    if not image_url:
        return None

    return AnimalEmbeddingBatchItem(
        desertion_no=record_id,
        gallery_id=gallery_id,
        species=species,
        photo_index=_parse_photo_index(gallery_id, meta),
        image_url=image_url,
        phash_full=str(gallery_data["phashes_full"][index]),
        phash_crop=str(gallery_data["phashes_crop"][index]),
        model_version=model_version,
        preprocess_version=preprocess_version,
        embedding_full=_vector_to_list(gallery_data["embeddings_full"][index]),
        embedding_crop=_vector_to_list(gallery_data["embeddings_crop"][index]),
        detection_confidence=float(gallery_data["detection_confidences"][index]),
        blur_score=float(gallery_data["blurs"][index]),
    )


def iter_animal_batch_items(
    gallery_data: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    *,
    model_version: str | None = None,
    preprocess_version: str | None = None,
    limit: int = 0,
) -> Iterator[AnimalEmbeddingBatchItem]:
    model_version = model_version or MODEL_VERSION
    preprocess_version = preprocess_version or PREPROCESS_VERSION
    total = len(gallery_data["gallery_ids"])
    if limit > 0:
        total = min(total, limit)

    for index in range(total):
        item = animal_batch_item_from_row(
            index,
            gallery_data,
            metadata,
            model_version=model_version,
            preprocess_version=preprocess_version,
        )
        if item is not None:
            yield item


def import_npz_to_rds(
    features_dir: str | Path,
    *,
    batch_size: int = 100,
    dry_run: bool = False,
    limit: int = 0,
    model_version: str | None = None,
    preprocess_version: str | None = None,
) -> NpzImportSummary:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    resolved = resolve_features_dir(features_dir)
    gallery_data, metadata, manifest = load_npz_gallery(resolved)
    model_version = model_version or str(manifest.get("model_version") or MODEL_VERSION)
    preprocess_version = preprocess_version or str(
        manifest.get("preprocess_version") or PREPROCESS_VERSION
    )

    total_rows = len(gallery_data["gallery_ids"])
    if limit > 0:
        total_rows = min(total_rows, limit)

    prepared_items: list[AnimalEmbeddingBatchItem] = list(
        iter_animal_batch_items(
            gallery_data,
            metadata,
            model_version=model_version,
            preprocess_version=preprocess_version,
            limit=limit,
        )
    )
    skipped = total_rows - len(prepared_items)

    if dry_run:
        return NpzImportSummary(
            total_rows=total_rows,
            prepared=len(prepared_items),
            skipped=skipped,
            upserted=0,
            backend_skipped=0,
            batches=0,
            dry_run=True,
        )

    upserted = 0
    backend_skipped = 0
    batches = 0
    for start in range(0, len(prepared_items), batch_size):
        chunk = prepared_items[start : start + batch_size]
        response = upsert_animal_embeddings(chunk)
        upserted += response.upserted
        backend_skipped += response.skipped
        batches += 1

    return NpzImportSummary(
        total_rows=total_rows,
        prepared=len(prepared_items),
        skipped=skipped,
        upserted=upserted,
        backend_skipped=backend_skipped,
        batches=batches,
        dry_run=False,
    )
