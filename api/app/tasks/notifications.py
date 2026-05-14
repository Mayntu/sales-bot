"""
Notifications Celery task — queue: notifications

Executed by worker_notifications (concurrency=4, see docker-compose.yml).

send_telegram_task is the Celery-wrapped version used for fire-and-forget
dispatches (e.g. manager payment links).

_send_telegram_async is the underlying coroutine shared with followup.py.
"""

import asyncio
import logging

from telegram import Bot

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


async def _send_telegram_async(chat_id: int, text: str) -> None:
    """Underlying async Telegram send — reused by followup task via asyncio.run()."""
    s = get_settings()
    bot = Bot(s.telegram_bot_token)
    async with bot:
        await bot.send_message(chat_id=chat_id, text=text)


@celery_app.task(name="notifications.send_telegram", queue="notifications", bind=True, max_retries=3)
def send_telegram_task(self, chat_id: int, text: str) -> None:
    """Celery task: send a Telegram message. Retries up to 3 times on failure."""
    try:
        asyncio.run(_send_telegram_async(chat_id, text))
    except Exception as exc:
        log.exception("send_telegram_task failed for chat_id=%s", chat_id)
        raise self.retry(exc=exc, countdown=30)
