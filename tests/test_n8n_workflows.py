"""Tests for N8N workflow integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from integrations.n8n_workflows import (
    get_n8n_base_url,
    get_webhook_url,
    trigger_workflow,
    get_workflow_info,
    list_workflows,
    handle_workflow_complete,
)


class TestN8NConfiguration:
    """Test N8N configuration and URL generation."""

    def test_get_webhook_url_valid_workflow(self):
        """Construct webhook URL for known workflow."""
        with patch("integrations.n8n_workflows.get_n8n_base_url") as mock_get_url:
            mock_get_url.return_value = "https://app.n8n.cloud"
            url = get_webhook_url("lead_nurture_start")
            assert "webhook" in url
            assert "lead_nurture_start" in url

    def test_list_workflows(self):
        """List all configured workflows."""
        workflows = list_workflows()
        assert len(workflows) >= 4
        assert "30_day_nurture" in workflows
        assert "hot_lead_urgent" in workflows
        assert "weekly_metrics_report" in workflows
        assert "daily_cost_alert" in workflows

    def test_get_workflow_info(self):
        """Get metadata for a specific workflow."""
        info = get_workflow_info("30_day_nurture")
        assert info is not None
        assert "webhook_path" in info
        assert info["webhook_path"] == "lead_nurture_start"
        assert "required_fields" in info
        assert "lead_email" in info["required_fields"]

    def test_get_workflow_info_not_found(self):
        """Return None for unknown workflows."""
        info = get_workflow_info("nonexistent_workflow")
        assert info is None


class TestWorkflowTriggering:
    """Test triggering N8N workflows."""

    @pytest.mark.asyncio
    async def test_trigger_workflow_success(self):
        """Successfully trigger a workflow."""
        payload = {
            "lead_phone": "+1-555-0100",
            "lead_email": "prospect@example.com",
            "lead_name": "Jane Doe",
            "owner_phone": "+1-555-8888",
        }

        with patch("integrations.n8n_workflows.httpx.AsyncClient") as mock_client:
            with patch("integrations.n8n_workflows.get_webhook_url") as mock_get_url:
                mock_get_url.return_value = "https://app.n8n.cloud/webhook/lead_nurture_start"
                
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"status": "accepted"}
                mock_response.text = '{"status": "accepted"}'
                mock_response.raise_for_status = MagicMock()  # sync method

                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                result = await trigger_workflow("30_day_nurture", payload)

                assert result["success"] is True
                assert result["workflow"] == "30_day_nurture"
                assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_trigger_workflow_unknown(self):
        """Reject triggering unknown workflows."""
        with pytest.raises(KeyError):
            await trigger_workflow("unknown_workflow", {})

    @pytest.mark.asyncio
    async def test_trigger_workflow_missing_required_field(self):
        """Reject workflows with missing required fields."""
        payload = {
            "lead_email": "prospect@example.com",
            # Missing: lead_phone, lead_name, owner_phone
        }

        with pytest.raises(ValueError, match="missing fields"):
            await trigger_workflow("30_day_nurture", payload)

    @pytest.mark.asyncio
    async def test_trigger_workflow_network_error(self):
        """Handle network errors gracefully."""
        payload = {
            "lead_phone": "+1-555-0100",
            "lead_email": "prospect@example.com",
            "lead_name": "Jane Doe",
            "owner_phone": "+1-555-8888",
        }

        with patch("integrations.n8n_workflows.httpx.AsyncClient") as mock_client:
            with patch("integrations.n8n_workflows.get_webhook_url"):
                import httpx

                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    side_effect=httpx.ConnectError("Connection refused")
                )

                result = await trigger_workflow("30_day_nurture", payload)

                assert result["success"] is False
                assert "error" in result


class TestWorkflowCompletion:
    """Test processing webhooks back from N8N."""

    def test_handle_workflow_complete_nurture(self):
        """Process completion webhook for nurture sequence."""
        data = {
            "lead_email": "prospect@example.com",
            "sequence_count": 3,
        }

        result = handle_workflow_complete(
            "sequence_complete",
            "30_day_nurture",
            data,
        )

        assert result["success"] is True

    def test_handle_workflow_complete_hot_lead(self):
        """Process completion webhook for hot lead sequence."""
        data = {
            "lead_email": "hotprospect@example.com",
            "temperature": 9,
        }

        result = handle_workflow_complete(
            "sequence_complete",
            "hot_lead_urgent",
            data,
        )

        assert result["success"] is True

    def test_handle_workflow_complete_unknown(self):
        """Handle unknown workflow type gracefully."""
        result = handle_workflow_complete(
            "sequence_complete",
            "unknown_workflow",
            {},
        )

        assert result["success"] is False


class TestWorkflowIntegration:
    """Test end-to-end workflow triggering and completion."""

    @pytest.mark.asyncio
    async def test_cold_lead_flow(self):
        """Test full flow: trigger 30-day nurture for cold lead."""
        cold_lead = {
            "phone": "+1-555-0100",
            "email": "newprospect@example.com",
            "name": "Bob Smith",
        }

        payload = {
            "lead_phone": cold_lead["phone"],
            "lead_email": cold_lead["email"],
            "lead_name": cold_lead["name"],
            "owner_phone": "+1-555-9999",
        }

        with patch("integrations.n8n_workflows.httpx.AsyncClient") as mock_client:
            with patch("integrations.n8n_workflows.get_webhook_url"):
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"status": "queued"}
                mock_response.text = '{"status": "queued"}'
                mock_response.raise_for_status = MagicMock()  # sync method

                mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                    return_value=mock_response
                )

                # Trigger the workflow
                result = await trigger_workflow("30_day_nurture", payload)

                assert result["success"] is True
                assert result["workflow"] == "30_day_nurture"

                # Simulate workflow completion
                completion = handle_workflow_complete(
                    "sequence_complete",
                    "30_day_nurture",
                    {"lead_email": cold_lead["email"]},
                )

                assert completion["success"] is True
