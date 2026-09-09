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


def test_create_guardian_succeeds_even_if_activation_email_fails(client, school_admin_headers, monkeypatch):
    """Regression test: production once returned a 500 here whenever
    Postmark hiccuped, even though the guardian/children had already been
    committed — see app/api/routes/guardians.py's _activation_email. The
    enrollment must still be reported as a success to the caller.
    """
    import app.api.routes.guardians as guardians_module

    def _boom(*args, **kwargs):
        raise RuntimeError("Postmark is down")

    monkeypatch.setattr(guardians_module, "send_email", _boom)

    resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["children"]) == 2

    # And the guardian really was persisted, not just "returned" without a commit.
    search_resp = client.get("/guardians", params={"query": "Gina"}, headers=school_admin_headers)
    assert "Gina Guardian" in [g["name"] for g in search_resp.json()]


def test_guardian_creation_requires_authentication(client, enrolled_school):
    resp = client.post(
        "/guardians",
        json=_guardian_payload(),
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert resp.status_code == 401


def test_search_guardians_includes_children(client, school_admin_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(name="Nora Naveen"), headers=school_admin_headers)
    assert create_resp.status_code == 201

    resp = client.get("/guardians", params={"query": "Nora"}, headers=school_admin_headers)
    assert resp.status_code == 200
    body = resp.json()[0]
    assert {c["name"] for c in body["children"]} == {"Charlie Child", "Chloe Child"}


def test_update_guardian_name_and_phone(client, school_admin_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    guardian_id = create_resp.json()["id"]

    resp = client.patch(
        f"/guardians/{guardian_id}",
        json={"name": "Gina Updated", "phone": "+15550001111"},
        headers=school_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Gina Updated"
    assert body["phone"] == "+15550001111"
    assert len(body["children"]) == 2


def test_update_guardian_email_conflict(client, school_admin_headers):
    email_a = f"guardian-a-{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"guardian-b-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/guardians", json=_guardian_payload(email=email_a, children=[]), headers=school_admin_headers)
    guardian_b = client.post(
        "/guardians", json=_guardian_payload(email=email_b, children=[]), headers=school_admin_headers
    ).json()

    resp = client.patch(
        f"/guardians/{guardian_b['id']}",
        json={"email": email_a},
        headers=school_admin_headers,
    )
    assert resp.status_code == 409


def test_update_guardian_not_found(client, school_admin_headers):
    resp = client.patch(
        f"/guardians/{uuid.uuid4()}",
        json={"name": "Nobody"},
        headers=school_admin_headers,
    )
    assert resp.status_code == 404


def test_delete_guardian(client, school_admin_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(name="Deletable Guardian"), headers=school_admin_headers)
    guardian_id = create_resp.json()["id"]

    resp = client.delete(f"/guardians/{guardian_id}", headers=school_admin_headers)
    assert resp.status_code == 204

    search_resp = client.get("/guardians", params={"query": "Deletable"}, headers=school_admin_headers)
    assert search_resp.json() == []

    pdf_resp = client.get(f"/guardians/{guardian_id}/qr-credential.pdf", headers=school_admin_headers)
    assert pdf_resp.status_code == 404


def test_delete_guardian_not_found(client, school_admin_headers):
    resp = client.delete(f"/guardians/{uuid.uuid4()}", headers=school_admin_headers)
    assert resp.status_code == 404


def test_school_staff_cannot_update_or_delete_guardians(client, school_admin_headers, school_staff_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    guardian_id = create_resp.json()["id"]

    update_resp = client.patch(f"/guardians/{guardian_id}", json={"name": "x"}, headers=school_staff_headers)
    assert update_resp.status_code == 403

    delete_resp = client.delete(f"/guardians/{guardian_id}", headers=school_staff_headers)
    assert delete_resp.status_code == 403


def test_guardian_attendance_history(client, school_admin_headers, school_staff_headers):
    create_resp = client.post(
        "/guardians",
        json={
            "name": "Hattie History",
            "email": f"hattie-{uuid.uuid4().hex[:10]}@example.com",
            "children": [{"name": "Hank History"}],
        },
        headers=school_admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    qr_token = body["qr_token"]
    guardian_id = body["id"]
    student_id = body["children"][0]["id"]

    scan_resp = client.post(
        "/attendance/scan",
        json={"token": qr_token, "student_id": student_id, "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert scan_resp.status_code == 200, scan_resp.text

    history_resp = client.get(f"/guardians/{guardian_id}/attendance", headers=school_admin_headers)
    assert history_resp.status_code == 200, history_resp.text
    events = history_resp.json()
    assert len(events) == 1
    assert events[0]["type"] == "drop_off"
    assert events[0]["student_name"] == "Hank History"
    assert events[0]["flagged"] is False


def test_guardian_attendance_history_unknown_guardian_is_404(client, school_admin_headers):
    resp = client.get(f"/guardians/{uuid.uuid4()}/attendance", headers=school_admin_headers)
    assert resp.status_code == 404


def test_school_staff_cannot_view_guardian_attendance_history(client, school_admin_headers, school_staff_headers):
    create_resp = client.post("/guardians", json=_guardian_payload(), headers=school_admin_headers)
    guardian_id = create_resp.json()["id"]

    resp = client.get(f"/guardians/{guardian_id}/attendance", headers=school_staff_headers)
    assert resp.status_code == 403


def test_guardian_attendance_history_date_range_filter(client, school_admin_headers, school_staff_headers):
    import datetime as dt

    create_resp = client.post(
        "/guardians",
        json={
            "name": "Rina Range",
            "email": f"rina-{uuid.uuid4().hex[:10]}@example.com",
            "children": [{"name": "Remi Range"}],
        },
        headers=school_admin_headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    qr_token = body["qr_token"]
    guardian_id = body["id"]
    student_id = body["children"][0]["id"]

    scan_resp = client.post(
        "/attendance/scan",
        json={"token": qr_token, "student_id": student_id, "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert scan_resp.status_code == 200, scan_resp.text

    today = dt.date.today()

    in_range = client.get(
        f"/guardians/{guardian_id}/attendance",
        params={"start_date": today.isoformat(), "end_date": today.isoformat()},
        headers=school_admin_headers,
    )
    assert in_range.status_code == 200, in_range.text
    assert len(in_range.json()) == 1

    out_of_range = client.get(
        f"/guardians/{guardian_id}/attendance",
        params={
            "start_date": (today - dt.timedelta(days=10)).isoformat(),
            "end_date": (today - dt.timedelta(days=1)).isoformat(),
        },
        headers=school_admin_headers,
    )
    assert out_of_range.status_code == 200, out_of_range.text
    assert out_of_range.json() == []
