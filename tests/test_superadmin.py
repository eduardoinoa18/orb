"""Tests for superadmin middleware and admin routes."""

from unittest.mock import MagicMock, patch

from jose import jwt

from config.settings import get_settings


def _auth_headers(payload: dict | None = None) -> dict[str, str]:
    settings = get_settings()
    token_payload = {"sub": "owner-1", **(payload or {})}
    token = jwt.encode(token_payload, settings.jwt_secret_key, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def test_admin_home_requires_superadmin(client) -> None:
    fake_db = MagicMock()
    fake_db.fetch_all.side_effect = [[{"id": "owner-1", "email": "owner@example.com", "role": "user", "is_superadmin": False}]]

    with patch("app.api.middleware.superadmin.SupabaseService", return_value=fake_db):
        response = client.get("/admin/", headers=_auth_headers({"owner_id": "owner-1"}))

    assert response.status_code == 403


def test_admin_users_returns_rows_for_superadmin(client) -> None:
    fake_db = MagicMock()
    fake_db.fetch_all.side_effect = [
        [{"id": "owner-1", "email": "owner@example.com", "role": "superadmin", "is_superadmin": True}],
        [
            {"id": "owner-1", "email": "owner@example.com", "name": "Edu", "role": "superadmin", "is_superadmin": True, "plan": "superadmin"},
            {"id": "owner-2", "email": "user@example.com", "name": "User", "role": "user", "plan": "starter"},
        ],
        [
            {"owner_id": "owner-1", "id": "a-1"},
            {"owner_id": "owner-2", "id": "a-2"},
            {"owner_id": "owner-2", "id": "a-3"},
        ],
        [
            {"owner_id": "owner-2", "cost_cents": 100, "created_at": "2026-04-03T08:00:00Z"},
        ],
    ]

    with patch("app.api.middleware.superadmin.SupabaseService", return_value=fake_db), patch(
        "app.api.routes.superadmin.SupabaseService", return_value=fake_db
    ):
        response = client.get("/admin/users", headers=_auth_headers({"owner_id": "owner-1"}))

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert any(item["email"] == "user@example.com" for item in body["users"])


def test_admin_plan_update_logs_override(client) -> None:
    fake_db = MagicMock()
    fake_db.fetch_all.side_effect = [[{"id": "owner-1", "email": "owner@example.com", "role": "superadmin", "is_superadmin": True}]]
    fake_db.update_many.return_value = [{"id": "owner-2"}]

    with patch("app.api.middleware.superadmin.SupabaseService", return_value=fake_db), patch(
        "app.api.routes.superadmin.SupabaseService", return_value=fake_db
    ):
        response = client.put(
            "/admin/users/owner-2/plan",
            json={"plan": "professional", "reason": "Support migration"},
            headers=_auth_headers({"owner_id": "owner-1"}),
        )

    assert response.status_code == 200
    assert response.json()["plan"] == "professional"
    fake_db.log_activity.assert_called_once()


def test_admin_home_renders_html_for_browser_accept(client) -> None:
    fake_db = MagicMock()
    fake_db.fetch_all.side_effect = [[{"id": "owner-1", "email": "owner@example.com", "role": "superadmin", "is_superadmin": True}]]

    with patch("app.api.middleware.superadmin.SupabaseService", return_value=fake_db):
        response = client.get(
            "/admin/",
            headers={**_auth_headers({"owner_id": "owner-1"}), "Accept": "text/html"},
        )

    assert response.status_code == 200
    assert "ORB Admin Control Center" in response.text


def test_admin_feature_flags_read_and_update(client) -> None:
    fake_db = MagicMock()
    fake_db.fetch_all.side_effect = [
        [{"id": "owner-1", "email": "owner@example.com", "role": "superadmin", "is_superadmin": True}],
        [{"flag_name": "custom_agent_builder", "is_enabled": True}],
        [{"id": "owner-1", "email": "owner@example.com", "role": "superadmin", "is_superadmin": True}],
    ]
    fake_db.update_many.return_value = [
        {
            "flag_name": "custom_agent_builder",
            "is_enabled": False,
            "enabled_for_plans": ["professional"],
            "description": "toggle",
        }
    ]

    with patch("app.api.middleware.superadmin.SupabaseService", return_value=fake_db), patch(
        "app.api.routes.superadmin.SupabaseService", return_value=fake_db
    ):
        read_response = client.get("/admin/feature-flags", headers=_auth_headers({"owner_id": "owner-1"}))
        update_response = client.put(
            "/admin/feature-flags/custom_agent_builder",
            json={
                "is_enabled": False,
                "enabled_for_plans": ["professional"],
                "description": "toggle",
            },
            headers=_auth_headers({"owner_id": "owner-1"}),
        )

    assert read_response.status_code == 200
    assert read_response.json()["count"] == 1
    assert update_response.status_code == 200
    assert update_response.json()["flag"]["is_enabled"] is False
