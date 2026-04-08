"""Short-lived secure action tokens with replay protection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt

from config.settings import get_settings

_CONSUMED_JTI: dict[str, datetime] = {}


def _purge_expired() -> None:
    now = datetime.now(timezone.utc)
    expired = [key for key, exp in _CONSUMED_JTI.items() if exp <= now]
    for key in expired:
        _CONSUMED_JTI.pop(key, None)


def create_action_token(owner_id: str, action: str, payload: dict[str, Any], ttl_minutes: int = 30) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=max(1, ttl_minutes))
    claims = {
        "sub": owner_id,
        "act": action,
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "payload": payload,
    }
    return jwt.encode(claims, get_settings().jwt_secret_key, algorithm="HS256")


def verify_and_consume_action_token(token: str, expected_action: str | None = None) -> dict[str, Any]:
    _purge_expired()
    try:
        claims = jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
    except JWTError as error:
        raise ValueError("Invalid or expired action token.") from error

    action = str(claims.get("act") or "").strip()
    if expected_action and action != expected_action:
        raise ValueError("Action token does not match expected action.")

    jti = str(claims.get("jti") or "").strip()
    exp_ts = int(claims.get("exp") or 0)
    if not jti or not exp_ts:
        raise ValueError("Malformed action token.")

    if jti in _CONSUMED_JTI:
        raise ValueError("Action token has already been used.")

    _CONSUMED_JTI[jti] = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
    return {
        "owner_id": str(claims.get("sub") or ""),
        "action": action,
        "payload": claims.get("payload") or {},
    }
