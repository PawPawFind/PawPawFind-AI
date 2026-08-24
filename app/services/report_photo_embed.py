"""Single report photo embed on upload (BE → AI → RDS)."""

from __future__ import annotations

from app.reid.config import MODEL_VERSION, PREPROCESS_VERSION
from app.schemas.embed import ReportPhotoEmbedRequest, ReportPhotoEmbedResponse
from app.schemas.gallery import EmbeddingBatchResponse
from app.schemas.sync import ReportPhotoForEmbeddingItem
from app.services.backend_client import upsert_report_embeddings
from app.services.image_download import make_temp_dir
from app.services.report_embed_sync import report_item_to_batch_item


def embed_report_photo(request: ReportPhotoEmbedRequest) -> ReportPhotoEmbedResponse:
    photo_url = request.photo_url.strip()
    if not photo_url:
        raise ValueError("photoUrl is required")

    item = ReportPhotoForEmbeddingItem(
        reportPhotoId=request.report_photo_id,
        reportId=request.report_id,
        species=request.species.strip().lower(),
        photoUrl=photo_url,
    )

    temp_dir = make_temp_dir("pawpawfind-report-upload-")
    batch_item = report_item_to_batch_item(
        item,
        model_version=MODEL_VERSION,
        preprocess_version=PREPROCESS_VERSION,
        temp_dir=temp_dir,
    )
    result: EmbeddingBatchResponse = upsert_report_embeddings([batch_item])
    return ReportPhotoEmbedResponse(upserted=result.upserted, skipped=result.skipped)
