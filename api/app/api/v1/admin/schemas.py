from datetime import date

from pydantic import BaseModel, Field


# ── Discounts ─────────────────────────────────────────────────────────────────


class DiscountItem(BaseModel):
    membership_id: str = Field(
        ...,
        description="id из memberships, bundle_memberships или temporary_memberships (например gold, gold_3_9)",
    )
    discounted_price: int
    label: str


class UpdateDiscountsRequest(BaseModel):
    discounts: list[DiscountItem]


class UpdateDiscountsResponse(BaseModel):
    ok: bool
    date: str
    count: int


# ── Prices ────────────────────────────────────────────────────────────────────


class UpdatePriceRequest(BaseModel):
    membership_id: str
    new_price: int


class UpdatePriceResponse(BaseModel):
    ok: bool
    membership_id: str
    new_price: int


# ── Temporary memberships ─────────────────────────────────────────────────────


class TemporaryMembershipItem(BaseModel):
    id: str
    name: str
    base_price: int
    start_date: date
    end_date: date
    access: str | None = None
    includes: list[str] = Field(default_factory=list)
    label: str | None = None


class UpsertTemporaryMembershipsRequest(BaseModel):
    items: list[TemporaryMembershipItem]


class UpsertTemporaryMembershipsResponse(BaseModel):
    ok: bool
    count: int


# ── Stats ─────────────────────────────────────────────────────────────────────


class StatsResponse(BaseModel):
    users_total: int
    manager_handoffs: int  # пользователи, у которых зафиксирована передача менеджеру (manager_handoff_at)
    paid: int  # только PAID
    conversion: float  # manager_handoffs / users_total
    payment_rate: float  # paid / manager_handoffs при manager_handoffs > 0, иначе 0


# ── Admin self-debug (переписка с ботом из админского чата) ──────────────────


class AdminSelfChatBody(BaseModel):
    telegram_chat_id: int


class RefreshUserResponse(BaseModel):
    ok: bool
    deleted: bool  # были ли записи пользователя до удаления


class UserSnapshotResponse(BaseModel):
    telegram_chat_id: int
    exists: bool
    state: str | None = None
    name: str | None = None
    goal: str | None = None
    followup_count: int = 0
    message_count: int = 0


class FollowupNowResponse(BaseModel):
    sent: bool = False
    message_type: str | None = None  # 2h | 5h | 1d | 3d | 7d | 14d
    user_state: str | None = None  # когда нет pending задач или нет user
    user_missing: bool = False
