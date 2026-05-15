"""
Немедленная отправка follow-up (демо «машина времени», тот же смысл что Celery send_followup).
Текст сообщения — детерминированный (compose_followup_message), без LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.followup_scenario import compose_followup_message
from app.cache.club_context import load_club_context_async
from app.domain.conversations.models import MessageRole
from app.domain.conversations.repo import ConversationsRepo
from app.domain.followup.models import FollowUpStatus, FollowUpTask
from app.domain.users.models import User
from app.tasks.notifications import _send_telegram_async

_FOLLOWUP_HISTORY_LIMIT = 10


async def dispatch_follow_up_now(
    db: AsyncSession,
    redis: aioredis.Redis,
    task: FollowUpTask,
    user: User,
    *,
    force_ignore_baseline: bool,
) -> None:
    """
    Вызывать уже для pending-таски после revoke Celery ETA.
    Если не force_ignore_baseline и клиент уже писал после baseline — задача считается устаревшей (как в worker).
    """
    if task.status != FollowUpStatus.pending:
        return

    if not force_ignore_baseline:
        bl = task.baseline_last_message_at
        if bl.tzinfo is None:
            bl = bl.replace(tzinfo=timezone.utc)
        la = user.last_message_at
        if la.tzinfo is None:
            la = la.replace(tzinfo=timezone.utc)
        if la > bl:
            task.status = FollowUpStatus.cancelled
            return

    conv = ConversationsRepo(db)
    history = await conv.last_messages(user.id, _FOLLOWUP_HISTORY_LIMIT)
    dialog = [{"role": m.role.value, "content": m.content} for m in history]

    club = await load_club_context_async(redis)
    reply = compose_followup_message(user, club, task.message_type.value, dialog)

    await _send_telegram_async(user.telegram_chat_id, reply)
    await conv.add_message(user.id, MessageRole.assistant, reply)

    task.status = FollowUpStatus.sent
    task.sent_at = datetime.now(timezone.utc)
    user.followup_count = (user.followup_count or 0) + 1
