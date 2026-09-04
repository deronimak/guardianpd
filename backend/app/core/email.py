"""Transactional email sending — ARCHITECTURE.md §7.

A separate channel from push notifications: welfare alerts need to reach a
guardian even if they haven't opened the app in weeks. Sent via Postmark's
HTTP API rather than raw SMTP — Railway (and most PaaS hosts) silently
firewall outbound SMTP ports (25/465/587) to stop their shared IP ranges
being used to relay spam, which surfaced as every send hanging until a
TimeoutError; a plain HTTPS API call has no such problem.

If POSTMARK_SERVER_TOKEN isn't configured, the email is logged instead of
sent, so the welfare job can be exercised end-to-end in local dev without a
real provider.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_POSTMARK_API_URL = "https://api.postmarkapp.com/email"


def send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.postmark_server_token:
        logger.info("EMAIL (dev, not sent) to=%s subject=%r\n%s", to_email, subject, body)
        return

    response = httpx.post(
        _POSTMARK_API_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": settings.postmark_server_token,
        },
        json={
            "From": settings.email_from_address,
            "To": to_email,
            "Subject": subject,
            "TextBody": body,
            "MessageStream": "outbound",
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Postmark send failed ({response.status_code}): {response.text}")
