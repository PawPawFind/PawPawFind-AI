"""Re-ID constants from Colab v10 notebook."""

from __future__ import annotations

import os
from pathlib import Path

MODEL_ID = "AvitoTech/DINO-v2-small-for-animal-identification"
BASE_MODEL_ID = "facebook/dinov2-small"
MODEL_VERSION = "avito-dinov2-small-v1.1"
TEXT_MODEL_ID = "intfloat/multilingual-e5-small"
RERANK_VERSION = "pawpawfind-spatiotemporal-reranker-v11.0"

USE_FOREGROUND_SEGMENTATION = False
PREPROCESS_VERSION = (
    "v8.2-yolo11n-seg-foreground" if USE_FOREGROUND_SEGMENTATION else "v8-yolo11n-full-crop"
)

SPECIES_LIST = ("dog", "cat")
STATES = ("protect", "notice")
ROWS = 100
QUICK_TEST = False
MAX_PAGES_PER_STATE = 2 if QUICK_TEST else None
MAX_IMAGES_PER_SPECIES = None
MAX_IMAGES_PER_RECORD = 4
HISTORICAL_DATE_WINDOWS: tuple[tuple[str, str], ...] = ()

API_CONNECT_TIMEOUT = 15
API_READ_TIMEOUT = 90
API_REQUEST_RETRIES = 7
API_CACHE_MAX_AGE_HOURS = 6
REFRESH_API_CACHE = False
UPR_CD = None
BGNDE = None
ENDDE = None

YOLO_CONFIDENCE = 0.20
FULL_IMAGE_WEIGHT = 0.00
CROP_IMAGE_WEIGHT = 1.00
PHASH_NEAR_DUPLICATE_MAX = 6
DEFAULT_TOP_K = 12
MULTIMODAL_CANDIDATE_POOL = 100
ENABLE_TEXT_RERANK = os.environ.get("ENABLE_TEXT_RERANK", "false").lower() == "true"
DEFAULT_RERANK_WEIGHTS = {
    "image": 0.70 if ENABLE_TEXT_RERANK else 0.75,
    "tags": 0.15,
    "text": 0.05 if ENABLE_TEXT_RERANK else 0.00,
    "location": 0.10,
}
LOCATION_DECAY_KM = 30.0
TEXT_MAX_LENGTH = 192
TEXT_BATCH_SIZE = 32

COCO_CLASS_TO_SPECIES = {15: "cat", 16: "dog"}
SPECIES_TO_COCO_CLASS = {value: key for key, value in COCO_CLASS_TO_SPECIES.items()}

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = Path(os.environ.get("GALLERY_CACHE_ROOT", REPO_ROOT / "cache" / "gallery"))
IMAGE_ROOT = CACHE_ROOT / "shelter_images"
FEATURE_ROOT = CACHE_ROOT / "features"
API_PAGE_ROOT = CACHE_ROOT / "api_pages"

FEATURE_FILE = FEATURE_ROOT / "gallery_features.npz"
META_FILE = FEATURE_ROOT / "gallery_meta.json"
MANIFEST_FILE = FEATURE_ROOT / "manifest.json"

SPECIES_KO_TO_EN = {"강아지": "dog", "고양이": "cat"}
