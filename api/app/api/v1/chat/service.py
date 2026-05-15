"""
ChatService — orchestrates a single chat turn.

Responsibilities:
  1. Rate-limit by telegram_chat_id
  2. Get or create User
  3. Persist user message + update last_message_at
  4. Load dialog history
  5. Load club context from Redis cache
  6. Call AI (with tenacity retries + fallback baked into AIClient)
  7. Persist assistant reply + update user state / name / goal
  8. Reschedule follow-up tasks, apply_async + persist celery_task_id (same txn)
  9. Commit all DB changes once
  10. Return ChatOut
"""

from __future__ import annotations

from datetime import timezone

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent_identity import pick_agent_name
from app.ai.client import AIClient
from app.ai.prompt_builder import build_system_prompt
from app.api.v1.chat.schemas import ChatOut
from app.cache.club_context import load_club_context_async
from app.core.config import get_settings
from app.core.rate_limit import rate_limit_chat
from app.domain.conversations.models import MessageRole
from app.domain.conversations.repo import ConversationsRepo
from app.domain.followup.repo import FollowUpRepo
from app.domain.followup.service import FollowUpService
from app.domain.users.models import UserState, utcnow
from app.domain.users.repo import UsersRepo
from app.domain.users.service import UsersService


class ChatService:
    def __init__(
        self,
        db: AsyncSession,
        redis: aioredis.Redis,
        ai: AIClient,
    ) -> None:
        self._db = db
        self._redis = redis
        self._ai = ai

        self._users_repo = UsersRepo(db)
        self._conv_repo = ConversationsRepo(db)
        self._followup_repo = FollowUpRepo(db)

        self._users_svc = UsersService(self._users_repo)
        self._followup_svc = FollowUpService(self._followup_repo)

    async def handle(self, telegram_chat_id: int, message_text: str) -> ChatOut:
        # 1. Rate-limit before any DB work
        await rate_limit_chat(telegram_chat_id, self._redis)

        # 2. Upsert user
        user = await self._users_svc.get_or_create(telegram_chat_id)
        agent_nm = pick_agent_name(user.id)
        if (user.name or "").strip().casefold() == agent_nm.casefold():
            user.name = None

        # 3. Store inbound message and stamp last_message_at
        await self._conv_repo.add_message(user.id, MessageRole.user, message_text)
        self._users_svc.touch(user)

        # 4. Build dialog history for AI context
        settings = get_settings()
        history = await self._conv_repo.last_messages(user.id, settings.max_dialog_messages)
        dialog = [{"role": m.role.value, "content": m.content} for m in history]

        # 5. Club context — from Redis cache (5 min TTL)
        club = await load_club_context_async(self._redis)

        # 6. AI call — retries + fallback handled inside AIClient
        result = await self._ai.generate(build_system_prompt(user, club), dialog, user.state)

        # 7. Persist reply + update user profile
        cn = (result.client_name or "").strip()
        if cn and cn.casefold() != agent_nm.casefold():
            user.name = cn
        if result.client_goal:
            user.goal = result.client_goal

        prev_state = user.state          # capture before overwrite
        user.state = result.next_state

        # When transitioning into CLOSE, always override the AI reply with the
        # guaranteed template — the LLM tends to add forbidden questions (name,
        # payment method, etc.) regardless of prompt instructions.
        reply_text = result.reply
        if user.state == UserState.CLOSE and prev_state != UserState.CLOSE:
            product = result.agreed_product or "абонемент"
            reply_text = (
                f"Отлично, оформляем {product}! 🔥 "
                f"Сейчас подключится менеджер и всё оформит — пару минут ⚡"
            )
            if user.manager_handoff_at is None:
                user.manager_handoff_at = utcnow()

        await self._conv_repo.add_message(user.id, MessageRole.assistant, reply_text)

        # 8. Reschedule follow-up chain
        tasks = await self._followup_svc.reschedule(user)

        # 9. Queue Celery ETA tasks and persist broker task id on each row (must be in one txn)
        await self._dispatch_and_record_celery_ids(tasks)

        # 10. Commit user + messages + follow_up_tasks (including celery_task_id)
        await self._db.commit()

        # Notify manager only on the transition INTO CLOSE, not on every message while in CLOSE
        actions = []
        if user.state == UserState.CLOSE and prev_state != UserState.CLOSE:
            actions.append("notify_manager")
            self._notify_manager(user)

        return ChatOut(reply_text=reply_text, state=user.state.value, actions=actions)

    @staticmethod
    def _notify_manager(user) -> None:
        """Fire-and-forget: send a Telegram DM to the manager when a client is ready to buy."""
        settings = get_settings()
        if not settings.manager_chat_id:
            return

        name = user.name or "—"
        goal = user.goal or "—"
        text = (
            f"🔥 Клиент готов купить!\n\n"
            f"Имя: {name}\n"
            f"Цель: {goal}\n"
            f"Telegram chat_id: {user.telegram_chat_id}\n\n"
            f"Напиши ему или отправь ссылку на оплату через /send_payment_link"
        )

        from app.tasks.notifications import send_telegram_task  # local import

        send_telegram_task.apply_async(
            args=[settings.manager_chat_id, text],
            queue="notifications",
        )

    async def _dispatch_and_record_celery_ids(self, tasks: list) -> None:
        """Apply_async + store result.id so cancel_pending can celery_app.control.revoke()."""
        from app.tasks.followup import send_followup  # local import avoids circular at startup

        for task in tasks:
            eta = task.scheduled_at
            if eta.tzinfo is None:
                eta = eta.replace(tzinfo=timezone.utc)
            result = send_followup.apply_async(args=[str(task.id)], eta=eta, queue="followup")
            task.celery_task_id = result.id
