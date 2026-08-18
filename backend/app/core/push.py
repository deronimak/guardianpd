"""Push notification sending — ARCHITECTURE.md §5 point 5.

Uses Firebase Cloud Messaging via the firebase-admin SDK. Requires a real
Firebase project's service-account credentials — something only you can
create, via the Firebase console — set as FIREBASE_CREDENTIALS_JSON (the
full JSON key file contents, as a single env var value).

Until that's configured, sends are logged instead, same fallback pattern
as app/core/email.py, so the scan flow works end-to-end in local dev
without a real Firebase project.
"""

import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_firebase_app = None
_firebase_init_attempted = False


def _get_firebase_app():
    global _firebase_app, _firebase_init_attempted
    if _firebase_init_attempted:
        return _firebase_app
    _firebase_init_attempted = True

    if not settings.firebase_credentials_json:
        return None

    import firebase_admin
    from firebase_admin import credentials

    cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


def send_push(device_token: str, title: str, body: str) -> None:
    app = _get_firebase_app()
    if app is None:
        logger.info("PUSH (dev, not sent) to=%s title=%r body=%r", device_token, title, body)
        return

    from firebase_admin import messaging

    message = messaging.Message(
        token=device_token,
        notification=messaging.Notification(title=title, body=body),
    )
    messaging.send(message, app=app)
