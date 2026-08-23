from fastapi import APIRouter

from app.schemas.match import MatchRequest, MatchResponse
from app.services.matcher import run_match

router = APIRouter()


@router.post("/match", response_model=MatchResponse)
def post_match(request: MatchRequest) -> MatchResponse:
    return run_match(request)
