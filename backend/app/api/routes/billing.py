"""Stripe billing — ARCHITECTURE.md §4.

Code-complete but requires your own Stripe account: set STRIPE_SECRET_KEY,
STRIPE_WEBHOOK_SECRET, and STRIPE_PRICE_ID in .env. Until those are set,
checkout-session creation returns a clear 501 rather than a fake URL —
unlike email/push, there's no meaningful stand-in for "here's where to pay."

To test the webhook locally against a real Stripe account, use the Stripe
CLI (`stripe listen --forward-to localhost:8000/platform/billing/webhook`)
— that's a separate tool you'd install yourself, not something set up here.
"""

import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.config import settings
from app.db.platform import get_platform_db
from app.models.platform import School, Subscription
from app.schemas.billing import CheckoutSessionResponse, SubscriptionStatusUpdate

router = APIRouter(prefix="/platform", tags=["billing"])


@router.patch(
    "/schools/{school_id}/subscription",
    dependencies=[Depends(require_platform_staff)],
)
def set_subscription_status(
    school_id: uuid.UUID,
    payload: SubscriptionStatusUpdate,
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Manual override, mirroring what the Stripe webhook would otherwise do
    (ARCHITECTURE.md §4) — needed since Stripe isn't wired up for every
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
    if not settings.stripe_secret_key or not settings.stripe_price_id:
        raise HTTPException(
            status_code=501,
            detail="Stripe is not configured (STRIPE_SECRET_KEY / STRIPE_PRICE_ID unset)",
        )

    school = platform_db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")

    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=settings.stripe_success_url,
        cancel_url=settings.stripe_cancel_url,
        client_reference_id=str(school.id),
    )
    return {"checkout_url": session.url}


@router.post("/billing/webhook")
async def stripe_webhook(request: Request, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Not gated by require_platform_staff — Stripe calls this directly, and
    authenticity is verified via the webhook signature instead.
    """
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=501, detail="Stripe webhook secret not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature")

    data = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        school_id = data.get("client_reference_id")
        subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
        if subscription is not None:
            subscription.status = "active"
            subscription.billing_provider_customer_id = data.get("customer")
            platform_db.commit()

    elif event["type"] == "invoice.payment_failed":
        subscription = (
            platform_db.query(Subscription).filter_by(billing_provider_customer_id=data.get("customer")).first()
        )
        if subscription is not None:
            subscription.status = "past_due"
            platform_db.commit()

    elif event["type"] == "customer.subscription.deleted":
        subscription = (
            platform_db.query(Subscription).filter_by(billing_provider_customer_id=data.get("customer")).first()
        )
        if subscription is not None:
            subscription.status = "canceled"
            platform_db.commit()

    return {"status": "ok"}
