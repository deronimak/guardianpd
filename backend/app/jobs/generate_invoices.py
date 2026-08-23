"""Per-child metered billing invoice generation (GuardianPD spec).

500 NGN per enrolled child, billed every 30 days. Meant to be invoked
periodically by an external scheduler (cron, Windows Task Scheduler, etc.
— see app/jobs/welfare_check.py for the same pattern), not run as an
in-process scheduler. Safe to run more than once a day: Invoice's unique
constraint on (school_id, period_start) makes generation idempotent, and
the overdue-marking pass just flips status on existing rows.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from app.core.email import send_email
from app.db.platform import SessionLocal as PlatformSessionLocal
from app.db.tenant import get_tenant_sessionmaker
from app.models.platform import Invoice, School, Subscription
from app.models.tenant import Student

logger = logging.getLogger(__name__)

PRICE_PER_CHILD_NAIRA = 500
BILLING_PERIOD_DAYS = 30
OVERDUE_GRACE_DAYS = 7


def _next_period_start(platform_db: Session, school: School, subscription: Subscription) -> dt.date:
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
            period_start = _next_period_start(platform_db, school, subscription)
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

            amount = child_count * PRICE_PER_CHILD_NAIRA
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
            created += 1

            if school.billing_email:
                send_email(
                    to_email=school.billing_email,
                    subject=f"Invoice for {school.name} — {amount} NGN due",
                    body=(
                        f"{school.name} had {child_count} enrolled child(ren) for the billing "
                        f"period {period_start} to {period_end}.\n\n"
                        f"Amount due: {amount} NGN (500 NGN per child).\n"
                        f"Due date: {period_end}.\n\n"
                        "Log in to the GuardianPD Master Admin console to pay via Paystack."
                    ),
                )
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
