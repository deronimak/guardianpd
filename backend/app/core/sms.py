"""SMS alerts for parents who don't have the app (or haven't registered a
phone for push) — an opt-in, per-school feature (School.sms_enabled) because
every message costs money.

Provider: Brevo's transactional SMS API, using the same BREVO_API_KEY as
email (app/core/email.py). The Brevo account needs SMS credits and a sender
name that Brevo/the Nigerian networks accept (SMS_SENDER_ID, up to 11 letters
or digits). If BREVO_API_KEY isn't configured the message is logged instead of
sent, so the scan flow works end-to-end in local dev.
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_SMS_URL = "https://api.brevo.com/v3/transactionalSMS/sms"


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
    """Brevo alphanumeric senders: letters and digits only, max 11."""
    return re.sub(r"[^A-Za-z0-9]", "", settings.sms_sender_id)[:11] or "GuardianPD"


def sms_configured() -> bool:
    return bool(settings.brevo_api_key)


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
        return {"ok": True, "sent": False, "number": number, "detail": "Not sent: BREVO_API_KEY is not set (logged only)"}

    response = httpx.post(
        _BREVO_SMS_URL,
        headers={"accept": "application/json", "content-type": "application/json", "api-key": settings.brevo_api_key},
        json={
            "sender": sender_name(),
            "recipient": number,
            "content": message,
            "type": "transactional",
            # Names with accents etc. need Unicode encoding or they arrive garbled.
            "unicodeEnabled": any(ord(ch) > 127 for ch in message),
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


def send_sms(raw_number: str, message: str) -> bool:
    """True if a send was attempted (or logged in dev), False if the number was unusable."""
    return bool(send_sms_detailed(raw_number, message)["ok"])
