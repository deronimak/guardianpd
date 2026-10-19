"""SMS alerts for parents who don't have the app (or haven't registered a
phone for push) — an opt-in, per-school feature (School.sms_enabled) because
every message costs money.

Providers (SMS_PROVIDER): "bulksmsnigeria" (default; https://www.bulksmsnigeria.com,
API v2 with a bearer token) or "brevo" (transactional SMS, reusing BREVO_API_KEY).
With no token for the chosen provider the message is logged instead of sent,
so the scan flow works end-to-end in local dev.
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
_BULKSMSNG_BASE = "https://www.bulksmsnigeria.com/api/v2"
# BulkSMSNigeria refuses an identical message to the same recipient within a
# minute and charges nothing: for our alerts that just means "already sent".
_BULKSMSNG_DUPLICATE = "BSNG-2012"


def normalize_phone(raw: str | None) -> str | None:
    """Nigerian-friendly normalization to "2348012345678" (international, no
    plus). Accepts 0801..., +234801..., 234801..., or a bare 10-digit 801...
    number; any other "+"-prefixed international number is passed through.
    Returns None for anything unusable.
    """
    if not raw:
        return None
    text = raw.strip()
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if plus:
        return digits if 8 <= len(digits) <= 15 else None
    if digits.startswith("234") and len(digits) == 13:
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return "234" + digits[1:]
    if len(digits) == 10 and digits[0] in "789":
        return "234" + digits
    return None


def sender_name() -> str:
    """Alphanumeric sender: letters and digits only, max 11."""
    return re.sub(r"[^A-Za-z0-9]", "", settings.sms_sender_id)[:11] or "GuardianPD"


def provider() -> str:
    return "brevo" if settings.sms_provider.strip().lower() == "brevo" else "bulksmsnigeria"


def sms_configured() -> bool:
    return bool(settings.brevo_api_key if provider() == "brevo" else settings.bulksmsnigeria_api_token)


def _needs_unicode(message: str) -> bool:
    # Names with accents (e.g. "Ọlá") arrive garbled unless sent as Unicode.
    return any(ord(ch) > 127 for ch in message)


def _send_brevo(number: str, message: str) -> dict:
    response = httpx.post(
        _BREVO_SMS_URL,
        headers={"accept": "application/json", "content-type": "application/json", "api-key": settings.brevo_api_key},
        json={
            "sender": sender_name(),
            "recipient": number,
            "content": message,
            "type": "transactional",
            "unicodeEnabled": _needs_unicode(message),
        },
        timeout=10,
    )
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(f"Brevo SMS failed ({response.status_code}): {response.text[:300]}")
    data = response.json() if response.content else {}
    return {
        "ok": True,
        "sent": True,
        "number": number,
        "message_id": data.get("messageId") or data.get("reference"),
        "remaining_credits": data.get("remainingCredits"),
        "detail": "Sent",
    }


def _bulksmsng_error(response: httpx.Response) -> tuple[str | None, str]:
    try:
        body = response.json()
    except ValueError:
        return None, response.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    code = (error or {}).get("code") or (body.get("code") if isinstance(body, dict) else None)
    message = (error or {}).get("message") or (body.get("message") if isinstance(body, dict) else None) or response.text[:300]
    return code, message


def _send_bulksmsnigeria(number: str, message: str) -> dict:
    response = httpx.post(
        f"{_BULKSMSNG_BASE}/sms",
        headers={
            "Authorization": f"Bearer {settings.bulksmsnigeria_api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={
            "from": sender_name(),
            "to": number,
            "body": message,
            "gateway": settings.sms_gateway,
            "unicode": _needs_unicode(message),
        },
        timeout=15,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code == 200 and isinstance(body, dict) and body.get("status") == "success":
        data = body.get("data") or {}
        return {
            "ok": True,
            "sent": True,
            "number": number,
            "message_id": data.get("message_id"),
            "cost": data.get("cost"),
            "detail": "Sent",
        }
    code, detail = _bulksmsng_error(response)
    if code == _BULKSMSNG_DUPLICATE:
        return {"ok": True, "sent": False, "number": number, "detail": "Not re-sent: the same message went to this number a moment ago"}
    raise RuntimeError(f"BulkSMSNigeria SMS failed ({response.status_code}{', ' + code if code else ''}): {detail}")


def sms_balance() -> dict | None:
    """The provider's remaining balance, for the Master Admin screen. Only
    BulkSMSNigeria exposes it; None if unavailable or on any error."""
    if provider() != "bulksmsnigeria" or not settings.bulksmsnigeria_api_token:
        return None
    try:
        response = httpx.get(
            f"{_BULKSMSNG_BASE}/balance",
            headers={"Authorization": f"Bearer {settings.bulksmsnigeria_api_token}", "Accept": "application/json"},
            timeout=8,
        )
        if response.status_code != 200:
            return None
        balance = (response.json() or {}).get("balance") or {}
        return {"total_balance": balance.get("total_balance"), "currency": "NGN"}
    except Exception:
        logger.exception("Could not read the SMS balance")
        return None


def send_sms_detailed(raw_number: str, message: str) -> dict:
    """Sends (or, in dev, logs) one SMS and reports what happened. Raises on a
    provider failure so callers can log it without affecting the scan itself.
    """
    number = normalize_phone(raw_number)
    if number is None:
        logger.info("SMS skipped: unusable phone number %r", raw_number)
        return {"ok": False, "sent": False, "detail": "That phone number isn't usable"}

    if not sms_configured():
        logger.info("SMS (dev, not sent) to=%s text=%r", number, message)
        key = "BREVO_API_KEY" if provider() == "brevo" else "BULKSMSNIGERIA_API_TOKEN"
        return {"ok": True, "sent": False, "number": number, "detail": f"Not sent: {key} is not set (logged only)"}

    return _send_brevo(number, message) if provider() == "brevo" else _send_bulksmsnigeria(number, message)


def send_sms(raw_number: str, message: str) -> bool:
    """True if a send was attempted (or logged in dev), False if the number was unusable."""
    return bool(send_sms_detailed(raw_number, message)["ok"])
