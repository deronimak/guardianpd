from typing import Literal

from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class SubscriptionStatusUpdate(BaseModel):
    status: Literal["trialing", "active", "past_due", "canceled"]
