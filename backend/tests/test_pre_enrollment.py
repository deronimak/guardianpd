VALID_PAYLOAD = {
    "school_name": "Fieldstone Academy",
    "school_address": "12 School Rd, Lagos",
    "contact_name": "Jordan Blake",
    "contact_email": "jordan@fieldstone.example",
    "contact_whatsapp": "08011122233",
    "active_parents_estimate": "300",
    "desired_enrollment_date": "2026-10-15",
}


def test_submit_pre_enrollment_inquiry_succeeds_without_auth(client):
    """Deliberately no Authorization header — a prospective school has no
    account yet, so this must be reachable anonymously."""
    resp = client.post("/pre-enrollment-inquiries", json=VALID_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    assert body["created_at"]
    assert body["school_name"] == "Fieldstone Academy"
    assert body["contact_email"] == "jordan@fieldstone.example"
    assert body["notes"] is None


def test_submit_pre_enrollment_inquiry_with_optional_notes(client):
    payload = {**VALID_PAYLOAD, "notes": "Currently using a paper sign-out sheet."}
    resp = client.post("/pre-enrollment-inquiries", json=payload)
    assert resp.status_code == 201
    assert resp.json()["notes"] == "Currently using a paper sign-out sheet."


def test_submit_pre_enrollment_inquiry_rejects_missing_field(client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "contact_email"}
    resp = client.post("/pre-enrollment-inquiries", json=payload)
    assert resp.status_code == 422


def test_submit_pre_enrollment_inquiry_rejects_invalid_email(client):
    payload = {**VALID_PAYLOAD, "contact_email": "not-an-email"}
    resp = client.post("/pre-enrollment-inquiries", json=payload)
    assert resp.status_code == 422
