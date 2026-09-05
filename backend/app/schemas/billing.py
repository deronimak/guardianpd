import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class SubscriptionUpdateRequest(BaseModel):
    """PATCH /platform/schools/{id}/subscription — the "Manage subscription"
    panel. All fields optional/partial, same exclude_unset pattern as
    SchoolUpdateRequest.
    """

    status: str | None = None
    price_per_child_naira: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in ("active", "trial", "suspended"):
            raise ValueError("status must be one of: active, trial, suspended")
        return value

    @field_validator("price_per_child_naira")
    @classmethod
    def _validate_price(cls, value: int | None) -> int | None:
        if value is not None and value % 500 != 0:
            raise ValueError("price_per_child_naira must be a multiple of 500")
        return value


class SubscriptionOut(BaseModel):
    school_id: uuid.UUID
    status: str
    price_per_child_naira: int
    started_at: datetime


class InvoiceUpdateRequest(BaseModel):
    """PATCH /platform/invoices/{id} — correcting a mistake (wrong child
    count, wrong due date) on an invoice that hasn't been paid yet. If
    `child_count` is set without `amount_naira`, the amount is recomputed
    from the school's current price-per-child rather than left stale.
    """

    child_count: int | None = Field(default=None, ge=0)
    amount_naira: int | None = Field(default=None, ge=0)
    due_date: date | None = None


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    school_name: str
    period_start: date
    period_end: date
    child_count: int
    amount_naira: int
    status: str
    due_date: date
    paid_at: datetime | None
    created_at: datetime


class ManualInvoiceOut(InvoiceOut):
    """Response for POST /platform/schools/{id}/invoices — same shape as
    InvoiceOut plus the Paystack checkout link, when one could be created
    (Paystack configured + school has a billing email), so the dashboard
    can show it immediately without a second request.
    """

    checkout_url: str | None = None
