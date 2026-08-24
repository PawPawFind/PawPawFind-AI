"""Metadata tag + text reranking."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from app.reid.config import (
    DEFAULT_RERANK_WEIGHTS,
    DEFAULT_TOP_K,
    MODEL_VERSION,
    MULTIMODAL_CANDIDATE_POOL,
    RERANK_VERSION,
    TEXT_BATCH_SIZE,
    TEXT_MAX_LENGTH,
    TEXT_MODEL_ID,
)
from app.reid.runtime import get_device
from app.reid.search import QueryPack, SearchMatch, search_gallery
from app.reid.spatiotemporal import (
    canonical_report_type,
    optional_float,
    spatiotemporal_similarity,
)

TAG_FIELDS = (
    "sex",
    "colors",
    "patterns",
    "coat_length",
    "ear_shape",
    "tail_shape",
    "size",
    "distinctive_features",
    "accessories",
    "body_condition",
    "behavior",
)

TAG_FIELD_WEIGHTS = {
    "sex": 0.7,
    "colors": 1.0,
    "patterns": 1.3,
    "coat_length": 0.6,
    "ear_shape": 0.8,
    "tail_shape": 0.8,
    "size": 0.5,
    "distinctive_features": 1.5,
    "accessories": 1.2,
    "body_condition": 0.7,
    "behavior": 0.4,
}

TAG_ALIASES = {
    "M": "male",
    "MALE": "male",
    "수": "male",
    "수컷": "male",
    "남아": "male",
    "F": "female",
    "FEMALE": "female",
    "암": "female",
    "암컷": "female",
    "여아": "female",
    "Q": "unknown",
    "U": "unknown",
    "UNKNOWN": "unknown",
    "미상": "unknown",
    "모름": "unknown",
    "흰": "white",
    "흰색": "white",
    "백색": "white",
    "화이트": "white",
    "검": "black",
    "검정": "black",
    "검정색": "black",
    "검은색": "black",
    "흑색": "black",
    "블랙": "black",
    "갈": "brown",
    "갈색": "brown",
    "밤색": "brown",
    "브라운": "brown",
    "황색": "tan",
    "연갈색": "tan",
    "베이지": "tan",
    "크림": "cream",
    "크림색": "cream",
    "회색": "gray",
    "회": "gray",
    "그레이": "gray",
    "노랑": "yellow",
    "노란색": "yellow",
    "황갈색": "tan",
    "주황": "orange",
    "주황색": "orange",
    "치즈": "orange",
    "삼색": "tricolor",
    "삼색이": "tricolor",
    "고등어": "tabby",
    "줄무늬": "tabby",
    "태비": "tabby",
    "턱시도": "tuxedo",
    "점박이": "spotted",
    "얼룩": "spotted",
    "얼룩무늬": "spotted",
    "단모": "short_coat",
    "짧은털": "short_coat",
    "장모": "long_coat",
    "긴털": "long_coat",
    "중모": "medium_coat",
    "직립": "upright_ears",
    "쫑긋귀": "upright_ears",
    "선귀": "upright_ears",
    "처진귀": "floppy_ears",
    "접힌귀": "folded_ears",
    "말린꼬리": "curled_tail",
    "짧은꼬리": "short_tail",
    "긴꼬리": "long_tail",
    "소형": "small",
    "중형": "medium",
    "대형": "large",
}

SHELTER_DESCRIPTION_KEYS = (
    "specialMark",
    "special_mark",
    "noticeComment",
    "notice_comment",
    "description",
    "etcBigo",
)

_text_tokenizer = None
_text_model = None  # lazy text encoder
_text_embedding_cache: Dict[Tuple[str, str], np.ndarray] = {}


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        rendered = [text_value(item) for item in value]
        return " ".join(item for item in rendered if item)
    return str(value).strip()


def compact_token(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", text_value(value)).strip()
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", normalized).lower()


def canonical_tag(value: Any, field: Optional[str] = None) -> str:
    raw = text_value(value)
    if not raw:
        return ""
    alias_key = re.sub(r"[\s_\-/]+", "", unicodedata.normalize("NFKC", raw)).upper()
    if alias_key in TAG_ALIASES:
        return TAG_ALIASES[alias_key]
    compact = compact_token(raw)
    if field == "sex" and compact:
        first = compact[0].upper()
        if first in TAG_ALIASES:
            return TAG_ALIASES[first]
    return TAG_ALIASES.get(compact, compact)


def split_tag_values(value: Any, field: Optional[str] = None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = re.split(r"[,/|+&·ㆍ;，、]|\s+및\s+|\s+와\s+|\s+과\s+", text_value(value))
    normalized = [canonical_tag(part, field=field) for part in parts]
    return list(dict.fromkeys(item for item in normalized if item and item != "unknown"))


def first_present(record: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if text_value(value):
            return value
    return ""


def nested_location(raw: Mapping[str, Any], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def normalize_query_metadata(raw: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    raw = dict(raw or {})
    location = nested_location(raw, ("lost_location", "lostLocation", "location"))
    return {
        "report_type": canonical_report_type(
            first_present(raw, ("report_type", "reportType", "type")), default="LOST"
        ),
        "sex": split_tag_values(first_present(raw, ("sex", "sexCd", "gender")), field="sex"),
        "colors": split_tag_values(
            first_present(raw, ("colors", "color", "colorCd")), field="colors"
        ),
        "patterns": split_tag_values(
            first_present(raw, ("patterns", "pattern", "markings")), field="patterns"
        ),
        "coat_length": split_tag_values(
            first_present(raw, ("coat_length", "coatLength")), field="coat_length"
        ),
        "ear_shape": split_tag_values(
            first_present(raw, ("ear_shape", "earShape")), field="ear_shape"
        ),
        "tail_shape": split_tag_values(
            first_present(raw, ("tail_shape", "tailShape")), field="tail_shape"
        ),
        "size": split_tag_values(
            first_present(raw, ("size", "body_size", "bodySize")), field="size"
        ),
        "distinctive_features": split_tag_values(
            first_present(raw, ("distinctive_features", "features", "feature_tags")),
            field="distinctive_features",
        ),
        "accessories": split_tag_values(
            first_present(raw, ("accessories", "wearing", "착용중")),
            field="accessories",
        ),
        "body_condition": split_tag_values(
            first_present(raw, ("body_condition", "bodyCondition", "몸상태")),
            field="body_condition",
        ),
        "behavior": split_tag_values(
            first_present(raw, ("behavior", "behaviour", "행동")),
            field="behavior",
        ),
        "description": text_value(first_present(raw, ("description", "free_text", "memo"))),
        "lost_at": text_value(first_present(raw, ("lost_at", "lostAt", "eventDate", "missingAt"))),
        "latitude": optional_float(
            first_present(location, ("latitude", "lat")) or first_present(raw, ("latitude", "lat"))
        ),
        "longitude": optional_float(
            first_present(location, ("longitude", "lng", "lon"))
            or first_present(raw, ("longitude", "lng", "lon"))
        ),
        "address": text_value(
            first_present(location, ("address", "roadAddress", "place"))
            or first_present(raw, ("happenPlace", "address", "lostAddress"))
        ),
    }


def normalize_candidate_metadata(record: Mapping[str, Any]) -> Dict[str, Any]:
    description_parts = [text_value(record.get(key)) for key in SHELTER_DESCRIPTION_KEYS]
    description = " ".join(dict.fromkeys(part for part in description_parts if part))
    location = nested_location(record, ("found_location", "foundLocation", "location"))
    normalized = normalize_query_metadata(
        {
            "sex": first_present(record, ("sexCd", "sex", "gender")),
            "colors": first_present(record, ("colorCd", "colors", "color")),
            "patterns": first_present(record, ("patterns", "pattern", "markings")),
            "coat_length": first_present(record, ("coat_length", "coatLength")),
            "ear_shape": first_present(record, ("ear_shape", "earShape")),
            "tail_shape": first_present(record, ("tail_shape", "tailShape")),
            "size": first_present(record, ("size", "body_size", "bodySize")),
            "distinctive_features": first_present(
                record, ("distinctive_features", "features", "feature_tags")
            ),
            "accessories": first_present(record, ("accessories", "wearing", "착용중")),
            "body_condition": first_present(record, ("body_condition", "bodyCondition", "몸상태")),
            "behavior": first_present(record, ("behavior", "behaviour", "행동")),
            "description": description,
        }
    )
    normalized.update(
        {
            "report_type": canonical_report_type(
                first_present(record, ("report_type", "reportType", "candidateReportType")),
                default="FOUND",
            ),
            "found_at": text_value(
                first_present(
                    record,
                    ("found_at", "foundAt", "eventDate", "happenDt", "noticeSdt"),
                )
            ),
            "latitude": optional_float(
                first_present(location, ("latitude", "lat", "foundLat"))
                or first_present(record, ("latitude", "lat", "foundLat", "happenLat"))
            ),
            "longitude": optional_float(
                first_present(location, ("longitude", "lng", "lon", "foundLng"))
                or first_present(record, ("longitude", "lng", "lon", "foundLng", "happenLng"))
            ),
            "address": text_value(
                first_present(location, ("address", "roadAddress", "place"))
                or first_present(record, ("happenPlace", "foundAddress", "address"))
            ),
        }
    )
    normalized["lost_at"] = ""
    return normalized


def metadata_description(metadata: Mapping[str, Any]) -> str:
    parts: List[str] = []
    labels = {
        "sex": "성별",
        "colors": "색상",
        "patterns": "무늬",
        "coat_length": "털길이",
        "ear_shape": "귀",
        "tail_shape": "꼬리",
        "size": "크기",
        "distinctive_features": "특징",
        "accessories": "착용",
        "body_condition": "몸상태",
        "behavior": "행동",
    }
    for field in TAG_FIELDS:
        values = metadata.get(field, [])
        if values:
            parts.append(f"{labels[field]} {' '.join(values)}")
    if text_value(metadata.get("description")):
        parts.append(text_value(metadata["description"]))
    return "; ".join(parts)


def structured_tag_similarity(
    query_metadata: Mapping[str, Any],
    candidate_metadata: Mapping[str, Any],
) -> Tuple[Optional[float], float, Tuple[str, ...], Tuple[str, ...]]:
    earned = 0.0
    compared_weight = 0.0
    available_weight = 0.0
    matched: List[str] = []
    conflicts: List[str] = []

    for field in TAG_FIELDS:
        query_values = set(query_metadata.get(field, []))
        if not query_values:
            continue
        weight = TAG_FIELD_WEIGHTS[field]
        available_weight += weight
        candidate_values = set(candidate_metadata.get(field, []))
        if not candidate_values:
            continue

        compared_weight += weight
        overlap = query_values & candidate_values
        field_score = len(overlap) / max(len(query_values | candidate_values), 1)
        earned += weight * field_score
        if overlap:
            matched.extend(f"{field}:{value}" for value in sorted(overlap))
        elif field in {"sex", "coat_length", "ear_shape", "tail_shape", "size"}:
            conflicts.append(field)

    if compared_weight <= 0:
        return None, 0.0, tuple(matched), tuple(conflicts)
    coverage = compared_weight / max(available_weight, 1e-12)
    return earned / compared_weight, coverage, tuple(matched), tuple(conflicts)


def load_text_encoder() -> Tuple[Any, Any]:
    global _text_tokenizer, _text_model
    if _text_tokenizer is None or _text_model is None:
        print("Loading optional Korean/multilingual text encoder:", TEXT_MODEL_ID)
        _text_tokenizer = AutoTokenizer.from_pretrained(TEXT_MODEL_ID, token=False)
        _text_model = AutoModel.from_pretrained(TEXT_MODEL_ID, token=False).to(get_device()).eval()
    return _text_tokenizer, _text_model


def average_pool_text(
    last_hidden_state: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    mask = attention_mask[..., None].bool()
    hidden = last_hidden_state.masked_fill(~mask, 0.0)
    return hidden.sum(dim=1) / attention_mask.sum(dim=1, keepdim=True).clamp(min=1)


@torch.inference_mode()
def embed_texts(texts: Sequence[str], role: str = "passage") -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype="float32")
    prefix = "query: " if role == "query" else "passage: "
    normalized_texts = [text_value(text) for text in texts]
    missing = list(
        dict.fromkeys(
            text for text in normalized_texts if (role, text) not in _text_embedding_cache
        )
    )
    if missing:
        tokenizer, model = load_text_encoder()
    for start in range(0, len(missing), TEXT_BATCH_SIZE):
        raw_batch = missing[start : start + TEXT_BATCH_SIZE]
        batch = [prefix + text for text in raw_batch]
        encoded = tokenizer(
            batch,
            max_length=TEXT_MAX_LENGTH,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
        encoded = {key: value.to(get_device()) for key, value in encoded.items()}
        output = model(**encoded)
        pooled = average_pool_text(output.last_hidden_state, encoded["attention_mask"])
        pooled = F.normalize(pooled, p=2, dim=-1)
        batch_vectors = pooled.cpu().numpy().astype("float32")
        for text, vector in zip(raw_batch, batch_vectors):
            _text_embedding_cache[(role, text)] = vector
    return np.stack([_text_embedding_cache[(role, text)] for text in normalized_texts])


def candidate_record(match: SearchMatch, metadata: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
    record = dict(metadata.get(match.gallery_id, {}))
    if not text_value(record.get("sexCd")):
        record["sexCd"] = match.sex
    if not text_value(record.get("colorCd")):
        record["colorCd"] = match.color
    return record


def active_rerank_weights(
    query_metadata: Mapping[str, Any],
    tag_scores: Sequence[Optional[float]],
    text_scores: Sequence[Optional[float]],
    spatiotemporal_scores: Sequence[Optional[float]],
    weights: Mapping[str, float],
) -> Dict[str, float]:
    active = {
        "image": max(float(weights.get("image", 0.0)), 0.0),
        "tags": 0.0,
        "text": 0.0,
        "location": 0.0,
    }
    has_query_tags = any(query_metadata.get(field) for field in TAG_FIELDS)
    if has_query_tags and any(score is not None for score in tag_scores):
        active["tags"] = max(float(weights.get("tags", 0.0)), 0.0)
    if text_value(query_metadata.get("description")) and any(
        score is not None for score in text_scores
    ):
        active["text"] = max(float(weights.get("text", 0.0)), 0.0)
    has_query_spatiotemporal = (
        query_metadata.get("latitude") is not None
        or query_metadata.get("longitude") is not None
        or text_value(query_metadata.get("address"))
        or text_value(query_metadata.get("lost_at"))
    )
    if has_query_spatiotemporal and any(score is not None for score in spatiotemporal_scores):
        active["location"] = max(float(weights.get("location", 0.0)), 0.0)
    total = sum(active.values())
    if total <= 0:
        return {"image": 1.0, "tags": 0.0, "text": 0.0, "location": 0.0}
    return {key: value / total for key, value in active.items()}


def rerank_matches(
    image_matches: Sequence[SearchMatch],
    query_metadata: Optional[Mapping[str, Any]],
    metadata: Mapping[str, Dict[str, Any]],
    weights: Mapping[str, float] = DEFAULT_RERANK_WEIGHTS,
) -> Tuple[List[SearchMatch], Dict[str, Any]]:
    normalized_query = normalize_query_metadata(query_metadata)
    candidates = [replace(match) for match in image_matches]
    if not candidates:
        return [], {"weights": {"image": 1.0, "tags": 0.0, "text": 0.0, "location": 0.0}}

    candidate_metadata = [
        normalize_candidate_metadata(candidate_record(match, metadata)) for match in candidates
    ]
    tag_details = [structured_tag_similarity(normalized_query, item) for item in candidate_metadata]
    tag_scores = [detail[0] for detail in tag_details]
    spatiotemporal_details = [
        spatiotemporal_similarity(normalized_query, item) for item in candidate_metadata
    ]
    spatiotemporal_scores = [detail["score"] for detail in spatiotemporal_details]

    # 구조화 태그와 자유 문장의 효과를 분리해 측정하기 위해 텍스트 분기는
    # description끼리만 비교합니다. 성별/색상은 tag_score에서만 사용합니다.
    query_text = text_value(normalized_query.get("description"))
    candidate_texts = [text_value(item.get("description")) for item in candidate_metadata]
    text_scores: List[Optional[float]] = [None] * len(candidates)
    if (
        float(weights.get("text", 0.0)) > 0
        and text_value(normalized_query.get("description"))
        and any(candidate_texts)
    ):
        try:
            query_vector = embed_texts([query_text], role="query")[0]
            nonempty_indices = [index for index, text in enumerate(candidate_texts) if text]
            passage_vectors = embed_texts(
                [candidate_texts[index] for index in nonempty_indices], role="passage"
            )
            for index, vector in zip(nonempty_indices, passage_vectors):
                cosine = float(np.clip(vector @ query_vector, -1.0, 1.0))
                text_scores[index] = (cosine + 1.0) / 2.0
        except Exception as exc:
            print("text reranking disabled for this search:", repr(exc))

    effective_weights = active_rerank_weights(
        normalized_query, tag_scores, text_scores, spatiotemporal_scores, weights
    )
    for match, tag_detail, text_score, spatiotemporal in zip(
        candidates, tag_details, text_scores, spatiotemporal_details
    ):
        tag_score, coverage, matched, conflicts = tag_detail
        image_unit_score = (float(match.visual_score) + 1.0) / 2.0
        # 후보 쪽 메타데이터가 비어 있으면 0점으로 벌주지 않고 이미지 점수를 유지합니다.
        # 일부 필드만 비교됐다면 coverage만큼만 태그 점수로 이동합니다.
        tag_component = image_unit_score
        if tag_score is not None:
            tag_component = coverage * tag_score + (1.0 - coverage) * image_unit_score
        text_component = image_unit_score if text_score is None else text_score
        spatiotemporal_component = (
            image_unit_score if spatiotemporal["score"] is None else float(spatiotemporal["score"])
        )
        ranking_score = (
            effective_weights["image"] * image_unit_score
            + effective_weights["tags"] * tag_component
            + effective_weights["text"] * text_component
            + effective_weights["location"] * spatiotemporal_component
        )
        match.tag_score = tag_score
        match.tag_coverage = coverage
        match.text_score = text_score
        match.location_score = spatiotemporal["location_score"]
        match.time_score = spatiotemporal["time_score"]
        match.spatiotemporal_score = spatiotemporal["score"]
        match.distance_km = spatiotemporal["distance_km"]
        match.elapsed_days = spatiotemporal["elapsed_days"]
        match.location_method = spatiotemporal["location_method"]
        match.ranking_score = float(ranking_score)
        match.matched_tags = matched
        match.conflicting_tags = conflicts

    reranked = sorted(
        candidates,
        key=lambda match: (
            1 if match.near_duplicate else 0,
            -match.phash_distance if match.near_duplicate else -65,
            match.ranking_score if match.ranking_score is not None else -1.0,
            match.visual_score,
        ),
        reverse=True,
    )
    for rank, match in enumerate(reranked, start=1):
        match.rank = rank

    diagnostics = {
        "rerank_version": RERANK_VERSION,
        "weights": effective_weights,
        "query_metadata": normalized_query,
        "candidate_count": len(reranked),
        "warning": "ranking_score is a ranking value, not a probability",
    }
    return reranked, diagnostics


def search_gallery_multimodal(
    query_paths: Sequence[str | Path],
    species: str,
    gallery_data: Dict[str, np.ndarray],
    metadata: Dict[str, Dict[str, Any]],
    query_metadata: Optional[Mapping[str, Any]] = None,
    top_k: int = DEFAULT_TOP_K,
    candidate_pool: int = MULTIMODAL_CANDIDATE_POOL,
    weights: Mapping[str, float] = DEFAULT_RERANK_WEIGHTS,
) -> Tuple[QueryPack, List[SearchMatch], List[SearchMatch], Dict[str, Any]]:
    pool_size = max(int(top_k), int(candidate_pool))
    query, image_matches = search_gallery(
        query_paths,
        species=species,
        gallery_data=gallery_data,
        metadata=metadata,
        top_k=pool_size,
    )
    image_only_top = [replace(match) for match in image_matches[:top_k]]
    for rank, match in enumerate(image_only_top, start=1):
        match.rank = rank
    reranked, diagnostics = rerank_matches(
        image_matches,
        query_metadata=query_metadata,
        metadata=metadata,
        weights=weights,
    )
    return query, image_only_top, reranked[:top_k], diagnostics


def print_multimodal_report(
    image_matches: Sequence[SearchMatch],
    reranked_matches: Sequence[SearchMatch],
    diagnostics: Mapping[str, Any],
) -> None:
    print("\n=== v11 image-only vs metadata/location/time reranking ===")
    print("effective weights:", diagnostics.get("weights"))
    print("주의: ranking_score와 visual_score는 동일 개체 확률이 아닙니다.")
    for match in reranked_matches:
        tag_text = "-" if match.tag_score is None else f"{match.tag_score:.3f}"
        text_text = "-" if match.text_score is None else f"{match.text_score:.3f}"
        location_text = (
            "-" if match.spatiotemporal_score is None else f"{match.spatiotemporal_score:.3f}"
        )
        print(
            f"{match.rank:02d}. ID={match.record_id} image_rank={match.image_rank} "
            f"visual={match.visual_score:.3f} tag={tag_text} text={text_text} "
            f"where/when={location_text} "
            f"ranking={match.ranking_score:.3f} matched={list(match.matched_tags)}"
        )
    if image_matches and reranked_matches:
        before = image_matches[0].record_id
        after = reranked_matches[0].record_id
        print("top-1 changed:", before, "->", after, before != after)


def match_to_backend_dict(match: SearchMatch) -> Dict[str, Any]:
    return {
        "rank": match.rank,
        "imageRank": match.image_rank,
        "animalId": match.record_id,
        "galleryId": match.gallery_id,
        "species": match.species,
        "visualSimilarity": round(match.visual_score, 6),
        "tagSimilarity": None if match.tag_score is None else round(match.tag_score, 6),
        "tagCoverage": round(match.tag_coverage, 6),
        "textSimilarity": None if match.text_score is None else round(match.text_score, 6),
        "locationSimilarity": (
            None if match.location_score is None else round(match.location_score, 6)
        ),
        "timeSimilarity": None if match.time_score is None else round(match.time_score, 6),
        "spatiotemporalSimilarity": (
            None if match.spatiotemporal_score is None else round(match.spatiotemporal_score, 6)
        ),
        "distanceKm": None if match.distance_km is None else round(match.distance_km, 3),
        "elapsedDays": match.elapsed_days,
        "locationMethod": match.location_method,
        "rankingScore": None if match.ranking_score is None else round(match.ranking_score, 6),
        "rankingScoreIsProbability": False,
        "visualDisplayScore": round(100.0 * max(match.visual_score, 0.0), 1),
        "scoreLabel": "AI visual similarity",
        "scoreIsProbability": False,
        "nearDuplicate": match.near_duplicate,
        "matchedTags": list(match.matched_tags),
        "conflictingTags": list(match.conflicting_tags),
        "imageUrl": match.image_url,
        "kind": match.kind,
        "color": match.color,
        "sex": match.sex,
        "careName": match.care_name,
        "careTel": match.care_tel,
        "careAddress": match.care_address,
    }


def save_backend_results_json(
    matches: Sequence[SearchMatch],
    diagnostics: Mapping[str, Any],
    path: str | Path,
) -> Path:
    path = Path(path)
    payload = {
        "modelVersion": MODEL_VERSION,
        "rerankVersion": RERANK_VERSION,
        "scoreNotice": "Scores rank candidates and are not identity probabilities.",
        "weights": diagnostics.get("weights", {}),
        "results": [match_to_backend_dict(match) for match in matches],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved:", path)
    return path


def diagnose_record_in_gallery(
    record_id: str,
    gallery_data: Dict[str, np.ndarray],
    metadata: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """특정 공고가 현재 검색 갤러리에 실제로 포함됐는지 확인합니다."""
    record_id = str(record_id).strip()
    indices = np.flatnonzero(gallery_data["record_ids"] == record_id)
    if len(indices) == 0:
        print(f"ID {record_id}: 현재 갤러리에 없음")
        print(
            "가능한 원인: 공고가 protect/notice 상태에서 종료됨, "
            "API 날짜 범위 밖임, 또는 해당 사진 다운로드 실패"
        )
        return []

    found: List[Dict[str, Any]] = []
    print(f"ID {record_id}: 갤러리 사진 {len(indices)}장")
    for index in indices:
        gallery_id = str(gallery_data["gallery_ids"][index])
        meta = metadata.get(gallery_id, {})
        item = {
            "gallery_id": gallery_id,
            "species": str(gallery_data["species"][index]),
            "image_path": str(meta.get("image_path", "")),
            "image_url": str(meta.get("image_url", "")),
            "api_state": str(meta.get("api_state", "")),
        }
        found.append(item)
        print(" -", item)
    return found
