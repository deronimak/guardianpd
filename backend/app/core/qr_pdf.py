"""Printed QR credential PDF generation — ARCHITECTURE.md §5.

Sized to a US standard business card (3.5" x 2") so it can be printed
directly onto business-card cardstock — small enough to carry in a wallet,
which is the point of a "printed credential." Prints the guardian's name,
the school's name, and the linked children's names alongside the QR code —
a deliberate product choice (children's names were originally left off so a
lost/dropped card wouldn't reveal which children a credential was tied to;
the school preferred the convenience of matching a credential to a child at
a glance instead). The guardian/child link is still fully enforced
server-side at scan time regardless of what's printed here.
"""

import io

import qrcode
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

CARD_WIDTH = 3.5 * inch
CARD_HEIGHT = 2 * inch
_MARGIN = 0.12 * inch


def _split_long_token(pdf: canvas.Canvas, token: str, font: str, size: float, max_width: float) -> list[str]:
    """A single space-separated token (e.g. a hyphenated surname) that's
    still too wide on its own — break at hyphens first, character-by-
    character as a last resort, so nothing can overflow the card.
    """
    if pdf.stringWidth(token, font, size) <= max_width:
        return [token]

    parts = token.split("-")
    if len(parts) > 1:
        pieces = [f"{p}-" for p in parts[:-1]] + [parts[-1]]
    else:
        pieces = list(token)

    lines: list[str] = []
    current = ""
    for piece in pieces:
        candidate = current + piece
        if pdf.stringWidth(candidate, font, size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = piece
    if current:
        lines.append(current)
    return lines


def _wrap_to_width(pdf: canvas.Canvas, text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word-wrap using actual glyph widths — a business card is too
    narrow for a fixed-character-count guess to reliably fit. Falls back to
    splitting a single overlong word (hyphens, then raw characters) so a
    long unbroken name can never run past the card edge.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if pdf.stringWidth(candidate, font, size) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        if pdf.stringWidth(word, font, size) <= max_width:
            current = word
        else:
            *full_lines, current = _split_long_token(pdf, word, font, size, max_width)
            lines.extend(full_lines)
    if current:
        lines.append(current)
    return lines


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
    pdf = canvas.Canvas(buffer, pagesize=(CARD_WIDTH, CARD_HEIGHT))

    qr_size = CARD_HEIGHT - 2 * _MARGIN
    qr_x = _MARGIN
    qr_y = _MARGIN
    pdf.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)

    text_x = qr_x + qr_size + 0.14 * inch
    text_width = CARD_WIDTH - _MARGIN - text_x
    y = CARD_HEIGHT - _MARGIN - 8

    pdf.setFillColor(colors.blue)
    pdf.setFont("Helvetica-Bold", 8)
    for line in _wrap_to_width(pdf, school_name, "Helvetica-Bold", 8, text_width):
        pdf.drawString(text_x, y, line)
        y -= 9

    pdf.setFillColor(colors.black)
    y -= 3
    pdf.setFont("Helvetica-Bold", 10)
    for line in _wrap_to_width(pdf, guardian_name, "Helvetica-Bold", 10, text_width):
        pdf.drawString(text_x, y, line)
        y -= 11

    if children_names:
        y -= 4
        pdf.setFont("Helvetica", 6.5)
        label = "Children: " + ", ".join(children_names)
        for line in _wrap_to_width(pdf, label, "Helvetica", 6.5, text_width)[:4]:
            pdf.drawString(text_x, y, line)
            y -= 7.5

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
