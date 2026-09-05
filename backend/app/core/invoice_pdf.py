"""Per-child metered billing invoice PDF generation.

Companion to app/core/qr_pdf.py's QR-credential PDF — same reportlab
approach (plain canvas drawing, no template engine), used by
app/core/invoicing.py to attach a PDF to the "invoice created" email sent
to a school's billing contact.
"""

import datetime as dt
import os

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

_BRAND_PURPLE = HexColor("#6A4FE0")
_TEXT = HexColor("#1A1A2E")
_MUTED = HexColor("#6B7280")
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "guardianpd_wordmark.png")


def generate_invoice_pdf(
    *,
    invoice_number: str,
    school_name: str,
    school_address: str | None,
    period_start: dt.date,
    period_end: dt.date,
    child_count: int,
    price_per_child_naira: int,
    amount_naira: int,
    due_date: dt.date,
    checkout_url: str | None,
) -> bytes:
    import io

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    page_width, page_height = LETTER
    margin = 0.75 * inch

    # Logo (wordmark, ~6.14:1 aspect ratio) top-left.
    logo = ImageReader(_LOGO_PATH)
    logo_width = 1.9 * inch
    logo_height = logo_width * (381 / 2340)
    top = page_height - margin
    pdf.drawImage(
        logo, margin, top - logo_height, width=logo_width, height=logo_height, mask="auto"
    )

    # "INVOICE" + number, right-aligned at the same height as the logo.
    pdf.setFont("Helvetica-Bold", 20)
    pdf.setFillColor(_TEXT)
    pdf.drawRightString(page_width - margin, top - 0.22 * inch, "INVOICE")
    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(_MUTED)
    pdf.drawRightString(page_width - margin, top - 0.45 * inch, invoice_number)

    y = top - logo_height - 0.55 * inch
    pdf.setStrokeColor(HexColor("#E5E7EB"))
    pdf.line(margin, y, page_width - margin, y)
    y -= 0.35 * inch

    # Bill to / invoice meta, two columns.
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(_MUTED)
    pdf.drawString(margin, y, "BILL TO")
    pdf.drawRightString(page_width - margin, y, "BILLING PERIOD")
    y -= 0.2 * inch

    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(_TEXT)
    pdf.drawString(margin, y, school_name)
    pdf.setFont("Helvetica", 11)
    pdf.drawRightString(page_width - margin, y, f"{period_start:%b %d, %Y} – {period_end:%b %d, %Y}")
    y -= 0.22 * inch

    if school_address:
        pdf.setFont("Helvetica", 10)
        pdf.setFillColor(_MUTED)
        pdf.drawString(margin, y, school_address)
        y -= 0.22 * inch

    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(_MUTED)
    pdf.drawRightString(page_width - margin, y, f"Due {due_date:%b %d, %Y}")
    y -= 0.5 * inch

    # Line-item table: header row, one row, total.
    col_desc_x = margin
    col_qty_x = page_width - margin - 2.6 * inch
    col_rate_x = page_width - margin - 1.6 * inch
    col_amount_x = page_width - margin

    pdf.setFillColor(_BRAND_PURPLE)
    pdf.rect(margin, y - 0.06 * inch, page_width - 2 * margin, 0.32 * inch, fill=1, stroke=0)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.drawString(col_desc_x + 0.1 * inch, y + 0.04 * inch, "DESCRIPTION")
    pdf.drawCentredString(col_qty_x, y + 0.04 * inch, "CHILDREN")
    pdf.drawCentredString(col_rate_x, y + 0.04 * inch, "RATE")
    pdf.drawRightString(col_amount_x - 0.1 * inch, y + 0.04 * inch, "AMOUNT")
    y -= 0.45 * inch

    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(_TEXT)
    pdf.drawString(col_desc_x + 0.1 * inch, y, "Per-child attendance billing")
    pdf.drawCentredString(col_qty_x, y, str(child_count))
    pdf.drawCentredString(col_rate_x, y, f"{price_per_child_naira:,} NGN")
    pdf.drawRightString(col_amount_x - 0.1 * inch, y, f"{amount_naira:,} NGN")
    y -= 0.3 * inch

    pdf.setStrokeColor(HexColor("#E5E7EB"))
    pdf.line(margin, y, page_width - margin, y)
    y -= 0.4 * inch

    pdf.setFont("Helvetica-Bold", 13)
    pdf.setFillColor(_TEXT)
    pdf.drawRightString(col_rate_x, y, "Amount due")
    pdf.setFillColor(_BRAND_PURPLE)
    pdf.drawRightString(col_amount_x - 0.1 * inch, y, f"{amount_naira:,} NGN")
    y -= 0.6 * inch

    if checkout_url:
        button_height = 0.42 * inch
        button_width = 2.2 * inch
        button_x = margin
        pdf.setFillColor(_BRAND_PURPLE)
        pdf.roundRect(button_x, y - button_height, button_width, button_height, 6, fill=1, stroke=0)
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.drawCentredString(button_x + button_width / 2, y - button_height + 0.14 * inch, "Pay now")
        pdf.linkURL(checkout_url, (button_x, y - button_height, button_x + button_width, y), relative=0)
        y -= button_height + 0.2 * inch

        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(_MUTED)
        pdf.drawString(margin, y, checkout_url)
        pdf.linkURL(
            checkout_url,
            (margin, y - 0.05 * inch, margin + pdf.stringWidth(checkout_url, "Helvetica", 8), y + 0.1 * inch),
            relative=0,
        )
        y -= 0.35 * inch
    else:
        pdf.setFont("Helvetica", 10)
        pdf.setFillColor(_MUTED)
        pdf.drawString(margin, y, "Contact GuardianPD to arrange payment for this invoice.")
        y -= 0.35 * inch

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(_MUTED)
    pdf.drawString(
        margin, margin, f"GuardianPD — invoice {invoice_number}, generated {dt.date.today():%b %d, %Y}."
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
