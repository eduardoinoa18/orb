from __future__ import annotations

from integrations import resend_client


def test_send_resend_email_returns_skip_when_provider_raises(monkeypatch):
    class _Boom:
        @staticmethod
        def send(_payload):
            raise RuntimeError("provider error")

    monkeypatch.setattr(resend_client.resend, "Emails", _Boom)
    monkeypatch.setattr(resend_client.resend, "api_key", "", raising=False)
    monkeypatch.setattr(
        resend_client,
        "get_settings",
        lambda: type("Settings", (), {"resend_api_key": "test-key"})(),
    )

    result = resend_client.send_resend_email(
        to_email="test@example.com",
        subject="subject",
        html="<p>hello</p>",
    )

    assert result["sent"] is False
    assert result["skipped"] is True
    assert "Resend send failed" in result["reason"]
