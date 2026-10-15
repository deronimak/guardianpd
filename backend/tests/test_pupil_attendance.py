"""Pupil attendance view, pupil-mode wording in welfare emails, and the
parent-app flag for events recorded from a pupil's own card."""

import datetime as dt
import uuid

from test_pupil_cards import (  # noqa: F401  (pupil_school is a fixture)
    _iso,
    _new_student,
    _print_card,
    _tenant_session,
    pupil_school,
)

from app.api.deps import get_current_parent
from app.db.platform import SessionLocal
from app.jobs import welfare_check
from app.main import app
from app.models.platform import PlatformUser, School


def _scan(client, headers, token, minutes_ago=None):
    body = {"token": token}
    if minutes_ago is not None:
        body["scanned_at"] = _iso(minutes_ago)
    resp = client.post("/attendance/pupil-scan", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_pupil_attendance_lists_arrived_left_and_not_arrived(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    ada = _new_student(client, school_admin_headers, "Ada Pupil", "Primary 3")
    bola = _new_student(client, school_admin_headers, "Bola Pupil", "Primary 3")
    _new_student(client, school_admin_headers, "Chidi Pupil", "Primary 4")
    ada_token = _print_card(client, school_admin_headers, pupil_school, ada)
    bola_token = _print_card(client, school_admin_headers, pupil_school, bola)

    _scan(client, school_staff_headers, ada_token, minutes_ago=60)  # arrival
    _scan(client, school_staff_headers, ada_token)  # departure
    _scan(client, school_staff_headers, bola_token, minutes_ago=30)  # arrival only

    data = client.get("/pupil-cards/attendance", headers=school_admin_headers).json()
    assert data["total"] == 3
    assert (data["arrived"], data["left"], data["not_arrived"]) == (2, 1, 1)
    by_name = {r["name"]: r for r in data["rows"]}
    assert by_name["Ada Pupil"]["status"] == "left" and by_name["Ada Pupil"]["arrived_time"]
    assert by_name["Ada Pupil"]["arrived_by"] and by_name["Ada Pupil"]["left_by"]  # staff name shown
    assert by_name["Bola Pupil"]["status"] == "present" and by_name["Bola Pupil"]["left_time"] is None
    assert by_name["Chidi Pupil"]["status"] == "not_arrived"

    # A different day has no activity.
    other = (dt.date.fromisoformat(data["date"]) - dt.timedelta(days=10)).isoformat()
    past = client.get("/pupil-cards/attendance", params={"day": other}, headers=school_admin_headers).json()
    assert past["arrived"] == 0 and past["not_arrived"] == 3

    # Only School Admins may view it; guardian-mode schools can't.
    assert client.get("/pupil-cards/attendance", headers=school_staff_headers).status_code == 403


def test_attendance_closed_in_guardian_mode(client, enrolled_school, school_admin_headers):
    assert client.get("/pupil-cards/attendance", headers=school_admin_headers).status_code == 403


def test_welfare_emails_use_arrival_wording_in_pupil_mode(client, pupil_school, school_admin_headers, monkeypatch):
    sent = []
    monkeypatch.setattr(welfare_check, "send_email", lambda **kw: sent.append(kw))
    resp = client.post(
        "/guardians",
        json={
            "name": "Welfare Parent",
            "email": f"welfare-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": "Welfare Kid", "grade": "Primary 1"}],
        },
        headers=school_admin_headers,
    )
    assert resp.status_code == 201, resp.text

    db_platform = SessionLocal()
    tenant = _tenant_session(pupil_school)
    try:
        school = db_platform.query(School).filter_by(slug=pupil_school["slug"]).one()
        today = dt.date.today()
        assert welfare_check.run_dropoff_check(school, tenant, today) == 1
        subject, body = sent[-1]["subject"], sent[-1]["body"]
        assert "arrived" in subject and "drop" not in (subject + body).lower()
        assert "scanned in" in body
    finally:
        tenant.close()
        db_platform.close()


def test_parent_history_flags_events_from_the_pupils_own_card(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    email = f"hist-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/guardians",
        json={"name": "History Parent", "email": email, "children": [{"name": "History Kid", "grade": "Primary 2"}]},
        headers=school_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["children"][0]["id"]
    token = _print_card(client, school_admin_headers, pupil_school, sid)
    _scan(client, school_staff_headers, token)

    db = SessionLocal()
    try:
        parent_id = db.query(PlatformUser).filter_by(email=email).one().id
    finally:
        db.close()

    app.dependency_overrides[get_current_parent] = lambda: {"sub": str(parent_id)}
    try:
        history = client.get(f"/parent/me/schools/{pupil_school['slug']}/students/{sid}/attendance")
    finally:
        app.dependency_overrides.pop(get_current_parent, None)
    assert history.status_code == 200, history.text
    events = history.json()
    assert len(events) == 1 and events[0]["by_pupil_card"] is True and events[0]["guardian_name"] is None
