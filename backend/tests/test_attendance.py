"""Covers the security-critical scan flow (app/api/routes/attendance.py):
signature check -> revocation check -> per-child authorization check ->
write, plus the subscription gate that suspending a school enforces.
"""

import uuid


def _create_guardian(client, headers, child_name):
    resp = client.post(
        "/guardians",
        json={
            "name": f"Guardian {uuid.uuid4().hex[:6]}",
            "email": f"guardian-{uuid.uuid4().hex[:10]}@example.com",
            "children": [{"name": child_name}],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["qr_token"], body["children"][0]["id"]


def test_lookup_and_scan_drop_off_succeeds(client, school_admin_headers, school_staff_headers):
    qr_token, student_id = _create_guardian(client, school_admin_headers, "Kid Authorized")

    lookup = client.get("/guardians/lookup", params={"token": qr_token}, headers=school_staff_headers)
    assert lookup.status_code == 200
    assert any(s["id"] == student_id for s in lookup.json()["students"])

    scan = client.post(
        "/attendance/scan",
        json={"token": qr_token, "student_id": student_id, "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert scan.status_code == 200, scan.text
    body = scan.json()
    assert body["status"] == "recorded"
    assert body["flagged"] is False


def test_scan_rejects_invalid_token(client, school_staff_headers):
    resp = client.post(
        "/attendance/scan",
        json={"token": "not-a-real-token", "student_id": str(uuid.uuid4()), "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert resp.status_code == 400


def test_scan_flags_guardian_not_authorized_for_student(client, school_admin_headers, school_staff_headers):
    qr_token_a, _ = _create_guardian(client, school_admin_headers, "Kid A")
    _, student_id_b = _create_guardian(client, school_admin_headers, "Kid B")

    # Guardian A's token, but the student belongs to Guardian B.
    resp = client.post(
        "/attendance/scan",
        json={"token": qr_token_a, "student_id": student_id_b, "type": "pick_up"},
        headers=school_staff_headers,
    )
    assert resp.status_code == 403


def test_suspended_subscription_blocks_scanning(
    client, platform_auth_headers, school_admin_headers, school_staff_headers, enrolled_school
):
    qr_token, student_id = _create_guardian(client, school_admin_headers, "Kid Suspended")
    school_id = enrolled_school["school"]["id"]

    deactivate = client.post(f"/platform/schools/{school_id}/deactivate", headers=platform_auth_headers)
    assert deactivate.status_code == 200

    scan = client.post(
        "/attendance/scan",
        json={"token": qr_token, "student_id": student_id, "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert scan.status_code == 402

    reactivate = client.post(f"/platform/schools/{school_id}/reactivate", headers=platform_auth_headers)
    assert reactivate.status_code == 200

    scan_again = client.post(
        "/attendance/scan",
        json={"token": qr_token, "student_id": student_id, "type": "drop_off"},
        headers=school_staff_headers,
    )
    assert scan_again.status_code == 200
