from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_match_returns_mock_ranked_candidates() -> None:
    response = client.post(
        "/match",
        json={
            "reportId": 1,
            "species": "강아지",
            "photoUrls": ["https://example.com/reports/1.jpg"],
            "features": [
                {"category": "털길이", "keyword": "장모"},
                {"category": "귀", "keyword": "귀 접힘"},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reportId"] == 1
    assert body["modelVersion"] == "mock-v0"
    assert body["rerankVersion"] == "mock-rerank-v0"
    assert body["decision"] == "RANKED_CANDIDATES_NEED_HUMAN_REVIEW"
    assert len(body["results"]) == 3

    top = body["results"][0]
    assert top["rank"] == 1
    assert top["candidateType"] == "SHELTER"
    assert top["desertionNo"] == "445467202601598"
    assert top["candidateReportId"] is None
    assert top["visualScore"] == 0.91234
    assert top["rankingScore"] == 0.88765
    assert top["tagScore"] == 0.75
    assert top["textScore"] is None
    assert top["phashDistance"] is None
    assert top["nearDuplicate"] is False
    assert top["matchedTags"] == {"털길이": "장모", "귀": "귀 접힘"}
    assert top["conflictingTags"] is None
    assert top["galleryId"] == "dog:record:0"
    assert top["imageUrl"] == "https://example.com/animals/445467202601598.jpg"
