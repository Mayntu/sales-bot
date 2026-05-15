"""
AdminService — manages club YAML data and invalidates Redis cache on writes.

All file I/O is synchronous (the YAML file is small, edited rarely).
Cache invalidation is async (Redis call).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import redis.asyncio as aioredis
import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.schemas import (
    DiscountItem,
    FollowupNowResponse,
    RefreshUserResponse,
    StatsResponse,
    TemporaryMembershipItem,
    UpdateDiscountsResponse,
    UpdatePriceResponse,
    UpsertTemporaryMembershipsResponse,
    UserSnapshotResponse,
)
from app.cache.club_context import invalidate_club_cache_async
from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.conversations.models import Message
from app.domain.followup.async_dispatch import dispatch_follow_up_now
from app.domain.followup.repo import FollowUpRepo
from app.domain.users.models import User, UserState
from app.domain.users.repo import UsersRepo


class AdminService:
    def __init__(self, redis: aioredis.Redis, db: AsyncSession, yaml_path: str) -> None:
        self._redis = redis
        self._db = db
        self._path = Path(yaml_path)

    # ── YAML helpers ─────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    async def _invalidate(self) -> None:
        await invalidate_club_cache_async(self._redis)

    # ── Discounts ─────────────────────────────────────────────────────────────

    async def update_discounts(self, discounts: list[DiscountItem]) -> UpdateDiscountsResponse:
        data = self._load()
        data["daily_discounts"] = {
            "date": date.today().isoformat(),
            "discounts": [d.model_dump() for d in discounts],
        }
        self._save(data)
        await self._invalidate()
        return UpdateDiscountsResponse(
            ok=True,
            date=date.today().isoformat(),
            count=len(discounts),
        )

    def get_discounts(self) -> dict:
        data = self._load()
        return data.get("daily_discounts", {"date": None, "discounts": []})

    # ── Prices ────────────────────────────────────────────────────────────────

    async def update_price(self, membership_id: str, new_price: int) -> UpdatePriceResponse:
        data = self._load()
        updated = False
        for section in ("memberships", "bundle_memberships", "temporary_memberships"):
            for m in data.get(section, []):
                if m.get("id") == membership_id:
                    m["base_price"] = new_price
                    updated = True
        if not updated:
            raise NotFoundError(f"membership_id '{membership_id}' not found")
        self._save(data)
        await self._invalidate()
        return UpdatePriceResponse(ok=True, membership_id=membership_id, new_price=new_price)

    # ── Temporary memberships ─────────────────────────────────────────────────

    async def upsert_temporary_memberships(
        self, items: list[TemporaryMembershipItem]
    ) -> UpsertTemporaryMembershipsResponse:
        data = self._load()
        data["temporary_memberships"] = [x.model_dump(mode="json") for x in items]
        self._save(data)
        await self._invalidate()
        return UpsertTemporaryMembershipsResponse(ok=True, count=len(items))

    def get_temporary_memberships(self) -> dict:
        data = self._load()
        return {"items": data.get("temporary_memberships", [])}

    def get_membership_catalog(self) -> dict:
        """Справочник карт из yaml — для админ-UI (шаблоны временных абонементов и т.п.)."""
        data = self._load()

        def pack(m: dict) -> dict:
            return {
                "id": m.get("id"),
                "name": m.get("name"),
                "base_price": m.get("base_price"),
                "access": m.get("access"),
                "includes": m.get("includes") or [],
            }

        return {
            "memberships": [pack(m) for m in data.get("memberships", []) if m.get("id")],
            "bundle_memberships": [pack(m) for m in data.get("bundle_memberships", []) if m.get("id")],
            "temporary_memberships": [pack(m) for m in data.get("temporary_memberships", []) if m.get("id")],
        }

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def get_stats(self) -> StatsResponse:
        total = int(
            (await self._db.execute(select(func.count()).select_from(User))).scalar() or 0
        )
        paid = int(
            (
                await self._db.execute(
                    select(func.count()).select_from(User).where(User.state == UserState.PAID)
                )
            ).scalar()
            or 0
        )
        handoffs = int(
            (
                await self._db.execute(
                    select(func.count()).select_from(User).where(User.manager_handoff_at.isnot(None))
                )
            ).scalar()
            or 0
        )
        conv = round((handoffs / total) if total else 0, 4)
        pay_rate = round((paid / handoffs) if handoffs else 0, 4)
        return StatsResponse(
            users_total=total,
            manager_handoffs=handoffs,
            paid=paid,
            conversion=conv,
            payment_rate=pay_rate,
        )

    def _require_admin_allowlisted_chat(self, telegram_chat_id: int) -> None:
        admins = get_settings().get_admin_chat_ids()
        if not admins:
            raise ForbiddenError(
                "Set ADMIN_CHAT_IDS (or ADMIN_TELEGRAM_CHAT_IDS) on the API for admin self-chat ops (/refresh-user, /user-state, /followup-now)"
            )
        if telegram_chat_id not in admins:
            raise ForbiddenError("telegram_chat_id is not allowed for this operation")

    async def refresh_my_user_record(self, telegram_chat_id: int) -> RefreshUserResponse:
        """Удалить пользователя по chat_id (только себя как админ) — следующее сообщение создаёт новую сессию."""
        self._require_admin_allowlisted_chat(telegram_chat_id)
        user = await UsersRepo(self._db).get_by_chat_id(telegram_chat_id)
        if not user:
            return RefreshUserResponse(ok=True, deleted=False)
        await FollowUpRepo(self._db).cancel_pending(user.id)
        await self._db.execute(delete(User).where(User.id == user.id))
        await self._db.commit()
        return RefreshUserResponse(ok=True, deleted=True)

    async def snapshot_my_user(self, telegram_chat_id: int) -> UserSnapshotResponse:
        self._require_admin_allowlisted_chat(telegram_chat_id)
        user = await UsersRepo(self._db).get_by_chat_id(telegram_chat_id)
        if not user:
            return UserSnapshotResponse(telegram_chat_id=telegram_chat_id, exists=False, message_count=0)
        n = (
            await self._db.execute(
                select(func.count()).select_from(Message).where(Message.user_id == user.id)
            )
        ).scalar() or 0
        return UserSnapshotResponse(
            telegram_chat_id=telegram_chat_id,
            exists=True,
            state=user.state.value,
            name=user.name,
            goal=user.goal,
            followup_count=user.followup_count or 0,
            message_count=int(n),
        )

    async def followup_now(self, telegram_chat_id: int) -> FollowupNowResponse:
        """Отправить ближайшую pending follow-up задачу сразу (демо инвесторам)."""
        self._require_admin_allowlisted_chat(telegram_chat_id)
        user = await UsersRepo(self._db).get_by_chat_id(telegram_chat_id)
        if not user:
            return FollowupNowResponse(user_missing=True)

        fu = FollowUpRepo(self._db)
        task = await fu.get_next_pending_ordered(user.id)
        if not task:
            return FollowupNowResponse(user_state=user.state.value)

        await fu.revoke_celery_for_task(task)
        await dispatch_follow_up_now(
            self._db,
            self._redis,
            task,
            user,
            force_ignore_baseline=True,
        )
        await self._db.commit()
        return FollowupNowResponse(sent=True, message_type=task.message_type.value)
