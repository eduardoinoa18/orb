"""Helpers for broadcasting live dashboard activity events."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.api.routes.websocket import manager

_AGENT_COLORS = {
    "rex": "#14b8a6",
    "aria": "#8b5cf6",
    "nova": "#ff6b6b",
    "orion": "#f59e0b",
    "sage": "#3b82f6",
    "atlas": "#22c55e",
}


def _agent_color_from_name(agent_name: str | None) -> str:
    key = (agent_name or "").strip().lower()
    return _AGENT_COLORS.get(key, "#185FA5")


async def broadcast_agent_action(
    agent_id: str,
    agent_name: str,
    action_type: str,
    message: str,
    outcome: str | None = None,
    agent_color: str | None = None,
) -> None:
    """Broadcast an agent action to all connected dashboard clients."""
    await manager.broadcast(
        {
            "type": "agent_action",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "action_type": action_type,
            "message": message,
            "outcome": outcome,
            "agent_color": agent_color or _agent_color_from_name(agent_name),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def dispatch_agent_action(
    agent_id: str,
    agent_name: str,
    action_type: str,
    message: str,
    outcome: str | None = None,
    agent_color: str | None = None,
) -> None:
    """Dispatch websocket broadcast from sync or async contexts."""
    coroutine = broadcast_agent_action(
        agent_id=agent_id,
        agent_name=agent_name,
        action_type=action_type,
        message=message,
        outcome=outcome,
        agent_color=agent_color,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coroutine)
        return

    loop.create_task(coroutine)
