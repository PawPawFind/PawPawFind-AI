from app.schemas.match import MatchRequest, MatchResponse, MatchResultItem

MOCK_MODEL_VERSION = "mock-v0"
MOCK_RERANK_VERSION = "mock-rerank-v0"

# Sample desertion numbers from animals table (mock until real model is wired).
MOCK_CANDIDATES: list[tuple[str, str, str, float, float, float]] = [
    (
        "445467202601598",
        "dog:record:0",
        "https://example.com/animals/445467202601598.jpg",
        0.91234,
        0.88765,
        0.75,
    ),
    (
        "445467202601599",
        "dog:record:1",
        "https://example.com/animals/445467202601599.jpg",
        0.84102,
        0.81234,
        0.62,
    ),
    (
        "445467202601600",
        "dog:record:2",
        "https://example.com/animals/445467202601600.jpg",
        0.76543,
        0.73456,
        0.55,
    ),
]


def _matched_tags_from_features(request: MatchRequest) -> dict[str, str] | None:
    if not request.features:
        return None
    return {feature.category: feature.keyword for feature in request.features}


def run_match(request: MatchRequest) -> MatchResponse:
    matched_tags = _matched_tags_from_features(request)

    results = [
        MatchResultItem(
            rank=rank,
            candidate_type="SHELTER",
            desertion_no=desertion_no,
            candidate_report_id=None,
            visual_score=visual_score,
            ranking_score=ranking_score,
            tag_score=tag_score,
            text_score=None,
            phash_distance=None,
            near_duplicate=False,
            matched_tags=matched_tags if rank == 1 else None,
            conflicting_tags=None,
            gallery_id=gallery_id,
            image_url=image_url,
        )
        for rank, (
            desertion_no,
            gallery_id,
            image_url,
            visual_score,
            ranking_score,
            tag_score,
        ) in enumerate(MOCK_CANDIDATES, start=1)
    ]

    return MatchResponse(
        report_id=request.report_id,
        model_version=MOCK_MODEL_VERSION,
        rerank_version=MOCK_RERANK_VERSION,
        decision="RANKED_CANDIDATES_NEED_HUMAN_REVIEW",
        results=results,
    )
