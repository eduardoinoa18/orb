"""Registration, login, and onboarding routes for ORB."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
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
logger = logging.getLogger("orb.api.onboarding")

ADMIN_BOOTSTRAP_DB_ERROR = (
    "Database unavailable for admin bootstrap. "
    "Verify Railway backend variables SUPABASE_URL, SUPABASE_SERVICE_KEY, and SUPABASE_ANON_KEY, "
    "then redeploy the orb-platform service."
)


def _make_jwt(owner_id: str, email: str, role: str = "standard_user") -> str:
    """Issue a signed JWT for the given owner."""
    settings = get_settings()
    payload = {
        "sub": owner_id,
        "email": email,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def _resolve_role(email: str) -> str:
    """Determines the role for an email. master_owner gets unlimited access."""
    settings = get_settings()
    master_email = (settings.my_email or "").strip().lower()
    if master_email and email.strip().lower() == master_email:
        return "master_owner"
    return "standard_user"

_SESSIONS: dict[str, dict[str, Any]] = {}


def schema_readiness_ready() -> bool:
    payload = schema_readiness_payload()
    return bool(payload.get("ready"))


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    accept_terms: bool
    name: str | None = Field(default=None, min_length=1)


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
    email = str(payload.email)
    degraded_mode = False
    owner_name = (payload.name or "").strip() or "New Owner"

    try:
        password_hash = hash_password(payload.password)
        owner = _upsert_owner(
            owner_id,
            email,
            {
                "full_name": owner_name,
                "name": owner_name,
                "plan": "starter",
                "subscription_status": "trialing",
                "password_hash": password_hash,
            },
        )
    except Exception:
        # Keep registration unblocked even when a dependency degrades.
        logger.exception("Onboarding register degraded", extra={"email": email})
        degraded_mode = True
        owner = {
            "id": owner_id,
            "email": email,
            "full_name": owner_name,
            "name": owner_name,
            "plan": "starter",
            "subscription_status": "trialing",
        }

    _step_done(owner_id, "register", {"email": str(payload.email)})

    try:
        send_resend_email(
            to_email=str(payload.email),
            subject="I'm online and ready - your Commander",
            html=(
                "<p>Welcome to ORB.</p>"
                "<p>Your Commander is online and ready to coordinate your team.</p>"
                "<p>Next step: finish onboarding and send your first command.</p>"
            ),
        )
    except Exception:
        # Keep registration available even if outbound email provider fails.
        logger.exception("Welcome email failed for onboarding registration", extra={"email": str(payload.email)})

    role = _resolve_role(email)

    # If this is the master owner registering, upgrade their account immediately
    if role == "master_owner":
        try:
            db_conn = _db()
            if db_conn:
                db_conn.update_many("owners", {"id": owner_id}, {
                    "role": "master_owner",
                    "billing_exempt": True,
                    "plan": "full_team",
                    "subscription_status": "active",
                })
        except DatabaseConnectionError:
            pass

    token = _make_jwt(owner_id, email, role=role)

    return {
        "token": token,
        "owner_id": owner_id,
        "email": email,
        "role": role,
        "name": owner.get("full_name") or owner.get("name") or owner_name,
        "plan": "full_team" if role == "master_owner" else (owner.get("plan") or "starter"),
        "owner": owner,
        "next_step": "about_you",
        "message": "Account created. Verification step is stubbed for local mode.",
        "degraded": degraded_mode,
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
        raise HTTPException(status_code=503, detail="Database unavailable. Please try again later.")

    try:
        owners = db.fetch_all("owners", {"email": email})
    except DatabaseConnectionError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if not owners:
        record_failed_login(email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    owner = owners[0]
    stored_hash = str(owner.get("password_hash") or "")
    if not stored_hash or not verify_password(payload.password, stored_hash):
        record_failed_login(email)
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    clear_failed_logins(email)

    owner_id = str(owner.get("id") or "")
    role = _resolve_role(email)

    # Auto-mark master_owner in DB for billing bypass
    if role == "master_owner":
        try:
            db.update_many("owners", {"id": owner_id}, {
                "role": "master_owner",
                "billing_exempt": True,
                "plan": "full_team",
                "subscription_status": "active",
            })
        except DatabaseConnectionError:
            pass

    token = _make_jwt(owner_id, email, role=role)
    owner_name = str(owner.get("name") or owner.get("full_name") or "")

    return {
        "token": token,
        "owner_id": owner_id,
        "email": email,
        "name": owner_name,
        "plan": "full_team" if role == "master_owner" else str(owner.get("plan") or "starter"),
        "role": role,
    }

class PromotePayload(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(standard_user|admin|master_owner)$", default="admin")


@router.post("/promote")
def promote_user(payload: PromotePayload, request: Request) -> dict[str, Any]:
    """Promote any existing user to a new role. Caller must be master_owner."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization token required.")
    token_str = auth[7:]
    settings = get_settings()
    try:
        decoded = jwt.decode(token_str, settings.jwt_secret_key, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    if decoded.get("role") != "master_owner":
        raise HTTPException(status_code=403, detail="Only the master owner can promote users.")

    email = str(payload.email).strip().lower()
    db = _db()
    if not db:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    try:
        owners = db.fetch_all("owners", {"email": email})
        if not owners:
            raise HTTPException(status_code=404, detail=f"No user found with email {email}.")
        target_id = str(owners[0].get("id") or "")
        new_role = payload.role
        is_elevated = new_role in ("admin", "master_owner")
        update: dict[str, Any] = {"role": new_role}
        if is_elevated:
            update["billing_exempt"] = True
            update["plan"] = "full_team"
            update["subscription_status"] = "active"
        try:
            db.update_many("owners", {"id": target_id}, update)
        except DatabaseConnectionError:
            # Schema may not have all columns — fall back to role-only update
            db.update_many("owners", {"id": target_id}, {"role": new_role})
    except HTTPException:
        raise
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=503, detail="Failed to update user role.") from exc

    logger.info("User promoted", extra={"email": email, "role": payload.role})
    return {
        "email": email,
        "new_role": payload.role,
        "message": f"User {email} promoted to {payload.role}.",
    }


class AdminBootstrapPayload(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


@router.post("/admin-bootstrap")
def admin_bootstrap(payload: AdminBootstrapPayload) -> dict[str, Any]:
    """Create or reset the master owner account.
    
    Only works when the submitted email matches MY_EMAIL env var.
    No secret required because the email itself is the gate.
    Use this once to create your admin account in production.
    """
    settings = get_settings()
    master_email = (settings.my_email or "").strip().lower()
    email = str(payload.email).strip().lower()

    if not master_email or email != master_email:
        raise HTTPException(status_code=403, detail="Email does not match the configured master owner.")

    try:
        db = SupabaseService()
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=503, detail=ADMIN_BOOTSTRAP_DB_ERROR) from exc

    try:
        password_hash = hash_password(payload.password)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to hash password.") from exc

    owner_id = None
    last_error: Exception | None = None
    try:
        existing = db.fetch_all("owners", {"email": email})
        if existing:
            owner_id = str(existing[0].get("id") or "")
            update_variants = [
                {
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "billing_exempt": True,
                    "plan": "full_team",
                    "subscription_status": "active",
                },
                {
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "plan": "full_team",
                    "subscription_status": "active",
                },
                {
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "plan": "full_team",
                },
                {
                    "password_hash": password_hash,
                    "role": "master_owner",
                },
                {
                    "password_hash": password_hash,
                },
            ]
            updated = False
            for update_payload in update_variants:
                try:
                    db.update_many("owners", {"id": owner_id}, update_payload)
                    updated = True
                    break
                except DatabaseConnectionError as exc:
                    last_error = exc
            if not updated:
                raise last_error or DatabaseConnectionError("Failed to update owner in database.")
        else:
            from uuid import uuid4 as _uuid4
            owner_id = str(_uuid4())
            insert_variants = [
                {
                    "id": owner_id,
                    "email": email,
                    "full_name": "Master Owner",
                    "name": "Master Owner",
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "billing_exempt": True,
                    "plan": "full_team",
                    "subscription_status": "active",
                },
                {
                    "id": owner_id,
                    "email": email,
                    "name": "Master Owner",
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "plan": "full_team",
                    "subscription_status": "active",
                },
                {
                    "id": owner_id,
                    "email": email,
                    "password_hash": password_hash,
                    "role": "master_owner",
                    "plan": "full_team",
                },
                {
                    "id": owner_id,
                    "email": email,
                    "password_hash": password_hash,
                    "role": "master_owner",
                },
                {
                    "id": owner_id,
                    "email": email,
                    "password_hash": password_hash,
                },
            ]
            inserted = False
            for insert_payload in insert_variants:
                try:
                    db.insert_one("owners", insert_payload)
                    inserted = True
                    break
                except DatabaseConnectionError as exc:
                    last_error = exc
            if not inserted:
                raise last_error or DatabaseConnectionError("Failed to create owner in database.")
    except DatabaseConnectionError as exc:
        reason = str(exc)[:180]
        raise HTTPException(status_code=503, detail=f"{ADMIN_BOOTSTRAP_DB_ERROR} Reason: {reason}") from exc

    token = _make_jwt(owner_id, email, role="master_owner")
    return {
        "token": token,
        "owner_id": owner_id,
        "email": email,
        "role": "master_owner",
        "plan": "full_team",
        "message": "Admin account created/updated. You can now login normally.",
    }
