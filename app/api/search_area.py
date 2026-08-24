from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.search_area import SearchAreaRequest, SearchAreaResponse
from app.search_area.environment import OverpassEnvironmentProvider
from app.search_area.settings import SearchAreaSettings
from app.services.search_area import SearchAreaRecommendationService

router = APIRouter()


def get_search_area_service(request: Request) -> SearchAreaRecommendationService:
    settings: SearchAreaSettings = request.app.state.search_area_settings
    provider = OverpassEnvironmentProvider(
        url=settings.overpass_api_url,
        timeout_seconds=settings.overpass_timeout_seconds,
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
