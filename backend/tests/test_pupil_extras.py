"""SMS alerts, the gate photo, and the CSV import for pupil-card mode."""

import uuid

import pytest
from test_pupil_cards import (  # noqa: F401  (pupil_school is a fixture)
    _iso,
    _new_student,
    _print_card,
    _sample_photo,
    _tenant_session,
    pupil_school,
)

from app.models.tenant import Guardian, GuardianDeviceToken, Notification


def test_phone_normalization():
    from app.core.sms import normalize_phone

    assert normalize_phone("08148247438") == "2348148247438"
    assert normalize_phone("+234 814 824 7438") == "2348148247438"
    assert normalize_phone("2348148247438") == "2348148247438"
    assert normalize_phone("8148247438") == "2348148247438"
    assert normalize_phone("+44 7700 900123") == "447700900123"
    assert normalize_phone("12345") is None
    assert normalize_phone("") is None
    assert normalize_phone(None) is None


def _enroll_family(client, admin_headers, name="Mum Sms", phone="08148247438", child="Sms Kid"):
    resp = client.post(
        "/guardians",
        json={
            "name": name,
            "email": f"sms-{uuid.uuid4().hex[:8]}@example.com",
            "phone": phone,
            "children": [{"name": child, "grade": "Primary 1"}],
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["children"][0]["id"]


@pytest.fixture
def sent_sms(monkeypatch):
    sent = []
    monkeypatch.setattr("app.api.routes.attendance.send_sms", lambda number, text: sent.append((number, text)) or True)
    return sent


def test_sms_goes_only_to_parents_without_the_app_and_only_when_enabled(
    client, platform_auth_headers, pupil_school, school_admin_headers, school_staff_headers, sent_sms
):
    sid = _enroll_family(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    # Off by default: a scan notifies nobody by SMS.
    client.post("/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(300)}, headers=school_staff_headers)
    assert sent_sms == []

    resp = client.patch(
        f"/platform/schools/{pupil_school['school']['id']}", json={"sms_enabled": True}, headers=platform_auth_headers
    )
    assert resp.status_code == 200 and resp.json()["sms_enabled"] is True

    second = client.post("/attendance/pupil-scan", json={"token": token}, headers=school_staff_headers)
    assert second.json()["status"] == "recorded"
    assert len(sent_sms) == 1
    number, text = sent_sms[0]
    assert number == "08148247438"  # normalization happens inside send_sms
    assert "Sms Kid left school" in text and "Test Academy" in text
    # The SMS states the time of the scan, in the school's own time zone.
    import re

    assert re.search(r"Sms Kid left school at \d{1,2}:\d{2} [AP]M\.", text), text

    db = _tenant_session(pupil_school)
    try:
        assert db.query(Notification).filter_by(event_id=second.json()["event_id"], channel="sms").count() == 1
    finally:
        db.close()


def test_no_sms_when_the_parent_has_the_app_registered(
    client, platform_auth_headers, pupil_school, school_admin_headers, school_staff_headers, sent_sms
):
    sid = _enroll_family(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)
    client.patch(
        f"/platform/schools/{pupil_school['school']['id']}", json={"sms_enabled": True}, headers=platform_auth_headers
    )
    db = _tenant_session(pupil_school)
    try:
        guardian = db.query(Guardian).filter_by(name="Mum Sms").one()
        db.add(GuardianDeviceToken(guardian_id=guardian.id, token=f"tok-{uuid.uuid4().hex}", platform="android"))
        db.commit()
    finally:
        db.close()

    client.post("/attendance/pupil-scan", json={"token": token}, headers=school_staff_headers)
    assert sent_sms == []


def test_gate_photo_and_roster_hash(client, pupil_school, school_admin_headers, school_staff_headers):
    sid = _new_student(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    # No photo yet: scan says so, roster has no hash, photo endpoint 404s.
    scan = client.post(
        "/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(200)}, headers=school_staff_headers
    )
    assert scan.json()["has_photo"] is False and scan.json()["student_id"] == sid
    assert client.get("/attendance/pupil-roster", headers=school_staff_headers).json()[0]["photo_hash"] is None
    assert client.get(f"/attendance/pupil-photo/{sid}", headers=school_staff_headers).status_code == 404

    client.put(
        f"/pupil-cards/{sid}/photo",
        files={"file": ("kid.jpg", _sample_photo(), "image/jpeg")},
        headers=school_admin_headers,
    )
    scan2 = client.post("/attendance/pupil-scan", json={"token": token}, headers=school_staff_headers)
    assert scan2.json()["has_photo"] is True
    first_hash = client.get("/attendance/pupil-roster", headers=school_staff_headers).json()[0]["photo_hash"]
    assert first_hash and len(first_hash) == 32

    # Plain staff (not admin) can fetch it for the gate screen.
    photo = client.get(f"/attendance/pupil-photo/{sid}", headers=school_staff_headers)
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"

    # A changed photo changes the hash, so devices know to re-download.
    client.put(
        f"/pupil-cards/{sid}/photo",
        files={"file": ("kid2.jpg", _sample_photo(size=(500, 700)), "image/jpeg")},
        headers=school_admin_headers,
    )
    assert client.get("/attendance/pupil-roster", headers=school_staff_headers).json()[0]["photo_hash"] != first_hash


def test_csv_import_creates_pupils_and_families_and_is_rerunnable(client, pupil_school, school_admin_headers):
    parent_email = f"import-{uuid.uuid4().hex[:8]}@example.com"
    rows = [
        {
            "pupil_name": "Import One",
            "grade": "Primary 2",
            "guardian_name": "Imp Parent",
            "guardian_email": parent_email,
            "guardian_phone": "08011112222",
        },
        {"pupil_name": "Import Two", "grade": "Primary 4", "guardian_name": "Imp Parent", "guardian_email": parent_email},
        {"pupil_name": "Import No Parent", "grade": "Primary 1"},
        {"pupil_name": "", "grade": "Primary 1"},
        {"pupil_name": "Bad Email Kid", "guardian_name": "X", "guardian_email": "not-an-email"},
        {"pupil_name": "No Name Parent", "guardian_email": "someone@example.com"},
    ]
    resp = client.post("/pupil-cards/import", json={"rows": rows}, headers=school_admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["status"] for r in body["rows"]] == ["created", "created", "created", "error", "error", "error"]
    assert (body["created"], body["existing"], body["failed"]) == (3, 0, 3)

    names = {p["name"] for p in client.get("/pupil-cards", headers=school_admin_headers).json()}
    assert {"Import One", "Import Two", "Import No Parent"} <= names

    # One parent identity, both children linked to it.
    guardians = client.get("/guardians", params={"query": "Imp Parent"}, headers=school_admin_headers).json()
    assert len(guardians) == 1 and {c["name"] for c in guardians[0]["children"]} == {"Import One", "Import Two"}

    # Re-running the same file changes nothing; a new sibling links to the existing parent.
    sibling = {
        "pupil_name": "Import Three",
        "grade": "Primary 6",
        "guardian_name": "Imp Parent",
        "guardian_email": parent_email.upper(),
    }
    again = client.post(
        "/pupil-cards/import", json={"rows": rows[:3] + [sibling]}, headers=school_admin_headers
    ).json()
    assert [r["status"] for r in again["rows"]] == ["exists", "exists", "exists", "created"]
    guardians = client.get("/guardians", params={"query": "Imp Parent"}, headers=school_admin_headers).json()
    assert len(guardians) == 1 and len(guardians[0]["children"]) == 3


def test_import_closed_in_guardian_mode(client, enrolled_school, school_admin_headers):
    resp = client.post("/pupil-cards/import", json={"rows": [{"pupil_name": "X"}]}, headers=school_admin_headers)
    assert resp.status_code == 403


def test_sms_for_an_offline_scan_states_the_time_it_actually_happened(
    client, platform_auth_headers, pupil_school, school_admin_headers, school_staff_headers, sent_sms
):
    import datetime as dt
    import re

    sid = _enroll_family(client, school_admin_headers, child="Late Kid")
    token = _print_card(client, school_admin_headers, pupil_school, sid)
    client.patch(
        f"/platform/schools/{pupil_school['school']['id']}", json={"sms_enabled": True}, headers=platform_auth_headers
    )

    scanned = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)  # school timezone in tests is UTC
    resp = client.post(
        "/attendance/pupil-scan/batch",
        json={"scans": [{"token": token, "type": "drop_off", "scanned_at": scanned.isoformat()}]},
        headers=school_staff_headers,
    )
    assert resp.json()["results"][0]["status"] == "recorded"
    assert len(sent_sms) == 1
    expected = scanned.strftime("%I:%M %p").lstrip("0")
    assert f"Late Kid arrived at school at {expected}." in sent_sms[0][1], sent_sms[0][1]
