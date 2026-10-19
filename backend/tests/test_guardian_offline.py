"""Offline guardian scanning: the cached guardian list for phones, and the batch
upload of scans saved while there was no signal."""

import datetime as dt
import uuid

from test_pupil_cards import _iso, _tenant_session

from app.models.tenant import AttendanceEvent, Notification


def _family(client, headers, guardian="Mrs Offline", kids=("Kid One", "Kid Two")):
    resp = client.post(
        "/guardians",
        json={
            "name": guardian,
            "email": f"off-{uuid.uuid4().hex[:8]}@example.com",
            "children": [{"name": k, "grade": "Primary 2"} for k in kids],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["qr_token"], [c["id"] for c in body["children"]], body["id"]


def _events(enrolled_school):
    db = _tenant_session(enrolled_school)
    try:
        return db.query(AttendanceEvent).order_by(AttendanceEvent.timestamp).all()
    finally:
        db.close()


def test_scan_roster_lists_guardians_with_children_but_no_tokens(
    client, enrolled_school, school_admin_headers, school_staff_headers
):
    _, kids, gid = _family(client, school_admin_headers)
    other_token, _, other_gid = _family(client, school_admin_headers, guardian="Mr Revoked", kids=("Solo",))

    roster = client.get("/guardians/scan-roster", headers=school_staff_headers)
    assert roster.status_code == 200, roster.text
    by_id = {g["guardian_id"]: g for g in roster.json()}
    assert gid in by_id and {s["id"] for s in by_id[gid]["students"]} == set(kids)
    assert by_id[gid]["fees_outstanding"] is False
    assert "token" not in roster.text and "email" not in roster.text and "phone" not in roster.text

    # Needs a signed-in staff member.
    assert client.get("/guardians/scan-roster", headers={"X-School-Slug": enrolled_school["slug"]}).status_code == 401


def test_batch_records_scans_with_their_real_time_and_in_order(
    client, enrolled_school, school_admin_headers, school_staff_headers
):
    token, kids, _ = _family(client, school_admin_headers)
    batch = {
        "scans": [
            {"token": token, "student_id": kids[0], "type": "pick_up", "scanned_at": _iso(10)},
            {"token": token, "student_id": kids[0], "type": "drop_off", "scanned_at": _iso(240)},
            {"token": token, "student_id": kids[1], "type": "drop_off", "scanned_at": _iso(239)},
        ]
    }
    resp = client.post("/attendance/scan/batch", json=batch, headers=school_staff_headers)
    assert resp.status_code == 200, resp.text
    assert [r["status"] for r in resp.json()["results"]] == ["recorded", "recorded", "recorded"]

    events = _events(enrolled_school)
    assert [(e.type, str(e.student_id)) for e in events] == [
        ("drop_off", kids[0]),
        ("drop_off", kids[1]),
        ("pick_up", kids[0]),
    ]
    # Timestamps are when the scans happened, not when they were uploaded.
    assert dt.datetime.now(dt.timezone.utc) - events[0].timestamp > dt.timedelta(hours=3)


def test_batch_is_safe_to_retry_and_reports_bad_items_individually(
    client, enrolled_school, school_admin_headers, school_staff_headers
):
    token, kids, _ = _family(client, school_admin_headers)
    batch = {
        "scans": [
            {"token": token, "student_id": kids[0], "type": "drop_off", "scanned_at": _iso(100)},
            {"token": "garbage", "student_id": kids[0], "type": "drop_off", "scanned_at": _iso(90)},
            {"token": token, "student_id": kids[0], "type": "pick_up", "scanned_at": _iso(-30)},  # future
        ]
    }
    first = client.post("/attendance/scan/batch", json=batch, headers=school_staff_headers).json()["results"]
    assert [r["status"] for r in first] == ["recorded", "rejected", "rejected"]
    assert "future" in first[2]["detail"]

    again = client.post("/attendance/scan/batch", json=batch, headers=school_staff_headers).json()["results"]
    assert [r["status"] for r in again] == ["duplicate", "rejected", "rejected"]
    assert len(_events(enrolled_school)) == 1


def test_batch_flags_a_guardian_who_is_not_authorized_for_that_child_and_alerts_parents(
    client, enrolled_school, school_admin_headers, school_staff_headers
):
    token_a, _, _ = _family(client, school_admin_headers, guardian="Guardian A", kids=("A Kid",))
    _, kids_b, _ = _family(client, school_admin_headers, guardian="Guardian B", kids=("B Kid",))

    resp = client.post(
        "/attendance/scan/batch",
        json={"scans": [{"token": token_a, "student_id": kids_b[0], "type": "pick_up", "scanned_at": _iso(30)}]},
        headers=school_staff_headers,
    )
    result = resp.json()["results"][0]
    assert result["status"] == "flagged" and "not authorized" in result["detail"]

    events = _events(enrolled_school)
    assert len(events) == 1 and events[0].flagged is True
    db = _tenant_session(enrolled_school)
    try:
        assert db.query(Notification).filter_by(event_id=events[0].id).count() >= 1  # B's guardian was alerted
    finally:
        db.close()


def test_live_scan_behaviour_is_unchanged(client, enrolled_school, school_admin_headers, school_staff_headers):
    token, kids, _ = _family(client, school_admin_headers)
    ok = client.post(
        "/attendance/scan", json={"token": token, "student_id": kids[0], "type": "drop_off"}, headers=school_staff_headers
    )
    assert ok.status_code == 200 and ok.json()["status"] == "recorded"
    bad = client.post(
        "/attendance/scan", json={"token": "nope", "student_id": kids[0], "type": "drop_off"}, headers=school_staff_headers
    )
    assert bad.status_code == 400
