"""
Admin controller — thin HTTP layer.

All business logic lives in AdminService.
Authentication is enforced via the require_admin dependency.
"""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.schemas import (
    AdminSelfChatBody,
    FollowupNowResponse,
    RefreshUserResponse,
    StatsResponse,
    UpdateDiscountsRequest,
    UpdateDiscountsResponse,
    UpdatePriceRequest,
    UpdatePriceResponse,
    UpsertTemporaryMembershipsRequest,
    UpsertTemporaryMembershipsResponse,
    UserSnapshotResponse,
)
from app.api.v1.admin.service import AdminService
from app.core.config import get_settings
from app.core.dependencies import get_db, get_redis_pool
from app.core.exceptions import ForbiddenError

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth dependency ───────────────────────────────────────────────────────────


def require_admin(x_admin_secret: str = Header(..., alias="X-Admin-Secret")) -> None:
    if x_admin_secret != get_settings().admin_secret:
        raise ForbiddenError()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("/discounts", response_model=UpdateDiscountsResponse, dependencies=[Depends(require_admin)])
async def update_discounts(
    body: UpdateDiscountsRequest,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> UpdateDiscountsResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).update_discounts(
        body.discounts
    )


@router.get("/discounts", dependencies=[Depends(require_admin)])
async def get_discounts(
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).get_discounts()


@router.post("/prices", response_model=UpdatePriceResponse, dependencies=[Depends(require_admin)])
async def update_price(
    body: UpdatePriceRequest,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> UpdatePriceResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).update_price(
        body.membership_id, body.new_price
    )


@router.post(
    "/temporary-memberships",
    response_model=UpsertTemporaryMembershipsResponse,
    dependencies=[Depends(require_admin)],
)
async def upsert_temporary_memberships(
    body: UpsertTemporaryMembershipsRequest,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> UpsertTemporaryMembershipsResponse:
    return await AdminService(
        redis=redis, db=db, yaml_path=get_settings().club_info_path
    ).upsert_temporary_memberships(body.items)


@router.get("/temporary-memberships", dependencies=[Depends(require_admin)])
async def get_temporary_memberships(
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return AdminService(
        redis=redis, db=db, yaml_path=get_settings().club_info_path
    ).get_temporary_memberships()


@router.get("/membership-catalog", dependencies=[Depends(require_admin)])
async def membership_catalog(
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return AdminService(
        redis=redis, db=db, yaml_path=get_settings().club_info_path
    ).get_membership_catalog()


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(require_admin)])
async def stats(
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).get_stats()


@router.post(
    "/refresh-user",
    response_model=RefreshUserResponse,
    dependencies=[Depends(require_admin)],
)
async def refresh_user(
    body: AdminSelfChatBody,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> RefreshUserResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).refresh_my_user_record(
        body.telegram_chat_id
    )


@router.get(
    "/user-state",
    response_model=UserSnapshotResponse,
    dependencies=[Depends(require_admin)],
)
async def user_state(
    telegram_chat_id: int,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> UserSnapshotResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).snapshot_my_user(
        telegram_chat_id
    )


@router.post(
    "/followup-now",
    response_model=FollowupNowResponse,
    dependencies=[Depends(require_admin)],
)
async def followup_now(
    body: AdminSelfChatBody,
    redis: aioredis.Redis = Depends(get_redis_pool),
    db: AsyncSession = Depends(get_db),
) -> FollowupNowResponse:
    return await AdminService(redis=redis, db=db, yaml_path=get_settings().club_info_path).followup_now(
        body.telegram_chat_id
    )
