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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.schemas import (
    DiscountItem,
    StatsResponse,
    TemporaryMembershipItem,
    UpdateDiscountsResponse,
    UpdatePriceResponse,
    UpsertTemporaryMembershipsResponse,
)
from app.cache.club_context import invalidate_club_cache_async
from app.core.exceptions import NotFoundError
from app.domain.users.models import User, UserState


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
        return StatsResponse(
            users_total=total,
            paid=paid,
            conversion=round((paid / total) if total else 0, 4),
        )
