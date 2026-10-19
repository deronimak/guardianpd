"""Master Admin test-push tool."""

import uuid

from test_pupil_cards import _tenant_session  # noqa: F401

from app.models.tenant import Guardian, GuardianDeviceToken


def _family(client, headers):
    email = f"push-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/guardians",
        json={"name": "Push Parent", "email": email, "children": [{"name": "Push Kid"}]},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return email


def test_test_push_reports_each_device_and_failures(
    client, platform_auth_headers, enrolled_school, school_admin_headers, monkeypatch
):
    assert client.post("/platform/push/test", json={"email": "x@example.com"}).status_code == 401
    email = _family(client, school_admin_headers)

    # Unknown parent / parent with no phone registered yet.
    assert client.post("/platform/push/test", json={"email": "nobody@example.com"}, headers=platform_auth_headers).status_code == 404
    none_yet = client.post("/platform/push/test", json={"email": email}, headers=platform_auth_headers)
    assert none_yet.status_code == 404 and "registered" in none_yet.json()["detail"]

    db = _tenant_session(enrolled_school)
    try:
        guardian = db.query(Guardian).filter_by(email=email).one()
        db.add(GuardianDeviceToken(guardian_id=guardian.id, token="good-token-ABCDEF", platform="ios"))
        db.add(GuardianDeviceToken(guardian_id=guardian.id, token="bad-token-123456", platform="android"))
        db.commit()
    finally:
        db.close()

    sent = []

    def fake_send(token, title, body):
        sent.append(token)
        if token.startswith("bad"):
            raise RuntimeError("Auth error from APNS or Web Push Service")

    monkeypatch.setattr("app.api.routes.platform_push.send_push", fake_send)
    result = client.post("/platform/push/test", json={"email": email.upper()}, headers=platform_auth_headers)
    assert result.status_code == 200, result.text
    by_tail = {d["token_tail"]: d for d in result.json()["devices"]}
    assert by_tail["ABCDEF"]["ok"] is True and by_tail["ABCDEF"]["registered_as"] == "ios"
    assert by_tail["123456"]["ok"] is False and "APNS" in by_tail["123456"]["detail"]
    assert sorted(sent) == ["bad-token-123456", "good-token-ABCDEF"]
