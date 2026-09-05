"""Per-child metered billing invoice generation (GuardianPD spec).

500 NGN per enrolled child by default (Master Admin can override this per
school via PATCH /platform/schools/{id}/subscription — see
Subscription.price_per_child_naira, app/models/platform.py), billed every
30 days. Meant to be invoked periodically by an external scheduler (cron,
Windows Task Scheduler, etc. — see app/jobs/welfare_check.py for the same
pattern) or the in-process scheduler (app/core/scheduler.py). Safe to run
more than once a day: Invoice's unique constraint on (school_id,
period_start) makes generation idempotent, and the overdue-marking pass
just flips status on existing rows.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from app.core.invoicing import send_invoice_created_email
from app.db.platform import SessionLocal as PlatformSessionLocal
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import Invoice, School, Subscription
from app.models.tenant import Student

logger = logging.getLogger(__name__)

BILLING_PERIOD_DAYS = 30
OVERDUE_GRACE_DAYS = 7


def next_period_start(platform_db: Session, school: School, subscription: Subscription) -> dt.date:
    """Also used by the manual "create invoice now" endpoint
    (app/api/routes/billing.py) so a manually-triggered invoice lands on
    the exact same period the periodic job would have generated next,
    rather than diverging from this job's own idempotency bookkeeping.
    """
    latest = (
        platform_db.query(Invoice)
        .filter_by(school_id=school.id)
        .order_by(Invoice.period_end.desc())
        .first()
    )
    if latest is not None:
        return latest.period_end
    return subscription.started_at.date()


def generate_invoices_for_all_schools(now: dt.datetime | None = None) -> int:
    """Returns the number of invoices created."""
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    created = 0

    platform_db = PlatformSessionLocal()
    try:
        schools = (
            platform_db.query(School)
            .join(Subscription, Subscription.school_id == School.id)
            .filter(Subscription.status == "active")
            .all()
        )
        for school in schools:
            subscription = platform_db.query(Subscription).filter_by(school_id=school.id).first()
            period_start = next_period_start(platform_db, school, subscription)
            period_end = period_start + dt.timedelta(days=BILLING_PERIOD_DAYS)
            if today < period_end:
                continue  # this billing cycle hasn't finished yet

            existing = (
                platform_db.query(Invoice)
                .filter_by(school_id=school.id, period_start=period_start)
                .first()
            )
            if existing is not None:
                continue  # already generated — idempotency guard

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
            created += 1

            send_invoice_created_email(invoice, school, subscription)
            logger.info("%s: generated invoice for %d child(ren) (%d NGN)", school.slug, child_count, amount)
    finally:
        platform_db.close()

    return created


def mark_overdue_invoices(now: dt.datetime | None = None) -> int:
    """Returns the number of invoices newly marked overdue."""
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    cutoff = today - dt.timedelta(days=OVERDUE_GRACE_DAYS)

    platform_db = PlatformSessionLocal()
    try:
        overdue = (
            platform_db.query(Invoice)
            .filter(Invoice.status == "pending", Invoice.due_date < cutoff)
            .all()
        )
        for invoice in overdue:
            invoice.status = "overdue"
        if overdue:
            platform_db.commit()
        return len(overdue)
    finally:
        platform_db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generated = generate_invoices_for_all_schools()
    overdue_count = mark_overdue_invoices()
    print(f"Generated {generated} invoice(s); marked {overdue_count} overdue.")
