from unittest.mock import MagicMock, patch

from agents.platform_scan import PlatformScanner


def test_scan_integration_health_only_blocks_on_required_integrations() -> None:
    scanner = PlatformScanner()

    with patch.dict(
        "os.environ",
        {
            "ANTHROPIC_API_KEY": "sk-ant-real",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_KEY": "service-key",
        },
        clear=True,
    ):
        result = scanner.scan_integration_health()

    assert result["all_healthy"] is True
    assert result["failed"] == []
    assert "openai" in result["missing_optional"]


def test_scan_pending_requests_skips_missing_table_without_error_noise() -> None:
    scanner = PlatformScanner()
    fake_db = MagicMock()
    fake_db.client.table.return_value.select.return_value.in_.return_value.order.return_value.limit.return_value.execute.side_effect = RuntimeError(
        "{'message': \"Could not find the table 'public.platform_requests' in the schema cache\", 'code': 'PGRST205'}"
    )
    scanner._db = fake_db

    result = scanner.scan_pending_requests()

    assert result["total"] == 0
    assert result["urgent"] == 0
    assert result["available"] is False
