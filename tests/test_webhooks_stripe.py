"""Tests for Stripe webhook handling."""

from unittest.mock import patch

import stripe as stripe_sdk

from app.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_stripe_webhook_processes_checkout_completed() -> None:
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_123",
                "subscription": "sub_123",
                "metadata": {"owner_id": "owner-1", "plan": "starter"},
            }
        },
    }

    with patch("app.api.routes.webhooks.get_settings") as mock_settings, \
         patch("app.api.routes.webhooks.stripe.Webhook.construct_event", return_value=event), \
         patch("app.api.routes.webhooks._update_owner_billing") as mock_update, \
         patch("app.api.routes.webhooks._provision_plan_agents", return_value=[{"name": "Commander"}]) as mock_provision, \
         patch("app.api.routes.webhooks._send_owner_billing_sms", return_value=True), \
         patch("app.api.routes.webhooks.log_activity"):
        mock_settings.return_value.stripe_secret_key = "sk_test_123"
        mock_settings.return_value.stripe_webhook_secret = "whsec_123"
        response = client.post("/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "sig_123"})

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["event_type"] == "checkout.session.completed"
    assert body["handler_result"]["success"] is True
    mock_update.assert_called_once()
    mock_provision.assert_called_once_with("owner-1", "starter")


def test_stripe_webhook_rejects_invalid_signature() -> None:
    with patch("app.api.routes.webhooks.get_settings") as mock_settings, \
         patch("app.api.routes.webhooks.stripe.Webhook.construct_event", side_effect=stripe_sdk.error.SignatureVerificationError("bad sig", "sig")):
        mock_settings.return_value.stripe_secret_key = "sk_test_123"
        mock_settings.return_value.stripe_webhook_secret = "whsec_123"
        response = client.post("/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "bad"})

    assert response.status_code == 401


def test_stripe_webhook_handles_subscription_deleted() -> None:
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"owner_id": "owner-1", "plan": "starter"}}},
    }

    with patch("app.api.routes.webhooks.get_settings") as mock_settings, \
         patch("app.api.routes.webhooks.stripe.Webhook.construct_event", return_value=event), \
         patch("app.api.routes.webhooks._update_owner_billing") as mock_update, \
         patch("app.api.routes.webhooks._deprovision_paid_agents", return_value=["agent-1"]) as mock_deprovision, \
         patch("app.api.routes.webhooks._send_owner_billing_sms", return_value=True), \
         patch("app.api.routes.webhooks.log_activity"):
        mock_settings.return_value.stripe_secret_key = "sk_test_123"
        mock_settings.return_value.stripe_webhook_secret = "whsec_123"
        response = client.post("/webhooks/stripe", content=b"{}", headers={"Stripe-Signature": "sig_123"})

    assert response.status_code == 200
    assert response.json()["handler_result"]["success"] is True
    mock_update.assert_called_once()
    mock_deprovision.assert_called_once_with("owner-1", 0)
