import os

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.search_area import SearchAreaRequest, SearchAreaResponse
from app.search_area.environment import OverpassEnvironmentProvider
from app.services.search_area import SearchAreaRecommendationService

router = APIRouter()


def get_search_area_service() -> SearchAreaRecommendationService:
    provider = OverpassEnvironmentProvider(
        url=os.getenv("OVERPASS_API_URL", "https://overpass-api.de/api/interpreter"),
        timeout_seconds=float(os.getenv("OVERPASS_TIMEOUT_SECONDS", "10")),
    )
    return SearchAreaRecommendationService(provider)


@router.post("/search-areas", response_model=SearchAreaResponse)
async def post_search_areas(
    request: SearchAreaRequest,
    service: SearchAreaRecommendationService = Depends(get_search_area_service),
) -> SearchAreaResponse:
    try:
        return await service.recommend(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
