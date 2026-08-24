from __future__ import annotations

import os
import threading
from typing import Literal

from app.schemas.match import MatchRequest, MatchResponse, MatchResultItem

MatchMode = Literal["real", "mock"]
_inference_lock = threading.Lock()


def _match_mode() -> MatchMode:
    return "mock" if os.environ.get("PAWPAWFIND_MATCH_MODE", "real").lower() == "mock" else "real"


def _to_result_item(match) -> MatchResultItem:
    from app.services.feature_mapper import conflicting_tags_for_be, matched_tags_for_be

    candidate_type = (
        match.candidate_type if match.candidate_type in {"SHELTER", "REPORT"} else "SHELTER"
    )
    desertion_no = match.record_id if candidate_type == "SHELTER" else None
    candidate_report_id = match.candidate_report_id if candidate_type == "REPORT" else None

    return MatchResultItem(
        rank=match.rank,
        candidate_type=candidate_type,
        desertion_no=desertion_no,
        candidate_report_id=candidate_report_id,
        visual_score=round(match.visual_score, 5),
        ranking_score=None if match.ranking_score is None else round(match.ranking_score, 5),
        tag_score=None if match.tag_score is None else round(match.tag_score, 5),
        text_score=None if match.text_score is None else round(match.text_score, 5),
        location_score=(None if match.location_score is None else round(match.location_score, 5)),
        time_score=None if match.time_score is None else round(match.time_score, 5),
        spatiotemporal_score=(
            None if match.spatiotemporal_score is None else round(match.spatiotemporal_score, 5)
        ),
        distance_km=None if match.distance_km is None else round(match.distance_km, 3),
        elapsed_days=match.elapsed_days,
        location_method=match.location_method,
        phash_distance=match.phash_distance,
        near_duplicate=match.near_duplicate,
        matched_tags=matched_tags_for_be(match.matched_tags),
        conflicting_tags=conflicting_tags_for_be(match.conflicting_tags),
        gallery_id=match.gallery_id,
        image_url=match.image_url or None,
    )


def _run_mock_match(request: MatchRequest) -> MatchResponse:
    from app.services.matcher_mock import run_mock_match

    return run_mock_match(request)


def _run_real_match(request: MatchRequest) -> MatchResponse:
    with _inference_lock:
        return _run_real_match_locked(request)


def _run_real_match_locked(request: MatchRequest) -> MatchResponse:
    from app.reid.config import DEFAULT_TOP_K, MODEL_VERSION, RERANK_VERSION, SPECIES_KO_TO_EN
    from app.reid.rerank import search_gallery_multimodal
    from app.reid.runtime import get_gallery
    from app.reid.search import search_decision
    from app.services.feature_mapper import features_to_query_metadata
    from app.services.photo_download import downloaded_photo_urls

    species = SPECIES_KO_TO_EN.get(request.species)
    if species is None:
        raise ValueError(f"Unsupported species: {request.species}")

    with downloaded_photo_urls(request.photo_urls) as query_paths:
        gallery_data, gallery_meta = get_gallery(
            species_ko=request.species,
            exclude_report_id=request.report_id,
        )
        query_metadata = features_to_query_metadata(request)
        top_k = int(os.environ.get("MATCH_TOP_K", str(DEFAULT_TOP_K)))

        _, _, matches, _diagnostics = search_gallery_multimodal(
            query_paths,
            species=species,
            gallery_data=gallery_data,
            metadata=gallery_meta,
            query_metadata=query_metadata,
            top_k=top_k,
        )

    return MatchResponse(
        report_id=request.report_id,
        model_version=MODEL_VERSION,
        rerank_version=RERANK_VERSION,
        decision=search_decision(matches),
        results=[_to_result_item(match) for match in matches],
    )


def run_match(request: MatchRequest) -> MatchResponse:
    if _match_mode() == "mock":
        return _run_mock_match(request)
    return _run_real_match(request)
