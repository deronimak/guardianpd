"""Covers the combined guardian+children enrollment (two-phase commit across
platform + tenant DBs) and the admin/staff permission split — see
app/api/routes/guardians.py and app/api/deps.py's require_school_admin.
"""

import uuid


def _guardian_payload(**overrides):
    payload = {
        "name": "Gina Guardian",
        "email": f"gina-{uuid.uuid4().hex[:10]}@example.com",
        "phone": "+15559876543",
        "children": [{"name": "Charlie Child"}, {"name": "Chloe Child"}],
    }
    payload.update(overrides)
    return payload


def test_create_guardian_with_children(client, school_admin_headers):
    resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Gina Guardian"
    assert body["qr_token"]
    assert len(body["children"]) == 2
    assert {c["name"] for c in body["children"]} == {"Charlie Child", "Chloe Child"}


def test_create_guardian_rejects_more_than_ten_children(client, school_admin_headers):
    payload = _guardian_payload(children=[{"name": f"Child {i}"} for i in range(11)])
    resp = client.post("/guardians", json=payload, headers=school_admin_headers)
    assert resp.status_code == 422


def test_school_staff_cannot_create_guardians(client, school_staff_headers):
    resp = client.post("/guardians", json=_guardian_payload(), headers=school_staff_headers)
    assert resp.status_code == 403


def test_school_staff_cannot_search_guardians(client, school_staff_headers):
    resp = client.get("/guardians", headers=school_staff_headers)
    assert resp.status_code == 403


def test_search_guardians_by_name(client, school_admin_headers):
    client.post("/guardians", json=_guardian_payload(name="Zoe Zealous"), headers=school_admin_headers)

    resp = client.get("/guardians", params={"query": "Zoe"}, headers=school_admin_headers)
    assert resp.status_code == 200
    names = [g["name"] for g in resp.json()]
    assert "Zoe Zealous" in names


def test_resend_activation_for_unactivated_guardian(client, school_admin_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    guardian_id = create_resp.json()["id"]

    resp = client.post(f"/guardians/{guardian_id}/resend-activation", headers=school_admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


def test_guardian_creation_requires_authentication(client, enrolled_school):
    resp = client.post(
        "/guardians",
        json=_guardian_payload(),
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert resp.status_code == 401
