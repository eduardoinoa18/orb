"""Tests for the expanded WhatsApp Commander module."""

from unittest.mock import MagicMock, patch


def test_send_whatsapp_message_formats_to_correctly() -> None:
    """send_whatsapp_message should prepend whatsapp: to both numbers."""
    with patch("integrations.twilio_client.get_twilio_client") as mock_get_client, \
         patch("integrations.whatsapp_commander.get_settings") as mock_settings:
        settings = MagicMock()
        settings.resolve.return_value = "+14155238886"
        mock_settings.return_value = settings

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from integrations.whatsapp_commander import send_whatsapp_message
        result = send_whatsapp_message(to_phone="+15555550199", message="Hello!")

    assert result is True
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["to"] == "whatsapp:+15555550199"


def test_handle_incoming_help_command_returns_help_text() -> None:
    from integrations.whatsapp_commander import WhatsAppCommander, HELP_TEXT

    with patch("integrations.whatsapp_commander._find_owner_by_phone") as mock_find:
        mock_find.return_value = {"id": "owner-123"}
        result = WhatsAppCommander.handle_incoming(from_number="+15555550100", body="help")

    assert result == HELP_TEXT


def test_handle_incoming_status_calls_status_summary() -> None:
    from integrations.whatsapp_commander import WhatsAppCommander

    with patch("integrations.whatsapp_commander._find_owner_by_phone") as mock_find, \
         patch("integrations.whatsapp_commander._get_status_summary") as mock_status:
        mock_find.return_value = {"id": "owner-456"}
        mock_status.return_value = "*ORB Status*\n• Max: active"

        result = WhatsAppCommander.handle_incoming(from_number="+15555550101", body="STATUS")

    mock_status.assert_called_once_with("owner-456")
    assert "ORB Status" in result


def test_handle_incoming_stop_pauses_agents() -> None:
    from integrations.whatsapp_commander import WhatsAppCommander

    with patch("integrations.whatsapp_commander._find_owner_by_phone") as mock_find, \
         patch("integrations.whatsapp_commander._pause_all_agents") as mock_pause:
        mock_find.return_value = {"id": "owner-789"}
        result = WhatsAppCommander.handle_incoming(from_number="+15555550102", body="STOP")

    mock_pause.assert_called_once_with("owner-789")
    assert "paused" in result.lower()


def test_handle_incoming_resume_resumes_agents() -> None:
    from integrations.whatsapp_commander import WhatsAppCommander

    with patch("integrations.whatsapp_commander._find_owner_by_phone") as mock_find, \
         patch("integrations.whatsapp_commander._resume_all_agents") as mock_resume:
        mock_find.return_value = {"id": "owner-321"}
        result = WhatsAppCommander.handle_incoming(from_number="+15555550103", body="resume")

    mock_resume.assert_called_once_with("owner-321")
    assert "online" in result.lower() or "restart" in result.lower()


def test_handle_incoming_unregistered_owner_returns_signup_message() -> None:
    from integrations.whatsapp_commander import WhatsAppCommander

    with patch("integrations.whatsapp_commander._find_owner_by_phone", return_value=None), \
         patch("integrations.whatsapp_commander.get_settings") as mock_settings:
        settings = MagicMock()
        settings.resolve.return_value = "app.orb.com"
        mock_settings.return_value = settings

        result = WhatsAppCommander.handle_incoming(from_number="+19999999999", body="STATUS")

    assert "not registered" in result.lower() or "sign up" in result.lower()


def test_format_hot_lead_alert_contains_required_fields() -> None:
    from integrations.whatsapp_commander import format_hot_lead_alert

    msg = format_hot_lead_alert(
        lead_name="John Doe",
        address="123 Main St",
        score=9,
        insight="Motivated seller",
        price="$250,000",
    )
    assert "John Doe" in msg
    assert "9/10" in msg
    assert "Motivated seller" in msg
    assert "$250,000" in msg
    assert "YES" in msg


def test_backward_compat_help_returns_help_text() -> None:
    """The legacy handle_incoming_whatsapp_message should still return HELP_TEXT for HELP."""
    from integrations.whatsapp_commander import handle_incoming_whatsapp_message, HELP_TEXT

    result = handle_incoming_whatsapp_message(from_number="+15555550200", message_body="HELP")
    assert result is not None
    assert result["handled"] is True
    assert result["message"] == HELP_TEXT


def test_backward_compat_yes_returns_none_for_trade_path() -> None:
    """YES must return None so the trade-reply handler can process it."""
    from integrations.whatsapp_commander import handle_incoming_whatsapp_message

    result = handle_incoming_whatsapp_message(from_number="+15555550201", message_body="YES")
    assert result is None
