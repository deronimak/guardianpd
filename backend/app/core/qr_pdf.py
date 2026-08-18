"""Printed QR credential PDF generation — ARCHITECTURE.md §5.

Deliberately renders only the guardian's name and the school's name
alongside the QR code — no children's names or photos. If a physical page
is lost or dropped, it should reveal only whose credential it is, not
which children it's tied to; that link is still fully enforced
server-side at scan time regardless of what's printed.
"""

import io

import qrcode
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def generate_qr_credential_pdf(guardian_name: str, school_name: str, qr_token: str) -> bytes:
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

    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        page_width / 2,
        qr_y - 1 * inch,
        "Present this code at drop-off and pick-up. Report a lost code to the school office immediately.",
    )

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
