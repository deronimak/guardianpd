"""Signed QR tokens (ARCHITECTURE.md §5) and staff auth primitives.

QR tokens are static/permanent per (guardian, school) by design — see the
"Decision: static QR" note in ARCHITECTURE.md. The signature stops anyone
from forging a token for a guardian_id/school_id they don't hold; it does
NOT by itself handle revocation. Revocation is enforced by checking the
token string against QRCredential.revoked_at in the tenant DB at scan time
(see app/api/routes/attendance.py) — signature validity alone is not enough.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def generate_qr_token(guardian_id: str, school_id: str) -> str:
    payload = {"gid": guardian_id, "sid": school_id, "n": secrets.token_urlsafe(16)}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(settings.qr_signing_key.encode(), payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def verify_qr_token(token: str) -> dict[str, Any] | None:
    """Checks the signature and returns the decoded payload, or None if invalid.

    Caller is still responsible for the revocation + authorization checks —
    a validly-signed token can still be revoked or not linked to the child
    being scanned.
    """
    try:
        payload_b64, sig_b64 = token.split(".")
        payload_bytes = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error):
        return None

    expected_signature = hmac.new(settings.qr_signing_key.encode(), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    return json.loads(payload_bytes)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    to_encode: dict[str, Any] = {"sub": subject, **(extra_claims or {})}
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expires_minutes)
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
