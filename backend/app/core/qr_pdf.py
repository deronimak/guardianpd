"""Printed QR credential PDF generation — ARCHITECTURE.md §5.

Prints the guardian's name, the school's name, and the linked children's
names alongside the QR code — a deliberate product choice (children's names
were originally left off so a lost/dropped page wouldn't reveal which
children a credential was tied to; the school preferred the convenience of
matching a credential to a child at a glance instead). The guardian/child
link is still fully enforced server-side at scan time regardless of what's
printed here.
"""

import io

import qrcode
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def generate_qr_credential_pdf(
    guardian_name: str,
    school_name: str,
    qr_token: str,
    children_names: list[str] | None = None,
) -> bytes:
    # qrcode.make() returns a qrcode.image.pil.PilImage wrapper, not a plain
    # PIL Image or file path — ReportLab's ImageReader needs one of the
    # latter, so round-trip it through a PNG buffer.
    qr_buffer = io.BytesIO()
    qrcode.make(qr_token).save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_image = ImageReader(qr_buffer)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=LETTER)
    page_width, page_height = LETTER

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawCentredString(page_width / 2, page_height - 1.5 * inch, school_name)

    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(page_width / 2, page_height - 2 * inch, "Attendance QR Credential")

    qr_size = 3 * inch
    qr_x = (page_width - qr_size) / 2
    qr_y = page_height - 5.5 * inch
    pdf.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(page_width / 2, qr_y - 0.5 * inch, guardian_name)

    next_y = qr_y - 0.85 * inch
    if children_names:
        pdf.setFont("Helvetica", 12)
        pdf.drawCentredString(page_width / 2, next_y, "Children: " + ", ".join(children_names))
        next_y -= 0.4 * inch

    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        page_width / 2,
        next_y - 0.15 * inch,
        "Present this code at drop-off and pick-up. Report a lost code to the school office immediately.",
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
