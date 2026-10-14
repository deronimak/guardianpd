"""Pupil-card mode (School.credential_mode == "pupil"): card issuing/printing,
arrival/departure scans, offline-captured scans synced later, and the
guarantee that guardian-mode schools are untouched.
"""

import datetime as dt
import uuid

import pytest

from app.db.tenant import get_tenant_sessionmaker
from app.models.tenant import AttendanceEvent, Notification, StudentCredential


def _tenant_session(enrolled_school):
    return get_tenant_sessionmaker(f"tenant_{enrolled_school['slug'].replace('-', '_')}")()


def _set_mode(client, platform_auth_headers, enrolled_school, mode):
    resp = client.patch(
        f"/platform/schools/{enrolled_school['school']['id']}",
        json={"credential_mode": mode},
        headers=platform_auth_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.fixture
def pupil_school(client, platform_auth_headers, enrolled_school):
    _set_mode(client, platform_auth_headers, enrolled_school, "pupil")
    return enrolled_school


def _new_student(client, admin_headers, name="Ada Pupil", grade="Primary 3"):
    resp = client.post("/students", json={"name": name, "grade": grade}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _print_card(client, admin_headers, enrolled_school, student_id):
    resp = client.get(f"/pupil-cards/{student_id}/card.pdf", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.content.startswith(b"%PDF")
    db = _tenant_session(enrolled_school)
    try:
        cred = db.query(StudentCredential).filter_by(student_id=student_id, revoked_at=None).one()
        return cred.token
    finally:
        db.close()


def _events(enrolled_school, student_id):
    db = _tenant_session(enrolled_school)
    try:
        return (
            db.query(AttendanceEvent)
            .filter_by(student_id=student_id)
            .order_by(AttendanceEvent.timestamp)
            .all()
        )
    finally:
        db.close()


def _iso(delta_minutes):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=delta_minutes)).isoformat()


def test_new_schools_default_to_guardian_mode_and_pupil_endpoints_are_closed(
    client, enrolled_school, school_admin_headers, school_staff_headers
):
    detail = client.get("/school/me", headers=school_admin_headers)
    assert detail.json()["credential_mode"] == "guardian"

    assert client.get("/pupil-cards", headers=school_admin_headers).status_code == 403
    scan = client.post("/attendance/pupil-scan", json={"token": "x"}, headers=school_staff_headers)
    assert scan.status_code == 403


def test_card_pdf_bulk_pdf_and_reissue(client, pupil_school, school_admin_headers):
    sid = _new_student(client, school_admin_headers)
    _new_student(client, school_admin_headers, name="Bola Pupil")
    old_token = _print_card(client, school_admin_headers, pupil_school, sid)

    bulk = client.get("/pupil-cards/bulk.pdf", headers=school_admin_headers)
    assert bulk.status_code == 200 and bulk.content.startswith(b"%PDF")

    listing = client.get("/pupil-cards", headers=school_admin_headers).json()
    assert {p["name"] for p in listing} == {"Ada Pupil", "Bola Pupil"}
    assert all(p["has_card"] for p in listing)

    assert client.post(f"/pupil-cards/{sid}/reissue", headers=school_admin_headers).status_code == 200
    new_token = _print_card(client, school_admin_headers, pupil_school, sid)
    assert new_token != old_token


def test_scan_alternates_arrival_and_departure_and_debounces(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    sid = _new_student(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    # Earlier in the day -> arrival; a later one -> departure.
    first = client.post(
        "/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(300)}, headers=school_staff_headers
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "recorded" and first.json()["type"] == "drop_off"
    assert first.json()["student_name"] == "Ada Pupil"

    second = client.post(
        "/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(1)}, headers=school_staff_headers
    )
    assert second.json()["status"] == "recorded" and second.json()["type"] == "pick_up"

    # Immediate re-tap is the same physical scan.
    again = client.post("/attendance/pupil-scan", json={"token": token}, headers=school_staff_headers)
    assert again.json()["status"] == "duplicate"

    events = _events(pupil_school, sid)
    assert [e.type for e in events] == ["drop_off", "pick_up"]
    assert all(e.guardian_id is None for e in events)


def test_revoked_foreign_and_garbage_tokens_are_rejected(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    sid = _new_student(client, school_admin_headers)
    old_token = _print_card(client, school_admin_headers, pupil_school, sid)
    client.post(f"/pupil-cards/{sid}/reissue", headers=school_admin_headers)

    revoked = client.post("/attendance/pupil-scan", json={"token": old_token}, headers=school_staff_headers)
    assert revoked.status_code == 400

    garbage = client.post("/attendance/pupil-scan", json={"token": "nope"}, headers=school_staff_headers)
    assert garbage.status_code == 400

    # A guardian token must not work as a pupil card.
    resp = client.post(
        "/guardians",
        json={
            "name": "Some Guardian",
            "email": f"g-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": "Kid"}],
        },
        headers=school_admin_headers,
    )
    guardian_token = resp.json()["qr_token"]
    wrong_kind = client.post("/attendance/pupil-scan", json={"token": guardian_token}, headers=school_staff_headers)
    assert wrong_kind.status_code == 400
    assert _events(pupil_school, sid) == []


def test_offline_batch_sync_orders_by_scan_time_and_reports_per_item(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    sid_a = _new_student(client, school_admin_headers, name="Ada Pupil")
    sid_b = _new_student(client, school_admin_headers, name="Bola Pupil")
    token_a = _print_card(client, school_admin_headers, pupil_school, sid_a)
    token_b = _print_card(client, school_admin_headers, pupil_school, sid_b)

    # Uploaded out of order: the device may flush in any order.
    batch = {
        "scans": [
            {"token": token_a, "scanned_at": _iso(10)},  # departure (second)
            {"token": "garbage", "scanned_at": _iso(60)},
            {"token": token_a, "scanned_at": _iso(120)},  # arrival (first)
            {"token": token_b, "scanned_at": _iso(100)},
            {"token": token_b, "scanned_at": _iso(100)},  # same tap, duplicate
        ]
    }
    resp = client.post("/attendance/pupil-scan/batch", json=batch, headers=school_staff_headers)
    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert [r["status"] for r in results] == ["recorded", "rejected", "recorded", "recorded", "duplicate"]
    assert results[0]["type"] == "pick_up"
    assert results[2]["type"] == "drop_off"

    assert [e.type for e in _events(pupil_school, sid_a)] == ["drop_off", "pick_up"]
    assert [e.type for e in _events(pupil_school, sid_b)] == ["drop_off"]

    # Re-uploading the same batch (e.g. the response was lost) adds nothing.
    again = client.post("/attendance/pupil-scan/batch", json=batch, headers=school_staff_headers).json()["results"]
    assert [r["status"] for r in again] == ["duplicate", "rejected", "duplicate", "duplicate", "duplicate"]
    assert len(_events(pupil_school, sid_a)) == 2


def test_future_and_stale_scan_times_are_rejected(client, pupil_school, school_admin_headers, school_staff_headers):
    sid = _new_student(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    future = client.post(
        "/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(-60)}, headers=school_staff_headers
    )
    assert future.status_code == 400
    stale = client.post(
        "/attendance/pupil-scan", json={"token": token, "scanned_at": _iso(60 * 24 * 5)}, headers=school_staff_headers
    )
    assert stale.status_code == 400
    assert _events(pupil_school, sid) == []


def test_linked_guardians_are_notified_and_roster_has_names_but_no_tokens(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    resp = client.post(
        "/guardians",
        json={
            "name": "Mum Pupil",
            "email": f"mum-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": "Chidi Pupil", "grade": "Primary 1"}],
        },
        headers=school_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["children"][0]["id"]
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    scan = client.post("/attendance/pupil-scan", json={"token": token}, headers=school_staff_headers)
    assert scan.json()["status"] == "recorded"

    db = _tenant_session(pupil_school)
    try:
        assert db.query(Notification).filter_by(event_id=scan.json()["event_id"]).count() == 1
    finally:
        db.close()

    roster = client.get("/attendance/pupil-roster", headers=school_staff_headers)
    assert roster.status_code == 200
    assert [r["name"] for r in roster.json()] == ["Chidi Pupil"]
    assert "token" not in roster.text


def test_deleting_a_pupil_removes_their_card(client, pupil_school, school_admin_headers):
    sid = _new_student(client, school_admin_headers)
    _print_card(client, school_admin_headers, pupil_school, sid)
    assert client.delete(f"/students/{sid}", headers=school_admin_headers).status_code in (200, 204)
    db = _tenant_session(pupil_school)
    try:
        assert db.query(StudentCredential).filter_by(student_id=sid).count() == 0
    finally:
        db.close()
