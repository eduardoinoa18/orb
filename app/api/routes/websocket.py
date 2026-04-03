"""WebSocket routes for live dashboard updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("orb.websocket")
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Tracks connected dashboard websocket clients."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            current = list(self.active_connections)

        for connection in current:
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)

        if dead:
            async with self._lock:
                for connection in dead:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)


manager = ConnectionManager()


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket, owner_id: str | None = None) -> None:
    """Dashboard websocket endpoint for live office updates."""
    await manager.connect(websocket)
    await manager.broadcast({
        "type": "presence",
        "message": "dashboard client connected",
        "owner_id": owner_id or "",
    })
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception as exc:
        logger.warning("dashboard websocket disconnected with error: %s", exc)
        await manager.disconnect(websocket)
