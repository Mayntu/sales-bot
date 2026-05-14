from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.dependencies import (
    bootstrap_ai_client,
    close_redis_pool,
    init_redis_pool,
)
from app.core.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()

    settings = get_settings()

    # Initialise shared resources — order matters
    await init_redis_pool(settings.redis_url, settings.redis_cache_db)
    bootstrap_ai_client()

    yield

    await close_redis_pool()


app = FastAPI(title="gym-sales-api", lifespan=lifespan)
app.include_router(v1_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"ok": True}
