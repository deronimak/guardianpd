def test_login_succeeds_with_correct_credentials(client, platform_staff):
    resp = client.post(
        "/auth/platform/login",
        json={"email": platform_staff["email"], "password": platform_staff["password"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["role"] == "ops"


def test_login_rejects_wrong_password(client, platform_staff):
    resp = client.post(
        "/auth/platform/login",
        json={"email": platform_staff["email"], "password": "not-the-password"},
    )
    assert resp.status_code == 401


def test_login_rejects_unknown_email(client):
    resp = client.post(
        "/auth/platform/login",
        json={"email": "nobody@example.com", "password": "whatever123"},
    )
    assert resp.status_code == 401


def test_protected_route_requires_token(client):
    resp = client.get("/platform/schools")
    assert resp.status_code == 401


def test_change_password_then_login_with_new_password(client, platform_staff, platform_auth_headers):
    resp = client.post(
        "/auth/platform/change-password",
        json={"current_password": platform_staff["password"], "new_password": "a-new-password-1"},
        headers=platform_auth_headers,
    )
    assert resp.status_code == 200

    old_login = client.post(
        "/auth/platform/login",
        json={"email": platform_staff["email"], "password": platform_staff["password"]},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/platform/login",
        json={"email": platform_staff["email"], "password": "a-new-password-1"},
    )
    assert new_login.status_code == 200
