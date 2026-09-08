"""Covers app/core/qr_pdf.py — the printed QR credential, sized to a US
business card so it can be printed directly onto cardstock.
"""

from app.core.qr_pdf import CARD_HEIGHT, CARD_WIDTH, generate_qr_credential_pdf


def test_pdf_page_size_is_a_business_card():
    pdf_bytes = generate_qr_credential_pdf(
        guardian_name="Gina Guardian",
        school_name="Kiddie Quest",
        qr_token="token-abc123",
    )
    assert CARD_WIDTH == 3.5 * 72  # 3.5 inches, in points
    assert CARD_HEIGHT == 2 * 72  # 2 inches, in points
    assert f"/MediaBox [ 0 0 {CARD_WIDTH:g} {CARD_HEIGHT:g} ]".encode() in pdf_bytes


def test_hyphenated_name_does_not_error_and_produces_a_pdf():
    # Regression: a long unbroken word (e.g. a hyphenated surname) with no
    # spaces used to overflow past the card's right edge because wrapping
    # only broke on whitespace.
    pdf_bytes = generate_qr_credential_pdf(
        guardian_name="Amara Chukwuemeka-Obiora",
        school_name="Kiddie Quest International Academy",
        qr_token="token-abc123",
        children_names=["Chidinma Obiora", "Kelechi Obiora", "Ngozi Obiora"],
    )
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 0
