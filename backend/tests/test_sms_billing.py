"""SMS usage metering and billing: counted per school from the SMS records,
charged at a per-school rate, added to the invoice total and shown on the PDF."""

import datetime as dt
import io
import uuid

import pymupdf
from test_pupil_cards import _tenant_session

from app.core import sms
from app.core.config import settings
from app.core.invoice_pdf import generate_invoice_pdf
from app.core.sms_usage import sms_charge
from app.jobs.generate_invoices import generate_invoices_for_all_schools
from app.models.tenant import Guardian, Notification


def _guardian_id(client, admin_headers, enrolled_school):
    resp = client.post(
        "/guardians",
        json={
            "name": "Billing Parent",
            "email": f"bill-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": "Bill Kid One"}, {"name": "Bill Kid Two"}],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_notifications(enrolled_school, guardian_id, specs):
    """specs: list of (channel, days_ago)."""
    db = _tenant_session(enrolled_school)
    try:
        now = dt.datetime.now(dt.timezone.utc)
        for channel, days_ago in specs:
            db.add(Notification(guardian_id=guardian_id, channel=channel, sent_at=now - dt.timedelta(days=days_ago)))
        db.commit()
    finally:
        db.close()


def _set_subscription(client, platform_auth_headers, school_id, **fields):
    resp = client.patch(f"/platform/schools/{school_id}/subscription", json=fields, headers=platform_auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_sms_charge_rounds_half_up_to_whole_naira():
    assert sms_charge(3, 6.5) == 20  # 19.5 -> 20
    assert sms_charge(10, 7) == 70
    assert sms_charge(0, 8) == 0
    assert sms_charge(5, 0) == 0
    assert sms_charge(7, 4.25) == 30  # 29.75 -> 30


def test_only_a_real_send_counts_as_billable(monkeypatch):
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "")
    assert sms.send_sms("08148247438", "hi") is False  # dev mode: logged, not sent, not billed
    monkeypatch.setattr(
        sms, "send_sms_detailed", lambda n, m: {"ok": True, "sent": False, "detail": "skipped"}
    )
    assert sms.send_sms("08148247438", "hi") is False
    monkeypatch.setattr(sms, "send_sms_detailed", lambda n, m: {"ok": True, "sent": True})
    assert sms.send_sms("08148247438", "hi") is True


def test_manual_invoice_adds_the_sms_charge(
    client, platform_auth_headers, enrolled_school, school_admin_headers
):
    school_id = enrolled_school["school"]["id"]
    gid = _guardian_id(client, school_admin_headers, enrolled_school)
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
    sub = _set_subscription(
        client, platform_auth_headers, school_id, price_per_sms_naira=6.5, started_at=started.isoformat()
    )
    assert sub["price_per_sms_naira"] == 6.5

    # 3 SMS inside the period, 1 push (not billable), 1 SMS from before the period started.
    _add_notifications(enrolled_school, gid, [("sms", 1), ("sms", 1), ("sms", 2), ("push", 1), ("sms", 20)])

    detail = client.get(f"/platform/schools/{school_id}", headers=platform_auth_headers).json()
    assert detail["sms_count_this_period"] == 3 and detail["sms_amount_this_period"] == 20
    assert detail["price_per_sms_naira"] == 6.5

    resp = client.post(f"/platform/schools/{school_id}/invoices", headers=platform_auth_headers)
    assert resp.status_code == 200, resp.text
    invoice = resp.json()
    assert invoice["sms_count"] == 3 and invoice["sms_amount_naira"] == 20
    assert invoice["price_per_sms_naira"] == 6.5
    assert invoice["child_count"] == 2
    assert invoice["amount_naira"] == 2 * 500 + 20  # children + SMS

    # Correcting the child count keeps the SMS charge on the invoice.
    fixed = client.patch(
        f"/platform/invoices/{invoice['id']}", json={"child_count": 3}, headers=platform_auth_headers
    ).json()
    assert fixed["amount_naira"] == 3 * 500 + 20 and fixed["sms_amount_naira"] == 20


def test_periodic_job_bills_sms_for_the_finished_period(
    client, platform_auth_headers, enrolled_school, school_admin_headers
):
    school_id = enrolled_school["school"]["id"]
    gid = _guardian_id(client, school_admin_headers, enrolled_school)
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=40)
    _set_subscription(client, platform_auth_headers, school_id, price_per_sms_naira=10, started_at=started.isoformat())
    # Inside the first 30-day period (days 5..35 ago): 4 SMS; the latest 2 days are the NEXT period.
    _add_notifications(enrolled_school, gid, [("sms", 36), ("sms", 36), ("sms", 30), ("sms", 20), ("sms", 1)])

    generate_invoices_for_all_schools()

    invoices = [
        i for i in client.get("/platform/invoices", params={"status": "all"}, headers=platform_auth_headers).json()
        if i["school_id"] == school_id
    ]
    assert len(invoices) == 1
    inv = invoices[0]
    assert inv["sms_count"] == 4 and inv["sms_amount_naira"] == 40
    assert inv["amount_naira"] == inv["child_count"] * 500 + 40


def test_schools_without_a_sms_rate_are_not_charged(client, platform_auth_headers, enrolled_school, school_admin_headers):
    school_id = enrolled_school["school"]["id"]
    gid = _guardian_id(client, school_admin_headers, enrolled_school)
    started = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=3)
    _set_subscription(client, platform_auth_headers, school_id, started_at=started.isoformat())
    _add_notifications(enrolled_school, gid, [("sms", 1), ("sms", 1)])

    invoice = client.post(f"/platform/schools/{school_id}/invoices", headers=platform_auth_headers).json()
    assert invoice["sms_count"] == 2 and invoice["sms_amount_naira"] == 0  # usage is recorded, free
    assert invoice["amount_naira"] == invoice["child_count"] * 500


def test_invoice_pdf_shows_the_sms_line_and_the_total():
    pdf = generate_invoice_pdf(
        invoice_number="GPD-000001-202610",
        school_name="Test Academy",
        school_address=None,
        period_start=dt.date(2026, 10, 1),
        period_end=dt.date(2026, 10, 31),
        child_count=40,
        price_per_child_naira=500,
        amount_naira=20_000 + 1_950,
        due_date=dt.date(2026, 10, 31),
        checkout_url=None,
        sms_count=300,
        price_per_sms_naira=6.5,
        sms_amount_naira=1_950,
    )
    text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
    assert "SMS alerts to parents" in text and "300 SMS" in text and "6.5 NGN" in text
    assert "1,950 NGN" in text and "20,000 NGN" in text  # children line is the total minus SMS
    assert "21,950 NGN" in text  # amount due

    no_sms = pymupdf.open(
        stream=generate_invoice_pdf(
            invoice_number="GPD-000001-202610",
            school_name="Test Academy",
            school_address=None,
            period_start=dt.date(2026, 10, 1),
            period_end=dt.date(2026, 10, 31),
            child_count=40,
            price_per_child_naira=500,
            amount_naira=20_000,
            due_date=dt.date(2026, 10, 31),
            checkout_url=None,
        ),
        filetype="pdf",
    )[0].get_text()
    assert "SMS alerts to parents" not in no_sms
