"""Covers the atomic two-phase-commit enrollment path (School + Subscription
in the platform DB, first StaffUser in a brand-new tenant DB) — see
app/api/routes/schools.py's enroll_school.
"""

import uuid


def test_enroll_creates_school_and_working_admin_login(client, platform_auth_headers, drop_tenant_db):
    slug = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "name": "Riverside Primary",
        "slug": slug,
        "address": "12 River Rd",
        "phone": "+15551234567",
        "admin_name": "Pat Principal",
        "admin_email": f"admin-{slug}@example.com",
        "admin_temp_password": "temp-password-1",
        "timezone": "Africa/Lagos",
    }
    resp = client.post("/platform/schools", json=payload, headers=platform_auth_headers)
    assert resp.status_code == 201, resp.text
    school = resp.json()
    assert school["name"] == "Riverside Primary"
    assert school["slug"] == slug
    assert isinstance(school["sequence_no"], int)

    # The StaffUser created inside the same atomic transaction can actually
    # log in — proving the tenant-DB half of the two-phase commit landed.
    login = client.post(
        "/auth/staff/login",
        json={"email": payload["admin_email"], "password": payload["admin_temp_password"]},
        headers={"X-School-Slug": slug},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"

    drop_tenant_db(f"tenant_{slug.replace('-', '_')}")


def test_enroll_rejects_duplicate_slug(client, platform_auth_headers, enrolled_school):
    payload = {
        "name": "Another School",
        "slug": enrolled_school["slug"],
        "address": "1 Test Way",
        "phone": "+10000000000",
        "admin_name": "Someone Else",
        "admin_email": f"someone-else-{uuid.uuid4().hex[:6]}@example.com",
        "admin_temp_password": "temp-password-1",
    }
    resp = client.post("/platform/schools", json=payload, headers=platform_auth_headers)
    assert resp.status_code == 409


def test_enroll_rejects_unknown_timezone(client, platform_auth_headers):
    slug = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "name": "Bad Timezone School",
        "slug": slug,
        "address": "1 Test Way",
        "phone": "+10000000000",
        "admin_name": "Ada Admin",
        "admin_email": f"admin-{slug}@example.com",
        "admin_temp_password": "temp-password-1",
        "timezone": "Not/A_Real_Zone",
    }
    resp = client.post("/platform/schools", json=payload, headers=platform_auth_headers)
    assert resp.status_code == 422


def test_enrolled_school_is_searchable_by_generated_id_and_name(client, platform_auth_headers, enrolled_school):
    gpd_id = f"GPD-{enrolled_school['school']['sequence_no']:06d}"

    by_id = client.get("/platform/schools", params={"query": gpd_id}, headers=platform_auth_headers)
    assert by_id.status_code == 200
    assert any(s["id"] == enrolled_school["school"]["id"] for s in by_id.json())

    by_name = client.get("/platform/schools", params={"query": "Test Academy"}, headers=platform_auth_headers)
    assert by_name.status_code == 200
    assert any(s["id"] == enrolled_school["school"]["id"] for s in by_name.json())


def test_archived_school_blocks_staff_login(client, platform_auth_headers, enrolled_school):
    school_id = enrolled_school["school"]["id"]

    archive_resp = client.post(f"/platform/schools/{school_id}/archive", headers=platform_auth_headers)
    assert archive_resp.status_code == 200
    assert archive_resp.json()["archived_at"] is not None

    login = client.post(
        "/auth/staff/login",
        json={"email": enrolled_school["admin_email"], "password": enrolled_school["admin_password"]},
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert login.status_code == 404

    unarchive_resp = client.post(f"/platform/schools/{school_id}/unarchive", headers=platform_auth_headers)
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["archived_at"] is None

    login_again = client.post(
        "/auth/staff/login",
        json={"email": enrolled_school["admin_email"], "password": enrolled_school["admin_password"]},
        headers={"X-School-Slug": enrolled_school["slug"]},
    )
    assert login_again.status_code == 200
