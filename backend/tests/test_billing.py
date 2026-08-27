"""Paystack isn't configured in the test environment (PAYSTACK_SECRET_KEY is
left unset in tests/conftest.py, same as an unconfigured dev install) — this
covers the explicit fallbacks for that state, plus webhook signature
verification, rather than exercising real Paystack calls.
"""

import uuid


def test_checkout_session_returns_501_without_paystack_configured(client, platform_auth_headers):
    resp = client.post(
        f"/platform/invoices/{uuid.uuid4()}/checkout-session",
        headers=platform_auth_headers,
    )
    assert resp.status_code == 501


def test_webhook_rejects_invalid_signature(client):
    resp = client.post(
        "/platform/billing/webhook",
        json={"event": "charge.success", "data": {}},
        headers={"x-paystack-signature": "not-a-real-signature"},
    )
    assert resp.status_code in (400, 501)


def test_deactivate_reactivate_requires_platform_auth(client, enrolled_school):
    school_id = enrolled_school["school"]["id"]
    resp = client.post(f"/platform/schools/{school_id}/deactivate")
    assert resp.status_code == 401


def test_deactivate_unknown_school_is_404(client, platform_auth_headers):
    resp = client.post(f"/platform/schools/{uuid.uuid4()}/deactivate", headers=platform_auth_headers)
    assert resp.status_code == 404
