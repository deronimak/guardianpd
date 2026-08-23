import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


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
