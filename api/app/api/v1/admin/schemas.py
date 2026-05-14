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
    paid: int
    conversion: float
