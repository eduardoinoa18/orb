"""Personal agent provisioning for Eduardo.
Run once: python scripts/provision_my_agents.py
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import get_supabase_client

BASE = "http://localhost:8000"
MY_EMAIL = "owner@example.com"
MY_NAME = "Eduardo"
MY_PHONE_NUMBER = os.getenv("MY_PHONE_NUMBER", "")

AGENTS = [
    {"agent_name": "Max", "role": "commander", "brain_provider": "claude"},
    {"agent_name": "Rex", "role": "sales", "brain_provider": "claude"},
    {"agent_name": "Aria", "role": "assistant", "brain_provider": "claude"},
    {"agent_name": "Nova", "role": "marketing", "brain_provider": "claude"},
    {"agent_name": "Orion", "role": "research", "brain_provider": "claude"},
    {"agent_name": "Sage", "role": "platform", "brain_provider": "claude"},
    {"agent_name": "Atlas", "role": "developer", "brain_provider": "claude"},
]


def _load_dotenv_phone() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MY_PHONE_NUMBER="):
            return line.split("=", 1)[1].strip()
    return ""


async def _create_or_get_owner(client: httpx.AsyncClient) -> str:
    db = get_supabase_client()
    existing = db.table("owners").select("id,email").eq("email", MY_EMAIL).limit(1).execute()
    if existing.data:
        return str(existing.data[0]["id"])

    payload = {
        "email": MY_EMAIL,
        "password": f"Temp#{secrets.token_hex(6)}A1!",
        "accept_terms": True,
    }
    register = await client.post(f"{BASE}/onboarding/register", json=payload)
    register.raise_for_status()
    owner_id = str(register.json().get("owner_id") or "")
    if not owner_id:
        raise RuntimeError("Owner creation failed: no owner_id returned from /onboarding/register")

    # Set owner details so downstream phone-based alerts can work immediately.
    about_payload = {
        "owner_id": owner_id,
        "first_name": MY_NAME,
        "industry": "real_estate",
        "business_name": "Eduardo Ventures",
    }
    about = await client.post(f"{BASE}/onboarding/about", json=about_payload)
    about.raise_for_status()
    return owner_id


def _upgrade_owner_plan_for_team(owner_id: str) -> None:
    db = get_supabase_client()
    variants = [
        {"plan": "team", "subscription_plan": "full_team", "subscription_status": "active"},
        {"plan": "team", "subscription_status": "active"},
        {"plan": "team"},
    ]
    for payload in variants:
        try:
            db.table("owners").update(payload).eq("id", owner_id).execute()
            return
        except Exception:
            continue


async def provision() -> None:
    phone = MY_PHONE_NUMBER or _load_dotenv_phone()
    timeout = httpx.Timeout(60.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        owner_id = await _create_or_get_owner(client)
        _upgrade_owner_plan_for_team(owner_id)
        print(f"Owner ID: {owner_id}")

        provisioned = 0
        for agent in AGENTS:
            payload: dict[str, Any] = {
                "owner_id": owner_id,
                "agent_name": agent["agent_name"],
                "role": agent["role"],
                "brain_provider": agent["brain_provider"],
            }
            if phone:
                payload["owner_phone_number"] = phone

            response = await client.post(f"{BASE}/agents/provision", json=payload)
            if response.status_code >= 400:
                detail = ""
                try:
                    detail = str(response.json().get("detail") or "")
                except Exception:
                    detail = response.text
                print(f"Provision failed: {agent['agent_name']} -> {response.status_code} {detail}")
                continue

            data = response.json()
            provisioned += 1
            print(f"Provisioned: {agent['agent_name']}")
            if data.get("phone"):
                print(f"  Phone: {data['phone']}")
            if data.get("email"):
                print(f"  Email: {data['email']}")

    if provisioned == len(AGENTS):
        print("\nAll agents online! You're ready.")
    else:
        print(f"\nProvisioned {provisioned}/{len(AGENTS)} agents. See failures above.")


if __name__ == "__main__":
    asyncio.run(provision())
