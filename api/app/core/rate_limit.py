"""
Per-chat-id rate limiter backed by Redis.

Uses a 1-minute sliding counter (INCR + EXPIRE).
Raises RateLimitError (HTTP 429) when the limit is exceeded.
"""

import redis.asyncio as aioredis

from app.core.config import get_settings
from app.core.exceptions import RateLimitError


async def rate_limit_chat(chat_id: int, redis_client: aioredis.Redis) -> None:
    """Enforce per-chat-id rate limit. Call this at the start of the chat handler."""
    settings = get_settings()
    key = f"rl:chat:{chat_id}"

    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    results = await pipe.execute()

    count: int = results[0]
    if count > settings.chat_rate_limit_per_minute:
        raise RateLimitError(
            detail=f"Rate limit exceeded: max {settings.chat_rate_limit_per_minute} messages per minute"
        )
