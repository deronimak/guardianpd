"""Paystack API calls.

Split out from app/api/routes/billing.py so app/jobs/generate_invoices.py
(and app/core/invoicing.py) can create a checkout session for an invoice
without a job module reaching into a route module — jobs/core should not
import from api.
"""

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.models.platform import Invoice, School

PAYSTACK_API_BASE = "https://api.paystack.co"


def create_paystack_checkout(invoice: Invoice, school: School) -> str:
    """One-off /transaction/initialize call for this invoice's exact
    amount — see app/api/routes/billing.py's module docstring for why
    there's no Paystack "Plan" involved.
    """
    if not settings.paystack_secret_key:
        raise HTTPException(status_code=501, detail="Paystack is not configured (PAYSTACK_SECRET_KEY unset)")
    if not school.billing_email:
        raise HTTPException(status_code=409, detail="This school has no billing email on file")

    response = httpx.post(
        f"{PAYSTACK_API_BASE}/transaction/initialize",
        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
        json={
            "email": school.billing_email,
            "amount": invoice.amount_naira * 100,  # kobo
            "callback_url": settings.paystack_callback_url,
            # Echoed back on the webhook event — how we correlate the
            # payment back to a specific invoice.
            "metadata": {"invoice_id": str(invoice.id)},
        },
        timeout=10,
    )
    body = response.json()
    if not body.get("status"):
        raise HTTPException(status_code=502, detail=f"Paystack error: {body.get('message', 'unknown error')}")

    return body["data"]["authorization_url"]
