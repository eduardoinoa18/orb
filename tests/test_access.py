"""Tests for access context and master-owner bootstrap routes."""

from __future__ import annotations

from unittest.mock import patch

from jose import jwt

from config.settings import get_settings


def _auth_headers(payload: dict[str, str] | None = None) -> dict[str, str]:
    settings = get_settings()
    token_payload = {"sub": "test-user", **(payload or {})}
    token = jwt.encode(token_payload, settings.jwt_secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_access_context_returns_role(client) -> None:
    response = client.get("/access/context", headers=_auth_headers({"role": "admin", "owner_id": "owner-1"}))
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "admin"
    assert body["owner_id"] == "owner-1"


def test_access_bootstrap_master_requires_role(client) -> None:
    response = client.post(
        "/access/bootstrap-master",
        json={"owner_id": "owner-2"},
        headers=_auth_headers({"role": "standard_user"}),
    )
    assert response.status_code == 403


def test_access_bootstrap_master_marks_owner(client) -> None:
    with patch("app.api.routes.access.mark_master_owner", return_value={"id": "owner-2", "billing_exempt": True}):
        response = client.post(
            "/access/bootstrap-master",
            json={"owner_id": "owner-2"},
            headers=_auth_headers({"role": "master_owner"}),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["owner"]["billing_exempt"] is True
