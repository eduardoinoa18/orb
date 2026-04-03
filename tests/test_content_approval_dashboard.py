"""Tests for content approval dashboard API additions."""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from app.api.main import app

client = TestClient(app)


def test_list_pending_content_returns_drafts():
    """GET /content/pending should return all draft content for an owner."""
    mock_rows = [
        {"id": "c1", "status": "draft", "content_type": "listing_post", "owner_id": "o1"},
        {"id": "c2", "status": "draft", "content_type": "market_update", "owner_id": "o1"},
    ]
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = mock_rows
        response = client.get("/agents/nova/content/pending?owner_id=o1")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["total"] == 2
    assert len(data["content"]) == 2


def test_list_pending_content_respects_limit():
    """GET /content/pending should respect the limit query param."""
    mock_rows = [{"id": f"c{i}", "status": "draft", "owner_id": "o1"} for i in range(50)]
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = mock_rows
        response = client.get("/agents/nova/content/pending?owner_id=o1&limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 5
    assert data["total"] == 50  # Full backlog count


def test_get_content_item_returns_single_item():
    """GET /content/{content_id} should return a single content row."""
    mock_rows = [{"id": "c1", "status": "draft", "body": "Great home in Miami!"}]
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = mock_rows
        response = client.get("/agents/nova/content/c1")

    assert response.status_code == 200
    assert response.json()["id"] == "c1"


def test_get_content_item_returns_404_when_not_found():
    """GET /content/{content_id} should 404 on unknown content_id."""
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = []
        response = client.get("/agents/nova/content/unknown-id")

    assert response.status_code == 404


def test_batch_approve_content_approves_all():
    """POST /content/batch-approve should queue all given ids."""
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.update_many.return_value = [{"id": "c1"}]
        response = client.post(
            "/agents/nova/content/batch-approve",
            json={"content_ids": ["c1", "c2", "c3"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["approved_count"] == 3
    assert len(data["approved"]) == 3
    assert len(data["failed"]) == 0


def test_batch_approve_content_handles_partial_failures():
    """POST /content/batch-approve should report partial failures."""
    call_count = 0

    def mock_update(table, filters, payload):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            return []  # Simulate not found on second item
        return [{"id": filters["id"]}]

    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.update_many.side_effect = mock_update
        response = client.post(
            "/agents/nova/content/batch-approve",
            json={"content_ids": ["c1", "c2", "c3"]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["approved_count"] == 2
    assert len(data["failed"]) == 1


def test_batch_approve_rejects_empty_list():
    """POST /content/batch-approve should 422 on empty content_ids."""
    response = client.post(
        "/agents/nova/content/batch-approve",
        json={"content_ids": []},
    )
    assert response.status_code == 422


def test_reschedule_content_updates_date():
    """PUT /content/{content_id}/reschedule should update scheduled_for."""
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = [{"id": "c1", "status": "queued"}]
        mock_db_cls.return_value.update_many.return_value = [{"id": "c1"}]
        response = client.put(
            "/agents/nova/content/c1/reschedule",
            json={"scheduled_for": "2026-05-01T10:00:00Z"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content_id"] == "c1"
    assert "2026-05-01" in data["scheduled_for"]


def test_reschedule_content_returns_404_when_not_found():
    """PUT /content/{content_id}/reschedule should 404 on unknown id."""
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = []
        response = client.put(
            "/agents/nova/content/no-such/reschedule",
            json={"scheduled_for": "2026-05-01T10:00:00Z"},
        )

    assert response.status_code == 404


def test_reschedule_rejects_already_published():
    """PUT /content/{content_id}/reschedule should 409 if status is published."""
    with patch("app.api.routes.content.SupabaseService") as mock_db_cls:
        mock_db_cls.return_value.fetch_all.return_value = [{"id": "c1", "status": "published"}]
        response = client.put(
            "/agents/nova/content/c1/reschedule",
            json={"scheduled_for": "2026-05-01T10:00:00Z"},
        )

    assert response.status_code == 409
