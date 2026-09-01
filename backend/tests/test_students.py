"""Covers School-Admin-scoped child record edit/delete — the same cascade
shape as the Master Admin's equivalent routes, but reachable with a staff
JWT for one school (see app/api/routes/students.py).
"""

import uuid


def _create_guardian_with_child(client, headers, child_name="Test Child"):
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
    return resp.json()["children"][0]["id"]


def test_update_student(client, school_admin_headers):
    student_id = _create_guardian_with_child(client, school_admin_headers)

    resp = client.patch(
        f"/students/{student_id}",
        json={"grade": "3rd", "dob": "2016-05-01"},
        headers=school_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["grade"] == "3rd"
    assert body["dob"] == "2016-05-01"


def test_update_student_not_found(client, school_admin_headers):
    resp = client.patch(f"/students/{uuid.uuid4()}", json={"grade": "1st"}, headers=school_admin_headers)
    assert resp.status_code == 404


def test_delete_student(client, school_admin_headers):
    student_id = _create_guardian_with_child(client, school_admin_headers, child_name="Removable Child")

    resp = client.delete(f"/students/{student_id}", headers=school_admin_headers)
    assert resp.status_code == 204

    resp_again = client.delete(f"/students/{student_id}", headers=school_admin_headers)
    assert resp_again.status_code == 404


def test_delete_student_also_removes_guardian_link(client, school_admin_headers):
    """Deleting a child shouldn't error out the guardian's own record —
    the guardian search should still work and simply show fewer children.
    """
    create_resp = client.post(
        "/guardians",
        json={
            "name": "Multi Child Guardian",
            "email": f"multi-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": "Kid One"}, {"name": "Kid Two"}],
        },
        headers=school_admin_headers,
    )
    children = create_resp.json()["children"]
    student_to_delete = children[0]["id"]

    delete_resp = client.delete(f"/students/{student_to_delete}", headers=school_admin_headers)
    assert delete_resp.status_code == 204

    search_resp = client.get("/guardians", params={"query": "Multi Child"}, headers=school_admin_headers)
    remaining = search_resp.json()[0]["children"]
    assert len(remaining) == 1
    assert remaining[0]["id"] != student_to_delete


def test_school_staff_cannot_update_or_delete_students(client, school_admin_headers, school_staff_headers):
    student_id = _create_guardian_with_child(client, school_admin_headers)

    update_resp = client.patch(f"/students/{student_id}", json={"grade": "2nd"}, headers=school_staff_headers)
    assert update_resp.status_code == 403

    delete_resp = client.delete(f"/students/{student_id}", headers=school_staff_headers)
    assert delete_resp.status_code == 403
