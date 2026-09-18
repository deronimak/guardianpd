"""Printed QR credential PDF generation — ARCHITECTURE.md §5.

Sized to a US standard business card (3.5" x 2") so it can be printed
directly onto business-card cardstock/PVC — small enough to carry in a
wallet, which is the point of a "printed credential." Two pages: the front
(page 1) carries the school's branding, the guardian's name, their
children's names, and the QR code; the back (page 2) states plainly what
the card is for and how to use it, so it still reads as a credential and
not just an ad, plus a small GuardianPD mark. Print both pages onto one
card (duplex, or as two single-sided cards glued back-to-back) for a
double-sided PVC card.

Brand color matches the GuardianPD app icon/wordmark (mobile/lib/main.dart's
_brandPurple, 0xFF6A4FE0) rather than an arbitrary accent, so the printed
card and the app it comes from visibly match.
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

BRAND_PURPLE = colors.HexColor("#6A4FE0")
BRAND_INK = colors.HexColor("#241F3D")
BRAND_MUTED = colors.HexColor("#6B6483")


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


def _draw_image_fit(pdf: canvas.Canvas, image: ImageReader, x: float, y: float, max_w: float, max_h: float) -> None:
    """Draw `image` left-aligned within (x, y, max_w, max_h), preserving its
    aspect ratio and vertically centering it — a school's uploaded logo can
    be any shape, and stretching it to a fixed box would distort it.
    """
    iw, ih = image.getSize()
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    pdf.drawImage(image, x, y + (max_h - h) / 2, width=w, height=h, mask="auto")


def _draw_front(
    pdf: canvas.Canvas,
    guardian_name: str,
    school_name: str,
    qr_image: ImageReader,
    children_names: list[str] | None,
    school_logo: ImageReader | None,
) -> None:
    # Two purple-on-black diagonal corner accents (top-left, bottom-left),
    # matching the school's reference PVC card design — recolored from its
    # orange to the app's own brand purple. The top-left one is short enough
    # (triangle_h) that the header row is the only content indented past it;
    # every row below goes back to the card's own margin.
    triangle_w = 0.55 * inch
    triangle_h = 0.34 * inch
    corner = pdf.beginPath()
    corner.moveTo(0, CARD_HEIGHT)
    corner.lineTo(triangle_w, CARD_HEIGHT)
    corner.lineTo(0, CARD_HEIGHT - triangle_h)
    corner.close()
    pdf.setFillColor(BRAND_INK)
    pdf.drawPath(corner, fill=1, stroke=0)

    accent = pdf.beginPath()
    accent.moveTo(0, CARD_HEIGHT)
    accent.lineTo(triangle_w + 0.05 * inch, CARD_HEIGHT)
    accent.lineTo(0, CARD_HEIGHT - triangle_h - 0.05 * inch)
    accent.close()
    pdf.setFillColor(BRAND_PURPLE)
    pdf.drawPath(accent, fill=1, stroke=0)
    pdf.setFillColor(BRAND_INK)
    pdf.drawPath(corner, fill=1, stroke=0)

    bar_h = 0.11 * inch
    pdf.setFillColor(BRAND_PURPLE)
    pdf.rect(0, 0, CARD_WIDTH, bar_h, fill=1, stroke=0)
    footer_triangle = pdf.beginPath()
    footer_triangle.moveTo(0, 0)
    footer_triangle.lineTo(triangle_w, 0)
    footer_triangle.lineTo(0, triangle_h)
    footer_triangle.close()
    pdf.drawPath(footer_triangle, fill=1, stroke=0)

    # QR block, right-aligned and large — the part that actually gets
    # scanned should dominate the card, not compete with the text column.
    # Computed before the text column below so the column's width can
    # actually stop at the QR's left edge instead of the card's, which
    # otherwise lets text run under the (opaque, drawn-on-top) QR box.
    qr_size = 0.72 * CARD_HEIGHT
    qr_x = CARD_WIDTH - _MARGIN - qr_size
    qr_y = CARD_HEIGHT - _MARGIN - qr_size

    # Logo + school name, indented clear of the top-left corner accent.
    # Sized to one line of the school-name font (not the old two-line-tall
    # box) so the logo sits beside the name instead of looming over it.
    header_h = 0.20 * inch
    header_y = CARD_HEIGHT - _MARGIN - header_h
    logo_x = triangle_w + 0.06 * inch
    if school_logo is not None:
        _draw_image_fit(pdf, school_logo, logo_x, header_y, header_h, header_h)
        name_x = logo_x + header_h + 0.05 * inch
    else:
        name_x = logo_x

    # Shrink-to-fit rather than wrap to a second line — the school name
    # needs to stay on the same line as the logo. Only a name still too
    # long at the smallest size gets an ellipsis, so it fails gracefully
    # instead of cutting off mid-word with no indication anything's missing.
    name_width = qr_x - 0.1 * inch - name_x
    font_size = 8.5
    while font_size > 5.5 and pdf.stringWidth(school_name, "Helvetica-Bold", font_size) > name_width:
        font_size -= 0.5
    line = school_name
    if pdf.stringWidth(line, "Helvetica-Bold", font_size) > name_width:
        truncated = line
        while truncated and pdf.stringWidth(truncated + "…", "Helvetica-Bold", font_size) > name_width:
            truncated = truncated[:-1]
        line = truncated.rstrip() + "…" if truncated else "…"

    pdf.setFillColor(BRAND_INK)
    pdf.setFont("Helvetica-Bold", font_size)
    # Baseline centered on the logo's vertical middle, not the box's top.
    pdf.drawString(name_x, header_y + header_h / 2 - font_size * 0.35, line)

    pdf.setStrokeColor(BRAND_PURPLE)
    pdf.setLineWidth(1.2)
    pdf.roundRect(qr_x - 0.05 * inch, qr_y - 0.05 * inch, qr_size + 0.1 * inch, qr_size + 0.1 * inch, 4, stroke=1, fill=0)
    pdf.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size)

    pdf.setFillColor(BRAND_MUTED)
    pdf.setFont("Helvetica", 5.5)
    pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 0.135 * inch, "Powered by GuardianPD")

    # Guardian name + children, left column below the header row — clear of
    # the top-left accent (which ends at CARD_HEIGHT - triangle_h) by the
    # time this starts, so it's safe back at the card's own margin.
    text_x = _MARGIN
    text_width = qr_x - 0.16 * inch - text_x
    y = header_y - 0.16 * inch

    pdf.setFillColor(BRAND_PURPLE)
    pdf.setFont("Helvetica-Bold", 13)
    for line in _wrap_to_width(pdf, guardian_name, "Helvetica-Bold", 13, text_width)[:2]:
        pdf.drawString(text_x, y, line)
        y -= 14

    if children_names:
        y -= 6
        pdf.setFillColor(BRAND_INK)
        pdf.setFont("Helvetica-Bold", 7.5)
        pdf.drawString(text_x, y, "Children:")
        y -= 11
        pdf.setFont("Helvetica", 7.5)
        # Floor above the footer accent (bar + triangle), which the text
        # column shares horizontal space with, unlike the QR on the right.
        floor_y = triangle_h + 0.06 * inch
        for i, child in enumerate(children_names[:4], start=1):
            if y < floor_y:
                break
            label = f"Child {i}"
            pdf.setFont("Helvetica-Bold", 7.5)
            pdf.drawString(text_x, y, label)
            label_w = pdf.stringWidth(label, "Helvetica-Bold", 7.5)
            pdf.setFont("Helvetica", 7.5)
            name_col_x = text_x + max(label_w, 0.5 * inch) + 6
            for line in _wrap_to_width(pdf, f": {child}", "Helvetica", 7.5, text_width - (name_col_x - text_x))[:1]:
                if y < floor_y:
                    break
                pdf.drawString(name_col_x, y, line)
                y -= 10.5


def _draw_back(
    pdf: canvas.Canvas,
    school_name: str,
    children_names: list[str] | None,
) -> None:
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, CARD_WIDTH, CARD_HEIGHT, fill=1, stroke=0)
    pdf.setStrokeColor(BRAND_PURPLE)
    pdf.setLineWidth(1.4)
    pdf.roundRect(_MARGIN * 0.6, _MARGIN * 0.6, CARD_WIDTH - _MARGIN * 1.2, CARD_HEIGHT - _MARGIN * 1.2, 8, stroke=1, fill=0)

    text_width = CARD_WIDTH - _MARGIN * 2.4
    center_x = CARD_WIDTH / 2
    y = CARD_HEIGHT - 0.34 * inch

    who = ", ".join(children_names) if children_names else "the enrolled child"
    statement = f"This card verifies authorized pickup for {who} at {school_name}."
    pdf.setFillColor(BRAND_PURPLE)
    pdf.setFont("Helvetica-Bold", 8)
    for line in _wrap_to_width(pdf, statement, "Helvetica-Bold", 8, text_width)[:4]:
        pdf.drawCentredString(center_x, y, line)
        y -= 10

    y -= 7
    pdf.setFillColor(BRAND_INK)
    pdf.setFont("Helvetica", 8)
    instruction = "Present at the gate for scanning. If lost, report to the school office immediately."
    for line in _wrap_to_width(pdf, instruction, "Helvetica", 8, text_width)[:3]:
        pdf.drawCentredString(center_x, y, line)
        y -= 10

    y -= 10
    pdf.setFillColor(BRAND_MUTED)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawCentredString(center_x, y, "Contact GuardianPD:")
    y -= 10
    pdf.setFont("Helvetica", 7.5)
    for contact_line in ("www.guardianpd.app", "info@guardianpd.app", "08032459607"):
        pdf.drawCentredString(center_x, y, contact_line)
        y -= 9.5


def generate_qr_credential_pdf(
    guardian_name: str,
    school_name: str,
    qr_token: str,
    children_names: list[str] | None = None,
    school_logo_bytes: bytes | None = None,
) -> bytes:
    # qrcode.make() returns a qrcode.image.pil.PilImage wrapper, not a plain
    # PIL Image or file path — ReportLab's ImageReader needs one of the
    # latter, so round-trip it through a PNG buffer.
    qr_buffer = io.BytesIO()
    qrcode.make(qr_token).save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_image = ImageReader(qr_buffer)

    school_logo = ImageReader(io.BytesIO(school_logo_bytes)) if school_logo_bytes else None

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(CARD_WIDTH, CARD_HEIGHT))

    _draw_front(pdf, guardian_name, school_name, qr_image, children_names, school_logo)
    pdf.showPage()
    _draw_back(pdf, school_name, children_names)
    pdf.showPage()

    pdf.save()
    return buffer.getvalue()
