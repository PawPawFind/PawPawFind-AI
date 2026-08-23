from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.services.npz_import import (
    animal_batch_item_from_row,
    import_npz_to_rds,
    iter_animal_batch_items,
    resolve_features_dir,
)


@pytest.fixture
def sample_features_dir(tmp_path: Path) -> Path:
    features_dir = tmp_path / "features"
    features_dir.mkdir()

    gallery_data = {
        "gallery_ids": np.asarray(["dog:111:0", "cat:222:1"], dtype=str),
        "record_ids": np.asarray(["111", "222"], dtype=str),
        "species": np.asarray(["dog", "cat"], dtype=str),
        "embeddings_full": np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype="float32"),
        "embeddings_crop": np.asarray([[0.5, 0.5], [0.4, 0.6]], dtype="float32"),
        "phashes_full": np.asarray(["aaa", "ccc"], dtype=str),
        "phashes_crop": np.asarray(["bbb", "ddd"], dtype=str),
        "detection_confidences": np.asarray([0.9, 0.8], dtype="float32"),
        "blurs": np.asarray([100.0, 120.0], dtype="float32"),
    }
    np.savez_compressed(features_dir / "gallery_features.npz", **gallery_data)

    metadata = {
        "dog:111:0": {
            "gallery_id": "dog:111:0",
            "record_id": "111",
            "species": "dog",
            "photo_index": 0,
            "image_url": "https://example.com/dog.jpg",
        },
        "cat:222:1": {
            "gallery_id": "cat:222:1",
            "record_id": "222",
            "species": "cat",
            "photo_index": 1,
            "image_url": "https://example.com/cat.jpg",
        },
    }
    (features_dir / "gallery_meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    (features_dir / "manifest.json").write_text(
        json.dumps(
            {
                "model_version": "avito-dinov2-small-v1.1",
                "preprocess_version": "v8-yolo11n-full-crop",
                "embedding_dim": 2,
                "gallery_size": 2,
            }
        ),
        encoding="utf-8",
    )
    return features_dir


def test_resolve_features_dir_accepts_cache_root(sample_features_dir: Path) -> None:
    cache_root = sample_features_dir.parent
    assert resolve_features_dir(cache_root / "features") == sample_features_dir
    assert resolve_features_dir(cache_root) == sample_features_dir


def test_animal_batch_item_from_row(sample_features_dir: Path) -> None:
    from app.services.npz_import import load_npz_gallery

    gallery_data, metadata, _manifest = load_npz_gallery(sample_features_dir)
    item = animal_batch_item_from_row(
        0,
        gallery_data,
        metadata,
        model_version="avito-dinov2-small-v1.1",
        preprocess_version="v8-yolo11n-full-crop",
    )
    assert item is not None
    assert item.gallery_id == "dog:111:0"
    assert item.desertion_no == "111"
    assert item.photo_index == 0
    assert item.embedding_full == [1.0, 0.0]


def test_iter_animal_batch_items_skips_missing_image_url(sample_features_dir: Path) -> None:
    from app.services.npz_import import load_npz_gallery

    gallery_data, metadata, _manifest = load_npz_gallery(sample_features_dir)
    metadata["dog:111:0"].pop("image_url")
    items = list(
        iter_animal_batch_items(
            gallery_data,
            metadata,
            model_version="avito-dinov2-small-v1.1",
            preprocess_version="v8-yolo11n-full-crop",
        )
    )
    assert len(items) == 1
    assert items[0].gallery_id == "cat:222:1"


def test_import_npz_to_rds_dry_run(sample_features_dir: Path) -> None:
    summary = import_npz_to_rds(sample_features_dir, dry_run=True)
    assert summary.total_rows == 2
    assert summary.prepared == 2
    assert summary.dry_run is True
    assert summary.upserted == 0


def test_import_npz_to_rds_posts_batches(
    sample_features_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[int] = []

    def fake_upsert(items):
        from app.schemas.gallery import EmbeddingBatchResponse

        posted.append(len(items))
        return EmbeddingBatchResponse(upserted=len(items), skipped=0)

    monkeypatch.setattr("app.services.npz_import.upsert_animal_embeddings", fake_upsert)

    summary = import_npz_to_rds(sample_features_dir, batch_size=1)
    assert summary.prepared == 2
    assert summary.upserted == 2
    assert summary.batches == 2
    assert posted == [1, 1]
