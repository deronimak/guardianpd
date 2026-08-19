"""Paystack billing — ARCHITECTURE.md §4.

Code-complete but requires your own Paystack account: set
PAYSTACK_SECRET_KEY and PAYSTACK_PLAN_CODE in .env. Until those are set,
checkout-session creation returns a clear 501 rather than a fake URL —
unlike email/push, there's no meaningful stand-in for "here's where to pay."

Paystack's flow differs from Stripe in two ways that shape this file:
- There's no per-request "client reference" field on the checkout call the
  way Stripe's checkout.session has one — Paystack's /transaction/initialize
  accepts arbitrary `metadata`, which is echoed back on the webhook event,
  so that's what carries the school_id through instead.
- Webhooks are verified with the *same* secret key (HMAC-SHA512 of the raw
  body, compared against the `x-paystack-signature` header) rather than a
  separate signing secret — so there's no PAYSTACK_WEBHOOK_SECRET setting.

To test the webhook locally against a real Paystack account, use their
CLI/ngrok to forward events to this endpoint and register that URL in the
Paystack dashboard (webhooks are configured account-wide there, not
per-session) — that's a separate setup step you'd do yourself.
"""

import hashlib
import hmac
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.config import settings
from app.db.platform import get_platform_db
from app.models.platform import School, Subscription
from app.schemas.billing import CheckoutSessionResponse, SubscriptionStatusUpdate

router = APIRouter(prefix="/platform", tags=["billing"])

PAYSTACK_API_BASE = "https://api.paystack.co"


@router.patch(
    "/schools/{school_id}/subscription",
    dependencies=[Depends(require_platform_staff)],
)
def set_subscription_status(
    school_id: uuid.UUID,
    payload: SubscriptionStatusUpdate,
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Manual override, mirroring what the Paystack webhook would otherwise
    do (ARCHITECTURE.md §4) — needed since Paystack isn't wired up for every
    school yet, and it's what the ops console uses to unblock a school
    without a real payment.
    """
    subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this school")

    subscription.status = payload.status
    platform_db.commit()
    return {"status": "updated", "subscription_status": subscription.status}


@router.post(
    "/schools/{school_id}/billing/checkout-session",
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(require_platform_staff)],
)
def create_checkout_session(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    if not settings.paystack_secret_key or not settings.paystack_plan_code:
        raise HTTPException(
            status_code=501,
            detail="Paystack is not configured (PAYSTACK_SECRET_KEY / PAYSTACK_PLAN_CODE unset)",
        )

    school = platform_db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")
    if not school.billing_email:
        raise HTTPException(status_code=409, detail="This school has no billing email on file")

    response = httpx.post(
        f"{PAYSTACK_API_BASE}/transaction/initialize",
        headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
        json={
            "email": school.billing_email,
            "plan": settings.paystack_plan_code,
            "callback_url": settings.paystack_callback_url,
            # Echoed back on every webhook event for this transaction/
            # subscription — how we correlate the payment back to a school,
            # since Paystack has no client-reference-id-style field.
            "metadata": {"school_id": str(school.id)},
        },
        timeout=10,
    )
    body = response.json()
    if not body.get("status"):
        raise HTTPException(status_code=502, detail=f"Paystack error: {body.get('message', 'unknown error')}")

    return {"checkout_url": body["data"]["authorization_url"]}


@router.post("/billing/webhook")
async def paystack_webhook(request: Request, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Not gated by require_platform_staff — Paystack calls this directly,
    and authenticity is verified via the webhook signature instead.
    """
    if not settings.paystack_secret_key:
        raise HTTPException(status_code=501, detail="Paystack secret key not configured")

    payload = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    expected_signature = hmac.new(settings.paystack_secret_key.encode(), payload, hashlib.sha512).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="Invalid Paystack webhook signature")

    event = (await request.json())
    event_type = event.get("event")
    data = event.get("data") or {}
    customer_code = (data.get("customer") or {}).get("customer_code")

    if event_type == "charge.success":
        school_id = (data.get("metadata") or {}).get("school_id")
        if school_id:
            subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
            if subscription is not None:
                subscription.status = "active"
                if customer_code:
                    subscription.billing_provider_customer_id = customer_code
                platform_db.commit()

    elif event_type == "invoice.payment_failed" and customer_code:
        subscription = (
            platform_db.query(Subscription).filter_by(billing_provider_customer_id=customer_code).first()
        )
        if subscription is not None:
            subscription.status = "past_due"
            platform_db.commit()

    elif event_type == "subscription.disable" and customer_code:
        subscription = (
            platform_db.query(Subscription).filter_by(billing_provider_customer_id=customer_code).first()
        )
        if subscription is not None:
            subscription.status = "canceled"
            platform_db.commit()

    return {"status": "ok"}
