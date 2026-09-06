"""Transactional email sending — ARCHITECTURE.md §7.

A separate channel from push notifications: welfare alerts need to reach a
guardian even if they haven't opened the app in weeks. Sent via Brevo's
HTTP API rather than raw SMTP — Railway (and most PaaS hosts) silently
firewall outbound SMTP ports (25/465/587) to stop their shared IP ranges
being used to relay spam, which surfaced as every send hanging until a
TimeoutError; a plain HTTPS API call has no such problem. (Previously
Postmark — switched after Postmark's account approval stalled.)

If BREVO_API_KEY isn't configured, the email is logged instead of sent, so
the welfare job can be exercised end-to-end in local dev without a real
provider.
"""

import base64
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(
    to_email: str,
    subject: str,
    body: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> None:
    """`attachments` is a list of (filename, content, content_type) — e.g.
    ("GPD-000123-202609.pdf", pdf_bytes, "application/pdf"), used by
    app/core/invoicing.py to attach a PDF invoice. Brevo infers the
    attachment's type from its filename extension, so content_type isn't
    sent — the parameter stays for signature compatibility with callers.
    """
    if not settings.brevo_api_key:
        names = [name for name, _, _ in attachments or []]
        logger.info("EMAIL (dev, not sent) to=%s subject=%r attachments=%s\n%s", to_email, subject, names, body)
        return

    payload = {
        "sender": {"email": settings.email_from_address},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    if attachments:
        payload["attachment"] = [
            {"name": name, "content": base64.b64encode(content).decode("ascii")}
            for name, content, _content_type in attachments
        ]

    response = httpx.post(
        _BREVO_API_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "api-key": settings.brevo_api_key,
        },
        json=payload,
        timeout=10,
    )
    if response.status_code not in (201, 202):
        raise RuntimeError(f"Brevo send failed ({response.status_code}): {response.text}")
