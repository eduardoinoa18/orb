"""Pytest configuration for ORB.

This file tells pytest where to find our Python packages.
Because our top-level package is called 'platform' (which shadows Python's
standard-library 'platform' module), we explicitly insert the project root
at the front of sys.path so the local package always wins.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.api.main import app

# Make sure `orb-platform/` is the first place Python looks for imports.
# We renamed 'platform/' to 'app/' to avoid shadowing Python's built-in
# 'platform' stdlib module (which caused pytest to crash at startup).
sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Shared test JWT secret — used to sign tokens for authed_client fixture.
# The middleware will accept this because settings.jwt_secret_key falls back
# to a predictable development default when DATABASE_URL is absent.
# ---------------------------------------------------------------------------
_TEST_OWNER_ID = "00000000-0000-0000-0000-000000000001"
_TEST_EMAIL = "test@orb.local"
_TEST_OWNER_ROW = {
    "id": _TEST_OWNER_ID,
    "email": _TEST_EMAIL,
    "role": "master_owner",
    "is_superadmin": True,
    "plan": "business",
    "status": "active",
}


def _make_test_token(secret: str) -> str:
    """Create a signed HS256 JWT accepted by jwt_auth_middleware."""
    return jwt.encode(
        {
            "sub": _TEST_OWNER_ID,
            "owner_id": _TEST_OWNER_ID,
            "email": _TEST_EMAIL,
            "role": "master_owner",
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def client():
    """FastAPI TestClient for making HTTP requests to the app (unauthenticated public paths)."""
    return TestClient(app, headers={"Authorization": "Bearer orb-test-token"})


@pytest.fixture
def authed_client():
    """TestClient with a valid bearer token injected.

    Patches SupabaseService so tests never need a live DB.
    The token_payload is set by the real JWT middleware after decoding.
    """
    from config.settings import get_settings

    settings = get_settings()
    token = _make_test_token(settings.jwt_secret_key)
    auth_header = {"Authorization": f"Bearer {token}"}

    mock_db = MagicMock()
    mock_db.fetch_all.return_value = [_TEST_OWNER_ROW]
    mock_db.fetch_one.return_value = _TEST_OWNER_ROW
    mock_db.insert_one.return_value = _TEST_OWNER_ROW
    mock_db.update_many.return_value = [_TEST_OWNER_ROW]
    mock_db.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [_TEST_OWNER_ROW]

    with patch("app.database.connection.SupabaseService", return_value=mock_db):
        tc = TestClient(app, headers=auth_header)
        yield tc
