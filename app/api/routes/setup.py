"""Setup Wizard API — Module 2, Step Z2.

Zero-code setup endpoints that allow a non-technical owner to configure
the platform from the browser without touching .env files.

Endpoints:
    GET  /setup/status                — Is setup complete?
    POST /setup/save-key              — Save an encrypted API key
    POST /setup/test-key              — Test a saved or provided key
    POST /setup/provision-first-agent — Trigger identity provisioning for agent #1
    GET  /setup/categories            — List available key categories
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.database.settings_store import SettingsStore
from app.database.schema_readiness import schema_readiness_payload
from app.runtime.execution_readiness import owner_execution_readiness
from app.runtime.preflight import build_preflight_report

logger = logging.getLogger("orb.setup")

router = APIRouter(prefix="/setup", tags=["setup"])


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class SaveKeyRequest(BaseModel):
    key_name: str = Field(..., min_length=2, max_length=100,
                          description="Logical name, e.g. 'anthropic_api_key'")
    value: str = Field(..., min_length=1, max_length=5000)
    description: str = Field(default="", max_length=300)
    category: str = Field(default="general", max_length=50)
    owner_id: str = Field(default="", max_length=200)


class TestKeyRequest(BaseModel):
    key_name: str = Field(..., min_length=2, max_length=100)
    value: str = Field(default="", max_length=5000,
                       description="Leave empty to test the stored value")


class ProvisionFirstAgentRequest(BaseModel):
    owner_id: str = Field(..., min_length=1, max_length=200)
    agent_name: str = Field(default="Rex", max_length=100)
    role: str = Field(default="sales_agent", max_length=100)
    owner_phone_number: str = Field(default="", max_length=20)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status")
def setup_status() -> dict[str, Any]:
    """Return setup completion status.

    Checks whether the minimum required keys are present in platform_settings.
    Returns a checklist the setup wizard can render step-by-step.
    """
    required_keys = [
        "anthropic_api_key",
        "openai_api_key",
        "twilio_account_sid",
        "twilio_auth_token",
    ]
    results: dict[str, bool] = {}
    try:
        store = SettingsStore()
        for key in required_keys:
            results[key] = bool(store.get(key))
    except Exception as exc:
        logger.warning("setup_status: DB unavailable: %s", exc)
        # DB not yet configured — nothing is set up
        results = {k: False for k in required_keys}

    completed = all(results.values())
    return {
        "setup_complete": completed,
        "steps_completed": sum(1 for v in results.values() if v),
        "total_steps": len(required_keys),
        "checklist": results,
    }


@router.get("/categories")
def list_categories() -> dict[str, Any]:
    """Return the available key categories with descriptions for the UI."""
    categories = [
        {"id": "ai", "label": "AI / Brain", "description": "Anthropic, OpenAI API keys"},
        {"id": "communications", "label": "Communications", "description": "Twilio, Bland AI keys"},
        {"id": "database", "label": "Database", "description": "Supabase connection strings"},
        {"id": "market_data", "label": "Market Data", "description": "Alpha Vantage, MarketAux keys"},
        {"id": "google", "label": "Google", "description": "Google OAuth credentials"},
        {"id": "general", "label": "General", "description": "Other platform settings"},
    ]
    return {"categories": categories}


@router.get("/schema-readiness")
def setup_schema_readiness() -> dict[str, Any]:
    """Return DB schema readiness checks used by setup wizard and onboarding gates."""
    return schema_readiness_payload()


@router.get("/preflight")
def setup_preflight() -> dict[str, Any]:
    """Return full platform preflight readiness including blockers and warnings."""
    return build_preflight_report()


@router.get("/core-values")
def setup_core_values() -> dict[str, Any]:
    """Return simplified core-values scorecard and recommendations for operators."""
    report = build_preflight_report()
    return {
        "north_star": report.get("core_values", {}).get("north_star"),
        "overall": report.get("core_values", {}).get("overall"),
        "scores": report.get("core_values", {}).get("scores", {}),
        "recommendations": report.get("core_values", {}).get("recommendations", []),
        "signals": report.get("core_values", {}).get("signals", {}),
        "preflight_ready": report.get("ready", False),
        "preflight_score": report.get("score", 0),
    }


@router.get("/execution-readiness/{owner_id}")
def setup_execution_readiness(owner_id: str) -> dict[str, Any]:
    """Return owner-specific readiness for real-world agent execution."""
    readiness = owner_execution_readiness(owner_id=owner_id)
    return {
        "owner_id": owner_id,
        "ready": readiness.get("ready", False),
        "score": readiness.get("score", 0),
        "identity": readiness.get("identity", {}),
        "integrations": readiness.get("integrations", {}),
        "tool_execution": readiness.get("tool_execution", {}),
        "blockers": readiness.get("blockers", []),
        "warnings": readiness.get("warnings", []),
    }


@router.post("/save-key")
def save_key(payload: SaveKeyRequest) -> dict[str, Any]:
    """Encrypt and save an API key to the platform settings store.

    The raw key is never retained after this request.
    Returns the key metadata (not the value).
    """
    try:
        store = SettingsStore()
        result = store.save(
            key=payload.key_name,
            value=payload.value,
            description=payload.description,
            category=payload.category,
            owner_id=payload.owner_id,
        )
        return {
            "saved": True,
            "key_name": payload.key_name,
            "category": payload.category,
            "id": result.get("id", ""),
            "message": f"'{payload.key_name}' encrypted and saved successfully.",
        }
    except Exception as exc:
        logger.error("setup /save-key error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to save key: {exc}") from exc


@router.post("/test-key")
def test_key(payload: TestKeyRequest) -> dict[str, Any]:
    """Test a saved key by making a live API call to the target service.

    If *value* is provided, it is tested directly (not persisted).
    If *value* is empty, the stored key is used.
    """
    try:
        store = SettingsStore()

        if payload.value:
            # Test the provided raw value without saving it first
            if "anthropic" in payload.key_name.lower() or payload.value.startswith("sk-ant"):
                result = store._test_anthropic(payload.value)
            else:
                result = {
                    "valid": True,
                    "service": payload.key_name,
                    "note": "Format looks valid but live test not available for this service type.",
                    "error": None,
                }
        else:
            result = store.test_connection_to_ai(payload.key_name)

        return result
    except Exception as exc:
        logger.error("setup /test-key error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Test failed: {exc}") from exc


@router.post("/provision-first-agent")
def provision_first_agent(payload: ProvisionFirstAgentRequest) -> dict[str, Any]:
    """Run the identity provisioner to create the owner's first AI agent.

    This is the final step of the setup wizard.  After this succeeds,
    the owner can use the dashboard to interact with their agent.
    """
    try:
        from agents.identity.provisioner import provision_agent
        result = provision_agent(
            owner_id=payload.owner_id,
            agent_name=payload.agent_name,
            role=payload.role,
            brain_provider="claude",
            owner_phone_number=payload.owner_phone_number or None,
        )
        return {
            "provisioned": True,
            "agent_name": payload.agent_name,
            "owner_id": payload.owner_id,
            "result": result,
            "message": f"{payload.agent_name} is ready. Head to the dashboard to meet your agent.",
        }
    except Exception as exc:
        logger.error("setup /provision-first-agent error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Agent provisioning failed: {exc}") from exc
