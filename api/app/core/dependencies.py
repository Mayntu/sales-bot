"""
FastAPI dependency providers.

Initialized in lifespan (app/main.py):
  - Redis connection pool (separate DB from Celery broker)
  - AIClient singleton

Usage in route handlers:
  db: AsyncSession = Depends(get_db)
  redis: aioredis.Redis = Depends(get_redis_pool)
  ai: AIClient = Depends(get_ai_client)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import SessionLocal

# ── Redis pool ────────────────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


async def init_redis_pool(redis_url: str, cache_db: int) -> aioredis.Redis:
    global _redis_pool
    base_url = redis_url.rsplit("/", 1)[0]
    _redis_pool = aioredis.from_url(
        f"{base_url}/{cache_db}",
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


def get_redis_pool() -> aioredis.Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis pool is not initialised; call init_redis_pool() in lifespan")
    return _redis_pool


# ── AIClient singleton ────────────────────────────────────────────────────────

from app.ai.client import AIClient, init_ai_client  # noqa: E402 (avoid circular at module level)

_ai_client: AIClient | None = None


def bootstrap_ai_client() -> AIClient:
    global _ai_client
    _ai_client = init_ai_client()
    return _ai_client


def get_ai_client() -> AIClient:
    if _ai_client is None:
        raise RuntimeError("AIClient is not initialised; call bootstrap_ai_client() in lifespan")
    return _ai_client


# ── DB session ────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
