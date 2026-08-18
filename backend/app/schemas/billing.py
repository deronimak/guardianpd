from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
