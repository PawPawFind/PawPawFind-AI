"""Map BE report features to Re-ID query metadata."""

from __future__ import annotations

from app.schemas.match import MatchRequest

CATEGORY_TO_FIELD: dict[str, str] = {
    "성별": "sex",
    "털색": "colors",
    "색상": "colors",
    "색": "colors",
    "무늬": "patterns",
    "털길이": "coat_length",
    "귀": "ear_shape",
    "꼬리": "tail_shape",
    "크기": "size",
    "특징": "distinctive_features",
    "눈/얼굴": "distinctive_features",
    "착용 중": "accessories",
    "몸 상태": "body_condition",
    "행동": "behavior",
}

FIELD_TO_CATEGORY: dict[str, str] = {value: key for key, value in CATEGORY_TO_FIELD.items()}


def features_to_query_metadata(request: MatchRequest) -> dict[str, object]:
    metadata: dict[str, object] = {
        "sex": "",
        "colors": [],
        "patterns": [],
        "coat_length": "",
        "ear_shape": "",
        "tail_shape": "",
        "size": "",
        "distinctive_features": [],
        "accessories": [],
        "body_condition": [],
        "behavior": [],
        "description": request.description or "",
        "report_type": request.report_type or "LOST",
        "lost_at": request.event_date or "",
        "lost_location": {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "address": request.happen_place or "",
        },
    }

    for feature in request.features:
        field = CATEGORY_TO_FIELD.get(feature.category.strip())
        if field is None:
            metadata.setdefault("distinctive_features", [])
            features_list = metadata["distinctive_features"]
            assert isinstance(features_list, list)
            features_list.append(f"{feature.category}:{feature.keyword}")
            continue

        if field in {
            "colors",
            "patterns",
            "distinctive_features",
            "accessories",
            "body_condition",
            "behavior",
        }:
            values = metadata[field]
            assert isinstance(values, list)
            values.append(feature.keyword)
        else:
            metadata[field] = feature.keyword

    return metadata


def matched_tags_for_be(matched: tuple[str, ...]) -> dict[str, str] | None:
    if not matched:
        return None

    result: dict[str, str] = {}
    for item in matched:
        if ":" not in item:
            continue
        field, value = item.split(":", 1)
        category = FIELD_TO_CATEGORY.get(field, field)
        result[category] = value
    return result or None


def conflicting_tags_for_be(conflicts: tuple[str, ...]) -> dict[str, str] | None:
    if not conflicts:
        return None
    return {FIELD_TO_CATEGORY.get(field, field): "conflict" for field in conflicts}
