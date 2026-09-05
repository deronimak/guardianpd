"""Paystack billing — per-child metered invoices (GuardianPD spec).

Code-complete but requires your own Paystack account: set
PAYSTACK_SECRET_KEY in .env. Until it's set, checkout-session creation
returns a clear 501 rather than a fake URL — unlike email/push, there's no
meaningful stand-in for "here's where to pay."

Unlike the old flat-plan approach, there is no Paystack "Plan" here at all:
each Invoice has its own amount (child_count * Subscription.price_per_child_naira,
500 NGN by default but overridable per school — see
app/jobs/generate_invoices.py and update_subscription below), so every
checkout is a one-off transaction (/transaction/initialize) for that
invoice's exact amount rather than a subscription to a fixed-price Plan.
Paystack amounts are in the smallest currency unit (kobo for NGN), hence
the *100 conversion below.

Webhooks are verified with the *same* secret key (HMAC-SHA512 of the raw
body, compared against the `x-paystack-signature` header) rather than a
separate signing secret — so there's no PAYSTACK_WEBHOOK_SECRET setting.
Paying an invoice does NOT automatically reactivate a suspended school —
see Subscription's docstring in app/models/platform.py — that's a
deliberate Master Admin action via the deactivate/reactivate endpoints
below (the Manage Subscription page).
"""

import datetime as dt
import hashlib
import hmac
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_platform_staff
from app.core.config import settings
from app.core.invoicing import send_invoice_created_email
from app.core.paystack import create_paystack_checkout
from app.db.platform import get_platform_db
from app.db.tenant import get_tenant_sessionmaker
from app.jobs.generate_invoices import next_period_start
from app.models.platform import Invoice, School, Subscription
from app.models.tenant import Student
from app.schemas.billing import (
    CheckoutSessionResponse,
    InvoiceOut,
    InvoiceUpdateRequest,
    ManualInvoiceOut,
    SubscriptionUpdateRequest,
)

router = APIRouter(prefix="/platform", tags=["billing"])


def _invoice_out(invoice: Invoice, school_name: str) -> dict:
    return {
        "id": invoice.id,
        "school_id": invoice.school_id,
        "school_name": school_name,
        "period_start": invoice.period_start,
        "period_end": invoice.period_end,
        "child_count": invoice.child_count,
        "amount_naira": invoice.amount_naira,
        "status": invoice.status,
        "due_date": invoice.due_date,
        "paid_at": invoice.paid_at,
        "created_at": invoice.created_at,
    }


@router.get(
    "/invoices",
    response_model=list[InvoiceOut],
    dependencies=[Depends(require_platform_staff)],
)
def list_invoices(
    status: str = "unpaid",
    school_id: uuid.UUID | None = None,
    platform_db: Session = Depends(get_platform_db),
) -> list[dict]:
    """`status` is one of:
    - "upcoming": pending invoices not yet due (Billing page)
    - "unpaid": pending or overdue invoices already past their due date (Manage Subscription page)
    - "overdue": invoices the generate_invoices job has flagged overdue specifically
    - "all": every invoice, most recent first

    `school_id` optionally restricts to one school's invoices (the School
    Detail page's billing history), on top of whichever `status` filter
    applies.
    """
    today = dt.date.today()
    q = platform_db.query(Invoice)
    if school_id is not None:
        q = q.filter(Invoice.school_id == school_id)
    if status == "upcoming":
        q = q.filter(Invoice.status == "pending", Invoice.due_date >= today)
    elif status == "unpaid":
        q = q.filter(Invoice.status.in_(("pending", "overdue")), Invoice.due_date < today)
    elif status == "overdue":
        q = q.filter(Invoice.status == "overdue")
    elif status != "all":
        raise HTTPException(status_code=400, detail="status must be one of: upcoming, unpaid, overdue, all")

    invoices = q.order_by(Invoice.due_date.asc()).all()
    schools_by_id = {school.id: school.name for school in platform_db.query(School).all()}
    return [_invoice_out(invoice, schools_by_id.get(invoice.school_id, "Unknown school")) for invoice in invoices]


def _get_invoice_or_404(invoice_id: uuid.UUID, platform_db: Session) -> Invoice:
    invoice = platform_db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Unknown invoice")
    return invoice


def _reject_if_paid(invoice: Invoice, action: str) -> None:
    if invoice.status == "paid":
        raise HTTPException(status_code=409, detail=f"Cannot {action} an invoice that's already been paid")


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceOut,
    dependencies=[Depends(require_platform_staff)],
)
def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdateRequest,
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Correct a mistake on an invoice that hasn't been paid yet — wrong
    child count, wrong due date, or a manual amount override. Blocked once
    an invoice is paid, same as everything else here: a paid invoice is a
    financial record, not something to quietly rewrite after the fact.
    """
    invoice = _get_invoice_or_404(invoice_id, platform_db)
    _reject_if_paid(invoice, "edit")

    updates = payload.model_dump(exclude_unset=True)
    if "child_count" in updates and "amount_naira" not in updates:
        subscription = platform_db.query(Subscription).filter_by(school_id=invoice.school_id).first()
        rate = subscription.price_per_child_naira if subscription else 500
        updates["amount_naira"] = updates["child_count"] * rate

    for field, value in updates.items():
        setattr(invoice, field, value)
    platform_db.commit()
    platform_db.refresh(invoice)

    school = platform_db.get(School, invoice.school_id)
    return _invoice_out(invoice, school.name if school else "Unknown school")


@router.post(
    "/invoices/{invoice_id}/cancel",
    response_model=InvoiceOut,
    dependencies=[Depends(require_platform_staff)],
)
def cancel_invoice(invoice_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Voids an invoice without deleting its record — e.g. the school was
    invoiced by mistake, or is being handled another way. Distinct from
    delete (below), which removes the row entirely.
    """
    invoice = _get_invoice_or_404(invoice_id, platform_db)
    _reject_if_paid(invoice, "cancel")

    invoice.status = "cancelled"
    platform_db.commit()
    platform_db.refresh(invoice)

    school = platform_db.get(School, invoice.school_id)
    return _invoice_out(invoice, school.name if school else "Unknown school")


@router.delete(
    "/invoices/{invoice_id}",
    status_code=204,
    dependencies=[Depends(require_platform_staff)],
)
def delete_invoice(invoice_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> Response:
    """Hard delete — for a duplicate or clearly-wrong invoice. A paid
    invoice can't be deleted (use accounting adjustments/refunds outside
    this system instead) since that would destroy a financial record;
    cancel (above) is the reversible alternative for anything else.
    """
    invoice = _get_invoice_or_404(invoice_id, platform_db)
    _reject_if_paid(invoice, "delete")

    platform_db.delete(invoice)
    platform_db.commit()
    return Response(status_code=204)


@router.post(
    "/schools/{school_id}/deactivate",
    dependencies=[Depends(require_platform_staff)],
)
def deactivate_school(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    """Manage Subscription page: suspends QR scanning/issuance for this
    school (enforced by require_active_subscription, app/api/deps.py).
    """
    subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this school")
    subscription.status = "suspended"
    platform_db.commit()
    return {"status": "updated", "subscription_status": subscription.status}


@router.post(
    "/schools/{school_id}/reactivate",
    dependencies=[Depends(require_platform_staff)],
)
def reactivate_school(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this school")
    subscription.status = "active"
    platform_db.commit()
    return {"status": "updated", "subscription_status": subscription.status}


@router.post(
    "/invoices/{invoice_id}/checkout-session",
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(require_platform_staff)],
)
def create_checkout_session(invoice_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    invoice = platform_db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Unknown invoice")

    school = platform_db.get(School, invoice.school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")

    return {"checkout_url": create_paystack_checkout(invoice, school)}


@router.patch(
    "/schools/{school_id}/subscription",
    dependencies=[Depends(require_platform_staff)],
)
def update_subscription(
    school_id: uuid.UUID,
    payload: SubscriptionUpdateRequest,
    platform_db: Session = Depends(get_platform_db),
) -> dict:
    """Backs the School Detail page's "Manage subscription" panel — status
    (incl. the Trial option), the per-child price override, and the
    billing-anchor date, all in one partial update. The simpler
    Deactivate/Reactivate buttons (above) keep using their own endpoints
    for the common suspend/restore action; this is the fuller control.
    """
    subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this school")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subscription, field, value)
    platform_db.commit()
    platform_db.refresh(subscription)

    return {
        "status": "updated",
        "subscription_status": subscription.status,
        "price_per_child_naira": subscription.price_per_child_naira,
        "started_at": subscription.started_at,
    }


@router.post(
    "/schools/{school_id}/invoices",
    response_model=ManualInvoiceOut,
    dependencies=[Depends(require_platform_staff)],
)
def create_manual_invoice(school_id: uuid.UUID, platform_db: Session = Depends(get_platform_db)) -> dict:
    """"Create and send Invoice" — generates the *next* invoice for this
    school right now instead of waiting for the periodic job
    (app/jobs/generate_invoices.py), using the exact same period
    computation (next_period_start) so it can't diverge from or duplicate
    what that job would have generated. Emails a PDF invoice with a
    Paystack checkout link to the school's billing contact via
    app/core/invoicing.py — the same helper the periodic job uses.
    """
    school = platform_db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="Unknown school")

    subscription = platform_db.query(Subscription).filter_by(school_id=school_id).first()
    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this school")

    period_start = next_period_start(platform_db, school, subscription)
    period_end = period_start + dt.timedelta(days=30)

    existing = platform_db.query(Invoice).filter_by(school_id=school_id, period_start=period_start).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An invoice for the current billing period already exists")

    tenant_db = get_tenant_sessionmaker(school.tenant_db_name)()
    try:
        child_count = tenant_db.query(Student).count()
    finally:
        tenant_db.close()

    amount = child_count * subscription.price_per_child_naira
    invoice = Invoice(
        school_id=school.id,
        period_start=period_start,
        period_end=period_end,
        child_count=child_count,
        amount_naira=amount,
        status="pending",
        due_date=period_end,
    )
    platform_db.add(invoice)
    platform_db.commit()
    platform_db.refresh(invoice)

    checkout_url = send_invoice_created_email(invoice, school, subscription)

    return {**_invoice_out(invoice, school.name), "checkout_url": checkout_url}


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

    event = await request.json()
    if event.get("event") == "charge.success":
        data = event.get("data") or {}
        invoice_id = (data.get("metadata") or {}).get("invoice_id")
        if invoice_id:
            invoice = platform_db.get(Invoice, uuid.UUID(invoice_id))
            if invoice is not None and invoice.status != "paid":
                invoice.status = "paid"
                invoice.paid_at = dt.datetime.now(dt.timezone.utc)
                invoice.paystack_reference = data.get("reference")
                platform_db.commit()

    return {"status": "ok"}
