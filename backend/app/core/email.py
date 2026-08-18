"""Transactional email sending — ARCHITECTURE.md §7.

A separate channel from push notifications: welfare alerts need to reach a
guardian even if they haven't opened the app in weeks. Plain SMTP works
with any transactional provider (SendGrid, SES, Postmark, or a local dev
catcher like MailHog) without a vendor-specific SDK dependency.

If SMTP_HOST isn't configured, the email is logged instead of sent, so the
welfare job can be exercised end-to-end in local dev without a real
provider.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.info("EMAIL (dev, not sent) to=%s subject=%r\n%s", to_email, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)
