"""Registration, login, and onboarding routes for ORB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from jose import jwt

from agents.identity.provisioner import provision_agent
from app.api.routes import billing
from app.database.connection import DatabaseConnectionError, SupabaseService
from app.database.schema_readiness import schema_readiness_payload
from config.settings import get_settings
from integrations.auth_utils import (
    hash_password,
    verify_password,
    record_failed_login,
    is_locked_out,
    clear_failed_logins,
)
from integrations.resend_client import send_resend_email

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _make_jwt(owner_id: str, email: str) -> str:
    """Issue a signed JWT for the given owner."""
    settings = get_settings()
    payload = {
        "sub": owner_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

_SESSIONS: dict[str, dict[str, Any]] = {}


def schema_readiness_ready() -> bool:
    payload = schema_readiness_payload()
    return bool(payload.get("ready"))


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    accept_terms: bool


class AboutPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    first_name: str = Field(min_length=1)
    industry: str = Field(min_length=2)
    business_name: str = Field(min_length=1)


class CommanderPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    commander_name: str = Field(min_length=1)
    personality_style: str = Field(default="professional")


class PlanPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    plan: str = Field(pattern="^(starter|professional|full_team)$")
    billing: str = Field(pattern="^(monthly|annual)$", default="monthly")
    trial: bool = True


class FirstAgentPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    agent_name: str = Field(min_length=2)
    role: str = Field(min_length=2)
    owner_phone_number: str | None = None


class ConnectToolPayload(BaseModel):
    owner_id: str = Field(min_length=2)
    tool_key: str = Field(pattern="^(google|stripe|twilio|supabase|none)$")
    connection_mode: str = Field(pattern="^(oauth|api_key|skip)$", default="skip")


def _db() -> SupabaseService | None:
    try:
        return SupabaseService()
    except DatabaseConnectionError:
        return None


def _upsert_owner(owner_id: str, email: str, updates: dict[str, Any]) -> dict[str, Any]:
    db = _db()
    base = {
        "id": owner_id,
        "email": email,
        "full_name": updates.get("full_name") or updates.get("first_name") or "New Owner",
        "name": updates.get("first_name") or "New Owner",
        "plan": updates.get("plan") or "starter",
    }
    if not db:
        return {**base, **updates}

    variants = [
        {"id": owner_id, "email": email, "full_name": base["full_name"], "plan": base["plan"]},
        {"id": owner_id, "email": email, "name": base["name"]},
        {"id": owner_id, "email": email},
    ]

    rows = []
    try:
        rows = db.fetch_all("owners", {"id": owner_id})
    except DatabaseConnectionError:
        pass

    if rows:
        try:
            db.update_many("owners", {"id": owner_id}, updates)
        except DatabaseConnectionError:
            pass
        return {**rows[0], **updates}

    for payload in variants:
        try:
            created = db.insert_one("owners", payload)
            if updates:
                try:
                    db.update_many("owners", {"id": owner_id}, updates)
                except DatabaseConnectionError:
                    pass
            return {**created, **updates}
        except DatabaseConnectionError:
            continue

    return {**base, **updates}


def _session(owner_id: str) -> dict[str, Any]:
    session = _SESSIONS.setdefault(owner_id, {"owner_id": owner_id, "steps": {}})
    return session


def _step_done(owner_id: str, step: str, payload: dict[str, Any] | None = None) -> None:
    session = _session(owner_id)
    session["steps"][step] = {
        "done": True,
        "at": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }


@router.post("/register")
def onboarding_register(payload: RegisterPayload) -> dict[str, Any]:
    if not payload.accept_terms:
        raise HTTPException(status_code=400, detail="You must accept terms before creating an account.")

    owner_id = str(uuid4())
    password_hash = hash_password(payload.password)
    owner = _upsert_owner(
        owner_id,
        str(payload.email),
        {
            "plan": "starter",
            "subscription_status": "trialing",
            "password_hash": password_hash,
        },
    )
    _step_done(owner_id, "register", {"email": str(payload.email)})

    send_resend_email(
        to_email=str(payload.email),
        subject="I'm online and ready - your Commander",
        html=(
            "<p>Welcome to ORB.</p>"
            "<p>Your Commander is online and ready to coordinate your team.</p>"
            "<p>Next step: finish onboarding and send your first command.</p>"
        ),
    )

    return {
        "owner_id": owner_id,
        "owner": owner,
        "next_step": "about_you",
        "message": "Account created. Verification step is stubbed for local mode.",
    }


@router.post("/about")
def onboarding_about(payload: AboutPayload) -> dict[str, Any]:
    updates = {
        "full_name": payload.first_name,
        "name": payload.first_name,
        "business_name": payload.business_name,
        "industry": payload.industry,
    }
    owner = _upsert_owner(payload.owner_id, f"{payload.owner_id}@example.com", updates)
    _step_done(payload.owner_id, "about_you", payload.model_dump())
    return {"owner_id": payload.owner_id, "owner": owner, "next_step": "commander"}


@router.post("/commander")
def onboarding_commander(payload: CommanderPayload) -> dict[str, Any]:
    db = _db()
    if db:
        try:
            rows = db.fetch_all("commander_config", {"owner_id": payload.owner_id})
            body = {
                "owner_id": payload.owner_id,
                "commander_name": payload.commander_name,
                "personality_style": payload.personality_style,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if rows:
                db.update_many("commander_config", {"owner_id": payload.owner_id}, body)
            else:
                db.insert_one("commander_config", body)
        except DatabaseConnectionError:
            pass

    _step_done(payload.owner_id, "commander", payload.model_dump())
    return {
        "owner_id": payload.owner_id,
        "commander_name": payload.commander_name,
        "next_step": "plan",
        "preview": f"Good morning, I'm {payload.commander_name}. I'll coordinate your AI team and keep you informed.",
    }


@router.post("/plan")
def onboarding_plan(payload: PlanPayload) -> dict[str, Any]:
    _step_done(payload.owner_id, "plan", payload.model_dump())
    _upsert_owner(payload.owner_id, f"{payload.owner_id}@example.com", {"plan": payload.plan, "subscription_plan": payload.plan})

    if payload.trial:
        return {
            "owner_id": payload.owner_id,
            "plan": payload.plan,
            "trial": True,
            "next_step": "first_agent",
            "message": "Trial started. No card required yet.",
        }

    checkout = billing.create_checkout(
        billing.CheckoutPayload(
            owner_id=payload.owner_id,
            plan=payload.plan,
            billing=payload.billing,
            trial_days=0,
        )
    )
    return {
        "owner_id": payload.owner_id,
        "plan": payload.plan,
        "trial": False,
        "checkout": checkout,
        "next_step": "stripe_checkout",
    }


@router.post("/first-agent")
def onboarding_first_agent(payload: FirstAgentPayload) -> dict[str, Any]:
    result = provision_agent(
        owner_id=payload.owner_id,
        agent_name=payload.agent_name,
        role=payload.role,
        brain_provider="claude",
        owner_phone_number=payload.owner_phone_number,
    )
    _step_done(payload.owner_id, "first_agent", payload.model_dump())
    return {
        "owner_id": payload.owner_id,
        "provisioning": result,
        "next_step": "connect_tool",
        "command_center_path": f"/dashboard?owner_id={payload.owner_id}",
    }


@router.get("/status/{owner_id}")
def onboarding_status(owner_id: str) -> dict[str, Any]:
    session = _session(owner_id)
    return {
        "owner_id": owner_id,
        "steps": session.get("steps", {}),
        "completed_count": len(session.get("steps", {})),
    }


@router.post("/connect-tool")
def onboarding_connect_tool(payload: ConnectToolPayload) -> dict[str, Any]:
    if payload.tool_key != "none" and payload.connection_mode != "skip" and not schema_readiness_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "Database schema is not ready for integration onboarding. "
                "Run scripts/setup_database.py --strict and apply scripts/database_migration_patch.sql."
            ),
        )

    _step_done(payload.owner_id, "connect_tool", payload.model_dump())

    db = _db()
    if db and payload.tool_key != "none":
        try:
            db.insert_one(
                "owner_integrations",
                {
                    "owner_id": payload.owner_id,
                    "integration_key": payload.tool_key,
                    "status": "connected" if payload.connection_mode != "skip" else "pending",
                    "connection_mode": payload.connection_mode,
                    "connected_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except DatabaseConnectionError:
            pass

    _upsert_owner(
        payload.owner_id,
        f"{payload.owner_id}@example.com",
        {
            "onboarding_status": "completed",
            "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "owner_id": payload.owner_id,
        "connected_tool": payload.tool_key,
        "connection_mode": payload.connection_mode,
        "completed": True,
        "next_step": "dashboard",
        "command_center_path": f"/dashboard?owner_id={payload.owner_id}",
    }


# ---------------------------------------------------------------------------
# Login — returns JWT token + owner_id
# ---------------------------------------------------------------------------

class LoginPayload(BaseModel):
    email: EmailStr
    password: str


@router.post("/login")
def onboarding_login(payload: LoginPayload) -> dict[str, Any]:
    """Authenticate owner with email + password; return JWT + owner_id."""
    email = str(payload.email).lower().strip()

    # Brute-force protection
    if is_locked_out(email):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Please wait 15 minutes and try again.",
        )

    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable. Please try again shortly.")

    try:
        rows = db.fetch_all("owners", {"email": email})
    except DatabaseConnectionError:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    if not rows:
        record_failed_login(email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    owner = rows[0]
    stored_hash = owner.get("password_hash") or ""

    if not stored_hash:
        # Owner registered before password support — allow login, prompt to set password
        raise HTTPException(
            status_code=401,
            detail="Account requires password reset. Please re-register or contact support.",
        )

    if not verify_password(payload.password, stored_hash):
        record_failed_login(email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    clear_failed_logins(email)
    owner_id = str(owner["id"])
    token = _make_jwt(owner_id, email)

    return {
        "token": token,
        "owner_id": owner_id,
        "email": email,
        "name": owner.get("full_name") or owner.get("name") or "",
        "plan": owner.get("plan") or "starter",
        "message": "Login successful.",
    }
