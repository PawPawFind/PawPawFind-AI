"""Gallery npz cache load/build helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from tqdm.auto import tqdm

from app.reid.config import (
    CACHE_ROOT,
    FEATURE_FILE,
    MANIFEST_FILE,
    META_FILE,
    MODEL_ID,
    MODEL_VERSION,
    PREPROCESS_VERSION,
)
from app.reid.preprocess import image_feature_pack
from app.reid.runtime import get_embed_dim


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def cache_is_compatible(manifest: Dict[str, Any]) -> bool:
    return (
        manifest.get("model_id") == MODEL_ID
        and manifest.get("model_version") == MODEL_VERSION
        and manifest.get("preprocess_version") == PREPROCESS_VERSION
        and int(manifest.get("embedding_dim", -1)) == get_embed_dim()
    )


def build_gallery_with_cache(
    records: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict[str, Any]]]:
    manifest = load_json(MANIFEST_FILE, {})
    cached_meta: Dict[str, Dict[str, Any]] = {}
    cached_arrays = None
    cached_index: Dict[str, int] = {}

    if FEATURE_FILE.exists() and META_FILE.exists() and cache_is_compatible(manifest):
        cached_arrays = np.load(FEATURE_FILE, allow_pickle=False)
        cached_meta = load_json(META_FILE, {})
        cached_index = {
            str(gallery_id): index
            for index, gallery_id in enumerate(cached_arrays["gallery_ids"])
        }
        print("compatible cached vectors:", len(cached_index))
    elif FEATURE_FILE.exists():
        print("cache ignored: model or preprocessing version changed")

    gallery_ids: List[str] = []
    record_ids: List[str] = []
    species_values: List[str] = []
    embeddings_full: List[np.ndarray] = []
    embeddings_crop: List[np.ndarray] = []
    phashes_full: List[str] = []
    phashes_crop: List[str] = []
    detection_confidences: List[float] = []
    blurs: List[float] = []
    current_meta: Dict[str, Dict[str, Any]] = {}
    reused = 0
    computed = 0

    for record in tqdm(records, desc="build Pet Re-ID gallery"):
        gallery_id = str(record["gallery_id"])
        record_id = str(record["record_id"])
        species = str(record["species"])

        can_reuse = (
            cached_arrays is not None
            and gallery_id in cached_index
            and gallery_id in cached_meta
            and cached_meta[gallery_id].get("image_url") == record.get("image_url")
            and cached_meta[gallery_id].get("species") == species
        )

        if can_reuse:
            index = cached_index[gallery_id]
            full_vector = cached_arrays["embeddings_full"][index]
            crop_vector = cached_arrays["embeddings_crop"][index]
            phash_full = str(cached_arrays["phashes_full"][index])
            phash_crop = str(cached_arrays["phashes_crop"][index])
            detection_confidence = float(cached_arrays["detection_confidences"][index])
            blur = float(cached_arrays["blurs"][index])
            reused += 1
        else:
            try:
                pack = image_feature_pack(record["image_path"], species=species)
            except Exception as exc:
                print("skip embedding:", gallery_id, repr(exc))
                continue
            full_vector = pack["embedding_full"]
            crop_vector = pack["embedding_crop"]
            phash_full = pack["phash_full"]
            phash_crop = pack["phash_crop"]
            detection_confidence = float(pack["detection_confidence"])
            blur = float(pack["blur"])
            computed += 1

        gallery_ids.append(gallery_id)
        record_ids.append(record_id)
        species_values.append(species)
        embeddings_full.append(np.asarray(full_vector, dtype="float32"))
        embeddings_crop.append(np.asarray(crop_vector, dtype="float32"))
        phashes_full.append(phash_full)
        phashes_crop.append(phash_crop)
        detection_confidences.append(detection_confidence)
        blurs.append(blur)
        current_meta[gallery_id] = dict(record)

    count = len(gallery_ids)
    embed_dim = get_embed_dim()
    gallery = {
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

    np.savez_compressed(FEATURE_FILE, **gallery)
    save_json(META_FILE, current_meta)
    save_json(
        MANIFEST_FILE,
        {
            "model_id": MODEL_ID,
            "model_version": MODEL_VERSION,
            "preprocess_version": PREPROCESS_VERSION,
            "embedding_dim": get_embed_dim(),
            "gallery_size": count,
            "species": sorted(set(species_values)),
        },
    )

    print("gallery size:", count)
    print("reused:", reused, "computed:", computed)
    print("feature cache:", FEATURE_FILE)
    return gallery, current_meta


def load_gallery_cache(
    cache_root: Path | None = None,
) -> tuple[Dict[str, np.ndarray], Dict[str, Dict[str, Any]]]:
    root = cache_root or CACHE_ROOT
    feature_root = root / "features"
    feature_file = feature_root / "gallery_features.npz"
    meta_file = feature_root / "gallery_meta.json"
    manifest_file = feature_root / "manifest.json"
    if not feature_file.exists() or not meta_file.exists():
        raise FileNotFoundError(
            f"Gallery cache not found under {feature_root}. "
            "Run scripts/build_gallery.py or set GALLERY_CACHE_ROOT."
        )
    manifest = load_json(manifest_file, {})
    from app.reid.runtime import get_embed_dim

    if manifest and not cache_is_compatible({**manifest, "embedding_dim": get_embed_dim()}):
        raise RuntimeError("Gallery cache incompatible with current model/preprocess version")
    arrays = np.load(feature_file, allow_pickle=False)
    gallery_data = {key: arrays[key] for key in arrays.files}
    metadata = load_json(meta_file, {})
    return gallery_data, metadata

