"""Covers the guardian activation code — now a 7-digit numeric code instead
of a long random token (easier to type on a phone), with a wrong-attempt
lockout to compensate for the much lower entropy. See
app/api/routes/guardians.py's _generate_invite_code and
app/api/routes/parent_auth.py's activate.
"""

import re
import uuid

from app.db.platform import SessionLocal
from app.models.platform import PlatformUser


def _create_guardian(client, school_admin_headers, email):
    resp = client.post(
        "/guardians",
        json={"name": "Gina Guardian", "email": email, "phone": "+15559876543", "children": []},
        headers=school_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _invite_token(email):
    db = SessionLocal()
    try:
        user = db.query(PlatformUser).filter_by(email=email).first()
        return user.invite_token
    finally:
        db.close()


def test_invite_code_is_seven_digits(client, school_admin_headers):
    email = f"gina-{uuid.uuid4().hex[:10]}@example.com"
    _create_guardian(client, school_admin_headers, email)

    token = _invite_token(email)
    assert re.fullmatch(r"\d{7}", token), token


def test_activate_with_correct_code_succeeds(client, school_admin_headers):
    email = f"gina-{uuid.uuid4().hex[:10]}@example.com"
    _create_guardian(client, school_admin_headers, email)
    token = _invite_token(email)

    resp = client.post(
        "/auth/parent/activate",
        json={"email": email, "invite_token": token, "password": "correct-horse-1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


def test_activate_locks_out_after_too_many_wrong_codes(client, school_admin_headers):
    email = f"gina-{uuid.uuid4().hex[:10]}@example.com"
    _create_guardian(client, school_admin_headers, email)
    real_token = _invite_token(email)
    wrong_token = "0000000" if real_token != "0000000" else "1111111"

    for _ in range(5):
        resp = client.post(
            "/auth/parent/activate",
            json={"email": email, "invite_token": wrong_token, "password": "correct-horse-1"},
        )
        assert resp.status_code == 400

    # The 5th wrong guess should have burned the code entirely — even the
    # real one no longer works, matching a fresh "resend activation" flow.
    resp = client.post(
        "/auth/parent/activate",
        json={"email": email, "invite_token": real_token, "password": "correct-horse-1"},
    )
    assert resp.status_code == 400
    assert "Invalid activation code" in resp.json()["detail"]
