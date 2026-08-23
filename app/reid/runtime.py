"""Lazy-loaded ML models and gallery cache."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

_model_lock = threading.Lock()
_gallery_lock = threading.Lock()
_reid_model: Any | None = None
_detector: Any | None = None
_embed_dim: int | None = None
_gallery_data: dict[str, Any] | None = None
_gallery_meta: dict[str, dict[str, Any]] | None = None


def get_device():
    import torch

    device_name = os.environ.get("MODEL_DEVICE", "").strip().lower()
    if device_name:
        return torch.device(device_name)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_embed_dim() -> int:
    global _embed_dim
    if _embed_dim is None:
        model = get_reid_model()
        _embed_dim = int(getattr(model.backbone.config, "hidden_size", 384))
    return _embed_dim


def get_reid_model():
    global _reid_model
    if _reid_model is None:
        with _model_lock:
            if _reid_model is None:
                from app.reid.models import PetReIDModel

                model = PetReIDModel()
                _reid_model = model.to(get_device()).eval()
    return _reid_model


def get_detector():
    global _detector
    if _detector is None:
        with _model_lock:
            if _detector is None:
                from ultralytics import YOLO

                from app.reid.config import USE_FOREGROUND_SEGMENTATION

                weight = "yolo11n-seg.pt" if USE_FOREGROUND_SEGMENTATION else "yolo11n.pt"
                _detector = YOLO(weight)
    return _detector


def get_gallery(
    *,
    species_ko: str | None = None,
    exclude_report_id: int | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    global _gallery_data, _gallery_meta
    source = os.environ.get("PAWPAWFIND_GALLERY_SOURCE", "rds").lower()
    if source == "npz":
        return _get_gallery_npz()
    if species_ko is None:
        raise ValueError("species_ko is required when PAWPAWFIND_GALLERY_SOURCE=rds")
    return _get_gallery_rds(species_ko=species_ko, exclude_report_id=exclude_report_id)


def _get_gallery_npz() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    global _gallery_data, _gallery_meta
    if _gallery_data is None or _gallery_meta is None:
        with _gallery_lock:
            if _gallery_data is None or _gallery_meta is None:
                from app.reid.config import CACHE_ROOT
                from app.reid.gallery import load_gallery_cache

                cache_root = Path(os.environ.get("GALLERY_CACHE_ROOT", str(CACHE_ROOT)))
                _gallery_data, _gallery_meta = load_gallery_cache(cache_root)
    return _gallery_data, _gallery_meta


def _get_gallery_rds(
    *,
    species_ko: str,
    exclude_report_id: int | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
    from app.reid.gallery_rds import gallery_response_to_arrays
    from app.services.backend_client import fetch_gallery_for_search

    response = fetch_gallery_for_search(
        species_ko=species_ko,
        model_version=MODEL_VERSION,
        preprocess_version=PREPROCESS_VERSION,
        exclude_report_id=exclude_report_id,
    )
    return gallery_response_to_arrays(response)
