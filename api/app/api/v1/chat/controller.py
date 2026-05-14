"""
Chat controller — thin HTTP layer.

All business logic lives in ChatService.
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import AIClient
from app.api.v1.chat.schemas import ChatIn, ChatOut
from app.api.v1.chat.service import ChatService
from app.core.dependencies import get_ai_client, get_db, get_redis_pool

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatOut)
async def chat(
    payload: ChatIn,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis_pool),
    ai: AIClient = Depends(get_ai_client),
) -> ChatOut:
    return await ChatService(db=db, redis=redis, ai=ai).handle(
        telegram_chat_id=payload.telegram_chat_id,
        message_text=payload.message_text,
    )
