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

import base64
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_POSTMARK_API_URL = "https://api.postmarkapp.com/email"


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """`attachments` is a list of (filename, content, content_type) — e.g.
    ("GPD-000123-202609.pdf", pdf_bytes, "application/pdf"), used by
    app/core/invoicing.py to attach a PDF invoice.
    """
    if not settings.postmark_server_token:
        names = [name for name, _, _ in attachments or []]
        logger.info("EMAIL (dev, not sent) to=%s subject=%r attachments=%s\n%s", to_email, subject, names, body)
        return

    payload = {
        "From": settings.email_from_address,
        "To": to_email,
        "Subject": subject,
        "TextBody": body,
        "MessageStream": "outbound",
    }
    if attachments:
        payload["Attachments"] = [
            {"Name": name, "Content": base64.b64encode(content).decode("ascii"), "ContentType": content_type}
            for name, content, content_type in attachments
        ]

    response = httpx.post(
        _POSTMARK_API_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": settings.postmark_server_token,
        },
        json=payload,
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Postmark send failed ({response.status_code}): {response.text}")
