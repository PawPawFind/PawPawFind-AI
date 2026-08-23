from fastapi import APIRouter, HTTPException

from app.schemas.embed import AnimalEmbedRequest, ReportPhotoEmbedRequest, ReportPhotoEmbedResponse
from app.services.animal_embed import embed_animal
from app.services.report_photo_embed import embed_report_photo

router = APIRouter()


@router.post("/embed/animal", response_model=ReportPhotoEmbedResponse)
def post_embed_animal(request: AnimalEmbedRequest) -> ReportPhotoEmbedResponse:
    try:
        return embed_animal(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/embed/report-photo", response_model=ReportPhotoEmbedResponse)
def post_embed_report_photo(request: ReportPhotoEmbedRequest) -> ReportPhotoEmbedResponse:
    try:
        return embed_report_photo(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
