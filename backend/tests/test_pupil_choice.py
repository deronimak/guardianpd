"""Pupil scan: look the card up first, then record the direction the user chose
("arrived at school" = drop_off, "leaving school" = pick_up)."""

from test_pupil_cards import (  # noqa: F401  (pupil_school is a fixture)
    _events,
    _iso,
    _new_student,
    _print_card,
    pupil_school,
)


def _lookup(client, headers, token):
    return client.post("/attendance/pupil-lookup", json={"token": token}, headers=headers)


def test_lookup_identifies_the_pupil_without_recording_anything(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    sid = _new_student(client, school_admin_headers, "Ada Pupil", "Primary 3")
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    first = _lookup(client, school_staff_headers, token)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["student_name"] == "Ada Pupil" and body["grade"] == "Primary 3" and body["student_id"] == sid
    assert body["suggested_type"] == "drop_off" and body["last_type"] is None
    assert _events(pupil_school, sid) == []  # a lookup never records

    client.post("/attendance/pupil-scan", json={"token": token, "type": "drop_off"}, headers=school_staff_headers)
    second = _lookup(client, school_staff_headers, token).json()
    assert second["suggested_type"] == "pick_up" and second["last_type"] == "drop_off" and second["last_time"]
    assert len(_events(pupil_school, sid)) == 1


def test_lookup_rejects_bad_cards_and_wrong_mode(client, enrolled_school, school_staff_headers, school_admin_headers):
    # Guardian-mode school: closed.
    assert _lookup(client, school_staff_headers, "x").status_code == 403


def test_lookup_rejects_garbage_and_replaced_cards(client, pupil_school, school_admin_headers, school_staff_headers):
    sid = _new_student(client, school_admin_headers)
    old = _print_card(client, school_admin_headers, pupil_school, sid)
    client.post(f"/pupil-cards/{sid}/reissue", headers=school_admin_headers)
    assert _lookup(client, school_staff_headers, "nope").status_code == 400
    assert _lookup(client, school_staff_headers, old).status_code == 400


def test_the_chosen_direction_is_recorded_and_corrections_are_allowed(
    client, pupil_school, school_admin_headers, school_staff_headers
):
    sid = _new_student(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)

    # Choosing "leaving" first is respected (no forced arrival-first rule).
    left = client.post("/attendance/pupil-scan", json={"token": token, "type": "pick_up"}, headers=school_staff_headers)
    assert left.json()["status"] == "recorded" and left.json()["type"] == "pick_up"

    # Tapping the same option again straight away is a duplicate...
    again = client.post("/attendance/pupil-scan", json={"token": token, "type": "pick_up"}, headers=school_staff_headers)
    assert again.json()["status"] == "duplicate"

    # ...but picking the other option moments later is a correction and is recorded.
    fix = client.post("/attendance/pupil-scan", json={"token": token, "type": "drop_off"}, headers=school_staff_headers)
    assert fix.json()["status"] == "recorded" and fix.json()["type"] == "drop_off"
    assert [e.type for e in _events(pupil_school, sid)] == ["pick_up", "drop_off"]


def test_offline_batch_keeps_the_chosen_direction(client, pupil_school, school_admin_headers, school_staff_headers):
    sid = _new_student(client, school_admin_headers)
    token = _print_card(client, school_admin_headers, pupil_school, sid)
    batch = {
        "scans": [
            {"token": token, "type": "drop_off", "scanned_at": _iso(180)},
            {"token": token, "type": "pick_up", "scanned_at": _iso(20)},
        ]
    }
    results = client.post("/attendance/pupil-scan/batch", json=batch, headers=school_staff_headers).json()["results"]
    assert [(r["status"], r["type"]) for r in results] == [("recorded", "drop_off"), ("recorded", "pick_up")]
