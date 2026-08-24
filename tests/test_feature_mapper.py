from app.schemas.match import MatchRequest
from app.services.feature_mapper import features_to_query_metadata, matched_tags_for_be


def test_features_to_query_metadata_maps_korean_categories() -> None:
    request = MatchRequest.model_validate(
        {
            "reportId": 1,
            "species": "강아지",
            "photoUrls": [],
            "features": [
                {"category": "털길이", "keyword": "장모"},
                {"category": "귀", "keyword": "귀 접힘"},
                {"category": "색상", "keyword": "흰색"},
                {"category": "털색", "keyword": "갈색"},
            ],
            "reportType": "LOST",
            "eventDate": "2026-08-01",
            "latitude": 37.5665,
            "longitude": 126.9780,
            "happenPlace": "서울특별시 마포구",
        }
    )

    metadata = features_to_query_metadata(request)
    assert metadata["coat_length"] == "장모"
    assert metadata["ear_shape"] == "귀 접힘"
    assert metadata["colors"] == ["흰색", "갈색"]
    assert metadata["lost_at"] == "2026-08-01"
    assert metadata["lost_location"]["latitude"] == 37.5665
    assert metadata["lost_location"]["address"] == "서울특별시 마포구"


def test_matched_tags_for_be_converts_field_names() -> None:
    matched = matched_tags_for_be(("coat_length:long_coat", "ear_shape:folded_ears"))
    assert matched == {"털길이": "long_coat", "귀": "folded_ears"}
