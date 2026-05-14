"""
Redis-backed cache for club context.

Strategy:
  - Key: club_context:v1 (single key, stores the full YAML as JSON)
  - TTL: 5 minutes (Settings.club_context_cache_ttl)
  - On miss: load from disk, write to Redis, return
  - Invalidation: delete key → next request reloads from disk

Two variants:
  - async  — for FastAPI handlers (uses redis.asyncio)
  - sync   — for Celery workers (uses redis plain sync client)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import redis as sync_redis_lib
import redis.asyncio as aioredis
import yaml

from app.core.config import get_settings

log = logging.getLogger(__name__)

_CACHE_KEY = "club_context:v1"


# ── Shared helpers ────────────────────────────────────────────────────────────


def _load_yaml_from_disk(path: str) -> dict:
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_club_context(raw: dict):
    """Convert a raw YAML dict into a ClubContext domain object."""
    # Imported here to avoid circular imports at module load time
    from app.ai.club_context import ClubContext, DailyDiscounts  # noqa: PLC0415

    gym_name = raw.get("gym", {}).get("name", "Underground Gym Astana")
    dd_raw = raw.get("daily_discounts") or {}
    try:
        daily = DailyDiscounts.model_validate(
            {"date": dd_raw.get("date"), "discounts": dd_raw.get("discounts") or []}
        )
    except Exception:
        log.warning("Failed to parse daily_discounts from cache, using empty")
        daily = DailyDiscounts()

    return ClubContext(gym_name=gym_name, raw=raw, daily_discounts=daily)


# ── Async (FastAPI) ───────────────────────────────────────────────────────────


async def load_club_context_async(redis_client: aioredis.Redis):
    """Return ClubContext, served from Redis cache or loaded from disk."""
    settings = get_settings()

    cached = await redis_client.get(_CACHE_KEY)
    if cached:
        try:
            raw = json.loads(cached)
            return _build_club_context(raw)
        except Exception:
            log.warning("Corrupt club_context cache, reloading from disk")

    raw = _load_yaml_from_disk(settings.club_info_path)
    try:
        await redis_client.setex(
            _CACHE_KEY,
            settings.club_context_cache_ttl,
            json.dumps(raw, default=str),
        )
    except Exception:
        log.exception("Failed to write club_context to Redis cache")

    return _build_club_context(raw)


async def invalidate_club_cache_async(redis_client: aioredis.Redis) -> None:
    """Delete cached club context so the next request reloads from disk."""
    await redis_client.delete(_CACHE_KEY)


# ── Sync (Celery workers) ─────────────────────────────────────────────────────


def load_club_context_sync(redis_client: sync_redis_lib.Redis):
    """Sync version for Celery workers — same logic as async variant."""
    settings = get_settings()

    cached = redis_client.get(_CACHE_KEY)
    if cached:
        try:
            raw = json.loads(cached)
            return _build_club_context(raw)
        except Exception:
            log.warning("Corrupt club_context cache (sync), reloading from disk")

    raw = _load_yaml_from_disk(settings.club_info_path)
    try:
        redis_client.setex(
            _CACHE_KEY,
            settings.club_context_cache_ttl,
            json.dumps(raw, default=str),
        )
    except Exception:
        log.exception("Failed to write club_context to Redis cache (sync)")

    return _build_club_context(raw)
