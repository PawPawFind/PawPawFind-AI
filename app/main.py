from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.embed import router as embed_router
from app.api.health import router as health_router
from app.api.match import router as match_router
from app.api.search_area import router as search_area_router
from app.search_area.settings import load_search_area_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.search_area_settings = load_search_area_settings()
    yield


app = FastAPI(title="PawPawFind AI API", lifespan=lifespan)
app.include_router(health_router)
app.include_router(match_router)
app.include_router(embed_router)
app.include_router(search_area_router)
