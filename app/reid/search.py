"""Visual gallery search."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.reid.config import (
    CROP_IMAGE_WEIGHT,
    DEFAULT_TOP_K,
    FULL_IMAGE_WEIGHT,
    MODEL_VERSION,
    PHASH_NEAR_DUPLICATE_MAX,
)
from app.reid.preprocess import (
    blur_score,
    detect_largest_pet,
    embed_images,
    open_rgb,
    phash_distance,
    quality_warnings,
    safe_phash,
)


@dataclass
class QueryPack:
    species: str
    embedding_full: np.ndarray
    embedding_crop: np.ndarray
    phashes_full: List[str]
    phashes_crop: List[str]
    quality: List[Dict[str, Any]]


@dataclass
class SearchMatch:
    rank: int
    image_rank: int
    record_id: str
    gallery_id: str
    species: str
    visual_score: float
    full_score: float
    crop_score: float
    phash_distance: int
    near_duplicate: bool
    image_path: str
    image_url: str
    kind: str
    color: str
    sex: str
    care_name: str
    care_tel: str
    care_address: str
    candidate_type: str = "SHELTER"
    candidate_report_id: int | None = None
    tag_score: Optional[float] = None
    tag_coverage: float = 0.0
    text_score: Optional[float] = None
    ranking_score: Optional[float] = None
    matched_tags: Tuple[str, ...] = ()
    conflicting_tags: Tuple[str, ...] = ()


def normalized_mean(vectors: Sequence[np.ndarray]) -> np.ndarray:
    mean = np.mean(np.stack(vectors).astype("float32"), axis=0)
    norm = float(np.linalg.norm(mean))
    if norm <= 1e-12:
        raise RuntimeError("평균 임베딩의 norm이 0입니다")
    return (mean / norm).astype("float32")


def resolve_query_species(path: str | Path, requested: str = "auto") -> str:
    if requested in ("dog", "cat"):
        return requested
    if requested != "auto":
        raise ValueError("QUERY_SPECIES must be 'auto', 'dog', or 'cat'")

    result = detect_largest_pet(open_rgb(path), expected_species=None)
    if not result.detected or result.species not in ("dog", "cat"):
        raise RuntimeError(
            "업로드 사진에서 개/고양이를 자동 판별하지 못했습니다. "
            "QUERY_SPECIES를 'dog' 또는 'cat'으로 직접 지정하세요."
        )
    return result.species


def build_query_pack(paths: Sequence[str | Path], species: str) -> QueryPack:
    full_vectors: List[np.ndarray] = []
    crop_vectors: List[np.ndarray] = []
    phashes_full: List[str] = []
    phashes_crop: List[str] = []
    quality: List[Dict[str, Any]] = []

    for path in paths:
        original = open_rgb(path)
        crop_result = detect_largest_pet(original, expected_species=species)
        full_vector, crop_vector = embed_images([original, crop_result.crop])
        full_vectors.append(full_vector)
        crop_vectors.append(crop_vector)
        phashes_full.append(safe_phash(original))
        phashes_crop.append(safe_phash(crop_result.crop))
        quality.append(
            {
                "path": str(path),
                "detected": crop_result.detected,
                "confidence": crop_result.confidence,
                "bbox_fraction": crop_result.bbox_fraction,
                "blur": blur_score(crop_result.crop),
                "warnings": quality_warnings(original, crop_result),
            }
        )

    return QueryPack(
        species=species,
        embedding_full=normalized_mean(full_vectors),
        embedding_crop=normalized_mean(crop_vectors),
        phashes_full=phashes_full,
        phashes_crop=phashes_crop,
        quality=quality,
    )


def query_pack_from_image_records(
    records: Sequence[Dict[str, Any]],
    species: str,
) -> QueryPack:
    """백엔드가 저장한 목격·실종 사진 레코드를 기존 검색 입력으로 변환합니다."""
    paths = [
        Path(str(record["image_path"]))
        for record in records
        if str(record.get("image_path", "")).strip()
    ]
    if not paths:
        raise ValueError("검색 가능한 image_path가 없습니다")
    return build_query_pack(paths, species=species)


def minimum_query_phash_distance(
    query: QueryPack,
    gallery_full: str,
    gallery_crop: str,
) -> int:
    distances = []
    for query_hash in query.phashes_full:
        distances.append(phash_distance(query_hash, gallery_full))
        distances.append(phash_distance(query_hash, gallery_crop))
    for query_hash in query.phashes_crop:
        distances.append(phash_distance(query_hash, gallery_full))
        distances.append(phash_distance(query_hash, gallery_crop))
    return min(distances)


def match_rank_key(match: SearchMatch) -> Tuple[int, int, float]:
    duplicate_priority = 1 if match.near_duplicate else 0
    duplicate_distance_priority = -match.phash_distance if match.near_duplicate else -65
    return duplicate_priority, duplicate_distance_priority, match.visual_score


def search_gallery(
    query_paths: Sequence[str | Path],
    species: str,
    gallery_data: Dict[str, np.ndarray],
    metadata: Dict[str, Dict[str, Any]],
    top_k: int = DEFAULT_TOP_K,
) -> Tuple[QueryPack, List[SearchMatch]]:
    if not query_paths:
        raise ValueError("query_paths is empty")
    if len(gallery_data["gallery_ids"]) == 0:
        return build_query_pack(query_paths, species), []

    query = build_query_pack(query_paths, species)
    species_indices = np.flatnonzero(gallery_data["species"] == species)
    if len(species_indices) == 0:
        return query, []

    full_scores = gallery_data["embeddings_full"][species_indices] @ query.embedding_full
    crop_scores = gallery_data["embeddings_crop"][species_indices] @ query.embedding_crop
    visual_scores = FULL_IMAGE_WEIGHT * full_scores + CROP_IMAGE_WEIGHT * crop_scores

    best_by_record: Dict[str, SearchMatch] = {}
    for local_index, gallery_index in enumerate(species_indices):
        gallery_id = str(gallery_data["gallery_ids"][gallery_index])
        record_id = str(gallery_data["record_ids"][gallery_index])
        meta = metadata[gallery_id]
        hash_distance = minimum_query_phash_distance(
            query,
            str(gallery_data["phashes_full"][gallery_index]),
            str(gallery_data["phashes_crop"][gallery_index]),
        )

        candidate = SearchMatch(
            rank=0,
            image_rank=0,
            record_id=record_id,
            gallery_id=gallery_id,
            species=species,
            visual_score=float(np.clip(visual_scores[local_index], -1.0, 1.0)),
            full_score=float(np.clip(full_scores[local_index], -1.0, 1.0)),
            crop_score=float(np.clip(crop_scores[local_index], -1.0, 1.0)),
            phash_distance=hash_distance,
            near_duplicate=hash_distance <= PHASH_NEAR_DUPLICATE_MAX,
            image_path=str(meta.get("image_path", "")),
            image_url=str(meta.get("image_url", "")),
            kind=str(meta.get("kindCd", "") or ""),
            color=str(meta.get("colorCd", "") or ""),
            sex=str(meta.get("sexCd", "") or ""),
            care_name=str(meta.get("careNm", "") or ""),
            care_tel=str(meta.get("careTel", "") or ""),
            care_address=str(meta.get("careAddr", "") or ""),
            candidate_type=str(meta.get("candidate_type", "SHELTER")),
            candidate_report_id=meta.get("candidate_report_id"),
        )

        previous = best_by_record.get(record_id)
        if previous is None or match_rank_key(candidate) > match_rank_key(previous):
            best_by_record[record_id] = candidate

    ranked = sorted(best_by_record.values(), key=match_rank_key, reverse=True)[:top_k]
    for rank, match in enumerate(ranked, start=1):
        match.rank = rank
        match.image_rank = rank
    return query, ranked


def search_decision(matches: Sequence[SearchMatch]) -> str:
    if not matches:
        return "NO_GALLERY"
    if matches[0].near_duplicate:
        return "NEAR_DUPLICATE_CANDIDATE"
    return "RANKED_CANDIDATES_NEED_HUMAN_REVIEW"


def print_search_report(query: QueryPack, matches: Sequence[SearchMatch]) -> str:
    decision = search_decision(matches)
    labels = {
        "NO_GALLERY": "검색할 갤러리가 비어 있습니다.",
        "NEAR_DUPLICATE_CANDIDATE": "동일하거나 거의 동일한 원본 사진 후보가 있습니다.",
        "RANKED_CANDIDATES_NEED_HUMAN_REVIEW": "시각적으로 가까운 후보 순위입니다. 동일 개체 확정이 아닙니다.",
    }
    print("판정:", labels[decision])
    print("종:", query.species)
    print("모델:", MODEL_VERSION)
    print("주의: visual_score는 코사인 유사도이며 확률이 아닙니다.")

    for item in query.quality:
        print(
            "query quality:",
            Path(item["path"]).name,
            f"detected={item['detected']}",
            f"conf={item['confidence']:.2f}",
            f"blur={item['blur']:.1f}",
            item["warnings"] or "warnings=none",
        )

    if len(matches) >= 2 and not matches[0].near_duplicate:
        gap = matches[0].visual_score - matches[1].visual_score
        print("top1-top2 visual gap:", round(gap, 4))

    for match in matches:
        duplicate_label = "near_duplicate" if match.near_duplicate else "reid"
        print(
            f"{match.rank:02d}. ID={match.record_id} "
            f"visual={match.visual_score:.3f} "
            f"full={match.full_score:.3f} crop={match.crop_score:.3f} "
            f"pHash={match.phash_distance} {duplicate_label} | "
            f"{match.kind} | {match.color} | {match.care_name} | {match.care_tel}"
        )
    return decision


def save_search_results_csv(matches: Sequence[SearchMatch], path: str | Path) -> Path:
    path = Path(path)
    fieldnames = list(SearchMatch.__dataclass_fields__.keys())
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for match in matches:
            writer.writerow(asdict(match))
    print("saved:", path)
    return path
