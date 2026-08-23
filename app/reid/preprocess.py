"""Image detection, embedding, and pHash."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import imagehash
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

from app.reid.config import (
    COCO_CLASS_TO_SPECIES,
    SPECIES_TO_COCO_CLASS,
    USE_FOREGROUND_SEGMENTATION,
    YOLO_CONFIDENCE,
)
from app.reid.runtime import get_detector, get_reid_model


@dataclass
class CropResult:
    crop: Image.Image
    detected: bool
    species: Optional[str]
    confidence: float
    bbox: Optional[Tuple[int, int, int, int]]
    bbox_fraction: float


def open_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def detect_largest_pet(
    image: Image.Image,
    expected_species: Optional[str] = None,
    confidence: float = YOLO_CONFIDENCE,
    padding: float = 0.08,
) -> CropResult:
    if expected_species not in (None, "dog", "cat"):
        raise ValueError("expected_species must be 'dog', 'cat', or None")

    classes = None if expected_species is None else [SPECIES_TO_COCO_CLASS[expected_species]]
    result = get_detector().predict(image, conf=confidence, classes=classes, verbose=False)[0]
    width, height = image.size
    image_area = max(width * height, 1)
    candidates = []

    if result.boxes is not None:
        for box_index, box in enumerate(result.boxes):
            class_id = int(box.cls[0].item())
            species = COCO_CLASS_TO_SPECIES.get(class_id)
            if species is None or (expected_species and species != expected_species):
                continue
            conf = float(box.conf[0].item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            rank_value = conf * math.sqrt(max(area / image_area, 0.0))
            candidates.append((rank_value, area, conf, species, x1, y1, x2, y2, box_index))

    if not candidates:
        return CropResult(
            crop=image.copy(),
            detected=False,
            species=expected_species,
            confidence=0.0,
            bbox=None,
            bbox_fraction=1.0,
        )

    _, area, conf, species, x1, y1, x2, y2, box_index = max(
        candidates,
        key=lambda item: item[0],
    )
    pad_x = padding * (x2 - x1)
    pad_y = padding * (y2 - y1)
    left = max(0, int(x1 - pad_x))
    top = max(0, int(y1 - pad_y))
    right = min(width, int(x2 + pad_x))
    bottom = min(height, int(y2 + pad_y))
    crop = image.crop((left, top, right, bottom))

    if USE_FOREGROUND_SEGMENTATION and result.masks is not None:
        masks = result.masks.data
        if box_index < len(masks):
            mask = masks[box_index].detach().float()[None, None]
            mask = torch.nn.functional.interpolate(
                mask,
                size=(height, width),
                mode="bilinear",
                align_corners=False,
            )[0, 0].cpu().numpy()
            mask_crop = mask[top:bottom, left:right]
            foreground = np.asarray(crop, dtype=np.float32)
            alpha = np.clip(mask_crop[..., None], 0.0, 1.0)
            # 검은 배경 대신 DINOv2 정규화 평균에 가까운 중립 회색을 사용합니다.
            neutral = np.full_like(foreground, 128.0)
            crop = Image.fromarray(
                np.clip(foreground * alpha + neutral * (1.0 - alpha), 0, 255).astype(np.uint8)
            )

    return CropResult(
        crop=crop,
        detected=True,
        species=species,
        confidence=conf,
        bbox=(left, top, right, bottom),
        bbox_fraction=float(area / image_area),
    )


def blur_score(image: Image.Image) -> float:
    gray = ImageOps.grayscale(image.resize((256, 256)))
    array = np.asarray(gray, dtype=np.float32)
    laplacian = (
        -4 * array[1:-1, 1:-1]
        + array[:-2, 1:-1]
        + array[2:, 1:-1]
        + array[1:-1, :-2]
        + array[1:-1, 2:]
    )
    return float(laplacian.var())


def quality_warnings(original: Image.Image, crop_result: CropResult) -> List[str]:
    warnings: List[str] = []
    if not crop_result.detected:
        warnings.append("동물을 찾지 못해 원본 전체를 사용함")
    elif crop_result.confidence < 0.35:
        warnings.append("동물 검출 신뢰도가 낮음")
    if crop_result.detected and crop_result.bbox_fraction < 0.04:
        warnings.append("사진에서 동물이 너무 작음")
    if blur_score(crop_result.crop) < 45:
        warnings.append("사진이 흐릴 가능성이 있음")
    if min(original.size) < 160:
        warnings.append("원본 해상도가 낮음")
    return warnings


@torch.inference_mode()
def embed_images(images: Sequence[Image.Image]) -> np.ndarray:
    vectors = get_reid_model()(images)
    vectors = F.normalize(vectors, p=2, dim=-1)
    return vectors.detach().cpu().numpy().astype("float32")


def safe_phash(image: Image.Image) -> str:
    return str(imagehash.phash(image.resize((256, 256))))


def phash_distance(left: str, right: str) -> int:
    return int(imagehash.hex_to_hash(left) - imagehash.hex_to_hash(right))


def image_feature_pack(path: str | Path, species: str) -> Dict[str, Any]:
    original = open_rgb(path)
    crop_result = detect_largest_pet(original, expected_species=species)
    full_vector, crop_vector = embed_images([original, crop_result.crop])
    return {
        "embedding_full": full_vector,
        "embedding_crop": crop_vector,
        "phash_full": safe_phash(original),
        "phash_crop": safe_phash(crop_result.crop),
        "detected": crop_result.detected,
        "detection_confidence": crop_result.confidence,
        "bbox_fraction": crop_result.bbox_fraction,
        "blur": blur_score(crop_result.crop),
    }



