"""SMS adapter (BulkSMSNigeria by default, Brevo optional) and the Master Admin
SMS test endpoint."""

import httpx
import pytest

from app.core import sms
from app.core.config import settings


class _FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.content = b"x"
        self.text = str(self._body)

    def json(self):
        return self._body


_BSNG_OK = {
    "status": "success",
    "code": "BSNG-0000",
    "message": "Message sent successfully",
    "data": {"message_id": "abc-123", "cost": 5.0, "currency": "NGN", "recipients_count": 1},
}


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setattr(settings, "sms_provider", "bulksmsnigeria")
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "")
    monkeypatch.setattr(settings, "brevo_api_key", "")
    monkeypatch.setattr(settings, "sms_gateway", "direct-refund")
    monkeypatch.setattr(settings, "sms_sender_id", "GuardianPD")


def test_dev_mode_logs_instead_of_sending(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must not call the provider without a token"))
    result = sms.send_sms_detailed("08148247438", "hi")
    assert result["ok"] is True and result["sent"] is False and result["number"] == "2348148247438"
    assert "BULKSMSNIGERIA_API_TOKEN" in result["detail"]


def test_unusable_number_is_not_sent(monkeypatch):
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must not call the provider for a bad number"))
    assert sms.send_sms_detailed("123", "hi")["ok"] is False
    assert sms.send_sms("123", "hi") is False


def test_bulksmsnigeria_request_shape(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "secret-token")
    monkeypatch.setattr(settings, "sms_sender_id", "Guardian PD-App!!extra-long")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append((url, kw)) or _FakeResponse(200, _BSNG_OK))

    result = sms.send_sms_detailed("+234 814 824 7438", "Ada arrived at school.")
    assert result == {
        "ok": True,
        "sent": True,
        "number": "2348148247438",
        "message_id": "abc-123",
        "cost": 5.0,
        "detail": "Sent",
    }
    url, kw = calls[0]
    assert url == "https://www.bulksmsnigeria.com/api/v2/sms"
    assert kw["headers"]["Authorization"] == "Bearer secret-token"
    body = kw["json"]
    assert body["to"] == "2348148247438" and body["body"] == "Ada arrived at school."
    assert body["gateway"] == "direct-refund" and body["unicode"] is False
    assert body["from"] == "GuardianPDA" and len(body["from"]) <= 11  # letters/digits only, max 11


def test_unicode_names_enable_unicode(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append(kw) or _FakeResponse(200, _BSNG_OK))
    sms.send_sms_detailed("08148247438", "Ọlá arrived at school.")
    assert calls[0]["json"]["unicode"] is True


def test_provider_errors_raise_with_the_code(monkeypatch):
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    error = {"status": "error", "code": "BSNG-3000", "error": {"message": "Insufficient balance", "code": "BSNG-3000"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(402, error))
    with pytest.raises(RuntimeError, match="BSNG-3000.*Insufficient balance"):
        sms.send_sms_detailed("08148247438", "hi")


def test_sender_not_approved_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    error = {"status": "error", "error": {"message": "Sender ID not registered", "code": "BSNG-2011"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(403, error))
    with pytest.raises(RuntimeError, match="BSNG-2011"):
        sms.send_sms_detailed("08148247438", "hi")


def test_duplicate_message_is_not_an_error(monkeypatch):
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    dup = {"status": "error", "code": "BSNG-2012", "error": {"message": "Duplicate message", "code": "BSNG-2012"}}
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(409, dup))
    result = sms.send_sms_detailed("08148247438", "hi")
    assert result["ok"] is True and result["sent"] is False and "moment ago" in result["detail"]


def test_balance_is_read_from_the_provider(monkeypatch):
    assert sms.sms_balance() is None  # no token
    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _FakeResponse(200, {"balance": {"total_balance": 9884.24, "sms_wallet": "5.01"}})
    )
    assert sms.sms_balance() == {"total_balance": 9884.24, "currency": "NGN"}
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _FakeResponse(500, {}))
    assert sms.sms_balance() is None


def test_brevo_remains_available_as_an_option(monkeypatch):
    calls = []
    monkeypatch.setattr(settings, "sms_provider", "brevo")
    monkeypatch.setattr(settings, "brevo_api_key", "brevo-key")
    monkeypatch.setattr(
        httpx, "post", lambda url, **kw: calls.append((url, kw)) or _FakeResponse(201, {"messageId": 7, "remainingCredits": 41})
    )
    result = sms.send_sms_detailed("08148247438", "hi")
    assert result["sent"] is True and result["remaining_credits"] == 41
    assert calls[0][0] == "https://api.brevo.com/v3/transactionalSMS/sms"
    assert calls[0][1]["headers"]["api-key"] == "brevo-key"


def test_test_endpoint_requires_platform_login_and_reports_results(client, platform_auth_headers, monkeypatch):
    assert client.get("/platform/sms/status").status_code == 401
    assert client.post("/platform/sms/test", json={"to": "08148247438"}).status_code == 401

    status = client.get("/platform/sms/status", headers=platform_auth_headers).json()
    assert status["configured"] is False and status["provider"] == "bulksmsnigeria" and status["balance"] is None

    dev = client.post("/platform/sms/test", json={"to": "08148247438"}, headers=platform_auth_headers)
    assert dev.status_code == 200 and dev.json()["sent"] is False

    assert client.post("/platform/sms/test", json={"to": "12"}, headers=platform_auth_headers).status_code == 400

    monkeypatch.setattr(settings, "bulksmsnigeria_api_token", "t")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeResponse(401, {"status": "error", "error": {"message": "Invalid token", "code": "BSNG-1000"}}))
    failed = client.post("/platform/sms/test", json={"to": "08148247438"}, headers=platform_auth_headers)
    assert failed.status_code == 502 and "Invalid token" in failed.json()["detail"]
