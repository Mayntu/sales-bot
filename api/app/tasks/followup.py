"""
Follow-up Celery task — queue: followup

Executed by worker_followup (concurrency=4, see docker-compose.yml).

Design:
  - Uses synchronous SQLAlchemy session (psycopg2, pool shared across tasks)
  - Uses synchronous Redis client for club context cache
  - asyncio.run() only for Telegram send (python-telegram-bot async API)
"""

import asyncio
import logging
import uuid

import redis as sync_redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db.sync import SyncSession
from app.tasks.celery_app import celery_app
from app.domain.followup.models import FollowUpStatus, FollowUpTask
from app.domain.users.models import User
from app.domain.conversations.models import Message, MessageRole
from app.cache.club_context import load_club_context_sync
from app.ai.followup_scenario import compose_followup_message

log = logging.getLogger(__name__)

settings = get_settings()


def _get_sync_redis() -> sync_redis.Redis:
    """One-off sync Redis connection for club context cache in Celery workers."""
    base_url = settings.redis_url.rsplit("/", 1)[0]
    return sync_redis.from_url(
        f"{base_url}/{settings.redis_cache_db}",
        decode_responses=True,
    )


@celery_app.task(name="followup.send", queue="followup", bind=True, max_retries=2)
def send_followup(self, task_id: str) -> None:
    db = SyncSession()
    try:
        task = db.execute(
            select(FollowUpTask).where(FollowUpTask.id == uuid.UUID(task_id))
        ).scalar_one_or_none()

        if not task or task.status != FollowUpStatus.pending:
            return

        user = db.execute(select(User).where(User.id == task.user_id)).scalar_one_or_none()
        if not user:
            task.status = FollowUpStatus.cancelled
            db.commit()
            return

        # Cancel if user replied after this chain was scheduled
        if user.last_message_at > task.baseline_last_message_at:
            task.status = FollowUpStatus.cancelled
            db.commit()
            return

        history = (
            db.execute(
                select(Message)
                .where(Message.user_id == user.id)
                .order_by(Message.created_at.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )
        dialog = [{"role": m.role.value, "content": m.content} for m in reversed(history)]

        # Club context from Redis cache (sync)
        r = _get_sync_redis()
        club = load_club_context_sync(r)
        r.close()

        reply = compose_followup_message(user, club, task.message_type.value, dialog)

        # Send via Telegram
        from app.tasks.notifications import _send_telegram_async  # local import

        asyncio.run(_send_telegram_async(user.telegram_chat_id, reply))

        db.add(Message(user_id=user.id, role=MessageRole.assistant, content=reply))
        task.status = FollowUpStatus.sent
        user.followup_count = (user.followup_count or 0) + 1
        db.commit()

    except Exception as exc:
        log.exception("send_followup failed for task_id=%s", task_id)
        db.rollback()
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()
