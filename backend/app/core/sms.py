"""SMS alerts for parents who don't have the app (or haven't registered a
phone for push) — an opt-in, per-school feature (School.sms_enabled) because
every message costs money.

Provider: Termii (https://developers.termii.com) — POST {base}/api/sms/send
with a JSON body carrying the api_key. If SMS_API_KEY isn't configured the
message is logged instead of sent, same fallback pattern as email/push, so
the scan flow works end-to-end in local dev.
"""

import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def normalize_phone(raw: str | None) -> str | None:
    """Nigerian-friendly normalization to Termii's "2348012345678" format
    (international, no plus). Accepts 0801..., +234801..., 234801..., or a
    bare 10-digit 801... number; any other "+"-prefixed international
    number is passed through. Returns None for anything unusable.
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


def send_sms(raw_number: str, message: str) -> bool:
    """Returns True if a send was attempted (or logged in dev), False if the
    number was unusable. Raises on a provider failure so the caller can log
    it without affecting the scan itself.
    """
    number = normalize_phone(raw_number)
    if number is None:
        logger.info("SMS skipped: unusable phone number %r", raw_number)
        return False

    if not settings.sms_api_key:
        logger.info("SMS (dev, not sent) to=%s text=%r", number, message)
        return True

    response = httpx.post(
        f"{settings.sms_base_url.rstrip('/')}/api/sms/send",
        json={
            "api_key": settings.sms_api_key,
            "to": number,
            "from": settings.sms_sender_id,
            "sms": message,
            "channel": settings.sms_channel,
            "type": "plain",
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"SMS send failed ({response.status_code}): {response.text[:200]}")
    return True
