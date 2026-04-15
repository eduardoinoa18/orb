"""Test-suite level conftest for ORB.

Patches jose.jwt.decode so that module-level TestClient instances (which
send "Bearer orb-test-token") receive a valid decoded payload without
needing a real secret key. The fake payload mirrors a master_owner account
so role-guard tests also pass.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# Sentinel token value injected via default_headers on module-level clients.
TEST_TOKEN = "orb-test-token"

_FAKE_TOKEN_PAYLOAD = {
    "sub": "00000000-0000-0000-0000-000000000001",
    "owner_id": "00000000-0000-0000-0000-000000000001",
    "email": "test@orb.local",
    "role": "master_owner",
}

_FAKE_OWNER_ROW = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "test@orb.local",
    "role": "master_owner",
    "is_superadmin": True,
    "plan": "business",
    "status": "active",
}


def _fake_jwt_decode(token, *args, **kwargs):
    """Always succeed — return fake master_owner payload for any token."""
    return _FAKE_TOKEN_PAYLOAD


def _make_mock_db():
    mock_db = MagicMock()
    mock_db.fetch_all.return_value = [_FAKE_OWNER_ROW]
    mock_db.fetch_one.return_value = _FAKE_OWNER_ROW
    mock_db.insert_one.return_value = _FAKE_OWNER_ROW
    mock_db.update_many.return_value = [_FAKE_OWNER_ROW]
    tbl = mock_db.client.table.return_value
    tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        _FAKE_OWNER_ROW
    ]
    tbl.select.return_value.execute.return_value.data = [_FAKE_OWNER_ROW]
    return mock_db


@pytest.fixture(autouse=True)
def _bypass_jwt_for_tests():
    """Patch jose.jwt.decode and SupabaseService for every test.

    This means:
    - The JWT middleware accepts *any* bearer token (including "orb-test-token")
    - get_current_owner() returns the fake master_owner row without hitting DB
    - Route handlers that call SupabaseService() get predictable mock data
    """
    mock_db = _make_mock_db()
    with (
        patch("jose.jwt.decode", side_effect=_fake_jwt_decode),
        patch("app.database.connection.SupabaseService", return_value=mock_db),
        patch("app.api.middleware.superadmin.SupabaseService", return_value=mock_db),
    ):
        yield mock_db
