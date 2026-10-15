"""Brevo SMS adapter and the Master Admin SMS test endpoint."""

import httpx
import pytest

from app.core import sms
from app.core.config import settings


class _FakeResponse:
    def __init__(self, status=201, body=None):
        self.status_code = status
        self._body = body if body is not None else {"messageId": 12345, "remainingCredits": 41}
        self.content = b"x"
        self.text = str(self._body)

    def json(self):
        return self._body


def test_dev_mode_logs_instead_of_sending(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must not call Brevo without a key"))
    result = sms.send_sms_detailed("08148247438", "hi")
    assert result["ok"] is True and result["sent"] is False and result["number"] == "2348148247438"


def test_unusable_number_is_not_sent(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must not call Brevo for a bad number"))
    assert sms.send_sms_detailed("123", "hi")["ok"] is False
    assert sms.send_sms("123", "hi") is False


def test_brevo_request_shape(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "brevo_api_key", "secret-key")
    monkeypatch.setattr(settings, "sms_sender_id", "Guardian PD-App!!extra-long")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append((url, kw)) or _FakeResponse())

    result = sms.send_sms_detailed("+234 814 824 7438", "Ada arrived at school.")
    assert result == {
        "ok": True,
        "sent": True,
        "number": "2348148247438",
        "message_id": 12345,
        "remaining_credits": 41,
        "detail": "Sent",
    }
    url, kw = calls[0]
    assert url == "https://api.brevo.com/v3/transactionalSMS/sms"
    assert kw["headers"]["api-key"] == "secret-key"
    body = kw["json"]
    assert body["recipient"] == "2348148247438" and body["type"] == "transactional"
    assert body["sender"] == "GuardianPDA" and len(body["sender"]) <= 11  # letters/digits only, max 11
    assert body["unicodeEnabled"] is False


def test_unicode_names_enable_unicode(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "brevo_api_key", "k")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append(kw) or _FakeResponse())
    sms.send_sms_detailed("08148247438", "Ọlá arrived at school.")
    assert calls[0]["json"]["unicodeEnabled"] is True


def test_provider_error_raises(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(400, {"code": "not_enough_credits", "message": "no credits"}))
    with pytest.raises(RuntimeError, match="not_enough_credits"):
        sms.send_sms_detailed("08148247438", "hi")


def test_test_endpoint_requires_platform_login_and_reports_results(client, platform_auth_headers, monkeypatch):
    assert client.get("/platform/sms/status").status_code == 401
    assert client.post("/platform/sms/test", json={"to": "08148247438"}).status_code == 401

    monkeypatch.setattr(settings, "brevo_api_key", "")
    status = client.get("/platform/sms/status", headers=platform_auth_headers).json()
    assert status["configured"] is False and status["sender"] == "GuardianPD"

    dev = client.post("/platform/sms/test", json={"to": "08148247438"}, headers=platform_auth_headers)
    assert dev.status_code == 200 and dev.json()["sent"] is False

    assert client.post("/platform/sms/test", json={"to": "12"}, headers=platform_auth_headers).status_code == 400

    monkeypatch.setattr(settings, "brevo_api_key", "k")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(400, {"code": "unauthorized"}))
    failed = client.post("/platform/sms/test", json={"to": "08148247438"}, headers=platform_auth_headers)
    assert failed.status_code == 502 and "unauthorized" in failed.json()["detail"]
