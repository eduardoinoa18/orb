"""Tests for Stripe billing endpoints."""

from unittest.mock import patch

from jose import jwt

from config.settings import get_settings


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    token = jwt.encode({"sub": "billing-owner"}, settings.jwt_secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_create_checkout_returns_checkout_url(client) -> None:
    owner_row = {"id": "owner-1", "email": "owner@example.com"}

    with patch("app.api.routes.billing._get_owner", return_value=owner_row), \
         patch("app.api.routes.billing._build_price_map", return_value={("starter", "monthly"): "price_123"}), \
         patch("app.api.routes.billing._stripe_client_ready") as mock_stripe:
        mock_stripe.return_value.checkout.Session.create.return_value = {
            "id": "cs_test_123",
            "url": "https://checkout.stripe.test/session/cs_test_123",
        }
        response = client.post(
            "/billing/create-checkout",
            json={"plan": "starter", "billing": "monthly", "owner_id": "owner-1", "trial_days": 14},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.test")
    assert body["session_id"] == "cs_test_123"


def test_create_portal_session_returns_portal_url(client) -> None:
    owner_row = {"id": "owner-1", "stripe_customer_id": "cus_123"}

    with patch("app.api.routes.billing._get_owner", return_value=owner_row), \
         patch("app.api.routes.billing._stripe_client_ready") as mock_stripe:
        mock_stripe.return_value.billing_portal.Session.create.return_value = {
            "url": "https://billing.stripe.test/session/portal_123"
        }
        response = client.post(
            "/billing/create-portal-session",
            json={"owner_id": "owner-1"},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["portal_url"].startswith("https://billing.stripe.test")


def test_get_subscription_returns_owner_billing_snapshot(client) -> None:
    owner_row = {
        "id": "owner-1",
        "plan": "professional",
        "subscription_status": "active",
        "subscription_current_period_end": "2026-05-01T00:00:00+00:00",
        "trial_ends_at": "2026-04-14T00:00:00+00:00",
        "subscription_amount_cents": 14900,
        "stripe_card_last4": "4242",
        "stripe_customer_id": "cus_123",
        "stripe_subscription_id": "sub_123",
    }

    with patch("app.api.routes.billing._get_owner", return_value=owner_row):
        response = client.get("/billing/subscription/owner-1", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] == "professional"
    assert body["status"] == "active"
    assert body["amount"] == 14900
    assert body["card_last_4"] == "4242"


def test_billing_plans_returns_catalog(client) -> None:
    response = client.get("/billing/plans", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert "starter" in body["plans"]
    assert "professional" in body["plans"]
    assert "full_team" in body["plans"]


def test_billing_upgrade_preview_returns_prompt(client) -> None:
    owner_row = {"id": "owner-1", "plan": "starter"}

    with patch("app.api.routes.billing._get_owner", return_value=owner_row), \
         patch("app.api.routes.billing._addon_price_map", return_value={"rex": "price_rex_123"}):
        response = client.get("/billing/upgrade-preview/owner-1?agent=rex", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["required_plan"] == "professional"
    assert "included in the professional plan" in body["upgrade_prompt"].lower()


def test_create_addon_checkout_returns_checkout_url(client) -> None:
    owner_row = {"id": "owner-1", "stripe_customer_id": "cus_123"}

    with patch("app.api.routes.billing._get_owner", return_value=owner_row), \
         patch("app.api.routes.billing._addon_price_map", return_value={"rex": "price_rex_123"}), \
         patch("app.api.routes.billing._stripe_client_ready") as mock_stripe:
        mock_stripe.return_value.checkout.Session.create.return_value = {
            "id": "cs_addon_123",
            "url": "https://checkout.stripe.test/session/cs_addon_123",
        }
        response = client.post(
            "/billing/create-addon-checkout",
            json={"owner_id": "owner-1", "agent": "rex"},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "rex"
    assert body["checkout_url"].startswith("https://checkout.stripe.test")
