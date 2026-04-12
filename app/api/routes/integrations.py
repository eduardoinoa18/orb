"""Integration Hub — module for connecting third-party services.

Endpoints for managing API keys, testing connections, and monitoring
integration health across all providers (Twilio, Anthropic, Stripe, etc.).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.database.connection import DatabaseConnectionError, SupabaseService
from integrations.encryption import EncryptionError, get_encryption_manager

logger = logging.getLogger("orb.integrations")

router = APIRouter(prefix="/integrations", tags=["Integration Hub"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class CredentialPayload(BaseModel):
    """Request body for connecting an integration."""
    credentials: dict[str, str] = Field(..., description="Field name -> encrypted value pairs")


class IntegrationStatus(BaseModel):
    """Status of an integration for a specific owner."""
    provider_slug: str
    status: str  # 'connected', 'disconnected', 'error', 'pending'
    last_tested_at: str | None = None
    last_sync_at: str | None = None
    error_message: str | None = None


class TestResult(BaseModel):
    """Result of a connection test."""
    success: bool
    latency_ms: int
    message: str


class ProviderInfo(BaseModel):
    """Information about an integration provider."""
    slug: str
    name: str
    category: str
    auth_type: str
    description: str | None = None
    docs_url: str | None = None
    logo_emoji: str | None = None
    required_fields: list[str]
    optional_fields: list[str]
    is_active: bool


class ProvidersResponse(BaseModel):
    """Grouped provider listing."""
    providers_by_category: dict[str, list[ProviderInfo]]


class SyncLogEntry(BaseModel):
    """A single sync log entry."""
    id: str
    event_type: str
    status: str
    message: str | None
    latency_ms: int | None
    created_at: str


class HealthSummary(BaseModel):
    """Health summary across all integrations."""
    total_connected: int
    total_disconnected: int
    total_errored: int
    last_sync_time: str | None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_owner_id(request: Request) -> str:
    """Extract owner_id from JWT token payload."""
    payload = getattr(request.state, "token_payload", {})
    owner_id = payload.get("sub") or payload.get("owner_id")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing owner_id")
    return owner_id


def _get_db() -> SupabaseService:
    """Get database service."""
    return SupabaseService()


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert timestamp fields to ISO strings."""
    if not row:
        return {}
    result = dict(row)
    for field in ["created_at", "updated_at", "last_tested_at", "last_sync_at"]:
        if field in result and result[field]:
            val = result[field]
            # Already string? return as-is
            if isinstance(val, str):
                result[field] = val
            else:
                # Try to convert to ISO string
                try:
                    result[field] = str(val)
                except Exception:
                    result[field] = None
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/providers", response_model=ProvidersResponse)
def list_providers() -> ProvidersResponse:
    """List all integration providers, grouped by category."""
    try:
        db = _get_db()
        rows = db.fetch_all("integration_providers", {"is_active": True})
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch providers: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    # Group by category
    by_category: dict[str, list[ProviderInfo]] = {}
    for row in rows:
        info = ProviderInfo(
            slug=row.get("slug", ""),
            name=row.get("name", ""),
            category=row.get("category", ""),
            auth_type=row.get("auth_type", ""),
            description=row.get("description"),
            docs_url=row.get("docs_url"),
            logo_emoji=row.get("logo_emoji"),
            required_fields=row.get("required_fields") or [],
            optional_fields=row.get("optional_fields") or [],
            is_active=row.get("is_active", True),
        )
        category = info.category
        if category not in by_category:
            by_category[category] = []
        by_category[category].append(info)

    return ProvidersResponse(providers_by_category=by_category)


@router.get("/status")
def get_integration_status(request: Request) -> list[dict[str, Any]]:
    """Get integration statuses for the current owner across all providers."""
    owner_id = _get_owner_id(request)
    try:
        db = _get_db()
        # Fetch all owner integrations
        rows = db.fetch_all("owner_integrations", {"owner_id": owner_id})
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch integration status: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    statuses = [
        {
            "slug": row.get("provider_slug", ""),
            "status": row.get("status", "disconnected"),
            "last_tested_at": row.get("last_tested_at"),
            "last_sync_at": row.get("last_sync_at"),
            "error_message": row.get("error_message"),
        }
        for row in rows
    ]

    return statuses


@router.post("/{provider_slug}/connect")
def connect_integration(provider_slug: str, payload: CredentialPayload, request: Request) -> dict[str, Any]:
    """Connect an integration by saving encrypted credentials."""
    owner_id = _get_owner_id(request)
    provider_slug = provider_slug.strip().lower()

    if not payload.credentials:
        raise HTTPException(status_code=400, detail="No credentials provided")

    try:
        db = _get_db()
        em = get_encryption_manager()
    except EncryptionError as error:
        logger.error("Encryption manager unavailable: %s", error)
        raise HTTPException(status_code=500, detail="Encryption unavailable") from error
    except DatabaseConnectionError as error:
        logger.error("Database unavailable: %s", error)
        raise HTTPException(status_code=503, detail="Database unavailable") from error

    # Store each credential encrypted
    stored_count = 0
    try:
        for field_name, value in payload.credentials.items():
            if not value:
                continue

            encrypted = em.encrypt(value)
            try:
                # Try to update if exists, otherwise insert
                db.delete_many(
                    "integration_credentials",
                    {"owner_id": owner_id, "provider_slug": provider_slug, "field_name": field_name},
                )
                db.insert_one(
                    "integration_credentials",
                    {
                        "owner_id": owner_id,
                        "provider_slug": provider_slug,
                        "field_name": field_name,
                        "encrypted_value": encrypted,
                    },
                )
                stored_count += 1
            except DatabaseConnectionError as error:
                logger.error("Failed to store credential for %s.%s: %s", provider_slug, field_name, error)
                raise

        # Mark integration as connected and log the event
        db.update_many(
            "owner_integrations",
            {"owner_id": owner_id, "provider_slug": provider_slug},
            {"status": "connected", "updated_at": "now()", "error_message": None},
        )

        # If row doesn't exist, insert it
        try:
            db.insert_one(
                "owner_integrations",
                {
                    "owner_id": owner_id,
                    "provider_slug": provider_slug,
                    "status": "connected",
                },
            )
        except DatabaseConnectionError:
            # Already exists, that's fine
            pass

        # Log the sync event
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="integration_connect",
            description=f"Connected {provider_slug} with {stored_count} credential(s)",
            metadata={"provider_slug": provider_slug, "credentials_count": stored_count},
        )

        return {
            "success": True,
            "provider_slug": provider_slug,
            "credentials_stored": stored_count,
            "message": f"Connected {provider_slug} integration",
        }

    except EncryptionError as error:
        logger.error("Encryption failed: %s", error)
        raise HTTPException(status_code=500, detail="Encryption failed") from error
    except DatabaseConnectionError as error:
        logger.error("Failed to connect integration: %s", error)
        raise HTTPException(status_code=503, detail="Database error") from error


@router.delete("/{provider_slug}/disconnect")
def disconnect_integration(provider_slug: str, request: Request) -> dict[str, Any]:
    """Disconnect an integration by removing all credentials."""
    owner_id = _get_owner_id(request)
    provider_slug = provider_slug.strip().lower()

    try:
        db = _get_db()
        # Delete all credentials for this integration
        db.delete_many(
            "integration_credentials",
            {"owner_id": owner_id, "provider_slug": provider_slug},
        )

        # Mark as disconnected
        db.update_many(
            "owner_integrations",
            {"owner_id": owner_id, "provider_slug": provider_slug},
            {"status": "disconnected", "updated_at": "now()", "error_message": None},
        )

        # Log the event
        db.log_activity(
            agent_id=None,
            owner_id=owner_id,
            action_type="integration_disconnect",
            description=f"Disconnected {provider_slug}",
            metadata={"provider_slug": provider_slug},
        )

        return {
            "success": True,
            "provider_slug": provider_slug,
            "message": f"Disconnected {provider_slug}",
        }

    except DatabaseConnectionError as error:
        logger.error("Failed to disconnect integration: %s", error)
        raise HTTPException(status_code=503, detail="Database error") from error


@router.post("/{provider_slug}/test", response_model=TestResult)
def test_integration(provider_slug: str, request: Request) -> TestResult:
    """Test connection to an integration by making a live API call."""
    owner_id = _get_owner_id(request)
    provider_slug = provider_slug.strip().lower()

    try:
        db = _get_db()
        em = get_encryption_manager()
    except (EncryptionError, DatabaseConnectionError) as error:
        logger.error("Failed to initialize test: %s", error)
        raise HTTPException(status_code=503, detail="Service unavailable") from error

    start_time = time.perf_counter()

    try:
        # Fetch credentials
        cred_rows = db.fetch_all(
            "integration_credentials",
            {"owner_id": owner_id, "provider_slug": provider_slug},
        )

        if not cred_rows:
            return TestResult(
                success=False,
                latency_ms=0,
                message=f"No credentials found for {provider_slug}",
            )

        # Decrypt credentials
        credentials: dict[str, str] = {}
        for row in cred_rows:
            try:
                decrypted = em.decrypt(row.get("encrypted_value", ""))
                credentials[row.get("field_name", "")] = decrypted
            except EncryptionError:
                return TestResult(
                    success=False,
                    latency_ms=0,
                    message="Failed to decrypt credentials",
                )

        # Provider-specific tests
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        success = False
        message = "Test not implemented"

        if provider_slug == "anthropic":
            success, message = _test_anthropic(credentials.get("api_key", ""))
        elif provider_slug == "twilio":
            success, message = _test_twilio(credentials)
        elif provider_slug == "openai":
            success, message = _test_openai(credentials.get("api_key", ""))
        elif provider_slug == "stripe":
            success, message = _test_stripe(credentials.get("secret_key", ""))
        else:
            # Generic test: just check that required fields exist
            provider_info = db.fetch_all("integration_providers", {"slug": provider_slug})
            if provider_info:
                required = provider_info[0].get("required_fields", []) or []
                has_all = all(field in credentials for field in required)
                success = has_all
                message = "All required fields present" if has_all else "Missing required fields"
            else:
                message = f"Unknown provider: {provider_slug}"

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # Log the test
        db.insert_one(
            "integration_sync_logs",
            {
                "owner_id": owner_id,
                "provider_slug": provider_slug,
                "event_type": "test",
                "status": "success" if success else "failure",
                "message": message,
                "latency_ms": latency_ms,
            },
        )

        # Update the integration status
        if success:
            db.update_many(
                "owner_integrations",
                {"owner_id": owner_id, "provider_slug": provider_slug},
                {"status": "connected", "last_tested_at": "now()", "error_message": None},
            )
        else:
            db.update_many(
                "owner_integrations",
                {"owner_id": owner_id, "provider_slug": provider_slug},
                {"status": "error", "last_tested_at": "now()", "error_message": message},
            )

        return TestResult(success=success, latency_ms=latency_ms, message=message)

    except DatabaseConnectionError as error:
        logger.error("Database error during test: %s", error)
        raise HTTPException(status_code=503, detail="Database error") from error


@router.get("/{provider_slug}/logs")
def get_sync_logs(provider_slug: str, request: Request) -> dict[str, Any]:
    """Get the last 20 sync log entries for an integration."""
    owner_id = _get_owner_id(request)
    provider_slug = provider_slug.strip().lower()

    try:
        db = _get_db()
        rows = db.fetch_all(
            "integration_sync_logs",
            {"owner_id": owner_id, "provider_slug": provider_slug},
        )
        # Sort by created_at descending and limit to 20
        sorted_rows = sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)[:20]

        logs = [
            SyncLogEntry(
                id=row.get("id", ""),
                event_type=row.get("event_type", ""),
                status=row.get("status", ""),
                message=row.get("message"),
                latency_ms=row.get("latency_ms"),
                created_at=str(row.get("created_at", "")),
            )
            for row in sorted_rows
        ]

        return {"provider_slug": provider_slug, "logs": logs}

    except DatabaseConnectionError as error:
        logger.error("Failed to fetch logs: %s", error)
        raise HTTPException(status_code=503, detail="Database error") from error


@router.get("/health")
def health_check(request: Request) -> dict[str, Any]:
    """Quick health summary across all configured integrations."""
    owner_id = _get_owner_id(request)

    try:
        db = _get_db()
        rows = db.fetch_all("owner_integrations", {"owner_id": owner_id})
    except DatabaseConnectionError as error:
        logger.error("Failed to fetch health: %s", error)
        raise HTTPException(status_code=503, detail="Database error") from error

    connected = sum(1 for r in rows if r.get("status") == "connected")
    disconnected = sum(1 for r in rows if r.get("status") == "disconnected")
    errored = sum(1 for r in rows if r.get("status") == "error")

    last_sync = None
    for row in rows:
        sync_at = row.get("last_sync_at")
        if sync_at:
            last_sync = str(sync_at)
            break

    summary = HealthSummary(
        total_connected=connected,
        total_disconnected=disconnected,
        total_errored=errored,
        last_sync_time=last_sync,
    )

    return summary.model_dump()


@router.get("/env-status")
def integration_env_status() -> dict[str, Any]:
    """Returns which integrations have env vars configured (no auth required).

    This powers the admin connections page — shows which services have
    API keys set in Railway Variables, regardless of DB state.
    """
    from config.settings import get_settings
    settings = get_settings()

    services = {
        "anthropic": {
            "name": "Claude (Anthropic)",
            "configured": settings.is_configured("anthropic_api_key"),
            "category": "AI Provider",
            "env_vars": ["ANTHROPIC_API_KEY"],
            "docs": "https://console.anthropic.com",
        },
        "groq": {
            "name": "Groq (Llama)",
            "configured": settings.is_configured("groq_api_key"),
            "category": "AI Provider",
            "env_vars": ["GROQ_API_KEY"],
            "docs": "https://console.groq.com",
        },
        "google_ai": {
            "name": "Google Gemini",
            "configured": settings.is_configured("google_ai_api_key"),
            "category": "AI Provider",
            "env_vars": ["GOOGLE_AI_API_KEY"],
            "docs": "https://aistudio.google.com/apikey",
        },
        "openai": {
            "name": "OpenAI GPT",
            "configured": settings.is_configured("openai_api_key"),
            "category": "AI Provider",
            "env_vars": ["OPENAI_API_KEY"],
            "docs": "https://platform.openai.com/api-keys",
        },
        "twilio": {
            "name": "Twilio",
            "configured": settings.is_configured("twilio_account_sid"),
            "category": "Communications",
            "env_vars": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
            "docs": "https://console.twilio.com",
        },
        "resend": {
            "name": "Resend",
            "configured": settings.is_configured("resend_api_key"),
            "category": "Communications",
            "env_vars": ["RESEND_API_KEY"],
            "docs": "https://resend.com/api-keys",
        },
        "stripe": {
            "name": "Stripe",
            "configured": settings.is_configured("stripe_secret_key"),
            "category": "Payments",
            "env_vars": ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"],
            "docs": "https://dashboard.stripe.com/apikeys",
        },
        "google_oauth": {
            "name": "Google OAuth",
            "configured": settings.is_configured("google_client_id"),
            "category": "Authentication",
            "env_vars": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
            "docs": "https://console.cloud.google.com",
        },
        "bland_ai": {
            "name": "Bland AI",
            "configured": settings.is_configured("bland_ai_api_key"),
            "category": "Communications",
            "env_vars": ["BLAND_AI_API_KEY"],
            "docs": "https://app.bland.ai",
        },
    }

    configured_count = sum(1 for s in services.values() if s["configured"])
    return {
        "services": services,
        "configured_count": configured_count,
        "total_count": len(services),
    }


# ---------------------------------------------------------------------------
# Provider-specific test helpers
# ---------------------------------------------------------------------------

def _test_anthropic(api_key: str) -> tuple[bool, str]:
    """Test Anthropic API connectivity."""
    if not api_key or not api_key.startswith("sk-ant"):
        return False, "Invalid or missing Anthropic API key"

    try:
        from integrations.anthropic_client import ask_claude
        response = ask_claude(
            system="You are a health check service.",
            prompt="Respond with 'healthy' and nothing else.",
        )
        return bool(response), "Connected to Anthropic API" if response else "No response from API"
    except Exception as error:
        return False, f"Anthropic API error: {str(error)[:100]}"


def _test_twilio(credentials: dict[str, str]) -> tuple[bool, str]:
    """Test Twilio API connectivity."""
    account_sid = credentials.get("account_sid", "")
    auth_token = credentials.get("auth_token", "")

    if not account_sid or not auth_token:
        return False, "Missing Twilio account SID or auth token"

    try:
        import twilio
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        account = client.api.accounts(account_sid).fetch()
        return bool(account), f"Connected to Twilio account {account_sid[:8]}..."
    except Exception as error:
        return False, f"Twilio error: {str(error)[:100]}"


def _test_openai(api_key: str) -> tuple[bool, str]:
    """Test OpenAI API connectivity."""
    if not api_key or not api_key.startswith("sk-"):
        return False, "Invalid or missing OpenAI API key"

    try:
        from integrations.openai_client import ask_gpt_mini
        response = ask_gpt_mini(
            system="You are a health check service.",
            prompt="Respond with 'healthy' and nothing else.",
        )
        return bool(response), "Connected to OpenAI API" if response else "No response from API"
    except Exception as error:
        return False, f"OpenAI API error: {str(error)[:100]}"


def _test_stripe(secret_key: str) -> tuple[bool, str]:
    """Test Stripe API connectivity."""
    if not secret_key or not secret_key.startswith("sk_"):
        return False, "Invalid or missing Stripe secret key"

    try:
        import stripe
        stripe.api_key = secret_key
        stripe.Account.retrieve()
        return True, "Connected to Stripe API"
    except Exception as error:
        return False, f"Stripe error: {str(error)[:100]}"
