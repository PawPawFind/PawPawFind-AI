from fastapi import FastAPI

from app.api.embed import router as embed_router
from app.api.health import router as health_router
from app.api.match import router as match_router

app = FastAPI(title="PawPawFind AI API")
app.include_router(health_router)
app.include_router(match_router)
app.include_router(embed_router)
