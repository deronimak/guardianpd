"""Composing and sending the "invoice created" notification.

Shared by the manual "create invoice now" endpoint
(app/api/routes/billing.py) and the periodic generation job
(app/jobs/generate_invoices.py) so both paths send the exact same
PDF-attached email rather than maintaining two versions. Every invoice now
gets a checkout link attempt regardless of which path created it — the PDF
a school receives should always carry a working "pay now" link.
"""

import logging

from fastapi import HTTPException

from app.core.email import send_email
from app.core.invoice_pdf import generate_invoice_pdf
from app.core.paystack import create_paystack_checkout
from app.models.platform import Invoice, School, Subscription

logger = logging.getLogger(__name__)


def invoice_number(school: School, invoice: Invoice) -> str:
    return f"GPD-{school.sequence_no:06d}-{invoice.period_start:%Y%m}"


def send_invoice_created_email(invoice: Invoice, school: School, subscription: Subscription) -> str | None:
    """Returns the checkout URL if one was created, else None."""
    if not school.billing_email:
        return None

    checkout_url: str | None = None
    try:
        checkout_url = create_paystack_checkout(invoice, school)
    except HTTPException as exc:
        logger.warning("no checkout link for invoice %s: %s", invoice.id, exc.detail)

    number = invoice_number(school, invoice)
    pdf_bytes = generate_invoice_pdf(
        invoice_number=number,
        school_name=school.name,
        school_address=school.address,
        period_start=invoice.period_start,
        period_end=invoice.period_end,
        child_count=invoice.child_count,
        price_per_child_naira=subscription.price_per_child_naira,
        amount_naira=invoice.amount_naira,
        due_date=invoice.due_date,
        checkout_url=checkout_url,
    )

    send_email(
        to_email=school.billing_email,
        subject=f"GuardianPD invoice {number} — {invoice.amount_naira:,} NGN due {invoice.due_date:%b %d, %Y}",
        body=(
            f"Hi,\n\n"
            f"Attached is invoice {number} for {school.name}: {invoice.child_count} enrolled "
            f"child(ren) for the billing period {invoice.period_start:%b %d, %Y} to "
            f"{invoice.period_end:%b %d, %Y}.\n\n"
            f"Amount due: {invoice.amount_naira:,} NGN ({subscription.price_per_child_naira:,} NGN per child).\n"
            f"Due date: {invoice.due_date:%b %d, %Y}.\n\n"
            + (f"Pay now: {checkout_url}\n\n" if checkout_url else "")
            + "The invoice PDF is attached to this email.\n\n"
            "— GuardianPD"
        ),
        attachments=[(f"{number}.pdf", pdf_bytes, "application/pdf")],
    )
    return checkout_url
